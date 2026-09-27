"""A chapter is a night in Azeroth: every session a character played that evening, stitched together.
Sessions stay as they were archived; nights are derived on demand."""
from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

from .archive import Archive, load_json
from .model import COUNTER_KEYS, SUSPEND_TIMEOUT
from .screenshots import pair_screenshots

CUTOFF_HOUR = 5  # play that runs past midnight still belongs to the evening it started


def night_date(started_at: int | None) -> str:
    dt = datetime.fromtimestamp(started_at or 0)
    if dt.hour < CUTOFF_HOUR:
        dt -= timedelta(days=1)
    return dt.strftime("%Y-%m-%d")


def _merge_keyed(existing: list[dict[str, Any]], incoming: list[dict[str, Any]], key: str, sum_fields: tuple[str, ...]) -> None:
    index = {str(e.get(key)): e for e in existing}
    for item in incoming:
        k = str(item.get(key))
        if k in index:
            e = index[k]
            for f in sum_fields:
                e[f] = (e.get(f) or 0) + (item.get(f) or 0)
            e["lastSeen"] = max(e.get("lastSeen") or 0, item.get("lastSeen") or 0)
        else:
            copy = dict(item)
            existing.append(copy)
            index[k] = copy


def session_over(s: dict[str, Any], now: float | None = None) -> bool:
    """Judged now, not when the snapshot was normalized: ended, or not seen for longer than the resume window."""
    if s.get("state") == "ended":
        return True
    now = time.time() if now is None else now
    return (now - (s.get("lastSeen") or s.get("startedAt") or 0)) > SUSPEND_TIMEOUT


def build_night(sessions: list[dict[str, Any]], now: float | None = None) -> dict[str, Any]:
    sessions = sorted(sessions, key=lambda s: s.get("startedAt") or 0)
    first, last = sessions[0], sessions[-1]
    date = night_date(first.get("startedAt"))
    night: dict[str, Any] = {
        "kind": "night",
        "schemaVersion": first.get("schemaVersion"),
        "id": f"night-{date}-{first['character'].get('slug', 'unknown')}",
        "nightDate": date,
        "sessionIds": [s["id"] for s in sessions],
        "state": "ended" if all(session_over(s, now) for s in sessions) else "open",
        "startedAt": first.get("startedAt"),
        "endedAt": max((s.get("endedAt") or s.get("lastSeen") or 0) for s in sessions) or None,
        "playedSeconds": sum(s.get("playedSeconds") or 0 for s in sessions),
        "endReason": last.get("endReason"),
        "character": dict(last.get("character", {})),
        "client": dict(last.get("client", {})),
        "counters": {k: sum((s.get("counters", {}).get(k) or 0) for s in sessions) for k in COUNTER_KEYS},
        "events": [], "zones": [], "people": [], "kills": {}, "screenshots": [], "failedEvents": [],
    }
    night["character"]["startLevel"] = first.get("character", {}).get("startLevel")
    night["character"]["endLevel"] = last.get("character", {}).get("endLevel")
    for i, s in enumerate(sessions):
        for ev in s.get("events", []):
            t = ev.get("type")
            if t == "RESUMED":
                continue
            if t == "SESSION_START" and i > 0:
                continue
            if t == "SESSION_END" and i < len(sessions) - 1:
                continue
            night["events"].append(ev)
        _merge_keyed(night["zones"], [dict(z, _k=f"{z.get('zone')}|{z.get('subzone') or ''}") for z in s.get("zones", [])], "_k", ("visits",))
        _merge_keyed(night["people"], s.get("people", []), "name", ("seconds", "joins"))
        for name, info in (s.get("kills") or {}).items():
            k = night["kills"].setdefault(name, {"count": 0, "xp": 0, "firstAt": info.get("firstAt"), "lastAt": info.get("lastAt")})
            k["count"] += info.get("count") or 0
            k["xp"] += info.get("xp") or 0
            k["lastAt"] = max(k.get("lastAt") or 0, info.get("lastAt") or 0)
        seen = {sh.get("file") for sh in night["screenshots"]}
        night["screenshots"] += [sh for sh in s.get("screenshots", []) if sh.get("file") not in seen]
        for fe in s.get("failedEvents", []):
            if fe not in night["failedEvents"]:
                night["failedEvents"].append(fe)
    for z in night["zones"]:
        z.pop("_k", None)
    night["events"].sort(key=lambda e: e.get("t") or 0)
    # screenshot → its event again, over the merged timeline
    night["screenshots"] = [dict(sh) for sh in night["screenshots"]]
    pair_screenshots(night["screenshots"], night["events"])
    night["counters"]["zonesVisited"] = len(night["zones"])
    return night


def nights(archive: Archive, slug: str | None = None) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in archive.list_sessions():
        if row.get("trivial"):
            continue
        if slug and row.get("slug") != slug:
            continue
        session = load_json(archive.normalized_dir / row["file"])
        key = (row.get("slug") or "unknown", night_date(row.get("startedAt")))
        groups.setdefault(key, []).append(session)
    out = [build_night(v) for v in groups.values()]
    out.sort(key=lambda n: n.get("startedAt") or 0)
    return out


def resolve_night(archive: Archive, ref: str) -> dict[str, Any] | None:
    """ref: latest | tonight | YYYY-MM-DD | a night id | a session id (its night)."""
    all_nights = nights(archive)
    if not all_nights:
        return None
    if ref in ("latest", "tonight", "last", ""):
        return all_nights[-1]
    for n in all_nights:
        if n["id"] == ref or n["nightDate"] == ref or ref in n["sessionIds"]:
            return n
    matches = [n for n in all_nights if n["id"].startswith(ref) or any(s.startswith(ref) for s in n["sessionIds"])]
    return matches[0] if len(matches) == 1 else None


def earlier_nights(archive: Archive, night: dict[str, Any]) -> list[dict[str, Any]]:
    """Nights of the same character strictly before this one, oldest first: index k-1 is chapter k.
    The night itself is never in the list, so re-writing a chapter never treats an earlier run of the
    same night as memory."""
    slug = night.get("character", {}).get("slug")
    started = night.get("startedAt") or 0
    return [n for n in nights(archive, slug)
            if (n.get("startedAt") or 0) < started and n.get("id") != night.get("id")]


def chapter_number(archive: Archive, night: dict[str, Any]) -> int:
    return len(earlier_nights(archive, night)) + 1
