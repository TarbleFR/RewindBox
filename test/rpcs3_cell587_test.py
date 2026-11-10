#!/usr/bin/env python3
"""Source-bound 587 host checks: MoltenVK asynchronous submits made safe (CELL587_MVK_ENCODE_BARRIER, CELL587_MVK_ASYNC_CANARY).

With MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS=0, MoltenVK 1.4.2 encodes every
vkQueueSubmit and vkQueuePresentKHR later, on a serial GCD queue, and
vkAcquireNextImageKHR releases, without a lock, the drawable of the image it
returns, which a still-queued render or present of that image fetches. The
551 boots ended in the first second, while the shader cache dialog flipped
frames back to back. Core 587:

* records MoltenVK's encoding queue through a renamed dispatch_queue_create
  reference (build-utils/rpcs3/patch_moltenvk_exec_queue.py, pinned digests);
* queues a marker behind each present and waits for the marker of the last
  present before every acquisition (VKPresent.cpp), and orders the MetalFX
  handoff (offloader flush + drain of the encoding queue);
* turns asynchronous submits on for God of War III (Automatic) only while the
  title's last asynchronous boot finished: a boot is armed durably at Vulkan
  instance creation and confirmed after 900 guest flips or a clean renderer
  shutdown; a title still armed at the next boot keeps synchronous submits.

This test authenticates the 585 preimages, checks the source contract and
the off-iOS text, and runs the header logic (labels, present tracker, boot
canary) and a model of MoltenVK's own swapchain rules on a serial queue
thread, plain, ASan/UBSan and TSan. On macOS it also runs the GCD registry of
ios/IOSMoltenVKExecQueue.h against the real libdispatch. No iPhone FPS,
frame time or crash result is inferred.
"""
import argparse
import json
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
from rpcs3_cell559_test import braced, compilers, normalized_sha, sha, without_ios_blocks

BASE = '2b013636f53a432bf67752d30d84a2bb33facbf2'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell587.diff'
PRESENT = 'rpcs3/Emu/RSX/VK/VKPresent.cpp'
RENDER = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
RENDER_H = 'rpcs3/Emu/RSX/VK/VKGSRender.h'
DEVICE = 'rpcs3/Emu/RSX/VK/vkutils/device.cpp'
INSTANCE = 'rpcs3/Emu/RSX/VK/vkutils/instance.cpp'
LEVERS = 'rpcs3/ios/IOSTitleLevers.h'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
PERF = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
PLATFORM = 'rpcs3/ios/RPCS3IOSPlatform.mm'
EXEC = 'rpcs3/ios/IOSMoltenVKExec.h'
QUEUE = 'rpcs3/ios/IOSMoltenVKExecQueue.h'
CANARY = 'rpcs3/ios/IOSMoltenVKAsyncCanary.h'
MODIFIED = {PRESENT, RENDER, RENDER_H, DEVICE, INSTANCE, LEVERS, POLICY, POLICY_H, PERF, PLATFORM}
NEW_FILES = [EXEC, QUEUE, CANARY]
SHARED = [PRESENT, RENDER, RENDER_H, DEVICE, INSTANCE]
TOOL = ROOT / 'build-utils/rpcs3/patch_moltenvk_exec_queue.py'
QOS_TOOL = ROOT / 'build-utils/rpcs3/patch_moltenvk_compile_qos.py'
BUILD = ROOT / 'build-utils/build_rpcs3_embedded_core.sh'
EXEC_TEST = ROOT / 'test/native/rpcs3_cell587_mvk_exec_test.cpp'
GCD_TEST = ROOT / 'test/native/rpcs3_cell587_mvk_gcd_test.cpp'
INPUTS = ['test/rpcs3_cell587_test.py', 'test/native/rpcs3_cell587_mvk_exec_test.cpp',
          'test/native/rpcs3_cell587_mvk_gcd_test.cpp', 'build-utils/rpcs3/patch_moltenvk_exec_queue.py']
QOS_PATCHED = 'b91a46f74456949aa2a6cb73de9696d0b5508efe3a7c30041e0ff07232fc9de4'
EXEC_PATCHED = '0ee6ae968193749e56d76be71dafb7c36ce4aa19b84f5bb69acd8154d38e06a1'


def full_base():
    return subprocess.check_output(['git', 'rev-parse', BASE], cwd=ROOT, text=True).strip()


def authenticated_baseline(source, work):
    """The 585 preimages: the reverse 587 fixture over the ten files, authenticated by both manifests."""
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell587']
    assert record['baseline'] == full_base()
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', full_base() + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell587' not in old_manifest and 'cell585' in old_manifest
    assert record['codegen'] == old_manifest['cell585']['codegen']
    assert record['core_baseline'] == 'cell585' and record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == NEW_FILES and set(record['modified_paths']) == MODIFIED
    assert record['moltenvk_archive'] == {'input_sha256': QOS_PATCHED, 'patched_sha256': EXEC_PATCHED,
                                          'renamed': ['_dispatch_queue_create', '_rbx_mvk_exec_q_create']}
    before = work / 'before585'
    for path in MODIFIED | set(NEW_FILES):
        assert normalized_sha(source / path) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest == old_manifest['files_sha256'][path], path
    for path in NEW_FILES:
        assert not (before / path).exists(), path
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256']) | set(NEW_FILES)
    for path, digest in old_manifest['files_sha256'].items():
        if path not in MODIFIED:
            assert manifest['files_sha256'][path] == digest, path
    return before, {'baseline': full_base(), 'fixtureSHA256': record['fixture_sha256'],
                    'sourceSHA256': record['after_sha256'], 'newFiles': NEW_FILES,
                    'otherCoreSourcesUnchanged': len(set(old_manifest['files_sha256']) - MODIFIED)}


def codegen_identity(source):
    """No PPU or SPU codegen source changes: the 585 object caches stay valid."""
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert cache_identities(source) == manifest['cell587']['codegen'] == manifest['cell585']['codegen']
    return {'identities': manifest['cell587']['codegen'], 'unchangedFrom585': True, 'coldCompileRequiredByThisChange': False}


def off_ios(source, before):
    """A non-iOS compiler sees the 585 text of every shared file."""
    for path in SHARED:
        assert without_ios_blocks((source / path).read_text()) == without_ios_blocks((before / path).read_text()), path
    return {'sharedFiles': SHARED, 'iosOnlyFiles': sorted((MODIFIED - set(SHARED)) | set(NEW_FILES))}


def source_contract(source, before):
    """Where the barrier, the canary and their profile sit, and what stays as in 585."""
    present = (source / PRESENT).read_text()
    flip = braced(present, 'void VKGSRender::flip(const rsx::display_flip_info_t& info)')
    # One acquisition site in the renderer, and the wait for the last queued present comes first.
    assert present.count('acquire_next_swapchain_image(') == 1
    assert flip.index('ios_wait_for_queued_present();') < flip.index('acquire_next_swapchain_image(')
    assert flip.index('ios_wait_for_queued_present();') > flip.index('ensure(m_current_frame->swap_command_buffer == nullptr);')
    vk_tree = source / 'rpcs3/Emu/RSX/VK'
    acquires = [p.relative_to(source).as_posix() for p in vk_tree.rglob('*') if p.is_file() and p.suffix in ('.cpp', '.h', '.hpp', '.mm')
                and 'vkAcquireNextImageKHR(' in p.read_text(errors='replace')]
    assert acquires == ['rpcs3/Emu/RSX/VK/vkutils/swapchain_core.h'], acquires
    callers = [p.relative_to(source).as_posix() for p in vk_tree.rglob('*.cpp') if 'acquire_next_swapchain_image(' in p.read_text(errors='replace')]
    assert sorted(callers) == [PRESENT, 'rpcs3/Emu/RSX/VK/vkutils/swapchain.cpp'], callers
    # The marker follows the present call.
    body = braced(present, 'void VKGSRender::present(vk::frame_context_t *ctx)')
    assert body.index('m_swapchain->present(ctx->present_wait_semaphore, ctx->present_image)') < body.index('rpcs3::ios::moltenvk_exec::mark_present()')
    assert 'm_ios_last_present_ticket = ticket;' in body
    waits = braced(present, 'void VKGSRender::ios_wait_for_queued_present()')
    assert 'rpcs3::ios::moltenvk_exec::wait_for_present(m_ios_last_present_ticket);' in waits
    assert 'barrier_missing' in waits and 'ios_drain_queued_submissions();' in waits
    drain = braced(present, 'void VKGSRender::ios_drain_queued_submissions()')
    assert 'rpcs3::ios::moltenvk_exec::drain();' in drain and 'vkQueueWaitIdle(m_device->get_present_queue());' in drain
    assert drain.index('vk::acquire_global_submit_lock();') < drain.index('vkQueueWaitIdle') < drain.index('vk::release_global_submit_lock();')
    # MetalFX: the handoff submission is flushed by the offloader and encoded before MetalFX commits.
    handoff = flip[flip.index('vk::command_buffer_chunk* const metal_fx_handoff = m_current_command_buffer;'):flip.index('if (m_metal_fx_spatial->encode())')]
    assert handoff.index('close_and_submit_command_buffer(') < handoff.index('metal_fx_handoff->flush();') < handoff.index('ios_drain_queued_submissions();')
    # Canary: guest flips after the swap request.
    assert flip.index('queue_swap_request(!acquire_consumed_before_present);') < flip.index('rpcs3::ios::note_moltenvk_async_flip();')
    assert 'if (info.emu_flip)\n\t{\n\t\trpcs3::ios::note_moltenvk_async_flip();' in flip
    render = (source / RENDER).read_text()
    destructor = braced(render, 'VKGSRender::~VKGSRender()')
    assert destructor.index('rpcs3::ios::confirm_moltenvk_async_boot("renderer shutdown");') < destructor.index('if (m_device == VK_NULL_HANDLE)')
    header = (source / RENDER_H).read_text()
    assert 'u64 m_ios_last_present_ticket = 0;' in header
    # Device: the queues of this device, recorded during vkCreateDevice.
    device = (source / DEVICE).read_text()
    assert device.index('rpcs3::ios::moltenvk_exec::begin_device();') < device.index('if (auto error = vkCreateDevice(*pgpu, &device, nullptr, &dev))')
    assert device.index('if (auto error = vkCreateDevice(*pgpu, &device, nullptr, &dev))') < device.index('rpcs3::ios::moltenvk_exec::queue_count();')
    assert 'barrier_missing.store(exec_queues != 1' in device
    # The 551 high global priority stays with asynchronous submits.
    assert 'ios_queue_priority.globalPriority = VK_QUEUE_GLOBAL_PRIORITY_HIGH_EXT;' in device
    instance = (source / INSTANCE).read_text()
    assert ('if (rpcs3::ios::get_experimental_policy().moltenvk_async_submits && rpcs3::ios::arm_moltenvk_async_boot())\n'
            '\t\t\t\t{\n\t\t\t\t\tmvk_settings.push_back(VkLayerSettingEXT{ kMVKMoltenVKDriverLayerName, "MVK_CONFIG_SYNCHRONOUS_QUEUE_SUBMITS"') in instance
    # Policy: Automatic is God of War III, through the canary.
    policy = (source / POLICY).read_text()
    assert ('resolved.moltenvk_async_submits = resolve_mvk_async(title_id,\n'
            '\t\tresolve_mode(g_cfg.ios_experimental.moltenvk_async_submits, is_god_of_war_iii_title(title_id)));') in policy
    old_policy = (before / POLICY).read_text()
    assert 'resolved.moltenvk_async_submits = resolve_mode(g_cfg.ios_experimental.moltenvk_async_submits, false);' in old_policy
    arm = braced(policy, 'bool arm_moltenvk_async_boot() noexcept')
    assert arm.index('!write_mvk_canary(records)') < arm.index('s_policy.moltenvk_async_submits = false;') < arm.index('s_mvk_canary_armed = true;')
    write = braced(policy, 'bool write_mvk_canary(const std::vector<mvk_async_canary::record>& records)')
    assert write.index('::fsync(fd)') < write.index('::rename(temp.c_str(), path.c_str())')
    # Platform: the renamed MoltenVK reference, defined once, hidden.
    plat = (source / PLATFORM).read_text()
    assert plat.count('REWINDBOX_MOLTENVK_EXEC_BARRIER_V1') == 1 and 'REWINDBOX_MOLTENVK_COMPILE_QOS_V1' in plat
    assert plat.count('extern "C" __attribute__((visibility("hidden"))) dispatch_queue_t rbx_mvk_exec_q_create(const char* label, dispatch_queue_attr_t attr)') == 1
    hook = braced(plat, 'extern "C" __attribute__((visibility("hidden"))) dispatch_queue_t rbx_mvk_exec_q_create(const char* label, dispatch_queue_attr_t attr)')
    assert 'dispatch_queue_create(label, attr);' in hook and 'registry::instance().record(queue, label);' in hook
    perf = (source / PERF).read_text()
    assert 'COREPROF OPT587 session=%llu window=%llu mvk_async=%u canary=%s confirmed=%u exec_queues=%u ' in perf
    levers = (source / LEVERS).read_text()
    assert without_comments(levers) == without_comments((before / LEVERS).read_text())
    assert 'CELL587_MVK_ENCODE_BARRIER' in levers and '490-640 ms per 5 s window' in levers
    return {'acquisitionSites': acquires, 'acquireCallers': sorted(callers),
            'barrierBeforeAcquire': True, 'markerAfterPresent': True, 'metalFxOrdered': True,
            'canaryArmedAtInstance': True, 'canaryConfirmedBy': ['900 guest flips', 'renderer shutdown'],
            'automatic': 'God of War III (is_god_of_war_iii_title)', 'globalPriorityHigh': True}


def without_comments(text):
    return '\n'.join(line for line in text.splitlines() if not line.lstrip().startswith('//'))


def build_tools():
    """The MoltenVK encoding-queue patch: pinned digests, same-length name, gated build step."""
    tool, qos, build = TOOL.read_text(), QOS_TOOL.read_text(), BUILD.read_text()
    assert f"PATCHED_SHA256 = '{QOS_PATCHED}'" in qos
    assert "ORIGINAL_SHA256 = qos.PATCHED_SHA256" in tool and f"PATCHED_SHA256 = '{EXEC_PATCHED}'" in tool
    assert "OLD = b'_dispatch_queue_create\\0'" in tool and "NEW = b'_rbx_mvk_exec_q_create\\0'" in tool
    assert len('_dispatch_queue_create') == len('_rbx_mvk_exec_q_create')
    step = build[build.index("if grep -q 'REWINDBOX_MOLTENVK_EXEC_BARRIER_V1'"):]
    assert build.index("if grep -q 'REWINDBOX_MOLTENVK_COMPILE_QOS_V1'") < build.index("if grep -q 'REWINDBOX_MOLTENVK_EXEC_BARRIER_V1'")
    assert 'patch_moltenvk_exec_queue.py" "$MOLTENVK_LIB"' in step and 'patch_moltenvk_exec_queue.py" "$MOLTENVK_LIB" --check' in step
    assert "nm -u \"$OUTPUT_DIR/libRPCS3Core.dylib\" | grep -q '_rbx_mvk_exec_q_create$'" in build
    assert 'log "MoltenVK encoding-queue hook linked"' in build
    return {'inputSHA256': QOS_PATCHED, 'patchedSHA256': EXEC_PATCHED, 'renamed': ['_dispatch_queue_create', '_rbx_mvk_exec_q_create'],
            'gate': 'REWINDBOX_MOLTENVK_EXEC_BARRIER_V1', 'appliedAfterCompileQoS': True, 'linkCheck': True}


def run_native(source, work, test, name, sanitizers, extra=()):
    reports = {}
    for label, flags in sanitizers:
        binary = work / f'{name}-{label}'
        subprocess.run(compilers() + ['-std=gnu++20', '-O1', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-fno-omit-frame-pointer',
                                      '-I' + str(source / 'rpcs3'), *flags, *extra, str(test), '-o', str(binary)], check=True)
        run = subprocess.run([str(binary)], text=True, capture_output=True, timeout=600,
                             env={'ASAN_OPTIONS': 'detect_leaks=0', 'UBSAN_OPTIONS': 'halt_on_error=1:print_stacktrace=1',
                                  'TSAN_OPTIONS': 'halt_on_error=1', 'PATH': '/usr/bin:/bin'})
        if run.returncode:
            print(run.stdout, run.stderr, file=sys.stderr)
            run.check_returncode()
        lines = [json.loads(line) for line in run.stdout.splitlines() if line.startswith('{')]
        merged = {}
        for line in lines:
            merged.update(line)
        assert merged.get('failures', merged.get('gcd', {}).get('failures')) == 0, (name, label, merged)
        reports[label] = merged
    return reports


SANITIZERS = (('plain', []), ('asanUbsan', ['-fsanitize=address,undefined']), ('tsan', ['-fsanitize=thread']))


def native(source, work):
    exec_reports = run_native(source, work, EXEC_TEST, 'cell587-exec', SANITIZERS)
    for label, report in exec_reports.items():
        model = report['model']
        assert model['hazardsWithoutBarrier'] > 0 and model['hazardsWithBarrier'] == 0, (label, model)
    result = {'exec': exec_reports, 'sanitizers': [s[0] for s in SANITIZERS]}
    if platform.system() == 'Darwin':
        gcd = run_native(source, work, GCD_TEST, 'cell587-gcd', SANITIZERS)
        for label, report in gcd.items():
            assert report['gcd']['failures'] == 0, (label, report)
        result['gcd'] = gcd
        result['realLibdispatch'] = True
    else:
        result['gcd'] = 'not run: this host has no libdispatch (runs on the macOS Core job)'
        result['realLibdispatch'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--require-gcd', action='store_true', help='fail unless the real libdispatch test ran (macOS)')
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='rpcs3-cell587-') as temporary:
        work = Path(temporary)
        before, contract = authenticated_baseline(source, work)
        result = {
            'passed': False, 'build': 587, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
            'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
            'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
            'offIOS': off_ios(source, before),
            'barrier': source_contract(source, before),
            'moltenvkArchive': build_tools(),
            'native': native(source, work),
        }
        if args.require_gcd:
            assert result['native']['realLibdispatch'] is True
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
        result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                      scope='Header logic, a model of MoltenVK 1.4.2 swapchain rules and (on macOS) the GCD registry against the real libdispatch. '
                            'No iPhone FPS, frame time or crash result.')
    text = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text, end='')


if __name__ == '__main__':
    main()
