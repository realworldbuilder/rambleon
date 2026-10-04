"""Factual Markdown adventure log. No narrative, no invention."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from .archive import atomic_write_bytes
from .events import describe, place, shown  # noqa: F401 — describe and place are imported from here all over
from .screenshots import caption


def clock(t: int | None) -> str:
    if not t:
        return "—"
    return datetime.fromtimestamp(t).strftime("%-I:%M %p")


def long_date(t: int | None) -> str:
    return datetime.fromtimestamp(t).strftime("%B %-d, %Y") if t else "Unknown date"


def duration(seconds: int | None) -> str:
    seconds = int(seconds or 0)
    h, m = divmod(seconds // 60, 60)
    if h:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def render_markdown(session: dict[str, Any]) -> str:
    c = session.get("character", {})
    cnt = session.get("counters", {})
    name = c.get("displayName", "Unknown")
    lines: list[str] = []
    lines.append(f"# {name}")
    lines.append("")
    meta = [long_date(session.get("startedAt")), f"Adventure duration: {duration(session.get('playedSeconds'))}"]
    if c.get("race") or c.get("class"):
        meta.append(f"{c.get('race', '')} {c.get('class', '')}".strip() + (f", Level {c.get('endLevel')}" if c.get("endLevel") else ""))
    lines.append("  ".join(f"{m}" for m in meta[:1]) + "  ")
    for m in meta[1:]:
        lines.append(m + "  ")
    if session.get("state") not in ("ended",):
        lines.append("")
        lines.append("_Still in progress: captured as last seen._")
    lines.append("")
    lines.append("## Journey")
    lines.append("")
    for ev in session.get("events", []):
        if not shown(ev):
            continue
        lines.append(f"* {clock(ev.get('t'))} — {describe(ev)}")
    lines.append("")
    lines.append("## Progress")
    lines.append("")
    levels = cnt.get("levelsGained", 0)
    if c.get("startLevel") and c.get("endLevel") and c["endLevel"] != c["startLevel"]:
        levels_text = f"{levels} ({c['startLevel']} → {c['endLevel']})"
    else:
        levels_text = str(levels)
    lines += [
        f"Levels gained: {levels_text}  ",
        f"Quests accepted: {cnt.get('questsAccepted', 0)}  ",
        f"Quests completed: {cnt.get('questsCompleted', 0)}  ",
        f"Enemies slain: {cnt.get('kills', 0)}  ",
        f"Loot worth keeping: {cnt.get('loot', 0)}  ",
        f"Experience gained: {cnt.get('xpGained', 0):,}  ",
        f"Deaths: {cnt.get('deaths', 0)}  ",
        f"Places visited: {len(session.get('zones', []))}  ",
        f"People adventured with: {len(session.get('people', []))}  ",
        f"Playtime: {duration(session.get('playedSeconds'))}",
    ]
    people = sorted(session.get("people", []), key=lambda p: -(p.get("seconds") or 0))
    if people:
        lines += ["", "## People Met", ""]
        for p in people:
            mins = int(round((p.get("seconds") or 0) / 60))
            cls = f" ({p['class']})" if p.get("class") else ""
            lines.append(f"* {p.get('name')}{cls} — {mins} minute{'s' if mins != 1 else ''}")
    loot = [ev for ev in session.get("events", []) if ev.get("type") in ("LOOT", "EQUIP")]
    if loot:
        lines += ["", "## Loot Worth Keeping", ""]
        for ev in loot:
            lines.append(f"* {clock(ev.get('t'))} — {describe(ev)}")
    kills = sorted(session.get("kills", {}).items(), key=lambda kv: -(kv[1].get("count") or 0))
    if kills:
        lines += ["", "## Enemies Slain", ""]
        for name, info in kills:
            lines.append(f"* {name} × {info.get('count', 0)}")
    zones = session.get("zones", [])
    if zones:
        lines += ["", "## Places", ""]
        for z in zones:
            label = f"{z.get('subzone')} ({z.get('zone')})" if z.get("subzone") else str(z.get("zone"))
            lines.append(f"* {label}")
    notes = [ev for ev in session.get("events", []) if ev.get("type") == "NOTE"]
    if notes:
        lines += ["", "## Notes", ""]
        for ev in notes:
            lines.append(f"* {clock(ev.get('t'))} — {ev.get('text')}")
    shots = session.get("screenshots", [])
    if shots:
        lines += ["", "## Screenshots", ""]
        for s in shots:
            lines.append(f"* {clock(s.get('takenAt'))} — {caption(s, session.get('events', []))} · `{s.get('archived') or s.get('path')}`")
    lines += ["", "---", f"Session `{session.get('id')}` · schema {session.get('schemaVersion')} · Rambleon {session.get('client', {}).get('addonVersion', '?')}", ""]
    return "\n".join(lines)


def night_stats(session: dict[str, Any]) -> dict[str, Any]:
    """The numbers of a night (or a session), under the names every page, table and notification uses."""
    cnt = session.get("counters", {})
    c = session.get("character", {})
    return {
        "duration": duration(session.get("playedSeconds")),
        "levels": cnt.get("levelsGained", 0), "startLevel": c.get("startLevel"), "endLevel": c.get("endLevel"),
        "quests": cnt.get("questsCompleted", 0), "accepted": cnt.get("questsAccepted", 0),
        "places": len(session.get("zones", [])), "kills": cnt.get("kills", 0), "loot": cnt.get("loot", 0),
        "deaths": cnt.get("deaths", 0), "people": len(session.get("people", [])), "xp": cnt.get("xpGained", 0),
    }


def render_recap(session: dict[str, Any]) -> str:
    """The short shareable recap, from the numbers alone. The AI version replaces it when available."""
    cnt = session.get("counters", {})
    people = session.get("people", [])
    lines = [f"{duration(session.get('playedSeconds'))} in Azeroth tonight."]
    levels = cnt.get("levelsGained", 0)
    lines.append(f"{levels} level{'s' if levels != 1 else ''}.")
    lines.append(f"{cnt.get('questsCompleted', 0)} quests.")
    lines.append(f"{len(session.get('zones', []))} places.")
    if cnt.get("kills"):
        lines.append(f"{cnt['kills']} enemies slain.")
    lines.append(f"{cnt.get('deaths', 0)} deaths.")
    if len(people) == 1:
        lines.append(f"Travelled with {people[0].get('name')}.")
    elif people:
        lines.append(f"{len(people)} travelling companions.")
    else:
        lines.append("Travelled alone.")
    lines.append("Ramble on.")
    return "\n".join(lines) + "\n"


def _quest_label(ev: dict[str, Any]) -> str:
    return ev.get("title") or "quest " + str(ev.get("questID"))


def _qkey(ev: dict[str, Any]) -> Any:
    """One quest = one questID; a quest whose id was never captured is keyed by its title."""
    return ev.get("questID") if ev.get("questID") is not None else ("title", ev.get("title"))


def quest_summary(night: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    """Quests of a night as lists, not counts.

    `completed`: QUEST_COMPLETED events in order, one per questID (sessions of one night can overlap).
    `open`: QUEST_ACCEPTED events (one per questID) whose quest was neither turned in nor abandoned that night.
    """
    completed: list[dict[str, Any]] = []
    accepted: list[dict[str, Any]] = []
    seen_done: set[Any] = set()
    seen_acc: set[Any] = set()
    for ev in night.get("events", []):
        t = ev.get("type")
        key = _qkey(ev)
        if t == "QUEST_COMPLETED" and key not in seen_done:
            seen_done.add(key)
            completed.append(ev)
        elif t == "QUEST_ACCEPTED" and key not in seen_acc:
            seen_acc.add(key)
            accepted.append(ev)
        elif t == "QUEST_ABANDONED" and key in seen_acc:     # dropped; picking it up again later counts afresh
            seen_acc.discard(key)
            accepted = [a for a in accepted if _qkey(a) != key]
    open_quests = [ev for ev in accepted if _qkey(ev) not in seen_done]
    return {"completed": completed, "open": open_quests}


def carried_over(prior: list[dict[str, Any]], night: dict[str, Any]) -> list[tuple[dict[str, Any], int]]:
    """Quests accepted on an earlier night and never turned in, up to the end of `night`.

    Returns (the first QUEST_ACCEPTED event, the chapter it was accepted in), oldest first. `prior` is
    nights.earlier_nights() output, so chapter k is prior[k-1]. A quest accepted again in `night` is not
    carried: it shows under that night's own "picked up". A quest abandoned since (AddOn 0.4.0 records
    that) is no longer carried; one abandoned before that still shows, so this is what Rambleon knows, not
    the quest log.
    """
    carrying: dict[Any, tuple[dict[str, Any], int]] = {}
    for k, earlier in enumerate(prior, start=1):
        for ev in earlier.get("events", []):
            t = ev.get("type")
            if t == "QUEST_ACCEPTED":
                carrying.setdefault(_qkey(ev), (ev, k))
            elif t in ("QUEST_COMPLETED", "QUEST_ABANDONED"):
                carrying.pop(_qkey(ev), None)
    for ev in night.get("events", []):
        if ev.get("type") in ("QUEST_ACCEPTED", "QUEST_COMPLETED", "QUEST_ABANDONED"):
            carrying.pop(_qkey(ev), None)
    return list(carrying.values())


def _by_zone(events: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        groups.setdefault(ev.get("zone") or "Elsewhere", []).append(ev)
    return list(groups.items())


def _collapse_titles(events: list[dict[str, Any]]) -> list[tuple[dict[str, Any], int]]:
    """Chain quests share a title ("Bashal'Aran" parts 1-4 are four questIDs): one line with a count, last part's details."""
    out: list[tuple[dict[str, Any], int]] = []
    index: dict[str, int] = {}
    for ev in events:
        label = _quest_label(ev)
        if label in index:
            i = index[label]
            out[i] = (ev, out[i][1] + 1)
        else:
            index[label] = len(out)
            out.append((ev, 1))
    return out


def _times(n: int) -> str:
    return f" ×{n}" if n > 1 else ""


def _collapse_carried(carried: list[tuple[dict[str, Any], int]]) -> list[tuple[dict[str, Any], int, int]]:
    """_collapse_titles for carried_over() output: (event, count, chapter first accepted in)."""
    chapter = {id(ev): k for ev, k in carried}
    out = []
    for ev, n in _collapse_titles([ev for ev, _ in carried]):
        first = min(chapter[id(e)] for e, _ in carried if _quest_label(e) == _quest_label(ev))
        out.append((ev, n, first))
    return out


def render_catchup(night: dict[str, Any], carried: list[tuple[dict[str, Any], int]] | None = None) -> str:
    """A plain-text quest list to paste to a friend: what was turned in tonight, where, what is still open,
    and (`carried`, from carried_over()) what is still being carried from earlier chapters."""
    c = night.get("character", {})
    started = night.get("startedAt")
    when = datetime.fromtimestamp(started).strftime("%A, %B %-d") if started else "Unknown date"
    start, end = c.get("startLevel"), c.get("endLevel")
    if start and end and start != end:
        level = f"Level {start} → {end}"
    elif end:
        level = f"Level {end}"
    else:
        level = ""
    header = " — ".join(x for x in (c.get("displayName", "Unknown"), when, level) if x)
    lines = [header]
    if night.get("state") not in ("ended",):
        lines.append("(night still open — captured as last seen)")
    q = quest_summary(night)
    lines.append("")
    if not q["completed"] and not q["open"]:
        lines.append("No quests turned in tonight.")
    if q["completed"]:
        lines.append(f"Quests turned in ({len(q['completed'])})")
        for zone, evs in _by_zone(q["completed"]):
            lines.append(zone)
            for ev, n in _collapse_titles(evs):
                detail = [d for d in (ev.get("subzone"), f"lv {ev['level']}" if ev.get("level") else None) if d]
                lines.append(f"  - {_quest_label(ev)}{_times(n)}" + (f" ({', '.join(detail)})" if detail else ""))
    if q["open"]:
        if q["completed"]:
            lines.append("")
        lines.append(f"Picked up, not finished yet ({len(q['open'])})")
        for ev, n in _collapse_titles(q["open"]):
            where = place(ev)
            lines.append(f"  - {_quest_label(ev)}{_times(n)}" + (f" ({where})" if where else ""))
    if carried:
        if q["completed"] or q["open"]:
            lines.append("")
        lines.append(f"Still carrying from earlier chapters ({len(carried)})")
        for ev, n, k in _collapse_carried(carried):
            detail = [d for d in (place(ev), f"since Chapter {k}") if d]
            lines.append(f"  - {_quest_label(ev)}{_times(n)} ({', '.join(detail)})")
    places = _by_zone([z for z in night.get("zones", []) if z.get("subzone")])
    if places:
        lines.append("")
        parts = []
        for zone, zs in places:
            names: list[str] = []
            for z in zs:
                if z["subzone"] not in names:
                    names.append(z["subzone"])
            parts.append(f"{', '.join(names)} ({zone})")
        lines.append("Places: " + "; ".join(parts))
    return "\n".join(lines) + "\n"


def export_filename(session: dict[str, Any], suffix: str = "") -> str:
    started = session.get("startedAt") or 0
    day = session.get("nightDate") or datetime.fromtimestamp(started).strftime("%Y-%m-%d")
    return f"{day}-{session.get('character', {}).get('slug', 'unknown')}{suffix}.md"


def export_session(session: dict[str, Any], exports_dir: Path) -> Path:
    out = exports_dir / "markdown" / export_filename(session)
    if out.exists() and session.get("kind") != "night":
        # Several sessions on one day: keep them apart with the session's local start time.
        started = session.get("startedAt") or 0
        stamp = datetime.fromtimestamp(started).strftime("%H%M")
        candidate = out.with_name(out.stem + f"-{stamp}.md")
        try:
            existing = out.read_text(encoding="utf-8")
            if f"Session `{session.get('id')}`" not in existing:
                out = candidate
        except OSError:
            out = candidate
    atomic_write_bytes(out, render_markdown(session).encode("utf-8"))
    return out
