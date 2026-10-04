"""What every HTML page shares: the document around it, the styles, the top bar, and the small pieces
(paragraphs, figures, page names). The story page and index (publish.py) and the route guide (guide.py)
are bodies inside `shell`; a new kind of page is one more body."""
from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .export import clock, export_filename
from .prompts import theme_css

PROJECT_URL = "https://github.com/realworldbuilder/rambleon"
ASSETS = Path(__file__).parent / "assets"
FONTS = ("<link rel='preconnect' href='https://fonts.gstatic.com' crossorigin>"
         "<link href='https://fonts.googleapis.com/css2?family=Cinzel:wght@700&display=swap' rel='stylesheet'>")


def css(guide: bool = False) -> str:
    """The page styles (assets/page.css, plus assets/guide.css for the route guide), then the player's own
    prompts/theme.css when there is one: later rules win, so a theme only says what it changes."""
    text = "\n" + (ASSETS / "page.css").read_text(encoding="utf-8")
    if guide:
        text += "\n" + (ASSETS / "guide.css").read_text(encoding="utf-8")
    theme = theme_css()
    if theme.strip():
        text += "\n/* prompts/theme.css */\n" + theme.rstrip() + "\n"
    return text


def top_nav(*links: tuple[str, str], home: str = "index.html") -> str:
    """The same slim bar on every page: wordmark home, then the page's own links."""
    return (f"<nav class='top'><a class='brand' href='{html.escape(home)}'>Rambleon</a>"
            + "".join(f"<a href='{html.escape(href)}'>{html.escape(label)}</a>" for label, href in links) + "</nav>")


def shell(title: str, nav: str, body: str, footer: str, body_attrs: str = "", guide: bool = False) -> str:
    """A whole page. `title`, `nav`, `body` and `footer` are HTML already (escape what goes into them)."""
    return "\n".join([
        "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
        f"<title>{title}</title>",
        f"{FONTS}<style>{css(guide)}</style></head><body{body_attrs}>",
        nav,
        body,
        f"<footer>{footer}</footer></body></html>",
    ])


def paragraphs(text: str) -> str:
    out = []
    for block in [b.strip() for b in text.replace("\r", "").split("\n\n") if b.strip()]:
        if block.startswith("#"):
            continue
        out.append("<p>" + html.escape(block).replace("\n", "<br>") + "</p>")
    return "\n".join(out)


def figure(img: dict[str, Any], cls: str = "") -> str:
    cap = f"{clock(img.get('takenAt'))} — {img['caption']}"
    return (f"<figure{' class=' + repr(cls) if cls else ''}><img src='{html.escape(img['src'])}' alt='{html.escape(img['caption'])}'>"
            f"<figcaption>{html.escape(cap)}</figcaption></figure>")


def page_name(session: dict[str, Any]) -> str:
    """A night's story page."""
    return export_filename(session).replace(".md", ".html")


def guide_page_name(slug: str) -> str:
    """A character's route guide page (guide.py writes it); story pages and the index link to it when it exists."""
    return f"guide-{slug}.html"


def index_anchor(slug: str) -> str:
    """index.html, at this character's chapters (the index gives each character an id)."""
    return "index.html" + (f"#{slug}" if slug else "")
