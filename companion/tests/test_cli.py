"""Every command a player types, run once against a small archive: it works, or it says why in one line."""
import time
from pathlib import Path

import pytest
from typer.testing import CliRunner

from rambleon.archive import Archive
from rambleon.cli import app
from rambleon.luaparse import parse, to_python
from rambleon.normalize import sessions_from_db

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


@pytest.fixture
def home(tmp_path, monkeypatch):
    """RAMBLEON_HOME (set by conftest) with the simulated evening archived and a place for Chapters.lua."""
    monkeypatch.setenv("COLUMNS", "200")          # tables are not squeezed into a narrow test terminal
    home = tmp_path / "home"
    (home / "addon" / "Rambleon").mkdir(parents=True)
    archive = Archive(home / "archive")
    archive.ensure()
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    for s in sessions_from_db(db):
        archive.upsert_session(s, {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"})
    archive.rebuild_index()
    return home


def run(*args: str, code: int = 0) -> str:
    result = runner.invoke(app, list(args))
    assert result.exit_code == code, f"ramble {' '.join(args)} exited {result.exit_code}:\n{result.output}\n{result.exception!r}"
    assert "Traceback" not in result.output
    return result.output


def test_the_everyday_commands(home):
    assert "ramble 0." in run("version")
    assert "Rambleon Birdsong" in run("nights")
    assert "rambleon-birdsong" in run("sessions")
    assert "session(s)" in run("status")
    assert "Journey" in run("show", "latest")
    assert "exported" in run("export", "latest")
    assert "golden (default)" in run("voices") and "bundled" in run("voices")
    assert "[journal]" in run("config") and "not there" in run("config")
    assert "The Emerald Dreamcatcher" in run("catchup", "latest")
    out = run("summarize", "latest", "--no-ai")
    assert "prompt:" in out and list((home / "exports" / "prompts").glob("*-prompt.md"))
    run("page", "latest", "--no-open")
    assert list((home / "exports" / "html").glob("2026-*.html"))
    assert "Chapters.lua" in run("publish").replace("\n", "") and (home / "addon" / "Rambleon" / "Chapters.lua").exists()
    assert "format = 1," in (home / "addon" / "Rambleon" / "Chapters.lua").read_text()
    assert "html:" in run("guide", "latest", "--no-ai")
    assert "route" in run("guide", "--list")


def test_finish_runs_every_step_and_shares_nothing(home):
    out = run("finish", "latest", "--no-ai")
    for step in ("screenshots", "markdown", "journal", "guide", "page", "index", "game"):
        assert f"{step}: ok" in out
    assert "share: skipped" in out and "notify: skipped" in out
    assert list((home / "exports" / "finished").glob("night-*.json"))


def test_post_dry_run_shows_the_text_and_posts_nothing(home):
    out = run("post", "latest", "--dry-run")
    assert "dry run: nothing posted" in out and not (home / "archive" / "posts" / "x.json").exists()


def test_what_goes_wrong_is_one_line_and_exit_code_1(home):
    assert "no night matches" in run("page", "1999-01-01", code=1)
    assert "no night matches" in run("finish", "1999-01-01", code=1)
    assert "no archived session matches" in run("show", "nope", code=1)
    assert "needs the Rambleon git checkout" in run("share", "--dry-run", code=1).replace("\n", " ")
    assert "unknown voice" in run("summarize", "latest", "--voice", "nope", code=1)
    (home / "rambleon.local.toml").write_text("[x\nauto = true\n")
    assert "not valid TOML" in run("post", "latest", "--dry-run", code=1)
    assert "not valid TOML" in run("config", code=1)
    (home / "rambleon.local.toml").unlink()
    session_file = Archive(home / "archive").session_files()[0]
    session_file.write_text("{ this is not json")
    out = run("nights", code=1)
    assert len(out.strip().splitlines()) <= 3            # one message, not a traceback
