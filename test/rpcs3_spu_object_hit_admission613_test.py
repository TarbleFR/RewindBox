#!/usr/bin/env python3
"""Build 613: SPU object-cache hits of small blocks no longer wait for the LLVM compile admission.

Black Ops II (BLES01717), Build 612 iPhone logs of 2 November 2026: every boot
rebuilds the SPU blocks it reaches; all of them are object-cache hits (one 5 s
window: 6,376 hits, 0 misses), yet they went through the admission meant for
code generation one at a time (JITMEM active_peak=1, WAITPROF527 llvm_budget_cv
10.8 s, JITPROF spu_cache_read 2.8 s), the 2.9-4.6 s frames at level and match
start.

This test reads the materialized Core (--source) and:
1. executes the real REWINDBOX_SPU_OBJECT_HIT_ADMISSION_613 block of
   SPUThread compile() (object read, validation event, admission decision),
   extracted verbatim, with stubs for the object loader and the admission:
   - hit of a block <= 16 KiB: the object is read, no admission is taken;
   - miss, rejected object, or hit of a block > 16 KiB: one admission, taken
     after the read; a refused admission returns nullptr as before;
   - the object is always read before the admission;
2. proves the change is confined to that block: removing it and restoring the
   Core 612 admission statement at its Core 612 place gives back the delivered
   Core 612 file byte for byte (pinned SHA-256);
3. recomputes the ordered CMake codegen identity recipe (CMakeLists.txt with
   JITCacheCompatibility.cmake) and requires the delivered identities
   PPU a987639e9f838d1c and SPU 477a3fa442d27917 through one exact new alias,
   while any other future SPULLVMRecompiler.cpp stays unaliased.
A later Core that changes this file again outside the 613 block (Core 660:
REWINDBOX_SPU_TIMEBASE_MAPPING_660 and REWINDBOX_SPU_DIRECT_OBJECT_HIT_660) is
accepted only as its reviewed file: its SHA-256 is the one its record pins, the
613 region is byte-identical, and reversing that file's hunks of the Core's
increment patch gives back the earlier file, on which point 2 is checked; the
file's own exact alias must lead to the same Core 612 hash.

No gameplay claim: the effect on the device is measured by the next logs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

LLVM = 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp'
COMPAT = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'
CMAKE = 'rpcs3/Emu/CMakeLists.txt'
MARK = 'REWINDBOX_SPU_OBJECT_HIT_ADMISSION_613'
CORE612_LLVM_SHA = 'deb95e09dfe245343b482b0b0cb4a20f69b50eb8694f838a87d2bfee193215ff'
EXTERNAL = {'../../3rdparty/llvm/llvm/llvm/lib/Target/AArch64/AArch64FrameLowering.cpp':
            'c6ee2a2a736b72b8f9109bbe9ad82e43a84d0ca1d5e2c75670603e423fd4c507'}
DELIVERED = {'PPU': 'a987639e9f838d1c', 'SPU': '477a3fa442d27917'}
OLD_ADMISSION = ('\t\trpcs3::ios::compile_admission admission(func.data.size() * sizeof(u32), '
                 '[] { return Emu.IsStopped(); });\n\t\tif (!admission) return nullptr;\n\n')
OBJECT_BLOCK_HEAD = '\t\t// NEOSTATION_BUILD481_SPU_OBJECT_CACHE_V1: read a previously generated\n'
ROOT = Path(__file__).resolve().parents[1]
# Later Cores that change SPULLVMRecompiler.cpp outside the 613 block, newest first: (record, increment, patch).
LATER = (('build-utils/rpcs3/core660-delta.json', 'increment_from_core659', 'build-utils/rpcs3/core660-from-659.patch'),)


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def earlier_file(raw: bytes) -> tuple[bytes, list]:
    """The file a reviewed later Core changed, reverted through each later increment (newest first)."""
    chain = []
    for record, key, patch in LATER:
        if not (ROOT / record).exists():
            continue  # without its record a later file is not accepted (point 2 then fails on it)
        increment = json.loads((ROOT / record).read_text())[key]
        if sha(raw) != increment['files_after_sha256'].get(LLVM):
            continue
        text = (ROOT / patch).read_bytes()
        require(sha(text) == increment['patch_sha256'], patch + ' differs from its record')
        start = text.index(b'diff --git a/' + LLVM.encode() + b' b/')
        end = text.find(b'\ndiff --git ', start)
        section = text[start:] if end < 0 else text[start:end + 1]
        with tempfile.TemporaryDirectory(prefix='core613-later-') as temporary:
            tree = Path(temporary)
            (tree / LLVM).parent.mkdir(parents=True)
            (tree / LLVM).write_bytes(raw)
            (tree / 'later.patch').write_bytes(section)
            subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
            subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', 'later.patch'], cwd=tree, check=True)
            raw = (tree / LLVM).read_bytes()
        require(sha(raw) == increment['files_before_sha256'][LLVM], 'the reverted file is not the one ' + record + ' starts from')
        chain.append(record)
    return raw, chain


def ios_region(text: str) -> tuple[int, int]:
    """The #ifdef RPCS3_IOS region holding the object read and the admission."""
    head = text.index(OBJECT_BLOCK_HEAD)
    start = text.rindex('#ifdef RPCS3_IOS\n', 0, head) + len('#ifdef RPCS3_IOS\n')
    end = text.index('#endif\n', head)
    return start, end


def new_block(region: str) -> str:
    start = region.index('\n\t\t// ' + MARK)
    require(region.endswith('\t\t}\n'), 'the 613 block must close the region')
    return region[start:]


def restored_612(text: str) -> bytes:
    start, end = ios_region(text)
    region = text[start:end]
    block = new_block(region)
    require(region.count(block) == 1 and OLD_ADMISSION not in text, 'one 613 block and no Core 612 admission')
    object_part = region[:-len(block)]
    require(object_part.startswith(OBJECT_BLOCK_HEAD), 'the object read opens the region')
    return (text[:start] + OLD_ADMISSION + object_part + text[end:]).encode()


HARNESS = r'''
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <optional>
#include <string>
#include <vector>

using u32 = std::uint32_t;
using usz = std::size_t;

static int g_failures = 0;
#define CHECK(cond, what) do { if (!(cond)) { std::fprintf(stderr, "FAIL: %s\n", what); ++g_failures; } } while (0)

struct trace_t { int reads = 0, admissions = 0, invalid = 0; bool read_before_admission = true; } trace;
struct scenario_t { bool hit = false, rejected = false, admit = true; } scenario;

struct jit_cached_object
{
	bool valid = false, removed_invalid = false;
	explicit operator bool() const { return valid; }
};
struct jit_cache_outcome {};
struct jit_compiler
{
	static jit_cached_object load_cached_object(const std::string&, const std::string&)
	{
		++trace.reads;
		jit_cached_object result;
		result.valid = scenario.hit && !scenario.rejected;
		result.removed_invalid = scenario.rejected;
		return result;
	}
};
namespace rpcs3::ios
{
	enum class spu_object_cache_event { invalid };
	inline void record_spu_object_cache_event(spu_object_cache_event) { ++trace.invalid; }
	class compile_admission
	{
		bool ok = false;
	public:
		compile_admission(std::size_t, const std::function<bool()>& stopped)
		{
			if (trace.reads == 0) trace.read_before_admission = false;
			++trace.admissions;
			ok = scenario.admit && !stopped();
		}
		compile_admission(const compile_admission&) = delete;
		compile_admission& operator=(const compile_admission&) = delete;
		explicit operator bool() const { return ok; }
	};
}
struct { bool IsStopped() const { return false; } } Emu;
struct { struct { bool spu_debug = false; } core; } g_cfg;
struct runtime_t { std::string path = "/cache/spuobj/"; const std::string& get_obj_cache_path() const { return path; } };
struct func_t { std::vector<u32> data; };

struct compiler_t
{
	runtime_t runtime;
	runtime_t* m_spurt = &runtime;
	std::string m_hash = "__spu-0x00000-test";

	// Returns 1 when the build proceeds past the admission, 0 for nullptr.
	int compile(const func_t& func)
	{
#include "block.inc"
		(void)spu_cache_outcome;
		(void)spu_cache_write_attempted;
		(void)use_spu_obj_cache;
		return 1;
	}
};

static int run(bool hit, bool rejected, usz guest_bytes, bool admit)
{
	trace = {};
	scenario = {hit, rejected, admit};
	compiler_t compiler;
	func_t func{std::vector<u32>(guest_bytes / sizeof(u32), 0)};
	return compiler.compile(func);
}

int main()
{
	CHECK(run(true, false, 104, true) == 1 && trace.reads == 1 && trace.admissions == 0, "small hit: read, no admission");
	CHECK(run(true, false, 16 * 1024, true) == 1 && trace.admissions == 0, "hit of exactly 16 KiB: no admission");
	CHECK(run(true, false, 16 * 1024 + 4, true) == 1 && trace.admissions == 1 && trace.read_before_admission, "large hit: admitted after the read");
	CHECK(run(false, false, 104, true) == 1 && trace.reads == 1 && trace.admissions == 1 && trace.read_before_admission, "miss: admitted after the read");
	CHECK(run(true, true, 104, true) == 1 && trace.invalid == 1 && trace.admissions == 1, "rejected object: invalid event, admitted");
	CHECK(run(false, false, 104, false) == 0 && trace.admissions == 1, "refused admission of a miss returns nullptr");
	CHECK(run(true, false, 104, false) == 1 && trace.admissions == 0, "a small hit never asks the admission");
	CHECK(run(true, false, 32 * 1024, false) == 0, "refused admission of a large hit returns nullptr");
	if (g_failures) return 1;
	std::puts("PASS");
	return 0;
}
'''


def execute(block: str, compiler: list[str], sanitize: bool) -> None:
    with tempfile.TemporaryDirectory(prefix='rpcs3-613-hit-') as temporary:
        work = Path(temporary)
        # The extracted region runs inside compiler_t::compile; its nullptr return becomes 0.
        (work / 'block.inc').write_text(block.replace('return nullptr;', 'return 0;'))
        (work / 'main.cpp').write_text(HARNESS)
        exe = work / 'hit'
        flags = ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror']
        if sanitize:
            flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
        subprocess.run([*compiler, *flags, '-I' + str(work), str(work / 'main.cpp'), '-o', str(exe)],
                       check=True, timeout=180)
        env = dict(os.environ)
        if sanitize:
            # The harness allocates nothing it keeps; leak detection needs ptrace,
            # which some CI sandboxes refuse.
            env['ASAN_OPTIONS'] = 'detect_leaks=0'
        output = subprocess.run([str(exe)], check=True, timeout=60, capture_output=True, text=True, env=env).stdout
        require(output.strip() == 'PASS', 'harness output')


def aliases(text: str) -> dict:
    found = re.findall(r'(?:if|elseif)\(source STREQUAL "([^"]+)" AND\s*actual STREQUAL "([0-9a-f]{64})"\)\s*'
                       r'set\(\$\{output\} "([0-9a-f]{64})" PARENT_SCOPE\)', text)
    result = {(path, actual): effective for path, actual, effective in found}
    require(len(result) == len(found), 'duplicate aliases')
    return result


def identity(tree: Path, cmake: str, table: dict, kind: str, replace: dict | None = None) -> str:
    names = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S).group(1).split()
    payload = ''
    for name in names:
        if name in EXTERNAL:
            digest = EXTERNAL[name]
        elif replace and name in replace:
            digest = replace[name]
        else:
            digest = sha((tree / 'rpcs3/Emu' / name).read_bytes())
        payload += name + ':' + table.get((name, digest), digest) + ';'
    return sha(payload.encode())[:16]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default=os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++') or 'c++')
    parser.add_argument('--sanitize', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    raw = (source / LLVM).read_bytes()
    text = raw.decode()
    require(text.count(MARK) == 1, 'one 613 marker in SPULLVMRecompiler.cpp')
    start, end = ios_region(text)
    region = text[start:end]
    block = new_block(region)
    require('constexpr usz unadmitted_hit_max_bytes = 16 * 1024;' in block, '16 KiB bound')
    earlier, later = earlier_file(raw)
    if later:
        earlier_text = earlier.decode()
        earlier_start, earlier_end = ios_region(earlier_text)
        require(earlier_text[earlier_start:earlier_end] == region, 'a later Core changed the 613 region')
    restored = restored_612(earlier.decode())
    require(sha(restored) == CORE612_LLVM_SHA, 'outside the 613 block the file is not the delivered Core 612 file')

    compiler = shlex.split(args.cxx)
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        compiler += ['-isysroot', sdk]
    execute(region, compiler, args.sanitize)

    compat = (source / COMPAT).read_text()
    cmake = (source / CMAKE).read_text()
    table = aliases(compat)
    candidate = sha(raw)
    require(table.get(('Cell/SPULLVMRecompiler.cpp', candidate)) == CORE612_LLVM_SHA, 'exact 613 alias to the Core 612 hash')
    unknown = sha(raw + b'\n// unknown future source\n')
    require(('Cell/SPULLVMRecompiler.cpp', unknown) not in table, 'a future source stays unaliased')
    result = {}
    for kind in ('PPU', 'SPU'):
        result[kind] = {'candidate': identity(source, cmake, table, kind),
                        'future_unknown_source': identity(source, cmake, table, kind, {'Cell/SPULLVMRecompiler.cpp': unknown})}
    require({k: v['candidate'] for k, v in result.items()} == DELIVERED, 'codegen identities changed: ' + repr(result))
    require(result['SPU']['future_unknown_source'] != DELIVERED['SPU'], 'an unknown source must change the SPU identity')
    report = {'passed': True, 'sanitized': args.sanitize, 'compiler': compiler[0],
              'spullvm_sha256': candidate, 'restored_core612_sha256': CORE612_LLVM_SHA, 'later_reviewed_cores': later,
              'codegen': result, 'executed_cases': 8, 'scope': 'extracted admission decision and codegen identity; no gameplay claim'}
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: Build 613 SPU object-hit admission (8 executed cases%s), Core 612 file outside the block, '
          'codegen identities PPU %s SPU %s' % (', ASan/UBSan' if args.sanitize else '', DELIVERED['PPU'], DELIVERED['SPU']))


if __name__ == '__main__':
    main()
