"""The words Rambleon hands the writer, and the look of its pages: bundled files, and the player's own.

    <home>/prompts/voices/<name>.md     a voice of your own (`--voice <name>`, or `[journal] voice`)
    <home>/prompts/guides/<name>.md     a guide mode of your own (`ramble guide --mode <name>`)
    <home>/prompts/journal.md           your own rules for the chapter, replacing the bundled ones
    <home>/prompts/theme.css            CSS added after the bundled page styles

<home> is ~/Rambleon for a package install and the checkout otherwise (RAMBLEON_HOME overrides; the folder is
gitignored). A file of yours with the name of a bundled one wins. A path to a .md file works wherever a name does."""
from __future__ import annotations

import re
from pathlib import Path

from .paths import find_repo_root

BUNDLED = Path(__file__).parent / "prompts"
KINDS = ("voices", "guides")
# What Rambleon fills in, per kind of prompt. Anything else in braces is sent to the writer as written; the
# bundled prompts use that on purpose ({duration} in the recap template is for the model, not for us).
PLACEHOLDERS = {
    "journal": {"voice", "chapter"},
    "guides": {"voice", "name", "pronouns", "startLevel", "endLevel", "nights"},
}
LITERAL = {
    "journal": {"duration", "levels", "quests", "places", "deaths"},
    "guides": {"number", "title"},
}


def user_dir(home: Path | None = None) -> Path:
    return (home or find_repo_root()) / "prompts"


def available(kind: str, home: Path | None = None) -> dict[str, Path]:
    """name -> file, bundled first, then the player's own (which win)."""
    found = {p.stem: p for p in sorted((BUNDLED / kind).glob("*.md"))}
    found.update({p.stem: p for p in sorted((user_dir(home) / kind).glob("*.md"))})
    return found


def is_yours(path: Path) -> bool:
    return BUNDLED not in path.parents


def load(kind: str, name: str, home: Path | None = None) -> tuple[str, str, Path]:
    """(name, text, file) for a known name or a path to a .md file. ValueError names what there is."""
    candidate = Path(name).expanduser()
    if (name.endswith(".md") or "/" in name) and candidate.is_file():
        return candidate.stem, candidate.read_text(encoding="utf-8").strip(), candidate
    known = available(kind, home)
    if name not in known:
        what = {"voices": "voice", "guides": "guide mode"}[kind]
        raise ValueError(f"unknown {what} {name!r}; available: {', '.join(sorted(known))} (or a path to a .md file)")
    return name, known[name].read_text(encoding="utf-8").strip(), known[name]


def journal_rules(home: Path | None = None) -> tuple[str, Path]:
    """The rules every chapter is written by: the player's prompts/journal.md when there is one."""
    own = user_dir(home) / "journal.md"
    path = own if own.is_file() else BUNDLED / "journal.md"
    return path.read_text(encoding="utf-8"), path


def theme_css(home: Path | None = None) -> str:
    """The player's prompts/theme.css, or nothing."""
    path = user_dir(home) / "theme.css"
    try:
        return path.read_text(encoding="utf-8") if path.is_file() else ""
    except OSError:
        return ""


def stray_placeholders(text: str, kind: str) -> list[str]:
    """{names} in a prompt that Rambleon neither fills nor knows as the writer's own: most likely a typo."""
    known = PLACEHOLDERS[kind] | LITERAL[kind]
    return sorted({m for m in re.findall(r"\{([A-Za-z][A-Za-z0-9_]*)\}", text) if m not in known})
