from copy import deepcopy
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace

spec = importlib.util.spec_from_file_location("tidy", Path(__file__).resolve().parents[1] / "build-utils/maintenance/tidy_repository.py")
tidy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tidy)
A, B = "a" * 40, "b" * 40


class Fake:
    def __init__(self):
        self.sha, self.merged, self.pr, self.active = A, True, False, False
        self.deleted, self.mutations = [], []
    def request(self, path, method="GET"):
        if method != "GET": self.mutations.append((method, path))
        if "/compare/" in path: return {"merge_base_commit": {"sha": A if self.merged else B}}
        if "/pulls?" in path: return [{"head": {"ref": "work/old"}, "base": {"ref": "Claude"}}] if self.pr else []
        if "/actions/runs?" in path: return {"workflow_runs": [{"id": 5, "head_branch": "work/old"}] if self.active else []}
        return {"commit": {"sha": self.sha}, "protected": False}
    def delete_branch(self, name, expected): self.deleted.append((name, expected))


class TidyTests(unittest.TestCase):
    def plan(self):
        return {"version": 1, "repository": tidy.REPO, "base_sha": A, "main_sha": A,
                "expires_at": "2050-01-01T00:00:00Z", "branches": [{"branch": "work/old", "sha": A}], "workflows": []}
    def test_reject_protected_or_expired_or_other_workflow(self):
        for name in ("main", "Claude", "backup/one", "work/../main", "work/backup-old"):
            plan = self.plan(); plan["branches"][0]["branch"] = name
            with self.assertRaises(RuntimeError): tidy.validate_plan(plan)
        plan = self.plan(); plan["expires_at"] = "2000-01-01T00:00:00Z"
        with self.assertRaises(RuntimeError): tidy.validate_plan(plan)
        plan = self.plan(); plan["workflows"] = [{"id": 1, "path": ".github/workflows/melonx-core.yml"}]
        with self.assertRaises(RuntimeError): tidy.validate_plan(plan)
    def test_moved_unmerged_open_pr_or_running_is_never_deleted(self):
        for attr, value in (("sha", B), ("merged", False), ("pr", True), ("active", True)):
            api = Fake(); setattr(api, attr, value)
            with self.assertRaises(RuntimeError): tidy.run(api, self.plan(), {"operations": []}, True)
            self.assertEqual(api.deleted, [])
    def test_dry_run_no_mutation_and_execute_uses_exact_lease(self):
        api = Fake(); tidy.run(api, self.plan(), {"operations": []})
        self.assertEqual(api.deleted, []); self.assertEqual(api.mutations, [])
        tidy.run(api, self.plan(), {"operations": []}, True)
        self.assertEqual(api.deleted, [("work/old", A)])
    def test_missing_token_does_not_expand_api_scope(self):
        api = tidy.API("test-placeholder")
        for path, method in ((tidy.PREFIX + "/actions/runs/1", "DELETE"), ("/repos/other/repo/actions/workflows/1/disable", "PUT")):
            with self.assertRaises(RuntimeError): api.request(path, method)
    def test_actual_delete_command_has_compare_and_delete_lease(self):
        with patch.object(tidy.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as run:
            tidy.API("unit-test-placeholder").delete_branch("work/old", A)
            command = run.call_args.args[0]
            self.assertIn("--force-with-lease=refs/heads/work/old:" + A, command)
            self.assertEqual(command[-1], ":refs/heads/work/old")
            self.assertNotIn("--force", command)
            self.assertNotIn("unit-test-placeholder", " ".join(command))
        with patch.object(tidy.subprocess, "run", return_value=SimpleNamespace(returncode=1)):
            with self.assertRaises(RuntimeError): tidy.API("test").delete_branch("work/old", A)

    def test_workflow_identity_and_active_run_guard(self):
        path = ".github/workflows/rewind610-delivery.yml"
        for mismatch, active in ((True, False), (False, True), (False, False)):
            api = Fake()
            original = api.request
            def request(url, method="GET"):
                if "/actions/workflows/" in url:
                    if method == "PUT":
                        api.mutations.append((method, url))
                    return {"path": "other.yml" if mismatch else path,
                            "state": "disabled_manually"}
                if "/actions/runs?" in url and active:
                    return {"workflow_runs": [{"id": 7, "head_branch": "Claude", "path": path}]}
                return original(url, method)
            api.request = request
            plan = self.plan(); plan["workflows"] = [{"id": 42, "path": path}]
            with patch.object(tidy, "check_branch"):
                if mismatch or active:
                    with self.assertRaises(RuntimeError): tidy.run(api, plan, {"operations": []}, True)
                    self.assertEqual(api.mutations, [])
                else:
                    tidy.run(api, plan, {"operations": []}, True)
                    self.assertEqual(api.mutations, [("PUT", tidy.PREFIX + "/actions/workflows/42/disable")])


if __name__ == "__main__": unittest.main()
