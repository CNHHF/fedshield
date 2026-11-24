"""Read-only compressed SQL export; bounded parallel chunks, resumable raw files."""
from pathlib import Path
import pymysql,json,zlib,hashlib,concurrent.futures,threading,datetime,os,sys
ROOT=Path(__file__).resolve().parents[1];FOLDER=ROOT/'instance/financial_data/raw/berka';CHUNK=50000
local=threading.local();connections=[];lock=threading.Lock()
def connection():
    if not getattr(local,'conn',None):
        local.conn=pymysql.connect(host='relational.fel.cvut.cz',port=3306,user='guest',password='ctu-relational',database='financial',connect_timeout=15,read_timeout=90)
        with local.conn.cursor() as c:c.execute('SET SESSION group_concat_max_len=32000000')
        with lock:connections.append(local.conn)
    return local.conn
def chunk(index):
    path=FOLDER/'chunks'/f'trans-{index:03d}.json'
    if path.exists():return len(json.loads(path.read_text(encoding='utf-8')))
    with connection().cursor() as c:
        c.execute("SELECT COMPRESS(CONCAT('[',GROUP_CONCAT(JSON_OBJECT('trans_id',trans_id,'account_id',account_id,'date',date,'type',type,'operation',operation,'amount',amount,'balance',balance,'k_symbol',k_symbol,'bank',bank,'account',account) ORDER BY trans_id SEPARATOR ','),']')) FROM (SELECT * FROM trans ORDER BY trans_id LIMIT %s OFFSET %s) t",(CHUNK,index*CHUNK))
        data=c.fetchone()[0]
    raw=zlib.decompress(data[4:]);rows=json.loads(raw)
    # Malformed/truncated aggregate never becomes a completed chunk.
    if not rows or len(rows)>CHUNK:raise ValueError('Invalid chunk size')
    tmp=path.with_suffix('.part');tmp.write_bytes(raw);os.replace(tmp,path)
    return len(rows)
def main():
    sys.stdout.reconfigure(encoding='utf-8');(FOLDER/'chunks').mkdir(exist_ok=True,parents=True)
    with connection().cursor() as q:q.execute('SELECT count(*) FROM trans');total=q.fetchone()[0]
    print('expected',total,flush=True)
    try:
        if '--reference-only' in sys.argv:
            path=FOLDER/'chunks'/'trans-reference.json'
            if not path.exists():
                with connection().cursor() as q:
                    q.execute("SELECT COMPRESS(CONCAT('[',GROUP_CONCAT(JSON_OBJECT('trans_id',trans_id,'account_id',account_id,'date',date,'type',type,'operation',operation,'amount',amount,'balance',balance,'k_symbol',k_symbol,'bank',bank,'account',account) SEPARATOR ','),']')) FROM (SELECT * FROM trans ORDER BY trans_id LIMIT 10000) t")
                    raw=zlib.decompress(q.fetchone()[0][4:]);rows=json.loads(raw)
                    if len(rows)!=10000:raise ValueError('Reference sample incomplete')
                    path.write_bytes(raw)
            print('reference sample ready',flush=True);return
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
            futures={ex.submit(chunk,i):i for i in range((total+CHUNK-1)//CHUNK)}
            for f in concurrent.futures.as_completed(futures):print('chunk',futures[f],'rows',f.result(),flush=True)
        digest=hashlib.sha256();count=0;tmp=FOLDER/'trans-batch.part'
        with tmp.open('wb') as f:
            for i in range((total+CHUNK-1)//CHUNK):
                for row in json.loads((FOLDER/'chunks'/f'trans-{i:03d}.json').read_text(encoding='utf-8')):
                    raw=(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n').encode();digest.update(raw);f.write(raw);count+=1
        if count!=total:raise ValueError('Export count mismatch')
        os.replace(tmp,FOLDER/'trans.jsonl');item={'rows':count,'sha256':digest.hexdigest(),'bytes':(FOLDER/'trans.jsonl').stat().st_size,'query':'SELECT original columns FROM trans ORDER BY trans_id, compressed in read-only 50000-row batches'}
        (FOLDER/'trans.json').write_text(json.dumps(item,indent=2),encoding='utf-8')
        meta={'source':'https://relational.fel.cvut.cz/dataset/Financial','retrievedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tables':{}}
        for table in ('account','card','client','disp','district','loan','order','trans'):meta['tables'][table]=json.loads((FOLDER/(table+'.json')).read_text(encoding='utf-8'))
        (FOLDER/'manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8');print('completed',count,flush=True)
    finally:
        for conn in connections:conn.close()
if __name__=='__main__':main()
