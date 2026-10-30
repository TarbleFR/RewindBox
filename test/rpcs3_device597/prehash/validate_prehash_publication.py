#!/usr/bin/env python3
"""Run only the new stale-prehash-publication scope against exact actual headers.

Both headers' bodies are unchanged; only their namespace identifiers are adapted
to permit side-by-side execution. Guest hashes are deterministic oracle payloads,
not real guest RAM, and replay byte counts model fallback requests rather than
measuring memory traffic or game frames. No engine is built.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import statistics
import subprocess

RELATIVE = 'rpcs3/ios/IOSTexturePrehash.h'
NAMESPACE = 'namespace rpcs3::ios::texture_prehash'
HERE = Path(__file__).resolve().parent

def sha(data): return hashlib.sha256(data).hexdigest()

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--baseline', required=True, type=Path)
    p.add_argument('--candidate', required=True, type=Path)
    p.add_argument('--compiler', default=os.environ.get('CXX', 'g++'))
    p.add_argument('--sanitizer', default='')
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--report', required=True, type=Path)
    p.add_argument('--benchmark', action='store_true')
    a = p.parse_args()
    a.work.mkdir(parents=True, exist_ok=True)
    source_hashes = {}
    adaptations = {}
    for name, root in [('before', a.baseline), ('after', a.candidate)]:
        data = (root / RELATIVE).read_bytes()
        source_hashes[name] = sha(data)
        text = data.decode()
        assert text.count(NAMESPACE) == 1
        if name == 'after':
            body = text[text.index('inline void publish'):text.index('// The texture cache\'s validation hash')]
            assert 'seq = slot.seq.load(std::memory_order_acquire);' in body, 'Pre-CAS epoch check requires an acquire sequence load.'
            assert 'slot.epoch.load(std::memory_order_acquire) > epoch' in body
        adapted = text.replace(NAMESPACE, 'namespace ' + name)
        (a.work / (name + '.hpp')).write_text(adapted)
        adaptations[name] = {'operation':'replace namespace identifier only', 'sha256':sha(adapted.encode())}
    template = (HERE / 'prehash_publication.inc').read_bytes()
    cpp = a.work / 'prehash_publication.cpp'
    cpp.write_bytes(template)
    binary = a.work / 'prehash_publication'
    compiler = shlex.split(a.compiler)
    flags = ['-std=c++20','-O2','-g','-UNDEBUG','-Wall','-Wextra','-Werror','-pthread','-fno-omit-frame-pointer']
    if a.sanitizer: flags += ['-fsanitize=' + a.sanitizer]
    if os.environ.get('HOST_MACOS_SDK'): flags += ['-isysroot',os.environ['HOST_MACOS_SDK']]
    command = compiler + flags + [str(cpp),'-o',str(binary)]
    built = subprocess.run(command, capture_output=True, text=True)
    (a.work / 'build.stdout').write_text(built.stdout)
    (a.work / 'build.stderr').write_text(built.stderr)
    base = {'scope':'stale prehash publication ordering only','compiler':subprocess.check_output(compiler + ['--version'],text=True).splitlines()[0],
            'machine':platform.machine(),'platform':platform.platform(),'flags':flags,'sanitizer':a.sanitizer,
            'sourceSHA256':source_hashes,'namespaceAdaptations':adaptations,'harnessSHA256':sha(template),
            'physicalDeviceTested':False,'gameplayMeasured':False,'fpsGainClaimed':False,
            'guestPayloadBoundary':'deterministic key/epoch oracle; no real texture reads',
            'buildReturnCode':built.returncode,
            'limits':['Concurrency stress is not a proof of all C++ interleavings.',
                      'Acquire ordering proof is reviewed separately; TSan does not detect every wrong atomic memory order.',
                      'Timings measure isolated host publication calls; retained negative samples are not iPhone timings.',
                      'Logical fallback-range bytes model demand misses; they are not measured device bandwidth.']}
    if built.returncode:
        base.update(passed=False, failure='compile', stderr=built.stderr)
        a.report.write_text(json.dumps(base,indent=2)+'\n')
        raise SystemExit(built.returncode)
    env = dict(os.environ)
    env['ASAN_OPTIONS']='detect_leaks=0:halt_on_error=1'
    env['UBSAN_OPTIONS']='halt_on_error=1:print_stacktrace=1'
    env['TSAN_OPTIONS']='halt_on_error=1'
    result = subprocess.run([str(binary),'bench' if a.benchmark else 'check'],capture_output=True,text=True,env=env,timeout=120)
    (a.work / 'run.stdout').write_text(result.stdout)
    (a.work / 'run.stderr').write_text(result.stderr)
    base.update(runReturnCode=result.returncode)
    if result.returncode:
        base.update(passed=False, failure='execution', stdout=result.stdout, stderr=result.stderr)
    else:
        actual=json.loads(result.stdout)
        base.update(actual)
        for timing in base['timingsNsPerPublish']:
            b=statistics.median(x['baseline'] for x in timing['samples'])
            c=statistics.median(x['candidate'] for x in timing['samples'])
            timing.update(baselineMedianNs=b,candidateMedianNs=c,percentChange=(c/b-1)*100)
    # Catch mutation during a run. Source input is not merely labeled after execution.
    assert sha((a.baseline / RELATIVE).read_bytes()) == source_hashes['before']
    assert sha((a.candidate / RELATIVE).read_bytes()) == source_hashes['after']
    a.report.write_text(json.dumps(base,indent=2)+'\n')
    print(json.dumps({k:base.get(k) for k in ['passed','sanitizer','failure','runReturnCode','baseline','candidate','baselineConcurrent','candidateConcurrent','timingsNsPerPublish']},indent=2))
    raise SystemExit(0 if base.get('passed') else 1)

if __name__ == '__main__': main()
