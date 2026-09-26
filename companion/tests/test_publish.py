import time
from pathlib import Path

from rambleon.archive import Archive
from rambleon.luaparse import parse, to_python
from rambleon.normalize import sessions_from_db
from rambleon.publish import build_chapters, export_html, lua_string, write_chapters_lua
from rambleon.summarize import build_prompt
from rambleon.export import render_recap

FIXTURES = Path(__file__).parent / "fixtures"


def test_lua_string_escaping():
    s = lua_string('he said "hi"\nnew|line\\')
    assert s == '"he said \\"hi\\"\\nnew||line\\\\"'


def test_publish_roundtrip(tmp_path):
    archive = Archive(tmp_path / "archive")
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    archive.upsert_session(s, {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"})
    archive.rebuild_index()
    chapters = build_chapters(archive, tmp_path / "exports")
    assert len(chapters) == 1 and chapters[0]["number"] == 1
    assert "Ramble on." in chapters[0]["recap"]
    addon = tmp_path / "addon"; addon.mkdir()
    path = write_chapters_lua(chapters, addon)
    parsed = to_python(parse(path.read_bytes()))["RambleonChapters"]
    assert parsed[0]["id"].startswith("night-") and "Moonhoof" in parsed[0]["log"]
    assert parsed[0]["guid"] == s["character"]["guid"] and parsed[0]["slug"] == "rambleon-birdsong"
    page = export_html(s, archive, tmp_path / "exports")
    text = page.read_text()
    assert "<h1>Chapter 1" in text and "Travelled with Moonhoof" in text


def test_two_nights_of_one_character_are_numbered_in_order(tmp_path):
    """The client changed how it spells the name between builds; the same GUID must stay one character."""
    import copy
    archive = Archive(tmp_path / "archive")
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    first = sessions_from_db(db)[0]
    raw_second = copy.deepcopy(db["sessions"][0])
    raw_second["id"] = raw_second["id"].replace("_rambleon-birdsong", "_rambleon")
    raw_second["character"].update({"name": "Rambleon", "fullName": "Rambleon", "realmFromFullName": "Birdsong"})
    raw_second["character"].pop("displayName", None)
    raw_second["character"].pop("surname", None)
    day = 86400
    raw_second["startedAt"] += day; raw_second["endedAt"] += day; raw_second["lastSeen"] += day
    for ev in raw_second["events"]:
        ev["t"] += day
    second = sessions_from_db({"sessions": [raw_second]})[0]
    assert second["character"]["slug"] == "rambleon-birdsong"
    cap = {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"}
    archive.upsert_session(first, cap); archive.upsert_session(second, cap)
    archive.rebuild_index()
    chapters = build_chapters(archive, tmp_path / "exports")
    assert [c["number"] for c in chapters] == [1, 2]
    assert {c["slug"] for c in chapters} == {"rambleon-birdsong"}
    assert {c["guid"] for c in chapters} == {first["character"]["guid"]}
    assert chapters[0]["id"] != chapters[1]["id"] and all(c["id"].endswith("-rambleon-birdsong") for c in chapters)


def test_recap_wording():
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    recap = render_recap(s)
    assert recap.startswith("6m in Azeroth tonight.") and recap.rstrip().endswith("Ramble on.")


def test_voices():
    from rambleon.summarize import available_voices, build_prompt, load_voice
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    assert {"golden", "field-journal"} <= set(available_voices())
    assert "Christie Golden" in load_voice("golden")
    assert "{voice}" not in build_prompt(s, 1, "field-journal")
    assert "field journal" in build_prompt(s, 1, "field-journal")


def test_character_overrides(tmp_path, monkeypatch):
    from rambleon import summarize as sm
    (tmp_path / "rambleon.local.toml").write_text('[characters."rambleon-birdsong"]\ngender = "male"\n')
    monkeypatch.setattr("rambleon.config.find_repo_root", lambda: tmp_path)
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    s["character"].pop("gender", None)
    assert "Gender: male" in sm.build_prompt(s, 1, "field-journal")


# --- screenshots on the story page ---------------------------------------------------------------

import base64
import os
import shutil

from rambleon import publish as pub
from rambleon.screenshots import attach_screenshots

PNG_1x1 = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==")


def session_with_shots(tmp_path):
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    s = sessions_from_db(db)[0]
    wow_shots = tmp_path / "Screenshots"; wow_shots.mkdir()
    shots = [ev for ev in s["events"] if ev["type"] == "SCREENSHOT"]
    for n, ev in enumerate(shots):
        p = wow_shots / f"WoWScrnShot_092226_2000{n:02d}.png"
        p.write_bytes(PNG_1x1)
        os.utime(p, (ev["t"], ev["t"]))
    attach_screenshots(s, wow_shots, tmp_path / "archive" / "screenshots")
    return s


def test_story_page_places_pictures_on_the_timeline(tmp_path, monkeypatch):
    monkeypatch.setattr(pub, "RESIZER", None)
    s = session_with_shots(tmp_path)
    archive = Archive(tmp_path / "archive")
    archive.upsert_session(s, {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"})
    archive.rebuild_index()
    page = export_html(s, archive, tmp_path / "exports")
    text = page.read_text()
    assert "<figure class='hero'>" in text and "Marked moment in Dolanaar" in text
    assert text.count("<li class='shot'>") == 4               # five pictures: one hero, four on the timeline
    assert f"<figure class='hero'><img src='{page.stem}/{page.stem}-02.png' alt='Reached Level 11 in Dolanaar'" in text
    zone_shot = f"<li class='shot'><figure><img src='{page.stem}/{page.stem}-01.png' alt='Entered Darkshore'"
    assert text.index("Entered Auberdine (Darkshore)") < text.index(zone_shot) < text.index("Reached Level 11</li>")
    assert "Screenshots</h2>" not in text and "Took a screenshot" not in text
    assert str(tmp_path) not in text and "WoWScrnShot_" not in text
    assert sorted(p.name for p in page.with_suffix("").iterdir()) == [f"{page.stem}-0{n}.png" for n in range(1, 6)]
    index = pub.write_html_index(archive, tmp_path / "exports")
    assert "class='thumb'" in index.read_text()
    assert "class='thumb'" not in pub.write_html_index(archive, tmp_path / "exports", only=set()).read_text()


def test_web_copies_are_jpeg_when_sips_is_available(tmp_path):
    if not shutil.which("sips"):
        import pytest
        pytest.skip("sips is macOS only")
    s = session_with_shots(tmp_path)
    images = pub.prepare_images(s, tmp_path / "web" / "2026-09-22-x")
    assert [i["src"] for i in images] == [f"2026-09-22-x/2026-09-22-x-0{n}.jpg" for n in range(1, 6)]
    first = tmp_path / "web" / "2026-09-22-x" / "2026-09-22-x-01.jpg"
    assert first.read_bytes()[:2] == b"\xff\xd8"
    stamp = first.stat().st_mtime_ns
    pub.prepare_images(s, tmp_path / "web" / "2026-09-22-x")
    assert first.stat().st_mtime_ns == stamp                     # unchanged source → no rewrite


def test_prompt_tells_the_writer_when_pictures_were_taken(tmp_path):
    s = session_with_shots(tmp_path)
    prompt = build_prompt(s, 1)
    assert "screenshot taken when: Reached Level 11 in Dolanaar at" in prompt
    assert str(tmp_path) not in prompt


def test_tga_without_sips_is_skipped_not_broken(tmp_path, monkeypatch):
    monkeypatch.setattr(pub, "RESIZER", None)
    src = tmp_path / "WoWScrnShot_092226_200000.tga"; src.write_bytes(b"\x00" * 18)
    s = {"events": [], "screenshots": [{"path": str(src), "file": src.name, "takenAt": 1}]}
    assert pub.prepare_images(s, tmp_path / "web" / "p") == []
    assert not (tmp_path / "web" / "p").exists() or not list((tmp_path / "web" / "p").iterdir())


def two_nights(tmp_path):
    import copy
    archive = Archive(tmp_path / "archive")
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    first = sessions_from_db(db)[0]
    raw_second = copy.deepcopy(db["sessions"][0])
    raw_second["id"] += "_2"
    day = 86400
    raw_second["startedAt"] += day; raw_second["endedAt"] += day; raw_second["lastSeen"] += day
    for ev in raw_second["events"]:
        ev["t"] += day
    second = sessions_from_db({"sessions": [raw_second]})[0]
    cap = {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"}
    archive.upsert_session(first, cap); archive.upsert_session(second, cap)
    archive.rebuild_index()
    return archive


def test_story_pages_link_to_neighbouring_chapters(tmp_path):
    from rambleon.nights import nights
    archive = two_nights(tmp_path)
    n1, n2 = nights(archive)
    p1 = export_html(n1, archive, tmp_path / "exports")
    p2 = export_html(n2, archive, tmp_path / "exports")
    t1, t2 = p1.read_text(), p2.read_text()
    assert "<nav class='top'>" in t1 and "href='index.html'>All chapters" in t1
    assert "<div class='jump'>" in t1 and "href='#journey'" in t1 and "<details class='journey' open>" in t1
    assert t1.count("<div class='pager") == 2 and f"class='next' href='{p2.name}'" in t1 and "class='prev'" not in t1
    assert f"class='prev' href='{p1.name}'" in t2 and "class='next'" not in t2
    # Only pages that will sit next to it on the site are linked.
    alone = export_html(n1, archive, tmp_path / "exports", siblings={p1.name}).read_text()
    assert "class='pager" not in alone and "class='next'" not in alone


def test_index_is_a_list_of_cards(tmp_path):
    import rambleon.publish as pub
    archive = two_nights(tmp_path)
    text = pub.write_html_index(archive, tmp_path / "exports").read_text()
    assert text.count("<a class='card'") == 2 and "<span class='n'>Chapter 2</span>" in text
    assert text.index("Chapter 2</span>") < text.index("Chapter 1</span>")      # newest first
    assert "<nav class='top'>" in text and "1 companion<" in text and "companions" not in text.split("Chapter 2")[1].split("</li>")[0]
