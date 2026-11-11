#!/usr/bin/env python3
"""Host test of the Core 926 Black Ops II FPS levers on a materialized Core source.

IPA 724 logs (10 November 2026), Call of Duty: Black Ops II (BLES01717, pid 50194, session 8), at 60 Hz: 52 % of the
frames take two vblanks (31-36 ms) and 11 % one; the RSX thread of each sampled frame spends 4.2-4.7 ms encoding Metal
command buffers (FRAMECAUSE_EVENT rsx_submit_ms, wait_dominant=submit_encode) and the texture stage 5.5-6.4 ms.

REWINDBOX_MVK_ASYNC_RETRY_926 (ios/IOSMoltenVKAsyncCanary.h): with asynchronous MoltenVK submits (build 662, pids 13540
and 13941, 75 play windows) RSXSYNC551 submit costs 0.05 ms per frame; without them (builds 694, 723, 724) 3.5-4.8 ms.
Every Black Ops II boot since build 676 is canary=failed_before: one 662 boot, among those of the 9-40 s PUTLLC stalls
later corrected by Cores 664 and 924, ended while armed. A new record file gives each title the second try of the
canary rule, with the same protection (a boot that ends while armed marks the title failed again).

REWINDBOX_TEXMEMO_SERVE_BO2_926 (ios/IOSTitleLevers.h): Black Ops II ran the texture lookup memo in verify_all mode on
builds 662, 676, 721, 723 and 724: 4,676,476 reuses looked up in full and compared, 0 differences, never disabled. Its
hits are now served with the sampled verification of the served titles.

This test checks the source and compiles test/native/rpcs3_fps_levers926_model.cpp against the real headers: the
title levers for the titles concerned, and the canary rule run on a record file of the 627 cell that marks Black Ops
II and God of War III failed (the 926 cell does not read it: both run; a 926 boot that ends while armed fails again).
No iPhone or FPS result is inferred.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODEL = ROOT / 'test/native/rpcs3_fps_levers926_model.cpp'
LEVERS = 'rpcs3/ios/IOSTitleLevers.h'
CANARY = 'rpcs3/ios/IOSMoltenVKAsyncCanary.h'
POLICY = 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp'
SETTINGS = 'rpcs3/ios/RPCS3IOSSettings.cpp'


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def read(source: Path, rel: str) -> str:
    return (source / rel).read_bytes().decode('utf-8').replace('\r\n', '\n')


def source_checks(source: Path) -> dict:
    levers = read(source, LEVERS)
    require('constexpr bool serves_texture_lookup_memo(std::string_view title_id) noexcept\n{\n'
            '\treturn is_assassins_creed_title(title_id) || is_black_ops_ii_title(title_id);\n}' in levers, 'Black Ops II served')
    require('constexpr bool verifies_texture_lookup_memo(std::string_view title_id) noexcept\n{\n'
            '\tstatic_cast<void>(title_id);\n\treturn false;\n}' in levers, 'no title only verified')
    require('REWINDBOX_TEXMEMO_SERVE_BO2_926' in levers, 'marker')
    canary = read(source, CANARY)
    require('inline constexpr std::string_view file_name = "rewindbox-mvk-async-926.txt";' in canary, 'new record file')
    require('REWINDBOX_MVK_ASYNC_RETRY_926' in canary and 'inline constexpr std::uint32_t confirm_presents = 900;' in canary,
            'marker; the confirmation rule is unchanged')
    policy = read(source, POLICY)
    require('return fs::get_config_dir() + std::string(mvk_async_canary::file_name);' in policy, 'the record path is the file name')
    require('rpcs3::ios::title_levers::joins_mvk_async_automatic_619(title_id) || // REWINDBOX_BO2_MVK_ASYNC_619' in policy,
            'Black Ops II still asks for asynchronous submits in Automatic')
    memo = policy[policy.index('namespace memo = rpcs3::ios::texture_lookup_memo;'):policy.index('memo::configure(memo_mode);')]
    require('memo_setting == ios_experimental_mode::enabled || rpcs3::ios::title_levers::serves_texture_lookup_memo(title_id)' in memo and
            'memo_setting != ios_experimental_mode::disabled' in memo, 'the per-game setting still decides')
    settings = read(source, SETTINGS)
    require("Automatic enables it for Assassin's Creed and Call of Duty: Black Ops II;" in settings, 'setting text')
    # The memo's own protection is unchanged.
    memo_h = read(source, 'rpcs3/ios/IOSTextureLookupMemo.h')
    require('constexpr std::uint64_t verify_first = 256;' in memo_h and 'constexpr std::uint64_t verify_period = 64;' in memo_h,
            'sampled verification unchanged')
    return {'record_file': 'rewindbox-mvk-async-926.txt'}


def run_model(source: Path, cxx: str) -> dict:
    with tempfile.TemporaryDirectory(prefix='levers926-') as tmp:
        binary = Path(tmp) / 'model'
        build = subprocess.run([cxx, '-std=c++20', '-Wall', '-Wextra', '-I', str(source / 'rpcs3'), str(MODEL), '-o', str(binary)],
                               capture_output=True, text=True)
        require(build.returncode == 0, 'model build failed:\n' + build.stderr[-4000:])
        result = subprocess.run([str(binary)], capture_output=True, text=True, timeout=120)
        require(result.returncode == 0, f'model failed ({result.returncode}):\n' + result.stderr[-4000:])
        report = json.loads(result.stdout)
        require(report['passed'] is True, 'model report')
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    report = {'test': 'rpcs3_fps_levers926', 'source_checks': source_checks(source), 'model': run_model(source, args.cxx),
              'iphone_tested': False, 'fps_claimed': False}
    report['result'] = 'passed'
    text = json.dumps(report, indent=2)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(text + '\n')
    print(text)
    print('PASS: Core 926 Black Ops II FPS levers (texture lookup memo served, MoltenVK canary retried)')


if __name__ == '__main__':
    main()
