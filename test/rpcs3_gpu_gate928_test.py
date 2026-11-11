#!/usr/bin/env python3
"""Host test of Core 928 on a materialized Core source: the GPU gate closes when the application is deactivated.

Why (REWINDBOX_GPU_DEACTIVATION_GATE_928):
- Core 927 closed the gate at UIApplicationDidEnterBackgroundNotification. The only device loss of the device journals
  (IPA 650, Assassin's Creed, pid 8767) has "Device lost" at 1793814730.525 and the host's own observer of that
  notification running at .555: a command buffer had been refused at least 30 ms before the application handled the
  notification. A gate closed there would not have prevented that loss.
- Apple's Metal documentation ("Preparing your Metal app to run in the background") gives the procedure: when the
  application is deactivated, stop sending work to Metal ("you've some time before the system restricts your app from
  using Metal"); when it enters the background, make sure every committed command buffer is scheduled before
  returning; enable the code again only once the application is reactivated.

Core 928:
- UIApplicationWillResignActiveNotification closes the gate and settles the queues (the Core 927 procedure, earlier);
- UIApplicationDidEnterBackgroundNotification only finishes what the deactivation left: nothing after a settle; a
  resumed settle, which gives the queues nothing new, after one that timed out; the whole procedure when a call was
  still inside at the deactivation;
- UIApplicationDidBecomeActiveNotification opens the gate, as before;
- a renderer created while the application is not active closes the gate at once;
- the freeze episode sampler counts the time the gate is closed as paused;
- COREPROF GPUGATE928 replaces COREPROF GPUGATE927.
Consequence stated in the header: while the application is inactive (Control Centre, application switcher, a system
alert) the picture stands still and goes on when the application is active again.

This test checks the source, then compiles and runs two models, plain, ASan/UBSan and TSan:
- test/native/rpcs3_gpu_gate928_model.cpp against the real gate and encoding-queue registry, with the Core 927 rule
  as control (frames refused between the restriction and the background notification), then every rule of the gate;
- test/native/rpcs3_gpu_settle928_model.cpp, which executes the text of vk::ios_settle_queues copied from the source
  against a model of the six Vulkan calls it makes: a resumed settle gives the queues nothing new.
On macOS the queue is the real libdispatch; elsewhere test/native/dispatch_shim. No iPhone or FPS result is inferred.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
GATE_MODEL = ROOT / 'test/native/rpcs3_gpu_gate928_model.cpp'
SETTLE_MODEL = ROOT / 'test/native/rpcs3_gpu_settle928_model.cpp'
SHIM = ROOT / 'test/native/dispatch_shim'
GATE = 'rpcs3/ios/IOSGpuBackgroundGate.h'
PLATFORM = 'rpcs3/ios/RPCS3IOSPlatform.mm'
PERF = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
STREAM = 'rpcs3/Emu/RSX/VK/VKCommandStream.cpp'
HELPERS = 'rpcs3/Emu/RSX/VK/VKHelpers.h'
RENDER = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
SETTLE_BEGIN = '\tbool ios_settle_queues(std::chrono::milliseconds limit, bool resume)\n'
SETTLE_END = '\tvoid ios_release_settle_fences()\n'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(source: Path, rel: str) -> str:
    return (source / rel).read_bytes().decode('utf-8').replace('\r\n', '\n')


def between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


def settle_text(source: Path) -> str:
    """The two functions of the renderer, as they are in the source (through the closing brace of the second)."""
    stream = read(source, STREAM)
    begin = stream.index(SETTLE_BEGIN)
    end = stream.index('\n\t}\n', stream.index(SETTLE_END, begin)) + len('\n\t}\n')
    return stream[begin:end]


def source_checks(source: Path) -> dict:
    gate = read(source, GATE)
    require('REWINDBOX_GPU_DEACTIVATION_GATE_928' in gate and 'Preparing your\n// Metal app to run in the background' in gate,
            'the gate names its procedure')
    require('using settle_function = bool (*)(std::chrono::milliseconds limit, bool resume);' in gate, 'settle function type')
    # One procedure for the three notifications; no settle while a call is still inside; nothing more once settled.
    procedure = between(gate, 'void stop_and_settle() noexcept', 'public:')
    order = [procedure.index(text) for text in ('if (!close())', 'return;', 'std::lock_guard lock(m_settle_mutex);',
                                                'if (!m_settle || m_settled)', 'const bool resume = m_settle_ran;',
                                                'm_settle_ran = true;', 'm_settled = m_settle(settle_limit, resume);')]
    require(order == sorted(order), 'close, then the settle under its mutex, resumed when one already ran')
    require(procedure.count('m_settle(') == 1, 'one call of the settle function')
    for name, counter in (('app_will_resign_active', 'deactivations'), ('app_found_not_active', 'found_not_active'),
                          ('app_entered_background', 'backgrounds')):
        body = between(gate, f'void {name}() noexcept', '\n\t}\n')
        require(f'{counter}.fetch_add(1, std::memory_order_relaxed);\n\t\tstop_and_settle();' in body, name + ' counts and runs the procedure')
    require(between(gate, 'void app_became_active() noexcept', '\n\t}\n').count('open();') == 1, 'reactivation opens')
    opened = between(gate, 'void open() noexcept', 'bool closed() noexcept')
    require(opened.index('m_opened.notify_all();') < opened.index('std::lock_guard lock(m_settle_mutex);') <
            opened.index('m_settle_ran = m_settled = false;'), 'opening forgets what was settled, outside the gate mutex')
    setter = between(gate, 'void set_settle(settle_function settle) noexcept', '// A function that never goes away')
    require('m_settle = settle;' in setter and 'm_settle_ran = m_settled = false;' in setter, 'another renderer starts from nothing settled')
    require('inline constexpr std::chrono::milliseconds in_flight_limit{500};' in gate and
            'inline constexpr std::chrono::milliseconds settle_limit{1000};' in gate, 'bounded waits of the posting thread')

    platform_mm = read(source, PLATFORM)
    observers = between(platform_mm, 'void install_application_observers() noexcept', 'namespace rpcs3::ios\n{\nvoid reservation_lock_yield()')
    require('static dispatch_once_t once;' in observers, 'once per process')
    for notification, call in (('UIApplicationWillResignActiveNotification', 'app_will_resign_active'),
                               ('UIApplicationDidEnterBackgroundNotification', 'app_entered_background'),
                               ('UIApplicationDidBecomeActiveNotification', 'app_became_active')):
        require(f'addObserverForName:{notification} object:nil queue:nil\n'
                f'\t\t\t\tusingBlock:^(NSNotification*) {{ gate::instance().{call}(); }}];' in observers,
                notification + ' is observed on the posting thread (no queue)')
    require(observers.count('addObserverForName:') == 3 and observers.count('CFBridgingRetain(') == 3, 'three observers, kept for the process')
    state = between(observers, 'dispatch_async(dispatch_get_main_queue(), ^{', '});')
    require('if (UIApplication.sharedApplication.applicationState != UIApplicationStateActive)' in state and
            'gate::instance().app_found_not_active();' in state, 'the state at installation is read on the main queue')

    stream = read(source, STREAM)
    text = settle_text(source)
    resumed = between(text, 'if (resume)', 'const auto deadline = std::chrono::steady_clock::now() + limit;')
    require(resumed.index('if (s_ios_settle_reached_queues)') < resumed.index('if (s_ios_unsettled_fences.empty())') <
            resumed.index('vkWaitForFences(*dev, ::size32(s_ios_unsettled_fences), s_ios_unsettled_fences.data(), VK_TRUE, limit_ns)') and
            'vkQueueSubmit' not in resumed and 'g_submit_mutex' not in resumed,
            'a resumed settle waits for the kept fences and gives the queues nothing')
    whole = text[text.index('const auto deadline = std::chrono::steady_clock::now() + limit;'):text.index(SETTLE_END)]
    require(whole.index('while (!g_submit_mutex.try_lock())') < whole.index('s_ios_settle_reached_queues = false;') <
            whole.index('s_ios_settle_reached_queues = true;') < whole.index('vkQueueSubmit(queue, 0, nullptr, fence)') <
            whole.index('g_submit_mutex.unlock();') < whole.index('vkWaitForFences(*dev, count, fences.data(), VK_TRUE, remaining_ns)'),
            'a whole settle: the submit lock or nothing, an empty submission with a fence on each queue, a bounded wait outside the lock')
    statics = between(stream, '#ifdef RPCS3_IOS\n\t// REWINDBOX_GPU_BACKGROUND_GATE_927 (ios/IOSGpuBackgroundGate.h): the settle function of the gate.', SETTLE_BEGIN)
    for declaration in ('std::mutex s_ios_settle_fences_mutex;', 'std::vector<VkFence> s_ios_unsettled_fences;',
                        'bool s_ios_settle_reached_queues = false;'):
        require(declaration in statics, declaration)
    require('bool ios_settle_queues(std::chrono::milliseconds limit, bool resume);' in read(source, HELPERS), 'declaration')
    require('rpcs3::ios::gpu_gate::gate::instance().set_settle(&vk::ios_settle_queues);' in read(source, RENDER), 'the renderer gives it')

    perf = read(source, PERF)
    require('"COREPROF GPUGATE928 session=%llu window=%llu closed=%u deactivations=%llu backgrounds=%llu "' in perf and
            '"found_not_active=%llu closes=%llu opens=%llu parks=%llu:%.3f park_bypasses=%llu in_flight_timeouts=%llu "' in perf and
            '"settles=%llu:%.3f settle_timeouts=%llu settle_waits=%llu:%.3f:%llu scope=process_since_boot"' in perf and
            'COREPROF GPUGATE927' not in perf, 'gate report line')
    sample = between(perf, 'sample.state = freeze_state(Emu.GetStatus(false));', 'sample.guest_flips = ')
    require('if (sample.state == episode::emu::running && rpcs3::ios::gpu_gate::gate::instance().closed())\n\t\t{\n'
            '\t\t\tsample.state = episode::emu::paused;\n\t\t}' in sample, 'a closed gate is paused time for the freeze episode sampler')
    return {'closedBy': 'UIApplicationWillResignActiveNotification', 'finishedBy': 'UIApplicationDidEnterBackgroundNotification',
            'openedBy': 'UIApplicationDidBecomeActiveNotification', 'reportLine': 'COREPROF GPUGATE928',
            'freezeSampler': 'closed gate counted as paused'}


def compiler_is_clang(cxx: str) -> bool:
    version = subprocess.run([cxx, '--version'], capture_output=True, text=True).stdout
    return 'clang' in version.lower()


def run_models(source: Path, cxx: str, sanitize: bool) -> dict:
    variants = [('plain', [])]
    if sanitize:
        variants += [('asanUbsan', ['-fsanitize=address,undefined', '-fno-sanitize-recover=undefined']), ('tsan', ['-fsanitize=thread'])]
    real_libdispatch = platform.system() == 'Darwin'
    gate_extra = [] if real_libdispatch else ['-I', str(SHIM)]
    if not compiler_is_clang(cxx):
        # The registry header asks __has_feature(objc_arc) behind defined(__OBJC__); GCC has no such builtin.
        gate_extra += ['-D__has_feature(x)=0']
    reports = {}
    environment = {'ASAN_OPTIONS': 'detect_leaks=0', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1', 'TSAN_OPTIONS': 'halt_on_error=1',
                   'PATH': '/usr/bin:/bin'}
    with tempfile.TemporaryDirectory(prefix='gpu-gate928-') as tmp:
        (Path(tmp) / 'settle928_text.inc').write_text(settle_text(source))
        for label, flags in variants:
            report = {}
            for name, model, extra in (('gate', GATE_MODEL, ['-I', str(source / 'rpcs3'), *gate_extra]), ('settle', SETTLE_MODEL, ['-I', tmp])):
                binary = Path(tmp) / f'{name}-{label}'
                build = subprocess.run([cxx, '-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-fno-omit-frame-pointer',
                                        *extra, *flags, str(model), '-o', str(binary)], capture_output=True, text=True)
                if build.returncode and label != 'plain' and 'libclang_rt.' in build.stderr and 'cannot find' in build.stderr:
                    report = 'not run: this compiler has no such sanitizer runtime on this host'
                    break
                require(build.returncode == 0, f'{name} model build failed ({label}):\n' + build.stderr[-4000:])
                result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=900, env=environment)
                require(result.returncode == 0, f'{name} model failed ({label}, {result.returncode}):\n' + (result.stdout + result.stderr)[-4000:])
                report[name] = json.loads([line for line in result.stdout.splitlines() if line.startswith('{')][-1])
                require(report[name]['failures'] == 0, f'{name} model report ({label})')
            if isinstance(report, dict):
                gate, settle = report['gate'], report['settle']
                require(gate['refusedGateAtBackground'] > 0 and gate['refusedGateAtDeactivation'] == 0,
                        'with the gate of Core 927 frames are refused between the restriction and the background notification; '
                        'closed at the deactivation none is')
                require(gate['refusedQueuedWithoutSettle'] == 30 and gate['refusedQueuedWithSettle'] == 0,
                        'what is queued at the deactivation is encoded and committed before the restriction')
                require(gate['settleResumes'] > 0 and gate['settleCalls'] > gate['settleResumes'], 'whole and resumed settles both ran')
                require(settle['submits'] == 12 and settle['fencesCreated'] == settle['fencesDestroyed'] == 12,
                        'the real settle text: six whole settles of two queues, no submission by a resumed wait, every fence released')
            reports[label] = report
    return {'variants': reports, 'realLibdispatch': real_libdispatch}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--no-sanitizers', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    report = {'test': 'rpcs3_gpu_gate928', 'source_checks': source_checks(source),
              'models': run_models(source, args.cxx, not args.no_sanitizers), 'iphone_tested': False, 'fps_claimed': False}
    report['result'] = 'passed'
    text = json.dumps(report, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + '\n')
    print(text)
    print('PASS: Core 928 GPU gate closed at the deactivation (background notification only finishes; resumed settle submits nothing)')


if __name__ == '__main__':
    main()
