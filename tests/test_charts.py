import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_chart_planning_module():
    """Chart-type selection and config live in web/assets/charts.js; its checks run under Node."""
    r = subprocess.run(["node", "tests/charts.test.js"], cwd=ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert "charts ok" in r.stdout
