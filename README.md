# Rambleon

**Your Azeroth adventure journal.** Play World of Warcraft normally. Rambleon quietly remembers the night. When you
log out, it hands you a permanent record: a timeline, a factual log, a story page with your screenshots, and a
journal chapter written from what actually happened, readable in game and ready to paste anywhere.

> *At Lake Al'Ameth he found the work turned strange and solitary — timberlings, one after another, seeds and
> sprouts to be gathered from creatures that should not, by any right, have walked. He wrote it down himself, plain
> as the water: "alone at the lake slayin timberlings".*
> — Chapter 1, written by Rambleon from one Tuesday night in Teldrassil

**See a real journal:** https://realworldbuilder.github.io/rambleon/example/

| In game: `/ramble` | A night's story page | The route guide: how the character actually leveled |
|---|---|---|
| ![The adventure log panel in game: tonight's numbers and the recent journey](docs/img/panel.jpg) | ![A story page: chapter title, the night's hero screenshot, the chapter](docs/img/story-page.jpg) | ![The route guide: zone stretches with level ranges, prose and facts](docs/img/route-guide.jpg) |

Rambleon is a **memory layer**, not a meter. It never automates anything, never reads protected combat data, and
never needs the network in game. Think Strava recap, travel journal, captain's log.

**Status:** early, real, and used nightly by its author on the **World of Warcraft: Forever** beta, on **macOS**.
Other WoW flavours and Windows are not supported yet. MIT licensed.

## What a night looks like

```
Rambleon Birdsong · September 21, 2026 · 1h 47m in Azeroth

 9:47 PM — Began the adventure
 9:47 PM — Joined forces with Hazardelf (Rogue)
 9:55 PM — Completed "Zenn's Bidding"
10:01 PM — Entered Starbreeze Village (Teldrassil)
10:13 PM — 8/8 Timberling Seed — "Timberling Seeds"
10:14 PM — Note: "alone at the lake slayin timberlings"
10:24 PM — Reached Level 9
11:01 PM — Joined forces with Tiamaat (Druid)

Levels gained: 1 (8 → 9) · Quests completed: 10 · Enemies slain: 63 · Places visited: 9 · People: 2
```

Then a chapter in your chosen voice, a short recap for socials, and an HTML story page, all built by themselves
after you log out. In game, `/ramble chapters` shows the chapter with selectable text.

## Install (macOS)

You need [Homebrew](https://brew.sh) and WoW installed. Then:

```bash
brew install uv
uv tool install "git+https://github.com/realworldbuilder/rambleon@v0.4.0#subdirectory=companion"
ramble setup
```

`ramble setup` finds your WoW folder, links the AddOn into it, starts a background watcher that survives reboots,
and opens your (empty) journal. Start WoW, or log out to the character screen and back in so it sees the AddOn.
That is the whole setup. The line above installs release 0.4.0; leave out `@v0.4.0` for the newest code on `main`,
and run the same line again (with `--force`) to upgrade, then `ramble service install` to restart the watcher.

For AI-written chapters, install [Claude Code](https://claude.com/claude-code) and log in once (`claude`, then
`/login`). Without it you still get the timeline, the story page, and a prompt file you can paste into any assistant.

To remove it: `ramble uninstall` (your archive stays unless you ask for it to go).

## Playing with it

- `/ramble` opens the panel: time, place, level, quests, places, kills, loot, deaths, people, and the recent journey.
  The first time, it says what Rambleon is; after that it stays out of the way.
- `/ramble note the cave is extremely cursed` — your own words are the best evidence the writer gets.
- `/ramble mark` — remember this moment and take a picture (there is a keybinding for it under AddOns).
- Level ups and the first step into a new zone are photographed too; `/ramble shots off` (or the Pictures row on the
  panel) if you would rather not.
- `/ramble chapters` — read past chapters in game; click the text, Ctrl-A, Ctrl-C.
- Log out when you are done. That is the save. A few seconds later the chapter is written on your Mac.

On the Mac: `ramble nights` lists chapters, `ramble page tonight` opens the story page, `ramble summarize tonight
--voice field-journal` rewrites a chapter in another voice, `ramble guide --open` shows the route guide (how you actually leveled, stretch by stretch; `--mode season` retells it
for you instead of for a stranger), `ramble share tonight` puts a chapter (pictures included) on
your GitHub Pages site after asking (it needs your own fork of this repository, checked out, with Pages on),
`ramble finish tonight` writes a night's chapter and pages again from scratch (or for a night the watcher missed),
`ramble doctor --fix` repairs a broken link or a stopped watcher. `ramble --help` has the rest.

### Your files and settings

Everything of yours is in one folder: `~/Rambleon/` (when you run from a git checkout, the checkout).

| | |
|---|---|
| `archive/` | your history: every session as plain JSON, and the raw files WoW wrote, byte for byte |
| `exports/` | everything made from it (logs, chapters, pages); can always be rebuilt |
| `rambleon.local.toml` | your settings; optional, every key has a default. `ramble config` shows what is in effect and warns about a key it does not know |
| `prompts/` | your own voices, guide modes, chapter rules and page theme ([docs/extending.md](docs/extending.md)) |

```toml
# ~/Rambleon/rambleon.local.toml — all optional
[journal]
voice = "field-journal"     # the voice the watcher writes in (`ramble voices`), or a path to your own .md
model = "sonnet"            # the Claude model

[guide]
mode = "route"              # or "season", or a mode of your own

[characters."rambleon-birdsong"]
gender = "male"             # a fact about a character the game did not record

[people."Cassidy"]
note = "my friend from work"   # your own words about a companion; the writer gets them as evidence
```

A voice of your own is a text file: put `saga.md` in `~/Rambleon/prompts/voices/` and write with `--voice saga`.

Want every chapter on your site the moment it is written, no questions asked? Put this in `rambleon.local.toml`
(it only affects that Mac) and restart the watcher with `ramble service install`:

```toml
[share]
auto = true
```

Want the story told on X as well? `ramble x login` stores the four keys of your own X developer app in the macOS
Keychain (console.x.com: create an app, set it to Read and write, generate the keys, add a few dollars of credits; X
bills about 1.5 cents a post). `ramble post tonight` then shows the post and asks before sending it: the chapter's
title, the night in one or two sentences from the writer, and the night's hero picture. `--style thread` tells the
whole chapter instead, `--dry-run` posts nothing. To have the watcher post by itself once a night has gone quiet:

```toml
[x]
auto = true
# style = "thread"      # the whole chapter instead of one post
# link = true           # add the shared story page's address (X charges about 20 cents for a post with a link)
# lowercase = true      # all lower case, if that is how you write there
# delay = 30            # minutes of quiet after the chapter was written before it is posted
# characters = ["rambleon-birdsong"]   # only these; default is every character
```

A night is posted once. If you come back and play more after it went out, the chapter on your Mac is rewritten but
the post is not repeated.

Inviting a friend? Send them [docs/invite-prompt.md](docs/invite-prompt.md): a message they can paste into Claude Code
and it installs Rambleon for them.

## What it records, and what it never records

Recorded: where you went, quests accepted, completed and abandoned and their objectives, levels, experience, kills
that gave experience (from the chat line), uncommon-or-better loot, deaths, who you grouped with and for how long,
dungeons and the bosses you defeated in them, the inn you made home, achievements, screenshots (yours, and the ones it takes at level ups, marks and new zones), your notes and marks, playtime.

Never: damage numbers or the combat log, chat content, other players beyond your group roster as the game shows it,
anything Blizzard marks protected or secret. Nothing leaves your Mac. If you use the AI step, the only thing sent is
the prompt for that chapter, through your own Claude login. `ramble share` and `ramble post` are the only commands that publish a chapter,
and they ask first unless you turned on `auto` for them yourself.

Your history lives as plain JSON in `~/Rambleon/archive/` (or the checkout's `archive/`). Raw files WoW wrote are
kept byte for byte and never edited. Stories are always generated downstream; the record is never touched to make
a better story.

## Why the Mac side exists

WoW only writes AddOn data on logout and reload, and the Forever beta currently does not restore it on the next
launch. So the AddOn treats every login as a fresh session and the Mac watcher snapshots every write. WoW may
forget; Rambleon does not.

## Development

```bash
git clone https://github.com/realworldbuilder/rambleon && cd rambleon
scripts/bootstrap        # uv, the companion env, `ramble` on PATH (editable)
scripts/test             # luac -p, a simulated session under a WoW API stub, pytest
```

[CONTRIBUTING.md](CONTRIBUTING.md) has the rules in short. [docs/extending.md](docs/extending.md) shows the three
things Rambleon is built to have added: a new thing to remember (one entry in the AddOn's `EventTypes.lua` and one in
the companion's `events.py`), a new output (one step in `pipeline.py`), and a new voice, guide mode or page theme
(a file, no code). `docs/` also has the Forever API findings, the data model, a running progress log and the roadmap.

## Roadmap, briefly

One-command setup and a base to build on (done), then chapter quality (a rating loop, more voices, a share card),
then memory over time (character timeline, people you have played with, weekly recaps, an adventure map), then a
small menu-bar app.
See `docs/roadmap.md`.

Ramble on.
