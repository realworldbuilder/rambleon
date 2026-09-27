"""Optional local overrides: <repo>/rambleon.local.toml (gitignored). Facts the archive does not hold yet."""
from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from .paths import find_repo_root

FILENAME = "rambleon.local.toml"


def load_local_config(repo_root: Path | None = None) -> dict[str, Any]:
    path = (repo_root or find_repo_root()) / FILENAME
    if not path.exists():
        return {}
    try:
        with open(path, "rb") as fh:
            return tomllib.load(fh)
    except (OSError, tomllib.TOMLDecodeError):
        return {}


def character_overrides(slug: str, repo_root: Path | None = None) -> dict[str, Any]:
    chars = load_local_config(repo_root).get("characters", {})
    return chars.get(slug, {}) if isinstance(chars, dict) else {}


def share_auto(repo_root: Path | None = None) -> bool:
    """`[share] auto = true`: push every finished chapter to GitHub Pages without asking. Off unless this
    machine's rambleon.local.toml says so; the file is gitignored, so it never travels with the repo."""
    share = load_local_config(repo_root).get("share", {})
    return bool(share.get("auto")) if isinstance(share, dict) else False


def guide_mode(repo_root: Path | None = None) -> str | None:
    """`[guide] mode = "season"`: which prompt the watcher uses for the route guide (a bundled mode or a path
    to your own .md). None means the default `route`."""
    guide = load_local_config(repo_root).get("guide", {})
    mode = guide.get("mode") if isinstance(guide, dict) else None
    return mode.strip() if isinstance(mode, str) and mode.strip() else None


def people_notes(repo_root: Path | None = None) -> dict[str, str]:
    """`[people."Cassidy"] note = "my friend from work"`: the player's own words about a companion, handed to
    the writer as evidence on every chapter. Names match the roster name the game shows."""
    people = load_local_config(repo_root).get("people", {})
    if not isinstance(people, dict):
        return {}
    out: dict[str, str] = {}
    for name, entry in people.items():
        note = entry.get("note") if isinstance(entry, dict) else None
        if isinstance(note, str) and note.strip():
            out[str(name)] = note.strip()
    return out
