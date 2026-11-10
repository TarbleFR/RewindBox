#!/usr/bin/env python3
"""Source-bound lifetime regressions; never infer an iPhone gain from host tests."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile

from rpcs3_cell559_test import normalized_sha, without_ios_blocks
from rpcs3_cell538_test import cache_identities

ROOT = Path(__file__).resolve().parents[1]
BASE = '99a57a663eed1a1e455e6c7baf7e9be621cb4b00'
SPU = 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp'
WARMUP = 'rpcs3/Emu/RSX/rsx_cache.h'


def helper(name):
    path = ROOT / 'test/native' / ('rpcs3_cell591_' + name + '.py')
    spec = importlib.util.spec_from_file_location('cell591_' + name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def source_contract(source, work):
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    rec = manifest['cell591']
    old = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert rec['baseline'] == BASE and rec['core_baseline'] == 'cell589'
    assert rec['codegen'] == old['cell589']['codegen']
    changed = {p for p, digest in old['files_sha256'].items()
               if manifest['files_sha256'][p] != digest}
    assert changed == set(rec['modified_paths'])
    assert set(manifest['files_sha256']) == set(old['files_sha256'])
    fixture = ROOT / 'test/fixtures/rpcs3_cell591.diff'
    assert hashlib.sha256(fixture.read_bytes()).hexdigest() == rec['fixture_sha256']
    before = work / 'before589'
    for path in rec['modified_paths']:
        assert normalized_sha(source / path) == rec['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(fixture)], cwd=before, check=True)
    for path in rec['modified_paths']:
        assert normalized_sha(before / path) == rec['before_sha256'][path] == old['files_sha256'][path], path
    for path in rec['shared_paths']:
        assert without_ios_blocks((before / path).read_text()) == without_ios_blocks((source / path).read_text()), path
    spu = (source / SPU).read_text()
    assert spu.count('CELL591_RELEASE_SPU_IR') == 1
    release = spu.index('// CELL591_RELEASE_SPU_IR')
    assert spu.index('if (!added || !m_jit.try_fin(llvm_error))') < spu.index('getPointerToFunction(main_func)') < spu.index('if (!fn)') < release
    assert release < spu.index('// Install unconditionally, possibly replacing existing one from spu_fast')
    assert spu.index('m_ir->ClearInsertionPoint();', release) < spu.index('m_engine->removeModule(m_module)', release)
    # The separate interpreter compiler must not lose its IR or change its path.
    start = spu.index('\n\tspu_function_t compile_interpreter()')
    old_spu = (before / SPU).read_text()
    old_start = old_spu.index('\n\tspu_function_t compile_interpreter()')
    assert spu[start:] == old_spu[old_start:]
    identity = cache_identities(source)
    assert identity == rec['codegen']
    return before, {'fixtureSHA256': rec['fixture_sha256'], 'changedPaths': sorted(changed),
                    'untouchedCanonicalFiles': len(old['files_sha256']) - len(changed),
                    'offIOSUnchanged': rec['shared_paths'], 'codegen': identity,
                    'coldCompileRequiredByThisChange': False, 'interpreterUnchanged': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--allow-unpinned', action='store_true', help='Local partial checks only; never a CI/build proof')
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='cell591-') as tmp:
        work = Path(tmp)
        before, contract = source_contract(source, work)
        warmup_report = work / 'warmup.json'
        helper('warmup').run(before / WARMUP, source / WARMUP, source, warmup_report)
        warmup = json.loads(warmup_report.read_bytes())
        spu = helper('spu').run(before, source, source, work)
        pinned = spu.get('pinnedLLVM22Tested') is True
        report = {'passed': pinned, 'availableChecksPassed': True,
                  'result': 'passed' if pinned else 'partial: pinned LLVM22 native test pending',
                  'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'sourceContract': contract, 'shaderWarmup': warmup, 'spuLifetime': spu,
                  'pinnedLLVM22Tested': pinned, 'physicalDeviceTested': False,
                  'gameplayMeasured': False, 'gainClaimed': False,
                  'scope': 'New lifetime regressions only. Shader warmup adapters exercise actual production bodies and ownership helpers. MCJIT uses actual LLVM; native code, globals, object-cache relocation and later compilations must survive removed IR. No iPhone RAM/FPS result.'}
        manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
        inputs = ['test/rpcs3_cell591_test.py'] + manifest['cell591']['test_inputs']
        report['inputs'] = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs}
    output = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output, end='')
    if not pinned and (not args.allow_unpinned or os.environ.get('CI')):
        raise SystemExit('Pinned LLVM22 native lifetime regression is required for a Core build')


if __name__ == '__main__':
    main()
