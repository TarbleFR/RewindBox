#!/usr/bin/env python3
"""REWINDBOX_POSITION_INVARIANCE_610: the scoped titles declare an invariant position.

Three layers, each reported separately; none executes Metal, a game or an iPhone:

1. Source contract on a materialized Core: the iOS branch of
   VKVertexDecompilerThread::insertMainStart, the policy field, its resolution
   from the title list, the boot-policy log field, and the unchanged non-iOS line.
2. Title predicate: ios/IOSTitleLevers.h compiled and evaluated on the scoped and
   unscoped serials.
3. Shader chain: the real prologue generator (GLSLCommon.cpp and StrFmt.cpp of
   the materialized Core) emits the Apple-GPU vertex prologue with and without
   the option; two vertex programs sharing the same RSX position computation
   (base pass A, light pass B) are compiled by the pinned glslang, and MoltenVK's
   own SPIRVToMSLConverter (pinned MoltenVK, pinned SPIRV-Cross) reports what
   decides MTLCompileOptions.preserveInvariance.

Logging, termination and MoltenVK debug-dump helpers are explicit adapters that
abort if reached. Tool paths are required for layer 3; without them the layer is
reported as skipped, never as passed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'test/native/rpcs3_position_invariance'
VERTEX = 'rpcs3/Emu/RSX/VK/VKVertexProgram.cpp'
POLICY_H = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h'
POLICY_CPP = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
LEVERS = 'rpcs3/ios/IOSTitleLevers.h'
UPSTREAM_LINE = ('properties2.require_explicit_invariance = (vk::is_NVIDIA(vk::get_driver_vendor()) && '
                 'g_cfg.video.shader_precision != gpu_preset_level::low);')
IOS_BRANCH = re.compile(
    r'#ifdef RPCS3_IOS\n(?:\t//[^\n]*\n)+'
    r'\tproperties2\.require_explicit_invariance = \(vk::is_NVIDIA\(vk::get_driver_vendor\(\)\) \|\|\n'
    r'\t\trpcs3::ios::get_experimental_policy\(\)\.position_invariance\) &&\n'
    r'\t\tg_cfg\.video\.shader_precision != gpu_preset_level::low;\n'
    r'#else\n\t' + re.escape(UPSTREAM_LINE) + r'\n#endif\n')
SCOPED = ['BLES01717', 'BLES00158', 'BLUS30089']
UNSCOPED = ['BCES00510', 'BCUS98111', 'BLES01658', 'BLES00113', 'BLUS30070', 'BLUS31011', 'NPEB00000', '']
PIN = dict(glslang='f0bd0257c308b9a26562c1a30c4748a0219cc951',
           moltenvk='db66022459ffb663aa2b50f6b018bc2e124f5edf',
           spirv_cross='6c09849fe88c48eaed08413aa022aaa136a3a057')


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def require(value, message):
    if not value:
        raise AssertionError(message)


def run(command, **kwargs):
    result = subprocess.run([str(part) for part in command], text=True, capture_output=True, **kwargs)
    if result.returncode:
        raise AssertionError(f'{command[0]} failed ({result.returncode}): {result.stdout}{result.stderr}')
    return result.stdout


def source_contract(source: Path) -> dict:
    vertex = (source / VERTEX).read_text()
    require(IOS_BRANCH.search(vertex), 'iOS invariance branch of insertMainStart differs')
    require(vertex.count('require_explicit_invariance') == 2, 'unexpected extra invariance assignment')
    require('#ifdef RPCS3_IOS\n#include "ios/RPCS3IOSExperimentalPolicy.h"\n#endif' in vertex, 'policy include missing')
    header = (source / POLICY_H).read_text()
    require(re.search(r'\n\tbool position_invariance = false;\n', header), 'policy field missing')
    policy = (source / POLICY_CPP).read_text()
    require('resolved.position_invariance = rpcs3::ios::title_levers::requires_position_invariance(title_id);' in policy,
            'policy resolution missing')
    require(policy.count('position_invariance') >= 3 and 'position_invariance=%d mvk_async=%d"' in policy,
            'boot policy log field missing')
    require('is_god_of_war_iii_title(title_id) || rpcs3::ios::title_levers::is_assassins_creed_title(title_id)));'
            in policy, 'Assassin\'s Creed is not in the asynchronous submit Automatic list')
    return {'vertex_sha256': sha((source / VERTEX).read_bytes()), 'policy_h_sha256': sha(header.encode()),
            'policy_cpp_sha256': sha(policy.encode()), 'levers_sha256': sha((source / LEVERS).read_bytes()),
            'non_ios_line_unchanged': True}


def predicate(source: Path, work: Path, compiler: str) -> dict:
    program = work / 'predicate.cpp'
    program.write_text('#include "ios/IOSTitleLevers.h"\n#include <cstdio>\nint main(int c,char**v){\n'
                       'for(int i=1;i<c;++i)std::printf("%s=%d\\n",v[i],'
                       '(int)rpcs3::ios::title_levers::requires_position_invariance(v[i]));}\n')
    binary = work / 'predicate'
    run([compiler, '-std=c++20', '-I', source / 'rpcs3', program, '-o', binary])
    values = dict(line.split('=') for line in run([binary, *SCOPED, *UNSCOPED]).split())
    require(all(values[s] == '1' for s in SCOPED), 'a scoped title is not selected')
    require(all(values.get(s, '0') == '0' for s in UNSCOPED if s), 'an unscoped title is selected')
    return {'scoped': SCOPED, 'unscoped_checked': [s for s in UNSCOPED if s], 'result': 'pass'}


def compose(work: Path, variant: str, kind: str) -> str:
    """Build a vertex program with the candidate's VK header/main-end structure."""
    header = ('#version 450\n\n#extension GL_EXT_scalar_block_layout : require\n'
              '#extension GL_EXT_uniform_buffer_unsized_array : require\n'
              '#extension GL_ARB_separate_shader_objects : enable\n\n')
    redirect = ('#define get_draw_params() draw_parameters[draw_parameters_offset]\n'
                '#define vs_context_offset get_draw_params().vs_context_offset\n\n'
                '#define get_vertex_context() vertex_contexts[vs_context_offset]\n'
                '#define get_user_clip_config() get_vertex_context().user_clip_configuration_bits\n\n')
    context = ('layout(std430, set=0, binding=3) uniform VertexContextBuffer\n{\n'
               '\tvertex_context_t vertex_contexts[];\n};\n\n'
               'layout(std430, set=0, binding=4) readonly buffer DrawParametersBuffer\n{\n'
               '\tdraw_parameters_t draw_parameters[];\n};\n\n'
               'layout(push_constant) uniform push_block { uint draw_parameters_offset; };\n\n')
    inputs = ('layout(location=0) in vec4 in_pos;\nlayout(location=1) in vec4 in_normal;\n'
              'layout(std140, set=0, binding=5) uniform VertexConstantsBuffer { vec4 vc[468]; };\n'
              '#define xform_constants_offset 0\n')
    outputs = 'layout(location=0) out vec4 tc0;\n' + ('layout(location=1) out vec4 diff_color;\n' if kind == 'B' else '')
    body = ['vec4 dst_reg0 = vec4(0., 0., 0., 1.);', 'vec4 dst_reg7 = vec4(0.);', 'vec4 tmp0;']
    body += [f'dst_reg0.{axis} = dot(in_pos, _fetch_constant({row}));' for axis, row in zip('xyzw', range(4))]
    body.append('dst_reg7 = in_pos * _fetch_constant(8) + _fetch_constant(9);')
    if kind == 'B':
        body += ['tmp0 = _fetch_constant(12) - in_pos;', 'tmp0.w = inversesqrt(dot(tmp0.xyz, tmp0.xyz));',
                 'dst_reg7.xyz = tmp0.xyz * tmp0.w;',
                 'dst_reg7.w = clamp(1.0 - dot(tmp0.xyz, tmp0.xyz) * _fetch_constant(13).x, 0.0, 1.0) * '
                 'max(dot(in_normal.xyz, dst_reg7.xyz), 0.0);']
    vs_main = ('vec4 dst_reg0_out;\nvoid vs_main()\n{\n\t' + '\n\t'.join(body) + '\n\tdst_reg0_out = dst_reg0;\n'
               '\ttc0 = dst_reg7;\n' + ('\tdiff_color = dst_reg7.wwww;\n' if kind == 'B' else '') + '}\n\n')
    main = ('void main ()\n{\n\n\tvs_main();\n\n\tgl_Position = dst_reg0_out;\n'
            '\tgl_Position = gl_Position * get_vertex_context().scale_offset_mat;\n'
            '\tgl_Position = apply_zclip_xform(gl_Position, get_vertex_context().z_near, get_vertex_context().z_far);\n}\n')
    return (header + (work / 'subheader.glsl').read_text() + redirect + context +
            (work / f'prologue-{variant}.glsl').read_text() + inputs + outputs + vs_main + main)


def chain(source: Path, work: Path, args) -> dict:
    sources = {name: sha((NATIVE / name).read_bytes()) for name in
               ('prologue_probe.cpp', 'prologue_adapters.cpp', 'mvk_probe.cpp', 'mvk_adapters.cpp',
                'shim/TargetConditionals.h')}
    gnu = [args.cxx, '-std=gnu++20', '-O1', '-I', source / 'rpcs3', '-I', source,
           '-include', source / 'rpcs3/stdafx.h']
    for name, rel in (('GLSLCommon.o', 'rpcs3/Emu/RSX/Program/GLSLCommon.cpp'), ('StrFmt.o', 'Utilities/StrFmt.cpp')):
        run(gnu + ['-c', source / rel, '-o', work / name])
    run(gnu + [NATIVE / 'prologue_probe.cpp', NATIVE / 'prologue_adapters.cpp', work / 'GLSLCommon.o',
               work / 'StrFmt.o', '-o', work / 'prologue'])
    for part in ('subheader', 'plain', 'invariant'):
        (work / ('subheader.glsl' if part == 'subheader' else f'prologue-{part}.glsl')).write_text(
            run([work / 'prologue', part]))
    plain, invariant = (work / 'prologue-plain.glsl').read_text(), (work / 'prologue-invariant.glsl').read_text()
    require('#define _FORCE_POSITION_INVARIANCE' not in plain and '#define _FORCE_POSITION_INVARIANCE' in invariant
            and '_EMULATE_ZCLIP_XFORM_FALLBACK' in invariant and 'invariant gl_Position;' in invariant,
            'real prologue generator did not emit the expected invariance define')
    mvk = args.moltenvk / 'MoltenVKShaderConverter/MoltenVKShaderConverter'
    includes = ['-I', NATIVE / 'shim', '-I', args.spirv_cross, '-I', args.moltenvk / 'Common', '-I', mvk,
                '-I', args.moltenvk / 'MoltenVKShaderConverter']
    libraries = [args.spirv_cross_build / f'libspirv-cross-{name}.a' for name in ('msl', 'glsl', 'core')]
    run([args.cxx, '-std=gnu++20', '-O1', *includes, NATIVE / 'mvk_probe.cpp', NATIVE / 'mvk_adapters.cpp',
         mvk / 'SPIRVToMSLConverter.cpp', *libraries, '-o', work / 'mvk_probe'])
    results = {}
    for variant in ('plain', 'invariant'):
        for kind in ('A', 'B'):
            name = f'{variant}-{kind}'
            vert = work / f'{name}.vert'
            vert.write_text(compose(work, variant, kind))
            spv = work / f'{name}.spv'
            run([args.glslang, '-V', '--target-env', 'vulkan1.2', '-S', 'vert', '-o', spv, vert])
            human = run([args.glslang, '-V', '--target-env', 'vulkan1.2', '-S', 'vert', '-H', '-o', work / f'{name}.h.spv', vert])
            report = run([work / 'mvk_probe', spv, work / f'{name}.msl'])
            msl = (work / f'{name}.msl').read_text()
            fields = dict(item.split('=', 1) for item in report.split() if '=' in item)
            results[name] = {
                'glsl_sha256': sha(vert.read_bytes()), 'spirv_sha256': sha(spv.read_bytes()),
                'spirv_position_invariant_decoration': bool(re.search(r'MemberDecorate \d+\(gl_PerVertex\) 0 Invariant', human)),
                'msl_position_attribute': re.search(r'float4 gl_Position \[\[([^\]]+)\]\]', msl).group(1),
                'mvk_isPositionInvariant': fields['isPositionInvariant'] == '1',
                'mvk_fpFastMathFlags': fields['fpFastMathFlags'], 'converted': fields['converted'] == '1'}
    for kind in ('A', 'B'):
        before, after = results[f'plain-{kind}'], results[f'invariant-{kind}']
        require(before['converted'] and after['converted'], 'MoltenVK conversion failed')
        require(not before['spirv_position_invariant_decoration'] and before['msl_position_attribute'] == 'position'
                and not before['mvk_isPositionInvariant'], 'current output is unexpectedly invariant')
        require(after['spirv_position_invariant_decoration'] and after['msl_position_attribute'] == 'position, invariant'
                and after['mvk_isPositionInvariant'], 'candidate does not make MoltenVK request preserveInvariance')
        require(before['mvk_fpFastMathFlags'] == after['mvk_fpFastMathFlags'] == '0xffffffff',
                'fast-math flags changed; MoltenVK would select a different math mode')
    return {'native_sources_sha256': sources, 'prologue_plain_sha256': sha(plain.encode()),
            'prologue_invariant_sha256': sha(invariant.encode()), 'shaders': results,
            'tool_pins': PIN, 'compiler': run([args.cxx, '--version']).splitlines()[0]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True, help='materialized candidate Core')
    parser.add_argument('--glslang', type=Path, help=f'glslang {PIN["glslang"]} standalone binary')
    parser.add_argument('--moltenvk', type=Path, help=f'MoltenVK {PIN["moltenvk"]} checkout')
    parser.add_argument('--spirv-cross', type=Path, help=f'SPIRV-Cross {PIN["spirv_cross"]} checkout')
    parser.add_argument('--spirv-cross-build', type=Path, help='its CMake build directory (static libraries)')
    parser.add_argument('--cxx', default=os.environ.get('CXX', 'g++'))
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'schema': 1, 'source_contract': source_contract(args.source)}
    with tempfile.TemporaryDirectory(prefix='rpcs3-invariance-') as temp:
        work = Path(temp)
        report['title_predicate'] = predicate(args.source, work, args.cxx)
        tools = [args.glslang, args.moltenvk, args.spirv_cross, args.spirv_cross_build]
        if all(tools):
            for checkout, pin in ((args.moltenvk, PIN['moltenvk']), (args.spirv_cross, PIN['spirv_cross'])):
                head = run(['git', '-C', checkout, 'rev-parse', 'HEAD^{commit}']).strip()
                # The MoltenVK checkout may carry the reviewed deferred-cache commit on its pin.
                base = run(['git', '-C', checkout, 'rev-list', '--max-parents=0', 'HEAD']).split()
                require(head == pin or pin in base, f'{checkout} is not on {pin}')
            report['shader_chain'] = chain(args.source, work, args)
        else:
            report['shader_chain'] = 'skipped: glslang, MoltenVK, SPIRV-Cross and its build are all required'
    report['limits'] = ['No Metal compilation, GPU execution, game, iPhone or frame measurement.',
                        'Programs A/B are composed around the real generated prologue; the full decompiler is not run.']
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text)
    print('PASS' if isinstance(report['shader_chain'], dict) else 'PASS (shader chain skipped)')
    return 0


if __name__ == '__main__':
    sys.exit(main())
