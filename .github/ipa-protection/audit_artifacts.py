"""Read-only inventory of Actions artifacts. No release or artifact mutation."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request

REPO = 'TarbleFR/RewindBox'
API = 'https://api.github.com/repos/' + REPO


def get_json(path):
    if not path.startswith('/actions/artifacts?per_page=100&page='):
        raise ValueError('Unsupported read-only API path')
    for attempt in range(3):
        request = urllib.request.Request(API + path, headers={
            'Accept': 'application/vnd.github+json',
            'Authorization': 'Bearer ' + os.environ['GITHUB_TOKEN'],
            'X-GitHub-Api-Version': '2022-11-28',
        })
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == 2:
                raise RuntimeError('Artifact inventory HTTP ' + str(error.code)) from None
            time.sleep(2 ** attempt)
    raise RuntimeError('Artifact inventory failed')


def inventory():
    started = datetime.now(timezone.utc).isoformat()
    artifacts = {}
    totals = []
    for page in range(1, 501):
        payload = get_json('/actions/artifacts?per_page=100&page=' + str(page))
        if not isinstance(payload.get('artifacts'), list):
            raise ValueError('Missing artifact list')
        totals.append(payload.get('total_count'))
        for artifact in payload['artifacts']:
            # Signed download URLs and tokens are never persisted.
            artifacts[artifact['id']] = {key: artifact.get(key) for key in (
                'id', 'name', 'size_in_bytes', 'created_at', 'updated_at',
                'expired', 'expires_at', 'digest', 'workflow_run')}
        if len(payload['artifacts']) < 100:
            break
    else:
        raise ValueError('Artifact inventory exceeded 500 pages')
    items = sorted(artifacts.values(), key=lambda item: item['id'])
    return {'schema': 1, 'repository': REPO, 'startedAt': started,
            'completedAt': datetime.now(timezone.utc).isoformat(),
            'source': os.environ.get('GITHUB_SHA'), 'runId': os.environ.get('GITHUB_RUN_ID'),
            'pages': len(totals), 'reportedTotals': totals,
            'artifactCount': len(items), 'unexpiredCount': sum(not x['expired'] for x in items),
            'totalUnexpiredBytes': sum(x['size_in_bytes'] for x in items if not x['expired']),
            'artifacts': items, 'mutations': 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = inventory()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k != 'artifacts'}, sort_keys=True))


if __name__ == '__main__':
    main()
