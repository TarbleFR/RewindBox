#!/usr/bin/env python3
"""Builds the REWINDBOX_TEXTURE_LOOKUP_MEMO_660 host harness from a tree (used by texture_lookup_memo660_test.py).

The tree's rpcs3/Emu/RSX headers are copied to a temporary include root with a few explicit seams
(renderer, configuration and tile lookups replaced by host functions; each pattern's count is checked),
and real function bodies are extracted from the tree's .cpp files by brace matching."""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
NATIVE = HERE / 'native'
VULKAN_INCLUDE = Path(__file__).resolve().parents[1] / 'packages/libretro_internal_bridge/ios/ThirdParty/include'

TEX = 'rpcs3/Emu/RSX/Common/texture_cache.h'
HELPERS = 'rpcs3/Emu/RSX/Common/texture_cache_helpers.h'
CPP = 'rpcs3/Emu/RSX/Common/texture_cache.cpp'
UTILS_CPP = 'rpcs3/Emu/RSX/Common/TextureUtils.cpp'
RSXTEX = 'rpcs3/Emu/RSX/RSXTexture.cpp'
VKH = 'rpcs3/Emu/RSX/VK/VKTextureCache.h'
VKCPP = 'rpcs3/Emu/RSX/VK/VKTextureCache.cpp'

# (file, pattern, replacement, expected count)
SEAMS = [
    (TEX, 'rsx::get_current_renderer()->get_tiled_memory_region(', '::host_seam::tiled_memory_region(', 2),
    (TEX, 'rsx::get_current_renderer()->is_current_thread()', '::host_seam::is_rsx_thread()', 2),
    (TEX, 'rsx::get_current_renderer()->ROP_sync_timestamp', '::host_seam::rop_sync_timestamp()', 1),
    (TEX, 'g_cfg.video.', '::host_seam::video.', 15),
    (HELPERS, 'rsx::get_current_renderer()->resolution_scaling_config', '::host_seam::scaling_config()', 2),
    (HELPERS, 'g_cfg.video.', '::host_seam::video.', 3),
    # Pre-existing UB that UBSan reports in both trees: the range iterator's pre-increment binds a reference to
    # *nullptr at the end (revalidate_overlapping discards it). The copy returns the iterator instead.
    ('rpcs3/Emu/RSX/Common/texture_cache_utils.h', 'inline reference operator++() { next(); return *obj; }',
     'inline range_iterator_tmpl& operator++() { next(); return *this; }', 1),
]


class Fail(SystemExit):
    pass


def require(condition, message):
    if not condition:
        raise Fail('FAIL: ' + message)


def text(tree: Path, name: str) -> str:
    return (tree / name).read_text(encoding='utf-8').replace('\r\n', '\n')


def braced_from(source: str, first: int) -> int:
    depth = 0
    for index in range(source.index('{', first), len(source)):
        depth += {'{': 1, '}': -1}.get(source[index], 0)
        if depth == 0:
            return index + 1
    raise Fail('FAIL: unbalanced block')


def block(source: str, start: str) -> str:
    require(source.count(start) == 1, 'not exactly one ' + repr(start.strip()[:100]))
    first = source.index(start)
    return source[first:braced_from(source, first)]


def body(source: str, start: str) -> str:
    """The braced body that follows a unique signature."""
    code = block(source, start)
    return code[code.index('{'):]


def seamed_include_root(tree: Path, root: Path) -> dict:
    """Copy the headers of rpcs3/ to root (it replaces -I rpcs3) and apply the seams."""
    source = tree / 'rpcs3'
    target = root
    for path in source.rglob('*'):
        if path.is_file() and path.suffix in ('.h', '.hpp', '.inl'):
            destination = target / path.relative_to(source)
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, destination)
    counts = {}
    for name, pattern, replacement, expected in SEAMS:
        path = root / name.replace('rpcs3/', '', 1)
        content = path.read_text(encoding='utf-8')
        count = content.count(pattern)
        require(count == expected, f'seam {pattern!r} in {name}: {count} occurrences, expected {expected}')
        path.write_text(content.replace(pattern, replacement), encoding='utf-8')
        counts[pattern] = count
    return counts


TEXTURE_ACCESSORS = {
    'fragment_texture': ['offset', 'location', 'cubemap', 'border_type', 'dimension', 'get_extended_texture_dimension', 'format',
                         'is_compressed_format', 'mipmap', 'get_exact_mipmap_count', 'wrap_s', 'wrap_t', 'wrap_r', 'enabled',
                         'remap', 'decoded_remap', 'width', 'height', 'depth', 'pitch'],
    'vertex_texture': ['offset', 'location', 'cubemap', 'border_type', 'dimension', 'get_extended_texture_dimension', 'format',
                       'mipmap', 'get_exact_mipmap_count', 'wrap_s', 'wrap_t', 'wrap_r', 'enabled', 'remap', 'decoded_remap',
                       'width', 'height', 'depth', 'pitch'],
}


def texture_methods(rsxtex: str, candidate: bool) -> str:
    parts = []
    for cls, names in TEXTURE_ACCESSORS.items():
        for name in names + (['lookup_words'] if candidate else []):
            matches = list(re.finditer(r'\n\t([^\n;{}]*?)\b' + cls + '::' + name + r'\(\) const\n\t\{', rsxtex))
            require(len(matches) == 1, f'{cls}::{name} definitions: {len(matches)}')
            first = matches[0].start() + 1
            parts.append(rsxtex[first:braced_from(rsxtex, first)])
    return '\n'.join(parts)


TEXTURE_UTILS = [
    '\tu8 get_format_block_size_in_bytes(int format)\n',
    '\tu8 get_format_block_size_in_texel(int format)\n',
    '\tu32 get_format_packed_pitch(u32 format, u16 width, bool border, bool swizzled)\n',
    '\tstatic usz get_texture_size(u32 format, u16 width, u16 height, u16 depth, u32 pitch, u16 mipmaps, u16 layers, u8 border)\n',
    '\tusz get_texture_size_with_mipmaps(const RSXTexture auto& texture, u16 mipmaps)\n',
    '\tusz get_texture_size_impl(const RSXTexture auto& texture, u8 mip_level)\n',
    '\tusz get_texture_size(const rsx::fragment_texture& texture, u8 mip_level)\n',
    '\tusz get_texture_size(const rsx::vertex_texture& texture, u8 mip_level)\n',
    '\trsx::format_class classify_format(rsx::surface_depth_format2 format)\n',
    '\trsx::format_class classify_format(u32 gcm_format)\n',
    '\tstd::pair<u32, bool> get_compatible_gcm_format(rsx::surface_color_format format)\n',
    '\tstd::pair<u32, bool> get_compatible_gcm_format(rsx::surface_depth_format2 format)\n',
]


def texture_utils(utils: str) -> str:
    parts = []
    for signature in TEXTURE_UTILS:
        parts.append(block(utils, signature))
    # get_texture_size(u32 ...) uses this helper; take it from the file wherever it is defined.
    match = re.search(r'\n\t((?:static )?(?:constexpr )?u8 get_format_texel_rows_per_line\(u32 [a-z_]+\))\n\t\{', utils)
    require(match is not None, 'get_format_texel_rows_per_line')
    parts.insert(0, block(utils, '\t' + match.group(1) + '\n'))
    return '\n'.join(parts)


def invalidation_cause_code(tree: Path) -> str:
    source = text(tree, 'rpcs3/Emu/RSX/Common/texture_cache_types.cpp')
    code = block(source, '\tvoid invalidation_cause::flag_bits_from_cause(enum_type cause)\n')
    require(code.count('g_cfg.video.') == 1, 'invalidation cause configuration seam')
    return code.replace('g_cfg.video.', '::host_seam::video.')


def buffered_section_methods(cpp: str) -> str:
    first = cpp.index('\tvoid buffered_section::init_lockable_range(const address_range32& range)\n')
    last_start = cpp.index('\tbool buffered_section::sync() const\n')
    return cpp[first:braced_from(cpp, last_start)]


def vk_section(vkh: str) -> tuple[str, str]:
    create = block(vkh, '\t\tvoid create(u16 w, u16 h, u16 depth, u16 mipmaps, vk::image* image, u32 rsx_pitch, bool managed, u32 gcm_format, bool pack_swap_bytes = false)\n')
    destroy = block(vkh, '\t\tvoid destroy()\n\t\t{\n\t\t\tif (!exists() && context != rsx::texture_upload_context::dma)\n')
    pitch = block(vkh, '\t\tvoid set_rsx_pitch(u32 pitch)\n')
    rt = block(vkh, '\t\tvoid create(u16 w, u16 h, u16 depth, u16 mipmaps, vk::image* image, u32 rsx_pitch, bool managed, const vk::render_target* surface)\n')
    return '\n'.join([create, destroy, pitch]), rt


TEST_ACCESS = '''
		template <typename F> void for_each_section(F&& f) { for (auto& block : m_storage) for (auto& s : block) f(s); }
		void test_revalidate(const utils::address_range32& range) { std::lock_guard lock(m_cache_mutex); revalidate_overlapping(range); }
		void test_set_component_order(section& s, rsx::component_order order) { std::lock_guard lock(m_cache_mutex); set_component_order(s, s.get_gcm_format(), order); }
'''


def vk_cache(vkcpp: str) -> tuple[str, str]:
    create = body(vkcpp, '\tcached_texture_section* texture_cache::create_new_texture(vk::command_buffer& cmd, const utils::address_range32& rsx_range, u16 width, u16 height, u16 depth, u16 mipmaps, u32 pitch,\n')
    order = body(vkcpp, '\tvoid texture_cache::set_component_order(cached_texture_section& section, u32 gcm_format, rsx::component_order expected_flags)\n')
    return create, order


def driver_code() -> str:
    driver = (NATIVE / 'rpcs3_texture_lookup_memo660_driver.cpp.in').read_text(encoding='utf-8')
    scenarios = (NATIVE / 'rpcs3_texture_lookup_memo660_scenarios.cpp.in').read_text(encoding='utf-8')
    require(driver.count('//@@SCENARIOS@@') == 1, 'driver marker')
    return driver.replace('//@@SCENARIOS@@', scenarios)


def render(tree: Path, candidate: bool, driver: str | None = None, compat: str = '', test_access: str = TEST_ACCESS) -> str:
    template = (NATIVE / 'rpcs3_texture_lookup_memo660_harness.cpp.in').read_text(encoding='utf-8')
    driver = driver_code() if driver is None else driver
    create, order = vk_cache(text(tree, VKCPP))
    section_code, section_rt = vk_section(text(tree, VKH))
    extracted = '\n'.join([
        'namespace rsx\n{',
        '// texture_cache.cpp: buffered_section',
        buffered_section_methods(text(tree, CPP)),
        '// RSXTexture.cpp: the accessors a lookup uses',
        texture_methods(text(tree, RSXTEX), candidate),
        '// TextureUtils.cpp: texture sizes and format classes',
        texture_utils(text(tree, UTILS_CPP)),
        '// texture_cache_types.cpp',
        invalidation_cause_code(tree),
        '}',
    ])
    code = template
    for marker, value in (('//@@COMPAT@@', compat), ('//@@VK_SECTION@@', section_code), ('//@@VK_SECTION_RT@@', section_rt),
                          ('//@@VK_CREATE_NEW_TEXTURE@@', create), ('//@@VK_SET_COMPONENT_ORDER@@', order),
                          ('//@@TEST_ACCESS@@', test_access), ('//@@EXTRACTED@@', extracted), ('//@@DRIVER@@', driver)):
        require(code.count(marker) == 1, 'harness marker ' + marker)
        code = code.replace(marker, value)
    return code


def mutate(include_root: Path, mutations: list) -> None:
    """Negative controls: (published path under rpcs3/, pattern, replacement) applied once each."""
    for name, pattern, replacement in mutations:
        path = include_root / name.replace('rpcs3/', '', 1)
        content = path.read_text(encoding='utf-8')
        require(content.count(pattern) == 1, f'mutation pattern in {name}: {pattern[:80]!r}')
        path.write_text(content.replace(pattern, replacement), encoding='utf-8')


def compile_harness(tree: Path, work: Path, name: str, code: str, defines: dict, cxx: str = 'g++', sanitize: bool = True,
                    mutations: list | None = None) -> Path:
    include_root = work / (name + '-include')
    if include_root.exists():
        shutil.rmtree(include_root)
    seams = seamed_include_root(tree, include_root)
    mutate(include_root, mutations or [])
    source = work / (name + '.cpp')
    source.write_text(''.join(f'#define {k} {v}\n' for k, v in defines.items()) + code, encoding='utf-8')
    binary = work / name
    flags = ['-std=gnu++20', '-O1', '-g', '-fno-omit-frame-pointer', '-Wall', '-Wno-unused-function', '-Wno-unused-variable',
             '-Wno-unused-but-set-variable', '-Wno-deprecated-declarations', '-Wno-missing-field-initializers', '-Wno-attributes']
    if sanitize:
        # vptr checks need the RTTI of rsx::thread, which only RSXThread.cpp emits; every other UBSan check stays.
        flags += ['-fsanitize=address,undefined', '-fno-sanitize=vptr', '-fno-sanitize-recover=all']
    command = [cxx, *flags, '-I', str(include_root), '-I', str(tree), '-I', str(tree / '3rdparty'),
               '-I', str(VULKAN_INCLUDE),
               # Last: resolves the headers' "../Utilities/..." includes when the tree has no 3rdparty/ (the Core 660
               # driver copies trees without it); every rpcs3/ header is found first in the seamed root.
               '-I', str(tree / 'rpcs3'), str(source), '-o', str(binary), '-pthread']
    built = subprocess.run(command, capture_output=True, text=True)
    if built.returncode:
        (work / (name + '.log')).write_text(built.stderr)
        errors = [line for line in built.stderr.splitlines() if 'error' in line]
        raise Fail(f'FAIL: {name} does not build ({len(errors)} error lines); first errors:\n' + '\n'.join(errors[:40]))
    return binary
