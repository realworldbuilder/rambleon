"""`ramble share`: put story pages (and their pictures) on the public GitHub Pages site.

This is the one step that makes a night public, so it is manual and asks first. It copies the night's
page and image folder from exports/html into site/example/ in the Rambleon git checkout, commits, and
pushes; the Pages workflow deploys site/ from main."""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .archive import Archive
from .export import export_filename
from .nights import nights as list_nights, resolve_night
from .publish import export_html, write_html_index
from .screenshots import refresh_session_screenshots

Runner = Callable[..., subprocess.CompletedProcess]
EXAMPLE_DIR = Path("site") / "example"


class ShareError(RuntimeError):
    pass


@dataclass
class ShareResult:
    checkout: Path
    pages: list[str] = field(default_factory=list)       # page file names copied
    files: list[str] = field(default_factory=list)       # everything staged, relative to the checkout
    commands: list[list[str]] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    committed: bool = False
    pushed: bool = False
    message: str = ""


def _git(runner: Runner, checkout: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    r = runner(["git", "-C", str(checkout), *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        raise ShareError(f"git {' '.join(args)} failed: {(r.stderr or r.stdout).strip()}")
    return r


def repo_checkout(repo_root: Path, runner: Runner = subprocess.run) -> Path:
    """The git checkout that holds site/ and the Pages workflow, or a clear error for package installs."""
    r = runner(["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"], capture_output=True, text=True)
    top = Path(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None
    if top is None or not (top / "site").is_dir() or not (top / ".github" / "workflows" / "pages.yml").exists():
        raise ShareError("ramble share needs the Rambleon git checkout (the one with site/ and the Pages workflow). "
                         "Clone https://github.com/realworldbuilder/rambleon and point RAMBLEON_HOME at it.")
    return top


def pages_url(remote_url: str, page_name: str = "") -> str | None:
    """https://<owner>.github.io/<repo>/example/<page> from a GitHub remote, else None."""
    m = re.search(r"github\.com[:/]([^/]+)/([^/\s]+?)(?:\.git)?$", remote_url.strip())
    if not m:
        return None
    owner, repo = m.group(1), m.group(2)
    return f"https://{owner}.github.io/{repo}/example/{page_name}"


def _select_nights(archive: Archive, refs: list[str], all_nights: bool) -> list[dict[str, Any]]:
    if all_nights:
        return list_nights(archive)
    out, seen = [], set()
    for ref in refs or ["tonight"]:
        night = resolve_night(archive, ref)
        if night is None:
            raise ShareError(f"no night matches {ref!r} (try `ramble nights`)")
        if night["id"] not in seen:
            seen.add(night["id"])
            out.append(night)
    return out


def share(archive: Archive, paths: Any, refs: list[str], all_nights: bool = False, yes: bool = False, dry_run: bool = False,
          log: Callable[[str], None] = lambda m: None, confirm: Callable[[str], bool] | None = None,
          runner: Runner = subprocess.run) -> ShareResult:
    checkout = repo_checkout(paths.repo_root, runner)
    result = ShareResult(checkout=checkout)
    nights_ = _select_nights(archive, refs, all_nights)
    if not nights_:
        raise ShareError("no nights archived yet")
    remote = _git(runner, checkout, "remote", "get-url", "origin", check=False).stdout
    example = checkout / EXAMPLE_DIR
    html_dir = paths.exports_dir / "html"

    # What the site will hold afterwards: pages already there plus tonight's (a whole-site replace only with --all).
    wanted = {export_filename(n).replace(".md", ".html") for n in nights_}
    present = set() if all_nights or not example.is_dir() else {p.name for p in example.glob("*.html") if p.name != "index.html"}
    present |= wanted

    # 1. Fresh pages, with late screenshots paired. Neighbouring chapters already on the site are re-rendered too,
    #    so their previous/next links pick up tonight's chapter.
    refresh = list(nights_) + [n for n in list_nights(archive)
                               if export_filename(n).replace(".md", ".html") in present - wanted]
    for night in refresh:
        ids = night.get("sessionIds") or []
        if refresh_session_screenshots(archive, paths, ids):
            night = resolve_night(archive, night["id"]) or night
        page = export_html(night, archive, paths.exports_dir, siblings=present)
        result.pages.append(page.name)

    # 2. Copy into site/example.
    plan: list[tuple[Path, Path]] = []
    for name in result.pages:
        page = html_dir / name
        plan.append((page, example / name))
        images = page.with_suffix("")
        if images.is_dir():
            plan.append((images, example / images.name))
    tmp_index = Path(tempfile.mkdtemp(prefix="rambleon-share-")) / "index.html"
    index_src = write_html_index(archive, paths.exports_dir, only=present, out=tmp_index)
    plan.append((index_src, example / "index.html"))
    result.files = [str(dest.relative_to(checkout)) for _, dest in plan]
    for src, dest in plan:
        log(f"{'would copy' if dry_run else 'copy'} {dest.relative_to(checkout)}")

    result.commands = [["git", "add", str(EXAMPLE_DIR)],
                       ["git", "commit", "-m", _message(nights_)],
                       ["git", "push", "origin", "HEAD"]]
    urls = [pages_url(remote, export_filename(n).replace(".md", ".html")) for n in nights_]
    result.urls = [u for u in urls if u]
    if dry_run:
        result.message = "dry run: nothing copied, committed or pushed"
        return result

    if all_nights and example.is_dir():
        shutil.rmtree(example)
    example.mkdir(parents=True, exist_ok=True)
    for src, dest in plan:
        if src.is_dir():
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(src, dest)
        else:
            shutil.copy2(src, dest)

    # 3. Commit and push, after the player says yes.
    _git(runner, checkout, "add", str(EXAMPLE_DIR))
    if _git(runner, checkout, "diff", "--cached", "--quiet", check=False).returncode == 0:
        result.message = "nothing new to share; the site already has these pages"
        return result
    branch = _git(runner, checkout, "rev-parse", "--abbrev-ref", "HEAD", check=False).stdout.strip()
    if branch and branch != "main":
        log(f"note: you are on branch {branch}; GitHub Pages deploys from main")
    question = "This makes the chapter public" + (f" at {result.urls[0]}" if result.urls else "") + ". Push it?"
    if not yes and confirm is not None and not confirm(question):
        _git(runner, checkout, "reset", "-q", "--", str(EXAMPLE_DIR), check=False)
        result.message = "not shared (files are staged locally under site/example; commit them yourself or run again)"
        return result
    _git(runner, checkout, "commit", "-q", "-m", _message(nights_))
    result.committed = True
    _git(runner, checkout, "push", "origin", "HEAD")
    result.pushed = True
    result.message = "pushed; GitHub Pages usually updates within a minute"
    return result


def _message(nights_: list[dict[str, Any]]) -> str:
    if len(nights_) == 1:
        return f"Journal: {nights_[0].get('nightDate')}"
    return f"Journal: {len(nights_)} chapters"
