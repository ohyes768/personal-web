"""Regression tests for the nginx auth gate on macro upload endpoints.

Context: 2026-11-17 (7508d09f) added basic auth to the whole :9443 server block
and only exempted ``/rss``. ``/api/macro/`` was left gated, so every macro
upload returned 401 (nginx HTML) and the weekly collection silently stopped
delivering. The write endpoints carry their own ``X-Upload-Token`` auth, so
they must stay exempt while the read endpoints stay gated.

These tests parse the effective config (``nginx -T``), not the repo file, and
assert the routing outcome rather than the literal text.
"""

import hashlib
import json
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

NGINX = "nginx"
REPO_CONF = ROOT / "nginx/web.conf"
BASE = "https://127.0.0.1:9443"
UP_SIGNAL = "/api/macro/signal/upload"
UP_REPORTS = "/api/macro/reports/upload"
ENV_FILE = Path("/home/ohyes768/skills/finance-macro/.env")
OUTPUT_DIR = Path("/home/ohyes768/skills/finance-macro/output")


def sh(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)


def curl(method, path, headers=None, body=None, timeout=20):
    cmd = ["curl", "-sk", "-o", "-", "-w", "\n__CODE__%{http_code}",
           "--max-time", str(timeout), "-X", method, BASE + path]
    for h in headers or []:
        cmd += ["-H", h]
    if body is not None:
        cmd += ["--data-binary", body]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 15)
    m = re.search(r"__CODE__(\d{3})\s*$", p.stdout)
    return (int(m.group(1)) if m else 0), (p.stdout[:m.start()] if m else p.stdout)


def norm(sel):
    """Normalise an nginx location selector: drop the '=' prefix and trailing '/'."""
    s = sel.strip()
    if s.startswith("="):
        s = s[1:].strip()
    return s.rstrip("/") or "/"


def blocks(text):
    """Extract location blocks by brace matching -> [(selector, body)]."""
    out = []
    for m in re.finditer(r"\blocation\s+([^\n{]+?)\s*\{", text):
        i = m.end() - 1
        depth, j = 0, i
        while j < len(text):
            if text[j] == "{":
                depth += 1
            elif text[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        out.append((norm(m.group(1)), text[i:j + 1]))
    return out


def load_token():
    if not ENV_FILE.exists():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("MACRO_SIGNAL_UPLOAD_TOKEN="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def load_payload():
    for cand in (OUTPUT_DIR / "monetary-policy-skill/macro_signal.json",
                 Path("/home/ohyes768/skills/finance-macro/monetary-policy-skill/macro_signal.json")):
        try:
            with open(cand, encoding="utf-8") as f:
                return json.load(f)
        except OSError:
            continue
    return {"conclusion": "probe", "data_date": "2026-01-01", "total_score": 0.0,
            "details": {"probe": 0.0}}


class MacroUploadAuthGateTest(unittest.TestCase):
    """The upload endpoints must bypass nginx basic auth; everything else must not."""

    @classmethod
    def setUpClass(cls):
        cls.effective = sh(f"docker exec {NGINX} nginx -T").stdout
        cls.blocks = blocks(cls.effective)
        cls.by = {}
        for sel, body in cls.blocks:
            cls.by.setdefault(sel, []).append(body)
        cls.token = load_token()
        cls.payload = load_payload()

    def test_nginx_config_is_valid(self):
        p = sh(f"docker exec {NGINX} nginx -t")
        out = p.stdout + p.stderr
        self.assertEqual(p.returncode, 0, out)
        self.assertIn("syntax is ok", out)

    def test_upload_endpoints_have_exact_match_locations(self):
        self.assertIn(UP_SIGNAL, self.by)
        self.assertIn(UP_REPORTS, self.by)

    def test_upload_endpoints_are_exempt_from_basic_auth(self):
        for sel in (UP_SIGNAL, UP_REPORTS):
            with self.subTest(endpoint=sel):
                self.assertIn("auth_basic off", self.by[sel][0])

    def test_read_endpoints_remain_gated(self):
        read = [s for s in self.by
                if s.startswith("/api/macro") and s not in (UP_SIGNAL, UP_REPORTS)]
        self.assertTrue(read, "expected macro read locations")
        for sel in read:
            with self.subTest(endpoint=sel):
                self.assertNotIn("auth_basic off", self.by[sel][0])

    def test_exemption_is_confined_to_rss_and_upload_endpoints(self):
        allow = {UP_SIGNAL, UP_REPORTS}
        off = [s for s, body in self.blocks if "auth_basic off" in body]
        for sel in off:
            with self.subTest(endpoint=sel):
                self.assertTrue(sel.startswith("/rss") or sel in allow)

    def test_container_serves_current_repo_config(self):
        """bind mount keeps the old inode after an in-place rewrite: reload is not enough."""
        p = sh(f"docker exec {NGINX} sha256sum /etc/nginx/conf.d/web.conf")
        self.assertEqual(p.returncode, 0, p.stderr)
        repo = hashlib.sha256(REPO_CONF.read_bytes()).hexdigest()
        self.assertEqual(repo, p.stdout.split()[0], "container has a stale nginx config")

    def test_upload_with_valid_token_succeeds(self):
        body = json.dumps({"skill": "monetary-policy-skill", "file": "macro_signal.json",
                           "data": self.payload}, ensure_ascii=False)
        code, out = curl("POST", UP_SIGNAL,
                         ["Content-Type: application/json",
                          "X-Upload-Token: " + self.token], body)
        self.assertEqual(code, 200, out[:200])

    def test_upload_without_token_is_rejected_by_backend(self):
        """422/401 JSON (not nginx HTML) proves the request reached the backend."""
        body = json.dumps({"skill": "monetary-policy-skill", "file": "macro_signal.json",
                           "data": self.payload}, ensure_ascii=False)
        for headers, label in (([], "no token"), (["X-Upload-Token: wrong-token"], "bad token")):
            with self.subTest(case=label):
                code, out = curl("POST", UP_SIGNAL,
                                 ["Content-Type: application/json"] + headers, body)
                self.assertIn(code, (401, 422), out[:200])
                self.assertNotIn("nginx", out, "request never reached the backend")

    def test_read_endpoint_is_still_gated_by_nginx(self):
        code, out = curl("GET", "/api/macro/months")
        self.assertEqual(code, 401)
        self.assertIn("nginx", out)

    def test_rss_exemption_still_works(self):
        code, _ = curl("GET", "/rss/api/rss-relay/rss.xml"
                             "?token=9baa5f18fbec85a724c0d2e70ccdb5e61c042ffd7bc5d01f455e59c89ac13228"
                             "&channel=macro")
        self.assertEqual(code, 200)


if __name__ == "__main__":
    unittest.main()
