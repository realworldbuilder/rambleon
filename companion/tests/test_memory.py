"""Chapter continuity: what the writer may remember from earlier nights."""
import copy
import time
from pathlib import Path

from rambleon.archive import Archive, atomic_write_json
from rambleon.luaparse import parse, to_python
from rambleon.memory import build_memory, companion_history, companion_suffix, previous_chapters, previous_journal, render_memory
from rambleon.nights import chapter_number, earlier_nights, nights
from rambleon.normalize import sessions_from_db
from rambleon.summarize import build_prompt, summarize

FIXTURES = Path(__file__).parent / "fixtures"
DAY = 86400


def _shifted(raw: dict, days: int, slug_suffix: str | None = None) -> dict:
    s = copy.deepcopy(raw)
    s["id"] = f"{s['id']}-d{days}"
    for k in ("startedAt", "endedAt", "lastSeen"):
        s[k] += days * DAY
    for ev in s["events"]:
        ev["t"] += days * DAY
    for p in s.get("people", []):
        for k in ("firstSeen", "lastSeen"):
            if p.get(k):
                p[k] += days * DAY
    if slug_suffix:
        for k in ("name", "fullName", "displayName"):
            if s["character"].get(k):
                s["character"][k] = s["character"][k] + slug_suffix
        s["character"]["guid"] = s["character"]["guid"] + slug_suffix
        s["id"] = s["id"] + slug_suffix
    return s


def three_nights(tmp_path):
    """Three nights of the fixture character a day apart, plus an earlier night of another character."""
    archive = Archive(tmp_path / "archive")
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    raw = db["sessions"][0]
    raws = [_shifted(raw, 0), _shifted(raw, 1), _shifted(raw, 2), _shifted(raw, -1, "Other")]
    cap = {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"}
    for s in sessions_from_db({"sessions": raws}):
        archive.upsert_session(s, cap)
    archive.rebuild_index()
    slug = sessions_from_db({"sessions": [raws[0]]})[0]["character"]["slug"]
    n1, n2, n3 = nights(archive, slug)
    assert nights(archive)[0]["character"]["slug"] != slug   # the other character's night comes first overall
    return archive, tmp_path / "exports", n1, n2, n3


def _write_sidecar(exports, night, chapter, heading, text):
    atomic_write_json(exports / "journal" / f"{night['id']}.json", {
        "sessionId": night["id"], "chapter": chapter, "title": f"Chapter {chapter} — {heading}",
        "journal": text, "recap": "Ramble on.\n"})


def test_earlier_nights_excludes_self_and_other_characters(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    assert [n["id"] for n in earlier_nights(archive, n3)] == [n1["id"], n2["id"]]
    assert earlier_nights(archive, n1) == []
    assert chapter_number(archive, n1) == 1 and chapter_number(archive, n3) == 3


def test_previous_chapters_titles_and_limit(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    _write_sidecar(exports, n2, 2, "The Test", "# Chapter 2 — The Test\n\nA night.\n")
    prior = earlier_nights(archive, n3)
    entries = previous_chapters(prior, exports)
    assert [e["chapter"] for e in entries] == [1, 2]
    assert entries[0]["title"] is None and entries[1]["title"] == "The Test"
    assert entries[1]["previous"] and not entries[0]["previous"]
    assert entries[1]["companions"][0]["name"] == "Moonhoof" and "Teldrassil" in entries[1]["zones"]
    only = previous_chapters(prior, exports, limit=1)
    assert [e["chapter"] for e in only] == [2]


def test_previous_journal(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    assert previous_journal(earlier_nights(archive, n3), exports) is None
    _write_sidecar(exports, n2, 2, "The Test", "# Chapter 2 — The Test\n\nMoonhoof came along.\n")
    j = previous_journal(earlier_nights(archive, n3), exports)
    assert j["chapter"] == 2 and "Moonhoof came along." in j["journal"]
    assert previous_journal([], exports) is None


def test_companion_history(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    prior = earlier_nights(archive, n3)
    h = companion_history(prior, n3)
    m = h["Moonhoof"]
    assert m["nights"] == 2 and m["chapters"] == [1, 2] and m["lastChapter"] == 2
    assert m["seconds"] == n1["people"][0]["seconds"] + n2["people"][0]["seconds"]
    assert m["firstMet"]["date"] == n1["nightDate"] and m["firstMet"]["chapter"] == 1
    assert m["firstMet"]["place"] == "Dolanaar"
    assert "Nobody" not in h
    assert companion_history([], n1) == {}


def test_prompt_memory_section_and_familiar_faces(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    _write_sidecar(exports, n2, 2, "The Test", "# Chapter 2 — The Test\n\nMoonhoof came along.\n")
    memory = build_memory(earlier_nights(archive, n3), n3, exports)
    prompt = build_prompt(n3, 3, "field-journal", memory)
    assert "## Story so far" in prompt
    assert "Chapter 2 — The Test" in prompt and ", the previous chapter:" in prompt
    assert "Moonhoof came along." in prompt
    assert "familiar: 2 earlier nights (Chapters 1 and 2)" in prompt
    assert "in Dolanaar" in prompt and "together before tonight" in prompt
    assert str(tmp_path) not in prompt
    first = build_prompt(n1, 1, "field-journal", build_memory([], n1, exports))
    assert "## Story so far" not in first and "— first time together" not in first and "— familiar:" not in first
    assert build_prompt(n1, 1, "field-journal") == first


def test_first_time_together(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    stranger = dict(n3, people=[{"name": "Stranger", "class": "Mage", "seconds": 600}])
    memory = build_memory(earlier_nights(archive, n3), stranger, exports)
    prompt = build_prompt(stranger, 3, "field-journal", memory)
    assert "Stranger (Mage) — about 10 minutes together — first time together" in prompt


def test_people_notes(tmp_path, monkeypatch):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    (tmp_path / "rambleon.local.toml").write_text('[people."Moonhoof"]\nnote = "guildmate"\n\n[people."Nobody"]\nnote = 3\n')
    monkeypatch.setattr("rambleon.config.find_repo_root", lambda: tmp_path)
    from rambleon.config import people_notes
    assert people_notes() == {"Moonhoof": "guildmate"}
    assert 'player\'s note: "guildmate"' in build_prompt(n1, 1, "field-journal")   # chapter 1 too
    assert companion_suffix("X", None, None) == ""


def test_summarize_prompt_file_carries_memory(tmp_path, monkeypatch):
    monkeypatch.setattr("rambleon.config.find_repo_root", lambda: tmp_path)
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    _write_sidecar(exports, n2, 2, "The Test", "# Chapter 2 — The Test\n\nMoonhoof came along.\n")
    result = summarize(n3, archive, exports, use_ai=False, log=lambda *_: None)
    text = result["prompt"].read_text()
    assert "Chapter number: 3" in text
    assert "## Story so far" in text and "Moonhoof came along." in text and "familiar: 2 earlier nights" in text
    first = summarize(n1, archive, exports, use_ai=False, log=lambda *_: None)["prompt"].read_text()
    assert "## Story so far" not in first


def test_resummarize_ignores_own_sidecar(tmp_path):
    archive, exports, n1, n2, n3 = three_nights(tmp_path)
    _write_sidecar(exports, n3, 3, "Tonight Already", "# Chapter 3 — Tonight Already\n\nOld run.\n")
    memory = build_memory(earlier_nights(archive, n3), n3, exports)
    text = "\n".join(render_memory(memory))
    assert "Tonight Already" not in text and "Old run." not in text
