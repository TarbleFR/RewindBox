#!/usr/bin/env python3
"""Which delivered native harness results still describe the Core 610 sources.

Core a4ae86d0 (delivered 607/608) reused twelve authenticated Apple modes: six
harnesses in plain and ASan/UBSan form. Each harness compiles production code it
extracts from the Core. A result can be reused for 610 only when every extracted
production body is byte-identical between the delivered tree and the 610 tree;
otherwise the harness is affected and needs its own new execution or proof.
This audit extracts the same bodies the harnesses extract and classifies them.
It runs no compiler and claims no new native execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def block(text: str, marker: str) -> str:
    start = text.index(marker)
    pos = text.index('{', start)
    depth = 0
    for end in range(pos, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            return text[start:end + 1]
    raise ValueError(marker)


def whole(rel):
    return lambda tree: (tree / rel).read_text()


def part(rel, marker):
    return lambda tree: block((tree / rel).read_text(), marker)


def between(rel, start, end):
    return lambda tree: (lambda t: t[t.index(start):t.index(end)])((tree / rel).read_text())


HARNESSES = {
    'color-feedback': {'test': 'test/rpcs3_color_feedback_test.py',
                       'inputs': {'VKDraw.cpp': whole('rpcs3/Emu/RSX/VK/VKDraw.cpp')}},
    'tiny-vertex': {'test': 'test/rpcs3_tiny_vertex_cache_test.py',
                    'inputs': {'rsx_cache.h vertex_cache': part('rpcs3/Emu/RSX/rsx_cache.h', 'namespace vertex_cache')}},
    'vertex-range': {'test': 'test/rpcs3_device597/renderer/test_vertex_upload_key.py',
                     'inputs': {'VKVertexBuffers.cpp': whole('rpcs3/Emu/RSX/VK/VKVertexBuffers.cpp'),
                                'rsx_cache.h vertex_cache': part('rpcs3/Emu/RSX/rsx_cache.h', 'namespace vertex_cache'),
                                'RSXThread.cpp calculate_required_range': part('rpcs3/Emu/RSX/RSXThread.cpp',
                                    'std::pair<u32, u32> interleaved_range_info::calculate_required_range'),
                                'RSXVertexTypes.h': whole('rpcs3/Emu/RSX/Core/RSXVertexTypes.h'),
                                'RSXDrawCommands.cpp': whole('rpcs3/Emu/RSX/Core/RSXDrawCommands.cpp'),
                                'IOSRendererCausality.h': whole('rpcs3/ios/IOSRendererCausality.h')}},
    'savestate-completion': {'test': 'test/rpcs3_savestate_completion601_test.py',
                             'inputs': {'NeoStationSavestateStatus.h': whole('rpcs3/ios/NeoStationSavestateStatus.h')}},
    'exitspawn-worker': {'test': 'test/rpcs3_exitspawn_worker601_test.py',
                         'inputs': {'lv2_exitspawn': between('rpcs3/Emu/Cell/lv2/sys_process.cpp', 'void lv2_exitspawn(', 'void sys_process_exit3('),
                                    'transition wrappers': between('rpcs3/ios/RPCS3IOS.cpp', 'namespace\n{\nstruct continuous_stop_request',
                                                                   '[[noreturn]] void report_fatal_error'),
                                    'IOSRestoreExecutor.h': whole('rpcs3/ios/IOSRestoreExecutor.h'),
                                    'NeoStationSavestateStatus.h': whole('rpcs3/ios/NeoStationSavestateStatus.h')},
                         'replacement': ['test/rpcs3_exitspawn_worker610_test.py (plain and ASan/UBSan, new execution)']},
    'mfc-decrementer': {'test': 'test/rpcs3_spu_mfc_decrementer_test.py',
                        'inputs': {'process_mfc_cmd': part('rpcs3/Emu/Cell/SPUThread.cpp', 'bool spu_thread::process_mfc_cmd()')},
                        'replacement': ['test/rpcs3_spu_mfc_lr_test.py unarmed projection equals the delivered prefix',
                                        'test/rpcs3_spu_mfc_lr_test.py candidate harness (60 checks, decrementer cases included)']},
}


def audit(source: Path, baseline: Path) -> dict:
    result = {}
    for name, harness in HARNESSES.items():
        changed, digests = [], {}
        for label, extract in harness['inputs'].items():
            before, after = extract(baseline), extract(source)
            digests[label] = {'delivered': sha(before.encode()), 'core610': sha(after.encode())}
            if before != after:
                changed.append(label)
        entry = {'test': harness['test'], 'changed_extracted_inputs': changed, 'inputs': digests,
                 'delivered_result_reusable': not changed}
        if changed:
            if 'replacement' not in harness:
                raise AssertionError(f'{name}: extracted inputs changed without replacement evidence: {changed}')
            entry['replacement_evidence'] = harness['replacement']
        result[name] = entry
    expected_affected = {'exitspawn-worker', 'mfc-decrementer'}
    affected = {name for name, entry in result.items() if entry['changed_extracted_inputs']}
    if affected != expected_affected:
        raise AssertionError(f'affected harnesses differ from the reviewed set: {sorted(affected)}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    report = {'schema': 1, 'harnesses': audit(args.source, args.baseline), 'native_execution_claimed': False}
    text = json.dumps(report, indent=2, sort_keys=True) + '\n'
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text)
    print(text)
    print('PASS')


if __name__ == '__main__':
    main()
