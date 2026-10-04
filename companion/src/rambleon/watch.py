"""Watch Rambleon's SavedVariables and archive every write. This is the defence against the
Forever beta bug: WoW may forget, the archive does not."""
from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Callable

from .archive import Archive, blake, is_trivial
from .luaparse import LuaParseError, TornFile, parse, to_python
from .normalize import sessions_from_db
from .paths import Paths
from .screenshots import attach_screenshots

Log = Callable[[str], None]
STABLE_POLLS = 2
RETRY_DELAYS = (0.5, 1.0, 2.0, 5.0)


def _signature(path: Path) -> tuple[int, int, int] | None:
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_mtime_ns, st.st_size, st.st_ino)


def _read(path: Path) -> bytes | None:
    try:
        with open(path, "rb") as fh:
            return fh.read()
    except OSError:
        return None


AfterCapture = Callable[[dict[str, Any]], None] | None
FINALIZE_GRACE = 15  # seconds after the resume window


class Finalizer:
    """Decides when a night is over. An explicitly ended session finalizes at once; a suspended one waits
    until nobody has resumed it (the AddOn's 10-minute window) — that is what a logout looks like from here."""

    def __init__(self, run: Callable[[dict[str, Any]], None], log: Log, timeout: float | None = None,
                 logged_out: Callable[[float], bool] | None = None):
        from .model import SUSPEND_TIMEOUT
        self.run = run
        self.log = log
        self.timeout = (SUSPEND_TIMEOUT + FINALIZE_GRACE) if timeout is None else timeout
        self.logged_out = logged_out          # (capture time) -> True when the player has clearly left
        self.pending: dict[str, tuple[float, dict[str, Any]]] = {}
        self._last_check = 0.0

    def on_capture(self, session: dict[str, Any]) -> None:
        slug = session.get("character", {}).get("slug", "unknown")
        if session.get("state") == "ended":
            self.pending.pop(slug, None)
            self._run(session)
        else:
            self.pending[slug] = (time.time() + self.timeout, session)
            self.log(f"{session['character'].get('displayName')} saved; the chapter is written as soon as they log out "
                     f"(or {int(self.timeout // 60)} min after the last save if that cannot be told)")

    def _run(self, session: dict[str, Any]) -> None:
        try:
            self.run(session)
        except Exception as e:  # noqa: BLE001 — the archive is safe; `ramble finish` writes the chapter by hand
            self.log(f"could not write the chapter for {session.get('id')}: {type(e).__name__}: {e}")

    def recover(self, nights: list[dict[str, Any]]) -> None:
        """At start: nights the pipeline still owes (pipeline.unfinished). The pending list lives in memory, so a
        watcher that was restarted or crashed would otherwise never write them. A night that is over is written
        now; one that may still be going waits like any save."""
        for night in nights:
            name = night.get("character", {}).get("displayName")
            if night.get("state") == "ended":
                self.log(f"{name}'s night of {night.get('nightDate')} was never finished — writing the chapter")
                self._run(night)
            else:
                slug = night.get("character", {}).get("slug", "unknown")
                self.pending[slug] = ((night.get("endedAt") or time.time()) + self.timeout, night)
                self.log(f"{name}'s night of {night.get('nightDate')} is still open; the chapter is written once they have left")

    def tick(self) -> None:
        now = time.time()
        check_logout = self.logged_out is not None and now - self._last_check >= 5
        if check_logout:
            self._last_check = now
        for slug, (due, session) in list(self.pending.items()):
            left = False
            if check_logout:
                try:
                    left = self.logged_out(due - self.timeout)
                except Exception:
                    left = False
            if now >= due or left:
                del self.pending[slug]
                if left:
                    self.log(f"{session['character'].get('displayName')} logged out — writing the chapter")
                self._run(session)


def process_file(path: Path, paths: Paths, archive: Archive, log: Log, copy_screenshots: bool = True,
                 allow_bak: bool = True, after_capture: AfterCapture = None) -> list[str]:
    """Snapshot, parse and archive one SavedVariables file. Returns a list of outcome strings."""
    data = _read(path)
    if data is None:
        return []
    h = blake(data)
    if archive.has_hash(h):
        return []
    parsed = None
    error: Exception | None = None
    for attempt, delay in enumerate((0.0,) + RETRY_DELAYS):
        if delay:
            time.sleep(delay)
            fresh = _read(path)
            if fresh is None:
                return []
            if fresh != data:
                data = fresh
                h = blake(data)
                if archive.has_hash(h):
                    return []
        try:
            parsed = parse(data)
            error = None
            break
        except TornFile as e:
            error = e
            continue
        except LuaParseError as e:
            error = e
            break
    if parsed is None:
        failed = archive.store_failed(data, path, f"{type(error).__name__}: {error}")
        log(f"could not parse {paths.redact(path)}: {error} — preserved at {failed.name}")
        bak = path.with_name(path.name + ".bak")
        if allow_bak and bak.exists():
            log("trying the .bak copy WoW kept from the previous flush")
            return process_file(bak, paths, archive, log, copy_screenshots, allow_bak=False, after_capture=after_capture)
        return [f"failed {path.name}"]

    raw_path, h = archive.snapshot_raw(data, path)
    if raw_path is None:
        return []
    outcomes: list[str] = []
    db = parsed.get("RambleonDB")
    if db is None:
        log(f"{paths.redact(path)} has no RambleonDB table (nothing to archive)")
        return ["no-db"]
    sessions = sessions_from_db(to_python(db))
    if not sessions:
        log(f"{paths.redact(path)}: RambleonDB is empty — no sessions to archive (expected right after a fresh login)")
        return ["empty"]
    capture = {
        "capturedAt": int(time.time()),
        "rawSnapshot": str(raw_path.relative_to(archive.root)),
        "sourceHash": h,
        "sourceFile": paths.redact(path),
    }
    for s in sessions:
        attach_screenshots(s, paths.screenshots_dir, archive.screenshots_dir if copy_screenshots else None)
        outcome, out_path = archive.upsert_session(s, capture)
        c = s.get("counters", {})
        summary = f"{len(s.get('events', []))} events, {s.get('state')}"
        if outcome in ("new", "updated"):
            log(f"captured {s['id']} ({summary}) → {out_path.name if out_path else '?'} [{outcome}]")
            if after_capture and not is_trivial(s):
                try:
                    after_capture(s)
                except Exception as e:  # the archive is safe; post-processing must never kill the watcher
                    log(f"post-processing failed: {e}")
        elif outcome == "rejected":
            log(f"kept existing archive for {s['id']} (incoming copy had fewer events)")
        outcomes.append(f"{outcome} {s['id']}")
    archive.rebuild_index()
    return outcomes


def reprocess(paths: Paths, archive: Archive, log: Log, copy_screenshots: bool = True) -> list[str]:
    """Rebuild normalized sessions from every archived raw snapshot, oldest first (after companion upgrades)."""
    outcomes: list[str] = []
    snapshots = sorted(p for p in archive.raw_dir.glob("*.lua") if p.is_file())
    for raw_path in snapshots:
        data = _read(raw_path)
        if data is None:
            continue
        try:
            parsed = parse(data)
        except LuaParseError as e:
            log(f"skipping {raw_path.name}: {e}")
            continue
        db = parsed.get("RambleonDB")
        sessions = sessions_from_db(to_python(db)) if db is not None else []
        capture = {"capturedAt": int(raw_path.stat().st_mtime), "rawSnapshot": str(raw_path.relative_to(archive.root)),
                   "sourceHash": blake(data), "sourceFile": "reprocessed", "reprocessedAt": int(time.time())}
        for s in sessions:
            attach_screenshots(s, paths.screenshots_dir, archive.screenshots_dir if copy_screenshots else None)
            outcome, out_path = archive.upsert_session(s, capture)
            if outcome in ("new", "updated"):
                log(f"{outcome} {s['id']} from {raw_path.name}")
            outcomes.append(f"{outcome} {s['id']}")
    archive.rebuild_index()
    log(f"reprocessed {len(snapshots)} snapshot(s)")
    return outcomes


def ingest_once(paths: Paths, archive: Archive, log: Log, copy_screenshots: bool = True,
                after_capture: AfterCapture = None) -> list[str]:
    files = paths.saved_variables_files()
    if not files:
        log("no Rambleon SavedVariables files found yet (play a session and end the chapter first)")
        return []
    outcomes: list[str] = []
    for f in files:
        outcomes += process_file(f, paths, archive, log, copy_screenshots, after_capture=after_capture)
    return outcomes


def watch(paths: Paths, archive: Archive, log: Log, interval: float = 1.0, copy_screenshots: bool = True,
          stop_after: float | None = None, rescan: float = 5.0, after_capture: AfterCapture = None,
          tick: Callable[[], None] | None = None) -> None:
    archive.ensure()
    archive.pid_path.write_text(str(os.getpid()))
    tracked: dict[Path, dict[str, Any]] = {}
    last_glob = 0.0
    files: list[Path] = []
    started = time.time()
    last_error: tuple[str, float] = ("", 0.0)
    log("watching for Rambleon SavedVariables writes (Ctrl-C to stop)")
    ingest_once(paths, archive, log, copy_screenshots, after_capture=after_capture)
    for f in paths.saved_variables_files():
        tracked[f] = {"sig": _signature(f), "stable": STABLE_POLLS, "done": _signature(f)}
    try:
        while True:
            now = time.time()
            if now - last_glob >= rescan:
                files = paths.saved_variables_files()
                last_glob = now
                for f in files:
                    tracked.setdefault(f, {"sig": None, "stable": 0, "done": None})
            for f, st in list(tracked.items()):
                sig = _signature(f)
                if sig is None:
                    st["sig"] = None
                    st["stable"] = 0
                    continue
                if sig != st["sig"]:
                    st["sig"] = sig
                    st["stable"] = 0
                    continue
                st["stable"] += 1
                if st["stable"] >= STABLE_POLLS and sig != st["done"]:
                    st["done"] = sig
                    process_file(f, paths, archive, log, copy_screenshots, after_capture=after_capture)
            if tick:
                try:
                    tick()
                except Exception as e:  # noqa: BLE001 — whatever runs between polls must never stop the archiving
                    message = f"{type(e).__name__}: {e}"
                    if message != last_error[0] or now - last_error[1] >= 60:
                        last_error = (message, now)
                        log(f"background step failed: {message}")
            if stop_after is not None and time.time() - started >= stop_after:
                return
            time.sleep(interval)
    finally:
        try:
            archive.pid_path.unlink()
        except OSError:
            pass
