"""Reuse only individually passed checks of the unchanged combined UI.

The previous run failed solely in one input fixture and one import lint. Do not
call that run successful or replay its 62 unchanged successful checks.
"""
import json
from pathlib import Path
import re
import subprocess

SOURCE = '534fb8426e17442f6f979ab8f95e43c78639bfa3'
RUN = 39845018642
JOB = 120055912702
FIXTURE = 'test/airplay_navigation_test.dart'


def git(*args):
    return subprocess.check_output(['git', *args], text=True).strip()


def api(path):
    return subprocess.check_output(['gh', 'api', 'repos/TarbleFR/RewindBox/' + path], text=True)


changed = set(git('diff', '--name-only', SOURCE, 'HEAD', '--',
                  'lib', 'test', 'packages', 'assets', 'native',
                  'pubspec.yaml', 'pubspec.lock', 'analysis_options.yaml').splitlines())
if changed != {FIXTURE}:
    raise ValueError('Previously passed test input changed: ' + ', '.join(sorted(changed)))
run = json.loads(api(f'actions/runs/{RUN}'))
assert run['head_sha'] == SOURCE and run['status'] == 'completed' and run['conclusion'] == 'failure'
job = json.loads(api(f'actions/jobs/{JOB}'))
assert job['run_id'] == RUN and job['conclusion'] == 'failure'
assert job['name'] == 'Liquid material and sequential AirPlay navigation'
raw = api(f'actions/jobs/{JOB}/logs')
plain = re.sub(r'\x1b\[[0-9;]*m', '', raw)
plain = re.sub(r'^\ufeff?\d{4}-\d\d-\d\dT[^ ]+ ', '', plain, flags=re.M)
assert re.search(r'\+62 -1: Some tests failed\.', plain), 'Prior individual pass/fail count changed'
failures = plain.split('Failing tests:\n', 1)[1].split('##[error]', 1)[0].strip().splitlines()
assert len(failures) == 1
assert failures[0].strip() == (
    '/home/runner/work/RewindBox/RewindBox/test/airplay_navigation_test.dart: '
    'keyboard, D-pad, stick and bumpers use the same cycle without double dispatch '
    '(variant: TargetPlatform.iOS)'
)
out = Path('build/bubble-review/reused-individual-checks.json')
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({
    'result': 'passed', 'previousRun': RUN, 'previousJob': JOB,
    'previousRunConclusion': 'failure', 'previousTestedSHA': SOURCE,
    'candidateSHA': git('rev-parse', 'HEAD'), 'individualChecksPassed': 62,
    'failedFixtureRerun': FIXTURE, 'testedInputChange': sorted(changed),
    'wholePreviousRunReusedAsSuccessful': False,
    'tool': 'Flutter 3.47.2, Ubuntu 24.04',
}, indent=2) + '\n')
print('PASS identities of 62 individual checks; prior whole run remains failed; rerun changed input fixture')
