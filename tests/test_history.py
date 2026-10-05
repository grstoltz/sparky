import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_chat_history_module():
    """Chat records, what gets stored and quota-aware saving live in web/assets/history.js."""
    r = subprocess.run(["node", "tests/history.test.js"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "history ok" in r.stdout
