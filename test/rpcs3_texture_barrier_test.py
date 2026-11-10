#!/usr/bin/env python3
"""Compile exact Vulkan image barrier selection before/after with a recording API.

The host boundary records vkCmdPipelineBarrier; there is no Vulkan device or
driver execution. Graphics stages are tested; compute callers have explicit
barriers and are not made safe by this test or by adding vertex stage bits.
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

ROOT = Path(__file__).resolve().parents[1]
SOURCE = 'rpcs3/Emu/RSX/VK/vkutils/image_helpers.cpp'
ADAPTER = ROOT / 'test/native/rpcs3_texture_barrier.inc'
SIGNATURE = 'void change_image_layout(const vk::command_buffer& cmd, VkImage image,'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def harness(source, baseline):
    old, new = (baseline / SOURCE).read_text(), (source / SOURCE).read_text()
    before, after = braced(old, SIGNATURE), braced(new, SIGNATURE)
    expected = re.sub(r'(?m)^(\s*)VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT\n',
                      r'\1VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT |\n\1VK_PIPELINE_STAGE_VERTEX_SHADER_BIT\n', before)
    expected = expected.replace('src_stage = VK_PIPELINE_STAGE_TRANSFER_BIT | VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT;',
                                'src_stage = VK_PIPELINE_STAGE_TRANSFER_BIT | VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT | VK_PIPELINE_STAGE_VERTEX_SHADER_BIT;')
    expected = expected.replace('src_stage = VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT;',
                                'src_stage = VK_PIPELINE_STAGE_FRAGMENT_SHADER_BIT | VK_PIPELINE_STAGE_VERTEX_SHADER_BIT;')
    assert expected == after
    assert old.replace(before, after) == new
    return ADAPTER.read_text().replace('@BEFORE@', before.replace('void change_image_layout(', 'void before(')).replace('@AFTER@', after.replace('void change_image_layout(', 'void after('))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--report', required=True, type=Path)
    args = parser.parse_args()
    source, baseline = args.source.resolve(), args.baseline.resolve()
    code = harness(source, baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror', '-UNDEBUG']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    with tempfile.TemporaryDirectory(prefix='texture-barriers-') as temp:
        cpp, exe = Path(temp) / 'test.cpp', Path(temp) / 'test'
        cpp.write_text(code)
        subprocess.run(compiler + flags + [str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)], capture_output=True, text=True, check=True, timeout=30)
    result = dict(passed=True, sourceSHA256={SOURCE: sha(source / SOURCE)},
                  baselineSHA256={SOURCE: sha(baseline / SOURCE)},
                  harnessSHA256=hashlib.sha256(code.encode()).hexdigest(), adapterSHA256=sha(ADAPTER),
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  compilerFlags=flags, host=platform.machine(), results=json.loads(run.stdout),
                  physicalDeviceTested=False, gameplayMeasured=False, scope=__doc__)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
