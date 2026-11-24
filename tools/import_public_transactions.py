"""Download UCI 352 and build a reproducible raw/normalized SQLite database."""
from pathlib import Path
import sqlite3,requests,zipfile,hashlib,json,datetime,sys,os
from decimal import Decimal,ROUND_HALF_UP
from openpyxl import load_workbook
ROOT=Path(__file__).resolve().parents[1]
URL='https://archive.ics.uci.edu/static/public/352/online+retail.zip'
SOURCE='https://archive.ics.uci.edu/dataset/352/online-retail'
EU={'Austria','Belgium','Cyprus','Czech Republic','Denmark','EIRE','Finland','France','Germany','Greece','Italy','Lithuania','Malta','Netherlands','Poland','Portugal','Spain','Sweden','European Community'}
def region(country):
    if country in EU:return 'EU'
    return {'United Kingdom':'UK','USA':'US','Canada':'NA','Australia':'APAC','Japan':'APAC','Hong Kong':'CN','Singapore':'SEA','Israel':'ME','Bahrain':'ME','United Arab Emirates':'ME','Saudi Arabia':'ME','Brazil':'LATAM','RSA':'AF'}.get(country,'OTHER')
def main():
    sys.stdout.reconfigure(encoding='utf-8')
    folder=ROOT/'instance/public_data';folder.mkdir(parents=True,exist_ok=True)
    archive=folder/'uci-online-retail.zip'
    if not archive.exists():
        tmp=folder/'download.part'
        with requests.get(URL,stream=True,timeout=(20,90)) as r:
            r.raise_for_status()
            with tmp.open('wb') as f:
                for chunk in r.iter_content(1024*1024):f.write(chunk)
        os.replace(tmp,archive)
    sha=hashlib.sha256(archive.read_bytes()).hexdigest()
    xlsx=folder/'Online Retail.xlsx'
    if not xlsx.exists():
        with zipfile.ZipFile(archive) as z:
            with xlsx.open('wb') as f:f.write(z.read('Online Retail.xlsx'))
    final=folder/'transactions.sqlite';tmpdb=folder/'transactions.build.sqlite'
    if tmpdb.exists():tmpdb.unlink()
    con=sqlite3.connect(tmpdb)
    con.executescript('''CREATE TABLE raw_lines(source_row INTEGER PRIMARY KEY, invoice_no TEXT,stock_code TEXT,description TEXT,quantity INTEGER,invoice_date TEXT,unit_price TEXT,customer_id TEXT,country TEXT,line_amount_pence INTEGER);
CREATE TABLE orders(code TEXT PRIMARY KEY,invoice_no TEXT,customer_id TEXT,country TEXT,dest_region TEXT,occurred_at TEXT,amount_pence INTEGER,line_count INTEGER,quantity INTEGER,status TEXT);
CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT);''')
    book=load_workbook(xlsx,read_only=True,data_only=True);sheet=book.active
    header=next(sheet.iter_rows(values_only=True));assert tuple(header)==('InvoiceNo','StockCode','Description','Quantity','InvoiceDate','UnitPrice','CustomerID','Country'),header
    batch=[];count=0;missing_customer=0
    for rowno,row in enumerate(sheet.iter_rows(min_row=2,values_only=True),2):
        inv,stock,description,quantity,date,price,customer,country=row
        inv=str(inv);customer='' if customer is None else str(int(customer));missing_customer+=not bool(customer)
        amount=int((Decimal(str(price))*Decimal(quantity)*100).quantize(Decimal('1'),rounding=ROUND_HALF_UP))
        batch.append((rowno,inv,str(stock),description,int(quantity),date.strftime('%Y-%m-%d %H:%M:%S'),str(price),customer,str(country),amount));count+=1
        if len(batch)>=5000:con.executemany('INSERT INTO raw_lines VALUES(?,?,?,?,?,?,?,?,?,?)',batch);batch=[]
    if batch:con.executemany('INSERT INTO raw_lines VALUES(?,?,?,?,?,?,?,?,?,?)',batch)
    book.close()
    con.executescript('CREATE INDEX raw_invoice ON raw_lines(invoice_no); CREATE INDEX raw_customer ON raw_lines(customer_id);')
    aggregates=con.execute('SELECT invoice_no,customer_id,country,MIN(invoice_date),SUM(line_amount_pence),COUNT(*),SUM(quantity) FROM raw_lines GROUP BY invoice_no,customer_id,country').fetchall()
    for inv,customer,country,date,amount,lines,quantity in aggregates:
        status='cancellation' if inv.upper().startswith('C') else 'non_positive' if amount<=0 or quantity<=0 else 'purchase'
        code='UCI352-'+inv+'-'+hashlib.sha256((customer+'|'+country).encode()).hexdigest()[:8]
        con.execute('INSERT INTO orders VALUES(?,?,?,?,?,?,?,?,?,?)',(code,inv,customer,country,region(country),date,amount,lines,quantity,status))
    manifest={'datasetId':'uci-online-retail-352','name':'UCI Online Retail','sourceUrl':SOURCE,'downloadUrl':URL,'doi':'10.24432/C5BW33','license':'CC BY 4.0','attribution':'Chen, D. (2015). Online Retail. UCI Machine Learning Repository.','downloadedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'archiveSha256':sha,'workbookSha256':hashlib.sha256(xlsx.read_bytes()).hexdigest(),'rawRows':count,'orders':len(aggregates),'eligibleOrders':con.execute("SELECT COUNT(*) FROM orders WHERE status='purchase'").fetchone()[0],'missingCustomerRows':missing_customer,'countries':con.execute('SELECT COUNT(DISTINCT country) FROM raw_lines').fetchone()[0],'currency':'GBP','period':'2010-12-01 / 2011-12-09','seller':'UK-based anonymous online retailer','transformation':'保留全部原始明细；按发票号、原客户号和客户国家汇总，金额按Quantity×UnitPrice逐行以便士舍入后求和。取消及非正数订单保留入库，但不进入默认付款批次。','limitations':'无银行卡号、真实商户名称或欺诈标签。商户展示为数据集匿名零售商；地区为国家分组，不是原始跨境支付路由。'}
    con.execute('INSERT INTO metadata VALUES(?,?)',('manifest',json.dumps(manifest,ensure_ascii=False)))
    con.commit();assert con.execute('PRAGMA integrity_check').fetchone()[0]=='ok';con.close()
    if final.exists():
        backup=folder/('transactions-before-'+datetime.datetime.now().strftime('%Y%m%d%H%M%S')+'.sqlite');os.replace(final,backup)
    os.replace(tmpdb,final)
    (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(manifest,ensure_ascii=False,indent=2),flush=True)
if __name__=='__main__':main()
