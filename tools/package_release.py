"""Build source and shareable demo ZIPs without local secrets or private runtime state."""
from pathlib import Path
import argparse
import datetime
import hashlib
import json
import re
import shutil
import sqlite3
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = ('UCI-352', 'ECB-FX', 'WB-REMIT', 'OFAC-SDN')

def copy_sources(target):
    root_files = ['README.md', 'AGENTS.md', '.gitignore', '.gitattributes', 'requirements.txt',
                  'run.py', 'start-backend.bat', 'start-frontend.bat', 'setup.bat', 'start.bat']
    files = [ROOT / name for name in root_files]
    files += [p for p in (ROOT / 'backend').rglob('*.py') if '__pycache__' not in p.parts]
    files += list((ROOT / 'backend/engine').glob('*.sql'))
    files += [p for p in (ROOT / 'frontend/src').rglob('*') if p.is_file()]
    files += [ROOT / 'frontend' / name for name in ['index.html', 'package.json', 'package-lock.json', 'vite.config.js', '.env.example']]
    files += list((ROOT / 'docs').glob('*.md'))
    files += [p for p in (ROOT / 'docs/examples').glob('*') if p.is_file()]
    files += list((ROOT / 'tools').glob('*.py'))
    for path in files:
        if not path.is_file():
            raise ValueError('Required release source is missing: ' + str(path.relative_to(ROOT)))
        dest = target / path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)

def safe_warehouse(target):
    folder = target / 'instance/financial_data'
    folder.mkdir(parents=True, exist_ok=True)
    source = ROOT / 'instance/financial_data/fedshield_finance.sqlite'
    c = sqlite3.connect(folder / 'fedshield_finance.sqlite', uri=True)
    try:
        c.executescript((ROOT / 'backend/engine/financial_schema.sql').read_text(encoding='utf-8'))
        # Read-only attachment; original warehouse and private application DB are never changed.
        c.execute('ATTACH DATABASE ? AS original', (source.resolve().as_uri() + '?mode=ro',))
        placeholders = ','.join('?' for _ in ALLOWED)
        for table in ['sources', 'source_files', 'countries', 'parties', 'transactions', 'exchange_rates', 'macro_indicators',
                      'risk_entities', 'quality_checks', 'field_lineage']:
            field = 'id' if table == 'sources' else 'source_id'
            c.execute(f'INSERT INTO main.{table} SELECT * FROM original.{table} WHERE {field} IN ({placeholders})', ALLOWED)
        for table in ['risk_aliases', 'risk_addresses']:
            c.execute(f'INSERT INTO main.{table} SELECT a.* FROM original.{table} a JOIN main.risk_entities e ON e.id=a.entity_id')
        counts = {sid: c.execute('SELECT row_count FROM sources WHERE id=?', (sid,)).fetchone()[0] for sid in ALLOWED}
        stats = {
            'financialTransactions': 0, 'commerceOrders': counts['UCI-352'], 'accounts': 0,
            'parties': c.execute('SELECT count(*) FROM parties').fetchone()[0], 'loans': 0,
            'countries': c.execute('SELECT count(DISTINCT country_iso3) FROM macro_indicators WHERE value IS NOT NULL').fetchone()[0],
            'currencies': c.execute('SELECT count(DISTINCT quote_currency) FROM exchange_rates').fetchone()[0] + 1,
            'fxObservations': counts['ECB-FX'], 'macroObservations': counts['WB-REMIT'],
            'sanctionEntities': counts['OFAC-SDN'], 'aliases': c.execute('SELECT count(*) FROM risk_aliases').fetchone()[0],
            'rawFiles': c.execute('SELECT count(*) FROM source_files').fetchone()[0],
        }
        manifest = {'schemaVersion': 'fedshield-financial-v1', 'builtAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    'sourceCounts': counts, 'stats': stats,
                    'tables': [r[0] for r in c.execute("SELECT name FROM main.sqlite_master WHERE type='table' ORDER BY name")],
                    'database': 'fedshield_finance.sqlite',
                    'notes': 'Shareable public-source subset. Bank/card research data and model predictions excluded; see docs/DATA_ATTRIBUTION.md.'}
        c.execute('INSERT INTO warehouse_metadata VALUES(?,?)', ('manifest', json.dumps(manifest, ensure_ascii=False)))
        c.commit()
        assert c.execute('PRAGMA quick_check').fetchall() == [('ok',)]
        assert not c.execute('PRAGMA foreign_key_check').fetchall()
        assert c.execute('SELECT count(*) FROM transactions').fetchone()[0] == counts['UCI-352']
        (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        c.close()
    pub = target / 'instance/public_data'
    pub.mkdir(parents=True)
    with sqlite3.connect((ROOT / 'instance/public_data/transactions.sqlite').resolve().as_uri() + '?mode=ro', uri=True) as src:
        tables = {r[0] for r in src.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        if tables != {'raw_lines', 'orders', 'metadata'}:
            raise ValueError('Unexpected table in public source database; refusing to package it.')
        metadata = json.loads(src.execute("SELECT value FROM metadata WHERE key='manifest'").fetchone()[0])
        if src.execute('SELECT count(*) FROM raw_lines').fetchone()[0] != metadata['rawRows']:
            raise ValueError('Public source line count does not match its manifest.')
        if src.execute('SELECT count(*) FROM orders').fetchone()[0] != counts['UCI-352']:
            raise ValueError('Public order count does not match the share warehouse.')
        with sqlite3.connect(pub / 'transactions.sqlite') as dest:
            src.backup(dest)
            assert dest.execute('PRAGMA quick_check').fetchall() == [('ok',)]
    for name in ['manifest.json', 'Online Retail.xlsx']:
        shutil.copy2(ROOT / 'instance/public_data' / name, pub / name)
    # Only the redistributable reference snapshots and their source sidecars.
    raw = ROOT / 'instance/financial_data/raw'
    for p in raw.iterdir():
        if p.is_file() and p.name.startswith(('ecb-', 'wb-', 'ofac-')):
            dest = folder / 'raw' / p.name
            dest.parent.mkdir(exist_ok=True)
            shutil.copy2(p, dest)
    return manifest

def audit(folder):
    forbidden = {'deepseek.local.json', 'paillier_keys.json', 'workbench_vault.key', 'fedshield.db', 'peer_session.key'}
    patterns = [re.compile(rb'sk-[A-Za-z0-9_-]{20,}'), re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
    for p in folder.rglob('*'):
        if not p.is_file():
            continue
        rel = p.relative_to(folder)
        if p.name in forbidden or any(part in {'.git', '.venv', 'node_modules', '__pycache__'} for part in rel.parts):
            raise ValueError('Forbidden runtime or dependency file: ' + str(rel))
        if p.suffix.lower() in {'.py', '.js', '.vue', '.md', '.json', '.html', '.txt', '.bat', '.css', '.example'}:
            content = p.read_bytes()
            if any(pattern.search(content) for pattern in patterns):
                raise ValueError('Possible secret in release file: ' + str(rel))

def archive(folder, path):
    audit(folder)
    with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for p in sorted(folder.rglob('*')):
            if p.is_file():
                z.write(p, Path('FedShield') / p.relative_to(folder))
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
    return {'name': path.name, 'bytes': path.stat().st_size, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stage = output / 'staging'
    stage.mkdir()  # Refuse to overwrite a previous staging directory.
    source = stage / 'source'
    source.mkdir()
    copy_sources(source)
    code = archive(source, output / 'FedShield-source-20261124.zip')
    peer = stage / 'peer'
    shutil.copytree(source, peer)
    if not (ROOT / 'frontend/dist/index.html').is_file():
        raise SystemExit('Build frontend before packaging.')
    shutil.copytree(ROOT / 'frontend/dist', peer / 'frontend/dist')
    manifest = safe_warehouse(peer)
    package = archive(peer, output / 'FedShield-demo-20261124.zip')
    report = {'source': code, 'demo': package, 'data': manifest['stats'], 'excludedSources': ['CTU-BERKA', 'ULB-1597']}
    (output / 'package-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (output / 'SHA256SUMS.txt').write_text('\n'.join(x['sha256'] + '  ' + x['name'] for x in [code, package]) + '\n', encoding='ascii')
    print(json.dumps(report, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
