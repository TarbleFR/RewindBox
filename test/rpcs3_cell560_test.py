#!/usr/bin/env python3
"""Source-bound 560 host checks for the deferred framebuffer-commit write-back.

Every production body is copied verbatim from the 560 Core source; its 559
control comes from the authenticated reverse fixture. Adapters model guest
memory, one GPU image and its pending copy in place of Vulkan, Metal and the
GPU. Results are host correctness only: no iPhone frame time, Metal rendering,
thermal or memory-pressure result is inferred.
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
BASE = '9e7bed794e71afde8817c6201cfdf4c72b1ae761'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell560.diff'
TEXTURES = 'rpcs3/Emu/RSX/Common/texture_cache.h'
UTILS = 'rpcs3/Emu/RSX/Common/texture_cache_utils.h'
TYPES_H = 'rpcs3/Emu/RSX/Common/texture_cache_types.h'
TYPES_CPP = 'rpcs3/Emu/RSX/Common/texture_cache_types.cpp'
VK_CACHE = 'rpcs3/Emu/RSX/VK/VKTextureCache.h'
VK_RENDER = 'rpcs3/Emu/RSX/VK/VKGSRender.cpp'
DEFERRED = 'rpcs3/ios/IOSDeferredCommit.h'
READBACK = 'rpcs3/ios/IOSReadbackProfile.h'
PERFORMANCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
CONFIG = 'rpcs3/Emu/system_config.h'
INPUTS = ['test/rpcs3_cell560_test.py', 'test/native/rpcs3_deferred560.inc']
SANITIZERS = (('addressUndefined', 'address,undefined'), ('thread', 'thread'))


def authenticated_baseline(source, work):
    manifest_path = ROOT / 'build-utils/rpcs3/canonical-source.json'
    manifest = json.loads(manifest_path.read_bytes())
    record = manifest['cell560']
    assert record['baseline'] == BASE
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert record['codegen'] == old_manifest['cell559']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    paths = set(record['modified_paths']) | set(record['new_files'])
    assert set(record['before_sha256']) == set(record['modified_paths'])
    assert set(record['after_sha256']) == paths
    assert record['new_files'] == [DEFERRED]
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
    assert not (before / DEFERRED).exists()
    # Every other Core source is byte-identical to the 559 Core.
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


def deferred_commit(source, before, work, sanitizer):
    """The deferral keeps every guest-observable byte, drops unseen copies and never waits on an unsubmitted buffer."""
    template = (NATIVE / 'rpcs3_deferred560.inc').read_text()
    prelude, rest = template.split('//@@VERSION\n')
    prelude = prelude.split('//@@PRELUDE\n')[1]
    version, main = rest.split('//@@MAIN\n')
    types_h, types_cpp = (source / TYPES_H).read_text(), (source / TYPES_CPP).read_text()
    # The cause class and its flag table are not part of the 560 change.
    assert types_h == (before / TYPES_H).read_text() if (before / TYPES_H).exists() else True
    prelude = prelude.replace('@CAUSE_CLASS@', braced(types_h, 'class invalidation_cause') + ';')
    prelude = prelude.replace('@CAUSE_FLAGS@', braced(types_cpp, 'void invalidation_cause::flag_bits_from_cause(enum_type cause)'))
    starts = {'@FLUSH@': 'void flush()\n\t\t{\n\t\t\tif (flushed) return;',
              '@UNPROTECT@': 'inline void unprotect()\n\t\t{',
              '@DISCARD@': 'inline void discard(bool set_dirty = true)\n\t\t{',
              '@REPROTECT@': 'void reprotect(const utils::protection prot)\n\t\t{'}

    def instance(root, ns, after):
        utils, cache, vk = (root / UTILS).read_text(), (root / TEXTURES).read_text(), (root / VK_CACHE).read_text()
        code = version.replace('@NS@', ns)
        for marker, start in starts.items():
            code = code.replace(marker, braced(utils, start))
        code = code.replace('@CREATE_SYNC@', braced(vk, '\t\t\tif (synchronized)\n\t\t\t{'))
        code = code.replace('@FLUSHABLE@', braced(cache, '\t\t\t\tif (tex.is_flushable())\n\t\t\t\t{'))
        if after:
            helpers = utils[utils.index('\t\t/**\n\t\t * CELL560_DEFERRED_COMMIT'):]
            helpers = helpers[:helpers.index('#endif')]
            code = code.replace('@HELPERS@', helpers)
            code = code.replace('@DECISION@', ios_block(cache, '\t\t\tbool ios_defer_commit = false;'))
        else:
            code = code.replace('@HELPERS@', '').replace('@DECISION@', '')
        return code

    # Outside the iOS blocks the four section functions are the 559 ones.
    for start in starts.values():
        assert squash(without_ios_blocks(braced((source / UTILS).read_text(), start))) == \
            squash(without_ios_blocks(braced((before / UTILS).read_text(), start))), start
    code = prelude + instance(before, 'before', False) + instance(source, 'after', True) + main
    report, digest = build_and_run(work, 'deferred560', code, source, sanitizer, extra=['-DRPCS3_IOS=1'])
    assert report['observedIdentical'] == report['scenarios'] == 12
    assert report['gpuWaitsAfter'] < report['gpuWaitsBefore']
    assert report['unsubmittedWaitsWithoutSubmit'] == 1 and report['unsubmittedWaits'] == 0
    return dict(report, harnessSHA256=digest)


def renderer_contract(source, before):
    """VK: each commit that recorded a copy is submitted before the next one; faults are attributed."""
    render, old = (source / VK_RENDER).read_text(), (before / VK_RENDER).read_text()
    assert squash(without_ios_blocks(render)) == squash(without_ios_blocks(old)), 'non-iOS renderer changed'
    commits = render.count('m_texture_cache.commit_framebuffer_memory_region(')
    assert commits == 3 == old.count('m_texture_cache.commit_framebuffer_memory_region(')
    assert render.count('ios_submit_deferred_commit();') == commits
    for call in render.split('m_texture_cache.commit_framebuffer_memory_region(')[1:]:
        statement_end = call.index(';')
        assert call[statement_end:statement_end + 80].lstrip(';\n').lstrip().startswith('#ifdef RPCS3_IOS\n'), call[:120]
    assert 'Origin::fault_write : rpcs3::ios::readback::Origin::fault_read' in render
    cache = (source / TEXTURES).read_text()
    assert 'Origin::fbo_commit' in ios_block(cache, '\t\t\tconst rpcs3::ios::readback::OriginScope ios_readback_origin(rpcs3::ios::readback::Origin::fbo_commit);')
    return {'commitsSubmittedAfterDeferral': commits, 'faultOriginsAttributed': True, 'nonIosRendererUnchanged': True}


def export_contract(source, before):
    """The setting, its Automatic scope, the boot log, the OPT560 line and the appended readback origins."""
    readback, old_readback = (source / READBACK).read_text(), (before / READBACK).read_text()
    old_names = '"unknown", "texture_cpu", "blit_source_cpu", "blit_destination_dma", "presentation_cpu"'
    assert old_names in old_readback and old_names + ',\n    "fbo_commit", "fault_read", "fault_write"' in readback
    performance = (source / PERFORMANCE).read_text()
    line = performance[performance.index('"COREPROF OPT560'):]
    line = line[:line.index('window_boundary_approximate=1"') + 31]
    for field in ('deferred_fbo_writeback=%u', 'deferrals=%llu', 'deferral_bytes=%llu', 'writebacks=%llu:%.3f:%.3f',
                  'writeback_bytes=%llu', 'forced_writebacks=%llu', 'dropped=%llu', 'dropped_bytes=%llu', 'submits=%llu'):
        assert field in line, field
    assert 'COREPROF READBACK555' in performance and 'COREPROF OPT559' in performance
    config = (source / CONFIG).read_text()
    assert 'deferred_fbo_writeback{ this, "Deferred Framebuffer Write-back", ios_experimental_mode::automatic };' in config
    policy = (source / POLICY).read_text()
    assert 'rpcs3::ios::deferred_commit::is_dbz_budokai_hd_title(Emu.GetTitleID())' in policy
    assert 'deferred_commit::enabled.store(resolved.deferred_fbo_writeback' in policy
    assert 'deferred_fbo_writeback=%d' in policy
    deferred = (source / DEFERRED).read_text()
    assert 'return title_id == "BLES01658";' in deferred
    settings = (source / SETTINGS).read_text()
    assert 'SETTING("experimental.deferred_fbo_writeback", "Experimental", "FPS Experiments", "Deferred framebuffer write-back"' in settings
    return {'line': 'COREPROF OPT560', 'automaticTitles': ['BLES01658'], 'readbackOriginsAppended': ['fbo_commit', 'fault_read', 'fault_write']}


def codegen_identity(source):
    """No PPU/SPU codegen input changes: the identities stay those of 559, without an alias."""
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell560']
    assert cache_identities(source) == record['codegen'] == manifest['cell559']['codegen']
    assert not any(p.startswith('rpcs3/Emu/Cell/') or p.endswith('.cmake') for p in record['modified_paths'] + record['new_files'])
    return {'identities': record['codegen'], 'unchangedFrom559': True, 'coldCompileRequiredByThisChange': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        before, contract = authenticated_baseline(source, work)
        result = {'passed': False, 'build': 560, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                  'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
                  'renderer': renderer_contract(source, before), 'exportLine': export_contract(source, before)}
        result['deferredCommit'] = {name: deferred_commit(source, before, work, flag) for name, flag in SANITIZERS}
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
    result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Host correctness of the 560 production bodies against their exact 559 preimages under sanitizers; '
                        'no iPhone FPS, frame time, Metal rendering, thermal or memory-pressure result.')
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output)


if __name__ == '__main__':
    main()
