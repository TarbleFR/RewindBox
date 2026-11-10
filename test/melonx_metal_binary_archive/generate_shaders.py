#!/usr/bin/env python3
"""Generate the synthetic SPIR-V shaders of the lot 7 MoltenVK test (mvk_archive_test.cpp) into shaders.spvz.

Nothing comes from a game. Each shader is a chain of small functions (sin, cos, mix, fract) whose constants depend on its
index, so its Metal translation and compilation have a real cost. Every shader multiplies by the literal 0.7654321: the
test replaces that constant in the SPIR-V words with a value derived from its salt, so a new salt gives sources Metal has
never compiled. Needs glslangValidator (the committed shaders.spvz is its output; the workflow does not need it).

shaders.spvz: 4 bytes "RBXS", the uncompressed size (uint32), then zlib data of: salt bits (uint32), shader count
(uint32), and per shader: name length (uint32), name, word count (uint32), SPIR-V words. Little endian.
"""
from pathlib import Path
import os
import struct
import subprocess
import tempfile
import zlib

HERE = Path(__file__).resolve().parent
FRAGMENTS, COMPUTES = 12, 6
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


def fragment(index, specialized):
    body = ['#version 450', 'layout(location = 0) in vec2 uv;', 'layout(location = 0) out vec4 color;',
            'layout(push_constant) uniform Params { vec4 a; vec4 b; } u;']
    if specialized:
        body.append('layout(constant_id = 0) const int MODE = 0;')
    body += [helpers(index), 'void main() {', '    vec3 c = vec3(uv, u.a.x);']
    for h in range(WEIGHT):
        body.append(f'    c += h{h}(c + u.b.xyz, u.a.y + {h}.0) * {1.0 / (h + 2):.6f};')
    if specialized:
        body.append('    c += vec3(float(MODE)) * 0.125;')
    body += ['    color = vec4(fract(abs(c)), 1.0);', '}']
    return '\n'.join(body) + '\n'


def compute(index):
    body = ['#version 450', 'layout(local_size_x = 64) in;', 'layout(set = 0, binding = 0) buffer Out { float data[]; } o;',
            helpers(index + 1000), 'void main() {', '    uint i = gl_GlobalInvocationID.x;', '    vec3 c = vec3(float(i) * 0.01, 0.25, 0.5);']
    for h in range(WEIGHT):
        body.append(f'    c += h{h}(c, float(i & 7u) + {h}.0) * {1.0 / (h + 2):.6f};')
    body += ['    o.data[i] = floor(fract(abs(c.x + c.y + c.z)) * 4096.0);', '}']
    return '\n'.join(body) + '\n'


VERTEX_INDEX = '''#version 450
layout(location = 0) out vec2 uv;
void main() {
    vec2 p = vec2((gl_VertexIndex << 1) & 2, gl_VertexIndex & 2);
    gl_Position = vec4(p * 2.0 - 1.0, 0.0, 1.0);
    uv = p;
}
'''
VERTEX_BUFFER = '''#version 450
layout(location = 0) in vec2 position;
layout(location = 0) out vec2 uv;
void main() {
    gl_Position = vec4(position * 2.0 - 1.0, 0.0, 1.0);
    uv = position;
}
'''


def spirv(source, stage, work):
    path = work / ('shader.' + stage)
    path.write_text(source)
    out = work / 'shader.spv'
    subprocess.run(['glslangValidator', '-V', '--quiet', '-o', str(out), str(path)], check=True)
    data = out.read_bytes()
    return struct.unpack('<%dI' % (len(data) // 4), data)


def main():
    shaders = [('vertexIndex', VERTEX_INDEX, 'vert'), ('vertexBuffer', VERTEX_BUFFER, 'vert')]
    shaders += [(f'fragment{i}', fragment(i, i == 0), 'frag') for i in range(FRAGMENTS)]
    shaders += [(f'compute{i}', compute(i), 'comp') for i in range(COMPUTES)]
    salt_bits = struct.unpack('<I', struct.pack('<f', SALT))[0]
    blob = struct.pack('<II', salt_bits, len(shaders))
    total = 0
    with tempfile.TemporaryDirectory() as directory:
        for name, source, stage in shaders:
            words = spirv(source, stage, Path(directory))
            if stage != 'vert':
                assert salt_bits in words, name
            encoded = name.encode()
            blob += struct.pack('<I', len(encoded)) + encoded + struct.pack('<I', len(words)) + struct.pack('<%dI' % len(words), *words)
            total += len(words) * 4
    packed = b'RBXS' + struct.pack('<I', len(blob)) + zlib.compress(blob, 9)
    Path(os.environ.get('SHADER_OUTPUT', HERE / 'shaders.spvz')).write_bytes(packed)
    print(len(shaders), 'shaders,', total, 'bytes of SPIR-V,', len(packed), 'bytes packed')


if __name__ == '__main__':
    main()
