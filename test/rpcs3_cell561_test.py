#!/usr/bin/env python3
"""Source-bound 561 host checks for early command-buffer submission.

The early-submission routine, the primary-submission tracking block and the
per-frame reset are copied verbatim from the 561 Core source; the 560 control
comes from the authenticated reverse fixture. Adapters model the RSX thread
recording draws, one in-order GPU queue and a per-frame readback in place of
Vulkan, Metal and the GPU. Results are host correctness and a timing model
only: no iPhone frame time, Metal rendering, thermal or memory-pressure result
is inferred.
"""
import argparse
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'test'))
from rpcs3_cell559_test import braced, build_and_run, compilers, normalized_sha, sha, squash, without_ios_blocks

NATIVE = ROOT / 'test/native'
BASE = 'e0f4f6d9f02763df0356669870e464eeab415443'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell561.diff'
VK_RENDER = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
VK_HEADER = 'rpcs3/Emu/RSX/VK/VKGSRender.h'
VK_DRAW = 'rpcs3/Emu/RSX/VK/VKDraw.cpp'
VK_PRESENT = 'rpcs3/Emu/RSX/VK/VKPresent.cpp'
EARLY = 'rpcs3/ios/IOSEarlySubmit.h'
PERFORMANCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
CONFIG = 'rpcs3/Emu/system_config.h'
INPUTS = ['test/rpcs3_cell561_test.py', 'test/native/rpcs3_early561.inc']
SANITIZERS = (('addressUndefined', 'address,undefined'), ('thread', 'thread'))


def authenticated_baseline(source, work):
    manifest_path = ROOT / 'build-utils/rpcs3/canonical-source.json'
    manifest = json.loads(manifest_path.read_bytes())
    record = manifest['cell561']
    assert record['baseline'] == BASE
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell561' not in old_manifest
    assert record['codegen'] == old_manifest['cell560']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    paths = set(record['modified_paths']) | set(record['new_files'])
    assert set(record['before_sha256']) == set(record['modified_paths'])
    assert set(record['after_sha256']) == paths
    assert record['new_files'] == [EARLY]
    before = work / 'before'
    for path in paths:
        current = source / path
        assert normalized_sha(current) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(current.read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest == old_manifest['files_sha256'][path], path
    assert not (before / EARLY).exists()
    # Every other Core source is byte-identical to the 560 Core.
    for path, digest in old_manifest['files_sha256'].items():
        if path not in paths:
            assert manifest['files_sha256'][path] == digest, path
    return before, {
        'baseline': BASE, 'fixtureSHA256': sha(FIXTURE.read_bytes()),
        'manifestSHA256': sha(manifest_path.read_bytes()), 'sourceSHA256': record['after_sha256'],
        'otherCoreSourcesUnchanged': len(old_manifest['files_sha256']) - len(record['modified_paths']),
    }


def ios_block(text, start):
    """The `#ifdef RPCS3_IOS` block that contains the unique `start` line."""
    assert text.count(start) == 1, start
    a = text.rindex('#ifdef RPCS3_IOS', 0, text.index(start))
    return text[a:text.index('#endif', text.index(start)) + len('#endif')]


def production_parts(source):
    render = (source / VK_RENDER).read_text()
    early = braced(render, 'void VKGSRender::ios_early_submit()').replace('void VKGSRender::ios_early_submit()', 'void ios_early_submit()', 1)
    track = ios_block(render, '\tm_ios_last_primary_submit = m_current_command_buffer;')
    reset = ios_block((source / VK_PRESENT).read_text(), '\tm_ios_early_submits_this_frame = 0;')
    return early, track, reset


def early_submission(source, work, sanitizer):
    """Early submissions keep the draw order, never meet a busy GPU, respect the
    chunk and frame limits and the guards, and leave 560 boundaries when off."""
    template = (NATIVE / 'rpcs3_early561.inc').read_text()
    prelude, main = template.split('//@@MAIN\n')
    prelude = prelude.split('//@@PRELUDE\n')[1]
    early, track, reset = production_parts(source)
    code = prelude.replace('//@EARLY@', early).replace('//@TRACK@', track).replace('//@RESET@', reset) + main
    report, digest = build_and_run(work, 'early561', code, source, sanitizer, extra=['-DRPCS3_IOS=1'])
    combat = report['combat']
    assert report['scenarios'] == 8 and report['decisions'] > 0
    assert combat['readbackWaitAfterMsPerFrame'] < combat['readbackWaitBeforeMsPerFrame']
    assert combat['frameAfterMs'] < combat['frameBeforeMs']
    assert report['capReachedWithFastGpu'] == report['maxPerFrame']
    return dict(report, harnessSHA256=digest)


def renderer_contract(source, before):
    """Non-iOS renderer code is the 560 one; the hook, the tracking and the reset sit where documented."""
    for path in (VK_RENDER, VK_HEADER, VK_DRAW, VK_PRESENT):
        assert squash(without_ios_blocks((source / path).read_text())) == \
            squash(without_ios_blocks((before / path).read_text())), path + ': non-iOS code changed'
    render = (source / VK_RENDER).read_text()
    # Tracking: right after the one primary submission of close_and_submit_command_buffer.
    submit = braced(render, 'void VKGSRender::close_and_submit_command_buffer(')
    assert submit.count('m_current_command_buffer->submit(primary_submit_info, force_flush);') == 1
    after_submit = submit.split('m_current_command_buffer->submit(primary_submit_info, force_flush);')[1].lstrip('\n')
    assert after_submit.startswith('#ifdef RPCS3_IOS\n\t// CELL561_EARLY_SUBMIT: every primary submission passes here.\n'
                                   '\tm_ios_last_primary_submit = m_current_command_buffer;\n\tm_ios_draws_since_submit = 0;\n#endif\n')
    # The early submission only switches command buffers through flush_command_queue.
    early, _, _ = production_parts(source)
    assert early.count('flush_command_queue();') == 1 and 'close_and_submit_command_buffer' not in early
    assert 'hard_sync' not in early and 'wait(' not in early
    # Hook: the last statement of VKGSRender::end(), after the draw is complete.
    draw = (source / VK_DRAW).read_text()
    end = braced(draw, 'void VKGSRender::end()')
    tail = end[end.rindex('m_rtts.on_write(m_framebuffer_layout.color_write_enabled, m_framebuffer_layout.zeta_write_enabled);'):]
    assert squash(tail) == squash('m_rtts.on_write(m_framebuffer_layout.color_write_enabled, m_framebuffer_layout.zeta_write_enabled);\n'
        '#ifdef RPCS3_IOS\n// CELL561_EARLY_SUBMIT: the draw is complete; feed a GPU that has drained.\nios_early_submit();\n#endif\n'
        'rsx::thread::end();\n}'), tail
    assert draw.count('ios_early_submit();') == 1 and render.count('ios_early_submit();') == 0
    # Reset: once per frame, at the flip's submission, before present().
    present = (source / VK_PRESENT).read_text()
    assert present.count('m_ios_early_submits_this_frame = 0;') == 1
    assert present.index('m_ios_early_submits_this_frame = 0;') < present.index('present(m_current_frame);')
    header = (source / VK_HEADER).read_text()
    assert ios_block(header, '\tu32 m_ios_draws_since_submit = 0;').count('m_ios_') == 3
    return {'hook': 'end of VKGSRender::end', 'tracking': 'after the primary submit', 'reset': 'flip submission',
            'switchesOnlyThroughFlushCommandQueue': True, 'nonIosRendererUnchanged': True}


def export_contract(source):
    """The setting, its Automatic scope, the boot log and the OPT561 line."""
    config = (source / CONFIG).read_text()
    assert 'early_submit{ this, "Early Command Buffer Submission", ios_experimental_mode::automatic };' in config
    assert 'bool early_submit = false;' in (source / POLICY_H).read_text()
    policy = (source / POLICY).read_text()
    assert ('resolved.early_submit = resolve_mode(g_cfg.ios_experimental.early_submit,\n'
            '\t\trpcs3::ios::deferred_commit::is_dbz_budokai_hd_title(Emu.GetTitleID()));') in policy
    assert 'rpcs3::ios::early_submit::enabled.store(resolved.early_submit, std::memory_order_relaxed);' in policy
    assert 'early_submit=%d' in policy
    settings = (source / SETTINGS).read_text()
    assert 'SETTING("experimental.early_submit", "Experimental", "FPS Experiments", "Early command buffer submission"' in settings
    performance = (source / PERFORMANCE).read_text()
    line = performance[performance.index('"COREPROF OPT561'):]
    line = line[:line.index('window_boundary_approximate=1"') + 31]
    for field in ('early_submit=%u', 'early_submits=%llu', 'early_draws=%llu', 'gpu_busy_checks=%llu',
                  'frame_capped_checks=%llu', 'min_draws=%u', 'max_per_frame=%u'):
        assert field in line, field
    assert 'COREPROF OPT560' in performance and 'COREPROF READBACK555' in performance
    header = (source / EARLY).read_text()
    assert 'constexpr std::uint32_t min_draws = 32;' in header and 'constexpr std::uint32_t max_per_frame = 6;' in header
    return {'line': 'COREPROF OPT561', 'automaticTitles': ['BLES01658'], 'minDraws': 32, 'maxPerFrame': 6}


def codegen_identity(source):
    """No PPU/SPU codegen input changes: the identities stay those of 560, without an alias."""
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell561']
    assert cache_identities(source) == record['codegen'] == manifest['cell560']['codegen']
    assert not any(p.startswith('rpcs3/Emu/Cell/') or p.endswith('.cmake') for p in record['modified_paths'] + record['new_files'])
    return {'identities': record['codegen'], 'unchangedFrom560': True, 'coldCompileRequiredByThisChange': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        before, contract = authenticated_baseline(source, work)
        result = {'passed': False, 'build': 561, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                  'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
                  'renderer': renderer_contract(source, before), 'exportLine': export_contract(source)}
        result['earlySubmission'] = {name: early_submission(source, work, flag) for name, flag in SANITIZERS}
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
    result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Host correctness of the 561 production bodies and a simulated-time model of the RSX thread and '
                        'one GPU queue; no iPhone FPS, frame time, Metal rendering, thermal or memory-pressure result.')
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output)


if __name__ == '__main__':
    main()
