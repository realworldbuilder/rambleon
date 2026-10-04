from rambleon.config import journal_model, journal_voice, load_config, share_auto, x_config


def test_defaults_without_a_file(tmp_path):
    cfg = load_config(tmp_path)
    assert not cfg.exists and cfg.error is None and cfg.warnings == ()
    assert cfg.share.auto is False and cfg.x.delay == 30 and cfg.journal.voice is None


def test_unknown_keys_and_bad_values_warn_and_fall_back(tmp_path):
    (tmp_path / "rambleon.local.toml").write_text(
        '[x]\nauto = true\ndelay = "soon"\nstyl = "thread"\n[sharing]\nauto = true\n[journal]\nvoice = "field-journal"\n'
        '[people."Moonhoof"]\nnote = "guildmate"\n[people."Nobody"]\n')
    cfg = load_config(tmp_path)
    assert cfg.x.auto is True and cfg.x.delay == 30 and cfg.x.style == "post"
    assert cfg.journal.voice == "field-journal" and cfg.people == {"Moonhoof": "guildmate"}
    text = " | ".join(cfg.warnings)
    assert "[x] delay" in text and "[x] styl" in text and "[sharing]" in text and "Nobody" in text
    assert x_config(tmp_path)["characters"] == []


def test_a_broken_file_is_an_error_and_everything_is_off(tmp_path):
    (tmp_path / "rambleon.local.toml").write_text("[share]\nauto = true\n[x\nauto = true\n")
    cfg = load_config(tmp_path)
    assert cfg.error and "not valid TOML" in cfg.error
    assert share_auto(tmp_path) is False and x_config(tmp_path)["auto"] is False


def test_voice_and_model_precedence(tmp_path, monkeypatch):
    (tmp_path / "rambleon.local.toml").write_text('[journal]\nvoice = "field-journal"\nmodel = "opus"\n')
    assert journal_voice(None, tmp_path) == "field-journal" and journal_model(None, tmp_path) == "opus"
    monkeypatch.setenv("RAMBLEON_VOICE", "golden")
    assert journal_voice(None, tmp_path) == "golden"
    assert journal_voice("mine.md", tmp_path) == "mine.md" and journal_model("haiku", tmp_path) == "haiku"
    assert journal_voice(None, tmp_path / "elsewhere") == "golden" and journal_model(None, tmp_path / "elsewhere") is None
