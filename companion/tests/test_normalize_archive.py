import json
import time
from pathlib import Path

from rambleon.archive import Archive
from rambleon.export import render_markdown
from rambleon.luaparse import parse, to_python
from rambleon.normalize import display_name, sessions_from_db, surname
from rambleon.summarize import build_prompt, split_output

FIXTURES = Path(__file__).parent / "fixtures"


def load_sessions():
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    return sessions_from_db(db)


def test_normalize_sessions():
    sessions = load_sessions()
    assert len(sessions) == 2
    ended, suspended = sessions
    assert ended["state"] == "ended" and ended["endReason"] == "save"
    assert ended["character"]["slug"] == "rambleon-birdsong"
    assert ended["counters"]["questsCompleted"] == 1
    assert [e["t"] for e in ended["events"]] == sorted(e["t"] for e in ended["events"])
    assert ended["id"] != suspended["id"]
    # seen a few seconds ago (pinned clock) → still resumable
    from rambleon.normalize import normalize_session
    raw = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]["sessions"][1]
    fresh = normalize_session(raw, now=raw["lastSeen"] + 10)
    assert fresh["state"] == "suspended" and fresh["addonState"] == "suspended"


def test_stale_suspended_session_becomes_ended():
    from rambleon.normalize import normalize_session
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    raw = db["sessions"][1]
    s = normalize_session(raw, now=raw["lastSeen"] + 3600)
    assert s["state"] == "ended" and s["endReason"] == "logout" and s["endedAt"] == raw["lastSeen"]


def test_end_level_derived_from_events():
    from rambleon.normalize import normalize_session
    raw = {"id": "x", "state": "ended", "startedAt": 1, "lastSeen": 2, "endedAt": 2,
           "character": {"name": "A", "startLevel": 8, "endLevel": 8},
           "events": [{"t": 1, "type": "SESSION_START", "level": 8}, {"t": 2, "type": "LEVEL_UP", "level": 9},
                      {"t": 3, "type": "ZONE_ENTER", "level": 9}]}
    s = normalize_session(raw, now=10_000)
    assert s["character"]["startLevel"] == 8 and s["character"]["endLevel"] == 9


def test_empty_db_yields_nothing():
    assert sessions_from_db({"schemaVersion": 1, "sessions": []}) == []
    assert sessions_from_db(None) == []


def test_archive_merge_rules(tmp_path):
    archive = Archive(tmp_path / "archive")
    sessions = load_sessions()
    s = sessions[0]
    capture = {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"}
    outcome, path = archive.upsert_session(s, capture)
    assert outcome == "new" and path.exists()
    assert archive.upsert_session(s, capture)[0] == "unchanged"
    fewer = dict(s, events=s["events"][:-1])
    assert archive.upsert_session(fewer, capture)[0] == "rejected"
    more = dict(s, events=s["events"] + [{"t": s["events"][-1]["t"] + 1, "type": "MARK"}])
    outcome, path2 = archive.upsert_session(more, capture)
    assert outcome == "updated" and path2 == path
    assert list(archive.history_dir.glob("*.json"))
    downgrade = dict(more, state="suspended")
    assert archive.upsert_session(downgrade, capture)[0] == "rejected"
    index = archive.rebuild_index()
    assert index["sessions"][0]["events"] == len(more["events"])
    assert archive.load_session("latest")["id"] == s["id"]
    # a trivial login-only session archived later must not become "latest"
    tiny = dict(sessions[1], events=sessions[1]["events"][:2], playedSeconds=5, startedAt=s["startedAt"] + 9999)
    assert archive.upsert_session(tiny, capture)[0] == "new"
    archive.rebuild_index()
    assert archive.load_session("latest")["id"] == s["id"]
    assert archive.list_sessions()[-1]["trivial"] is True
    assert archive.resolve(s["id"]) is not None
    assert archive.resolve(s["id"][:10]) is None  # ambiguous prefix (matches both sessions)
    assert archive.resolve(s["id"][:10] + "zzz") is None


def test_raw_snapshot_dedupe(tmp_path):
    archive = Archive(tmp_path / "archive")
    data = b"\r\nRambleonDB = {\r\n}\r\n"
    p, h = archive.snapshot_raw(data, Path("Rambleon.lua"))
    assert p and p.exists() and archive.has_hash(h)
    assert archive.snapshot_raw(data, Path("Rambleon.lua"))[0] is None


def test_markdown_export_is_factual():
    s = load_sessions()[0]
    md = render_markdown(s)
    assert md.startswith("# Rambleon Birdsong")
    assert "## Journey" in md and "## Progress" in md and "## People Met" in md
    assert 'Accepted "The Emerald Dreamcatcher"' in md
    assert "Moonhoof" in md
    assert "this cave is extremely cursed" in md
    assert "## Enemies Slain" in md and "Timberling × 2" in md
    assert "First Grell slain" in md and "8/8 Timberling slain" in md
    assert "## Loot Worth Keeping" in md and "Looted Arcane Staff ×2 (Rare)" in md and "Equipped Arcane Staff" in md


def test_prompt_and_split():
    s = load_sessions()[0]
    prompt = build_prompt(s, 3)
    assert "# Chapter 3" in prompt and "Only what happened" in prompt and "Moonhoof" in prompt
    journal, recap, post = split_output("# Chapter 3 — Test\n\nbody\n\n---RECAP---\n2h in Azeroth.\nRamble on.")
    assert journal.startswith("# Chapter 3") and recap.startswith("2h") and post is None
    journal, recap, post = split_output("# Chapter 3 — Test\n\nbody\n\n---RECAP---\n2h in Azeroth.\nRamble on.\n"
                                        "---POST---\nRambleon walked\nto Dolanaar.\n")
    assert recap == "2h in Azeroth.\nRamble on.\n" and post == "Rambleon walked to Dolanaar." and "POST" not in journal
    assert "---POST---" in prompt


def test_display_name_survives_the_client_name_change():
    old_build = {"name": "Rambleon Birdsong", "fullName": "Rambleon Birdsong", "realmFromFullName": "ClassicBetaPvE",
                 "realm": "Classic Beta PvE", "normalizedRealm": "ClassicBetaPvE"}
    new_build = {"name": "Rambleon", "fullName": "Rambleon", "realmFromFullName": "Birdsong",
                 "realm": "Classic Beta PvE", "normalizedRealm": "ClassicBetaPvE"}
    mainline = {"name": "Rambleon", "fullName": "Rambleon", "realmFromFullName": "Area 52",
                "realm": "Area 52", "normalizedRealm": "Area52"}
    assert surname(old_build) is None and display_name(old_build) == "Rambleon Birdsong"
    assert surname(new_build) == "Birdsong" and display_name(new_build) == "Rambleon Birdsong"
    assert surname(mainline) is None and display_name(mainline) == "Rambleon"
    assert display_name({"name": "Rambleon", "displayName": "Rambleon Birdsong"}) == "Rambleon Birdsong"
    assert display_name({}) == "Unknown"
    s = load_sessions()[0]
    assert s["character"]["displayName"] == "Rambleon Birdsong" and s["character"]["slug"] == "rambleon-birdsong"
