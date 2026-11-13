#!/usr/bin/env python3
"""Retire only reviewed, never-executed obsolete queued runs and four launchers."""
import argparse
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import time
import urllib.error
import urllib.request
from tidy_repository import API as BaseAPI, PREFIX, REPO, SHA, ALLOWED_WORKFLOWS, require, live


class API(BaseAPI):
    def request(self, path, method="GET"):
        if method != "POST":
            return super().request(path, method)
        require(re.fullmatch(re.escape(PREFIX) + r"/actions/runs/[0-9]+/(cancel|force-cancel)", path), "Unexpected cancellation")
        request = urllib.request.Request("https://api.github.com" + path, method="POST", headers={
            "Authorization": "Bearer " + self.token, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read()
            return json.loads(raw) if raw else None


def eligible(api, entry):
    path = PREFIX + f'/actions/runs/{entry["id"]}'
    run = api.request(path)
    require(run["head_sha"] == entry["sha"] and run["path"] == entry["path"] and
            run["created_at"] == entry["created_at"] and run["run_attempt"] == 1, "Run identity changed")
    if run["status"] == "completed":
        return False
    require(run["status"] in ("queued", "waiting", "pending", "requested"), "A run started: preserve it")
    created = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
    require(datetime.now(timezone.utc) - created > timedelta(hours=24), "Not an old pending run")
    artifacts = api.request(path + "/artifacts?per_page=100")
    jobs = api.request(path + "/jobs?filter=all&per_page=100")
    require(artifacts.get("total_count") == 0 and artifacts.get("artifacts") == [], "Artifact exists: preserve")
    rows = jobs.get("jobs")
    require(isinstance(rows, list) and jobs.get("total_count") == len(rows) and len(rows) < 100,
            "Incomplete job inventory")
    require(all(j.get("status") in ("queued", "waiting", "pending", "requested", "completed") and
                j.get("conclusion") in (None, "skipped") and not j.get("steps") for j in rows),
            "Job execution exists: preserve")
    final = api.request(path)
    if final["status"] == "completed":
        return False
    require(all(final.get(k) == run.get(k) for k in
                ("id", "head_sha", "path", "created_at", "run_attempt", "status")),
            "Run changed during inventory: preserve")
    return True


def cancel(api, entry, sleep=time.sleep):
    if not eligible(api, entry):
        return "already_completed"
    path = PREFIX + f'/actions/runs/{entry["id"]}'
    for operation in ("cancel", "force-cancel"):
        if not eligible(api, entry):
            return "completed"
        try:
            api.request(path + "/" + operation, "POST")
        except urllib.error.HTTPError as error:
            if error.code != 409:
                raise
        for _ in range(12):
            run = api.request(path)
            if run["status"] == "completed":
                return "cancelled" if run["conclusion"] == "cancelled" else "completed"
            sleep(5)
    raise RuntimeError("Cancellation not confirmed; preserve and inspect run " + str(entry["id"]))


def validate(plan):
    require(plan.get("version") == 1 and plan.get("repository") == REPO, "Wrong plan")
    require(SHA.fullmatch(plan.get("base_sha", "")), "Bad base")
    require(datetime.fromisoformat(plan["expires_at"].replace("Z", "+00:00")) > datetime.now(timezone.utc), "Expired")
    require(len(plan["runs"]) <= 9 and len({x["id"] for x in plan["runs"]}) == len(plan["runs"]), "Run bound")
    allowed = ALLOWED_WORKFLOWS | {".github/workflows/standard-delivery.yml", ".github/workflows/xenia-core.yml",
        ".github/workflows/s2arm-core.yml", ".github/workflows/s2arm-engine.yml", ".github/workflows/s2arm-delivery.yml"}
    require(all(type(x["id"]) is int and x["id"] > 0 and SHA.fullmatch(x["sha"]) and x["path"] in allowed for x in plan["runs"]), "Unexpected run")
    require(len(plan["workflows"]) <= 4 and all(x["path"] in ALLOWED_WORKFLOWS and type(x["id"]) is int for x in plan["workflows"]), "Unexpected workflow")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(); raw = args.plan.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == args.expected_plan_sha256, "Plan bytes changed")
    plan = json.loads(raw); validate(plan)
    if args.execute:
        require(os.environ.get("GITHUB_ACTIONS") == "true" and os.environ.get("GITHUB_EVENT_NAME") == "push" and
                os.environ.get("GITHUB_REPOSITORY") == REPO and os.environ.get("GITHUB_REF") == "refs/heads/Claude", "Wrong execution")
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        require(event["before"] == plan["base_sha"] and event["after"] == os.environ["GITHUB_SHA"] and
                not any(event.get(x) for x in ("forced", "deleted", "created")), "Wrong boundary")
    api = API(os.environ["GITHUB_TOKEN"])
    receipt = {"plan_sha256": hashlib.sha256(raw).hexdigest(), "operations": [], "status": "running"}
    path = Path("cleanup-output/obsolete-actions.json"); path.parent.mkdir(exist_ok=True)
    def save():
        tmp = path.with_suffix(".tmp"); tmp.write_text(json.dumps(receipt, indent=2)+"\n"); tmp.replace(path)
    try:
        for entry in plan["runs"]:
            result = cancel(api, entry) if args.execute else ("eligible" if eligible(api, entry) else "completed")
            receipt["operations"].append({"kind": "run", **entry, "result": result}); save()
        for item in plan["workflows"]:
            current = api.request(PREFIX + f'/actions/workflows/{item["id"]}')
            require(current["path"] == item["path"], "Workflow identity mismatch")
            require(not any(r["path"] == item["path"] and r["status"] != "completed" for r in live(api)), "Workflow still has active run")
            if args.execute:
                api.request(PREFIX + f'/actions/workflows/{item["id"]}/disable', "PUT")
                require(api.request(PREFIX + f'/actions/workflows/{item["id"]}')["state"] == "disabled_manually", "Disable not confirmed")
            receipt["operations"].append({"kind": "workflow", **item, "result": "disabled" if args.execute else "eligible"}); save()
        receipt["status"] = "completed" if args.execute else "dry_run"
    except Exception as error:
        receipt.update(status="stopped", error=str(error)); raise
    finally:
        save()


if __name__ == "__main__":
    main()
