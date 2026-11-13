#!/usr/bin/env python3
"""One-time reversible disable of the exact reviewed legacy workflow list."""
import json
import os
import urllib.request
from pathlib import Path

REPO = 'TarbleFR/RewindBox'
ROOT = 'https://api.github.com/repos/' + REPO


def api(path, method='GET'):
    request = urllib.request.Request(ROOT + path, method=method, headers={
        'Authorization': 'Bearer ' + os.environ['GH_TOKEN'],
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    })
    with urllib.request.urlopen(request, timeout=30) as response:
        body = response.read()
    return json.loads(body) if body else None


def pages(path, key):
    rows = []
    separator = '&' if '?' in path else '?'
    for page in range(1, 101):
        batch = api(f'{path}{separator}per_page=100&page={page}')[key]
        rows.extend(batch)
        if len(batch) < 100:
            return rows
    raise RuntimeError('Incomplete inventory')


def run(plan):
    selected = plan['selected']
    assert plan['repository'] == REPO
    assert 0 < len(selected) < 150
    assert len({w['id'] for w in selected}) == len(selected)
    before = {w['id']: w for w in pages('/actions/workflows', 'workflows')}
    busy = set()
    for status in ['queued', 'in_progress', 'waiting', 'pending', 'requested']:
        busy.update(r['workflow_id'] for r in pages('/actions/runs?status=' + status, 'workflow_runs'))
    for w in selected:
        actual = before[w['id']]
        assert actual['path'] == w['path'] and actual['name'] == w['name'], w
    results = []
    for w in selected:
        item = {'id': w['id'], 'path': w['path']}
        if w['id'] in busy:
            item['result'] = 'kept_active_run'
        else:
            current = api('/actions/workflows/' + str(w['id']))
            assert current['path'] == w['path'] and current['name'] == w['name']
            if current['state'] == 'active':
                # Check the latest run again immediately before the reversible change.
                latest = api('/actions/workflows/' + str(w['id']) + '/runs?per_page=1')['workflow_runs']
                if latest and latest[0]['status'] != 'completed':
                    item['result'] = 'kept_active_run'
                else:
                    api('/actions/workflows/' + str(w['id']) + '/disable', 'PUT')
                    assert api('/actions/workflows/' + str(w['id']))['state'] == 'disabled_manually'
                    item['result'] = 'disabled'
            else:
                item['result'] = 'already_' + current['state']
        results.append(item)
        print('WORKFLOW_RESULT ' + json.dumps(item), flush=True)
    after = {w['id']: w for w in pages('/actions/workflows', 'workflows')}
    selected_ids = {w['id'] for w in selected}
    unexpected = [i for i in before if i not in selected_ids and (i not in after or after[i]['state'] != before[i]['state'])]
    summary = {'selected': len(selected), 'disabled': sum(x['result'] == 'disabled' for x in results),
               'already_disabled': sum(x['result'].startswith('already_') for x in results),
               'kept_active_run': sum(x['result'] == 'kept_active_run' for x in results),
               'before_active': sum(w['state'] == 'active' for w in before.values()),
               'after_active': sum(w['state'] == 'active' for w in after.values()),
               'unselected_state_changes': unexpected, 'run_or_artifact_deletions': 0}
    print('WORKFLOW_SUMMARY ' + json.dumps(summary), flush=True)
    assert not unexpected, 'Unselected workflows changed state; investigate external changes'
    return results, summary


if __name__ == '__main__':
    assert os.environ['GITHUB_REPOSITORY'] == REPO
    assert os.environ['GITHUB_REF'] == 'refs/heads/Claude'
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    assert event['head_commit']['message'].startswith('[workflow-list-cleanup]')
    run(json.loads(Path('build-utils/maintenance/workflow-list-cleanup-2026-11-13.json').read_text()))
    # Leave no active maintenance launcher after this one-time operation.
    own = [w for w in pages('/actions/workflows', 'workflows')
           if w['path'] == '.github/workflows/workflow-list-cleanup.yml']
    assert len(own) == 1
    api('/actions/workflows/' + str(own[0]['id']) + '/disable', 'PUT')
    assert api('/actions/workflows/' + str(own[0]['id']))['state'] == 'disabled_manually'
    print('SELF_DISABLED ' + str(own[0]['id']), flush=True)
