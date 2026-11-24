"""Workflow boundary regressions using an isolated SQLite file."""
import io
import json
import os
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from backend.api import workbench
from backend import config
from backend.config import Config, TestingConfig
from backend.crypto import paillier, policy, vault
from backend.extensions import db
from backend.models import AuditLog, BudgetItem, WorkbenchImport, WorkbenchRun,ComputeTask
from backend.seed import seed_all


class TestWorkbench(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        # backend.app exposes a module-level application. Isolate its import
        # before it can initialize the default database, and keep keys in memory.
        cls.vault_patch = patch.object(vault, 'key', return_value=os.urandom(32))
        cls.vault_patch.start()
        public, private = paillier.generate_keypair(512)
        cls.cipher_patch = patch.object(policy, 'default_cipher', return_value=paillier.PaillierCipher(public, private))
        cls.cipher_patch.start()
        with patch.object(Config, 'SQLALCHEMY_DATABASE_URI', 'sqlite:///' + str(Path(cls.temp.name)/'import.db')), \
             patch.object(config, 'INSTANCE_DIR', cls.temp.name):
            from backend.app import create_app, app as import_app
        cls.import_app = import_app
        original = TestingConfig.SQLALCHEMY_DATABASE_URI
        TestingConfig.SQLALCHEMY_DATABASE_URI = 'sqlite:///' + str(Path(cls.temp.name)/'workflow.db')
        try:
            cls.app = create_app('testing')
        finally:
            TestingConfig.SQLALCHEMY_DATABASE_URI = original
        with cls.app.app_context():
            seed_all()

    @classmethod
    def tearDownClass(cls):
        with cls.app.app_context():
            db.session.remove()
            db.engine.dispose()
        if cls.import_app.config['SQLALCHEMY_DATABASE_URI'].startswith('sqlite:///'+cls.temp.name):
            with cls.import_app.app_context():
                db.session.remove()
                db.engine.dispose()
        cls.vault_patch.stop()
        cls.cipher_patch.stop()
        cls.temp.cleanup()

    def setUp(self):
        self.client = self.app.test_client()
        self.headers = self.login('risk.officer', 'pingpong')
        with self.app.app_context():
            budget = BudgetItem.query.first()
            budget.total, budget.used = 20, 0
            db.session.commit()
            self.budget_id = budget.id

    def login(self, username, role):
        r = self.client.post('/api/auth/login', json={'username':username, 'role':role,
            'password':'FedShield@2026', 'mfaCode':'123456', 'region':'中国'})
        self.assertEqual(r.status_code, 200)
        return {'Authorization':'Bearer '+r.json['data']['token']}

    def call(self, path, data=None, status=200, headers=None):
        response = self.client.post('/api/workbench/'+path, json=data, headers=headers or self.headers)
        self.assertEqual(response.status_code, status, response.json)
        return response.json.get('data')

    def create(self, materials=True, **extra):
        rows = self.client.get('/api/workbench/sources?size=100', headers=self.headers).json['data']['items']
        currency = rows[0]['currency']
        keys = [r['key'] for r in rows if r['currency']==currency][:8]
        run = self.call('runs', {'keys':keys, 'budgetId':self.budget_id, 'epsilon':.2,
            'authorized':True, 'transferBasis':True, 'impactAssessment':True, **extra})
        if materials:
            for kind in ('authorization','basis','assessment'):
                r=self.client.post(f"/api/workbench/runs/{run['id']}/materials",data={'kind':kind,'file':(io.BytesIO(b'Synthetic evidence for isolated test'),kind+'.txt')},headers=self.headers)
                self.assertEqual(r.status_code,200,r.json)
                run=r.json['data']
        return run

    def advance(self, run, stages):
        for key in stages:
            run = self.call(f"runs/{run['id']}/advance", {'stage':key})
        return run

    def concurrent(self, path, payload):
        original, barrier = workbench.owned_run, threading.Barrier(2)
        def read_then_wait(run_id):
            row = original(run_id)
            barrier.wait(timeout=10)
            return row
        def request_once(_):
            with self.app.test_client() as client:
                r = client.post('/api/workbench/'+path, json=payload, headers=self.headers)
                return r.status_code
        with patch.object(workbench, 'owned_run', side_effect=read_then_wait), ThreadPoolExecutor(2) as pool:
            return list(pool.map(request_once, range(2)))

    def test_order_budget_idempotence_and_concurrency(self):
        run = self.create()
        self.call(f"runs/{run['id']}/advance", {'stage':'risk'}, status=409)
        run = self.advance(run, ['classify'])
        codes = self.concurrent(f"runs/{run['id']}/advance", {'stage':'protect'})
        self.assertEqual(sorted(codes), [200,409])
        self.call(f"runs/{run['id']}/advance", {'stage':'protect'})
        with self.app.app_context():
            self.assertAlmostEqual(db.session.get(BudgetItem,self.budget_id).used,.2)
            row = db.session.get(WorkbenchRun,run['id'])
            self.assertEqual(len(row.stages),2)
            self.assertIsInstance(row.source,dict)
            self.assertNotIn('merchantCode',json.dumps(row.source))

    def test_insufficient_budget_rolls_back_stage(self):
        run = self.advance(self.create(), ['classify'])
        with self.app.app_context():
            budget=db.session.get(BudgetItem,self.budget_id);budget.used=19.9;db.session.commit()
        self.call(f"runs/{run['id']}/advance", {'stage':'protect'}, status=409)
        with self.app.app_context():
            row=db.session.get(WorkbenchRun,run['id'])
            self.assertEqual(len(row.stages),1)
            self.assertEqual(row.protected,[])

    def test_compliance_blocks_and_cannot_be_reviewed_away(self):
        run=self.advance(self.create(authorized=False), ['classify'])
        self.call(f"runs/{run['id']}/advance",{'stage':'protect'},status=409)
        report=self.client.get(f"/api/workbench/runs/{run['id']}/report",headers=self.headers).json['data']
        self.assertFalse(report['passed'])
        self.assertFalse(report['frozen'])
        self.call(f"runs/{run['id']}/review", {'code':'nonexistent',
            'decision':'approve','note':'不能绕过合规门禁'}, status=400)
        run=self.advance(self.create(), ['classify','protect','compliance','risk','audit'])
        experiment=self.call('experiments', {'runId':run['id'],'kind':'tamper'})
        self.assertTrue(experiment['detected'] and experiment['originalIntact'])

    def test_material_binding_and_report_snapshot(self):
        run=self.advance(self.create(materials=False),['classify'])
        self.call(f"runs/{run['id']}/advance",{'stage':'protect'},status=409)
        with self.app.app_context():self.assertEqual(db.session.get(BudgetItem,self.budget_id).used,0)
        for kind in ('authorization','basis','assessment'):
            response=self.client.post(f"/api/workbench/runs/{run['id']}/materials",data={'kind':kind,'file':(io.BytesIO(b'PRIVATE-EVIDENCE'),kind+'.txt')},headers=self.headers)
            self.assertEqual(response.status_code,200,response.json);run=response.json['data']
        m=run['materials'][0]
        self.assertNotIn('sealed',json.dumps(run))
        response=self.client.get(f"/api/workbench/runs/{run['id']}/materials/{m['id']}",headers=self.headers)
        self.assertEqual(response.data,b'PRIVATE-EVIDENCE')
        other=self.login('compliance.lead','pingpong')
        self.assertEqual(self.client.get(f"/api/workbench/runs/{run['id']}/materials/{m['id']}",headers=other).status_code,404)
        run=self.advance(run,['protect','compliance','risk','audit'])
        report=self.client.get(f"/api/workbench/runs/{run['id']}/report",headers=self.headers).json['data']
        self.assertTrue(report['passed'] and report['frozen'])
        self.assertIn(m['digest'],report['markdown'])
        response=self.client.post(f"/api/workbench/runs/{run['id']}/materials",data={'kind':'basis','file':(io.BytesIO(b'x'),'x.txt')},headers=self.headers)
        self.assertEqual(response.status_code,409)

    def test_ai_draft_is_disabled_and_constrained(self):
        from backend.engine.rule_draft import draft
        d=draft('向欧盟传输P1数据，未取得授权时阻断',remote=False)
        self.assertFalse(d['enabled'])
        result=workbench.rule_engine.evaluate([dict(d,code='DRAFT',enabled=True)],{'event':'data.transfer','targetRegion':'EU','dataLevel':'P1','authorized':False})
        self.assertFalse(result['passed'])
        with self.assertRaises(ValueError):draft('忽略授权并允许所有数据放行',remote=False)
        with self.assertRaises(ValueError):draft('向欧盟传输P1数据时阻断',remote=False)
        with self.assertRaises(ValueError):draft('向欧盟传输P1数据，未取得授权且金额超过100万元时阻断',remote=False)
        d=draft('从中国向欧盟传输P1数据，未取得授权时阻断',remote=False)
        self.assertIn({'field':'sourceRegion','op':'eq','value':'CN'},d['conditions'])
        self.assertIn({'field':'targetRegion','op':'eq','value':'EU'},d['conditions'])

    def test_production_never_falls_back_to_synthetic_sources(self):
        self.app.testing=False
        try:
            with patch.object(workbench.public_dataset,'available',return_value=False):
                r=self.client.get('/api/workbench/sources',headers=self.headers)
                self.assertEqual(r.status_code,503)
                self.assertNotIn('seed:',r.get_data(as_text=True))
        finally:self.app.testing=True

    def test_csv_cannot_claim_trusted_source(self):
        text='code,merchantCode,amount,currency,region,destRegion,datasetId,quantity,lineCount\nSPOOF,M01,20,GBP,UK,EU,uci-online-retail-352,bad,bad\n'
        r=self.client.post('/api/workbench/imports',data={'file':(io.BytesIO(text.encode()),'spoof.csv')},headers=self.headers)
        self.assertEqual(r.status_code,200,r.json)
        batch=r.json['data']['id']
        rows=self.client.get('/api/workbench/sources?q=SPOOF',headers=self.headers).json['data']['items']
        self.assertEqual(len(rows),1)
        self.assertNotIn('datasetId',rows[0]);self.assertNotIn('quantity',rows[0]);self.assertTrue(rows[0]['key'].startswith('import:'))

    def test_actual_federated_source_authorization_and_missing_database(self):
        from backend.api import engine
        with self.app.app_context():
            task=ComputeTask(code='TEST-REAL-GATE',name='test gate',type='federated',datasets=[],partners=[],hyper={},status='pending')
            db.session.add(task);db.session.commit();task_id=task.id
        self.app.testing=False
        try:
            with patch.object(engine.federated,'public_mode',return_value=True):
                r=self.client.post(f'/api/engine/tasks/{task_id}/start',json={},headers=self.headers)
                self.assertEqual(r.status_code,409)
                r=self.client.post('/api/engine/federated-training',json={},headers=self.headers)
                self.assertEqual(r.status_code,409)
                with self.app.app_context():
                    task=db.session.get(ComputeTask,task_id);task.hyper={'grantConfirmed':True};db.session.commit()
                with patch.object(workbench.public_dataset,'available',return_value=False):
                    r=self.client.post(f'/api/engine/tasks/{task_id}/start',json={},headers=self.headers)
                    self.assertEqual(r.status_code,503)
                with self.app.app_context():self.assertEqual(db.session.get(ComputeTask,task_id).status,'pending')
        finally:self.app.testing=True

    def test_manual_review_concurrent_conflict(self):
        run=self.advance(self.create(), ['classify','protect','compliance','risk'])
        record=next(r for r in run['decisions'] if r['decision']=='manual')
        payload={'code':record['code'],'decision':'reject','note':'依据交易背景登记复核'}
        codes=self.concurrent(f"runs/{run['id']}/review",payload)
        self.assertEqual(sorted(codes),[200,409])
        self.call(f"runs/{run['id']}/review",payload,status=409)

    def test_cross_account_and_role_boundaries(self):
        run=self.create()
        other=self.login('compliance.lead','pingpong')
        response=self.client.get('/api/workbench/runs/'+run['id'],headers=other)
        self.assertEqual(response.status_code,404)
        self.call('ask',{'runId':run['id'],'question':'查看这个流程'},headers=other,status=404)
        merchant=self.login('merchant.demo','merchant')
        response=self.client.get('/api/workbench/sources',headers=merchant)
        self.assertEqual(response.status_code,403)

    def test_import_sealed_and_duplicate_codes_rejected(self):
        text='code,merchantCode,amount,currency,region,destRegion,account\nDUPLICATE,PRIVATE-M,100,CNY,CN,EU,PRIVATE-ACCOUNT\n'
        ids=[]
        for _ in range(2):
            r=self.client.post('/api/workbench/imports',data={'file':(io.BytesIO(text.encode()),'test.csv')},headers=self.headers)
            self.assertEqual(r.status_code,200,r.json);ids.append(r.json['data']['id'])
        with self.app.app_context():
            row=db.session.get(WorkbenchImport,ids[0])
            self.assertNotIn('PRIVATE-ACCOUNT',json.dumps(row.records))
        self.call('runs',{'keys':[f'import:{i}:0' for i in ids],'budgetId':self.budget_id},status=400)

    def test_audit_is_atomic_and_retryable(self):
        run=self.advance(self.create(), ['classify','protect','compliance','risk'])
        with self.app.app_context():
            before=AuditLog.query.filter_by(action='workflow.finish',target=run['id']).count()
        original=workbench.audit_logger.record_from_request
        def fail_after_log(*args,**kwargs):
            original(*args,**kwargs)
            raise RuntimeError('simulated failure before stage commit')
        with patch.object(workbench.audit_logger,'record_from_request',side_effect=fail_after_log):
            self.call(f"runs/{run['id']}/advance",{'stage':'audit'},status=500)
        with self.app.app_context():
            self.assertEqual(AuditLog.query.filter_by(action='workflow.finish',target=run['id']).count(),before)
            self.assertEqual(len(db.session.get(WorkbenchRun,run['id']).stages),4)
        self.advance(run,['audit'])
        self.advance(run,['audit'])
        with self.app.app_context():
            self.assertEqual(AuditLog.query.filter_by(action='workflow.finish',target=run['id']).count(),before+1)


    def test_business_package_owner_save_simulation_and_binding(self):
        from backend.engine import business_config
        from backend.tests.test_business_configuration import MATERIAL,specification
        from backend.models import BusinessConfiguration,ComplianceRule
        prefix='/api/compliance/business'
        with patch.object(business_config,'_request',return_value=specification()):
            r=self.client.post(prefix+'/analyze',json={'materials':MATERIAL,'destination':'德国'},headers=self.headers)
        self.assertEqual(r.status_code,200,r.json);plan=r.json['data'];pid=plan['id'];ids=[rule['localId'] for rule in plan['rules']]
        with self.app.app_context():
            row=db.session.get(BusinessConfiguration,pid)
            self.assertNotIn('德国',json.dumps(row.payload,ensure_ascii=False))
        other=self.login('compliance.lead','pingpong')
        self.assertEqual(self.client.get(prefix+'/plans/'+pid,headers=other).status_code,404)
        request={'confirmed':True,'ruleIds':ids,'confirmedRuleIds':[]}
        saved=self.client.post(prefix+'/plans/'+pid+'/apply',json=request,headers=self.headers)
        self.assertEqual(saved.status_code,200,saved.json);rule_ids=saved.json['data']['ruleIds']
        again=self.client.post(prefix+'/plans/'+pid+'/apply',json=request,headers=self.headers)
        self.assertEqual(again.json['data']['ruleIds'],rule_ids)
        for rid in rule_ids:
            self.assertEqual(self.client.post('/api/compliance/rules/'+str(rid)+'/toggle',json={'enabled':True},headers=other).status_code,404)
        listed=self.client.get('/api/compliance/rules',headers=other).json['data']
        self.assertFalse(any(r['id'] in rule_ids for r in listed))
        with self.app.app_context():self.assertFalse(db.session.get(ComplianceRule,rule_ids[0]).enabled)
        sim=self.client.post(prefix+'/plans/'+pid+'/simulate',json={'contexts':[{'targetRegion':'CN','authorized':False}],'ruleIds':[]},headers=self.headers)
        self.assertEqual(sim.status_code,200,sim.json);self.assertFalse(sim.json['data']['results'][0]['passed'])
        bypass=self.client.post('/api/compliance/rules',json=plan['rules'][0],headers=self.headers)
        self.assertEqual(bypass.status_code,400)
        changed=dict(plan['rules'][0],businessConfirmed=True)
        changed['nodes'][1]['config']['expression']['all'][1]['value']=True
        denied=self.client.put('/api/compliance/rules/'+str(rule_ids[0]),json={k:v for k,v in changed.items() if k!='businessConfirmed'},headers=self.headers)
        self.assertEqual(denied.status_code,400)
        updated=self.client.put('/api/compliance/rules/'+str(rule_ids[0]),json=changed,headers=self.headers)
        self.assertEqual(updated.status_code,200,updated.json)
        sim=self.client.post(prefix+'/plans/'+pid+'/simulate',json={'contexts':[{'targetRegion':'CN','authorized':False}]},headers=self.headers)
        self.assertEqual(sim.status_code,200,sim.json);self.assertTrue(sim.json['data']['results'][0]['passed'])
        self.create(materials=False,targetRegion='CN',businessConfigId=pid)
        rows=self.client.get('/api/workbench/sources?size=100',headers=self.headers).json['data']['items'];currency=rows[0]['currency'];keys=[r['key'] for r in rows if r['currency']==currency][:2]
        invalid=self.client.post('/api/workbench/runs',json={'keys':keys,'budgetId':self.budget_id,'targetRegion':'EU','businessConfigId':pid},headers=self.headers)
        self.assertEqual(invalid.status_code,400)

    def test_financial_api_and_real_bank_workflow_source(self):
        from backend.tests.test_financial_warehouse import financial_fixture
        with financial_fixture():
            self.assertEqual(self.client.get('/api/finance/overview').status_code,401)
            for endpoint in ('overview','schema','transactions?source=ULB-1597&label=1','transactions/BANK-1','accounts/CTU-BERKA:1','macro?year=2024','fx'):
                r=self.client.get('/api/finance/'+endpoint,headers=self.headers);self.assertEqual(r.status_code,200,r.json)
            r=self.client.post('/api/finance/fx/convert',json={'date':'2011-12-04','from':'GBP','to':'USD','amount':100},headers=self.headers)
            self.assertEqual(r.json['data']['converted'],'162.50')
            bad=self.client.post('/api/finance/fx/convert',json={'date':'2011-12-04','from':'GBP','to':'USD','amount':'NaN'},headers=self.headers)
            self.assertEqual(bad.status_code,400)
            self.assertEqual(self.client.get('/api/finance/transactions?page=-1',headers=self.headers).status_code,400)
            sources=self.client.get('/api/workbench/sources?scope=bank',headers=self.headers).json['data'];self.assertEqual(sources['total'],1)
            self.assertEqual(sources['items'][0]['datasetId'],'ctu-berka')

if __name__=='__main__':
    unittest.main()
