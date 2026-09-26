# Changelog

## Unreleased

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
