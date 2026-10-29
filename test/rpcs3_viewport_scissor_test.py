#!/usr/bin/env python3
"""Compare exact production viewport/scissor writers and command-cache lifetimes.

Reuse only the previous dynamic-state extractor and Vulkan boundary preamble;
its historical main is never built or run. GPU commands, fences and driver state
are explicit host adapters. Results count commands in controlled traces, not FPS.
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

import rpcs3_dynamic_state_retention_test as retained

ROOT = Path(__file__).resolve().parents[1]
REL = 'rpcs3/Emu/RSX/VK/'
SOURCE = tuple(REL + p for p in ('vkutils/dynamic_state_cache.hpp',
    'vkutils/commands.cpp', 'vkutils/commands.h', 'VKGSRender.cpp', 'VKOverlays.cpp'))
SUPPORT = tuple(REL + p for p in ('VKProgramPipeline.cpp', 'VKProgramPipeline.h'))
BASELINE = SOURCE + SUPPORT
ADAPTER = ROOT / 'test/native/rpcs3_viewport_scissor.inc'
REUSED = ('test/rpcs3_dynamic_state_retention_test.py',
          'test/native/rpcs3_dynamic_state_retention.inc', 'test/rpcs3_runtime_log_followup.py')
WRITERS = ('overlay_pass', 'attachment_clear_pass', 'stencil_clear_pass')
METHODS = ('void command_buffer::begin()', 'void command_buffer::reset()', 'void command_buffer::end()')


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def production(core, namespace, candidate):
    result = retained.production(core, namespace, True)
    source = (core / SOURCE[1]).read_text()
    extension = '\nbool is_pending=false; Fence* m_submit_fence=nullptr;\noperator Driver*() const { return commands; }\n'
    extension += '\n'.join(signature.replace('command_buffer::', '') + ';' for signature in METHODS)
    setters = ('void command_buffer::set_viewport(const VkViewport& viewport) const',
               'void command_buffer::set_scissor(const VkRect2D& scissor) const')
    if candidate:
        extension += '\n' + '\n'.join(signature.replace('command_buffer::', '') + ';' for signature in setters)
    anchor = 'explicit command_buffer(Driver* d):commands(d){}\n'
    assert result.count(anchor) == 1
    result = result.replace(anchor, anchor + extension + '\n')
    result += '\nnamespace ' + namespace + ' {\n'
    result += '\n'.join(retained.definition(source, signature) for signature in METHODS)
    if candidate:
        result += '\n' + '\n'.join(retained.definition(source, signature) for signature in setters)
    result += '''
struct VKGSRender {
    command_buffer* m_current_command_buffer;
    DeviceBoundary* m_device;
    GraphicsState m_graphics_state{};
    VkViewport m_viewport{};
    VkRect2D m_scissor{};
    void bind_viewport();
};
'''
    result += retained.definition((core / SOURCE[3]).read_text(), 'void VKGSRender::bind_viewport()')
    for writer in WRITERS:
        result += ('\nstruct ' + writer + ' { VkRect2D region{}; '
                   'void set_up_viewport(command_buffer& cmd, u32 x, u32 y, u32 w, u32 h); };\n')
        signature = 'void ' + writer + '::set_up_viewport(vk::command_buffer& cmd, u32 x, u32 y, u32 w, u32 h)'
        result += retained.definition((core / SOURCE[4]).read_text(), signature).replace('vk::command_buffer&', 'command_buffer&')
    return result + '\n}\n'


def harness(source, baseline):
    source, baseline = Path(source), Path(baseline)
    for path in SUPPORT:
        assert (source / path).read_bytes() == (baseline / path).read_bytes(), path
    pipeline = (source / SUPPORT[0]).read_text()
    assert 'm_dynamic_state_mask = vk::pipeline_dynamic_state_mask(create_info.pDynamicState);' in pipeline
    assert 'cmd.bind_pipeline(m_pipeline, bind_point, m_dynamic_state_mask);' in pipeline
    for path, signature in ((SOURCE[1], method) for method in METHODS):
        assert retained.definition((source / path).read_text(), signature) == retained.definition((baseline / path).read_text(), signature)
    overlay = (source / SOURCE[4]).read_text()
    assert 'cmd.flags |= vk::command_buffer::cb_reload_dynamic_state;' in overlay
    assert overlay.count('vkCmdSetViewport(') == 3 and overlay.count('vkCmdSetScissor(') == 3
    render = (source / SOURCE[3]).read_text()
    assert render.count('vkCmdSetViewport(') == 1 and render.count('vkCmdSetScissor(') == 1
    common = (ROOT / REUSED[1]).read_text().split('// @PRODUCTION@')[0]
    assert common.count('constexpr unsigned slot_count = 10;') == 1
    common = common.replace('constexpr unsigned slot_count = 10;', 'constexpr unsigned slot_count = 13;')
    common = common.replace('u64 setters = 0, binds = 0;',
        'u64 setters = 0, binds = 0, viewport_calls = 0, scissor_calls = 0; std::vector<int> lifetime;')
    code = ADAPTER.read_text()
    for marker, fragment in (('@REUSED_BOUNDARY@', common),
                             ('@PRODUCTION@', production(baseline, 'reference', False) + production(source, 'candidate', True)),
                             ('@DRAW_EQUAL@', retained.definition((ROOT / REUSED[1]).read_text(), 'void draw_equal(const Driver& a, const Driver& b)'))):
        assert code.count(marker) == 1
        code = code.replace(marker, fragment)
    return code


def expected(source, baseline):
    source, baseline = Path(source), Path(baseline)
    return dict(sourceSHA256={p: sha((source / p).read_bytes()) for p in SOURCE + SUPPORT},
                baselineSHA256={p: sha((baseline / p).read_bytes()) for p in BASELINE},
                harnessSHA256=sha(harness(source, baseline).encode()),
                adapterSHA256=sha(ADAPTER.read_bytes()),
                reusedInputSHA256={p: sha((ROOT / p).read_bytes()) for p in REUSED})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=('address,undefined', 'thread'), default='')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    code = harness(args.source, args.baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-DRPCS3_IOS', '-O1' if args.sanitizer else '-O2',
             '-g', '-UNDEBUG', '-Wall', '-Wextra', '-Werror']
    if args.sanitizer:
        flags += ['-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer']
        if sys.platform.startswith('linux'):
            flags += ['-fno-pie', '-no-pie']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0:halt_on_error=1',
               UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1')
    with tempfile.TemporaryDirectory(prefix='rpcs3-viewport-') as temporary:
        cpp, binary = Path(temporary) / 'test.cpp', Path(temporary) / 'test'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(binary)], check=True)
        run = subprocess.run([str(binary)], capture_output=True, text=True, timeout=60, env=env)
        assert run.returncode == 0 and not run.stderr, (run.returncode, run.stdout, run.stderr)
        result = json.loads(run.stdout)
    assert result['passed'] and result['assertionsActive']
    report = dict(passed=True, assertionsActive=True, results=result,
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, sanitizer=args.sanitizer or None,
                  **expected(args.source, args.baseline), leakSanitizer=False,
                  physicalDeviceTested=False, gameplayMeasured=False,
                  scope='Exact production cache, decoder, bind, begin/reset/end and all four viewport/scissor writers; Vulkan/driver/fence boundary only. Bit-pattern unit cases do not execute invalid values on a GPU. No FPS or submit-time claim.')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
