import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location("status", Path(__file__).resolve().parents[1] / "tools/coordination/status.py")
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)


class CoordinationTests(unittest.TestCase):
    def pr(self, body):
        return {"number": 9, "html_url": "https://github.com/TarbleFR/RewindBox/pull/9", "title": "handoff",
                "head": {"sha": "a" * 40, "ref": "work/owner"}, "base": {"ref": "Claude"}, "body": body}

    def test_source_advance_invalidates_handoff(self):
        pr = self.pr('<!-- rewindbox-handoff {"source":"' + "a"*40 + '","owner":"owner"} -->')
        self.assertEqual(status.handoff(pr)["handoff"], "current")
        pr["head"]["sha"] = "b"*40
        self.assertEqual(status.handoff(pr)["handoff"], "stale")

    def test_bad_or_absent_receipt_never_ready(self):
        for body in (None, "ready", '<!-- rewindbox-handoff {broken} -->'):
            self.assertEqual(status.handoff(self.pr(body))["handoff"], "missing")

    def test_pagination_and_no_mutating_requests(self):
        calls = []
        def get(path):
            calls.append(path)
            return list(range(100)) if path.endswith("&page=1") else [100]
        self.assertEqual(len(status.pages("repos/x/y/pulls?state=open", reader=get)), 101)
        self.assertEqual(calls[-1], "repos/x/y/pulls?state=open&per_page=100&page=2")

    def test_nonterminal_runs_deduplicated_and_exact_source_separate(self):
        def get(path):
            if path.endswith("/branches/Claude"):
                return {"commit": {"sha": "a"*40}}
            if "/pulls?" in path:
                return [self.pr("")]
            return {"workflow_runs": [{"id": 12, "head_sha": "a"*40, "status": "queued"}]}
        value = status.snapshot(get, "a"*40)
        self.assertEqual(len(value["activeRuns"]), 1)
        self.assertEqual(len(value["sourceRuns"]), 1)
        with self.assertRaises(ValueError):
            status.snapshot(get, "short")


if __name__ == "__main__":
    unittest.main()
