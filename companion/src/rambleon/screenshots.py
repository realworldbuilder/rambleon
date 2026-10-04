"""Pair WoW screenshot files with a session and caption them.

The AddOn records a SCREENSHOT event (with a `reason` when it took the picture itself) the moment the
client confirms the file. A file is matched to the SCREENSHOT event closest in time; the caption then
names the moment ("Reached Level 9 in Dolanaar"). Files with no matching event fall back to the
nearest ordinary event. Files are copied into the archive when a copy directory is given, because the
WoW Screenshots folder belongs to the player and may be emptied at any time."""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from .archive import Archive
from .events import types_where

SCREENSHOT_RE = re.compile(r"^WoWScrnShot_(\d{2})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})\.(jpg|jpeg|png|tga)$", re.IGNORECASE)
WINDOW = 60          # seconds of slack around the session when looking for files
PAIR_WINDOW = 5      # seconds between a file's time and its SCREENSHOT event
FALLBACK_SKIP = types_where(shot_fallback=False)
INHERIT = ("reason", "auto", "level", "zone", "subzone")


def screenshot_time(path: Path) -> int:
    """The file's mtime is authoritative; the filename (local time) is the fallback."""
    try:
        return int(path.stat().st_mtime)
    except OSError:
        m = SCREENSHOT_RE.match(path.name)
        if m:
            mm, dd, yy, hh, mi, ss = (int(x) for x in m.groups()[:6])
            return int(datetime(2000 + yy, mm, dd, hh, mi, ss).timestamp())
        return 0


def find_screenshots(directory: Path | None, start: int | None, end: int | None) -> list[dict[str, Any]]:
    if not directory or not directory.is_dir() or not start:
        return []
    end = end or start
    out = []
    for p in sorted(directory.iterdir()):
        if not p.is_file() or not SCREENSHOT_RE.match(p.name):
            continue
        taken = screenshot_time(p)
        if start - WINDOW <= taken <= end + WINDOW:
            out.append({"path": str(p), "file": p.name, "takenAt": taken})
    return out


def _place(*candidates: dict[str, Any] | None) -> str | None:
    for c in candidates:
        if c and (c.get("subzone") or c.get("zone")):
            return c.get("subzone") or c.get("zone")
    return None


def event_index(shot: dict[str, Any]) -> int | None:
    """The paired event's index; tolerates entries written before 0.3."""
    idx = shot.get("eventIndex")
    return idx if idx is not None else shot.get("nearestEventIndex")


def caption(shot: dict[str, Any], events: list[dict[str, Any]]) -> str:
    idx = event_index(shot)
    ev = events[idx] if idx is not None and 0 <= idx < len(events) else None
    reason = shot.get("reason")
    place = _place(shot, ev)
    where = f" in {place}" if place else ""
    if reason == "LEVEL_UP":
        level = shot.get("level") or (ev or {}).get("level")
        return f"Reached Level {level}{where}" if level else f"Levelled up{where}"
    if reason == "MARK":
        return f"Marked moment{where}"
    if reason == "ZONE_ENTER":
        zone = shot.get("zone") or (ev or {}).get("zone")
        return f"Entered {zone}" if zone else f"Somewhere new{where}"
    return f"Screenshot{where}"


def pair_screenshots(shots: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
    """Match each file to its SCREENSHOT event (one file per event), else the nearest ordinary event.
    Rewrites eventIndex/eventSeconds/reason/caption in place; the old nearestEvent* keys are dropped."""
    shots.sort(key=lambda s: s.get("takenAt") or 0)
    claimed: set[int] = set()
    for shot in shots:
        taken = shot.get("takenAt") or 0
        for k in ("nearestEventIndex", "nearestEventSeconds"):
            shot.pop(k, None)
        for k in INHERIT:
            shot.pop(k, None)
        best_i, best_d = None, None
        for i, ev in enumerate(events):
            if ev.get("type") != "SCREENSHOT" or i in claimed:
                continue
            d = abs((ev.get("t") or 0) - taken)
            if d <= PAIR_WINDOW and (best_d is None or d < best_d):
                best_i, best_d = i, d
        if best_i is not None:
            claimed.add(best_i)
            ev = events[best_i]
            shot["eventIndex"], shot["eventSeconds"] = best_i, best_d
            for k in INHERIT:
                if ev.get(k) is not None:
                    shot[k] = ev[k]
            shot.setdefault("reason", "MANUAL")
        else:
            for i, ev in enumerate(events):
                if ev.get("type") in FALLBACK_SKIP:
                    continue
                d = abs((ev.get("t") or 0) - taken)
                if best_d is None or d < best_d:
                    best_i, best_d = i, d
            shot["eventIndex"], shot["eventSeconds"] = best_i, best_d
        shot["caption"] = caption(shot, events)


def attach_screenshots(session: dict[str, Any], directory: Path | None, copy_to: Path | None = None) -> dict[str, Any]:
    found = find_screenshots(directory, session.get("startedAt"), session.get("endedAt") or session.get("lastSeen"))
    merged = list(session.get("screenshots", []))
    existing = {s.get("file") for s in merged}
    merged += [shot for shot in found if shot["file"] not in existing]   # entries whose source vanished are kept
    if copy_to is not None:
        for shot in merged:
            if shot.get("archived") and Path(shot["archived"]).exists():
                continue
            src = Path(shot.get("path") or "")
            if not src.exists():
                continue
            dest_dir = copy_to / session["id"]
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / shot["file"]
            if not dest.exists():
                shutil.copy2(src, dest)
            shot["archived"] = str(dest)
    pair_screenshots(merged, session.get("events", []))
    session["screenshots"] = merged
    return session


def refresh_session_screenshots(archive: Archive, paths: Any, session_ids: list[str]) -> int:
    """Re-run pairing for archived sessions (late files, upgraded captions). Returns how many changed."""
    changed = 0
    for sid in session_ids:
        session = archive.load_session(sid)
        if session is None:
            continue
        capture = dict(session.get("archive") or {})
        attach_screenshots(session, paths.screenshots_dir, archive.screenshots_dir)
        outcome, _ = archive.upsert_session(session, capture)
        if outcome in ("new", "updated"):
            changed += 1
    if changed:
        archive.rebuild_index()
    return changed
