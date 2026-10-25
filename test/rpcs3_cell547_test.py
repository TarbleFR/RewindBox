#!/usr/bin/env python3
"""Execute the production CELL547 bodies (bounded-spin fence wait, compile pressure) against the 546 baseline.

Usage: rpcs3_cell547_test.py <547 Core work tree> [--report out.json]

vk::wait_for_fence is copied verbatim from the 547 and 546 trees (the 546 one is
reconstructed by reverse-applying the reviewed fixture). The Vulkan fence is an
adapter shaped like MoltenVK's: vkGetFenceStatus reads the state under a lock,
vkWaitForFences sleeps on a condition variable that the simulated GPU signals,
as MVKFenceSitter does. IOSCompilePressure.h is the production header. The
GETLLAR decision and the pipeline-build scope are checked as exact source
deltas; their passive path is RPCS3's own. Host timings, not iPhone ones.
"""
import argparse, hashlib, json, os, re, shlex, subprocess, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell547.diff'
sha = lambda b: hashlib.sha256(b).hexdigest()
MODIFIED = ['rpcs3/Crypto/unzip.cpp', 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake', 'rpcs3/Emu/Cell/SPUThread.cpp',
            'rpcs3/Emu/RSX/Program/ProgramStateCache.h', 'rpcs3/Emu/RSX/VK/vkutils/sync.cpp', 'rpcs3/ios/RPCS3IOSPerformance.cpp']
NEW = ['rpcs3/ios/IOSCompilePressure.h']
PRELUDE = r'''#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <mutex>
#include <thread>
#include <vector>
using u32 = std::uint32_t; using u64 = std::uint64_t; using usz = std::size_t;
#define RPCS3_IOS 1
enum VkResult { VK_SUCCESS = 0, VK_NOT_READY = 1, VK_TIMEOUT = 2, VK_ERROR_DEVICE_LOST = -4 };
using VkBool32 = u32; constexpr VkBool32 VK_FALSE = 0;
using VkDevice = void*;
// Adapter shaped like MoltenVK 1.4.2: status under the fence lock, waits on a
// condition variable signalled by the GPU completion (MVKFence/MVKFenceSitter).
struct sim_fence
{
	std::mutex lock; std::condition_variable cv; bool signaled = false; VkResult error = VK_SUCCESS;
	std::atomic<u64> status_calls{0}, wait_calls{0};
	void signal() { { std::lock_guard g(lock); signaled = true; } cv.notify_all(); }
};
using VkFence = sim_fence*;
static VkResult vkGetFenceStatus(VkDevice, VkFence f)
{
	f->status_calls++;
	std::lock_guard g(f->lock);
	if (f->error != VK_SUCCESS) return f->error;
	return f->signaled ? VK_SUCCESS : VK_NOT_READY;
}
static VkResult vkWaitForFences(VkDevice, u32, const VkFence* f, VkBool32, u64 timeout_ns)
{
	(*f)->wait_calls++;
	std::unique_lock g((*f)->lock);
	if ((*f)->error != VK_SUCCESS) return (*f)->error;
	return (*f)->cv.wait_for(g, std::chrono::nanoseconds(timeout_ns), [&] { return (*f)->signaled; }) ? VK_SUCCESS : VK_TIMEOUT;
}
struct device_stub { operator VkDevice() const { return nullptr; } };
static device_stub device_instance;
static device_stub* g_render_device = &device_instance;
static std::atomic<int> g_die_calls{0};
static void die_with_error(VkResult) { g_die_calls++; }
namespace utils
{
inline void pause() { std::atomic_signal_fence(std::memory_order_seq_cst); }
inline u64 get_tsc() { return static_cast<u64>(std::chrono::steady_clock::now().time_since_epoch().count()); }
}
namespace rpcs3::ios { inline std::atomic<u64> recorded_waits{0}; inline void record_gpu_fence_wait(u64, bool) { recorded_waits++; } }
struct fence { VkFence handle; void wait_flush() {} };
'''


def braced(text, start):
    a = text.index(start)
    b = text.index('{', a) + 1
    depth = 1
    while depth:
        depth += (text[b] == '{') - (text[b] == '}')
        b += 1
    return text[a:b]


def baseline(source: Path, work: Path) -> Path:
    tree = work / 'before'
    for path in MODIFIED + NEW:
        dest = tree / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=tree, check=True)
    return tree


def hunk_lines(path):
    """Added and removed lines of one file in the fixture."""
    text = FIXTURE.read_text()
    block = text[text.index(f'diff --git a/{path} b/{path}'):]
    nxt = block.find('\ndiff --git', 1)
    block = block if nxt < 0 else block[:nxt]
    added = [l[1:] for l in block.splitlines() if l.startswith('+') and not l.startswith('+++')]
    removed = [l[1:] for l in block.splitlines() if l.startswith('-') and not l.startswith('---')]
    return added, removed


def static_checks(source: Path, before: Path) -> dict:
    added_all = [l[1:] for l in FIXTURE.read_text().splitlines() if l.startswith('+') and not l.startswith('+++')]
    assert not [l for l in added_all if re.search(r'\b(try|catch|throw)\b', l)]
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    if record := manifest.get('cell547'):
        for path, digest in record['before_sha256'].items():
            assert sha((before / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
        for path, digest in record['after_sha256'].items():
            assert sha((source / path).read_bytes().replace(b'\r\n', b'\n')) == digest, path
    # Codegen: SPUThread.cpp is the only changed file of either digest list; the
    # alias maps this exact snapshot to the 546 hash, so SPU objects are reused.
    cmake = (source / 'rpcs3/Emu/CMakeLists.txt').read_text()
    listed = set()
    for block in re.findall(r'foreach\(NEOSTATION_(?:PPU|SPU)_CODEGEN_SOURCE IN ITEMS(.*?)\)', cmake, re.S):
        listed |= {('rpcs3/Emu/' + p).replace('rpcs3/Emu/../../', '').replace('rpcs3/Emu/../', 'rpcs3/') for p in block.split()}
    assert listed & set(MODIFIED + NEW) == {'rpcs3/Emu/Cell/SPUThread.cpp'}, listed & set(MODIFIED + NEW)
    table = (source / 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake').read_text()
    alias = re.search(r'source STREQUAL "Cell/SPUThread\.cpp" AND\s+actual STREQUAL "([0-9a-f]{64})"\)\s+'
                      r'set\(\$\{output\} "([0-9a-f]{64})"', table)
    after_hash = sha((source / 'rpcs3/Emu/Cell/SPUThread.cpp').read_bytes())
    before_hash = sha((before / 'rpcs3/Emu/Cell/SPUThread.cpp').read_bytes())
    assert alias and alias.group(1) == after_hash and alias.group(2) == before_hash
    # SPUThread.cpp: only iOS-guarded lines; the passive decision needs a
    # confirmed poll (count >= 2) and the active pressure; history kept intact.
    added, removed = hunk_lines('rpcs3/Emu/Cell/SPUThread.cpp')
    assert removed == ['\t' * 7 + 'u8& val = getllar_wait_time[(addr % SPU_LS_SIZE) / 128].front();',
                       '\t' * 7 + 'val = static_cast<u8>(std::min<u32>(val + 1, u8{umax}));'], removed
    spu = (source / 'rpcs3/Emu/Cell/SPUThread.cpp').read_text()
    decision = spu[spu.index('REWINDBOX_COMPILE_PRESSURE_V1 (ios/IOSCompilePressure.h):'):spu.index('// Either 1 or umax')]
    assert 'getllar_busy_waiting_switch != 0 && getllar_spin_count >= 2 &&' in decision
    assert 'rpcs3::ios::compile_pressure::active()' in decision and 'return false;' in decision
    for line in added:
        assert not re.search(r'\bbusy_wait\(|thread_ctrl::|sleep', line), line
    # ProgramStateCache.h: one scope around the build a draw waits for.
    added, removed = hunk_lines('rpcs3/Emu/RSX/Program/ProgramStateCache.h')
    assert not removed and [l for l in added if 'BlockingBuildScope' in l] == [
        '\t\trpcs3::ios::compile_pressure::BlockingBuildScope pressure_scope(wait_for_inline_build);']
    cache = (source / 'rpcs3/Emu/RSX/Program/ProgramStateCache.h').read_text()
    assert cache.index('const bool wait_for_inline_build = !compile_async && allow_notification;') < cache.index('pressure_scope(wait_for_inline_build)') < cache.index('pipeline_type* result = backend_traits::build_pipeline(')
    # sync.cpp: the timed path and the non-iOS spin are unchanged.
    added, removed = hunk_lines('rpcs3/Emu/RSX/VK/vkutils/sync.cpp')
    assert not removed
    return dict(noExceptionsAdded=True, codegenFilesChanged=['rpcs3/Emu/Cell/SPUThread.cpp'],
                spuThread=dict(before=before_hash, after=after_hash, aliasedToBefore=True))


def wait_namespace(name, text):
    body = braced(text, 'VkResult wait_for_fence(fence* pFence, u64 timeout)')
    return f'namespace {name} {{\n{body}\n}}\n'


def assemble(source: Path, before: Path) -> str:
    code = PRELUDE + f'#include "{source / "rpcs3/ios/IOSCompilePressure.h"}"\n'
    for tree, suffix in ((source, 'after'), (before, 'before')):
        code += wait_namespace('wait_' + suffix, (tree / 'rpcs3/Emu/RSX/VK/vkutils/sync.cpp').read_text())
    return code + (ROOT / 'test/native/rpcs3_cell547.inc').read_text()


def main():
    p = argparse.ArgumentParser()
    p.add_argument('source', type=Path)
    p.add_argument('--report', type=Path)
    a = p.parse_args()
    source = a.source.resolve()
    cxx = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        cxx += ['-isysroot', sdk]
    with tempfile.TemporaryDirectory(prefix='cell547-') as td:
        work = Path(td)
        before = baseline(source, work)
        checks = static_checks(source, before)
        code = assemble(source, before)
        cpp = work / 'cell547.cpp'
        cpp.write_text(code)
        results = {}
        for mode, flags in (('sanitized', ['-O1', '-fsanitize=address,undefined']), ('timing', ['-O2'])):
            exe = work / ('cell547-' + mode)
            subprocess.run(cxx + ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-unused-function',
                                  '-D_GLIBCXX_ASSERTIONS', '-pthread', '-fno-omit-frame-pointer', *flags, str(cpp), '-o', str(exe)], check=True)
            env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
            run = subprocess.run([str(exe), mode], capture_output=True, text=True, timeout=900, env=env)
            if run.returncode:
                print(run.stdout, run.stderr)
                run.check_returncode()
            results[mode] = json.loads(run.stdout)
        harness = sha(code.encode())
    assert results['sanitized']['failures'] == 0 and results['timing']['failures'] == 0
    inputs = ['test/rpcs3_cell547_test.py', 'test/native/rpcs3_cell547.inc', 'test/fixtures/rpcs3_cell547.diff']
    report = dict(result='passed', passed=True, static=checks, scenarios=results, harnessSHA256=harness,
                  sanitizers='ASan+UBSan run, then an -O2 timing run', cpuCount=os.cpu_count(),
                  sourceSHA256={p: sha((source / p).read_bytes().replace(b'\r\n', b'\n')) for p in MODIFIED + NEW},
                  inputs={p: sha((ROOT / p).read_bytes()) for p in inputs}, physicalDeviceTested=False,
                  scope='host scheduler and a condition-variable fence adapter; not MoltenVK, Metal or the iPhone scheduler')
    if a.report:
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    print('RPCS3 CELL547: bounded-spin fence wait (same results, CPU released) and compile-pressure scope passed against 546.')


if __name__ == '__main__':
    main()
