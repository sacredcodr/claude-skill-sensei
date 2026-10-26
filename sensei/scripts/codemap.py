#!/usr/bin/env python3
"""Fast recon of an unfamiliar codebase: where to start reading.

  codemap.py [path]

Prints languages by lines, manifests, likely entry points, largest files and,
if it is a git repo, the most-changed files (hotspots) and top contributors.
Facts only; interpreting them is the job of the learner and the coach.
"""
import collections
import subprocess
import sys
from pathlib import Path

SKIP = {".git", "node_modules", "target", "dist", "build", "__pycache__", ".venv", "venv", ".next", "vendor"}
LANG = {".py": "Python", ".rs": "Rust", ".go": "Go", ".js": "JavaScript", ".ts": "TypeScript",
        ".tsx": "TypeScript", ".jsx": "JavaScript", ".c": "C", ".h": "C/C++ header", ".cc": "C++",
        ".cpp": "C++", ".hpp": "C++", ".java": "Java", ".kt": "Kotlin", ".rb": "Ruby", ".cs": "C#",
        ".swift": "Swift", ".sh": "Shell", ".lua": "Lua", ".vala": "Vala", ".css": "CSS",
        ".html": "HTML", ".md": "Markdown", ".sql": "SQL"}
MANIFESTS = {"package.json", "Cargo.toml", "go.mod", "pyproject.toml", "setup.py", "requirements.txt",
             "pom.xml", "build.gradle", "meson.build", "CMakeLists.txt", "Makefile", "Dockerfile",
             "docker-compose.yml", "flake.nix", "justfile"}
ENTRY = {"main.py", "__main__.py", "app.py", "manage.py", "main.rs", "lib.rs", "main.go", "main.c",
         "main.cpp", "index.js", "index.ts", "main.ts", "server.js", "cli.py", "main.vala"}


def walk(root):
    for p in root.rglob("*"):
        if any(part in SKIP for part in p.relative_to(root).parts):
            continue
        if p.is_file():
            yield p


def nlines(p):
    try:
        with p.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def git(root, *args):
    r = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else ""


def main():
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    if not root.is_dir():
        sys.exit(f"not a directory: {root}")
    langs, sizes, manifests, entries, docs = collections.Counter(), [], [], [], []
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
        if lang:
            n = nlines(p)
            langs[lang] += n
            if lang != "Markdown":
                sizes.append((n, rel))

    print(f"# {root.name}\n")
    print("## Languages (lines)")
    for lang, n in langs.most_common(8):
        print(f"  {lang:<14}{n}")
    for title, items in (("Docs worth reading first", docs[:12]), ("Manifests / build", manifests[:12]),
                         ("Likely entry points", entries[:12])):
        print(f"\n## {title}")
        print("\n".join(f"  {i}" for i in sorted(items)) or "  (none found)")
    print("\n## Largest source files (often central or tangled)")
    for n, rel in sorted(sizes, reverse=True)[:10]:
        print(f"  {n:>6}  {rel}")

    if git(root, "rev-parse", "--is-inside-work-tree").strip() == "true":
        log = git(root, "log", "--since=1 year ago", "--name-only", "--pretty=format:")
        hot = collections.Counter(l for l in log.splitlines() if l and (root / l).exists())
        print("\n## Hotspots: most-changed files, last year (where the action is)")
        for f, n in hot.most_common(10):
            print(f"  {n:>5}  {f}")
        who = git(root, "shortlog", "-sn", "--no-merges", "HEAD").splitlines()[:5]
        print("\n## Top contributors\n" + ("\n".join(who) or "  (none)"))
        first = git(root, "log", "--reverse", "--pretty=%ad %s", "--date=short", "-n", "1").strip()
        print(f"\n## First commit\n  {first}")


if __name__ == "__main__":
    main()
