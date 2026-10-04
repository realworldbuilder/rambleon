# Invite a friend

Send them everything below the line. They paste it into Claude Code (or any Claude that can run commands on their
Mac) and it walks them through the install. Rambleon is free and open; their journal stays on their Mac unless
they choose to share a page.

---

I want to set up **Rambleon** on this Mac. It is a free, open-source "personal memory layer" for World of Warcraft:
a small AddOn quietly records my adventure while I play (places, levels, quests, deaths, people I grouped with, my
own notes, screenshots at big moments), and a Mac companion turns each evening into a chapter I can read in game and
as a web page. Repo and README: https://github.com/realworldbuilder/rambleon. Please read the README first, then do
the following, telling me what each step does before you run it, and stopping to ask me if anything needs a decision.

1. Check the ground: this must be macOS with World of Warcraft installed (Rambleon was built on WoW: Forever, the
   Classic-beta client, and expects the mainline-style 12.x AddOn API). Tell me which WoW folders you find.
2. Install the companion:
   - `brew install uv` if `uv` is missing (install Homebrew first if that is missing too, and tell me).
   - `uv tool install "git+https://github.com/realworldbuilder/rambleon@v0.4.0#subdirectory=companion"`
   - `ramble setup` — it finds my WoW folder, links the AddOn into `Interface/AddOns`, installs a background
     watcher that survives reboots, and opens my empty journal. If it cannot find WoW, ask me for the path and set
     `RAMBLEON_WOW_DIR`. Run `ramble doctor` afterwards and show me the result.
3. AI-written chapters are optional. If I have Claude Code installed and logged in (`claude`, then `/login`), the
   companion uses it to write the chapter at the end of the night. If not, tell me I still get the timeline, the
   factual log, the story page and a prompt file I can paste anywhere, and offer `ramble setup --no-ai`.
4. Explain the in-game side in a few lines: start WoW (or relog so it sees the AddOn), `/ramble` opens the panel,
   `/ramble note <text>` adds my own words (the best thing I can give the writer), `/ramble mark` remembers a moment
   and takes a picture, `/ramble chapters` shows past chapters, and logging out is the save. There is no end button.
5. Tell me what Rambleon never does: no DPS meter, no automation, no combat log, nothing leaves my Mac except, when AI
   is on, the prompt for the chapter.
6. Sharing is manual: `ramble share tonight` puts a chapter on a GitHub Pages site, but only from a git checkout of
   my own fork with Pages enabled. Leave that for later unless I ask.

When you are done, give me a short checklist of what is installed and where, and what to do after my first night
(`ramble nights`, `ramble page tonight`).
