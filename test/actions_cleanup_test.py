"""Behavioral safety tests for the destructive Actions maintenance boundary.

All API calls are fakes. These tests do not contact GitHub or delete anything.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.error


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("actions_cleanup", ROOT / "build-utils/maintenance/cleanup_actions.py")
cleanup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cleanup)

BASE_SHA, MAIN_SHA, EXEC_SHA = "a" * 40, "b" * 40, "c" * 40


def records(count):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return [{"id": 100000 + i, "created_at": (start + timedelta(seconds=i)).isoformat(),
             "updated_at": (start + timedelta(seconds=i + 1)).isoformat(),
             "head_sha": "d" * 40, "path": ".github/workflows/check.yml", "status": "completed",
             "run_attempt": 1}
            for i in range(count, 0, -1)]


def plan_for(runs, **changes):
    result = {"schema_version": 1, "repository": cleanup.REPOSITORY, "branch": "Claude",
              "base_sha": BASE_SHA, "main_sha": MAIN_SHA, "expires_at": "2050-01-01T00:00:00Z",
              "keep_recent": 300, "snapshot_total": len(runs), "snapshot_runs": deepcopy(runs),
              "protected_runs": [], "max_deletions": 1925}
    result.update(changes)
    return result


def context():
    environment = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push",
                   "GITHUB_REPOSITORY": cleanup.REPOSITORY, "GITHUB_REF": "refs/heads/Claude",
                   "GITHUB_SHA": EXEC_SHA, "GITHUB_TOKEN": "unit-test-placeholder",
                   "GITHUB_RUN_ID": "999999", "GITHUB_WORKFLOW_SHA": EXEC_SHA,
                   "GITHUB_API_URL": cleanup.API_URL}
    event = {"repository": {"full_name": cleanup.REPOSITORY}, "ref": "refs/heads/Claude",
             "before": BASE_SHA, "after": EXEC_SHA, "forced": False, "created": False, "deleted": False}
    return environment, event


class FakeAPI:
    def __init__(self, runs):
        self.runs = {r["id"]: deepcopy(r) for r in runs}
        self.deleted = []
        self.requests = []
        self.responses = {}
        self.claude_sha = EXEC_SHA
        self.main_sha = MAIN_SHA
        self.after_delete = None

    def get_json(self, path):
        self.requests.append(("GET", path))
        if path == cleanup.PREFIX + "/git/ref/heads/Claude":
            return {"object": {"sha": self.claude_sha}}
        if path == cleanup.PREFIX + "/git/ref/heads/main":
            return {"object": {"sha": self.main_sha}}
        if path.startswith(cleanup.PREFIX + '/actions/runs/') and '?' not in path:
            return deepcopy(self.runs[int(path.rsplit('/', 1)[1])])
        page = int(path.rsplit("=", 1)[1])
        ordered = sorted(self.runs.values(), key=cleanup.run_key, reverse=True)
        return {"total_count": len(ordered), "workflow_runs": deepcopy(ordered[(page-1)*100:page*100])}

    def delete_run(self, run_id):
        self.requests.append(("DELETE", run_id))
        self.deleted.append(run_id)
        status = self.responses.get(run_id, 204)
        if status in (204, 404):
            self.runs.pop(run_id, None)
        if self.after_delete:
            self.after_delete(self, run_id)
        return status

    def pace(self):
        pass


class CleanupSafetyTest(unittest.TestCase):
    def test_skipped_only_policy_protects_executed_jobs_and_allows_product_push(self):
        runs = records(302)
        for r in runs:
            r['conclusion'] = 'skipped'
        runs[-1]['conclusion'] = 'success'
        plan = plan_for(runs, skipped_only=True)
        with self.assertRaises(cleanup.SafetyError):
            cleanup.validate_plan(plan)
        plan['protected_runs'] = [{'id': runs[-1]['id'], 'reasons': ['successful_build']}]
        cleanup.validate_plan(plan)
        api = FakeAPI(runs)
        api.claude_sha = 'e' * 40
        cleanup.check_refs(api, EXEC_SHA, MAIN_SHA, allow_claude_advance=True)
        with tempfile.TemporaryDirectory() as tmp:
            env, event = context()
            journal = cleanup.Journal(Path(tmp), execute=True)
            result = cleanup.run_cleanup(api, plan, journal, execute=True, environment=env, event=event)
            self.assertEqual(result['status'], 'completed')
            self.assertEqual(api.deleted, [runs[-2]['id']])
        current = deepcopy(runs)
        current[-2]['conclusion'] = 'success'
        self.assertEqual(cleanup.refresh_selection(plan, current, {}, {}, None), [])

    def test_api_id_order_with_inverted_creation_clock_is_normalized(self):
        runs = records(4)
        runs[0]['created_at'], runs[1]['created_at'] = runs[1]['created_at'], runs[0]['created_at']
        class IDOrderedAPI(FakeAPI):
            def get_json(self, path):
                value = super().get_json(path)
                if 'workflow_runs' in value:
                    value['workflow_runs'].sort(key=lambda r: r['id'], reverse=True)
                return value
        api = IDOrderedAPI(runs)
        self.assertEqual(cleanup.list_all_runs(api), sorted(runs, key=cleanup.run_key, reverse=True))
        self.assertEqual(api.deleted, [])

    def test_same_second_api_order_is_normalized_after_stability_check(self):
        runs = records(4)
        for run in runs:
            run['created_at'] = runs[0]['created_at']
        class TiedAPI(FakeAPI):
            def get_json(self, path):
                value = super().get_json(path)
                if 'workflow_runs' in value:
                    value['workflow_runs'].reverse()
                return value
        api = TiedAPI(runs)
        actual = cleanup.list_all_runs(api)
        self.assertEqual([r['id'] for r in actual], sorted((r['id'] for r in runs), reverse=True))
        self.assertEqual(api.deleted, [])

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def run_cleanup(self, api, plan, execute=True, environment=None, event=None):
        env, ev = context()
        journal = cleanup.Journal(Path(self.directory.name), "f" * 64, execute)
        return cleanup.run_cleanup(api, plan, journal, execute=execute,
                                   environment=env if environment is None else environment,
                                   event=ev if event is None else event)

    def test_dry_run_has_no_mutation_and_writes_reviewable_selection(self):
        runs = records(304)
        api = FakeAPI(runs)
        result = self.run_cleanup(api, plan_for(runs), execute=False)
        self.assertEqual(api.deleted, [])
        self.assertEqual(result["initial_candidate_count"], 4)
        self.assertTrue((Path(self.directory.name) / "dry-run.json").is_file())
        self.assertTrue((Path(self.directory.name) / "summary.md").is_file())

    def test_current_recent_dependencies_active_new_and_rerun_are_kept(self):
        runs = records(307)
        plan = plan_for(runs, protected_runs=[{"id": 100003, "reasons": ["active native dependency"]}])
        plan["snapshot_runs"][-1]["status"] = "in_progress"  # Keep even if it has since completed.
        api = FakeAPI(records(357))  # Fifty new IDs are never eligible.
        api.runs[100002]["status"] = "queued"
        api.runs[100004]["run_attempt"] = 2
        api.runs[100005]["updated_at"] = "2026-01-02T00:00:00Z"
        result = self.run_cleanup(api, plan)
        self.assertEqual(api.deleted, list(range(100006, 100058)))
        self.assertEqual(result["deleted_run_ids"], list(range(100006, 100058)))
        self.assertTrue(set(r["id"] for r in records(357)[:300]).issubset(api.runs))
        self.assertTrue(set(range(100308, 100358)).issubset(api.runs))

    def test_executing_run_is_never_a_target(self):
        runs = records(301)
        env, event = context()
        env["GITHUB_RUN_ID"] = "100001"
        api = FakeAPI(runs)
        self.run_cleanup(api, plan_for(runs), environment=env, event=event)
        self.assertEqual(api.deleted, [])

    def test_changed_identity_stops_before_any_deletion(self):
        runs = records(301)
        api = FakeAPI(runs)
        api.runs[100001]["head_sha"] = "e" * 40
        with self.assertRaisesRegex(cleanup.SafetyError, "identity changed"):
            self.run_cleanup(api, plan_for(runs))
        self.assertEqual(api.deleted, [])

    def test_changed_claude_ref_stops_at_the_next_50_boundary(self):
        runs = records(401)
        api = FakeAPI(runs)
        api.after_delete = lambda a, rid: setattr(a, "claude_sha", "e" * 40) if len(a.deleted) == 50 else None
        with self.assertRaisesRegex(cleanup.SafetyError, "Claude SHA changed"):
            self.run_cleanup(api, plan_for(runs))
        self.assertEqual(len(api.deleted), 50)
        receipt = json.loads((Path(self.directory.name) / "receipt.json").read_text())
        self.assertEqual(len(receipt["deleted_run_ids"]), 50)

    def test_changed_main_ref_stops_before_deletion(self):
        runs = records(301)
        api = FakeAPI(runs)
        api.main_sha = "e" * 40
        with self.assertRaisesRegex(cleanup.SafetyError, "main SHA changed"):
            self.run_cleanup(api, plan_for(runs))
        self.assertEqual(api.deleted, [])

    def test_active_run_seen_at_chunk_refresh_is_not_deleted(self):
        runs = records(552)
        api = FakeAPI(runs)
        def change(a, rid):
            if len(a.deleted) == 250:
                a.runs[100251]["status"] = "in_progress"
        api.after_delete = change
        self.run_cleanup(api, plan_for(runs))
        self.assertNotIn(100251, api.deleted)
        self.assertIn(100252, api.deleted)
        self.assertEqual(len(api.deleted), 251)

    def test_404_is_idempotent_and_409_is_preserved(self):
        runs = records(303)
        api = FakeAPI(runs)
        api.responses = {100001: 404, 100002: 409}
        result = self.run_cleanup(api, plan_for(runs))
        self.assertEqual(result["already_absent_run_ids"], [100001])
        self.assertEqual(result["conflict_run_ids"], [100002])
        self.assertEqual(result["deleted_run_ids"], [100003])
        self.assertIn(100002, api.runs)
        # A second execution is bounded by the same original snapshot.
        second = self.run_cleanup(api, plan_for(runs))
        self.assertEqual(second["deleted_run_ids"], [])

    def test_candidate_limit_fails_closed_instead_of_truncating(self):
        runs = records(304)
        api = FakeAPI(runs)
        with self.assertRaisesRegex(cleanup.SafetyError, "exceeds the reviewed maximum"):
            self.run_cleanup(api, plan_for(runs, max_deletions=3))
        self.assertEqual(api.deleted, [])

    def test_404_is_not_reported_as_success_when_run_is_still_listed(self):
        runs = records(301)
        api = FakeAPI(runs)
        api.responses = {100001: 404}
        api.after_delete = lambda a, rid: a.runs.update({rid: deepcopy(runs[-1])})
        with self.assertRaisesRegex(cleanup.SafetyError, "reported deleted or absent is still listed"):
            self.run_cleanup(api, plan_for(runs))
        self.assertEqual(api.deleted, [100001])

    def test_wrong_event_parent_or_ref_cannot_execute(self):
        runs = records(301)
        for field, value in (("before", "e" * 40), ("ref", "refs/heads/main"), ("forced", True)):
            with self.subTest(field=field):
                env, event = context()
                event[field] = value
                api = FakeAPI(runs)
                with self.assertRaises(cleanup.SafetyError):
                    self.run_cleanup(api, plan_for(runs), environment=env, event=event)
                self.assertEqual(api.requests, [])

    def test_duplicate_pagination_fails_closed(self):
        runs = records(301)
        api = FakeAPI(runs)
        original = api.get_json
        def moved(path):
            response = original(path)
            if path.endswith("page=2"):
                response["workflow_runs"][0] = deepcopy(runs[99])
            return response
        api.get_json = moved
        with self.assertRaises(cleanup.SafetyError):
            self.run_cleanup(api, plan_for(runs))
        self.assertEqual(api.deleted, [])

    def test_page_count_or_first_page_movement_fails_closed(self):
        runs = records(301)
        for kind in ("count", "first_page"):
            with self.subTest(kind=kind):
                api = FakeAPI(runs)
                original = api.get_json
                first_calls = [0]
                def moved(path):
                    response = original(path)
                    if kind == "count" and path.endswith("page=2"):
                        response["total_count"] += 1
                    if path.endswith("page=1"):
                        first_calls[0] += 1
                        if kind == "first_page" and first_calls[0] == 2:
                            response["workflow_runs"] = response["workflow_runs"][1:]
                    return response
                api.get_json = moved
                with self.assertRaises(cleanup.SafetyError):
                    self.run_cleanup(api, plan_for(runs))
                self.assertEqual(api.deleted, [])

    def test_expired_plan_and_invalid_host_fail_before_network(self):
        runs = records(301)
        api = FakeAPI(runs)
        with self.assertRaisesRegex(cleanup.SafetyError, "expired"):
            self.run_cleanup(api, plan_for(runs, expires_at="2000-01-01T00:00:00Z"))
        env, event = context()
        env["GITHUB_API_URL"] = "https://example.invalid"
        with self.assertRaisesRegex(cleanup.SafetyError, "GITHUB_API_URL"):
            self.run_cleanup(api, plan_for(runs), environment=env, event=event)
        self.assertEqual(api.requests, [])

    def test_quota_pause_rechecks_refs_and_current_target_before_retrying_delete(self):
        runs = records(301)
        for change in ("active", "main_sha"):
            with self.subTest(change=change):
                backing = FakeAPI(runs)
                elapsed = [0.0]
                delete_requests = []
                class Server:
                    def open(inner, request, timeout):
                        path = request.full_url.removeprefix(cleanup.API_URL)
                        if request.method == "DELETE":
                            delete_requests.append(path)
                            if change == "active":
                                backing.runs[100001]["status"] = "in_progress"
                            else:
                                backing.main_sha = "e" * 40
                            raise urllib.error.HTTPError(request.full_url, 429, "test", {"Retry-After": "60"}, io.BytesIO(b""))
                        response = io.BytesIO(json.dumps(backing.get_json(path)).encode())
                        response.status, response.headers = 200, {}
                        return response
                def sleep(seconds):
                    elapsed[0] += seconds
                api = cleanup.GitHubAPI("unit-test-placeholder", opener=Server(), sleep=sleep,
                                        clock=lambda: 1000 + elapsed[0], monotonic=lambda: elapsed[0],
                                        progress=lambda *a, **k: None)
                with self.assertRaises(cleanup.SafetyError):
                    self.run_cleanup(api, plan_for(runs))
                self.assertEqual(len(delete_requests), 1)  # Only the rate-limited request, never a retry.
                self.assertEqual(backing.deleted, [])
                self.assertEqual(elapsed[0], 60)

    def test_quota_pause_in_get_refs_invalidates_selection_before_first_delete(self):
        runs = records(301)
        backing = FakeAPI(runs)
        elapsed = [0.0]
        claude_reads = [0]
        delete_requests = []
        class Server:
            def open(inner, request, timeout):
                path = request.full_url.removeprefix(cleanup.API_URL)
                if request.method == "DELETE":
                    delete_requests.append(path)
                    raise AssertionError("An active run must never be sent to DELETE")
                if path.endswith("/git/ref/heads/Claude"):
                    claude_reads[0] += 1
                    # First refs check precedes selection; the second is the
                    # immediate pre-DELETE guard and must invalidate that list.
                    if claude_reads[0] == 2:
                        backing.runs[100001]["status"] = "in_progress"
                        raise urllib.error.HTTPError(request.full_url, 429, "test", {"Retry-After": "60"}, io.BytesIO(b""))
                response = io.BytesIO(json.dumps(backing.get_json(path)).encode())
                response.status, response.headers = 200, {}
                return response
        def sleep(seconds):
            elapsed[0] += seconds
        api = cleanup.GitHubAPI("unit-test-placeholder", opener=Server(), sleep=sleep,
                                clock=lambda: 1000 + elapsed[0], monotonic=lambda: elapsed[0],
                                progress=lambda *a, **k: None)
        with self.assertRaisesRegex(cleanup.SafetyError, "no longer eligible"):
            self.run_cleanup(api, plan_for(runs))
        self.assertEqual(delete_requests, [])
        self.assertEqual(elapsed[0], 60)


class RateLimitTest(unittest.TestCase):
    class Opener:
        def __init__(self, errors):
            self.errors = list(errors)
            self.calls = 0
        def open(self, request, timeout):
            self.calls += 1
            status, headers, body = self.errors.pop(0)
            if status >= 400:
                raise urllib.error.HTTPError(request.full_url, status, "test", headers, io.BytesIO(body))
            result = io.BytesIO(body)
            result.status = status
            result.headers = headers
            return result

    def client(self, responses):
        elapsed = [0.0]
        pauses = []
        def sleep(seconds):
            pauses.append(seconds)
            elapsed[0] += seconds
        opener = self.Opener(responses)
        api = cleanup.GitHubAPI("unit-test-placeholder", sleep=sleep, clock=lambda: 1000 + elapsed[0],
                                monotonic=lambda: elapsed[0], opener=opener, progress=lambda *a, **k: None)
        return api, pauses, opener

    def test_secondary_limit_waits_60_seconds_and_revalidates_before_delete_retry(self):
        api, pauses, opener = self.client([(403, {}, b'{"message":"secondary rate limit"}'), (204, {}, b"")])
        revalidated = []
        api.on_delete_resume = revalidated.append
        self.assertEqual(api.delete_run(100001), 204)
        self.assertEqual(sum(pauses), 60)
        self.assertEqual(revalidated, [100001])
        self.assertEqual(opener.calls, 2)

    def test_retry_after_is_respected_and_permission_error_is_not_retried(self):
        api, pauses, opener = self.client([(429, {"Retry-After": "90"}, b""), (200, {}, b"{}")])
        self.assertEqual(api.get_json(cleanup.PREFIX + "/git/ref/heads/main"), {})
        self.assertEqual(sum(pauses), 90)
        api, pauses, opener = self.client([(403, {}, b'{"message":"Resource not accessible"}')])
        with self.assertRaisesRegex(cleanup.SafetyError, "HTTP 403"):
            api.delete_run(100001)
        self.assertEqual(opener.calls, 1)
        self.assertEqual(pauses, [])

    def test_rate_retries_are_bounded_and_long_wait_stops(self):
        api, pauses, opener = self.client([(403, {}, b'{"message":"secondary rate limit"}')] * 5)
        with self.assertRaisesRegex(cleanup.SafetyError, "retries exhausted"):
            api.get_json(cleanup.PREFIX + "/git/ref/heads/main")
        self.assertEqual(opener.calls, 5)
        self.assertEqual(sum(pauses), 60 + 120 + 240 + 480)
        api, pauses, opener = self.client([(429, {"Retry-After": "10000"}, b"")])
        with self.assertRaisesRegex(cleanup.SafetyError, "150-minute"):
            api.get_json(cleanup.PREFIX + "/git/ref/heads/main")
        self.assertEqual(pauses, [])

    def test_mutation_api_allowlist_is_exact(self):
        api, pauses, opener = self.client([])
        for method, path in (("DELETE", cleanup.PREFIX + "/actions/artifacts/1"),
                             ("POST", cleanup.PREFIX + "/actions/runs/1"),
                             ("DELETE", "/repos/Other/repo/actions/runs/1"),
                             ("DELETE", cleanup.PREFIX + "/actions/runs/1?other=1")):
            with self.subTest(path=path), self.assertRaises(cleanup.SafetyError):
                api.request(method, path)
        self.assertEqual(opener.calls, 0)

    def test_wait_during_revalidation_is_not_lost(self):
        api, pauses, opener = self.client([(204, {}, b"")])
        api.wait(1, "initial quota wait")
        calls = []
        def callback(run_id):
            calls.append(run_id)
            if len(calls) == 1:
                api.wait(60, "GET quota wait during fresh listing")
        api.on_delete_resume = callback
        self.assertEqual(api.delete_run(100001), 204)
        self.assertEqual(calls, [100001, 100001])
        self.assertEqual(api.selection_epoch, api.wait_epoch)
        self.assertEqual(opener.calls, 1)


if __name__ == "__main__":
    unittest.main()
