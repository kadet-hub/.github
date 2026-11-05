"""mint-token against a throwaway key, a fake op and a local fake GitHub API (registry AGT-4)."""
import base64
import http.server
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(HERE, "mint-token")
REF = "op://Agents/kadet-hub-agent/private key"
TOKEN = "ghs_fake0123456789"


def b64url_decode(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class FakeAPI(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def record(self):
        n = int(self.headers.get("Content-Length") or 0)
        self.server.requests.append((self.command, self.path, self.headers.get("Authorization"), self.rfile.read(n).decode()))

    def do_GET(self):
        self.record()
        if self.path == "/orgs/kadet-hub/installation":
            self.reply(200, {"id": 42, "account": {"login": "kadet-hub"}})
        else:
            self.reply(404, {"message": "Not Found"})

    def do_POST(self):
        self.record()
        if self.path != "/app/installations/42/access_tokens":
            self.reply(404, {"message": "Not Found"})
        elif self.server.refuse:
            self.reply(422, {"message": "There is at least one repository that does not exist or is not accessible to the parent installation."})
        else:
            self.reply(201, {"token": TOKEN, "expires_at": "2026-11-05T12:00:00Z"})


class MintToken(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.key = os.path.join(cls.tmp.name, "throwaway.pem")
        cls.pub = os.path.join(cls.tmp.name, "throwaway.pub")
        subprocess.run(["openssl", "genpkey", "-algorithm", "RSA", "-pkeyopt", "rsa_keygen_bits:2048", "-out", cls.key], check=True, capture_output=True)
        subprocess.run(["openssl", "pkey", "-in", cls.key, "-pubout", "-out", cls.pub], check=True, capture_output=True)
        with open(cls.key) as f:
            cls.key_body = [line for line in f.read().splitlines() if line and not line.startswith("-----")]
        bin_dir = os.path.join(cls.tmp.name, "bin")
        os.mkdir(bin_dir)
        cls.argv_log = os.path.join(cls.tmp.name, "curl-argv")
        with open(os.path.join(bin_dir, "op"), "w") as f:
            f.write(f'#!/bin/sh\n[ "$1" = read ] && [ "$2" = "{REF}" ] && [ $# -eq 2 ] || exit 3\nexec cat "{cls.key}"\n')
        with open(os.path.join(bin_dir, "curl"), "w") as f:  # records the command line, then runs the real curl
            f.write(f'#!/bin/sh\nprintf "%s\\n" "$@" >> "{cls.argv_log}"\nexec "{shutil.which("curl")}" "$@"\n')
        for name in ("op", "curl"):
            os.chmod(os.path.join(bin_dir, name), 0o755)
        cls.path = bin_dir + os.pathsep + os.environ["PATH"]
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.tmp.cleanup()

    def setUp(self):
        self.server.requests = []
        self.server.refuse = False
        if os.path.exists(self.argv_log):
            os.remove(self.argv_log)
        self.work = tempfile.mkdtemp(dir=self.tmp.name)
        self.scratch = tempfile.mkdtemp(dir=self.tmp.name)

    def mint(self, *repos):
        env = {
            "PATH": self.path,
            "HOME": self.work,
            "TMPDIR": self.scratch,
            "AGENT_APP_ID": "123456",
            "AGENT_KEY_REF": REF,
            "GITHUB_API_URL": f"http://127.0.0.1:{self.server.server_address[1]}",
        }
        return subprocess.run([SCRIPT, *repos], env=env, cwd=self.work, capture_output=True, text=True, timeout=60, check=False)

    def jwt(self):
        auth = {a for _, _, a, _ in self.server.requests}
        self.assertEqual(len(auth), 1)
        scheme, jwt = auth.pop().split(" ")
        self.assertEqual(scheme, "Bearer")
        return jwt

    def assert_no_secret(self, *outputs):
        jwt = self.jwt() if self.server.requests else None
        for out in outputs:
            for line in self.key_body:
                self.assertNotIn(line, out)
            if jwt:
                self.assertNotIn(jwt, out)
        self.assertEqual(os.listdir(self.work), [])
        self.assertEqual(os.listdir(self.scratch), [])

    def test_prints_only_the_token(self):
        r = self.mint("registry", "recipes")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, TOKEN + "\n")
        self.assertEqual([(m, p) for m, p, _, _ in self.server.requests],
                         [("GET", "/orgs/kadet-hub/installation"), ("POST", "/app/installations/42/access_tokens")])
        self.assertEqual(json.loads(self.server.requests[1][3]), {"repositories": ["registry", "recipes"]})
        with open(self.argv_log) as f:
            argv = f.read()
        self.assert_no_secret(r.stdout, r.stderr, argv)

    def test_jwt(self):
        self.assertEqual(self.mint("registry").returncode, 0)
        jwt = self.jwt()
        header, payload, signature = jwt.split(".")
        self.assertEqual(json.loads(b64url_decode(header)), {"alg": "RS256", "typ": "JWT"})
        claims = json.loads(b64url_decode(payload))
        self.assertEqual(claims["iss"], 123456)
        now = time.time()
        self.assertTrue(claims["iat"] <= now - 30 and claims["exp"] - claims["iat"] <= 600 and claims["exp"] > now, claims)
        signed, sig = os.path.join(self.tmp.name, "signed"), os.path.join(self.tmp.name, "sig")
        with open(signed, "w") as f:
            f.write(f"{header}.{payload}")
        with open(sig, "wb") as f:
            f.write(b64url_decode(signature))
        subprocess.run(["openssl", "dgst", "-sha256", "-verify", self.pub, "-signature", sig, signed], check=True, capture_output=True)

    def test_refused_by_github(self):
        self.server.refuse = True
        r = self.mint("not-installed")
        self.assertNotEqual(r.returncode, 0)
        self.assertEqual(r.stdout, "")
        self.assertIn("HTTP 422", r.stderr)
        self.assertIn("not accessible to the parent installation", r.stderr)
        self.assert_no_secret(r.stdout, r.stderr)

    def test_needs_repositories(self):
        r = self.mint()
        self.assertEqual(r.returncode, 2)
        self.assertEqual(r.stdout, "")
        self.assertEqual(self.server.requests, [])


if __name__ == "__main__":
    unittest.main()
