# Visual floorplan

`scripts/floorplan.py` turns a codebase topic into one self-contained HTML map: parts and the arrows between them, a view inside each part with its files, playable flows, a quiz mode that hides names, and the learner's cards pinned to the code they cover. Dark, minimal styling; no dependencies, and it works offline (the Inter font loads from Google Fonts when online, with a system fallback).

```
F="python3 -I ~/.claude/skills/sensei/scripts/floorplan.py"
$F init  <topic>          # starter floorplan.json from the folder layout (needs profile --root)
$F build <topic> [--open] # validate, write floorplan.html next to cards.json
$F show  <topic> [ref]    # the same connections as text: whole map, a part id, or a file
```

Use `show` yourself to read the map: it prints every part with what it uses and how (import counts or hand-written labels), and for a part or file the exact import pairs behind each arrow. Check the spec against it before you open the page for the learner, and use it rather than a screenshot when you need to know what connects to what.

Division of labour: the script finds files, imports (Python, JS/TS, Go, Rust, C/C++), HTTP endpoints, git hotspots and lays everything out. You write `floorplan.json`: what the parts *are*, how they are described, and which flows matter. `init` only mirrors folders; always regroup it into whiteboard parts (see "The map file" in `codebase.md` for how to carve).

## floorplan.json

```json
{
  "project": {"name": "Vellum", "summary": "What it does, for whom."},
  "parts": [
    {"id": "store", "label": "Encrypted vault", "kind": "data",
     "summary": "One sentence of responsibility.", "details": "Optional; blank lines split paragraphs.",
     "paths": ["src/VaultStore.*"]},
    {"id": "sodium", "label": "libsodium", "kind": "external", "summary": "..."}
  ],
  "edges": [{"from": "store", "to": "sodium", "label": "derive key, encrypt"}],
  "notes": {"src/VaultStore.cpp": "One line on what this file does."},
  "tour":  [{"node": "store", "title": "Where secrets live", "note": "..."}],
  "flows": [{"id": "unlock", "title": "Unlocking the vault", "description": "optional",
             "steps": [{"node": "src/VaultWindow.cpp", "note": "unlock() (VaultWindow.cpp:555) ..."},
                       {"node": "store", "note": "..."}]}],
  "ignore": ["src/generated/**"]
}
```

- **kind**: `ui service worker library feature data config test script infra external`. Externals own no files; connect them with `edges`.
- **paths**: globs relative to the root. `**` any depth, `*` one segment, `{a,b}` alternation; a bare path is a directory. A file goes to the part whose matching glob has the longest literal prefix, so broad globs and narrow ones can coexist.
- **edges**: only what imports can't show (calls into externals, queues, files on disk, OS events). `from`/`to` are part ids or file paths. An edge on a part is drawn from its largest file inside the part view; use a file path when that is wrong.
- **notes**: optional one-liners for the files that matter; they replace the path on the card and are hidden in quiz mode.
- **flows / tour**: steps are part ids or file paths; put `file:line` in the note. The tour plays as "Start here". 1-3 flows, 3-7 steps, consecutive steps really connected.

`build` names every problem ("did you mean …"), exits 1 on broken refs, and reports assigned %, unassigned files by directory, and how many cards it placed. Aim for 100% assigned (or `ignore`d) and no warnings.

## Cards on the map

Each card lands on the file its `ref` points at, or on the part named by its `tag`. Cards show the question and whether it's due, never the answer. Rebuild after adding cards or a review session so the due badges stay current.

## Using it in a session

- **Blank floorplan first**: ask the learner to sketch the parts before they open the map. Then open it in quiz mode (`q`), have them name each part out loud and click twice to reveal.
- **Flows in quiz mode** hide each step's note: the learner says what happens at this stop and where it goes next, then presses Show.
- **Reading arrows**: hovering or selecting a card lights up what it uses in blue and what uses it in violet, animated in the direction of the dependency; everything else fades. Clicking an arrow lists the imports behind it. Long arrows run through gaps between columns, never behind cards.
- **Deep links** to point at something: `floorplan.html#part=<id>`, `#sel=<file or part>`, `#hover=<ref>`, `#edge=<from>><to>`, `#flow=<n>&step=<n>`, `#quiz=1`.
- Keys: `/` search, `q` quiz, `f` fit, arrow keys step a flow, Esc or Backspace back out.
- The map is a snapshot. After code changes, run `srs.py check-refs`, then rebuild.
