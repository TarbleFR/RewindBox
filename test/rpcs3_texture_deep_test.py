#!/usr/bin/env python3
"""Run extracted Vulkan texture identity, native-view and copy-input methods.

Vulkan handles/driver calls are host boundaries. This verifies cache ownership,
view selection and CPU bookkeeping, not GPU execution or iPhone gameplay.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import subprocess
import tempfile

from rpcs3_texture_address_index_test import braced
from rpcs3_texture_exact_index_test import stripped
from rpcs3_texture_barrier_test import harness as barrier_harness

ROOT = Path(__file__).resolve().parents[1]
VK = 'rpcs3/Emu/RSX/VK/'
CPP = VK + 'VKTextureCache.cpp'
HDR = VK + 'VKTextureCache.h'
INPUTS = [CPP, HDR, VK + 'vkutils/image.cpp', VK + 'vkutils/image_helpers.cpp',
          VK + 'VKFormats.cpp', 'rpcs3/Emu/RSX/Utils/color_utils.hpp',
          'rpcs3/Emu/RSX/gcm_enums.h', 'rpcs3/Emu/RSX/Common/TextureUtils.h',
          'rpcs3/Emu/RSX/Common/TextureUtils.cpp',
          'rpcs3/Emu/RSX/Common/texture_cache_types.h',
          'rpcs3/Emu/RSX/Common/simple_array.hpp']
ADAPTER = ROOT / 'test/native/rpcs3_texture_deep.inc'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def source_parts(root):
    cpp, hdr = (root / CPP).read_text(), (root / HDR).read_text()
    copy = braced(cpp, 'void texture_cache::copy_transfer_regions_impl(')
    declarations = copy[copy.index('\n', copy.index('const auto dst_bpp')):copy.index('\n\t\t// Generates a region')]
    loop = braced(copy, 'for (const auto& section : sections_to_transfer)')
    predicate = '!processed_input_images.contains(section.src)' if 'contains(section.src)' in loop else 'first_use(section.src)'
    first_use = braced(loop, 'if (' + predicate + ')')
    # Every copy/cast/scale body and both subresource helpers are identical,
    # allowing only indentation for the generic lambda's two instantiations.
    normalize = lambda text: '\n'.join(line.strip() for line in text.splitlines() if line.strip())
    unchanged_copy = normalize(loop[loop.index('auto src_image = section.src;'):loop.rfind('}')])
    unchanged_copy += normalize(braced(copy, 'const auto get_output_region ='))
    unchanged_copy += normalize(braced(copy, 'const auto configure_subresource ='))
    if 'const auto transfer_regions =' in copy:
        generic = braced(copy, 'const auto transfer_regions =')
        body = generic[generic.index('{')+1:generic.index('for (const auto& section')]
        epilogue = generic[generic.index('// Pop unique image layouts here'):generic.rfind('}')]
        dispatch = copy[copy.index('if (sections_to_transfer.size() <= 8)'):copy.rfind('}')]
        bookkeeping = declarations + '\nconst auto transfer_regions = [&]<bool use_inline_inputs>() {\n' + body + '\n for (const auto& section : sections_to_transfer) {if (!section.src) continue;\n' + first_use + '\nsection.src->copy(cmd);\n}\n' + epilogue + '\n};\n' + dispatch
    else:
        epilogue = copy[copy.index('// Pop unique image layouts here'):copy.rfind('\n\t}')]
        bookkeeping = declarations + '\n for (const auto& section : sections_to_transfer) {if (!section.src) continue;\n' + first_use + '\nsection.src->copy(cmd);\n}\n' + epilogue
    create = braced(cpp, 'cached_texture_section* texture_cache::create_new_texture(')
    native_line = next(line.strip() for line in create.splitlines() if 'apply_component_mapping_flags(' in line)
    return dict(cpp=cpp, hdr=hdr, copy=copy, unchanged_copy=unchanged_copy,
                bookkeeping=bookkeeping,
                native_line=native_line,
                pool=braced(cpp, 'std::unique_ptr<vk::viewable_image> texture_cache::find_cached_image('),
                depth=braced(hdr, 'void create(u16 w, u16 h, u16 depth, u16 mipmaps, vk::image* image, u32 rsx_pitch, bool managed, const vk::render_target* surface)'))


def harness(source, baseline):
    before, after = source_parts(baseline), source_parts(source)
    for path in INPUTS[2:]:
        if path == VK + 'vkutils/image_helpers.cpp':
            # Its independent barrier test permits exactly four added vertex
            # stage masks; the remapping helper extracted here stays identical.
            barrier_harness(source, baseline)
            assert braced((source / path).read_text(), 'VkComponentMapping apply_swizzle_remap(') == braced((baseline / path).read_text(), 'VkComponentMapping apply_swizzle_remap(')
            continue
        assert sha(source / path) == sha(baseline / path), path
    assert before['unchanged_copy'] == after['unchanged_copy']
    for signature in ['vk::image_view* texture_cache::generate_cubemap_from_images(',
                      'vk::image_view* texture_cache::generate_3d_from_2d_images(']:
        old_gather, new_gather = braced(before['cpp'], signature), braced(after['cpp'], signature)
        clear = '\t\t\tVkClearColorValue clear = {};\n\t\t\tvkCmdClearColorImage(cmd, image->value, image->current_layout, &clear, 1, &dst_range);'
        guarded = '\t\t\tif (!copy_transfer_regions_fully_cover_image(image, sections_to_copy))\n\t\t\t{\n' + '\n'.join('\t' + line for line in clear.splitlines()) + '\n\t\t\t}'
        assert old_gather.replace(clear, guarded) == new_gather
    assert before['depth'].replace('gcm_format = (surface->get_surface_depth_format() != rsx::surface_depth_format::z16) ? CELL_GCM_TEXTURE_DEPTH16 : CELL_GCM_TEXTURE_DEPTH24_D8;\n\t\t\t\tswap_bytes = true;',
        'const auto info = get_compatible_gcm_format(surface->get_surface_depth_format());\n\t\t\t\tgcm_format = info.first;\n\t\t\t\tswap_bytes = info.second;') == after['depth']
    assert before['native_line'] == 'image->native_component_map = apply_component_mapping_flags(gcm_format, swizzle_flags, rsx::default_remap_vector);'
    assert after['native_line'] == 'image->set_native_component_layout(apply_component_mapping_flags(gcm_format, swizzle_flags, rsx::default_remap_vector));'
    assert 'usage_flags, VK_SHARING_MODE_EXCLUSIVE, format_class)' in after['cpp']
    assert 'usage_flags, sharing_mode, rsx::classify_format(gcm_format))' in after['cpp']
    # Existing lookup ownership/accounting and pool retirement stay intact.
    for signature in ['void texture_cache::dispose_reusable_image(', 'void texture_cache::release_temporary_subresource(',
                      'texture_cache::cached_image_reference_t::~cached_image_reference_t()',
                      'void texture_cache::on_frame_end()', 'bool texture_cache::handle_memory_pressure(']:
        assert braced(after['cpp'], signature) == braced(before['cpp'], signature)
    color = (source / 'rpcs3/Emu/RSX/Utils/color_utils.hpp').read_text()
    remap_start = color.index('struct texture_channel_remap_t')
    remap_fields = color[remap_start:color.index('\n\t\ttemplate <typename T>', remap_start)]
    remap = remap_fields + '\n template<typename T>\n' + braced(color, 'std::array<T, 4> remap(') + '\n};\n'
    enums = (source / 'rpcs3/Emu/RSX/gcm_enums.h').read_text()
    attrs = (source / 'rpcs3/Emu/RSX/Common/TextureUtils.h').read_text()
    formats = (source / (VK + 'VKFormats.cpp')).read_text()
    image = (source / (VK + 'vkutils/image.cpp')).read_text()
    code = ADAPTER.read_text()
    replacements = {
        '@GCM_ENUM@': braced(enums, 'enum CellGcmTexture : u32') + ';',
        '@DEPTH_CONSTANTS@': 'enum : u32 {\n' + '\n'.join(line for line in enums.splitlines() if line.strip().startswith(('CELL_GCM_SURFACE_Z16 =', 'CELL_GCM_SURFACE_Z24S8 ='))) + '\n};',
        '@DEPTH_ENUM@': braced(enums, 'enum class surface_depth_format : u8') + ';\n' + braced(enums, 'enum class surface_depth_format2 : u8') + ';\n' + braced(enums, 'constexpr bool operator ==(surface_depth_format2'),
        '@CLASS_ENUM@': braced(attrs, 'enum format_class : u8') + ';',
        '@ORDER_ENUM@': braced((source / 'rpcs3/Emu/RSX/Common/texture_cache_types.h').read_text(), 'enum class component_order') + ';',
        '@REMAP@': remap + '\n#pragma GCC diagnostic push\n#pragma GCC diagnostic ignored "-Wmissing-field-initializers"\n' + braced(color, 'static inline texture_channel_remap_t decode_remap_encoding(') + '\n#pragma GCC diagnostic pop\n',
        '@GET_VIEW@': braced(image, 'image_view* viewable_image::get_view('),
        '@AS@': braced(image, 'image_view* image_view::as('),
        '@SET_LAYOUT@': braced(image, 'void viewable_image::set_native_component_layout('),
        '@COMPONENTS@': braced(formats, 'std::array<VkComponentSwizzle, 4> get_component_mapping('),
        '@APPLY_REMAP@': braced((source / (VK + 'vkutils/image_helpers.cpp')).read_text(), 'VkComponentMapping apply_swizzle_remap('),
        '@APPLY_FLAGS@': braced(after['cpp'], 'VkComponentMapping texture_cache::apply_component_mapping_flags(').replace('texture_cache::', '').replace(') const', ')'),
        '@HASH@': braced(after['cpp'], 'u64 hash_image_properties('),
        '@FULL_COVERAGE@': braced(after['cpp'], 'bool texture_cache::copy_transfer_regions_fully_cover_image(').replace('texture_cache::', '').replace(') const', ')'),
        '@CLASSIFY@': braced((source / 'rpcs3/Emu/RSX/Common/TextureUtils.cpp').read_text(), 'rsx::format_class classify_format(u32 gcm_format)'),
        '@DEPTH_COMPATIBLE@': braced((source / 'rpcs3/Emu/RSX/Common/TextureUtils.cpp').read_text(), 'std::pair<u32, bool> get_compatible_gcm_format(rsx::surface_depth_format2 format)'),
        '@ARRAY@': '#define RPCS3_IOS\n' + stripped(source / 'rpcs3/Emu/RSX/Common/simple_array.hpp') + '\n#undef RPCS3_IOS',
    }
    for variant, parts in [('before', before), ('after', after)]:
        replacements['@' + variant.upper() + '_NATIVE@'] = parts['native_line']
        replacements['@' + variant.upper() + '_DEPTH@'] = parts['depth']
        replacements['@' + variant.upper() + '_POOL@'] = parts['pool'].replace('texture_cache::', variant + '_pool::')
        replacements['@' + variant.upper() + '_POOL_DECL@'] = parts['pool'].split('{', 1)[0].replace('texture_cache::', '').strip() + ';'
        replacements['@' + variant.upper() + '_COPY@'] = ('[[gnu::noinline]] void ' + variant + '_copy(command_buffer& cmd, const std::vector<copy_region_descriptor>& sections_to_transfer) {\n' + parts['bookkeeping'] + '\n}\n')
        replacements['@' + variant.upper() + '_STORAGE@'] = braced(parts['cpp'], 'std::unique_ptr<vk::viewable_image> texture_cache::create_temporary_subresource_storage(').replace('texture_cache::', '')
    for marker, value in replacements.items():
        code = code.replace(marker, value)
    assert '@' not in code
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=['address,undefined'])
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    code = harness(source, baseline)
    inputs = {p: sha(source / p) for p in INPUTS}
    flags = ['-std=c++20', '-Wall', '-Wextra', '-Werror', '-UNDEBUG', '-g']
    flags += ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer'] if args.sanitizer else ['-O3']
    if args.sanitizer and platform.system() == 'Linux':
        flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    compiler = shlex.split(args.compiler)
    with tempfile.TemporaryDirectory(prefix='rpcs3-texture-deep-') as temp:
        cpp, exe = Path(temp) / 'test.cpp', Path(temp) / 'test'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
        symbols = subprocess.check_output(['nm', '-S', '--size-sort', '--demangle', str(exe)], text=True)
        code_sizes = [dict(symbol=line.split(None, 3)[3], bytes=int(line.split()[1], 16)) for line in symbols.splitlines()
                      if re.search(r'\bvk::(?:before|after)_copy\(', line)]
        run = subprocess.run([str(exe)], text=True, capture_output=True, timeout=180,
                             env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:
            raise RuntimeError(run.stdout + run.stderr)
    assert inputs == {p: sha(source / p) for p in INPUTS}
    report = dict(passed=True, sourceSHA256=inputs,
                  baselineSHA256={p: sha(baseline / p) for p in INPUTS},
                  harnessSHA256=hashlib.sha256(code.encode()).hexdigest(), adapterSHA256=sha(ADAPTER),
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, host=platform.machine(), sanitizer=args.sanitizer,
                  bookkeepingCodeSizes=code_sizes,
                  results=json.loads(run.stdout), physicalDeviceTested=False, gameplayMeasured=False,
                  leakSanitizerEnabled=False, scope=__doc__)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
