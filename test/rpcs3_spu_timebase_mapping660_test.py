#!/usr/bin/env python3
"""Host test of REWINDBOX_SPU_TIMEBASE_MAPPING_660: SPU LLVM blocks that read the decrementer link spu_timebase_offs.

Since Build 481 (NEOSTATION_BUILD481_SPU_OBJECT_CACHE_V1) the fast SPU_RdDec path of the SPU LLVM recompiler loads the
timebase offset through an external global named spu_timebase_offs instead of a baked host address, so that its objects
can be cached. The name was mapped to g_timebase_offs once, in spu_llvm_recompiler::init(); but compile() calls
m_engine->clearAllGlobalMappings() before building every module, and nothing mapped the name again. When a block that
reads the decrementer was linked, the name was therefore unresolved by the engine, MemoryManager2::findSymbol found no
process symbol of that name and returned make_null_function(): the block loaded 8 bytes of a stub's code as the offset,
so its decrementer value differed from spu_thread's C++ read by a per-boot constant.

Core 660 maps the name again in the RdDec emitter, right before the load, for the module being built (an IR cache hit
builds the same IR before linking its object). A direct cache hit (REWINDBOX_SPU_DIRECT_OBJECT_HIT_660) builds no IR:
it clears the mappings once in its own block, before try_add_minimal_object, and binds spu_timebase_offs through its
direct_bindings() row, which is the same expression. The IR and the emitted objects are unchanged; exact aliases in
JITCacheCompatibility.cmake keep the SPU codegen identity (test/rpcs3_core660_codegen_test.py).

This test:
- audits the real SPULLVMRecompiler.cpp of Core 660 and Core 659: in 660 every load of spu_timebase_offs is preceded, in
  the same block, by its mapping, and no statement between them touches the engine mappings; the direct cache-hit block
  clears once, before its link, and its table binds spu_timebase_offs to g_timebase_offs; in 659 the only mapping is the
  one in init(), before the clear of compile(), and there is no direct block;
- checks, in both trees, that compile() and compile_interpreter() clear the mappings before building IR, and that the
  memory manager's last resort for an unresolved name is make_null_function (the defect's path);
- runs test/native/rpcs3_spu_timebase_mapping660_llvm.cpp against the host libLLVM (MCJIT): a name mapped once is gone
  for a module linked after clearAllGlobalMappings() (the 659 order) and resolves again when mapped after the clear (the
  660 order). Without a host libLLVM this part is reported as not run, never as passed.
Host model and LLVM proof only; no iPhone, timing or gameplay claim.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPU = 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp'
JIT = 'Utilities/JITLLVM.cpp'
PROOF = ROOT / 'test/native/rpcs3_spu_timebase_mapping660_llvm.cpp'
MARK = 'REWINDBOX_SPU_TIMEBASE_MAPPING_660'
MAP = 'm_engine->updateGlobalMapping("spu_timebase_offs", reinterpret_cast<u64>(&g_timebase_offs));'
LOAD = 'm_module->getOrInsertGlobal("spu_timebase_offs", get_type<u64>())'


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def read(tree: Path, name: str) -> str:
    return (tree / name).read_text(encoding='utf-8', errors='surrogateescape').replace('\r\n', '\n')


def audit(tree: Path, candidate: bool) -> dict:
    spu, jit = read(tree, SPU), read(tree, JIT)
    lines = spu.splitlines()
    loads = [i for i, line in enumerate(lines) if LOAD in line]
    maps = [i for i, line in enumerate(lines) if 'updateGlobalMapping("spu_timebase_offs"' in line]
    clears = [i for i, line in enumerate(lines) if 'm_engine->clearAllGlobalMappings();' in line]
    require(len(loads) == 1, 'one load of spu_timebase_offs')
    # REWINDBOX_SPU_DIRECT_OBJECT_HIT_660: the direct cache-hit link clears once more, inside its own block, before
    # try_add_minimal_object; its spu_timebase_offs binding is the direct_bindings() row (no IR, so no emitter mapping).
    direct_begin = [i for i, line in enumerate(lines) if 'REWINDBOX_SPU_DIRECT_OBJECT_HIT_660 DIRECT BEGIN' in line]
    direct_end = [i for i, line in enumerate(lines) if 'REWINDBOX_SPU_DIRECT_OBJECT_HIT_660 DIRECT END' in line]
    if candidate:
        require(len(direct_begin) == len(direct_end) == 1 and direct_begin[0] < direct_end[0], 'one direct cache-hit block')
        direct_clears = [i for i in clears if direct_begin[0] < i < direct_end[0]]
        require(len(direct_clears) == 1, 'one clear in the direct block')
        link = [i for i in range(direct_clears[0], direct_end[0]) if 'try_add_minimal_object(' in lines[i]]
        require(len(link) == 1, 'the direct clear precedes the direct link')
        require(spu.count('{"spu_timebase_offs", reinterpret_cast<u64>(&g_timebase_offs)},') == 1, 'the direct table binds spu_timebase_offs')
    else:
        require(not direct_begin and not direct_end, 'Core 659 has no direct cache-hit block')
        direct_clears = []
    clears = [i for i in clears if i not in direct_clears]
    require(len(clears) == 2, 'compile() and compile_interpreter() each clear the mappings')
    # init() maps the name once, before any compile() clear in runtime order (init runs at construction).
    init_at = spu.index('void init() override')
    init_map = [i for i in maps if lines[i].strip() == MAP and spu.index(lines[i]) > init_at and i < clears[0]]
    require(len(init_map) == 1, 'the init() mapping of spu_timebase_offs')
    # Both clears precede IR construction in their function: compile() clears right after its admission block.
    compile_at = spu.index('spu_function_t compile(spu_program&& _func) override')
    ir_from = spu.index('REWINDBOX_SPU_DIRECT_OBJECT_HIT_660 DIRECT END', compile_at) if candidate else compile_at
    require(spu.index('m_engine->clearAllGlobalMappings();', ir_from) < spu.index('m_ir->SetInsertPoint', ir_from),
            'compile() clears the mappings before building IR')
    # The memory manager's last resort for an unresolved name: make_null_function (no error, a stub).
    find = jit[jit.index('llvm::JITSymbol findSymbol(const std::string& name) override'):]
    find = find[:find.index('\n\t}\n')]
    require('RTDyldMemoryManager::getSymbolAddress(name)' in find and 'addr = make_null_function(name);' in find,
            'MemoryManager2::findSymbol ends in make_null_function')
    load = loads[0]
    if candidate:
        emitter = [i for i in maps if i not in init_map]
        require(len(emitter) == 1 and lines[emitter[0]].strip() == MAP, 'one mapping in the RdDec emitter')
        between = lines[emitter[0] + 1:load]
        require(emitter[0] < load and all('GlobalMapping' not in line for line in between) and len(between) <= 1,
                'the mapping immediately precedes the load, nothing between them touches the mappings')
        require(MARK in '\n'.join(lines[max(0, emitter[0] - 8):emitter[0]]), MARK + ' marks the mapping')
    else:
        require(maps == init_map and MARK not in spu, 'Core 659: the only mapping is the init() one (the defect)')
    return {'loads': len(loads), 'mappings': len(maps), 'clears': len(clears), 'direct_block_clears': len(direct_clears),
            'load_line': load + 1, 'mapped_after_clear_for_the_loading_module': candidate}


def llvm_proof(work: Path, cxx: str) -> dict:
    libraries = sorted(set(glob.glob('/usr/lib/x86_64-linux-gnu/libLLVM.so.*') + glob.glob('/usr/lib/llvm-*/lib/libLLVM.so.*')))
    libraries = [lib for lib in libraries if re.search(r'libLLVM\.so\.\d+(\.\d+)?$', lib)]
    if not libraries:
        return {'run': False, 'reason': 'no host libLLVM shared library'}
    results = {}
    for library in libraries:
        version = re.search(r'libLLVM\.so\.(\d+)', library).group(1)
        if version in results:
            continue
        binary = work / f'timebase-map-llvm{version}'
        built = subprocess.run([cxx, '-std=c++20', '-O1', '-rdynamic', str(PROOF), '-o', str(binary), library],
                               capture_output=True, text=True)
        if built.returncode != 0:
            results[version] = {'built': False, 'stderr': built.stderr[-600:]}
            continue
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
        results[version] = dict(json.loads(run.stdout.strip().splitlines()[-1]), built=True, exit=run.returncode)
    ran = {v: r for v, r in results.items() if r.get('built')}
    require(ran, 'the LLVM proof builds against no host libLLVM: ' + json.dumps(results))
    for version, r in ran.items():
        require(r['exit'] == 0 and r['mapped_no_clear'] == r['cell'] and r['after_clear'] == r['decoy'] and
                r['after_clear_remap'] == r['cell'],
                f'LLVM {version}: the mapping did not behave as the defect and its fix require: ' + json.dumps(r))
    return {'run': True, 'llvm': ran}


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--candidate', type=Path, required=True, help='Core 660 tree')
    parser.add_argument('--control', type=Path, required=True, help='Core 659 tree')
    parser.add_argument('--cxx', default=shutil.which('g++') or 'c++')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'candidate': audit(args.candidate.resolve(), True), 'control': audit(args.control.resolve(), False)}
    with tempfile.TemporaryDirectory(prefix='timebase-660-') as temporary:
        report['llvm_proof'] = llvm_proof(Path(temporary), args.cxx)
    report.update(result='passed', physical_device_tested=False, timing_claimed=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: Core 660 maps spu_timebase_offs for the module that loads it (Core 659: only before the clear); LLVM proof ' +
          (json.dumps({v: r['after_clear'] for v, r in report['llvm_proof']['llvm'].items()}) if report['llvm_proof']['run']
           else 'not run: ' + report['llvm_proof']['reason']))


if __name__ == '__main__':
    main()
