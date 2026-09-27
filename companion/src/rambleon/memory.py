"""What the writer may remember from earlier chapters: a factual line per earlier night, the previous chapter
as it was written, and who the character has travelled with before. Everything comes from nights already on
disk and their journal sidecars; nothing here is new evidence, and the prompt says so."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from .export import duration, long_date
from .publish import chapter_title, load_journal

STORY_LIMIT = 3           # earlier chapters summarized as one line each
ZONES_PER_CHAPTER = 3
COMPANIONS_PER_CHAPTER = 3
MOST_OF_THE_NIGHT = 0.6   # share of playedSeconds above which a companion was there "most of the night"


def _heading(session: dict[str, Any], journal: dict[str, Any] | None, number: int) -> str | None:
    """The title without its 'Chapter N —' prefix, or None when the chapter was never written."""
    if not journal or not journal.get("title"):
        return None
    title = chapter_title(session, journal, number)
    return title.split(" — ", 1)[1].strip() if " — " in title else title.strip()


def _zones(night: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for z in night.get("zones", []):
        name = z.get("zone")
        if name and name not in out:
            out.append(name)
    return out[:ZONES_PER_CHAPTER]


def _companions(night: dict[str, Any]) -> list[dict[str, Any]]:
    people = sorted(night.get("people", []), key=lambda p: -(p.get("seconds") or 0))
    return [{"name": p.get("name"), "seconds": p.get("seconds") or 0} for p in people[:COMPANIONS_PER_CHAPTER] if p.get("name")]


def previous_chapters(prior: list[dict[str, Any]], exports_dir: Path, limit: int = STORY_LIMIT) -> list[dict[str, Any]]:
    """One factual record per earlier night, the last `limit` of them, oldest first. `prior` is
    nights.earlier_nights() output, so chapter k is prior[k-1]."""
    out = []
    for i, n in enumerate(prior, start=1):
        if i <= len(prior) - limit:
            continue
        c = n.get("character", {})
        out.append({
            "chapter": i,
            "date": n.get("nightDate"),
            "startedAt": n.get("startedAt"),
            "title": _heading(n, load_journal(exports_dir, n["id"]), i),
            "startLevel": c.get("startLevel"),
            "endLevel": c.get("endLevel"),
            "zones": _zones(n),
            "companions": _companions(n),
            "playedSeconds": n.get("playedSeconds") or 0,
            "previous": i == len(prior),
        })
    return out


def previous_journal(prior: list[dict[str, Any]], exports_dir: Path) -> dict[str, Any] | None:
    """The last earlier chapter as it was written, or None when no journal exists for it."""
    if not prior:
        return None
    last = prior[-1]
    journal = load_journal(exports_dir, last["id"])
    text = (journal or {}).get("journal")
    if not isinstance(text, str) or not text.strip():
        return None
    return {"chapter": len(prior), "title": journal.get("title"), "journal": text.strip()}


def _first_join(night: dict[str, Any], name: str) -> dict[str, Any] | None:
    for ev in night.get("events", []):
        if ev.get("type") == "GROUP_JOIN" and ev.get("name") == name:
            return ev
    return None


def companion_history(prior: list[dict[str, Any]], night: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """For each person in tonight's roster: what earlier nights know about them. Names never seen before
    are absent. Other players are known by name only (the client gives no realm or GUID for them)."""
    out: dict[str, dict[str, Any]] = {}
    for p in night.get("people", []):
        name = p.get("name")
        if not name:
            continue
        chapters: list[int] = []
        seconds = 0
        first_met: dict[str, Any] | None = None
        for i, n in enumerate(prior, start=1):
            match = next((q for q in n.get("people", []) if q.get("name") == name), None)
            if not match:
                continue
            chapters.append(i)
            seconds += match.get("seconds") or 0
            if first_met is None:
                join = _first_join(n, name)
                first_met = {"date": n.get("nightDate"), "startedAt": n.get("startedAt"), "chapter": i,
                             "place": (join.get("subzone") or join.get("zone")) if join else None}
        if chapters:
            out[name] = {"nights": len(chapters), "chapters": chapters, "seconds": seconds,
                         "firstMet": first_met, "lastChapter": chapters[-1]}
    return out


def build_memory(prior: list[dict[str, Any]], night: dict[str, Any], exports_dir: Path) -> dict[str, Any] | None:
    if not prior:
        return None
    return {"previous": previous_chapters(prior, exports_dir),
            "journal": previous_journal(prior, exports_dir),
            "history": companion_history(prior, night)}


def _chapters_phrase(chapters: list[int]) -> str:
    labels = [str(c) for c in chapters]
    if len(labels) == 1:
        return f"Chapter {labels[0]}"
    return "Chapters " + ", ".join(labels[:-1]) + " and " + labels[-1]


def _with_phrase(entry: dict[str, Any]) -> str:
    comps = entry.get("companions") or []
    if not comps:
        return "travelled alone"
    first = comps[0]
    played = entry.get("playedSeconds") or 0
    if played and first["seconds"] >= MOST_OF_THE_NIGHT * played:
        lead = f"{first['name']} (most of the night)"
    else:
        lead = f"{first['name']} ({duration(first['seconds'])})"
    rest = [c["name"] for c in comps[1:]]
    return "with " + ", ".join([lead] + rest)


def render_memory(memory: dict[str, Any] | None) -> list[str]:
    """Prompt lines for the 'Story so far' section; empty when there is nothing to remember."""
    if not memory or not memory.get("previous"):
        return []
    lines = ["## Story so far (memory of earlier chapters — not tonight's events)", ""]
    for e in memory["previous"]:
        head = f"Chapter {e['chapter']}" + (f" — {e['title']}" if e.get("title") else "")
        when = long_date(e.get("startedAt"))
        tag = ", the previous chapter" if e.get("previous") else ""
        levels = f"level {e.get('startLevel')} → {e.get('endLevel')}"
        zones = ", ".join(e.get("zones") or []) or "no place recorded"
        lines.append(f"- {head} ({when}){tag}: {levels}; {zones}; {_with_phrase(e)}.")
    j = memory.get("journal")
    if j:
        lines += ["", "### The previous chapter, as written (for continuity only; do not retell it)", "", j["journal"]]
    return lines


def companion_suffix(name: str, history: dict[str, dict[str, Any]] | None, note: str | None = None) -> str:
    """Appended to a 'People met' line. Empty when there is no memory at all (a lone session record)."""
    parts: list[str] = []
    if history is not None:
        h = history.get(name)
        if h:
            bits = [f"familiar: {h['nights']} earlier night{'s' if h['nights'] != 1 else ''} ({_chapters_phrase(h['chapters'])})"]
            fm = h.get("firstMet") or {}
            if fm.get("startedAt"):
                bits.append(f"first met {long_date(fm['startedAt'])}" + (f" in {fm['place']}" if fm.get("place") else ""))
            bits.append(f"{duration(h['seconds'])} together before tonight")
            parts.append(", ".join(bits))
        else:
            parts.append("first time together")
    if note:
        parts.append(f"player's note: \"{note}\"")
    return "".join(f" — {p}" for p in parts)
