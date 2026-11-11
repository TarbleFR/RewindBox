#!/usr/bin/env python3
"""REWINDBOX_SPU_WAIT_SITE_930, executed: what a waiting SPU thread waits on, in the SPU region profile.

Build 725 (Call of Duty: Black Ops II, PID 52378, session 2): the six SPURS kernel threads were waiting in 41 % of their
samples and COREPROF SPUPROF923 named sys_spu_thread_send_event for about 98 % of them. That name is the last named
call: spu_thread::current_func is only cleared when a call is aborted (SPUThread.cpp). The sampler now classifies each
waiting sample by the thread's flags, then by the instruction at the pc the SPU LLVM recompiler saved before the
blocking call (rdch/wrch channel, the MFC command of a wrch MFC_Cmd, rchcnt, STOP code), and exports wait_sites=.

The driver checks, on the real source: the recompiler saves the pc before the blocking calls; the classifier's channel
numbers, opcodes and STOP codes are the engine's (parsed here, static_assert in the sampler); the sampler classifies
inside the waiting branch only and writes nothing to the SPU thread; the export line. It compiles the real header and
classifies real SPU instruction words (g++ ASan/UBSan, clang). Negative control, always run: a classifier that reads the
channel from the rb field is caught. Diagnostic only: no SPU behaviour changes.

    python3 test/rpcs3_spu_wait_site930_test.py --source CORE [--cxx g++] [--no-sanitizers]
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HARNESS = r'''
#include "ios/IOSSpuWaitSite930.h"
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <set>
#include <string>

namespace w = rpcs3::ios::spu_wait_site;
static int failures = 0, checks = 0;
static void check(bool ok, const char* what) { checks++; if (!ok) { failures++; std::printf("FAILED: %s\n", what); } }

// SPU RR-form words: op11 in bits 21-31, ra (the channel of rdch/wrch/rchcnt) in bits 7-13, rt in bits 0-6.
static std::uint32_t rr(std::uint32_t op11, std::uint32_t ra, std::uint32_t rt) { return op11 << 21 | (ra & 0x7f) << 7 | (rt & 0x7f) | 0x3f << 14; }
static w::site at(std::uint32_t insn, std::uint8_t cmd = 0) { return w::classify({}, insn, cmd); }

int main()
{
	check(at(rr(0x00d, 0, 5)) == w::rdch_event, "rdch SPU_RdEventStat");
	check(at(rr(0x00d, 29, 5)) == w::rdch_in_mbox, "rdch SPU_RdInMbox");
	check(at(rr(0x00d, 3, 5)) == w::rdch_signal && at(rr(0x00d, 4, 5)) == w::rdch_signal, "rdch signal 1 and 2");
	check(at(rr(0x00d, 24, 5)) == w::rdch_tag_status, "rdch MFC_RdTagStat");
	check(at(rr(0x00d, 27, 5)) == w::rdch_atomic_status, "rdch MFC_RdAtomicStat");
	check(at(rr(0x00d, 25, 5)) == w::rdch_list_stall, "rdch MFC_RdListStallStat");
	check(at(rr(0x00d, 8, 5)) == w::rdch_other, "rdch SPU_RdDec is another channel");
	check(at(rr(0x00f, 29, 5)) == w::rchcnt_wait, "rchcnt");
	check(at(rr(0x10d, 21, 5), 0xd0) == w::mfc_getllar, "wrch MFC_Cmd GETLLAR");
	check(at(rr(0x10d, 21, 5), 0xb4) == w::mfc_putllc, "wrch MFC_Cmd PUTLLC");
	check(at(rr(0x10d, 21, 5), 0xb0) == w::mfc_putlluc && at(rr(0x10d, 21, 5), 0xb8) == w::mfc_putlluc, "PUTLLUC and PUTQLLUC");
	check(at(rr(0x10d, 21, 5), 0x40) == w::mfc_get && at(rr(0x10d, 21, 5), 0x46) == w::mfc_get && at(rr(0x10d, 21, 5), 0x4a) == w::mfc_get, "GET family");
	check(at(rr(0x10d, 21, 5), 0x20) == w::mfc_put && at(rr(0x10d, 21, 5), 0x24) == w::mfc_put && at(rr(0x10d, 21, 5), 0x36) == w::mfc_put, "PUT family");
	check(at(rr(0x10d, 21, 5), 0xa0) == w::mfc_other && at(rr(0x10d, 21, 5), 0xcc) == w::mfc_other && at(rr(0x10d, 21, 5), 0x8d) == w::mfc_other, "SNDSIG, SYNC, SDCR");
	check(at(rr(0x10d, 28, 5)) == w::wrch_out_mbox, "wrch SPU_WrOutMbox");
	check(at(rr(0x10d, 30, 5)) == w::wrch_out_intr_mbox, "wrch SPU_WrOutIntrMbox (send event)");
	check(at(rr(0x10d, 23, 5)) == w::wrch_tag_update, "wrch MFC_WrTagUpdate");
	check(at(rr(0x10d, 16, 5)) == w::wrch_other, "wrch MFC_LSA is another channel");
	check(at(0x110) == w::stop_receive_event && at(0x111) == w::stop_receive_event, "STOP 0x110 and 0x111");
	check(at(0x100) == w::stop_yield, "STOP 0x100");
	check(at(0x3fff) == w::stop_other, "other STOP code");
	check(at(0x04000000u | 5) == w::not_a_call && at(0x40800000u) == w::not_a_call, "ori, il: not a blocking instruction");
	w::state_bits p; p.pause = true; p.memory = true;
	check(w::classify(p, rr(0x00d, 0, 5), 0) == w::flag_pause, "pause wins over the instruction and the memory flag");
	w::state_bits s; s.suspend = true;
	check(w::classify(s, rr(0x10d, 21, 5), 0xb4) == w::flag_suspend, "suspend wins over PUTLLC");
	w::state_bits m; m.memory = true;
	check(w::classify(m, rr(0x10d, 21, 5), 0xb4) == w::flag_memory, "memory flag");
	w::state_bits d; d.debug = true;
	check(w::classify(d, 0x110, 0) == w::flag_debug, "debug pause");
	std::set<std::string> unique;
	for (int i = 0; i < w::count; i++) unique.insert(w::names[i]);
	check(unique.size() == static_cast<std::size_t>(w::count), "one name per site");
	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures != 0;
}
'''


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def body(text: str, signature: str) -> str:
    start = text.index(signature)
    open_brace = text.index('{', start)
    depth = 0
    for index in range(open_brace, len(text)):
        depth += {'{': 1, '}': -1}.get(text[index], 0)
        if depth == 0:
            return text[open_brace:index + 1]
    raise SystemExit('FAIL: unbalanced ' + signature)


def static_checks(source: Path) -> None:
    read = lambda name: (source / name).read_text('utf-8', 'surrogateescape')
    header, dump, spu_h, opcodes, sys_spu, llvm = (read('rpcs3/ios/IOSSpuWaitSite930.h'), read('rpcs3/ios/RPCS3IOSFreezeDump.cpp'),
        read('rpcs3/Emu/Cell/SPUThread.h'), read('rpcs3/Emu/Cell/SPUOpcodes.h'), read('rpcs3/Emu/Cell/lv2/sys_spu.h'),
        read('rpcs3/Emu/Cell/SPULLVMRecompiler.cpp'))
    # The engine's numbers, as the classifier uses them.
    channel = lambda name: int(re.search(r'\b%s\s*=\s*(\d+)' % name, spu_h).group(1))
    expected = {'ch_rd_event_stat': 'SPU_RdEventStat', 'ch_rd_sig_notify1': 'SPU_RdSigNotify1', 'ch_rd_sig_notify2': 'SPU_RdSigNotify2',
                'ch_mfc_cmd': 'MFC_Cmd', 'ch_wr_tag_update': 'MFC_WrTagUpdate', 'ch_rd_tag_stat': 'MFC_RdTagStat',
                'ch_rd_list_stall_stat': 'MFC_RdListStallStat', 'ch_rd_atomic_stat': 'MFC_RdAtomicStat', 'ch_wr_out_mbox': 'SPU_WrOutMbox',
                'ch_rd_in_mbox': 'SPU_RdInMbox', 'ch_wr_out_intr_mbox': 'SPU_WrOutIntrMbox'}
    for ours, theirs in expected.items():
        value = int(re.search(r'\b%s = (\d+)' % ours, header).group(1))
        require(value == channel(theirs), f'{ours} = {value}, engine {theirs} = {channel(theirs)}')
        require(f'ch_{ours[3:]} == {theirs}' in dump.replace('rpcs3::ios::spu_wait_site::', ''), 'static_assert for ' + ours)
    for op, name in (('op_rdch', 'RDCH'), ('op_wrch', 'WRCH'), ('op_rchcnt', 'RCHCNT'), ('op_stop', 'STOP')):
        value = int(re.search(r'\b%s = (0x[0-9a-f]+)' % op, header).group(1), 16)
        require(re.search(r'\{ 0, 0x%x, GET\(%s\) \}' % (value, name), opcodes), f'{op} {value:#x} is the decoder entry of {name}')
    require('return inst >> 21;' in opcodes, 'the decoder index is the top 11 bits')
    for stop, name in (('code_stop_yield', 'SYS_SPU_THREAD_STOP_YIELD'), ('code_stop_receive_event', 'SYS_SPU_THREAD_STOP_RECEIVE_EVENT'),
                       ('code_stop_try_receive_event', 'SYS_SPU_THREAD_STOP_TRY_RECEIVE_EVENT')):
        ours = int(re.search(r'\b%s = (0x[0-9a-f]+)' % stop, header).group(1), 16)
        theirs = int(re.search(r'\b%s\s*=\s*(0x[0-9a-fA-F]+)' % name, sys_spu).group(1), 16)
        require(ours == theirs, f'{stop} {ours:#x} != {name} {theirs:#x}')
    # The recompiler saves the pc before the blocking calls the classifier reads.
    rdch, wrch = body(llvm, '	void RDCH(spu_opcode_t op)'), body(llvm, '	void WRCH(spu_opcode_t op)')
    for case in ('case SPU_RdInMbox:', 'case SPU_RdSigNotify1:', 'case SPU_RdSigNotify2:', 'case SPU_RdEventStat:'):
        segment = rdch[rdch.index(case):]
        require(segment.index('update_pc();') < segment.index('call('), 'pc saved before the call of ' + case)
    segment = rdch[rdch.index('		default:'):]
    require(segment.index('update_pc();') < segment.index('call("spu_read_channel"'), 'pc saved before a generic channel read')
    mfc = wrch[wrch.index('case MFC_Cmd:'):]
    require(mfc.count('update_pc();') >= 2 and 'call("spu_exec_mfc_cmd"' in mfc, 'pc saved before the MFC command calls')
    require('update_pc();' in body(llvm, '	void STOP(spu_opcode_t op)'), 'pc saved before STOP')
    # The sampler: the waiting branch only, nothing written to the SPU thread.
    require('#include "ios/IOSSpuWaitSite930.h"' in dump, 'the sampler includes the classifier')
    loop = body(dump, '	void run()')
    waiting = loop[loop.index('spu_tracked[i].add_waiting();'):loop.index('const char* call = spu.current_func;')]
    require('spu_wait_sites[i][site::classify(bits, insn, static_cast<u8>(spu.ch_mfc_cmd.cmd))]++;' in waiting, 'classified in the waiting branch')
    require(loop.index('spu_tracked[i].add_running(spu.pc);') < loop.index('spu_tracked[i].add_waiting();'), 'running samples are not classified')
    require('const u32 insn = spu._ref<u32>(spu.pc & 0x3fffc);' in waiting, 'the instruction read inside local storage, word-aligned')
    require(not re.search(r'spu\.[a-z_]+\s*(=|\+=|\+\+|-=)[^=]', waiting) and 'spu.state +=' not in waiting and 'spu.state -=' not in waiting,
            'the sampler writes nothing to the SPU thread')
    for flag in ('cpu_flag::pause', 'cpu_flag::suspend', 'cpu_flag::memory', 'cpu_flag::dbg_global_pause', 'cpu_flag::dbg_pause'):
        require(flag in waiting, 'flag read: ' + flag)
    require('wait_sites=%s wait_calls=%s top=%s' in dump and 'wait_calls_scope=last_named_call wait_sites_scope=flags_then_instruction_at_saved_pc' in dump,
            'export: wait_sites before wait_calls, both scopes declared')
    require(dump.count('COREPROF SPUPROF923') == 3, 'begin, thread and end lines unchanged in number')


def run(source: Path, cxx: str, sanitize: bool, mutation: str | None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory(prefix='spuwait930-') as temporary:
        work = Path(temporary)
        include = work / 'inc' / 'ios'
        include.mkdir(parents=True)
        header = (source / 'rpcs3/ios/IOSSpuWaitSite930.h').read_text()
        if mutation == 'rb_channel':
            changed = header.replace('const std::uint32_t channel = (insn >> 7) & 0x7f;', 'const std::uint32_t channel = (insn >> 14) & 0x7f;')
            require(changed != header, 'mutation applied')
            header = changed
        (include / 'IOSSpuWaitSite930.h').write_text(header)
        (work / 'h.cpp').write_text(HARNESS)
        flags = ['-O1', '-g', '-fsanitize=address,undefined', '-fno-sanitize-recover=undefined'] if sanitize else ['-O2']
        build = subprocess.run([cxx, '-std=c++20', '-Wall', '-Wextra', '-Werror', *flags, '-I', str(work / 'inc'), str(work / 'h.cpp'), '-o', str(work / 'h')],
                               capture_output=True, text=True)
        require(build.returncode == 0, 'harness does not build:\n' + build.stderr[-3000:])
        done = subprocess.run([str(work / 'h')], capture_output=True, text=True, timeout=120)
        return done.returncode, done.stdout


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    static_checks(source)
    sanitize = not args.no_sanitizers and Path(args.cxx).name.startswith('g++') and sys.platform.startswith('linux')
    code, out = run(source, args.cxx, sanitize, None)
    require(code == 0 and out.strip().endswith('"failures": 0}'), 'candidate:\n' + out[-2000:])
    mcode, mout = run(source, args.cxx, sanitize, 'rb_channel')
    require(mcode != 0 and 'rdch SPU_RdInMbox' in mout, 'the rb_channel mutation is not caught:\n' + mout[-1500:])
    result = out.strip().splitlines()[-1]
    if args.report:
        args.report.write_text(json.dumps({'passed': True, 'result': result, 'mutation': 'rb_channel caught'}) + '\n')
    print('PASS: SPU wait sites (%s); the rb_channel mutation is caught' % result)
    return 0


if __name__ == '__main__':
    sys.exit(main())
