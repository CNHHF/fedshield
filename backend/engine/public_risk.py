"""Unsupervised anomaly screening fitted only on real UCI purchase orders."""
from functools import lru_cache
import datetime,math
import numpy as np
from . import public_dataset
NAMES=['订单金额（对数）','商品件数（对数）','明细数（对数）','开票小时','星期序号']
def features(row):
    date=datetime.datetime.strptime(row['occurredAt'],'%Y-%m-%d %H:%M:%S')
    return [math.log1p(max(0,row['amount'])),math.log1p(max(0,row['quantity'])),math.log1p(max(0,row['lineCount'])),date.hour/23,date.weekday()/6]
@lru_cache(maxsize=2)
def fitted(fingerprint):
    from sklearn.ensemble import IsolationForest
    rows=sorted(public_dataset.orders()[0],key=lambda r:(r['occurredAt'],r['code']))
    x=np.asarray([features(r) for r in rows]);cut=int(len(x)*.8);train,test=x[:cut],x[cut:]
    m=IsolationForest(n_estimators=100,max_samples=256,random_state=20261110,n_jobs=1).fit(train)
    calibration=np.sort(-m.score_samples(train));hold=-m.score_samples(test)
    percentile=np.searchsorted(calibration,hold,side='right')/len(calibration)
    center=np.median(train,axis=0);scale=np.maximum(np.median(abs(train-center),axis=0),.05)
    meta={'name':'Isolation Forest · 真实公开订单异常初筛','kind':'anomaly','trainingRows':len(train),'validationRows':len(test),
        'validationAuc':None,'validationAlertRate':round(float(np.mean(percentile>=.98)),4),'features':NAMES,
        'trainingEnd':rows[cut-1]['occurredAt'],'validationStart':rows[cut]['occurredAt'],'threshold':.98,'seed':20261110,
        'scope':'UCI真实正向订单按时间前80%拟合，后20%观察告警率。无欺诈标签；异常分位不等于欺诈概率，不编造AUC或置信度。',
        'datasetId':'uci-online-retail-352','sourceHash':fingerprint}
    return m,calibration,center,scale,meta
def model():
    if not public_dataset.available():
        from ..utils.response import ApiError
        raise ApiError('真实训练数据尚未就绪，不回退合成模型',code=503)
    return fitted(public_dataset.manifest()['workbookSha256'])
def score(row,compliance_passed):
    m,calibration,center,scale,meta=model();x=np.asarray(features(row));raw=float(-m.score_samples(x.reshape(1,-1))[0]);percentile=float(np.searchsorted(calibration,raw,side='right')/len(calibration))
    decision='blocked' if not compliance_passed else 'manual' if percentile>=.98 else 'approve'
    reason='合规要件未满足' if not compliance_passed else '异常分位达到98%，需人工核查；不等于欺诈' if decision=='manual' else '异常分位低于98%，初筛通过；不代表资金已放行'
    distance=abs((x-center)/scale);order=np.argsort(distance)[::-1][:3]
    return {'code':row['code'],'riskScore':round(percentile,5),'scoreKind':'anomaly','confidence':None,'decision':decision,'reason':reason,
        'factorBasis':'特征相对训练中位数的稳健偏离，仅用于核查，不是模型因果贡献。',
        'factors':[{'name':NAMES[i],'contribution':round(float(distance[i]),3)} for i in order]}
