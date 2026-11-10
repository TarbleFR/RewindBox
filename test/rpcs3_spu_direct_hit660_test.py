#!/usr/bin/env python3
"""REWINDBOX_SPU_DIRECT_OBJECT_HIT_660: host evidence for the SPU cache-hit path that links a cached
object without building its IR.

Usage: spu_direct_hit660_test.py [--control TREE] [--candidate TREE] [--report FILE]

Executed (g++ -std=c++20 -fsanitize=address,undefined, -Werror):
 1. the real classifier header rpcs3/ios/IOSSpuObjectBindings.h of the candidate, against the real
    binding names regenerated from the candidate's call sites (accept/reject cases of the synthesis,
    copy_failed, the per-reason fallback notice limit);
 2. the REAL binding table (its 27 rows, a function-local static) and the REAL helper region of the
    candidate SPULLVMRecompiler.cpp, next to stand-ins with the real declarations of what the rows name:
    every row is evaluated and equals what its IR-path call sites map; the table is evaluated once per
    process; the helper binds, regenerates the patchpoint names, reports the offending symbol as a copy
    and makes no stub; direct_object_patchpoints() makes them in ascending number; a swapped row fails;
 3. the lifted PUTLLC16_fail / PUTLLC0_fail / spu_memcpy helpers of the candidate against the lambdas
    of the control tree, on the same inputs;
 8. the REAL try_add_minimal_object (add and finalize in one run_recoverable_llvm) and try_fin bodies of
    the candidate JITLLVM.cpp with the real held_object_bytes: added, refused, fatal while adding, fatal
    while finalizing, each equal to the reviewed two-call sequence, with one worker handoff instead of
    two; two plausible mistakes fail;
 9. llc-18 aarch64-unknown-linux-android PIC objects (small and large code model) of an SPU-shaped module
    and four mutations, their readelf symbols through the real classifier.
Static (both trees):
 4. the binding table of the candidate is the block regenerated from every call("name", expr) and
    updateGlobalMapping("name", expr) site outside compile_interpreter (ARCH_X64-only sites excluded);
    the control tree's sites map to the same names and the same expressions, the six lambdas aside,
    which are lifted to named statics whose bodies are byte-equal (uniform tab shift);
 5. the candidate SPULLVMRecompiler.cpp minus its marked insertions equals the control tree with the
    six lambdas lifted mechanically; JITLLVM.cpp differs only inside try_add_minimal_object();
 6. the direct block: place; order of classification, copy, copy_failed, stubs, clear, merged
    add + finalize, entry by getFunctionAddress, publication equal to the IR path's, fallback notice;
 7. codegen identity: the changed codegen inputs are exactly SPULLVMRecompiler.cpp and JITLLVM.cpp,
    each with one exact alias to the effective hash of its control file, and the recomputed
    identities are PPU a987639e9f838d1c / SPU 477a3fa442d27917 for both trees;
10. no table name and no "-pp-" name gets a body, an initializer or an internal/private linkage in
    SPULLVMRecompiler.cpp or CPUTranslator.h (every definition step traced to its symbol's name family),
    with five mutations that must fail.
No MCJIT, CMake or iPhone is involved (llc 18 only generates the objects of 9); nothing here is device evidence.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import rpcs3_spu_bindings_extract660 as bx  # noqa: E402

LLVM = 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp'
JIT = 'Utilities/JITLLVM.cpp'
HEADER = 'rpcs3/ios/IOSSpuObjectBindings.h'
COMPAT = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'
CMAKE = 'rpcs3/Emu/CMakeLists.txt'
MARK = 'REWINDBOX_SPU_DIRECT_OBJECT_HIT_660'
DELIVERED = {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}
CXX = shutil.which('g++')  # --cxx overrides it (the Apple host tests pass clang++)
FLAGS = ['-std=c++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-fsanitize=address,undefined',
         '-fno-sanitize-recover=all', '-fno-omit-frame-pointer']


def module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def read(tree: Path, name: str) -> str:
    raw = (tree / name).read_bytes()
    assert b'\r' not in raw, name + ' must stay LF'
    return raw.decode('utf-8')


def braced_text(text: str, marker: str, start: int = 0) -> str:
    begin = text.index(marker, start)
    a, b = bx.braced(text, begin)
    return text[a:b]


def body_of(text: str, marker: str) -> str:
    """The braces of the definition that starts at marker, inclusive."""
    begin = text.index(marker)
    a, b = bx.braced(text, begin)
    return text[text.index('{', begin):b]


def run(command, **kwargs):
    return subprocess.run([str(c) for c in command], check=True, capture_output=True, text=True, timeout=600, **kwargs)


def build_and_run(source: str, work: Path, name: str, includes: list[Path], extra: list[str] | None = None) -> str:
    cpp = work / f'{name}.cpp'
    cpp.write_text(source)
    exe = work / name
    run([CXX, *FLAGS, *(extra or []), *[f'-I{inc}' for inc in includes], cpp, '-o', exe])
    return run([exe]).stdout


def fails_to_build_or_run(source: str, work: Path, name: str, includes: list[Path], extra: list[str] | None = None) -> bool:
    try:
        build_and_run(source, work, name, includes, extra)
    except subprocess.CalledProcessError:
        return True
    return False


# ---------------------------------------------------------------- lambdas and their lifted statics
LAMBDAS = [
    # binding name, control header line, function the lambda sits in, lifted name, return, params, call-site expression
    ('PUTLLC16_fail', '\t\tstatic const auto on_fail = [](spu_thread* _spu, u32 addr)\n', 'putllc16_pattern',
     'exec_putllc16_fail', 'void', 'spu_thread* _spu, u32 addr', '+on_fail'),
    ('PUTLLC0_fail', '\t\tstatic const auto on_fail = [](spu_thread* _spu, u32 addr)\n', 'putllc0_pattern',
     'exec_putllc0_fail', 'void', 'spu_thread* _spu, u32 addr', '+on_fail'),
    ('spu_putllc16_rsx_res', '\t\t\tconst auto success = call("spu_putllc16_rsx_res", +[](spu_thread* _spu, u32 ls_dst, u32 lsa, u32 eal, u32 notify) -> bool\n',
     'putllc16_pattern', 'exec_putllc16_rsx_res', 'bool', 'spu_thread* _spu, u32 ls_dst, u32 lsa, u32 eal, u32 notify', None),
    ('wait_on_spu_channel', '\t\tauto wait_on_channel = [](spu_thread* _spu, spu_channel* ch, u32 is_read) -> u32\n', 'wait_rchcnt',
     'exec_wait_on_channel', 'u32', 'spu_thread* _spu, spu_channel* ch, u32 is_read', '+wait_on_channel'),
    ('wait_spu_inbox', '\t\t\t\tauto wait_inbox = [](spu_thread* _spu, spu_channel_4_t* ch) -> u32\n', 'RCHCNT',
     'exec_wait_inbox', 'u32', 'spu_thread* _spu, spu_channel_4_t* ch', '+wait_inbox'),
    ('spu_memcpy', '\t\t\t\t\t\tauto spu_memcpy = [](u8* dst, const u8* src, u32 size)\n', 'WRCH',
     'exec_spu_memcpy', 'void', 'u8* dst, const u8* src, u32 size', '+spu_memcpy'),
]
FUNCTION_HEADS = {
    'putllc16_pattern': '\tvoid putllc16_pattern(const spu_program& /*prog*/, u64 pattern_info)\n',
    'putllc0_pattern': '\tvoid putllc0_pattern(const spu_program& /*prog*/, u64 pattern_info)\n',
    'wait_rchcnt': '\tllvm::Value* wait_rchcnt(u32 off, u32 inv = 0)\n',
    'RCHCNT': '\tvoid RCHCNT(spu_opcode_t op) //\n',
    'WRCH': '\tvoid WRCH(spu_opcode_t op) //\n',
}


def function_span(text: str, function: str) -> tuple[int, int]:
    begin = text.index(FUNCTION_HEADS[function])
    return bx.braced(text, begin)


def lambda_body(control: str, binding: str, header: str, function: str) -> tuple[str, int]:
    """Lambda body lines (from its '{' line to its closing brace line, closing as '}\\n') and indent."""
    fa, fb = function_span(control, function)
    at = control.index(header, fa)
    assert at < fb, binding
    depth = len(header) - len(header.lstrip('\t'))
    start = at + len(header)
    assert control.startswith('\t' * depth + '{\n', start), binding
    a, b = bx.braced(control, start)
    body = control[start:b] + '\n'
    tail = control[b:control.index('\n', b) + 1]
    assert tail in (';\n', ', m_thread, dest, _lsa, _eal, m_ir->getInt32(!info.no_notify));\n'), (binding, tail)
    return body, depth


def unshift(body: str, delta: int) -> str:
    out = []
    for line in body.splitlines(keepends=True):
        if line == '\n':
            out.append(line)
        else:
            assert line.startswith('\t' * delta), line
            out.append(line[delta:])
    return ''.join(out)


def lifted_definition(name: str, ret: str, params: str, body: str, origin: str) -> str:
    return (f'\t// {MARK}: the lambda of {origin}, lifted so that the direct\n'
            f'\t// cache-hit path binds the same function under the same name. Same body.\n'
            f'\tstatic {ret} {name}({params})\n' + body + '\n')


def lift(control: str) -> str:
    """The control file with the six lambdas lifted mechanically (what the candidate must equal once
    its other insertions are removed)."""
    text = control
    origins = {'spu_putllc16_rsx_res': 'putllc16_pattern (spu_putllc16_rsx_res)'}
    order = ['spu_putllc16_rsx_res', 'PUTLLC16_fail', 'PUTLLC0_fail', 'wait_on_spu_channel', 'wait_spu_inbox', 'spu_memcpy']
    specs = {spec[0]: spec for spec in LAMBDAS}
    for binding in order:
        _, header, function, name, ret, params, site = specs[binding]
        body, depth = lambda_body(text, binding, header, function)
        lifted = unshift(body, depth - 1)
        fa, fb = function_span(text, function)
        at = text.index(header, fa)
        if site is None:
            end = text.index('\n', text.index('}, m_thread, dest, _lsa, _eal', at)) + 1
            replacement = f'\t\t\tconst auto success = call("{binding}", &{name}, m_thread, dest, _lsa, _eal, m_ir->getInt32(!info.no_notify));\n'
            text = text[:at] + replacement + text[end:]
        else:
            end = text.index('\n', text.index('\t' * depth + '};\n', at)) + 1
            if text[end] == '\n':
                end += 1
            text = text[:at] + text[end:]
            fa, fb = function_span(text, function)
            segment = text[fa:fb]
            old = f'call("{binding}", {site},'
            assert segment.count(old) >= 1, (binding, old)
            text = text[:fa] + segment.replace(old, f'call("{binding}", &{name},') + text[fb:]
        head = text.index(FUNCTION_HEADS[function])
        text = text[:head] + lifted_definition(name, ret, params, lifted, origins.get(binding, function)) + text[head:]
    return text


# ---------------------------------------------------------------- marked insertions of the candidate
INCLUDES = ['#include "ios/IOSSpuObjectBindings.h" // REWINDBOX_SPU_DIRECT_OBJECT_HIT_660\n',
            '#include <llvm/Object/ObjectFile.h> // REWINDBOX_SPU_DIRECT_OBJECT_HIT_660\n',
            '#include <llvm/Support/MemoryBuffer.h> // REWINDBOX_SPU_DIRECT_OBJECT_HIT_660\n']
GUARD = '#if defined(RPCS3_IOS) && defined(ARCH_ARM64)\n'


def strip_insertions(candidate: str) -> tuple[str, dict]:
    text = candidate
    for include in INCLUDES:
        assert text.count(include) == 1, include
        text = text.replace(include, '', 1)
    # The table and its helper, one guarded block before compile().
    start = text.index(GUARD + bx.TABLE_BEGIN)
    end_mark = f'\t// {MARK} HELPER END\n#endif\n\n'
    end = text.index(end_mark, start) + len(end_mark)
    helper = text[start:end]
    text = text[:start] + text[end:]
    # The direct block of compile().
    dstart = text.index(GUARD + f'\t\t// {MARK} DIRECT BEGIN')
    dend_mark = f'\t\t// {MARK} DIRECT END\n#endif\n\n'
    dend = text.index(dend_mark, dstart) + len(dend_mark)
    direct = text[dstart:dend]
    text = text[:dstart] + text[dend:]
    return text, {'helper': helper, 'direct': direct}


# ---------------------------------------------------------------- 4. binding table
def audit_bindings(control: str, candidate: str) -> dict:
    csites, cdyn = bx.extract(control)
    nsites, ndyn = bx.extract(candidate)
    # Same call sites, line for line, in the same order; only the six lambda expressions change.
    assert [(s.name, s.kind, s.active) for s in csites] == [(s.name, s.kind, s.active) for s in nsites], 'site lists differ'
    lifted = {spec[0]: f'&{spec[3]}' for spec in LAMBDAS}
    changed = set()
    for old, new in zip(csites, nsites):
        if old.expr != new.expr:
            assert old.name in lifted and new.expr == lifted[old.name], (old, new)
            assert old.expr.startswith('+'), old
            changed.add(old.name)
        assert '[' not in new.expr and not new.expr.startswith('+'), ('lambda left in a call() argument', new)
    assert changed == set(lifted), changed
    # Every name has one expression, in both trees.
    ctable, ntable = bx.table(control), bx.table(candidate)
    assert set(ctable) == set(ntable)
    for name in ntable:
        assert ntable[name] == (ctable[name][0], lifted.get(name, ctable[name][1])), name
    # ARCH_X64-only sites: compiled out on iOS, and only spu_rotqby is X64-only as a name.
    inactive = {s.name for s in nsites if not s.active}
    assert inactive == {'spu_rotqby', 'spu_check_interrupts'}, inactive
    assert 'spu_rotqby' not in ntable and 'spu_check_interrupts' in ntable
    # The special mappings and notify_all are bound; interpreter-only names are not.
    for name in ('atomic_wait_engine::notify_all', 'spu_timebase_offs', 'spu_segment_base', 'spu_dispatcher', 'spu_memcpy'):
        assert name in ntable, name
    assert 'spu_interp_check' not in ntable
    # The generated block is exactly what the sites give.
    block_start = candidate.index(bx.TABLE_BEGIN)
    block = candidate[block_start:candidate.index(bx.TABLE_END, block_start) + len(bx.TABLE_END)]
    assert block == bx.emit(candidate), 'the binding table is not the block regenerated from the call sites'
    assert bx.TABLE_BEGIN not in control
    # Names that are not literals: the patchpoint name of tail_chunk(), the dead chunk patchpoint, fall<>.
    code = bx.blank_comments(candidate)
    lines = code.split('\n')
    kinds = []
    for line_no in ndyn:
        line = lines[line_no - 1]
        if 'updateGlobalMapping(ppname, reinterpret_cast<u64>(m_spurt->make_branch_patchpoint()))' in line:
            kinds.append('tail_chunk_pp')
        elif 'updateGlobalMapping(ppname, reinterpret_cast<u64>(m_spurt->make_branch_patchpoint(i / 4)))' in line:
            context = '\n'.join(lines[line_no - 4:line_no])
            assert 'if (false && g_cfg.core.spu_verification)' in context, 'chunk patchpoints must stay disabled'
            kinds.append('dead_chunkpp')
        elif line.strip() in ('call(name, F, m_thread, m_interp_op);', 'call(name, &exec_fall<F>, m_thread, m_ir->getInt32(op.opcode));'):
            kinds.append('fall')
        else:
            raise AssertionError(('unexpected non-literal binding', line_no, line))
    assert sorted(kinds) == ['dead_chunkpp', 'fall', 'fall', 'tail_chunk_pp'], kinds
    assert len(cdyn) == len(ndyn)
    assert not re.search(r'fall<\s*&|&spu_llvm_recompiler::fall|fall<spu_interpreter', code), 'fall<> gained a caller'
    assert 'fmt::format("%s-pp-%u", m_hash, m_pp_id++)' in candidate
    # Every function a table row names is compiled in the iOS ARM64 build.
    cond = bx.conditions(candidate)
    source_lines = candidate.split('\n')
    for name in sorted(set(re.findall(r'&(exec_\w+)', bx.emit(candidate)))):
        defs = [i + 1 for i, l in enumerate(source_lines) if re.search(r'static [\w:\[\]<> ]+\b' + name + r'\(', l)]
        assert len(defs) == 1 and cond[defs[0]][0], (name, defs)
    assert 'm_spurt->make_branch_patchpoint()));' in candidate
    return {'names': len(ntable), 'sites': len(nsites), 'x64_only_sites': sorted(inactive),
            'lifted_call_sites': sorted(changed), 'non_literal_sites': sorted(kinds)}


def audit_lambdas(control: str, candidate: str) -> dict:
    result = {}
    for binding, header, function, name, ret, params, site in LAMBDAS:
        body, depth = lambda_body(control, binding, header, function)
        delta = depth - 1
        head = f'\tstatic {ret} {name}({params})\n'
        assert candidate.count(head) == 1, head
        start = candidate.index(head) + len(head)
        lifted = candidate[start:bx.braced(candidate, start)[1]] + '\n'
        assert lifted == unshift(body, delta), name + ' body is not the lambda body'
        # Return type: explicit in the lambda header, or void when it returns no value.
        explicit = re.search(r'\) -> (\w+)\n$', header)
        assert (explicit.group(1) if explicit else 'void') == ret, name
        if not explicit:
            assert not re.search(r'return\s+[^;]', body), name
        assert header.count('(' + params + ')') == 1, name
        result[name] = {'binding': binding, 'tab_shift': delta, 'lines': body.count('\n'), 'sha256': sha(lifted.encode())}
    on16, on0 = result['exec_putllc16_fail']['sha256'], result['exec_putllc0_fail']['sha256']
    assert on16 != on0, 'the two on_fail lambdas differ (one blank line); each keeps its own lift'
    return result


# ---------------------------------------------------------------- 5/6. structure of the candidate
def audit_structure(control: str, candidate: str, control_jit: str, candidate_jit: str) -> dict:
    stripped, parts = strip_insertions(candidate)
    assert stripped == lift(control), 'SPULLVMRecompiler.cpp changes beyond the marked insertions and the lifts'
    direct = parts['direct']
    # Place: after the admission, before the trace and the IR build.
    admission = candidate.index('if (!*admission) return nullptr;')
    begin = candidate.index(direct)
    assert admission < begin < candidate.index('spu_log.trace("SPUCORE499 Building function') < candidate.index('m_engine->clearAllGlobalMappings();\n\n\t\t// Create LLVM module')
    assert candidate.index('spu_cached_object = jit_compiler::load_cached_object(') < begin
    # Condition, order, entry, failure handling.
    assert 'if (spu_cached_object && g_spu_llvm_compile_context && rpcs3::ios::spu_direct_hit::enabled.load(std::memory_order_relaxed))' in direct
    # Classification and names first, then the copy and its null check, only then the stubs (fix 3); one merged
    # add + finalize (one worker handoff, item 10); the entry by getFunctionAddress (fix 1); the fallback notice
    # only after every accepted return (fix 4).
    order = ['direct_object_bindings(*spu_cached_object.buffer, func.data.size(), direct_map, direct_pp_names, direct_offending)',
             'getMemBufferCopy(', 'if (!direct_object.buffer)', 'direct_reason = direct::reason::copy_failed;',
             'direct_object_patchpoints(direct_map, direct_pp_names);', 'm_engine->clearAllGlobalMappings();',
             'm_jit.try_add_minimal_object(std::move(direct_object), m_hash, direct_map, llvm_error)',
             'reinterpret_cast<spu_function_t>(m_jit.get_engine().getFunctionAddress(m_hash))', 'add_loc->compiled = fn;', 'return fn;',
             'direct_reason = direct::reason::add_rejected;', 'direct::stats().record_fallback(direct_reason);',
             'if (direct::should_log_fallback(direct_reason))',
             'spu_log.notice("SPUDIRECT660 fallback %s: %s (%s)", direct::reason_names[static_cast<usz>(direct_reason)], direct_offending, m_hash);',
             'llvm_error.clear();']
    code = bx.blank_comments(direct)
    positions = [code.index(item) for item in order]
    assert positions == sorted(positions), 'direct block order'
    for item in order[1:]:
        assert code.count(item) == 1, item
    for forbidden in ('m_size', 'm_pos', 'm_base', 'm_ir', 'm_module', 'm_pp_id', 'getGlobalValueAddress', 'm_jit.get(',
                      'getPointerToNamedFunction', 'getPointerToFunction', 'getSymbolAddress', 'try_fin', 'make_branch_patchpoint'):
        assert not re.search(r'\b' + re.escape(forbidden) + r'\b', code), forbidden
    assert code.count('getFunctionAddress') == 1
    # No log formatting on the accepted path: the no-entry error, the publication trace, the fallback notice.
    assert re.findall(r'spu_log\.(\w+)\(', code) == ['error', 'trace', 'notice'], re.findall(r'spu_log\.(\w+)\(', code)
    assert direct.count('return nullptr;') == 3  # add/finalize recovery failure, null entry, trampoline (as IR)
    assert direct.count('add_loc->cached = 0;') == 2
    assert 'fs::remove_file(spu_obj_cache + m_hash + ".obj.gz");' in direct
    # Publication: the IR path's tail without its spu_debug log, three tabs deeper.
    start = candidate.index('\t\t// Install unconditionally, possibly replacing existing one from spu_fast\n', candidate.index(f'{MARK} DIRECT END'))
    end = candidate.index('\t\treturn fn;\n', start) + len('\t\treturn fn;\n')
    tail = candidate[start:end]
    debug = ('\t\tif (g_cfg.core.spu_debug)\n\t\t{\n\t\t\tout.flush();\n\t\t\tfs::write_file(m_spurt->get_cache_path() + "spu-ir.log", '
             'fs::create + fs::write + fs::append, llvm_log);\n\t\t}\n\n')
    assert tail.count(debug) == 1
    expected = ''.join(('\t\t\t' + line if line.strip() and not line.startswith('#') else line)
                       for line in tail.replace(debug, '').splitlines(keepends=True))
    assert expected in direct, 'the direct publication is not the IR path publication'
    for item in ('jit_write_protect(false);', 'jit_write_protect(true);', 'asm("ISB");', 'asm("DSB ISH");', 'rebuild_ubertrampoline(func.data[0])',
                 'record_spu_block_compiled(', 'jit_phase::spu_object_load', 'spu_object_cache_event::hit'):
        assert item in direct, item
    helper = parts['helper']
    hb = helper.index('\trpcs3::ios::spu_direct_hit::reason direct_object_bindings(')
    allocation = helper.index('reinterpret_cast<u64>(m_spurt->make_branch_patchpoint())')
    for check in ('direct::classify(m_hash, symbols, names, direct::patchpoint_limit(guest_words))', 'return direct::reason::null_binding;',
                  'return direct::reason::malformed_patchpoint;', 'fmt::format("%s-pp-%u", m_hash, id)'):
        assert hb < helper.index(check) < allocation, check
    assert helper.count('make_branch_patchpoint') == 1
    bindings_body = body_of(helper, '\trpcs3::ios::spu_direct_hit::reason direct_object_bindings(')
    assert 'make_branch_patchpoint' not in bindings_body and 'direct_object_patchpoints' not in bindings_body, 'no stub before the copy'
    stubs = body_of(helper, '\tvoid direct_object_patchpoints(std::unordered_map<std::string, u64>& bindings, std::vector<std::string>& patchpoints)')
    assert 'reinterpret_cast<u64>(m_spurt->make_branch_patchpoint())' in stubs
    assert 'offending.assign(plan.offending.data(), plan.offending.size());' in bindings_body
    # The table is one function-local static (thread-safe initialization), evaluated once per process (fix 2).
    assert '\t\tstatic const std::array<direct_binding, ' in helper and '\t\treturn table;\n' in helper
    assert 'const auto& table = direct_bindings();' in bindings_body
    # The timebase mapping of the control tree is kept, after compile()'s clear in runtime order (RdDec emitter).
    timebase = '\t\t\t\tm_engine->updateGlobalMapping("spu_timebase_offs", reinterpret_cast<u64>(&g_timebase_offs));\n'
    assert timebase in control and timebase in candidate
    # build481 wiring rules that still hold for the candidate.
    for number, line in enumerate(candidate.splitlines(), 1):
        assert not ('reinterpret_cast<u64>' in line and 'm_ir->' in line), number
    assert candidate.index('m_engine->updateGlobalMapping("spu_timebase_offs"') < candidate.index('m_module->getOrInsertGlobal("spu_timebase_offs"')

    # JITLLVM.cpp: only the body of try_add_minimal_object.
    signature = 'bool jit_compiler::try_add_minimal_object(jit_cached_object object, const std::string& entry,'
    old, new = braced_text(control_jit, signature), braced_text(candidate_jit, signature)
    assert old != new and candidate_jit.replace(new, old, 1) == control_jit, 'JITLLVM.cpp changes outside try_add_minimal_object'
    for item in ('run_recoverable_llvm(', 'jit_minimal_object::add(*m_engine, buffer, entry, bindings, refused)', 'release_bytes.load(',
                 'llvm::MemoryBuffer::getMemBuffer(owner->getMemBufferRef(), false)', 'held_objects().hold(this, std::move(owner));',
                 'm_announcer->finalized(false)', 'm_announcer->finalized(true)', 'held_objects().release(this);', 'error.clear();'):
        assert item in new, item
    assert new.index('run_recoverable_llvm(') < new.index('held_objects().hold')
    # Item 10: add and finalize in ONE recoverable run; the finalize only after an add.
    newcode = bx.blank_comments(new)
    assert newcode.count('run_recoverable_llvm(') == 1 and newcode.count('m_engine->finalizeObject();') == 1
    run_body = braced_text(newcode, 'run_recoverable_llvm(')
    assert run_body.index('jit_minimal_object::add(') < run_body.index('if (added)') < run_body.index('m_engine->finalizeObject();')
    # try_fin (the IR path's finalize) is unchanged.
    assert braced_text(control_jit, 'bool jit_compiler::try_fin(std::string& error)') == braced_text(candidate_jit, 'bool jit_compiler::try_fin(std::string& error)')
    return {'stripped_equals_lifted_control': True, 'direct_block_lines': direct.count('\n'), 'helper_lines': helper.count('\n'),
            'try_add_minimal_object_sha256': {'control': sha(old.encode()), 'candidate': sha(new.encode())}}


# ---------------------------------------------------------------- 10. no SPU object defines a bound name (fix 6)
TRANSLATOR = 'rpcs3/Emu/CPU/CPUTranslator.h'
ANALYSER = 'rpcs3/Emu/Cell/SPUAnalyser.h'
STRFMT = 'Utilities/StrFmt.cpp'
POLICY = 'rpcs3/Emu/Cell/SPUObjectCachePolicy.h'
ORIGIN = re.compile(r'(getOrInsertFunction|getOrInsertGlobal)\s*\(')
NEW_GLOBAL = re.compile(r'new\s+(?:llvm::)?GlobalVariable\s*\(')
UNSUPPORTED = re.compile(r'\bFunction::Create\b|\bGlobalAlias::create\b|\bGlobalIFunc::create\b|\btakeName\s*\(|\bsetSection\s*\(|'
                         r'\bsetVisibility\s*\(|\bsetDSOLocal\s*\(|\bGlobalValue::\w+Linkage\b(?!.*(?:setLinkage|GlobalVariable))')


def statement_at(code: str, at: int) -> tuple[int, int]:
    start = max(code.rfind(';', 0, at), code.rfind('{', 0, at), code.rfind('}', 0, at)) + 1
    return start, code.index(';', at)


def name_family(code: str, expr: str, at: int, table: set[str], mnemonics: set[str]) -> tuple[bool, str]:
    """(may be a table or patchpoint name, description) of a symbol name expression at offset at."""
    expr = expr.strip()

    def pattern_family(pattern: str, args: list[str], suffixes: list[str]) -> tuple[bool, str]:
        if pattern == 'spu_%s' and args and args[0].strip() == 'g_spu_iname.decode(op)' and suffixes in ([], ['_%X']):
            hits = [n for n in table if re.fullmatch(r'spu_(?:' + '|'.join(sorted(mnemonics)) + r')(?:_[0-9A-F]+)?', n)]
            return bool(hits), 'spu_<MNEMONIC>[_<hex>]'
        literal = pattern.split('%', 1)[0]
        collides = (not literal or '-pp-' in pattern + ''.join(suffixes) or any(n.startswith(literal) for n in table) or
                    '__spu-0x'.startswith(literal) or literal.startswith('__spu-0x'))
        return collides, pattern + ''.join(suffixes)

    if re.fullmatch(r'"[^"\\]*"', expr):
        value = expr[1:-1]
        return value in table or '-pp-' in value, value
    if expr == 'm_hash':
        return False, '<entry>'
    if re.fullmatch(r'\w+', expr):
        decls = list(re.finditer(r'(?:const\s+)?std::string\s+' + expr + r'\s*=\s*fmt::format\(', code[:at]))
        if not decls:
            return True, expr
        decl = decls[-1]
        args, _ = bx.split_args(code, decl.end() - 1)
        if not re.fullmatch(r'"[^"\\]*"', args[0]):
            return True, expr
        suffixes = []
        for append in re.finditer(r'fmt::append\(\s*' + expr + r'\s*,', code[decl.end():at]):
            more, _ = bx.split_args(code, decl.end() + append.end() - len(append.group(0)) + append.group(0).index('('))
            if not re.fullmatch(r'"[^"\\]*"', more[1]):
                return True, expr
            suffixes.append(more[1][1:-1])
        if re.search(r'(?<![\w>.])' + expr + r'\s*(?:\+=|=(?!=))', code[decl.end():at]):
            return True, expr
        return pattern_family(args[0][1:-1], args[1:], suffixes)
    return True, expr  # {lame.data(), lame.size()}, iname, ...: any name a caller passes


def audit_local_names(texts: dict[str, str], table: set[str], analyser: str, strfmt: str, policy: str) -> dict:
    """No table name and no '-pp-' name gets a body, an initializer or InternalLinkage/PrivateLinkage in
    SPULLVMRecompiler.cpp or CPUTranslator.h. Every symbol a module creates (getOrInsertFunction,
    getOrInsertGlobal, new GlobalVariable) has a name family; every definition step (setLinkage,
    setInitializer, a BasicBlock in a function, set_function, an assignment to m_function or to a
    function's chunk/fn) is traced to the symbol it defines, and that symbol's family must be one that
    cannot be a table or patchpoint name. Anything the trace cannot follow fails."""
    iname = analyser[analyser.index('struct spu_iname'):]
    mnemonics = set(re.findall(r'NAME\((\w+)\);', iname[:iname.index('};')]))
    assert len(mnemonics) > 150 and all(m == m.upper() for m in mnemonics), len(mnemonics)
    alphabet = re.search(r'"([0-9A-Za-z]{57})"\[value % 57\]', strfmt).group(1)
    assert '-' not in alphabet
    suffix_body = braced_text(policy, 'inline std::string variant_suffix(bool use_tbl2, bool use_fma)')
    assert re.findall(r'"([^"]*)"', suffix_body) == ['-notbl2', '-nofma']
    report = {'mnemonics': len(mnemonics), 'origins': {}, 'definitions': 0}
    for name, text in texts.items():
        code = bx.blank_comments(text)
        assert not UNSUPPORTED.search(code.replace('llvm::GlobalValue::InternalLinkage', '').replace('GlobalValue::InternalLinkage', '')
                                      .replace('llvm::GlobalValue::PrivateLinkage', '').replace('llvm::GlobalVariable::PrivateLinkage', '')), \
            (name, 'a symbol construct the guard does not follow', UNSUPPORTED.search(code).group(0) if UNSUPPORTED.search(code) else '')
        if name == LLVM:
            # The entry: "__spu-0x%05x-%s" of a base57 hash, then the variant suffix only.
            writes = re.findall(r'(?<![\w>.])m_hash\s*(\+=|=(?!=)|\.clear\(\)|\.append\()|fmt::append\(\s*m_hash\s*,\s*("[^"]*")', code)
            assert writes == [('.clear()', ''), ('', '"__spu-0x%05x-%s"'), ('+=', '')], writes
            assert 'm_hash += rpcs3::spu::object_cache::variant_suffix(m_use_tbl2, m_use_fma);' in code
        origins = []
        for match in ORIGIN.finditer(code):
            args, _ = bx.split_args(code, match.end() - 1)
            colliding, family = name_family(code, args[0], match.start(), table, mnemonics)
            start, _ = statement_at(code, match.start())
            lhs = re.match(r'\s*(?:const\s+auto|auto|llvm::Function\s*\*|Function\s*\*)?\s*([\w.\->\[\]]+)\s*=(?!=)', code[start:match.start()])
            origins.append({'at': match.start(), 'receiver': lhs.group(1) if lhs else None, 'colliding': colliding, 'family': family})
        for match in NEW_GLOBAL.finditer(code):
            args, _ = bx.split_args(code, match.end() - 1)
            colliding, family = (False, '<unnamed>') if len(args) < 6 else name_family(code, args[5], match.start(), table, mnemonics)
            start, _ = statement_at(code, match.start())
            lhs = re.match(r'\s*(?:return\s+)?([\w.\->\[\]]+)?\s*=?', code[start:match.start()])
            origins.append({'at': match.start(), 'receiver': lhs.group(1) if lhs and '=' in code[start:match.start()] else None,
                            'colliding': colliding, 'family': family})
        report['origins'][name] = sorted({(o['family'], o['colliding']) for o in origins})

        def origin_of(receiver: str, at: int):
            """The symbol a receiver holds at offset at: nearest preceding assignment in the file."""
            if receiver in ('m_function', 'm_function_alias') or re.fullmatch(r'm_functions\[\w+\]\.chunk|m_finfo->chunk', receiver):
                return 'alias'
            assigned = [m for m in re.finditer(r'(?<![\w>.])' + re.escape(receiver) + r'\s*=(?!=)', code[:at])]
            if not assigned:
                return None
            rhs_start = assigned[-1].end()
            rhs = code[rhs_start:code.index(';', rhs_start)]
            for o in origins:
                if rhs_start <= o['at'] < rhs_start + len(rhs):
                    return o
            if re.match(r'\s*std::exchange\(m_finfo->fn, nullptr\)\)', rhs):
                return 'alias'
            return None

        definitions = []
        for m in re.finditer(r'([\w\]\)]+)\s*->\s*(setLinkage|setInitializer)\s*\(', code):
            definitions.append((m.group(1), m.start(), m.group(2)))
        for m in re.finditer(r'BasicBlock::Create\s*\(', code):
            args, _ = bx.split_args(code, m.end() - 1)
            if len(args) >= 3:
                definitions.append((args[2], m.start(), 'body'))
        for m in re.finditer(r'(?<![\w:])set_function\s*\(', code):
            args, _ = bx.split_args(code, m.end() - 1)
            if args[0] != 'llvm::Function* func':
                definitions.append((args[0], m.start(), 'set_function'))
        # Aliases: what m_function and the chunk/fn members of a function info can hold.
        for m in re.finditer(r'(?<![\w>.])m_function\s*=(?!=)\s*([^;]+);', code):
            if m.group(1).strip() not in ('func', 'nullptr'):
                definitions.append((m.group(1).strip(), m.start(), 'm_function'))
        for m in re.finditer(r'(?:\.|->)(chunk|fn)\s*=(?!=)\s*([^;]+);', code):
            value = m.group(2).strip()
            if not (m.group(1) == 'fn' and value == 'fn' and 'std::exchange(m_finfo->fn, nullptr)' in code[max(0, m.start() - 600):m.start()]):
                definitions.append((value, m.start(), m.group(1)))
        for receiver, at, kind in definitions:
            if receiver == 'func' and kind == 'body' and 'void set_function(llvm::Function* func)' in code[max(0, at - 400):at]:
                continue
            origin = origin_of(receiver, at)
            line = code.count('\n', 0, at) + 1
            assert origin is not None, (name, line, kind, receiver, 'definition the guard cannot trace')
            if origin != 'alias':
                assert not origin['colliding'], (name, line, kind, receiver, origin['family'], 'a table or patchpoint name gets a definition')
            report['definitions'] += 1
        for o in origins:
            if o['colliding'] and o['receiver'] is None:
                start, end = statement_at(code, o['at'])
                assert not re.search(r'setLinkage|setInitializer|BasicBlock::Create|set_function', code[start:end]), (name, 'inline definition')
    return report


def audit_wiring(tree: Path) -> dict:
    checks = {
        'rpcs3/Emu/system_config.h': ['cfg::_enum<ios_experimental_mode> spu_direct_object_hits{ this, "SPU Direct Object Hits", ios_experimental_mode::automatic };'],
        'rpcs3/ios/RPCS3IOSExperimentalPolicy.h': ['bool spu_direct_object_hits = false;'],
        'rpcs3/ios/IOSTitleLevers.h': ['constexpr bool wants_spu_direct_object_hits(std::string_view /*title_id*/) noexcept'],
        'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp': [
            '#include "IOSSpuObjectBindings.h" // REWINDBOX_SPU_DIRECT_OBJECT_HIT_660',
            'resolved.spu_direct_object_hits = arm64_default && resolve_mode(g_cfg.ios_experimental.spu_direct_object_hits,\n\t\trpcs3::ios::title_levers::wants_spu_direct_object_hits(title_id));',
            'rpcs3::ios::spu_direct_hit::enabled.store(resolved.spu_direct_object_hits, std::memory_order_relaxed);',
            'Resolved title policy 660: spu_direct_object_hits=%d'],
        'rpcs3/ios/RPCS3IOSSettings.cpp': ['GAME_SETTING("experimental.spu_direct_object_hits", "Experimental", "SPU",',
                                           'g_cfg.ios_experimental.spu_direct_object_hits, 0, 0, 0)'],
        'rpcs3/ios/RPCS3IOSPerformance.cpp': ['COREPROF SPUDIRECT660 session=%llu window=%llu enabled=%u direct=%llu',
                                              'rpcs3::ios::spu_direct_hit::stats().take_window()', '" fb_%s=%llu"'],
    }
    for name, needles in checks.items():
        text = read(tree, name)
        for needle in needles:
            assert text.count(needle) == 1, (name, needle)
    title = read(tree, 'rpcs3/ios/IOSTitleLevers.h')
    assert 'return true;' in title[title.index('wants_spu_direct_object_hits'):title.index('wants_spu_direct_object_hits') + 200]
    return {'files': sorted(checks)}


# ---------------------------------------------------------------- 7. codegen identity
def audit_identity(control: Path, candidate: Path) -> dict:
    c610 = module('c610', REPO / 'test/rpcs3_core610_codegen_test.py')
    c619 = module('c619', REPO / 'test/rpcs3_core619_codegen_test.py')
    inputs = c619.codegen_inputs(candidate)
    assert len(inputs) == 41, len(inputs)
    changed = sorted(name for name in inputs if not name.startswith('3rdparty/') and
                     (control / name).read_bytes() != (candidate / name).read_bytes())
    assert changed == [JIT, LLVM], changed
    assert (control / CMAKE).read_bytes() == (candidate / CMAKE).read_bytes(), 'identity recipe changed'
    old_table, new_table = c610.aliases(read(control, COMPAT)), c610.aliases(read(candidate, COMPAT))
    llvm_sha, jit_sha = sha((candidate / LLVM).read_bytes()), sha((candidate / JIT).read_bytes())
    old_llvm, old_jit = sha((control / LLVM).read_bytes()), sha((control / JIT).read_bytes())
    keys = {('Cell/SPULLVMRecompiler.cpp', llvm_sha), ('../../Utilities/JITLLVM.cpp', jit_sha)}
    assert set(new_table) - set(old_table) == keys, set(new_table) - set(old_table)
    # The control's own SPULLVMRecompiler.cpp alias, added by the timebase step (REWINDBOX_SPU_TIMEBASE_MAPPING_660),
    # names a file that no Core ships once this step replaces it: this step drops it; every other alias stays.
    timebase = 'REWINDBOX_SPU_TIMEBASE_MAPPING_660'
    dropped = ({('Cell/SPULLVMRecompiler.cpp', old_llvm)}
               if timebase in read(control, COMPAT) and timebase not in read(candidate, COMPAT) else set())
    assert set(old_table) - set(new_table) == dropped, set(old_table) - set(new_table)
    assert all(new_table[key] == value for key, value in old_table.items() if key not in dropped), 'an existing alias changed'
    assert new_table[('Cell/SPULLVMRecompiler.cpp', llvm_sha)] == old_table[('Cell/SPULLVMRecompiler.cpp', old_llvm)]
    assert new_table[('../../Utilities/JITLLVM.cpp', jit_sha)] == old_table[('../../Utilities/JITLLVM.cpp', old_jit)]
    compat_old, compat_new = read(control, COMPAT), read(candidate, COMPAT)
    assert compat_new.count(f'# {MARK}') == 2 and f'# {MARK}' not in compat_old
    cmake = read(candidate, CMAKE)
    result = {}
    for kind in ('PPU', 'SPU'):
        cand, _ = c610_identity(c610, candidate, cmake, new_table, kind)
        base, _ = c610_identity(c610, control, cmake, old_table, kind)
        without, _ = c610_identity(c610, candidate, cmake, old_table, kind)
        result[kind] = {'control': base, 'candidate': cand, 'candidate_without_660_aliases': without}
        assert base == cand == DELIVERED[kind], (kind, base, cand)
        assert without != DELIVERED[kind], kind + ' must depend on the new aliases'
    return {'changed_codegen_inputs': changed, 'codegen_inputs': len(inputs), 'dropped_aliases': sorted(f'{s} {h}' for s, h in dropped), 'aliases': {'SPULLVMRecompiler.cpp': [llvm_sha, new_table[('Cell/SPULLVMRecompiler.cpp', llvm_sha)]],
            'JITLLVM.cpp': [jit_sha, new_table[('../../Utilities/JITLLVM.cpp', jit_sha)]]}, 'identities': result}


def c610_identity(c610, tree: Path, cmake: str, table: dict, kind: str):
    # test/rpcs3_core616_codegen_test.py identity() without its module imports (same recipe).
    names = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S).group(1).split()
    payload, digests = '', {}
    for name in names:
        digest = c610.EXTERNAL[name] if name in c610.EXTERNAL else c610.sha((tree / 'rpcs3/Emu' / name).read_bytes())
        digests[name] = digest
        payload += name + ':' + table.get((name, digest), digest) + ';'
    return c610.sha(payload.encode())[:16], digests


# ---------------------------------------------------------------- 1. native classifier
CLASSIFIER_TEST = r'''
#include "ios/IOSSpuObjectBindings.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <string>
#include <vector>

namespace d = rpcs3::ios::spu_direct_hit;
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)

static const std::vector<std::string_view> table = { @TABLE@ };
static const std::string entry = "__spu-0x01234-AbCdEfGhIjKlMnOp";
static int cases = 0;

static d::symbol undef(std::string_view n) { d::symbol s; s.name = n; s.undefined = true; s.global = true; return s; }
static d::symbol defined_global(std::string_view n) { d::symbol s; s.name = n; s.global = true; return s; }
static d::symbol local(std::string_view n, bool absolute = false) { d::symbol s; s.name = n; s.absolute = absolute; return s; }

static std::vector<d::symbol> base(std::vector<std::string>& keep)
{
	std::vector<d::symbol> s;
	s.push_back(local("", true));                 // ELF null / file symbols: local, absolute
	s.push_back(local(".text"));
	s.push_back(local("__spu-cx01234-Zz"));        // internal chunk
	s.push_back(defined_global(entry));
	(void)keep;
	return s;
}

static d::plan run(const std::vector<d::symbol>& s, std::size_t limit = 1000)
{
	++cases;
	return d::classify(entry, s, table, limit);
}

static void reject(std::vector<d::symbol> s, d::reason why, std::size_t limit = 1000)
{
	const auto p = run(s, limit);
	if (p.result != why) { std::fprintf(stderr, "expected %s got %s (%.*s)\n", d::reason_names[std::size_t(why)].data(), d::reason_names[std::size_t(p.result)].data(), int(p.offending.size()), p.offending.data()); std::exit(1); }
	CHECK(p.named.empty() && p.patchpoints.empty());
}

int main()
{
	std::vector<std::string> keep;
	keep.reserve(4096);
	const auto pp = [&](std::string suffix) -> std::string_view { keep.push_back(entry + suffix); return keep.back(); };

	// parse_patchpoint: exact regeneration only.
	std::uint32_t id = 7;
	CHECK(d::parse_patchpoint(entry, entry + "-pp-0", id) && id == 0);
	CHECK(d::parse_patchpoint(entry, entry + "-pp-4294967295", id) && id == 4294967295u);
	for (const char* bad : {"-pp-01", "-pp--1", "-pp-+1", "-pp-4294967296", "-pp-", "-pp-1x", "-pp- 1", "-pp-1 ", "-pp-0x10", "-pp-١", "-chunkpp-0x00010", "-pp", "pp-1"})
	{
		CHECK(!d::parse_patchpoint(entry, entry + bad, id));
	}
	CHECK(!d::parse_patchpoint(entry, "__spu-0x01234-AbCdEfGhIjKlMnOq-pp-1", id));
	CHECK(!d::parse_patchpoint(entry + "-nofma", entry + "-pp-1", id));
	CHECK(!d::parse_patchpoint(entry, entry + "-nofma-pp-1", id));
	CHECK(d::patchpoint_limit(0) == 64 && d::patchpoint_limit(100) == 1664 && d::patchpoint_limit(1u << 20) == (1u << 20));

	// Accepted: every table name and shuffled patchpoints.
	{
		auto s = base(keep);
		std::vector<std::uint32_t> ids = {5, 0, 3, 17, 2};
		for (auto n : table) s.push_back(undef(n));
		for (auto i : ids) s.push_back(undef(pp("-pp-" + std::to_string(i))));
		s.push_back(undef(""));                       // ignored
		std::mt19937 rng(660);
		std::shuffle(s.begin(), s.end(), rng);
		const auto p = run(s);
		CHECK(p.result == d::reason::accepted);
		CHECK(p.named.size() == table.size());
		for (std::size_t i = 0; i < p.named.size(); ++i) CHECK(p.named[i] == i);
		CHECK((p.patchpoints == std::vector<std::uint32_t>{0, 2, 3, 5, 17}));
	}
	// Accepted: no patchpoint (spu_verification off), a subset of the table.
	{
		auto s = base(keep);
		s.push_back(undef(table[3])); s.push_back(undef(table[1]));
		const auto p = run(s);
		CHECK(p.result == d::reason::accepted && (p.named == std::vector<std::uint32_t>{1, 3}) && p.patchpoints.empty());
	}
	// Only the entry.
	{ auto s = base(keep); CHECK(run(s).result == d::reason::accepted); }

	// Rejections (synthesis cases).
	for (const char* bad : {"-pp-01", "-pp--1", "-pp-4294967296", "-pp-", "-pp-1x"})
	{
		auto s = base(keep); s.push_back(undef(pp(bad))); reject(s, d::reason::malformed_patchpoint);
	}
	for (std::string bad : {std::string("__spu-0x01234-AbCdEfGhIjKlMnOq-pp-1"), entry + "-nofma-pp-0", entry + "-notbl2-pp-3", entry + "-chunkpp-0x00010",
		std::string("spu_FREST"), std::string("spu_STOP"), std::string("memcpy"), std::string("memset"), std::string("__aarch64_cas8_acq_rel"), std::string("fmaf"),
		std::string("spu_rotqby"), std::string("spu_interp_check"), entry, std::string("spu_timebase_offs ") })
	{
		keep.push_back(bad);
		auto s = base(keep); s.push_back(undef(keep.back())); reject(s, d::reason::unknown_symbol);
	}
	{ // a pp of the base name when the module carries a variant suffix
		const std::string variant = entry + "-nofma";
		auto s = std::vector<d::symbol>{defined_global(variant), undef(pp("-pp-0"))};
		++cases;
		CHECK(d::classify(variant, s, table, 100).result == d::reason::unknown_symbol);
	}
	{ auto s = base(keep); d::symbol a = local("abs_global", true); a.global = true; s.push_back(a); reject(s, d::reason::absolute_global); }
	{ auto s = base(keep); d::symbol a = undef("spu_escape"); a.absolute = true; s.push_back(a); reject(s, d::reason::absolute_global); }
	{ auto s = base(keep); s.push_back(undef(pp("-pp-4"))); s.push_back(undef(pp("-pp-4"))); reject(s, d::reason::duplicate_symbol); }
	{ auto s = base(keep); s.push_back(undef(table[0])); s.push_back(undef(table[0])); reject(s, d::reason::duplicate_symbol); }
	{ auto s = base(keep); for (int i = 0; i < 9; ++i) s.push_back(undef(pp("-pp-" + std::to_string(i)))); reject(s, d::reason::patchpoint_bound, 8); }
	{ auto s = base(keep); s.push_back(undef(pp("-pp-1048576"))); reject(s, d::reason::patchpoint_bound); }
	{ auto s = base(keep); s.push_back(undef(pp("-pp-1048575"))); CHECK(run(s).result == d::reason::accepted); }
	{ auto s = base(keep); d::symbol u; u.readable = false; s.push_back(u); reject(s, d::reason::symbol_unreadable); }
	{ auto s = base(keep); s.push_back(defined_global("spu_escape")); reject(s, d::reason::foreign_definition); }
	{ auto s = base(keep); s.push_back(defined_global(entry)); reject(s, d::reason::duplicate_entry); }
	{ std::vector<d::symbol> s{local(entry)}; reject(s, d::reason::missing_entry); }
	{ std::vector<d::symbol> s{undef(table[0])}; reject(s, d::reason::missing_entry); }
	{ std::vector<d::symbol> s(d::max_symbols + 1, local("x")); reject(s, d::reason::symbol_bound); }
	{ ++cases; CHECK(d::classify("", base(keep), table, 10).result == d::reason::missing_entry); }

	// Every reason has a name; copy_failed is its own reason (fix 3); counters exchange per window.
	for (std::size_t i = 0; i < d::reason_count; ++i) CHECK(!d::reason_names[i].empty());
	CHECK(d::reason_names[std::size_t(d::reason::copy_failed)] == "copy_failed" && d::reason::copy_failed != d::reason::add_rejected);
	// Fallback notices (fix 4): the first 8 of each reason, then every 256th; never for accepted; reasons apart.
	{
		std::vector<int> logged;
		for (int i = 1; i <= 1024; ++i) if (d::should_log_fallback(d::reason::unknown_symbol)) logged.push_back(i);
		CHECK((logged == std::vector<int>{1, 2, 3, 4, 5, 6, 7, 8, 256, 512, 768, 1024}));
		int other = 0;
		for (int i = 1; i <= 300; ++i) other += d::should_log_fallback(d::reason::copy_failed);
		CHECK(other == 9);
		for (int i = 0; i < 20; ++i) CHECK(!d::should_log_fallback(d::reason::accepted));
		CHECK(!d::should_log_fallback(d::reason::count));
	}
	auto& c = d::stats();
	c.record_direct(4096, 100, 10, 50, 7, 2);
	c.record_direct(1024, 300, 20, 60, 5, 0);
	c.record_fallback(d::reason::unknown_symbol);
	c.record_fallback(d::reason::count); // ignored
	c.record_failure();
	auto w = c.take_window();
	CHECK(w.direct == 2 && w.direct_bytes == 5120 && w.direct_ticks == 400 && w.direct_max_ticks == 300 && w.classify_ticks == 30 && w.link_ticks == 110);
	CHECK(w.bindings == 12 && w.patchpoints == 2 && w.failures == 1 && w.fallbacks[std::size_t(d::reason::unknown_symbol)] == 1);
	w = c.take_window();
	CHECK(w.direct == 0 && w.direct_max_ticks == 0 && w.fallbacks[std::size_t(d::reason::unknown_symbol)] == 0);
	CHECK(!d::enabled.load());
	std::printf("classifier cases=%d table=%zu\n", cases, table.size());
	return 0;
}
'''


# ---------------------------------------------------------------- 2. the real binding table and helper
# The REAL BINDINGS block (its 27 rows, the function-local static) and the REAL HELPER region of the candidate
# are pasted into a class next to stand-ins with the real declarations of what the rows name (the exec_* statics
# with their real heads, spu_runtime's three trampolines, jit_runtime::alloc, atomic_wait_engine::notify_all,
# g_timebase_offs). Every row is type-checked and evaluated, then compared with what each call site of the IR
# path maps (call() maps reinterpret_cast<uptr> of its RT(*)(FArgs...) parameter; updateGlobalMapping its
# address), the site expressions being those of the candidate file. The helper runs on minimal llvm::object /
# llvm::MemoryBuffer stand-ins. -DNULL_ESCAPE builds the same TU with g_escape still null at the first hit.
BINDINGS_TEST = r'''
#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <set>
#include <string>
#include <string_view>
#include <tuple>
#include <type_traits>
#include <unordered_map>
#include <vector>
using u8 = std::uint8_t; using u16 = std::uint16_t; using u32 = std::uint32_t; using u64 = std::uint64_t; using usz = std::size_t; using uptr = std::uintptr_t;
#include "ios/IOSSpuObjectBindings.h"

namespace fmt
{
	// RPCS3's fmt::format for the only pattern used here: %s then %u (decimal).
	inline std::string format(const char* pattern, const std::string& s, u32 v)
	{
		if (std::string_view(pattern) != "%s-pp-%u") std::abort();
		char buf[16]; std::snprintf(buf, sizeof(buf), "%u", v);
		return s + "-pp-" + buf;
	}
}

namespace llvm
{
	struct StringRef { const char* p; usz n; const char* data() const { return p; } usz size() const { return n; } };
	struct Error { bool failed = true; };
	static int consumed = 0;
	inline void consumeError(Error) { ++consumed; }
	template <typename T> struct Expected
	{
		T value{}; bool ok = true;
		explicit operator bool() const { return ok; }
		T& operator*() { return value; }
		T* operator->() { return &value; }
		Error takeError() { return {}; }
	};
	struct Triple { enum ArchType { aarch64, x86_64 }; ArchType arch = aarch64; ArchType getArch() const { return arch; } };
	namespace object
	{
		struct fake_symbol { std::string name; bool name_ok = true, flags_ok = true; u32 flags = 0; };
		struct SymbolRef
		{
			enum : u32 { SF_Undefined = 1u << 0, SF_Global = 1u << 1, SF_Weak = 1u << 2, SF_Absolute = 1u << 3 };
			const fake_symbol* s;
			Expected<StringRef> getName() const { return {{s->name.data(), s->name.size()}, s->name_ok}; }
			Expected<u32> getFlags() const { return {s->flags, s->flags_ok}; }
		};
		struct fake_object { bool parses = true; Triple::ArchType arch = Triple::aarch64; std::vector<fake_symbol> symbols; };
		struct ObjectFile
		{
			const fake_object* o;
			Triple::ArchType getArch() const { return o->arch; }
			std::vector<SymbolRef> symbols() const { std::vector<SymbolRef> r; for (auto& s : o->symbols) r.push_back({&s}); return r; }
			static Expected<std::unique_ptr<ObjectFile>> createObjectFile(const fake_object* ref)
			{
				Expected<std::unique_ptr<ObjectFile>> r; r.ok = ref->parses; if (r.ok) r.value = std::make_unique<ObjectFile>(ObjectFile{ref}); return r;
			}
		};
	}
	struct MemoryBuffer { const object::fake_object* o; const object::fake_object* getMemBufferRef() const { return o; } };
}

// Stand-ins with the real declarations the rows name (SPURecompiler.h, JIT.h, util/atomic.hpp, lv2/sys_time.h).
static int g_touched = 0;
struct spu_thread; struct spu_channel; struct spu_channel_4_t;
using spu_function_t = void(*)(spu_thread&, void*, u8*);
struct atomic_wait_engine
{
	static void notify_one(const void* data);
	static void notify_all(const void* data);
};
void atomic_wait_engine::notify_one(const void*) { g_touched = -1; }
void atomic_wait_engine::notify_all(const void*) { g_touched = -2; }
[[maybe_unused]] static void fake_dispatch(spu_thread&, void*, u8*) { g_touched = -3; }
[[maybe_unused]] static void fake_all(spu_thread&, void*, u8*) { g_touched = -4; }
[[maybe_unused]] static void fake_escape(spu_thread*) { g_touched = -5; }
struct spu_runtime
{
	static spu_function_t tr_dispatch;
	static spu_function_t tr_all;
	static void(*g_escape)(spu_thread*);
	mutable std::vector<u64> made; mutable u64 next = 0x7000'0000;
	spu_function_t make_branch_patchpoint(u16 data = 0) const { if (data) std::abort(); made.push_back(next += 0x30); return reinterpret_cast<spu_function_t>(next); }
};
spu_function_t spu_runtime::tr_dispatch = nullptr;
spu_function_t spu_runtime::tr_all = nullptr;
void(*spu_runtime::g_escape)(spu_thread*) = nullptr;
static u8 g_code_base[64];
static int g_subrange_queries = 0;
struct jit_runtime
{
	static u8* alloc(usz size, usz align, bool exec = true) noexcept
	{
		if (size || align || !exec) std::abort();
		++g_subrange_queries; // on Apple each call takes s_alloc_lock
		return g_code_base;
	}
};
u64 g_timebase_offs = 0;

struct fake_target { llvm::Triple t; const llvm::Triple& getTargetTriple() const { return t; } };
struct fake_engine { fake_target tm; fake_target* getTargetMachine() { return &tm; } };
struct fake_jit { fake_engine e; fake_engine& get_engine() { return e; } };

struct recompiler
{
	std::string m_hash = "__spu-0x00400-Hash57";
	fake_jit m_jit;
	spu_runtime runtime;
	const spu_runtime* m_spurt = &runtime;

@EXEC@
@BINDINGS@
@HELPER@
	// The IR path's call sites of the candidate, emulated in the same scope.
	std::unordered_map<std::string, u64> site_map;
	int site_conflicts = 0;
	void record(std::string_view name, u64 address)
	{
		const auto [it, inserted] = site_map.emplace(std::string(name), address);
		if (!inserted && it->second != address) ++site_conflicts;
	}
	template <typename RT, typename... FArgs>
	void call_site(std::string_view name, RT(*_func)(FArgs...)) { record(name, reinterpret_cast<uptr>(_func)); }
	void mapping_site(std::string_view name, u64 address) { record(name, address); }
	void sites()
	{
@SITES@
	}
};

namespace d = rpcs3::ios::spu_direct_hit;
using llvm::object::fake_symbol; using llvm::object::SymbolRef;
#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)

static fake_symbol und(std::string n) { return {std::move(n), true, true, SymbolRef::SF_Undefined | SymbolRef::SF_Global}; }
static const std::vector<std::string_view> expected_names = { @NAMES@ };

int main()
{
#ifndef NULL_ESCAPE
	// spu_runtime::initialize_static_trampolines() at Core init, before any SPU compile.
	spu_runtime::tr_dispatch = &fake_dispatch; spu_runtime::tr_all = &fake_all; spu_runtime::g_escape = &fake_escape;
#endif
	recompiler r;
	CHECK(g_subrange_queries == 0);
	const auto& table = recompiler::direct_bindings();
	CHECK(g_subrange_queries == 1);
	CHECK(&recompiler::direct_bindings() == &table && g_subrange_queries == 1); // one evaluation per process
	CHECK(table.size() == expected_names.size());
	for (usz i = 0; i < table.size(); ++i) CHECK(table[i].name == expected_names[i]);

#ifndef NULL_ESCAPE
	// Every real row is the value its call sites map; all are distinct and non-zero.
	r.sites();
	CHECK(r.site_conflicts == 0 && r.site_map.size() == table.size());
	std::set<u64> distinct;
	for (const auto& row : table)
	{
		const auto found = r.site_map.find(std::string(row.name));
		if (found == r.site_map.end() || found->second != row.address)
		{
			std::fprintf(stderr, "row %.*s differs from its call sites\n", int(row.name.size()), row.name.data());
			return 1;
		}
		CHECK(row.address != 0);
		distinct.insert(row.address);
	}
	CHECK(distinct.size() == table.size());
	const int subrange_after_sites = g_subrange_queries;

	llvm::object::fake_object o;
	o.symbols = {{"", true, true, SymbolRef::SF_Absolute}, {r.m_hash, true, true, SymbolRef::SF_Global}, und(r.m_hash + "-pp-9"), und(r.m_hash + "-pp-2"),
		und(std::string(table[4].name)), und(std::string(table[0].name)), {"", true, true, SymbolRef::SF_Undefined}};
	llvm::MemoryBuffer buffer{&o};
	std::unordered_map<std::string, u64> bindings{{"stale", 1}};
	std::vector<std::string> pps{"stale"};
	std::string offending;

	// Accepted: the real table addresses under their names and the regenerated names, no stub yet (fix 3).
	CHECK(r.direct_object_bindings(buffer, 16, bindings, pps, offending) == d::reason::accepted);
	CHECK(offending.empty() && r.runtime.made.empty());
	CHECK(bindings.size() == 2 && !bindings.count("stale"));
	CHECK(bindings.at(std::string(table[0].name)) == table[0].address && bindings.at(std::string(table[4].name)) == table[4].address);
	CHECK((pps == std::vector<std::string>{r.m_hash + "-pp-2", r.m_hash + "-pp-9"}));
	// Then the stubs, in ascending number.
	r.direct_object_patchpoints(bindings, pps);
	CHECK(r.runtime.made.size() == 2 && bindings.size() == 4);
	CHECK(bindings.at(r.m_hash + "-pp-2") == r.runtime.made[0] && bindings.at(r.m_hash + "-pp-9") == r.runtime.made[1]);

	int cases = 1;
	// symbol: what the refusal reports ("stale": nothing was assigned, the refusal came before the classifier).
	const auto refused = [&](llvm::object::fake_object obj, d::reason why, std::string_view symbol, usz words = 16)
	{
		++cases;
		const usz before = r.runtime.made.size();
		auto owned = std::make_unique<llvm::object::fake_object>(std::move(obj));
		llvm::MemoryBuffer b{owned.get()};
		std::unordered_map<std::string, u64> m; std::vector<std::string> n; std::string off = "stale";
		const auto got = r.direct_object_bindings(b, words, m, n, off);
		owned.reset(); // the offending symbol is a copy: it outlives the object
		if (got != why || off != symbol)
		{
			std::fprintf(stderr, "expected %s/%.*s got %s/%s\n", d::reason_names[usz(why)].data(), int(symbol.size()), symbol.data(), d::reason_names[usz(got)].data(), off.c_str());
			std::exit(1);
		}
		CHECK(r.runtime.made.size() == before); // no stub on any refusal
	};

	auto x = o; x.parses = false; refused(x, d::reason::object_unreadable, "stale");
	x = o; x.arch = llvm::Triple::x86_64; refused(x, d::reason::object_unreadable, "stale");
	x = o; x.symbols.push_back(und("memcpy")); refused(x, d::reason::unknown_symbol, "memcpy");
	x = o; x.symbols.push_back(und(r.m_hash + "-pp-007")); refused(x, d::reason::malformed_patchpoint, r.m_hash + "-pp-007");
	x = o; x.symbols.push_back({"broken", false, true, 0}); refused(x, d::reason::symbol_unreadable, "");
	x = o; x.symbols.push_back({"broken", true, false, 0}); refused(x, d::reason::symbol_unreadable, "");
	CHECK(llvm::consumed == 3);
	x = o; x.symbols.push_back({"absolute", true, true, SymbolRef::SF_Absolute | SymbolRef::SF_Global}); refused(x, d::reason::absolute_global, "absolute");
	x = o; x.symbols.erase(x.symbols.begin() + 1); refused(x, d::reason::missing_entry, r.m_hash);
	x = o; x.symbols.push_back({"spu_escape", true, true, SymbolRef::SF_Global}); refused(x, d::reason::foreign_definition, "spu_escape");
	x = o; x.symbols.push_back(und(std::string(table[0].name))); refused(x, d::reason::duplicate_symbol, table[0].name);
	x = o; for (int i = 10; i < 80; ++i) x.symbols.push_back(und(r.m_hash + "-pp-" + std::to_string(i))); refused(x, d::reason::patchpoint_bound, r.m_hash + "-pp-72", 0);
	x = o; x.symbols.resize(d::max_symbols + 1, fake_symbol{"local", true, true, 0}); refused(x, d::reason::symbol_bound, "stale");
	CHECK(g_subrange_queries == subrange_after_sites); // no hit evaluates the table again
	std::printf("bindings ok rows=%zu sites=%zu cases=%d stubs=%zu table_evaluations=1\n", table.size(), r.site_map.size(), cases, r.runtime.made.size());
#else
	// g_escape still null at the first hit (an initialization order that RPCS3IOS.cpp rules out): the row stays 0
	// for the process, and only the objects that need it fall back.
	usz escape = 0;
	while (table[escape].name != "spu_escape") ++escape;
	CHECK(table[escape].address == 0);
	spu_runtime::g_escape = &fake_escape; // a later assignment does not change the evaluated table
	llvm::object::fake_object o;
	o.symbols = {{r.m_hash, true, true, SymbolRef::SF_Global}, und("spu_escape")};
	llvm::MemoryBuffer buffer{&o};
	std::unordered_map<std::string, u64> m; std::vector<std::string> n; std::string off;
	CHECK(r.direct_object_bindings(buffer, 16, m, n, off) == d::reason::null_binding && off == "spu_escape");
	o.symbols = {{r.m_hash, true, true, SymbolRef::SF_Global}, und("spu_read_channel")};
	off.clear();
	CHECK(r.direct_object_bindings(buffer, 16, m, n, off) == d::reason::accepted && off.empty() && m.size() == 1);
	CHECK(g_subrange_queries == 1 && r.runtime.made.empty());
	std::printf("null binding ok row=spu_escape table_evaluations=1\n");
#endif
	return 0;
}
'''


def exec_stand_ins(candidate: str, block: str) -> str:
    """The real heads of the exec_* statics the table names, with stand-in bodies."""
    out = []
    for number, name in enumerate(sorted(set(re.findall(r'&(exec_\w+)', block))), 1):
        heads = re.findall(r'^((?:\ttemplate <bool Saveable>\n)?\t(?:\[\[noreturn\]\] )?static (\w+) ' + name + r'\(([^)]*)\))\n\t\{\n',
                           candidate, re.M)
        assert len(heads) == 1, (name, heads)
        head, ret, _params = heads[0]
        if head.lstrip().startswith('template') or '[[noreturn]]' not in head:
            body = f'g_touched = {number};' + ('' if ret == 'void' else ' return {};')
        else:
            body = f'g_touched = {number}; std::abort();'
        out.append(f'{head}\n\t{{\n\t\t{body}\n\t}}\n')
    return ''.join(out)


def bindings_source(candidate: str) -> str:
    block_start = candidate.index(bx.TABLE_BEGIN)
    block = candidate[block_start:candidate.index(bx.TABLE_END, block_start) + len(bx.TABLE_END)]
    helper_begin = candidate.index(f'\t// {MARK} HELPER BEGIN')
    helper_end_mark = f'\t// {MARK} HELPER END\n'
    helper = candidate[helper_begin:candidate.index(helper_end_mark, helper_begin) + len(helper_end_mark)]
    sites = []
    for site in bx.extract(candidate)[0]:
        if site.active:
            fn = 'call_site' if site.kind == 'call' else 'mapping_site'
            sites.append(f'\t\t{fn}("{site.name}", {site.expr});\n')
    names = sorted(bx.table(candidate))
    return (BINDINGS_TEST.replace('@EXEC@', exec_stand_ins(candidate, block)).replace('@BINDINGS@', block)
            .replace('@HELPER@', helper).replace('@SITES@', ''.join(sites))
            .replace('@NAMES@', ', '.join(f'"{n}"' for n in names)))


# ---------------------------------------------------------------- 3. lifted helpers vs lambdas
LIFT_TEST = r'''
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
using u8 = std::uint8_t; using u32 = std::uint32_t; using u64 = std::uint64_t;
enum : u32 { SPU_EVENT_LR = 0x400 };
struct spu_thread
{
	u32 raddr = 0;
	struct { u32 events = 0; } ev;
	struct { auto load() const { return parent->ev; } const spu_thread* parent; } ch_events{this};
	std::vector<int> log;
	void set_events(u32 e) { log.push_back(int(e)); ev.events |= e; }
	void get_events(u32 e) { log.push_back(-int(e)); }
	spu_thread() = default;
	spu_thread(const spu_thread& o) : raddr(o.raddr), ev(o.ev), ch_events{this}, log(o.log) {}
};

struct control
{
	static void putllc16(spu_thread* s, u32 a) { @L16@ (s, a); }
	static void putllc0(spu_thread* s, u32 a) { @L0@ (s, a); }
	static void memcpy_(u8* d, const u8* s, u32 n) { @LM@ (d, s, n); }
};
struct candidate
{
@F16@
@F0@
@FM@
};

#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)

int main()
{
	int cases = 0;
	for (u32 raddr : {0u, 0x1000u, 0x2000u})
		for (u32 events : {0u, u32(SPU_EVENT_LR), 0x1u})
			for (u32 addr : {0x1000u, 0x3000u})
			{
				spu_thread a; a.raddr = raddr; a.ev.events = events; spu_thread b = a, c = a, e = a;
				control::putllc16(&a, addr); candidate::exec_putllc16_fail(&b, addr);
				control::putllc0(&c, addr); candidate::exec_putllc0_fail(&e, addr);
				CHECK(a.raddr == b.raddr && a.ev.events == b.ev.events && a.log == b.log);
				CHECK(c.raddr == e.raddr && c.ev.events == e.ev.events && c.log == e.log);
				CHECK(a.log == c.log && a.raddr == c.raddr);
				cases += 2;
			}
	u8 src[64], d1[64] = {}, d2[64] = {};
	for (int i = 0; i < 64; ++i) src[i] = u8(i * 7 + 1);
	control::memcpy_(d1, src, 48); candidate::exec_spu_memcpy(d2, src, 48);
	CHECK(std::memcmp(d1, d2, 64) == 0 && d1[47] == src[47] && d1[48] == 0);
	std::printf("lifted helpers cases=%d\n", cases + 1);
	return 0;
}
'''


# ---------------------------------------------------------------- 8. try_add_minimal_object control flow (7c, item 10)
# The REAL body of jit_compiler::try_add_minimal_object (candidate JITLLVM.cpp), the REAL try_fin body and the REAL
# held_object_bytes / held_objects() of REWINDBOX_JIT_OBJECT_RELEASE_634 are compiled against stand-ins of
# jit_minimal_object::add, run_recoverable_llvm (an LLVM fatal error is a thrown llvm_fatal; each call counts one
# worker handoff), llvm::MemoryBuffer (heap bytes, so ASan sees any read after release) and ExecutionEngine. The
# reviewed pre-item-10 body (add only; the caller then called try_fin) is compiled next to it as the reference:
# every outcome of the merged call must equal the old two-call sequence, with one handoff instead of two.
TWO_CALL_REFERENCE = r'''bool jit_compiler::try_add_minimal_object(jit_cached_object object, const std::string& entry,
	const std::unordered_map<std::string, u64>& bindings, std::string& error)
{
	// Callers must provide every patchpoint/helper symbol from this process. No
	// address is read from or written to the persistent cache.
	// REWINDBOX_SPU_DIRECT_OBJECT_HIT_660 (ios/IOSSpuObjectBindings.h): the SPU
	// cache-hit path links validated objects here. As in try_add_cached, the load
	// runs in run_recoverable_llvm (RuntimeDyld reports errors as fatal errors):
	// false with an error means the compiler must be discarded. False with an
	// empty error means jit_minimal_object::add refused the object before it
	// touched the engine, and the caller may still link it another way.
	std::unique_ptr<llvm::MemoryBuffer> buffer = std::move(object.buffer);
#ifdef RPCS3_IOS
	// REWINDBOX_JIT_OBJECT_RELEASE_634: MCJIT gets a view; the compiler keeps the
	// bytes until finalizeObject, as ObjectCache::getObject does for a cached hit.
	std::unique_ptr<llvm::MemoryBuffer> owner;
	if (buffer && rpcs3::ios::jit_load::release_bytes.load(std::memory_order_relaxed))
	{
		owner = std::move(buffer);
		buffer = llvm::MemoryBuffer::getMemBuffer(owner->getMemBufferRef(), false);
	}
#endif

	bool added = false;
	std::string refused;
	const bool recovered = run_recoverable_llvm([&]()
	{
		added = jit_minimal_object::add(*m_engine, buffer, entry, bindings, refused);
	}, error);

#ifdef RPCS3_IOS
	if (owner && (added || !recovered))
	{
		held_objects().hold(this, std::move(owner));
	}
#endif

	if (!recovered)
	{
		if (m_announcer) m_announcer->finalized(false);
		return false;
	}

	if (!added)
	{
		jit_log.trace("LLVM: Minimal object %s refused: %s", entry, refused);
		error.clear();
		return false;
	}

	return true;
}'''
TWO_CALL_REFERENCE_SHA = '0d83d29ee5a19a7958aa366ca94d1cc2074162a3a57e5d0da2c34f961bdfbbde'
MINIMAL_TEST = r'''
#define RPCS3_IOS 1
#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>
#include <vector>
using u8 = std::uint8_t; using u32 = std::uint32_t; using u64 = std::uint64_t; using usz = std::size_t;

namespace llvm
{
	struct MemoryBufferRef { const char* data; usz size; };
	struct MemoryBuffer
	{
		std::vector<char> owned; // heap bytes of an owning buffer
		MemoryBufferRef view{};  // the bytes of a non-owning view
		bool owning = true;
		MemoryBufferRef getMemBufferRef() const { return owning ? MemoryBufferRef{owned.data(), owned.size()} : view; }
		static std::unique_ptr<MemoryBuffer> getMemBuffer(MemoryBufferRef ref, bool /*RequiresNullTerminator*/)
		{
			auto result = std::make_unique<MemoryBuffer>(); result->owning = false; result->view = ref; return result;
		}
	};
}

struct llvm_fatal { std::string message; };
enum class mode { added, refused, fatal_add, fatal_fin };
static mode g_mode = mode::added;
static int g_handoffs = 0, g_finalized = 0, g_traces = 0;
static std::string g_last_trace;

struct fake_engine
{
	std::unique_ptr<llvm::MemoryBuffer> loaded;
	void finalizeObject()
	{
		++g_finalized;
		// RuntimeDyld reads the object bytes until finalize: a released owner is a heap-use-after-free here.
		const auto ref = loaded->getMemBufferRef();
		unsigned sum = 0;
		for (usz i = 0; i < ref.size; ++i) sum += static_cast<unsigned char>(ref.data[i]);
		if (sum != 0x41u * 64u) std::abort();
		if (g_mode == mode::fatal_fin) throw llvm_fatal{"LLVM ERROR: finalize"};
	}
};

namespace jit_minimal_object
{
	inline bool add(fake_engine& engine, std::unique_ptr<llvm::MemoryBuffer>& buffer, const std::string& entry,
		const std::unordered_map<std::string, u64>& bindings, std::string& error)
	{
		if (entry.empty() || bindings.empty()) std::abort();
		if (g_mode == mode::refused) { error = "unbound_symbol:memcpy"; return false; }
		if (g_mode == mode::fatal_add) throw llvm_fatal{"LLVM ERROR: load"};
		engine.loaded = std::move(buffer);
		return true;
	}
}

namespace
{
	template <typename F>
	bool run_recoverable_llvm(F&& func, std::string& error)
	{
		++g_handoffs; // one worker of the iOS thread pool per call
		error.clear();
		try { std::forward<F>(func)(); return true; }
		catch (const llvm_fatal& fatal) { error = fatal.message; return false; }
	}
}

namespace rpcs3::ios::jit_load { inline std::atomic<bool> release_bytes{false}; }
struct { template <typename... A> void trace(const char*, const std::string& entry, const std::string& why) { ++g_traces; g_last_trace = entry + ":" + why; } } jit_log;

class jit_compiler;
@HELD@

struct JITAnnouncer { std::vector<int> calls; void finalized(bool success) { calls.push_back(success); } };
struct jit_cached_object { std::unique_ptr<llvm::MemoryBuffer> buffer; usz bytes = 0; };

class jit_compiler
{
public:
	std::unique_ptr<JITAnnouncer> m_announcer = std::make_unique<JITAnnouncer>();
	std::unique_ptr<fake_engine> m_engine = std::make_unique<fake_engine>();
	bool try_add_minimal_object(jit_cached_object object, const std::string& entry, const std::unordered_map<std::string, u64>& bindings, std::string& error);
	bool two_call_add(jit_cached_object object, const std::string& entry, const std::unordered_map<std::string, u64>& bindings, std::string& error);
	bool try_fin(std::string& error);
};

@MERGED@

@REFERENCE@

@TRY_FIN@

#define CHECK(x) do { if (!(x)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); std::exit(1); } } while (0)

struct outcome
{
	bool result = false, error_empty = true, engine_owns = false; usz held = 0; int handoffs = 0, finalized = 0, traces = 0; std::vector<int> announced;
	bool same(const outcome& o) const
	{
		return result == o.result && error_empty == o.error_empty && engine_owns == o.engine_owns && held == o.held && finalized == o.finalized &&
			traces == o.traces && announced == o.announced;
	}
};

static jit_cached_object object()
{
	jit_cached_object o; o.buffer = std::make_unique<llvm::MemoryBuffer>(); o.buffer->owned.assign(64, 'A'); o.bytes = 64; return o;
}

static usz held(const jit_compiler* c)
{
	auto& h = held_objects();
	std::lock_guard lock(h.mutex);
	const auto found = h.owners.find(c);
	return found == h.owners.end() ? 0 : found->second.size();
}

// merged: the direct block today; otherwise the reviewed sequence (add, then try_fin when it added).
static outcome run(mode m, bool release, bool merged)
{
	g_mode = m; g_handoffs = g_finalized = g_traces = 0; g_last_trace.clear();
	rpcs3::ios::jit_load::release_bytes = release;
	jit_compiler jit;
	const std::unordered_map<std::string, u64> bindings{{"spu_escape", 0x1000}};
	std::string error = "stale";
	bool result;
	if (merged)
	{
		result = jit.try_add_minimal_object(object(), "__spu-0x00400-H", bindings, error);
	}
	else
	{
		result = jit.two_call_add(object(), "__spu-0x00400-H", bindings, error);
		if (result) result = jit.try_fin(error);
	}
	outcome o;
	o.result = result; o.error_empty = error.empty(); o.held = held(&jit); o.handoffs = g_handoffs; o.finalized = g_finalized;
	o.traces = g_traces; o.announced = jit.m_announcer->calls; o.engine_owns = jit.m_engine->loaded && jit.m_engine->loaded->owning;
	held_objects().release(&jit);
	return o;
}

int main()
{
	int cases = 0;
	for (const bool release : {true, false})
	{
		// Added and finalized: true, one handoff, finalize read live bytes, nothing held after it, announced once.
		const outcome a = run(mode::added, release, true), a2 = run(mode::added, release, false);
		CHECK(a.result && a.error_empty && a.handoffs == 1 && a.finalized == 1 && a.held == 0 && (a.announced == std::vector<int>{1}));
		CHECK(a.engine_owns == !release && a2.handoffs == 2 && a.same(a2));
		// Refused before the engine is touched: false, error empty, bytes not held, no finalize, nothing announced.
		const outcome r = run(mode::refused, release, true), r2 = run(mode::refused, release, false);
		CHECK(!r.result && r.error_empty && r.handoffs == 1 && r.finalized == 0 && r.held == 0 && r.announced.empty() && r.traces == 1);
		CHECK(g_last_trace == "__spu-0x00400-H:unbound_symbol:memcpy" && r2.handoffs == 1 && r.same(r2));
		// Fatal while adding: false, error kept, bytes held (with the 634 release), announced as failed.
		const outcome f = run(mode::fatal_add, release, true), f2 = run(mode::fatal_add, release, false);
		CHECK(!f.result && !f.error_empty && f.handoffs == 1 && f.finalized == 0 && f.held == (release ? 1u : 0u) && (f.announced == std::vector<int>{0}));
		CHECK(f2.handoffs == 1 && f.same(f2));
		// Added, then fatal while finalizing: false, error kept, bytes still held, announced as failed (a failed try_fin).
		const outcome g = run(mode::fatal_fin, release, true), g2 = run(mode::fatal_fin, release, false);
		CHECK(!g.result && !g.error_empty && g.handoffs == 1 && g.finalized == 1 && g.held == (release ? 1u : 0u) && (g.announced == std::vector<int>{0}));
		CHECK(g2.handoffs == 2 && g.same(g2));
		cases += 8;
	}
	std::printf("minimal object cases=%d merged_handoffs_per_hit=1 two_call_handoffs_per_hit=2\n", cases);
	return 0;
}
'''


def minimal_source(candidate_jit: str, merged_body: str | None = None) -> str:
    signature = 'bool jit_compiler::try_add_minimal_object(jit_cached_object object, const std::string& entry,'
    merged = merged_body if merged_body is not None else braced_text(candidate_jit, signature)
    reference = TWO_CALL_REFERENCE
    assert sha(reference.encode()) == TWO_CALL_REFERENCE_SHA
    reference = reference.replace('bool jit_compiler::try_add_minimal_object(', 'bool jit_compiler::two_call_add(', 1)
    try_fin = braced_text(candidate_jit, 'bool jit_compiler::try_fin(std::string& error)')
    held_start = candidate_jit.index('struct held_object_bytes\n')
    held_end = candidate_jit.index('\treturn objects;\n}\n', held_start) + len('\treturn objects;\n}\n')
    return (MINIMAL_TEST.replace('@HELD@', candidate_jit[held_start:held_end]).replace('@MERGED@', merged)
            .replace('@REFERENCE@', reference).replace('@TRY_FIN@', try_fin))


# ---------------------------------------------------------------- 9. llc-generated aarch64 ELF objects (7a)
# An SPU-shaped module (the shape of review/obj/blk.ll plus spu_test_state: GHC chunks, the internal function
# table, a private LUT, __spu-null, the entry, two patchpoints, helpers and the three mapped globals) is compiled
# by llc 18 for aarch64-unknown-linux-android (jit_compiler::triple2()), PIC, small and large code model, as the
# SPU engine does (JITLLVM.cpp: PIC_, Small or Large). Its symbol table is read with readelf and mapped as
# ELFObjectFile::getSymbolFlags maps it (Bind != LOCAL: SF_Global, Ndx UND: SF_Undefined, Ndx ABS: SF_Absolute),
# then fed to the real classifier with the real 27 table names. Mutated modules give the refusals that real
# objects would: memcpy from a variable-length llvm.memcpy, outline atomics, a chunk that lost its internal
# linkage, a malformed patchpoint name.
SPU_SHAPED_LL = r'''target triple = "aarch64-unknown-linux-android"
@spu_timebase_offs = external global i64
@"tbl" = internal constant [2 x ptr] [ptr @"__spu-cx00400-HH", ptr @"__spu-null"]
@lut = private constant [4 x i32] [i32 1, i32 2, i32 3, i32 4]
declare void @spu_dispatcher(ptr, ptr, i64)
declare ghccc void @"__spu-0x00400-HASH-pp-0"(ptr, ptr, i32)
declare ghccc void @"__spu-0x00400-HASH-pp-1"(ptr, ptr, i32)
declare i32 @spu_read_channel(ptr, i32)
declare i1 @spu_exec_check_state(ptr)
declare void @spu_escape(ptr)
declare void @spu_segment_base()
declare void @llvm.memcpy.p0.p0.i64(ptr, ptr, i64, i1)
define internal preserve_mostcc void @spu_test_state(ptr %t) {
  %c = call i1 @spu_exec_check_state(ptr %t)
  br i1 %c, label %y, label %n
y:
  call void @spu_escape(ptr %t)
  ret void
n:
  ret void
}
define internal ghccc void @"__spu-null"(ptr noalias %t, ptr noalias %ls, i32 %pc) {
  tail call void @spu_dispatcher(ptr %t, ptr %ls, i64 0)
  ret void
}
define internal ghccc void @"__spu-cx00400-HH"(ptr noalias %t, ptr noalias %ls, i32 %pc) {
  call preserve_mostcc void @spu_test_state(ptr %t)
  %v = call i32 @spu_read_channel(ptr %t, i32 3)
  %o = load i64, ptr @spu_timebase_offs
  %o32 = trunc i64 %o to i32
  %s = add i32 %v, %o32
  %i = and i32 %s, 1
  %ix = zext i32 %i to i64
  %lp = getelementptr [4 x i32], ptr @lut, i64 0, i64 %ix
  %lv = load i32, ptr %lp
  store i32 %lv, ptr %ls
  %seg = ptrtoint ptr @spu_segment_base to i64
  store i64 %seg, ptr %t
  %fp = getelementptr [2 x ptr], ptr @tbl, i64 0, i64 %ix
  %f = load ptr, ptr %fp
  %c = icmp eq i32 %i, 0
  br i1 %c, label %a, label %b
a:
  tail call ghccc void @"__spu-0x00400-HASH-pp-0"(ptr %t, ptr %ls, i32 0)
  ret void
b:
  tail call ghccc void %f(ptr %t, ptr %ls, i32 0)
  ret void
}
define ghccc void @"__spu-0x00400-HASH"(ptr %t, ptr %ls, i64 %x) {
  %c = icmp eq i64 %x, 0
  br i1 %c, label %a, label %b
a:
  tail call ghccc void @"__spu-cx00400-HH"(ptr %t, ptr %ls, i32 0)
  ret void
b:
  tail call ghccc void @"__spu-0x00400-HASH-pp-1"(ptr %t, ptr %ls, i32 4)
  ret void
}
'''
ELF_ENTRY = '__spu-0x00400-HASH'
ELF_VARIANTS = {
    # name: (mutation of the module, llc attributes, expected reason, expected offending symbol)
    'spu_shaped': (None, '', 'accepted', ''),
    'memcpy': (('  store i32 %lv, ptr %ls\n', '  store i32 %lv, ptr %ls\n  %n = zext i32 %v to i64\n'
                '  call void @llvm.memcpy.p0.p0.i64(ptr %ls, ptr %t, i64 %n, i1 false)\n'), '', 'unknown_symbol', 'memcpy'),
    'outline_atomics': (('  store i64 %seg, ptr %t\n', '  store i64 %seg, ptr %t\n  %old = atomicrmw add ptr %ls, i64 1 acq_rel\n'),
                        '+outline-atomics', 'unknown_symbol', '__aarch64_ldadd8_acq_rel'),
    'global_chunk': (('define internal ghccc void @"__spu-cx00400-HH"', 'define ghccc void @"__spu-cx00400-HH"'), '', 'foreign_definition',
                     '__spu-cx00400-HH'),
    'malformed_pp': (('@"__spu-0x00400-HASH-pp-1"', '@"__spu-0x00400-HASH-pp-01"'), '', 'malformed_patchpoint', '__spu-0x00400-HASH-pp-01'),
}
ELF_TEST = r'''
#include "ios/IOSSpuObjectBindings.h"
#include <cstdio>
#include <cstdlib>
#include <string>
#include <vector>
namespace d = rpcs3::ios::spu_direct_hit;
struct elf_case { const char* name; std::vector<d::symbol> symbols; d::reason expected; std::string_view offending; std::vector<std::uint32_t> named, pps; };
static const std::vector<std::string_view> table = { @TABLE@ };
static d::symbol sym(std::string_view n, bool u, bool a, bool g) { d::symbol s; s.name = n; s.undefined = u; s.absolute = a; s.global = g; return s; }
int main()
{
	const std::vector<elf_case> cases = {
@CASES@
	};
	for (const auto& c : cases)
	{
		const d::plan p = d::classify("@ENTRY@", c.symbols, table, d::patchpoint_limit(16));
		if (p.result != c.expected || p.offending != c.offending || p.named != c.named || p.patchpoints != c.pps)
		{
			std::fprintf(stderr, "%s: got %s (%.*s)\n", c.name, d::reason_names[std::size_t(p.result)].data(), int(p.offending.size()), p.offending.data());
			return 1;
		}
	}
	std::printf("elf objects=%zu\n", cases.size());
	return 0;
}
'''


def readelf_symbols(obj: Path) -> list[dict]:
    text = run(['readelf', '-sW', obj]).stdout
    symbols = []
    for line in text.splitlines():
        m = re.match(r'\s*(\d+): ([0-9a-f]+)\s+(\d+)\s+(\w+)\s+(\w+)\s+(\w+)\s+(\w+)\s?(.*)$', line)
        if m:
            _, _, _, kind, bind, _, ndx, name = m.groups()
            symbols.append({'name': name, 'type': kind, 'undefined': ndx == 'UND', 'absolute': ndx == 'ABS', 'global': bind != 'LOCAL'})
    assert symbols and symbols[0]['name'] == '' and symbols[0]['undefined'], obj
    return symbols


def run_elf_objects(candidate: str, work: Path, include: Path) -> dict:
    llc = shutil.which('llc-18') or shutil.which('llc')
    if not llc or not shutil.which('readelf'):
        # The Apple host tests have neither: reported as not run, never as passed.
        return {'run': False, 'reason': 'llc or readelf is not installed on this host'}
    names = sorted(bx.table(candidate))
    cases, report = [], {}
    for variant, (mutation, attrs, expected, offending) in ELF_VARIANTS.items():
        module = SPU_SHAPED_LL if mutation is None else SPU_SHAPED_LL.replace(*mutation)
        assert mutation is None or module != SPU_SHAPED_LL, variant
        ll = work / f'{variant}.ll'
        ll.write_text(module)
        for model in ('small', 'large'):
            obj = work / f'{variant}.{model}.o'
            run([llc, '-O2', '-mtriple=aarch64-unknown-linux-android', '-relocation-model=pic', f'-code-model={model}',
                 *([f'-mattr={attrs}'] if attrs else []), '-filetype=obj', ll, '-o', obj])
            symbols = readelf_symbols(obj)
            undefined = sorted(s['name'] for s in symbols if s['undefined'] and s['name'])
            if shutil.which('llvm-nm'):
                assert undefined == sorted(run(['llvm-nm', '-u', '--format=just-symbols', obj]).stdout.split()), (variant, model)
            named, pps = [], []
            if expected == 'accepted':
                named = sorted(names.index(n) for n in undefined if n in names)
                pps = sorted(int(n.rsplit('-pp-', 1)[1]) for n in undefined if '-pp-' in n)
                assert len(named) + len(pps) == len(undefined), (variant, undefined)
            rows = ', '.join(f'sym("{s["name"]}", {str(s["undefined"]).lower()}, {str(s["absolute"]).lower()}, {str(s["global"]).lower()})'
                             for s in symbols)
            cases.append(f'\t\t{{"{variant}.{model}", {{{rows}}}, d::reason::{expected}, "{offending}", {{{", ".join(map(str, named))}}}, '
                         f'{{{", ".join(map(str, pps))}}}}},\n')
            report[f'{variant}.{model}'] = {'expected': expected, 'offending': offending, 'symbols': len(symbols), 'undefined': undefined,
                                            'locals': sorted(s['name'] for s in symbols if not s['global'] and s['type'] in ('FUNC', 'OBJECT', 'NOTYPE') and s['name'])}
    source = (ELF_TEST.replace('@TABLE@', ', '.join(f'"{n}"' for n in names)).replace('@CASES@', ''.join(cases))
              .replace('@ENTRY@', ELF_ENTRY))
    report['result'] = build_and_run(source, work, 'elf_objects', [include]).strip()
    report['llc'] = next(line.strip() for line in run([llc, '--version']).stdout.splitlines() if 'LLVM version' in line)
    report['run'] = True
    return report


def lambda_text(control: str, binding: str) -> str:
    spec = next(s for s in LAMBDAS if s[0] == binding)
    body, _ = lambda_body(control, binding, spec[1], spec[2])
    params = spec[5]
    return f'[]({params}){body.rstrip()}'


def run_native(control: Path, candidate: Path, work: Path) -> dict:
    assert CXX, 'g++ is required (clang++ has no sanitizer runtimes here)'
    assert not (control / HEADER).exists(), 'the control tree has no classifier'
    ctext, ntext = read(control, LLVM), read(candidate, LLVM)
    table = bx.table(ntext)
    names = sorted(table)
    out = {}
    source = CLASSIFIER_TEST.replace('@TABLE@', ', '.join(f'"{n}"' for n in names))
    out['classifier'] = build_and_run(source, work, 'classifier', [candidate / 'rpcs3']).strip()

    # 7b: the real rows and the real helper; the same TU with g_escape null at the first hit; a swapped row fails.
    quiet = ['-Wno-unused-parameter']
    out['bindings'] = build_and_run(bindings_source(ntext), work, 'bindings', [candidate / 'rpcs3'], quiet).strip()
    out['bindings_null_escape'] = build_and_run(bindings_source(ntext), work, 'bindings_null', [candidate / 'rpcs3'], quiet + ['-DNULL_ESCAPE']).strip()
    swapped = ntext.replace('{"PUTLLC0_fail", reinterpret_cast<uptr>(&exec_putllc0_fail)}', '{"PUTLLC0_fail", reinterpret_cast<uptr>(&exec_putllc16_fail)}', 1)
    assert swapped != ntext
    out['negative_bindings_row_swapped_fails'] = fails_to_build_or_run(bindings_source(swapped), work, 'bindings_swapped', [candidate / 'rpcs3'], quiet)
    assert out['negative_bindings_row_swapped_fails']

    def lifted(name: str, ret: str, params: str) -> str:
        head = f'\tstatic {ret} {name}({params})\n'
        return head + body_of(ntext, head)

    source = (LIFT_TEST.replace('@L16@', lambda_text(ctext, 'PUTLLC16_fail')).replace('@L0@', lambda_text(ctext, 'PUTLLC0_fail'))
              .replace('@LM@', lambda_text(ctext, 'spu_memcpy'))
              .replace('@F16@', lifted('exec_putllc16_fail', 'void', 'spu_thread* _spu, u32 addr'))
              .replace('@F0@', lifted('exec_putllc0_fail', 'void', 'spu_thread* _spu, u32 addr'))
              .replace('@FM@', lifted('exec_spu_memcpy', 'void', 'u8* dst, const u8* src, u32 size')))
    out['lifted'] = build_and_run(source, work, 'lifted', []).strip()

    # 7c / item 10: the merged add + finalize against the reviewed two-call sequence; two plausible mistakes fail.
    jtext = read(candidate, JIT)
    out['minimal_object'] = build_and_run(minimal_source(jtext), work, 'minimal', [], quiet).strip()
    signature = 'bool jit_compiler::try_add_minimal_object(jit_cached_object object, const std::string& entry,'
    merged = braced_text(jtext, signature)
    no_hold = merged.replace('\t\tif (owner)\n\t\t{\n\t\t\theld_objects().hold(this, std::move(owner));\n\t\t}\n', '', 1)
    always_fin = merged.replace('\t\tif (added)\n\t\t{\n\t\t\tm_engine->finalizeObject();\n\t\t}\n', '\t\tm_engine->finalizeObject();\n', 1)
    early_release = merged.replace('\tif (m_announcer) m_announcer->finalized(true);\n', '\tif (m_announcer) m_announcer->finalized(true);\n\towner.reset();\n', 1)
    assert no_hold != merged and always_fin != merged and early_release != merged
    out['negative_minimal_fatal_bytes_not_held_fails'] = fails_to_build_or_run(minimal_source(jtext, no_hold), work, 'minimal_no_hold', [], quiet)
    out['negative_minimal_finalize_after_refusal_fails'] = fails_to_build_or_run(minimal_source(jtext, always_fin), work, 'minimal_always_fin', [], quiet)
    out['negative_minimal_compiles_with_extra_statement'] = not fails_to_build_or_run(minimal_source(jtext, early_release), work, 'minimal_early', [], quiet)
    assert out['negative_minimal_fatal_bytes_not_held_fails'] and out['negative_minimal_finalize_after_refusal_fails']
    assert out['negative_minimal_compiles_with_extra_statement']  # owner.reset() after the finalize is harmless: the harness is not over-strict

    # 7a: llc 18 aarch64 ELF objects through the real classifier.
    out['elf_objects'] = run_elf_objects(ntext, work, candidate / 'rpcs3')
    return out


def negative_controls(control: str, candidate: str, control_jit: str, candidate_jit: str) -> dict:
    """Each audit must reject a candidate with one plausible mistake."""
    def fails(check, *args) -> bool:
        try:
            check(*args)
        except (AssertionError, ValueError):
            return True
        return False

    swapped = candidate.replace('{"PUTLLC0_fail", reinterpret_cast<uptr>(&exec_putllc0_fail)}',
                                '{"PUTLLC0_fail", reinterpret_cast<uptr>(&exec_putllc16_fail)}', 1)
    dropped = candidate.replace('\t\t\t{"atomic_wait_engine::notify_all", reinterpret_cast<uptr>(static_cast<void(*)(const void*)>(atomic_wait_engine::notify_all))},\n', '', 1)
    body = candidate.replace('\t\t\t_spu->raddr = 0;\n\t\t}\n\t}\n\n\tvoid putllc16_pattern', '\t\t\t_spu->raddr = 1;\n\t\t}\n\t}\n\n\tvoid putllc16_pattern', 1)
    site = candidate.replace('call("PUTLLC0_fail", &exec_putllc0_fail, m_thread, _eal);', 'call("PUTLLC0_fail", &exec_putllc16_fail, m_thread, _eal);', 1)
    emitter = candidate.replace('m_ir->CreateStore(m_ir->getInt32(0), spu_ptr(&spu_thread::raddr));', 'm_ir->CreateStore(m_ir->getInt32(1), spu_ptr(&spu_thread::raddr));', 1)
    order = candidate.replace('\t\t\t\tm_engine->clearAllGlobalMappings();\n\t\t\t\tconst u64 link_started', '\t\t\t\tconst u64 link_started', 1)
    tail = candidate.replace('\t\t\t\t\tadd_loc->compiled.notify_all();\n\t\t\t\t\tadd_loc->llvm_compile_state.release(2);', '\t\t\t\t\tadd_loc->llvm_compile_state.release(2);', 1)
    jit = candidate_jit.replace('jit_compiler::try_fin(std::string& error)\n{', 'jit_compiler::try_fin(std::string& error)\n{\n\t// changed', 1)
    entry_lookup = candidate.replace('m_jit.get_engine().getFunctionAddress(m_hash)', 'm_jit.get_engine().getPointerToNamedFunction(m_hash, false)', 1)
    stub_first = candidate.replace('\t\t\t\tdirect_object_patchpoints(direct_map, direct_pp_names);\n', '', 1).replace(
        '\t\t\tif (direct_reason == direct::reason::accepted)\n\t\t\t{\n\t\t\t\t// MCJIT gets a copy',
        '\t\t\tif (direct_reason == direct::reason::accepted)\n\t\t\t{\n\t\t\t\tdirect_object_patchpoints(direct_map, direct_pp_names);\n\t\t\t\t// MCJIT gets a copy', 1)
    second_handoff = candidate.replace('\t\t\t\t\tconst u64 link_done = utils::get_tsc();\n',
                                       '\t\t\t\t\tif (!m_jit.try_fin(llvm_error)) return nullptr;\n\t\t\t\t\tconst u64 link_done = utils::get_tsc();\n', 1)
    per_table = candidate.replace('\t\tstatic const std::array<direct_binding, 27> table\n', '\t\tconst std::array<direct_binding, 27> table\n', 1)
    split_jit = candidate_jit.replace('\t\tif (added)\n\t\t{\n\t\t\tm_engine->finalizeObject();\n\t\t}\n', '', 1)
    result = {
        'table_row_swapped': fails(audit_bindings, control, swapped),
        'table_row_dropped': fails(audit_bindings, control, dropped),
        'lifted_body_changed': fails(audit_lambdas, control, body),
        'call_site_rebound': fails(audit_bindings, control, site),
        'emitter_changed': fails(audit_structure, control, emitter, control_jit, candidate_jit),
        'clear_removed': fails(audit_structure, control, order, control_jit, candidate_jit),
        'publication_changed': fails(audit_structure, control, tail, control_jit, candidate_jit),
        'jitllvm_outside_body': fails(audit_structure, control, candidate, control_jit, jit),
        'entry_by_getPointerToNamedFunction': fails(audit_structure, control, entry_lookup, control_jit, candidate_jit),
        'stubs_before_the_copy': fails(audit_structure, control, stub_first, control_jit, candidate_jit),
        'second_handoff_try_fin': fails(audit_structure, control, second_handoff, control_jit, candidate_jit),
        'table_evaluated_per_hit': fails(audit_structure, control, per_table, control_jit, candidate_jit),
        'finalize_not_merged': fails(audit_structure, control, candidate, control_jit, split_jit),
    }
    assert all(result.values()), result
    assert all(text != candidate for text in (swapped, dropped, body, site, emitter, order, tail, entry_lookup, stub_first, second_handoff, per_table))
    assert jit != candidate_jit and split_jit != candidate_jit
    return result


def local_name_negative_controls(texts: dict[str, str], table: set[str], extras: tuple) -> dict:
    """The fix-6 guard must fail when a table or patchpoint name gets an internal definition."""
    spu, translator = texts[LLVM], texts[TRANSLATOR]
    mutations = {
        'table_name_internal_function': (LLVM, spu.replace('getOrInsertFunction("spu_test_state", get_ftype<void, u8*>())',
                                                           'getOrInsertFunction("spu_escape", get_ftype<void, u8*>())', 1)),
        'patchpoint_internal': (LLVM, spu.replace('\t\t\tppfunc->setCallingConv(m_finfo->chunk->getCallingConv());\n\n\t\t\tif (m_finfo->chunk->getReturnType()',
                                                  '\t\t\tppfunc->setCallingConv(m_finfo->chunk->getCallingConv());\n\t\t\tppfunc->setLinkage(llvm::GlobalValue::InternalLinkage);\n\n'
                                                  '\t\t\tif (m_finfo->chunk->getReturnType()', 1)),
        'table_name_internal_global': (LLVM, spu.replace('m_size / 4), true, llvm::GlobalValue::InternalLinkage, nullptr);',
                                                         'm_size / 4), true, llvm::GlobalValue::InternalLinkage, nullptr, "spu_timebase_offs");', 1)),
        'chunk_named_like_a_helper': (LLVM, spu.replace('fmt::format("__spu-cx%05x-%s", addr, fmt::base57(be_t<u64>{m_hash_start}))',
                                                        'fmt::format("spu_escape%.0x%.0s", addr, fmt::base57(be_t<u64>{m_hash_start}))', 1)),
        'call_helper_internal': (TRANSLATOR, translator.replace('\t\tm_engine->updateGlobalMapping({lame.data(), lame.size()}, reinterpret_cast<uptr>(_func));\n',
                                                                '\t\tfunc->setLinkage(llvm::GlobalValue::InternalLinkage);\n'
                                                                '\t\tm_engine->updateGlobalMapping({lame.data(), lame.size()}, reinterpret_cast<uptr>(_func));\n', 1)),
    }
    result = {}
    for label, (name, mutated) in mutations.items():
        assert mutated != texts[name], label
        try:
            audit_local_names({**texts, name: mutated}, table, *extras)
        except AssertionError:
            result[label] = True
        else:
            result[label] = False
    assert all(result.values()), result
    return result
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--control', type=Path, required=True, help='the tree before the SPU direct-hit step (Core 659 + timebase)')
    parser.add_argument('--candidate', type=Path, required=True, help='the tree after it')
    parser.add_argument('--cxx', help='C++ compiler with ASan/UBSan runtimes (default: g++)')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    global CXX
    if args.cxx:
        CXX = shutil.which(args.cxx) or args.cxx
    control, candidate = args.control.resolve(), args.candidate.resolve()
    ctext, ntext = read(control, LLVM), read(candidate, LLVM)
    report = {'control': str(control), 'candidate': str(candidate),
              'control_sha256': {LLVM: sha(ctext.encode()), JIT: sha((control / JIT).read_bytes())},
              'candidate_sha256': {LLVM: sha(ntext.encode()), JIT: sha((candidate / JIT).read_bytes())}}
    report['bindings'] = audit_bindings(ctext, ntext)
    report['lambdas'] = audit_lambdas(ctext, ntext)
    report['structure'] = audit_structure(ctext, ntext, read(control, JIT), read(candidate, JIT))
    report['negative_controls'] = negative_controls(ctext, ntext, read(control, JIT), read(candidate, JIT))
    report['wiring'] = audit_wiring(candidate)
    names_texts = {LLVM: ntext, TRANSLATOR: read(candidate, TRANSLATOR)}
    extras = (read(candidate, ANALYSER), read(candidate, STRFMT), read(candidate, POLICY))
    report['local_names'] = audit_local_names(names_texts, set(bx.table(ntext)), *extras)
    report['local_names']['negative_controls'] = local_name_negative_controls(names_texts, set(bx.table(ntext)), extras)
    report['identity'] = audit_identity(control, candidate)
    with tempfile.TemporaryDirectory(prefix='spu-direct-660-') as temporary:
        report['native'] = run_native(control, candidate, Path(temporary))
    report.update(passed=True, compiler=f'{CXX} {" ".join(FLAGS)}', llvm_executed=('llc 18 only (object generation for 7a); no MCJIT here' if report['native']['elf_objects'].get('run') else 'no LLVM tool on this host (7a not run)'),
                  cmake_executed=False,
                  scope='host classifier (also on llc-18 aarch64 ELF objects), the real binding table and helper, the real '
                        'try_add_minimal_object/try_fin bodies, lifted helpers, static audits (local names included) and codegen '
                        'identity; no device claim')
    text = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
