import json
import os
import time
from pathlib import Path

from rambleon import pipeline
from rambleon.archive import Archive, atomic_write_json
from rambleon.luaparse import parse, to_python
from rambleon.nights import resolve_night
from rambleon.normalize import sessions_from_db
from rambleon.paths import Paths
from rambleon.pipeline import NightContext, Step, finish_night, is_finished, marker_path, run_steps, unfinished
from rambleon.watch import Finalizer

FIXTURES = Path(__file__).parent / "fixtures"


def archived(tmp_path: Path):
    paths = Paths(repo_root=tmp_path, wow_dir=tmp_path / "wow", archive_dir=tmp_path / "archive", exports_dir=tmp_path / "exports")
    (tmp_path / "addon" / "Rambleon").mkdir(parents=True)
    archive = Archive(paths.archive_dir)
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    archive.upsert_session(sessions_from_db(db)[0], {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"})
    archive.rebuild_index()
    return archive, paths, resolve_night(archive, "latest")


def test_a_night_is_finished_step_by_step_and_marked(tmp_path):
    archive, paths, night = archived(tmp_path)
    logs: list[str] = []
    ctx = finish_night(archive, paths, "latest", log=logs.append, use_ai=False)
    assert list(ctx.results) == [s.name for s in pipeline.STEPS] and not ctx.failed
    assert ctx.results["share"].startswith("skipped") and ctx.results["notify"].startswith("skipped")   # by hand: nothing leaves the Mac
    assert (paths.exports_dir / "prompts").glob("*-prompt.md") and list((paths.exports_dir / "prompts").glob("2026-*-prompt.md"))  # --no-ai still writes the prompt
    assert ctx.outputs["page"].exists() and (paths.repo_root / "addon" / "Rambleon" / "Chapters.lua").exists()
    marker = json.loads(marker_path(paths.exports_dir, night["id"]).read_text())
    assert marker["formatVersion"] == 1 and marker["events"] == len(night["events"]) and marker["steps"]["page"] == "ok"
    assert is_finished(paths.exports_dir, night)


def test_one_failing_step_does_not_stop_the_rest(tmp_path):
    archive, paths, night = archived(tmp_path)
    ran, logs = [], []

    def boom(ctx):
        raise OSError("disk full")
    steps = [Step("a", lambda ctx: ran.append("a") or "did a"), Step("page", boom), Step("game", lambda ctx: ran.append("game")),
             Step("stop", boom, fatal=True), Step("never", lambda ctx: ran.append("never"))]
    ctx = run_steps(NightContext(archive=archive, paths=paths, night=night, log=logs.append), steps)
    assert ran == ["a", "game"] and "never" not in ctx.results
    assert ctx.results["page"] == "failed: OSError: disk full" and set(ctx.failed) == {"page", "stop"}
    assert "did a" in logs and any("page failed" in m for m in logs)
    only = run_steps(NightContext(archive=archive, paths=paths, night=night, log=logs.append), steps, only={"game"})
    assert list(only.results) == ["game"]


def test_what_counts_as_finished(tmp_path):
    archive, paths, night = archived(tmp_path)
    ended = night["endedAt"]
    assert not is_finished(paths.exports_dir, night)                          # nothing written yet
    # before markers existed: a chapter written after the night's last minute, or else its story page
    journal = paths.exports_dir / "journal" / f"{night['id']}.json"
    atomic_write_json(journal, {"journal": "x", "createdAt": ended - 60})
    assert not is_finished(paths.exports_dir, night)                          # the chapter misses the end of the night
    atomic_write_json(journal, {"journal": "x", "createdAt": ended + 60})
    assert is_finished(paths.exports_dir, night)
    journal.unlink()
    page = paths.exports_dir / "html" / f"{night['nightDate']}-rambleon-birdsong.html"
    page.parent.mkdir(parents=True)
    page.write_text("<p>page</p>")
    os.utime(page, (ended - 60, ended - 60))
    assert not is_finished(paths.exports_dir, night)
    os.utime(page, (ended + 60, ended + 60))
    assert is_finished(paths.exports_dir, night)
    # a marker decides once there is one: the night grew after it was written
    atomic_write_json(marker_path(paths.exports_dir, night["id"]), {"endedAt": ended, "events": len(night["events"]) - 1})
    assert not is_finished(paths.exports_dir, night)
    assert [n["id"] for n in unfinished(archive, paths.exports_dir, now=ended + 3600)] == [night["id"]]
    assert unfinished(archive, paths.exports_dir, now=ended + 3 * 86400) == []     # old nights are left to `ramble finish`


def test_a_restarted_watcher_finishes_what_it_owes(tmp_path):
    archive, paths, night = archived(tmp_path)
    now = night["endedAt"] + 3600
    logs, ran = [], []

    def run(session):
        ran.append(session["id"])
        finish_night(archive, paths, session["id"], log=logs.append, use_ai=False, unattended=True)
    finalizer = Finalizer(run, logs.append)
    finalizer.recover(unfinished(archive, paths.exports_dir, now=now))
    assert ran == [night["id"]] and is_finished(paths.exports_dir, night)
    finalizer.recover(unfinished(archive, paths.exports_dir, now=now))       # the next start owes nothing
    assert ran == [night["id"]]
    still_open = dict(night, state="open")
    finalizer.recover([still_open])
    assert ran == [night["id"]] and "rambleon-birdsong" in finalizer.pending  # waits like any save
