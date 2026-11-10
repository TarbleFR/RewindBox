#!/usr/bin/env python3
"""Validate refined runtime bodies against the actual verified global Core.

Reuse existing production extractors and boundary adapters, with both sides
already containing the global correctness fixes. No historical executable is
replayed. Reports bind the complete sources, exact generated programs and tools.
GPU/DMA execution and iPhone gameplay are outside these host models.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import statistics
import subprocess
import tempfile

import rpcs3_descriptor_bind_cache_test as descriptor
import rpcs3_spu_timer_runtime_test as timer
import rpcs3_spu_runtime_cache_test as cache
import rpcs3_texture_hash_reuse_test as texture
import rpcs3_texture_hash_reuse_benchmark as hash_benchmark

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = 'docs/evidence/rpcs3-runtime-refinement-20261029'
HISTORY = ROOT / 'docs/evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/preflight'
EDGES = ROOT / 'test/native/rpcs3_refinement_timer_edges.inc'
PATHS = (timer.CPP, cache.COMPAT, descriptor.SOURCE[0], texture.HEADER)
CASES = ('timer', 'descriptor', 'hash', 'hash-benchmark', 'lookup', 'codegen')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def timer_program(source, baseline):
    code = timer.harness(source, baseline)
    anchor = 'int main() {\n'
    assert code.count(anchor) == 1
    code = code.replace(anchor, EDGES.read_text() + '\n' + anchor +
                        '    const u64 edge_cases=arithmetic_edges();\n')
    anchor = '<<",\\"callbacksWhileLocked\\":0'
    assert code.count(anchor) == 1
    return code.replace(anchor, '<<",\\"arithmeticEdgeCases\\":"<<edge_cases\n        ' + anchor)


def scope(source, baseline):
    source, baseline = Path(source), Path(baseline)
    result = timer.scope_proof(source, baseline)
    assert result['changedBodies']['baseline']['mask'] == result['changedBodies']['candidate']['mask']
    sig = 'bool command_buffer::update_descriptor_binding_cache('
    before, after = ((tree / descriptor.SOURCE[0]).read_text() for tree in (baseline, source))
    assert before.replace(descriptor.braced(before, sig), '@HELPER@') == after.replace(descriptor.braced(after, sig), '@HELPER@')
    a, b = ((tree / texture.HEADER).read_text() for tree in (baseline, source))
    sig = 'inline bool lookup('
    assert a.replace(texture.braced(a, sig), '@LOOKUP@') == b.replace(texture.braced(b, sig), '@LOOKUP@')
    assert ' || stored_epoch != epoch' in a and 'if (stored_epoch != epoch)' in b
    assert b.count('compare_exchange_strong') == 1
    for path in set(descriptor.SOURCE[1:] + descriptor.SUPPORT + list(texture.SOURCE[:1]) + texture.SUPPORT):
        assert (source / path).read_bytes() == (baseline / path).read_bytes(), path
    old, new = (sha((tree / timer.CPP).read_bytes()) for tree in (baseline, source))
    assert (source / cache.COMPAT).read_text().replace(new, old, 1) == (baseline / cache.COMPAT).read_text()
    return result


def programs(name, source, baseline):
    if name == 'timer':
        return {'functional': timer_program(source, baseline), 'timing': timer.timing_program(source, baseline)}
    if name == 'descriptor':
        return {label: descriptor.harness(tree) for label, tree in [('baseline', baseline), ('candidate', source)]}
    if name in ('hash', 'hash-benchmark'):
        helper = texture if name == 'hash' else hash_benchmark
        return {label: helper.harness(tree, True) for label, tree in [('baseline', baseline), ('candidate', source)]}
    if name == 'lookup':
        return {label: lookup_program(tree) for label, tree in [('baseline', baseline), ('candidate', source)]}
    if name == 'codegen':
        proof = codegen_proof(source, baseline)
        return {'script': cache.cmake_script(source, baseline, proof)}
    raise ValueError(name)


def expected(name, source, baseline):
    scope(source, baseline)
    deps = set(PATHS)
    for module in (descriptor, timer, texture):
        deps.update(module.SOURCE)
        deps.update(module.SUPPORT)
    code = programs(name, source, baseline)
    return dict(sourceSHA256={p: sha((source / p).read_bytes()) for p in sorted(deps)},
                baselineSHA256={p: sha((baseline / p).read_bytes()) for p in sorted(deps)},
                programSHA256={k: sha(v.encode()) for k, v in code.items()},
                scriptSHA256=sha(Path(__file__).read_bytes()),
                timerEdgesSHA256=sha(EDGES.read_bytes()))


def codegen_proof(source, baseline):
    scope(source, baseline)
    old_alias, new_alias = (cache.aliases((tree / cache.COMPAT).read_text()) for tree in (baseline, source))
    cmake = (source / cache.CMAKE).read_text()
    assert cmake == (baseline / cache.CMAKE).read_text()
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    inputs, names, ids, rawids, changed = {}, {}, {}, {}, set()
    for kind in ('PPU', 'SPU'):
        names[kind] = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S).group(1).split()
        oldparts, newparts, rawparts = [], [], []
        for name in names[kind]:
            external = name.endswith('/AArch64FrameLowering.cpp')
            if external:
                old = new = manifest['llvm_aarch64_ghc_patch']['postimage_sha256']
            else:
                old, new = (sha((tree / 'rpcs3/Emu' / name).read_bytes()) for tree in (baseline, source))
            if old != new:
                changed.add(name)
            inputs[name] = dict(baselineSHA256=old, sourceSHA256=new, externalManifestPostimage=external)
            oldparts.append(f'{name}:{old_alias.get((name, old), old)};')
            newparts.append(f'{name}:{new_alias.get((name, new), new)};')
            rawparts.append(f'{name}:{old_alias.get((name, new), new)};')
        old_id = sha(''.join(oldparts).encode())[:16]
        ids[kind] = sha(''.join(newparts).encode())[:16]
        rawids[kind] = sha(''.join(rawparts).encode())[:16]
        assert ids[kind] == old_id == cache.KNOWN_IDS[kind]
    assert len(inputs) == 41 and changed == {'Cell/SPUThread.cpp'}
    assert rawids['SPU'] != ids['SPU']
    return dict(inputs=inputs, sourceLists=names, codegen=ids, withoutUpdatedAlias=rawids,
                alias=dict(actualSHA256=sha((source / timer.CPP).read_bytes())),
                runtimeScope=timer.scope_proof(source, baseline), physicalCodegenInputs=40,
                externalLLVMBackendMaterialized=False)


def lookup_program(tree):
    header = (tree / texture.HEADER).read_text().replace('#pragma once', '')
    # This isolated lookup harness does not compile the production callers
    # using these policy constants; keep Clang's -Werror active everywhere.
    for declaration in (
        'constexpr std::uint32_t min_bytes = 64u << 10;',
        'constexpr std::size_t max_sequence = 2048;',
        'constexpr std::size_t lookahead = 64;',
    ):
        assert header.count(declaration) == 1
        header = header.replace(declaration, '[[maybe_unused]] ' + declaration)
    anchor = '\tconst std::uint64_t stored_hash = slot.hash.load(std::memory_order_acquire);'
    assert header.count(anchor) == 1
    # A writer advances the epoch precisely between the reader's epoch and
    # payload loads. This test-only scheduling hook does not replace any read.
    header = header.replace(anchor, '\tif (before_payload) { auto fn=std::move(before_payload); before_payload={}; fn(); }\n' + anchor)
    return '''#include <cassert>
#include <chrono>
#include <functional>
#include <iostream>
#include <utility>
#include <vector>
std::function<void()> before_payload;
''' + header + '''
namespace tp=rpcs3::ios::texture_prehash;
int main(int argc,char** argv) {
    constexpr std::uint32_t addr=0x10000,len=0x10000;
    std::uint64_t out=0;
    tp::publish(addr,len,10,111);
    assert(tp::lookup(addr,len,10,out) && out==111);
    before_payload=[&]{tp::publish(addr,len,11,222);};
    assert(!tp::lookup(addr,len,10,out));
    assert(tp::lookup(addr,len,11,out) && out==222);
    assert(!tp::lookup(addr,len+1,11,out));
    tp::table[tp::slot_of(tp::make_key(addr,len))].seq.fetch_add(1);
    assert(!tp::lookup(addr,len,11,out));
    tp::table[tp::slot_of(tp::make_key(addr,len))].seq.fetch_add(1);
    std::cout<<"{\\"passed\\":true,\\"interleavedEpochRejected\\":true,\\"samples\\":[";
    if(argc==2 && std::string_view(argv[1])=="--benchmark") {
        std::uint64_t sink=0;
        for(unsigned mode=0;mode<3;++mode) for(unsigned sample=0;sample<7;++sample) {
            auto start=std::chrono::steady_clock::now();
            for(unsigned i=0;i<2000000;++i) {
                auto epoch=std::uint64_t{mode==1?12u:11u};
                auto address=std::uint32_t{mode==2?addr+1:addr};
                asm volatile("" : "+r"(epoch),"+r"(address) : : "memory");
                sink+=tp::lookup(address,len,epoch,out)?out:1;
            }
            auto elapsed=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/2000000;
            if(mode || sample) std::cout<<',';
            std::cout<<"{\\"mode\\":"<<mode<<",\\"nanoseconds\\":"<<elapsed<<'}';
        }
        std::cout<<"],\\"sink\\":"<<sink;
    } else std::cout<<']';
    std::cout<<"}\\n";
}
'''


def validate(name, result):
    if name == 'timer':
        r = result['functional']
        assert r['passed'] and r['assertionsActive'] and r['matrixCases'] == 210
        assert r['arithmeticEdgeCases'] == 1792 and r['callbacksWhileLocked'] == 0
        assert r['baselineNonemptyErases'] == r['candidateNonemptyErases'] == 277
        assert r['baselineDueAllocations'] == r['candidateDueAllocations'] == 277
        assert r['baselineShiftedSlots'] == r['candidateShiftedSlots'] == 0
        assert r['notifications'] == 2172 and r['obsoleteTokensRejected'] == 6145
        assert r['firstAllocationFailureCases'] == 2 and r['reentrantRetainedUntilCallbackReturned']
    elif name == 'descriptor':
        expected = json.loads((HISTORY / 'descriptor-bind-plain-result.json').read_bytes())['results']['candidate-ios']
        for r in result.values():
            assert r['mismatches'] == 0 and r['cases'] == expected['cases']
            assert r['commandBufferBytes'] == expected['commandBufferBytes']
            for b in r['benchmark']:
                old = next(x for x in expected['benchmark'] if x['name'] == b['name'])
                assert (b['calls'],b['checksum'],b['operations']) == (old['calls'],old['checksum'],old['operations'])
    elif name == 'hash':
        old = json.loads((HISTORY / 'texture-hash-reuse-plain-result.json').read_bytes())['candidate']
        for r in result.values():
            for key, value in old.items():
                if key in ('compilerFlags','benchmarks','stressAcceptedMatches'):
                    continue
                assert r[key] == value, (key,r[key],value)
            assert r['stressAcceptedMatches'] > 0
    elif name == 'lookup':
        assert all(r['passed'] and r['interleavedEpochRejected'] for r in result.values())
    elif name == 'codegen':
        cache.verify_counts(result)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('--baseline', required=True, type=Path)
    ap.add_argument('--case', required=True, choices=CASES)
    ap.add_argument('--compiler', default=os.environ.get('CXX','g++'))
    ap.add_argument('--sanitizer', choices=('address,undefined','thread'), default='')
    ap.add_argument('--benchmark', action='store_true')
    ap.add_argument('--cmake', default='cmake')
    ap.add_argument('--report', type=Path, required=True)
    a = ap.parse_args()
    assert not (a.sanitizer and a.benchmark)
    assert a.sanitizer != 'thread' or a.case == 'hash'
    source, baseline = a.source.resolve(), a.baseline.resolve()
    identity = expected(a.case, source, baseline)
    code = programs(a.case, source, baseline)
    compiler = shlex.split(a.compiler)
    flags = ['-std=c++20','-O1' if a.sanitizer else '-O3','-g','-Wall','-Wextra','-Werror','-UNDEBUG','-pthread','-DRPCS3_IOS=1']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot',sdk]
    if a.sanitizer:
        flags += ['-fsanitize='+a.sanitizer,'-fno-omit-frame-pointer']
        if platform.system() == 'Linux':
            flags += ['-fno-pie','-no-pie']
    env = dict(os.environ,ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',UBSAN_OPTIONS='halt_on_error=1',TSAN_OPTIONS='halt_on_error=1')
    result = {}
    with tempfile.TemporaryDirectory(prefix='rpcs3-refinement-') as directory:
        work = Path(directory)
        for label, text in code.items():
            if a.case == 'codegen':
                script = work/'test.cmake'; script.write_text(text)
                out = subprocess.check_output([a.cmake,'-P',str(script)],stderr=subprocess.STDOUT,text=True)
                result = {m:dict(re.findall(m+r'_(PPU|SPU)=([a-f0-9]{16})',out)) for m in ('baseline','candidate','unaliased','future')}
                result.update(passed=True,wrongPathAndFutureRejected='wrong_path_and_future_rejected=1' in out,cmakeScriptInvocations=1,coreConfigured=False)
                continue
            if label == 'timing' and not a.benchmark:
                continue
            cpp,exe = work/(label+'.cpp'),work/label
            cpp.write_text(text)
            subprocess.run(compiler+flags+['-I'+str(source/'rpcs3'),'-I'+str(source),str(cpp),'-o',str(exe)],check=True)
            argv = [str(exe)]+(['--benchmark'] if a.benchmark and a.case in ('descriptor','lookup') else [])
            if a.case == 'hash-benchmark':
                continue
            run = subprocess.run(argv,capture_output=True,text=True,env=env,timeout=180)
            assert run.returncode == 0 and not run.stderr,(label,run.returncode,run.stdout,run.stderr)
            result[label] = json.loads(run.stdout)
        if a.case == 'hash-benchmark':
            assert not a.sanitizer
            for size in hash_benchmark.SIZES:
                for kind,pattern in enumerate(hash_benchmark.PATTERNS):
                    pair = dict(bytes=size,pattern=pattern,baseline=[],candidate=[])
                    for series in range(7):
                        for label in (('baseline','candidate') if series%2==0 else ('candidate','baseline')):
                            out = json.loads(subprocess.check_output([str(work/label),str(size),str(kind)],text=True,env=env,timeout=60))
                            assert out['passed'] and out['workerHashesDuringTiming'] == 0
                            pair[label].append(out['nsPerValidation'])
                    result.setdefault('comparisons',[]).append(pair)
    validate(a.case,result)
    assert identity == expected(a.case,source,baseline)
    report = dict(passed=True,case=a.case,**identity,results=result,compilerFlags=flags,
        compiler=subprocess.check_output(compiler+['--version'],text=True).splitlines()[0],
        sanitizer=a.sanitizer,benchmark=a.benchmark,host=dict(system=platform.system(),machine=platform.machine()),
        physicalDeviceTested=False,gameplayMeasured=False,gpuExecuted=False,coreBuilt=False,
        tsanSuppressions=[],leakSanitizer=False)
    if a.case == 'codegen':
        report['codegenProof'] = codegen_proof(source,baseline)
        report['cmake'] = subprocess.check_output([a.cmake,'--version'],text=True).splitlines()[0]
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,case=a.case,sanitizer=a.sanitizer,report=str(a.report))))


if __name__ == '__main__':
    main()
