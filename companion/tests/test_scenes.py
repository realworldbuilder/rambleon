"""The roleplay: CHAT lines become scenes; scenes reach the log, the prompt and the page; noise does not."""
from pathlib import Path

from rambleon.archive import Archive
from rambleon.events import describe
from rambleon.export import night_stats, render_markdown
from rambleon.luaparse import parse, to_python
from rambleon.nights import build_night
from rambleon.normalize import sessions_from_db
from rambleon.publish import export_html
from rambleon.scenes import PROMPT_SCENE_LINES, SCENE_GAP, marker, render_prompt, scenes, title
from rambleon.summarize import build_prompt

FIXTURES = Path(__file__).parent / "fixtures"


def fixture_night() -> dict:
    sessions = sessions_from_db(to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"])
    return build_night(sessions)


def line(t: int, speaker: str, text: str, **extra) -> dict:
    return {"t": t, "type": "CHAT", "channel": "say", "speaker": speaker, "text": text, "zone": "Elwynn Forest",
            "subzone": "Goldshire", "level": 12, **extra}


def session_of(events: list[dict], people: tuple[str, ...] = ()) -> dict:
    return {"id": "s", "events": events, "people": [{"name": p} for p in people], "counters": {"rpLines": len(events)},
            "character": {"displayName": "Rambleon Birdsong", "name": "Rambleon", "slug": "rambleon-birdsong"}}


def test_the_scripted_evening_has_one_scene_the_player_was_part_of():
    night = fixture_night()
    found = scenes(night)
    assert len(found) == 1
    sc = found[0]
    assert sc.own and sc.others == ["Cassidy", "Wes"] and sc.speakers == ["Cassidy", "Rambleon", "Wes"]
    assert title(sc) == "A scene in Dolanaar with Cassidy and Wes"
    assert marker(sc) == "A scene in Dolanaar with Cassidy and Wes (7 lines)"
    lines = [describe(ev) for ev in sc.lines]
    assert lines[0] == 'Cassidy: "Well met, hunter."' and "Cassidy bows low." in lines and 'Wes yells: "To the lake!"' in lines
    assert 'Cassidy (party): "pull when ready"' in lines
    assert night_stats(night)["rpLines"] == 7 and night_stats(night)["scenes"] == 1


def test_who_is_worth_telling():
    me = [line(100, "Rambleon", "Evening.", self=True)]
    assert len(scenes(session_of(me))) == 1 and title(scenes(session_of(me))[0]) == "A scene in Goldshire, alone"
    stranger = [line(100, "Bob", "lfg deadmines")]
    assert scenes(session_of(stranger)) == []
    companion = [line(100, "Cassidy", "one more run?")]
    assert len(scenes(session_of(companion, people=("Cassidy",)))) == 1
    chatter = [line(100, "Bob", "lfg"), line(110, "Bob", "lfg dm"), line(120, "Bob", "LFG DM pst")]
    assert scenes(session_of(chatter)) == []                       # three lines, one voice: noise
    talk = [line(100, "Bob", "Well met."), line(110, "Ann", "And you."), line(120, "Bob", "Where to?")]
    assert title(scenes(session_of(talk))[0]) == "Overheard in Goldshire: Bob and Ann"
    ooc = [line(100, "Bob", "((anyone?))"), line(110, "Ann", "((here))"), line(120, "Bob", "((ok))", ooc=True)]
    for ev in ooc:
        ev["ooc"] = True
    assert scenes(session_of(ooc)) == []                           # out of character does not make a scene


def test_silence_and_a_new_zone_end_a_scene():
    evs = [line(100, "Rambleon", "One.", self=True), line(100 + SCENE_GAP, "Rambleon", "Two.", self=True),
           line(100 + SCENE_GAP + 1 + SCENE_GAP, "Rambleon", "Three.", self=True),
           dict(line(100 + 2 * SCENE_GAP + 2, "Rambleon", "Four.", self=True), zone="Westfall", subzone="Sentinel Hill")]
    found = scenes(session_of(evs))
    assert [len(sc.lines) for sc in found] == [2, 1, 1]
    assert [sc.place for sc in found] == ["Goldshire", "Goldshire", "Sentinel Hill"]


def test_scenes_reach_the_log_the_prompt_and_the_page_and_the_lines_leave_the_timeline(tmp_path):
    night = fixture_night()
    md = render_markdown(night)
    assert "## Scenes" in md and "### " in md and 'Cassidy: "Well met, hunter."  ' in md
    assert "A scene in Dolanaar with Cassidy and Wes (7 lines)" in md
    assert md.count('Well met, hunter.') == 1                       # under Scenes, not again on the Journey
    assert "Lines of roleplay: 7 in 1 scene" in md
    prompt = build_prompt(night, 1)
    assert "## Scenes (what was said in character" in prompt and "see Scenes" in prompt
    assert "Rambleon: \"And to you. ((brb, dog))\"" in prompt
    page = export_html(night, Archive(tmp_path / "a"), tmp_path / "exports").read_text()
    assert "<h2 id='scenes'>Scenes</h2>" in page and "href='#scenes'>Scenes</a>" in page
    assert "<p class='say me ooc'><b>Rambleon</b> “And to you. ((brb, dog))”</p>" in page
    assert "<p class='emote'>Cassidy bows low.</p>" in page
    assert "<b>Wes</b> <i>yells</i> “To the lake!”" in page and "<span class='ch'>party</span>" in page
    assert "Lines of roleplay</span>" in page and "class='scene-link'" in page


def test_a_long_scene_is_cut_in_the_middle_for_the_writer():
    evs = [line(100 + i, "Rambleon" if i % 2 else "Cassidy", f"Line {i}.", self=bool(i % 2) or None) for i in range(300)]
    text = "\n".join(render_prompt(session_of(evs)))
    assert "Line 0." in text and "Line 299." in text and "Line 150." not in text
    assert f"(… {300 - PROMPT_SCENE_LINES} more lines not shown)" in text


def test_no_scenes_is_said_plainly():
    assert "- none (nothing was said in character" in "\n".join(render_prompt(session_of([])))
    assert "## Scenes" not in render_markdown(session_of([]) | {"startedAt": 1, "state": "ended", "zones": [], "kills": {}})
