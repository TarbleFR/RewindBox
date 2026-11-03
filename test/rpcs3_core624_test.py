#!/usr/bin/env python3
"""Host tests of RPCS3 Core 624 = Core 621 + build-utils/rpcs3/core624-from-621.patch.

From the Build 622 iPhone logs (3 November 2026, PID 1459):

1. REWINDBOX_ZCULL_LABEL_PAGE_624 (ios/IOSZcullLabelPage.h, Emu/Cell/lv2/sys_rsx.cpp):
   with the ZCULL on-demand lever the RSX reports block is placed so that its report
   array starts on a host page; GCM label and notify reads no longer share a page with a
   report ZCULL holds locked (Assassin's Creed: 411 of 444 faults in a window were label
   reads, the lever tripped, then 4.1-4.3 s of RSX ZCULL syncs per 5 s window).
2. REWINDBOX_ZCULL_COND_PREVIOUS_624 (RSXThread.cpp): a conditional render whose query is
   still on the GPU and whose report already shows the object visible draws without
   waiting (Black Ops II multiplayer: 0.9-1.2 s of RSX waits per 5 s window); a report
   holding 0 still waits.
3. REWINDBOX_ZCULL_FAULT_CENSUS_624 (RSXZCULL.cpp, RPCS3IOSPerformance.cpp): COREPROF
   ZCULL624 per window.

This test:
- reverts core624-from-621.patch on a copy of the touched files, authenticated by the
  Core 621 SHA-256 pinned in core624-delta.json (increment_from_core621);
- runs the whole Core 621 suite (test/rpcs3_core621_test.py) on the reverted Core 621
  tree;
- runs the ZCULL on-demand guard and the real fault protocol of the Core 624 RSXZCULL.cpp
  (with the census) plain, TSan and ASan/UBSan;
- builds test/rpcs3_core624/label_page_test.cpp (placement on the PS3 layout, the
  conditional render decision, the counters) plain, TSan and ASan/UBSan;
- checks the wiring of sys_rsx.cpp and RSXThread.cpp and the ZCULL624 line arguments.
No gameplay claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT / 'test/rpcs3_core624'
DELTA = ROOT / 'build-utils/rpcs3/core624-from-621.patch'
RECORD = ROOT / 'build-utils/rpcs3/core624-delta.json'
MARKERS = ('REWINDBOX_ZCULL_LABEL_PAGE_624', 'REWINDBOX_ZCULL_COND_PREVIOUS_624', 'REWINDBOX_ZCULL_FAULT_CENSUS_624')

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core621_test as core621  # noqa: E402  (shared helpers: require, build, execute, notice_arguments)
import rpcs3_core621_zcull as zcull621  # noqa: E402

require = core621.require


def patch_files(text: str) -> list[str]:
    return sorted(set(re.findall(r'^diff --git a/(\S+) b/', text, re.M)))


def check_increment(source: Path, work: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core621']
    pinned = increment['files_before_sha256']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core624-from-621.patch differs from its record')
    files = patch_files(raw.decode('utf-8', 'surrogateescape'))
    require(files, 'core624-from-621.patch names no file')
    copy = work / 'revert624'
    for name in files:
        body = (source / name).read_text('utf-8', 'surrogateescape')
        require(any(marker in body for marker in MARKERS), f'{name} names no Core 624 marker')
        target = copy / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / name, target)
    subprocess.run(['git', 'init', '-q'], cwd=copy, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=copy,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'core624-from-621.patch does not revert: ' + result.stdout[-2000:])
    for name in files:
        reverted = copy / name
        if name in increment['new_files']:
            require(not reverted.exists() or reverted.stat().st_size == 0, f'{name} survives the revert')
            continue
        require(pinned.get(name) == hashlib.sha256(reverted.read_bytes()).hexdigest(),
                f'{name} reverted does not match its pinned Core 621 SHA-256')
    return {'files': len(files), 'new_files': increment['new_files'], 'patch_sha256': hashlib.sha256(raw).hexdigest(),
            'authenticated_by': 'pinned_sha256'}


def core621_tree(source: Path, work: Path) -> Path:
    """The Core 621 tree: the rpcs3 directory of the source with the 624 increment reverted."""
    tree = work / 'core621'
    shutil.copytree(source / 'rpcs3', tree / 'rpcs3', symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 621 tree cannot be rebuilt: ' + result.stdout[-2000:])
    require(not (tree / 'rpcs3/ios/IOSZcullLabelPage.h').exists(), 'the Core 624 header survives in the Core 621 tree')
    return tree


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    report: dict = {'cxx': args.cxx}
    plain = ['-O2', '-Wall', '-Wextra', '-Werror']
    asan = ['-O1', '-g', '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=undefined']
    tsan = ['-O1', '-g', '-fsanitize=thread'] + (['-Wno-tsan'] if 'clang' not in Path(args.cxx).name and 'g++' in Path(args.cxx).name else [])
    sanitize = not args.no_sanitizers
    with tempfile.TemporaryDirectory(prefix='core624-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source, work)

        print('core 621 suite on the reverted tree')
        tree = core621_tree(source, work)
        command = [sys.executable, str(ROOT / 'test/rpcs3_core621_test.py'), '--source', str(tree), '--cxx', args.cxx,
                   '--report', str(work / 'core621.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=3600)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 621' in result.stdout, 'the Core 621 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core621'] = json.loads((work / 'core621.json').read_text())

        print('zcull on demand on the Core 624 tree (fault census)')
        report['zcull_on_demand'] = zcull621.run(
            source, [args.cxx], {'plain': [], 'tsan': [f for f in tsan if f not in ('-O1', '-g')],
                                 'asan': ['-fsanitize=address,undefined', '-fno-sanitize-recover=all']},
            work, sanitize)
        require(zcull621.WITH_LABEL_PAGE_HEADER, 'the Core 624 fault path was built without its header')

        print('reports block placement and conditional render decision')
        core_include = source / 'rpcs3'
        binary = work / 'label_page'
        core621.build(args.cxx, [HERE / 'label_page_test.cpp'], binary, [core_include], plain)
        output = core621.execute([str(binary)], 'label page (plain)')
        report['label_page'] = json.loads(output.strip().splitlines()[-1])
        if sanitize:
            core621.build(args.cxx, [HERE / 'label_page_test.cpp'], work / 'label_page_tsan', [core_include], tsan)
            core621.execute([str(work / 'label_page_tsan')], 'label page (TSan)', env=dict(os.environ, TSAN_OPTIONS='halt_on_error=1'))
            core621.build(args.cxx, [HERE / 'label_page_test.cpp'], work / 'label_page_asan', [core_include], asan)
            core621.execute([str(work / 'label_page_asan')], 'label page (ASan/UBSan)')

        print('wiring')
        rsx = (core_include / 'Emu/Cell/lv2/sys_rsx.cpp').read_text()
        allocate = rsx[rsx.index('error_code sys_rsx_context_allocate('):]
        allocate = allocate[:allocate.index('\nerror_code ')]
        require(allocate.index('*lpar_reports = dma_address + 0x200000;') <
                allocate.index('if (rpcs3::ios::get_experimental_policy().zcull_on_demand)') <
                allocate.index('rpcs3::ios::zcull_label_page::offset(::offset32(&RsxReports::report), static_cast<u32>(utils::get_page_size()))') <
                allocate.index('ensure(shift + sizeof(RsxReports) <= 0x100000);') <
                allocate.index('*lpar_reports += shift;') <
                allocate.index('auto &reports = *vm::_ptr<RsxReports>(vm::cast(*lpar_reports));') <
                allocate.index('render->label_addr = vm::cast(*lpar_reports);'),
                'the reports block is not shifted before it is initialised and handed to the RSX')
        require(allocate.count('*lpar_reports') == 5, 'another use of lpar_reports in sys_rsx_context_allocate')
        thread = (core_include / 'Emu/RSX/RSXThread.cpp').read_text()
        begin = thread[thread.index('void thread::begin()'):]
        begin = begin[:begin.index('in_begin_end = true;')]
        require(begin.index('zcull_ctrl->check_occlusion_query_status(cond_render_ctrl.eval_sources.front())') <
                begin.index('cond_previous::decide(rpcs3::ios::get_experimental_policy().zcull_on_demand, ios_ready,') <
                begin.index('vm::get_super_ptr<CellGcmReportData>(cond_render_ctrl.eval_address)->value') <
                begin.index('cond_render_ctrl.set_eval_result(this, false);') <
                begin.index('zcull_ctrl->read_barrier(this, cond_render_ctrl.eval_address, cond_render_ctrl.eval_sources.front());') <
                begin.index('ensure(!cond_render_ctrl.eval_pending());'),
                'conditional render: decision, early draw and the upstream wait in that order')
        require(begin.count('set_eval_result(this, false)') == 1 and 'supports_hw_conditional_render' in begin,
                'the early draw is only for the CPU-evaluated path')
        zcull = (core_include / 'Emu/RSX/RSXZCULL.cpp').read_text()
        require('(fault_spu ? census.spu : census.ppu).fetch_add(1, std::memory_order_relaxed);' in zcull and
                'census.other_last.store(address, std::memory_order_relaxed);' in zcull, 'the fault census')
        performance = (core_include / 'ios/RPCS3IOSPerformance.cpp').read_text()
        conversions, arguments = core621.notice_arguments(performance, 'COREPROF ZCULL624 ')
        require(conversions == arguments == 11, f'ZCULL624 line has {conversions} conversions for {arguments} arguments')
        prefetch = performance.index('// REWINDBOX_SPU_OBJECT_PREFETCH_616')
        require(performance.index('COREPROF ZCULL624 ') > prefetch, 'the ZCULL624 block must not enter the ZCULLDEMAND619 probe')
        report['wiring'] = {'zcull624_conversions': conversions}

    print('PASS: Core 624 increment reverts to Core 621; the Core 621 suite on that tree; ZCULL fault protocol with the '
          'census; reports block placement and conditional render decision (TSan/ASan); wiring')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
