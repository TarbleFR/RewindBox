#!/usr/bin/env python3
"""Shader kit tests: portable core (any platform) and Metal runtime (macOS).

Builds packages/neo_shader_kit/tools with CMake (vendored glslang and
SPIRV-Cross, the core, the core tests and, on macOS, the Metal runtime
NeoSlangRenderer.mm with test/neo_shader_kit/slang_render_test.mm), writes the
render fixtures below (presets, slang sources, PNG lookup textures) into a
temporary directory and runs:

  * neoshader-core-tests: preset/source rules, reflection, MSL bindings;
  * neoshader-kit-tests FIXTURES (macOS): verified downloads through a fake
    network, shared files and removal, refusals, previews, favourites,
    profiles, storage report, catalog parsing;
  * neoshader-render-tests FIXTURES (macOS): every check renders through the
    application's program and chain code on the Metal device and reads the
    pixels back (orientation, nearest/linear and the smooth setting,
    semantics and parameters, aliases and scale types, history, feedback,
    LUTs with straight alpha, mipmap_input, wrap modes, sRGB framebuffers,
    failure codes).

On Linux only the core tests run; the render tests need macOS and a Metal
device (the CI's macOS runners have one). With --require-metal the absence
of either is a failure.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'packages/neo_shader_kit/tools'
NO_DEVICE = 3

TEMPLATE = '''#version 450
{pragmas}
{push}
layout(std140, set = 0, binding = 0) uniform UBO
{{
   mat4 MVP;
{ubo}
}} global;

#pragma stage vertex
layout(location = 0) in vec4 Position;
layout(location = 1) in vec2 TexCoord;
layout(location = 0) out vec2 vTexCoord;

void main()
{{
   gl_Position = global.MVP * Position;
   vTexCoord = TexCoord;
}}

#pragma stage fragment
layout(location = 0) in vec2 vTexCoord;
layout(location = 0) out vec4 FragColor;
{samplers}

void main()
{{
{body}
}}
'''


def slang(body, push=(), ubo=(), samplers=('Source',), pragmas=()):
    push_block = ''
    if push:
        members = '\n'.join(f'   {member};' for member in push)
        push_block = f'layout(push_constant) uniform Push\n{{\n{members}\n}} params;\n'
    sampler_lines = '\n'.join(f'layout(set = 0, binding = {index + 2}) uniform sampler2D {name};'
                              for index, name in enumerate(samplers))
    return TEMPLATE.format(pragmas='\n'.join(pragmas), push=push_block,
                           ubo='\n'.join(f'   {member};' for member in ubo), samplers=sampler_lines,
                           body='\n'.join(f'   {line}' for line in body.strip().splitlines()))


def png(width, height, rows):
    """Straight-alpha RGBA8 PNG (colour type 6), rows of (r, g, b, a)."""
    raw = b''.join(b'\x00' + b''.join(bytes(pixel) for pixel in row) for row in rows)

    def chunk(kind, data):
        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data) & 0xffffffff)

    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 6, 0, 0, 0)) +
            chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b''))


STOCK = slang('FragColor = texture(Source, vTexCoord);')

FIXTURES = {
    'stock.slang': STOCK,
    'stock.slangp': 'shaders = 1\nshader0 = stock.slang\nfilter_linear0 = false\n',
    'stock-smooth.slangp': 'shaders = 1\nshader0 = stock.slang\n',
    'semantics.slang': slang(
        '''
ivec2 p = ivec2(gl_FragCoord.xy);
int i = p.y * 4 + p.x;
vec4 v = vec4(vTexCoord, 0.0, 1.0);
if (i == 0) v = params.OutputSize;
else if (i == 1) v = params.SourceSize;
else if (i == 2) v = params.OriginalSize;
else if (i == 3) v = params.FinalViewportSize;
else if (i == 4) v = vec4(float(params.FrameCount), float(params.FrameDirection), float(params.Rotation), params.OriginalAspect);
else if (i == 5) v = vec4(global.OriginalAspectRotated, global.OriginalFPS, float(global.FrameTimeDelta), float(global.TotalSubFrames));
else if (i == 6) v = vec4(float(global.CurrentSubFrame), global.PARAM_A, global.PARAM_B, texture(Source, vec2(0.5)).a);
else if (i == 7) v = global.MVP[0];
else if (i == 8) v = global.MVP[1];
else if (i == 9) v = global.MVP[2];
else if (i == 10) v = global.MVP[3];
FragColor = v;
''',
        push=('vec4 OutputSize', 'vec4 SourceSize', 'vec4 OriginalSize', 'vec4 FinalViewportSize',
              'uint FrameCount', 'int FrameDirection', 'uint Rotation', 'float OriginalAspect'),
        ubo=('float OriginalAspectRotated', 'float OriginalFPS', 'uint FrameTimeDelta', 'uint TotalSubFrames',
             'uint CurrentSubFrame', 'float PARAM_A', 'float PARAM_B'),
        pragmas=('#pragma format R32G32B32A32_SFLOAT',
                 '#pragma parameter PARAM_A "Parameter A" 0.5 0.0 2.0 0.1',
                 '#pragma parameter PARAM_B "Parameter B" 1.0 0.0 1.0 0.05')),
    'semantics.slangp': ('shaders = 1\nshader0 = semantics.slang\nscale_type0 = absolute\nscale0 = 4\n'
                         'frame_count_mod0 = 7\nfilter_linear0 = false\nPARAM_A = 0.75\n'),
    'final3.slang': slang(
        '''
ivec2 p = ivec2(gl_FragCoord.xy);
if (p == ivec2(0, 0)) FragColor = vec4(params.FirstSize.xy, params.SourceSize.xy) / 255.0;
else if (p == ivec2(1, 0)) FragColor = vec4(params.OutputSize.xy, global.PassOutputSize0.xy) / 255.0;
else if (p == ivec2(2, 0)) FragColor = vec4(params.PassOutputSize1.xy, 0.0, 255.0) / 255.0;
else FragColor = texture(First, vTexCoord);
''',
        # FirstSize and PassOutputSize0 name the same semantic: RetroArch
        # accepts that only in different blocks (slang_reflection.cpp
        # set_ubo_texture_offset), so one is a push constant, one in the UBO.
        push=('vec4 SourceSize', 'vec4 OutputSize', 'vec4 FirstSize', 'vec4 PassOutputSize1'),
        ubo=('vec4 PassOutputSize0',),
        samplers=('Source', 'First')),
    'multipass.slangp': '''shaders = 3
shader0 = stock.slang
alias0 = First
scale_type0 = source
scale0 = 2.0
filter_linear0 = false
shader1 = stock.slang
scale_type_x1 = viewport
scale_x1 = 0.5
scale_type_y1 = absolute
scale_y1 = 5
filter_linear1 = false
shader2 = final3.slang
filter_linear2 = false
''',
    'history.slang': slang(
        'FragColor = vec4(texture(OriginalHistory1, vTexCoord).r, texture(OriginalHistory2, vTexCoord).g, '
        'texture(Original, vTexCoord).b, 1.0);',
        samplers=('OriginalHistory1', 'OriginalHistory2', 'Original')),
    'history.slangp': 'shaders = 1\nshader0 = history.slang\nfilter_linear0 = false\n',
    'accumulate.slang': slang(
        'FragColor = vec4(texture(PassFeedback0, vTexCoord).r + 1.0, texture(AccFeedback, vTexCoord).g + 2.0, 0.0, 1.0);',
        samplers=('PassFeedback0', 'AccFeedback'), pragmas=('#pragma format R32G32B32A32_SFLOAT',)),
    'final5.slang': slang('FragColor = vec4(texture(Source, vTexCoord).rg / 255.0, 0.0, 1.0);'),
    'feedback.slangp': '''shaders = 2
shader0 = accumulate.slang
alias0 = Acc
scale_type0 = source
scale0 = 1.0
filter_linear0 = false
shader1 = final5.slang
filter_linear1 = false
''',
    'lut.slang': slang(
        '''
ivec2 p = ivec2(gl_FragCoord.xy);
if (p == ivec2(3, 1)) FragColor = vec4(params.PaletteSize.xy, 0.0, 255.0) / 255.0;
else FragColor = texture(Palette, vTexCoord);
''',
        push=('vec4 PaletteSize',), samplers=('Palette',)),
    'lut.slangp': ('shaders = 1\nshader0 = lut.slang\nfilter_linear0 = false\ntextures = Palette\n'
                   'Palette = textures/palette.png\nPalette_linear = false\n'),
    'textures/palette.png': png(4, 2, [
        [(255, 0, 0, 255), (0, 255, 0, 255), (0, 0, 255, 255), (200, 100, 50, 128)],
        [(10, 20, 30, 255), (0, 0, 0, 0), (255, 255, 255, 255), (1, 2, 3, 255)],
    ]),
    'mipdown.slang': slang('FragColor = textureLod(Source, vec2(0.0625), 10.0);'),
    'mipmap.slangp': '''shaders = 2
shader0 = stock.slang
scale_type0 = source
scale0 = 1.0
filter_linear0 = false
shader1 = mipdown.slang
mipmap_input1 = true
filter_linear1 = true
wrap_mode1 = clamp_to_edge
''',
    'mipmap-border.slangp': '''shaders = 2
shader0 = stock.slang
scale_type0 = source
scale0 = 1.0
filter_linear0 = false
shader1 = mipdown.slang
mipmap_input1 = true
filter_linear1 = true
''',
    'wrap.slang': slang('FragColor = texture(Source, vTexCoord * 2.0 - 0.49);'),
    'wrap-border.slangp': 'shaders = 1\nshader0 = wrap.slang\nfilter_linear0 = false\n',
    'wrap-repeat.slangp': 'shaders = 1\nshader0 = wrap.slang\nfilter_linear0 = false\nwrap_mode0 = repeat\n',
    'constant.slang': slang('FragColor = vec4(0.01, 0.01, 0.01, 1.0);'),
    'times20.slang': slang('FragColor = vec4(texture(Source, vTexCoord).rgb * 20.0, 1.0);'),
    'srgb.slangp': '''shaders = 2
shader0 = constant.slang
scale_type0 = source
scale0 = 1.0
srgb_framebuffer0 = true
filter_linear0 = false
shader1 = times20.slang
filter_linear1 = false
''',
    'sections.slang': slang(
        'FragColor = texture(Source, vTexCoord) * global.STRENGTH;', ubo=('float STRENGTH',),
        pragmas=('#pragma parameter HEADER "== Section ==" 0.0 0.0 0.0 0.0',
                 '#pragma parameter STRENGTH "Strength" 1.0 0.0 2.0 0.05')),
    'sections.slangp': 'shaders = 1\nshader0 = sections.slang\n',
    'unknown.slang': slang('FragColor = texture(Source, vTexCoord) * params.MysteryUniform;',
                           push=('vec4 MysteryUniform',)),
    'unknown-semantic.slangp': 'shaders = 1\nshader0 = unknown.slang\n',
    'missing-lut.slangp': ('shaders = 1\nshader0 = lut.slang\ntextures = Palette\n'
                           'Palette = textures/missing.png\n'),
    'symlink-lut.slangp': ('shaders = 1\nshader0 = lut.slang\ntextures = Palette\n'
                           'Palette = textures/link.png\n'),
    'corrupt-lut.slangp': ('shaders = 1\nshader0 = lut.slang\ntextures = Palette\n'
                           'Palette = textures/corrupt.png\n'),
    'textures/corrupt.png': b'\x89PNG\r\n\x1a\n' + bytes(range(64)),
    'huge.slang': slang('FragColor = vec4(1.0);', pragmas=('#pragma format R32G32B32A32_SFLOAT',)),
    'huge.slangp': 'shaders = 1\nshader0 = huge.slang\nscale_type0 = absolute\nscale0 = 16384\n',
    # Catalog preview served by the storage tests' fake network.
    'previews/stock.png': png(2, 1, [[(10, 20, 30, 255), (40, 50, 60, 255)]]),
}


def write_fixtures(directory):
    for name, contents in FIXTURES.items():
        path = directory / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(contents, bytes):
            path.write_bytes(contents)
        else:
            path.write_text(contents)
    os.symlink('palette.png', directory / 'textures/link.png')
    # A preset outside the root, reachable only through "..".
    (directory.parent / 'outside.slangp').write_text('shaders = 1\nshader0 = fixtures/stock.slang\n')


def run(*arguments, **options):
    print('+', ' '.join(str(argument) for argument in arguments), flush=True)
    return subprocess.run([str(argument) for argument in arguments], **options)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--require-metal', action='store_true',
                        help='fail when the Metal render tests cannot run (CI macOS job)')
    parser.add_argument('--build-directory', type=Path, help='reuse a CMake build directory')
    arguments = parser.parse_args()
    if arguments.require_metal and sys.platform != 'darwin':
        raise SystemExit('The Metal render tests run on macOS.')
    with tempfile.TemporaryDirectory(prefix='neo-shader-kit-') as temporary:
        temporary = Path(temporary)
        build = arguments.build_directory or temporary / 'build'
        jobs = str(os.cpu_count() or 2)
        run('cmake', '-S', TOOLS, '-B', build, '-DCMAKE_BUILD_TYPE=Release', check=True)
        targets = ['neoshader-core-tests']
        if sys.platform == 'darwin':
            targets += ['neoshader-kit-tests', 'neoshader-render-tests']
        run('cmake', '--build', build, '--parallel', jobs, '--target', *targets, check=True)
        run(build / 'neoshader-core-tests', check=True)
        if sys.platform != 'darwin':
            print('Metal render tests skipped: they need macOS', flush=True)
            return
        fixtures = temporary / 'fixtures'
        fixtures.mkdir()
        write_fixtures(fixtures)
        run(build / 'neoshader-kit-tests', fixtures, check=True)
        result = run(build / 'neoshader-render-tests', fixtures)
        if result.returncode == NO_DEVICE:
            if arguments.require_metal:
                raise SystemExit('No Metal device: the render tests did not run')
            print('NO METAL DEVICE: render tests skipped', flush=True)
            return
        if result.returncode != 0:
            raise SystemExit(f'Metal render tests failed (exit {result.returncode})')
        print('PASS: shader kit core and Metal runtime render tests', flush=True)


if __name__ == '__main__':
    main()
