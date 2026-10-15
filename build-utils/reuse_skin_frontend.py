"""Reuse only the exact successful portable phase, otherwise run it again.

The original native job later failed a Git-history UI contract. That failure
remains recorded; it does not invalidate the preceding successful executables.
UIKit renderer/session tests are never reused by this gate.
"""
import json
import os
from pathlib import Path
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = '871986710377f54ba92b10e9a7c5b7d47adddfa8'
RUN = 38715089014
NON_INPUTS = {
    'AGENTS.md', '.github/workflows/libretro-skin-checks.yml',
    'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m',
    'test/libretro_simulator/probe.m', 'test/libretro_simulator/skin_press_probe.h',
    'test/libretro_skin_press_probe.py', 'build-utils/reuse_skin_frontend.py',
    'test/skin_frontend_reuse_test.py',
}


def tree(revision):
    result = subprocess.check_output(['git', 'ls-tree', '-rz', revision], cwd=ROOT)
    return {path.decode(): metadata.decode() for entry in result.split(b'\0') if entry
            for metadata, path in [entry.split(b'\t', 1)]}


def same_inputs(before, after):
    return all(before.get(p) == after.get(p) for p in before.keys() | after.keys()
               if p not in NON_INPUTS and not p.startswith('docs/'))


def phase_passed(run, jobs):
    if run.get('head_sha') != REFERENCE or run.get('status') != 'completed':
        return False
    matches = [j for j in jobs.get('jobs', []) if j.get('name') == 'native']
    if len(matches) != 1:
        return False
    steps = matches[0].get('steps', [])
    wanted = [s for s in steps if s.get('name') == 'Frontend behaviour and pressure pixel tests']
    setup = [s for s in steps if s.get('name') == 'Run maxim-lobanov/setup-xcode@v1']
    return (len(wanted) == len(setup) == 1 and
            all(s.get('status') == 'completed' and s.get('conclusion') == 'success' for s in wanted + setup))


def api(path):
    request = urllib.request.Request('https://api.github.com/repos/TarbleFR/neostation-ios/' + path,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    try:
        if not same_inputs(tree(REFERENCE), tree('HEAD')):
            raise ValueError('a closed-tree portable input changed')
        tools = subprocess.check_output(['xcodebuild', '-version'], text=True)
        if tools.strip() != 'Xcode 26.3\nBuild version 17C529':
            raise ValueError('Xcode identity differs')
        if os.environ.get('ImageVersion') != '20260907.0337.1':
            raise ValueError('macOS runner image differs')
        run = api(f'actions/runs/{RUN}')
        jobs = api(f'actions/runs/{RUN}/jobs?per_page=100')
        if not phase_passed(run, jobs):
            raise ValueError('successful phase provenance missing')
        print(json.dumps({'reusedPortablePhase': RUN, 'source': REFERENCE,
                          'overallRunConclusion': run.get('conclusion'), 'xcode': tools.strip(),
                          'runnerImage': os.environ['ImageVersion'], 'inputs': 'identical closed Git tree except listed non-inputs'}))
    except (OSError, ValueError, KeyError) as error:
        print('Portable phase reuse unavailable; executing tests:', str(error), flush=True)
        subprocess.run(['python3', 'test/libretro_frontend_test.py'], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
