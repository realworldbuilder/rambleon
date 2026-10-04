import time
from pathlib import Path

import pytest

from rambleon import pages, prompts
from rambleon.archive import Archive
from rambleon.guide import available_modes, load_mode
from rambleon.luaparse import parse, to_python
from rambleon.normalize import sessions_from_db
from rambleon.publish import export_html, write_html_index
from rambleon.summarize import available_voices, build_prompt, load_voice, summarize

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("RAMBLEON_HOME", str(home))
    return home


def session() -> dict:
    return sessions_from_db(to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"])[0]


def test_bundled_prompts_fill_cleanly():
    assert available_voices() == ["field-journal", "golden"] and set(available_modes()) == {"route", "season"}
    assert prompts.stray_placeholders(prompts.journal_rules()[0], "journal") == []
    for mode in available_modes():
        assert prompts.stray_placeholders(load_mode(mode)[1], "guides") == []
    prompt = build_prompt(session(), 1)
    assert "{voice}" not in prompt and "{chapter}" not in prompt and "{duration}" in prompt   # the recap template is the writer's


def test_your_own_voice_rules_and_mode(home, tmp_path):
    (home / "prompts" / "voices").mkdir(parents=True)
    (home / "prompts" / "guides").mkdir()
    (home / "prompts" / "voices" / "saga.md").write_text("Write it like an old saga.\n")
    (home / "prompts" / "voices" / "golden.md").write_text("My own golden.\n")           # yours wins over the bundled one
    (home / "prompts" / "guides" / "letters.md").write_text("Letters home from {name}, {nights}. {signoff}\n")
    assert available_voices() == ["field-journal", "golden", "saga"]
    assert load_voice("saga") == "Write it like an old saga." and load_voice(None) == "My own golden."
    assert prompts.is_yours(prompts.available("voices")["golden"]) and not prompts.is_yours(prompts.available("voices")["field-journal"])
    elsewhere = tmp_path / "terse.md"
    elsewhere.write_text("Three sentences. No more.\n")
    assert load_voice(str(elsewhere)) == "Three sentences. No more."                      # a path works wherever a name does
    with pytest.raises(ValueError, match="unknown voice 'nope'; available: field-journal, golden, saga"):
        load_voice("nope")
    assert "letters" in available_modes() and load_mode("letters")[0] == "letters"
    assert prompts.stray_placeholders(load_mode("letters")[1], "guides") == ["signoff"]
    (home / "prompts" / "journal.md").write_text("Chapter {chapter}. Voice: {voice} Sign as {penname}.\n")
    prompt = build_prompt(session(), 4, "saga")
    assert prompt.startswith("Chapter 4. Voice: Write it like an old saga. Sign as {penname}.")
    logs: list[str] = []
    summarize(session(), Archive(tmp_path / "a"), tmp_path / "exports", use_ai=False, log=logs.append, voice="saga")
    assert any("{penname} is not something Rambleon fills in" in m for m in logs)


def test_your_own_theme_is_added_to_every_page(home, tmp_path):
    s = session()
    archive = Archive(tmp_path / "archive")
    archive.upsert_session(s, {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"})
    archive.rebuild_index()
    plain = export_html(s, archive, tmp_path / "exports").read_text()
    assert "theme.css" not in plain and pages.css().startswith("\n:root{")
    (home / "prompts").mkdir(parents=True)
    (home / "prompts" / "theme.css").write_text(":root{--paper:#101418;--ink:#e8e2d0}\n")
    themed = export_html(s, archive, tmp_path / "exports").read_text()
    index = write_html_index(archive, tmp_path / "exports").read_text()
    for text in (themed, index):
        assert text.index("--paper:#f5ecd8") < text.index("/* prompts/theme.css */") < text.index("--paper:#101418") < text.index("</style>")
    assert "body.guide" in pages.css(guide=True) and "body.guide" not in pages.css()
