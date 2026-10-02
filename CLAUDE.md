# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Rambleon

Rambleon is a **personal memory layer for World of Warcraft**. You play; it quietly remembers; at the end of the
night it hands you a permanent record: a timeline, a factual log, a story page, and an AI-written chapter you can
read in game and paste anywhere. Strava for Azeroth, written like a field journal.

Owner: William Hussey. First character: **Rambleon Birdsong**, Night Elf Hunter (male), World of Warcraft: Forever beta.
Goal: something to *offer* other players (free, open), not primarily something to sell.

## What Rambleon is NOT

- not a DPS meter, not a combat assistant, not a rotation helper
- not a leveling guide or quest helper: no advice, no optimal route, no help in game. Your own path, retold
  (`ramble guide`), is memory, not guidance.
- not a general WoW database
- not automation of any kind (no movement, no ability use, no interaction with other players)

## The one question

Before adding a feature or recording an event: **"Will this help the player remember their adventure?"**
If it would not be interesting to read six months later, it does not belong. Memories, not telemetry.
The player's own words (`/ramble note`) always outrank anything the API can tell us.

## How it works (current, 2026-09-22)

```
WoW: Forever → Rambleon AddOn (Lua) → SavedVariables (written on logout and /reload)
             → ramble watch (Mac, launchd service) → archive/ (immutable raw + normalized JSON)
             → nights (a chapter = one evening) → Markdown log, AI journal, HTML story page
             → Chapters.lua published back into the AddOn → /ramble chapters in game
```

- **The log just runs.** There is no "end" button. Logging out is the save. `/ramble save` is an optional flush.
- **Pictures**: the AddOn calls `Screenshot()` at level ups, `/ramble mark` and the first visit to a new zone (UI visible,
  `/ramble shots on|off`). The `SCREENSHOT` event carries the reason; the companion pairs the file, captions it, copies it
  into `archive/screenshots/`, and the story page shows a hero picture plus the rest on the timeline.
- **Sharing is manual by default**: `ramble share tonight` copies the page and web-sized pictures into `site/example`,
  commits and pushes after asking. A Mac can opt in to automatic sharing with `[share] auto = true` in the gitignored
  `rambleon.local.toml`: then every finished chapter is pushed by the watcher. Nothing else publishes.
- **X**: `ramble post tonight` tells a night on X (asks first): title, the writer's `---POST---` line, hero picture;
  `--style thread` posts the whole chapter. Keys of the player's own X developer app live in the macOS Keychain
  (`ramble x login`; OAuth 1.0a, stdlib only, pay-per-use API, a link in a post costs ~13× more so `link` is off by
  default). `[x] auto = true` in `rambleon.local.toml`: the watcher's `AutoPoster` posts a night once it is over, its
  chapter covers the last session, it has been quiet for `delay` minutes and (for tonight's) the player is not in the world.
  `archive/posts/x.json` is the ledger: a night is never posted twice. Unverified against the live API as of 10-01.
- **A chapter is a night**: every session of one evening (5 a.m. cutoff) stitched together in `nights.py`.
  Reloads and relogs are continuity, not breaks (the AddOn resumes a session seen < 10 min ago).
- **Finalization**: the watcher writes the chapter the moment the player leaves (WoW quit, or `Logs/Client.log`
  shows a logout after the last save), ten minutes after the last write as fallback, or at once after `/ramble save`.
  Then: export → AI journal (if the Claude CLI is logged in) → route guide (facts always; prose only when a night is new to it)
  → story page + index → publish to the game → macOS notification.
- **Route guide**: one page per character, `exports/html/guide-<slug>.html`, linked from every story page and the index,
  and copied by `ramble share`. `guide.py` cuts the nights into zone stretches (a visit stands alone when a quest was
  turned in, a level reached, a death or a note happened there, or 20+ minutes with something done; anything else folds
  into its neighbour as "passing through"; stretches span nights) and lists what was picked up, turned in, first fought,
  looted, where the deaths were, and the player's notes. A **mode** is the prompt that says what to write from those facts:
  `prompts/guides/route.md` (default, for another player), `season.md` (the story so far, for the player), or
  `--mode /your/file.md`. `RAMBLEON_GUIDE_MODE` or `[guide] mode = "..."` in `rambleon.local.toml` sets the watcher's.
  Sidecar `exports/guide/<slug>-<mode>.json` remembers which nights the prose covers.
- **Voices**: `companion/src/rambleon/prompts/voices/*.md`. Default `golden` (warm, close third person, Christie
  Golden-like); `field-journal` (dry, observational). `--voice`, `RAMBLEON_VOICE`, `ramble voices`.
- **Local facts**: `rambleon.local.toml` (gitignored) overrides character fields for sessions recorded before the
  AddOn captured them (e.g. gender), and `[people."Name"] note = "..."` gives the writer your own words about a companion.
- **Memory between chapters**: `memory.py` builds what the writer may remember (last three chapters as facts, the
  previous chapter's text, each companion's history) from earlier nights and their journal sidecars. Rule 6 in
  `prompts/journal.md` says how it may be used: continue the story, never retell it.

## Layout

- `addon/Rambleon/` — the AddOn. `Rambleon_Camelot.toc` (Forever, Interface 16001) + `Rambleon.toc` fallback.
  `Chapters.lua` is generated by the companion and gitignored. `Bindings.xml` is loaded by name; never list it in a TOC.
- `addon/tests/` — Lua 5.5 stub + `run.lua`: a scripted session that also emits the parser fixture.
- `companion/` — Python ≥ 3.11, uv, typer. `src/rambleon/`: `paths` (find WoW/WTF), `luaparse` (safe SV parser),
  `normalize`, `archive`, `watch` (+ `Finalizer`), `wowstate` (logout detection), `nights`, `export`, `summarize`,
  `publish` (Chapters.lua, HTML), `service` (launchd), `notify`, `config`, `doctor`, `install`, `cli`,
  `model` (schema constants), `screenshots` (pairs files with SCREENSHOT events, captions), `share` (GitHub Pages),
  `memory` (what earlier chapters lend the prompt), `guide` (the route guide: stretches, modes, page),
  `xpost` (X: keys, signing, composing the post or thread, ledger, the watcher's auto-post).
- The companion wheel **bundles the AddOn** via an explicit per-file `force-include` list in `companion/pyproject.toml`.
  Adding a file to `addon/Rambleon/` means adding it there too, or `uv tool install` users get a broken AddOn.
  Without a checkout, `install.py` seeds `~/Rambleon/addon/Rambleon` from the bundled copy.
- `archive/` — **source of truth**, gitignored. Raw snapshots never edited; normalized sessions never shrink.
- `exports/` — regenerable, gitignored: `markdown/`, `prompts/`, `journal/` (sidecars), `guide/` (guide sidecars), `html/`, `social/`.
- `site/` — GitHub Pages (`.github/workflows/pages.yml`): landing page + `example/`, a committed snapshot of
  Rambleon Birdsong's story pages. Refresh with `ramble share`; pushing makes the journal public.
- `docs/` — `environment.md` (this Mac), `addon-api.md` (Forever facts + the SV bug), `data-model.md`,
  `progress.md` (running log; read "To verify next session" first), `roadmap.md` (product plan).

## What we know about the Forever client (verified in game)

- Mainline 12.x UI codebase, version 1.60.1, builds 69913 → 70009. `WOW_PROJECT_ID` = 1. Surnames, no realms;
  realm `"Classic Beta PvE"`, WTF folder `70/Rambleon-Birdsong`. **The name API changed with build 70009** (2026-09-24):
  before, `UnitName("player")` → `"Rambleon Birdsong"` and `UnitFullName` → `"Rambleon Birdsong", "ClassicBetaPvE"`;
  now `UnitName` → `"Rambleon"` and `UnitFullName` → `"Rambleon", "Birdsong"`. Both sides derive one `displayName`
  (`ns.ComposeDisplayName` / `normalize.display_name`) and the game matches chapters by GUID, never by name alone.
- `C_UI.Reload()` works from a popup button. `QUEST_TURNED_IN` fires with questID. No event registration failed.
- The SavedVariables bug: files are written but not restored on **cold start**; on this Mac they *were* restored
  across `/reload`. Design assumes nothing: the Mac owns history.
- `UnitLevel` at logout can be stale; end level is derived from event levels on both sides.
- Kills come from the "X dies, you gain N experience." chat line (no combat log). Loot from the chat loot line
  (uncommon+ only). Unverified in game as of 09-22: LOOT events, `Screenshot()` and file pairing.

## Coding rules

**AddOn (Lua 5.1 syntax, retail 12.x-style API):**
- Register events only via `ns.SafeRegister` (pcall). Unknown events throw on this client.
- Everything under `RambleonDB` must be a string, number, boolean or table of those. Route values through
  `ns.Clean` / `ns.CleanString`; never store Secret Values.
- No combat log, no protected APIs, no automation. If Blizzard hides something, accept it.
- Store view state in `ns`/`UI` tables, never as ad-hoc fields on frames.
- Chat stays quiet: one login line. Debug output only behind `/ramble debug on`.
- Never call `ReloadUI` without the user confirming via the `/ramble save` popup.
- Lists of client globals (`COMBATLOG_XPGAIN_*`, `LOOT_ITEM_*`) can contain nils: never `ipairs` over them directly.

**Companion:**
- Never execute SavedVariables as Lua; use `luaparse.py`. Raw snapshot first, parse second. Atomic writes.
- Merge by session id; never shrink or delete. `ramble reprocess` rebuilds normalized data from raw after upgrades.
- AI is optional: `ramble summarize` must always write the prompt file. The Claude CLI runs with `--tools ""`,
  no session persistence, an empty cwd and a writer's system prompt; never `--bare` (it bypasses the keychain login).
- Printed WTF paths go through `Paths.redact()`.
- Restart the watcher after changing companion code (`ramble service install` again); a running process keeps old modules.

**Journal writing:** only what was recorded. Names of people, quest-givers and places only from the evidence.
Feelings only as reactions to recorded events. Pronouns from the recorded gender, else name/they. Rules in
`prompts/journal.md`; voice in `prompts/voices/`.

## Dev loop

```
edit addon/Rambleon/*.lua or companion/src/rambleon/*.py
scripts/test                    # luac -p, simulated session, pytest (same as CI, macos-latest)
scripts/test -k nights          # extra args go to pytest (single test: -k name, or tests/test_x.py::test_y)
/reload in WoW                  # AddOn is symlinked; new files need a restart of WoW only when added to the TOC
ramble service install          # restart the background watcher after companion changes
/ramble debug                   # paste output + any Lua errors back here
ramble share tonight            # copy the page + pictures into site/example, commit, push (asks first)
```

`/console scriptErrors 1` shows Lua errors in game. `scripts/bootstrap` sets up uv and `ramble` from scratch.
CI (`.github/workflows/ci.yml`) runs `scripts/test`, builds the wheel and zips the AddOn; a `v*` tag makes a GitHub
release. Record user-facing changes in `CHANGELOG.md` and bump `companion/pyproject.toml` version on release.

## Command cheat sheet

In game: `/ramble` · `status` · `note <text>` · `mark` · `shots [on|off]` · `chapters` · `save` · `debug [on|off]` · `dump` · `help`.
Keybindings under AddOns: Open Adventure Log, Mark Moment.

Mac: `ramble setup [--no-ai]` · `doctor [--fix]` · `uninstall` · `install [--copy]` · `service install|uninstall|status` · `watch [--no-ai] [--no-auto] [--voice]`
· `ingest` · `reprocess` · `status` · `sessions` · `nights` · `show latest` · `export tonight|YYYY-MM-DD|--all`
· `summarize tonight [--voice] [--no-ai]` · `page tonight` · `publish` · `share [tonight|date|--all] [--yes] [--dry-run]` · `voices`
· `post [tonight|date] [--style post|thread] [--link] [--no-picture] [--yes] [--dry-run] [--force]` · `x login|logout|status`
· `catchup [tonight|date] [--copy]` · `guide [slug|latest] [--no-ai] [--voice] [--mode route|season|file.md] [--list] [--open]`.

## Where this is going

See `docs/roadmap.md`. Short version: make it install in one command for a stranger, make the chapter good
enough to paste unedited, then memory over time (timeline, people, weekly recaps, map). Free and open; the
player's data never leaves the Mac unless they run the AI step, and even then only the prompt does.
