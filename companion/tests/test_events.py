"""One definition per event type: the AddOn's EventTypes.lua and the companion's events.py hold the same types."""
import re
from pathlib import Path

from rambleon.archive import Archive
from rambleon.events import EVENTS, describe, spec
from rambleon.export import carried_over, quest_summary, render_markdown
from rambleon.guide import stretches
from rambleon.luaparse import parse, to_python
from rambleon.model import COUNTER_KEYS, EVENT_TYPES
from rambleon.nights import build_night
from rambleon.normalize import sessions_from_db
from rambleon.publish import export_html

FIXTURES = Path(__file__).parent / "fixtures"
ADDON = Path(__file__).parents[2] / "addon" / "Rambleon"


def fixture_sessions() -> list[dict]:
    return sessions_from_db(to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"])


def test_both_sides_know_the_same_types():
    lua = (ADDON / "EventTypes.lua").read_text()
    table = lua[lua.index("ns.EVENT_TYPES = {"):lua.index("ns.EXTRA_COUNTERS")]
    addon_types = set(re.findall(r"^  ([A-Z_]+) = \{", table, re.M))
    assert addon_types == set(EVENTS) == EVENT_TYPES
    addon_counters = dict(re.findall(r'^  ([A-Z_]+) = \{ counter = "(\w+)"', table, re.M))
    assert addon_counters == {name: et.counter for name, et in EVENTS.items() if et.counter}
    extra = set(re.findall(r'"(\w+)"', lua[lua.index("ns.EXTRA_COUNTERS"):lua.index("function ns.NewCounters")]))
    assert set(addon_counters.values()) | extra == set(COUNTER_KEYS)
    for source in ADDON.glob("*.lua"):
        if source.name != "Chapters.lua":
            assert set(re.findall(r'AddEvent\("([A-Z_]+)"', source.read_text())) <= set(EVENTS), source.name


def test_everything_the_simulated_session_records_is_known_and_readable():
    seen = {ev["type"] for s in fixture_sessions() for ev in s["events"]}
    assert seen == set(EVENTS)                     # the AddOn's script records one of everything
    for name in EVENTS:
        assert describe({"type": name}) and describe({"type": name}) != name


def test_an_unknown_type_is_a_moment_not_a_crash(tmp_path):
    s = fixture_sessions()[0]
    s["events"].insert(3, {"t": s["events"][2]["t"], "type": "FLIGHT_TAKEN", "zone": "Teldrassil", "level": 10})
    assert describe(s["events"][3]) == "Flight taken" and spec("FLIGHT_TAKEN").guide == "active"
    night = build_night([s])
    assert any(ev["type"] == "FLIGHT_TAKEN" for ev in night["events"])
    assert "Flight taken" in render_markdown(night)
    assert "Flight taken" in export_html(night, Archive(tmp_path / "a"), tmp_path / "exports").read_text()
    assert stretches([night])


def test_an_abandoned_quest_is_no_longer_open_or_carried():
    s = fixture_sessions()[0]
    q = quest_summary(s)
    assert "A Troubling Breeze" not in [e.get("title") for e in q["open"]]
    assert any(e["type"] == "QUEST_ABANDONED" and e["title"] == "A Troubling Breeze" for e in s["events"])
    earlier = {"events": [{"type": "QUEST_ACCEPTED", "questID": 7, "title": "Old Errand", "t": 1}]}
    tonight = {"events": [{"type": "QUEST_ABANDONED", "questID": 7, "title": "Old Errand", "t": 2}]}
    assert [ev["questID"] for ev, _ in carried_over([earlier], {"events": []})] == [7]
    assert carried_over([earlier], tonight) == []
