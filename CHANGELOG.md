# Changelog

## Unreleased — the roleplay

Rambleon turns toward roleplay. Until now the record was deeds: where you went, what fell, who you grouped with.
A roleplay night is words, and the record had none of them. Now it does.

**In game (none of it seen in the real client yet, see `docs/progress.md`)**

- **What was said in character is remembered**, word for word: `/say`, `/emote` (both `/e` and the built-in
  emotes) and `/yell` from anyone within earshot, and your own lines. New file `Roleplay.lua`, one event type
  `CHAT {channel, speaker, surname, text, self, ooc}`, counter `rpLines`. Whispers, guild, trade and the numbered
  channels are never read. The group's chat (`/p`, `/raid`) is off until you ask: `/ramble rp party on`.
- `/ramble rp [on|off]` turns it off and on (on by default); `/ramble status` says how many lines the night has.
  The panel's recent list keeps to deeds; the lines are for the page.
- A line in double brackets, `(( like this ))`, is marked out of character. A busy inn is capped at 1,500 lines a
  session; a line past that is counted as dropped, never kept.

**On the Mac**

- **Scenes.** The lines of a night are gathered into scenes (`scenes.py`): a run of lines in one zone with no five
  minutes of silence between them. A scene is told when you spoke in it, a companion of the night did, or strangers
  held a conversation (three lines, two voices); a lone "lfg" stays in the archive and off the page.
- The story page has a **Scenes** section, each scene as a script with your own lines marked, long ones folded; the
  Journey carries one italic marker where each scene began. The factual log has the same under `## Scenes`, and
  "Lines of roleplay" in Progress. The writer's prompt hands over every scene (cut in the middle past 120 lines,
  400 over the night) and the chapter rules gain a dialogue rule: quote or paraphrase a recorded line, never invent
  one; double brackets are the player out of character, never dialogue.
- This reverses a stance the docs stated since the first week ("no chat content is stored"). The reason is the one
  question: on a roleplay night the words are the adventure. What is stored is what you could hear standing there.

## 0.5.0 — 2026-10-08

The night knows more, and the season has a page. Capture techniques borrowed from
[JourneyTracker](https://github.com/skittlenicks/JourneyTracker) (skittlenicks, MIT), a Forever stats tracker, and
retold the Rambleon way: as memories, never as rankings.

**In game (0.5.0; none of it seen in the real client yet, see `docs/progress.md`)**

- **What killed you.** A death now says what did it when the client can tell: the creature you were fighting
  (with its level, and "rare" or "elite" when it was one), a fall, drowning, fatigue, or another player (class
  only, never a name). "Slain by Hogger in Elwynn Forest", "Fell to death in Thousand Needles". Older nights still
  say "Died in".
- **New moments**: `HEARTH_USED` (the stone took you home, to where), `FLIGHT` (from, to), `FLIGHT_PATH_DISCOVERED`,
  `DISCOVERED` (a place first explored; counted), `SPELL_LEARNED` (counted), `BOAT_RIDE` (two docks of one route a
  few minutes apart, no hearth or flight between; Alliance docks seen, Horde towers unverified).
- `FIRST_KILL` carries the enemy's level and its rare/elite tag when the target frame knew it. `LEVEL_UP` carries
  what tipped it (a quest, a kill, a discovery) and the gold on hand; `SESSION_START` and `SESSION_END` carry the gold
  too, so a night knows what it earned.
- **A building is not a zone.** Forever names some buildings as the zone ("Lakeshire Inn", "Sentinel Tower") and
  says nothing for a moment after login; the zone map now decides, and the building becomes the subzone. The
  archive had "Sentinel Tower" as a zone sixteen times.
- New file `Capture.lua` holds the target cache, death attribution, the movement sampler, the system-line parser,
  the taxi hook and the docks. `ns.SafeBool` and `ns.SafeRegisterUnit` in `Util.lua`.

**On the Mac**

- **The season page**, `exports/html/season-<slug>.html`, one per character from every night: how long each level
  took, firsts in the order they came, where you died and what did it, the enemies that fell most, where the hours
  went, when you play, who you travelled with, and every chapter in a row. Each section opens with a sentence
  written from its numbers; a section with nothing to say is left out. No AI. `ramble season [slug] [--open]`; a
  `season` step in the pipeline; linked from the index and every story page; copied by `ramble share`.
- The log, the route guide and the prompt show the new facts: killers on deaths, tags on first kills, discoveries
  and spells learned, gold for the night. The writer's rules now allow "what" for a death and still forbid "why".
- Lua and Python disagreed on how eight event types read, and nothing checked. The scripted evening now writes
  every line as the AddOn would say it, and a test compares (`Rambleon_simulated.describe.json`).
- The panel's "Moment remembered." line no longer overlaps the footer text beneath it.
- README: the in-game panel is pictured.

## 0.4.0 — 2026-10-04

Finished and extendable: nothing a night depends on can fail silently any more, and the three things people
ask to add (something new to remember, something new made from a night, a different way of writing it) are
each one entry in one place. `docs/extending.md` shows how.

- A command that cannot do its work says why in one line and exits 1 (a missing night, a corrupt archive file, a
  broken `rambleon.local.toml`, git or X saying no) instead of a traceback; `RAMBLEON_DEBUG=1` shows the traceback.
- A release now carries the companion wheel next to the AddOn zip, and CI checks that the wheel holds the AddOn,
  the prompts and the page styles, and that a tag matches the version.
- Journal and guide sidecars, the finish marker, X ledger entries and `Chapters.lua` carry a format version
  (a file without one is version 1).
- **Your own writing styles, in your own folder.** `<home>/prompts/` (`~/Rambleon/prompts/` for a package install;
  gitignored in a checkout): `voices/<name>.md` is a voice of your own, `guides/<name>.md` a guide mode,
  `journal.md` replaces the rules every chapter is written by, and `theme.css` is added after the page styles on
  every story page, index and route guide. A file of yours with a bundled name wins. `--voice` now also takes a
  path to a `.md` file, as `--mode` did. `ramble voices` shows which are bundled and which are yours. A `{name}`
  in your prompt that Rambleon does not fill in is pointed out when the prompt is written.
- Story page, index and route guide share one page shell (`pages.py`) and their styles live in
  `assets/page.css` and `assets/guide.css`. Story pages are byte-for-byte what they were; the index and the guide
  differ only by line breaks in `<head>`. Writing a page or the index reads the archive once instead of once per chapter.
- **`ramble finish [tonight|date]`**: do for a night everything the watcher does when you log out (log, chapter,
  route guide, story page, index, chapters in game), for a night it missed or to write one again. `--share` also
  puts the page on your site (asks first).
- **A restarted watcher catches up.** A night whose chapter was never (fully) written, because the watcher was
  down, restarted or hit an error, is finished when the watcher next starts; `ramble status` lists such nights.
  Nights older than two days are left to `ramble finish`. A chapter that already covers the night is not paid for twice.
- What happens after a night is now a list of steps (`pipeline.py`); one failing step no longer skips the rest, so
  a page that cannot be written never keeps the chapter out of the game. `ramble watch --no-ai` now still writes
  the journal prompt, as `ramble summarize --no-ai` always did.
- **A first run says hello.** The one login line welcomes a new player, and the first time the log opens a short
  note explains that there is nothing to press. Never shown again, and never to someone who already has chapters.
- The log panel has a **Pictures** row: click it to turn automatic screenshots on or off (same as `/ramble shots`).
- `/ramble help` is generated from the command list, so it now shows every command and alias (`read`, `end`,
  `screenshots`, `debug on|off`). The slash command, the keybinding and the button mark a moment the same way.
- **Three more things remembered** (AddOn): a quest you **abandon** (`QUEST_ABANDONED`; it leaves "Still open" and
  "Carrying" on the story page and the catch-up list), the inn you make **home** (`HEARTH_BOUND`), and a dungeon
  or raid **boss defeated** (`BOSS_KILL`, from the encounter's own end event, not the combat log; the route guide
  lists them). The last two are unverified on Forever until seen in game; an event the client does not know is
  skipped and shows under `/ramble debug`.
- **One definition per event type.** `addon/Rambleon/EventTypes.lua` (how it reads in game, which counter it
  bumps) and `companion/src/rambleon/events.py` (how it reads in the log, how nights are stitched, how the route
  guide and the screenshot captions treat it). A new thing to remember is one entry on each side; tests fail if
  the two disagree or the simulated session never records it. An event of a type the companion does not know yet
  is shown by its name in plain words instead of in capitals, and never breaks a page.
- **`rambleon.local.toml` is checked.** A key Rambleon does not know or a value of the wrong kind is a warning
  (`ramble doctor`, the watcher's log) and the default applies; a file that is not valid TOML is said out loud
  instead of silently switching auto-share and auto-post off. `ramble config` prints the settings in effect and
  where the file lives (`~/Rambleon/` for a package install).
- `[journal] voice = "..."` and `model = "..."` in `rambleon.local.toml` (or `RAMBLEON_VOICE` / `RAMBLEON_MODEL`):
  the background watcher can now write in a voice of your choosing. A `--voice` / `--model` flag still wins.
- AddOn settings have defaults in one table and survive upgrades; `/ramble debug on` now survives a `/reload`.
- **A chapter that fails to write no longer stops the watcher.** Every step after a night is guarded; an error is
  logged and the archiving goes on. The X auto-post's scan is guarded the same way.
- **`ramble share` commits only `site/example`.** Anything else you had staged in the checkout stays staged instead
  of riding along into the public push. Its scratch folder is cleaned up.
- **Leaving a dungeon is recorded.** A loading screen made the AddOn forget it was inside, so no night ever had an
  "Left …" line. The exit now carries the instance's name, and a `/reload` inside is not a second arrival.
- The chapters reader stays out of automatic screenshots (it never hid), and shows the published date as written.
- A session resumes by character GUID; the name only decides for sessions recorded before the GUID was.
- `ramble doctor` no longer asks the Claude CLI a (paid) question on every run; `ramble doctor --check-ai` does.
- Tests no longer depend on the clock, the timezone or this Mac's `rambleon.local.toml`; the simulated session is
  the same bytes on every run. CI skips pushes that only add a shared journal page.
- **Loot was never recorded.** Item links on the 12.x codebase carry a named colour (`|cnIQ2:`), not the old hex
  colour, and the parser only knew the hex form, so no uncommon-or-better loot and no equip was ever kept. Both
  spellings are read now (quality from the API, else from the link). `/ramble debug` shows how many loot lines
  arrived, how many were read, and the last one that was not.
- **Deaths were counted twice.** Since Forever build 70009 the client fires `PLAYER_DEAD` twice per death, a few
  seconds apart, and every death from 09-24 on was recorded twice (13 on the night of 10-01; 8 real). The AddOn now
  ignores a repeat within 30 seconds, and the companion drops the echo from old recordings: `ramble reprocess`
  rebuilds the archive (normalized version 3; a renormalized session may hold fewer events than before, once).
- The writer treats a death as a fact, not a verdict: at most one dry sentence per chapter however many there were,
  never the title or the social post, and never a reason the record does not contain ("careless", "a lesson").
  Same for the route guide and the season recap.
- `ramble post [tonight|date]`: tell a night on X. One post with the chapter title, the night in one or two sentences
  and the hero picture (with its caption as the picture's description); `--style thread` posts the whole chapter as a
  thread; `--link` adds the shared story page (X charges far more for a post with a link, so it is off by default);
  `--dry-run` shows the text and posts nothing; `--lowercase` (or `[x] lowercase = true`) posts in all lower case.
  It asks before posting. `ramble x login|logout|status` keeps the four
  keys of your own X developer app in the macOS Keychain (X's API is pay-per-use, about 1.5 cents a post).
  `[x] auto = true` in `rambleon.local.toml` lets the watcher post by itself: once per night, after the chapter was
  written and the night has been quiet for `delay` minutes (default 30). Tonight's chapter is held while you are
  still in the world, and a chapter older than two days is never posted. `archive/posts/x.json` remembers what was posted so nothing goes out twice.
- The journal prompt now also asks for a `---POST---` line (the night in miniature, at most 200 characters); it is
  kept in the journal sidecar as `post`. Chapters written before this use the opening sentences of the chapter.
- Index page: with more than one character it is no longer one mixed list under the last-played name. A roster at
  the top (race, class, faction, level, chapters, last played) jumps to a section per character, each with its own
  chapters and route guide link. "All chapters" on a story page or guide returns to that character's section.
  One character: unchanged.
- In-game chapters: `Chapters.lua` keeps the last 12 nights **per character**, so a second character's nights never
  push the first one's chapters out of `/ramble chapters`. Recording, nights, numbering, memory and the route guide
  were already per character.
- Story pages: a **Quests** section between the stats and the timeline lists what was turned in that night (by zone,
  with the turn-in spot and level), what was picked up but not finished, and what is still being carried from earlier
  chapters ("since Chapter 3"), so a friend playing alongside can see what to do and what to hold off on. A jump link
  takes you there. `ramble catchup` prints the same carry-over list. Abandoned quests are not recorded, so the
  carry-over list says what Rambleon knows, not what the quest log holds.
- `ramble guide`: a route guide per character — how they actually leveled, one zone stretch per chapter with a numbered
  sidebar, the quests picked up and turned in, first kills, loot, deaths, companions and your notes, drawn from every
  night. Not the best route; the road taken. AI prose when the Claude CLI is present, written by the watcher only when
  a new night was added. Modes say what to write from the same facts: `route` (for another player, default), `season`
  (the story so far, for you) or `--mode your-prompt.md`; `[guide] mode` in `rambleon.local.toml` sets the watcher's.
  The page is linked from the index and every story page, and `ramble share` copies it to the site along with the
  chapters, so sharing now also publishes one page that sums up the whole character.
- `ramble catchup [tonight|date]` prints a plain-text list of the quests turned in that night, grouped by zone with
  the turn-in spot and level, plus the quests picked up but not finished, ready to paste to a friend who wants to catch
  up. `--copy` puts it on the clipboard; a copy lands in `exports/social/<date>-<slug>-catchup.txt`.
- Chapter continuity. The journal prompt now carries a "Story so far" block (one factual line for each of the last
  three chapters, and the previous chapter as it was written) and marks every companion as familiar or new, with the
  night they were first met, where, and the hours shared before tonight. The writer continues the story instead of
  starting over, and an old friend is never introduced as a stranger. `[people."Name"] note = "..."` in
  `rambleon.local.toml` hands the writer your own words about a person. Re-run `ramble summarize <date>` to rewrite
  a chapter that mis-introduced a friend, then `ramble publish`.
- Site: one slim top bar on every page, previous/next chapter links, jump links (Story · Recap · Journey · Notes)
  and a foldable timeline on story pages, a card list on the chapter index, a how-it-works strip and a tabbed Quick Start
  (terminal, a paste-into-Claude-Code prompt, from source) on the landing page.
  `ramble share` re-renders the neighbouring chapters already on the site so their links pick up the new one.
- `[share] auto = true` in `rambleon.local.toml` makes the watcher push every finished chapter to GitHub Pages
  (off by default; the file is gitignored, so it is a per-Mac choice). `docs/invite-prompt.md`: a paste-ready
  message that installs Rambleon for a friend through Claude Code.
- Forever build 70009 changed the name API (`UnitName` → first name, surname in `UnitFullName`'s second return), which
  hid every earlier chapter in `/ramble chapters` and started the companion on a "new" character. The AddOn and the
  companion now derive one display name from the raw fields, `Chapters.lua` carries the character GUID and the game
  matches chapters by it. `ramble reprocess` repairs sessions recorded on the new build.

## 0.3.0 — 2026-09-22

- Automatic screenshots at level ups, `/ramble mark` and the first visit to a new zone each night (`/ramble shots on|off`).
  The UI stays visible. Unverified on Forever until the next session; `/ramble debug` reports whether `Screenshot()` worked.
- Screenshots are captioned by the moment they were taken ("Reached Level 9 in Dolanaar") and copied into the archive
  by default; pictures taken after the last save are paired when the chapter is written.
- Story page: a hero picture, the rest inline on the timeline; thumbnails on the index; web-sized JPEG copies.
- The journal prompt lists when pictures were taken (never what they show).
- `ramble share [tonight|date|--all]`: copy a night's page and pictures into `site/example`, commit and push to GitHub Pages
  after a confirmation. `scripts/publish-example` now wraps it.
- Example journal on GitHub Pages (`site/`).

## 0.2.0 — 2026-09-22

- The log just runs: no END CHAPTER. Logging out is the save; `/ramble save` is an optional flush.
- A chapter is a night: every session of one evening stitched together (`ramble nights`, `ramble export tonight`).
- Chapters published back into the game: `/ramble chapters` with selectable text.
- HTML story pages with screenshots, plus an index page (`ramble page tonight`).
- Background watcher as a launchd service (`ramble service install`); chapter written the moment you log out.
- `ramble setup` (one command), `ramble doctor --fix`, `ramble uninstall`, `ramble reprocess`.
- Kills (from the experience chat line), XP, quest objective completions, uncommon-or-better loot and equips.
- Journal voices (`golden`, `field-journal`); character gender recorded; names only from the evidence.
- The companion package now carries the AddOn, so it installs without a checkout.
- MIT license; public repository.

## 0.1.0 — 2026-09-21

- First playable: AddOn loads on WoW: Forever (Interface 16001), `/ramble` panel, session and event model,
  notes and marks, SavedVariables watcher, immutable archive, Markdown export, AI prompt and Claude CLI adapter.
