"""The route guide: nights cut into zone stretches, facts always, prose per stretch when the writer ran."""
import json

import pytest

from rambleon import guide as guide_mod
from rambleon.archive import atomic_write_json
from rambleon.guide import (build_guide, build_guide_prompt, export_guide_html, load_mode, needs_prose, render_guide_markdown,
                            sidecar_path, split_prose, stretches, write_guide)
from rambleon.publish import _page_name
from test_memory import three_nights

SLUG = "rambleon-birdsong"


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """No rambleon.local.toml and no env from this Mac may leak into the tests."""
    monkeypatch.setattr("rambleon.config.find_repo_root", lambda: tmp_path)
    monkeypatch.delenv("RAMBLEON_GUIDE_MODE", raising=False)
    monkeypatch.delenv("RAMBLEON_VOICE", raising=False)


def test_three_nights_in_one_zone_are_one_stretch(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    g = build_guide(archive, SLUG, exports)
    assert g["title"] == "How Rambleon Birdsong leveled 10–12 on Forever"
    assert g["nightCount"] == 3 and g["nightIds"] == [n1["id"], n2["id"], n3["id"]]
    assert len(g["chapters"]) == 1
    ch = g["chapters"][0]
    assert ch["zone"] == "Teldrassil" and ch["subzones"] == ["Shadowglen", "Dolanaar"]
    assert ch["passing"] == ["Darkshore"]                       # the two-second Auberdine hop folded in
    assert ch["nights"] == [1, 2, 3]
    assert (ch["startLevel"], ch["endLevel"]) == (10, 12)
    assert [u["level"] for u in ch["levelUps"]] == [11, 12]
    assert [e["questID"] for e in ch["completed"]] == [123]     # once, not three times
    assert [e["questID"] for e in ch["accepted"]] == [123, 124]
    assert ch["deaths"] == 3 and ch["deathPlaces"] == ["Dolanaar"]
    assert len(ch["notes"]) == 3 and ch["notes"][0][0] == 1 and ch["notes"][2][0] == 3
    assert ch["firstKills"] == ["Timberling", "Grell"]
    assert [(e["type"], e["itemID"]) for e in ch["loot"]] == [("LOOT", 2044), ("LOOT", 2140), ("EQUIP", 2140)]
    assert ch["people"] == ["Moonhoof"] and ch["instances"] == ["Ragefire Chasm"]


def test_a_real_zone_change_starts_a_new_stretch(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    moved = dict(n3, events=[dict(e, zone="Darkshore", subzone="Auberdine") if e.get("zone") else e for e in n3["events"]])
    chapters = stretches([n1, n2, moved])
    assert [c["number"] for c in chapters] == [1, 2]
    assert chapters[0]["zone"] == "Teldrassil" and chapters[0]["nights"] == [1, 2]
    assert chapters[1]["zone"] == "Darkshore" and chapters[1]["nights"] == [3] and chapters[1]["subzones"] == ["Auberdine"]
    assert [e["questID"] for e in chapters[0]["completed"]] == [123]
    assert chapters[1]["completed"] == []                          # turned in before: not again
    assert [e["questID"] for e in chapters[1]["accepted"]] == [123, 124]


def _night(events):
    return {"id": "night-x", "events": events, "screenshots": [], "character": {"slug": "x"}}


def _ev(t, type_, zone, **extra):
    return {"t": t, "type": type_, "zone": zone, "level": 5, **extra}


def test_fold_rules():
    a = [_ev(0, "QUEST_COMPLETED", "A", questID=1, title="One")]
    back = [_ev(300, "QUEST_ACCEPTED", "A", questID=2, title="Two")]
    c = [_ev(400, "QUEST_COMPLETED", "C", questID=3, title="Three")]

    hop = [_ev(100, "ZONE_ENTER", "B"), _ev(220, "ZONE_ENTER", "B")]          # two minutes, nothing done
    assert [ch["zone"] for ch in stretches([_night(a + hop + back + c)])] == ["A", "C"]
    assert stretches([_night(a + hop + back + c)])[0]["passing"] == ["B"]

    death = [_ev(100, "ZONE_ENTER", "B"), _ev(150, "DEATH", "B")]             # an anchor: stands alone however short
    assert [ch["zone"] for ch in stretches([_night(a + death + back + c)])] == ["A", "B", "C"]

    idle = [_ev(100, "ZONE_ENTER", "B"), _ev(100 + 25 * 60, "ZONE_ENTER", "B")]   # long but empty: folds
    assert [ch["zone"] for ch in stretches([_night(a + idle + [dict(e, t=e["t"] + 1600) for e in back + c])])] == ["A", "C"]

    busy = [_ev(100, "QUEST_ACCEPTED", "B", questID=9, title="Nine"), _ev(100 + 25 * 60, "FIRST_KILL", "B", name="Boar")]
    assert [ch["zone"] for ch in stretches([_night(a + busy + [dict(e, t=e["t"] + 1600) for e in back + c])])] == ["A", "B", "C"]

    assert [ch["zone"] for ch in stretches([_night(hop)])] == ["B"]        # nothing stood alone: one stretch anyway


def test_markdown_layout(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    text = render_guide_markdown(build_guide(archive, SLUG, exports))
    assert text.startswith("# How Rambleon Birdsong leveled 10–12 on Forever\n")
    assert "Not the best route; her route." in text                          # the fixture character is recorded female
    assert "## 1. Teldrassil, level 10–12" in text
    assert "Shadowglen · Dolanaar" in text and "Auberdine" not in text.split("## 1.")[1]
    assert "From Chapters 1, 2 and 3 (" in text and "Passing through Darkshore" in text
    assert "**Picked up:** The Emerald Dreamcatcher, Precious Waters" in text
    assert "**Turned in:** The Emerald Dreamcatcher (Dolanaar, level 10)" in text
    assert "**Reached:** level 11 (Dolanaar), level 12 (Dolanaar)" in text
    assert "**Loot worth keeping:** Sturdy Bow (Uncommon), Arcane Staff ×2 (Rare), equipped Arcane Staff (Rare)" in text
    assert "**Deaths:** 3 (Dolanaar)" in text
    assert '- "this cave is extremely cursed" (Chapter 1)' in text
    assert str(tmp_path) not in text


def test_write_guide_without_ai_and_modes(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    result = write_guide(archive, exports, SLUG, use_ai=False, log=lambda m: None)
    assert result["prose"] is None and not sidecar_path(exports, SLUG, "route").exists()
    assert result["markdown"] == exports / "markdown" / "guide-rambleon-birdsong.md" and result["markdown"].exists()
    assert result["html"] == exports / "html" / "guide-rambleon-birdsong.html" and result["html"].exists()
    prompt = result["prompt"].read_text()
    assert result["prompt"].name == "guide-rambleon-birdsong-route-prompt.md"
    assert "## 1. Teldrassil, level 10–12" in prompt and "- Gender: female (use matching pronouns)" in prompt
    assert "Rambleon Birdsong (she/her)" in prompt and "from level\n10 to level 12 over 3 nights" in prompt
    assert "{voice}" not in prompt and "{name}" not in prompt and "{number}" in prompt   # {number} is the writer's template
    assert "Player notes (verbatim" in prompt and "this cave is extremely cursed" in prompt

    season = write_guide(archive, exports, SLUG, use_ai=False, mode="season", log=lambda m: None)
    assert season["prompt"].name == "guide-rambleon-birdsong-season-prompt.md"
    assert season["html"].name == "guide-rambleon-birdsong-season.html"
    assert "the story so far" in season["prompt"].read_text()

    mine = tmp_path / "mine.md"
    mine.write_text("Write {name} as a list.\n{voice}\n")
    custom = write_guide(archive, exports, SLUG, use_ai=False, mode=str(mine), log=lambda m: None)
    assert custom["prompt"].name == "guide-rambleon-birdsong-mine-prompt.md"
    assert custom["prompt"].read_text().startswith("Write Rambleon Birdsong as a list.\n")

    with pytest.raises(ValueError) as e:
        load_mode("nope")
    assert "route" in str(e.value) and "season" in str(e.value)


def test_config_and_env_pick_the_default_mode(tmp_path, monkeypatch):
    assert guide_mod.default_mode() == "route"
    (tmp_path / "rambleon.local.toml").write_text('[guide]\nmode = "season"\n')
    assert guide_mod.default_mode() == "season"
    assert guide_mod.guide_page_name(SLUG) == "guide-rambleon-birdsong.html"            # the default owns the linked page
    assert guide_mod.guide_page_name(SLUG, "route") == "guide-rambleon-birdsong-route.html"
    monkeypatch.setenv("RAMBLEON_GUIDE_MODE", "route")
    assert guide_mod.default_mode() == "route"


def test_split_prose_and_page(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    intro, sections = split_prose("# A title the writer added\n\nIntro.\n\n## 1. Teldrassil, level 10–12\n\nHe walked.\n\nFar.\n\n## 9. Bogus\n\nDropped.")
    assert intro == "Intro." and sections == {1: "He walked.\n\nFar.", 9: "Dropped."}
    assert split_prose("Only an intro.") == ("Only an intro.", {})

    g = build_guide(archive, SLUG, exports)
    sidecar = {"slug": SLUG, "mode": "route", "nights": list(g["nightIds"]), "chapters": 1,
               "prose": "Intro.\n\n## 1. Teldrassil, level 10–12\n\nHe walked.\n\n## 9. Bogus\n\nDropped."}
    page = export_guide_html(g, sidecar, exports, "route").read_text()
    assert "<section class='stretch' id='ch-1'>" in page and "<p>He walked.</p>" in page and "Dropped." not in page
    assert "<p class='intro'>Intro.</p>" in page
    assert page.count("<li><a href='#ch-") == 1 and "<small>Level 10–12</small>" in page
    assert f"href='{_page_name(n1)}'" in page and f"href='{_page_name(n3)}'" in page
    assert "<dt>Turned in</dt><dd>The Emerald Dreamcatcher (Dolanaar, level 10)</dd>" in page
    assert "this cave is extremely cursed" in page and "retold through" not in page
    assert "<a href='index.html#rambleon-birdsong'>All chapters</a>" in page

    lonely = export_guide_html(g, sidecar, exports, "route", siblings=set()).read_text()
    assert f"href='{_page_name(n1)}'" not in lonely and "Chapter 1" in lonely

    stale = dict(sidecar, nights=[n1["id"], n2["id"]])
    assert needs_prose(g, stale) and not needs_prose(g, sidecar) and needs_prose(g, None)
    assert "prose retold through Chapter 2" in export_guide_html(g, stale, exports, "route").read_text()


def test_prose_is_written_only_when_a_night_is_new(tmp_path, monkeypatch):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    calls = []
    monkeypatch.setattr(guide_mod, "claude_available", lambda: "/usr/bin/claude")
    monkeypatch.setattr(guide_mod, "run_claude", lambda prompt, model: calls.append(model) or
                        ("Intro.\n\n## 1. Teldrassil, level 10–12\n\nShe walked.", "ok"))
    g = build_guide(archive, SLUG, exports)
    atomic_write_json(sidecar_path(exports, SLUG, "route"), {"nights": list(g["nightIds"]), "prose": "Old.\n\n## 1. T\n\nOld prose."})
    r = write_guide(archive, exports, SLUG, only_if_new=True, log=lambda m: None)
    assert calls == [] and r["prose"] is None and "Old prose." in r["html"].read_text()

    atomic_write_json(sidecar_path(exports, SLUG, "route"), {"nights": [n1["id"], n2["id"]], "prose": "Old."})
    r = write_guide(archive, exports, SLUG, only_if_new=True, model="sonnet", log=lambda m: None)
    assert calls == ["sonnet"] and r["prose"] == exports / "markdown" / "guide-rambleon-birdsong-route-prose.md"
    side = json.loads(sidecar_path(exports, SLUG, "route").read_text())
    assert side["nights"] == g["nightIds"] and side["mode"] == "route" and side["chapters"] == 1
    assert "She walked." in r["html"].read_text() and "She walked." in r["prose"].read_text()

    write_guide(archive, exports, SLUG, log=lambda m: None)              # no only_if_new: always rewrites
    assert calls == ["sonnet", "sonnet"]
    write_guide(archive, exports, SLUG, use_ai=False, log=lambda m: None)   # facts only, prose kept
    assert calls == ["sonnet", "sonnet"] and "She walked." in (exports / "html" / "guide-rambleon-birdsong.html").read_text()


def test_prompt_placeholders_and_open_night(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    g = build_guide(archive, SLUG, exports)
    g["open"] = True
    prompt = build_guide_prompt(g, "Mode for {name}, {pronouns}, {startLevel}-{endLevel}, {nights}. {voice}", "field-journal")
    assert prompt.startswith("Mode for Rambleon Birdsong, she/her, 10-12, 3 nights. ")
    assert "still in progress" in prompt
    assert "captured as last seen" in render_guide_markdown(g)
