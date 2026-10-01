"""Verify all three public services without credentials in the image build."""
import http.server
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request

START = Path(os.environ.get('IUNO_START_SCRIPT', '/opt/iunoasc/start.sh'))

@unittest.skipUnless(shutil.which('nginx') and START.is_file(), 'integration runs in image build')
class GatewayTest(unittest.TestCase):
    def test_public_services(self):
        start = START.read_text()
        setup = start[start.index('cat > /tmp/iunoasc-nginx.conf'):start.index('\nnginx -c')]
        subprocess.run(['bash', '-euc', setup], check=True)
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'comfy-ok')
            def log_message(self, *args): pass
        backend = http.server.HTTPServer(('127.0.0.1', 3001), Handler)
        threading.Thread(target=backend.serve_forever, daemon=True).start()
        processes = []
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'outputs'
            output.mkdir()
            (output / 'result.txt').write_text('output-ok')
            env = {**os.environ, 'PYTHONPATH': '/opt/iunoasc', 'IUNO_DATA_DIR': directory}
            env.pop('PANEL_PASSWORD', None)
            try:
                subprocess.run(['nginx', '-t', '-c', '/tmp/iunoasc-nginx.conf'], check=True)
                subprocess.run(['nginx', '-c', '/tmp/iunoasc-nginx.conf'], check=True)
                for mode, port in [('models', 8081), ('outputs', 8083)]:
                    processes.append(subprocess.Popen(['python', '-m', 'uvicorn', 'panel.app:app', '--host', '0.0.0.0', '--port', str(port)], env={**env, 'PANEL_MODE': mode}))
                def get(port, path='/'):
                    for attempt in range(100):
                        try:
                            with urllib.request.urlopen(f'http://127.0.0.1:{port}{path}', timeout=2) as response:
                                self.assertNotIn('WWW-Authenticate', response.headers)
                                return response.read()
                        except urllib.error.URLError:
                            if attempt == 99: raise
                            time.sleep(.1)
                self.assertEqual(get(3000), b'comfy-ok')
                for port in [8081, 8083]:
                    self.assertIn(b'<!doctype html>', get(port))
                    self.assertTrue(get(port, '/app.js'))
                    self.assertTrue(get(port, '/style.css'))
                self.assertEqual(len(json.loads(get(8081, '/api/preset'))['files']), 5)
                self.assertIn('nodes', json.loads(get(8081, '/api/workflow')))
                presets = json.loads(get(8081, '/api/presets'))['presets']
                self.assertEqual([p['id'] for p in presets], ['native-h3', 'my-h3'])
                self.assertEqual(presets[1]['name'], 'LightSpeed H3')
                self.assertEqual(len(presets[1]['files']), 4)
                self.assertEqual(len(presets[1]['custom_nodes']), 1)
                lightspeed = json.loads(get(8081, '/api/workflow?preset=my-h3'))
                self.assertEqual(next(n for n in lightspeed['nodes'] if n['type']=='UNETLoader')['widgets_values'][0],
                                 'minimax_h3_fl2va_pruned_int8_convrot.safetensors')
                self.assertEqual(json.loads(get(8083, '/api/outputs'))['files'][0]['name'], 'result.txt')
                self.assertEqual(get(8083, '/api/outputs/file?path=result.txt'), b'output-ok')
                self.assertTrue(get(8083, '/api/outputs/archive').startswith(b'PK'))
            finally:
                for process in processes:
                    process.terminate()
                    process.wait(timeout=10)
                subprocess.run(['nginx', '-s', 'quit', '-c', '/tmp/iunoasc-nginx.conf'], check=False)
                backend.shutdown()
                backend.server_close()
                Path('/tmp/iunoasc-nginx.conf').unlink(missing_ok=True)

if __name__ == '__main__': unittest.main()
