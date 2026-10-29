#!/usr/bin/env python3
"""Compare production Vulkan state-cache/command methods with Core 592.

Only the Vulkan driver and surrounding command-buffer lifetime are adapted.
The real bind/setter methods, cache and dynamic-declaration decoder are compiled.
No GPU/iOS execution, draw skipping, or FPS result is implied.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

from rpcs3_runtime_log_followup import authenticate, normalized_sha, reconstruct

ROOT = Path(__file__).resolve().parents[1]
REL = 'rpcs3/Emu/RSX/VK/'
PATHS = [REL+p for p in ('vkutils/dynamic_state_cache.hpp','vkutils/commands.cpp','vkutils/commands.h','VKProgramPipeline.cpp','VKProgramPipeline.h')]

def definition(text, signature):
    start=text.index(signature); body=text.index('{', start); depth=1; end=body+1
    while depth:
        depth += (text[end]=='{')-(text[end]=='}'); end+=1
    # Select the signature explicitly: production uses an iOS/non-iOS signature guard.
    return signature+'\n'+text[body:end]

def production(core, namespace, candidate):
    cache=(core/PATHS[0]).read_text().replace('#pragma once','').replace('namespace vk',f'namespace {namespace}')
    source=(core/PATHS[1]).read_text()
    bind='void command_buffer::bind_pipeline(VkPipeline pipeline, VkPipelineBindPoint bind_point'+(', u32 dynamic_state_mask' if candidate else '')+') const'
    methods=['void command_buffer::clear_state_cache()',bind,
        'void command_buffer::set_line_width(float width) const',
        'void command_buffer::set_blend_constants(const float* colors) const',
        'void command_buffer::set_depth_bias(float constant, float clamp, float slope) const',
        'void command_buffer::set_depth_bounds(float minimum, float maximum) const',
        'void command_buffer::set_stencil_write_mask(VkStencilFaceFlags faces, u32 value) const',
        'void command_buffer::set_stencil_compare_mask(VkStencilFaceFlags faces, u32 value) const',
        'void command_buffer::set_stencil_reference(VkStencilFaceFlags faces, u32 value) const']
    declarations='\n'.join(x.replace('command_buffer::','').replace(', u32 dynamic_state_mask)',', u32 dynamic_state_mask = 0)')+';' for x in methods)
    result=cache+f'\nnamespace {namespace} {{\nclass command_buffer {{\npublic:\n'
    result+='bool is_open=true; Driver* commands; mutable std::array<VkDescriptorSet,2> m_bound_descriptor_sets{}; mutable std::array<VkPipeline,2> m_bound_pipelines{}; mutable dynamic_state_cache m_dynamic_state;\n'
    result+='explicit command_buffer(Driver* d):commands(d){}\n'+declarations+'\n};\n'
    if candidate:result+=definition(source,'u32 pipeline_dynamic_state_mask(const VkPipelineDynamicStateCreateInfo* info) noexcept')+'\n'
    result+='\n'.join(definition(source,x) for x in methods)+'\n}\n'
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('core',type=Path);p.add_argument('--baseline',type=Path)
    p.add_argument('--compiler',default=os.environ.get('CXX','c++'));p.add_argument('--sanitize',action='store_true');p.add_argument('--output',type=Path)
    a=p.parse_args();core=a.core.resolve()
    authenticated=authenticate(core)
    # The compiled program feeds the exact declaration into the mask and the actual bind.
    integration=(core/PATHS[3]).read_text()
    assert 'm_dynamic_state_mask = vk::pipeline_dynamic_state_mask(create_info.pDynamicState);' in integration
    assert 'cmd.bind_pipeline(m_pipeline, bind_point, m_dynamic_state_mask);' in integration
    with tempfile.TemporaryDirectory(prefix='rpcs3-dynamic-') as temp:
        before=a.baseline.resolve() if a.baseline else reconstruct(core,Path(temp)/'before',authenticated)
        for relative in PATHS:
            assert normalized_sha(before/relative)==authenticated[1]['before_sha256'][relative],relative
        source=(ROOT/'test/native/rpcs3_dynamic_state_retention.inc').read_text()
        generated=source.replace('// @PRODUCTION@',production(before,'reference',False)+production(core,'candidate',True))
        cpp=Path(temp)/'test.cpp';exe=Path(temp)/'test';cpp.write_text(generated)
        compiler=shlex.split(a.compiler)
        if sdk:=os.environ.get('HOST_MACOS_SDK'):compiler+=['-isysroot',sdk]
        command=compiler+['-std=c++20','-DRPCS3_IOS','-O1' if a.sanitize else '-O3','-UNDEBUG','-g','-Wall','-Wextra','-Werror',str(cpp),'-o',str(exe)]
        if a.sanitize:
            command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
            if sys.platform.startswith('linux'):command+=['-fno-pie','-no-pie']
        subprocess.run(command,check=True)
        run=subprocess.run([str(exe)],capture_output=True,text=True,
            env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:
            print(run.stdout, end='')
            print(run.stderr, end='', file=sys.stderr)
            run.check_returncode()
        result=json.loads(run.stdout)
        report={'passed':True,'test':'Vulkan dynamic-state retention','sanitized':a.sanitize,'compiler':subprocess.check_output(shlex.split(a.compiler)+['--version'],text=True).splitlines()[0],
            'compilerFlags':[flag for flag in command[len(compiler):] if flag not in (str(cpp),str(exe),'-o')],
            'results':result,'harness_sha256':hashlib.sha256(generated.encode()).hexdigest(),
            'before_sha256':{f:hashlib.sha256((before/f).read_bytes()).hexdigest() for f in PATHS},
            'after_sha256':{f:hashlib.sha256((core/f).read_bytes()).hexdigest() for f in PATHS},
            'limits':'Host adapter of Vulkan commands; no Apple SDK, GPU execution or iPhone FPS measurement.'}
        if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(report,indent=2)+'\n')
        print(json.dumps(report,indent=2))

if __name__=='__main__':main()
