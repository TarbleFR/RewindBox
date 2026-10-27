#!/usr/bin/env python3
"""Source-bound 573 host checks: texture residency cap and scoped texture revalidation.

Build 567, God of War III: 4.75 GB footprint (1.25 GB compressed by iOS); the
texture pool grew to 1.72 GB, fell to 366 MB when the pressure reclaim purged it
and grew back to 1.56 GB, because on iOS textures are confirmed by content hash
and a texture whose guest memory was reused is only found stale when looked up
again. Texture preparation took ~10 ms per frame, ~8 ms of it hashing (6-13 GB
per 5 s window over ~9 validation epochs per frame). 573: above 768 MB of live
textures, sections no lookup used for 64 frames are released, least recently
used first (CELL573_TEXTURE_RESIDENCY); a render target the RSX writes back or
commits revalidates only the sections over its range (CELL573_SCOPED_RSX_WRITES).
The eviction routine, the revalidation helper and the iOS blocks of flush_set and
invalidate_range_impl_base are copied verbatim from the Core into host models;
ios/IOSTextureResidency.h is compiled as the Core has it; the 571 preimages come
from the authenticated reverse fixture. Host behaviour only: no iPhone FPS,
frame time or memory result is inferred.
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
from rpcs3_cell559_test import braced, build_and_run, compilers, normalized_sha, sha, without_ios_blocks

NATIVE = ROOT / 'test/native'
BASE = 'a786dad5e4d589455f37d433349b46604727f336'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell573.diff'
TEXTURES = 'rpcs3/Emu/RSX/Common/texture_cache.h'
UTILS = 'rpcs3/Emu/RSX/Common/texture_cache_utils.h'
CACHE_CPP = 'rpcs3/Emu/RSX/Common/texture_cache.cpp'
TYPES_CPP = 'rpcs3/Emu/RSX/Common/texture_cache_types.cpp'
UPLOAD = 'rpcs3/Emu/RSX/Common/TextureUtils.h'
VK_CACHE = 'rpcs3/Emu/RSX/VK/VKTextureCache.cpp'
VK_CACHE_H = 'rpcs3/Emu/RSX/VK/VKTextureCache.h'
PRESENT = 'rpcs3/Emu/RSX/VK/VKPresent.cpp'
RESIDENCY = 'rpcs3/ios/IOSTextureResidency.h'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'
CONFIG = 'rpcs3/Emu/system_config.h'
CONFIG_TYPES = 'rpcs3/Emu/system_config_types.h'
PRESSURE = 'rpcs3/ios/IOSMemoryPressurePolicy.h'
MODIFIED = {TEXTURES, UTILS, VK_CACHE, VK_CACHE_H, PRESENT, POLICY, POLICY_H, SETTINGS, CONFIG}
INPUTS = ['test/rpcs3_cell573_test.py', 'test/native/rpcs3_texture_residency573.inc',
          'test/native/rpcs3_scoped_revalidation573.inc']
POLICY_START = '\t// CELL573_TEXTURE_RESIDENCY / CELL573_SCOPED_RSX_WRITES: Automatic is God of War III,'
POLICY_END = 'rpcs3::ios::texture_validation_scope::enabled.store(resolved.scoped_texture_revalidation, std::memory_order_relaxed);\n'
EVICT = 'template <typename HostBytes>\n\t\tu64 evict_idle_sections('
REVALIDATE = 'void revalidate_overlapping(const address_range32& range)'
FLUSH_HEAD = ('#ifdef RPCS3_IOS\n\t\t\t// CELL559_TEXTURE_EPOCH: GPU data is about to be written to guest memory.\n'
              '\t\t\t// CELL573_SCOPED_RSX_WRITES:')
INVALIDATE_HEAD = '#ifdef RPCS3_IOS\n\t\t\t// CELL559_TEXTURE_EPOCH: a write, unmap or surface commit changes guest memory.\n'
RESET = '#ifdef RPCS3_IOS\n\t\t// CELL573_SCOPED_RSX_WRITES: the next validation hashes again.\n'
STAMP = 'last_use_frame = rpcs3::ios::texture_residency::current_frame();'
PASS = '#ifdef RPCS3_IOS\n\t// CELL573_TEXTURE_RESIDENCY: above the soft cap, release textures no draw has\n'


def authenticated_baseline(source, work):
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell573']
    assert record['baseline'] == BASE
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert 'cell573' not in old_manifest and 'cell571' in old_manifest
    assert record['codegen'] == old_manifest['cell571']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    assert record['new_files'] == [RESIDENCY] and set(record['modified_paths']) == MODIFIED
    before = work / 'before'
    for path in MODIFIED | {RESIDENCY}:
        assert normalized_sha(source / path) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / path).read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    assert not (before / RESIDENCY).exists()
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest == old_manifest['files_sha256'][path], path
    assert set(manifest['files_sha256']) == set(old_manifest['files_sha256']) | {RESIDENCY}
    for path, digest in old_manifest['files_sha256'].items():
        if path not in MODIFIED:
            assert manifest['files_sha256'][path] == digest, path
    return before, {'baseline': BASE, 'fixtureSHA256': record['fixture_sha256'],
                    'sourceSHA256': record['after_sha256'],
                    'otherCoreSourcesUnchanged': len(old_manifest['files_sha256']) - len(MODIFIED)}


def between(text, start, end):
    assert text.count(start) == 1, start
    a = text.index(start)
    return text[a:text.index(end, a) + len(end)]


def ios_block(text, start):
    """The `#ifdef RPCS3_IOS` block beginning at the unique `start`, through its `#endif`."""
    return between(text, start, '#endif\n')


def placement_contract(source, before):
    """Every 573 line is inside an iOS block (a non-iOS build is the 571 one); the global epoch
    advances at the same sites unless the scope is on; uses stamp sections, maintenance does
    not; the frame-end pass runs before the texture cache's frame end."""
    for path in (TEXTURES, UTILS, VK_CACHE, VK_CACHE_H, PRESENT):
        now, old = (source / path).read_text(), (before / path).read_text()
        # A new iOS block leaves its surrounding blank lines behind; no other line may differ.
        code_lines = lambda text: [line for line in without_ios_blocks(text).splitlines() if line.strip()]
        assert code_lines(now) == code_lines(old), path
    textures = (source / TEXTURES).read_text()
    assert textures.count('texture_validation::advance_epoch()') == 3
    assert textures.count('revalidate_overlapping(') == 3
    flush = braced(textures, 'void flush_set(commandbuffer_type& cmd, thrashed_set& data')
    assert flush.index(FLUSH_HEAD) < flush.index('data.sections_to_flush.size() > 1')
    invalidate = textures[textures.index('thrashed_set invalidate_range_impl_base('):]
    head = invalidate[invalidate.index(INVALIDATE_HEAD):invalidate.index('thrashed_set result = {};')]
    assert 'if (!cause.is_read() && !ios_scoped_commit)' in head and head.count('#endif') == 2
    frame_end = braced(textures, 'virtual void on_frame_end()')
    assert 'rpcs3::ios::texture_residency::advance_frame();' in frame_end
    utils = (source / UTILS).read_text()
    assert utils.count(STAMP) == 2
    protection = braced(utils, 'bool sync_protection()')
    assert protection.index('if (!buffered_section::sync())') < protection.index(STAMP) < protection.index('return true;')
    trim = braced(utils, 'void trim_sections()')
    assert 'tex.sync_protection_untouched();\n#else\n\t\t\t\t\t\t\ttex.sync_protection();\n#endif' in trim
    assert ios_block(utils, RESET).count('void reset_validation() const { validated_epoch = 0; }') == 1
    present = (source / PRESENT).read_text()
    frame = braced(present, 'void VKGSRender::advance_queued_frames()')
    assert frame.index(PASS) < frame.index('m_texture_cache.on_frame_end();')
    block = ios_block(frame, PASS)
    for needle in ('rsx::method_registers.fragment_textures', 'rsx::method_registers.vertex_textures',
                   'm_texture_cache.evict_idle_textures(bound_textures)', 'std::lock_guard lock(m_sampler_mutex);',
                   'rsx::texture_upload_context::shader_read, rsx::texture_upload_context::blit_engine_src',
                   'invalidate_sampler_context(fs_sampler_state, m_textures_dirty, context)',
                   'invalidate_sampler_context(vs_sampler_state, m_vertex_textures_dirty, context)'):
        assert block.count(needle) == 1, needle
    vk = (source / VK_CACHE).read_text()
    evict = braced(vk, 'bool texture_cache::evict_idle_textures(const std::set<u32>& exclusion_list)')
    assert 'vmm_get_application_pool_usage(VMM_ALLOCATION_POOL_TEXTURE_CACHE)' in evict
    assert 'm_cached_memory_size.load()' in evict and 'residency::soft_cap_bytes' in evict
    upload = (source / UPLOAD).read_text()
    assert squash(braced(upload, 'enum texture_upload_context : u32')) == squash(
        'enum texture_upload_context : u32 { shader_read = 1, blit_engine_src = 2, blit_engine_dst = 4, framebuffer_storage = 8, dma = 16 }')
    config = (source / CONFIG).read_text()
    assert 'texture_residency{ this, "Texture Residency Cap", ios_experimental_mode::automatic };' in config
    assert 'scoped_texture_revalidation{ this, "Scoped Texture Revalidation", ios_experimental_mode::automatic };' in config
    settings = (source / SETTINGS).read_text()
    assert settings.count('SETTING("experimental.texture_residency"') == 1
    assert settings.count('SETTING("experimental.scoped_texture_revalidation"') == 1
    policy = (source / POLICY).read_text()
    assert 'passive_fairness=%d texture_residency=%d scoped_revalidation=%d' in policy
    assert '#include "IOSTextureResidency.h"' in policy
    policy_h = (source / POLICY_H).read_text()
    assert 'bool texture_residency = false;' in policy_h and 'bool scoped_texture_revalidation = false;' in policy_h
    for path, count in {'rpcs3/Emu/RSX/RSXFIFO.cpp': 1, 'rpcs3/Emu/RSX/NV47/HW/nv406e.cpp': 2}.items():
        assert (source / path).read_text().count('texture_validation::advance_epoch()') == count, path
    return {'nonIosBuildIdentical': 5, 'globalEpochSites': 3, 'usesStampMaintenanceDoesNot': True,
            'passBeforeFrameEnd': True, 'boundTexturesExcluded': True, 'descriptorsInvalidated': ['shader_read', 'blit_engine_src'],
            'settingsAndLogWired': True}


def squash(text):
    return re.sub(r'\s+', ' ', text).strip()


def residency(source, work, sanitizer, optimize='-O1'):
    template = (NATIVE / 'rpcs3_texture_residency573.inc').read_text()
    prelude, main = template.split('//@@MAIN\n')
    prelude = prelude.split('//@@PRELUDE\n')[1]
    assert prelude.count('//@EVICT@') == 1
    prelude = prelude.replace('//@EVICT@', braced((source / TEXTURES).read_text(), EVICT))
    report, digest = build_and_run(work, 'residency573', prelude + main, source, sanitizer,
                                   extra=['-DRPCS3_IOS=1'], optimize=optimize)
    assert report['on']['reuploadsWorkingSet'] == 0 and report['on']['peakLiveMiB'] < report['off']['peakLiveMiB'], report
    return dict(report, harnessSHA256=digest)


def scoped(source, work, sanitizer):
    textures = (source / TEXTURES).read_text()
    template = (NATIVE / 'rpcs3_scoped_revalidation573.inc').read_text()
    prelude, main = template.split('//@@MAIN\n')
    prelude = prelude.split('//@@PRELUDE\n')[1]
    invalidate = textures[textures.index('thrashed_set invalidate_range_impl_base('):]
    a = invalidate.index(INVALIDATE_HEAD)
    second = invalidate.index('#ifdef RPCS3_IOS\n\t\t\tif (ios_scoped_commit)', a)
    head = invalidate[a:invalidate.index('#endif\n', second) + len('#endif\n')]
    parts = {
        '//@FLAG_BITS@': braced((source / TYPES_CPP).read_text(), 'void invalidation_cause::flag_bits_from_cause(enum_type cause)'),
        '//@RESET_VALIDATION@': ios_block((source / UTILS).read_text(), RESET),
        '//@SYNC@': braced((source / CACHE_CPP).read_text(), 'bool buffered_section::sync() const'),
        '//@REVALIDATE@': braced(textures, REVALIDATE),
        '//@FLUSH_HEAD@': ios_block(textures, FLUSH_HEAD),
        '//@INVALIDATE_HEAD@': head,
    }
    for marker, text in parts.items():
        assert prelude.count(marker) == 1, marker
        prelude = prelude.replace(marker, text)
    report, digest = build_and_run(work, 'scoped573', prelude + main, source, sanitizer, extra=['-DRPCS3_IOS=1'])
    return dict(report, harnessSHA256=digest)


def policy_modes(source, work):
    """The policy block, verbatim: Automatic is God of War III only, Enabled every title, Disabled none."""
    policy = (source / POLICY).read_text()
    block = between(policy, POLICY_START, POLICY_END)
    gow3 = braced((source / PRESSURE).read_text(), 'constexpr bool is_god_of_war_iii_title(std::string_view title_id) noexcept')
    code = (
        '#include <cstdio>\n#include <string>\n#include <string_view>\n#include "ios/IOSTextureResidency.h"\n'
        + braced((source / CONFIG_TYPES).read_text(), 'enum class ios_experimental_mode') + ';\n'
        + gow3 + '\n'
        + braced(policy, 'bool resolve_mode(ios_experimental_mode mode, bool automatic_value) noexcept') + '\n'
        + 'struct { struct { ios_experimental_mode texture_residency, scoped_texture_revalidation; } ios_experimental; } g_cfg;\n'
        + 'struct { std::string id; const std::string& GetTitleID() const { return id; } } Emu;\n'
        + 'int main() { int ok = 1, cases = 0;\n'
        + ' for (const char* title : {"BCES00510", "BCUS98111", "BLES01658"}) {\n'
        + '  const bool is_gow3 = std::string_view(title)[1] == \'C\'; Emu.id = title;\n'
        + '  for (auto mode : {ios_experimental_mode::automatic, ios_experimental_mode::enabled, ios_experimental_mode::disabled}) {\n'
        + '   g_cfg.ios_experimental.texture_residency = g_cfg.ios_experimental.scoped_texture_revalidation = mode;\n'
        + '   struct { bool texture_residency = false, scoped_texture_revalidation = false; } resolved;\n'
        + block + '\n'
        + '   const bool on = mode == ios_experimental_mode::enabled || (mode == ios_experimental_mode::automatic && is_gow3);\n'
        + '   ok &= resolved.texture_residency == on && rpcs3::ios::texture_residency::enabled.load() == on;\n'
        + '   ok &= resolved.scoped_texture_revalidation == on && rpcs3::ios::texture_validation_scope::enabled.load() == on;\n'
        + '   cases++; } }\n'
        + ' std::printf("{\\"passed\\": %s, \\"cases\\": %d}\\n", ok ? "true" : "false", cases); return ok ? 0 : 1; }\n')
    report, digest = build_and_run(work, 'policy573', code, source, 'address,undefined', extra=['-DRPCS3_IOS=1'])
    assert report['cases'] == 9
    return dict(report, harnessSHA256=digest)


def codegen_identity(source):
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    assert cache_identities(source) == manifest['cell573']['codegen'] == manifest['cell571']['codegen']
    return {'identities': manifest['cell573']['codegen'], 'unchangedFrom571': True, 'coldCompileRequiredByThisChange': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory() as temp:
        work = Path(temp)
        before, contract = authenticated_baseline(source, work)
        result = {'passed': False, 'build': 573, 'hostSystem': platform.system(), 'hostMachine': platform.machine(),
                  'compiler': subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                  'sourceContract': contract, 'codegenIdentity': codegen_identity(source),
                  'placement': placement_contract(source, before), 'policy': policy_modes(source, work)}
        result['residency'] = {'addressUndefined': residency(source, work, 'address,undefined'),
                               'optimized': residency(source, work, '', optimize='-O2')}
        result['scopedRevalidation'] = {'addressUndefined': scoped(source, work, 'address,undefined')}
        result['inputs'] = {p: sha((ROOT / p).read_bytes()) for p in INPUTS}
    result.update(passed=True, result='passed', physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Host models of the 573 eviction routine and scoped revalidation, copied from the Core; '
                        'no iPhone FPS, frame time or memory result.')
    output = json.dumps(result, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output)


if __name__ == '__main__':
    main()
