"""The immutable local archive. Raw snapshots are never modified; normalized sessions never shrink, except when
a newer companion renormalizes them (a higher normalizedVersion, e.g. death echoes dropped on reprocess)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STATE_RANK = {"active": 0, "suspended": 1, "ended": 2}
TRIVIAL_EVENTS = 3        # SESSION_START + ZONE_ENTER (+ one more) …
TRIVIAL_SECONDS = 120     # … and under two minutes: the login-then-logout that follows every END & SAVE reload


def is_trivial(session: dict[str, Any]) -> bool:
    return len(session.get("events", [])) <= TRIVIAL_EVENTS and (session.get("playedSeconds") or 0) < TRIVIAL_SECONDS


def blake(data: bytes) -> str:
    return hashlib.blake2b(data, digest_size=16).hexdigest()


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(data)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def atomic_write_json(path: Path, obj: Any) -> None:
    atomic_write_bytes(path, (json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=False) + "\n").encode("utf-8"))


def load_json(path: Path) -> Any:
    with open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def _content_key(session: dict[str, Any]) -> str:
    body = {k: v for k, v in session.items() if k != "archive"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False)


class Archive:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.raw_dir = self.root / "sessions" / "raw"
        self.failed_dir = self.raw_dir / "failed"
        self.normalized_dir = self.root / "sessions" / "normalized"
        self.history_dir = self.normalized_dir / "history"
        self.screenshots_dir = self.root / "screenshots"
        self.index_path = self.root / "index.json"
        self.hash_index_path = self.raw_dir / "hashes.json"
        self.pid_path = self.root / "watch.pid"

    def ensure(self) -> None:
        for d in (self.raw_dir, self.failed_dir, self.normalized_dir, self.history_dir, self.screenshots_dir):
            d.mkdir(parents=True, exist_ok=True)

    # -- raw snapshots ------------------------------------------------------
    def _hashes(self) -> dict[str, str]:
        if self.hash_index_path.exists():
            try:
                return load_json(self.hash_index_path)
            except (OSError, ValueError):
                return {}
        return {}

    def has_hash(self, h: str) -> bool:
        return h in self._hashes()

    def snapshot_raw(self, data: bytes, source: Path | str) -> tuple[Path | None, str]:
        """Store the bytes exactly as WoW wrote them. Returns (path or None if duplicate, hash)."""
        self.ensure()
        h = blake(data)
        hashes = self._hashes()
        if h in hashes:
            return None, h
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        name = f"{stamp}_{h[:8]}_{Path(source).name}"
        path = self.raw_dir / name
        atomic_write_bytes(path, data)
        hashes[h] = name
        atomic_write_json(self.hash_index_path, hashes)
        return path, h

    def store_failed(self, data: bytes, source: Path | str, reason: str) -> Path:
        self.ensure()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
        path = self.failed_dir / f"{stamp}_{blake(data)[:8]}_{Path(source).name}"
        atomic_write_bytes(path, data)
        atomic_write_bytes(path.with_suffix(path.suffix + ".reason.txt"), reason.encode("utf-8"))
        return path

    # -- normalized sessions ------------------------------------------------
    def session_files(self) -> list[Path]:
        return sorted(p for p in self.normalized_dir.glob("*.json") if p.is_file())

    def _find_existing(self, session_id: str) -> Path | None:
        for p in self.session_files():
            try:
                if load_json(p).get("id") == session_id:
                    return p
            except (OSError, ValueError):
                continue
        return None

    def _filename_for(self, session: dict[str, Any]) -> str:
        started = session.get("startedAt") or int(time.time())
        local = datetime.fromtimestamp(started)
        return f"{local:%Y-%m-%d_%H%M}_{session['character'].get('slug', 'unknown')}.json"

    def upsert_session(self, session: dict[str, Any], capture: dict[str, Any]) -> tuple[str, Path | None]:
        """Merge rule: new wins only if it has at least as many events and is not a downgrade. A session normalized
        by a newer companion (higher normalizedVersion) replaces the old one even with fewer events: reprocess walks
        the raw snapshots oldest first, so the newest snapshot still ends up on top.
        Returns (outcome, path) with outcome in new | updated | unchanged | rejected."""
        self.ensure()
        existing_path = self._find_existing(session["id"])
        record = dict(session)
        record["archive"] = dict(capture)
        if existing_path is None:
            path = self.normalized_dir / self._filename_for(session)
            n = 2
            while path.exists():  # same minute, same character, different id: disambiguate
                path = self.normalized_dir / self._filename_for(session).replace(".json", f"_{n}.json")
                n += 1
            record["archive"]["firstCapturedAt"] = capture.get("capturedAt")
            atomic_write_json(path, record)
            return "new", path
        old = load_json(existing_path)
        old_events = len(old.get("events", []))
        new_events = len(session.get("events", []))
        renormalized = int(session.get("normalizedVersion") or 0) > int(old.get("normalizedVersion") or 0)
        if new_events < old_events and not renormalized:
            return "rejected", existing_path
        old_rank = STATE_RANK.get(old.get("state"), 0)
        new_rank = STATE_RANK.get(session.get("state"), 0)
        if new_events == old_events and new_rank < old_rank and not renormalized:
            return "rejected", existing_path
        if _content_key(old) == _content_key(session):
            return "unchanged", existing_path
        record["archive"]["firstCapturedAt"] = old.get("archive", {}).get("firstCapturedAt", capture.get("capturedAt"))
        record["archive"]["revision"] = int(old.get("archive", {}).get("revision", 1)) + 1
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        shutil.copy2(existing_path, self.history_dir / f"{existing_path.stem}.{stamp}.json")
        atomic_write_json(existing_path, record)
        return "updated", existing_path

    # -- index --------------------------------------------------------------
    def rebuild_index(self) -> dict[str, Any]:
        entries = []
        for p in self.session_files():
            try:
                s = load_json(p)
            except (OSError, ValueError):
                continue
            entries.append({
                "id": s.get("id"),
                "file": p.name,
                "character": s.get("character", {}).get("displayName"),
                "slug": s.get("character", {}).get("slug"),
                "startedAt": s.get("startedAt"),
                "endedAt": s.get("endedAt"),
                "playedSeconds": s.get("playedSeconds"),
                "state": s.get("state"),
                "events": len(s.get("events", [])),
                "counters": s.get("counters", {}),
                "startLevel": s.get("character", {}).get("startLevel"),
                "endLevel": s.get("character", {}).get("endLevel"),
                "people": len(s.get("people", [])),
                "trivial": is_trivial(s),
            })
        entries.sort(key=lambda e: (e.get("startedAt") or 0, e.get("id") or ""))
        index = {"generatedAt": int(time.time()), "sessions": entries}
        atomic_write_json(self.index_path, index)
        return index

    def list_sessions(self) -> list[dict[str, Any]]:
        if not self.index_path.exists():
            if not self.session_files():
                return []
            return self.rebuild_index()["sessions"]
        try:
            return load_json(self.index_path)["sessions"]
        except (OSError, ValueError, KeyError):
            return self.rebuild_index()["sessions"]

    def resolve(self, ref: str) -> Path | None:
        """ref: 'latest', a session id, a file name, or a unique prefix of either."""
        sessions = self.list_sessions()
        if not sessions:
            return None
        if ref in ("latest", "last", ""):
            # Prefer the newest session that actually contains an adventure; the short login-only session
            # that follows every END & SAVE reload is skipped when a real one exists.
            real = [s for s in sessions if not s.get("trivial")]
            return self.normalized_dir / (real or sessions)[-1]["file"]
        exact = [s for s in sessions if s.get("id") == ref or s.get("file") == ref or s.get("file") == ref + ".json"]
        if len(exact) == 1:
            return self.normalized_dir / exact[0]["file"]
        prefix = [s for s in sessions if (s.get("id") or "").startswith(ref) or (s.get("file") or "").startswith(ref)]
        if len(prefix) == 1:
            return self.normalized_dir / prefix[0]["file"]
        return None

    def load_session(self, ref: str) -> dict[str, Any] | None:
        p = self.resolve(ref)
        return load_json(p) if p else None

    def chapter_number(self, session: dict[str, Any]) -> int:
        slug = session.get("character", {}).get("slug")
        started = session.get("startedAt") or 0
        earlier = [s for s in self.list_sessions() if s.get("slug") == slug and (s.get("startedAt") or 0) < started]
        return len(earlier) + 1

    # -- watcher pid ----------------------------------------------------------
    def watcher_pid(self) -> int | None:
        try:
            pid = int(self.pid_path.read_text().strip())
        except (OSError, ValueError):
            return None
        try:
            os.kill(pid, 0)
        except OSError:
            return None
        return pid
