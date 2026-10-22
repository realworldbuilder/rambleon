"""The roleplay of a night: CHAT events (what was said in character around the player) gathered into scenes.

A scene is a run of lines in one zone with no long silence between them. A run is worth telling when the
player spoke in it, a companion of the night did, or strangers held an actual conversation (three lines, two
voices). A lone stranger's "lfg" stays in the archive and off the page. The AddOn records; this decides."""
from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .events import describe

SCENE_GAP = 5 * 60          # seconds of silence that end a scene
STRANGER_LINES = 3          # a scene nobody you know spoke in needs this many in-character lines...
STRANGER_VOICES = 2         # ...from this many speakers to be a conversation rather than noise
PROMPT_LINES = 400          # lines the writer is handed at most over the night
PROMPT_SCENE_LINES = 120    # and per scene: the opening and the close are kept, the middle is cut
FOLD_LINES = 40             # a longer scene starts folded on the page

Event = dict[str, Any]


def clock(t: int | None) -> str:
    """As export.clock, which cannot be imported here: the log imports this module."""
    return datetime.fromtimestamp(t).strftime("%-I:%M %p") if t else "—"


@dataclass
class Scene:
    lines: list[Event]

    @property
    def start(self) -> int | None:
        return self.lines[0].get("t")

    @property
    def end(self) -> int | None:
        return self.lines[-1].get("t")

    @property
    def place(self) -> str | None:
        first = self.lines[0]
        return first.get("subzone") or first.get("zone")

    @property
    def speakers(self) -> list[str]:
        """Everyone who spoke, in order of their first line, the player included."""
        out: list[str] = []
        for ev in self.lines:
            who = ev.get("speaker")
            if who and who not in out:
                out.append(who)
        return out

    @property
    def others(self) -> list[str]:
        mine = {ev.get("speaker") for ev in self.lines if ev.get("self")}
        return [s for s in self.speakers if s not in mine]

    @property
    def own(self) -> bool:
        return any(ev.get("self") for ev in self.lines)

    @property
    def in_character(self) -> list[Event]:
        return [ev for ev in self.lines if not ev.get("ooc")]


def chat_lines(session: dict[str, Any]) -> list[Event]:
    return [ev for ev in session.get("events", []) if ev.get("type") == "CHAT" and ev.get("text")]


def worth_telling(scene: Scene, companions: set[str]) -> bool:
    if scene.own or any(s in companions for s in scene.speakers):
        return True
    ic = scene.in_character
    return len(ic) >= STRANGER_LINES and len({ev.get("speaker") for ev in ic}) >= STRANGER_VOICES


def scenes(session: dict[str, Any]) -> list[Scene]:
    """The night's scenes, in order. `session` may be a night or a single session."""
    companions = {p.get("name") for p in session.get("people", []) if p.get("name")}
    runs: list[Scene] = []
    current: Scene | None = None
    for ev in chat_lines(session):
        if current is not None:
            last = current.lines[-1]
            if (ev.get("t") or 0) - (last.get("t") or 0) > SCENE_GAP or ev.get("zone") != last.get("zone"):
                runs.append(current)
                current = None
        if current is None:
            current = Scene([ev])
        else:
            current.lines.append(ev)
    if current is not None:
        runs.append(current)
    return [run for run in runs if worth_telling(run, companions)]


def starts(scenes_: list[Scene]) -> dict[int, Scene]:
    """The first line of each scene, by identity, so a walk over the events can place a marker where it began."""
    return {id(sc.lines[0]): sc for sc in scenes_}


def _and(names: list[str]) -> str:
    if len(names) > 4:
        return f"{', '.join(names[:3])} and {len(names) - 3} others"
    if len(names) > 1:
        return f"{', '.join(names[:-1])} and {names[-1]}"
    return names[0] if names else ""


def title(scene: Scene) -> str:
    place = scene.place or "the wilds"
    others = scene.others
    if scene.own and others:
        return f"A scene in {place} with {_and(others)}"
    if scene.own:
        return f"A scene in {place}, alone"
    return f"Overheard in {place}: {_and(others)}"


def marker(scene: Scene) -> str:
    """The one line a scene gets on the timeline; the lines themselves are in the Scenes section."""
    n = len(scene.lines)
    return f"{title(scene)} ({n} line{'s' if n != 1 else ''})"


def line(ev: Event) -> str:
    return describe(ev)


def _trimmed(scene: Scene, keep: int) -> tuple[list[Event], int]:
    if len(scene.lines) <= keep:
        return scene.lines, 0
    head = keep * 2 // 3
    tail = keep - head
    return scene.lines[:head] + scene.lines[-tail:], len(scene.lines) - keep


def render_markdown(session: dict[str, Any]) -> list[str]:
    """The Scenes section of the factual log; empty when the night had none."""
    found = scenes(session)
    if not found:
        return []
    out = ["", "## Scenes", ""]
    for sc in found:
        out.append(f"### {clock(sc.start)} — {title(sc)}")
        out.append("")
        out += [line(ev) + "  " for ev in sc.lines]
        out.append("")
    return out[:-1]


def render_prompt(session: dict[str, Any]) -> list[str]:
    """What the writer is handed: every scene, word for word, within the caps."""
    found = scenes(session)
    out = ["", "## Scenes (what was said in character around the player, word for word; the only dialogue you may quote)", ""]
    if not found:
        out.append("- none (nothing was said in character, or it was not recorded)")
        return out
    budget = PROMPT_LINES
    for sc in found:
        shown, cut = _trimmed(sc, min(PROMPT_SCENE_LINES, max(budget, 6)))
        out.append(f"### {clock(sc.start)} — {title(sc)}")
        out += [line(ev) for ev in shown]
        if cut:
            out.append(f"(… {cut} more lines not shown)")
        out.append("")
        budget -= len(shown)
        if budget <= 0:
            out.append("(the rest of the night's scenes are left out for length)")
            break
    return out[:-1] if out[-1] == "" else out


def _html_line(ev: Event) -> str:
    who = html.escape(str(ev.get("speaker") or ""))
    text = html.escape(str(ev.get("text") or ""))
    cls = " ".join(c for c in (ev.get("channel") or "say", "me" if ev.get("self") else "", "ooc" if ev.get("ooc") else "") if c)
    if ev.get("channel") == "emote":
        return f"<p class='{cls}'>{html.escape(line(ev))}</p>"
    if ev.get("channel") == "yell":
        return f"<p class='{cls}'><b>{who}</b> <i>yells</i> “{text}”</p>"
    if ev.get("channel") == "party":
        return f"<p class='{cls}'><b>{who}</b> <span class='ch'>party</span> “{text}”</p>"
    return f"<p class='{cls}'><b>{who}</b> “{text}”</p>"


def render_html(session: dict[str, Any]) -> str:
    """The Scenes section of the story page, or an empty string."""
    found = scenes(session)
    if not found:
        return ""
    parts = ["<h2 id='scenes'>Scenes</h2>"]
    for sc in found:
        head = f"<span class='when'>{html.escape(clock(sc.start))}</span>{html.escape(title(sc))}"
        body = "".join(_html_line(ev) for ev in sc.lines)
        if len(sc.lines) > FOLD_LINES:
            parts.append(f"<details class='scene'><summary class='scene-head'>{head} · {len(sc.lines)} lines, unfold</summary>{body}</details>")
        else:
            parts.append(f"<div class='scene'><div class='scene-head'>{head}</div>{body}</div>")
    return "".join(parts)
