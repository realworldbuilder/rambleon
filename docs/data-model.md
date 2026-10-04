# Data model

## 1. What the AddOn writes (`RambleonDB`, schemaVersion 1)

`## SavedVariablesPerCharacter: RambleonDB`, so WoW writes
`WTF/Account/<ACCOUNT>/<realm folder>/<Character-Name>/SavedVariables/Rambleon.lua`.

Only strings, numbers, booleans and tables are ever stored (`ns.Clean` enforces this and refuses secret values).

```lua
RambleonDB = {
  schemaVersion = 1,
  addonVersion = "0.4.0",
  settings = { autoScreenshots = true, debug = false, welcomed = false },   -- defaults in Session.lua; see below
  sessions = {                     -- array, oldest first; at most 10 non-active sessions are kept in WoW
    {
      id = "2026-09-21T201547Z_rambleon-birdsong",
      schemaVersion = 1,
      state = "active" | "suspended" | "ended",
      startedAt = 1790000000,      -- epoch seconds, time()
      startedServerTime = ...,     -- GetServerTime(), for cross-checking clocks
      lastSeen = ...,              -- bumped every event and every 30 s heartbeat
      endedAt = ..., endReason = "save" | ...,       -- "save" from /ramble save; older sessions say "end_chapter"
      playedSeconds = 8040,
      resumes = 0,
      character = { name, fullName, realmFromFullName, realm, normalizedRealm, race, raceFile, class, classFile,
                    faction, gender, guid, surname, displayName, startLevel, endLevel },
      client = { version, build, buildDate, tocVersion, projectId, flavorHint, flavor, addonVersion, locale },
      counters = { levelsGained, questsAccepted, questsCompleted, deaths, zonesVisited, notes, marks, screenshots, achievements,
                   kills, xpGained, objectivesCompleted, loot, questsAbandoned },
      zones = { { zone, subzone, mapID, firstSeen, lastSeen, visits }, ... },
      people = { { name, class, classFile, firstSeen, lastSeen, seconds, joins }, ... },
      kills = { ["Timberling"] = { count = 12, xp = 540, firstAt = ..., lastAt = ... }, ... },
      events = { { t = 1790000123, type = "ZONE_ENTER", zone = "Teldrassil", subzone = "Dolanaar", mapID = 57, x = 55.3, y = 58.1, level = 11 }, ... },
      failedEvents = { "ACHIEVEMENT_EARNED" },   -- registrations the client refused
    },
  },
}
```

### Event types

The list itself is code: `addon/Rambleon/EventTypes.lua` (how each reads in game, which counter it bumps) and its
twin `companion/src/rambleon/events.py` (how the companion's outputs treat it). Tests keep the two and this table's
types in step; `docs/extending.md` shows how to add one.

| type | fields |
|---|---|
| `SESSION_START`, `RESUMED`, `SESSION_END {reason}` | |
| `ZONE_ENTER` | `zone`, `subzone`, `mapID`, `x`, `y` (map percent, one decimal; absent in instances) |
| `LEVEL_UP` | `level` |
| `QUEST_ACCEPTED`, `QUEST_COMPLETED`, `QUEST_ABANDONED` | `questID`, `title` (+ `xp`, `money` on completion). Abandoned (0.4.0): the quest left the log without being turned in |
| `DEATH`, `REVIVED` | |
| `GROUP_JOIN {name, class}`, `GROUP_LEAVE {name}` | |
| `INSTANCE_ENTER {name, instanceType}`, `INSTANCE_EXIT {name}` | the exit was never recorded before 0.4.0 |
| `BOSS_KILL {name, encounterID}` | a dungeon or raid encounter ended in a kill (`ENCOUNTER_END`; 0.4.0) |
| `HEARTH_BOUND {name}` | an innkeeper made this place home (0.4.0) |
| `ACHIEVEMENT {id, name}` | |
| `SCREENSHOT` | `reason` (`LEVEL_UP` \| `MARK` \| `ZONE_ENTER` \| `MANUAL`), `auto`, and for automatic shots the `level`/`zone`/`subzone` of the moment; the companion finds the file by time |
| `NOTE {text}`, `MARK` | |
| `FIRST_KILL {name, xp}` | first time an enemy of that name gave XP this session (from the "X dies, you gain N experience." chat line; no combat log) |
| `OBJECTIVE_COMPLETE {questID, title, text}` | a quest objective finished, e.g. "8/8 Timberling slain" |
| `LOOT {itemID, name, quality, qualityName, count}` | an uncommon-or-better item you received (loot, quest reward, crafted); from the chat loot line |
| `EQUIP {itemID, name, quality, qualityName, slot}` | an uncommon-or-better item equipped, once per item per session |

Every event also carries `level`, and `zone`/`subzone` unless it is a zone event itself.

`RambleonDB.settings`: `autoScreenshots` (`/ramble shots on|off`, or the Pictures row on the panel), `debug`
(`/ramble debug on|off`), `welcomed` (the first-run note has been shown). Missing keys get their defaults at load;
keys the AddOn does not know are left alone. The companion never reads settings.

**Versions.** `schemaVersion` (1) is the shape of `RambleonDB`. Adding an event type, an event field, a counter or a
setting does not change it: both sides ignore what they do not know. Bump it only when existing data must be
rewritten to be read, and add the rewrite to `ns.MIGRATIONS[n]` in `Session.lua` (run once at load, oldest first;
data from a newer Rambleon is left untouched). `normalizedVersion` (3) is the companion's own: bump it in `model.py`
when normalization changes what an old raw snapshot turns into, so `ramble reprocess` is worth running.

### States

- `active` while playing. `PLAYER_LOGOUT` (logout and `/reload`) turns it into `suspended`.
- `/ramble save` (the save popup) turns it into `ended`. Recording anything afterwards starts a new session automatically.
- On load, a `suspended` session for the same character (by GUID; by name for sessions without one) seen
  < 10 minutes ago is resumed (`RESUMED` event).

## 2. The Lua subset the companion parses

`companion/src/rambleon/luaparse.py` is a hand-written tokenizer + recursive-descent parser. It never executes Lua.
It accepts what Blizzard's serializer emits (observed on this machine, see `environment.md`) plus a little slack:

- `Name = value` assignments at top level, repeated; `nil` allowed as a top-level value.
- Tables `{ ... }` with `["key"] = v`, `[123] = v`, bare positional values (1-based; a positional `nil,` advances the
  index without storing), and `key = v` for hand-edited files. Trailing `,` or `;` after every entry.
- Strings with `\"`, `\\`, `\n`, `\r`, `\t`, `\a`, `\b`, `\f`, `\v`, `\ddd`, `\xhh`, backslash-newline. `|` is not escaped.
- Numbers: integers, floats (`%.16g` output), exponents, hex; plus non-Lua spellings `inf`, `-inf`, `nan`, `-nan(ind)`,
  `1.#INF`, `1.#IND`, `1.#QNAN` (Windows clients) mapped to IEEE values.
- `-- comments` and `--[[ ]]` blocks. CRLF and a leading blank line.
- Guards: 64 MB size cap, 500 levels of nesting. An unexpected end of file raises `TornFile` (WoW was still writing);
  any other problem raises `LuaParseError`.

`to_python()` turns tables keyed exactly `1..n` into lists and everything else into string-keyed dicts.

## 3. Normalized session JSON (`archive/sessions/normalized/<YYYY-MM-DD_HHMM>_<slug>.json`)

```json
{
  "schemaVersion": 1, "normalizedVersion": 3,
  "id": "2026-09-21T201547Z_rambleon-birdsong",
  "addonState": "ended", "state": "ended",
  "startedAt": 1790000000, "startedServerTime": 1790000001, "endedAt": 1790008040, "lastSeen": 1790008040,
  "playedSeconds": 8040, "endReason": "save", "resumes": 0,
  "character": { "...raw fields...", "displayName": "Rambleon Birdsong", "slug": "rambleon-birdsong" },
  "client": { "...": "..." },
  "counters": { "levelsGained": 2, "...": 0 },
  "events": [ { "t": 1790000123, "type": "ZONE_ENTER", "zone": "Teldrassil", "subzone": "Dolanaar", "mapID": 57 } ],
  "zones": [], "people": [], "failedEvents": [],
  "screenshots": [ { "path": "...", "file": "WoWScrnShot_092126_201547.jpg", "takenAt": 1790000500, "archived": "archive/screenshots/<session>/WoWScrnShot_092126_201547.jpg",
                     "eventIndex": 4, "eventSeconds": 1, "reason": "LEVEL_UP", "auto": true, "level": 9, "zone": "Teldrassil", "subzone": "Dolanaar",
                     "caption": "Reached Level 9 in Dolanaar" } ],
  "archive": { "capturedAt": 1790008100, "rawSnapshot": "sessions/raw/2026-09-22T031500Z_ab12cd34_Rambleon.lua",
               "sourceHash": "...", "sourceFile": ".../WTF/Account/<ACCOUNT>/70/Rambleon-Birdsong/SavedVariables/Rambleon.lua",
               "firstCapturedAt": 1790008100, "revision": 1 }
}
```

Normalization rules:
- Timestamps stay epoch seconds (UTC). Only exports render local time.
- `state` is the *effective* state: a `suspended`/`active` session whose `lastSeen` is more than 10 minutes old is
  reported as `ended` with `endedAt = lastSeen` and `endReason = "logout"`. `addonState` keeps the original.
- Events are sorted by `t` (stable). Non-scalar event fields are dropped.
- A session without an id, start time, character or event list is skipped.
- Screenshots (`screenshots.py`): a file is matched to the `SCREENSHOT` event within 5 s of its mtime (one file per event)
  and inherits its `reason`; otherwise `eventIndex` is the nearest ordinary event and the caption is "Screenshot in <place>".
  Pairing runs at capture, at finalization (late files), on `ramble page`/`share`, and again over the merged night.
  Entries written before 0.3 carry `nearestEventIndex` instead; `ramble reprocess` rewrites them.

## 4. Archive rules (`archive/`)

```
archive/
  sessions/raw/            <utc stamp>_<hash8>_Rambleon.lua   exact bytes WoW wrote; never modified
  sessions/raw/hashes.json hash → raw file (dedupe)
  sessions/raw/failed/     files that would not parse, with a .reason.txt beside each
  sessions/normalized/     one JSON per session id
  sessions/normalized/history/  previous versions of any normalized file that was replaced
  screenshots/<session>/   copies of the night's screenshots (default; `--no-copy-screenshots` keeps references only)
  index.json               rebuilt after every change
  posts/x.json             what `ramble post` sent to X: night id → { v, postedAt, style, ids, texts, image, partial? }
  watch.pid                present while `ramble watch` runs
```

- Raw snapshot first, always. Parsing happens after the bytes are safe.
- A normalized session is replaced only by a copy with **at least as many events** that is not a state downgrade
  (`ended` beats `suspended`). Fewer events → rejected and logged. Never deleted, never shrunk.
- A file whose `RambleonDB` has no sessions (the beta bug, or a fresh character) touches nothing.
- Atomic writes everywhere (`tmp` + `os.replace`).

## 5. Exports (`exports/`)

- `markdown/<date>-<slug>.md` — factual log (`ramble export`).
- `prompts/<date>-<slug>-prompt.md` — AI-neutral prompt with rules + evidence (`ramble summarize`).
- `markdown/<date>-<slug>-journal.md` and `social/<date>-<slug>-recap.txt` — when the Claude CLI wrote the chapter.
- `social/<date>-<slug>-catchup.txt` — plain-text quest list for a friend (`ramble catchup`).
- `markdown/guide-<slug>.md`, `prompts/guide-<slug>-<mode>-prompt.md`, `html/guide-<slug>.html` — the route guide
  (`ramble guide`): every night of one character cut into zone stretches. `guide/<slug>-<mode>.json` is its sidecar:
  `formatVersion, slug, displayName, title, mode, nights (ids the prose covers), chapters, prose, model, voice, createdAt`;
  `markdown/guide-<slug>-<mode>-prose.md` the same prose as a file. A mode other than the configured default writes
  `html/guide-<slug>-<mode>.html` beside the linked page.
- `journal/<night id>.json` — the chapter as written: `formatVersion, sessionId, chapter, title, journal, recap, post, model, voice, createdAt`
  (`post`: the one-line telling for a social feed, from the prompt's `---POST---` section; absent before 2026-10-01).
  The story page, `Chapters.lua` and the prompts for later nights all read it: `memory.py` hands the writer the previous
  chapter's text, the last three chapters' titles and a companion history built from the normalized nights. Deleting
  a sidecar costs a title and the previous-chapter text, never a fact.

- `finished/<night id>.json` — the marker `pipeline.py` writes when every step has run over a night:
  `formatVersion, nightId, endedAt, events (how many the night held), finishedAt, steps (name → ok | skipped: … | failed: …)`.
  A night with no marker, or one that has grown since, is what a restarted watcher finishes (`ramble status` lists
  them). Nights finished before markers existed count when their journal sidecar, or else their story page, is newer
  than the night's last minute.
- `html/` — story pages, `index.html`, `guide-<slug>.html`, and an image folder per page.

Files with a `formatVersion` (and X ledger entries with `v`, `Chapters.lua` with `RambleonChaptersMeta.format`) are
at version 1; a file without the field is version 1 too.

Generated artifacts are downstream of the archive and can always be regenerated. Raw history is never edited.

## 6. The player's own files (`<home>/`)

`<home>` is `~/Rambleon` for a package install and the checkout when running from one (`RAMBLEON_HOME` overrides).

- `rambleon.local.toml` — settings; every key optional. `ramble config` prints what is in effect and warns about
  keys it does not know. Sections: `[share] auto`; `[x] auto, style, link, picture, lowercase, delay, characters`;
  `[guide] mode`; `[journal] voice, model`; `[characters."<slug>"]` (character fields to override, e.g. `gender`);
  `[people."<Name>"] note`.
- `prompts/voices/*.md`, `prompts/guides/*.md`, `prompts/journal.md`, `prompts/theme.css` — your own voices, guide
  modes, chapter rules and page styles (`docs/extending.md`).
