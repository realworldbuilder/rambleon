import os
import sys
import time
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """No test reads this Mac's rambleon.local.toml, depends on its timezone, or reaches a real service."""
    monkeypatch.setenv("TZ", "UTC")
    time.tzset()
    for name in list(os.environ):
        if name.startswith("RAMBLEON_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("RAMBLEON_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("RAMBLEON_WOW_DIR", str(tmp_path / "no-wow"))      # never this Mac's World of Warcraft
    for target in ("rambleon.notify.notify", "rambleon.cli.notify", "rambleon.pipeline.notify"):
        monkeypatch.setattr(target, lambda *a, **k: None)
    for target in ("rambleon.summarize.claude_available", "rambleon.guide.claude_available"):
        monkeypatch.setattr(target, lambda: None)
    monkeypatch.setattr("rambleon.xpost.load_credentials", lambda *a, **k: None)
    yield
    monkeypatch.undo()
    time.tzset()
