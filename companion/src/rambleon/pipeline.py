"""What happens when a night is over, as a list of steps.

The watcher runs every step for a finished night; `ramble finish` does the same by hand; `ramble summarize`,
`page` and `publish` run a few of them. Each step is guarded: one that fails is logged and the rest still run,
so a page that cannot be written never keeps the chapter out of the game.

A new output (a weekly recap, a timeline page, another place to post) is one function that takes the
NightContext and returns a line for the log, plus one `Step` in STEPS. docs/extending.md walks through it."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .archive import Archive, atomic_write_json, load_json
from .config import share_auto
from .export import duration, export_filename, export_session, night_stats
from .guide import write_guide
from .nights import night_date, nights as list_nights, resolve_night
from .notify import notify
from .publish import export_html, load_journal, publish_chapters, write_html_index
from .screenshots import refresh_session_screenshots
from .share import share as run_share
from .summarize import summarize as run_summarize

Log = Callable[[str], None]
MARKER_VERSION = 1
RECOVER_WITHIN = 2 * 86400    # a night older than this is never finished by itself after a restart


class Skip(Exception):
    """Raised by a step that has nothing to do; the reason is recorded, nothing is logged as an error."""


@dataclass
class NightContext:
    archive: Archive
    paths: Any                              # paths.Paths
    night: dict[str, Any] | None            # None for the steps that are about every night (index, game)
    log: Log = print
    use_ai: bool = True
    model: str | None = None                # None: [journal] model, else the default
    voice: str | None = None                # None: [journal] voice, else the default
    unattended: bool = False                # the watcher: nobody is there to ask, and nobody is watching the log
    share: bool = False                     # asked for by hand (`ramble finish --share`)
    confirm: Callable[[str], bool] | None = None
    outputs: dict[str, Any] = field(default_factory=dict)    # what steps made, by step name (paths mostly)
    results: dict[str, str] = field(default_factory=dict)    # step name -> ok | skipped: why | failed: why

    @property
    def failed(self) -> dict[str, str]:
        return {name: r for name, r in self.results.items() if r.startswith("failed")}


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[NightContext], str | None]   # returns a line for the log (or None); raises Skip to sit out
    fatal: bool = False                         # a failure here stops the steps after it
    needs_ai: bool = False                      # may call the Claude CLI (it still runs without: the prompt is written)


# -- the steps -----------------------------------------------------------------

def step_screenshots(ctx: NightContext) -> str | None:
    """Screenshots taken after the last SavedVariables write are only on disk: pair them now."""
    night = ctx.night
    changed = refresh_session_screenshots(ctx.archive, ctx.paths, night.get("sessionIds") or [night["id"]])
    if not changed:
        return None
    ctx.night = resolve_night(ctx.archive, night["id"]) or night
    return f"paired late screenshots in {changed} session(s)"


def step_markdown(ctx: NightContext) -> str:
    out = export_session(ctx.night, ctx.paths.exports_dir)
    ctx.outputs["markdown"] = out
    return f"exported {out.name}"


def step_journal(ctx: NightContext) -> str | None:
    """The prompt always; the chapter when the Claude CLI is there. The watcher does not pay twice for a chapter
    that already covers the night (a restart, or a second look at the same save)."""
    night = ctx.night
    use_ai = ctx.use_ai
    if use_ai and ctx.unattended and chapter_is_current(ctx.paths.exports_dir, night):
        ctx.log("the chapter already covers this night; not written again")
        use_ai = False
    result = run_summarize(night, ctx.archive, ctx.paths.exports_dir, use_ai=use_ai, model=ctx.model, log=ctx.log, voice=ctx.voice)
    ctx.outputs["journal"] = result
    return None


def step_guide(ctx: NightContext) -> str:
    """The route guide: facts every time, prose only when this night is new to it; the story page links to it."""
    slug = ctx.night["character"].get("slug", "unknown")
    result = write_guide(ctx.archive, ctx.paths.exports_dir, slug, use_ai=ctx.use_ai, model=ctx.model, voice=ctx.voice,
                         log=ctx.log, only_if_new=True)
    ctx.outputs["guide"] = result
    return f"route guide {result['html']}"


def step_page(ctx: NightContext) -> str:
    out = export_html(ctx.night, ctx.archive, ctx.paths.exports_dir)
    ctx.outputs["page"] = out
    return f"story page {out}"


def step_index(ctx: NightContext) -> str | None:
    ctx.outputs["index"] = write_html_index(ctx.archive, ctx.paths.exports_dir)
    return None


def step_game(ctx: NightContext) -> str:
    path, n = publish_chapters(ctx.archive, ctx.paths)
    ctx.outputs["game"] = path
    return f"published {n} chapter(s) to the game — they show under /ramble chapters after the next login or /reload"


def step_share(ctx: NightContext) -> str:
    """The page goes to GitHub Pages: by itself only where this Mac opted in ([share] auto), by hand when asked."""
    auto = ctx.unattended and share_auto(ctx.paths.repo_root)
    if not (auto or ctx.share):
        raise Skip("not asked for" if not ctx.unattended else "[share] auto is off")
    result = run_share(ctx.archive, ctx.paths, [ctx.night["id"]], yes=auto, log=ctx.log, confirm=ctx.confirm)
    ctx.outputs["share"] = result
    for url in result.urls:
        ctx.log(url)
    return f"share: {result.message}"


def step_notify(ctx: NightContext) -> None:
    if not ctx.unattended:
        raise Skip("someone is at the keyboard")
    night, st = ctx.night, night_stats(ctx.night)
    shared = " Shared." if getattr(ctx.outputs.get("share"), "pushed", False) else ""
    notify("Rambleon", f"{night['character'].get('displayName')}: {st['duration']} in Azeroth, "
                       f"{st['quests']} quests, {st['kills']} kills. Chapter written.{shared}")


STEPS: list[Step] = [
    Step("screenshots", step_screenshots),
    Step("markdown", step_markdown),
    Step("journal", step_journal, needs_ai=True),
    Step("guide", step_guide, needs_ai=True),
    Step("page", step_page),
    Step("index", step_index),
    Step("game", step_game),
    Step("share", step_share),
    Step("notify", step_notify),
]


# -- running them ---------------------------------------------------------------

def run_steps(ctx: NightContext, steps: list[Step] | None = None, only: set[str] | None = None) -> NightContext:
    """Run the steps in order (`only`: just the named ones). Nothing a step raises gets past here."""
    for step in (STEPS if steps is None else steps):
        if only is not None and step.name not in only:
            continue
        try:
            line = step.run(ctx)
            ctx.results[step.name] = "ok"
            if line:
                ctx.log(line)
        except Skip as why:
            ctx.results[step.name] = f"skipped: {why}"
        except Exception as e:  # noqa: BLE001 — the other steps must still run
            ctx.results[step.name] = f"failed: {type(e).__name__}: {e}"
            ctx.log(f"{step.name} failed: {type(e).__name__}: {e}")
            if step.fatal:
                break
    return ctx


def finish_night(archive: Archive, paths: Any, ref: str, log: Log = print, **options: Any) -> NightContext:
    """Every step for one night (ref: a night or session id, a date, `latest`), then the marker that says so."""
    night = resolve_night(archive, ref)
    if night is None:
        raise ValueError(f"no night matches {ref!r} (try `ramble nights`)")
    ctx = run_steps(NightContext(archive=archive, paths=paths, night=night, log=log, **options))
    write_marker(paths.exports_dir, ctx)
    return ctx


# -- knowing what is finished ---------------------------------------------------

def marker_path(exports_dir: Path, night_id: str) -> Path:
    return exports_dir / "finished" / f"{night_id}.json"


def write_marker(exports_dir: Path, ctx: NightContext) -> None:
    night = ctx.night
    atomic_write_json(marker_path(exports_dir, night["id"]), {
        "formatVersion": MARKER_VERSION, "nightId": night["id"], "endedAt": night.get("endedAt") or 0,
        "events": len(night.get("events", [])), "finishedAt": int(time.time()), "steps": dict(ctx.results),
    })


def chapter_is_current(exports_dir: Path, night: dict[str, Any]) -> bool:
    """The AI chapter was written after the night's last minute."""
    journal = load_journal(exports_dir, night["id"])
    return bool(journal) and (journal.get("createdAt") or 0) >= (night.get("endedAt") or 0)


def is_finished(exports_dir: Path, night: dict[str, Any]) -> bool:
    """Has the pipeline run over everything this night holds? The marker says so; a night finished before
    markers existed counts when its chapter, or else its story page, is newer than its last minute."""
    ended = night.get("endedAt") or 0
    marker = marker_path(exports_dir, night["id"])
    if marker.exists():
        try:
            m = load_json(marker)
            return (m.get("endedAt") or 0) >= ended and (m.get("events") or 0) >= len(night.get("events", []))
        except (OSError, ValueError):
            return False
    if load_journal(exports_dir, night["id"]):
        return chapter_is_current(exports_dir, night)
    page = exports_dir / "html" / export_filename(night).replace(".md", ".html")
    try:
        return page.stat().st_mtime >= ended
    except OSError:
        return False


def unfinished(archive: Archive, exports_dir: Path, now: float | None = None, within: float = RECOVER_WITHIN) -> list[dict[str, Any]]:
    """Recent nights the pipeline has not (fully) run over: what a watcher that was down, or crashed, still owes."""
    now = time.time() if now is None else now
    recent = list_nights(archive, since=night_date(int(now - within - 86400)))
    return [n for n in recent if now - (n.get("endedAt") or 0) <= within and not is_finished(exports_dir, n)]
