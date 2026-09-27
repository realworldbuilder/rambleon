# Changelog

## Unreleased

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
