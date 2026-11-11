#!/usr/bin/env python3
"""Host test of Core 927 on a materialized Core source: asynchronous MoltenVK submits made definitive.

Maintainer's order (11 November 2026): no protection, the lever must work, for every title that needs it.

What the device journals say (private exports of builds 640 to 724, summarized here):
- 16 sessions ran with asynchronous submits (9 of Assassin's Creed, 7 of Call of Duty: Black Ops II; 9 processes,
  76,148 presents): 0 acquisitions timed out, the encoding queue recorded each time. RSXSYNC551 submit then costs
  0.05 ms per frame on the RSX thread, against 3.5-4.8 ms per Black Ops II frame without them (builds 694 to 724).
- Every Black Ops II and God of War III boot since build 676 is canary=failed_before: the boot record of Core 587
  marks a title whose boot ended before 900 guest flips, whatever ended it.
- The only device loss of the journals (IPA 650, Assassin's Creed, pid 8767, asynchronous submits) is raised at
  1793814730.525 and HOST_STATE app=background is recorded at .555: iOS refuses a command buffer committed in the
  background and MoltenVK then reports the device lost (MVKQueue::handleMTLCommandBufferError).

What the source audit found (the MoltenVK tree the Core links, and the Vulkan renderer):
- the acquisition gave up waiting for the last queued present after 2 s, and MoltenVK's event semaphores count when
  the waiting submit is encoded while vkAcquireNextImageKHR reads the counter on the calling thread;
- an occlusion gather and a fence wait spun until MoltenVK had encoded their submission (a query is "written by the
  device" only once vkCmdEndQuery is encoded: vkGetQueryPoolResults(WAIT) returns VK_NOT_READY at once before that);
- asynchronous texture streaming orders two queues with those same counters, each queue now encoding on its own thread.

Core 927:
- REWINDBOX_MVK_ASYNC_DEFINITIVE_927: the boot record is removed; Automatic is every title (synchronous only for a
  configuration that turns asynchronous texture streaming on); the present barrier never gives up; every submission
  of the presenting queue gets a marker, its fence the ticket, and fence waits and occlusion gathers sleep until their
  submission is encoded.
- REWINDBOX_GPU_BACKGROUND_GATE_927: the application's move to the background closes a gate (submissions, presents,
  acquisitions and device waits park), waits for the calls inside and for the queues to settle, and the gate opens
  when the application is active again.

This test checks the source and compiles test/native/rpcs3_mvk_async927_model.cpp against the real headers: the real
encoding-queue registry, tickets and gate, against models of MoltenVK's semaphore counter, of its query availability
and of iOS refusing background commits, each with the rule before 927 as control. Plain, ASan/UBSan and TSan. On
macOS the queue is the real libdispatch; elsewhere test/native/dispatch_shim. No iPhone or FPS result is inferred.

From Core 928 (REWINDBOX_GPU_DEACTIVATION_GATE_928) the gate closes when the application is deactivated and its
settle function takes a second argument. On such a source this test keeps everything about the submits (source and
model) and the passes around the GPU calls; the gate's own text and scenarios, these ones included, are checked by
test/rpcs3_gpu_gate928_test.py.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'test/native/rpcs3_mvk_async927_model.cpp'
SHIM = ROOT / 'test/native/dispatch_shim'
EXEC = 'rpcs3/ios/IOSMoltenVKExec.h'
QUEUE = 'rpcs3/ios/IOSMoltenVKExecQueue.h'
GATE = 'rpcs3/ios/IOSGpuBackgroundGate.h'
CANARY = 'rpcs3/ios/IOSMoltenVKAsyncCanary.h'
PLATFORM = 'rpcs3/ios/RPCS3IOSPlatform.mm'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
PERF = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
LEVERS = 'rpcs3/ios/IOSTitleLevers.h'
STREAM = 'rpcs3/Emu/RSX/VK/VKCommandStream.cpp'
HELPERS = 'rpcs3/Emu/RSX/VK/VKHelpers.h'
SYNC = 'rpcs3/Emu/RSX/VK/vkutils/sync.cpp'
SYNC_H = 'rpcs3/Emu/RSX/VK/vkutils/sync.h'
TYPES = 'rpcs3/Emu/RSX/VK/VKGSRenderTypes.hpp'
PRESENT = 'rpcs3/Emu/RSX/VK/VKPresent.cpp'
RENDER = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
INSTANCE = 'rpcs3/Emu/RSX/VK/vkutils/instance.cpp'
DEVICE = 'rpcs3/Emu/RSX/VK/vkutils/device.cpp'
QUERY = 'rpcs3/Emu/RSX/VK/VKQueryPool.cpp'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(source: Path, rel: str) -> str:
    return (source / rel).read_bytes().decode('utf-8').replace('\r\n', '\n')


def between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin)]


def source_checks(source: Path) -> dict:
    # --- no boot record, every title -------------------------------------------------------------------------------
    # The header of the boot record stays as a file without code (the canonical delta drops no file); nothing includes it.
    retired = read(source, CANARY)
    require('retired by REWINDBOX_MVK_ASYNC_DEFINITIVE_927' in retired and
            all(line.startswith('//') or not line.strip() or line == '#pragma once' for line in retired.splitlines()),
            'the boot record header holds no code')
    for path in sorted((source / 'rpcs3').rglob('*')):
        if path.suffix in ('.cpp', '.h', '.hpp', '.mm') and path.is_file() and str(path.relative_to(source)) != CANARY:
            text = path.read_bytes().decode('utf-8', 'replace')
            for name in ('mvk_async_canary', 'arm_moltenvk_async_boot', 'note_moltenvk_async_flip', 'confirm_moltenvk_async_boot',
                         'moltenvk_async_canary_verdict', 'IOSMoltenVKAsyncCanary', 'rewindbox-mvk-async-'):
                require(name not in text, f'{path.relative_to(source)} still refers to {name}')
    policy = read(source, POLICY)
    require('resolved.moltenvk_async_submits = resolve_mode(g_cfg.ios_experimental.moltenvk_async_submits,\n'
            '\t\t!g_cfg.video.vk.asynchronous_texture_streaming);' in policy, 'Automatic is every title without texture streaming')
    require('joins_mvk_async_automatic_619' not in policy and 'joins_mvk_async_automatic_619' not in read(source, LEVERS),
            'no title list decides any more')
    require('"Resolved title policy 927: mvk_async=%d rule=%s texture_streaming=%d boot_record=none"' in policy, 'resolved policy line')
    for rule in ('"automatic_texture_streaming"', '"automatic_every_title"', '"setting_enabled"', '"setting_disabled"'):
        require(rule in policy, 'rule name ' + rule)
    instance = read(source, INSTANCE)
    require('if (rpcs3::ios::get_experimental_policy().moltenvk_async_submits)\n\t\t\t\t{\n'
            '\t\t\t\t\tmvk_settings.push_back(VkLayerSettingEXT{ kMVKMoltenVKDriverLayerName, "MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS", '
            'VK_LAYER_SETTING_TYPE_BOOL32_EXT, 1, &setting_false });' in instance, 'the resolved policy alone sets the MoltenVK configuration')
    settings = read(source, SETTINGS)
    require('Automatic enables it for every game, except a game whose configuration turns asynchronous texture streaming on; '
            'Enabled keeps it on and uploads textures on the RSX thread; Disabled keeps synchronous submits.' in settings, 'setting text')
    render = read(source, RENDER)
    streaming = between(render, 'if (g_cfg.video.vk.asynchronous_texture_streaming)', '// Sanity checks')
    require('if (backend_config.supports_asynchronous_compute && rpcs3::ios::get_experimental_policy().moltenvk_async_submits)\n'
            '\t\t{\n\t\t\trsx_log.warning(' in streaming and
            streaming.count('backend_config.supports_asynchronous_compute = false;') == 2, 'texture streaming is not combined with asynchronous submits')

    # --- the order of encoding is kept by waiting --------------------------------------------------------------------
    exec_h = read(source, EXEC)
    require('constexpr std::chrono::milliseconds wait_limit{2000};' in exec_h and 'gives up' not in exec_h, 'no wait is given up')
    for declaration in ('void set_presenting_queue(void* vk_queue) noexcept;', 'std::uint64_t mark_submit(void* vk_queue) noexcept;',
                        'bool wait_for_encoding(std::uint64_t ticket, wait_site site) noexcept;'):
        require(declaration in exec_h, declaration)
    queue = read(source, QUEUE)
    strict = between(queue, 'bool wait_until_encoded(', 'void wait_for_present(')
    require('while (result == present_tracker::wait_result::timed_out)\n\t\t{\n\t\t\ttimeouts.fetch_add(1, std::memory_order_relaxed);\n'
            '\t\t\tresult = m_presents.wait(ticket);\n\t\t}' in strict, 'a wait that times out is counted and goes on')
    present_wait = between(queue, 'void wait_for_present(std::uint64_t ticket) noexcept', 'bool wait_for_encoding(')
    require('wait_until_encoded(ticket, acquire_timeouts, waited)' in present_wait, 'the present barrier uses the strict wait')
    mark = between(queue, 'std::uint64_t mark_submit(void* vk_queue) noexcept', '// Sleeps until the marker of ticket has run')
    require('if (!vk_queue || vk_queue != m_presenting_vk_queue)' in mark and
            mark.index('m_presents.issue(now_us())') < mark.index('dispatch_async_f(queue,'), 'only the presenting queue is ticketed, in order')
    platform_mm = read(source, PLATFORM)
    for forward in ('gcd::registry::instance().set_presenting_queue(vk_queue);', 'return gcd::registry::instance().mark_submit(vk_queue);',
                    'return gcd::registry::instance().wait_for_encoding(ticket, site);'):
        require(forward in platform_mm, forward)
    stream = read(source, STREAM)
    submit = between(stream, 'static void queue_submit_impl(const queue_submit_t& submit_info)', 'void queue_submit(const queue_submit_t& submit_info, VkBool32 flush)')
    order = [submit.index(text) for text in ('const rpcs3::ios::gpu_gate::pass ios_gpu_pass;', 'acquire_global_submit_lock();',
                                             'vkQueueSubmit(submit_info.queue, 1, &info, submit_info.pfence->handle);',
                                             'submit_info.pfence->ios_encode_ticket = rpcs3::ios::moltenvk_exec::mark_submit(submit_info.queue);',
                                             'release_global_submit_lock();', 'submit_info.pfence->signal_flushed();')]
    require(order == sorted(order), 'gate, lock, submit, ticket, unlock, then the fence is published')
    require('u64 ios_encode_ticket  = 0;' in read(source, SYNC_H), 'the fence carries its ticket')
    sync = read(source, SYNC)
    fence_wait = between(sync, 'VkResult wait_for_fence(fence* pFence, u64 timeout)', 'VkResult wait_for_event(')
    require(fence_wait.index('pFence->wait_flush();') <
            fence_wait.index('rpcs3::ios::moltenvk_exec::wait_for_encoding(pFence->ios_encode_ticket, rpcs3::ios::moltenvk_exec::wait_site::fence);') <
            fence_wait.index('const auto spin_until = '), 'a fence wait sleeps until its submission is encoded, then spins')
    timed = between(fence_wait, 'if (timeout)', 'else')
    require('wait_for_encoding' not in timed, 'a timed fence wait keeps its timeout')
    types = read(source, TYPES)
    chunk_wait = between(types, 'void ios_wait_encoded(rpcs3::ios::moltenvk_exec::wait_site site)', '// REWINDBOX_GPU_TIMING_621')
    require(chunk_wait.index('if (!is_pending)') < chunk_wait.index('m_submit_fence->wait_flush();') <
            chunk_wait.index('rpcs3::ios::moltenvk_exec::wait_for_encoding(m_submit_fence->ios_encode_ticket, site);'), 'chunk wait')
    gather = between(types, 'void sync()', 'struct frame_context_t')
    require(gather.index('command_buffer_to_wait->flush();') <
            gather.index('command_buffer_to_wait->ios_wait_encoded(rpcs3::ios::moltenvk_exec::wait_site::query);'), 'the gather waits for its command buffer')
    # The blocking read itself is as before: only where it waits changed.
    query = read(source, QUERY)
    require('? result_flags | VK_QUERY_RESULT_WAIT_BIT : result_flags;' in query and 'while (!query_info.ready)' in query, 'query read unchanged')
    device = read(source, DEVICE)
    require('rpcs3::ios::moltenvk_exec::set_presenting_queue(present_queue_idx != umax ? m_present_queue : m_graphics_queue);' in device and
            'rpcs3::ios::gpu_gate::install_application_observers();' in device, 'the device names its presenting queue and installs the observers')
    perf = read(source, PERF)
    require('"COREPROF OPT587 session=%llu window=%llu mvk_async=%u boot_record=none exec_queues=%u "' in perf and
            'submits_marked=%llu fence_encode_waits=%llu:%.3f:%.3f "' in perf and
            '"query_encode_waits=%llu:%.3f:%.3f encode_wait_timeouts=%llu scope=process_window_counters window_boundary_approximate=1"' in perf,
            'report line')

    # --- the background gate ---------------------------------------------------------------------------------------------
    gate = read(source, GATE)
    gate928 = 'REWINDBOX_GPU_DEACTIVATION_GATE_928' in gate
    require('inline constexpr std::chrono::milliseconds in_flight_limit{500};' in gate and
            'inline constexpr std::chrono::milliseconds settle_limit{1000};' in gate, 'bounded waits of the posting thread')
    enter = between(gate, 'void enter() noexcept', '// After the call.')
    require(enter.index('if (bypass && bypass())') < enter.index('if (m_opened.wait_for(lock, park_slice, [this] { return !m_closed; }))'),
            'a parked call waits for the gate; only a stopping emulator goes on, without waiting first')
    if not gate928:
        background = between(gate, 'void app_entered_background() noexcept', 'void app_became_active() noexcept')
        require(background.index('if (!close())') < background.index('return;') < background.index('m_settle(settle_limit)'),
                'no settle while a call is still inside')
    observers = between(platform_mm, 'void install_application_observers() noexcept', 'namespace rpcs3::ios\n{\nvoid reservation_lock_yield()')
    require('static dispatch_once_t once;' in observers, 'once per process')
    require('addObserverForName:UIApplicationDidEnterBackgroundNotification object:nil queue:nil\n'
            '\t\t\t\tusingBlock:^(NSNotification*) { gate::instance().app_entered_background(); }];' in observers and
            'addObserverForName:UIApplicationDidBecomeActiveNotification object:nil queue:nil\n'
            '\t\t\t\tusingBlock:^(NSNotification*) { gate::instance().app_became_active(); }];' in observers,
            'both observers run on the posting thread (no queue)')
    present = read(source, PRESENT)
    require(present.count('const rpcs3::ios::gpu_gate::pass ios_gpu_pass;') == 5, 'present, acquisition, MetalFX and the two device waits')
    present_call = between(present, 'void VKGSRender::present(vk::frame_context_t *ctx)', 'rpcs3::ios::moltenvk_exec::mark_present()')
    require(present_call.index('const rpcs3::ios::gpu_gate::pass ios_gpu_pass;') < present_call.index('m_swapchain->present('), 'present')
    require('while (VkResult status = ios_acquire(timeout))\n#else\n'
            '\twhile (VkResult status = m_swapchain->acquire_next_swapchain_image(m_current_frame->acquire_signal_semaphore, timeout, &m_current_frame->present_image))\n#endif'
            in present, 'acquisition')
    require(render.count('const rpcs3::ios::gpu_gate::pass ios_gpu_pass;') == 1, 'the device wait of the destructor')
    constructor = between(render, 'vk::set_current_renderer(m_swapchain->get_device());', 'ios_gpu_timing_init();')
    require('rpcs3::ios::gpu_gate::gate::instance().set_settle(&vk::ios_settle_queues);' in constructor, 'the renderer gives its settle function')
    require('rpcs3::ios::gpu_gate::gate::instance().set_bypass([]() -> bool' in constructor and
            'return state == system_state::stopping || state == system_state::stopped;' in constructor, 'a stopping emulator does not park')
    destructor = between(render, 'VKGSRender::~VKGSRender()', '// Globals. TODO: Refactor lifetime management')
    require(destructor.index('rpcs3::ios::gpu_gate::gate::instance().set_settle(nullptr);') < destructor.index('vkDeviceWaitIdle(*m_device);') <
            destructor.index('vk::ios_release_settle_fences();'), 'the renderer takes it back before its device goes')
    signature = 'bool ios_settle_queues(std::chrono::milliseconds limit, bool resume)' if gate928 else 'bool ios_settle_queues(std::chrono::milliseconds limit)'
    settle = between(stream, signature, 'void ios_release_settle_fences()')
    require(settle.index('while (!g_submit_mutex.try_lock())') < settle.index('vkQueueSubmit(queue, 0, nullptr, fence)') <
            settle.index('g_submit_mutex.unlock();') < settle.index('vkWaitForFences(*dev, count, fences.data(), VK_TRUE, remaining_ns)'),
            'an empty submission with a fence behind each queue, then a bounded wait outside the submit lock')
    require(signature + ';' in read(source, HELPERS), 'declaration')
    if not gate928:
        require('"COREPROF GPUGATE927 session=%llu window=%llu closed=%u closes=%llu opens=%llu parks=%llu:%.3f "' in perf and
                '"park_bypasses=%llu in_flight_timeouts=%llu settles=%llu:%.3f settle_timeouts=%llu scope=process_since_boot"' in perf, 'gate report line')

    # A non-iOS compiler sees the previous text of the shared files: every 927 line is inside an RPCS3_IOS block, and the
    # only shared lines touched are repeated unchanged in the #else branches.
    for rel, lines in ((PRESENT, ['\tvkDeviceWaitIdle(*m_device);\n#endif\n\n\t// Clean the FBO caches']),
                       (RENDER, ['#else\n\tvkDeviceWaitIdle(*m_device);\n#endif\n\n\t// Globals. TODO: Refactor lifetime management'])):
        text = read(source, rel)
        for line in lines:
            require(line in text, rel + ': the shared line is kept for other platforms')
    return {'bootRecord': 'none', 'automatic': 'every title without asynchronous texture streaming', 'presentBarrier': 'never abandoned',
            'ticketedWaits': ['fence', 'occlusion gather'], 'gatePasses': 7, 'inFlightLimitMs': 500, 'settleLimitMs': 1000,
            'gate': 'closed at the deactivation (Core 928): rpcs3_gpu_gate928_test.py' if gate928 else 'closed at the background notification (Core 927)'}


def compiler_is_clang(cxx: str) -> bool:
    version = subprocess.run([cxx, '--version'], capture_output=True, text=True).stdout
    return 'clang' in version.lower()


def run_model(source: Path, cxx: str, sanitize: bool) -> dict:
    variants = [('plain', [])]
    if sanitize:
        variants += [('asanUbsan', ['-fsanitize=address,undefined', '-fno-sanitize-recover=undefined']), ('tsan', ['-fsanitize=thread'])]
    extra = []
    real_libdispatch = platform.system() == 'Darwin'
    if not real_libdispatch:
        extra += ['-I', str(SHIM)]
    if not compiler_is_clang(cxx):
        # The registry header asks __has_feature(objc_arc) behind defined(__OBJC__); GCC has no such builtin.
        extra += ['-D__has_feature(x)=0']
    # From Core 928 the gate's scenarios are those of test/native/rpcs3_gpu_gate928_model.cpp (another settle signature).
    gate928 = 'REWINDBOX_GPU_DEACTIVATION_GATE_928' in read(source, GATE)
    if gate928:
        extra += ['-DREWINDBOX_GPU_DEACTIVATION_GATE_928']
    reports = {}
    with tempfile.TemporaryDirectory(prefix='mvk-async927-') as tmp:
        for label, flags in variants:
            binary = Path(tmp) / f'model-{label}'
            build = subprocess.run([cxx, '-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-fno-omit-frame-pointer',
                                    '-I', str(source / 'rpcs3'), *extra, *flags, str(MODEL), '-o', str(binary)], capture_output=True, text=True)
            if build.returncode and label != 'plain' and 'libclang_rt.' in build.stderr and 'cannot find' in build.stderr:
                reports[label] = 'not run: this compiler has no such sanitizer runtime on this host'
                continue
            require(build.returncode == 0, f'model build failed ({label}):\n' + build.stderr[-4000:])
            result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=900,
                                    env={'ASAN_OPTIONS': 'detect_leaks=0', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1',
                                         'TSAN_OPTIONS': 'halt_on_error=1', 'PATH': '/usr/bin:/bin'})
            require(result.returncode == 0, f'model failed ({label}, {result.returncode}):\n' + (result.stdout + result.stderr)[-4000:])
            report = json.loads([line for line in result.stdout.splitlines() if line.startswith('{')][-1])
            require(report['failures'] == 0, f'model report ({label})')
            require(report['semaphore']['neverSignaledOldRule'] > 0 and report['semaphore']['neverSignaledStrict'] == 0,
                    'the rule before 927 hands a semaphore token out twice; the strict barrier never does')
            require(report['query']['notReadySpinsOldRule'] > 100 and report['query']['notReadySpinsEncodeWait'] == 0,
                    'the gather spun on VK_NOT_READY; it now sleeps until its command buffer is encoded')
            require((report['gate'] is None) == gate928, 'the gate scenarios run here for Core 927 and in the 928 test afterwards')
            require(gate928 or (report['gate']['refusedWithoutGate'] > 0 and report['gate']['refusedWithGate'] == 0 and
                                report['gate']['refusedQueuedWithoutSettle'] > 0 and report['gate']['refusedQueuedWithSettle'] == 0),
                    'commits were refused in the background; with the gate and the settle none is')
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
    report = {'test': 'rpcs3_mvk_async927', 'source_checks': source_checks(source),
              'model': run_model(source, args.cxx, not args.no_sanitizers), 'iphone_tested': False, 'fps_claimed': False}
    report['result'] = 'passed'
    text = json.dumps(report, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + '\n')
    print(text)
    print('PASS: Core 927 asynchronous MoltenVK submits (no boot record, every title, strict encoding order, background gate)')


if __name__ == '__main__':
    main()
