"""Run `ramble watch` as a launchd user agent so nothing has to stay open in a terminal."""
from __future__ import annotations

import os
import plistlib
import shutil
import subprocess
from pathlib import Path

LABEL = "com.rambleon.watch"
PLIST = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
LOG_DIR = Path.home() / "Library" / "Logs" / "Rambleon"


def _ramble_path() -> str:
    exe = shutil.which("ramble") or str(Path.home() / ".local" / "bin" / "ramble")
    return exe


def _domain() -> str:
    return f"gui/{os.getuid()}"


def _launchctl(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["launchctl", *args], capture_output=True, text=True)


def install(extra_args: list[str] | None = None) -> str:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    PLIST.parent.mkdir(parents=True, exist_ok=True)
    path_env = ":".join(p for p in [str(Path.home() / ".local" / "bin"), "/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin"] if p)
    plist = {
        "Label": LABEL,
        "ProgramArguments": [_ramble_path(), "watch", *(extra_args or [])],
        "RunAtLoad": True,
        "KeepAlive": True,
        "ProcessType": "Background",
        "StandardOutPath": str(LOG_DIR / "watch.log"),
        "StandardErrorPath": str(LOG_DIR / "watch.log"),
        "EnvironmentVariables": {"PATH": path_env, "HOME": str(Path.home())},
    }
    for key in ("RAMBLEON_HOME", "RAMBLEON_WOW_DIR", "RAMBLEON_ARCHIVE_DIR", "RAMBLEON_EXPORTS_DIR",
                "RAMBLEON_VOICE", "RAMBLEON_MODEL", "RAMBLEON_GUIDE_MODE"):
        if os.environ.get(key):
            plist["EnvironmentVariables"][key] = os.environ[key]
    if is_loaded():
        _launchctl("bootout", _domain(), str(PLIST))
    with open(PLIST, "wb") as fh:
        plistlib.dump(plist, fh)
    r = _launchctl("bootstrap", _domain(), str(PLIST))
    if r.returncode != 0:
        r = _launchctl("load", "-w", str(PLIST))
        if r.returncode != 0:
            raise RuntimeError(f"launchctl failed: {(r.stderr or r.stdout).strip()}")
    return f"installed {LABEL}; it starts at login and keeps running. Log: {LOG_DIR / 'watch.log'}"


def uninstall() -> str:
    if PLIST.exists():
        r = _launchctl("bootout", _domain(), str(PLIST))
        if r.returncode != 0:
            _launchctl("unload", "-w", str(PLIST))
        PLIST.unlink()
        return f"removed {LABEL}"
    return "service was not installed"


def is_loaded() -> bool:
    r = _launchctl("print", f"{_domain()}/{LABEL}")
    return r.returncode == 0


def status() -> str:
    if not PLIST.exists():
        return "not installed (run `ramble service install`)"
    return f"{'running' if is_loaded() else 'installed but not loaded'} — log at {LOG_DIR / 'watch.log'}"
