#!/usr/bin/env python3
"""Fast recon of an unfamiliar codebase: where to start reading.

  codemap.py [path]

Prints languages by lines, manifests, likely entry points, HTTP endpoints, the
internal import graph (most depended-on files, heaviest directory-to-directory
imports, two-way directory dependencies), largest files and, if it is a git
repo, the most-changed files (hotspots) and top contributors.
Facts only; interpreting them is the job of the learner and the coach.
"""
import collections
import os
import re
import subprocess
import sys
from pathlib import Path

SKIP = {".git", "node_modules", "target", "dist", "build", "__pycache__", ".venv", "venv", ".next", "vendor"}
LANG = {".py": "Python", ".rs": "Rust", ".go": "Go", ".js": "JavaScript", ".ts": "TypeScript",
        ".tsx": "TypeScript", ".jsx": "JavaScript", ".mjs": "JavaScript", ".cjs": "JavaScript",
        ".c": "C", ".h": "C/C++ header", ".cc": "C++", ".cpp": "C++", ".hpp": "C++", ".java": "Java",
        ".kt": "Kotlin", ".rb": "Ruby", ".cs": "C#", ".swift": "Swift", ".sh": "Shell", ".lua": "Lua",
        ".vala": "Vala", ".vue": "Vue", ".svelte": "Svelte", ".css": "CSS", ".html": "HTML",
        ".md": "Markdown", ".sql": "SQL"}
MANIFESTS = {"package.json", "Cargo.toml", "go.mod", "pyproject.toml", "setup.py", "requirements.txt",
             "pom.xml", "build.gradle", "meson.build", "CMakeLists.txt", "Makefile", "Dockerfile",
             "docker-compose.yml", "flake.nix", "justfile"}
ENTRY = {"main.py", "__main__.py", "app.py", "manage.py", "main.rs", "lib.rs", "main.go", "main.c",
         "main.cpp", "index.js", "index.ts", "main.ts", "server.js", "cli.py", "main.vala"}
JS_EXT = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".vue", ".svelte")
C_EXT = (".c", ".h", ".cc", ".cpp", ".hpp")
ROUTE_EXT = (".py", ".go", ".java", ".kt") + JS_EXT
ROUTE_HINT = re.compile(r"\.(?:route|get|post|put|patch|delete|all|GET|POST|PUT|PATCH|DELETE)\(|HandleFunc|Mapping\(")
MAX_BYTES = 1 << 20

PY_IMPORT = re.compile(r"^[ \t]*(?:from[ \t]+(\.*[\w.]*)[ \t]+import[ \t]+(\([^)]*\)|[^\n#]+)|import[ \t]+([^\n#]+))", re.M)
JS_IMPORT = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\brequire\(\s*)["']([^"']+)["']""")
GO_IMPORT = re.compile(r'^\s*(?:import\s+)?(?:[\w.]+\s+)?"([^"]+)"', re.M)
RS_MOD = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+(\w+)\s*;", re.M)
RS_USE = re.compile(r"\buse\s+crate::([\w:]+)")
C_INCLUDE = re.compile(r'^\s*#\s*include\s+"([^"]+)"', re.M)
ROUTE = re.compile(
    r"""@\w+\.(route|get|post|put|patch|delete)\(\s*["']([^"']+)"""                      # Flask, FastAPI
    r"""|\b(?:app|router|server|api|\w+Router)\.(get|post|put|patch|delete|all)\(\s*["'`](/[^"'`]*)"""
    r"""|\b(HandleFunc)\(\s*"([^"]+)"|\.(GET|POST|PUT|PATCH|DELETE)\(\s*"(/[^"]*)"""      # Go
    r"""|@(Get|Post|Put|Patch|Delete|Request)Mapping\(\s*(?:value\s*=\s*|path\s*=\s*)?"([^"]*)""")  # Spring


def walk(root):
    """Tracked files when root is a git repo (honours .gitignore), else a filtered walk."""
    tracked = git(root, "ls-files", "-z", "--cached", "--others", "--exclude-standard")
    if tracked:
        for name in filter(None, tracked.split("\0")):
            p = root / name
            if p.is_file():
                yield p
        return
    for p in root.rglob("*"):
        if any(part in SKIP for part in p.relative_to(root).parts):
            continue
        if p.is_file():
            yield p


def is_test(rel):
    name = rel.name.lower()
    return (any(part in ("test", "tests", "__tests__", "spec") for part in rel.parts[:-1])
            or name.startswith(("test_", "test.")) or ".test." in name or ".spec." in name
            or name.endswith(("_test.go", "_test.py", "_test.rs")))


def read(p):
    try:
        return None if p.stat().st_size > MAX_BYTES else p.read_text(errors="replace")
    except OSError:
        return None


def git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def names(clause):
    return [n.split(" as ")[0].strip() for n in clause.strip("() \t").split(",") if n.strip()]


class Imports:
    """Resolves import statements to files inside the repo. Pattern matching, not a compiler:
    it catches most internal edges and silently drops the rest (third-party, generated, aliased)."""

    def __init__(self, root, files):
        self.files = set(files)
        self.py = collections.defaultdict(set)  # every dotted suffix of a module path -> files
        self.by_name = collections.defaultdict(set)
        for f in files:
            self.by_name[f.name].add(f)
            if f.suffix == ".py":
                parts = list(f.with_suffix("").parts)
                if parts[-1] == "__init__":
                    parts.pop()
                for i in range(len(parts)):
                    self.py[".".join(parts[i:])].add(f)
        m = re.search(r"^module\s+(\S+)", read(root / "go.mod") or "", re.M)
        self.gomod = m.group(1) if m else None
        self.godirs = {f.parent for f in files if f.suffix == ".go"}

    def first(self, cands):
        return next((c for c in cands if c in self.files), None)

    def python(self, rel, text):
        for frm, clause, plain in PY_IMPORT.findall(text):
            if frm.startswith("."):
                base = rel.parent
                for _ in range(len(frm) - len(frm.lstrip(".")) - 1):
                    base = base.parent
                here = base / frm.lstrip(".").replace(".", "/")
                for t in [here / n for n in names(clause) if n != "*"] + [here]:
                    hit = self.first([t.with_suffix(".py"), t / "__init__.py"])
                    if hit:
                        yield hit
                        break
                continue
            mods = names(plain) if plain else [f"{frm}.{n}" for n in names(clause) if n != "*"] + [frm]
            for mod in mods:
                parts = mod.split(".")
                while parts:
                    cands = self.py.get(".".join(parts), ())
                    if len(cands) == 1:
                        yield next(iter(cands))
                        break
                    parts.pop()

    def javascript(self, rel, text):
        for spec in JS_IMPORT.findall(text):
            if spec.startswith("."):
                base = Path(os.path.normpath(rel.parent / spec))
            elif spec.startswith(("@/", "~/")):
                base = Path("src") / spec[2:]
            else:
                continue
            hit = self.first([base] + [base.with_name(base.name + e) for e in JS_EXT]
                             + [base / f"index{e}" for e in JS_EXT])
            if hit:
                yield hit

    def go(self, rel, text):
        for spec in GO_IMPORT.findall(text) if self.gomod else ():
            d = Path(spec[len(self.gomod) + 1:])
            if spec.startswith(self.gomod + "/") and d in self.godirs:
                yield d  # Go imports packages, so the target is a directory

    def rust(self, rel, text):
        base = rel.parent if rel.name in ("main.rs", "lib.rs", "mod.rs") else rel.with_suffix("")
        for name in RS_MOD.findall(text):
            hit = self.first([base / f"{name}.rs", base / name / "mod.rs"])
            if hit:
                yield hit
        src = next((p for p in rel.parents if p.name == "src"), None)
        for path in RS_USE.findall(text) if src else ():
            parts = path.split("::")
            while parts:
                t = src.joinpath(*parts)
                hit = self.first([t.with_suffix(".rs"), t / "mod.rs"])
                if hit:
                    yield hit
                    break
                parts.pop()

    def c(self, rel, text):
        for inc in C_INCLUDE.findall(text):
            same = self.by_name.get(Path(inc).name, ())
            hit = self.first([Path(os.path.normpath(rel.parent / inc))]) or \
                (next(iter(same)) if len(same) == 1 else None)
            if hit:
                yield hit

    def of(self, rel, text):
        s = rel.suffix
        fn = (self.python if s == ".py" else self.javascript if s in JS_EXT else self.go if s == ".go"
              else self.rust if s == ".rs" else self.c if s in C_EXT else None)
        return set(fn(rel, text)) - {rel, rel.parent} if fn else set()


def routes_in(rel, text):
    """(METHOD, path, line) for each HTTP endpoint a file defines."""
    if rel.suffix not in ROUTE_EXT or not ROUTE_HINT.search(text):
        return []
    out = []
    for m in ROUTE.finditer(text):
        method, path = [g for g in m.groups() if g]
        method = "ANY" if method.lower() in ("route", "handlefunc", "request", "all") else method.upper()
        out.append((method, path, text.count("\n", 0, m.start()) + 1))
    return out


def area(p, depth):
    """The directory a file belongs to, cut to `depth` levels: the unit for boundary edges."""
    d = p.parent if p.suffix else p
    return "/".join(d.parts[:depth]) or "."


def area_depth(files):
    """Shallowest depth at which no single area holds most of the code, so wrappers like
    src/ or skills/<name>/ do not swallow every boundary."""
    for depth in range(1, 6):
        biggest = collections.Counter(area(f, depth) for f in files).most_common(1)
        if not biggest or biggest[0][1] <= 0.6 * len(files):
            return depth
    return 6


def section(title, lines):
    print(f"\n## {title}")
    print("\n".join(f"  {l}" for l in lines) or "  (none found)")


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        sys.exit(f"not a directory: {root}")
    langs, sizes, manifests, entries, docs, tests, src = collections.Counter(), [], [], [], [], [], {}
    for p in walk(root):
        rel = p.relative_to(root)
        if p.name in MANIFESTS:
            manifests.append(rel)
        if p.name in ENTRY:
            entries.append(rel)
        if p.name.upper().startswith(("README", "ARCHITECTURE", "CONTRIBUTING", "CLAUDE", "AGENTS")) \
                or "adr" in rel.parts or "docs" in rel.parts[:1]:
            docs.append(rel)
        lang = LANG.get(p.suffix)
        if lang and lang != "Markdown" and is_test(rel):
            tests.append(rel)
        if lang:
            text = read(p)
            n = text.count("\n") if text is not None else 0
            langs[lang] += n
            if lang != "Markdown":
                sizes.append((n, rel))
                if text is not None and not is_test(rel):
                    src[rel] = text

    print(f"# {root.name}\n")
    print("## Languages (lines)")
    for lang, n in langs.most_common(8):
        print(f"  {lang:<14}{n}")
    section("Docs worth reading first", map(str, sorted(docs)[:12]))
    section("Manifests / build", map(str, sorted(manifests)[:12]))
    section("Likely entry points", map(str, sorted(entries)[:12]))

    routes = [f"{m:<7}{path:<32} {rel}:{line}" for rel, text in src.items() for m, path, line in routes_in(rel, text)]
    section(f"HTTP endpoints: {len(routes)} (each is a flow you can trace end to end)", sorted(routes)[:15])

    imports = Imports(root, list(src))
    fan_in, edges, depth = collections.Counter(), collections.Counter(), area_depth(list(src))
    for rel, text in src.items():
        for t in imports.of(rel, text):
            fan_in[t] += 1
            a, b = area(rel, depth), area(t, depth)
            if a != b:
                edges[a, b] += 1
    section("Most depended-on files (fan-in; likely central abstractions)",
            [f"{n:>5}  {t}{'' if t.suffix else '/'}" for t, n in fan_in.most_common(10)])
    section("Heaviest directory -> directory imports (the real boundaries)",
            [f"{n:>5}  {a} -> {b}" for (a, b), n in edges.most_common(10)])
    both = sorted({tuple(sorted(k)) for k in edges if k[::-1] in edges},
                  key=lambda k: -(edges[k] + edges[k[::-1]]))
    section("Two-way directory dependencies (a tangle, or a boundary that isn't one)",
            [f"{a} <-> {b}  ({edges[a, b]} / {edges[b, a]})" for a, b in both[:8]])

    print("\n## Tests (the feedback loop for making changes)")
    if tests:
        dirs = collections.Counter(str(t.parent) for t in tests)
        print(f"  {len(tests)} test files; most in: " + ", ".join(f"{d} ({n})" for d, n in dirs.most_common(3)))
    else:
        print("  (none found)")
    section("Largest source files (often central or tangled)",
            [f"{n:>6}  {rel}" for n, rel in sorted(sizes, reverse=True)[:10]])

    if git(root, "rev-parse", "--is-inside-work-tree").strip() == "true":
        log = git(root, "log", "--since=1 year ago", "--name-only", "--pretty=format:")
        hot = collections.Counter(l for l in log.splitlines() if l and (root / l).exists())
        section("Hotspots: most-changed files, last year (where the action is)",
                [f"{n:>5}  {f}" for f, n in hot.most_common(10)])
        who = git(root, "shortlog", "-sn", "--no-merges", "HEAD").splitlines()[:5]
        print("\n## Top contributors\n" + ("\n".join(who) or "  (none)"))
        first = git(root, "log", "--reverse", "--pretty=%ad %s", "--date=short", "-n", "1").strip()
        print(f"\n## First commit\n  {first}")

    if (root / "floorplan" / "graph.json").is_file():
        print("\n## Floorplan map present\n  floorplan/graph.json: query it with "
              "`node floorplan/query.mjs overview` (see reference/codebase.md)")


if __name__ == "__main__":
    main()
