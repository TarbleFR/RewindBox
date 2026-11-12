#!/usr/bin/env python3
"""One reviewed cleanup: merged branches and four obsolete delivery launchers.

Never removes workflow source, artifacts, successful/failed runs or tags. Branch
deletion uses a Git lease, so an advance after the API checks cannot be lost.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request

REPO = "TarbleFR/RewindBox"
PREFIX = "/repos/" + REPO
ALLOWED_WORKFLOWS = {
    ".github/workflows/rewind608-retro-achievements-delivery.yml",
    ".github/workflows/rewind609-hogwarts-liveness-delivery.yml",
    ".github/workflows/rewind610-delivery.yml",
    ".github/workflows/hogwarts606-host-recovery.yml",
}
ACTIVE = ("queued", "in_progress", "waiting", "pending", "requested")
SHA = re.compile(r"[0-9a-f]{40}\Z")


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def validate_plan(plan, now=None):
    require(plan.get("repository") == REPO and plan.get("version") == 1, "Wrong plan target")
    require(SHA.fullmatch(plan.get("base_sha", "")), "Missing reviewed integration base")
    require(SHA.fullmatch(plan.get("main_sha", "")), "Missing protected main identity")
    expiry = datetime.fromisoformat(plan["expires_at"].replace("Z", "+00:00"))
    require(expiry > (now or datetime.now(timezone.utc)), "Plan expired")
    require(0 < len(plan["branches"]) <= 7, "Branch deletion bound exceeded")
    names = []
    for branch in plan["branches"]:
        name = branch["branch"]
        require(re.fullmatch(r"work/[a-zA-Z0-9][a-zA-Z0-9._/-]*", name) and
                ".." not in name and not name.endswith(".lock") and "backup" not in name.lower(), "Protected or invalid branch")
        require(SHA.fullmatch(branch["sha"]), "Invalid branch source")
        names.append(name)
    require(len(set(names)) == len(names), "Duplicate branch")
    paths = [w["path"] for w in plan["workflows"]]
    require(len(paths) == len(set(paths)) <= 4 and set(paths) <= ALLOWED_WORKFLOWS, "Unreviewed workflow")
    require(all(type(w["id"]) is int and w["id"] > 0 for w in plan["workflows"]), "Invalid workflow ID")


class API:
    def __init__(self, token):
        self.token = token

    def request(self, path, method="GET"):
        require(path.startswith(PREFIX + "/"), "Unexpected API target")
        if method != "GET":
            require(method == "PUT" and re.fullmatch(re.escape(PREFIX) + r"/actions/workflows/[0-9]+/disable", path), "Unexpected mutation")
        request = urllib.request.Request("https://api.github.com" + path, method=method,
            headers={"Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
                     "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read()
            return json.loads(data) if data else None

    def delete_branch(self, name, expected):
        # Atomic compare-and-delete, not a history rewrite. Do not print credentials.
        environment = os.environ.copy()
        environment.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_COUNT="1",
            GIT_CONFIG_KEY_0="http.https://github.com/.extraheader",
            GIT_CONFIG_VALUE_0="AUTHORIZATION: basic " + base64.b64encode(("x-access-token:" + self.token).encode()).decode())
        result = subprocess.run(["git", "push", "--porcelain",
            f"--force-with-lease=refs/heads/{name}:{expected}", "https://github.com/" + REPO + ".git",
            f":refs/heads/{name}"], env=environment, capture_output=True, text=True)
        require(result.returncode == 0, "Branch delete refused (lease or permissions): " + name)


def listing(api, path, key=None):
    values = []
    separator = "&" if "?" in path else "?"
    for page in range(1, 101):
        result = api.request(path + f"{separator}per_page=100&page={page}")
        batch = result[key] if key else result
        values.extend(batch)
        if len(batch) < 100:
            return values
    raise RuntimeError("Incomplete inventory")


def live(api):
    runs = {}
    for state in ACTIVE:
        for run in listing(api, PREFIX + "/actions/runs?status=" + state, "workflow_runs"):
            runs[run["id"]] = run
    return list(runs.values())


def check_base(api, plan):
    main = api.request(PREFIX + "/branches/main")
    require(main["commit"]["sha"] == plan["main_sha"], "main changed: refresh the plan")
    current = api.request(PREFIX + "/branches/Claude")["commit"]["sha"]
    comparison = api.request(PREFIX + "/compare/" + plan["base_sha"] + "..." + current)
    require(comparison["merge_base_commit"]["sha"] == plan["base_sha"], "Integration history no longer contains the reviewed base")
    return current


def check_branch(api, branch, current):
    name, expected = branch["branch"], branch["sha"]
    value = api.request(PREFIX + "/branches/" + urllib.parse.quote(name, safe=""))
    require(not value.get("protected") and value["commit"]["sha"] == expected, "Branch changed/protected: " + name)
    comparison = api.request(PREFIX + "/compare/" + expected + "..." + current)
    require(comparison["merge_base_commit"]["sha"] == expected, "Unmerged work: " + name)
    pulls = listing(api, PREFIX + "/pulls?state=open")
    require(not any(p["head"]["ref"] == name or p["base"]["ref"] == name for p in pulls), "Open PR uses branch: " + name)
    require(not any(r["head_branch"] == name for r in live(api)), "Active run uses branch: " + name)


def run(api, plan, receipt, execute=False):
    validate_plan(plan)
    current = check_base(api, plan)
    for branch in plan["branches"]:
        check_branch(api, branch, current)
        if execute:
            api.delete_branch(branch["branch"], branch["sha"])
        receipt["operations"].append({"kind": "branch", **branch, "result": "deleted" if execute else "eligible"})
    for workflow in plan["workflows"]:
        value = api.request(PREFIX + "/actions/workflows/" + str(workflow["id"]))
        require(value["path"] == workflow["path"], "Workflow identity changed")
        require(not any(r["path"] == workflow["path"] for r in live(api)), "Workflow has an active run")
        if execute:
            api.request(PREFIX + f'/actions/workflows/{workflow["id"]}/disable', "PUT")
            after = api.request(PREFIX + "/actions/workflows/" + str(workflow["id"]))
            require(after["state"] == "disabled_manually", "Workflow disable not confirmed")
        receipt["operations"].append({"kind": "workflow", **workflow, "result": "disabled" if execute else "eligible"})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    raw = args.plan.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == args.expected_plan_sha256, "Plan bytes changed")
    plan = json.loads(raw)
    if args.execute:
        require(os.environ.get("GITHUB_REPOSITORY") == REPO and os.environ.get("GITHUB_REF") == "refs/heads/Claude"
                and os.environ.get("GITHUB_EVENT_NAME") == "push", "Execution requires the authorized integration push")
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        require(event["before"] == plan["base_sha"] and event["after"] == os.environ["GITHUB_SHA"]
                and not any(event.get(x) for x in ("forced", "deleted", "created")), "Unexpected push boundary")
    receipt = {"planSHA256": hashlib.sha256(raw).hexdigest(), "operations": [], "result": "in_progress"}
    path = Path("cleanup-output/repository-tidy.json")
    path.parent.mkdir(exist_ok=True)
    try:
        run(API(os.environ["GITHUB_TOKEN"]), plan, receipt, args.execute)
        receipt["result"] = "completed" if args.execute else "dry_run"
    except Exception as error:
        receipt["result"] = "stopped"
        receipt["error"] = str(error)
        raise
    finally:
        path.write_text(json.dumps(receipt, indent=2) + "\n")


if __name__ == "__main__":
    main()
