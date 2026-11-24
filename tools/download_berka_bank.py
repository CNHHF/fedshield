"""Read-only export of CTU's public financial database into local raw snapshots."""
from pathlib import Path
import pymysql,json,hashlib,datetime,sys,os
ROOT=Path(__file__).resolve().parents[1]
TABLES={'account','card','client','disp','district','loan','order','trans'}
def main():
    sys.stdout.reconfigure(encoding='utf-8');folder=ROOT/'instance/financial_data/raw/berka';folder.mkdir(parents=True,exist_ok=True)
    # Public read-only repository credentials documented by CTU, not user credentials.
    conn=pymysql.connect(host='relational.fel.cvut.cz',port=3306,user='guest',password='ctu-relational',database='financial',connect_timeout=15,read_timeout=90,cursorclass=pymysql.cursors.SSDictCursor,charset='utf8mb4')
    metadata={'source':'https://relational.fel.cvut.cz/dataset/Financial','retrievedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'tables':{}}
    try:
        selected=TABLES-{'trans'} if '--metadata-only' in sys.argv else TABLES
        for table in sorted(selected):
            path=folder/(table+'.jsonl');meta=path.with_suffix('.json')
            if path.exists() and meta.exists():metadata['tables'][table]=json.loads(meta.read_text(encoding='utf-8'));print(table,'cached',flush=True);continue
            with conn.cursor() as cur:
                cur.execute('SELECT * FROM `'+table+'`')
                digest=hashlib.sha256();count=0;tmp=path.with_suffix('.part')
                with tmp.open('wb') as f:
                    for row in cur:
                        raw=(json.dumps(row,ensure_ascii=False,default=str,separators=(',',':'))+'\n').encode();digest.update(raw);f.write(raw);count+=1
                os.replace(tmp,path)
                item={'rows':count,'sha256':digest.hexdigest(),'bytes':path.stat().st_size,'query':'SELECT * FROM `'+table+'`'}
                meta.write_text(json.dumps(item,indent=2),encoding='utf-8');metadata['tables'][table]=item;print(table,count,flush=True)
    finally:conn.close()
    (folder/'manifest.json').write_text(json.dumps(metadata,ensure_ascii=False,indent=2),encoding='utf-8')
if __name__=='__main__':main()
