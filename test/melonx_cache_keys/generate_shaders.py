#!/usr/bin/env python3
"""Generate the synthetic SPIR-V shaders of the cache key measure (mvk_cache_keys_test.cpp) into shaders.spvz.

Nothing comes from a game. The shaders read resources at the binding numbers MeloNX gives a graphics program (the vertex
stage's uniform buffer 1 of set 0; the fragment stage's uniform buffer 73 of set 0, storage buffer 64 of set 1, textures
256 and 257 and buffer texture 288 of set 2, image 128 of set 3), so a pipeline built with MeloNX's descriptor set layouts
has used and unused bindings as a game's has. Each fragment is a chain of small functions whose constants depend on its
index (a real Metal translation and compilation cost); the chain weighs at most 1/128 in the colour, the bound resources
the rest, so a draw shows whether each resource reached the shader. Every shader multiplies by the literal 0.7654321:
the test replaces it with a value derived from its salt and round, which makes distinct shaders.
Needs glslangValidator (the committed shaders.spvz is its output; the workflow does not need it).

shaders.spvz: the format of test/melonx_metal_binary_archive (4 bytes "RBXS", the uncompressed size, zlib data of: salt
bits, shader count, and per shader: name length, name, word count, SPIR-V words; little endian).
"""
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import zlib

HERE = Path(__file__).resolve().parent
FRAGMENTS = 12
WEIGHT = int(os.environ.get('SHADER_WEIGHT', '24'))  # a lighter set for a quick local check on a software driver
SALT = 0.7654321


def helpers(index):
    lines = []
    for h in range(WEIGHT):
        lines.append(f'vec3 h{h}(vec3 p, float t) {{')
        lines.append(f'    vec3 q = p * {1.0 + 0.013 * h + index * 0.11:.6f} + vec3(t);')
        lines.append(f'    q += vec3({SALT}) * t;')
        for k in range(10):
            lines.append(f'    q = mix(sin(q.yzx * {1.3 + 0.07 * k + index * 0.011:.6f} + q.zxy), cos(q * {0.7 + 0.05 * k:.6f}), '
                         f'fract(q.x * {k + 1}.0 + {((h * 31 + k * 7 + index) % 1000) * 0.001:.6f}));')
        lines.append('    return q;')
        lines.append('}')
    return '\n'.join(lines)


def fragment(index):
    kind = index % 3   # 0: buffers and textures; 1: also the buffer texture; 2: also the image
    body = ['#version 450', 'layout(location = 0) in vec2 uv;', 'layout(location = 0) out vec4 color;',
            'layout(set = 0, binding = 0) uniform Support { vec4 scale; } support;',
            'layout(set = 0, binding = 73) uniform FragmentParams { vec4 tint; vec4 a; vec4 b; } fp;',
            'layout(set = 1, binding = 64) readonly buffer Values { vec4 values[]; } sb;',
            'layout(set = 2, binding = 256) uniform sampler2D tex0;',
            'layout(set = 2, binding = 257) uniform sampler2D tex1;']
    if kind == 1:
        body.append('layout(set = 2, binding = 288) uniform samplerBuffer texels;')
    if kind == 2:
        body.append('layout(set = 3, binding = 128, rgba8) uniform readonly image2D picture;')
    body += [helpers(index), 'void main() {', '    vec3 c = vec3(uv, fp.a.x);']
    for h in range(WEIGHT):
        body.append(f'    c += h{h}(c + fp.b.xyz, fp.a.y + {h}.0) * {1.0 / (h + 2):.6f};')
    body.append('    vec3 bound = fp.tint.rgb * texture(tex0, vec2(0.5)).r + texture(tex1, vec2(0.5)).g * sb.values[0].rgb * support.scale.x;')
    if kind == 1:
        body.append('    bound += texelFetch(texels, 0).rgb;')
    if kind == 2:
        body.append('    bound += imageLoad(picture, ivec2(0)).rgb;')
    body += ['    color = vec4(fract(abs(c)) * 0.0078125 + bound * 0.25, 1.0);', '}']
    return '\n'.join(body) + '\n'


VERTEX = f'''#version 450
layout(set = 0, binding = 1) uniform VertexParams {{ vec4 offset; }} vp;
layout(location = 0) out vec2 uv;
void main() {{
    vec2 p = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    gl_Position = vec4(p * 2.0 - 1.0 + vp.offset.xy * {SALT}, 0.0, 1.0);
    uv = p;
}}
'''


def spirv(source, stage, work):
    path = work / ('shader.' + stage)
    path.write_text(source)
    out = work / 'shader.spv'
    subprocess.run(['glslangValidator', '-V', '--quiet', '-o', str(out), str(path)], check=True)
    data = out.read_bytes()
    return struct.unpack('<%dI' % (len(data) // 4), data)


def main():
    shaders = [('vertex', VERTEX, 'vert')] + [(f'fragment{i}', fragment(i), 'frag') for i in range(FRAGMENTS)]
    salt_bits = struct.unpack('<I', struct.pack('<f', SALT))[0]
    blob = struct.pack('<II', salt_bits, len(shaders))
    total = 0
    with tempfile.TemporaryDirectory() as directory:
        for name, source, stage in shaders:
            words = spirv(source, stage, Path(directory))
            assert salt_bits in words, name
            encoded = name.encode()
            blob += struct.pack('<I', len(encoded)) + encoded + struct.pack('<I', len(words)) + struct.pack('<%dI' % len(words), *words)
            total += len(words) * 4
    packed = b'RBXS' + struct.pack('<I', len(blob)) + zlib.compress(blob, 9)
    Path(os.environ.get('SHADER_OUTPUT', HERE / 'shaders.spvz')).write_bytes(packed)
    print(len(shaders), 'shaders,', total, 'bytes of SPIR-V,', len(packed), 'bytes packed')


if __name__ == '__main__':
    main()
