"""FedShield's own normalized financial warehouse, deterministic lineage and checks."""
from pathlib import Path
import sqlite3,json,csv,zipfile,hashlib,datetime,decimal,uuid,os,sys,unicodedata,io
import pyarrow.parquet as pq
ROOT=Path(__file__).resolve().parents[1];FOLDER=ROOT/'instance/financial_data';RAW=FOLDER/'raw'
VERSION='fedshield-financial-v1'
COUNTRIES={'United Kingdom':'GB','EIRE':'IE','Germany':'DE','France':'FR','Spain':'ES','Portugal':'PT','Belgium':'BE','Netherlands':'NL','Switzerland':'CH','Austria':'AT','Italy':'IT','Denmark':'DK','Norway':'NO','Sweden':'SE','Finland':'FI','Greece':'GR','Cyprus':'CY','Malta':'MT','Poland':'PL','Lithuania':'LT','Czech Republic':'CZ','Iceland':'IS','Australia':'AU','Japan':'JP','Hong Kong':'HK','Singapore':'SG','USA':'US','Canada':'CA','Israel':'IL','Bahrain':'BH','United Arab Emirates':'AE','Saudi Arabia':'SA','Brazil':'BR','RSA':'ZA','Lebanon':'LB' }
def js(value):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
def fingerprint(path):
    digest=hashlib.sha256();size=0;lines=0
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk);size+=len(chunk);lines+=chunk.count(b'\n')
    return digest.hexdigest(),size,lines
def verify_snapshots():
    required={'creditcard.parquet':'card','creditcard-metadata.json':'card_metadata','ecb-fx.zip':'ecb','wb-countries.json':'wb_countries','wb-remittances-in.json':'wb_in','wb-remittances-out.json':'wb_out','ofac-sdn.csv':'ofac','ofac-alias.csv':'ofac_alias','ofac-address.csv':'ofac_address','berka/trans.asc':'berka_mirror'}
    for name,source in required.items():
        file=RAW/name;sidecar=Path(str(file)+'.source.json')
        if not file.is_file() or not sidecar.is_file():raise ValueError('Required snapshot or provenance missing: '+name)
        m=json.loads(sidecar.read_text(encoding='utf-8'))
        if m.get('source')!=source:raise ValueError('Snapshot source identity mismatch: '+name)
    for sidecar in RAW.rglob('*.source.json'):
        m=json.loads(sidecar.read_text(encoding='utf-8'));path=Path(str(sidecar).removesuffix('.source.json'));sha,size,_=fingerprint(path)
        if sha!=m['sha256'] or size!=m['bytes']:raise ValueError('Source snapshot mismatch: '+path.name)
    bank=json.loads((RAW/'berka/manifest.json').read_text(encoding='utf-8'))
    if set(bank.get('tables',{}))!={'account','card','client','disp','district','loan','order','trans'}:raise ValueError('Bank source manifest must contain all eight input tables')
    for name,m in bank['tables'].items():
        sha,size,rows=fingerprint(RAW/'berka'/(name+'.jsonl'))
        if (sha,size,rows)!=(m['sha256'],m['bytes'],m['rows']):raise ValueError('Bank snapshot mismatch: '+name)
    m=json.loads((ROOT/'instance/public_data/manifest.json').read_text(encoding='utf-8'))
    if fingerprint(ROOT/'instance/public_data/Online Retail.xlsx')[0]!=m['workbookSha256']:raise ValueError('UCI workbook hash mismatch')
    with sqlite3.connect((ROOT/'instance/public_data/transactions.sqlite').resolve().as_uri()+'?mode=ro',uri=True) as c:
        if c.execute('SELECT count(*) FROM orders').fetchone()[0]!=m['orders'] or c.execute('SELECT count(*) FROM raw_lines').fetchone()[0]!=m['rawRows']:raise ValueError('UCI derived table counts mismatch')
    print('all source snapshot hashes, sizes and bank row counts verified',flush=True)
def minor(value):return int((decimal.Decimal(str(value))*100).quantize(decimal.Decimal('1'),rounding=decimal.ROUND_HALF_UP))
def fold(value):return ' '.join(''.join(c if c.isalnum() else ' ' for c in unicodedata.normalize('NFKD',value).casefold() if not unicodedata.combining(c)).split())
def jsonl(name):
    with (RAW/'berka'/(name+'.jsonl')).open(encoding='utf-8') as f:
        for line in f:yield json.loads(line)
def add_source(c,id,title,kind,url,citation,license,geography,limitations):
    c.execute('INSERT INTO sources VALUES(?,?,?,?,?,?,?,?,?,0)',(id,title,kind,url,citation,license,datetime.datetime.now(datetime.timezone.utc).isoformat(),geography,limitations))
def check(c,source,name,count,detail,severity='info'):c.execute('INSERT INTO quality_checks(source_id,check_name,affected_rows,severity,detail) VALUES(?,?,?,?,?)',(source,name,count,severity,detail))
def lineage(c,source,target,original,transformation):c.execute('INSERT INTO field_lineage(source_id,target_field,source_field,transformation) VALUES(?,?,?,?)',(source,target,original,transformation))
def transaction(c,values):c.executemany('INSERT INTO transactions VALUES('+','.join('?'*19)+')',values)

def load_retail(c):
    source='UCI-352'
    add_source(c,source,'电商零售订单','commerce','https://archive.ics.uci.edu/dataset/352/online-retail','Chen D. (2015), DOI 10.24432/C5BW33','CC BY 4.0','英国零售商及客户国家','电商订单，不是银行流水；不具有欺诈标签。')
    old=sqlite3.connect((ROOT/'instance/public_data/transactions.sqlite').resolve().as_uri()+'?mode=ro',uri=True);old.row_factory=sqlite3.Row
    customers=old.execute("SELECT DISTINCT customer_id,country FROM orders WHERE customer_id<>''").fetchall()
    c.executemany('INSERT INTO parties VALUES(?,?,?,?,?,?,?,?)',[(source+':'+r['customer_id']+':'+r['country'],source,r['customer_id']+':'+r['country'],'anonymous_customer','匿名客户 '+r['customer_id'],COUNTRIES.get(r['country']),None,js(dict(r))) for r in customers])
    batch=[]
    for r in old.execute('SELECT * FROM orders'):
        party=source+':'+r['customer_id']+':'+r['country'] if r['customer_id'] else None
        batch.append((r['code'],source,r['code'],None,party,'retail_invoice',str(decimal.Decimal(r['amount_pence'])/100),r['amount_pence'],'GBP',r['occurred_at'],'minute',None,'sale' if r['amount_pence']>0 else 'adjustment',r['status'],None,'GB',COUNTRIES.get(r['country']),'orders:'+r['code'],js(dict(r))))
    transaction(c,batch);old.close()
    check(c,source,'missing_customer',sum(r[4] is None for r in batch),'保留原始匿名客户缺失，不补造账户。')
    lineage(c,source,'transactions.amount_minor','Quantity × UnitPrice','原始工作簿逐行按便士舍入后聚合；包含取消和非正金额。')
    print('retail',len(batch),flush=True)

def load_card(c):
    source='ULB-1597';meta=json.loads((RAW/'creditcard-metadata.json').read_text(encoding='utf-8'))['data_set_description']
    add_source(c,source,'欧洲信用卡交易与欺诈标签','card','https://www.openml.org/d/1597','Worldline / ULB, Dal Pozzolo et al. (2015)','OpenML元数据标记Public，未提供具体再分发许可证；本机研究使用，不随提交包分发原始数据。','欧洲持卡人，未提供逐笔国家','两天历史匿名交易。PCA特征无法还原客户/国家；Amount单位未在该镜像元数据明确，币种保持NULL；标签不作推理输入。')
    names=pq.ParquetFile(RAW/'creditcard.parquet').schema.names
    required={'Amount','Class'}|{f'V{i}' for i in range(1,29)}
    if not required.issubset(names):raise ValueError('Unexpected credit-card schema: '+str(names))
    count=0;frauds=0
    for batch in pq.ParquetFile(RAW/'creditcard.parquet').iter_batches(batch_size=10000):
        records=batch.to_pylist();tx=[];features=[];labels=[]
        for r in records:
            count+=1;id=f'CARD-{count:07d}';label=int(float(r['Class']));frauds+=label
            elapsed=float(r['Time']) if r.get('Time') is not None else None
            tx.append((id,source,str(count),None,None,'card_payment',str(r['Amount']),None,None,None,'relative_seconds' if elapsed is not None else 'unknown',elapsed,None,None,None,None,None,'creditcard.parquet:row='+str(count),None))
            features.append((id,js({k:float(r[k]) for k in names if k.startswith('V') and k[1:].isdigit()})))
            labels.append((id,'fraud',label,source))
        transaction(c,tx);c.executemany('INSERT INTO transaction_features VALUES(?,?)',features);c.executemany('INSERT INTO transaction_labels VALUES(?,?,?,?)',labels)
    if count!=284807 or frauds!=492:raise ValueError(f'Credit-card benchmark count changed: {count}/{frauds}')
    check(c,source,'known_fraud_labels',frauds,'原始Class=1，严格保留；不作为输入特征。')
    check(c,source,'unknown_currency',count,'元数据未确认币种，不换汇、不参与同币种金额发布。')
    check(c,source,'missing_individual_country',count,'欧洲群体说明不被扩写为逐笔国家或跨境路由。')
    lineage(c,source,'transaction_features','V1–V28','保留发布方PCA特征；Class仅入独立标签表。')
    lineage(c,source,'transactions.occurred_at','Time','仅保存相对秒数；不编造具体日历时刻。')
    print('card',count,'fraud',frauds,flush=True)

def load_bank(c):
    source='CTU-BERKA'
    manifest=json.loads((RAW/'berka/manifest.json').read_text(encoding='utf-8'))
    add_source(c,source,'匿名银行账户与交易流水','bank','https://relational.fel.cvut.cz/dataset/Financial','PKDD 1999 / Berka; CTU Relational Learning Repository, financial version','CTU公开学术库；原发布未列统一开放许可证，仅本机研究，不打包再分发。','捷克银行历史数据','真实匿名银行记录，非全球逐笔跨境流水；银行代码不扩写为虚构机构名；贷款状态不等于交易欺诈。')
    for r in jsonl('district'):c.execute('INSERT INTO bank_districts VALUES(?,?,?,?,?,?)',(source+':'+str(r['district_id']),source,str(r['district_id']),r.get('A2'),r.get('A3'),js(r)))
    for r in jsonl('client'):
        key=str(r['client_id']);c.execute('INSERT INTO parties VALUES(?,?,?,?,?,?,?,?)',(source+':'+key,source,key,'bank_customer','匿名银行客户 '+key,'CZ',source+':'+str(r['district_id']),js(r)))
    for r in jsonl('account'):
        key=str(r['account_id']);c.execute('INSERT INTO accounts VALUES(?,?,?,?,?,?,?,?,?)',(source+':'+key,source,key,'CZ','CZK',str(r.get('date') or ''),source+':'+str(r['district_id']),r.get('frequency'),js(r)))
    dispositions={}
    for r in jsonl('disp'):
        account=source+':'+str(r['account_id']);dispositions[str(r['disp_id'])]=account
        c.execute('INSERT INTO account_parties VALUES(?,?,?,?)',(account,source+':'+str(r['client_id']),r['type'],str(r['disp_id'])))
    for r in jsonl('card'):
        c.execute('INSERT INTO bank_cards VALUES(?,?,?,?,?)',(source+':'+str(r['card_id']),dispositions[str(r['disp_id'])],r.get('type'),str(r.get('issued') or ''),js(r)))
    for r in jsonl('loan'):
        c.execute('INSERT INTO loan_contracts VALUES(?,?,?,?,?,?,?,?,?)',(source+':'+str(r['loan_id']),source+':'+str(r['account_id']),minor(r['amount']),'CZK',str(r['date']),int(r['duration']),minor(r['payments']),r['status'],js(r)))
    for r in jsonl('order'):
        c.execute('INSERT INTO payment_orders VALUES(?,?,?,?,?,?,?,?)',(source+':'+str(r['order_id']),source+':'+str(r['account_id']),r.get('bank_to'),str(r.get('account_to') or ''),minor(r['amount']),'CZK',r.get('k_symbol'),js(r)))
    batch=[];count=0;unknown=0
    for r in jsonl('trans'):
        kind=str(r.get('type') or '');direction='credit' if kind in ('PRIJEM','credit') else 'debit' if kind in ('VYDAJ','VYBER','debit') else 'unknown';unknown+=direction=='unknown'
        key=str(r['trans_id']);batch.append(('BANK-'+key,source,key,source+':'+str(r['account_id']),None,'bank_ledger',str(r['amount']),minor(r['amount']),'CZK',str(r['date']),'day',None,direction,r.get('operation'),minor(r['balance']),'CZ',None,'berka/trans.jsonl:trans_id='+key,js(r)))
        count+=1
        if len(batch)==10000:transaction(c,batch);batch=[]
    if batch:transaction(c,batch)
    c.execute("INSERT INTO account_daily SELECT account_id,substr(occurred_at,1,10),sum(CASE WHEN direction='credit' THEN amount_minor ELSE 0 END),sum(CASE WHEN direction='debit' THEN amount_minor ELSE 0 END),count(*),min(balance_minor),max(balance_minor) FROM transactions WHERE source_id=? GROUP BY account_id,substr(occurred_at,1,10)",(source,))
    check(c,source,'unmapped_direction',unknown,'原始type未在映射内时标unknown，不猜测借贷方向。','warning' if unknown else 'info')
    check(c,source,'unknown_counterparty_country',count,'原始bank和account仅标识对手，无法据此判断跨境方向。')
    check(c,source,'mirror_cross_checked',manifest['tables']['trans'].get('crossCheckedCtuRows',count),'流水原始镜像与CTU导出交叉核对；镜像保留分，CTU版本部分金额舍入为整数，不混淆版本。')
    lineage(c,source,'accounts ↔ parties','account.account_id / disp / client.client_id','用原始键建立账户—客户—持卡—贷款—交易关系，不跨来源合并匿名主体。')
    lineage(c,source,'transactions.currency','PKDD99 dataset context','原始捷克银行金额为CZK，保留源数值并按分量化。')
    print('bank',count,flush=True)

def load_fx(c):
    source='ECB-FX';add_source(c,source,'央行多币种参考汇率','fx','https://www.ecb.europa.eu/stats/policy_and_exchange_rates/euro_reference_exchange_rates/html/index.en.html','European Central Bank, euro foreign exchange reference rates','ECB公开统计，注明来源；仅参考，不作交易报价。','多币种参考序列','以EUR为基准；N/A保留缺失，不采用未来日期补历史汇率。')
    with zipfile.ZipFile(RAW/'ecb-fx.zip') as z:
        rows=csv.DictReader(io.StringIO(z.read('eurofxref-hist.csv').decode('utf-8-sig')))
        batch=[];missing=0
        for r in rows:
            for currency,value in r.items():
                if not currency or currency=='Date':continue
                if not value or value.strip()=='N/A':missing+=1;continue
                decimal.Decimal(value);batch.append((r['Date'],'EUR',currency.strip(),value.strip(),source))
        c.executemany('INSERT INTO exchange_rates VALUES(?,?,?,?,?)',batch)
    check(c,source,'missing_rate_cells',missing,'原始N/A不插值、不采用未来汇率。')
    lineage(c,source,'exchange_rates','eurofxref-hist.csv: Date × currency','宽表转成长表，保留原始十进制值。')
    print('fx',len(batch),flush=True)

def load_macro(c):
    source='WB-REMIT';add_source(c,source,'全球个人汇款收支统计','macro','https://data.worldbank.org/indicator/BX.TRF.PWKR.CD.DT','World Bank WDI / IMF balance of payments, personal remittances','CC BY 4.0','国家/经济体年度汇总','年度宏观收支，不是逐笔流水，也不是双边汇款走廊；剔除地区/收入汇总项，缺失值不填0。')
    countries=json.loads((RAW/'wb-countries.json').read_text(encoding='utf-8'))
    if countries[0]['pages']!=1:raise ValueError('Countries response truncated')
    codes=set()
    for r in countries[1]:
        if r['region']['id']=='NA':continue
        codes.add(r['id']);c.execute('INSERT INTO countries VALUES(?,?,?,?,?)',(r['id'],r['iso2Code'],r['name'],r['region']['value'],source))
    count=0;null=0
    for name in ('in','out'):
        data=json.loads((RAW/f'wb-remittances-{name}.json').read_text(encoding='utf-8'))
        if data[0]['pages']!=1:raise ValueError('Macro response truncated')
        for i,r in enumerate(data[1]):
            if r['countryiso3code'] not in codes:continue
            value=None if r['value'] is None else str(r['value']);null+=value is None;count+=1
            c.execute('INSERT INTO macro_indicators VALUES(?,?,?,?,?,?,?)',(r['countryiso3code'],r['indicator']['id'],int(r['date']),value,'USD',source,f'wb-remittances-{name}.json:record={i}'))
    check(c,source,'missing_observations',null,'原始null保留NULL，与0美元明确区分。')
    lineage(c,source,'macro_indicators','World Bank API: countryiso3code / indicator.id / date / value','国家维度过滤Aggregates，保留指标方向及年度，不转成虚构交易。')
    print('macro',count,flush=True)

def load_sanctions(c):
    source='OFAC-SDN';add_source(c,source,'OFAC公开名单及别名','risk','https://ofac.treasury.gov/specially-designated-nationals-list-sdn-list','US Treasury, OFAC SDN / ALT / ADD official CSV snapshots','美国政府公开名单；保持官方来源和采集时间，仅作筛查候选。','名单主体及地址国家','单一司法辖区名单，不等于全球完整制裁清单；姓名相同不自动认定同一主体，不自动阻断匿名交易。')
    def rows(name):
        with (RAW/name).open(encoding='utf-8-sig',newline='') as f:
            for row in csv.reader(f):
                # Official legacy CSV snapshots end with a DOS EOF marker.
                if row==['\x1a']:continue
                if row and any(cell.strip() for cell in row):yield row
    entities=set()
    def clean(value):return '' if value.strip()=='-0-' else value.strip()
    for r in rows('ofac-sdn.csv'):
        id=source+':'+r[0];entities.add(id);c.execute('INSERT INTO risk_entities VALUES(?,?,?,?,?,?,?,?)',(id,source,r[0],clean(r[1]),fold(r[1]),clean(r[2]),clean(r[3]),clean(r[11])))
    orphans=0
    for r in rows('ofac-alias.csv'):
        entity=source+':'+r[0]
        if entity not in entities:orphans+=1;continue
        c.execute('INSERT INTO risk_aliases VALUES(?,?,?,?,?)',(source+':alias:'+r[1],entity,clean(r[2]),clean(r[3]),fold(r[3])))
    for r in rows('ofac-address.csv'):
        entity=source+':'+r[0]
        if entity not in entities:orphans+=1;continue
        c.execute('INSERT INTO risk_addresses VALUES(?,?,?,?,?,?)',(source+':address:'+r[1],entity,clean(r[2]),clean(r[3]),clean(r[4]),clean(r[5])))
    check(c,source,'orphan_alias_addresses',orphans,'关联不到主体的别名/地址不强行合并。','warning' if orphans else 'info')
    lineage(c,source,'risk_entities ↔ aliases / addresses','SDN.ent_num = ALT.ent_num = ADD.ent_num','只按官方实体ID关联；另建去重音大小写索引供姓名候选筛查。')
    print('risk_entities',len(entities),flush=True)

def main():
    sys.stdout.reconfigure(encoding='utf-8');FOLDER.mkdir(exist_ok=True,parents=True)
    verify_snapshots()
    final=FOLDER/'fedshield_finance.sqlite';temp=FOLDER/'fedshield_finance.build.sqlite'
    if temp.exists():temp.unlink()
    c=sqlite3.connect(temp);c.executescript((ROOT/'backend/engine/financial_schema.sql').read_text(encoding='utf-8'))
    started=datetime.datetime.now(datetime.timezone.utc).isoformat();run=uuid.uuid4().hex;c.execute('INSERT INTO ingestion_runs VALUES(?,?,NULL,?,?)',(run,started,'building',VERSION))
    try:
        for load in (load_retail,load_card,load_bank,load_fx,load_macro,load_sanctions):load(c);c.commit()
        mapping={'card':'ULB-1597','card_metadata':'ULB-1597','ecb':'ECB-FX','wb_countries':'WB-REMIT','wb_in':'WB-REMIT','wb_out':'WB-REMIT','ofac':'OFAC-SDN','ofac_alias':'OFAC-SDN','ofac_address':'OFAC-SDN','berka_mirror':'CTU-BERKA'}
        for path in RAW.rglob('*.source.json'):
            m=json.loads(path.read_text(encoding='utf-8'));source=mapping[m['source']]
            c.execute('INSERT INTO source_files VALUES(?,?,?,?,?,?,?)',(m['source'],source,str(path.relative_to(RAW)).removesuffix('.source.json'),m['url'],m['sha256'],m['bytes'],m['retrievedAt']))
        for table,m in json.loads((RAW/'berka/manifest.json').read_text(encoding='utf-8'))['tables'].items():c.execute('INSERT INTO source_files VALUES(?,?,?,?,?,?,?)',('berka-'+table,'CTU-BERKA','berka/'+table+'.jsonl',m.get('sourceUrl','https://relational.fel.cvut.cz/dataset/Financial'),m['sha256'],m['bytes'],started))
        sourcefile=ROOT/'instance/public_data/manifest.json';m=json.loads(sourcefile.read_text(encoding='utf-8'))
        c.execute('INSERT INTO source_files VALUES(?,?,?,?,?,?,?)',('uci-workbook','UCI-352','../public_data/Online Retail.xlsx',m['sourceUrl'],m['workbookSha256'],(ROOT/'instance/public_data/Online Retail.xlsx').stat().st_size,started))
        counts={}
        for source,table in [('UCI-352','transactions'),('ULB-1597','transactions'),('CTU-BERKA','transactions'),('ECB-FX','exchange_rates'),('WB-REMIT','macro_indicators'),('OFAC-SDN','risk_entities')]:
            n=c.execute(f'SELECT count(*) FROM {table} WHERE source_id=?',(source,)).fetchone()[0];counts[source]=n;c.execute('UPDATE sources SET row_count=? WHERE id=?',(n,source))
        if c.execute('PRAGMA foreign_key_check').fetchone():raise ValueError('Foreign-key check failed')
        if c.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Integrity check failed')
        finished=datetime.datetime.now(datetime.timezone.utc).isoformat();c.execute('UPDATE ingestion_runs SET finished_at=?,status=? WHERE id=?',(finished,'complete',run))
        stats={'financialTransactions':counts['CTU-BERKA']+counts['ULB-1597'],'commerceOrders':counts['UCI-352'],'accounts':c.execute('SELECT count(*) FROM accounts').fetchone()[0],'parties':c.execute('SELECT count(*) FROM parties').fetchone()[0],'loans':c.execute('SELECT count(*) FROM loan_contracts').fetchone()[0],'countries':c.execute('SELECT count(DISTINCT country_iso3) FROM macro_indicators WHERE value IS NOT NULL').fetchone()[0],'currencies':c.execute('SELECT count(DISTINCT quote_currency) FROM exchange_rates').fetchone()[0]+1,'fxObservations':counts['ECB-FX'],'macroObservations':counts['WB-REMIT'],'sanctionEntities':counts['OFAC-SDN'],'aliases':c.execute('SELECT count(*) FROM risk_aliases').fetchone()[0],'rawFiles':c.execute('SELECT count(*) FROM source_files').fetchone()[0]}
        manifest={'schemaVersion':VERSION,'builtAt':finished,'sourceCounts':counts,'stats':stats,'tables':[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")],'database':'fedshield_finance.sqlite','notes':'数据计数按类型分别统计，宏观和汇率不冒充交易。'}
        c.execute('INSERT INTO warehouse_metadata VALUES(?,?)',('manifest',js(manifest)));c.commit();c.close()
        if final.exists():
            backup=final.with_suffix('.previous.sqlite')
            if backup.exists():backup.unlink()
            os.replace(final,backup)
        os.replace(temp,final);(FOLDER/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(js(manifest),flush=True)
    except Exception:
        c.close();raise
if __name__=='__main__':main()
