#!/usr/bin/env python3
"""Run extracted descriptor-cache and command-buffer lifecycle code.

The class declaration, reset/begin/end/clear, pipeline/descriptor bind methods,
program::bind and descriptor_table_t::commit come from the native source. A recording driver checks binding
arguments against an uncached required-state model. Layout IDs in that model
represent descriptor-compatible layouts with incompatible push-constant ranges.
No Vulkan device, GPU, Metal compiler, or gameplay is executed. Optional timings
measure Linux/macOS host wrapper cost with a counter-only driver adapter.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import statistics
import subprocess
import tempfile

from rpcs3_bo2_fragment_key_test import braced

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ['rpcs3/Emu/RSX/VK/vkutils/commands.cpp',
          'rpcs3/Emu/RSX/VK/vkutils/commands.h']
SUPPORT = ['rpcs3/Emu/RSX/VK/vkutils/dynamic_state_cache.hpp',
           'rpcs3/Emu/RSX/VK/VKProgramPipeline.cpp']
ADAPTER = ROOT / 'test/native/rpcs3_descriptor_bind_cache.inc'


def sha(path):
    return hashlib.sha256(path.read_bytes().replace(b'\r\n', b'\n')).hexdigest()


def harness(source):
    cpp, header, dynamic, program = [(source / name).read_text() for name in SOURCE + SUPPORT]
    declarations = braced(header, '\tclass command_buffer\n') + ';'
    dynamic_class = braced(dynamic, '\tstruct dynamic_state_cache\n') + ';'
    methods = [braced(cpp, f'void command_buffer::{name}(')
               for name in ['reset', 'clear_state_cache', 'begin', 'end']]
    methods.append(braced(cpp, '#ifdef RPCS3_IOS\n\tvoid command_buffer::bind_pipeline('))
    helper = 'bool command_buffer::update_descriptor_binding_cache('
    if helper in cpp:
        methods.append('#ifdef RPCS3_IOS\n' + braced(cpp, helper) + '\n#endif')
    binds = [braced(cpp[match.start():], 'void command_buffer::bind_descriptor_sets(')
             for match in re.finditer(r'void command_buffer::bind_descriptor_sets\(', cpp)]
    assert len(binds) == 2
    assert cpp.count('vkCmdBindDescriptorSets(') == 2
    methods.extend(binds)
    code = ADAPTER.read_text().replace('// @DYNAMIC_STATE_CLASS@', dynamic_class)
    code = code.replace('// @COMMAND_BUFFER_CLASS@', declarations)
    code = code.replace('// @PRODUCTION_METHODS@', '\n\n'.join(methods))
    code = code.replace('// @PRODUCTION_PROGRAM_BIND@', braced(program, 'program& program::bind('))
    code = code.replace('// @PRODUCTION_DESCRIPTOR_COMMIT@', braced(program, 'VkDescriptorSet descriptor_table_t::commit('))
    assert '// @' not in code
    return code


def expected(source, baseline):
    source, baseline = Path(source), Path(baseline)
    return dict(sourceSHA256={name: sha(source / name) for name in SOURCE + SUPPORT},
                baselineSHA256={name: sha(baseline / name) for name in SOURCE + SUPPORT},
                adapterSHA256=sha(ADAPTER),
                programSHA256={label: hashlib.sha256(harness(root).encode()).hexdigest()
                               for label, root in [('baseline', baseline), ('candidate', source)]})


def verify_counts(results):
    assert set(results) == {'baseline-desktop', 'baseline-ios', 'candidate-desktop', 'candidate-ios'}
    for name, result in results.items():
        fixed = name == 'candidate-ios'
        assert result['returncode'] == (0 if fixed else 86)
        assert len(result['cases']) == 20
        cases = {item['name']: item for item in result['cases']}
        assert len(cases) == 20
        assert result['mismatches'] == sum(item['mismatches'] for item in cases.values())
        assert result['mismatches'] == (0 if fixed else 1141)
        for case_name, attempts, before, after in [
            ('graphics_repeat_plain', 64, 1, 1),
            ('graphics_repeat_empty_offset_overload', 64, 1, 1),
            ('alternating_bind_points', 128, 128, 2),
            ('equal_handles_different_bind_point', 8, 1, 2),
            ('incompatible_layout_same_handles', 8, 1, 8),
            ('overlay_return', 32, 25, 18),
            ('prefix_count_changes', 24, 1, 17),
            ('changed_descriptor_handles', 64, 64, 64),
            ('dynamic_offsets_passthrough', 32, 32, 32),
            ('dynamic_compute_preserves_graphics', 33, 33, 17),
            ('dynamic_prefix_to_plain', 24, 16, 24),
            ('unknown_bind_point_passthrough', 8, 1, 8),
            ('empty_spans', 16, 0, 0),
            ('real_begin_resets', 4, 4, 4),
            ('already_open_begin_preserves', 2, 1, 1),
            ('pending_reuse', 2, 2, 2),
            ('independent_command_buffers', 4, 2, 2),
            ('production_program_reuse', 32, 32, 2),
            ('production_program_dirty_and_overlay', 36, 36, 5),
        ]:
            item = cases[case_name]
            assert item['attempts'] == attempts, (name, item)
            assert item['calls'] == (after if fixed else before), (name, item)
            defects = 4 if not fixed and case_name in {
                'equal_handles_different_bind_point', 'incompatible_layout_same_handles'} else 0
            assert item['mismatches'] == defects, (name, item)
        assert cases['dynamic_offsets_passthrough']['dynamicCalls'] == 32
        assert cases['dynamic_compute_preserves_graphics']['dynamicCalls'] == 16
        assert cases['dynamic_prefix_to_plain']['dynamicCalls'] == 8
        mixed = cases['deterministic_mixed_sequence']
        assert mixed['attempts'] == 4096 and mixed['dynamicCalls'] == 854
        assert mixed['calls'] == (3616 if fixed else 2331)
        assert mixed['mismatches'] == (0 if fixed else 1133)
        for item in cases.values():
            expected_dynamic = {'dynamic_offsets_passthrough': 32, 'dynamic_compute_preserves_graphics': 16,
                                'dynamic_prefix_to_plain': 8, 'deterministic_mixed_sequence': 854}
            assert item['dynamicCalls'] == expected_dynamic.get(item['name'], 0)
            expected_allocation = {'production_program_reuse': (3, 3, 0, 2),
                                   'production_program_dirty_and_overlay': (5, 4, 1, 4)}
            assert (item['allocations'], item['templateCreates'], item['templateUpdates'], item['pipelineCalls']) == expected_allocation.get(item['name'], (0, 0, 0, 0))
        for benchmark in result['benchmark']:
            assert benchmark['operations'] == 2000000
            assert len(benchmark['nanoseconds']) == 7
            assert all(value > 0 for value in benchmark['nanoseconds'])
            expected_calls = {'graphics_hits': 1, 'changing_sets': 2000000,
                              'alternating_bind_points': 2 if fixed else 2000000}
            assert benchmark['calls'] == expected_calls[benchmark['name']]
            expected_checksum = {'graphics_hits': 114, 'changing_sets': 2000227000000,
                                 'alternating_bind_points': 339 if fixed else 339000000}
            assert benchmark['checksum'] == expected_checksum[benchmark['name']]
    # The non-iOS preprocessor path must preserve every observed result. Timings
    # vary across runs and are not part of this equality check.
    def controls_only(result):
        return {key: value for key, value in result.items() if key != 'benchmark'}
    assert controls_only(results['baseline-desktop']) == controls_only(results['candidate-desktop'])
    assert results['candidate-ios']['commandBufferBytes'] == results['baseline-ios']['commandBufferBytes'] + 48


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    parser.add_argument('--sanitizer', choices=['address,undefined'])
    parser.add_argument('--benchmark', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    assert not (args.sanitizer and args.benchmark), 'Do not time sanitizer instrumentation'
    identity = expected(args.source, args.baseline)
    compiler = shlex.split(args.compiler)
    flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-UNDEBUG']
    if sdk := os.environ.get('HOST_MACOS_SDK'):
        flags += ['-isysroot', sdk]
    flags += ['-O1', '-fsanitize=' + args.sanitizer, '-fno-omit-frame-pointer'] if args.sanitizer else ['-O3']
    if args.sanitizer and platform.system() == 'Linux':
        flags += ['-fno-pie', '-no-pie']
    results = {}
    with tempfile.TemporaryDirectory(prefix='rpcs3-descriptor-bind-') as directory:
        for label, root in [('baseline', args.baseline), ('candidate', args.source)]:
            cpp = Path(directory) / (label + '.cpp')
            cpp.write_text(harness(root))
            for ios in [False, True]:
                name = label + ('-ios' if ios else '-desktop')
                exe = Path(directory) / name
                compile_flags = flags + (['-DRPCS3_IOS'] if ios else [])
                subprocess.run(compiler + compile_flags + [str(cpp), '-o', str(exe)], check=True)
                run = subprocess.run([str(exe)] + (['--benchmark'] if args.benchmark else []),
                                     capture_output=True, text=True, timeout=60,
                                     env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1'))
                expected_rc = 0 if ios and label == 'candidate' else 86
                if run.returncode != expected_rc or run.stderr:
                    raise RuntimeError(f'{name}: {run.returncode}\n{run.stdout}\n{run.stderr}')
                results[name] = dict(returncode=run.returncode, **json.loads(run.stdout))
    verify_counts(results)
    assert identity == expected(args.source, args.baseline)
    summaries = {}
    for name, result in results.items():
        summaries[name] = {item['name']: dict(medianNanoseconds=statistics.median(item['nanoseconds']),
                                             minimumNanoseconds=min(item['nanoseconds']),
                                             maximumNanoseconds=max(item['nanoseconds']),
                                             medianNanosecondsPerOperation=statistics.median(item['nanoseconds']) / item['operations'])
                           for item in result['benchmark']}
    report = dict(passed=True, assertionsActive=True, compilerFlags=flags,
                  compiler=subprocess.check_output(compiler + ['--version'], text=True).splitlines()[0],
                  host=platform.machine(), system=platform.system(), sanitizer=args.sanitizer,
                  **identity, results=results, timingSummary=summaries,
                  physicalDeviceTested=False, gameplayMeasured=False, gpuExecuted=False,
                  scope=__doc__)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
