"""Every kind of event a session can hold, in one place: how it reads, and how each output treats it.

A new thing to remember is one entry here and its twin in the AddOn's EventTypes.lua (docs/extending.md walks
through it). An event of a type this table does not know is never dropped and never an error: it reads as its
name in plain words and is treated as an ordinary moment."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

Event = dict[str, Any]


def place(ev: Event) -> str | None:
    return ev.get("subzone") or ev.get("zone")


def _quest(ev: Event) -> str:
    return f"\"{ev.get('title') or 'quest ' + str(ev.get('questID'))}\""


def _in_place(text: str) -> Callable[[Event], str]:
    return lambda ev: text + (f" in {place(ev)}" if place(ev) else "")


def _zone_enter(ev: Event) -> str:
    if ev.get("subzone") and ev.get("zone"):
        return f"Entered {ev['subzone']} ({ev['zone']})"
    return f"Entered {ev.get('zone') or 'somewhere new'}"


def _screenshot(ev: Event) -> str:
    reason = ev.get("reason")
    if reason == "LEVEL_UP":
        return f"Screenshot (Level {ev.get('level')})"
    if reason == "MARK":
        return "Screenshot (marked moment)"
    if reason == "ZONE_ENTER":
        return f"Screenshot (entering {ev.get('zone')})"
    return "Took a screenshot"


def _loot(ev: Event) -> str:
    q = f" ({ev['qualityName']})" if ev.get("qualityName") else ""
    n = f" ×{ev['count']}" if (ev.get("count") or 1) > 1 else ""
    return f"Looted {ev.get('name')}{n}{q}"


@dataclass(frozen=True)
class EventType:
    describe: Callable[[Event], str]   # the line in the log, the timeline and the prompt
    guide: str = "active"              # route guide: skip (never part of a stretch) | anchor (a visit with one stands
    #                                    alone) | passive (being somewhere, not doing anything) | active
    stitch: str = "keep"               # when sessions become a night: keep | drop | first (only the night's first
    #                                    session's) | last (only the last session's)
    timeline: bool = True              # False: never listed
    shot_fallback: bool = True         # a screenshot with no event of its own may be captioned by this moment
    counter: str | None = None         # the session counter the AddOn bumps for it


EVENTS: dict[str, EventType] = {
    "SESSION_START": EventType(_in_place("Began the adventure"), guide="skip", stitch="first", shot_fallback=False),
    "RESUMED": EventType(lambda ev: "Picked the story back up", guide="skip", stitch="drop", timeline=False, shot_fallback=False),
    "SESSION_END": EventType(lambda ev: "Ended the adventure", guide="skip", stitch="last", shot_fallback=False),
    "ZONE_ENTER": EventType(_zone_enter, guide="passive"),
    "LEVEL_UP": EventType(lambda ev: f"Reached Level {ev.get('level')}", guide="anchor", counter="levelsGained"),
    "QUEST_ACCEPTED": EventType(lambda ev: f"Accepted {_quest(ev)}", counter="questsAccepted"),
    "QUEST_COMPLETED": EventType(lambda ev: f"Completed {_quest(ev)}", guide="anchor", counter="questsCompleted"),
    "QUEST_ABANDONED": EventType(lambda ev: f"Abandoned {_quest(ev)}", guide="passive", counter="questsAbandoned"),
    "OBJECTIVE_COMPLETE": EventType(lambda ev: f"{ev.get('text') or 'Objective complete'}" + (f" — \"{ev['title']}\"" if ev.get("title") else ""),
                                    counter="objectivesCompleted"),
    "DEATH": EventType(lambda ev: f"Died in {place(ev) or 'the wilds'}", guide="anchor", counter="deaths"),
    "REVIVED": EventType(lambda ev: "Back among the living", guide="passive"),
    "GROUP_JOIN": EventType(lambda ev: f"Joined forces with {ev.get('name')}" + (f" ({ev['class']})" if ev.get("class") else "")),
    "GROUP_LEAVE": EventType(lambda ev: f"Parted ways with {ev.get('name')}", guide="passive"),
    "INSTANCE_ENTER": EventType(lambda ev: f"Entered {ev.get('name') or 'an instance'}"),
    "INSTANCE_EXIT": EventType(lambda ev: f"Left {ev.get('name') or 'the instance'}", guide="passive"),
    "BOSS_KILL": EventType(lambda ev: f"Defeated {ev.get('name') or 'a boss'}", guide="anchor"),
    "HEARTH_BOUND": EventType(lambda ev: f"Made {ev.get('name') or place(ev) or 'this place'} home"),
    "ACHIEVEMENT": EventType(lambda ev: f"Earned achievement: {ev.get('name') or ev.get('id')}", counter="achievements"),
    "SCREENSHOT": EventType(_screenshot, guide="passive", shot_fallback=False, counter="screenshots"),
    "NOTE": EventType(lambda ev: f"Note: \"{ev.get('text')}\"", guide="anchor", counter="notes"),
    "MARK": EventType(_in_place("Marked moment"), counter="marks"),
    "FIRST_KILL": EventType(lambda ev: f"First {ev.get('name')} slain"),
    "LOOT": EventType(_loot, counter="loot"),
    "EQUIP": EventType(lambda ev: f"Equipped {ev.get('name')}" + (f" ({ev['qualityName']})" if ev.get("qualityName") else "")),
}


def _unknown(type_: Any) -> EventType:
    words = str(type_ or "something").replace("_", " ").strip().capitalize() or "Something"
    return EventType(lambda ev: words)


def spec(type_: Any) -> EventType:
    """The entry for an event type; a type this companion does not know yet gets a harmless default."""
    return EVENTS.get(type_) or _unknown(type_)


def describe(ev: Event) -> str:
    return spec(ev.get("type")).describe(ev)


def shown(ev: Event) -> bool:
    """Whether the event is listed at all (a resume is continuity, not a moment)."""
    return spec(ev.get("type")).timeline


def types_where(**wanted: Any) -> set[str]:
    """The known types whose entry matches, e.g. types_where(guide="anchor")."""
    return {name for name, et in EVENTS.items() if all(getattr(et, k) == v for k, v in wanted.items())}
