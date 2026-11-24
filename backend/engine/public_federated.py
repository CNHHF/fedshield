"""Observed cancellation classification, not fraud; disjoint local real-data shards."""
from functools import lru_cache
import datetime,math
import numpy as np
from . import public_dataset
NAMES=['绝对金额对数','商品件数绝对值对数','明细条数对数','平均单价对数','最高单价对数','最低非负单价对数','不同商品数对数','含匿名客户号','小时正弦','小时余弦','星期正弦','星期余弦','月份正弦','月份余弦','最高行数量绝对值对数','最低行数量绝对值对数','行数量绝对值总和对数','平均行数量绝对值对数','单价标准差对数','客户为欧盟地区']
def specs():return [{'key':f'uciFeature{i}','name':n,'level':'P2'} for i,n in enumerate(NAMES)]
@lru_cache(maxsize=2)
def arrays(fingerprint):
    with public_dataset.connect() as c:
        rows=c.execute('''SELECT o.*,AVG(CAST(r.unit_price AS REAL)) mean_price,MAX(CAST(r.unit_price AS REAL)) max_price,MIN(MAX(0,CAST(r.unit_price AS REAL))) min_price,COUNT(DISTINCT r.stock_code) stocks,MAX(ABS(r.quantity)) max_qty,MIN(ABS(r.quantity)) min_qty,SUM(ABS(r.quantity)) sum_qty,AVG(ABS(r.quantity)) mean_qty,AVG(CAST(r.unit_price AS REAL)*CAST(r.unit_price AS REAL)) square_price FROM orders o JOIN raw_lines r ON o.invoice_no=r.invoice_no AND o.customer_id=r.customer_id AND o.country=r.country WHERE o.status IN ('purchase','cancellation') GROUP BY o.code ORDER BY o.occurred_at,o.code''').fetchall()
    x=[];y=[];dates=[]
    def log(v):return math.log1p(max(0,float(v or 0)))
    for r in rows:
        dt=datetime.datetime.strptime(r['occurred_at'],'%Y-%m-%d %H:%M:%S');h=dt.hour*math.pi/12;wd=dt.weekday()*math.pi/3.5;mo=dt.month*math.pi/6
        x.append([log(abs(r['amount_pence'])/100),log(abs(r['quantity'])),log(r['line_count']),log(r['mean_price']),log(r['max_price']),log(r['min_price']),log(r['stocks']),float(bool(r['customer_id'])),math.sin(h),math.cos(h),math.sin(wd),math.cos(wd),math.sin(mo),math.cos(mo),log(r['max_qty']),log(r['min_qty']),log(r['sum_qty']),log(r['mean_qty']),log(math.sqrt(max(0,r['square_price']-r['mean_price']**2))),float(r['dest_region']=='EU')]);y.append(int(r['status']=='cancellation'));dates.append(r['occurred_at'])
    x=np.asarray(x);y=np.asarray(y);train_end=int(len(x)*.7);test_start=int(len(x)*.8);mean=x[:train_end].mean(0);scale=x[:train_end].std(0)+1e-9;x=(x-mean)/scale
    return x[:train_end],y[:train_end],x[test_start:],y[test_start:],{'datasetId':'uci-online-retail-352','target':'取消发票标记（不是欺诈）','split':'按时间70%训练、10%校准阈值、20%测试；本地节点按索引互斥分片','trainingRows':train_end,'calibrationRows':test_start-train_end,'testRows':len(x)-test_start,'trainingEnd':dates[train_end-1],'calibrationStart':dates[train_end],'calibrationEnd':dates[test_start-1],'testStart':dates[test_start],'sourceHash':fingerprint,'normalization':'仅使用训练区间均值与标准差；阈值仅在校准集选择；全部在本机进行'},x[train_end:test_start],y[train_end:test_start]
def data():return arrays(public_dataset.manifest()['workbookSha256'])[:5]
def calibration():return arrays(public_dataset.manifest()['workbookSha256'])[-2:]
