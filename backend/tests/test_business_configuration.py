import copy,io,unittest,zipfile
from backend.engine.business_config import validate_plan,simulate,extract_file
from backend.compliance.rule_engine import evaluate

MATERIAL='我们销售家具。我们处理客户地址并存储在中国。'
def specification():
    return {'summary':'德国家具业务，客户地址在中国处理','marketRegion':'EU','region':'CN','facts':[{'key':'business','label':'经营内容','value':'家具销售','evidence':'我们销售家具。'},{'key':'dataTypes','label':'数据类型','value':'客户地址','evidence':'我们处理客户地址并存储在中国。'},{'key':'processingLocation','label':'数据地点','value':'中国','evidence':'我们处理客户地址并存储在中国。'}],'questions':[],'requirements':[{'name':'核对处理依据','reason':'保留业务处理材料','sourceIds':['EC-PRINCIPLES']}],'rules':[{'name':'缺少处理依据时补件','kind':'project','reason':'处理前核对材料','sourceIds':[],'condition':{'all':[{'field':'targetRegion','op':'eq','value':'CN'},{'field':'authorized','op':'eq','value':False}]},'actions':[{'action':'require','message':'补齐处理依据'}]}]}

class TestBusinessConfiguration(unittest.TestCase):
    def test_facts_sources_and_missing_information(self):
        spec=specification();p=validate_plan(spec,MATERIAL,'德国')
        self.assertEqual(p['status'],'ready');self.assertEqual(p['region'],'CN');self.assertEqual(p['marketRegion'],'EU')
        spec['facts'][0]['evidence']='编造的原文'
        with self.assertRaises(ValueError):validate_plan(spec,MATERIAL,'德国')
        spec=specification();spec['requirements'][0]['sourceIds']=['FAKE-LAW']
        with self.assertRaises(ValueError):validate_plan(spec,MATERIAL,'德国')
        spec=specification();spec['facts']=[]
        self.assertEqual(validate_plan(spec,MATERIAL,'德国')['status'],'clarification')
    def test_scoping_short_circuit_and_selected_simulation(self):
        p=validate_plan(specification(),MATERIAL,'德国');p['id']='BC-test'
        for r in p['rules']:r['nodes'][0]['config']['businessConfigId']=p['id']
        r=p['rules'][0];r.update(enabled=True,code='TEST')
        self.assertTrue(evaluate([r],{'event':'data.transfer','targetRegion':'CN','authorized':False})['passed'])
        self.assertFalse(evaluate([r],{'event':'data.transfer','targetRegion':'CN','authorized':False,'businessConfigId':'BC-test'})['passed'])
        samples=[{'targetRegion':'CN','authorized':False},{'targetRegion':'CN','authorized':True},{'targetRegion':'US'}]
        rs=simulate(p,samples,[r['localId']]);self.assertEqual([i['passed'] for i in rs],[False,True,True])
        with self.assertRaises(ValueError):simulate(p,samples,['unknown'])
        from backend.engine.rule_schema import compile_spec
        rule=compile_spec({'name':'或条件','condition':{'any':[{'field':'authorized','op':'eq','value':True},{'field':'amount','op':'gt','value':100}]},'actions':[{'action':'require'}]})
        rule.update(enabled=True,code='OR')
        self.assertIn('补充',evaluate([rule],{'event':'data.transfer','authorized':True})['checkedRules'][0]['detail'])
    def test_thresholds_need_confirmation_and_nonbusiness_cannot_block(self):
        spec=specification();r=spec['rules'][0];r['kind']='business';r['evidence']='我们销售家具。';r['actions']=[{'action':'block','message':'阻断'}];r['condition']['all'].append({'field':'amount','op':'gt','value':100})
        with self.assertRaises(ValueError):validate_plan(spec,MATERIAL,'德国')
        r['condition']['all'].append({'field':'currency','op':'eq','value':'EUR'})
        plan=validate_plan(spec,MATERIAL,'德国');self.assertTrue(plan['rules'][0]['requiresConfirmation'])
        spec['rules'][0]['kind']='project'
        with self.assertRaises(ValueError):validate_plan(spec,MATERIAL,'德国')
    def test_document_extraction(self):
        self.assertEqual(extract_file('业务.txt',MATERIAL.encode()),MATERIAL)
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:p><w:r><w:t>'+MATERIAL+'</w:t></w:r></w:p></w:document>')
        self.assertEqual(extract_file('业务.docx',b.getvalue()),MATERIAL)
        with self.assertRaises(ValueError):extract_file('file.txt',b'x'*(2*1024*1024+1))
    def test_ai_edit_preserves_server_owned_business_binding(self):
        import json
        from unittest.mock import patch
        from backend.engine.rule_draft import draft
        spec=specification()['rules'][0]
        response=io.BytesIO(json.dumps({'choices':[{'message':{'content':json.dumps(spec)}}]}).encode())
        current={'nodes':[{'type':'trigger','config':{'businessConfigId':'BC-owned'}}]}
        with patch('backend.engine.rule_draft.settings',return_value=('test-only','test')),patch('backend.engine.rule_draft.urlopen',return_value=response):result=draft('修改当前规则',current_rule=current)
        self.assertEqual(result['nodes'][0]['config']['businessConfigId'],'BC-owned')
