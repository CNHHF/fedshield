"""Create an isolated environment and prepare the prebuilt demo or source checkout."""
from pathlib import Path
import os
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]

def main():
    if sys.version_info < (3, 12):
        raise SystemExit('Python 3.12 or newer is required; Python 3.12/3.13 is recommended.')
    folder = ROOT / '.venv'
    python = folder / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
    if not python.exists():
        venv.EnvBuilder(with_pip=True).create(folder)
    subprocess.run([str(python), '-m', 'pip', 'install', '-r', str(ROOT / 'requirements.txt')], check=True)
    if not (ROOT / 'frontend/dist/index.html').is_file():
        npm = shutil.which('npm.cmd' if os.name == 'nt' else 'npm')
        if not npm:
            raise SystemExit('Source checkout needs Node.js 20+ to build frontend; the demo ZIP has it prebuilt.')
        subprocess.run([npm, 'ci'], cwd=ROOT / 'frontend', check=True)
        subprocess.run([npm, 'run', 'build'], cwd=ROOT / 'frontend', check=True)
    if not (ROOT / 'instance/public_data/transactions.sqlite').is_file():
        print('Public transactions are missing. Importing the attributed UCI dataset.', flush=True)
        subprocess.run([str(python), str(ROOT / 'tools/import_public_transactions.py')], cwd=ROOT, check=True)
    print('Ready. Run start.bat on Windows, or .venv/bin/python tools/launch_peer.py elsewhere.')

if __name__ == '__main__':
    main()
