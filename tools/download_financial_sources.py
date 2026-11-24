"""Fetch named public sources; store immutable snapshots and non-secret provenance."""
from pathlib import Path
import requests,hashlib,json,datetime,os,concurrent.futures,sys
ROOT=Path(__file__).resolve().parents[1]
FOLDER=ROOT/'instance/financial_data/raw'
SOURCES={
 'card':('https://data.openml.org/datasets/0000/1597/dataset_1597.pq','creditcard.parquet'),
 'card_metadata':('https://www.openml.org/api/v1/json/data/1597','creditcard-metadata.json'),
 'ecb':('https://www.ecb.europa.eu/stats/eurofxref/eurofxref-hist.zip','ecb-fx.zip'),
 'wb_countries':('https://api.worldbank.org/v2/country?format=json&per_page=400','wb-countries.json'),
 'wb_in':('https://api.worldbank.org/v2/country/all/indicator/BX.TRF.PWKR.CD.DT?format=json&date=2000:2025&per_page=20000','wb-remittances-in.json'),
 'wb_out':('https://api.worldbank.org/v2/country/all/indicator/BM.TRF.PWKR.CD.DT?format=json&date=2000:2025&per_page=20000','wb-remittances-out.json'),
 'ofac':('https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/SDN.CSV','ofac-sdn.csv'),
 'ofac_alias':('https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ALT.CSV','ofac-alias.csv'),
 'ofac_address':('https://sanctionslistservice.ofac.treas.gov/api/PublicationPreview/exports/ADD.CSV','ofac-address.csv')}
def fetch(item):
    key,(url,name)=item;path=FOLDER/name;meta=path.with_suffix(path.suffix+'.source.json')
    if path.exists() and meta.exists():return {'source':key,'cached':True,'bytes':path.stat().st_size}
    temp=path.with_suffix(path.suffix+'.part')
    for attempt in range(2):
        try:
            digest=hashlib.sha256();size=0
            with requests.get(url,stream=True,timeout=(15,100)) as r:
                r.raise_for_status()
                if 'text/html' in r.headers.get('Content-Type',''):raise ValueError('Expected data, received HTML')
                with temp.open('wb') as f:
                    for chunk in r.iter_content(1024*1024):
                        size+=len(chunk)
                        if size>350*1024*1024:raise ValueError('Source exceeds size limit')
                        digest.update(chunk);f.write(chunk)
                provenance={'source':key,'url':url,'retrievedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'sha256':digest.hexdigest(),'bytes':size,'httpLastModified':r.headers.get('Last-Modified'),'etag':r.headers.get('ETag')}
            os.replace(temp,path);meta.write_text(json.dumps(provenance,ensure_ascii=False,indent=2),encoding='utf-8')
            return {'source':key,'bytes':size,'sha256':digest.hexdigest()}
        except Exception:
            if temp.exists():temp.unlink()
            if attempt:raise
def main():
    sys.stdout.reconfigure(encoding='utf-8');FOLDER.mkdir(parents=True,exist_ok=True)
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures={ex.submit(fetch,i):i[0] for i in SOURCES.items()}
        for future in concurrent.futures.as_completed(futures):
            try:print(json.dumps(future.result(),ensure_ascii=False),flush=True)
            except Exception as e:
                failures.append(futures[future]);print(json.dumps({'source':futures[future],'error':type(e).__name__},ensure_ascii=False),flush=True)
    if failures:raise SystemExit('Downloads incomplete: '+','.join(failures))
if __name__=='__main__':main()
