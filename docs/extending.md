# Extending Rambleon

Three things are built to be added to: what is remembered, what is made from a night, and how it is written.
Each is one entry in one list. Before any of them, ask the question in `CLAUDE.md`:
**will this help the player remember their adventure?** Memories, not telemetry.

`scripts/test` must pass afterwards. It runs a scripted evening through the AddOn under a WoW API stub, writes that
evening as the companion's test fixture, and runs the companion's tests against it.

## 1. A new thing to remember (an event type)

An event type lives in two tables that must agree: `addon/Rambleon/EventTypes.lua` and
`companion/src/rambleon/events.py`. The tests fail if one has a type the other lacks, if their counters differ, or if
the scripted evening never records it.

Worked example: remembering that the player took a flight (`FLIGHT_TAKEN`).

**AddOn**

1. `EventTypes.lua`: one entry. `describe` is how it reads in the in-game log; `counter` (optional) is the key in
   `session.counters` that goes up by one.

   ```lua
   FLIGHT_TAKEN = { describe = function(ev) return "Flew to " .. tostring(ev.name or "somewhere") end },
   ```

2. `Events.lua`: a handler for the game event that tells you. Registration is automatic and guarded (an event this
   client does not know is skipped and listed under `/ramble debug`).

   ```lua
   handlers.SOME_GAME_EVENT = function(destination)
     if not ns.EnsureSession() then return end
     ns.AddEvent("FLIGHT_TAKEN", { name = ns.CleanString(destination) })
   end
   ```

   Rules that are not optional: values go through `ns.Clean` / `ns.CleanString` (nothing secret, nothing that is not
   a string, number or boolean); call client functions through `ns.SafeCall`; no combat log, no protected APIs.
   `ns.AddEvent` adds the time, level and place by itself.

3. `addon/tests/wowstub.lua` if the handler calls a client function the stub lacks, and `addon/tests/run.lua`: fire
   the event in the scripted evening (before the fixture is written, without adding clock time) and assert the result.

**Companion**

4. `events.py`: the twin entry.

   ```python
   "FLIGHT_TAKEN": EventType(lambda ev: f"Flew to {ev.get('name') or 'somewhere'}", guide="passive"),
   ```

   | field | meaning | default |
   |---|---|---|
   | `describe` | the line in the Markdown log, the story page timeline and the writer's prompt | required |
   | `guide` | route guide: `skip`, `anchor` (a visit with one is a stretch of its own), `passive` (being somewhere), `active` | `active` |
   | `stitch` | joining sessions into a night: `keep`, `drop`, `first`, `last` | `keep` |
   | `timeline` | listed at all | `True` |
   | `shot_fallback` | a screenshot with no event of its own may be captioned by this moment | `True` |
   | `counter` | the counter the AddOn bumps; must also be in `model.COUNTER_KEYS` | none |

That is a complete type: it is archived, shown in the log, on the page and in the prompt. Anything more specific
(a line in the route guide's facts, a section in the prompt) is ordinary code in `guide.py` or `summarize.py`.

A type the companion does not know yet is never dropped: it reads as its name in plain words. So an AddOn that is
newer than the companion loses nothing.

Adding a **new file** to `addon/Rambleon/` means listing it in both TOCs, in `companion/pyproject.toml`
(`force-include`) and in `addon/tests/run.lua`; `tests/test_packaging.py` checks all four agree.

## 2. A new output (a pipeline step)

What happens after a night is `STEPS` in `companion/src/rambleon/pipeline.py`. The watcher runs all of them;
`ramble finish` does the same by hand. A step is a function of the `NightContext` that returns a line for the log:

```python
def step_recap_card(ctx: NightContext) -> str:
    out = ctx.paths.exports_dir / "social" / f"{ctx.night['id']}.txt"
    atomic_write_bytes(out, render_recap(ctx.night).encode("utf-8"))
    ctx.outputs["recap_card"] = out
    return f"recap card {out}"

STEPS = [..., Step("page", step_page), Step("recap_card", step_recap_card), Step("index", step_index), ...]
```

- A step that raises is logged and recorded as failed; the steps after it still run.
- `raise Skip("why")` when there is nothing to do.
- `ctx.unattended` is true when the watcher is running it: nobody is there to ask. Anything that leaves the Mac
  must be opted into in `rambleon.local.toml` when unattended, and asked for by hand otherwise (see `step_share`).
- `needs_ai=True` marks a step that may call the Claude CLI. It must still do its non-AI part (write the prompt)
  when `ctx.use_ai` is false.

A new HTML page is a body inside `pages.shell(...)`; the styles are `assets/page.css`.

A new setting goes in `config.py`: a field on the section's dataclass and a rule in `SECTIONS`. Unknown keys and
bad values are reported by `ramble config` and `ramble doctor` without any further code.

## 3. A new way of writing (voices, guide modes, rules, theme)

No code. Files in the player's own folder, `<home>/prompts/` (`~/Rambleon/prompts/` for a package install, the
checkout otherwise; `ramble voices` prints the path):

| file | what it is | used by |
|---|---|---|
| `voices/<name>.md` | a voice: how the chapter should sound | `--voice <name>`, `[journal] voice = "<name>"` |
| `guides/<name>.md` | a guide mode: what to write from the route's facts | `ramble guide --mode <name>`, `[guide] mode` |
| `journal.md` | the rules every chapter is written by (replaces the bundled ones) | every chapter |
| `theme.css` | CSS added after the page styles | every story page, index and guide |

A file of yours with a bundled name wins. A path to a `.md` file works wherever a name does.

Placeholders Rambleon fills in: `{voice}` and `{chapter}` in `journal.md`; `{voice}`, `{name}`, `{pronouns}`,
`{startLevel}`, `{endLevel}` and `{nights}` in a guide mode. Any other `{word}` is sent to the writer as written,
and pointed out when the prompt is built in case it was a typo.

To ship a voice or mode with Rambleon, put the file in `companion/src/rambleon/prompts/voices/` or `guides/`.
The honesty rules in `journal.md` (only what was recorded; names only from the evidence) are the product; a voice
changes the sound, never the facts.
