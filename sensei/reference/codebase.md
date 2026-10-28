# Learning a codebase

Naur: the real knowledge in a program is the *theory* in people's heads (purpose, why it is shaped this way, how it should change), and the source text is a lossy record of it. Goal is to rebuild that theory, not memorize files.

1. **Recon**: `python3 -I ~/.claude/skills/sensei/scripts/codemap.py <path>`. Reports languages, docs, manifests, entry points, HTTP endpoints, the internal import graph (most depended-on files, heaviest directory-to-directory imports, two-way dependencies), tests, largest files, git hotspots, contributors; honours `.gitignore` in a git repo. These are facts; interpretation comes next. The import graph is regex matching, not a compiler: strong hints, with missing edges for aliases, plugins and anything wired at runtime.
2. **Orient**: read the docs it flagged. State in one sentence what the system is for and who uses it. Make the learner state it too.
3. **Blank floorplan** (before you show any structure): the learner sketches the parts they expect and the arrows between them, from the recon and the docs alone. Keep it; step 5 is diffed against it, and the gaps are the first cards.
4. **Run it** and watch behavior before deep reading. Build, run tests, use the thing.
5. **Map it** into `$S map <topic>`, in the format below. This replaces the generic concept map for codebases. Then draw it: the same parts, flows and tour go into `floorplan.json` and `floorplan.py build <topic> --open` renders the visual map (read `reference/floorplan.md`). Open it in quiz mode after the blank-floorplan sketch, not before.
6. **Trace one real flow end to end**, starting from something the learner already knows from the outside: a screen, a command, an endpoint from the recon. Smallest flow touching the main layers, `file:line` per step. The learner predicts the next hop before you reveal it.
7. **Ask why**: what constraints produced this shape? what alternatives were plausible? Evidence: git history, ADRs, comments, tests. Label guesses as guesses. Two-way dependencies and god-files are good places to ask.
8. **Predict, then verify**: before opening a file, the learner predicts what is in it or how a change would propagate ("if I change this table, what breaks?"). Check by reading, by the import graph, or by running.
9. **Make a small change**: a trivial fix, a log line, a test. Failing tests are the feedback loop.
10. **Teach-back**: learner redraws the map from memory and names each part in one sentence; diff against the map file.
11. **Bank it** with `ref` set to the `file:line` (and `profile --root <repo>` once). Cards such as "where does X state live and who mutates it?", "what happens between request and response?", "why is Y a separate module?", "which part would you change to do Z?"

## The map file

The map is useful when each part is something a person would name at a whiteboard. It is useless when it mirrors the folder tree.

```
# <system>: <one sentence: what it does, for whom>

## Parts (3-9; learn-first order)
- <Name>: <one sentence of responsibility, in the codebase's vocabulary>. <main paths>. Central: <file:line>
## Connections
- <A> -> <B>: <how: import, HTTP, queue, DB, shared file>   (from the import graph, plus what it can't see)
## Flows (1-3, 3-7 steps each, every hop really connected)
- <Flow name>: <trigger> -> <part/file:line> -> ... -> <final side effect>
## Surprises
- <two-way dependencies, god-files, dead areas, a frontend importing backend code>
## Misconceptions to expect
```

- **Carving parts.** Several deployables (frontend, API, worker, admin app): one part each, plus shared libraries and externals. Monorepo: apps and services become parts; group packages as one shared-libraries part unless one is big and central. Monolith: use the layers or domains the code actually follows, not the ones you'd prefer. Prefer responsibility ("Orders", "Auth") over file type ("routes", "models"), unless the code really is layered, in which case show the layers.
- **Externals are parts**: the database and each third-party service the code really talks to. Utility libraries are not.
- **Tests, scripts, migrations** get their own part, or they bury the real dependency structure (tests import everything).
- **Plain-words test.** Each part's sentence says what it does ("takes card payments at checkout"), not what it is built with ("Stripe wrapper"). When the learner can only name a part by its technology or folder, that part is a gap.
- **Sanity check**: read top to bottom, do the parts tell the system's story (UI -> API -> services -> data/externals)? A part connected to almost everything is either a shared kit (say so) or a wrong boundary.
- **Tour order** is the learn-first order: what the system is, what people use, the main server or core, outside services, then one important flow.

## If the repo has a floorplan

[Floorplan](https://github.com/haydenschmitty/floorplan) is a Claude Code plugin that builds an interactive map of a codebase (`floorplan/` at the repo root). codemap reports it when `floorplan/graph.json` exists. Use it as an accelerator, never as a substitute for the learner's own retrieval:

- **Lookups** before grepping: `node floorplan/query.mjs overview`, `find "<words>"`, `show <file | module id | "GET /path">`, `path <from> <to>` (how two things connect). The map can lag recent edits, so verify in code before citing.
- **Curriculum**: its parts, flows and "Start here" tour are a ready-made map and learn order. Copy what holds up into the map file. Quiz first: the learner names the parts and predicts each flow's next hop *before* opening the map. The map is the answer key, not the lesson.
- **Health items** (files nothing uses, files over ~1,000 lines, endpoints with no sign-in check, secrets in code) are ready "find the smell" and "why is this shaped like this?" exercises. Never repeat a secret's value.
- **Recent work** (`floorplan/recent-work.json`) is a returning-session opener: "these parts changed; predict which of your cards are now wrong", then run `check-refs`.
- No floorplan and the learner wants a visual they can click through: mention the plugin (`claude plugin marketplace add haydenschmitty/floorplan`, then `claude plugin install floorplan@floorplan`). Don't install it unasked; it writes a `floorplan/` folder and a block in `CLAUDE.local.md` (both kept out of git).

## Returning sessions

Code moves under the cards. `$S check-refs <topic>` re-points cards whose code only moved and ignores edits elsewhere in the file. What it prints is real drift: `changed` (with `was`, the line the card was anchored on) or `missing`. Re-verify those before asking them, then fix the card with `edit` (`--ref` to re-point; `edit` with no flags re-stamps a card that is still right). Worth doing first as an exercise: show `git log --oneline --since=<last session>` and have the learner predict which parts and cards it touched.

Pitfalls: reading top to bottom; trusting stale docs (or a stale map) over code; confusing the largest or most-imported file with the most important; mirroring the folder tree; stopping at what, never reaching why. Hotspots, fan-in and big files are leads, not verdicts.
