"""Start the local demo with fresh per-installation secrets and open its actual port."""
from pathlib import Path
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if not (ROOT / 'frontend/dist/index.html').is_file():
        raise SystemExit('Missing frontend build. Run setup.bat first.')
    port = None
    for candidate in range(args.port, min(args.port + 11, 65536)):
        with socket.socket() as probe:
            try:
                probe.bind(('127.0.0.1', candidate))
                port = candidate
                break
            except OSError:
                pass
    if port is None:
        raise SystemExit('No free local port found. Stop another demo or pass --port.')
    instance = ROOT / 'instance'
    instance.mkdir(exist_ok=True)
    secret_file = instance / 'peer_session.key'
    # Exclusive creation avoids replacing the key when two launchers start together.
    try:
        with secret_file.open('x', encoding='ascii') as stream:
            stream.write(secrets.token_hex(32))
    except FileExistsError:
        pass
    env = dict(os.environ)
    env.setdefault('FEDSHIELD_SECRET_KEY', secret_file.read_text(encoding='ascii').strip())
    process = subprocess.Popen([sys.executable, 'run.py', '--port', str(port)], cwd=ROOT, env=env)
    url = f'http://127.0.0.1:{port}/'
    opener = build_opener(ProxyHandler({}))
    try:
        for _ in range(90):
            if process.poll() is not None:
                raise SystemExit('Server exited during startup. Review the console error above.')
            try:
                with opener.open(url + 'api/health', timeout=2) as response:
                    if json.load(response).get('data', {}).get('service') == 'fedshield-backend':
                        break
            except (OSError, ValueError):
                pass
            time.sleep(1)
        else:
            raise SystemExit('Startup timed out. Review the console error above.')
        print(f'FedShield: {url}\nAccount: risk.officer / FedShield@2026 / MFA 123456', flush=True)
        if not args.no_browser:
            webbrowser.open(url)
        return process.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()

if __name__ == '__main__':
    sys.exit(main())
