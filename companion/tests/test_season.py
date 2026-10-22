"""The season page: every night of a character read as one. Facts only; a section with nothing to say is absent."""
import copy

from rambleon.season import (UNSAID, build_season, headline_deaths, headline_road, hour_profile, level_times, render_season_html,
                             write_season, zone_times)
from rambleon.nights import nights
from rambleon.pages import season_page_name
from test_memory import three_nights

SLUG = "rambleon-birdsong"


def test_level_times_cut_sessions_at_the_dings():
    sessions = [
        {"startedAt": 1000, "endedAt": 1600, "events": [{"t": 1100, "type": "LEVEL_UP", "level": 11}, {"t": 1500, "type": "LEVEL_UP", "level": 12}]},
        {"startedAt": 5000, "lastSeen": 5300, "events": []},                       # logged out between: nothing counts
    ]
    times, dings = level_times(sessions, 10)
    assert times == {10: 100, 11: 400, 12: 100 + 300} and sorted(dings) == [11, 12]


def test_zone_time_follows_the_events_and_skips_the_logged_out_gap():
    s = {"startedAt": 0, "endedAt": 1000, "events": [
        {"t": 0, "type": "SESSION_START"}, {"t": 10, "type": "ZONE_ENTER", "zone": "A"}, {"t": 110, "type": "QUEST_ACCEPTED", "zone": "A"},
        {"t": 200, "type": "ZONE_ENTER", "zone": "B"}, {"t": 700, "type": "RESUMED", "zone": "B"}, {"t": 800, "type": "ZONE_ENTER", "zone": "A"}]}
    assert zone_times([s]) == {"A": 190 + 200, "B": 100}        # B: from the resume on; what came before the logout is unknown


def test_hour_profile_splits_a_session_across_hours():
    hours = hour_profile([{"startedAt": 3600 * 20 + 1800, "endedAt": 3600 * 22}])   # 20:30 to 22:00 UTC (the tests run in UTC)
    assert hours[20] == 1800 and hours[21] == 3600 and sum(hours) == 5400


def test_the_season_of_three_nights(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    season = build_season(archive, SLUG, exports)
    t = season["totals"]
    assert t["nights"] == 3 and (t["startLevel"], t["endLevel"]) == (10, 12) and t["deaths"] == 3 and t["discoveries"] == 6
    assert [r["level"] for r in season["road"]] == [10, 11, 12]
    assert season["road"][0]["partial"] and season["road"][2]["current"] and season["road"][1]["cause"] == "quest"
    assert season["road"][1]["place"] == "Dolanaar" and season["road"][1]["chapter"] == 1
    assert season["deaths"]["byZone"] == [("Teldrassil", 3)] and season["deaths"]["byCause"] == [("Grell", 3)]
    assert season["enemies"][0] == ("Timberling", 6)
    assert season["zoneTime"][0][0] == "Teldrassil" and sum(s for _, s in season["zoneTime"]) <= t["playedSeconds"] + 3 * 60
    assert [f["label"] for f in season["firsts"]][:3] == ["First crossing", "First discovery", "First home"]
    assert season["people"] == [dict(season["people"][0], name="Moonhoof", nights=3)]
    assert [c["number"] for c in season["chapters"]] == [1, 2, 3] and season["chapters"][0]["title"].startswith("Chapter 1")
    assert "Died 3 times, all in Teldrassil." == headline_deaths(season)
    assert headline_road(season) == f"Level 11 took the longest: {__import__('rambleon.export', fromlist=['duration']).duration(season['road'][1]['seconds'])}."


def test_the_page_hides_what_it_cannot_say(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    page = write_season(archive, exports, SLUG)
    assert page.name == season_page_name(SLUG)
    text = page.read_text()
    assert "the season so far</h1>" in text and "id='road'" in text and "id='deaths'" in text and "id='company'" in text
    assert "Slain by" not in text and "What did it" in text and "Grell" in text
    assert str(tmp_path) not in text
    # A character whose record never said what killed them: the bucket exists but is not drawn as a bar chart of one
    quiet = copy.deepcopy(build_season(archive, SLUG, exports))
    quiet["deaths"]["byCause"] = [(UNSAID, 3)]
    quiet["people"] = []
    quiet["enemies"] = []
    html = render_season_html(quiet, exports)
    assert "What did it" not in html and "id='company'" not in html and "id='enemies'" not in html and "id='chapters'" in html


def test_a_character_with_no_nights_is_an_error(tmp_path):
    archive, exports, *_ = three_nights(tmp_path)
    try:
        build_season(archive, "nobody", exports)
    except ValueError as e:
        assert "nobody" in str(e)
    else:
        raise AssertionError("expected a ValueError")
