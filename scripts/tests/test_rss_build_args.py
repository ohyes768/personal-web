"""Exercise the real deployment build function with a harmless Docker stub."""

import os
from pathlib import Path
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash") if os.name != "nt" else "C:/Program Files/Git/bin/bash.exe"


class RssBuildArgumentsTest(unittest.TestCase):
    def test_shared_token_reaches_frontend_build(self):
        script = (ROOT / "scripts/deploy-nas.sh").read_text(encoding="utf-8")
        config = script.split("get_buildx_config() {", 1)[1].split("\n}", 1)[0]
        build = script.split("buildx_build_frontend() {", 1)[1].split("\n}", 1)[0]
        harness = "\n".join([
            "set -euo pipefail",
            "RSS_RELAY_TOKEN=regression-test-token",
            "BUILDX_BUILDER=test-builder; COLD=false",
            "get_buildx_config() {" + config + "\n}",
            "buildx_build_frontend() {" + build + "\n}",
            'docker() { printf "%s\\n" "$@"; }',
            "buildx_build_frontend rss-relay-frontend",
        ])
        result = subprocess.run([BASH, "--noprofile", "--norc", "-c", harness],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        args = result.stdout.splitlines()
        self.assertIn("--build-arg", args)
        self.assertIn("NEXT_PUBLIC_RSS_TOKEN=regression-test-token", args)


if __name__ == "__main__":
    unittest.main()
