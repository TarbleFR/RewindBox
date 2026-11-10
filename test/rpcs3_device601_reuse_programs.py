#!/usr/bin/env python3
"""Regenerate the ten unchanged device601 Apple programs without executing them.

The caller must authenticate these runners and fixtures against their original
Git blobs before importing this helper. Imports load only frozen constants and
extraction functions; no runner main, compiler or native executable is called.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def module(repo, relative):
    spec = importlib.util.spec_from_file_location('_device601_reuse_' + sha(relative.encode()), repo / relative)
    require(spec is not None and spec.loader is not None, 'Missing authenticated runner: ' + relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def audit_report(report, job, source: Path, baseline: Path, repo: Path):
    """Check recorded source/extraction hashes and return exact compiled-C++ hashes."""
    source, baseline, repo = source.resolve(), baseline.resolve(), repo.resolve()
    name, mode = job['name'], job['mode']
    require(mode in ('plain', 'asan-ubsan'), 'Unknown reuse mode')
    sanitized = mode == 'asan-ubsan'
    runner_path = job['argv'][1].removeprefix('{repo}/')
    runner = module(repo, runner_path)
    source_inputs, baseline_inputs, fixture_inputs, extractions, programs = {}, {}, {}, {}, {}
    fixture_inputs[runner_path] = sha((repo / runner_path).read_bytes())

    def input_digest(root, relative, normalized=False):
        raw = (root / relative).read_bytes()
        return sha(raw.replace(b'\r\n', b'\n') if normalized else raw)

    def current_inputs(expected, actual, normalized=False):
        require(set(actual) == set(expected), 'Reported candidate input set differs: ' + name)
        for relative in expected:
            digest = input_digest(source, relative, normalized)
            require(actual[relative] == digest, 'Candidate input changed: ' + relative)
            source_inputs[relative] = digest

    def prior_inputs(expected, actual, normalized=False):
        require(set(actual) == set(expected), 'Reported baseline input set differs: ' + name)
        for relative in expected:
            digest = input_digest(baseline, relative, normalized)
            require(actual[relative] == digest, 'Baseline input changed: ' + relative)
            baseline_inputs[relative] = digest

    if name.startswith('tiny-vertex-'):
        require(report['sanitizer'] is sanitized and report['gpu_executed'] is False, 'Tiny report scope differs')
        variants = [('candidate-ios', source)] if sanitized else [
            ('baseline-ios', baseline), ('candidate-ios', source), ('candidate-other', source)]
        require([item['name'] for item in report['results']] == [item[0] for item in variants], 'Tiny variants differ')
        for item, (variant, root) in zip(report['results'], variants):
            text = (root / runner.REL).read_text()
            body = '\n'.join(runner.block(text, marker) + ';' for marker in [
                'template <typename storage_type>\n\t\tclass default_vertex_cache',
                'struct uploaded_range', 'class weak_vertex_cache'])
            cpp = runner.PREFIX + '\nnamespace rsx::vertex_cache {\n' + body + '\n}\n' + runner.SUFFIX
            digest = input_digest(root, runner.REL)
            require(item['source_sha256'] == digest and item['program_sha256'] == sha(cpp.encode()),
                    'Tiny generated program differs: ' + variant)
            (baseline_inputs if root == baseline else source_inputs)[str(runner.REL)] = digest
            programs[variant] = sha(cpp.encode())
    elif name.startswith('color-feedback-'):
        require(report['sanitizer'] is sanitized and report['gpu_executed'] is False, 'Feedback report scope differs')
        variants = [('before', baseline), ('after', source), ('after-nonios', source)]
        require([item['name'] for item in report['variants']] == [item[0] for item in variants], 'Feedback variants differ')
        for item, (variant, root) in zip(report['variants'], variants):
            helper = runner.block((root / runner.REL).read_text(), 'vk::image_view* VKGSRender::snapshot_color_feedback(')
            cpp = runner.PRELUDE + helper + '\n' + runner.MAIN
            digest = input_digest(root, runner.REL)
            require(item['source_sha256'] == digest and item['helper_sha256'] == sha(helper.encode())
                    and item['program_sha256'] == sha(cpp.encode()), 'Feedback generated program differs: ' + variant)
            (baseline_inputs if root == baseline else source_inputs)[str(runner.REL)] = digest
            extractions[variant] = sha(helper.encode())
            programs[variant] = sha(cpp.encode())
    elif name.startswith('vertex-range-'):
        require(report['sanitizer'] is sanitized, 'Vertex range sanitizer differs')
        paths = [str(runner.REL), 'rpcs3/ios/IOSRendererCausality.h', 'rpcs3/Emu/RSX/RSXThread.cpp',
                 'rpcs3/Emu/RSX/rsx_cache.h', 'rpcs3/Emu/RSX/Core/RSXVertexTypes.h',
                 'rpcs3/Emu/RSX/Core/RSXDrawCommands.cpp']
        current_inputs(paths, report['inputs'])
        text = (source / paths[2]).read_text()
        range_method = runner.block(text, 'std::pair<u32, u32> interleaved_range_info::calculate_required_range')
        range_method = range_method.replace('interleaved_range_info::', 'rsx::interleaved_range_info::', 1)
        cache = runner.block((source / paths[3]).read_text(), 'namespace vertex_cache')
        getter = runner.block((source / paths[4]).read_text(), 'std::pair<u32, u32> get_required_range')
        copytext = (source / paths[5]).read_text()
        start = copytext.index('void draw_command_processor::write_vertex_data_to_memory')
        copy_loop = runner.block(copytext[start:], 'for (interleaved_range_info* block : layout.interleaved_blocks)')
        copy_loop = copy_loop.replace('interleaved_range_info*', 'rsx::interleaved_range_info*', 1)
        causality = (source / paths[1]).read_text().replace('#pragma once', '')
        fixture = 'test/rpcs3_device597/renderer/fixtures/VKVertexBuffers.before.cpp'
        fixture_inputs[fixture] = sha((repo / fixture).read_bytes())
        require(set(report['variants']) == {'before', 'after'}, 'Vertex range variants differ')
        for variant, vertex in [('before', (repo / fixture).read_text()), ('after', (source / runner.REL).read_text())]:
            cache_block = runner.block(vertex[vertex.index('VKGSRender::upload_vertex_data'):], 'if (required.first > 0)')
            cpp = runner.PRELUDE.replace('__CAUSALITY_HELPER__', causality).replace('__GET_REQUIRED_RANGE__', getter)
            cpp = cpp.replace('__RANGE_METHOD__', range_method).replace('__VERTEX_CACHE__', cache)
            cpp = cpp.replace('__CACHE_BLOCK__', cache_block).replace('__COPY_LOOP__', copy_loop) + runner.MAIN
            require(report['variants'][variant]['generated_sha256'] == sha(cpp.encode())
                    and report['variants'][variant]['returncode'] == 0, 'Vertex range generated program differs: ' + variant)
            programs[variant] = sha(cpp.encode())
    elif name.startswith('exitspawn-worker-'):
        require(report['sanitizers'] == (['address', 'undefined'] if sanitized else []), 'Boot sanitizer differs')
        current_inputs(runner.INPUTS, report['source_inputs_sha256'])
        prior_inputs(runner.INPUTS, report['baseline_inputs_sha256'])
        api = (source / runner.INPUTS[2]).read_text()
        methods = api.split('// REWINDBOX_RESTORE_EXECUTOR_BEGIN:')[1].split('\n', 1)[1].split('// REWINDBOX_RESTORE_EXECUTOR_END')[0]
        wrappers = runner.body(api, 'std::uint64_t continuous_boot_generation() noexcept') + '\n' + api[
            api.index('namespace\n{\nstruct continuous_stop_request'):api.index(
                '\n}\n\n[[noreturn]] void report_fatal_error', api.index('struct continuous_stop_request'))]
        require(report['extracted_executor_sha256'] == sha(methods.encode())
                and report['extracted_wrappers_sha256'] == sha(wrappers.encode()), 'Boot extraction differs')
        fixture = 'test/native/rpcs3_exitspawn_worker601.cpp'
        digest = sha((repo / fixture).read_bytes())
        require(report['test_source_sha256'] == digest, 'Boot fixture differs')
        fixture_inputs[fixture] = digest
        extractions.update(executor=sha(methods.encode()), continuations=sha(wrappers.encode()))
        programs['fixture'] = digest
    elif name.startswith('savestate-completion-'):
        require(report['sanitizers'] == (['address', 'undefined'] if sanitized else [])
                and report['exceptions_disabled'] is True and report['core_ui_gpu_device_executed'] is False,
                'Savestate report scope differs')
        current_inputs([runner.INPUT], report['source_inputs_sha256'], normalized=True)
        prior_inputs([runner.INPUT], report['baseline_inputs_sha256'], normalized=True)
        fixture = 'test/native/rpcs3_savestate_completion601.cpp'
        digest = sha((repo / fixture).read_bytes().replace(b'\r\n', b'\n'))
        require(report['fixture_sha256'] == digest and report['runner_sha256'] == fixture_inputs[runner_path],
                'Savestate fixture/runner differs')
        fixture_inputs[fixture] = digest
        programs['fixture'] = digest
    else:
        raise ValueError('Mode is not one of the ten unchanged programs: ' + name)
    require(programs, 'No regenerated program')
    return dict(schema=1, job=name, mode=mode, source_inputs_sha256=source_inputs,
                baseline_inputs_sha256=baseline_inputs, fixture_inputs_sha256=fixture_inputs,
                extraction_sha256=extractions, program_variants_sha256=programs,
                generated_cpp_sha256=sorted(set(programs.values())),
                compiler_executed=False, native_executed=False)
