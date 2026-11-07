"""Locate the WoW: Forever install, Rambleon's SavedVariables, screenshots and our archive."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ADDON_NAME = "Rambleon"
DEFAULT_WOW_ROOT = Path("/Applications/World of Warcraft")
# Live Forever has its own product folder (wowf, since launch on 4 Nov 2026); the beta folder it shipped under
# before can linger after the beta ends, so it comes second. Keep the others as fallbacks.
FLAVOR_PREFERENCE = ["_forever_", "_classic_beta_", "_beta_", "_classic_", "_classic_era_", "_retail_", "_ptr_"]


def find_repo_root() -> Path:
    """Where Rambleon keeps its files: the source checkout when running from one, else ~/Rambleon.
    (RAMBLEON_HOME overrides.) A non-developer install gets the AddOn from the package itself (see bundled_addon)."""
    env = os.environ.get("RAMBLEON_HOME")
    if env:
        return Path(env).expanduser()
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "addon" / ADDON_NAME / f"{ADDON_NAME}.toc").exists():
            return parent
    return Path.home() / "Rambleon"


def bundled_addon() -> Path | None:
    """The AddOn shipped inside the Python package (for installs without the repository)."""
    p = Path(__file__).resolve().parent / "addon" / ADDON_NAME
    return p if (p / f"{ADDON_NAME}.toc").exists() else None


def candidate_wow_dirs() -> list[Path]:
    env = os.environ.get("RAMBLEON_WOW_DIR")
    if env:
        return [Path(env).expanduser()]
    roots = [DEFAULT_WOW_ROOT, Path.home() / "Applications" / "World of Warcraft"]
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for flavor in FLAVOR_PREFERENCE:
            d = root / flavor
            if d.is_dir():
                found.append(d)
        for d in sorted(root.glob("_*_")):
            if d.is_dir() and d not in found:
                found.append(d)
    return found


def find_wow_dir() -> Path | None:
    for d in candidate_wow_dirs():
        if (d / "WTF").is_dir() or (d / "Interface").is_dir() or (d / ".flavor.info").exists():
            return d
    return None


def read_flavor(wow_dir: Path) -> str | None:
    f = wow_dir / ".flavor.info"
    if not f.exists():
        return None
    try:
        lines = [ln.strip() for ln in f.read_text(errors="replace").splitlines() if ln.strip()]
        return lines[-1] if lines else None
    except OSError:
        return None


def read_build_version(wow_dir: Path) -> str | None:
    """Version string like 1.60.1.69913 from the parent .build.info (if present)."""
    for candidate in (wow_dir.parent / ".build.info", wow_dir / ".build.info"):
        if candidate.exists():
            try:
                lines = candidate.read_text(errors="replace").splitlines()
            except OSError:
                continue
            if len(lines) >= 2:
                header = lines[0].split("|")
                row = lines[1].split("|")
                for name, value in zip(header, row):
                    if name.startswith("Version"):
                        return value
    return None


@dataclass
class Paths:
    repo_root: Path
    wow_dir: Path | None
    archive_dir: Path
    exports_dir: Path

    @property
    def addon_src(self) -> Path:
        """Where the live AddOn files are: the checkout, or ~/Rambleon/addon/Rambleon seeded from the package."""
        return self.repo_root / "addon" / ADDON_NAME

    @property
    def addons_dir(self) -> Path | None:
        return self.wow_dir / "Interface" / "AddOns" if self.wow_dir else None

    @property
    def addon_install(self) -> Path | None:
        return self.addons_dir / ADDON_NAME if self.addons_dir else None

    @property
    def wtf_dir(self) -> Path | None:
        return self.wow_dir / "WTF" if self.wow_dir else None

    @property
    def screenshots_dir(self) -> Path | None:
        return self.wow_dir / "Screenshots" if self.wow_dir else None

    @property
    def config_wtf(self) -> Path | None:
        return self.wow_dir / "WTF" / "Config.wtf" if self.wow_dir else None

    def saved_variables_files(self, include_bak: bool = False) -> list[Path]:
        """Every Rambleon SavedVariables file: account-wide and per-character."""
        wtf = self.wtf_dir
        if not wtf or not wtf.is_dir():
            return []
        names = [f"{ADDON_NAME}.lua"] + ([f"{ADDON_NAME}.lua.bak"] if include_bak else [])
        out: list[Path] = []
        for name in names:
            out.extend(wtf.glob(f"Account/*/SavedVariables/{name}"))
            out.extend(wtf.glob(f"Account/*/*/*/SavedVariables/{name}"))
        return sorted(set(out))

    def redact(self, p: Path | str) -> str:
        """Hide the Battle.net account folder name in printed paths."""
        s = str(p)
        wtf = self.wtf_dir
        if wtf:
            prefix = str(wtf / "Account") + os.sep
            if s.startswith(prefix):
                rest = s[len(prefix):]
                parts = rest.split(os.sep, 1)
                rest = "<ACCOUNT>" + (os.sep + parts[1] if len(parts) > 1 else "")
                return prefix + rest
        return s


def resolve_paths() -> Paths:
    repo = find_repo_root()
    archive = Path(os.environ.get("RAMBLEON_ARCHIVE_DIR", repo / "archive")).expanduser()
    exports = Path(os.environ.get("RAMBLEON_EXPORTS_DIR", repo / "exports")).expanduser()
    return Paths(repo_root=repo, wow_dir=find_wow_dir(), archive_dir=archive, exports_dir=exports)
