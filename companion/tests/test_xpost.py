import json
import subprocess
import time
from pathlib import Path

import pytest

from rambleon.archive import Archive, atomic_write_json
from rambleon.config import x_config
from rambleon.luaparse import parse, to_python
from rambleon.nights import resolve_night
from rambleon.normalize import sessions_from_db
from rambleon.paths import Paths
from rambleon import xpost
from rambleon.xpost import (LIMIT, AutoPoster, XClient, XError, compose, due_nights, fit, load_credentials, load_ledger,
                            oauth_header, pack, post_night, store_credentials, weighted_len)

FIXTURES = Path(__file__).parent / "fixtures"
CREDS = {"api_key": "k", "api_secret": "ks", "access_token": "t", "access_secret": "ts"}
LONG = ("Cassidy was waiting for him again at Astranaar, and Rambleon fell into step beside her as easily as breathing. "
        "Ashenvale gave way to Darkshore in its familiar folds. " * 6).strip()


def archived(tmp_path: Path):
    paths = Paths(repo_root=tmp_path, wow_dir=tmp_path / "wow", archive_dir=tmp_path / "archive", exports_dir=tmp_path / "exports")
    archive = Archive(paths.archive_dir)
    db = to_python(parse((FIXTURES / "Rambleon_simulated.lua").read_bytes()))["RambleonDB"]
    archive.upsert_session(sessions_from_db(db)[0], {"capturedAt": int(time.time()), "rawSnapshot": "x", "sourceHash": "h"})
    archive.rebuild_index()
    return archive, paths, resolve_night(archive, "latest")


def write_journal(paths: Paths, night: dict, created_at: float | None = None, post: str | None = "Rambleon reached Dolanaar.") -> dict:
    journal = {"sessionId": night["id"], "chapter": 1, "title": "Chapter 1 — The Road to Dolanaar",
               "journal": f"# Chapter 1 — The Road to Dolanaar\n\n{LONG}\n", "recap": "Ramble on.\n", "post": post,
               "createdAt": int(created_at if created_at is not None else (night["endedAt"] or 0) + 60)}
    atomic_write_json(paths.exports_dir / "journal" / f"{night['id']}.json", journal)
    return journal


class FakeX:
    """Stands in for api.x.com: records every call and answers like the real thing."""

    def __init__(self, fail_on: int | None = None):
        self.calls: list[tuple[str, str, dict, bytes | None]] = []
        self.fail_on = fail_on      # the n-th post (0-based) is refused

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        assert headers["Authorization"].startswith("OAuth oauth_consumer_key=")
        if url.endswith("/2/media/upload"):
            return 200, {"data": {"id": "m1"}}
        if url.endswith("/2/media/metadata"):
            return 200, {"data": {"id": "m1"}}
        if url.endswith("/2/tweets"):
            n = len(self.posts) - 1     # this call is already on the list
            if self.fail_on == n:
                return 402, {"title": "Payment Required"}
            return 201, {"data": {"id": f"p{n}"}}
        return 404, {}

    @property
    def posts(self) -> list[dict]:
        return [json.loads(body) for _, url, _, body in self.calls if url.endswith("/2/tweets")]


def test_oauth_signature_matches_the_documented_example():
    creds = {"api_key": "xvz1evFS4wEEPTGEFPHBog", "api_secret": "kAcSOqF21Fu85e7zjz7ZN2U4ZRhfV3WpwPAoE3Z7kBw",
             "access_token": "370773112-GmHxMAgYyLbNEtIKZeRNFsMKPR9EyMZeS9weJAEb",
             "access_secret": "LswwdoUaIvS8ltyTt5jkRh4J50vUPVVHtR2YPi5kE"}
    header = oauth_header("POST", "https://api.twitter.com/1.1/statuses/update.json", creds,
                          {"include_entities": "true", "status": "Hello Ladies + Gentlemen, a signed OAuth request!"},
                          nonce="kYjzVBB8Y0ZFabxSWbWovY3uYSQ2pTgmZeNu2VS4cg", timestamp=1318622958)
    assert 'oauth_signature="hCtSmYh%2BiHYCEqBWrE7C7hYmtUk%3D"' in header


def test_length_counts_like_x():
    assert weighted_len("Ramble on.") == 10
    assert weighted_len("a — b · c’s") == 11          # dashes, the middle dot and curly quotes are single
    assert weighted_len("so…") == 4                    # the ellipsis is double
    assert weighted_len("read https://realworldbuilder.github.io/rambleon/example/2026-09-29-rambleon-birdsong.html") == 28
    assert fit("One. Two. Three.", 9) == "One. Two."
    cut = fit("A single sentence that runs on far too long to fit", 20)
    assert cut.endswith("…") and weighted_len(cut) <= 20
    assert all(weighted_len(p) <= 60 for p in pack(xpost.sentences(LONG), 40, 60))


def test_compose_post_prefers_the_writers_line(tmp_path):
    archive, paths, night = archived(tmp_path)
    journal = write_journal(paths, night)
    name = night["character"]["displayName"]
    [text] = compose(night, journal, 1)
    assert text == f"{name} · Chapter 1 — The Road to Dolanaar\n\nRambleon reached Dolanaar."
    # an older chapter has no line of its own: the opening of the story, whole sentences only
    [text] = compose(night, {**journal, "post": None}, 1, url="https://example.github.io/rambleon/example/page.html")
    assert weighted_len(text) <= LIMIT and text.endswith("page.html")
    assert "Cassidy was waiting" in text and text.split("\n\n")[1].endswith(".")
    # no chapter at all: the numbers
    [text] = compose(night, None, 1)
    assert "in Azeroth tonight." in text and weighted_len(text) <= LIMIT


def test_compose_thread_tells_the_whole_chapter(tmp_path):
    archive, paths, night = archived(tmp_path)
    journal = write_journal(paths, night)
    posts = compose(night, journal, 1, style="thread", url="https://example.github.io/x.html")
    assert len(posts) > 2 and all(weighted_len(p) <= LIMIT for p in posts)
    assert posts[0].startswith(night["character"]["displayName"]) and posts[-1].endswith("x.html")
    told = " ".join(posts).replace("\n\n", " ")
    assert LONG in told


def test_post_night_posts_once_and_remembers(tmp_path):
    archive, paths, night = archived(tmp_path)
    write_journal(paths, night)
    x = FakeX()
    client = XClient(CREDS, http=x)
    dry = post_night(archive, paths, night, dry_run=True, client=client)
    assert dry.texts and not dry.posted and x.calls == []
    result = post_night(archive, paths, night, yes=True, client=client)
    assert result.posted and result.ids == ["p0"] and result.url == "https://x.com/i/status/p0"
    assert x.posts == [{"text": result.texts[0]}]
    assert load_ledger(archive)[night["id"]]["ids"] == ["p0"]
    again = post_night(archive, paths, night, yes=True, client=client)
    assert not again.posted and "already posted" in again.message and len(x.posts) == 1
    assert post_night(archive, paths, night, yes=True, force=True, client=client).posted and len(x.posts) == 2


def test_post_night_asks_first(tmp_path):
    archive, paths, night = archived(tmp_path)
    x = FakeX()
    result = post_night(archive, paths, night, confirm=lambda q: False, client=XClient(CREDS, http=x))
    assert not result.posted and x.calls == [] and load_ledger(archive) == {}


def test_picture_goes_with_the_first_post(tmp_path, monkeypatch):
    archive, paths, night = archived(tmp_path)
    write_journal(paths, night)
    picture = tmp_path / "hero.jpg"
    picture.write_bytes(b"\xff\xd8jpeg")
    monkeypatch.setattr(xpost, "hero_image", lambda night, exports: (picture, "Reached Level 9 in Dolanaar"))
    x = FakeX()
    result = post_night(archive, paths, night, style="thread", yes=True, client=XClient(CREDS, http=x))
    upload = next(c for c in x.calls if c[1].endswith("/2/media/upload"))
    assert b'name="media_category"\r\n\r\ntweet_image' in upload[3] and b"\xff\xd8jpeg" in upload[3]
    assert upload[2]["Content-Type"].startswith("multipart/form-data; boundary=")
    alt = next(json.loads(c[3]) for c in x.calls if c[1].endswith("/2/media/metadata"))
    assert alt == {"id": "m1", "metadata": {"alt_text": {"text": "Reached Level 9 in Dolanaar"}}}
    assert x.posts[0]["media"] == {"media_ids": ["m1"]} and "reply" not in x.posts[0]
    assert "media" not in x.posts[1] and x.posts[1]["reply"] == {"in_reply_to_tweet_id": "p0"}
    assert x.posts[2]["reply"] == {"in_reply_to_tweet_id": "p1"} and len(result.ids) == len(result.texts)


def test_refusal_is_explained_and_half_a_thread_is_not_repeated(tmp_path):
    archive, paths, night = archived(tmp_path)
    write_journal(paths, night)
    with pytest.raises(XError, match="402.*credits"):
        post_night(archive, paths, night, yes=True, client=XClient(CREDS, http=FakeX(fail_on=0)))
    assert load_ledger(archive) == {}                      # nothing went out: free to try again
    x = FakeX(fail_on=1)
    result = post_night(archive, paths, night, style="thread", yes=True, client=XClient(CREDS, http=x))
    assert result.posted and result.ids == ["p0"] and "posted 1 of" in result.message
    assert load_ledger(archive)[night["id"]]["partial"] is True
    assert due_nights(archive, paths.exports_dir, x_config(tmp_path), now=night["endedAt"] + 7200) == []


def test_due_nights_waits_for_a_quiet_finished_chapter(tmp_path):
    archive, paths, night = archived(tmp_path)
    cfg = x_config(tmp_path)
    ended = night["endedAt"]
    assert cfg == {"auto": False, "style": "post", "link": False, "picture": True, "delay": 30, "characters": []}
    assert due_nights(archive, paths.exports_dir, cfg, now=ended + 3600) == []          # no chapter written yet
    write_journal(paths, night, created_at=ended - 600)
    assert due_nights(archive, paths.exports_dir, cfg, now=ended + 3600) == []          # the chapter misses the last session
    write_journal(paths, night)
    assert due_nights(archive, paths.exports_dir, cfg, now=ended + 600) == []           # not quiet for long enough
    assert [n["id"] for n in due_nights(archive, paths.exports_dir, cfg, now=ended + 3600)] == [night["id"]]
    assert due_nights(archive, paths.exports_dir, cfg, now=ended + 3 * 86400) == []     # old chapters are never flooded out
    assert due_nights(archive, paths.exports_dir, {**cfg, "characters": ["someone-else"]}, now=ended + 3600) == []


def test_autoposter_holds_while_playing_then_posts_once(tmp_path):
    archive, paths, night = archived(tmp_path)
    write_journal(paths, night)
    now = night["endedAt"] + 3600
    x = FakeX()
    playing = {"yes": True}
    logs, notes = [], []
    poster = AutoPoster(archive, paths, logs.append, in_world=lambda since: playing["yes"],
                        client_factory=lambda: XClient(CREDS, http=x), notify=lambda t, m: notes.append(m))
    assert poster.tick(now) == [] and x.calls == []                 # [x] auto is off
    (tmp_path / "rambleon.local.toml").write_text('[x]\nauto = true\ndelay = 45\nstyle = "post"\n')
    assert x_config(tmp_path)["delay"] == 45
    if night["nightDate"] == xpost.night_date(int(now + 60)):       # (a run across the 5 a.m. cutoff has no "tonight")
        assert poster.tick(now + 60) == [] and x.calls == []        # still in the world, and it is tonight's chapter
    playing["yes"] = False
    assert poster.tick(now + 90) == []                              # scans once a minute
    [result] = poster.tick(now + 120)
    assert result.posted and len(x.posts) == 1 and notes
    assert poster.tick(now + 600) == [] and len(x.posts) == 1       # on the ledger: never twice
    # an earlier night cannot grow any more: it is not held because tonight is being played
    archive2, paths2, night2 = archived(tmp_path / "later")
    write_journal(paths2, night2)
    (tmp_path / "later" / "rambleon.local.toml").write_text("[x]\nauto = true\n")
    eager = AutoPoster(archive2, paths2, logs.append, in_world=lambda since: True, client_factory=lambda: XClient(CREDS, http=x))
    assert len(eager.tick(night2["endedAt"] + 30 * 3600)) == 1


def test_autoposter_backs_off_and_survives_failures(tmp_path):
    archive, paths, night = archived(tmp_path)
    write_journal(paths, night)
    (tmp_path / "rambleon.local.toml").write_text("[x]\nauto = true\n")
    now = night["endedAt"] + 3600
    x = FakeX(fail_on=0)
    logs = []
    poster = AutoPoster(archive, paths, logs.append, client_factory=lambda: XClient(CREDS, http=x))
    assert poster.tick(now) == [] and "trying again later" in logs[-1]
    assert poster.tick(now + 120) == [] and len(x.calls) == 1       # not hammering X every minute
    x.fail_on = None
    [result] = poster.tick(now + 400)
    assert result.posted
    # no keys: said once, nothing sent
    archive2, paths2, night2 = archived(tmp_path / "second")
    write_journal(paths2, night2)
    (tmp_path / "second" / "rambleon.local.toml").write_text("[x]\nauto = true\n")
    said = []
    silent = AutoPoster(archive2, paths2, said.append, client_factory=lambda: None)
    silent.tick(now)
    silent.tick(now + 120)
    assert len(said) == 1 and "ramble x login" in said[0]


def test_credentials_come_from_env_or_keychain_and_never_argv(monkeypatch):
    env = {f"RAMBLEON_X_{k.upper()}": f"v-{k}" for k in xpost.KEYS}

    def no_keychain(cmd, **kw):
        return subprocess.CompletedProcess(cmd, 44, "", "not found")
    assert load_credentials(env, runner=no_keychain) == {k: f"v-{k}" for k in xpost.KEYS}
    assert load_credentials({}, runner=no_keychain) is None
    monkeypatch.setattr(xpost, "_security", lambda: "/usr/bin/security")
    store: dict[str, str] = {}
    seen: list[list[str]] = []

    def keychain(cmd, **kw):
        seen.append(cmd)
        if cmd[1] == "-i":
            line = kw["input"]
            store[line.split('-a "')[1].split('"')[0]] = line.split('-w "')[1].split('"')[0]
            return subprocess.CompletedProcess(cmd, 0, "", "")
        value = store.get(cmd[cmd.index("-a") + 1])
        return subprocess.CompletedProcess(cmd, 0 if value else 44, (value or "") + "\n", "")
    store_credentials({k: f"secret-{k}" for k in xpost.KEYS}, runner=keychain)
    assert load_credentials({}, runner=keychain) == {k: f"secret-{k}" for k in xpost.KEYS}
    assert not any("secret-" in arg for cmd in seen for arg in cmd)
    with pytest.raises(XError, match="does not look like"):
        store_credentials({**{k: "fine" for k in xpost.KEYS}, "api_key": 'has "quotes"'}, runner=keychain)
