import time
from pathlib import Path

from rambleon.archive import Archive
from rambleon.paths import Paths
from rambleon.watch import ingest_once, process_file, watch

FIXTURES = Path(__file__).parent / "fixtures"


def fake_wow(tmp_path: Path) -> tuple[Paths, Path]:
    wow = tmp_path / "wow"
    sv_dir = wow / "WTF" / "Account" / "123#1" / "70" / "Rambleon-Birdsong" / "SavedVariables"
    sv_dir.mkdir(parents=True)
    (wow / "Interface" / "AddOns").mkdir(parents=True)
    paths = Paths(repo_root=tmp_path, wow_dir=wow, archive_dir=tmp_path / "archive", exports_dir=tmp_path / "exports")
    return paths, sv_dir / "Rambleon.lua"


def test_ingest_archives_sessions(tmp_path):
    paths, sv = fake_wow(tmp_path)
    sv.write_bytes((FIXTURES / "Rambleon_simulated.lua").read_bytes())
    archive = Archive(paths.archive_dir)
    logs = []
    outcomes = ingest_once(paths, archive, logs.append)
    assert len(outcomes) == 2 and all(o.startswith("new") for o in outcomes)
    assert len(list(archive.raw_dir.glob("*_Rambleon.lua"))) == 1
    assert len(archive.session_files()) == 2
    # same bytes again → nothing happens
    assert ingest_once(paths, archive, logs.append) == []
    # a blank DB (the beta bug) never touches the archive
    sv.write_bytes(b"\r\nRambleonDB = {\r\n[\"schemaVersion\"] = 1,\r\n[\"sessions\"] = {\r\n},\r\n}\r\n")
    assert ingest_once(paths, archive, logs.append) == ["empty"]
    assert len(archive.session_files()) == 2


def test_torn_file_falls_back_to_bak(tmp_path):
    paths, sv = fake_wow(tmp_path)
    good = (FIXTURES / "Rambleon_simulated.lua").read_bytes()
    sv.with_name("Rambleon.lua.bak").write_bytes(good)
    sv.write_bytes(good[:1500])
    archive = Archive(paths.archive_dir)
    logs = []
    outcomes = process_file(sv, paths, archive, logs.append)
    assert any(o.startswith("new") for o in outcomes)
    assert list(archive.failed_dir.glob("*_Rambleon.lua"))
    assert any("could not parse" in m for m in logs)


def test_watch_loop_picks_up_a_write(tmp_path):
    paths, sv = fake_wow(tmp_path)
    archive = Archive(paths.archive_dir)
    logs = []
    import threading
    def writer():
        time.sleep(0.5)
        sv.write_bytes((FIXTURES / "Rambleon_simulated.lua").read_bytes())
    threading.Thread(target=writer).start()
    watch(paths, archive, logs.append, interval=0.2, stop_after=3.0, rescan=0.5)
    assert len(archive.session_files()) == 2
    assert not archive.pid_path.exists()


def test_install_without_checkout_seeds_from_bundle(tmp_path, monkeypatch):
    from rambleon import install as inst
    bundle = tmp_path / "pkg" / "addon" / "Rambleon"
    bundle.mkdir(parents=True)
    (bundle / "Rambleon.toc").write_text("## Version: 9.9.9\n")
    (bundle / "Core.lua").write_text("-- core\n")
    monkeypatch.setattr(inst, "bundled_addon", lambda: bundle)
    wow = tmp_path / "wow"; (wow / "Interface" / "AddOns").mkdir(parents=True)
    home = tmp_path / "home"
    paths = Paths(repo_root=home, wow_dir=wow, archive_dir=home / "archive", exports_dir=home / "exports")
    msg = inst.install_addon(paths)
    assert "unpacked" in msg and (home / "addon" / "Rambleon" / "Core.lua").exists()
    assert (wow / "Interface" / "AddOns" / "Rambleon").is_symlink()
    (home / "addon" / "Rambleon" / "Chapters.lua").write_text("RambleonChapters = {}\n")
    inst.install_addon(paths)  # same version: nothing re-copied, generated file untouched
    assert (home / "addon" / "Rambleon" / "Chapters.lua").exists()


def test_a_failing_chapter_never_stops_the_watcher(tmp_path):
    from rambleon.watch import Finalizer
    paths, sv = fake_wow(tmp_path)
    logs, ran = [], []

    def run(session):
        ran.append(session["id"])
        raise RuntimeError("the page could not be written")
    finalizer = Finalizer(run, logs.append, timeout=0)
    finalizer.on_capture({"id": "a", "state": "ended", "character": {"slug": "x", "displayName": "X"}})
    finalizer.on_capture({"id": "b", "state": "suspended", "character": {"slug": "x", "displayName": "X"}})
    finalizer.tick()
    finalizer.tick()                                    # nothing is left pending, and nothing raised
    assert ran == ["a", "b"] and sum("could not write the chapter" in m for m in logs) == 2

    ticks = []

    def tick():
        ticks.append(1)
        raise ValueError("a bad file")
    watch(paths, Archive(paths.archive_dir), logs.append, interval=0.01, stop_after=0.1, tick=tick)
    assert len(ticks) > 1 and sum("background step failed" in m for m in logs) == 1   # said once, not every poll
