import subprocess
import time
from pathlib import Path

import pytest

from rambleon.archive import Archive
from rambleon.luaparse import parse, to_python
from rambleon.normalize import sessions_from_db
from rambleon.paths import Paths
from rambleon.share import ShareError, pages_url, share

FIXTURES = Path(__file__).parent / "fixtures"


def checkout(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "site").mkdir(parents=True)
    (repo / "site" / "index.html").write_text("<p>landing</p>")
    (repo / ".github" / "workflows").mkdir(parents=True)
    (repo / ".github" / "workflows" / "pages.yml").write_text("name: Pages\n")
    for cmd in (["git", "init", "-q", "-b", "main"], ["git", "config", "user.email", "t@example.com"], ["git", "config", "user.name", "t"],
                ["git", "remote", "add", "origin", "https://github.com/someone/rambleon.git"], ["git", "add", "."], ["git", "commit", "-q", "-m", "init"]):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True)
    return repo


def archived(tmp_path: Path, repo: Path):
    paths = Paths(repo_root=repo, wow_dir=tmp_path / "wow", archive_dir=tmp_path / "archive", exports_dir=tmp_path / "exports")
    archive = Archive(paths.archive_dir)
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    archive.upsert_session(s, {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"})
    archive.rebuild_index()
    return archive, paths


def recording_runner(pushes: list):
    def run(cmd, **kw):
        if cmd[:1] == ["git"] and "push" in cmd:
            pushes.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, "", "")
        return subprocess.run(cmd, **kw)
    return run


def test_share_copies_commits_and_pushes(tmp_path):
    repo = checkout(tmp_path)
    archive, paths = archived(tmp_path, repo)
    pushes, logs = [], []
    result = share(archive, paths, ["tonight"], yes=True, log=logs.append, runner=recording_runner(pushes))
    page = result.pages[0]
    assert (repo / "site" / "example" / page).exists() and (repo / "site" / "example" / "index.html").exists()
    assert page in (repo / "site" / "example" / "index.html").read_text()
    assert result.committed and result.pushed and pushes == [["git", "-C", str(repo), "push", "origin", "HEAD"]]
    last = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=repo, capture_output=True, text=True).stdout.strip()
    assert last.startswith("Journal: 20")
    assert result.urls == [f"https://someone.github.io/rambleon/example/{page}"]
    # nothing new the second time
    again = share(archive, paths, ["tonight"], yes=True, runner=recording_runner(pushes))
    assert not again.committed and "nothing new" in again.message and len(pushes) == 1


def test_share_dry_run_and_declined_confirm_change_nothing(tmp_path):
    repo = checkout(tmp_path)
    archive, paths = archived(tmp_path, repo)
    pushes = []
    dry = share(archive, paths, [], dry_run=True, runner=recording_runner(pushes))
    assert dry.files and not (repo / "site" / "example").exists() and dry.commands[-1][1] == "push"
    declined = share(archive, paths, [], confirm=lambda q: False, runner=recording_runner(pushes))
    assert not declined.committed and pushes == []
    status = subprocess.run(["git", "status", "--porcelain"], cwd=repo, capture_output=True, text=True).stdout
    assert "site/example/" in status                      # copied and left for the player, not committed


def test_share_needs_the_checkout(tmp_path):
    archive, paths = archived(tmp_path, tmp_path / "not-a-repo")
    with pytest.raises(ShareError):
        share(archive, paths, [], yes=True)


def test_pages_url():
    assert pages_url("git@github.com:me/rambleon.git", "x.html") == "https://me.github.io/rambleon/example/x.html"
    assert pages_url("https://github.com/me/rambleon", "") == "https://me.github.io/rambleon/example/"
    assert pages_url("https://example.org/foo.git", "x") is None


def test_share_auto_is_off_unless_this_machine_says_so(tmp_path):
    from rambleon.config import share_auto
    assert share_auto(tmp_path) is False
    (tmp_path / "rambleon.local.toml").write_text("[share]\nauto = true\n")
    assert share_auto(tmp_path) is True
    (tmp_path / "rambleon.local.toml").write_text("[share]\nauto = false\n")
    assert share_auto(tmp_path) is False


def test_finished_night_is_shared_when_auto_is_on(tmp_path, monkeypatch):
    from rambleon import cli, pipeline
    repo = checkout(tmp_path)
    archive, paths = archived(tmp_path, repo)
    (repo / "addon" / "Rambleon").mkdir(parents=True)
    calls: list = []
    monkeypatch.setattr(pipeline, "run_share", lambda archive_, paths_, refs, **kw: calls.append((refs, kw)) or type(
        "R", (), {"message": "pushed", "urls": ["https://x/y.html"], "pushed": True})())
    session = archive.load_session("latest")
    cli._finish_night(archive, paths, use_ai=False, model="sonnet")(session)
    assert calls == []                                       # no toml: nothing leaves the Mac
    assert (paths.exports_dir / "html" / "guide-rambleon-birdsong.html").exists()   # the route guide is part of a finished night
    assert "Route guide" in next(paths.exports_dir.glob("html/2026-*.html")).read_text()
    (repo / "rambleon.local.toml").write_text("[share]\nauto = true\n")
    cli._finish_night(archive, paths, use_ai=False, model="sonnet")(session)
    assert len(calls) == 1 and calls[0][0][0].startswith("night-") and calls[0][1]["yes"] is True


def test_share_takes_the_route_guide_along(tmp_path, monkeypatch):
    from rambleon.guide import write_guide
    from rambleon.nights import nights
    monkeypatch.setattr("rambleon.config.find_repo_root", lambda: tmp_path)
    repo = checkout(tmp_path)
    archive, paths = archived(tmp_path, repo)
    pushes: list = []
    plain = share(archive, paths, ["tonight"], dry_run=True, runner=recording_runner(pushes))
    assert not any("guide-" in f for f in plain.files)                   # no guide written yet: nothing to take
    write_guide(archive, paths.exports_dir, "rambleon-birdsong", use_ai=False, log=lambda m: None)
    dry = share(archive, paths, ["tonight"], dry_run=True, runner=recording_runner(pushes))
    assert "site/example/guide-rambleon-birdsong.html" in dry.files
    result = share(archive, paths, ["tonight"], yes=True, runner=recording_runner(pushes))
    example = repo / "site" / "example"
    page = (example / "guide-rambleon-birdsong.html").read_text()
    night_page = nights(archive)[0]["id"]  # sanity: one night
    assert result.pushed and "guide-rambleon-birdsong.html" in result.pages
    assert "href='2026-" in page and night_page.startswith("night-")
    assert "<a href='guide-rambleon-birdsong.html'>Route guide</a>" in (example / "index.html").read_text()
    assert "Route guide" in [p for p in example.glob("2026-*.html")][0].read_text()


def test_share_commits_only_the_site_pages(tmp_path):
    repo = checkout(tmp_path)
    archive, paths = archived(tmp_path, repo)
    (repo / "notes.txt").write_text("half-finished work")
    subprocess.run(["git", "add", "notes.txt"], cwd=repo, check=True)
    result = share(archive, paths, ["tonight"], yes=True, runner=recording_runner([]))
    assert result.committed
    committed = subprocess.run(["git", "show", "--stat", "--format=", "HEAD"], cwd=repo, capture_output=True, text=True).stdout
    assert "site/example/" in committed and "notes.txt" not in committed
    staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=repo, capture_output=True, text=True).stdout.split()
    assert staged == ["notes.txt"]                      # still staged, still the player's to commit
