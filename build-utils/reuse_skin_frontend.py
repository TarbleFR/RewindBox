"""Reuse only the exact successful portable phase, otherwise run it again.

The original native job later failed a Git-history UI contract. That failure
remains recorded; it does not invalidate the preceding successful executables.
UIKit renderer/session tests are never reused by this gate.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
REFERENCE = 'b3538c127fe54799a3822cfd27f853b2a0ac246f'
RUN = 38719706135
IPHONE_REFERENCE = 'b3538c127fe54799a3822cfd27f853b2a0ac246f'
IPHONE_RUN = 38719706135
RENDERER = 'packages/libretro_internal_bridge/ios/Classes/LibretroSkinRenderer.m'
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


def same_inputs(before, after, iphone=False):
    return all(before.get(p) == after.get(p) for p in before.keys() | after.keys()
               if (p not in NON_INPUTS or (iphone and p == RENDERER)) and not p.startswith('docs/'))


def phase_passed(run, jobs, iphone=False):
    if run.get('head_sha') != (IPHONE_REFERENCE if iphone else REFERENCE) or run.get('status') != 'completed':
        return False
    matches = [j for j in jobs.get('jobs', []) if j.get('name') == 'native']
    if len(matches) != 1:
        return False
    steps = matches[0].get('steps', [])
    name = 'Compile and link every bridge source for iPhone' if iphone else 'Frontend behaviour and pressure pixel tests'
    wanted = [s for s in steps if s.get('name') == name]
    setup = [s for s in steps if s.get('name') == 'Run maxim-lobanov/setup-xcode@v1']
    return (len(wanted) == len(setup) == 1 and
            all(s.get('status') == 'completed' and s.get('conclusion') == 'success' for s in wanted + setup))


def api(path):
    request = urllib.request.Request('https://api.github.com/repos/TarbleFR/neostation-ios/' + path,
        headers={'Authorization': 'Bearer ' + os.environ['GH_TOKEN'], 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    iphone = '--iphone' in sys.argv[1:]
    reference, run_id = (IPHONE_REFERENCE, IPHONE_RUN) if iphone else (REFERENCE, RUN)
    try:
        if not same_inputs(tree(reference), tree('HEAD'), iphone):
            raise ValueError('a closed-tree input changed')
        tools = subprocess.check_output(['xcodebuild', '-version'], text=True)
        if tools.strip() != 'Xcode 26.3\nBuild version 17C529':
            raise ValueError('Xcode identity differs')
        if os.environ.get('ImageVersion') != '20260907.0337.1':
            raise ValueError('macOS runner image differs')
        run = api(f'actions/runs/{run_id}')
        jobs = api(f'actions/runs/{run_id}/jobs?per_page=100')
        if not phase_passed(run, jobs, iphone):
            raise ValueError('successful phase provenance missing')
        print(json.dumps({'reusedPhase': 'iphone-compile-link' if iphone else 'portable', 'run': run_id, 'source': reference,
                          'overallRunConclusion': run.get('conclusion'), 'xcode': tools.strip(),
                          'runnerImage': os.environ['ImageVersion'], 'inputs': 'identical closed Git tree except listed non-inputs'}))
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as error:
        print('Phase reuse unavailable; executing checks:', str(error), flush=True)
        script = 'test/libretro_ios_syntax_test.py' if iphone else 'test/libretro_frontend_test.py'
        subprocess.run(['python3', script], cwd=ROOT, check=True)


if __name__ == '__main__':
    main()
