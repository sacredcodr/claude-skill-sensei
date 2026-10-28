"""Tests for srs.py: python3 -I ~/.claude/skills/sensei/scripts/test_srs.py"""
import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRS = Path(__file__).with_name("srs.py")


class Srs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {**os.environ, "LEARN_HOME": self.tmp.name}

    def tearDown(self):
        self.tmp.cleanup()

    def run_srs(self, *args, stdin=None, ok=True):
        r = subprocess.run([sys.executable, "-I", str(SRS), *args], input=stdin,
                           capture_output=True, text=True, env=self.env)
        self.assertEqual(r.returncode == 0, ok, r.stderr)
        return r.stdout.strip() if ok else r.stderr

    def test_sm2_schedule(self):
        self.run_srs("add", "t", "q", "a")
        days = []
        for _ in range(3):
            out = self.run_srs("grade", "t", "1", "4")
            days.append(int(out.split("interval ")[1].split("d")[0]))
        self.assertEqual(days[:2], [1, 6])
        self.assertGreater(days[2], 6)

    def test_fail_resets(self):
        self.run_srs("add", "t", "q", "a")
        self.run_srs("grade", "t", "1", "5")
        out = self.run_srs("grade", "t", "1", "1")
        self.assertIn("interval 1d", out)

    def test_due_orders_failed_first_and_counts_total(self):
        self.run_srs("add-batch", "t", stdin=json.dumps([{"q": f"q{i}", "a": "a"} for i in range(4)]))
        self.run_srs("grade-batch", "t", "1:5,2:1")
        # card 2 failed (due tomorrow); push everything due so ordering is visible
        path = Path(self.tmp.name) / "t" / "cards.json"
        cards = json.loads(path.read_text())
        yesterday = (dt.date.today() - dt.timedelta(days=1)).isoformat()
        for c in cards:
            c["due"] = yesterday
        path.write_text(json.dumps(cards))
        out = json.loads(self.run_srs("due", "t", "--limit", "2"))
        self.assertEqual(out["total_due"], 4)
        self.assertEqual(len(out["cards"]), 2)
        self.assertEqual(out["cards"][0]["id"], 2)

    def test_suspend_hides_card(self):
        self.run_srs("add", "t", "q", "a")
        self.run_srs("suspend", "t", "1")
        self.assertEqual(json.loads(self.run_srs("due", "t"))["total_due"], 0)
        self.run_srs("unsuspend", "t", "1")
        self.assertEqual(json.loads(self.run_srs("due", "t"))["total_due"], 1)

    def test_edit_and_delete(self):
        self.run_srs("add", "t", "q", "a")
        self.run_srs("edit", "t", "1", "--q", "better")
        self.assertIn("better", self.run_srs("due", "t"))
        self.run_srs("delete", "t", "1")
        self.assertEqual(json.loads(self.run_srs("stats", "t"))["cards"], 0)

    def test_grade_batch_is_atomic(self):
        self.run_srs("add", "t", "q", "a")
        self.run_srs("grade-batch", "t", "1:4,99:4", ok=False)
        cards = json.loads((Path(self.tmp.name) / "t" / "cards.json").read_text())
        self.assertEqual(cards[0]["history"], [])

    def test_bad_slug_rejected(self):
        self.run_srs("add", "../evil", "q", "a", ok=False)
        self.run_srs("add", "Has Caps", "q", "a", ok=False)

    def test_unknown_topic_is_a_clear_error(self):
        err = self.run_srs("due", "nope", ok=False)
        self.assertIn("no topic", err)
        self.assertFalse((Path(self.tmp.name) / "nope").exists())

    def test_profile_and_resume(self):
        self.run_srs("add", "t", "q", "a")
        self.run_srs("profile", "t", "--goal", "g", "--stage", "parsing=2:stuck on X",
                     "--shaky", "a;b", "--log", "first session")
        r = json.loads(self.run_srs("resume", "t"))
        self.assertEqual(r["stages"]["parsing"], "2 conscious incompetence")
        self.assertEqual(r["shaky"], ["a", "b"])
        self.assertEqual(r["total_due"], 1)
        self.assertEqual(r["last_log"][1], "first session")

    def test_check_refs_detects_change(self):
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        (repo / "m.py").write_text("a\n")
        self.run_srs("profile", "t", "--root", str(repo))
        self.run_srs("add", "t", "q", "a", "--ref", "m.py:1")
        self.assertEqual(self.run_srs("check-refs", "t"), "")
        (repo / "m.py").write_text("b\n")
        self.assertIn("changed", self.run_srs("check-refs", "t"))
        (repo / "m.py").unlink()
        self.assertIn("missing", self.run_srs("check-refs", "t"))

    def test_check_refs_follows_code_not_file(self):
        repo = Path(self.tmp.name) / "repo"
        repo.mkdir()
        (repo / "m.py").write_text("import os\n\ndef load_config(path):\n    return path\n")
        self.run_srs("profile", "t", "--root", str(repo))
        self.run_srs("add", "t", "q", "a", "--ref", "m.py:3-4")
        # Code that only moved is re-pointed, and reported once.
        (repo / "m.py").write_text("import os\nimport sys\n\ndef load_config(path):\n    return path\n")
        moved = json.loads(self.run_srs("check-refs", "t"))
        self.assertEqual((moved["status"], moved["new_ref"]), ("moved", "m.py:4-5"))
        self.assertEqual(json.loads(self.run_srs("due", "t"))["cards"][0]["ref"], "m.py:4-5")
        self.assertEqual(self.run_srs("check-refs", "t"), "")
        # An edit that leaves the referenced line intact is not a reason to re-verify.
        (repo / "m.py").write_text("import os\nimport sys\n\ndef load_config(path):\n    return path  # x\n")
        self.assertEqual(self.run_srs("check-refs", "t"), "")
        (repo / "m.py").write_text("import os\n\ndef read_settings(path):\n    return path\n")
        changed = json.loads(self.run_srs("check-refs", "t"))
        self.assertEqual(changed["status"], "changed")
        self.assertIn("load_config", changed["was"])
        # Re-pointing (or a bare edit) re-stamps a verified card.
        self.run_srs("edit", "t", "1", "--ref", "m.py:3")
        self.assertEqual(self.run_srs("check-refs", "t"), "")

    def test_profile_only_topic_is_resumable(self):
        self.run_srs("profile", "fresh", "--goal", "g")
        self.assertIn("fresh", self.run_srs("topics"))
        self.assertEqual(json.loads(self.run_srs("resume", "fresh"))["total_due"], 0)

    def test_overview(self):
        self.run_srs("add", "one", "q", "a")
        self.run_srs("add", "two", "q", "a")
        lines = self.run_srs("overview").splitlines()
        self.assertEqual({json.loads(l)["topic"] for l in lines}, {"one", "two"})


if __name__ == "__main__":
    unittest.main()
