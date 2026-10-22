# Rambleon — plan to offer it to other players

Updated 2026-10-04 (release 0.4.0), after two weeks of nightly use. "Productize" here means: a stranger who plays WoW: Forever on a
Mac can install it in one sitting, never think about it again, and get a chapter they want to paste somewhere.
Free and open. Money, if ever, is a tip jar or a nicer Mac app later; never a gate on the data.

## What two nights taught us

- The loop works. Play → logout → chapter in game and on a page, unattended.
- Players hate ceremony. No "end" button. The log runs; logout saves. (Done.)
- The first questions are always "why isn't X in it?" — kills, then loot. The capture list is driven by the player's
  memory of the night, not by API availability. Expect more of these: hearthstones, flight paths, rares, talents.
- The AI chapter is the product. Voice matters more than expected, and the honesty rules need teeth: the model
  will happily invent an NPC it knows from lore or guess a character's gender. Every named thing must trace to evidence.
- "Is it there yet?" will be every user's first support question. Show state everywhere: publish time in game,
  a notification on the Mac, the story page opening itself.

## Decisions (made 2026-09-22)

1. **Name.** Rambleon: the character's name, and "ramble on".
2. **Where it lives.** Public on GitHub: `realworldbuilder/rambleon`.
3. **License.** MIT.
4. **Platform for the first offer.** Mac only, said plainly. The Python core stays portable; Windows is not planned yet.
5. **AI stance.** The prompt file always; the Claude CLI when it is there. Never a hosted service that sees other
   people's play data. A hosted site is shelved (2026-09-25) until the core has earned it.

## Phase A — Works for a stranger

Done when a friend with WoW Forever and a Mac installs it from the README and gets a chapter on night one with no
help from us.

- [x] **One-command setup.** `ramble setup`: doctor → install AddOn → install service → open the index page.
      Detects a missing `claude` login and says exactly what to do.
- [x] **Install without the repo.** AddOn as a versioned zip (GitHub release, later CurseForge/Wago). Companion via
      `uv tool install` from the GitHub URL, or a Homebrew tap. `RAMBLEON_HOME` defaults to `~/Rambleon` for non-dev installs.
- [x] **Self-healing.** `ramble doctor --fix`: recreate a deleted symlink (Battle.net updater), restart a stale
      service, rebuild the index. A watcher that was down or crashed finishes the nights it owes when it starts
      (0.4.0). Still open: the service restarting itself when the companion is upgraded.
- [ ] **Multi-character, multi-flavor.** Already per-character on disk; make the CLI show and select characters, and
      handle `_retail_`/`_classic_` folders if present (TOC work + a test pass).
- [x] **First-run in game.** A welcome in the one login line and a one-time note the first time the log opens (0.4.0).
- [x] **Capture gaps players will hit next.** Done in 0.4.0: abandoned quests, hearthstone bound, dungeon boss
      kills, leaving an instance. Done in 0.5.0, techniques borrowed from JourneyTracker: what killed you, hearthstone
      used, flights and flight paths, discoveries, spells learned, rare/elite tags on first kills, boat rides, the
      level's cause and gold. Still open: talents (`TRAIT_CONFIG_UPDATED` exists on Forever), the Forever campfire.
- [x] **Verify** loot events and screenshot pairing in game. Both confirmed by the archive: loot since 10-02,
      paired pictures since 09-23.
- [ ] **README for humans**: the in-game panel (a 0.3.0 screenshot, before the Pictures row), a story page and the
      route guide are pictured, and "what leaves my Mac" is written. Still open: a picture of the chapters reader
      (no screenshot of it exists yet).
- [x] **License file, CHANGELOG, releases**, a GitHub Actions job that runs `scripts/test` and builds the zip and the wheel.

## Phase B — Worth pasting unedited

- [ ] **Rating loop.** `ramble rate tonight 👍|👎 "note"` stored next to the journal sidecar; a `ramble review` that
      shows chapters and ratings side by side so the rules can be tuned on evidence.
- [ ] **Evidence density.** Quest text at accept time (`C_QuestLog.GetQuestInfo`), zone/subzone first-visit flags,
      "first time in Darnassus" moments, time-of-day in the character's world.
- [ ] **Voices.** Your own voices, guide modes, journal rules and page theme live in `<home>/prompts/` (0.4.0), and
      `[journal] voice` picks one for the watcher. Still open: a terse "captain's log" in the box, and
      `ramble voices try tonight` to render every voice for comparison.
- [x] **X.** `ramble post` and `[x] auto`: one post per night (title, the writer's one-line telling, hero picture) or
      the whole chapter as a thread. Built 2026-10-01; the live API refused the first try (the developer app was not enrolled in a project), so no
      post has gone out yet.
- [ ] **Recap card.** A PNG share card (title, date, stats, one line) generated from the story page for socials.
- [x] **Screenshots on the timeline** in the story page, captioned by the moment (auto shots at level ups, marks, new
      zones; hero picture; `ramble share`). Done 2026-09-22; in use since 09-23.
- [x] **Chapter continuity.** The writer gets the last three chapters as one factual line each, the previous chapter's
      text, and each companion's history (familiar or new, first met when and where, hours before tonight), with a rule
      against re-narrating old nights. `memory.py`. Done 2026-09-26.

## Phase C — Memory over time

Each of these is a new output: one step in `pipeline.py` and a body inside `pages.shell` (`docs/extending.md`).


- [x] **The season page** (`ramble season`, 0.5.0): the level curve with the slow and fast levels, firsts in order,
      deaths by place and by killer, the enemies that fell most, where the hours went, when you play, company, and
      every chapter in a row, with a sentence per section written from its numbers. `season.py`. Done 2026-10-08.
      What it deliberately is not (JourneyTracker has them): rankings against other players, percentiles, a hosted
      upload site, joke one-liners, chat-word tallies, PvP and economy telemetry, a heat map.
- [ ] People page: first met, last seen, hours together, nights shared.
- [x] **Route guide** (`ramble guide`): the nights cut into zone stretches with the level range reached there, one page
      per character, facts always and prose per stretch from a *mode* prompt (`route` for another player, `season` for
      the player, or your own file). The season-grouping idea, done as the player's own path, never as advice. `guide.py`.
      Done 2026-09-26.
- [ ] Weekly recap (a mode over the last seven nights, once the guide's stretches can be windowed).
- [ ] Adventure map: `ZONE_ENTER` coordinates plotted on the client's own map images (no asset bundling).
- [ ] `ramble ask "when did I first meet Tiamaat?"`: answers grounded in the archive.

## Phase D — The Mac app (only if A–C hold up)

A small menu-bar app wrapping `ramble`: status dot, last chapter, open tonight's page, open the journal folder,
voice picker. Signed and notarised .dmg. This is where a "buy me a coffee" could live. The CLI stays free and complete.

## Non-negotiables

- Passive. Never automates, never touches protected or secret values, never needs the network in game.
- Plain files on the player's disk. Export everything and delete everything are each one command.
- Other players appear as the game shows them to you: your group's roster, and (since 2026-10-21) what anyone said
  in `/say`, `/emote` or `/yell` within earshot. Whispers, guild and the channels are never stored; the group's chat
  only when the player turns it on. Until 2026-10-21 this line read "No chat content is stored"; a roleplay night is
  its words, so the stance changed. Publishing a page with other people's lines on it is still the player's own act.
- Raw history is never edited to make a story better. AI is downstream, always.

## Phase R — The roleplay (begun 2026-10-21)

The turn William asked for: Rambleon as the roleplayer's memory. The first cut records what is said in character
and tells it as scenes; what follows builds on that.

- [x] `/say`, `/emote`, `/yell` and your own lines as `CHAT` events; group chat opt-in; scenes on the page, in the
      log and in the prompt; a dialogue rule for the writer. Unverified in game.
- [ ] Verify the chat events on Forever: sender format (`Name`, `Name-Surname`?), the guid in slot 12, whether a
      built-in emote arrives as "You wave." for your own and "Cassidy waves at you." for others.
- [ ] A **People** page that remembers the people by what they said: first met, last seen, their lines with you.
- [ ] A scene the player marks by hand (`/ramble scene <title>`), so a planned RP event has a name before the Mac
      guesses one. Until then `/ramble note` and `/ramble mark` do the job.
- [ ] A `transcript` mode for the guide (`prompts/guides/`): the night's scenes as a clean script, nothing else.
- [ ] Decide what the AI chapter does with a scene the player was only a witness to.
- [ ] Whispers: never, or opt-in with the other party's lines left out? Left out until someone asks.

## Next three things (in order)

1. Pull on the gaming Mac, restart WoW (two new files in the TOC), play a roleplay night, and tick off the
   roleplay items and the 0.5.0 items at the top of `docs/progress.md`.
2. Get one post out on X for real, or take X out of the README until it has worked once.
3. The People page, now with the words (Phase R), then Phase B's rating loop.

## Deliberately left for later

- Splitting `Session.lua` further (850 lines). 0.5.0 put the new capture in `Capture.lua`; moving kills, objectives,
  loot and screenshots out too is a pure move whose only risk shows in game.
- The heat map: JourneyTracker samples the map square every five seconds and draws it on the zone art, which it
  reads from the client. Capture would be cheap (`where[mapID][square] += 5`); the drawing needs the art. Not taken
  until the adventure map (Phase C) has a way to show it.
- A Blizzard Settings panel category. `/ramble shots` and the Pictures row cover the one setting; the Settings API
  is unverified on Forever.
- Localization (the AddOn's own text is English; chat parsing already uses the client's localized formats).
- Other WoW flavours, Windows, plugin loading from third-party packages, the journal on its own branch.
