"""The season so far: one page per character, read from every night at once.

Where a story page is one evening and the route guide is the road, this is the long view: how long each
level took, what killed the character and where, which enemy fell most often, where the hours went, when
the player tends to play, who they travelled with, and the chapters in a row. Facts only, no AI call: each
section opens with a plain sentence written from its numbers, and a section with nothing to say is left out.
The shape is borrowed from JourneyTracker's recap (skittlenicks, MIT); the rankings and the jokes are not."""
from __future__ import annotations

import html
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from .archive import Archive, atomic_write_bytes
from .events import place
from .export import duration, long_date, money, night_gold
from .guide import death_cause
from .nights import chapter_numbers, nights
from .pages import guide_page_name, index_anchor, page_name, season_page_name, shell, top_nav
from .publish import chapter_title, load_journal, pick_hero, prepare_images

TOP_ENEMIES = 5
TOP_ZONES = 8
TOP_KILLERS = 6
TOP_PEOPLE = 8
UNSAID = "the record doesn't say"      # deaths from before the AddOn knew what did it

FIRSTS = [   # (event type, test, label, text): the first time each happened, in the order they happened
    ("DEATH", lambda ev: True, "First death", lambda ev: place(ev) or ""),
    ("GROUP_JOIN", lambda ev: bool(ev.get("name")), "First companion", lambda ev: ev["name"]),
    ("HEARTH_BOUND", lambda ev: bool(ev.get("name")), "First home", lambda ev: ev["name"]),
    ("INSTANCE_ENTER", lambda ev: bool(ev.get("name")), "First dungeon", lambda ev: ev["name"]),
    ("BOSS_KILL", lambda ev: bool(ev.get("name")), "First boss", lambda ev: ev["name"]),
    ("LOOT", lambda ev: ev.get("quality") == 3, "First rare item", lambda ev: ev.get("name") or ""),
    ("LOOT", lambda ev: ev.get("quality") == 4, "First epic", lambda ev: ev.get("name") or ""),
    ("FIRST_KILL", lambda ev: ev.get("classification") in ("rare", "rareelite"), "First rare slain", lambda ev: ev.get("name") or ""),
    ("FIRST_KILL", lambda ev: ev.get("classification") in ("elite", "worldboss"), "First elite slain", lambda ev: ev.get("name") or ""),
    ("DISCOVERED", lambda ev: bool(ev.get("name")), "First discovery", lambda ev: ev["name"]),
    ("FLIGHT", lambda ev: True, "First flight", lambda ev: f"to {ev['to']}" if ev.get("to") else ""),
    ("BOAT_RIDE", lambda ev: True, "First crossing", lambda ev: f"{ev.get('from')} to {ev.get('to')}"),
    ("ACHIEVEMENT", lambda ev: bool(ev.get("name")), "First achievement", lambda ev: ev["name"]),
    ("NOTE", lambda ev: bool(ev.get("text")), "First note", lambda ev: f"“{ev['text']}”"),
]


# ---------------------------------------------------------------------------------------------------
# The facts

def _spans(archive: Archive, night: dict[str, Any]) -> list[dict[str, Any]]:
    """The night's sessions as the archive holds them (events in order, with their RESUMED marks)."""
    out = []
    for sid in night.get("sessionIds") or [night["id"]]:
        s = archive.load_session(sid)
        if s:
            out.append(s)
    return out or [night]


def _end_of(s: dict[str, Any]) -> int:
    return int(s.get("endedAt") or s.get("lastSeen") or s.get("startedAt") or 0)


def level_times(sessions: list[dict[str, Any]], start_level: int | None) -> tuple[dict[int, int], dict[int, dict[str, Any]]]:
    """Seconds played at each level, and the ding that reached each level, across every session given.
    A session's time is cut at the dings inside it; between sessions nothing counts."""
    dings: dict[int, dict[str, Any]] = {}
    for s in sessions:
        for ev in s.get("events", []):
            if ev.get("type") == "LEVEL_UP" and isinstance(ev.get("level"), int) and ev["level"] not in dings:
                dings[ev["level"]] = ev
    cuts = sorted((ev["t"], lv) for lv, ev in dings.items())
    times: dict[int, int] = defaultdict(int)
    for s in sessions:
        a, b = int(s.get("startedAt") or 0), _end_of(s)
        if b <= a:
            continue
        edges = [a] + [t for t, _ in cuts if a < t < b] + [b]
        for lo, hi in zip(edges, edges[1:]):
            level = start_level
            for t, lv in cuts:
                if t <= lo:
                    level = lv
            if level is not None:
                times[level] += hi - lo
    return dict(times), dings


def zone_times(sessions: list[dict[str, Any]]) -> dict[str, int]:
    """Seconds in each zone: every event knows its zone, so the time to the next event is that zone's.
    The gap before a RESUMED mark was spent logged out and counts for nothing."""
    times: dict[str, int] = defaultdict(int)
    for s in sessions:
        evs = [ev for ev in s.get("events", []) if isinstance(ev.get("t"), (int, float))]
        end = _end_of(s)
        for ev, nxt in zip(evs, evs[1:] + [None]):
            zone = ev.get("zone")
            if not zone or (nxt is not None and nxt.get("type") == "RESUMED"):
                continue
            until = nxt["t"] if nxt is not None else end
            if until > ev["t"]:
                times[zone] += int(until - ev["t"])
    return dict(times)


def hour_profile(sessions: list[dict[str, Any]]) -> list[int]:
    """Seconds played in each hour of the day (local time), 24 buckets."""
    buckets = [0] * 24
    for s in sessions:
        a, b = int(s.get("startedAt") or 0), _end_of(s)
        t = a
        while t < b:
            hour = datetime.fromtimestamp(t).hour
            next_hour = (t // 3600 + 1) * 3600
            step = min(next_hour, b) - t
            buckets[hour] += step
            t += step
    return buckets


def _firsts(nights_: list[dict[str, Any]], numbers: dict[str, int]) -> list[dict[str, Any]]:
    found: dict[str, dict[str, Any]] = {}
    for night in nights_:
        for ev in night.get("events", []):
            for type_, test, label, text in FIRSTS:
                if label in found or ev.get("type") != type_:
                    continue
                try:
                    ok = test(ev)
                except (TypeError, KeyError):
                    ok = False
                if ok:
                    found[label] = {"label": label, "text": text(ev), "level": ev.get("level"), "t": ev.get("t"),
                                    "place": place(ev), "chapter": numbers.get(night["id"]), "date": night.get("startedAt")}
    return sorted(found.values(), key=lambda f: f["t"] or 0)


def _people(nights_: list[dict[str, Any]], numbers: dict[str, int]) -> list[dict[str, Any]]:
    people: dict[str, dict[str, Any]] = {}
    for night in nights_:
        for p in night.get("people", []):
            name = p.get("name")
            if not name:
                continue
            row = people.setdefault(name, {"name": name, "class": p.get("class"), "seconds": 0, "nights": 0,
                                           "firstMet": night.get("startedAt"), "lastSeen": night.get("startedAt"),
                                           "firstChapter": numbers.get(night["id"])})
            row["seconds"] += int(p.get("seconds") or 0)
            row["nights"] += 1
            row["lastSeen"] = night.get("startedAt")
            row["class"] = row["class"] or p.get("class")
    return sorted(people.values(), key=lambda r: (-r["seconds"], r["name"]))


def build_season(archive: Archive, slug: str, exports_dir: Path) -> dict[str, Any]:
    """Everything the page says, as data. Pure apart from reading the archive and the journal sidecars."""
    own = nights(archive, slug)
    if not own:
        raise ValueError(f"no nights archived for {slug}")
    numbers = chapter_numbers(own)
    sessions = [s for night in own for s in _spans(archive, night)]
    first, last = own[0], own[-1]
    character = dict(last.get("character", {}))
    start_level = first.get("character", {}).get("startLevel")
    end_level = max((n.get("character", {}).get("endLevel") or 0 for n in own), default=None) or character.get("endLevel")
    character["startLevel"], character["endLevel"] = start_level, end_level

    times, dings = level_times(sessions, start_level)
    levels = sorted(set(times) | set(dings))
    road = []
    for lv in levels:
        ding = dings.get(lv)
        night_of = next((n for n in own if ding and any(ev is ding or (ev.get("t") == ding.get("t") and ev.get("type") == "LEVEL_UP")
                                                       for ev in n.get("events", []))), None)
        road.append({"level": lv, "seconds": times.get(lv, 0), "reachedAt": ding.get("t") if ding else None,
                     "place": place(ding) if ding else None, "cause": ding.get("cause") if ding else None,
                     "chapter": numbers.get(night_of["id"]) if night_of else None,
                     "partial": lv == start_level and lv not in dings,      # tracking began part-way through it
                     "current": lv == end_level})
    complete = [r for r in road if not r["partial"] and not r["current"] and r["seconds"] > 0]
    slowest = max(complete, key=lambda r: r["seconds"]) if complete else None
    fastest = min(complete, key=lambda r: r["seconds"]) if len(complete) > 1 else None

    by_zone: dict[str, int] = defaultdict(int)
    by_cause: dict[str, int] = defaultdict(int)
    deaths_per_night = []
    for night in own:
        n = 0
        for ev in night.get("events", []):
            if ev.get("type") == "DEATH":
                n += 1
                by_zone[ev.get("zone") or place(ev) or "somewhere"] += 1
                by_cause[death_cause(ev) or UNSAID] += 1
        deaths_per_night.append(n)
    streak, best = 0, 0
    for n in deaths_per_night:
        streak = streak + 1 if n == 0 else 0
        best = max(best, streak)

    kills: dict[str, int] = defaultdict(int)
    for night in own:
        for name, info in (night.get("kills") or {}).items():
            kills[name] += int(info.get("count") or 0)

    zone_time = zone_times(sessions)
    hours = hour_profile(sessions)
    weekdays = [0] * 7
    for night in own:
        if night.get("startedAt"):
            weekdays[datetime.fromtimestamp(night["startedAt"]).weekday()] += 1

    chapters = []
    for night in own:
        journal = load_journal(exports_dir, night["id"])
        page = page_name(night)
        hero = pick_hero(prepare_images(night, exports_dir / "html" / page.replace(".html", "")))
        chapters.append({"id": night["id"], "number": numbers[night["id"]], "title": chapter_title(night, journal, numbers[night["id"]]),
                         "date": night.get("startedAt"), "playedSeconds": night.get("playedSeconds") or 0, "page": page,
                         "hero": hero, "deaths": night["counters"].get("deaths", 0), "levels": night["counters"].get("levelsGained", 0)})

    gold = [g for g in (night_gold(n) for n in own) if g is not None]
    played = sum(n.get("playedSeconds") or 0 for n in own)
    cnt = lambda key: sum(n.get("counters", {}).get(key) or 0 for n in own)
    return {
        "slug": slug, "displayName": character.get("displayName") or slug, "character": character,
        "nightIds": [n["id"] for n in own], "open": any(n.get("state") != "ended" for n in own),
        "firstAt": first.get("startedAt"), "lastAt": last.get("startedAt"),
        "totals": {"nights": len(own), "playedSeconds": played, "startLevel": start_level, "endLevel": end_level,
                   "quests": cnt("questsCompleted"), "kills": cnt("kills"), "deaths": cnt("deaths"), "loot": cnt("loot"),
                   "places": len({z.get("zone") for n in own for z in n.get("zones", []) if z.get("zone")}),
                   "discoveries": cnt("discoveries"), "spells": cnt("spellsLearned"), "notes": cnt("notes"),
                   "pictures": sum(len(n.get("screenshots") or []) for n in own), "xp": cnt("xpGained"),
                   "gold": sum(gold) if gold else None},
        "road": road, "slowest": slowest, "fastest": fastest,
        "deaths": {"total": cnt("deaths"), "byZone": sorted(by_zone.items(), key=lambda kv: (-kv[1], kv[0])),
                   "byCause": sorted(by_cause.items(), key=lambda kv: (-kv[1], kv[0] == UNSAID, kv[0])),
                   "longestStreak": best, "perNight": deaths_per_night},
        "enemies": sorted(kills.items(), key=lambda kv: (-kv[1], kv[0]))[:TOP_ENEMIES],
        "zoneTime": sorted(zone_time.items(), key=lambda kv: (-kv[1], kv[0])),
        "hours": hours, "weekdays": weekdays,
        "firsts": _firsts(own, numbers),
        "people": _people(own, numbers),
        "chapters": chapters,
    }


# ---------------------------------------------------------------------------------------------------
# The sentences

def _n(n: int, noun: str, plural: str | None = None) -> str:
    return f"{n:,} {noun if n == 1 else (plural or noun + 's')}"


def _clock_hour(hour: int) -> str:
    return datetime(2000, 1, 1, hour).strftime("%-I %p")


def headline_hero(season: dict[str, Any]) -> str:
    t = season["totals"]
    levels = (f"Level {t['startLevel']} to {t['endLevel']}" if t["startLevel"] and t["endLevel"] and t["endLevel"] != t["startLevel"]
              else f"Level {t['endLevel']}" if t["endLevel"] else "")
    span = long_date(season["firstAt"]) if t["nights"] == 1 else f"{long_date(season['firstAt'])} to {long_date(season['lastAt'])}"
    return ", ".join(x for x in (levels, f"{_n(t['nights'], 'night')}", f"{duration(t['playedSeconds'])} played", span) if x) + "."


def headline_road(season: dict[str, Any]) -> str:
    slow, fast = season["slowest"], season["fastest"]
    if not slow:
        return "Every level so far is still under way."
    text = f"Level {slow['level']} took the longest: {duration(slow['seconds'])}."
    if fast and fast is not slow:
        text += f" Level {fast['level']} went by in {duration(fast['seconds'])}."
    return text


def headline_deaths(season: dict[str, Any]) -> str:
    d = season["deaths"]
    if d["total"] == 1:
        where = d["byZone"][0][0] if d["byZone"] else None
        return f"Died once{', in ' + where if where else ''}."
    zone, n = d["byZone"][0] if d["byZone"] else (None, 0)
    text = f"Died {_n(d['total'], 'time')}"
    if zone and n and len(d["byZone"]) > 1:
        text += f", {n} of them in {zone}"
    elif zone:
        text += f", all in {zone}" if d["total"] > 1 else ""
    return text + "."


def headline_enemies(season: dict[str, Any]) -> str:
    name, n = season["enemies"][0]
    return f"{_n(season['totals']['kills'], 'enemy', 'enemies')} slain; {name} most often, {_n(n, 'time')}."


def headline_zones(season: dict[str, Any]) -> str:
    zone, secs = season["zoneTime"][0]
    return f"Lingered longest in {zone}: {duration(secs)} of {duration(season['totals']['playedSeconds'])}."


def headline_hours(season: dict[str, Any]) -> str:
    hours = season["hours"]
    busiest = max(range(24), key=lambda h: hours[h])
    text = f"Most often around {_clock_hour(busiest)}"
    days = season["weekdays"]
    if sum(days) >= 3 and max(days) > 1:
        names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        text += f"; {names[max(range(7), key=lambda i: days[i])]}s most of all"
    return text + "."


def headline_people(season: dict[str, Any]) -> str:
    top = season["people"][0]
    nights_ = _n(top["nights"], "night")
    return f"Travelled with {_n(len(season['people']), 'person', 'people')}; {top['name']} the longest, {duration(top['seconds'])} over {nights_}."


# ---------------------------------------------------------------------------------------------------
# The page

def _bars(rows: list[tuple[str, int | str, int]], fmt=lambda v: f"{v:,}") -> str:
    """Horizontal bars: (label, value, width) with the widest at 100%."""
    top = max((w for _, _, w in rows), default=0) or 1
    return "<div class='bars'>" + "".join(
        f"<div class='bar'><span class='l'>{html.escape(str(label))}</span><span class='b'><i style='width:{100 * w / top:.1f}%'></i></span>"
        f"<span class='v'>{html.escape(fmt(v))}</span></div>" for label, v, w in rows) + "</div>"


def _road_svg(road: list[dict[str, Any]], slowest: dict[str, Any] | None, fastest: dict[str, Any] | None) -> str:
    if not road:
        return ""
    w, h, gap = 24, 120, 6
    top = max((r["seconds"] for r in road), default=0) or 1
    width = len(road) * (w + gap) + gap
    parts = [f"<svg class='road' viewBox='0 0 {width} {h + 28}' role='img' aria-label='Time spent at each level'>"]
    for i, r in enumerate(road):
        x = gap + i * (w + gap)
        bar_h = max(2, round(h * r["seconds"] / top)) if r["seconds"] else 2
        cls = "cur" if r["current"] else "part" if r["partial"] else "slow" if slowest and r is slowest else "fast" if fastest and r is fastest else ""
        title = f"Level {r['level']}: {duration(r['seconds'])}" + (" so far" if r["current"] else " (from when tracking began)" if r["partial"] else "")
        if r.get("place"):
            title += f" · reached in {r['place']}"
        parts.append(f"<rect class='{cls}' x='{x}' y='{h - bar_h}' width='{w}' height='{bar_h}'><title>{html.escape(title)}</title></rect>")
        parts.append(f"<text x='{x + w / 2}' y='{h + 18}' text-anchor='middle'>{r['level']}</text>")
    parts.append("</svg>")
    return "".join(parts)


def _hour_strip(hours: list[int]) -> str:
    top = max(hours) or 1
    cells = "".join(f"<i style='opacity:{0.15 + 0.85 * v / top:.2f}' title='{_clock_hour(hh)}: {duration(v)}'></i>" if v else
                    f"<i class='none' title='{_clock_hour(hh)}'></i>" for hh, v in enumerate(hours))
    return (f"<div class='hours'>{cells}</div><div class='hours-axis'><span>midnight</span><span>6 AM</span><span>noon</span>"
            "<span>6 PM</span><span>midnight</span></div>")


def _section(id_: str, title: str, headline: str, body: str) -> str:
    return (f"<section class='season' id='{id_}'><h2>{html.escape(title)}</h2><p class='headline'>{html.escape(headline)}</p>"
            f"{body}</section>")


def render_season_html(season: dict[str, Any], exports_dir: Path, siblings: set[str] | None = None) -> str:
    t, c = season["totals"], season["character"]
    name = season["displayName"]
    who = " · ".join(x for x in (f"{c.get('race') or ''} {c.get('class') or ''}".strip(), c.get("faction")) if x)
    nav = top_nav(("All chapters", index_anchor(season["slug"])),
                  *([("Route guide", guide_page_name(season["slug"]))] if (exports_dir / "html" / guide_page_name(season["slug"])).exists()
                    and (siblings is None or guide_page_name(season["slug"]) in siblings) else []),
                  ("About Rambleon", "../"))
    sections: list[str] = []

    # The road
    if season["road"]:
        body = _road_svg(season["road"], season["slowest"], season["fastest"])
        rows = [r for r in season["road"] if r["reachedAt"]]
        if rows:
            body += "<ul class='dings'>" + "".join(
                f"<li><b>Level {r['level']}</b> {html.escape(long_date(r['reachedAt']))}"
                + (f", {html.escape(r['place'])}" if r.get("place") else "")
                + (f" <span class='faint'>({ {'quest': 'a quest turned in', 'kill': 'a kill', 'explore': 'a discovery'}[r['cause']] })</span>" if r.get("cause") in ("quest", "kill", "explore") else "")
                + (f" · Chapter {r['chapter']}" if r.get("chapter") else "") + "</li>" for r in rows) + "</ul>"
        sections.append(_section("road", "The road", headline_road(season), body))

    # Firsts
    if season["firsts"]:
        chips = "".join(f"<li><span class='lv'>Level {f['level']}</span><b>{html.escape(f['label'])}</b>"
                        + (f"<span class='t'>{html.escape(f['text'])}</span>" if f["text"] else "")
                        + (f"<span class='faint'>Chapter {f['chapter']}</span>" if f.get("chapter") else "") + "</li>"
                        for f in season["firsts"])
        sections.append(_section("firsts", "Firsts", f"{_n(len(season['firsts']), 'first time')}, in the order they came.", f"<ul class='chips'>{chips}</ul>"))

    # Deaths
    d = season["deaths"]
    if d["total"]:
        body = ""
        if d["byZone"]:
            body += "<h3>Where</h3>" + _bars([(z, n, n) for z, n in d["byZone"][:TOP_ZONES]])
        causes = [(k, n, n) for k, n in d["byCause"][:TOP_KILLERS]]
        if causes and not (len(causes) == 1 and causes[0][0] == UNSAID):
            body += "<h3>What did it</h3>" + _bars(causes)
        if d["longestStreak"] >= 2:
            body += f"<p class='faint'>Longest run of nights without one: {d['longestStreak']}.</p>"
        sections.append(_section("deaths", "Deaths", headline_deaths(season), body))

    # Enemies
    if season["enemies"]:
        sections.append(_section("enemies", "Enemies", headline_enemies(season), _bars([(n, k, k) for n, k in season["enemies"]])))

    # Where the time went
    if season["zoneTime"]:
        sections.append(_section("places", "Where the time went", headline_zones(season),
                                 _bars([(z, s, s) for z, s in season["zoneTime"][:TOP_ZONES]], fmt=duration)))

    # When you played
    if sum(season["hours"]):
        sections.append(_section("when", "When you played", headline_hours(season), _hour_strip(season["hours"])))

    # Company
    if season["people"]:
        rows = "".join(f"<tr><td>{html.escape(p['name'])}{' <span class=faint>(' + html.escape(p['class']) + ')</span>' if p.get('class') else ''}</td>"
                       f"<td>{html.escape(duration(p['seconds']))}</td><td>{p['nights']}</td>"
                       f"<td>{html.escape(long_date(p['firstMet']))}{' · Chapter ' + str(p['firstChapter']) if p.get('firstChapter') else ''}</td></tr>"
                       for p in season["people"][:TOP_PEOPLE])
        sections.append(_section("company", "Company", headline_people(season),
                                 f"<table class='people'><thead><tr><th>Who</th><th>Together</th><th>Nights</th><th>First met</th></tr></thead><tbody>{rows}</tbody></table>"))

    # Chapters
    cards = []
    for ch in season["chapters"]:
        thumb = f"<img class='thumb' src='{html.escape(ch['hero']['src'])}' alt=''>" if ch.get("hero") else "<span class='noshot'></span>"
        heading = ch["title"].split(" — ", 1)[1] if " — " in ch["title"] else ch["title"]
        facts = " · ".join(x for x in (long_date(ch["date"]), duration(ch["playedSeconds"]),
                                       _n(ch["levels"], "level") if ch["levels"] else "", _n(ch["deaths"], "death") if ch["deaths"] else "") if x)
        inner = (f"{thumb}<span class='body'><span class='n'>Chapter {ch['number']}</span><span class='t'>{html.escape(heading)}</span>"
                 f"<span class='m'>{html.escape(facts)}</span></span>")
        if siblings is None or ch["page"] in siblings:
            cards.append(f"<li><a class='card' href='{html.escape(ch['page'])}'>{inner}</a></li>")
        else:
            cards.append(f"<li><span class='card'>{inner}</span></li>")
    sections.append(_section("chapters", "Chapters", f"{_n(len(cards), 'chapter')}, oldest first.", "<ul class='chapters'>" + "".join(cards) + "</ul>"))

    stats = [("Nights", t["nights"]), ("Quests", t["quests"]), ("Enemies slain", t["kills"]), ("Deaths", t["deaths"]),
             ("Places", t["places"]), ("Loot", t["loot"])]
    if t["discoveries"]:
        stats.append(("Discoveries", t["discoveries"]))
    if t["gold"] is not None:
        stats.append(("Gold", money(t["gold"])))
    stats += [("Notes", t["notes"]), ("Pictures", t["pictures"])]
    hero = next((ch["hero"] for ch in reversed(season["chapters"]) if ch.get("hero")), None)
    parts = [f"<h1>{html.escape(name)}: the season so far</h1>",
             f"<div class='meta'>{html.escape(who)}{' · ' if who else ''}{html.escape(headline_hero(season))}"
             + (" · a night is still in progress" if season["open"] else "") + "</div>",
             "<div class='jump'>" + "".join(f"<a href='#{s.split(chr(39))[1]}'>{html.escape(s.split('<h2>')[1].split('</h2>')[0])}</a>" for s in sections) + "</div>"]
    if hero:
        parts.append(f"<figure class='hero'><img src='{html.escape(hero['src'])}' alt='{html.escape(hero['caption'])}'>"
                     f"<figcaption>{html.escape(hero['caption'])}</figcaption></figure>")
    parts.append("<div class='stats'>" + "".join(f"<div class='stat'><b>{html.escape(str(v))}</b><span>{html.escape(k)}</span></div>"
                                                 for k, v in stats if v or v == 0) + "</div>")
    parts += sections
    parts.append("<a class='totop' href='#top'>↑ Back to top</a>")
    return shell(f"{html.escape(name)} — the season so far", nav, "\n".join(parts),
                 f"Recorded by Rambleon · {_n(t['nights'], 'night')} · nothing here was written by anyone but the numbers",
                 body_attrs=" id='top' class='season-page'", extra="season")


def write_season(archive: Archive, exports_dir: Path, slug: str, siblings: set[str] | None = None) -> Path:
    """Build the facts and write exports/html/season-<slug>.html."""
    season = build_season(archive, slug, exports_dir)
    out = exports_dir / "html" / season_page_name(slug)
    atomic_write_bytes(out, render_season_html(season, exports_dir, siblings).encode("utf-8"))
    return out
