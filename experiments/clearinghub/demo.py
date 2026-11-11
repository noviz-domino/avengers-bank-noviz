"""로컬 ClearingHub 저장소를 인자로 받아 가짜 계좌의 실제 HTTP 연결을 시험한다."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

import httpx
import uvicorn

from test_bank import keys
from signing import sign_request, verify_response


def ready(url):
    for _ in range(100):
        try:
            httpx.get(url, timeout=0.3)
            return
        except httpx.HTTPError:
            time.sleep(0.1)
    raise RuntimeError(f'서버 시작 실패: {url}')


def main():
    repo = Path(sys.argv[1]).resolve()
    hub = 'http://127.0.0.1:18080'
    private, public = keys()
    with tempfile.TemporaryDirectory(prefix='clearinghub-demo-') as temp:
        env = {**os.environ, 'DATABASE_URL': 'sqlite+aiosqlite:///' + Path(temp, 'hub.db').as_posix(),
               'PYTHONPATH': str(repo / 'src'), 'PYTHONIOENCODING': 'utf-8'}
        for name in ('ADMIN_TOKEN', 'HUB_SIGNING_KEY', 'SIM_SIGNING_KEY'):
            env.pop(name, None)
        with open(Path(temp, 'hub.log'), 'w', encoding='utf-8') as log:
            process = subprocess.Popen([sys.executable, '-m', 'clearing_hub.devserver', '--hub-port', '18080', '--sim-port', '18180'], cwd=temp, env=env, stdout=log, stderr=log)
            server = None
            try:
                ready(hub + '/docs')
                values = dict(line.split('=', 1) for line in Path(temp, '.env.dev').read_text(encoding='utf-8').splitlines() if line and not line.startswith('#'))
                from clearing_hub.core.signing import public_key_of, fingerprint
                hub_public = public_key_of(values['HUB_SIGNING_KEY'])
                os.environ.update(BANK_PRIVATE_KEY=private, HUB_PUBLIC_KEY=hub_public)
                import bank
                server = uvicorn.Server(uvicorn.Config(bank.app, host='127.0.0.1', port=18300, log_level='error'))
                thread = threading.Thread(target=server.run, daemon=True)
                thread.start()
                ready('http://127.0.0.1:18300/docs')
                with httpx.Client(base_url=hub, timeout=15) as client:
                    invite = client.post('/admin/invites', json={'note': 'isolated local demo'}, headers={'X-Admin-Token': values['ADMIN_TOKEN']})
                    invite.raise_for_status()
                    response = client.post('/v1/banks/register', json={'invite_code': invite.json()['code'], 'name': 'LocalDemoBank', 'base_url': 'http://127.0.0.1:18300/interbank', 'public_key': public})
                    response.raise_for_status()
                    registration = response.json()
                    assert fingerprint(registration['hub_public_key']) == fingerprint(hub_public)
                    assert verify_response(hub_public, response.headers['X-Response-Timestamp'], response.status_code, '', response.content, response.headers['X-Response-Signature'])
                    assert registration['ping']['ok']

                    def call(method, path, payload=None):
                        body = json.dumps(payload).encode() if payload is not None else b''
                        signed = sign_request(private, method, path, body)
                        result = client.request(method, path, content=body, headers={**signed, 'X-Bank-Code': registration['bank_code'], 'X-Api-Key': registration['api_key'], 'Content-Type': 'application/json'})
                        assert verify_response(hub_public, result.headers['X-Response-Timestamp'], result.status_code, signed['X-Signature'], result.content, result.headers['X-Response-Signature'])
                        result.raise_for_status()
                        return result.json()

                    first = call('POST', '/v1/test-receive', {'to_account': '110-123-000001', 'amount': 1000})
                    assert first['status'] == 'COMPLETED'
                    tid = first['transfer_id']
                    duplicate = call('POST', f'/v1/test-receive/{tid}/resend')
                    assert duplicate['receiver_reply']['status'] == 200
                    assert len(bank.received) == 1
                    invalid = httpx.post('http://127.0.0.1:18300/interbank/receive', json={})
                    assert invalid.status_code == 401
                    report = {'registration': 'PASS', 'ping': 'PASS', 'signed_response': 'PASS', 'receive': first['status'], 'amount': 1000, 'requests': 2, 'stored_receipts': len(bank.received), 'unsigned_request_http': invalid.status_code, 'transfer_id': tid, 'target': hub, 'real_bank_db_connected': False}
                    Path(__file__).with_name('demo-result.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
                    print(json.dumps(report, ensure_ascii=False, indent=2))
            finally:
                if server:
                    server.should_exit = True
                    thread.join(timeout=5)
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    process.terminate()
                process.wait(timeout=10)


if __name__ == '__main__':
    main()
