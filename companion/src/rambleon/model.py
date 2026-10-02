"""Schema constants and validation for Rambleon sessions (schemaVersion 1)."""
from __future__ import annotations

import re
from typing import Any

SCHEMA_VERSION = 1
NORMALIZED_VERSION = 3  # 2: displayName/slug derived with the surname rule, guid published in game; 3: death echoes dropped
DEATH_ECHO = 30         # seconds: Forever build 70009 fires PLAYER_DEAD twice per death; AddOns before 0.3.1 recorded both
SUSPEND_TIMEOUT = 600  # seconds; a suspended session older than this is treated as ended
KEEP_ALL = True

EVENT_TYPES = {
    "SESSION_START", "RESUMED", "SESSION_END", "ZONE_ENTER", "LEVEL_UP", "QUEST_ACCEPTED", "QUEST_COMPLETED",
    "DEATH", "REVIVED", "GROUP_JOIN", "GROUP_LEAVE", "INSTANCE_ENTER", "INSTANCE_EXIT", "ACHIEVEMENT",
    "SCREENSHOT", "NOTE", "MARK", "FIRST_KILL", "OBJECTIVE_COMPLETE", "LOOT", "EQUIP",
}
STATES = {"active", "suspended", "ended"}
COUNTER_KEYS = ["levelsGained", "questsAccepted", "questsCompleted", "deaths", "zonesVisited", "notes", "marks",
                "screenshots", "achievements", "kills", "xpGained", "objectivesCompleted", "loot"]


def slugify(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", str(text or "")).strip("-").lower()
    return s or "unknown"


def validate_session(s: dict[str, Any]) -> list[str]:
    """Return a list of problems (empty means valid)."""
    problems: list[str] = []
    if not isinstance(s, dict):
        return ["session is not a table"]
    if not isinstance(s.get("id"), str) or not s["id"]:
        problems.append("missing id")
    if not isinstance(s.get("startedAt"), (int, float)):
        problems.append("missing startedAt")
    if not isinstance(s.get("character"), dict):
        problems.append("missing character")
    if s.get("state") not in STATES:
        problems.append(f"unknown state {s.get('state')!r}")
    events = s.get("events")
    if not isinstance(events, list):
        problems.append("events is not a list")
    else:
        for i, ev in enumerate(events):
            if not isinstance(ev, dict) or not isinstance(ev.get("t"), (int, float)) or not isinstance(ev.get("type"), str):
                problems.append(f"event {i} malformed")
                break
    return problems
