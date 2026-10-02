"""`ramble post`: tell a night on X.

One post per night: the chapter in miniature (the writer's own line when the chapter has one) and the
night's hero picture; `style = "thread"` tells the whole chapter instead. Like `ramble share`, this makes a
night public, so it asks first unless this Mac opted in with `[x] auto = true` in rambleon.local.toml; then
the watcher posts once the night has gone quiet. A ledger in the archive remembers what was posted, so a
night is never told twice.

X's API is pay-per-use and takes the four keys of your own developer app (OAuth 1.0a user context). They live
in the macOS Keychain (`ramble x login`), never in a file in the checkout."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .archive import Archive, atomic_write_json, load_json
from .config import x_config
from .export import export_filename, render_recap
from .nights import chapter_number, night_date, nights as list_nights
from .publish import chapter_title, load_journal, pick_hero, prepare_images
from .share import ShareError, pages_url, repo_checkout, EXAMPLE_DIR

API = "https://api.x.com"
KEYCHAIN_SERVICE = "rambleon-x"
KEYS = ("api_key", "api_secret", "access_token", "access_secret")
LIMIT = 280
URL_LENGTH = 23                 # X counts every link as this many characters, whatever its length
MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_AGE = 48 * 3600             # the watcher never reaches further back than this: no flood of old chapters
SCAN_EVERY = 60
RETRY_AFTER = (300, 1800, 7200)  # seconds; after the last one a failed night waits for `ramble post`

Runner = Callable[..., subprocess.CompletedProcess]
Http = Callable[[str, str, dict[str, str], bytes | None], tuple[int, Any]]
Log = Callable[[str], None]
_URL = re.compile(r"https?://\S+")
_SENTENCE_END = re.compile(r"(?<=[.!?…][\"”’)])\s+|(?<=[.!?…])\s+")
_KEY_SHAPE = re.compile(r"^[A-Za-z0-9_\-%.~+/=]+$")


class XError(RuntimeError):
    pass


# -- keys -------------------------------------------------------------------

def _security() -> str | None:
    return shutil.which("security") if sys.platform == "darwin" else None


def _keychain_get(name: str, runner: Runner) -> str | None:
    exe = _security()
    if not exe:
        return None
    try:
        r = runner([exe, "find-generic-password", "-s", KEYCHAIN_SERVICE, "-a", name, "-w"],
                   capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = (r.stdout or "").strip()
    return value if r.returncode == 0 and value else None


def load_credentials(env: dict[str, str] | None = None, runner: Runner = subprocess.run) -> dict[str, str] | None:
    """The four keys, from RAMBLEON_X_API_KEY / _API_SECRET / _ACCESS_TOKEN / _ACCESS_SECRET or the Keychain.
    None unless all four are there."""
    env = os.environ if env is None else env
    creds: dict[str, str] = {}
    for name in KEYS:
        value = env.get(f"RAMBLEON_X_{name.upper()}") or _keychain_get(name, runner)
        if not value:
            return None
        creds[name] = value
    return creds


def store_credentials(creds: dict[str, str], runner: Runner = subprocess.run) -> None:
    exe = _security()
    if not exe:
        raise XError("the macOS Keychain is not available here; set RAMBLEON_X_API_KEY, RAMBLEON_X_API_SECRET, "
                     "RAMBLEON_X_ACCESS_TOKEN and RAMBLEON_X_ACCESS_SECRET instead")
    for name in KEYS:
        value = (creds.get(name) or "").strip()
        if not _KEY_SHAPE.match(value):
            raise XError(f"{name} does not look like an X key (empty, or it has spaces or quotes in it)")
        # Through stdin, so the secret never shows up in the process list.
        line = f'add-generic-password -U -s "{KEYCHAIN_SERVICE}" -a "{name}" -w "{value}"\n'
        runner([exe, "-i"], input=line, capture_output=True, text=True, timeout=15)
        if _keychain_get(name, runner) != value:
            raise XError(f"the Keychain did not keep {name}")


def delete_credentials(runner: Runner = subprocess.run) -> int:
    exe = _security()
    if not exe:
        return 0
    gone = 0
    for name in KEYS:
        r = runner([exe, "delete-generic-password", "-s", KEYCHAIN_SERVICE, "-a", name], capture_output=True, text=True)
        gone += r.returncode == 0
    return gone


# -- the API ----------------------------------------------------------------

def _enc(value: Any) -> str:
    return urllib.parse.quote(str(value), safe="-._~")


def oauth_header(method: str, url: str, creds: dict[str, str], params: dict[str, str] | None = None,
                 nonce: str | None = None, timestamp: int | None = None) -> str:
    """OAuth 1.0a, HMAC-SHA1. `params` are query or form fields; a JSON or multipart body is not signed."""
    oauth = {
        "oauth_consumer_key": creds["api_key"],
        "oauth_nonce": nonce or secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(timestamp if timestamp is not None else int(time.time())),
        "oauth_token": creds["access_token"],
        "oauth_version": "1.0",
    }
    signed = sorted((_enc(k), _enc(v)) for k, v in {**(params or {}), **oauth}.items())
    base = "&".join([method.upper(), _enc(url), _enc("&".join(f"{k}={v}" for k, v in signed))])
    key = f"{_enc(creds['api_secret'])}&{_enc(creds['access_secret'])}"
    oauth["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{_enc(k)}="{_enc(v)}"' for k, v in sorted(oauth.items()))


def _http(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, Any]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    except (urllib.error.URLError, OSError) as e:
        raise XError(f"could not reach X: {e}") from e
    try:
        return status, json.loads(raw) if raw else {}
    except ValueError:
        return status, {"detail": raw[:300].decode("utf-8", "replace")}


HINTS = {
    401: "the keys were refused; run `ramble x login` again",
    402: "the developer account has no credits left; add some at console.x.com",
    403: "the app needs Read and write permission and an access token generated after that was set; "
         "X also refuses an exact repeat of a recent post",
    429: "X says slow down; try again later",
}


def _explain(status: int, payload: Any) -> str:
    detail = ""
    if isinstance(payload, dict):
        errors = payload.get("errors")
        first = errors[0] if isinstance(errors, list) and errors and isinstance(errors[0], dict) else {}
        detail = str(payload.get("detail") or first.get("message") or first.get("detail") or payload.get("title") or "")
    hint = HINTS.get(status)
    return f"X answered {status}" + (f": {detail}" if detail else "") + (f" ({hint})" if hint else "")


class XClient:
    def __init__(self, creds: dict[str, str], http: Http = _http):
        self.creds = creds
        self.http = http

    def _call(self, method: str, path: str, body: bytes | None = None, content_type: str | None = None) -> dict[str, Any]:
        url = API + path
        headers = {"Authorization": oauth_header(method, url, self.creds), "User-Agent": "rambleon"}
        if content_type:
            headers["Content-Type"] = content_type
        status, payload = self.http(method, url, headers, body)
        data = payload.get("data") if isinstance(payload, dict) else None
        if status not in (200, 201) or not isinstance(data, dict):
            raise XError(_explain(status, payload))
        return data

    def _json(self, path: str, obj: dict[str, Any]) -> dict[str, Any]:
        return self._call("POST", path, json.dumps(obj).encode("utf-8"), "application/json")

    def me(self) -> str:
        return str(self._call("GET", "/2/users/me").get("username") or "")

    def upload_image(self, path: Path) -> str:
        data = path.read_bytes()
        if len(data) > MAX_IMAGE_BYTES:
            raise XError(f"{path.name} is over X's 5 MB limit for pictures")
        mime = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
        boundary = "rambleon" + secrets.token_hex(12)
        body = b"".join([
            f'--{boundary}\r\nContent-Disposition: form-data; name="media_category"\r\n\r\ntweet_image\r\n'.encode(),
            f'--{boundary}\r\nContent-Disposition: form-data; name="media"; filename="{path.name}"\r\n'
            f"Content-Type: {mime}\r\n\r\n".encode(),
            data, f"\r\n--{boundary}--\r\n".encode(),
        ])
        return str(self._call("POST", "/2/media/upload", body, f"multipart/form-data; boundary={boundary}")["id"])

    def alt_text(self, media_id: str, text: str) -> None:
        self._json("/2/media/metadata", {"id": media_id, "metadata": {"alt_text": {"text": text[:1000]}}})

    def post(self, text: str, media_ids: list[str] | None = None, reply_to: str | None = None) -> str:
        body: dict[str, Any] = {"text": text}
        if media_ids:
            body["media"] = {"media_ids": media_ids}
        if reply_to:
            body["reply"] = {"in_reply_to_tweet_id": reply_to}
        return str(self._json("/2/tweets", body)["id"])


# -- what to say ------------------------------------------------------------

def weighted_len(text: str) -> int:
    """Length the way X counts it: links are 23, and anything outside the Latin ranges counts double."""
    text = unicodedata.normalize("NFC", text)
    total = URL_LENGTH * len(_URL.findall(text))
    for ch in _URL.sub("", text):
        cp = ord(ch)
        total += 1 if cp <= 0x10FF or 0x2000 <= cp <= 0x200D or 0x2010 <= cp <= 0x201F or 0x2032 <= cp <= 0x2037 else 2
    return total


def sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(" ".join(text.split())) if s]


def _wrap(text: str, limit: int) -> list[str]:
    out, cur = [], ""
    for word in text.split(" "):
        candidate = f"{cur} {word}".strip()
        if cur and weighted_len(candidate) > limit:
            out.append(cur)
            cur = word
        else:
            cur = candidate
    return out + [cur] if cur else out


def fit(text: str, limit: int) -> str:
    """As many whole sentences as fit; a first sentence that is too long by itself is cut at a word, with an ellipsis."""
    text = " ".join(text.split())
    if weighted_len(text) <= limit:
        return text
    kept = ""
    for s in sentences(text):
        candidate = f"{kept} {s}".strip()
        if weighted_len(candidate) > limit:
            break
        kept = candidate
    if kept:
        return kept
    head = _wrap(text, max(limit - 2, 1))[0]
    return head.rstrip(" ,;:—-") + "…"


def pack(parts: list[str], first: int, limit: int) -> list[str]:
    """Sentences into posts: the first has `first` characters of room (the header takes the rest), the others `limit`."""
    narrow = max(min(first, limit), 1)
    out: list[str] = []
    cur = ""
    for part in parts:
        for piece in ([part] if weighted_len(part) <= narrow else _wrap(part, narrow)):
            candidate = f"{cur} {piece}".strip()
            if cur and weighted_len(candidate) > (limit if out else first):
                out.append(cur)
                cur = piece
            else:
                cur = candidate
    return out + [cur] if cur else out


def story_text(journal: dict[str, Any] | None) -> str:
    """The chapter's prose without its heading."""
    lines = [ln.strip() for ln in ((journal or {}).get("journal") or "").splitlines()]
    return " ".join(ln for ln in lines if ln and not ln.startswith("#"))


def compose(night: dict[str, Any], journal: dict[str, Any] | None, number: int, style: str = "post",
            url: str | None = None) -> list[str]:
    """The post, or the thread, for one night. Every text fits X's limit."""
    name = str(night.get("character", {}).get("displayName") or "").strip()
    title = chapter_title(night, journal, number)
    header = f"{name} · {title}" if name else title
    if weighted_len(header) > 100:
        header = fit(title, 100)
    story = sentences(story_text(journal))
    if style == "thread" and story:
        chunks = pack(story, LIMIT - weighted_len(header) - 2, LIMIT)
        posts = [f"{header}\n\n{chunks[0]}"] + chunks[1:]
        if url and weighted_len(posts[-1]) + 2 + URL_LENGTH <= LIMIT:
            posts[-1] += f"\n\n{url}"
        elif url:
            posts.append(url)
        return posts
    room = LIMIT - weighted_len(header) - 2 - ((2 + URL_LENGTH) if url else 0)
    line = (journal or {}).get("post") or " ".join(story) or render_recap(night)
    return [f"{header}\n\n{fit(str(line), room)}" + (f"\n\n{url}" if url else "")]


def hero_image(night: dict[str, Any], exports_dir: Path) -> tuple[Path, str] | None:
    """The web-sized copy of the night's hero picture (the one the story page leads with) and its caption."""
    html_dir = exports_dir / "html"
    hero = pick_hero(prepare_images(night, html_dir / export_filename(night).replace(".md", "")))
    if not hero:
        return None
    path = html_dir / hero["src"]
    return (path, str(hero.get("caption") or "")) if path.exists() else None


def shared_url(paths: Any, night: dict[str, Any], runner: Runner = subprocess.run) -> str | None:
    """Where `ramble share` put this night's story page, or None when it has not been shared."""
    try:
        checkout = repo_checkout(paths.repo_root, runner)
    except (ShareError, OSError):
        return None
    page = export_filename(night).replace(".md", ".html")
    if not (checkout / EXAMPLE_DIR / page).exists():
        return None
    remote = runner(["git", "-C", str(checkout), "remote", "get-url", "origin"], capture_output=True, text=True)
    return pages_url(remote.stdout or "", page) if remote.returncode == 0 else None


# -- the ledger ---------------------------------------------------------------

def ledger_path(archive: Archive) -> Path:
    return archive.root / "posts" / "x.json"


def load_ledger(archive: Archive) -> dict[str, Any]:
    try:
        data = load_json(ledger_path(archive))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _record(archive: Archive, night_id: str, entry: dict[str, Any]) -> None:
    ledger = load_ledger(archive)
    ledger[night_id] = entry
    atomic_write_json(ledger_path(archive), ledger)


# -- posting ----------------------------------------------------------------

@dataclass
class PostResult:
    night_id: str
    texts: list[str] = field(default_factory=list)
    image: Path | None = None
    ids: list[str] = field(default_factory=list)
    posted: bool = False
    message: str = ""

    @property
    def url(self) -> str | None:
        return f"https://x.com/i/status/{self.ids[0]}" if self.ids else None


def post_night(archive: Archive, paths: Any, night: dict[str, Any], style: str = "post", link: bool = False,
               picture: bool = True, dry_run: bool = False, force: bool = False, yes: bool = False,
               confirm: Callable[[str], bool] | None = None, client: XClient | None = None,
               log: Log = lambda m: None, runner: Runner = subprocess.run) -> PostResult:
    result = PostResult(night_id=night["id"])
    earlier = load_ledger(archive).get(night["id"])
    journal = load_journal(paths.exports_dir, night["id"])
    url = shared_url(paths, night, runner) if link else None
    if link and not url:
        log("no link: this night's page is not on the site yet (`ramble share` puts it there)")
    result.texts = compose(night, journal, chapter_number(archive, night), style, url)
    hero = hero_image(night, paths.exports_dir) if picture else None
    result.image = hero[0] if hero else None
    if earlier and not force:
        result.ids = list(earlier.get("ids") or [])
        result.message = "already posted" + (f": {result.url}" if result.url else "") + " (--force posts it again)"
        return result
    if dry_run:
        result.message = "dry run: nothing posted"
        return result
    if client is None:
        creds = load_credentials(runner=runner)
        if creds is None:
            raise XError("no X keys on this Mac yet; run `ramble x login`")
        client = XClient(creds)
    if not yes and confirm is not None and not confirm("This posts to your X account. Post it?"):
        result.message = "not posted"
        return result

    media: list[str] = []
    if hero:
        try:
            media = [client.upload_image(hero[0])]
        except (XError, OSError) as e:        # the story matters more than the picture
            log(f"picture skipped: {e}")
        if media and hero[1]:
            try:
                client.alt_text(media[0], hero[1])
            except XError as e:
                log(f"picture description skipped: {e}")
    entry = {"postedAt": int(time.time()), "style": style, "ids": result.ids, "texts": result.texts,
             "image": result.image.name if media and result.image else None}
    for n, text in enumerate(result.texts):
        try:
            result.ids.append(client.post(text, media if n == 0 else None, result.ids[-1] if result.ids else None))
        except XError as e:
            if not result.ids:
                raise
            # Part of a thread is out. It is on the ledger, so nothing repeats it by itself.
            _record(archive, night["id"], {**entry, "partial": True})
            result.posted = True
            result.message = f"posted {len(result.ids)} of {len(result.texts)}, then: {e}"
            return result
        _record(archive, night["id"], entry)
    result.posted = True
    result.message = f"posted: {result.url}"
    return result


# -- the watcher's part -------------------------------------------------------

def due_nights(archive: Archive, exports_dir: Path, cfg: dict[str, Any], now: float | None = None) -> list[dict[str, Any]]:
    """Nights the watcher may post now: over, written up by the AI after their last minute, quiet for the
    configured delay, not on the ledger, and no older than two days."""
    now = time.time() if now is None else now
    ledger = load_ledger(archive)
    out = []
    for night in list_nights(archive, since=night_date(int(now - MAX_AGE - 86400))):
        ended = night.get("endedAt") or 0
        slug = night.get("character", {}).get("slug")
        if night["id"] in ledger or night.get("state") != "ended":
            continue
        if cfg["characters"] and slug not in cfg["characters"]:
            continue
        if not cfg["delay"] * 60 <= now - ended <= MAX_AGE:
            continue
        journal = load_journal(exports_dir, night["id"])
        if not journal or (journal.get("createdAt") or 0) < ended:   # no chapter yet, or one that misses the last session
            continue
        out.append(night)
    return out


class AutoPoster:
    """The watcher's tick: once a minute, post what is due. Tonight's chapter is held while you are in the
    world, and a failure is retried a few times, further apart, then left for `ramble post`."""

    def __init__(self, archive: Archive, paths: Any, log: Log, in_world: Callable[[float], bool] | None = None,
                 client_factory: Callable[[], XClient | None] | None = None,
                 notify: Callable[[str, str], None] | None = None):
        self.archive = archive
        self.paths = paths
        self.log = log
        self.in_world = in_world                  # (night end) -> True while the player may still add to tonight
        self.client_factory = client_factory or self._client
        self.notify = notify
        self._next_scan = 0.0
        self._failures: dict[str, tuple[int, float]] = {}   # night id -> (attempts, not before)
        self._told_no_keys = False

    @staticmethod
    def _client() -> XClient | None:
        creds = load_credentials()
        return XClient(creds) if creds else None

    def tick(self, now: float | None = None) -> list[PostResult]:
        now = time.time() if now is None else now
        if now < self._next_scan:
            return []
        self._next_scan = now + SCAN_EVERY
        cfg = x_config(self.paths.repo_root)
        if not cfg["auto"]:
            return []
        due = [n for n in due_nights(self.archive, self.paths.exports_dir, cfg, now)
               if self._failures.get(n["id"], (0, 0.0))[1] <= now]
        if self.in_world is not None:             # still playing: tonight may not be over (an earlier night is)
            tonight = night_date(int(now))
            due = [n for n in due if n.get("nightDate") != tonight or not self.in_world(n.get("endedAt") or 0)]
        if not due:
            return []
        client = self.client_factory()
        if client is None:
            if not self._told_no_keys:
                self._told_no_keys = True
                self.log("X: [x] auto is on but there are no keys on this Mac; run `ramble x login`")
            return []
        results = []
        for night in due:
            name = night.get("character", {}).get("displayName")
            try:
                result = post_night(self.archive, self.paths, night, style=cfg["style"], link=cfg["link"],
                                    picture=cfg["picture"], yes=True, client=client, log=self.log)
            except Exception as e:  # noqa: BLE001 — posting must never take the watcher down
                attempts = self._failures.get(night["id"], (0, 0.0))[0]
                if attempts < len(RETRY_AFTER):
                    self._failures[night["id"]] = (attempts + 1, now + RETRY_AFTER[attempts])
                    self.log(f"X: could not post {name}'s chapter ({e}); trying again later")
                else:
                    self._failures[night["id"]] = (attempts + 1, float("inf"))
                    self.log(f"X: giving up on {name}'s chapter ({e}); `ramble post {night['nightDate']}` posts it by hand")
                continue
            self.log(f"X: {name}: {result.message}")
            if result.posted and self.notify:
                self.notify("Rambleon", f"{name}'s chapter is on X.")
            results.append(result)
        return results
