"""Pinned original-format mirror, cross-checked against the university SQL export."""
from pathlib import Path
import requests,csv,json,datetime,hashlib,os,sys,decimal
ROOT=Path(__file__).resolve().parents[1];FOLDER=ROOT/'instance/financial_data/raw/berka'
COMMIT='77e9972a1ead107e5f42a91dd989d587bff055a4'
URL=f'https://raw.githubusercontent.com/jlacko/berka-dataset/{COMMIT}/trans.asc'
def main():
    sys.stdout.reconfigure(encoding='utf-8');path=FOLDER/'trans.asc'
    if not path.exists():
        tmp=path.with_suffix('.download')
        with requests.get(URL,stream=True,timeout=(15,90)) as r:
            r.raise_for_status()
            with tmp.open('wb') as f:
                for chunk in r.iter_content(1024*1024):f.write(chunk)
        os.replace(tmp,path)
    reference={}
    for chunk in sorted((FOLDER/'chunks').glob('trans-*.json')):
        for r in json.loads(chunk.read_text(encoding='utf-8')):reference[int(r['trans_id'])]=r
    if len(reference)<10000:raise ValueError('Not enough university-export rows for mirror validation')
    digest=hashlib.sha256();count=0;matched=0;rounded=0;tmp=FOLDER/'trans-mirror.part'
    with path.open(encoding='utf-8-sig',newline='') as f,tmp.open('wb') as output:
        reader=csv.DictReader(f,delimiter=';')
        for r in reader:
            row={k:(None if v.strip()=='' else v.strip()) for k,v in r.items()}
            for k in ('trans_id','account_id'):row[k]=int(row[k])
            row['date']=datetime.datetime.strptime(row['date'],'%y%m%d').date().isoformat()
            for k in ('amount','balance'):row[k]=str(decimal.Decimal(row[k]))
            if row['account'] is not None:row['account']=str(int(row['account']))
            original=reference.get(row['trans_id'])
            if original:
                for key in ('account_id','date','type','operation','k_symbol','bank'):
                    norm=lambda v:None if v is None or not str(v).strip() else str(v).strip()
                    if norm(original.get(key))!=norm(row.get(key)):raise ValueError(f'Mirror differs from CTU at {row["trans_id"]}:{key}: {original.get(key)!r} vs {row.get(key)!r}')
                for key in ('amount','balance'):
                    actual=decimal.Decimal(row[key]);reference_value=decimal.Decimal(str(original[key]))
                    if reference_value!=actual:
                        if reference_value!=actual.quantize(decimal.Decimal('1'),rounding=decimal.ROUND_HALF_UP):raise ValueError(f'Mirror monetary mismatch {row["trans_id"]}/{key}: original={actual}, CTU={reference_value}')
                        rounded+=1
                matched+=1
            raw=(json.dumps(row,ensure_ascii=False,separators=(',',':'))+'\n').encode();digest.update(raw);output.write(raw);count+=1
    if count!=1056320 or matched!=len(reference):raise ValueError(f'Incomplete mirror: {count}, matched {matched}/{len(reference)}')
    os.replace(tmp,FOLDER/'trans.jsonl');retrieved=datetime.datetime.now(datetime.timezone.utc).isoformat()
    item={'rows':count,'sha256':digest.hexdigest(),'bytes':(FOLDER/'trans.jsonl').stat().st_size,'sourceUrl':URL,'query':'Original semicolon file parsed, dates normalized; validated against '+str(matched)+' independent CTU SQL-export records','crossCheckedCtuRows':matched,'ctuIntegerRoundedCells':rounded,'precisionNote':'Original mirror retains cents; CTU SQL version has integer-rounded amount/balance. Source IDs, account, date, type and rounded monetary values cross-checked; original decimal monetary values retained.'}
    (FOLDER/'trans.json').write_text(json.dumps(item,indent=2),encoding='utf-8')
    meta={'source':'https://relational.fel.cvut.cz/dataset/Financial','retrievedAt':retrieved,'tables':{}}
    for table in ('account','card','client','disp','district','loan','order','trans'):meta['tables'][table]=json.loads((FOLDER/(table+'.json')).read_text(encoding='utf-8'))
    (FOLDER/'manifest.json').write_text(json.dumps(meta,indent=2),encoding='utf-8')
    mirror={'source':'berka_mirror','url':URL,'retrievedAt':retrieved,'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'bytes':path.stat().st_size,'commit':COMMIT,'crossCheckedCtuRows':matched}
    (FOLDER/'trans.asc.source.json').write_text(json.dumps(mirror,indent=2),encoding='utf-8');print('Bank mirror imported:',count,'independent university rows matched:',matched,flush=True)
if __name__=='__main__':main()
