#!/usr/bin/env python3
"""Host tests of RPCS3 Core 652 = Core 651 + build-utils/rpcs3/core652-from-651.patch.

Core 652 (iOS, Vulkan render targets and render passes; Assassin's Creed IPA 643: 51 render passes per frame, 1104
cyclic depth barriers against 635 skipped in 127 frames, each inserted barrier ending the pass):
- REWINDBOX_DEPTH_TEST_OFF_READ_ONLY_652: a draw with the depth test off and no stencil write is read-only for the
  cyclic depth barriers, as a masked one already was (RSX zeta_write_enabled and VKGSRender depthWriteEnable agree);
  two counters on the TEXCACHE621 line;
- REWINDBOX_DEPTH_READ_CHAIN_652: a skipped read counts in image_reference_sync_barrier, so read-only chains keep one
  barrier instead of one every other draw;
- REWINDBOX_RENDERPASS_CENSUS_652: vk::end_renderpass records its caller's site, vk::begin_renderpass attributes each
  begun pass to the previous end (same or other framebuffer); one COREPROF RPASS652 line per window.
This driver:
- authenticates the increment against its record and reverts it to the pinned Core 651 files;
- checks the source: only these rules, counters and log fields;
- runs test/rpcs3_depth_test_off_read_only652_test.py (real barrier code of both trees, hazard checker) on the
  reverted Core 651 tree (control) and this tree (candidate), and test/rpcs3_renderpass_census652_test.py (real
  begin/end functions, unchanged Vulkan command stream) on this tree;
- runs the Core 651 suite on the reverted tree (which runs the 645, 641, 638, 636, 634, 630 and 627 suites in turn).
No rendering, gameplay, iPhone or FPS claim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DELTA = ROOT / 'build-utils/rpcs3/core652-from-651.patch'
RECORD = ROOT / 'build-utils/rpcs3/core652-delta.json'
FILES = ('rpcs3/Emu/RSX/VK/VKRenderPass.cpp', 'rpcs3/Emu/RSX/VK/VKRenderPass.h', 'rpcs3/Emu/RSX/VK/VKRenderTargets.cpp',
         'rpcs3/ios/IOSRenderPassCensus.h', 'rpcs3/ios/IOSTextureCacheProfile.h', 'rpcs3/ios/RPCS3IOSPerformance.cpp')
NEW = ('rpcs3/ios/IOSRenderPassCensus.h',)
MARKS = ('REWINDBOX_DEPTH_TEST_OFF_READ_ONLY_652', 'REWINDBOX_DEPTH_READ_CHAIN_652', 'REWINDBOX_RENDERPASS_CENSUS_652')

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha, build, execute, last_json)

require = core636.require


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core651']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core652-from-651.patch differs from its record')
    text = raw.decode('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)
    require(sorted(files) == sorted(FILES) == sorted(increment['files_after_sha256']) and increment['files'] == 6 and
            increment['new_files'] == list(NEW), 'core652 files')
    removed = [line[1:].strip() for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    added = [line[1:].strip() for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')]
    # Replaced lines: the two read-only predicates, the TEXCACHE621 format tail and its arguments, the end_renderpass
    # declaration (now under #else) and nothing else.
    require(sorted(removed) == sorted([
        'const auto is_framebuffer_read_only = is_depth_surface() && !rsx::method_registers.depth_write_enabled();',
        'const bool is_framebuffer_read_only = is_depth_surface() && !rsx::method_registers.depth_write_enabled();',
        '"feedback_barriers=%llu feedback_skipped=%llu post_barriers=%llu post_skipped=%llu scope=process_window_counters",',
        'static_cast<u64>(c.unreleased.load(std::memory_order_relaxed)), fb, fb_skip, post, post_skip);']),
        'replaced lines: ' + repr(removed))
    for mark in MARKS:
        require(any(mark in line for line in added), mark + ' is not marked')
    code = [line for line in added if line and not line.startswith('//')]
    require('static bool rewindbox_depth_test_off_zeta_unwritten()' in code and
            'm_cyclic_ref_tracker.on_insert_texture_barrier();' in code and 'm_cyclic_ref_tracker.allow_skip();' in code,
            'the read-only rule and the chain count')
    require('void end_renderpass(const vk::command_buffer& cmd, std::source_location where = std::source_location::current());' in code
            and any('renderpass_census::on_begin(g_rewindbox_last_end[cmd], target);' in line for line in code)
            and any('renderpass_census::on_end(g_rewindbox_last_end[cmd], g_current_renderpass[cmd].fbo' in line for line in code),
            'the census hooks')
    for name in files:
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 652 file')
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'added_code_lines': len(code)}


def core651_tree(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core651']
    tree = work / 'core651'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 651 tree cannot be rebuilt: ' + result.stdout[-2000:])
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 651 SHA-256')
    for name in NEW:
        require(not (tree / name).exists(), name + ' survives the revert')
    return tree


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--cxx', default='g++')
    parser.add_argument('--report', type=Path)
    parser.add_argument('--no-sanitizers', action='store_true')
    args = parser.parse_args()
    source = args.source.resolve()
    sanitize = not args.no_sanitizers
    report: dict = {'cxx': args.cxx}
    with tempfile.TemporaryDirectory(prefix='core652-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        tree651 = core651_tree(source, work)
        require(all(mark not in (tree651 / FILES[2]).read_text('utf-8', 'surrogateescape') for mark in MARKS[:2]),
                'the Core 651 tree already has the change')
        print('cyclic depth barriers: real code, control 651 and candidate 652')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'test/rpcs3_depth_test_off_read_only652_test.py'), '--control', str(tree651),
                                 '--candidate', str(source), '--cxx', args.cxx, '--report', str(work / 'depth-barriers.json')],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800)
        require(result.returncode == 0, 'cyclic depth barrier test fails:\n' + result.stdout[-3000:])
        report['depthBarriers'] = json.loads((work / 'depth-barriers.json').read_text())['summary']
        print('render pass census: real begin/end functions')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'test/rpcs3_renderpass_census652_test.py'), '--source', str(source),
                                 '--cxx', args.cxx, '--report', str(work / 'census.json')],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
        require(result.returncode == 0, 'render pass census test fails:\n' + result.stdout[-3000:])
        report['census'] = json.loads((work / 'census.json').read_text())['totals']
        print('core 651 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core651_test.py'), '--source', str(tree651), '--cxx', args.cxx,
                   '--report', str(work / 'core651.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 651' in result.stdout, 'the Core 651 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core651'] = json.loads((work / 'core651.json').read_text())
    print('PASS: Core 652 increment reverts to Core 651; read-only cyclic depth chains keep one barrier (test-off draws '
          'included, no hazard on the real code); the render pass census leaves the command stream unchanged; the Core 651 '
          'suite on that tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
