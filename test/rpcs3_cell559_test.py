#!/usr/bin/env python3
"""Source-bound 559 host checks for the five Core optimizations.

Every production body is copied verbatim from the 559 Core source; its 555
control comes from the authenticated reverse fixture. Adapters replace LLVM
codegen, Vulkan/Metal, the GPU and the disk. Results are host correctness and
host CPU measurements only: no iPhone frame time, Metal rendering, thermal,
SPU stall or memory-pressure result is inferred.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'test/native'
BASE = '9d0ca40569f8428e29bd4a65f29a330afb25b755'
FIXTURE = ROOT / 'test/fixtures/rpcs3_cell559.diff'
SPU = 'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp'
TEXTURES = 'rpcs3/Emu/RSX/Common/texture_cache.h'
UTILS = 'rpcs3/Emu/RSX/Common/texture_cache_utils.h'
CACHE_CPP = 'rpcs3/Emu/RSX/Common/texture_cache.cpp'
PROGRAMS = 'rpcs3/Emu/RSX/Program/ProgramStateCache.cpp'
PROGRAMS_H = 'rpcs3/Emu/RSX/Program/ProgramStateCache.h'
VK_PROGRAMS = 'rpcs3/Emu/RSX/VK/VKProgramBuffer.h'
COMPAT = 'rpcs3/Emu/CPU/JITCacheCompatibility.cmake'
OVERWRITE = 'rpcs3/ios/IOSFullOverwrite.h'
PERFORMANCE = 'rpcs3/ios/RPCS3IOSPerformance.cpp'
FIFO = 'rpcs3/Emu/RSX/RSXFIFO.cpp'
INPUTS = ['test/rpcs3_cell559_test.py', 'test/native/rpcs3_dirty559.inc', 'test/native/rpcs3_vpcompare559.inc',
          'test/native/rpcs3_inline559.inc', 'test/native/rpcs3_inline559_main.inc',
          'test/native/rpcs3_overwrite559.inc', 'test/native/rpcs3_spupasses559.inc', 'test/native/rpcs3_epoch559.inc']
SANITIZERS = (('addressUndefined', 'address,undefined'), ('thread', 'thread'))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def normalized_sha(path):
    return sha(path.read_bytes().replace(b'\r\n', b'\n'))


def braced(text, start):
    """The complete brace-balanced construct beginning at the unique `start`."""
    assert text.count(start) == 1, start
    a = text.index(start)
    b = text.index('{', a) + 1
    depth = 1
    while depth:
        depth += (text[b] == '{') - (text[b] == '}')
        b += 1
    return text[a:b]


def without_ios_blocks(text):
    """What a non-iOS compiler sees: drop `#ifdef RPCS3_IOS` branches, keep their `#else`."""
    out, depth, keep = [], 0, True
    for line in text.splitlines(keepends=True):
        directive = re.match(r'\s*#\s*(ifdef|ifndef|if|endif|else|elif)\b(.*)', line)
        if not depth:
            if directive and directive.group(1) == 'ifdef' and directive.group(2).strip() == 'RPCS3_IOS':
                depth, keep = 1, False
            else:
                out.append(line)
            continue
        if directive and directive.group(1) in ('if', 'ifdef', 'ifndef'):
            depth += 1
        elif directive and directive.group(1) == 'endif':
            depth -= 1
            if not depth:
                continue
        elif directive and directive.group(1) == 'elif' and depth == 1:
            raise AssertionError('unsupported #elif in an iOS block')
        elif directive and directive.group(1) == 'else' and depth == 1:
            keep = True
            continue
        if keep:
            out.append(line)
    assert depth == 0
    return ''.join(out)


def squash(text):
    return re.sub(r'\s+', ' ', text).strip()


def authenticated_baseline(source, work):
    manifest_path = ROOT / 'build-utils/rpcs3/canonical-source.json'
    manifest = json.loads(manifest_path.read_bytes())
    record = manifest['cell559']
    assert record['baseline'] == BASE
    assert sha(FIXTURE.read_bytes()) == record['fixture_sha256']
    old_manifest = json.loads(subprocess.check_output(
        ['git', 'show', BASE + ':build-utils/rpcs3/canonical-source.json'], cwd=ROOT))
    assert record['codegen'] == old_manifest['cell555']['codegen']
    assert record['core_baseline_patch_sha256'] == old_manifest['patch_sha256']
    paths = set(record['modified_paths']) | set(record['new_files'])
    assert set(record['before_sha256']) == set(record['modified_paths'])
    assert set(record['after_sha256']) == paths
    assert record['new_files'] == [OVERWRITE]
    before = work / 'before'
    for path in paths:
        current = source / path
        assert normalized_sha(current) == record['after_sha256'][path] == manifest['files_sha256'][path], path
        target = before / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(current.read_bytes())
    subprocess.run(['git', 'apply', '--reverse', str(FIXTURE)], cwd=before, check=True)
    for path, digest in record['before_sha256'].items():
        assert normalized_sha(before / path) == digest, path
        if path in old_manifest['files_sha256']:
            assert old_manifest['files_sha256'][path] == digest, path
        else:
            upstream = subprocess.check_output(
                ['git', 'show', old_manifest['upstream_commit'] + ':' + path], cwd=source)
            assert sha(upstream.replace(b'\r\n', b'\n')) == digest, path
    assert not (before / OVERWRITE).exists()
    # Every other Core source is byte-identical to the 555 Core.
    for path, digest in old_manifest['files_sha256'].items():
        if path not in paths:
            assert manifest['files_sha256'][path] == digest, path
    return before, {
        'baseline': BASE, 'fixtureSHA256': sha(FIXTURE.read_bytes()),
        'manifestSHA256': sha(manifest_path.read_bytes()), 'sourceSHA256': record['after_sha256'],
        'otherCoreSourcesUnchanged': len(old_manifest['files_sha256']) - len(set(record['modified_paths']) & set(old_manifest['files_sha256'])),
    }


def compilers():
    cxx = shlex.split(os.environ.get('CXX', 'c++'))
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        cxx += ['-isysroot', sdk]
    return cxx


def build_and_run(work, name, code, source, sanitizer, extra=(), args=(), link=(), optimize='-O1'):
    cpp = work / (name + '.cpp')
    cpp.write_text(code)
    binary = work / (name + '-' + sanitizer.replace(',', '-'))
    flags = ['-std=gnu++20', optimize, '-g', '-Wall', '-Wextra', '-Werror', '-fno-exceptions', '-pthread',
             '-fno-omit-frame-pointer', '-I' + str(source / 'rpcs3'), '-I' + str(source)]
    if sanitizer:
        flags.append('-fsanitize=' + sanitizer)
    subprocess.run(compilers() + flags + list(extra) + [str(cpp), '-o', str(binary)] + list(link), check=True)
    run = subprocess.run([str(binary), *args], text=True, capture_output=True, timeout=600,
        env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1',
                 TSAN_OPTIONS='halt_on_error=1'))
    if run.returncode:
        print(run.stdout, run.stderr, file=sys.stderr)
        run.check_returncode()
    report = json.loads(run.stdout)
    assert report['passed'] is True, name
    return report, sha(code.encode())


def spu_cache_hit(source, before):
    """A: the pass construction moves under the miss guard, unchanged."""
    current, old = (source / SPU).read_text(), (before / SPU).read_text()
    start, end = 'LoopAnalysisManager lam;', 'fpm.addPass(ADCEPass());'
    def region(text):
        a = text.index(start)
        return text[a:text.index(end, a) + len(end)]
    assert squash(region(current)) == squash(region(old)), 'pass pipeline changed'
    guard = '\t\tif (!spu_cached_object)\n#endif\n\t\t{\n\t\t\t// Create the analysis managers.'
    assert current.count(guard) == 1, 'analysis managers are not inside the cache-miss block'
    assert current.index('CELL559_SPU_CACHE_HIT_PASSES') < current.index(guard)
    block = braced(current, guard.split('\n#endif\n')[0].strip() + '\n#endif\n\t\t{')
    assert region(current) in block and 'fpm.run(*f, fam);' in block and 'run_transforms(f);' in block
    # Outside the iOS guard the statements and their order are the 555 ones.
    def statements(text):
        a = text.index('// Create the analysis managers.')
        b = text.rindex('#ifdef RPCS3_IOS', a, text.index('const u64 codegen_started', a))
        return squash(without_ios_blocks(text[a:b]).replace('{', ' ').replace('}', ' '))
    assert statements(current) == statements(old)
    return {'passPipelineByteIdenticalModuloIndentation': True, 'constructedOnlyForCacheMiss': True,
            'regionSHA256': sha(region(current).encode())}


def codegen_identity(source, work):
    """A: the SPU/PPU object-cache identities stay those of 555, by an exact alias only."""
    sys.path.insert(0, str(ROOT / 'test'))
    from rpcs3_cell538_test import cache_identities
    manifest = json.loads((ROOT / 'build-utils/rpcs3/canonical-source.json').read_bytes())
    record = manifest['cell559']
    ids = cache_identities(source)
    assert ids == record['codegen'], ids
    alias = record['codegen_alias']
    compat = (source / COMPAT).read_text()
    assert alias['alias_sha256'] == normalized_sha(source / SPU)
    assert alias['identity_sha256'] == record['before_sha256'][SPU]
    assert f'actual STREQUAL "{alias["alias_sha256"]}"' in compat and f'"{alias["identity_sha256"]}" PARENT_SCOPE' in compat
    # Negative control: without the alias, this change would invalidate every SPU cache.
    control = work / 'identity-control'
    for path in (COMPAT, 'rpcs3/Emu/CMakeLists.txt'):
        target = control / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / path).read_bytes())
    unaliased = compat.replace(compat[compat.index('    # CELL559: compile()'):compat.index('    else()', compat.index('# CELL559'))], '')
    assert unaliased != compat and 'CELL559' not in unaliased
    (control / COMPAT).write_text(unaliased)
    cmake = (source / 'rpcs3/Emu/CMakeLists.txt').read_text()
    for kind in ('PPU', 'SPU'):
        names = re.search(r'foreach\(NEOSTATION_' + kind + r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)', cmake, re.S).group(1).split()
        for name in names:
            if name.endswith('AArch64FrameLowering.cpp'):
                continue
            relative = (source / 'rpcs3/Emu' / name).resolve().relative_to(source)
            target = control / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((source / relative).read_bytes())
    (control / 'Utilities').mkdir(exist_ok=True)
    (control / 'Utilities/JITLLVM.cpp').write_bytes((source / 'Utilities/JITLLVM.cpp').read_bytes())
    try:
        cache_identities(control)
        raise RuntimeError('the unaliased control kept the 555 identity')
    except AssertionError as error:
        control_ids = error.args[0]
    assert control_ids['PPU'] == ids['PPU'] and control_ids['SPU'] != ids['SPU'], control_ids
    script = 'include("' + str(control / COMPAT) + '")\n'
    script += f'neostation_codegen_compatible_hash("Cell/SPULLVMRecompiler.cpp" "{alias["alias_sha256"]}" mapped)\nmessage("MAPPED=${{mapped}}")\n'
    (control / 'probe.cmake').write_text(script)
    probe = subprocess.check_output(['cmake', '-P', str(control / 'probe.cmake')], stderr=subprocess.STDOUT, text=True)
    assert f'MAPPED={alias["alias_sha256"]}' in probe, probe
    script = 'include("' + str(source / COMPAT) + '")\n'
    script += f'neostation_codegen_compatible_hash("Cell/SPULLVMRecompiler.cpp" "{alias["alias_sha256"]}" mapped)\nmessage("MAPPED=${{mapped}}")\n'
    script += f'neostation_codegen_compatible_hash("Cell/SPULLVMRecompiler.cpp" "{sha(b"other")}" other)\nmessage("OTHER=${{other}}")\n'
    (control / 'probe2.cmake').write_text(script)
    probe = subprocess.check_output(['cmake', '-P', str(control / 'probe2.cmake')], stderr=subprocess.STDOUT, text=True)
    assert f'MAPPED={alias["identity_sha256"]}' in probe and f'OTHER={sha(b"other")}' in probe, probe
    return {'identities': ids, 'unchangedFrom555': True, 'aliasExactSnapshotOnly': True,
            'spuIdentityWithoutAlias': control_ids['SPU'], 'coldCompileRequiredByThisChange': False}


def dirty_hash(source, before, work, sanitizer):
    """B: a dirty hash-validated section is released without hashing."""
    utils_now, utils_old = (source / UTILS).read_text(), (before / UTILS).read_text()
    cache_cpp, cache_old = (source / CACHE_CPP).read_text(), (before / CACHE_CPP).read_text()
    old = braced(utils_old, 'bool sync_protection()')
    new = braced(utils_now, 'bool sync_protection()')
    assert without_ios_blocks(new) == without_ios_blocks(old), 'non-iOS validation changed'
    getter = braced(utils_now, 'const address_range32& get_confirmed_range() const')
    assert getter == braced(utils_old, 'const address_range32& get_confirmed_range() const')
    # Callers either test is_dirty() first or ignore the result (release only).
    texture = (source / TEXTURES).read_text()
    sites = [m.start() for m in re.finditer(r'sync_protection\(\)', texture)]
    assert len(sites) == 5, len(sites)
    for needle in ('!tex.is_dirty() && (context_mask', 'check_protection && !tex.sync_protection()',
                   '!tex.is_dirty() &&\n\t\t\t\t\ttex.matches(rsx_address, format, width, height, depth, mipmaps) &&\n\t\t\t\t\ttex.sync_protection()',
                   '// We must validate\n\t\t\t\t\ttex.sync_protection();',
                   "return e->is_dirty() || (e->get_context() != rsx::texture_upload_context::blit_engine_dst) ||\n\t\t\t\t\t\t!e->sync_protection();"):
        assert needle in texture, needle
    assert '\t\t\t\t\t\t\ttex.sync_protection();\n' in utils_now  # trim_sections ignores the result
    code = (NATIVE / 'rpcs3_dirty559.inc').read_text()
    for marker, value in (('@IS_LOCKED@', braced(cache_cpp, 'bool buffered_section::is_locked(bool actual_page_flags) const')),
                          ('@BEFORE_SYNC@', braced(cache_old, 'bool buffered_section::sync() const')),
                          ('@AFTER_SYNC@', braced(cache_cpp, 'bool buffered_section::sync() const')),
                          ('@CONFIRMED_RANGE@', getter), ('@BEFORE_SYNC_PROTECTION@', old),
                          ('@AFTER_SYNC_PROTECTION@', new)):
        assert marker in code
        code = code.replace(marker, value)
    report, digest = build_and_run(work, 'dirty559', '#define RPCS3_IOS 1\n' + code, source, sanitizer)
    return dict(report, harnessSHA256=digest, beforeSHA256=sha(old.encode()), afterSHA256=sha(new.encode()))


def vertex_compare(source, before, work, sanitizer, benchmark=False):
    """C: identical vertex programs are confirmed by one vectorized compare."""
    now, old = (source / PROGRAMS).read_text(), (before / PROGRAMS).read_text()
    head = 'bool vertex_program_compare::operator()(const RSXVertexProgram &binary1, const RSXVertexProgram &binary2) const'
    props = 'bool vertex_program_compare::compare_properties(const RSXVertexProgram& binary1, const RSXVertexProgram& binary2)'
    new_body, old_body = braced(now, head), braced(old, head)
    assert without_ios_blocks(new_body) == without_ios_blocks(old_body)
    assert braced(now, props) == braced(old, props)
    code = '#define RPCS3_IOS 1\n#include <algorithm>\n#include <source_location>\n#include <string_view>\n' + \
        'namespace fmt { [[noreturn]] void raw_range_error(std::source_location, std::string_view, std::size_t) { std::abort(); }\n' + \
        '[[noreturn]] void raw_range_error(std::source_location, std::size_t, std::size_t) { std::abort(); } }\n' + \
        (NATIVE / 'rpcs3_vpcompare559.inc').read_text()
    equality = braced((source / 'rpcs3/Emu/RSX/Program/program_util.cpp').read_text(),
                      'bool vertex_program_texture_state::operator == (const vertex_program_texture_state& other) const')
    for marker, value in (('@TEXTURE_STATE_EQUALITY@', equality),
                          ('@BEFORE_COMPARE@', old_body), ('@BEFORE_PROPERTIES@', braced(old, props)),
                          ('@AFTER_COMPARE@', new_body), ('@AFTER_PROPERTIES@', braced(now, props))):
        assert marker in code
        code = code.replace(marker, value)
    code = code.replace('#include <cstdlib>', '#include <cstdlib>\n#include <algorithm>', 1)
    report, digest = build_and_run(work, 'vpcompare559' + ('-bench' if benchmark else ''), code, source, sanitizer,
        args=['--benchmark'] if benchmark else [], optimize='-O2' if benchmark else '-O1')
    return dict(report, harnessSHA256=digest)


def inline_callback(source, before, work, sanitizer):
    """D: an inline build stops copying the vertex program and the callback state."""
    def parts(tree):
        lookup = (tree / PROGRAMS_H).read_text()
        keys = '\n'.join(braced(lookup, 'struct ' + n + '\n') + ';' for n in ('pipeline_key', 'pipeline_key_hash', 'pipeline_key_compare'))
        body = 'template<typename... Args>\n' + braced(lookup, 'pipeline_data_type get_graphics_pipeline(')
        for helper in ('pipeline_type* acquire_pipeline(', 'pipeline_type* publish_pipeline(',
                       'void abandon_pipeline_build(', 'void wake_pipeline_waiters()'):
            body += '\n' + braced(lookup, helper)
        build = braced((tree / VK_PROGRAMS).read_text(), 'pipeline_type* build_pipeline(')
        return keys, body, build
    now_parts, old_parts = parts(source), parts(before)
    assert without_ios_blocks(now_parts[1]) == without_ios_blocks(old_parts[1])
    assert without_ios_blocks(now_parts[2]) == without_ios_blocks(old_parts[2])
    # The inline variant keeps the fragment snapshot (guest memory) and references the vertex program.
    assert '&vertex_shader, fragment_shader_ = RSXFragmentProgram::clone(fragment_shader), key]' in now_parts[1]
    template = (NATIVE / 'rpcs3_inline559.inc').read_text()
    shared, per = template.split('// PER_NAMESPACE', 1)
    per = per.split('\n', 1)[1]
    def namespace(name, items):
        text = per
        for marker, value in zip(('@KEY_TYPES@', '@LOOKUP@', '@BUILD_PIPELINE@'), items):
            assert marker in text
            text = text.replace(marker, value)
        return 'namespace ' + name + ' {\n' + text + '\n}\n'
    code = ('#define RPCS3_IOS 1\n#include <atomic>\n#include <condition_variable>\n#include <cstdio>\n#include <cstdlib>\n'
            '#include <functional>\n#include <memory>\n#include <mutex>\n#include <shared_mutex>\n#include <source_location>\n'
            '#include <string_view>\n#include <thread>\n#include <tuple>\n#include <unordered_map>\n#include <unordered_set>\n#include <vector>\n'
            '#include "util/types.hpp"\n#include "util/fnv_hash.hpp"\n#include "Emu/RSX/Program/RSXVertexProgram.h"\n'
            '#include "Emu/RSX/Program/RSXFragmentProgram.h"\n#include "ios/IOSShaderTiming.h"\n#include "ios/IOSCompilePressure.h"\n'
            'namespace utils { u64 _get_main_tid() { return 0; } }\n'
            'namespace fmt { [[noreturn]] void raw_range_error(std::source_location, std::string_view, std::size_t) { std::abort(); }\n'
            '[[noreturn]] void raw_range_error(std::source_location, std::size_t, std::size_t) { std::abort(); }\n'
            '[[noreturn]] void raw_verify_error(std::source_location, const char8_t*, std::size_t) { std::abort(); } }\n'
            'namespace rsx { struct program_cache_hint_t {}; }\n' + shared +
            namespace('before', old_parts) + namespace('after', now_parts) + (NATIVE / 'rpcs3_inline559_main.inc').read_text())
    report, digest = build_and_run(work, 'inline559', code, source, sanitizer)
    return dict(report, harnessSHA256=digest)


def full_overwrite(source, before, work, sanitizer):
    """E: read-backs and reloads are skipped only for proven whole overwrites."""
    now, old = (source / TEXTURES).read_text(), (before / TEXTURES).read_text()
    anchor = 'if (tex.is_flushable())\n\t\t\t\t{\n\t\t\t\t\t// Write if and only if'
    new_block, old_block = braced(now, anchor), braced(old, anchor)
    assert without_ios_blocks(new_block) == without_ios_blocks(old_block)
    assert without_ios_blocks(now) == without_ios_blocks(old), 'texture_cache.h changed outside its iOS blocks'
    # The overwrite range is set only around the one strict-bounds invalidation of a new DMA destination.
    assert now.count('cause_uses_strict_data_bounds') == 1
    assert now.count('rpcs3::ios::full_overwrite::RangeScope') == 1
    scope = now.index('rpcs3::ios::full_overwrite::RangeScope')
    assert now.index('blit_engine_internals::create_blit_dst(', scope) - scope < 900
    assert 'use_null_region && rpcs3::ios::full_overwrite::dma_copy_writes_whole_payload(' in now
    # The render-target reload is skipped only when the helper proves a whole replacement.
    rt = braced(now, 'if (!dest_section || !dest_section->is_locked())')
    assert 'blit_replaces_whole_surface(' in rt and 'dst_is_depth_surface || dst_subres.is_depth, typeless_info.dst_is_typeless' in rt
    assert without_ios_blocks(rt) == without_ios_blocks(braced(old, 'if (!dest_section || !dest_section->is_locked())'))
    code = (NATIVE / 'rpcs3_overwrite559.inc').read_text()
    code = code.replace('@BEFORE_FLUSHABLE@', old_block).replace('@AFTER_FLUSHABLE@', new_block)
    report, digest = build_and_run(work, 'overwrite559', '#define RPCS3_IOS 1\n' + code, source, sanitizer)
    return dict(report, harnessSHA256=digest, productionHeaderSHA256=normalized_sha(source / OVERWRITE))


def texture_epoch(source, before, work, sanitizer):
    """Texture validation per FIFO batch: a confirmed hash lasts until the next synchronization point."""
    now, old = (source / CACHE_CPP).read_text(), (before / CACHE_CPP).read_text()
    heads = {'IS_LOCKED': 'bool buffered_section::is_locked(bool actual_page_flags) const',
             'PROTECT': 'void buffered_section::protect(utils::protection new_prot, bool force)',
             'SYNC': 'bool buffered_section::sync() const', 'DISCARD': 'void buffered_section::discard()'}
    for head in heads.values():
        assert without_ios_blocks(braced(now, head)) == without_ios_blocks(braced(old, head)), head
    assert without_ios_blocks(now) == without_ios_blocks(old), 'texture_cache.cpp changed outside its iOS blocks'
    fifo = (source / FIFO).read_text()
    read_put = braced(fifo, 'template <bool Full>\n\t\tinline u32 FIFO_control::read_put() const')
    assert without_ios_blocks(fifo) == without_ios_blocks((before / FIFO).read_text())
    # Every synchronization point, and nothing else, advances the epoch.
    sites = {FIFO: 1, 'rpcs3/Emu/RSX/NV47/HW/nv406e.cpp': 2, TEXTURES: 3}
    for path, count in sites.items():
        assert (source / path).read_text().count('texture_validation::advance_epoch()') == count, path
    texture = (source / TEXTURES).read_text()
    for anchor in ('void flush_set(commandbuffer_type& cmd, thrashed_set& data', 'virtual void on_frame_end()'):
        a = texture.index(anchor)
        assert texture.index('advance_epoch()', a) - a < 400, anchor
    assert "if (!cause.is_read())\n\t\t\t{\n\t\t\t\trpcs3::ios::texture_validation::advance_epoch();" in texture
    policy = (source / 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp').read_text()
    assert 'resolve_mode(g_cfg.ios_experimental.texture_validation_epoch,\n\t\tis_god_of_war_iii_title(Emu.GetTitleID()));' in policy
    assert 'texture_validation::epoch_enabled.store(resolved.texture_validation_epoch' in policy
    gow3 = re.search(r'is_god_of_war_iii_title\(std::string_view title_id\) noexcept\s*\{\s*return ([^;]+);',
                     (source / 'rpcs3/ios/IOSMemoryPressurePolicy.h').read_text()).group(1)
    assert sorted(re.findall(r'"([A-Z0-9]{9})"', gow3)) == sorted(['BCES00510', 'BCES00799', 'BCUS98111', 'BCJS37001', 'BCAS25003', 'BCKS15003'])
    assert 'texture_validation_epoch{ this, "Texture Validation Per FIFO Batch", ios_experimental_mode::automatic }' in (source / 'rpcs3/Emu/system_config.h').read_text()
    assert 'SETTING("experimental.texture_validation_epoch"' in (source / 'rpcs3/ios/RPCS3IOSSettings.cpp').read_text()
    code = (NATIVE / 'rpcs3_epoch559.inc').read_text()
    for name, head in heads.items():
        for side, text in (('BEFORE', old), ('AFTER', now)):
            marker = '@' + side + '_' + name + '@'
            assert marker in code
            code = code.replace(marker, braced(text, head))
    code = code.replace('@AFTER_READ_PUT@', read_put)
    report, digest = build_and_run(work, 'epoch559', '#define RPCS3_IOS 1\n' + code, source, sanitizer)
    return dict(report, harnessSHA256=digest)


def export_contract(source):
    performance = (source / PERFORMANCE).read_text()
    for marker in ('COREPROF OPT559', 'dirty_hash_releases=%llu', 'dma_flush_skips=%llu', 'rt_reload_skips=%llu',
                   'texture_epoch=%u', 'epoch_skips=%llu', 'epoch_advances=%llu',
                   'bytes_scope=section_ranges_not_transfers'):
        assert marker in performance, marker
    return {'line': 'COREPROF OPT559', 'oneLinePerWindow': True}


def spu_pass_benchmark(source, work):
    """A: host LLVM cost of the per-hit construction that 559 removes."""
    config = os.environ.get('LLVM_CONFIG')
    if not config:
        return {'skipped': 'LLVM_CONFIG not set'}
    text = (source / SPU).read_text()
    a = text.index('LoopAnalysisManager lam;')
    region = text[a:text.index('fpm.addPass(ADCEPass());', a) + len('fpm.addPass(ADCEPass());')]
    code = (NATIVE / 'rpcs3_spupasses559.inc').read_text().replace('@PASS_SETUP@', region)
    cxxflags = shlex.split(subprocess.check_output([config, '--cxxflags'], text=True))
    cxxflags = [f for f in cxxflags if not f.startswith('-std=') and f not in ('-fno-exceptions',)]
    ldflags = shlex.split(subprocess.check_output([config, '--ldflags', '--libs', 'passes'], text=True))
    ldflags += shlex.split(subprocess.check_output([config, '--system-libs'], text=True))
    ldflags.append('-Wl,-rpath,' + subprocess.check_output([config, '--libdir'], text=True).strip())
    cpp = work / 'spupasses559.cpp'
    cpp.write_text(code)
    binary = work / 'spupasses559'
    subprocess.run(compilers() + ['-std=c++20', '-O2', *cxxflags, str(cpp), '-o', str(binary), *ldflags], check=True)
    run = subprocess.run([str(binary)], text=True, capture_output=True, timeout=600, check=True)
    report = json.loads(run.stdout)
    assert report['passed'] is True
    return dict(report, harnessSHA256=sha(code.encode()), host=platform.machine())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--benchmark', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='rpcs3-cell559-') as td:
        work = Path(td)
        before, contract = authenticated_baseline(source, work)
        report = dict(passed=True, result='passed', build=559, hostSystem=platform.system(),
                      hostMachine=platform.machine(), compiler=subprocess.check_output(compilers() + ['--version'], text=True).splitlines()[0],
                      sourceContract=contract, spuCacheHit=spu_cache_hit(source, before),
                      codegenIdentity=codegen_identity(source, work), exportLine=export_contract(source),
                      dirtyHash={}, vertexCompare={}, inlineCallback={}, fullOverwrite={}, textureEpoch={})
        for mode, sanitizer in SANITIZERS:
            report['dirtyHash'][mode] = dirty_hash(source, before, work, sanitizer)
            report['vertexCompare'][mode] = vertex_compare(source, before, work, sanitizer)
            report['inlineCallback'][mode] = inline_callback(source, before, work, sanitizer)
            report['fullOverwrite'][mode] = full_overwrite(source, before, work, sanitizer)
            report['textureEpoch'][mode] = texture_epoch(source, before, work, sanitizer)
        if args.benchmark:
            report['vertexCompareBenchmark'] = vertex_compare(source, before, work, '', benchmark=True)
            report['spuPassSetupBenchmark'] = spu_pass_benchmark(source, work)
    report['inputs'] = {path: sha((ROOT / path).read_bytes()) for path in INPUTS}
    report.update(physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Host correctness of the 559 production bodies against their exact 555 preimages, '
                        'sanitizers and host CPU measurements; no iPhone FPS, frame time, Metal rendering, '
                        'thermal, SPU stall or memory-pressure result.')
    output = json.dumps(report, indent=2) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(output)
    print(output, end='')


if __name__ == '__main__':
    main()
