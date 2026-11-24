"""Read-only access to the sourced UCI database; never invent missing fields."""
from pathlib import Path
import sqlite3,json
from contextlib import contextmanager
from flask import current_app
from .. import config
FIELD_MAP={'datasetId':'UCI数据集注册标识（派生）','code':'InvoiceNo + 数据集前缀及分组校验值（派生主键）','invoiceNo':'InvoiceNo 原值','customerId':'CustomerID 原匿名编号，缺失保持为空','customerCountry':'Country 原值','amount':'同一订单各行 Quantity × UnitPrice，以便士舍入后汇总','currency':'UCI单位说明 sterling，映射GBP','quantity':'同一订单Quantity求和','lineCount':'同一订单原始行计数','occurredAt':'同一订单最早InvoiceDate','region':'UCI说明零售商位于英国，映射UK','destRegion':'客户Country归入展示地区，不等于真实资金路由','merchantCode':'项目标识“UCI匿名零售商”；原数据无商户名称','category':'项目业务分组“零售订单”，原商品描述见原始行'}

def location():return Path(config.INSTANCE_DIR)/'public_data/transactions.sqlite'
def available():return not current_app.testing and location().is_file()
@contextmanager
def connect():
    c=sqlite3.connect(location().resolve().as_uri()+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:yield c
    finally:c.close()
def manifest():
    with connect() as c:return json.loads(c.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0])
def register():
    if not available():return
    from ..models import Dataset
    from ..extensions import db
    m=manifest();row=Dataset.query.filter_by(code='UCI-ONLINE-RETAIL-352').first()
    if row is None:row=Dataset(code='UCI-ONLINE-RETAIL-352');db.session.add(row)
    row.name='UCI Online Retail · 真实公开交易';row.level='P1';row.owner='UCI / Chen D.';row.region='UK';row.category='交易数据';row.rows=m['rawRows'];row.storage='SQLite'
    row.description='CC BY 4.0；541909条原始明细。无银行卡号或欺诈标签；原始行、汇总订单及来源哈希可回查。'
    row.fields=[{'name':v,'level':'P1' if v=='CustomerID' else 'P2' if v in ('Quantity','UnitPrice') else 'P3','type':'string'} for v in ['InvoiceNo','StockCode','Description','Quantity','InvoiceDate','UnitPrice','CustomerID','Country']]
    db.session.commit()
def adapt(row):
    return {'key':'public:'+row['code'],'code':row['code'],'merchantCode':'UCI匿名零售商','amount':row['amount_pence']/100,
        'currency':'GBP','region':'UK','destRegion':row['dest_region'],'category':'零售订单',
        'occurredAt':row['occurred_at'],'origin':'UCI Online Retail · 真实公开交易',
        'datasetId':'uci-online-retail-352','invoiceNo':row['invoice_no'],'customerId':row['customer_id'],
        'customerCountry':row['country'],'lineCount':row['line_count'],'quantity':row['quantity'],
        'sourceNote':'匿名零售商为数据集主体标识，不是真实商户名称；未提供银行卡号或欺诈标签。'}
def orders(keys=None,q='',region='',page=None,size=20):
    where=["status='purchase'"];params=[]
    if keys is not None:
        if not keys:return [],0
        where.append('code IN ('+','.join('?' for _ in keys)+')');params.extend(k.removeprefix('public:') for k in keys)
    if q:where.append('(code LIKE ? OR invoice_no LIKE ? OR customer_id LIKE ? OR country LIKE ?)');params.extend(['%'+q+'%']*4)
    if region:where.append("'UK'=?");params.append(region)
    sql=' FROM orders WHERE '+' AND '.join(where)
    with connect() as c:
        total=c.execute('SELECT COUNT(*)'+sql,params).fetchone()[0]
        tail=' ORDER BY occurred_at DESC,code'
        if page is not None:tail+=' LIMIT ? OFFSET ?';params=params+[size,(page-1)*size]
        rows=c.execute('SELECT *'+sql+tail,params).fetchall()
    return [adapt(r) for r in rows],total
def raw_record(code,page=1,size=30):
    with connect() as c:
        order=c.execute('SELECT * FROM orders WHERE code=?',(code,)).fetchone()
        if order is None:return None
        params=(order['invoice_no'],order['customer_id'],order['country'])
        total=c.execute('SELECT COUNT(*) FROM raw_lines WHERE invoice_no=? AND customer_id=? AND country=?',params).fetchone()[0]
        rows=c.execute('SELECT * FROM raw_lines WHERE invoice_no=? AND customer_id=? AND country=? ORDER BY source_row LIMIT ? OFFSET ?',(*params,size,(page-1)*size)).fetchall()
        return {'order':adapt(order),'items':[dict(r) for r in rows],'total':total,'page':page,'size':size,'sourceUrl':'https://archive.ics.uci.edu/dataset/352/online-retail'}
