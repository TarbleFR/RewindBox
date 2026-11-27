#!/usr/bin/env python3
"""Generate the 8 x 4 t_nvn_mesh raster fixture through the production S2A.Dsh wrapper."""
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import sys

root, output = (Path(arg).resolve() for arg in sys.argv[1:])
sys.path.insert(0, str(root / 'graphics/tools/direct/tests'))
import dshfn

HEAD = '''#include <metal_stdlib>
using namespace metal;
template<typename T, size_t Num>
struct spvUnsafeArray {
    T elements[Num];
    threadgroup T& operator [] (size_t i) threadgroup { return elements[i]; }
};
'''
def fixture(kind):
    ctl = bytearray(0xe0)
    ctl[0x56] = 6 if kind == 1 else 7
    ctl[0x5e] = int(kind == 2)
    payload = 12 if kind in (1, 2) else 0
    struct.pack_into('<HH', ctl, 0x58, 32, payload)
    struct.pack_into('<HH', ctl, 0x60, 4, 2)
    area = bytearray(0x80)
    area[0x35] = 0xf0
    # Stage words: workgroup at [0], input at [4], output starts after 16-byte-aligned payload.
    out = 8 if payload else 4
    if kind == 1:
        words = 11
        body = f'    if (lane == 0u) {{ m[{out+1}] = 2u; m[{out+2}] = m[0]; }}'
    else:
        prim = out + 4 * 32  # 4 position components, each occupies a 32-vertex block.
        words = prim + 3
        col = '2u * m[6] + m[4]' if kind == 2 else 'm[0]'
        body = f'''    if (lane < 4u) {{
        uint c = {col};
        m[{out}u + lane] = as_type<uint>(float(c + (lane & 1u)) / 4.0f - 1.0f);
        m[{out+32}u + lane] = as_type<uint>((lane & 2u) != 0u ? 1.0f : -1.0f);
        m[{out+96}u + lane] = as_type<uint>(1.0f);
    }}
    if (lane == 0u) {{
        m[{prim}u] = 2u << 24u;
        m[{prim+1}u] = 0x02020100u;
        m[{prim+2}u] = 0x00000301u;
    }}'''
    kernel = HEAD + f'''kernel void main0(uint lane [[thread_position_in_threadgroup]])
{{
    threadgroup spvUnsafeArray<uint, {words}> m;
{body}
}}
'''
    return 'mesh_to_stage', [kernel, ctl.hex(), area.hex()]

previous = []
for switch in ('0', '1'):
    os.environ['S2A_RB_MESH_BARRIER'] = switch
    folder = output / switch
    folder.mkdir(parents=True, exist_ok=True)
    batch = dshfn.batch([fixture(n) for n in (1,2,3)] + [('effective_xfp',[])])
    stages = [s['ok'] for s in batch[:3]]
    manifest = dict(xfp=batch[3]['ok'], shaders=[])
    for index, source in enumerate(stages):
        shader = str(index+1)*16 + '_b.metal'
        (folder / shader).write_text(source)
        entries = re.split(r'(?=\[\[(?:object|mesh)\]\] void main0)', source)[1:]
        marker = '    threadgroup_barrier(mem_flags::mem_threadgroup);\n'
        counts = [e.count(marker) for e in entries]
        expected_off = [3, 4, 3][index]
        assert counts == [expected_off - int(switch)] * (1 if index == 0 else 2)
        if switch == '1':
            assert previous[index].replace(marker,'') == source.replace(marker,'')
        manifest['shaders'].append(dict(name=shader,entry_barriers=counts,
                                         sha256=hashlib.sha256(source.encode()).hexdigest()))
    (folder/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(json.dumps(manifest))
    if switch == '0':
        previous = stages
        reference_xfp = manifest['xfp']
    else:
        assert reference_xfp != manifest['xfp']
