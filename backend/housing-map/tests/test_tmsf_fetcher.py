import subprocess
import sys
from pathlib import Path

from src.services.tmsf_fetcher import TmsfClient, fetch_community_snapshots


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content
        self.encoding = None

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return FakeResponse("<html>小区均价：12345元/㎡</html>".encode("utf-8"))


class FlakySession(FakeSession):
    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if len(self.calls) == 1:
            raise RuntimeError("temporary network error")
        return FakeResponse("<html>小区均价：12345元/㎡</html>".encode("utf-8"))


def test_tmsf_client_uses_chrome_impersonation_and_browser_headers():
    session = FakeSession()
    client = TmsfClient(session_factory=lambda **kwargs: session)

    html = client.fetch_text("https://www.tmsf.com/esf/xq_xqtendency_100.htm", timeout=12)

    assert "12345" in html
    assert client.session_options == {"impersonate": "chrome"}
    assert session.calls[0][1]["timeout"] == 12
    assert session.calls[0][1]["headers"]["Accept-Language"].startswith("zh-CN")


def test_tmsf_client_retries_a_transient_request_once():
    session = FlakySession()
    client = TmsfClient(session_factory=lambda **kwargs: session, retry_delay_seconds=0)

    html = client.fetch_text("https://www.tmsf.com/esf/xq_xqtendency_100.htm", timeout=12)

    assert "12345" in html
    assert len(session.calls) == 2


def test_fetch_keeps_tendency_snapshot_when_index_page_fails():
    def fetch_text(url: str, timeout: int) -> str:
        if "xq_indexnew" in url:
            raise RuntimeError("blocked")
        return "var tendency2 = '[{&quot;ticks&quot;:[&quot;2026-09&quot;],&quot;line&quot;:[32000]}]';"

    result = fetch_community_snapshots("100", fetch_text=fetch_text, timeout=12)

    assert [snapshot.price_type for snapshot in result.snapshots] == ["monthly_deal_avg_latest"]
    assert result.errors == ["index: RuntimeError: blocked"]


def test_fetch_never_builds_recommended_listing_card_average():
    def fetch_text(url: str, timeout: int) -> str:
        if "xq_xqtendency" in url:
            return ""
        return '<span class="big">测试花园</span><div class="house_guess"><text>52383元/㎡</text></div>'

    result = fetch_community_snapshots("100", fetch_text=fetch_text, timeout=12)

    assert result.snapshots == []


def test_price_cli_can_import_the_shared_service_when_run_as_a_script():
    project_root = Path(__file__).resolve().parents[1]
    completed = subprocess.run(
        [sys.executable, "scripts/fetch_tmsf_price_snapshot.py", "--help"],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "Fetch low-frequency TMSF community price snapshots" in completed.stdout
