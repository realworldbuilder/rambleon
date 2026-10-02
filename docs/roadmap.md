# Rambleon — plan to offer it to other players

Updated 2026-09-22 after two nights of real use. "Productize" here means: a stranger who plays WoW: Forever on a
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

## Decisions that are William's (not yet made)

1. **Name and identity.** "Rambleon" is the character's name. Fine as the product name? (I think yes: it sounds like
   "ramble on", and the sign-off is already "Ramble on.")
2. **Where it lives.** A public GitHub repo (`rambleon`) under your account, now or after Phase A?
3. **License.** MIT (simplest, most permissive) vs. something with attribution requirements. Recommendation: MIT.
4. **Platform scope for the first offer.** Mac only (what we can test) vs. promising Windows. Recommendation: Mac
   first, say so plainly, keep the Python core portable.
5. **AI stance.** Recommendation: prompt file always; Claude CLI if present; bring-your-own API key next; local
   Ollama as the privacy option. Never a hosted service that sees other people's play data unless they opt in.

## Phase A — Works for a stranger (target: two weeks)

Done when a friend with WoW Forever and a Mac installs it from the README and gets a chapter on night one with no
help from us.

- [ ] **One-command setup.** `ramble setup`: doctor → install AddOn → install service → open the index page.
      Detects a missing `claude` login and says exactly what to do.
- [ ] **Install without the repo.** AddOn as a versioned zip (GitHub release, later CurseForge/Wago). Companion via
      `uv tool install` from the GitHub URL, or a Homebrew tap. `RAMBLEON_HOME` defaults to `~/Rambleon` for non-dev installs.
- [ ] **Self-healing.** `ramble doctor --fix`: recreate a deleted symlink (Battle.net updater), restart a stale
      service, rebuild the index. The service restarts itself when the companion is upgraded.
- [ ] **Multi-character, multi-flavor.** Already per-character on disk; make the CLI show and select characters, and
      handle `_retail_`/`_classic_` folders if present (TOC work + a test pass).
- [ ] **First-run in game.** A one-time welcome in the panel: what it records, what it never records, `/ramble note`.
- [ ] **Capture gaps players will hit next.** Hearthstone bound/used, flight paths, rare/elite kills marked,
      new spells/talents learned, dungeon boss kills. Each one small; each one behind the "six months later" test.
- [ ] **Verify** loot events and screenshot pairing in game (still unconfirmed).
- [ ] **README for humans**: screenshots of the panel, the chapters reader, a story page; a "what leaves my Mac"
      section (nothing, unless you run the AI step, and then only the prompt).
- [ ] **License file, CHANGELOG, version bump to 0.2.0**, a GitHub Actions job that runs `scripts/test` and builds the zip.

## Phase B — Worth pasting unedited (target: the two weeks after)

- [ ] **Rating loop.** `ramble rate tonight 👍|👎 "note"` stored next to the journal sidecar; a `ramble review` that
      shows chapters and ratings side by side so the rules can be tuned on evidence.
- [ ] **Evidence density.** Quest text at accept time (`C_QuestLog.GetQuestInfo`), zone/subzone first-visit flags,
      "first time in Darnassus" moments, time-of-day in the character's world.
- [ ] **Voices.** Two or three good ones, chosen per night or per character. Keep `golden` and `field-journal`;
      add a terse "captain's log". A `ramble voices try tonight` that renders all voices for comparison.
- [x] **X.** `ramble post` and `[x] auto`: one post per night (title, the writer's one-line telling, hero picture) or
      the whole chapter as a thread. Built 2026-10-01; not yet run against the live API.
- [ ] **Recap card.** A PNG share card (title, date, stats, one line) generated from the story page for socials.
- [x] **Screenshots on the timeline** in the story page, captioned by the moment (auto shots at level ups, marks, new
      zones; hero picture; `ramble share`). Done 2026-09-22; in-game verification pending.
- [x] **Chapter continuity.** The writer gets the last three chapters as one factual line each, the previous chapter's
      text, and each companion's history (familiar or new, first met when and where, hours before tonight), with a rule
      against re-narrating old nights. `memory.py`. Done 2026-09-26.

## Phase C — Memory over time (a month out)

- [ ] Character timeline page (level curve, nights, places, companions, deaths) from the index alone.
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
- Other players appear only as the game shows them in your group. No chat content is stored.
- Raw history is never edited to make a story better. AI is downstream, always.

## Next three things (in order)

1. `ramble setup` + `doctor --fix` + install-without-the-repo (Phase A core).
2. Verify loot and screenshots in game; add hearthstone/flight path/rare capture.
3. README with pictures, license, first GitHub release.
