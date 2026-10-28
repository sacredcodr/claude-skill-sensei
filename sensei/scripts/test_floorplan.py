"""Tests for floorplan.py: python3 -I ~/.claude/skills/sensei/scripts/test_floorplan.py"""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import floorplan  # noqa: E402


class Globs(unittest.TestCase):
    def test_glob_forms(self):
        g = floorplan.glob_re
        self.assertTrue(g("src/**").match("src/a/b.py"))
        self.assertTrue(g("**/tests/**").match("tests/x.py"))
        self.assertTrue(g("src/*.py").match("src/a.py"))
        self.assertFalse(g("src/*.py").match("src/a/b.py"))
        self.assertTrue(g("src/{a,b}.c").match("src/b.c"))
        self.assertTrue(g("src/app").match("src/app/x.py"))  # bare path is a directory
        self.assertFalse(g("src/app").match("src/apple.py"))

    def test_longest_literal_prefix_wins(self):
        parts = [{"id": "all", "paths": ["src/**"]}, {"id": "store", "paths": ["src/store/**"]}]
        owner, ties, _ = floorplan.assign(["src/store/db.py", "src/ui.py"], parts, [])
        self.assertEqual(owner, {"src/store/db.py": "store", "src/ui.py": "all"})
        self.assertFalse(ties)


class Build(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        self.env = {**os.environ, "LEARN_HOME": str(t / "learn")}
        self.repo = t / "repo"
        (self.repo / "app").mkdir(parents=True)
        (self.repo / "app" / "main.py").write_text("from app import store\n")
        (self.repo / "app" / "store.py").write_text("X = 1\n")
        self.run_py("srs.py", "profile", "t", "--root", str(self.repo))

    def tearDown(self):
        self.tmp.cleanup()

    def run_py(self, script, *args, ok=True):
        r = subprocess.run([sys.executable, "-I", str(HERE / script), *args], capture_output=True,
                           text=True, env=self.env)
        self.assertEqual(r.returncode == 0, ok, r.stdout + r.stderr)
        return r.stdout

    def spec(self, data):
        (Path(self.env["LEARN_HOME"]) / "t" / "floorplan.json").write_text(json.dumps(data))

    def test_init_then_build_embeds_graph(self):
        self.run_py("floorplan.py", "init", "t")
        out = self.run_py("floorplan.py", "build", "t")
        self.assertIn("2/2 assigned", out)
        html = (Path(self.env["LEARN_HOME"]) / "t" / "floorplan.html").read_text()
        self.assertNotIn("__FLOORPLAN_DATA__", html)
        self.assertIn('["app/main.py","app/store.py"]', html)

    def test_bad_refs_fail_with_a_hint(self):
        self.spec({"project": {"name": "x"},
                   "parts": [{"id": "core", "label": "Core", "summary": "s", "paths": ["app"]}],
                   "flows": [{"id": "f", "title": "F", "steps": [{"node": "core"}, {"node": "app/stor.py"}]}]})
        out = self.run_py("floorplan.py", "build", "t", ok=False)
        self.assertIn("did you mean 'app/store.py'", out)

    def test_cards_land_on_their_file_and_answers_stay_out(self):
        self.spec({"project": {"name": "x"},
                   "parts": [{"id": "core", "label": "Core", "summary": "s", "paths": ["app"]}]})
        self.run_py("srs.py", "add", "t", "Where is X defined?", "SECRET-ANSWER", "--ref", "app/store.py:1")
        out = self.run_py("floorplan.py", "build", "t")
        self.assertIn("1 cards placed", out)
        html = (Path(self.env["LEARN_HOME"]) / "t" / "floorplan.html").read_text()
        self.assertIn("Where is X defined?", html)
        self.assertNotIn("SECRET-ANSWER", html)

    def test_show_prints_connections_with_their_imports(self):
        self.spec({"project": {"name": "x"},
                   "parts": [{"id": "ui", "label": "UI", "summary": "s", "paths": ["app/main.py"]},
                             {"id": "core", "label": "Core", "summary": "s", "paths": ["app/store.py"]},
                             {"id": "db", "label": "DB", "kind": "external", "summary": "s"}],
                   "edges": [{"from": "core", "to": "db", "label": "writes"}]})
        out = self.run_py("floorplan.py", "show", "t")
        self.assertIn("-> Core [core]: 1 import", out)
        self.assertIn("-> DB [db]: writes", out)
        self.assertIn("app/main.py -> app/store.py", self.run_py("floorplan.py", "show", "t", "core"))


if __name__ == "__main__":
    unittest.main()
