# Progress

## 2026-10-02 — Deaths were counted twice

- Looking into why the chapters dwelt on dying: the raw archive showed every DEATH recorded twice, 1–4 s apart, with
  one REVIVED per pair, on every night from 09-24 (build 70009) on. 74 recorded deaths were 46. 09-22 and Winterland
  Dew's nights had no doubles. The prose followed the data ("died once, and died again moments later, the kind of
  careless end…", "nine deaths there", a guide saying "died seventeen times" where it was nine).
- AddOn: `PLAYER_DEAD` within 30 s of the last recorded death is the same death; `UnitIsFeignDeath` skipped.
  Companion: `normalize.drop_death_echoes` (normalized version 3); a renormalized session may shrink once on
  reprocess. Archive reprocessed: every night now has DEATH == REVIVED.
- Prompts: a death is a fact, not a verdict. One dry sentence per chapter at most, never the title or the post,
  never a reason the record lacks. Same in the route and season guide modes. Chapter 10 and the route guide were
  rewritten; chapters 1–9 keep their old prose (correct counts on their pages and recaps only where regenerated).

### To verify next session
- Loot a green: `/ramble debug` should say `loot: … 1 kept` and `/ramble dump` show "Looted …". If `read` stays 0,
  paste the `last unread loot line`.
- One death in game → exactly one "Died in …" line in `/ramble dump` and one DEATH in the night's JSON.

## 2026-09-21 — Day one

Goal: first playable milestone (AddOn loads, `/ramble` works, a session is captured, `ramble export latest` produces Markdown).

### Done
- Inspected the Mac and the WoW: Forever install (`environment.md`). Only `_classic_beta_` (1.60.1.69913) is installed.
- Researched the Forever client: mainline 12.x codebase, TOC `16001`, `_Camelot` suffix, `WOW_PROJECT_ID` = mainline,
  Secret Values, missing spec APIs, `RegisterEvent` throwing on unknown events (`addon-api.md`).
- Researched and documented the SavedVariables restore bug on build 69913 (`addon-api.md`); designed around it:
  every login is a new session, the Mac archive owns history, blank files never erase anything.
- Repository, `.gitignore`, git initialised.
- **AddOn v0.1.0** (`addon/Rambleon`): `Rambleon_Camelot.toc` + `Rambleon.toc`, session model (schema 1), events
  (zones with debounce, levels, quests, deaths, group roster + time together, instances, achievements, screenshots),
  manual notes and marks, parchment panel with stats + recent journey + MARK MOMENT / ADD NOTE / END CHAPTER,
  `/ramble` commands (`status`, `note`, `mark`, `end`, `debug`, `dump`), keybindings, END & SAVE popup with
  `/reload` fallback. Symlinked into `_classic_beta_/Interface/AddOns/Rambleon`.
- Offline harness: `addon/tests/wowstub.lua` + `run.lua` simulate a full session under Lua 5.5 and emit a
  Blizzard-format SavedVariables fixture.
- **Companion v0.1.0** (`companion/`, `ramble`): `doctor`, `install`, `watch`, `ingest`, `status`, `sessions`, `show`,
  `export`, `summarize`. Hand-written SavedVariables parser (verified on all 38 real Blizzard SV files on this Mac,
  plus torn-file detection), immutable archive with merge rules, polling watcher, screenshot pairing, factual
  Markdown export, AI-neutral prompt + Claude CLI adapter. 19 pytest cases. `uv tool install` → `ramble` on PATH.
- `ramble doctor` on this Mac: WoW Forever FOUND, AddOn INSTALLED (symlink, TOC 16001), Archive READY, Claude CLI FOUND.
- Docs: `environment.md`, `addon-api.md`, `data-model.md`, `CLAUDE.md`, `README.md`.

### Confirmed in game (2026-09-21, first session)
- Rambleon loads on Forever with Interface 16001; `/ramble` opens the panel; no event registration failed.
- `UnitName("player")` and `UnitFullName("player")` both return `"Rambleon Birdsong"`; realm `"Classic Beta PvE"`,
  normalized `"ClassicBetaPvE"`; `WOW_PROJECT_ID` 1; build 69913; GUID `Player-4618-…`; Dolanaar has mapID 1438.
- WoW wrote `Rambleon.lua` on `/reload`; `ramble watch` captured it within seconds and archived the session.
- **SavedVariables were restored across `/reload`** for this player (the session resumed: "Picked the story back up").
  Cold start behaviour still unknown.
- **`C_UI.Reload()` works from the END & SAVE button** on Forever (confirmed by the player).
- Bindings.xml must not use the `header` attribute, and must not be listed in the TOC at all (fixed).
- Group members and the zone were logged twice after a resume (fixed: the resume seeds roster and zone silently).
- Kills were invisible. Added kill tracking from the "X dies, you gain N experience." chat line, XP accounting,
  and quest objective completion events. The combat log stays untouched.

### Added after the first session
- `/ramble chapters`: an in-game reader for published chapters (journal or factual log + recap) with selectable text.
  The companion writes `addon/Rambleon/Chapters.lua`; WoW loads it as an addon file on `/reload`.
- `ramble page latest`: HTML story page (journal, recap, stats, screenshots, timeline) in `exports/html/` for Substack.
- `ramble watch` now runs export → journal → page → publish automatically when an ended chapter is captured.
- `ramble reprocess` rebuilds normalized sessions from raw snapshots after companion upgrades.

### Design change: running log, no END CHAPTER (player feedback)
- The END CHAPTER button is gone. The log just runs; logout writes it; `/ramble save` is an optional flush.
- A chapter is now a *night*: every session of an evening stitched together (`companion/src/rambleon/nights.py`).
  `ramble nights`, `ramble export tonight`, `ramble summarize tonight`, `ramble page tonight`.
- `ramble watch` finalizes a night ten minutes after the last write (the AddOn's resume window), or at once after
  `/ramble save`, then exports, journals, builds the page and publishes to the game.
- RESUMED markers are kept in the data but hidden from every rendered timeline.

### Loot (player request)
- `LOOT` events for uncommon-or-better items received (loot, quest rewards, crafted) via the chat loot line, and
  `EQUIP` events for uncommon-or-better items equipped (once per item per session). Quality from
  `C_Item.GetItemQualityByID`, falling back to the link colour. Panel row "Loot Worth Keeping"; export section; prompt section.

### Late-night improvements (2026-09-21, after the player left)
- `ramble service install|uninstall|status`: the watcher as a launchd user agent (starts at login, no terminal).
- Night finalization now fires the moment the player leaves: WoW process gone, or `Logs/Client.log` shows a logout
  after the last save (`wowstate.py`); the ten-minute timer stays as the fallback.
- macOS notification when a chapter is written; `exports/html/index.html` lists every night; the in-game chapters
  reader shows when chapters were last published.
- End level is now derived from event levels on both sides (the client's level at logout came back stale: a
  session with a `LEVEL_UP` to 9 still had `endLevel = 8`).
- The stale terminal watcher was replaced by a background `ramble watch` (log: `~/Library/Logs/Rambleon/watch.log`).
- `docs/roadmap.md`: the product plan.

### 2026-09-22
- Overnight: logout detection fired 5 s after the 23:35 write; chapter exported, page built, published. AI skipped
  (CLI logged out). Background watcher did not survive the night → player installed `ramble service` (launchd).
- Player logged the Claude CLI in; first AI chapter written. Every specific checked out against the log except one
  flourish ("didn't put up much of a fight").
- Voice profiles: `prompts/voices/*.md`, `ramble voices`, `--voice`, `RAMBLEON_VOICE`. Default is now `golden`
  (a Christie Golden-style warm close third person) at the player's request; `field-journal` is the original.
- Golden draft invented a quest-giver (Loganaar) and guessed the character's gender. Fixes: rule 6 now forbids
  names not in the evidence; the AddOn records `character.gender` from `UnitSex`; the prompt says to use the
  name or they/them when gender is not recorded.

### 2026-09-22, afternoon — productizing
- Decisions (William): public GitHub repo now, MIT, Mac only for the first offer, one-command setup first.
- Public repo: https://github.com/realworldbuilder/rambleon (MIT). CI runs `scripts/test`, builds the wheel and the
  AddOn zip; a `v*` tag makes a GitHub release with the zip.
- 0.2.0: `ramble setup` (link AddOn + launchd service + journal index + doctor), `ramble doctor --fix`,
  `ramble uninstall`, Claude login check in doctor. The wheel bundles the AddOn; without a checkout it is unpacked
  to `~/Rambleon/addon/Rambleon` and upgraded by TOC version, keeping Chapters.lua.
- Verified: install from the built wheel in a clean venv against a fake WoW tree (install → doctor → ingest → publish).
- CLAUDE.md rewritten for the current product; roadmap rewritten as the "offer it" plan (phases A–D).

### 2026-09-22, evening — pictures
- The AddOn now takes screenshots itself (`Screenshot()`, guarded) at level ups, `/ramble mark` and the first visit to
  a new main zone each night; `/ramble shots on|off`; the SCREENSHOT event carries the reason.
- Companion: files pair with SCREENSHOT events (not "nearest event", which was always the screenshot itself), captions
  like "Reached Level 9 in Dolanaar", copies into `archive/screenshots/` by default, re-pairing when the chapter is
  written so a picture taken after the last save still lands.
- Story page: hero picture + pictures on the timeline, web copies named `<page>-NN.jpg` (sips, 1600 px) so they are
  not caught by the `WoWScrnShot_*` ignore rule; thumbnails on the index. Prompt lists when pictures were taken.
- `ramble share tonight|--all [--yes] [--dry-run]` copies pages + pictures into `site/example`, commits, pushes after
  asking. `scripts/publish-example` wraps it. 0.3.0.
- Test stub: `time()` now follows the simulated clock, so the fixture's events are spaced like a real evening.

### Test script for the first night with pictures (2026-09-23)
In game, in order, with `/console scriptErrors 1`:
1. `/reload` → `/ramble debug` must show `auto shots: on, Screenshot(): available`. If `missing`, stop: Forever has no `Screenshot()`.
2. `/ramble mark` → flash; `/ramble dump` ends with "Screenshot (marked moment)".
3. `/ramble mark` again at once → no flash (rate limit). Subzone walk → no flash. New zone → one flash ~2.5 s after the
   name appears. Level up → flash ~1 s after the ding. Manual screenshot key → dump shows "Took a screenshot".
4. `/ramble shots off` + mark → no flash; `/ramble shots on`. Paste `/ramble debug` before logging out.
On the Mac after logout: `ls "<WoW>/_classic_beta_/Screenshots/"` (note the extension), `ls archive/screenshots/*/`,
`ramble page tonight` (hero + timeline pictures), then `ramble share tonight` only if it should be public.

### To verify next session
- `Screenshot()` exists and fires `SCREENSHOT_SUCCEEDED` on Forever: `/ramble debug` → `auto shots: on, Screenshot(): available, last: ok`
  after a `/ramble mark`; a file appears in `_classic_beta_/Screenshots/` (which format? `screenshotFormat` CVar).
- Level-up picture shows the glow (1 s delay); zone picture is not a loading-screen fade (1 s after the debounce).
- Two marks within 3 s → one file; a subzone walk → no picture; `/ramble shots off` survives a cold start?
- After logout: `archive/screenshots/<session>/` populated, story page shows the hero + timeline pictures,
  `ramble share --dry-run` lists them.
- Loot capture in the real client (the three greens came before the loot code was loaded; no LOOT events yet).
- Whether `/ramble chapters` shows tonight's chapter after login (published at 23:27, republished after reprocess).
- Whether logout detection fires (watch.log will say "logged out — writing the chapter").

### Known issue found tonight
- The standalone `claude` CLI on this Mac reports "OAuth access token has been revoked", so `ramble summarize` skipped
  the AI chapter and only wrote the prompt (correct degraded behaviour). Fix on the Mac: run `claude` in a terminal
  and `/login`, then `ramble summarize latest` again.

### Next: first in-game test (needs the player)
1. `ramble watch` in a terminal.
2. Log in as Rambleon Birdsong. If Rambleon is greyed out in the AddOns list, enable "Load out of date AddOns" and
   report the interface number the game expects.
3. `/ramble` → panel titled RAMBLEON BIRDSONG. Walk somewhere new, accept/finish a quest, `/ramble mark`,
   `/ramble note hello from azeroth`, `/ramble debug` (paste the output).
4. END CHAPTER → END & SAVE. If the UI does not reload, type `/reload`.
5. The watcher prints `captured …`. Then `ramble export latest` and `ramble summarize latest`.

### Open questions (resolve on first in-game test)
- What `UnitFullName("player")` / `GetRealmName()` return on Forever for a two-part name (`/ramble debug`, session JSON).
- Whether `C_UI.Reload()` works from the END & SAVE button or is protected on Forever.
- Whether `QUEST_TURNED_IN` fires with a questID on this build.
- How chatty `ZONE_CHANGED` subzone transitions are in starting zones (debounce is 1.5 s).
- Whether the per-character SV file lands under `WTF/Account/<acct>/70/Rambleon-Birdsong/SavedVariables/`.
- Whether `QuestBG-Parchment` atlas exists (harmless either way) and how the panel looks.
- Any events listed under "failed events" in `/ramble debug`.

### 2026-09-24 — Forever build 70009 changed the player's name API; only one chapter showed in game
- Symptom: `/ramble chapters` listed only tonight's chapter. Cause: the client update (69977 → 70009, "Sep 23 2026")
  now returns `UnitName("player")` = `"Rambleon"` and `UnitFullName` = `"Rambleon", "Birdsong"`. The AddOn's display
  name became "Rambleon", slug `rambleon`, and the chapter window filters by slug; the companion treated it as a new
  character (night `night-2026-09-24-rambleon`, "Chapter 1" again, own story-page group, local overrides not applied).
  The GUID never changed.
- Fix: `ns.Surname` / `ns.ComposeDisplayName` (AddOn) and `normalize.surname` / `display_name` (companion) derive
  `displayName` from the raw fields; `Chapters.lua` carries `guid` and `myChapters()` matches by GUID first, slug as
  fallback. `NORMALIZED_VERSION` 2. Tests for both shapes plus mainline in `run.lua` and pytest.
- Repair: `ramble reprocess` (tonight's two sessions → `rambleon-birdsong`), journal sidecar renamed to
  `night-2026-09-24-rambleon-birdsong` and renumbered to Chapter 4 (text kept), stale `2026-09-24-rambleon*` exports
  removed, `export`/`page`/`publish` rerun, watcher restarted. `Chapters.lua`: 4 chapters, one slug, GUID on each.
- Note: finalization reruns the AI journal for the night, so tonight's text is rewritten again when the player logs out.
- Later that night: `[share] auto = true` (local toml) → the finalizer calls `share` with `yes=True` after publishing;
  this Mac opted in. A bare-environment `git push --dry-run` with the launchd PATH succeeded (osxkeychain), so the
  service can push. `docs/invite-prompt.md` written for a friend.
- To verify in game: `/reload` → `/ramble chapters` shows "4 of 4"; `/ramble debug` shows displayName Rambleon Birdsong.

### 2026-09-27 — Quests on every chapter page (player request)
- Friends who play alongside want to see, per chapter, which quests were picked up and turned in. `publish.py` adds a
  Quests section (turned in by zone with level, picked up but still open, still carrying from earlier chapters with
  the chapter it was accepted in) before The Journey, plus a jump link. `export.carried_over(prior, night)` computes
  the carry-over from `nights.earlier_nights`; `ramble catchup` prints the same list. Caveat on the page: abandoned
  quests are not recorded (no QUEST_REMOVED handler in the AddOn), so the carry-over is what Rambleon saw.
- Restart the watcher (`ramble service install`) so the next finished chapter gets the section.

### Later
- Milestone 2: nicer timeline, satisfying MARK MOMENT, minimap button or keybind polish, Tier 2 events (loot, hearth).
- Milestone 3: chapter numbering across many sessions, recap cards, weekly recap.
