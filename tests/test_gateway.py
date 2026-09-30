"""Exercise the actual startup auth configuration without requiring a GPU."""
import base64
import http.server
import os
from pathlib import Path
import shutil
import subprocess
import threading
import unittest
import urllib.error
import urllib.request


@unittest.skipUnless(shutil.which("nginx") and
                     Path(os.environ.get("IUNO_START_SCRIPT", "/opt/iunoasc/start.sh")).is_file(),
                     "nginx integration test runs in the image build")
class GatewayAuthTest(unittest.TestCase):
    def test_worker_can_read_password_file(self):
        start = Path(os.environ.get("IUNO_START_SCRIPT", "/opt/iunoasc/start.sh")).read_text()
        setup = start[start.index("printf 'iunoasc:"):start.index("\nnginx -c")]
        subprocess.run(["bash", "-euc", setup], check=True,
                       env={**os.environ, "PANEL_PASSWORD": "gateway-build-test"})
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"gateway-ok")
            def log_message(self, *args):
                pass
        backend = http.server.HTTPServer(("127.0.0.1", 3001), Handler)
        threading.Thread(target=backend.serve_forever, daemon=True).start()
        subprocess.run(["nginx", "-t", "-c", "/tmp/iunoasc-nginx.conf"], check=True)
        subprocess.run(["nginx", "-c", "/tmp/iunoasc-nginx.conf"], check=True)
        try:
            for credentials, expected in [(None, 401), ("iunoasc:wrong", 401),
                                           ("iunoasc:gateway-build-test", 200)]:
                headers = {} if credentials is None else {
                    "Authorization": "Basic " + base64.b64encode(credentials.encode()).decode()}
                request = urllib.request.Request("http://127.0.0.1:3000/", headers=headers)
                try:
                    with urllib.request.urlopen(request, timeout=5) as response:
                        code = response.status
                        self.assertEqual(response.read(), b"gateway-ok")
                except urllib.error.HTTPError as error:
                    code = error.code
                self.assertEqual(code, expected)
        finally:
            subprocess.run(["nginx", "-s", "quit", "-c", "/tmp/iunoasc-nginx.conf"], check=True)
            backend.shutdown()
            backend.server_close()
            for name in ["/tmp/iunoasc.htpasswd", "/tmp/iunoasc-nginx.conf"]:
                Path(name).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
