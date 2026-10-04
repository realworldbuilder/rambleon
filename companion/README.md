# rambleon (Mac companion)

The `ramble` command: it watches World of Warcraft's SavedVariables for the Rambleon AddOn, keeps every session in
a plain-JSON archive, and turns each night into a factual log, an AI-written chapter (optional), a story page and
a route guide, then publishes the chapters back into the game.

```bash
uv tool install "git+https://github.com/realworldbuilder/rambleon@v0.4.0#subdirectory=companion"
ramble setup        # link the AddOn (bundled in this package), start the background watcher, open the journal
ramble doctor       # is everything where Rambleon expects it?
ramble --help       # everything else
```

macOS, Python 3.11+. Your files live in `~/Rambleon/` (archive, exports, `rambleon.local.toml`, `prompts/`).
The repository README has the full picture: https://github.com/realworldbuilder/rambleon
