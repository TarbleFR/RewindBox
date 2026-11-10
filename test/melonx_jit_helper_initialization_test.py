#!/usr/bin/env python3
"""Regression for the whole packaged helper, including its blocking event loop."""
import argparse
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
import sys
sys.path.insert(0,str(ROOT/'build-utils/melonx'))
from helper_initialization import SCRIPT, BASE, relocate, verify


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--require-apple', action='store_true')
    parser.add_argument('--report', type=Path, default=ROOT/'build/delivery/melonx-jit-helper-init.json')
    args = parser.parse_args()
    before = subprocess.check_output(['git', 'show', BASE + ':' + SCRIPT], cwd=ROOT).decode()
    after = (ROOT/SCRIPT).read_text()
    verify()
    assert after == relocate(before), 'Only the exact reviewed block relocation is permitted'
    node = json.loads(subprocess.check_output(['node', str(ROOT/'test/melonx_sized_jit_session_test.js'), str(ROOT/SCRIPT)], text=True))
    assert node['result'] == 'passed' and node['checks'] == 99
    isolated = json.loads(subprocess.check_output(['node', str(ROOT/'test/melonx_sized_jit/Protocol.js'), str(ROOT/SCRIPT)], text=True))
    assert isolated['result'] == 'passed' and isolated['checks'] == 101
    apple = None
    with tempfile.TemporaryDirectory(prefix='melonx-helper-init-') as directory:
        work = Path(directory)
        old = work/'delivered601.js'; old.write_text(before)
        cases = [dict(refused=n, events=['probe','capability','sized','capability','sized','detach']) for n in range(10)]
        cases += [dict(prepareFailure=True,events=['probe','capability','sized','sized','detach']),
                  dict(events=['probe','legacy','detach']), dict(attachFailure=True,events=['probe']),dict(wrongPid=True,events=['probe'])]
        options = work/'cases.json'; options.write_text(json.dumps(cases))
        command = ['node', str(ROOT/'test/melonx_sized_jit_session_test.js')]
        old_results = json.loads(subprocess.check_output(command+[str(old),'--observations',str(options)],text=True))
        assert 'before initialization' in old_results[0]['error']
        assert old_results[0]['state']['allocations'] == old_results[0]['state']['prepared'] == []
        current = json.loads(subprocess.check_output(command+[str(ROOT/SCRIPT),'--observations',str(options)],text=True))
        if platform.system() == 'Darwin':
            exe = work/'session-jsc'
            subprocess.run(['xcrun','swiftc',str(ROOT/'test/melonx_sized_jit/Session.swift'),'-framework','JavaScriptCore','-o',str(exe)],check=True)
            def execute(source):
                return json.loads(subprocess.check_output([str(exe),str(source),str(ROOT/'test/melonx_sized_jit/Session.js'),str(options)],text=True))
            old_apple = execute(old)
            assert old_apple[0]['error'] is not None and old_apple[0]['state']['allocations'] == old_apple[0]['state']['prepared'] == []
            actual = execute(ROOT/SCRIPT)
            assert actual == current, 'Whole-script JavaScriptCore and Node observations differ'
            apple = dict(result='passed',sessions=len(actual),originalFailure=old_apple[0]['error'],observations=actual)
        elif args.require_apple:
            raise AssertionError('Apple JavaScriptCore execution is required')
    inputs = [SCRIPT, 'build-utils/melonx/helper_initialization.py', 'test/melonx_jit_helper_initialization_test.py','test/melonx_sized_jit_session_test.js',
              'test/melonx_sized_jit/Session.js','test/melonx_sized_jit/Session.swift','test/melonx_sized_jit/Protocol.js']
    report = dict(result='passed',baseline=BASE,baselineScriptSHA256=hashlib.sha256(before.encode()).hexdigest(),
        currentScriptSHA256=hashlib.sha256(after.encode()).hexdigest(),exactBlockRelocation=True,
        wholeScript=node,isolatedProtocol=isolated,originalFailure=old_results[0]['error'],appleJavaScriptCore=apple,
        nativeVMAndDebugserverDoubled=True,physicalDeviceTested=False,coreRecompiled=False,
        inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs})
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ('result','exactBlockRelocation','originalFailure','wholeScript','appleJavaScriptCore')}))


if __name__ == '__main__': main()
