"""The route guide: how one character actually leveled, stretch by stretch, across every night.

Facts come from the archive; prose from the writer when the Claude CLI is present. It is not advice and never
the best route: the road this character took, retold so another player could walk it. A *mode* is a prompt
file (`prompts/guides/<mode>.md`) that says what to write from the same facts; `route` speaks to another
player, `season` to the player themself, and any file of your own works too."""
from __future__ import annotations

import html
import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from .archive import Archive, atomic_write_bytes, atomic_write_json, load_json
from .config import character_overrides, guide_mode
from .export import _collapse_titles, _quest_label, _times, duration, long_date, place
from .memory import _chapters_phrase
from .nights import nights as list_nights
from .publish import (CSS, FONTS, _figure, _page_name, _paragraphs, chapter_title, guide_page_name as default_page_name,
                      index_anchor, load_journal, prepare_images, top_nav)
from .screenshots import caption as shot_caption, event_index
from .summarize import DEFAULT_MODEL, DEFAULT_VOICE, claude_available, load_voice, run_claude

GUIDES_DIR = Path(__file__).parent / "prompts" / "guides"
DEFAULT_MODE = "route"
SKIP = {"SESSION_START", "SESSION_END", "RESUMED"}
ANCHORS = {"QUEST_COMPLETED", "LEVEL_UP", "DEATH", "NOTE"}       # a visit with one of these is a stretch of its own
PASSIVE = {"ZONE_ENTER", "SCREENSHOT", "REVIVED", "GROUP_LEAVE", "INSTANCE_EXIT"}   # being somewhere, not doing anything
MIN_STRETCH = 20 * 60      # a visit with no anchor needs this much play, with something done, to stand alone
MAX_FIRST_KILLS = 12
MAX_LOOT = 10
ELSEWHERE = "Elsewhere"


# ---------------------------------------------------------------------------------------------------
# Modes

def available_modes() -> list[str]:
    return sorted(p.stem for p in GUIDES_DIR.glob("*.md"))


def default_mode(repo_root: Path | None = None) -> str:
    return os.environ.get("RAMBLEON_GUIDE_MODE") or guide_mode(repo_root) or DEFAULT_MODE


def load_mode(name: str | None) -> tuple[str, str]:
    """(mode name, prompt text). `name` is a bundled mode or a path to your own prompt file."""
    name = name or default_mode()
    candidate = Path(name).expanduser()
    if (name.endswith(".md") or "/" in name) and candidate.is_file():
        return candidate.stem, candidate.read_text(encoding="utf-8").strip()
    path = GUIDES_DIR / f"{name}.md"
    if not path.exists():
        raise ValueError(f"unknown guide mode {name!r}; available: {', '.join(available_modes())} (or a path to a .md file)")
    return name, path.read_text(encoding="utf-8").strip()


def guide_page_name(slug: str, mode: str | None = None) -> str:
    """The configured default mode owns `guide-<slug>.html` (what the story pages link to); other modes sit beside it."""
    mode = mode or default_mode()
    return default_page_name(slug) if mode == default_mode() else f"guide-{slug}-{mode}.html"


def sidecar_path(exports_dir: Path, slug: str, mode: str) -> Path:
    return exports_dir / "guide" / f"{slug}-{mode}.json"


def load_guide_prose(exports_dir: Path, slug: str, mode: str) -> dict[str, Any] | None:
    p = sidecar_path(exports_dir, slug, mode)
    if p.exists():
        try:
            return load_json(p)
        except (OSError, ValueError):
            return None
    return None


# ---------------------------------------------------------------------------------------------------
# Segmentation: a chapter is a zone stretch

def _span(events: list[dict[str, Any]]) -> int:
    """Play inside a run: per night, last moment minus first, so a run that spans nights is not measured in days."""
    by_night: dict[int, tuple[int, int]] = {}
    for ev in events:
        t = ev.get("t") or 0
        lo, hi = by_night.get(ev["_night"], (t, t))
        by_night[ev["_night"]] = (min(lo, t), max(hi, t))
    return sum(hi - lo for lo, hi in by_night.values())


def _stands_alone(run: dict[str, Any]) -> bool:
    types = {ev.get("type") for ev in run["events"]}
    if types & ANCHORS:
        return True
    return bool(types - PASSIVE) and _span(run["events"]) >= MIN_STRETCH


def _runs(nights_: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Consecutive events in one zone, across night boundaries. Events without a zone inherit their neighbour's."""
    runs: list[dict[str, Any]] = []
    zone: str | None = None
    lead: list[dict[str, Any]] = []      # events before the first zone is known
    for k, night in enumerate(nights_):
        for i, ev in enumerate(night.get("events", [])):
            if ev.get("type") in SKIP:
                continue
            tagged = dict(ev, _night=k, _idx=i)
            if ev.get("zone"):
                zone = ev["zone"]
            if zone is None:
                lead.append(tagged)
                continue
            tagged["_zone"] = zone
            for early in lead:
                early["_zone"] = zone
            if runs and runs[-1]["zone"] == zone:
                runs[-1]["events"] += lead + [tagged]
            else:
                runs.append({"zone": zone, "events": lead + [tagged]})
            lead = []
    if lead:
        for early in lead:
            early["_zone"] = ELSEWHERE
        runs.append({"zone": ELSEWHERE, "events": lead})
    return runs


def _fold(runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Visits where nothing happened fold into their neighbour; adjacent visits to one zone merge."""
    out: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for run in runs:
        if _stands_alone(run):
            events = [e for p in pending for e in p["events"]] + run["events"]
            pending = []
            if out and out[-1]["zone"] == run["zone"]:
                out[-1]["events"] += events
            else:
                out.append({"zone": run["zone"], "events": events})
        elif out:
            out[-1]["events"] += run["events"]
        else:
            pending.append(run)
    if pending:                              # nothing stood alone: one stretch, named after the busiest zone
        events = [e for p in pending for e in p["events"]]
        busiest = max(pending, key=lambda r: len(r["events"]))["zone"]
        out.append({"zone": busiest, "events": events})
    return out


def _qkey(ev: dict[str, Any]) -> Any:
    return ev.get("questID") if ev.get("questID") is not None else ("title", ev.get("title"))


def _chapter(number: int, run: dict[str, Any], seen_done: set[Any]) -> dict[str, Any]:
    zone, evs = run["zone"], run["events"]
    subzones: list[str] = []
    passing: list[str] = []
    accepted: dict[Any, dict[str, Any]] = {}
    completed: dict[Any, dict[str, Any]] = {}
    level_ups: dict[int, str | None] = {}
    first_kills: list[str] = []
    loot: list[dict[str, Any]] = []
    loot_seen: set[tuple[str, Any]] = set()
    deaths = 0
    death_places: list[str] = []
    notes: list[tuple[int, dict[str, Any]]] = []
    people: list[str] = []
    instances: list[str] = []
    for ev in evs:
        t = ev.get("type")
        if ev["_zone"] == zone:
            if ev.get("subzone") and ev["subzone"] not in subzones:
                subzones.append(ev["subzone"])
        elif ev["_zone"] != ELSEWHERE and ev["_zone"] not in passing:
            passing.append(ev["_zone"])
        if t == "QUEST_ACCEPTED":
            accepted.setdefault(_qkey(ev), ev)
        elif t == "QUEST_COMPLETED":
            key = _qkey(ev)
            if key not in seen_done:
                seen_done.add(key)
                completed[key] = ev
        elif t == "LEVEL_UP" and ev.get("level"):
            level_ups.setdefault(int(ev["level"]), place(ev))
        elif t == "FIRST_KILL" and ev.get("name") and ev["name"] not in first_kills:
            first_kills.append(ev["name"])
        elif t in ("LOOT", "EQUIP"):
            key = (t, ev.get("itemID") if ev.get("itemID") is not None else ev.get("name"))
            if key not in loot_seen:
                loot_seen.add(key)
                loot.append(ev)
        elif t == "DEATH":
            deaths += 1
            where = place(ev)
            if where and where not in death_places:
                death_places.append(where)
        elif t == "NOTE" and ev.get("text"):
            notes.append((ev["_night"] + 1, ev))
        elif t == "GROUP_JOIN" and ev.get("name") and ev["name"] not in people:
            people.append(ev["name"])
        elif t == "INSTANCE_ENTER" and ev.get("name") and ev["name"] not in instances:
            instances.append(ev["name"])
    levels = [int(ev["level"]) for ev in evs if ev.get("level")]
    night_ks = sorted({ev["_night"] for ev in evs})
    return {
        "number": number, "zone": zone, "subzones": subzones, "passing": passing,
        "startLevel": levels[0] if levels else None, "endLevel": max(levels) if levels else None,
        "levelUps": [{"level": lv, "place": where} for lv, where in sorted(level_ups.items())],
        "nights": [k + 1 for k in night_ks],                   # journal chapter numbers
        "startedAt": evs[0].get("t"), "endedAt": evs[-1].get("t"), "playedSeconds": _span(evs),
        "accepted": list(accepted.values()), "completed": list(completed.values()),
        "firstKills": first_kills[:MAX_FIRST_KILLS], "loot": loot[:MAX_LOOT],
        "deaths": deaths, "deathPlaces": death_places, "notes": notes, "people": people, "instances": instances,
        "events": [(ev["_night"], ev["_idx"]) for ev in evs],
        "screenshots": [],
    }


def stretches(nights_: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """The nights of one character, oldest first, cut into zone stretches. Pure."""
    seen_done: set[Any] = set()
    chapters = [_chapter(n, run, seen_done) for n, run in enumerate(_fold(_runs(nights_)), start=1)]
    owner = {key: ch for ch in chapters for key in ch["events"]}
    last_of_night: dict[int, dict[str, Any]] = {}
    for ch in chapters:
        for k in ch["nights"]:
            last_of_night[k - 1] = ch
    for k, night in enumerate(nights_):
        for shot in night.get("screenshots", []):
            idx = event_index(shot)
            ch = owner.get((k, idx)) if idx is not None else None
            ch = ch or last_of_night.get(k)
            if ch is not None:
                ch["screenshots"].append((k + 1, dict(shot, caption=shot.get("caption") or shot_caption(shot, night.get("events", [])))))
    return chapters


# ---------------------------------------------------------------------------------------------------
# The guide record

def _pronouns(gender: str | None) -> tuple[str, str]:
    """(subject, possessive) from the recorded gender; they/their when nothing was recorded."""
    g = (gender or "").lower()
    if g == "male":
        return "he", "his"
    if g == "female":
        return "she", "her"
    return "they", "their"


def build_guide(archive: Archive, slug: str, exports_dir: Path) -> dict[str, Any]:
    nights_ = list_nights(archive, slug)
    if not nights_:
        raise ValueError(f"no nights archived for {slug!r} (try `ramble nights`)")
    c = dict(nights_[-1].get("character", {}))
    for k, v in character_overrides(slug).items():        # rambleon.local.toml wins over old sessions
        if isinstance(v, (str, int, float, bool)) and k not in ("name", "slug"):
            c[k] = v
    name = c.get("displayName") or slug
    start = nights_[0].get("character", {}).get("startLevel")
    end = max((n.get("character", {}).get("endLevel") or 0) for n in nights_) or None
    if start and end and start != end:
        title = f"How {name} leveled {start}–{end} on Forever"
    else:
        title = f"How {name} travelled at level {end or start or '?'} on Forever"
    return {
        "slug": slug, "displayName": name, "character": c, "title": title,
        "startLevel": start, "endLevel": end,
        "nightCount": len(nights_), "nightIds": [n["id"] for n in nights_],
        "playedSeconds": sum(n.get("playedSeconds") or 0 for n in nights_),
        "firstAt": nights_[0].get("startedAt"), "lastAt": nights_[-1].get("startedAt"),
        "open": any(n.get("state") != "ended" for n in nights_),
        "nightTitles": {k + 1: chapter_title(n, load_journal(exports_dir, n["id"]), k + 1) for k, n in enumerate(nights_)},
        "pages": {k + 1: _page_name(n) for k, n in enumerate(nights_)},
        "nights": nights_,
        "chapters": stretches(nights_),
    }


def chapter_heading(ch: dict[str, Any]) -> str:
    a, b = ch.get("startLevel"), ch.get("endLevel")
    if a and b and a != b:
        return f"{ch['zone']}, level {a}–{b}"
    return f"{ch['zone']}, level {b or a}" if (a or b) else str(ch["zone"])


def level_range(ch: dict[str, Any]) -> str:
    a, b = ch.get("startLevel"), ch.get("endLevel")
    if a and b and a != b:
        return f"Level {a}–{b}"
    return f"Level {b or a}" if (a or b) else ""


def _dates(ch: dict[str, Any], guide: dict[str, Any]) -> str:
    nights_ = guide["nights"]
    first, last = nights_[ch["nights"][0] - 1], nights_[ch["nights"][-1] - 1]
    if first is last:
        return long_date(first.get("startedAt"))
    return f"{long_date(first.get('startedAt'))} – {long_date(last.get('startedAt'))}"


def _quest_line(evs: list[dict[str, Any]], where: bool) -> str:
    parts = []
    for ev, n in _collapse_titles(evs):
        detail = []
        if where and ev.get("subzone"):
            detail.append(ev["subzone"])
        if where and ev.get("level"):
            detail.append(f"level {ev['level']}")
        parts.append(f"{_quest_label(ev)}{_times(n)}" + (f" ({', '.join(detail)})" if detail else ""))
    return ", ".join(parts)


def _loot_line(evs: list[dict[str, Any]]) -> str:
    parts = []
    for ev in evs:
        q = f" ({ev['qualityName']})" if ev.get("qualityName") else ""
        n = f" ×{ev['count']}" if (ev.get("count") or 1) > 1 else ""
        parts.append(("equipped " if ev.get("type") == "EQUIP" else "") + f"{ev.get('name')}{n}{q}")
    return ", ".join(parts)


def facts(ch: dict[str, Any]) -> list[tuple[str, str]]:
    """The factual lines of one stretch, shared by the Markdown, the prompt and the page. Notes are separate."""
    out: list[tuple[str, str]] = []
    if ch["accepted"]:
        out.append(("Picked up", _quest_line(ch["accepted"], where=False)))
    if ch["completed"]:
        out.append(("Turned in", _quest_line(ch["completed"], where=True)))
    if ch["levelUps"]:
        out.append(("Reached", ", ".join(f"level {u['level']}" + (f" ({u['place']})" if u.get("place") else "") for u in ch["levelUps"])))
    if ch["firstKills"]:
        out.append(("First met in combat", ", ".join(ch["firstKills"])))
    if ch["loot"]:
        out.append(("Loot worth keeping", _loot_line(ch["loot"])))
    if ch["deaths"]:
        out.append(("Deaths", str(ch["deaths"]) + (f" ({', '.join(ch['deathPlaces'])})" if ch["deathPlaces"] else "")))
    if ch["people"]:
        out.append(("Company", ", ".join(ch["people"])))
    if ch["instances"]:
        out.append(("Instances", ", ".join(ch["instances"])))
    if ch["screenshots"]:
        out.append(("Pictures", "; ".join(f"{s.get('caption')} (Chapter {k})" for k, s in ch["screenshots"])))
    return out


def _where_line(ch: dict[str, Any]) -> str:
    return " · ".join(ch["subzones"]) if ch["subzones"] else ch["zone"]


def _from_line(ch: dict[str, Any], guide: dict[str, Any]) -> str:
    return f"From {_chapters_phrase(ch['nights'])} ({_dates(ch, guide)}) · {duration(ch['playedSeconds'])}"


def _meta_line(guide: dict[str, Any]) -> str:
    c = guide["character"]
    who = f"{c.get('race', '')} {c.get('class', '')}".strip()
    n = guide["nightCount"]
    span = long_date(guide["firstAt"]) if n == 1 else f"{long_date(guide['firstAt'])} – {long_date(guide['lastAt'])}"
    k = len(guide["chapters"])
    return " · ".join(x for x in (who, f"{n} night{'s' if n != 1 else ''}, {span}", f"{duration(guide['playedSeconds'])} in Azeroth",
                                  f"{k} stretch{'es' if k != 1 else ''}") if x)


def render_guide_markdown(guide: dict[str, Any]) -> str:
    _, poss = _pronouns(guide["character"].get("gender"))
    lines = [f"# {guide['title']}", "", f"_{_meta_line(guide)}_", "",
             f"The road {guide['displayName']} actually took, one stretch at a time. Not the best route; {poss} route. "
             "Chapter numbers refer to the journal."]
    if guide["open"]:
        lines += ["", "_(A night is still in progress: captured as last seen.)_"]
    lines += ["", "## Contents", ""]
    for ch in guide["chapters"]:
        lines.append(f"{ch['number']}. {chapter_heading(ch)}" + (f" — {', '.join(ch['subzones'])}" if ch["subzones"] else ""))
    for ch in guide["chapters"]:
        lines += ["", f"## {ch['number']}. {chapter_heading(ch)}", "", _where_line(ch) + "  ", _from_line(ch, guide) + "  "]
        if ch["passing"]:
            lines.append(f"Passing through {', '.join(ch['passing'])}  ")
        lines.append("")
        for label, text in facts(ch):
            lines.append(f"**{label}:** {text}  ")
        if ch["notes"]:
            lines.append("**Notes:**")
            for k, ev in ch["notes"]:
                lines.append(f"- \"{ev.get('text')}\" (Chapter {k})")
    lines += ["", "---", f"Route guide from {guide['nightCount']} night{'s' if guide['nightCount'] != 1 else ''} · Rambleon", ""]
    return "\n".join(lines)


# ---------------------------------------------------------------------------------------------------
# The prompt and the prose

def build_guide_prompt(guide: dict[str, Any], mode_text: str, voice: str | None = None) -> str:
    c = guide["character"]
    subj, poss = _pronouns(c.get("gender"))
    n = guide["nightCount"]
    rules = mode_text
    for key, value in (("{voice}", load_voice(voice)), ("{name}", guide["displayName"]), ("{pronouns}", f"{subj}/{poss}"),
                       ("{startLevel}", str(guide["startLevel"] or "?")), ("{endLevel}", str(guide["endLevel"] or "?")),
                       ("{nights}", f"{n} night{'s' if n != 1 else ''}")):
        rules = rules.replace(key, value)
    lines = [rules, "", "=" * 72, "", "## Character", "", f"- Name: {guide['displayName']}"]
    if c.get("race") or c.get("class"):
        lines.append(f"- {c.get('race', '')} {c.get('class', '')}".rstrip())
    if c.get("gender"):
        lines.append(f"- Gender: {c['gender']} (use matching pronouns)")
    else:
        lines.append("- Gender: not recorded — refer to the character by name or with they/them, never guess")
    lines.append(f"- Level at the start of the record: {guide['startLevel']}; now: {guide['endLevel']}")
    lines.append(f"- Nights recorded: {n} ({_meta_line(guide)})")
    lines.append("- Game: World of Warcraft: Forever")
    if guide["open"]:
        lines.append("- The last night is still in progress: its facts are as last seen")
    lines += ["", "## Stretches, in order (the only facts you may use; one section each, same headings)"]
    for ch in guide["chapters"]:
        lines += ["", f"## {ch['number']}. {chapter_heading(ch)}", ""]
        lines.append(f"- Where: {_where_line(ch)}" + (f" (passing through {', '.join(ch['passing'])})" if ch["passing"] else ""))
        lines.append(f"- When: {_chapters_phrase(ch['nights'])} of the journal ({_dates(ch, guide)}), {duration(ch['playedSeconds'])} of play")
        for label, text in facts(ch):
            lines.append(f"- {label}: {text}")
        if ch["notes"]:
            lines.append("- Player notes (verbatim, most important evidence): " +
                         "; ".join(f"\"{ev.get('text')}\" (Chapter {k})" for k, ev in ch["notes"]))
    lines.append("")
    return "\n".join(lines)


_HEADING = re.compile(r"^## (\d+)\.", re.M)


def split_prose(text: str) -> tuple[str, dict[int, str]]:
    """(intro, {stretch number: prose}) from the writer's output. Sections the guide does not have are the caller's to drop."""
    parts = _HEADING.split(text.replace("\r", ""))
    intro = "\n".join(l for l in parts[0].splitlines() if not l.lstrip().startswith("#")).strip()
    sections: dict[int, str] = {}
    for i in range(1, len(parts) - 1, 2):
        body = parts[i + 1]
        body = body.split("\n", 1)[1] if "\n" in body else ""
        sections[int(parts[i])] = body.strip()
    return intro, sections


def needs_prose(guide: dict[str, Any], sidecar: dict[str, Any] | None) -> bool:
    if not sidecar:
        return True
    return set(sidecar.get("nights") or []) != set(guide["nightIds"])


# ---------------------------------------------------------------------------------------------------
# The page

GUIDE_CSS = """
body.guide{max-width:1040px}
.guide-layout{display:grid;grid-template-columns:230px minmax(0,1fr);gap:36px;align-items:start}
.toc{position:sticky;top:16px;font-size:14px}.toc ol{list-style:none;margin:0;padding:0}.toc li{margin:0 0 8px}
.toc a{display:flex;gap:10px;text-decoration:none;color:var(--soft)}.toc a:hover{color:var(--link)}
.toc b{font:700 15px/1.3 Cinzel,Georgia,serif;color:#5a3510;min-width:20px}.toc small{display:block;color:var(--faint)}
p.intro{font-size:19px;color:var(--soft);margin:0 0 28px}
section.stretch{margin:0 0 40px}section.stretch h2{margin-top:0}section.stretch h2 .n{color:var(--gold);margin-right:8px}
section.stretch h2 .lv{font-size:14px;color:var(--faint);margin-left:10px;letter-spacing:1px;text-transform:uppercase}
.where,.from{color:var(--soft);font-size:15px}.prose{margin:14px 0}.prose p{margin:0 0 14px}
.facts{display:grid;grid-template-columns:max-content 1fr;gap:4px 14px;margin:14px 0}
.facts dt{color:var(--faint);font-size:13px;text-transform:uppercase;letter-spacing:1px}.facts dd{margin:0}
ul.notes li{font-style:italic}
@media(max-width:760px){.guide-layout{grid-template-columns:1fr}.toc{position:static}.facts{grid-template-columns:1fr;gap:2px}}
"""


def render_guide_html(guide: dict[str, Any], sidecar: dict[str, Any] | None, exports_dir: Path,
                      siblings: set[str] | None = None) -> str:
    _, poss = _pronouns(guide["character"].get("gender"))
    intro, prose = split_prose(sidecar["prose"]) if sidecar and sidecar.get("prose") else ("", {})
    written_through = None
    if sidecar and set(sidecar.get("nights") or []) != set(guide["nightIds"]):
        covered = [k + 1 for k, nid in enumerate(guide["nightIds"]) if nid in set(sidecar.get("nights") or [])]
        written_through = max(covered) if covered else None
    meta = [_meta_line(guide), f"the road {poss} feet actually took, not the best one"]
    if written_through:
        meta.append(f"prose retold through Chapter {written_through}")
    if guide["open"]:
        meta.append("a night is still in progress")
    parts = [f"<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
             f"<title>{html.escape(guide['title'])}</title>{FONTS}<style>{CSS}{GUIDE_CSS}</style></head><body id='top' class='guide'>",
             top_nav(("All chapters", index_anchor(guide["slug"])), ("About Rambleon", "../")),
             f"<h1>{html.escape(guide['title'])}</h1>",
             f"<div class='meta'>{html.escape(' · '.join(meta))}</div>",
             "<div class='guide-layout'><aside class='toc'><ol>"]
    for ch in guide["chapters"]:
        lv = level_range(ch)
        parts.append(f"<li><a href='#ch-{ch['number']}'><b>{ch['number']}</b><span>{html.escape(ch['zone'])}"
                     + (f"<small>{html.escape(lv)}</small>" if lv else "") + "</span></a></li>")
    parts.append("</ol></aside><main>")
    if intro:
        parts.append(f"<p class='intro'>{html.escape(intro)}</p>")
    else:
        parts.append(f"<p class='intro'>{html.escape(guide['displayName'])}'s road, one stretch at a time. Not the best route; {poss} route.</p>")
    for ch in guide["chapters"]:
        lv = level_range(ch)
        parts.append(f"<section class='stretch' id='ch-{ch['number']}'><h2><span class='n'>{ch['number']}</span>{html.escape(ch['zone'])}"
                     + (f"<span class='lv'>{html.escape(lv)}</span>" if lv else "") + "</h2>")
        where = _where_line(ch) + (f" · passing through {', '.join(ch['passing'])}" if ch["passing"] else "")
        parts.append(f"<div class='where'>{html.escape(where)}</div>")
        links = []
        for k in ch["nights"]:
            page = guide["pages"][k]
            title = guide["nightTitles"][k]
            label = title if title.startswith("Chapter") else f"Chapter {k} — {title}"
            if siblings is None or page in siblings:
                links.append(f"<a href='{html.escape(page)}'>{html.escape(label)}</a>")
            else:
                links.append(html.escape(label))
        parts.append(f"<div class='from'>From {', '.join(links)} · {html.escape(_dates(ch, guide))} · {html.escape(duration(ch['playedSeconds']))}</div>")
        if ch["number"] in prose and prose[ch["number"]]:
            parts.append("<div class='prose'>" + _paragraphs(prose[ch["number"]]) + "</div>")
        picture = _first_picture(ch, guide, exports_dir, siblings)
        if picture:
            parts.append(_figure(picture))
        rows = [(label, text) for label, text in facts(ch) if label != "Pictures"]
        if rows:
            parts.append("<dl class='facts'>" + "".join(f"<dt>{html.escape(l)}</dt><dd>{html.escape(t)}</dd>" for l, t in rows) + "</dl>")
        if ch["notes"]:
            parts.append("<ul class='notes'>" + "".join(f"<li>“{html.escape(str(ev.get('text')))}” <span class='faint'>(Chapter {k})</span></li>"
                                                        for k, ev in ch["notes"]) + "</ul>")
        parts.append("</section>")
    parts.append("<a class='totop' href='#top'>↑ Back to top</a></main></div>")
    parts.append(f"<footer>Recorded by Rambleon · {guide['nightCount']} night{'s' if guide['nightCount'] != 1 else ''}</footer></body></html>")
    return "\n".join(parts)


def _first_picture(ch: dict[str, Any], guide: dict[str, Any], exports_dir: Path, siblings: set[str] | None) -> dict[str, Any] | None:
    """The stretch's first screenshot as a web copy beside its night's page (the story page owns the image folder)."""
    for k, shot in ch["screenshots"]:
        page = guide["pages"][k]
        if siblings is not None and page not in siblings:
            continue
        night = guide["nights"][k - 1]
        for img in prepare_images(night, exports_dir / "html" / page.replace(".html", "")):
            if (img.get("takenAt") == shot.get("takenAt")) or (img.get("eventIndex") is not None and img.get("eventIndex") == event_index(shot)):
                return img
    return None


def export_guide_html(guide: dict[str, Any], sidecar: dict[str, Any] | None, exports_dir: Path, mode: str | None = None,
                      siblings: set[str] | None = None) -> Path:
    out = exports_dir / "html" / guide_page_name(guide["slug"], mode)
    atomic_write_bytes(out, render_guide_html(guide, sidecar, exports_dir, siblings).encode("utf-8"))
    return out


# ---------------------------------------------------------------------------------------------------
# Putting it together

def write_guide(archive: Archive, exports_dir: Path, slug: str, use_ai: bool = True, model: str = DEFAULT_MODEL,
                voice: str | None = None, mode: str | None = None, log: Callable[[str], None] = print,
                only_if_new: bool = False, siblings: set[str] | None = None) -> dict[str, Path | None]:
    """Facts always (Markdown + prompt), prose when the CLI is there and — with `only_if_new` — a night is new, then the page."""
    guide = build_guide(archive, slug, exports_dir)
    mode_name, mode_text = load_mode(mode)
    md_path = exports_dir / "markdown" / f"guide-{slug}.md"
    atomic_write_bytes(md_path, render_guide_markdown(guide).encode("utf-8"))
    prompt = build_guide_prompt(guide, mode_text, voice)
    prompt_path = exports_dir / "prompts" / f"guide-{slug}-{mode_name}-prompt.md"
    atomic_write_bytes(prompt_path, prompt.encode("utf-8"))
    result: dict[str, Path | None] = {"markdown": md_path, "prompt": prompt_path, "prose": None, "html": None}
    sidecar = load_guide_prose(exports_dir, slug, mode_name)
    k = len(guide["chapters"])
    if not use_ai:
        log(f"route guide: {k} stretch{'es' if k != 1 else ''}; prompt at {prompt_path} (AI skipped)")
    elif not claude_available():
        log(f"route guide: {k} stretch{'es' if k != 1 else ''}; prompt at {prompt_path}. No `claude` CLI found; paste it into any assistant.")
    elif only_if_new and not needs_prose(guide, sidecar):
        log("route guide prose unchanged (no new nights)")
    else:
        log(f"asking claude ({model}) to write the {mode_name} guide, {k} stretch{'es' if k != 1 else ''}…")
        text, diag = run_claude(prompt, model=model)
        if text is None:
            log(f"AI guide skipped: {diag}. The prompt is at {prompt_path}.")
        else:
            sidecar = {"slug": slug, "displayName": guide["displayName"], "title": guide["title"], "mode": mode_name,
                       "nights": list(guide["nightIds"]), "chapters": k, "prose": text.strip() + "\n",
                       "model": model, "voice": voice or os.environ.get("RAMBLEON_VOICE") or DEFAULT_VOICE,
                       "createdAt": int(time.time())}
            atomic_write_json(sidecar_path(exports_dir, slug, mode_name), sidecar)
            prose_path = exports_dir / "markdown" / f"guide-{slug}-{mode_name}-prose.md"
            header = f"_{guide['displayName']} · {_meta_line(guide)}_\n\n"
            atomic_write_bytes(prose_path, (f"# {guide['title']}\n\n" + header + text.strip() + "\n").encode("utf-8"))
            result["prose"] = prose_path
            log(f"guide prose written to {prose_path}")
    result["html"] = export_guide_html(guide, sidecar, exports_dir, mode_name, siblings)
    return result
