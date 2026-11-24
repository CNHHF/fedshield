"""Read-only access to the project-owned, normalized multi-source warehouse."""
from contextlib import contextmanager
from pathlib import Path
import sqlite3,json,datetime,decimal,unicodedata,hashlib,re
from .. import config

def location():return Path(config.INSTANCE_DIR)/'financial_data/fedshield_finance.sqlite'
def available():return location().is_file()
@contextmanager
def connect():
    c=sqlite3.connect(location().resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:yield c
    finally:c.close()
def metadata():
    with connect() as c:
        m=json.loads(c.execute("SELECT value FROM warehouse_metadata WHERE key='manifest'").fetchone()[0])
        sources=[dict(r) for r in c.execute('SELECT * FROM sources ORDER BY kind,id')]
        return dict(m,sources=sources)
def source_detail(source):
    with connect() as c:
        r=c.execute('SELECT * FROM sources WHERE id=?',(source,)).fetchone()
        if not r:return None
        return dict(r,files=[dict(x) for x in c.execute('SELECT * FROM source_files WHERE source_id=?',(source,))],quality=[dict(x) for x in c.execute('SELECT * FROM quality_checks WHERE source_id=?',(source,))],lineage=[dict(x) for x in c.execute('SELECT * FROM field_lineage WHERE source_id=?',(source,))])
def transactions(source='',q='',page=1,size=20,label=''):
    filters=[];params=[]
    if source:filters.append('t.source_id=?');params.append(source)
    if q:filters.append('(t.id LIKE ? OR t.account_id LIKE ?)');params.extend(['%'+q+'%']*2)
    if label in ('0','1'):filters.append("EXISTS(SELECT 1 FROM transaction_labels l WHERE l.transaction_id=t.id AND l.label_type='fraud' AND l.label_value=?)");params.append(int(label))
    where=(' WHERE '+' AND '.join(filters)) if filters else ''
    with connect() as c:
        total=c.execute('SELECT count(*) FROM transactions t'+where,params).fetchone()[0]
        rows=[dict(r) for r in c.execute('SELECT t.id,t.source_id,t.source_key,t.account_id,t.event_type,t.amount_value,t.currency,t.occurred_at,t.time_precision,t.elapsed_seconds,t.direction,t.operation,t.country_from,t.country_to,(SELECT label_value FROM transaction_labels l WHERE l.transaction_id=t.id AND label_type=\'fraud\') AS observed_fraud_label FROM transactions t'+where+' ORDER BY t.id LIMIT ? OFFSET ?',params+[size,(page-1)*size])]
    return {'items':rows,'total':total,'page':page,'size':size}
def transaction_detail(id):
    with connect() as c:
        r=c.execute('SELECT * FROM transactions WHERE id=?',(id,)).fetchone()
        if not r:return None
        result=dict(r);result['raw']=json.loads(result.pop('raw_json') or '{}')
        f=c.execute('SELECT feature_json FROM transaction_features WHERE transaction_id=?',(id,)).fetchone();result['features']=json.loads(f[0]) if f else {}
        result['labels']=[dict(x) for x in c.execute('SELECT label_type,label_value,source_id FROM transaction_labels WHERE transaction_id=?',(id,))]
        if result['account_id']:
            result['account']=dict(c.execute('SELECT * FROM accounts WHERE id=?',(result['account_id'],)).fetchone());result['account'].pop('raw_json',None)
            result['parties']=[dict(x) for x in c.execute('SELECT p.id,p.display_name,p.country,ap.rights FROM account_parties ap JOIN parties p ON p.id=ap.party_id WHERE ap.account_id=?',(result['account_id'],))]
            result['loans']=[dict(x) for x in c.execute('SELECT id,start_date,amount_minor,currency,duration_months,source_status FROM loan_contracts WHERE account_id=?',(result['account_id'],))]
        result['prediction']=prediction(id)
        return result
def _model_bundle():
    root=location().parent/'models/card';pointer=root/'current.json'
    if not pointer.is_file():return None
    try:
        p=json.loads(pointer.read_text(encoding='utf-8'));version=p['version']
        if not re.fullmatch('[0-9a-f]{32}',version):return None
        with connect() as c:
            source=c.execute("SELECT sha256 FROM source_files WHERE id='card'").fetchone()
        if source is None or source[0]!=p['sourceSha256']:return None
        folder=root/'versions'/version;raw=(folder/'metrics.json').read_bytes()
        if hashlib.sha256(raw).hexdigest()!=p['metricsSha256']:return None
        m=json.loads(raw)
        if m.get('sourceSha256')!=source[0] or m.get('modelVersion')!=version:return None
        return folder,m
    except (OSError,ValueError,KeyError):return None
def prediction(id):
    bundle=_model_bundle()
    if not bundle:return None
    folder,metrics=bundle;file=folder/'predictions.sqlite'
    if not file.is_file():return None
    c=sqlite3.connect(file.resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:
        version=dict(c.execute('SELECT key,value FROM model_metadata'))
        if version.get('sourceSha256')!=metrics['sourceSha256'] or version.get('modelVersion')!=metrics['modelVersion']:return None
        row=c.execute('SELECT * FROM predictions WHERE transaction_id=?',(id,)).fetchone()
        return dict(row) if row else None
    finally:c.close()
def model_metrics():
    bundle=_model_bundle()
    return bundle[1] if bundle else {'status':'not_trained','scope':'尚无与当前数据版本一致的实测结果，不展示旧模型或虚构指标。'}
def account_detail(id):
    with connect() as c:
        a=c.execute('SELECT * FROM accounts WHERE id=?',(id,)).fetchone()
        if not a:return None
        return dict(a,parties=[dict(r) for r in c.execute('SELECT p.id,p.display_name,ap.rights FROM account_parties ap JOIN parties p ON p.id=ap.party_id WHERE ap.account_id=?',(id,))],daily=[dict(r) for r in c.execute('SELECT * FROM account_daily WHERE account_id=? ORDER BY day DESC LIMIT 30',(id,))],loans=[dict(r) for r in c.execute('SELECT id,amount_minor,currency,start_date,duration_months,source_status FROM loan_contracts WHERE account_id=?',(id,))],standingOrders=[dict(r) for r in c.execute('SELECT id,destination_bank_code,amount_minor,currency,purpose FROM payment_orders WHERE account_id=?',(id,))])
def macro(indicator,year):
    with connect() as c:
        return [dict(r) for r in c.execute('SELECT m.*,c.name AS country_name,c.region FROM macro_indicators m JOIN countries c ON c.iso3=m.country_iso3 WHERE m.indicator=? AND m.year=? ORDER BY CAST(m.value AS REAL) DESC',(indicator,year))]
def fx(date,source,target,amount):
    day=datetime.date.fromisoformat(date)
    if day<datetime.date(1999,1,1):raise ValueError('ECB历史序列从1999年开始')
    lower=(day-datetime.timedelta(days=7)).isoformat()
    if source==target:return {'date':date,'from':source,'to':target,'amount':str(amount),'converted':str(amount),'rate':'1','note':'同币种，不引用汇率'}
    with connect() as c:
        # Both legs must come from the same historical date; never look forward.
        required=[v for v in (source,target) if v!='EUR']
        rows=c.execute('SELECT rate_date FROM exchange_rates WHERE rate_date BETWEEN ? AND ? AND quote_currency IN ('+','.join('?'*len(required))+') GROUP BY rate_date HAVING count(DISTINCT quote_currency)=? ORDER BY rate_date DESC LIMIT 1',[lower,date,*required,len(required)]).fetchone()
        if not rows:return None
        effective=rows[0];rates={r['quote_currency']:decimal.Decimal(r['rate']) for r in c.execute('SELECT * FROM exchange_rates WHERE rate_date=?',(effective,))};rates['EUR']=decimal.Decimal(1)
        rate=rates[target]/rates[source];converted=decimal.Decimal(str(amount))*rate
        return {'date':effective,'requestedDate':date,'from':source,'to':target,'amount':str(amount),'rate':str(rate),'converted':str(converted.quantize(decimal.Decimal('.01'))),'sourceId':'ECB-FX','note':'ECB参考汇率，仅分析展示；未改写原币金额，不是实际交易报价。'}
def latest_fx():
    with connect() as c:
        day=c.execute('SELECT max(rate_date) FROM exchange_rates').fetchone()[0]
        return {'date':day,'items':[dict(r) for r in c.execute('SELECT * FROM exchange_rates WHERE rate_date=? ORDER BY quote_currency',(day,))]}
def screen(name):
    folded=' '.join(''.join(ch if ch.isalnum() else ' ' for ch in unicodedata.normalize('NFKD',name).casefold() if not unicodedata.combining(ch)).split())
    with connect() as c:
        rows=c.execute('SELECT DISTINCT e.* FROM risk_entities e LEFT JOIN risk_aliases a ON a.entity_id=e.id WHERE e.folded_name=? OR a.folded_name=? LIMIT 30',(folded,folded)).fetchall()
        return {'query':name,'matchMethod':'规范化姓名或别名完全相等；仅候选，非身份认定','items':[dict(r,aliases=[dict(a) for a in c.execute('SELECT name,alias_type FROM risk_aliases WHERE entity_id=? LIMIT 20',(r['id'],))],addresses=[dict(a) for a in c.execute('SELECT city,country FROM risk_addresses WHERE entity_id=? LIMIT 10',(r['id'],))]) for r in rows],'note':'无候选不代表无风险；同名也不代表同一主体，不自动处置交易。'}
def schema():
    with connect() as c:
        names=[r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        return [{'table':n,'columns':[dict(r) for r in c.execute('PRAGMA table_info("'+n+'")')],'foreignKeys':[dict(r) for r in c.execute('PRAGMA foreign_key_list("'+n+'")')]} for n in names]
def bank_orders(keys=None,page=1,size=20,q=''):
    where=["source_id='CTU-BERKA'","amount_minor>0"];params=[]
    if keys is not None:
        if not keys:return [],0
        where.append('id IN ('+','.join('?'*len(keys))+')');params.extend(k.removeprefix('finance:') for k in keys)
    if q:where.append('(id LIKE ? OR account_id LIKE ?)');params.extend(['%'+q+'%']*2)
    with connect() as c:
        clause=' WHERE '+' AND '.join(where);total=c.execute('SELECT count(*) FROM transactions'+clause,params).fetchone()[0]
        rows=c.execute('SELECT id,account_id,amount_minor,occurred_at,direction,operation FROM transactions'+clause+' ORDER BY id LIMIT ? OFFSET ?',params+[size,(page-1)*size]).fetchall()
        result=[{'key':'finance:'+r['id'],'code':r['id'],'merchantCode':r['account_id'],'amount':r['amount_minor']/100,'currency':'CZK','region':'EU','destRegion':'OTHER','category':'银行流水','occurredAt':r['occurred_at']+' 00:00:00','origin':'CTU / PKDD99 真实匿名银行','datasetId':'ctu-berka','sourceNote':'匿名账户，不是商户；日期精度为日，00:00只为流程兼容，不是真实交易时刻；对手国家未知，不据此认定跨境。','account':r['account_id']} for r in rows]
    return result,total
