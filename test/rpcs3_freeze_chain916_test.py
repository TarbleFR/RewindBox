#!/usr/bin/env python3
"""REWINDBOX_FREEZE_CHAIN_916 and REWINDBOX_LEVERS_EXPORT_916, executed.

Build 718, Black Flag (BLES01882, PID 44597): twelve PPU threads waited in _sys_lwcond_queue_wait and the stall dump
has no lwcond line: Core 908 matched a condition's waiters by r3 of the waiting threads, where the system call has
already stored its return value (the dump shows r3=0x0). The waiters are now the condition's own queue, and the dump
adds the return addresses of the waiting threads from their stack back chain.
Same build: CONFIG_LAYERS levers627= has 18 digits although Core 912 and later compose 21 (PUT horizon, heavy PUTLLC
trace, PPU region profile): the export limit was 18, and the host reads digits 20 and 21 from that line before it
asks for a capture, so no capture request could be sent.

The driver compiles the real rpcs3/ios/IOSFreezeChain916.h (queue walk: order, cap and `more`, a queue that loops;
back chain: a three-frame stack, an unreadable frame, a chain that does not go up, a chain that jumps too far, an
unaligned pointer) and the real rpcs3/ios/RPCS3IOSBootDiagnostics.h (a 21-digit and a 30-digit lever string are
exported whole; the limit of the previous Core cut them at 18: negative control with --previous).
Static: the stall dump reads the condition's queue under its lock and no longer reads r3 for it.

    python3 test/rpcs3_freeze_chain916_test.py --source CORE [--previous CORE914] [--cxx g++]
"""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import tempfile

CHAIN = r'''
#include "ios/IOSFreezeChain916.h"
#include <cstdint>
#include <cstdio>
#include <map>

namespace chain = rpcs3::ios::freeze_chain;
static int failures = 0, checks = 0;
static void check(bool ok, const char* what) { checks++; if (!ok) { failures++; std::printf("FAILED: %s\n", what); } }
struct node { std::uint32_t id; const node* next; };

int main()
{
	node c{0x1000009, nullptr}, b{0x1000008, &c}, a{0x1000000, &b};
	const auto next = [](const node* n) { return n->next; };
	const auto id = [](const node* n) { return n->id; };
	std::uint32_t out[8]{};
	bool more = true;
	check(chain::queue_ids(&a, next, id, out, 8, more) == 3 && out[0] == 0x1000000 && out[1] == 0x1000008 && out[2] == 0x1000009 && !more, "the queue in its order");
	check(chain::queue_ids(&a, next, id, out, 2, more) == 2 && more, "the cap is said");
	check(chain::queue_ids(static_cast<const node*>(nullptr), next, id, out, 8, more) == 0 && !more, "an empty queue");
	c.next = &a; // a queue that loops is still bounded
	check(chain::queue_ids(&a, next, id, out, 8, more) == 8 && more, "a looping queue ends at the cap");

	std::map<std::uint32_t, std::uint64_t> stack;
	const auto readable = [&](std::uint32_t at) { return stack.count(at) != 0; };
	const auto read64 = [&](std::uint32_t at) { return stack[at]; };
	// Three frames: sp 0xd0010000 -> 0xd0010080 -> 0xd0010140 -> 0xd0010200 (no entry: the walk stops there).
	stack = {{0xd0010000, 0xd0010080}, {0xd0010090, 0x2c05a94}, {0xd0010080, 0xd0010140}, {0xd0010150, 0x5e3408}, {0xd0010140, 0xd0010200}, {0xd0010210, 0x7bfed8}};
	std::uint32_t frames[10]{};
	check(chain::back_chain(0xd0010000, readable, read64, frames, 10) == 3 && frames[0] == 0x2c05a94 && frames[1] == 0x5e3408 && frames[2] == 0x7bfed8, "the saved return addresses, innermost first");
	check(chain::back_chain(0xd0010000, readable, read64, frames, 2) == 2, "the cap of frames");
	check(chain::back_chain(0, readable, read64, frames, 10) == 0 && chain::back_chain(0xd0010008, readable, read64, frames, 10) == 0 &&
		chain::back_chain(0x1d0010000ull, readable, read64, frames, 10) == 0 && chain::back_chain(0xd0020000, readable, read64, frames, 10) == 0,
		"a null, unaligned, 64-bit or unreadable stack pointer gives nothing");
	stack[0xd0010080] = 0xd0010080; // the chain does not go up
	check(chain::back_chain(0xd0010000, readable, read64, frames, 10) == 1, "a chain that does not go up ends the walk");
	stack[0xd0010080] = 0xd0010000; // downwards
	check(chain::back_chain(0xd0010000, readable, read64, frames, 10) == 1, "a chain that goes down ends the walk");
	stack[0xd0010080] = 0xd0210140; stack[0xd0210150] = 0x1234; // more than 1 MiB above
	check(chain::back_chain(0xd0010000, readable, read64, frames, 10) == 1, "a jump of more than 1 MiB ends the walk");
	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures != 0;
}
'''

LEVERS = r'''
#include "ios/RPCS3IOSBootDiagnostics.h"
#include <cstdio>
#include <string>

int main()
{
	using namespace rpcs3::ios::boot_diagnostics;
	int failures = 0;
	for (const std::string digits : {std::string("010111011111111112100"), std::string("010111011111111112100111000111"), std::string("0101110111111111")})
	{
		config_rsx rsx{};
		rsx.title = "BLES01717";
		rsx.levers627 = digits;
		const std::string line = format_config_rsx_line(rsx);
		const bool whole = line.find(" levers627=" + digits + " ") != std::string::npos;
		std::printf("%s digits=%zu exported_whole=%d\n", EXPECT_WHOLE ? "current" : "previous", digits.size(), whole ? 1 : 0);
		if (whole != (EXPECT_WHOLE || digits.size() <= 18)) failures++;
	}
	return failures != 0;
}
'''


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def compile_and_run(cxx: str, source: Path, folder: Path, name: str, code: str, defines=()) -> str:
    (folder / (name + '.cpp')).write_text(code)
    binary = folder / name
    build = subprocess.run([cxx, '-std=c++20', '-O1', '-Wall', '-Wextra', *defines, '-I', str(source / 'rpcs3'), '-I', str(source), str(folder / (name + '.cpp')), '-o', str(binary)],
                           capture_output=True, text=True)
    require(build.returncode == 0, name + ' does not build:\n' + build.stderr[-3000:])
    run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
    require(run.returncode == 0, name + ':\n' + run.stdout[-2000:])
    return run.stdout.strip()


def static_checks(source: Path) -> None:
    dump = (source / 'rpcs3/ios/RPCS3IOSFreezeDump.cpp').read_text('utf-8', 'surrogateescape')
    begin = dump.index('// REWINDBOX_FREEZE_CHAIN_916: the waiters are read from each condition')
    block = dump[begin:dump.index('if (g_fxo->is_init<id_manager::id_map<named_thread<spu_thread>>>())', begin)]
    require('cond.mutex.try_lock_shared()' in block and 'cond.mutex.unlock_shared();' in block and 'freeze_chain::queue_ids(+cond.sq' in block,
            "a condition's waiters are its own queue, read under its lock (only tried)")
    require('gpr[3]' not in block, 'no register of the waiting threads names the condition')
    require('lwconds.insert(lwconds.begin(), std::move(state));' in block, 'the condition of the first PPU thread comes first')
    require('deep.push_back(ppu_stack_line(*ppus[i]));' in dump and 'freeze_chain::back_chain(ppu.gpr[1]' in dump, 'the stack lines of the waiting threads')
    require(dump.count('vm::check_addr(addr, vm::page_readable, 8)') >= 1, 'the back chain reads checked guest addresses only')
    boot = (source / 'rpcs3/ios/RPCS3IOSBootDiagnostics.h').read_text()
    require('append_text(line, "levers627", rsx.levers627, levers627_limit);' in boot and 'constexpr std::size_t levers627_limit = 48;' in boot,
            'the lever string is exported whole')
    system = (source / 'rpcs3/Emu/System.cpp').read_text('utf-8', 'surrogateescape')
    require(system.count('\tios_add_lever(ios_levers.') == 21, 'the Core composes 21 lever digits')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--previous', type=Path)
    parser.add_argument('--cxx', default='g++')
    args = parser.parse_args()
    source = args.source.resolve()
    static_checks(source)
    with tempfile.TemporaryDirectory(prefix='chain916-') as temporary:
        folder = Path(temporary)
        chain = compile_and_run(args.cxx, source, folder, 'chain', CHAIN, ['-Werror'])
        require(chain.endswith('"failures": 0}'), 'the walks: ' + chain)
        levers = compile_and_run(args.cxx, source, folder, 'levers', LEVERS, ['-DEXPECT_WHOLE=1'])
        require('digits=21 exported_whole=1' in levers and 'digits=30 exported_whole=1' in levers, 'the lever export: ' + levers)
        control = ''
        if args.previous:
            old = compile_and_run(args.cxx, args.previous.resolve(), folder, 'levers_previous', LEVERS, ['-DEXPECT_WHOLE=0'])
            require('digits=21 exported_whole=0' in old and 'digits=16 exported_whole=1' in old, 'the previous Core is expected to cut the 21 digits: ' + old)
            control = '; the previous Core cuts 21 digits at 18'
    print('PASS: lwcond waiters from the kernel queue, stack back chain, lever digits exported whole (%s)%s' % (chain.splitlines()[-1], control))
    return 0


if __name__ == '__main__':
    sys.exit(main())
