#!/usr/bin/env python3
"""Remove only exact old empty queued records reviewed after cancellation failed."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import time
import urllib.error
import urllib.request
from retire_obsolete_actions import API, eligible, validate, REPO, PREFIX, require


CONFIRMATION_ATTEMPTS = 6
CONFIRMATION_DELAY_SECONDS = 2


def remove(api, entry, delete, sleep=time.sleep):
    if not eligible(api, entry):
        return 'completed_preserved'
    path = PREFIX + f'/actions/runs/{entry["id"]}'
    already_absent = False
    try:
        delete(path)
    except urllib.error.HTTPError as error:
        if error.code not in (403, 404, 409, 422):
            raise
        if error.code != 404:
            return 'delete_refused_' + str(error.code)
        already_absent = True
    # GitHub may briefly serve the old record after acknowledging deletion.
    # Poll only GET: a delayed observation must never repeat the mutation.
    for attempt in range(CONFIRMATION_ATTEMPTS):
        try:
            api.request(path)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return 'already_absent_confirmed' if already_absent else 'deleted_confirmed'
            raise
        if attempt + 1 < CONFIRMATION_ATTEMPTS:
            sleep(CONFIRMATION_DELAY_SECONDS)
    return 'deletion_not_confirmed'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan',type=Path,required=True)
    parser.add_argument('--expected-plan-sha256',required=True)
    args=parser.parse_args(); raw=args.plan.read_bytes()
    require(hashlib.sha256(raw).hexdigest()==args.expected_plan_sha256,'Changed plan')
    plan=json.loads(raw);validate(plan)
    require(plan.get('remove_empty_orphans') is True,'Not an orphan removal plan')
    require(os.environ.get('GITHUB_ACTIONS')=='true' and os.environ.get('GITHUB_REPOSITORY')==REPO and
            os.environ.get('GITHUB_REF')=='refs/heads/Claude' and os.environ.get('GITHUB_EVENT_NAME')=='push','Wrong execution')
    event=json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    require(event['before']==plan['base_sha'] and event['after']==os.environ['GITHUB_SHA'] and
            not any(event.get(k) for k in ('created','forced','deleted')),'Wrong push boundary')
    api=API(os.environ['GITHUB_TOKEN'])
    prior=api.request(PREFIX+f'/actions/runs/{plan["prior_cancellation_run"]}')
    require(prior['status']=='completed' and prior['conclusion']=='success' and
            prior['head_sha']==plan['prior_cancellation_source'], 'Cancellation pass not completed at reviewed source')
    allowed={PREFIX+f'/actions/runs/{e["id"]}' for e in plan['runs']}
    def delete(path):
        require(path in allowed,'Unreviewed target')
        req=urllib.request.Request('https://api.github.com'+path,method='DELETE',headers={
            'Authorization':'Bearer '+api.token,'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
        with urllib.request.urlopen(req,timeout=30) as response:
            require(response.status==204,'Unexpected deletion response')
    path=Path('cleanup-output/orphaned-runs.json');path.parent.mkdir(exist_ok=True)
    receipt={'planSHA256':hashlib.sha256(raw).hexdigest(),'operations':[],'status':'running'}
    def save():
        temp=path.with_suffix('.tmp');temp.write_text(json.dumps(receipt,indent=2)+'\n');temp.replace(path)
    try:
        for entry in plan['runs']:
            receipt['operations'].append({**entry,'result':remove(api,entry,delete)});save()
        receipt['status']='completed'
    except Exception as error:
        receipt.update(status='stopped',error=str(error));raise
    finally:save()
if __name__=='__main__':main()
