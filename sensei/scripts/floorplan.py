#!/usr/bin/env python3
"""A visual floorplan of a codebase for a sensei topic: one self-contained HTML page.

  floorplan.py init  <topic> [--root DIR]   write a starter floorplan.json from the directory layout
  floorplan.py build <topic> [--open]       validate floorplan.json, write floorplan.html
  floorplan.py show  <topic> [part|file]    the same connections as text (for the coach)

Both files live in $LEARN_HOME/<topic>/ next to cards.json; the codebase root comes from
`srs.py profile <topic> --root DIR`. The scripts do the mechanical work (files, imports, routes,
hotspots, layout data); the coach writes floorplan.json (parts, flows, tour), which is the part
only a reader of the code can do. Format: reference/floorplan.md.
"""
import argparse
import collections
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # -I drops the script dir from sys.path
import codemap  # noqa: E402

HOME = Path(os.environ.get("LEARN_HOME", Path.home() / ".claude" / "learning"))
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
TEMPLATE = Path(__file__).resolve().parent.parent / "assets" / "floorplan.html"
KINDS = {"ui", "service", "worker", "library", "feature", "data", "config", "test", "script", "infra",
         "external"}
CODE = {lang for lang in codemap.LANG.values()} - {"Markdown", "HTML", "CSS"}


def die(msg):
    sys.exit(f"floorplan: {msg}")


def read_json(p, default=None):
    try:
        return json.loads(p.read_text())
    except FileNotFoundError:
        return default
    except json.JSONDecodeError as e:
        die(f"{p}: {e}")


def topic_dir(topic):
    if not SLUG.match(topic):
        die(f"bad topic slug {topic!r}: use lowercase kebab-case")
    return HOME / topic


def glob_re(pattern):
    """`**` any depth, `*` one segment, `?` one char, `{a,b}` alternation; a bare path matches as a dir."""
    out, i = "", 0
    while i < len(pattern):
        c = pattern[i]
        if pattern.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
            continue
        if pattern.startswith("**", i):
            out, i = out + ".*", i + 2
            continue
        if c == "{":
            j = pattern.find("}", i)
            if j > i:
                out, i = out + "(?:" + "|".join(map(re.escape, pattern[i + 1:j].split(","))) + ")", j + 1
                continue
        out += "[^/]*" if c == "*" else "[^/]" if c == "?" else re.escape(c)
        i += 1
    if not re.search(r"[*?{]", pattern):
        out += "(?:/.*)?"
    return re.compile(out + "$")


def literal_prefix(pattern):
    return len(re.split(r"[*?{]", pattern, maxsplit=1)[0])


def scan(root):
    """Files, LOC, file-level import edges, routes and hotspots. Tests are included so a Tests
    part can show what it exercises."""
    src = {}
    for p in codemap.walk(root):
        if codemap.LANG.get(p.suffix) in CODE:
            text = codemap.read(p)
            if text is not None:
                src[p.relative_to(root)] = text
    imports = codemap.Imports(root, list(src))
    by_dir = collections.defaultdict(list)
    for f in src:
        by_dir[f.parent].append(f)
    edges = set()
    for rel, text in src.items():
        for t in imports.of(rel, text):
            for target in ([t] if t.suffix else by_dir.get(t, [])):  # Go: a package is its files
                if target != rel:
                    edges.add((str(rel), str(target)))
    heat = collections.Counter()
    if codemap.git(root, "rev-parse", "--is-inside-work-tree").strip() == "true":
        log = codemap.git(root, "log", "--since=1 year ago", "--name-only", "--pretty=format:")
        heat.update(l for l in log.splitlines() if l)
    files = {str(rel): {"loc": text.count("\n"), "routes": codemap.routes_in(rel, text),
                        "heat": heat.get(str(rel), 0), "test": codemap.is_test(rel)}
             for rel, text in src.items()}
    return files, sorted(edges)


def cmd_init(a):
    d = topic_dir(a.topic)
    spec_path = d / "floorplan.json"
    if spec_path.exists():
        die(f"{spec_path} exists; edit it, or delete it to start over")
    root = Path(a.root or (read_json(d / "profile.json", {}) or {}).get("root") or ".").expanduser().resolve()
    files, _ = scan(root)
    code = [Path(f) for f, v in files.items() if not v["test"]]
    depth = codemap.area_depth(code) if code else 1
    areas = collections.Counter()
    for f in code:
        areas[codemap.area(f, depth)] += files[str(f)]["loc"]
    parts = []
    for name, _ in areas.most_common(8):
        pid = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "root"
        paths = [f"{name}/*"] if name == "." or len(Path(name).parts) < depth else [name]
        parts.append({"id": pid, "label": Path(name).name or root.name, "kind": "library",
                      "summary": "TODO: one sentence of responsibility", "paths": paths})
    if any(v["test"] for v in files.values()):
        parts.append({"id": "tests", "label": "Tests", "kind": "test", "summary": "TODO",
                      "paths": ["**/test/**", "**/tests/**", "**/*test*", "**/*spec*"]})
    spec = {"project": {"name": root.name, "summary": "TODO: what it does, for whom"},
            "parts": parts, "edges": [], "flows": [], "tour": [], "ignore": []}
    d.mkdir(parents=True, exist_ok=True)
    spec_path.write_text(json.dumps(spec, indent=2) + "\n")
    print(f"wrote {spec_path} ({len(parts)} parts from the directory layout).\n"
          "It mirrors folders: rename and regroup into whiteboard parts, write summaries, add flows.")


def assign(files, parts, ignore):
    """Each file goes to the matching part with the longest literal glob prefix (later
    duplicates of that length are reported as ties). Returns {file: part id}, ties, ignored."""
    compiled = [(p["id"], glob_re(g), literal_prefix(g)) for p in parts for g in p.get("paths", [])]
    ign = [glob_re(g) for g in ignore]
    owner, ties, ignored = {}, collections.Counter(), set()
    for f in files:
        if any(r.match(f) for r in ign):
            ignored.add(f)
            continue
        best = None
        for pid, rx, n in compiled:
            if rx.match(f):
                if best is None or n > best[1]:
                    best = (pid, n)
                elif n == best[1] and pid != best[0]:
                    ties[f"{best[0]} / {pid}"] += 1
        if best:
            owner[f] = best[0]
    return owner, ties, ignored


def compute(topic):
    """Spec + scan + cards -> (data the viewer embeds, problems, warnings, totals)."""
    d = topic_dir(topic)
    spec = read_json(d / "floorplan.json")
    if spec is None:
        die(f"no {d / 'floorplan.json'}; run: floorplan.py init {topic}")
    profile = read_json(d / "profile.json", {}) or {}
    if not profile.get("root"):
        die(f"no root set; run: srs.py profile {topic} --root <dir>")
    root = Path(profile["root"]).expanduser().resolve()
    problems, warnings = [], []

    parts = spec.get("parts", [])
    ids = [p.get("id") for p in parts]
    for dup in {i for i in ids if ids.count(i) > 1}:
        problems.append(f"duplicate part id {dup!r}")
    for p in parts:
        if not p.get("id") or not p.get("label"):
            problems.append(f"part needs id and label: {json.dumps(p)[:80]}")
        if p.get("kind", "library") not in KINDS:
            problems.append(f"part {p.get('id')}: kind {p['kind']!r} not in {sorted(KINDS)}")
        if p.get("kind") != "external" and not p.get("paths"):
            warnings.append(f"part {p.get('id')}: no paths, so it owns no files")
        if not p.get("summary") or p["summary"].startswith("TODO"):
            warnings.append(f"part {p.get('id')}: needs a summary")

    files, file_edges = scan(root)
    owner, ties, ignored = assign(files, parts, spec.get("ignore", []))
    for t, n in ties.items():
        warnings.append(f"{n} file(s) matched equally by parts {t}; first one wins")
    unassigned = sorted(f for f in files if f not in owner and f not in ignored)
    known = set(ids) | set(owner)

    def ref_ok(ref, where):
        if ref in known:
            return True
        problems.append(f"{where}: {ref!r} is not a part id or mapped file" +
                        hint(ref, known))
        return False

    explicit = []
    for e in spec.get("edges", []):
        if ref_ok(e.get("from", ""), "edge") & ref_ok(e.get("to", ""), "edge"):
            explicit.append(e)
    flows = []
    tour = spec.get("tour") or []
    if tour:
        flows.append({"id": "tour", "title": "Start here", "tour": True,
                      "steps": [s for s in tour if ref_ok(s.get("node", ""), "tour")]})
    for f in spec.get("flows", []):
        steps = [s for s in f.get("steps", []) if ref_ok(s.get("node", ""), f"flow {f.get('id')}")]
        if len(steps) < 2:
            problems.append(f"flow {f.get('id')}: needs at least 2 valid steps")
        flows.append({**f, "steps": steps})

    notes = {}
    for f, note in (spec.get("notes") or {}).items():
        if f in owner:
            notes[f] = note
        else:
            problems.append(f"notes: {f!r} is not a mapped file" + hint(f, set(owner)))

    cards = read_json(d / "cards.json", []) or []
    today = dt.date.today().isoformat()
    card_view = collections.defaultdict(list)
    for c in cards:
        if c.get("suspended"):
            continue
        path = (c.get("ref") or "").rsplit(":", 1)[0] if re.search(r":\d", c.get("ref", "")) else c.get("ref", "")
        target = path if path in owner else c.get("tag") if c.get("tag") in ids else None
        if target:
            card_view[target].append({"id": c["id"], "q": c["q"], "due": c.get("due", today) <= today,
                                      "ref": c.get("ref", "")})

    data = {
        "project": spec.get("project", {}), "root": root.name, "built": today,
        "parts": [{**{k: p.get(k) for k in ("id", "label", "kind", "summary", "details")},
                   "kind": p.get("kind", "library")} for p in parts],
        "files": {f: {**files[f], "part": owner[f]} for f in owner},
        "edges": [[s, t] for s, t in file_edges if s in owner and t in owner],
        "explicit": explicit, "flows": flows, "notes": notes, "cards": card_view, "unassigned": unassigned[:200],
    }
    return data, problems, warnings, {"total": len(files) - len(ignored), "ignored": len(ignored),
                                      "unassigned": unassigned, "title": spec.get("project", {}).get("name") or root.name}


def cmd_build(a):
    d = topic_dir(a.topic)
    data, problems, warnings, t = compute(a.topic)
    owner, card_view, unassigned, ignored = data["files"], data["cards"], t["unassigned"], t["ignored"]
    if problems:
        print("PROBLEMS (fix floorplan.json and rebuild)\n" + "\n".join(f"  {p}" for p in problems))
    blob = json.dumps(data, separators=(",", ":")).replace("<", "\\u003c")
    html = TEMPLATE.read_text().replace("__FLOORPLAN_DATA__", blob).replace(
        "__TITLE__", t["title"].replace("<", "&lt;"))
    out = d / "floorplan.html"
    out.write_text(html)

    total = t["total"]
    pct = 100 * len(owner) / total if total else 100
    print(f"wrote {out}")
    print(f"FILES  {len(owner)}/{total} assigned ({pct:.0f}%), {ignored} ignored, "
          f"{len(data['edges'])} import edges, {sum(len(v) for v in card_view.values())} cards placed")
    if unassigned:
        by_dir = collections.Counter(str(Path(f).parent) for f in unassigned)
        print("UNASSIGNED by directory: " + ", ".join(f"{k} ({n})" for k, n in by_dir.most_common(8)))
    for w in warnings:
        print(f"  warn: {w}")
    if a.open:
        subprocess.Popen(["xdg-open", str(out)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    sys.exit(1 if problems else 0)


def connections(data):
    """Part-to-part connections exactly as the map draws them: (from, to) -> {imports, labels, pairs}."""
    out = collections.defaultdict(lambda: {"imports": 0, "labels": [], "pairs": []})
    files = data["files"]
    owner = lambda ref: ref if ref in {p["id"] for p in data["parts"]} else files[ref]["part"]
    for s, t in data["edges"]:
        a, b = files[s]["part"], files[t]["part"]
        if a != b:
            c = out[a, b]
            c["imports"] += 1
            c["pairs"].append(f"{s} -> {t}")
    for e in data["explicit"]:
        a, b = owner(e["from"]), owner(e["to"])
        if a != b:
            out[a, b]["labels"].append(e.get("label") or e.get("kind") or "linked")
    return out


def cmd_show(a):
    """The map as text, so a coach can read the connections without looking at the page."""
    data, problems, _, _ = compute(a.topic)
    parts = {p["id"]: p for p in data["parts"]}
    conns = connections(data)
    files = data["files"]
    def how(c):
        bits = ([f"{c['imports']} import{'s' if c['imports'] > 1 else ''}"] if c["imports"] else []) + c["labels"]
        return ", ".join(bits)
    ref = a.ref
    if ref is None:
        print(f"# {data['project'].get('name', data['root'])}: {data['project'].get('summary', '')}\n")
        for pid, p in parts.items():
            fs = [f for f, v in files.items() if v["part"] == pid]
            print(f"[{pid}] {p['label']} ({p['kind']}, {len(fs)} files): {p.get('summary') or ''}")
            for (x, y), c in sorted(conns.items(), key=lambda kv: -kv[1]["imports"]):
                if x == pid:
                    print(f"    -> {parts[y]['label']} [{y}]: {how(c)}")
        for f in data["flows"]:
            print(f"\nflow {f['title']}: " + " -> ".join(s["node"] for s in f["steps"]))
    elif ref in parts:
        p = parts[ref]
        print(f"[{ref}] {p['label']} ({p['kind']}): {p.get('summary') or ''}")
        for title, side in (("uses", 0), ("used by", 1)):
            rows = [(k, c) for k, c in conns.items() if k[side] == ref]
            print(f"\n{title}:" + ("" if rows else " nothing"))
            for k, c in sorted(rows, key=lambda kv: -kv[1]["imports"]):
                other = k[1 - side]
                print(f"  {parts[other]['label']} [{other}]: {how(c)}")
                for pair in c["pairs"][:a.limit]:
                    print(f"      {pair}")
        print("\nfiles:")
        inside = sorted((f for f, v in files.items() if v["part"] == ref), key=lambda f: -files[f]["loc"])
        for f in inside:
            n_in = sum(1 for _, t in data["edges"] if t == f)
            print(f"  {f}  ({files[f]['loc']} lines, used by {n_in})")
    elif ref in files:
        v = files[ref]
        print(f"{ref} in [{v['part']}] {parts[v['part']]['label']}, {v['loc']} lines")
        if data["notes"].get(ref):
            print(f"  {data['notes'][ref]}")
        for m, path, line in v["routes"]:
            print(f"  endpoint {m} {path} :{line}")
        for title, mine, other in (("uses", 0, 1), ("used by", 1, 0)):
            rows = [e[other] for e in data["edges"] if e[mine] == ref]
            print(f"{title}:" + ("" if rows else " nothing"))
            for r in rows:
                print(f"  {r}  [{files[r]['part']}]")
    else:
        die(f"{ref!r} is not a part id or mapped file" + hint(ref, set(parts) | set(files)))
    for p in problems:
        print(f"problem: {p}", file=sys.stderr)


def hint(ref, known):
    import difflib
    close = difflib.get_close_matches(ref, list(known), n=1)
    return f" (did you mean {close[0]!r}?)" if close else ""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init")
    s.add_argument("topic")
    s.add_argument("--root")
    s = sub.add_parser("build")
    s.add_argument("topic")
    s.add_argument("--open", action="store_true")
    s = sub.add_parser("show")
    s.add_argument("topic")
    s.add_argument("ref", nargs="?", help="a part id or file path; omit for the whole map")
    s.add_argument("--limit", type=int, default=3, help="example import pairs per connection")
    a = ap.parse_args()
    {"init": cmd_init, "build": cmd_build, "show": cmd_show}[a.cmd](a)


if __name__ == "__main__":
    main()
