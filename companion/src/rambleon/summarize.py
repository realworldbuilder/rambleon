"""Build an AI-neutral journal prompt and, when the local Claude CLI exists, write the chapter with it."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from .archive import Archive, atomic_write_bytes, atomic_write_json
from .config import character_overrides, journal_model, journal_voice, people_notes
from .events import shown
from .export import clock, describe, duration, export_filename, long_date, render_recap
from .memory import build_memory, companion_suffix, render_memory
from .screenshots import caption

RULES_PATH = Path(__file__).parent / "prompts" / "journal.md"
VOICES_DIR = Path(__file__).parent / "prompts" / "voices"
DEFAULT_VOICE = "golden"


def available_voices() -> list[str]:
    return sorted(p.stem for p in VOICES_DIR.glob("*.md"))


def load_voice(name: str | None) -> str:
    name = name or os.environ.get("RAMBLEON_VOICE") or DEFAULT_VOICE
    path = VOICES_DIR / f"{name}.md"
    if not path.exists():
        raise ValueError(f"unknown voice {name!r}; available: {', '.join(available_voices())}")
    return path.read_text(encoding="utf-8").strip()
RECAP_MARKER = "---RECAP---"
POST_MARKER = "---POST---"
DEFAULT_MODEL = "sonnet"
SYSTEM_PROMPT = ("You are a careful writer helping a player keep a personal journal of their World of Warcraft "
                 "adventures. Follow the instructions in the message exactly. Output only the requested text.")


def build_prompt(session: dict[str, Any], chapter: int, voice: str | None = None,
                 memory: dict[str, Any] | None = None) -> str:
    """`memory` is memory.build_memory() output: what earlier chapters may lend tonight's. None for chapter 1
    or a lone session record; then the prompt is exactly what it was before memory existed."""
    c = dict(session.get("character", {}))
    for k, v in character_overrides(c.get("slug", "")).items():   # rambleon.local.toml wins over old sessions
        if isinstance(v, (str, int, float, bool)) and k not in ("name", "slug"):
            c[k] = v
    cnt = session.get("counters", {})
    rules = RULES_PATH.read_text(encoding="utf-8").replace("{voice}", load_voice(voice))
    people = sorted(session.get("people", []), key=lambda p: -(p.get("seconds") or 0))
    lines = [rules.replace("{chapter}", str(chapter)), "", "=" * 72, "", "## Character", ""]
    lines.append(f"- Name: {c.get('displayName')}")
    if c.get("race") or c.get("class"):
        lines.append(f"- {c.get('race', '')} {c.get('class', '')}".rstrip())
    if c.get("gender"):
        lines.append(f"- Gender: {c['gender']} (use matching pronouns)")
    else:
        lines.append("- Gender: not recorded — refer to the character by name or with they/them, never guess")
    lines.append(f"- Level at start: {c.get('startLevel')}; level at end: {c.get('endLevel')}")
    lines.append(f"- Game: World of Warcraft: Forever (client {session.get('client', {}).get('version', '?')})")
    lines += ["", "## Session", "", f"- Date: {long_date(session.get('startedAt'))}",
              f"- Started: {clock(session.get('startedAt'))}; ended: {clock(session.get('endedAt'))}",
              f"- Duration: {duration(session.get('playedSeconds'))}",
              f"- Chapter number: {chapter}",
              f"- Ended formally: {'yes' if session.get('endReason') == 'end_chapter' else 'no (' + str(session.get('endReason')) + ')'}"]
    story = render_memory(memory)
    if story:
        lines += [""] + story
    lines += ["", "## Chronological events (the only facts you may use)", ""]
    for ev in session.get("events", []):
        if not shown(ev):
            continue
        extra = ""
        if ev.get("type") == "ZONE_ENTER" and ev.get("x") is not None:
            extra = f" [map {ev.get('mapID')}, {ev.get('x')}, {ev.get('y')}]"
        lines.append(f"- {clock(ev.get('t'))} — {describe(ev)}{extra}")
    lines += ["", "## Counters", ""]
    for k, v in cnt.items():
        lines.append(f"- {k}: {v}")
    lines.append(f"- placesVisited: {len(session.get('zones', []))}")
    lines += ["", "## Places (in order of first visit)", ""]
    for z in session.get("zones", []):
        label = f"{z.get('subzone')} ({z.get('zone')})" if z.get("subzone") else str(z.get("zone"))
        lines.append(f"- {label} (visits: {z.get('visits', 1)})")
    kills = sorted(session.get("kills", {}).items(), key=lambda kv: -(kv[1].get("count") or 0))
    lines += ["", "## Enemies slain (from experience messages; only kills that gave XP)", ""]
    if kills:
        for name, info in kills:
            lines.append(f"- {name} × {info.get('count', 0)}")
    else:
        lines.append("- none recorded")
    loot = [ev for ev in session.get("events", []) if ev.get("type") in ("LOOT", "EQUIP")]
    lines += ["", "## Loot worth keeping (uncommon or better)", ""]
    if loot:
        for ev in loot:
            lines.append(f"- {clock(ev.get('t'))} — {describe(ev)}")
    else:
        lines.append("- none")
    lines += ["", "## People met", ""]
    notes_about = people_notes()
    history = memory.get("history") if memory else None
    if people:
        for p in people:
            mins = int(round((p.get("seconds") or 0) / 60))
            extra = companion_suffix(p.get("name") or "", history, notes_about.get(p.get("name") or ""))
            lines.append(f"- {p.get('name')}{' (' + p['class'] + ')' if p.get('class') else ''} — about {mins} minutes together{extra}")
    else:
        lines.append("- none")
    lines += ["", "## Player notes (verbatim, most important evidence)", ""]
    notes = [ev for ev in session.get("events", []) if ev.get("type") == "NOTE"]
    if notes:
        for ev in notes:
            lines.append(f"- {clock(ev.get('t'))} in {ev.get('subzone') or ev.get('zone') or 'unknown place'}: \"{ev.get('text')}\"")
    else:
        lines.append("- none")
    lines += ["", "## Screenshots (you cannot see them; only the moment they were taken is known)", ""]
    shots = session.get("screenshots", [])
    if shots:
        for s in shots:
            lines.append(f"- screenshot taken when: {caption(s, session.get('events', []))} at {clock(s.get('takenAt'))}")
    else:
        lines.append("- none")
    lines += ["", "## Recap numbers to use verbatim", "",
              f"- duration: {duration(session.get('playedSeconds'))}",
              f"- levels: {cnt.get('levelsGained', 0)}",
              f"- quests: {cnt.get('questsCompleted', 0)}",
              f"- places: {len(session.get('zones', []))}",
              f"- deaths: {cnt.get('deaths', 0)}",
              f"- enemies slain: {cnt.get('kills', 0)}",
              f"- people: {len(people)}", ""]
    return "\n".join(lines)


def claude_available() -> str | None:
    return shutil.which("claude")


def run_claude(prompt: str, model: str = DEFAULT_MODEL, timeout: int = 600) -> tuple[str | None, str]:
    """Returns (text, diagnostic). Uses only flags verified on the installed CLI."""
    exe = claude_available()
    if not exe:
        return None, "claude CLI not found on PATH"
    # No tools, no session, a writer's system prompt instead of the coding one, and an empty working
    # directory so no CLAUDE.md or project settings leak into the journal. Uses the CLI's own login.
    cmd = [exe, "-p", "--tools", "", "--output-format", "json", "--no-session-persistence",
           "--max-budget-usd", "0.50", "--model", model,
           "--system-prompt", SYSTEM_PROMPT]
    with tempfile.TemporaryDirectory(prefix="rambleon-") as cwd:
        try:
            proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        except (OSError, subprocess.TimeoutExpired) as e:
            return None, f"claude failed to run: {e}"
    out = (proc.stdout or "").strip()
    payload: Any = None
    try:
        payload = json.loads(out) if out else None
    except ValueError:
        payload = None
    if isinstance(payload, dict):
        text = payload.get("result")
        if payload.get("is_error") or proc.returncode != 0:
            return None, f"claude reported an error: {text or proc.stderr.strip()[:300]}"
        if isinstance(text, str) and text.strip():
            return text.strip(), "ok"
        return None, f"claude returned no result: {out[:300]}"
    if proc.returncode != 0:
        return None, f"claude exited {proc.returncode}: {(proc.stderr or out).strip()[:500]}"
    return (out, "ok (plain text)") if out else (None, "claude returned nothing")


def split_output(text: str) -> tuple[str, str | None, str | None]:
    """(journal, recap, post). The post is the one-line telling for a social feed; either tail may be missing."""
    post = None
    if POST_MARKER in text:
        text, tail = text.split(POST_MARKER, 1)
        if RECAP_MARKER in tail:              # sections in the wrong order: the recap still belongs to the recap
            tail, recap_tail = tail.split(RECAP_MARKER, 1)
            text += RECAP_MARKER + recap_tail
        post = " ".join(tail.split()) or None
    if RECAP_MARKER in text:
        journal, recap = text.split(RECAP_MARKER, 1)
        return journal.strip() + "\n", recap.strip() + "\n", post
    return text.strip() + "\n", None, post


def summarize(session: dict[str, Any], archive: Archive, exports_dir: Path, use_ai: bool = True,
              model: str | None = None, log=print, voice: str | None = None) -> dict[str, Path | None]:
    """`voice` and `model`: what was asked for; else the environment, else `[journal]` in rambleon.local.toml."""
    from .nights import earlier_nights
    voice = journal_voice(voice)
    model = journal_model(model) or DEFAULT_MODEL
    memory = None
    if session.get("kind") == "night":
        prior = earlier_nights(archive, session)          # one nights() pass: chapter number and memory together
        chapter = len(prior) + 1
        memory = build_memory(prior, session, exports_dir)
    else:
        chapter = archive.chapter_number(session)
    prompt = build_prompt(session, chapter, voice, memory)
    prompt_path = exports_dir / "prompts" / export_filename(session, "-prompt")
    atomic_write_bytes(prompt_path, prompt.encode("utf-8"))
    result: dict[str, Path | None] = {"prompt": prompt_path, "journal": None, "recap": None}
    if not use_ai:
        log(f"prompt written to {prompt_path} (AI skipped)")
        return result
    if not claude_available():
        log(f"prompt written to {prompt_path}. No `claude` CLI found; paste the prompt into any assistant.")
        return result
    log(f"asking claude ({model}) to write chapter {chapter}…")
    text, diag = run_claude(prompt, model=model)
    if text is None:
        log(f"AI journal skipped: {diag}. The prompt is at {prompt_path}.")
        return result
    journal, recap, post = split_output(text)
    title = None
    for line in journal.splitlines():
        if line.startswith("#"):
            title = line.lstrip("#").strip()
            break
    atomic_write_json(exports_dir / "journal" / f"{session['id']}.json", {
        "sessionId": session["id"], "chapter": chapter, "title": title, "journal": journal,
        "recap": recap or render_recap(session), "post": post, "model": model, "voice": voice or DEFAULT_VOICE,
        "createdAt": int(time.time()),
    })
    journal_path = exports_dir / "markdown" / export_filename(session, "-journal")
    header = f"_{session.get('character', {}).get('displayName')} · {long_date(session.get('startedAt'))} · {duration(session.get('playedSeconds'))} in Azeroth_\n\n"
    atomic_write_bytes(journal_path, (journal.rstrip() + "\n\n" + header).encode("utf-8"))
    result["journal"] = journal_path
    if recap:
        recap_path = exports_dir / "social" / export_filename(session, "-recap").replace(".md", ".txt")
        atomic_write_bytes(recap_path, recap.encode("utf-8"))
        result["recap"] = recap_path
    log(f"journal written to {journal_path}")
    return result
