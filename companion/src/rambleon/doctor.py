"""ramble doctor: is everything where Rambleon expects it?"""
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .archive import Archive
from .config import load_config
from .install import link_status
from .paths import ADDON_NAME, Paths, read_build_version, read_flavor


@dataclass
class Check:
    label: str
    status: str      # FOUND / INSTALLED / READY / MISSING / ...
    detail: str
    ok: bool
    essential: bool = True
    fix: str | None = None   # name of a repair `ramble doctor --fix` can apply


def _toc_interface(paths: Paths) -> str | None:
    for name in (f"{ADDON_NAME}_Camelot.toc", f"{ADDON_NAME}.toc"):
        toc = paths.addon_src / name
        if toc.exists():
            m = re.search(r"^## Interface:\s*(\d+)", toc.read_text(errors="replace"), re.M)
            if m:
                return m.group(1)
    return None


def _character_folders(paths: Paths) -> list[str]:
    wtf = paths.wtf_dir
    if not wtf or not wtf.is_dir():
        return []
    names = []
    for char_dir in wtf.glob("Account/*/*/*/"):
        if char_dir.name in ("SavedVariables",) or char_dir.parent.name == "SavedVariables":
            continue
        if (char_dir / "SavedVariables").is_dir() or any(char_dir.glob("*.txt")):
            names.append(f"{char_dir.name} (realm folder {char_dir.parent.name})")
    return sorted(set(names))


def run_doctor(paths: Paths, check_ai: bool = False) -> list[Check]:
    """check_ai asks the Claude CLI one tiny (paid) question to see whether it is logged in."""
    checks: list[Check] = []
    wow = paths.wow_dir
    if wow:
        flavor = read_flavor(wow) or "unknown flavor"
        version = read_build_version(wow) or "unknown version"
        checks.append(Check("WoW Forever", "FOUND", f"{wow} ({flavor}, {version})", True))
    else:
        checks.append(Check("WoW Forever", "MISSING", "no WoW install found; set RAMBLEON_WOW_DIR", False))

    state, detail = link_status(paths)
    toc = _toc_interface(paths)
    ok = state in ("linked", "copied")
    label = {"linked": "INSTALLED (symlink)", "copied": "INSTALLED (copy)", "missing": "NOT INSTALLED",
             "broken": "BROKEN LINK", "foreign": "SOMETHING ELSE", "no-wow": "NO WOW"}[state]
    checks.append(Check("Rambleon AddOn", label, f"{detail}; TOC Interface {toc or '?'}" if ok else detail + " — run `ramble install`", ok,
                        fix=None if ok else "install"))

    sv = paths.saved_variables_files()
    if sv:
        newest = max(sv, key=lambda p: p.stat().st_mtime)
        when = datetime.fromtimestamp(newest.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        checks.append(Check("SavedVariables", "FOUND", f"{len(sv)} file(s); newest {paths.redact(newest)} at {when}", True))
    else:
        checks.append(Check("SavedVariables", "NOT YET WRITTEN",
                            "no Rambleon.lua under WTF yet — WoW writes it when you /reload, log out or quit", True, essential=False))

    shots = paths.screenshots_dir
    if shots and shots.is_dir():
        n = len([p for p in shots.iterdir() if p.name.startswith("WoWScrnShot_")])
        checks.append(Check("Screenshots", "FOUND", f"{shots} ({n} screenshots)", True, essential=False))
    else:
        checks.append(Check("Screenshots", "NOT YET CREATED", f"{shots} appears after your first in-game screenshot", True, essential=False))

    archive = Archive(paths.archive_dir)
    try:
        archive.ensure()
        sessions = archive.list_sessions()
        checks.append(Check("Archive", "READY", f"{paths.archive_dir} ({len(sessions)} session(s))", True))
    except OSError as e:
        checks.append(Check("Archive", "NOT WRITABLE", f"{paths.archive_dir}: {e}", False))

    pid = archive.watcher_pid()
    from . import service as svc
    try:
        loaded = svc.is_loaded()
    except OSError:   # no launchctl here
        loaded = False
    if loaded:
        detail = f"background service (pid {pid})" if pid else "background service (starting)"
        checks.append(Check("Watcher", "RUNNING", detail, True, essential=False))
    elif pid:
        checks.append(Check("Watcher", "RUNNING", f"ramble watch in a terminal (pid {pid})", True, essential=False))
    elif svc.PLIST.exists():
        checks.append(Check("Watcher", "SERVICE STOPPED", "run `ramble service install` again", False, essential=False, fix="service"))
    else:
        checks.append(Check("Watcher", "NOT RUNNING", "`ramble service install` runs it in the background at login", False, essential=False, fix="service"))

    chars = _character_folders(paths)
    latest = archive.list_sessions()[-1] if archive.list_sessions() else None
    if latest:
        checks.append(Check("Character", "KNOWN", f"{latest.get('character')} (last session {datetime.fromtimestamp(latest.get('startedAt') or 0):%Y-%m-%d})", True, essential=False))
    elif chars:
        checks.append(Check("Character", "SEEN IN WTF", ", ".join(chars), True, essential=False))
    else:
        checks.append(Check("Character", "UNKNOWN", "no sessions archived yet", True, essential=False))

    cfg = load_config(paths.repo_root)
    if cfg.error:
        checks.append(Check("Config", "CANNOT BE READ", f"{cfg.error} — auto-share and auto-post are off until it is fixed", False, essential=False))
    elif cfg.warnings:
        checks.append(Check("Config", f"{len(cfg.warnings)} WARNING(S)", f"{cfg.path}: " + "; ".join(cfg.warnings), False, essential=False))
    elif cfg.exists:
        checks.append(Check("Config", "FOUND", f"{cfg.path} (`ramble config` shows what is in effect)", True, essential=False))
    else:
        checks.append(Check("Config", "DEFAULTS", f"optional; settings would live in {cfg.path}", True, essential=False))

    claude = shutil.which("claude")
    if claude:
        try:
            v = subprocess.run([claude, "--version"], capture_output=True, text=True, timeout=10).stdout.strip()
        except (OSError, subprocess.TimeoutExpired):
            v = "version unknown"
        logged_in = _claude_logged_in(claude) if check_ai else None
        if logged_in is False:
            checks.append(Check("Claude CLI", "NOT LOGGED IN", f"{claude} ({v}) — run `claude`, then `/login`; chapters are prompt-only until then", True, essential=False))
        else:
            note = "" if check_ai else "; login not checked (`ramble doctor --check-ai` asks it one small question)"
            checks.append(Check("Claude CLI", "FOUND", f"{claude} ({v}){note}", True, essential=False))
    else:
        checks.append(Check("Claude CLI", "NOT FOUND", "optional; `ramble summarize` will still write the prompt", True, essential=False))
    return checks


def _claude_logged_in(claude: str) -> bool | None:
    """True/False when we can tell, None when unsure. Costs one tiny request."""
    try:
        r = subprocess.run([claude, "-p", "--tools", "", "--output-format", "json", "--no-session-persistence",
                            "--max-budget-usd", "0.01", "--model", "haiku"],
                           input="Reply with the single word OK.", capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (r.stdout or "") + (r.stderr or "")
    if "Not logged in" in out or "401" in out or "revoked" in out or "authenticate" in out.lower():
        return False
    if r.returncode == 0:
        return True
    return None


def apply_fixes(paths: Paths, checks: list[Check]) -> list[str]:
    """Repair what `--fix` knows how to repair. Returns a line per action."""
    from .install import install_addon
    from . import service as svc
    done: list[str] = []
    for c in checks:
        if c.ok or not c.fix:
            continue
        try:
            if c.fix == "install":
                done.append(install_addon(paths))
            elif c.fix == "service":
                done.append(svc.install())
        except Exception as e:  # report, keep going
            done.append(f"could not fix {c.label}: {e}")
    return done
