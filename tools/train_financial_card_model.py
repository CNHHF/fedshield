"""Chronological, deduplicated supervised financial-fraud benchmark, not synthetic."""
from pathlib import Path
import json,hashlib,time,sqlite3,sys,datetime,os,uuid
import numpy as np,pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import precision_recall_curve,roc_auc_score,average_precision_score,precision_score,recall_score,f1_score,confusion_matrix
ROOT=Path(__file__).resolve().parents[1];FOLDER=ROOT/'instance/financial_data';MODEL_ROOT=FOLDER/'models/card'
def main():
    sys.stdout.reconfigure(encoding='utf-8');version=uuid.uuid4().hex;OUT=MODEL_ROOT/'versions'/version;OUT.mkdir(exist_ok=True,parents=True)
    source_hash=hashlib.sha256((FOLDER/'raw/creditcard.parquet').read_bytes()).hexdigest()
    if source_hash!=json.loads((FOLDER/'raw/creditcard.parquet.source.json').read_text())['sha256']:raise ValueError('Training snapshot hash mismatch')
    start=time.perf_counter();frame=pd.read_parquet(FOLDER/'raw/creditcard.parquet');columns=[f'V{i}' for i in range(1,29)]+['Amount','Time']
    y=frame['Class'].astype(int).to_numpy();x=frame[columns].to_numpy(dtype=float)
    keep=~frame[columns].duplicated(keep='first').to_numpy();times=frame.Time.to_numpy();ordered=np.flatnonzero(keep);ordered=ordered[np.argsort(times[ordered],kind='stable')]
    one=times[ordered[int(len(ordered)*.6)]];two=times[ordered[int(len(ordered)*.8)]]
    train=np.flatnonzero(keep&(times<one));validation=np.flatnonzero(keep&(times>=one)&(times<two));test=np.flatnonzero(keep&(times>=two))
    assert times[train].max()<times[validation].min() and times[validation].max()<times[test].min()
    model=HistGradientBoostingClassifier(max_iter=80,max_leaf_nodes=15,learning_rate=.08,l2_regularization=1,class_weight='balanced',early_stopping=False,random_state=20261110)
    print('training',len(train),'calibration',len(validation),'test',len(test),flush=True);model.fit(x[train],y[train])
    val=model.predict_proba(x[validation])[:,1];precision,recall,thresholds=precision_recall_curve(y[validation],val);f1=2*precision[:-1]*recall[:-1]/np.maximum(precision[:-1]+recall[:-1],1e-12);threshold=float(thresholds[int(np.argmax(f1))])
    scores=model.predict_proba(x)[:,1];pred=scores[test]>=threshold;tn,fp,fn,tp=map(int,confusion_matrix(y[test],pred).ravel())
    report={'status':'trained','model':'HistGradientBoostingClassifier','target':'原始信用卡欺诈标签Class','featureNames':columns,'sourceId':'ULB-1597','sourceSha256':json.loads((FOLDER/'raw/creditcard.parquet.source.json').read_text())['sha256'],'rawRows':len(frame),'deduplicatedRows':int(keep.sum()),'excludedDuplicates':int((~keep).sum()),'split':{'train':len(train),'calibration':len(validation),'test':len(test),'trainEndSeconds':float(times[train].max()),'calibrationStartSeconds':float(times[validation].min()),'calibrationEndSeconds':float(times[validation].max()),'testStartSeconds':float(times[test].min()),'trainFrauds':int(y[train].sum()),'calibrationFrauds':int(y[validation].sum()),'testFrauds':int(y[test].sum())},'threshold':threshold,'thresholdMethod':'仅在独立时间校准集最大化F1，测试标签不参与阈值选择','test':{'rocAuc':float(roc_auc_score(y[test],scores[test])),'prAuc':float(average_precision_score(y[test],scores[test])),'precision':float(precision_score(y[test],pred,zero_division=0)),'recall':float(recall_score(y[test],pred,zero_division=0)),'f1':float(f1_score(y[test],pred,zero_division=0)),'falsePositiveRate':fp/(fp+tn),'confusion':{'tn':tn,'fp':fp,'fn':fn,'tp':tp}},'seconds':round(time.perf_counter()-start,3),'builtAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'limitations':'两天历史匿名欧洲信用卡基准；PCA不可解释为真实身份或国家。仅基准验证，不保证未来跨境支付性能。分值未经真实欺诈概率校准，疑似记录需人工。'}
    tmp=OUT/'predictions.build.sqlite'
    if tmp.exists():tmp.unlink()
    c=sqlite3.connect(tmp);c.execute('CREATE TABLE predictions(transaction_id TEXT PRIMARY KEY, partition TEXT, model_score REAL, threshold REAL, decision TEXT)')
    c.execute('CREATE TABLE model_metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL)');c.executemany('INSERT INTO model_metadata VALUES(?,?)',[('modelVersion',version),('sourceSha256',source_hash)])
    partitions=np.full(len(frame),'excluded_duplicate',dtype=object);partitions[train]='train';partitions[validation]='calibration';partitions[test]='test'
    c.executemany('INSERT INTO predictions VALUES(?,?,?,?,?)',((f'CARD-{i+1:07d}',str(partitions[i]),float(scores[i]),threshold,'manual_review' if scores[i]>=threshold else 'initial_pass') for i in range(len(frame))))
    c.commit();c.close();os.replace(tmp,OUT/'predictions.sqlite')
    import joblib
    report['modelVersion']=version
    joblib.dump(model,OUT/'model.joblib');(OUT/'metrics.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    pointer={'version':version,'sourceSha256':source_hash,'metricsSha256':hashlib.sha256((OUT/'metrics.json').read_bytes()).hexdigest()}
    staging=MODEL_ROOT/'current.build.json';staging.write_text(json.dumps(pointer),encoding='utf-8');os.replace(staging,MODEL_ROOT/'current.json')
    print(json.dumps(report,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
