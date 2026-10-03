# Rambleon

**Your Azeroth adventure journal.** Play World of Warcraft normally. Rambleon quietly remembers the night. When you
log out, it hands you a permanent record: a timeline, a factual log, a story page with your screenshots, and a
journal chapter written from what actually happened, readable in game and ready to paste anywhere.

> *At Lake Al'Ameth he found the work turned strange and solitary — timberlings, one after another, seeds and
> sprouts to be gathered from creatures that should not, by any right, have walked. He wrote it down himself, plain
> as the water: "alone at the lake slayin timberlings".*
> — Chapter 1, written by Rambleon from one Tuesday night in Teldrassil

**See a real journal:** https://realworldbuilder.github.io/rambleon/example/

Rambleon is a **memory layer**, not a meter. It never automates anything, never reads protected combat data, and
never needs the network in game. Think Strava recap, travel journal, captain's log.

**Status:** early, real, and used nightly by its author on the **World of Warcraft: Forever** beta, on **macOS**.
Windows and other WoW flavours are on the roadmap. MIT licensed.

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
uv tool install "git+https://github.com/realworldbuilder/rambleon#subdirectory=companion"
ramble setup
```

`ramble setup` finds your WoW folder, links the AddOn into it, starts a background watcher that survives reboots,
and opens your (empty) journal. Start WoW, or log out to the character screen and back in so it sees the AddOn.
That is the whole setup.

For AI-written chapters, install [Claude Code](https://claude.com/claude-code) and log in once (`claude`, then
`/login`). Without it you still get the timeline, the story page, and a prompt file you can paste into any assistant.

To remove it: `ramble uninstall` (your archive stays unless you ask for it to go).

## Playing with it

- `/ramble` opens the panel: time, place, level, quests, places, kills, loot, deaths, people, and the recent journey.
- `/ramble note the cave is extremely cursed` — your own words are the best evidence the writer gets.
- `/ramble mark` — remember this moment and take a picture (there is a keybinding for it under AddOns).
- Level ups and the first step into a new zone are photographed too; `/ramble shots off` if you would rather not.
- `/ramble chapters` — read past chapters in game; click the text, Ctrl-A, Ctrl-C.
- Log out when you are done. That is the save. A few seconds later the chapter is written on your Mac.

On the Mac: `ramble nights` lists chapters, `ramble page tonight` opens the story page, `ramble summarize tonight
--voice field-journal` rewrites a chapter in another voice, `ramble guide --open` shows the route guide (how you actually leveled, stretch by stretch; `--mode season` retells it
for you instead of for a stranger), `ramble share tonight` puts a chapter (pictures included) on
your GitHub Pages site after asking, `ramble doctor --fix` repairs a broken link or a stopped watcher. `ramble --help`
has the rest.

Want every chapter on your site the moment it is written, no questions asked? Put this in `rambleon.local.toml`
next to your checkout (the file is gitignored, so it only affects that Mac) and restart the watcher with
`ramble service install`:

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

Recorded: where you went, quests accepted and completed and their objectives, levels, experience, kills that gave
experience (from the chat line), uncommon-or-better loot, deaths, who you grouped with and for how long, dungeons,
achievements, screenshots (yours, and the ones it takes at level ups, marks and new zones), your notes and marks, playtime.

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

`CLAUDE.md` explains the philosophy and the rules; `docs/` has the environment notes, the Forever API findings,
the data model, a running progress log, and the roadmap.

## Roadmap, briefly

One-command setup (done), then chapter quality (rating loop, voices, a share card), then memory over time
(character timeline, people you have played with, weekly recaps, an adventure map), then a small menu-bar app.
See `docs/roadmap.md`.

Ramble on.
