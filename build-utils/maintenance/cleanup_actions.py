#!/usr/bin/env python3
"""One-shot, manifest-bounded GitHub Actions history cleanup.

Dry-run is the default. The only permitted mutation is DELETE of a completed
workflow run listed in the reviewed snapshot. No token or API response body is
written to the progress journal. This script does not build or publish anything.

A plan keeps at least the newest 300 runs of each listing (more when its
keep_recent says so). With a reference_guard, Claude may advance while the plan
runs: every file a later commit changes is read, and a target it newly cites
(run or artifact ID) is kept. A GitHub server error is retried a bounded number
of times; a run whose DELETE keeps failing is kept.
"""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.request


REPOSITORY = "TarbleFR/RewindBox"
BRANCH = "Claude"
API_URL = "https://api.github.com"
PREFIX = f"/repos/{REPOSITORY}"
KEEP_RECENT = 300  # Minimum; a plan may keep more (keep_recent).
MAX_DELETIONS = 2700
REFRESH_EVERY = 250
CHECK_REFS_EVERY = 50
MAX_WAIT_SECONDS = 150 * 60
MAX_RUNTIME_SECONDS = 170 * 60  # Leave ten minutes for the workflow's evidence upload.
LISTING_ATTEMPTS = 6  # Pushes create runs while the pages are read: a moved listing is read again.
LISTING_SETTLE_SECONDS = 20.0
SERVER_ERRORS = frozenset({500, 502, 503, 504})
SERVER_RETRIES = 3  # A repeated DELETE is idempotent: an applied one then answers 404.
SERVER_RETRY_SECONDS = 15.0
MAX_SERVER_ERROR_RUNS = 10  # Runs kept after repeated server errors before the cleanup stops.
SHA_RE = re.compile(r"[0-9a-f]{40}\Z")
ID_RE = re.compile(rb"(?<![0-9])[0-9]{11}(?![0-9])")
PLAN_PATH_RE = re.compile(r"build-utils/maintenance/[A-Za-z0-9._-]+\.json\Z")
RUN_IDENTITY_FIELDS = ('id', 'created_at', 'head_sha', 'path', 'status', 'conclusion',
                       'run_attempt', 'updated_at')
COMPLETED_CONCLUSIONS = {'action_required', 'cancelled', 'failure', 'neutral', 'skipped',
                         'stale', 'startup_failure', 'success', 'timed_out'}


class SafetyError(RuntimeError):
    """An invariant failed; no further DELETE is allowed."""


class ListingMoved(SafetyError):
    """Runs were created or removed while the listing pages were read."""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat().replace("+00:00", "Z")


def timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise SafetyError("Missing or invalid ISO timestamp")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SafetyError("Invalid ISO timestamp") from exc
    if result.tzinfo is None:
        raise SafetyError("Timestamp must include its UTC offset")
    return result.astimezone(timezone.utc)


def positive_id(value: object) -> int:
    if type(value) is not int or value <= 0:
        raise SafetyError("Run IDs must be positive integers")
    return value


def run_key(run: dict) -> tuple:
    return timestamp(run["created_at"]), run["id"]


def validate_run(run: object) -> dict:
    if not isinstance(run, dict):
        raise SafetyError("Run record must be an object")
    positive_id(run.get("id"))
    timestamp(run.get("created_at"))
    if not isinstance(run.get("head_sha"), str) or not SHA_RE.fullmatch(run["head_sha"]):
        raise SafetyError(f"Invalid source SHA for run {run['id']}")
    if not isinstance(run.get("path"), str) or not run["path"]:
        raise SafetyError(f"Missing workflow path for run {run['id']}")
    if not isinstance(run.get("status"), str) or not run["status"]:
        raise SafetyError(f"Missing status for run {run['id']}")
    if "run_attempt" in run and (type(run["run_attempt"]) is not int or run["run_attempt"] < 1):
        raise SafetyError(f"Invalid attempt for run {run['id']}")
    if "updated_at" in run:
        timestamp(run["updated_at"])
    return run


def validate_order(runs: list[dict]) -> None:
    keys = [run_key(run) for run in runs]
    if keys != sorted(keys, reverse=True):
        raise SafetyError("Run listing is not in descending creation time/ID order")
    if len({run["id"] for run in runs}) != len(runs):
        raise SafetyError("Duplicate run IDs: pagination moved; refusing cleanup")


def validate_plan(plan: object, now: datetime | None = None) -> dict:
    if not isinstance(plan, dict) or plan.get("schema_version", plan.get("schema")) != 1:
        raise SafetyError("Expected cleanup plan schema_version 1")
    if plan.get("repository") != REPOSITORY or plan.get("branch") != BRANCH:
        raise SafetyError("Plan repository/branch is not the authorized target")
    for field in ("base_sha", "main_sha"):
        if not isinstance(plan.get(field), str) or not SHA_RE.fullmatch(plan[field]):
            raise SafetyError(f"Invalid {field}")
    if timestamp(plan.get("expires_at")) <= (now or utc_now()):
        raise SafetyError("Cleanup plan has expired")
    if type(plan.get("keep_recent")) is not int or plan["keep_recent"] < KEEP_RECENT:
        raise SafetyError("The plan must preserve at least the newest 300 runs")
    limit = plan.get("max_deletions")
    if type(limit) is not int or not 0 <= limit <= MAX_DELETIONS:
        raise SafetyError("Deletion limit exceeds the authorized bound")
    runs = plan.get("snapshot_runs")
    if not isinstance(runs, list):
        raise SafetyError("Missing snapshot_runs")
    for run in runs:
        validate_run(run)
    validate_order(runs)
    if "snapshot_total" in plan and plan["snapshot_total"] != len(runs):
        raise SafetyError("Snapshot count disagrees with snapshot_runs")
    protected = plan.get("protected_runs")
    if not isinstance(protected, list):
        raise SafetyError("Missing explicit protected_runs")
    ids = []
    for item in protected:
        if not isinstance(item, dict) or not isinstance(item.get("reasons"), list) or not item["reasons"]:
            raise SafetyError("Every protected run requires a reason list")
        ids.append(positive_id(item.get("id")))
    if len(ids) != len(set(ids)):
        raise SafetyError("Duplicate explicit protected run IDs")
    if 'preserve_artifacts' in plan and type(plan['preserve_artifacts']) is not bool:
        raise SafetyError('preserve_artifacts must be an explicit boolean')
    if plan.get('preserve_artifacts') is True:
        if plan.get('skipped_only') is True:
            raise SafetyError('Choose preserve_artifacts or skipped_only, not both')
        for run in runs:
            if any(field not in run for field in RUN_IDENTITY_FIELDS):
                raise SafetyError('Artifact-preserving snapshots require every run identity field')
            if run['status'] == 'completed' and (not isinstance(run['conclusion'], str)
                                                or run['conclusion'] not in COMPLETED_CONCLUSIONS):
                raise SafetyError('Artifact-preserving snapshots require a known completed conclusion')
    if plan.get('skipped_only') is True:
        protected_ids = set(ids)
        if any(r.get('conclusion') != 'skipped' and r['id'] not in protected_ids for r in runs):
            raise SafetyError('Skipped-only policy must explicitly protect every other conclusion')
    if 'reference_guard' in plan:
        validate_reference_guard(plan, set(ids))
    return plan


def validate_reference_guard(plan: dict, protected_ids: set[int]) -> None:
    guard = plan['reference_guard']
    if not isinstance(guard, dict) or set(guard) != {'plan_path', 'target_artifacts'}:
        raise SafetyError('reference_guard needs exactly plan_path and target_artifacts')
    if plan.get('skipped_only') is True or plan.get('preserve_artifacts') is True:
        raise SafetyError('reference_guard is a separate policy from skipped_only and preserve_artifacts')
    if not isinstance(guard['plan_path'], str) or not PLAN_PATH_RE.fullmatch(guard['plan_path']):
        raise SafetyError('reference_guard plan_path must name the reviewed maintenance plan')
    artifacts = guard['target_artifacts']
    if not isinstance(artifacts, dict):
        raise SafetyError('reference_guard target_artifacts must map artifact IDs to target runs')
    targets = {run['id'] for run in plan['snapshot_runs']} - protected_ids
    for artifact, run in artifacts.items():
        if not isinstance(artifact, str) or not artifact.isdigit() or len(artifact) != 11:
            raise SafetyError('reference_guard artifact IDs must be 11-digit strings')
        if positive_id(run) not in targets:
            raise SafetyError('reference_guard maps an artifact to a run that is not a target')


def validate_execution_context(plan: dict, environment: dict, event: dict) -> str:
    required = {"GITHUB_ACTIONS": "true", "GITHUB_EVENT_NAME": "push",
                "GITHUB_REPOSITORY": REPOSITORY, "GITHUB_REF": "refs/heads/Claude"}
    for key, expected in required.items():
        if environment.get(key) != expected:
            raise SafetyError(f"Execution requires {key}={expected}")
    if environment.get("GITHUB_API_URL", "") not in ("", API_URL):
        raise SafetyError("Unexpected GITHUB_API_URL")
    sha = environment.get("GITHUB_SHA", "")
    if not SHA_RE.fullmatch(sha):
        raise SafetyError("Invalid executing SHA")
    if not environment.get("GITHUB_TOKEN"):
        raise SafetyError("Execution requires the workflow GITHUB_TOKEN")
    if not environment.get("GITHUB_RUN_ID", "").isdigit():
        raise SafetyError("Missing executing run ID")
    positive_id(int(environment["GITHUB_RUN_ID"]))
    if not isinstance(event, dict) or event.get("ref") != "refs/heads/Claude":
        raise SafetyError("Push event is not on Claude")
    if event.get("repository", {}).get("full_name") != REPOSITORY:
        raise SafetyError("Push event repository mismatch")
    if event.get("before") != plan["base_sha"] or event.get("after") != sha:
        raise SafetyError("Push parent/source SHA differs from the reviewed plan")
    if event.get("forced") or event.get("deleted") or event.get("created"):
        raise SafetyError("A forced, created, or deleted branch event cannot execute cleanup")
    if environment.get("GITHUB_WORKFLOW_SHA", sha) != sha:
        raise SafetyError("Workflow source SHA differs from the executing push")
    return sha


class NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None


class GitHubAPI:
    def __init__(self, token: str | None, *, sleep=time.sleep, clock=time.time,
                 monotonic=time.monotonic, opener=None, progress=print):
        self.token = token
        self.sleep = sleep
        self.clock = clock
        self.monotonic = monotonic
        self.opener = opener or urllib.request.build_opener(NoRedirects())
        self.progress = progress
        self.started = monotonic()
        self.waited = 0.0
        self.requests = 0
        self.remaining = None
        self.reset = None
        self.on_delete_resume = None
        self.wait_epoch = 0
        self.selection_epoch = 0

    def ensure_time(self) -> None:
        if self.monotonic() - self.started >= MAX_RUNTIME_SECONDS:
            raise SafetyError("Runtime bound reached; remaining snapshot targets were not deleted")

    def wait(self, seconds: float, reason: str) -> None:
        seconds = max(0.0, seconds)
        if self.waited + seconds > MAX_WAIT_SECONDS:
            raise SafetyError("Rate-limit wait would exceed the 150-minute bound")
        if self.monotonic() - self.started + seconds >= MAX_RUNTIME_SECONDS:
            raise SafetyError("Waiting would exceed the runtime bound")
        self.waited += seconds
        # A pause in a GET can make an earlier selection stale too. The next
        # DELETE must observe a complete listing obtained after this epoch.
        self.wait_epoch += 1
        self.progress(f"Cleanup pause: {reason}; {math.ceil(seconds)} seconds", flush=True)
        # Bounded heartbeats keep logs informative during a quota reset.
        while seconds > 0:
            part = min(seconds, 60.0)
            self.sleep(part)
            seconds -= part
            self.ensure_time()

    def _headers(self, headers) -> dict:
        values = {key.lower(): value for key, value in headers.items()}
        try:
            self.remaining = int(values["x-ratelimit-remaining"]) if "x-ratelimit-remaining" in values else None
            self.reset = float(values["x-ratelimit-reset"]) if "x-ratelimit-reset" in values else None
        except ValueError as exc:
            raise SafetyError("Malformed rate-limit response headers") from exc
        return values

    def _wait_for_request(self, method: str, path: str, seconds: float, reason: str) -> None:
        self.wait(seconds, reason)

    def _refresh_after_wait(self, path: str) -> None:
        if self.selection_epoch == self.wait_epoch:
            return
        if self.on_delete_resume is None:
            raise SafetyError("A DELETE after a quota pause requires a fresh listing")
        for _ in range(4):
            epoch = self.wait_epoch
            self.on_delete_resume(int(path.rsplit("/", 1)[1]))
            if epoch == self.wait_epoch:
                self.selection_epoch = epoch
                return
            # A GET inside the callback waited again. Do not clear the newer
            # invalidation: repeat the entire guarded listing after that wait.
        raise SafetyError("Repeated quota pauses prevented a stable fresh selection")

    def request(self, method: str, path: str) -> tuple[int, bytes]:
        allowed_get = (re.fullmatch(re.escape(PREFIX) + r"/actions/runs\?per_page=100&page=[1-9][0-9]*", path)
                       or re.fullmatch(re.escape(PREFIX) + r"/actions/runs/[1-9][0-9]*", path)
                       or re.fullmatch(re.escape(PREFIX) + r"/actions/runs/[1-9][0-9]*/artifacts\?per_page=100", path)
                       or re.fullmatch(re.escape(PREFIX) + r"/actions/runs/[1-9][0-9]*/jobs\?filter=all&per_page=100(?:&page=[1-9][0-9]*)?", path)
                       or re.fullmatch(re.escape(PREFIX) + r"/git/trees/[0-9a-f]{40}\?recursive=1", path)
                       or re.fullmatch(re.escape(PREFIX) + r"/git/blobs/[0-9a-f]{40}", path)
                       or path in (PREFIX + "/git/ref/heads/Claude", PREFIX + "/git/ref/heads/main"))
        allowed_delete = re.fullmatch(re.escape(PREFIX) + r"/actions/runs/[1-9][0-9]*", path)
        if not ((method == "GET" and allowed_get) or (method == "DELETE" and allowed_delete)):
            raise SafetyError("Request is outside the fixed cleanup API allowlist")
        retries = 0
        server_retries = 0
        while True:
            self.ensure_time()
            if self.remaining == 0 and self.reset is not None:
                delay = self.reset - self.clock() + 2
                if delay > 0:
                    self._wait_for_request(method, path, delay, "primary API quota reset")
            if method == "DELETE":
                self._refresh_after_wait(path)
            headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                       "User-Agent": "NeoStation-reviewed-actions-cleanup"}
            if self.token:
                headers["Authorization"] = "Bearer " + self.token
            request = urllib.request.Request(API_URL + path, headers=headers, method=method)
            self.requests += 1
            try:
                with self.opener.open(request, timeout=30) as response:
                    status, body = response.status, response.read()
                    values = self._headers(response.headers)
            except urllib.error.HTTPError as exc:
                status, body = exc.code, exc.read()
                values = self._headers(exc.headers)
            except (urllib.error.URLError, TimeoutError) as exc:
                # A transport failure could follow an accepted DELETE. Stop and
                # retain that uncertainty; a fresh bounded run may resume safely.
                raise SafetyError(f"Transport failed during {method}; operation outcome may be unknown") from exc
            rate_error = status in (403, 429) and (
                status == 429 or "retry-after" in values or self.remaining == 0
                or b"rate limit" in body.lower() or b"secondary rate" in body.lower())
            if rate_error:
                if retries >= 4:
                    raise SafetyError(f"HTTP {status}: bounded rate-limit retries exhausted")
                retry_after = values.get("retry-after")
                if retry_after is not None:
                    try:
                        delay = float(retry_after)
                    except ValueError:
                        try:
                            delay = parsedate_to_datetime(retry_after).timestamp() - self.clock()
                        except (TypeError, ValueError) as exc:
                            raise SafetyError("Invalid Retry-After response header") from exc
                    delay = max(delay, 1.0)
                elif self.remaining == 0 and self.reset is not None:
                    delay = max(1.0, self.reset - self.clock() + 2)
                else:
                    delay = 60.0 * (2 ** retries)
                retries += 1
                self._wait_for_request(method, path, delay, f"HTTP {status} rate limit, retry {retries}/4")
                continue
            if status in SERVER_ERRORS and server_retries < SERVER_RETRIES:
                server_retries += 1
                self.progress(f"GitHub HTTP {status} on {method}; retry {server_retries}/{SERVER_RETRIES}", flush=True)
                self.ensure_time()
                self.sleep(SERVER_RETRY_SECONDS * server_retries)
                self.ensure_time()
                continue
            return status, body

    def get_json(self, path: str) -> dict:
        status, body = self.request("GET", path)
        if status != 200:
            raise SafetyError(f"GET failed with HTTP {status}")
        try:
            result = json.loads(body)
        except (UnicodeError, ValueError) as exc:
            raise SafetyError("API returned invalid JSON") from exc
        if not isinstance(result, dict):
            raise SafetyError("API response is not an object")
        return result

    def delete_run(self, run_id: int) -> int:
        positive_id(run_id)
        status, _ = self.request("DELETE", PREFIX + f"/actions/runs/{run_id}")
        if status not in (204, 404, 409) and status not in SERVER_ERRORS:
            raise SafetyError(f"DELETE run {run_id} failed with HTTP {status}")
        return status

    def pace(self) -> None:
        self.ensure_time()
        self.sleep(1.0)

    def settle(self, seconds: float) -> None:
        """A pause before a moved listing is read again (not a quota wait)."""
        self.ensure_time()
        self.sleep(seconds)
        self.ensure_time()


def list_all_runs(api) -> list[dict]:
    """Unfiltered complete pagination, never interleaved with our deletions.

    A listing that moved while its pages were read is discarded and read again in
    full; only a complete and stable listing is ever used for a selection.
    """
    for attempt in range(1, LISTING_ATTEMPTS + 1):
        try:
            return list_all_runs_once(api)
        except ListingMoved:
            if attempt == LISTING_ATTEMPTS:
                raise
            settle = getattr(api, "settle", None)
            if settle is not None:
                settle(LISTING_SETTLE_SECONDS * attempt)
    raise SafetyError("Unreachable listing state")


def list_all_runs_once(api) -> list[dict]:
    first = api.get_json(PREFIX + "/actions/runs?per_page=100&page=1")
    total = first.get("total_count")
    if type(total) is not int or total < 0:
        raise SafetyError("Invalid total_count")
    runs = []
    for page in range(1, max(1, (total + 99) // 100) + 1):
        response = first if page == 1 else api.get_json(PREFIX + f"/actions/runs?per_page=100&page={page}")
        if response.get("total_count") != total:
            raise ListingMoved("Run count changed during pagination; refusing cleanup")
        part = response.get("workflow_runs")
        if not isinstance(part, list) or len(part) != min(100, max(0, total - len(runs))):
            raise ListingMoved("Incomplete or shifted pagination")
        runs.extend(validate_run(item) for item in part)
    if len(runs) != total:
        raise ListingMoved("Unique enumeration does not match total_count")
    # Across GitHub workers, timestamps may invert while IDs stay stable.
    # Detect shifted/duplicate pages, then sort the complete set locally.
    if len({run['id'] for run in runs}) != len(runs):
        raise ListingMoved('Duplicate run IDs: pagination moved; refusing cleanup')
    # Detect insertion/deletion at the first-page boundary while later pages
    # were read. There is no API transaction spanning this listing and DELETE.
    check = api.get_json(PREFIX + "/actions/runs?per_page=100&page=1")
    if check.get("total_count") != total or [r.get("id") for r in check.get("workflow_runs", [])] != [r["id"] for r in runs[:100]]:
        raise ListingMoved("First page moved during pagination; refusing cleanup")
    return sorted(runs, key=run_key, reverse=True)


def check_refs(api, expected_claude_sha: str, main_sha: str, *, allow_claude_advance=False) -> None:
    for branch, expected in (("Claude", expected_claude_sha), ("main", main_sha)):
        response = api.get_json(PREFIX + "/git/ref/heads/" + branch)
        if branch == 'Claude' and allow_claude_advance:
            # The immutable skipped-only plan never targets any executed job.
            # Product pushes may continue while these fixed old IDs are cleaned.
            continue
        if response.get("object", {}).get("sha") != expected:
            raise SafetyError(f"{branch} SHA changed; no further deletion is authorized")


class ReferenceGuard:
    """Claude may advance during a long cleanup; a target a later commit newly cites is kept.

    The files of the executing commit are the reviewed baseline: the plan was computed
    against them. At each check every blob of the current Claude tree that differs
    from that baseline is read in full; an 11-digit number naming a remaining target
    run, or one of its artifacts, that the baseline version of the same path did not
    hold protects that run. An incomplete tree, an unreadable blob or a changed or
    removed plan stops the cleanup.
    """

    def __init__(self, api, plan: dict, executing_sha: str):
        self.api = api
        self.plan_path = plan["reference_guard"]["plan_path"]
        protected = {item["id"] for item in plan["protected_runs"]}
        self.watch = {run["id"]: run["id"] for run in plan["snapshot_runs"] if run["id"] not in protected}
        for artifact, run in plan["reference_guard"]["target_artifacts"].items():
            self.watch[int(artifact)] = run
        self.baseline = self.tree(executing_sha)
        if self.plan_path not in self.baseline:
            raise SafetyError("The executing commit does not contain the reviewed plan")
        self.checked = executing_sha
        self.blobs: dict[str, set[int]] = {}
        self.referenced: set[int] = set()

    def cited(self, blob: str) -> set[int]:
        if blob not in self.blobs:
            self.blobs[blob] = self.scan(blob)
        return self.blobs[blob]

    def tree(self, sha: str) -> dict[str, str]:
        if not SHA_RE.fullmatch(sha or ""):
            raise SafetyError("Invalid commit SHA for the reference guard")
        response = self.api.get_json(PREFIX + f"/git/trees/{sha}?recursive=1")
        entries = response.get("tree")
        if response.get("truncated") is not False or not isinstance(entries, list):
            raise SafetyError("Incomplete Claude tree; later references cannot be excluded")
        result = {}
        for entry in entries:
            if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
                raise SafetyError("Malformed Claude tree entry")
            if entry.get("type") == "blob":
                if not SHA_RE.fullmatch(entry.get("sha") or ""):
                    raise SafetyError("Malformed Claude blob entry")
                result[entry["path"]] = entry["sha"]
        return result

    def scan(self, blob: str) -> set[int]:
        response = self.api.get_json(PREFIX + f"/git/blobs/{blob}")
        if response.get("sha") != blob or response.get("encoding") != "base64" or not isinstance(response.get("content"), str):
            raise SafetyError("Unreadable Claude blob; later references cannot be excluded")
        try:
            data = base64.b64decode(response["content"], validate=False)
        except (ValueError, TypeError) as exc:
            raise SafetyError("Undecodable Claude blob") from exc
        if type(response.get("size")) is not int or len(data) != response["size"]:
            raise SafetyError("Truncated Claude blob; later references cannot be excluded")
        return {self.watch[int(found)] for found in ID_RE.findall(data) if int(found) in self.watch}

    def check(self, head: str) -> set[int]:
        """Runs newly cited by Claude at `head`, relative to the executing commit."""
        if head == self.checked:
            return set()
        current = self.tree(head)
        if current.get(self.plan_path) != self.baseline[self.plan_path]:
            raise SafetyError("The reviewed plan changed or disappeared on Claude; no further deletion is authorized")
        found: set[int] = set()
        for path, blob in current.items():
            before = self.baseline.get(path)
            if before == blob:
                continue
            cited = self.cited(blob)
            if cited and before is not None:
                # Citations the reviewed version of this file already held were judged by the plan.
                cited = cited - self.cited(before)
            found |= cited
        self.checked = head
        new = found - self.referenced
        self.referenced |= found
        return new


def check_refs_guarded(api, guard: ReferenceGuard, main_sha: str, sticky: dict[int, set[str]], journal) -> None:
    claude = api.get_json(PREFIX + "/git/ref/heads/Claude").get("object", {}).get("sha")
    if not SHA_RE.fullmatch(claude or ""):
        raise SafetyError("Invalid Claude SHA")
    if api.get_json(PREFIX + "/git/ref/heads/main").get("object", {}).get("sha") != main_sha:
        raise SafetyError("main SHA changed; no further deletion is authorized")
    for run_id in sorted(guard.check(claude)):
        sticky.setdefault(run_id, set()).add("referenced_after_plan")
        journal.event("protected_new_reference", run_id=run_id, claude_sha=claude)


def refresh_selection(plan: dict, current: list[dict], sticky: dict[int, set[str]],
                      observations: dict[int, dict], executing_run: int | None) -> list[dict]:
    snapshot = {r["id"]: r for r in plan["snapshot_runs"]}
    for item in plan["protected_runs"]:
        sticky.setdefault(item["id"], set()).add("explicit_dependency")
    for run in plan["snapshot_runs"]:
        if run["status"] != "completed":
            sticky.setdefault(run["id"], set()).add("active_in_snapshot")
    if executing_run is not None:
        sticky.setdefault(executing_run, set()).add("executing_cleanup_run")
    keep = plan["keep_recent"]
    for run in current[:keep]:
        sticky.setdefault(run["id"], set()).add(f"current_recent_{keep}")
    candidates = []
    for run in current:
        rid = run["id"]
        prior = snapshot.get(rid)
        if prior is None:
            sticky.setdefault(rid, set()).add("not_in_reviewed_snapshot")
            continue
        if plan.get('preserve_artifacts') is True and not same_completed_run(run, prior):
            sticky.setdefault(rid, set()).add('changed_or_incomplete_since_snapshot')
            continue
        if any(run[field] != prior[field] for field in ("created_at", "head_sha", "path")):
            raise SafetyError(f"Snapshot identity changed for run {rid}")
        if run["status"] != "completed":
            sticky.setdefault(rid, set()).add("currently_active")
        if plan.get('skipped_only') is True and run.get('conclusion') != 'skipped':
            sticky.setdefault(rid, set()).add('not_skipped_currently')
        observed = observations.get(rid, prior)
        if "run_attempt" in observed and run.get("run_attempt") != observed["run_attempt"]:
            sticky.setdefault(rid, set()).add("rerun_since_snapshot_or_observation")
        if "updated_at" in observed and run.get("updated_at") != observed["updated_at"]:
            sticky.setdefault(rid, set()).add("updated_since_snapshot_or_observation")
        observations.setdefault(rid, dict(run))
        if rid not in sticky and run["status"] == "completed":
            candidates.append(run)
    # The oldest eligible runs go first; keep sets remain sticky for this run.
    return sorted(candidates, key=run_key)


def has_execution_or_artifact(api, run_id: int) -> bool:
    """Keep a nominally skipped run if any attempt has executed or stored data."""
    artifacts = api.get_json(PREFIX + f'/actions/runs/{run_id}/artifacts?per_page=100')
    if artifacts.get('total_count') != 0 or artifacts.get('artifacts') != []:
        return True
    jobs = api.get_json(PREFIX + f'/actions/runs/{run_id}/jobs?filter=all&per_page=100')
    rows = jobs.get('jobs')
    if not isinstance(rows, list) or jobs.get('total_count') != len(rows) or len(rows) >= 100:
        return True
    return any(job.get('status') != 'completed' or job.get('conclusion') != 'skipped'
               or job.get('steps') not in (None, []) for job in rows)


def same_completed_run(live: object, snapshot: dict) -> bool:
    """Exact immutable selection identity, including fields absent in older plans."""
    try:
        validate_run(live)
    except (SafetyError, KeyError, TypeError, ValueError):
        return False
    return (live['status'] == 'completed'
            and isinstance(live.get('conclusion'), str) and live['conclusion'] in COMPLETED_CONCLUSIONS
            and all(field in live and field in snapshot and live[field] == snapshot[field]
                    for field in RUN_IDENTITY_FIELDS))


def has_artifact_or_active_job(api, run_id: int) -> bool:
    """Only a proven empty artifact list and complete, completed job history qualify.

    filter=all includes earlier attempts. Any artifact metadata, including expired
    artifacts, is preserved. Unknown or moving pagination is preservation evidence.
    HTTP/JSON failures stop execution through the existing API boundary.
    """
    artifacts = api.get_json(PREFIX + f'/actions/runs/{run_id}/artifacts?per_page=100')
    if (not isinstance(artifacts, dict) or type(artifacts.get('total_count')) is not int
            or artifacts['total_count'] != 0 or artifacts.get('artifacts') != []):
        return True
    path = PREFIX + f'/actions/runs/{run_id}/jobs?filter=all&per_page=100'
    first = api.get_json(path + '&page=1')
    if not isinstance(first, dict) or type(first.get('total_count')) is not int:
        return True
    total = first['total_count']
    # Bound unusual histories; preserving uncertainty is safer than unbounded reads.
    if not 0 <= total <= 1000:
        return True
    seen = set()
    for page in range(1, max(1, (total + 99) // 100) + 1):
        response = first if page == 1 else api.get_json(path + f'&page={page}')
        if not isinstance(response, dict) or type(response.get('total_count')) is not int:
            return True
        rows = response.get('jobs')
        if (response['total_count'] != total or not isinstance(rows, list)
                or len(rows) != min(100, max(0, total - len(seen)))):
            return True
        for job in rows:
            if (not isinstance(job, dict) or type(job.get('id')) is not int or job['id'] <= 0
                    or job['id'] in seen or type(job.get('run_id')) is not int or job['run_id'] != run_id
                    or job.get('status') != 'completed' or not isinstance(job.get('conclusion'), str)
                    or job['conclusion'] not in COMPLETED_CONCLUSIONS):
                return True
            seen.add(job['id'])
    if total > 100:
        check = api.get_json(path + '&page=1')
        if check != first:
            return True
    return len(seen) != total


def artifact_preserving_target(api, snapshot: dict) -> bool:
    """Recheck individual identity around evidence reads, including after quota waits."""
    path = PREFIX + f"/actions/runs/{snapshot['id']}"
    if not same_completed_run(api.get_json(path), snapshot):
        return False
    if has_artifact_or_active_job(api, snapshot['id']):
        return False
    return same_completed_run(api.get_json(path), snapshot)


class Journal:
    def __init__(self, output: Path, plan_sha256: str = "", execute: bool = False):
        self.output = output
        output.mkdir(parents=True, exist_ok=True)
        self.state = {"schema_version": 1, "repository": REPOSITORY,
                      "plan_sha256": plan_sha256, "execute": execute,
                      "started_at": iso_now(), "status": "starting",
                      "deleted_run_ids": [], "already_absent_run_ids": [],
                      "conflict_run_ids": [], "server_error_run_ids": [], "delete_attempts": 0}
        self.save()

    def write_json(self, name: str, value: object) -> None:
        destination = self.output / name
        temporary = destination.with_suffix(destination.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(destination)

    def save(self) -> None:
        self.state["updated_at"] = iso_now()
        self.write_json("receipt.json", self.state)

    def event(self, event: str, **values) -> None:
        record = {"at": iso_now(), "event": event, **values}
        with (self.output / "progress.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.save()

    def summary(self) -> None:
        s = self.state
        lines = ["# GitHub Actions history cleanup", "",
                 f"- Repository: `{REPOSITORY}`", f"- Mode: {'execute' if s['execute'] else 'dry run'}",
                 f"- State: **{s['status']}**", f"- Plan SHA-256: `{s['plan_sha256']}`",
                 f"- DELETE attempts: {s['delete_attempts']}",
                 f"- Deleted (HTTP 204): {len(s['deleted_run_ids'])}",
                 f"- Already absent (HTTP 404): {len(s['already_absent_run_ids'])}",
                 f"- Preserved after conflict (HTTP 409): {len(s['conflict_run_ids'])}",
                 f"- Preserved after repeated server errors (HTTP 5xx): {len(s.get('server_error_run_ids', []))}"]
        for name in ("initial_total", "final_total", "initial_candidate_count", "remaining_candidate_count", "error"):
            if name in s:
                lines.append(f"- {name}: {s[name]}")
        lines += ["", f"Only reviewed snapshot IDs were eligible. The newest {s.get('keep_recent', KEEP_RECENT)} in each current",
                  "listing, explicit dependencies, new IDs and active/changed runs",
                  "were protected. A concurrent change after a listing is not an API transaction.", ""]
        (self.output / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def run_cleanup(api, plan: dict, journal: Journal, *, execute: bool = False,
                environment: dict | None = None, event: dict | None = None) -> dict:
    environment = environment if environment is not None else dict(os.environ)
    validate_plan(plan)
    expected_sha = validate_execution_context(plan, environment, event or {}) if execute else None
    executing_run = int(environment["GITHUB_RUN_ID"]) if environment.get("GITHUB_RUN_ID", "").isdigit() else None
    sticky: dict[int, set[str]] = {}
    observations: dict[int, dict] = {}
    journal.state["keep_recent"] = plan["keep_recent"]
    guard = ReferenceGuard(api, plan, expected_sha) if execute and "reference_guard" in plan else None

    def refs() -> None:
        if guard is not None:
            check_refs_guarded(api, guard, plan["main_sha"], sticky, journal)
        else:
            check_refs(api, expected_sha, plan["main_sha"], allow_claude_advance=plan.get("skipped_only") is True)

    if execute:
        refs()
    current = list_all_runs(api)
    candidates = refresh_selection(plan, current, sticky, observations, executing_run)
    if len(candidates) > plan["max_deletions"]:
        raise SafetyError("Candidate count exceeds the reviewed maximum; refusing all deletions")
    journal.state.update(status="running" if execute else "dry-run", initial_total=len(current),
                         initial_candidate_count=len(candidates), remaining_candidate_count=len(candidates),
                         max_deletions=plan["max_deletions"], executing_sha=expected_sha,
                         executing_run_id=executing_run)
    journal.write_json("dry-run.json", {"plan_sha256": journal.state["plan_sha256"],
                       "candidate_runs": candidates,
                       "protected_runs": [{"id": rid, "reasons": sorted(reasons)} for rid, reasons in sorted(sticky.items())],
                       "current_total": len(current), "snapshot_total": len(plan["snapshot_runs"])})
    journal.event("enumerated", total=len(current), candidates=len(candidates), execute=execute)
    if not execute:
        journal.state["final_total"] = len(current)
        journal.save()
        journal.summary()
        return journal.state

    def revalidate_after_quota_pause(run_id: int) -> None:
        validate_plan(plan)
        refs()
        fresh = list_all_runs(api)
        eligible = refresh_selection(plan, fresh, sticky, observations, executing_run)
        journal.event("quota_resume_revalidated", total=len(fresh), candidate_count=len(eligible))
        if run_id not in {run["id"] for run in eligible}:
            raise SafetyError(f"Run {run_id} is no longer eligible after the quota pause")
        if plan.get('preserve_artifacts') is True:
            snapshot = next(run for run in plan['snapshot_runs'] if run['id'] == run_id)
            if not artifact_preserving_target(api, snapshot):
                sticky.setdefault(run_id, set()).add('evidence_or_change_after_quota_pause')
                raise SafetyError(f'Run {run_id} has changed or has preservation evidence after the quota pause')

    if isinstance(api, GitHubAPI):
        api.on_delete_resume = revalidate_after_quota_pause

    attempted: set[int] = set()
    while candidates:
        # Every chunk comes from a complete validated listing. No offset-based
        # listing occurs while deleting that chunk.
        chunk = [run for run in candidates if run["id"] not in attempted][:REFRESH_EVERY]
        if not chunk:
            break
        for run in chunk:
            validate_plan(plan)
            if journal.state["delete_attempts"] >= plan["max_deletions"]:
                raise SafetyError("Deletion attempt bound reached")
            if journal.state["delete_attempts"] % CHECK_REFS_EVERY == 0:
                refs()
            rid = run["id"]
            if "referenced_after_plan" in sticky.get(rid, ()):
                # A commit pushed after the plan cites this run: it stays.
                journal.event("preserved_new_reference", run_id=rid)
                continue
            # Defense in depth: never let a changed selection produce a new ID.
            if rid in sticky or rid not in {r["id"] for r in plan["snapshot_runs"]} or run["status"] != "completed":
                raise SafetyError("Deletion target failed the final snapshot membership guard")
            if plan.get('skipped_only') is True:
                live = api.get_json(PREFIX + f'/actions/runs/{rid}')
                fields = ('id', 'created_at', 'head_sha', 'path', 'status', 'conclusion', 'run_attempt', 'updated_at')
                if live.get('conclusion') != 'skipped' or any(live.get(k) != run.get(k) for k in fields):
                    sticky.setdefault(rid, set()).add('changed_at_individual_pre_delete_check')
                    journal.event('preserved_changed_run', run_id=rid)
                    continue
                if has_execution_or_artifact(api, rid):
                    sticky.setdefault(rid, set()).add('execution_or_artifact_evidence')
                    journal.event('preserved_evidence', run_id=rid)
                    continue
            elif plan.get('preserve_artifacts') is True:
                snapshot = next(item for item in plan['snapshot_runs'] if item['id'] == rid)
                if not artifact_preserving_target(api, snapshot):
                    sticky.setdefault(rid, set()).add('artifact_active_job_or_changed_run')
                    journal.event('preserved_evidence_or_changed_run', run_id=rid)
                    continue
            journal.state["delete_attempts"] += 1
            attempted.add(rid)
            journal.event("delete_requested", run_id=rid, head_sha=run["head_sha"], created_at=run["created_at"])
            status = api.delete_run(rid)
            if status == 204:
                journal.state["deleted_run_ids"].append(rid)
            elif status == 404:
                journal.state["already_absent_run_ids"].append(rid)
            elif status == 409:
                journal.state["conflict_run_ids"].append(rid)
                sticky.setdefault(rid, set()).add("delete_conflict")
            elif status in SERVER_ERRORS:
                # Still listed after the bounded retries: kept, never reported as deleted.
                journal.state["server_error_run_ids"].append(rid)
                sticky.setdefault(rid, set()).add("delete_server_error")
                if len(journal.state["server_error_run_ids"]) > MAX_SERVER_ERROR_RUNS:
                    journal.event("delete_result", run_id=rid, http_status=status)
                    raise SafetyError("Repeated GitHub server errors on DELETE; no further deletion is attempted")
            else:
                raise SafetyError("Unexpected DELETE response")
            journal.event("delete_result", run_id=rid, http_status=status)
            if journal.state["delete_attempts"] % 25 == 0:
                print(f"Cleanup progress: {journal.state['delete_attempts']} attempts; "
                      f"{len(journal.state['deleted_run_ids'])} deleted; "
                      f"{len(journal.state['conflict_run_ids'])} conflicts retained", flush=True)
            api.pace()
        refs()
        current = list_all_runs(api)
        candidates = refresh_selection(plan, current, sticky, observations, executing_run)
        journal.state["remaining_candidate_count"] = len([r for r in candidates if r["id"] not in attempted])
        journal.state["final_total"] = len(current)
        journal.event("refreshed", total=len(current), remaining=journal.state["remaining_candidate_count"])
    refs()
    # Even an empty initial candidate list gets a final independent enumeration.
    current = list_all_runs(api)
    candidates = refresh_selection(plan, current, sticky, observations, executing_run)
    journal.write_json("remaining-runs.json", current)
    absent = set(journal.state["deleted_run_ids"]) | set(journal.state["already_absent_run_ids"])
    if absent.intersection(r["id"] for r in current):
        raise SafetyError("A run reported deleted or absent is still listed; inspect the receipt")
    journal.state.update(status="completed", final_total=len(current),
                         remaining_candidate_count=len([r for r in candidates if r["id"] not in attempted]),
                         protected_run_ids=sorted(sticky), finished_at=iso_now())
    journal.event("completed", total=len(current))
    journal.summary()
    return journal.state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("cleanup-output"))
    args = parser.parse_args(argv)
    journal = Journal(args.output, execute=args.execute)
    api = None
    try:
        raw = args.plan.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        journal.state["plan_sha256"] = digest
        if args.expected_plan_sha256 is not None and digest != args.expected_plan_sha256:
            raise SafetyError("Plan SHA-256 does not match the reviewed bytes")
        plan = validate_plan(json.loads(raw))
        if os.environ.get("GITHUB_API_URL", "") not in ("", API_URL):
            raise SafetyError("Unexpected GITHUB_API_URL")
        event = {}
        if args.execute:
            event_path = os.environ.get("GITHUB_EVENT_PATH")
            if not event_path:
                raise SafetyError("Execution requires GITHUB_EVENT_PATH")
            event = json.loads(Path(event_path).read_text(encoding="utf-8"))
            validate_execution_context(plan, dict(os.environ), event)
        api = GitHubAPI(os.environ.get("GITHUB_TOKEN"))
        run_cleanup(api, plan, journal, execute=args.execute, event=event)
        return 0
    except (SafetyError, OSError, ValueError, TypeError, KeyError, KeyboardInterrupt) as exc:
        journal.state.update(status="interrupted" if isinstance(exc, KeyboardInterrupt) else "stopped",
                             error=str(exc) or type(exc).__name__, finished_at=iso_now())
        journal.event("stopped", error=journal.state["error"])
        print("Cleanup stopped: " + journal.state["error"], file=sys.stderr, flush=True)
        return 130 if isinstance(exc, KeyboardInterrupt) else 1
    finally:
        if api is not None:
            journal.state.update(api_requests=api.requests, rate_limit_wait_seconds=api.waited)
        journal.save()
        journal.summary()


if __name__ == "__main__":
    sys.exit(main())

