#!/usr/bin/env python3
"""Build 616: the three RPCS3 Core 616 changes, reverted exactly and executed on the host.

Core 616 is Core 613 plus build-utils/rpcs3/core616-from-613.patch, insertions only:

1. REWINDBOX_ZCULL_POLL_NO_WAIT_616 (VKGSRender.cpp check_occlusion_query_status):
   a non-forced ZCULL poll reports a query ready only when gathering its host
   queries will not wait for the GPU. Assassin's Creed (BLES00158), Build 614
   logs: 4.1-4.4 s of every 5 s window inside report reads, about one GPU wait
   per submitted command buffer. REWINDBOX_ZCULL_WAIT_PROBE_616 splits that wait
   by the path that asked for it (COREPROF ZCULLWAIT616).
2. REWINDBOX_ZCLIP_WINDOW_Z_616 (RSXVertexPrologue.glsl, Black Ops II only):
   the vertex fallback (no float64, no unrestricted depth range: MoltenVK)
   compresses window Z above 1, not clip-space Z, so the draws pinned in front
   of the scene (clip [1, 1e19]) keep their depth order.
3. REWINDBOX_SPU_OBJECT_PREFETCH_616 (ios/IOSSpuObjectPrefetch.h, JITLLVM.cpp,
   SPUCommonRecompiler.cpp, System.cpp; Black Ops II only): the title's SPU
   object files are read into memory ahead of the compile threads, which take
   each one once and inflate and validate it as after their own read.

This test reads the materialized Core (--source) and:
- applies the incremental patch in reverse to a copy of the touched files and
  requires the delivered Core 613 files byte for byte (pinned SHA-256), every
  hunk being an insertion that names its 616 marker;
- compiles and runs the real predicate and gather of the ZCULL change against a
  query manager mock, exhaustively: the poll reports ready exactly when the
  gather does not wait, never earlier than upstream, and counts the deferred polls;
- runs the real IOSSpuObjectPrefetch.h store (plan order and bounds, one take
  per object, claims, drops, failures, stop, restart, concurrent takes) and the
  real load_compressed() body of JITLLVM.cpp on gzip members made by zlib;
- runs the real fallback transform of RSXVertexPrologue.glsl as C++ (GLSL float
  literals kept as float) with the clip range and viewport Z of the BLES01717
  capture of RPCS3 issue #13227: without the 616 define every pinned fragment
  gets one depth; with it the depth follows the view distance;
- checks the title scope (constexpr levers) and, with --glslang, that the SPIR-V
  of a vertex shader without the define is byte-identical to Core 613's.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import os
from pathlib import Path
import random
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / 'build-utils/rpcs3/core616-from-613.patch'
NEW_FILE = 'rpcs3/ios/IOSSpuObjectPrefetch.h'
# Delivered Core 613 files (payload 3d40b7de...), LF-or-CRLF bytes as shipped.
CORE613 = {
    'Utilities/JITLLVM.cpp': '772636dc0bd451e1c580a677a5450647f0727b16d6105d9f304d8aee9b0112bf',
    'rpcs3/Emu/CPU/JITCacheCompatibility.cmake': '94e9a5191779071a8c1cb27708f412051842fb1d9a4ecddb4147213b7be31253',
    'rpcs3/Emu/Cell/SPUCommonRecompiler.cpp': '6fecf56f4e20f36b93413ee702958cbf7faaad95f91e59730b915a761207e1fb',
    'rpcs3/Emu/RSX/Program/GLSLCommon.cpp': '8b36c1e2cac8760a842ed180906d53ca87caf7ff3ffe617bb4e7bc4aa25cdd53',
    'rpcs3/Emu/RSX/Program/GLSLSnippets/RSXProg/RSXVertexPrologue.glsl': 'ceb99480a9e91d71566853bc0b00e88f64c9006457497cffc7285c2a927298c7',
    'rpcs3/Emu/RSX/Program/GLSLTypes.h': '80668e419f75c9a10bf917c03157e3238e6cbb8946dd6be7f069e972d0de48b4',
    'rpcs3/Emu/RSX/RSXThread.cpp': '2b8c3fd1cb2b0431cdd464efa9836133f3cab4ede4b45c0553bd5129a466ace4',
    'rpcs3/Emu/RSX/RSXZCULL.cpp': '0bd9062ea715958ccbd9e262f3b76501b50532181204e2278fb73fccc6a983d6',
    'rpcs3/Emu/RSX/VK/VKGSRender.cpp': 'c22c6c6fa1c15cd52222fa75af6e1dc9608c9331bfe045808a3f32abe458db0f',
    'rpcs3/Emu/RSX/VK/VKQueryPool.cpp': '48058196bb3faba20082f5c3a9b82cd816c0ac52a52faa7fdd30082975d52d55',
    'rpcs3/Emu/RSX/VK/VKVertexProgram.cpp': 'bcba0cbe6063f916b02041345059a0aa9eeff59c9f5e872f030cf9fa263f4c8a',
    'rpcs3/Emu/System.cpp': 'ea22852fd8519f645b1fe894d41aac055e542aacdec7f64b22a68b1a80ff273a',
    'rpcs3/ios/IOSRsxSyncProfile.h': '5a44dc14238caca5fa3d0b4956accfb40c64d5e731471f42cb564f5408e66285',
    'rpcs3/ios/IOSTitleLevers.h': '42dea18801bafe08dc96b50fae2a5003f492fb498b97ea264d67b673a414a144',
    'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp': 'a4b5cee689c61cd23130ac2d5048745367db96dd4e3944924ef5f1b1a1316b1c',
    'rpcs3/ios/RPCS3IOSExperimentalPolicy.h': 'e6556e47f85ff6863452df70c085806b8d1ee406a1e29cab58656e27dc89e081',
    'rpcs3/ios/RPCS3IOSPerformance.cpp': '96d2b968534fc7dbe345333142fc4121a908648321bbed63088462eb7a9dfd81',
}
MARKERS = ('REWINDBOX_ZCULL_POLL_NO_WAIT_616', 'REWINDBOX_ZCULL_WAIT_PROBE_616', 'REWINDBOX_ZCLIP_WINDOW_Z_616',
           'REWINDBOX_SPU_OBJECT_PREFETCH_616')
PROLOGUE = 'rpcs3/Emu/RSX/Program/GLSLSnippets/RSXProg/RSXVertexPrologue.glsl'


def sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def require(condition, message):
    if not condition:
        raise SystemExit('FAIL: ' + message)


def patch_files(text: str) -> list[str]:
    return re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)


def hunks(text: str):
    """(file, added lines) for every hunk; removed lines are reported as None."""
    current, result, added, removed = None, [], [], 0
    for line in text.splitlines():
        if line.startswith('diff --git '):
            if added or removed:
                result.append((current, added, removed))
            current, added, removed = line.split(' b/', 1)[1], [], 0
        elif line.startswith('@@'):
            if added or removed:
                result.append((current, added, removed))
            added, removed = [], 0
        elif line.startswith('+') and not line.startswith('+++'):
            added.append(line[1:])
        elif line.startswith('-') and not line.startswith('---'):
            removed += 1
    if added or removed:
        result.append((current, added, removed))
    return result


def restore(source: Path, work: Path, core613: dict) -> Path:
    raw = PATCH.read_bytes()
    text = raw.decode()
    files = patch_files(text)
    tree = work / 'tree'
    for name in files:
        target = tree / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(PATCH)], cwd=tree, check=True, timeout=60)
    require(not (tree / NEW_FILE).exists(), 'the reverse patch removes the new prefetch header')
    for name in files:
        if name == NEW_FILE:
            continue
        restored = sha((tree / name).read_bytes())
        require(name in core613, 'pinned Core 613 digest for ' + name)
        require(restored == core613[name], name + ' differs from Core 613 outside the 616 insertions')
    return tree


def extract_between(text: str, start: str, end: str) -> str:
    begin = text.index(start) + len(start)
    return text[begin:text.index(end, begin)]


def braced_after(text: str, anchor: str) -> str:
    """The statement that follows anchor, from its first '{' to the matching '}'."""
    position = text.index(anchor)
    opening = text.index('{', position)
    depth = 0
    for index in range(opening, len(text)):
        if text[index] == '{':
            depth += 1
        elif text[index] == '}':
            depth -= 1
            if depth == 0:
                return text[position:index + 1]
    raise SystemExit('FAIL: unbalanced braces after ' + anchor)


def compile_and_run(work: Path, name: str, sources: dict, compiler: list[str], flags: list[str], includes: list[Path],
                    libs: list[str] = (), env_extra: dict | None = None, args: list[str] = ()) -> str:
    folder = work / name
    folder.mkdir(parents=True, exist_ok=True)
    for file_name, content in sources.items():
        (folder / file_name).write_text(content)
    exe = folder / 'run'
    subprocess.run([*compiler, *flags, '-I' + str(folder), *('-I' + str(path) for path in includes), str(folder / 'main.cpp'),
                    '-o', str(exe), *libs], check=True, timeout=300)
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', TSAN_OPTIONS='halt_on_error=1', **(env_extra or {}))
    result = subprocess.run([str(exe), *args], timeout=300, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        raise SystemExit('FAIL: harness %s exited %d\n%s\n%s' % (name, result.returncode, result.stdout[-4000:], result.stderr[-4000:]))
    return result.stdout


ZCULL_HARNESS = r'''
#include <cstdint>
#include <cstdio>
#include <vector>
#include "ios/IOSRsxSyncProfile.h"
using u32 = std::uint32_t;
using u64 = std::uint64_t;
struct manager
{
	std::vector<int> state; // 0 pending on the GPU, 1 ready without a hit, 2 ready with a hit
	int waits = 0;
	bool check_query_status(u32 index) const { return state[index] != 0; }
	u32 get_query_result(u32 index)
	{
		if (state[index] == 0) { waits++; state[index] = 1; } // the MoltenVK wait, then no hit
		return state[index] == 2 ? 7u : 0u;
	}
};
static struct { struct { bool precise_zpass_count = false; } video; } g_cfg;
static struct { std::vector<u32> indices; } data;
struct query_info { u32 result = 0; };
static manager mgr;
static manager* m_occlusion_query_manager = &mgr;
static bool predicate()
{
#include "predicate.inc"
}
static void gather(query_info* query)
{
#include "gather.inc"
}
int main()
{
	namespace sync = rpcs3::ios::rsx_sync;
	long cases = 0, upstream_blocking = 0, deferred_cases = 0, failures = 0;
	for (unsigned n = 1; n <= 4; n++)
	{
		std::vector<int> states(n, 0);
		for (unsigned code = 0; code < 81u; code++)
		{
			unsigned rest = code;
			for (unsigned i = 0; i < n; i++) { states[i] = rest % 3; rest /= 3; }
			if (rest && n < 4) continue;
			for (const bool precise : {false, true})
			{
				g_cfg.video.precise_zpass_count = precise;
				data.indices.clear();
				for (unsigned i = 0; i < n; i++) data.indices.push_back(i);
				mgr.state = states; mgr.waits = 0;
				const u64 deferred_before = sync::zcull_poll_deferred.load();
				const bool ready = predicate();
				const bool deferred = sync::zcull_poll_deferred.load() != deferred_before;
				const int predicate_waits = mgr.waits;
				mgr.state = states; mgr.waits = 0;
				query_info query{};
				gather(&query);
				const bool gather_waits = mgr.waits != 0;
				const bool upstream_ready = states[0] != 0;
				bool expected_deferred = !ready && states[0] != 0;
				cases++;
				if (upstream_ready && gather_waits) upstream_blocking++;
				if (deferred) deferred_cases++;
				if (predicate_waits) { std::printf("predicate waited\n"); failures++; }
				if (ready == gather_waits) { std::printf("ready=%d but gather waits=%d\n", ready, gather_waits); failures++; }
				if (ready && !upstream_ready) { std::printf("ready before upstream\n"); failures++; }
				if (deferred != expected_deferred) { std::printf("deferred mismatch\n"); failures++; }
			}
		}
	}
	std::printf("{\"cases\": %ld, \"upstream_blocking\": %ld, \"deferred\": %ld, \"failures\": %ld}\n", cases, upstream_blocking, deferred_cases, failures);
	// Probe paths: the innermost scope wins and is restored on exit.
	{
		const sync::ZcullPathScope outer(sync::t_zcull_forced_path, sync::zcull_cond_render);
		const sync::ZcullPathScope inner(sync::t_zcull_read_path, sync::t_zcull_forced_path);
		sync::record_zcull_wait(5); sync::count_zcull_gather();
	}
	sync::record_zcull_wait(2); sync::count_zcull_gather();
	const auto cond = sync::zcull_wait_ticks[sync::zcull_cond_render].take();
	const auto poll = sync::zcull_wait_ticks[sync::zcull_poll].take();
	if (cond.count != 1 || cond.total != 5 || poll.count != 1 || poll.total != 2 ||
		sync::zcull_gathers[sync::zcull_cond_render].load() != 1 || sync::zcull_gathers[sync::zcull_poll].load() != 1 ||
		sync::t_zcull_read_path != sync::zcull_poll || sync::t_zcull_forced_path != sync::zcull_forced)
	{
		std::printf("probe paths wrong\n"); failures++;
	}
	return failures ? 1 : 0;
}
'''

PREFETCH_HARNESS = r'''
#include <cstdio>
#include <future>
#include <map>
#include <random>
#include "ios/IOSSpuObjectPrefetch.h"
namespace pf = rpcs3::ios::spu_object_prefetch;
static int failures = 0;
#define CHECK(c, w) do { if (!(c)) { std::printf("FAIL: %s (line %d)\n", w, __LINE__); ++failures; } } while (0)
static void wait_done(pf::store& s)
{
	for (int i = 0; i < 20000 && !s.current().done; i++) std::this_thread::sleep_for(std::chrono::microseconds(100));
}
int main()
{
	// plan(): only .gz members within bounds, newest first, then name; the budget skips what does not fit.
	{
		std::vector<pf::candidate> entries{{"old.obj.gz", 100, 1}, {"new.obj.gz", 100, 9}, {"b.obj.gz", 100, 5}, {"a.obj.gz", 100, 5},
			{"raw.obj", 100, 9}, {"tiny.obj.gz", 10, 9}, {"huge.obj.gz", 600, 9}, {"big.obj.gz", 250, 8}, {"marker", 30, 9}, {"small.obj.gz", 40, 2}};
		const auto chosen = pf::plan(entries, 400, 500);
		std::vector<std::string> names;
		for (const auto& c : chosen) names.push_back(c.name);
		CHECK((names == std::vector<std::string>{"new.obj.gz", "big.obj.gz", "small.obj.gz"}), "plan order, bounds and budget");
		const auto all = pf::plan(entries);
		std::vector<std::string> all_names;
		for (const auto& c : all) all_names.push_back(c.name);
		CHECK((all_names == std::vector<std::string>{"huge.obj.gz", "new.obj.gz", "big.obj.gz", "a.obj.gz", "b.obj.gz", "small.obj.gz", "old.obj.gz"}),
			"default bounds keep every compressed object of at least 18 bytes, newest first then by name");
	}
	std::map<std::string, std::vector<unsigned char>> disk;
	std::vector<pf::candidate> entries;
	for (int i = 0; i < 64; i++)
	{
		const std::string name = "o" + std::to_string(i) + ".obj.gz";
		disk["/c/" + name] = std::vector<unsigned char>(20 + i, static_cast<unsigned char>(i));
		entries.push_back({name, static_cast<std::uint64_t>(20 + i), i});
	}
	entries.push_back({"wrong.obj.gz", 50, 100});
	disk["/c/wrong.obj.gz"] = std::vector<unsigned char>(49, 1); // size changed on disk
	std::atomic<int> reads{0};
	const auto reader = [&](const std::string& path, std::uint64_t expected, std::vector<unsigned char>& out)
	{
		reads++;
		auto it = disk.find(path);
		if (it == disk.end()) return false;
		out = it->second;
		return out.size() == expected;
	};
	pf::store s;
	CHECK(!s.take("/c/o1.obj.gz"), "inactive store serves nothing");
	s.start("/c/", pf::plan(entries), reader);
	wait_done(s);
	{
		const auto g = s.current();
		CHECK(g.active && g.done && g.planned == 65 && g.resident == 64 && g.pending == 0, "every planned object read once");
		const auto w = s.take_window();
		CHECK(w.read == 64 && w.failures == 1 && w.dropped == 0 && w.hits == 0, "read and failure counters");
		auto bytes = s.take("/c/o5.obj.gz");
		CHECK(bytes && *bytes == disk["/c/o5.obj.gz"], "same bytes as the file");
		CHECK(!s.take("/c/o5.obj.gz"), "taken once");
		CHECK(!s.take("/c/wrong.obj.gz"), "a failed read is not served");
		CHECK(!s.take("/c/unknown.obj.gz"), "unknown object");
		const auto w2 = s.take_window();
		CHECK(w2.hits == 1 && w2.hit_bytes == 25 && w2.claimed == 0, "hit counters");
		CHECK(s.current().resident == 63, "resident after a take");
	}
	s.stop();
	CHECK(!s.current().active && s.current().resident == 0 && s.current().resident_bytes == 0, "stop frees everything");
	CHECK(!s.take("/c/o6.obj.gz"), "nothing after stop");
	// Claims: an object a compile thread asks for first is skipped or dropped, never kept twice.
	{
		std::promise<void> gate;
		std::shared_future<void> opened = gate.get_future().share();
		std::atomic<bool> reading_first{false};
		const auto slow_reader = [&](const std::string& path, std::uint64_t expected, std::vector<unsigned char>& out)
		{
			if (path == "/c/o63.obj.gz") { reading_first = true; opened.wait(); }
			return reader(path, expected, out);
		};
		reads = 0;
		s.start("/c/", pf::plan(entries), slow_reader);
		while (!reading_first) std::this_thread::yield();
		CHECK(!s.take("/c/o63.obj.gz"), "claimed while being read");
		CHECK(!s.take("/c/o0.obj.gz"), "claimed before being read");
		gate.set_value();
		wait_done(s);
		const auto w = s.take_window();
		CHECK(w.claimed == 2 && w.dropped == 1 && w.read == 62, "one drop, one skip");
		CHECK(reads == 64, "the claimed object that was not started is never read");
		CHECK(!s.take("/c/o63.obj.gz") && !s.take("/c/o0.obj.gz"), "claimed objects stay on the disk path");
		CHECK(s.current().resident == 62, "resident excludes claims");
	}
	// Concurrent takes while the worker reads: each object served at most once.
	{
		s.start("/c/", pf::plan(entries), reader);
		std::atomic<int> served{0};
		std::vector<std::thread> takers;
		for (int t = 0; t < 4; t++)
		{
			takers.emplace_back([&, t]()
			{
				std::mt19937 rng(t);
				for (int i = 0; i < 400; i++)
				{
					if (s.take("/c/o" + std::to_string(rng() % 64) + ".obj.gz")) served++;
				}
			});
		}
		for (auto& t : takers) t.join();
		wait_done(s);
		const auto w = s.take_window();
		const auto g = s.current();
		CHECK(static_cast<std::uint64_t>(served.load()) == w.hits, "hits counted");
		CHECK(w.hits + g.resident + w.dropped + w.claimed - w.dropped == 64 || w.hits + g.resident + w.claimed == 64 + w.dropped, "conservation");
		CHECK(w.hits + g.resident <= 64, "never more than the planned objects");
		s.stop();
	}
	std::printf("{\"failures\": %d}\n", failures);
	return failures ? 1 : 0;
}
'''

LOAD_HARNESS = r'''
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <memory>
#include <vector>
using u64 = std::uint64_t;
namespace llvm
{
struct MemoryBuffer
{
	std::vector<char> bytes;
	virtual ~MemoryBuffer() = default;
	std::size_t getBufferSize() const { return bytes.size(); }
};
struct WritableMemoryBuffer : MemoryBuffer
{
	char* getBufferStart() { return bytes.data(); }
	static std::unique_ptr<WritableMemoryBuffer> getNewUninitMemBuffer(std::size_t size)
	{
		auto result = std::make_unique<WritableMemoryBuffer>();
		result->bytes.resize(size);
		return result;
	}
};
}
namespace utils { inline u64 get_tsc() { return 0; } }
namespace jit_phase
{
enum phase { spu_cache_read };
struct scope { u64 bytes = 0; scope(phase, u64 (*)()) {} };
}
#include "Utilities/JITObjectBuffer.h"
struct ObjectCache
{
#include "load_compressed.inc"
};
static std::vector<unsigned char> slurp(const char* path)
{
	std::ifstream in(path, std::ios::binary);
	return std::vector<unsigned char>(std::istreambuf_iterator<char>(in), {});
}
int main(int, char** argv)
{
	int failures = 0;
	const auto gz = slurp(argv[1]);
	const auto raw = slurp(argv[2]);
	const auto out = ObjectCache::load_compressed(gz, jit_phase::spu_cache_read);
	if (!out || out->getBufferSize() != raw.size() || std::memcmp(out->bytes.data(), raw.data(), raw.size())) { std::printf("inflate differs\n"); failures++; }
	auto truncated = gz; truncated.resize(gz.size() - 9);
	if (ObjectCache::load_compressed(truncated, jit_phase::spu_cache_read)) { std::printf("truncated accepted\n"); failures++; }
	auto corrupt = gz; corrupt[gz.size() - 6] ^= 0x5a; // CRC32
	if (ObjectCache::load_compressed(corrupt, jit_phase::spu_cache_read)) { std::printf("bad CRC accepted\n"); failures++; }
	if (ObjectCache::load_compressed(std::vector<unsigned char>(10, 0), jit_phase::spu_cache_read)) { std::printf("short accepted\n"); failures++; }
	std::printf("{\"failures\": %d, \"bytes\": %zu}\n", failures, raw.size());
	return failures ? 1 : 0;
}
'''

ZCLIP_HARNESS = r'''
#include <cmath>
#include <cstdio>
#include <vector>
struct vec4
{
	float x, y, z, w;
	vec4(float x_, float y_, float z_, float w_) : x(x_), y(y_), z(z_), w(w_) {}
};
inline float min(float a, float b) { return a < b ? a : b; }
#define in
#include "fallback.inc"
#undef in
static float depth_of(float z, float w, float n, float f)
{
	const vec4 out = apply_zclip_xform(vec4(0.f, 0.f, z, w), n, f);
	return out.z / out.w;
}
int main()
{
	// BLES01717 capture (#13227): clip [1, 1e19], viewport Z scale 1e19 over offset 1, reversed depth.
	const float clip_min = 1.0f, clip_max = 9.999999980506448e18f, scale = 9.99999888099482e18f, offset = 1.0f;
	const float near_distance = 4.0f, far_distance = 32768.0f;
	std::printf("{\"infinite\": [");
	const float views[] = {4.0f, 4.5f, 6.0f, 8.0f, 16.0f, 40.0f, 400.0f};
	for (unsigned i = 0; i < 7; i++)
	{
		const float w = views[i];
		const float z_clip = near_distance; // reversed infinite projection: z_ndc = n / w
		std::printf("%s%.9g", i ? ", " : "", depth_of(scale * z_clip + offset * w, w, clip_min, clip_max));
	}
	std::printf("], \"finite\": [");
	for (unsigned i = 0; i < 7; i++)
	{
		const float w = views[i];
		const float z_clip = (far_distance * near_distance - near_distance * w) / (far_distance - near_distance);
		std::printf("%s%.9g", i ? ", " : "", depth_of(scale * z_clip + offset * w, w, clip_min, clip_max));
	}
	// In range, below the range, beyond the far clip.
	std::printf("], \"in_range\": [%.9g, %.9g], \"below\": %.9g, \"beyond\": %.9g}\n",
		depth_of(0.25f * 3.0f, 3.0f, 0.0f, 1.0f), depth_of(1.0f * 2.0f, 2.0f, 0.0f, 1.0f),
		depth_of(-0.5f * 2.0f, 2.0f, -1.0f, 1.0f), depth_of(3.0f * 2.0f, 2.0f, 0.0f, 2.0f));
	return 0;
}
'''

LEVERS_HARNESS = r'''
#include "ios/IOSTitleLevers.h"
namespace levers = rpcs3::ios::title_levers;
static_assert(levers::requires_zclip_fallback_window_z("BLES01717"));
static_assert(levers::requires_spu_object_prefetch("BLES01717"));
static_assert(!levers::requires_zclip_fallback_window_z("BLES00158") && !levers::requires_spu_object_prefetch("BLES00158"));
static_assert(!levers::requires_zclip_fallback_window_z("BCES00510") && !levers::requires_spu_object_prefetch("BLUS30089"));
static_assert(!levers::requires_zclip_fallback_window_z("") && !levers::requires_spu_object_prefetch(""));
int main() { return 0; }
'''


def float_literals(text: str) -> str:
    """GLSL '0.99' is a float; keep it one in C++."""
    return re.sub(r'(?<![\w.])(\d+\.\d*)(?![\w.])', r'\1f', text)


def glslang_check(glslang: str, restored_prologue: str, prologue: str, work: Path) -> dict:
    def body(text):
        return text.split('R"(', 1)[1].rsplit(')"', 1)[0]
    variants = {'core613_off': (body(restored_prologue), []), 'core616_off': (body(prologue), []),
                'core616_on': (body(prologue), ['_EMULATE_ZCLIP_XFORM_FALLBACK_WINDOW_Z'])}
    digests = {}
    for name, (text, extra) in variants.items():
        source = '#version 450\n' + ''.join('#define %s\n' % d for d in ['_EMULATE_ZCLIP_XFORM_FALLBACK', *extra]) + text + '''
layout(location=0) in vec4 p;
layout(set=0,binding=0) uniform U { float z_near; float z_far; };
void main(){ gl_Position = apply_zclip_xform(p, z_near, z_far); }
'''
        (work / (name + '.vert')).write_text(source)
        subprocess.run([glslang, '-V', '--quiet', str(work / (name + '.vert')), '-o', str(work / (name + '.spv'))], check=True, timeout=60)
        digests[name] = sha((work / (name + '.spv')).read_bytes())
    require(digests['core613_off'] == digests['core616_off'], 'SPIR-V of every other title is unchanged')
    require(digests['core616_on'] != digests['core616_off'], 'the Black Ops II variant changes its SPIR-V')
    return digests


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default=os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++') or 'c++')
    parser.add_argument('--sanitize', action='store_true', help='ASan/UBSan')
    parser.add_argument('--tsan', action='store_true', help='ThreadSanitizer for the prefetch store')
    parser.add_argument('--glslang', default=None, help='glslang executable for the SPIR-V identity check')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    compiler = shlex.split(args.cxx)
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        compiler += ['-isysroot', sdk]

    patch_text = PATCH.read_text()
    files = patch_files(patch_text)
    core613 = dict(CORE613)
    require(sorted(files) == sorted([*core613, NEW_FILE]), 'the incremental patch touches exactly the reviewed files')
    for name, added, removed in hunks(patch_text):
        require(removed == 0, 'insertions only: ' + name)
        require(name == NEW_FILE or any(marker in line for line in added for marker in MARKERS),
                'every hunk names its 616 marker: ' + name + ' ' + repr(added[:2]))

    flags = ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function']
    if args.sanitize:
        flags += ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']
    report = {'passed': False, 'sanitized': args.sanitize, 'tsan': args.tsan, 'compiler': compiler[0],
              'patch_sha256': sha(PATCH.read_bytes()), 'core613_files': len(core613)}

    with tempfile.TemporaryDirectory(prefix='rpcs3-616-') as temporary:
        work = Path(temporary)
        tree = restore(source, work, core613)

        # 1. ZCULL poll: the real predicate and gather.
        render = (source / 'rpcs3/Emu/RSX/VK/VKGSRender.cpp').read_text()
        status = braced_after(render, 'bool VKGSRender::check_occlusion_query_status(')
        predicate = '\t// REWINDBOX_ZCULL_POLL_NO_WAIT_616' + extract_between(status, '#ifdef RPCS3_IOS\n\t// REWINDBOX_ZCULL_POLL_NO_WAIT_616', '\n#else')
        result = braced_after(render, 'void VKGSRender::get_occlusion_query_result(')
        gather = braced_after(result, '// Gather data')
        out = compile_and_run(work, 'zcull', {'main.cpp': ZCULL_HARNESS, 'predicate.inc': predicate, 'gather.inc': gather},
                              compiler, flags, [source / 'rpcs3'])
        zcull = json.loads(out.strip().splitlines()[-1])
        require(zcull['failures'] == 0 and zcull['cases'] > 200 and zcull['upstream_blocking'] > 0 and zcull['deferred'] > 0,
                'ZCULL poll predicate: ' + repr(zcull))
        report['zcull_poll'] = zcull

        perf = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
        block = extract_between(perf, '// REWINDBOX_ZCULL_WAIT_PROBE_616', '// REWINDBOX_SPU_OBJECT_PREFETCH_616')
        fmt = ''.join(re.findall(r'"((?:[^"\\]|\\.)*)"', block.split('ios_core_profiler.notice(', 1)[1].split('profile_session', 1)[0]))
        require(fmt.startswith('COREPROF ZCULLWAIT616 session=%llu window=%llu ') and 'poll_deferred=%llu' in fmt and
                'gathers_order=poll:forced:cond_render:sync' in fmt, 'ZCULLWAIT616 line')
        zcull_text = (source / 'rpcs3/Emu/RSX/RSXZCULL.cpp').read_text()
        require(zcull_text.count('ZcullPathScope') == 2 and 'zcull_sync_all' in zcull_text and 't_zcull_forced_path : rpcs3::ios::rsx_sync::zcull_poll' in zcull_text,
                'sync() and update() name their read path')
        thread_text = (source / 'rpcs3/Emu/RSX/RSXThread.cpp').read_text()
        require(re.search(r'zcull_cond_render\);\s*#endif\s*zcull_ctrl->read_barrier\(this, cond_render_ctrl\.eval_address', thread_text) is not None,
                'the conditional render evaluation names its path')

        # 2. SPU object prefetch: the real store and load_compressed().
        prefetch_flags = list(flags) + ['-pthread']
        if args.tsan:
            prefetch_flags = [f for f in prefetch_flags if not f.startswith('-fsanitize') and f != '-fno-sanitize-recover=all'] + ['-fsanitize=thread']
        out = compile_and_run(work, 'prefetch', {'main.cpp': PREFETCH_HARNESS}, compiler, prefetch_flags, [source / 'rpcs3'])
        require(json.loads(out.strip().splitlines()[-1])['failures'] == 0, 'prefetch store')
        jit = (source / 'Utilities/JITLLVM.cpp').read_text()
        load = braced_after(jit, 'static std::unique_ptr<llvm::MemoryBuffer> load_compressed(')
        payload = bytes(random.Random(616).getrandbits(8) for _ in range(3000)) + b'\x7fELF' * 900
        (work / 'object.gz').write_bytes(gzip.compress(payload, mtime=0))
        (work / 'object.raw').write_bytes(payload)
        out = compile_and_run(work, 'load', {'main.cpp': LOAD_HARNESS, 'load_compressed.inc': load}, compiler, flags,
                              [source], ['-lz'], args=[str(work / 'object.gz'), str(work / 'object.raw')])
        require(json.loads(out.strip().splitlines()[-1])['failures'] == 0, 'load_compressed')
        require(re.search(r'take\(path \+ "\.gz"\)\)\s*\{\s*buffer = ObjectCache::load_compressed\(\*prefetched, jit_phase::spu_cache_read\);\s*\}\s*if \(!buffer\)\s*\{\s*buffer = ObjectCache::load\(path, jit_phase::spu_cache_read\);',
                          jit) is not None, 'a failed in-memory inflate falls back to the file read, then the same validation')
        spu = (source / 'rpcs3/Emu/Cell/SPUCommonRecompiler.cpp').read_text()
        require(spu.count('get_experimental_policy().spu_object_prefetch') == 2 and 'plan.remove' in extract_between(spu, 'REWINDBOX_SPU_OBJECT_PREFETCH_616: what the eviction keeps', 'spu_object_prefetch::instance().start('),
                'the prefetch starts after the eviction plan, without the removed objects')
        system = (source / 'rpcs3/Emu/System.cpp').read_text()
        require(system.count('spu_object_prefetch::instance().stop()') == 2, 'the store is emptied when emulation stops and at exit')
        report['spu_prefetch'] = {'store': 'executed', 'load_compressed_bytes': len(payload)}

        # 3. Vertex fallback transform: the real GLSL function, both define states.
        prologue = (source / PROLOGUE).read_text()
        fallback = extract_between(prologue, '#elif defined(_EMULATE_ZCLIP_XFORM_FALLBACK)\n', '\n#endif\n\n#if defined(_ENABLE_INSTANCED_CONSTANTS)')
        fallback = float_literals(fallback)
        results = {}
        for name, define in (('core613', []), ('core616', ['-D_EMULATE_ZCLIP_XFORM_FALLBACK_WINDOW_Z'])):
            out = compile_and_run(work, 'zclip_' + name, {'main.cpp': ZCLIP_HARNESS, 'fallback.inc': fallback}, compiler,
                                  [f for f in flags if f != '-Werror'] + define, [])
            results[name] = json.loads(out.strip().splitlines()[-1])
        old, new = results['core613'], results['core616']
        for kind in ('infinite', 'finite'):
            require(len(set(old[kind])) == 1, 'Core 613 gives every pinned fragment one depth (%s): %r' % (kind, old[kind]))
            require(all(0.99 < value <= 1.0 for value in new[kind]), 'the band stays in (0.99, 1]: %r' % new[kind])
            require(all(a > b for a, b in zip(new[kind], new[kind][1:])), 'nearer is deeper in reversed Z (%s): %r' % (kind, new[kind]))
        require(old['in_range'] == new['in_range'] == [0.25, 1.0] and old['below'] == new['below'] == 0.0 and old['beyond'] == new['beyond'] == 3.0,
                'in-range, clamped and clipped depths are unchanged')
        report['zclip'] = results
        common = (source / 'rpcs3/Emu/RSX/Program/GLSLCommon.cpp').read_text()
        require(re.search(r'"_EMULATE_ZCLIP_XFORM_FALLBACK"\);\s*if \(props\.emulate_zclip_fallback_window_z\)\s*\{[^}]*"_EMULATE_ZCLIP_XFORM_FALLBACK_WINDOW_Z"', common) is not None,
                'the define only follows the fallback')
        vertex = (source / 'rpcs3/Emu/RSX/VK/VKVertexProgram.cpp').read_text()
        require('properties2.emulate_zclip_fallback_window_z = !properties2.emulate_depth_clip_only &&\n\t\trpcs3::ios::get_experimental_policy().zclip_fallback_window_z;' in vertex,
                'only without float64 and only for the scoped title')
        compile_and_run(work, 'levers', {'main.cpp': LEVERS_HARNESS}, compiler, flags, [source / 'rpcs3'])
        policy = (source / 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp').read_text()
        require('resolved.zclip_fallback_window_z = rpcs3::ios::title_levers::requires_zclip_fallback_window_z(title_id);' in policy and
                'resolved.spu_object_prefetch = rpcs3::ios::title_levers::requires_spu_object_prefetch(title_id);' in policy,
                'both levers follow the title list, without a setting')
        if args.glslang:
            report['spirv'] = glslang_check(args.glslang, (tree / PROLOGUE).read_text(), prologue, work)

    report['passed'] = True
    report['scope'] = 'host execution of the reviewed source; no Core build, no iPhone run, no gameplay claim'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print('PASS: Core 616 = Core 613 + insertions; ZCULL poll %d cases (%d upstream blocking); prefetch store and inflate%s; '
          'fallback depth order%s' % (zcull['cases'], zcull['upstream_blocking'], ' (TSan)' if args.tsan else ' (ASan/UBSan)' if args.sanitize else '',
                                      '; SPIR-V identity' if args.glslang else ''))


if __name__ == '__main__':
    main()
