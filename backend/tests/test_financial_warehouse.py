import contextlib,json,sqlite3,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from backend.engine import financial_warehouse as warehouse

@contextlib.contextmanager
def financial_fixture():
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'fedshield_finance.sqlite';c=sqlite3.connect(path)
        c.executescript((Path(__file__).parents[1]/'engine/financial_schema.sql').read_text(encoding='utf-8'))
        for source in ('CTU-BERKA','ULB-1597','ECB-FX','WB-REMIT','OFAC-SDN'):
            c.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,?)',(source,source,'fixture','https://example.invalid','isolated test','fixture','2026-11-10','unknown','test only',1))
        c.execute('INSERT INTO bank_districts VALUES(?,?,?,?,?,?)',('CTU-BERKA:18','CTU-BERKA','18','Test district','Test region','{}'))
        c.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?,?)',('CTU-BERKA:1','CTU-BERKA','1','CZ','CZK','1993-01-01','CTU-BERKA:18','MONTHLY','{}'))
        c.execute('INSERT INTO parties VALUES(?,?,?,?,?,?,?,?)',('P1','CTU-BERKA','1','bank_customer','Anonymous','CZ','CTU-BERKA:18','{}'))
        c.execute('INSERT INTO account_parties VALUES(?,?,?,?)',('CTU-BERKA:1','P1','OWNER','1'))
        c.execute('INSERT INTO loan_contracts VALUES(?,?,?,?,?,?,?,?,?)',('L1','CTU-BERKA:1',10000,'CZK','1997-01-01',12,1000,'A','{}'))
        bank=('BANK-1','CTU-BERKA','1','CTU-BERKA:1',None,'bank_ledger','100',10000,'CZK','1998-01-01','day',None,'credit','VKLAD',10000,'CZ',None,'trans:1','{"trans_id":1}')
        card=('CARD-0000001','ULB-1597','1',None,None,'card_payment','25.50',None,None,None,'relative_seconds',3600,None,None,None,None,None,'parquet:1',None)
        c.executemany('INSERT INTO transactions VALUES('+','.join('?'*19)+')',[bank,card])
        c.execute('INSERT INTO transaction_labels VALUES(?,?,?,?)',(card[0],'fraud',1,'ULB-1597'))
        c.execute('INSERT INTO transaction_features VALUES(?,?)',(card[0],'{"V1":0.3}'))
        c.executemany('INSERT INTO exchange_rates VALUES(?,?,?,?,?)',[('2011-12-02','EUR','USD','1.3','ECB-FX'),('2011-12-02','EUR','GBP','0.8','ECB-FX'),('2011-12-09','EUR','USD','2','ECB-FX')])
        c.execute('INSERT INTO countries VALUES(?,?,?,?,?)',('DEU','DE','Germany','Europe','WB-REMIT'))
        c.execute('INSERT INTO macro_indicators VALUES(?,?,?,?,?,?,?)',('DEU','BX.TRF.PWKR.CD.DT',2024,None,'USD','WB-REMIT','record:1'))
        c.execute('INSERT INTO risk_entities VALUES(?,?,?,?,?,?,?,?)',('S1','OFAC-SDN','1','EXAMPLE BANK','example bank','entity','TEST','fixture'))
        c.execute('INSERT INTO risk_aliases VALUES(?,?,?,?,?)',('A1','S1','aka','Sample Name','sample name'))
        c.execute('INSERT INTO warehouse_metadata VALUES(?,?)',('manifest',json.dumps({'sourceCounts':{'CTU-BERKA':1,'ULB-1597':1},'stats':{},'tables':['transactions']})))
        c.commit();c.close()
        with patch.object(warehouse,'location',return_value=path):yield path

class TestFinancialWarehouse(unittest.TestCase):
    def test_units_labels_and_provenance_remain_distinct(self):
        with financial_fixture():
            card=warehouse.transaction_detail('CARD-0000001');self.assertIsNone(card['currency']);self.assertIsNone(card['occurred_at']);self.assertEqual(card['elapsed_seconds'],3600)
            self.assertEqual(card['labels'][0]['label_value'],1);self.assertNotIn('Class',card['features'])
            self.assertEqual(warehouse.transactions('ULB-1597',label='1')['total'],1)
            self.assertEqual(warehouse.transactions(q="' OR 1=1 --")['total'],0)
            bank=warehouse.transaction_detail('BANK-1');self.assertEqual(bank['account']['id'],'CTU-BERKA:1');self.assertEqual(bank['loans'][0]['source_status'],'A')
            self.assertIsNone(bank['country_to']);self.assertEqual(bank['raw']['trans_id'],1)
    def test_foreign_keys_and_isolated_monetary_series(self):
        with financial_fixture() as path:
            c=sqlite3.connect(path);c.execute('PRAGMA foreign_keys=ON')
            with self.assertRaises(sqlite3.IntegrityError):c.execute('INSERT INTO transaction_features VALUES(?,?)',('MISSING','{}'))
            c.close()
            result=warehouse.fx('2011-12-04','GBP','USD',100)
            self.assertEqual(result['date'],'2011-12-02');self.assertEqual(result['converted'],'162.50')
            with self.assertRaises(ValueError):warehouse.fx('1998-01-01','GBP','USD',100)
            self.assertIsNone(warehouse.fx('2011-12-08','GBP','JPY',100))
            self.assertIsNone(warehouse.macro('BX.TRF.PWKR.CD.DT',2024)[0]['value'])
    def test_model_bundle_rejects_mismatched_source_and_modified_metrics(self):
        import hashlib
        with financial_fixture() as path:
            root=path.parent/'models/card';version='a'*32;folder=root/'versions'/version;folder.mkdir(parents=True)
            metrics={'sourceSha256':'trusted-source','modelVersion':version,'status':'trained'};raw=json.dumps(metrics).encode();(folder/'metrics.json').write_bytes(raw)
            (root/'current.json').write_text(json.dumps({'version':version,'sourceSha256':'trusted-source','metricsSha256':hashlib.sha256(raw).hexdigest()}))
            self.assertEqual(warehouse.model_metrics()['status'],'not_trained')
            c=sqlite3.connect(path);c.execute('INSERT INTO source_files VALUES(?,?,?,?,?,?,?)',('card','ULB-1597','file','url','trusted-source',10,'date'));c.commit();c.close()
            self.assertEqual(warehouse.model_metrics()['status'],'trained')
            (folder/'metrics.json').write_text('{}')
            self.assertEqual(warehouse.model_metrics()['status'],'not_trained')
    def test_risk_candidate_matching_not_identity_or_substring(self):
        with financial_fixture():
            self.assertEqual(len(warehouse.screen('  EXAMPLE   BANK ')['items']),1)
            self.assertEqual(len(warehouse.screen('Sample Name')['items']),1)
            self.assertEqual(warehouse.screen('EXAMPLE')['items'],[])
            self.assertIn('不自动',warehouse.screen('EXAMPLE BANK')['note'])
            bank,total=warehouse.bank_orders(keys=['finance:BANK-1']);self.assertEqual(total,1);self.assertEqual(bank[0]['currency'],'CZK');self.assertIn('不是真实交易时刻',bank[0]['sourceNote'])
