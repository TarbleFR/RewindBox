#!/usr/bin/env python3
"""Read the shared GitHub handoff and build state; never mutate or dispatch.

Both Claude accounts use the same command. PRs carry reviewable diffs, while
docs/AI_TASK_BOARD.md remains the single task/ownership contract.
"""
import argparse
import json
import os
import re
import subprocess
import urllib.request

REPO = "TarbleFR/RewindBox"
ACTIVE = {"queued", "in_progress", "waiting", "pending", "requested"}


def get(path):
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request = urllib.request.Request("https://api.github.com/" + path, headers={
            "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"})
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.load(response)
    result = subprocess.run(["gh", "api", path], text=True, capture_output=True)
    if result.returncode:
        raise RuntimeError("GitHub read failed; check the account's existing gh login. " + result.stderr.strip())
    return json.loads(result.stdout)


def pages(path, key=None, reader=get):
    values = []
    separator = "&" if "?" in path else "?"
    for page in range(1, 101):
        result = reader(f"{path}{separator}per_page=100&page={page}")
        batch = result[key] if key else result
        values.extend(batch)
        if len(batch) < 100:
            return values
    raise RuntimeError("Incomplete GitHub inventory; refusing to infer readiness")


def handoff(pr):
    match = re.search(r"<!-- rewindbox-handoff\s+(\{.*?\})\s*-->", pr.get("body") or "", re.S)
    declared = {}
    if match:
        try:
            declared = json.loads(match.group(1))
        except (ValueError, TypeError):
            pass
    actual = pr["head"]["sha"]
    expected = declared.get("source")
    return {"pr": pr["number"], "url": pr["html_url"], "title": pr["title"],
            "branch": pr["head"]["ref"], "source": actual, "base": pr["base"]["ref"],
            "draft": pr.get("draft", False), "declaredSource": expected,
            "handoff": "current" if expected == actual else "stale" if expected else "missing",
            "owner": declared.get("owner"), "reviewer": declared.get("reviewer")}


def summarize_run(run):
    return {key: run.get(key) for key in ("id", "html_url", "name", "path", "head_branch", "head_sha",
                                           "run_attempt", "event", "status", "conclusion")}


def snapshot(reader=get, source=None):
    root = "repos/" + REPO
    branch = reader(root + "/branches/Claude")
    pulls = pages(root + "/pulls?state=open&base=Claude", reader=reader)
    active = {}
    for status in sorted(ACTIVE):
        for run in pages(root + "/actions/runs?status=" + status, "workflow_runs", reader):
            active[run["id"]] = summarize_run(run)
    report = {"repository": REPO, "integrationSource": branch["commit"]["sha"],
              "handoffs": [handoff(pr) for pr in pulls], "activeRuns": list(active.values()),
              "notice": "A current handoff is not approval, a green CI is not an IPA, and a board note is not an acknowledgement."}
    if source:
        if not re.fullmatch(r"[0-9a-f]{40}", source):
            raise ValueError("--source requires the full commit SHA")
        report["sourceRuns"] = [summarize_run(run) for run in pages(
            root + "/actions/runs?head_sha=" + source, "workflow_runs", reader)]
        report["dispatchAdvice"] = "Inspect sourceRuns before dispatch; reuse the exact successful producer or follow its active run. Never dispatch a duplicate blindly."
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", help="Inspect existing runs before building this exact source")
    args = parser.parse_args()
    print(json.dumps(snapshot(source=args.source), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
