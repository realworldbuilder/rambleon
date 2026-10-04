"""The `ramble` command."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import typer
from rich.console import Console
from rich.markup import escape
from rich.table import Table

from . import __version__
from .archive import Archive
from .doctor import apply_fixes, run_doctor
from .archive import atomic_write_bytes
from .export import carried_over, duration, export_filename, export_session, render_catchup, render_markdown
from .install import install_addon
from .paths import resolve_paths
from . import service as svc
from .nights import earlier_nights, nights as list_nights, resolve_night
from .notify import notify
from .publish import export_html, publish_chapters, write_html_index
from .screenshots import refresh_session_screenshots
from .config import X_STYLES, effective, load_config, share_auto, x_config
from .guide import available_modes, default_mode, write_guide
from .share import ShareError, share as run_share
from . import xpost
from .watch import Finalizer
from .wowstate import logged_out_since
from .summarize import DEFAULT_MODEL, DEFAULT_VOICE, available_voices, summarize as run_summarize
from .watch import ingest_once, reprocess as run_reprocess, watch as run_watch

app = typer.Typer(help="Rambleon — your Azeroth adventure journal, Mac side.", no_args_is_help=True, add_completion=False)
console = Console()


def log(msg: str) -> None:
    console.print(f"[dim]{datetime.now():%H:%M:%S}[/dim] {escape(msg)}", highlight=False)


def _archive() -> tuple[Archive, "Paths"]:  # type: ignore[name-defined]
    paths = resolve_paths()
    archive = Archive(paths.archive_dir)
    archive.ensure()
    return archive, paths


def _load(ref: str) -> dict:
    archive, _ = _archive()
    session = archive.load_session(ref)
    if session is None:
        console.print(f"[red]no archived session matches {ref!r}[/red] — try `ramble sessions`")
        raise typer.Exit(1)
    return session


def _night(ref: str) -> dict:
    """A chapter = a night. ref: latest | tonight | YYYY-MM-DD | night id | session id."""
    archive, _ = _archive()
    night = resolve_night(archive, ref)
    if night is None:
        console.print(f"[red]no night matches {ref!r}[/red] — try `ramble nights`")
        raise typer.Exit(1)
    return night


def _x_config(paths) -> dict:
    """[x] from rambleon.local.toml. A file that cannot be read is said out loud: posting on defaults would surprise."""
    cfg = load_config(paths.repo_root)
    if cfg.error:
        console.print(f"[red]{cfg.error}[/red]", highlight=False)
        raise typer.Exit(1)
    return x_config(paths.repo_root)


@app.command()
def version() -> None:
    """Print the companion version."""
    console.print(f"ramble {__version__}")


def _print_checks(checks) -> None:
    width = max(len(c.label) for c in checks) + 1
    for c in checks:
        color = "green" if c.ok else ("yellow" if not c.essential else "red")
        console.print(f"{c.label + ':':<{width}} [{color}]{c.status}[/{color}]  [dim]{escape(c.detail)}[/dim]", highlight=False)


@app.command()
def doctor(fix: bool = typer.Option(False, "--fix", help="Repair what can be repaired (AddOn link, background service)."),
           check_ai: bool = typer.Option(False, "--check-ai", help="Ask the Claude CLI one small (paid) question to see if it is logged in.")) -> None:
    """Check WoW, the AddOn, SavedVariables, the archive, the watcher and the AI adapter."""
    paths = resolve_paths()
    checks = run_doctor(paths, check_ai=check_ai)
    _print_checks(checks)
    if fix:
        actions = apply_fixes(paths, checks)
        for a in actions:
            console.print(f"[green]fixed[/green] {a}")
        if actions:
            _print_checks(run_doctor(paths))
    if any(not c.ok and c.essential for c in checks):
        raise typer.Exit(1)


@app.command()
def setup(no_ai: bool = typer.Option(False, "--no-ai", help="Do not use the Claude CLI for chapters.")) -> None:
    """One command for a new Mac: link the AddOn, start the background watcher, build the journal index, open it."""
    paths = resolve_paths()
    archive = Archive(paths.archive_dir)
    archive.ensure()
    if paths.wow_dir is None:
        console.print("[red]World of Warcraft was not found.[/red] Install WoW: Forever, or set RAMBLEON_WOW_DIR to its folder "
                      "(the one that contains Interface/ and WTF/).")
        raise typer.Exit(1)
    console.print(f"WoW: {paths.wow_dir}")
    try:
        console.print(install_addon(paths))
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    try:
        console.print(svc.install(["--no-ai"] if no_ai else []))
    except RuntimeError as e:
        console.print(f"[yellow]background watcher not installed: {e}[/yellow] — you can run `ramble watch` in a terminal instead")
    index = write_html_index(archive, paths.exports_dir)
    console.print(f"journal: {index}")
    checks = run_doctor(paths, check_ai=True)
    _print_checks(checks)
    console.print()
    console.print("Next: start WoW (or log out to the character screen and back in so it sees the AddOn), then play. "
                  "Type /ramble in game. When you log out for the night, your chapter is written by itself.")
    if any(c.label == "Claude CLI" and c.status != "FOUND" for c in checks):
        console.print("For AI-written chapters, install Claude Code and log in: run `claude`, then `/login`. "
                      "Without it you still get the timeline, the story page, and a prompt you can paste into any assistant.")
    if sys.platform == "darwin":
        subprocess.run(["open", str(index)], check=False)


@app.command()
def uninstall(keep_archive: bool = typer.Option(True, "--keep-archive/--delete-archive",
                                                help="The archive (your history) is kept unless you say otherwise.")) -> None:
    """Remove the background service and the AddOn link. Your archive stays unless --delete-archive."""
    paths = resolve_paths()
    console.print(svc.uninstall())
    dest = paths.addon_install
    if dest and dest.is_symlink():
        dest.unlink()
        console.print(f"removed AddOn link {dest}")
    elif dest and dest.is_dir():
        console.print(f"AddOn copy left in place at {dest} (delete it yourself if you want it gone)")
    if not keep_archive:
        import shutil
        shutil.rmtree(paths.archive_dir, ignore_errors=True)
        console.print(f"deleted {paths.archive_dir}")
    else:
        console.print(f"archive kept at {paths.archive_dir}")


@app.command()
def install(copy: bool = typer.Option(False, "--copy", help="Copy the AddOn instead of symlinking it.")) -> None:
    """Link (or copy) the AddOn into the WoW Forever AddOns folder."""
    paths = resolve_paths()
    try:
        console.print(install_addon(paths, copy=copy))
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print("Now /reload in WoW (or restart it if Rambleon was not loaded before).")


def _finish_night(archive: Archive, paths, use_ai: bool, model: str | None = None, voice: str | None = None):
    """What happens when a night is over: export, journal, HTML, publish to the game."""
    def run(session: dict) -> None:
        night = resolve_night(archive, session["id"]) or session
        # Screenshots taken after the last SavedVariables write are only on disk: pair them now.
        if refresh_session_screenshots(archive, paths, night.get("sessionIds") or [session["id"]]):
            night = resolve_night(archive, session["id"]) or session
        md = export_session(night, paths.exports_dir)
        log(f"exported {md.name}")
        if use_ai:
            run_summarize(night, archive, paths.exports_dir, use_ai=True, model=model, log=log, voice=voice)
        try:   # the route guide: facts every time, prose only when this night is new to it; the story page links to it
            g = write_guide(archive, paths.exports_dir, night["character"].get("slug", "unknown"), use_ai=use_ai,
                            model=model, voice=voice, log=log, only_if_new=True)
            log(f"route guide {g['html']}")
        except Exception as e:  # noqa: BLE001 — the chapter must still be written and published
            log(f"route guide skipped: {e}")
        page = export_html(night, archive, paths.exports_dir)
        log(f"story page {page}")
        write_html_index(archive, paths.exports_dir)
        _, n = publish_chapters(archive, paths)
        log(f"published {n} chapter(s) to the game — they show under /ramble chapters after the next login or /reload")
        shared = ""
        if share_auto(paths.repo_root):   # this Mac opted in via rambleon.local.toml: the page goes to GitHub Pages
            try:
                result = run_share(archive, paths, [night["id"]], yes=True, log=log)
                log(f"share: {result.message}")
                for url in result.urls:
                    log(url)
                shared = " Shared." if result.pushed else ""
            except ShareError as e:
                log(f"share failed (the chapter is safe on this Mac): {e}")
        c = night.get("counters", {})
        notify("Rambleon", f"{night['character'].get('displayName')}: {duration(night.get('playedSeconds'))} in Azeroth, "
                           f"{c.get('questsCompleted', 0)} quests, {c.get('kills', 0)} kills. Chapter written.{shared}")
    return run


@app.command()
def watch(interval: float = typer.Option(1.0, help="Seconds between polls."),
          copy_screenshots: bool = typer.Option(True, "--copy-screenshots/--no-copy-screenshots", help="Copy matching screenshots into the archive."),
          no_ai: bool = typer.Option(False, "--no-ai", help="Do not call the Claude CLI when a chapter ends."),
          no_auto: bool = typer.Option(False, "--no-auto", help="Only archive; skip export/journal/publish."),
          model: str = typer.Option(None, "--model", help=f"Claude model for the chapter (default: [journal] model, else {DEFAULT_MODEL})."),
          voice: str = typer.Option(None, "--voice", help="Journal voice profile (see `ramble voices`; default: [journal] voice).")) -> None:
    """Watch SavedVariables and archive every session WoW writes. Leave this running while you play.
    When a chapter ends it also exports it, writes the journal, builds the story page and publishes it to the game."""
    archive, paths = _archive()
    if paths.wow_dir is None:
        console.print("[red]WoW directory not found[/red] (set RAMBLEON_WOW_DIR)")
        raise typer.Exit(1)
    finalizer = None if no_auto else Finalizer(_finish_night(archive, paths, use_ai=not no_ai, model=model, voice=voice), log,
                                               logged_out=lambda since: logged_out_since(paths.wow_dir, since))
    # `[x] auto = true` in rambleon.local.toml: a finished chapter is told on X once the night has gone quiet.
    poster = None if no_auto else xpost.AutoPoster(archive, paths, log, notify=notify,
                                                   in_world=lambda since: not logged_out_since(paths.wow_dir, since))

    seen_config: list = [None]

    def check_config() -> None:
        """Say it once when rambleon.local.toml changes into something that cannot be used."""
        cfg_path = paths.repo_root / "rambleon.local.toml"
        try:
            stamp = cfg_path.stat().st_mtime_ns
        except OSError:
            stamp = 0
        if stamp == seen_config[0]:
            return
        seen_config[0] = stamp
        cfg = load_config(paths.repo_root)
        if cfg.error:
            log(f"{cfg.error} — auto-share and auto-post are off until it is fixed")
            notify("Rambleon", "rambleon.local.toml cannot be read; auto-share and auto-post are off until it is fixed.")
        for w in cfg.warnings:
            log(f"rambleon.local.toml: {w}")
    check_config()

    def tick() -> None:
        check_config()
        finalizer.tick()
        poster.tick()
    try:
        run_watch(paths, archive, log, interval=interval, copy_screenshots=copy_screenshots,
                  after_capture=finalizer.on_capture if finalizer else None, tick=tick if finalizer else None)
    except KeyboardInterrupt:
        console.print("\nstopped.")


@app.command()
def publish() -> None:
    """Write the latest chapters into the AddOn (Chapters.lua) so /ramble chapters can show them in game."""
    archive, paths = _archive()
    path, n = publish_chapters(archive, paths)
    index = write_html_index(archive, paths.exports_dir)
    console.print(f"published {n} chapter(s) → {path}. In WoW: /reload, then /ramble chapters. Web index: {index}")


service_app = typer.Typer(help="Run the watcher in the background at login (launchd), no terminal needed.")
app.add_typer(service_app, name="service")


@service_app.command("install")
def service_install(no_ai: bool = typer.Option(False, "--no-ai")) -> None:
    """Install and start the background watcher (starts again at every login)."""
    try:
        console.print(svc.install(["--no-ai"] if no_ai else []))
    except RuntimeError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)


@service_app.command("uninstall")
def service_uninstall() -> None:
    """Stop and remove the background watcher."""
    console.print(svc.uninstall())


@service_app.command("status")
def service_status() -> None:
    """Is the background watcher installed and running?"""
    console.print(svc.status())


@app.command()
def config() -> None:
    """Show the settings in effect and where they come from (rambleon.local.toml; every key is optional)."""
    paths = resolve_paths()
    cfg = load_config(paths.repo_root)
    console.print(f"file: {cfg.path} ({'found' if cfg.exists else 'not there; these are the defaults'})", highlight=False, soft_wrap=True)
    if cfg.error:
        console.print(f"[red]{cfg.error}[/red]", highlight=False)
        raise typer.Exit(1)
    for section, values in effective(cfg).items():
        console.print(f"[{section}]", markup=False, highlight=False)
        for key, value in values.items():
            shown = "unset" if value is None else (", ".join(value) or "all" if isinstance(value, (list, tuple)) else str(value).lower() if isinstance(value, bool) else value)
            console.print(f"  {key} = {shown}", markup=False, highlight=False)
    for slug, fields in cfg.characters.items():
        console.print(f'[characters."{slug}"] ' + ", ".join(f"{k} = {v}" for k, v in fields.items()), markup=False, highlight=False)
    for name, note in cfg.people.items():
        console.print(f'[people."{name}"] note = {note}', markup=False, highlight=False)
    for w in cfg.warnings:
        console.print(f"[yellow]warning[/yellow] {escape(w)}", highlight=False)


@app.command()
def voices() -> None:
    """List journal voice profiles (companion/src/rambleon/prompts/voices/*.md). Default: golden."""
    for v in available_voices():
        marker = " (default)" if v == DEFAULT_VOICE else ""
        console.print(f"{v}{marker}")


@app.command()
def nights() -> None:
    """List chapters: one per night, per character."""
    archive, _ = _archive()
    rows = list_nights(archive)
    if not rows:
        console.print("no nights archived yet.")
        return
    table = Table(box=None, header_style="bold")
    for col in ("Night", "Character", "Duration", "Lv", "Quests", "Places", "Kills", "Deaths", "People", "Sessions", "State"):
        table.add_column(col)
    for n in rows:
        c = n["counters"]; ch = n["character"]
        lv = f"{ch.get('startLevel', '?')}→{ch.get('endLevel', '?')}" if ch.get("startLevel") != ch.get("endLevel") else str(ch.get("endLevel", "?"))
        table.add_row(n["nightDate"], str(ch.get("displayName")), duration(n.get("playedSeconds")), lv, str(c.get("questsCompleted", 0)),
                      str(len(n["zones"])), str(c.get("kills", 0)), str(c.get("deaths", 0)), str(len(n["people"])),
                      str(len(n["sessionIds"])), n["state"])
    console.print(table)


@app.command()
def page(ref: str = typer.Argument("latest"), open_it: bool = typer.Option(True, "--open/--no-open")) -> None:
    """Build the HTML story page for a night (journal, recap, screenshots, timeline) and open it in the browser."""
    archive, paths = _archive()
    session = _night(ref)
    if refresh_session_screenshots(archive, paths, session.get("sessionIds") or []):
        session = _night(ref)
    out = export_html(session, archive, paths.exports_dir)
    console.print(f"story page {out}")
    if open_it and sys.platform == "darwin":
        subprocess.run(["open", str(out)], check=False)


@app.command()
def share(refs: list[str] = typer.Argument(None, help="tonight | latest | YYYY-MM-DD | night id (default: tonight)"),
          all_nights: bool = typer.Option(False, "--all", help="Every night; replaces site/example entirely."),
          yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before pushing."),
          dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be copied and run; change nothing.")) -> None:
    """Put a night's story page (with its pictures) on your public GitHub Pages site. Manual on purpose:
    this is the moment the chapter leaves your Mac."""
    archive, paths = _archive()
    try:
        result = run_share(archive, paths, list(refs or []), all_nights=all_nights, yes=yes, dry_run=dry_run, log=log,
                           confirm=lambda q: typer.confirm(q, default=False))
    except ShareError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    if dry_run:
        for cmd in result.commands:
            console.print("  " + " ".join(cmd))
    console.print(result.message)
    for url in result.urls:
        console.print(url)


@app.command()
def post(ref: str = typer.Argument("tonight", help="tonight | latest | YYYY-MM-DD | night id"),
         style: str = typer.Option(None, "--style", help="post (one post, the night in miniature) or thread (the whole chapter)."),
         link: bool = typer.Option(None, "--link/--no-link", help="Add the shared story page's address. X charges far more for a post with a link."),
         picture: bool = typer.Option(None, "--picture/--no-picture", help="Attach the night's hero screenshot."),
         lowercase: bool = typer.Option(None, "--lowercase/--no-lowercase", help="All lower case, the way you write on X."),
         yes: bool = typer.Option(False, "--yes", "-y", help="Do not ask before posting."),
         dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be posted; post nothing."),
         force: bool = typer.Option(False, "--force", help="Post a night that was already posted.")) -> None:
    """Tell a night on X: the chapter in miniature with its hero picture, or the whole chapter as a thread.
    Defaults come from [x] in rambleon.local.toml. Needs your X developer keys once: `ramble x login`."""
    archive, paths = _archive()
    cfg = _x_config(paths)
    style = style or cfg["style"]
    if style not in X_STYLES:
        console.print(f"[red]unknown style {style!r}[/red]; choose from: {', '.join(X_STYLES)}")
        raise typer.Exit(1)
    night = _night(ref)

    def confirm(question: str) -> bool:
        return typer.confirm(question, default=False)
    link = cfg["link"] if link is None else link
    picture = cfg["picture"] if picture is None else picture
    lowercase = cfg["lowercase"] if lowercase is None else lowercase
    preview = xpost.post_night(archive, paths, night, style=style, link=link, picture=picture, lowercase=lowercase,
                               dry_run=True, force=force, log=log)
    for n, text in enumerate(preview.texts, 1):
        console.print(f"[dim]— {n}/{len(preview.texts)} · {xpost.weighted_len(text)} of {xpost.LIMIT} —[/dim]")
        console.print(text, markup=False, highlight=False, soft_wrap=True)
    console.print(f"[dim]picture: {preview.image or 'none'}[/dim]", soft_wrap=True)
    if dry_run or not preview.message.startswith("dry run"):
        console.print(preview.message)
        return
    try:
        result = xpost.post_night(archive, paths, night, style=style, link=link and "https://" in preview.texts[-1],
                                  picture=picture, lowercase=lowercase, force=force, yes=yes, confirm=confirm, log=log)
    except xpost.XError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(result.message)


x_app = typer.Typer(help="Your X account: the keys `ramble post` and the watcher's auto-post use.")
app.add_typer(x_app, name="x")


@x_app.command("login")
def x_login(check: bool = typer.Option(True, "--check/--no-check", help="Ask X who the keys belong to (one small paid request).")) -> None:
    """Store the four keys of your X developer app in the macOS Keychain."""
    console.print("At console.x.com: create an app, set its user authentication to [bold]Read and write[/bold], then generate\n"
                  "the API Key and Secret and the Access Token and Secret (in that order: a token made before the permission\n"
                  "change stays read-only), and add a few dollars of credits. Paste the four values here; they go into your\n"
                  "Keychain and nowhere else.")
    creds = {
        "api_key": typer.prompt("API Key", hide_input=True),
        "api_secret": typer.prompt("API Key Secret", hide_input=True),
        "access_token": typer.prompt("Access Token", hide_input=True),
        "access_secret": typer.prompt("Access Token Secret", hide_input=True),
    }
    try:
        xpost.store_credentials(creds)
        console.print("stored in the Keychain.")
        if check:
            console.print(f"X knows these keys as [bold]@{xpost.XClient(creds).me()}[/bold].")
    except xpost.XError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    archive, paths = _archive()
    cfg = _x_config(paths)
    if cfg["auto"]:
        due = [f"{n['character'].get('displayName')} ({n['nightDate']})" for n in xpost.due_nights(archive, paths.exports_dir, cfg)]
        console.print("Auto-post is on. " + (f"The watcher posts these within a minute or two: {', '.join(due)}." if due else
                      "Nothing is waiting; the next finished chapter is posted once the night has gone quiet."), markup=False)
    else:
        console.print("Try `ramble post tonight --dry-run`, then `ramble post tonight`. For posting by itself, put\n"
                      "[x] auto = true in rambleon.local.toml.", markup=False)


@x_app.command("logout")
def x_logout() -> None:
    """Remove the X keys from the Keychain."""
    console.print(f"removed {xpost.delete_credentials()} key(s) from the Keychain.")


@x_app.command("status")
def x_status() -> None:
    """Are the keys here, is auto-post on, and what was posted last?"""
    archive, paths = _archive()
    cfg = _x_config(paths)
    console.print(f"keys: {'found' if xpost.load_credentials() else 'none (run `ramble x login`)'}")
    console.print(f"auto-post: {'on' if cfg['auto'] else 'off ([x] auto = true in rambleon.local.toml turns it on)'}", markup=False)
    console.print(f"style: {cfg['style']} · link: {'yes' if cfg['link'] else 'no'} · picture: {'yes' if cfg['picture'] else 'no'} · lower case: {'yes' if cfg['lowercase'] else 'no'} · "
                  f"quiet before posting: {cfg['delay']:g} min · characters: {', '.join(cfg['characters']) or 'all'}", soft_wrap=True)
    ledger = xpost.load_ledger(archive)
    for night_id, entry in sorted(ledger.items(), key=lambda kv: kv[1].get("postedAt") or 0)[-5:]:
        ids = entry.get("ids") or []
        when = datetime.fromtimestamp(entry.get("postedAt") or 0)
        console.print(f"{when:%Y-%m-%d %H:%M}  {night_id}  https://x.com/i/status/{ids[0] if ids else '?'}", highlight=False)
    if not ledger:
        console.print("nothing posted yet.")


@app.command()
def ingest(copy_screenshots: bool = typer.Option(True, "--copy-screenshots/--no-copy-screenshots")) -> None:
    """Archive whatever Rambleon SavedVariables exist right now (one pass, no watching)."""
    archive, paths = _archive()
    outcomes = ingest_once(paths, archive, log, copy_screenshots)
    if outcomes:
        console.print(f"{len(outcomes)} outcome(s): " + ", ".join(outcomes))
    else:
        console.print("nothing new.")


@app.command()
def reprocess(copy_screenshots: bool = typer.Option(True, "--copy-screenshots/--no-copy-screenshots")) -> None:
    """Rebuild normalized sessions from the archived raw snapshots (use after upgrading the companion)."""
    archive, paths = _archive()
    run_reprocess(paths, archive, log, copy_screenshots)


@app.command()
def status() -> None:
    """Archive overview and the latest session."""
    archive, paths = _archive()
    sessions = archive.list_sessions()
    pid = archive.watcher_pid()
    console.print(f"Archive: {paths.archive_dir} — {len(sessions)} session(s)")
    console.print(f"Watcher: {'running (pid ' + str(pid) + ')' if pid else 'not running'}")
    sv = paths.saved_variables_files()
    if sv:
        newest = max(sv, key=lambda p: p.stat().st_mtime)
        console.print(f"SavedVariables last written: {datetime.fromtimestamp(newest.stat().st_mtime):%Y-%m-%d %H:%M:%S}")
    total = sum(s.get("playedSeconds") or 0 for s in sessions)
    if sessions:
        console.print(f"Total time in Azeroth (archived): {duration(total)}")
        s = sessions[-1]
        console.print(f"Latest: {s['character']} — {datetime.fromtimestamp(s['startedAt']):%B %-d, %Y %-I:%M %p} — "
                      f"{duration(s.get('playedSeconds'))} — {s['events']} events — {s['state']}")


@app.command()
def sessions() -> None:
    """List archived sessions."""
    archive, _ = _archive()
    rows = archive.list_sessions()
    if not rows:
        console.print("no sessions archived yet.")
        return
    table = Table(box=None, header_style="bold")
    for col in ("When", "Character", "Duration", "Lv", "Quests", "Places", "Deaths", "People", "Events", "State", "Session ID"):
        table.add_column(col)
    for s in rows:
        c = s.get("counters", {})
        lv = f"{s.get('startLevel', '?')}→{s.get('endLevel', '?')}" if s.get("startLevel") != s.get("endLevel") else str(s.get("endLevel", "?"))
        table.add_row(datetime.fromtimestamp(s["startedAt"]).strftime("%Y-%m-%d %H:%M"), str(s.get("character")),
                      duration(s.get("playedSeconds")), lv, str(c.get("questsCompleted", 0)), str(c.get("zonesVisited", 0)),
                      str(c.get("deaths", 0)), str(s.get("people", 0)), str(s.get("events")),
                      ("trivial" if s.get("trivial") else str(s.get("state"))), str(s.get("id")))
    console.print(table)


@app.command()
def show(ref: str = typer.Argument("latest"), as_json: bool = typer.Option(False, "--json")) -> None:
    """Show one session (default: latest) as a factual log, or as JSON."""
    session = _load(ref)
    if as_json:
        console.print_json(json.dumps(session))
    else:
        console.print(render_markdown(session), markup=False, highlight=False)


@app.command()
def export(ref: str = typer.Argument("latest"), all_nights: bool = typer.Option(False, "--all")) -> None:
    """Write the factual Markdown log of a night (latest | tonight | YYYY-MM-DD | session id) to exports/markdown/."""
    archive, paths = _archive()
    targets = list_nights(archive) if all_nights else [_night(ref)]
    for night in targets:
        out = export_session(night, paths.exports_dir)
        console.print(f"exported {out}")


def _copy_to_clipboard(text: str) -> bool:
    if sys.platform != "darwin":
        return False
    try:
        env = {**os.environ, "LANG": "en_US.UTF-8"}  # pbcopy reads its input in the locale's encoding
        return subprocess.run(["pbcopy"], input=text.encode("utf-8"), check=False, env=env).returncode == 0
    except OSError:
        return False


@app.command()
def catchup(ref: str = typer.Argument("latest", help="tonight | latest | YYYY-MM-DD | night id"),
            copy: bool = typer.Option(False, "--copy/--no-copy", help="Also put the text on the clipboard (macOS).")) -> None:
    """A plain-text list of the quests turned in one night, grouped by zone, to paste to a friend who wants to catch up."""
    archive, paths = _archive()
    night = _night(ref)
    text = render_catchup(night, carried_over(earlier_nights(archive, night), night))
    out = paths.exports_dir / "social" / export_filename(night, "-catchup").replace(".md", ".txt")
    atomic_write_bytes(out, text.encode("utf-8"))
    console.print(text, markup=False, highlight=False, soft_wrap=True)
    console.print(f"[dim]saved {out}[/dim]", soft_wrap=True)
    if copy:
        console.print("copied to the clipboard." if _copy_to_clipboard(text) else "[yellow]could not copy (pbcopy unavailable).[/yellow]")


def _slug(archive: Archive, ref: str) -> str:
    """A character slug from `latest` (the character who played last) or a slug seen in the archive."""
    if ref in ("latest", "tonight", "last", ""):
        night = resolve_night(archive, "latest")
        if night is None:
            console.print("[red]no nights archived yet[/red] — play a session first, or run `ramble ingest`")
            raise typer.Exit(1)
        return night["character"].get("slug", "unknown")
    known = sorted({n["character"].get("slug") for n in list_nights(archive) if n["character"].get("slug")})
    if ref in known:
        return ref
    console.print(f"[red]no character matches {ref!r}[/red] — known: {', '.join(known) or 'none yet'}")
    raise typer.Exit(1)


@app.command()
def guide(ref: str = typer.Argument("latest", help="character slug | latest"),
          no_ai: bool = typer.Option(False, "--no-ai", help="Only the factual guide and the prompt; do not call the Claude CLI."),
          model: str = typer.Option(None, "--model", help=f"Claude model (default: [journal] model, else {DEFAULT_MODEL})."),
          voice: str = typer.Option(None, "--voice", help="Tone profile (see `ramble voices`)."),
          mode: str = typer.Option(None, "--mode", help="What to write from the facts: a bundled mode (--list) or a path to your own .md prompt."),
          list_modes: bool = typer.Option(False, "--list", help="List the bundled guide modes and exit."),
          open_it: bool = typer.Option(False, "--open", help="Open the guide page in the browser.")) -> None:
    """The route guide of a character: how they actually leveled, one zone stretch per chapter, across every night."""
    if list_modes:
        for m in available_modes():
            console.print(f"{m}{'  (default)' if m == default_mode() else ''}")
        console.print("Or --mode /path/to/your-prompt.md; placeholders: {voice} {name} {pronouns} {startLevel} {endLevel} {nights}.",
                      markup=False, highlight=False)
        return
    archive, paths = _archive()
    slug = _slug(archive, ref)
    try:
        result = write_guide(archive, paths.exports_dir, slug, use_ai=not no_ai, model=model, voice=voice, mode=mode, log=log)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    for k, v in result.items():
        if v:
            console.print(f"{k}: {v}")
    write_html_index(archive, paths.exports_dir)
    if open_it and sys.platform == "darwin":
        subprocess.run(["open", str(result["html"])], check=False)


@app.command()
def summarize(ref: str = typer.Argument("latest"),
              no_ai: bool = typer.Option(False, "--no-ai", help="Only write the prompt; do not call the Claude CLI."),
              model: str = typer.Option(None, "--model", help=f"Claude model (default: [journal] model, else {DEFAULT_MODEL})."),
              voice: str = typer.Option(None, "--voice", help="Journal voice profile (see `ramble voices`).")) -> None:
    """Write the journal prompt for a night and, if the Claude CLI is available, the AI-written chapter."""
    archive, paths = _archive()
    session = _night(ref)
    try:
        result = run_summarize(session, archive, paths.exports_dir, use_ai=not no_ai, model=model, log=log, voice=voice)
    except ValueError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    for k, v in result.items():
        if v:
            console.print(f"{k}: {v}")
    page_path = export_html(session, archive, paths.exports_dir)
    console.print(f"story page: {page_path}")
    _, n = publish_chapters(archive, paths)
    console.print(f"published {n} chapter(s) to the game — /reload in WoW, then /ramble chapters")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
