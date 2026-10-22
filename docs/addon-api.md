# AddOn API notes for World of Warcraft: Forever

Researched 2026-09-21. Sources are listed at the end. Anything marked *verify in-game* is unconfirmed on our client.

## What Forever is, for an AddOn author

- Forever (codename **Camelot**) runs the **mainline 12.x UI codebase** ("all Modern changes up to 12.0.7" per
  warcraft.wiki.gg; Blizzard devs cite the 12.1.5 API surface) while reporting version **1.60.1**.
  It is distributed as product `wow_classic_beta`, so it lives in `_classic_beta_`, but it is not a Classic client.
- Beta: Sept 17 – Oct 21, 2026. Level cap 20, rising to 30 later.
- `GetBuildInfo()` on build 69913 returns `"1.60.1", "69913", "Sep 17 2026", 16001`.

## TOC and flavor detection

| Item | Value |
|---|---|
| `## Interface:` | `16001` |
| Flavor TOC suffix | `Rambleon_Camelot.toc` (also matched by `_Mainline`); we ship a plain `Rambleon.toc` fallback too |
| `WOW_PROJECT_ID` | `1` (`WOW_PROJECT_MAINLINE`). There is **no** Forever constant. |
| Our detection | `Forever.lua` is listed only in the Camelot TOC and sets `ns.flavorHint = "forever"`; `tocVersion == 16001` is the secondary hint |
| Game mode | `C_GameRules.GetActiveGameMode()` exists but its numbering does not match `currentGameMode "15"` in Config.wtf. Not used. |

## What is gone or restricted

- `GetSpecialization*` do not exist. Legacy globals `GetItemInfo`, `GetSpellInfo`, `UnitAura` moved to `C_*` namespaces.
- `COMBAT_LOG_EVENT` / `COMBAT_LOG_EVENT_UNFILTERED` error on registration. We never register them.
- **`RegisterEvent` throws on unknown events.** Every registration in `Events.lua` goes through `ns.SafeRegister`
  (pcall); failures are listed in `/ramble debug` and stored in the session as `failedEvents`.
- Lua error reporting stops after 100 errors per session. Keep the addon error-free; `pcall` anything uncertain.
- **Secret values (12.0):** unit health/power/auras/cooldowns/cast/threat and, in some encounter contexts, unit identity.
  Zone text, quest titles, level and map position are not restricted. `ns.Clean()` refuses secret values before
  anything reaches SavedVariables (a secret value in SV would be an error).
- `C_Map.GetPlayerMapPosition` returns nil inside instances. We record coordinates only when they are available.
- `C_UI.Reload()` is hardware-event restricted on retail. One Forever report says it is fully protected there.
  END & SAVE calls it inside `pcall` from the popup button; if the UI is still up one second later the panel says
  "Type /reload to save this chapter." *Verify in-game.*

## Names and realms

Forever has surnames and no realms, and **the client changed how it reports them** (verified in game):

| build | `UnitName("player")` | `UnitFullName("player")` | `GetRealmName()` | `GetNormalizedRealmName()` |
|---|---|---|---|---|
| 69913, 69977 (to 2026-09-23) | `"Rambleon Birdsong"` | `"Rambleon Birdsong", "ClassicBetaPvE"` | `"Classic Beta PvE"` | `"ClassicBetaPvE"` |
| 70009 (from 2026-09-24) | `"Rambleon"` | `"Rambleon", "Birdsong"` | `"Classic Beta PvE"` | `"ClassicBetaPvE"` |

`UnitGUID("player")` (`Player-4618-00BCBDC7`) stayed the same, so it is the identity. The WTF folder is still
`70/Rambleon-Birdsong`. Rambleon stores the raw results of `UnitName`, `UnitFullName`, `GetRealmName` and
`GetNormalizedRealmName` unchanged and never splits on `-`. On top of them it derives `character.surname` and
`character.displayName` with one rule, in `ns.CaptureCharacter` (AddOn) and `normalize.display_name` (companion):
the second return of `UnitFullName` is a surname when it is non-empty, is not the realm in any spelling, and the
name has no space already; the display name is the name plus that surname. Every shape above yields
`"Rambleon Birdsong"`; mainline's `"Name", "Realm"` yields `"Name"`. `Chapters.lua` carries the GUID and the AddOn
matches chapters by it (slug only as a fallback for old files). Group members are now first-name only.

## Events Rambleon uses

| Event | Used for | Notes |
|---|---|---|
| `ADDON_LOADED` | init `RambleonDB` | if nil (the beta bug), a fresh table is created; nothing is migrated |
| `PLAYER_LOGIN` | one chat line | |
| `PLAYER_ENTERING_WORLD` | start/resume the session, first zone, instance check, roster | |
| `PLAYER_LOGOUT` | suspend the session | fires before SV are written, on logout and `/reload` |
| `ZONE_CHANGED_NEW_AREA`, `ZONE_CHANGED`, `ZONE_CHANGED_INDOORS` | `ZONE_ENTER` | debounced 1.5 s; only logged when (zone, subzone) actually changes |
| `PLAYER_LEVEL_UP` | `LEVEL_UP` | arg1 = new level |
| `QUEST_ACCEPTED` | `QUEST_ACCEPTED` | retail passes `(questID)`, classic `(index, questID)`; both handled. Title from `C_QuestLog.GetTitleForQuestID`, retried once after 1 s |
| `QUEST_TURNED_IN` | `QUEST_COMPLETED` | `(questID, xp, money)` |
| `QUEST_REMOVED` | `QUEST_ABANDONED` | `(questID)`. Fires for a turn-in too, in an order the client does not promise, so the AddOn waits a second and records only a quest that was not turned in and whose title it already knew (hidden bookkeeping quests have none). **Unverified on Forever as of 2026-10-04** |
| `HEARTHSTONE_BOUND` | `HEARTH_BOUND {name}` | name from `GetBindLocation()`. **Unverified on Forever as of 2026-10-04** |
| `ENCOUNTER_END` | `BOSS_KILL {name, encounterID}` | `(encounterID, name, difficultyID, groupSize, success)`; only `success == 1`. Not the combat log. **Unverified on Forever as of 2026-10-04** |
| `PLAYER_TARGET_CHANGED`, `NAME_PLATE_UNIT_ADDED` | the target cache (`Capture.lua`) | `UnitName/UnitLevel/UnitClassification/UnitCreatureType` of hostile units, which JourneyTracker's probe found readable in combat on build 70124; every read through `ns.Clean`, a secret reads as nothing. Players: class only. **Unverified here as of 2026-10-08** |
| `MIRROR_TIMER_START` / `MIRROR_TIMER_STOP` | a death while the breath or fatigue bar is empty is a drowning / fatigue | `(timer, value, maxValue, scale, paused, label)`; after a `/reload` the client does not resend a running bar. **Unverified** |
| `UNIT_SPELLCAST_SUCCEEDED` (player) | `HEARTH_USED {to}` | `(unit, castGUID, spellID)`; spell 8690. Registered with `RegisterUnitEvent` where the client has it. The roadmap once feared spellcast data was secret; the id is cleaned before use. **Unverified** |
| `UI_INFO_MESSAGE` / `CHAT_MSG_SYSTEM` | `DISCOVERED`, `FLIGHT_PATH_DISCOVERED`, the spell name fallback | the same line arrives on both; one memory per second per text. Patterns from `ERR_ZONE_EXPLORED(_XP)`, `ERR_NEWTAXIPATH`, `ERR_LEARN_SPELL_S` / `ERR_LEARN_ABILITY_S` with English fallbacks. **Unverified** |
| `LEARNED_SPELL_IN_TAB` / `LEARNED_SPELL_IN_SKILL_LINE` | `SPELL_LEARNED` | `(spellID)`; name via `C_Spell.GetSpellName`. Forever may have one, both or neither (`/ramble debug` lists the refused one). **Unverified** |
| `hooksecurefunc("TakeTaxiNode")` | `FLIGHT {from, to}` | not an event: the hook remembers the node (`TaxiNodeName(index)`), the event is recorded once `UnitOnTaxi("player")` is true (polled each second for ten). **Unverified** |
| `PLAYER_DEAD` / `PLAYER_UNGHOST` / `PLAYER_ALIVE` | `DEATH` / `REVIVED` | **build 70009 fires `PLAYER_DEAD` twice per death**, 1–4 s apart (every death from 09-24 to 10-01 was recorded twice; 09-22 and the second character were not). The AddOn ignores a repeat within 30 s and skips `UnitIsFeignDeath`; `normalize.drop_death_echoes` does the same for old recordings (`ramble reprocess`). Revival only logged if `UnitIsDeadOrGhost` is false |
| `CHAT_MSG_LOOT` | `LOOT` (uncommon+) | the item link in the line uses the 12.x **named colour** `|cnIQ2:|Hitem:…`, not `|cff1eff00`; the parser read only the hex form until 0.3.1, which is why no night before 10-02 has loot. `/ramble debug` now shows `loot: N chat lines, M read, K kept` and the last line it could not read |
| `GROUP_ROSTER_UPDATE` | `GROUP_JOIN` / `GROUP_LEAVE`, people table | roster diff, names guarded against secret values, time together accumulated on heartbeat |
| `UPDATE_INSTANCE_INFO`, `PLAYER_ENTERING_WORLD` | `INSTANCE_ENTER` / `INSTANCE_EXIT {name}` | via `IsInInstance()` transitions. Until 0.4.0 every loading screen reset the remembered state, so the exit (which is a loading screen) was never recorded: 18 enters, 0 exits in the archive |
| `ACHIEVEMENT_EARNED` | `ACHIEVEMENT` | pcall-registered; may not exist |
| `SCREENSHOT_SUCCEEDED` | `SCREENSHOT {reason, auto, level, zone, subzone}` | no payload; the companion pairs the file by time. `reason` is `LEVEL_UP`, `MARK`, `ZONE_ENTER` when the AddOn took the picture (`auto = true`), else `MANUAL` |
| `SCREENSHOT_FAILED` | — | clears the pending reason; `/ramble debug` shows `last: failed` |

| `CHAT_MSG_SAY`, `CHAT_MSG_YELL`, `CHAT_MSG_EMOTE`, `CHAT_MSG_TEXT_EMOTE`, `CHAT_MSG_PARTY(_LEADER)`, `CHAT_MSG_RAID(_LEADER)` | `CHAT {channel, speaker, surname, text, self, ooc}` | the roleplay (`Roleplay.lua`, unreleased 2026-10-21). Read as the mainline 12.x signature `(text, sender, language, channelString, target, flags, zoneChannelID, channelIndex, channelBaseName, languageID, lineID, guid)`: slot 11 dedupes, slot 12 against `UnitGUID("player")` marks your own lines. **Unverified on Forever**: whether the sender is `Name`, `Name-Surname` or `Name Surname` (the AddOn splits on the dash), whether the guid is in slot 12, and whether a built-in emote comes as "You wave." for your own line |

Deliberately not recorded: anything from the combat log, protected or secret values, whispers, guild, trade and the
numbered channels, other players' names outside your group and what you could hear in `/say`, `/emote` and `/yell`
(a player who kills you is recorded by class). Until 2026-10-21 chat content was on this list; roleplay put it off.

### Learned from JourneyTracker (skittlenicks, MIT; its probe ran on builds up to 70124)

Kept here because each one cost someone a night to find. None verified by Rambleon itself unless said so.

- `GetZoneText()` / `GetRealZoneText()` return a building's name as the zone inside some buildings ("Lakeshire Inn",
  "Lion's Pride Inn"; Rambleon's archive has "Sentinel Tower"), and `""` for a moment after login. The map is right:
  `C_Map.GetBestMapForUnit` plus `C_Map.GetMapInfo` walked up to `mapType == 3`. Rambleon 0.5.0 does this
  (`ns.ZoneMapName`). The Deeprun Tram has no map.
- `COMBAT_LOG_EVENT_UNFILTERED` is not merely absent: registering it is a blocked action (`ADDON_ACTION_BLOCKED`) that
  `pcall` cannot catch. `CombatLogGetCurrentEventInfo` does not exist.
- Your own health and power are secret even out of combat; the aura API is blocked in combat. Hostile units' name,
  level, classification, creature type and threat situation are readable in combat.
- `UnitOnTaxi` counts as `IsMounted`. `PLAYER_MONEY` arrives before `CHAT_MSG_MONEY`; kill, quest and exploration
  events arrive before `PLAYER_XP_UPDATE`. `GetInventoryItemLink` is empty at login (retry after 3–5 s); `IsInGuild`
  is false briefly at login.
- Missing: `AcceptXPLoss` (the spirit healer shows as the `CONFIRM_XP_LOSS` dialog), `GetNumSkillLines` (skill-ups
  only via `CHAT_MSG_SKILL`), the Classic talent API (`C_ClassTalents` / `C_Traits` instead), `UnitPVPRank`.
  `C_PvP.GetZonePVPInfo` returns nothing for most zones.
- Dungeon names may carry a "The " prefix or a ": Zone" suffix ("Excavation Site: Wetlands").
- Item links carry the quality as `|cnIQ<n>:` (Rambleon has read it since 0.3.1).
- Forever-only events that exist: `AUCTION_HOUSE_SHOW_NOTIFICATION`, `LOOT_HISTORY_UPDATE_DROP`,
  `TRAIT_CONFIG_UPDATED`, `PLAYER_INTERACTION_MANAGER_FRAME_SHOW/HIDE`, `LEARNED_SPELL_IN_SKILL_LINE`.

### Automatic screenshots (0.3.0; working on Forever, pictures paired nightly since 2026-09-23)

The AddOn calls the global `Screenshot()` (retail API; other addons use it for level-up shots) from `ns.TakeScreenshot`
in `Session.lua`: one second after `PLAYER_LEVEL_UP` (the glow), 0.2 s after `/ramble mark`, and one second after the
`ZONE_ENTER` for the first visit to a new main zone tonight. Guards: `type(Screenshot) == "function"`, `pcall`, a 3 s
rate limit, `RambleonDB.settings.autoScreenshots` (`/ramble shots on|off`). The reason is parked in `ns.pendingShot`
and consumed by `SCREENSHOT_SUCCEEDED` (15 s TTL), so a manual screenshot in between would inherit it (rare, accepted).
Rambleon's own panel and chapters reader are hidden for the picture and shown again after; the game's UI is not touched. Files land in `<WoW>/Screenshots/WoWScrnShot_MMDDYY_HHMMSS.<jpg|tga|png>` per the
`screenshotFormat` CVar; the companion converts to JPEG for the web (sips) and can only *display* jpg/png.

## SavedVariables mechanics and the Forever beta bug

**Mechanics (warcraft.wiki.gg):** SV are written on logout, `/reload`, disconnect and quit; not on crash. Only strings,
numbers, booleans and tables persist. Load order: FrameXML → addon code → SV load → `ADDON_LOADED(name)` → `PLAYER_LOGIN`.
`PLAYER_LOGOUT` fires just before SV are written, so changes made there persist.

**The bug (build 1.60.1.69913, since ~2026-09-17):** the client writes `<AddOn>.lua` correctly but never opens it on the
next load. Globals are nil at `ADDON_LOADED`. It affects both `SavedVariables` and `SavedVariablesPerCharacter`, on cold
start, logout/login and (for most people) `/reload`. It reproduces with no addons installed (default Blizzard frames
lose their positions too). There is no Blizzard response. One "works after the reset" post on 09-21 is contradicted by
"no fix yet" the same day. Treat it as **not fixed**.

Consequences and our design:

1. Every login is a new session unless a `suspended` session for the same character was seen < 10 minutes ago
   (works whether or not the DB was restored).
2. WoW overwrites the file with the current in-memory table at every flush, so after a fresh login the file only
   contains the current session. The Mac watcher snapshots every write and merges by session id; an archived session
   is never shrunk or deleted by a later, smaller file.
3. We do **not** use the community workarounds (ForeverSVFix, WTFix) that load SV through the addon-file loader.
4. A crash loses the in-memory session. END CHAPTER (or `/reload`) is what makes it permanent.

## Sources

- https://warcraft.wiki.gg/wiki/TOC_format · https://warcraft.wiki.gg/wiki/WOW_PROJECT_ID · https://warcraft.wiki.gg/wiki/API_GetBuildInfo
- https://warcraft.wiki.gg/wiki/Secret_values · https://warcraft.wiki.gg/wiki/Patch_12.0.0/API_changes
- https://warcraft.wiki.gg/wiki/SavedVariables · https://warcraft.wiki.gg/wiki/Saving_variables_between_game_sessions
- https://warcraft.wiki.gg/wiki/PLAYER_LOGOUT · https://warcraft.wiki.gg/wiki/API_C_UI.Reload · https://warcraft.wiki.gg/wiki/API_C_Map.GetPlayerMapPosition
- https://us.forums.blizzard.com/en/wow/t/wowf-beta-addon-savedvariables-appear-to-write-correctly-to-disk-but-are-not-restored-at-startup/2356559
- https://us.forums.blizzard.com/en/wow/t/uiaddon-settings-wiped-on-client-restart/2353992
- https://us.forums.blizzard.com/en/wow/t/savedvariables-never-load-in-the-beta-%E2%80%94-all-addon-settings-reset-on-login-69913/2354798
- https://eu.forums.blizzard.com/en/wow/t/forever-beta-160169913-savedvariables-fail-to-load-on-client-startupreload-%E2%80%94-all-addon-settings-reset-on-restart/629888
- https://github.com/ClassicWoWCommunity/forever-bugs/issues/34 · https://github.com/nobewayo/ForeverSVFix
- https://github.com/Cidan/BetterBags/pull/1092 · https://github.com/Total-RP/Total-RP-3/pull/1367 · https://github.com/wowaddonmaker/classicuiforever/issues/13
- https://news.blizzard.com/en-us/article/24304160/the-world-of-warcraft-forever-beta-now-live
