#!/usr/bin/env python3
"""Remove only exact reviewed refs whose complete history is retained by Backup.

Backup is an archival parent graph, never a product merge. This command does not
close PRs, cancel jobs, disable workflows, or delete runs, artifacts or tags.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import quote

from tidy_repository import API, PREFIX, REPO, SHA, check_base, listing, require


def validate_plan(plan, now=None):
    require(plan.get('repository') == REPO and plan.get('version', plan.get('schema_version')) == 1, 'Wrong plan target')
    for key in ('base_sha', 'main_sha', 'backup_sha'):
        require(isinstance(plan.get(key), str) and SHA.fullmatch(plan[key]), 'Invalid ' + key)
    expiry = datetime.fromisoformat(plan['expires_at'].replace('Z', '+00:00'))
    require(expiry > (now or datetime.now(timezone.utc)), 'Plan expired')
    branches = plan.get('branches')
    require(isinstance(branches, list) and 0 < len(branches) <= 40, 'Invalid branch bound')
    names = []
    for row in branches:
        name = row['branch']
        require(isinstance(name, str) and re.fullmatch(r'(work|dependabot)/[A-Za-z0-9][A-Za-z0-9._/-]*', name)
                and '..' not in name and not name.endswith('.lock')
                and 'backup' not in name.lower(), 'Protected or invalid branch')
        require(isinstance(row.get('sha'), str) and SHA.fullmatch(row['sha']), 'Invalid branch SHA')
        names.append(name)
    require(len(names) == len(set(names)), 'Duplicate branch')


def check_archive(api, plan):
    value = api.request(PREFIX + '/branches/Backup')
    require(value['commit']['sha'] == plan['backup_sha'], 'Backup changed')
    commit = api.request(PREFIX + '/git/commits/' + plan['backup_sha'])
    require(commit['sha'] == plan['backup_sha'], 'Archive commit identity changed')
    parents = {p['sha'] for p in commit['parents']}
    value = api.request(PREFIX + '/contents/branch-archive.json?ref=' + plan['backup_sha'])
    require(value.get('type') == 'file' and value.get('encoding') == 'base64', 'Missing archive manifest')
    manifest = json.loads(base64.b64decode(''.join(value['content'].split()), validate=True))
    require(manifest.get('repository') == REPO and manifest.get('version') == 1, 'Wrong archive manifest')
    rows = manifest.get('branches')
    require(isinstance(rows, list), 'Missing manifest branches')
    names = [row['branch'] for row in rows]
    require(len(names) == len(set(names)), 'Duplicate manifest branch')
    archived = {row['branch']: row['sha'] for row in rows}
    for branch in plan['branches']:
        require(archived.get(branch['branch']) == branch['sha'], 'Branch does not match archive manifest: ' + branch['branch'])
        require(branch['sha'] in parents, 'Branch is not a direct archive parent: ' + branch['branch'])
    return parents


def check_target(api, branch):
    name = branch['branch']
    try:
        value = api.request(PREFIX + '/branches/' + quote(name, safe=''))
    except HTTPError as error:
        if error.code == 404:
            return False
        raise
    require(value['commit']['sha'] == branch['sha'] and not value.get('protected'), 'Branch changed/protected: ' + name)
    pulls = listing(api, PREFIX + '/pulls?state=open')
    require(not any(p['head']['ref'] == name or p['base']['ref'] == name for p in pulls), 'Open PR uses branch: ' + name)
    return True


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    os.replace(temporary, path)


def run(api, plan, receipt, execute=False, output=None):
    validate_plan(plan)
    check_base(api, plan)
    check_archive(api, plan)
    for branch in plan['branches']:
        validate_plan(plan)
        check_base(api, plan)
        check_archive(api, plan)
        present = check_target(api, branch)
        operation = {'kind': 'branch', **branch, 'backup_sha': plan['backup_sha']}
        if not present:
            operation['result'] = 'already_absent'
        elif execute:
            # The server's atomic lease rejects any advance after the GET checks.
            api.delete_branch(branch['branch'], branch['sha'])
            operation['result'] = 'deleted'
        else:
            operation['result'] = 'eligible'
        receipt['operations'].append(operation)
        if output is not None:
            save(Path(output) / ('operation-%03d.json' % len(receipt['operations'])), operation)
            save(Path(output) / 'branch-consolidation.json', receipt)


def execution_context(plan, environment, event):
    require(environment.get('GITHUB_ACTIONS') == 'true' and environment.get('GITHUB_REPOSITORY') == REPO
            and environment.get('GITHUB_REF') == 'refs/heads/Claude'
            and environment.get('GITHUB_EVENT_NAME') == 'push', 'Requires authorized Claude push')
    sha = environment.get('GITHUB_SHA', '')
    require(SHA.fullmatch(sha), 'Invalid execution SHA')
    require(environment.get('GITHUB_API_URL', 'https://api.github.com') == 'https://api.github.com', 'Unexpected API URL')
    require(environment.get('GITHUB_WORKFLOW_SHA', sha) == sha, 'Workflow source differs')
    require(event.get('ref') == 'refs/heads/Claude' and event.get('repository', {}).get('full_name') == REPO
            and event.get('before') == plan['base_sha'] and event.get('after') == sha
            and not any(event.get(x) for x in ('forced', 'deleted', 'created')), 'Unexpected push boundary')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', required=True, type=Path)
    parser.add_argument('--expected-plan-sha256', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--output', type=Path, default=Path('cleanup-output'))
    args = parser.parse_args()
    receipt = {'operations': [], 'result': 'in_progress'}
    try:
        raw = args.plan.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(digest == args.expected_plan_sha256, 'Plan bytes changed')
        receipt['planSHA256'] = digest
        plan = json.loads(raw)
        validate_plan(plan)
        if args.execute:
            event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
            execution_context(plan, os.environ, event)
        run(API(os.environ['GITHUB_TOKEN']), plan, receipt, args.execute, args.output)
        receipt['result'] = 'completed' if args.execute else 'dry_run'
    except Exception as error:
        receipt['result'] = 'stopped'
        receipt['error'] = str(error)
        raise
    finally:
        save(args.output / 'branch-consolidation.json', receipt)


if __name__ == '__main__':
    main()
