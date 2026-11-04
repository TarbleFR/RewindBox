#!/usr/bin/env python3
"""Host tests of RPCS3 Core 655 = Core 652 + build-utils/rpcs3/core655-from-652.patch.

Core 655 (iOS, Vulkan render passes; Assassin's Creed IPA 653: 44-53 passes begun per frame, 4-11 of them after
vk::change_image_layout ended the pass and the next draw began the same framebuffer again):
- REWINDBOX_IN_PASS_READ_TRANSITION_655: a transition to SHADER_READ_ONLY_OPTIMAL of an image that is not an attachment
  of the open render pass (attachments noted by the draw path), from an attachment or transfer layout with the standard
  masks and no queue family transfer, is recorded inside the pass; Assassin's Creed only, and only when the linked
  MoltenVK defines rbx_mvk_in_pass_read_barrier_waits (its in-pass fence wait); COREPROF RPASS655 per window.
This driver:
- authenticates the increment against its record (insertions only) and reverts it to the pinned Core 652 files;
- checks the source: the decision, the registry, the policy (title and MoltenVK hook) and the reporter;
- runs test/rpcs3_in_pass_read_transition655_test.py (real render pass and layout code of both trees, ASan and UBSan);
- runs the Core 652 suite on the reverted tree (which runs the 651, 645, 641, 638, 636, 634, 630 and 627 suites in turn).
The MoltenVK side is tested by test/rpcs3_moltenvk_in_pass_read_wait_test.py in the dependency route.
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
DELTA = ROOT / 'build-utils/rpcs3/core655-from-652.patch'
RECORD = ROOT / 'build-utils/rpcs3/core655-delta.json'
FILES = ('rpcs3/Emu/RSX/VK/VKDraw.cpp', 'rpcs3/Emu/RSX/VK/VKRenderPass.cpp', 'rpcs3/Emu/RSX/VK/VKRenderPass.h',
         'rpcs3/Emu/RSX/VK/vkutils/image_helpers.cpp', 'rpcs3/ios/IOSInPassReadTransition.h',
         'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp', 'rpcs3/ios/RPCS3IOSExperimentalPolicy.h', 'rpcs3/ios/RPCS3IOSPerformance.cpp')
NEW = ('rpcs3/ios/IOSInPassReadTransition.h',)
MARK = 'REWINDBOX_IN_PASS_READ_TRANSITION_655'

sys.path.insert(0, str(ROOT / 'test'))
import rpcs3_core636_test as core636  # noqa: E402  (require, lf_sha, build, execute, last_json)

require = core636.require


def check_increment(source: Path) -> dict:
    increment = json.loads(RECORD.read_text())['increment_from_core652']
    raw = DELTA.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == increment['patch_sha256'], 'core655-from-652.patch differs from its record')
    text = raw.decode('utf-8', 'surrogateescape')
    files = re.findall(r'^diff --git a/(\S+) b/\S+$', text, re.M)
    require(sorted(files) == sorted(FILES) == sorted(increment['files_after_sha256']) and increment['files'] == 8 and
            increment['new_files'] == list(NEW) and increment['insertions_only'] is True, 'core655 files')
    removed = [line for line in text.splitlines() if line.startswith('-') and not line.startswith('---')]
    require(not removed, 'Core 655 only inserts lines: ' + repr(removed[:3]))
    added = [line[1:].strip() for line in text.splitlines() if line.startswith('+') and not line.startswith('+++')]
    require(any(MARK in line for line in added), MARK + ' is not marked')
    code = [line for line in added if line and not line.startswith('//')]
    for needle in ('if (!rewindbox_keep_pass_for_read_transition(cmd, image, current_layout, new_layout, src_queue_family, dst_queue_family,',
                   'if (new_layout != VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL)',
                   'src_access_mask_bits != ~0u || dst_access_mask_bits != ~0u)',
                   'case vk::open_pass_image::not_attachment:',
                   'vk::note_renderpass_attachments(*m_current_command_buffer, m_draw_fbo->value, images.data(), count);',
                   'g_rewindbox_open_attachments[cmd] = {}; // REWINDBOX_IN_PASS_READ_TRANSITION_655: unknown until the draw path notes them',
                   'resolved.moltenvk_in_pass_waits = rpcs3::ios::in_pass_read::moltenvk_waits_in_pass();',
                   'rpcs3::ios::title_levers::is_assassins_creed_title(title_id);',
                   'rpcs3::ios::in_pass_read::enabled.store(resolved.in_pass_read_transitions, std::memory_order_relaxed);',
                   'extern "C" __attribute__((weak)) int rbx_mvk_in_pass_read_barrier_waits(void);'):
        require(any(needle in line for line in code), 'missing from the increment: ' + needle)
    # The policy enables the lever only with the MoltenVK hook, for Assassin's Creed.
    policy = (source / 'rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp').read_text()
    require(policy.count('resolved.in_pass_read_transitions = resolved.moltenvk_in_pass_waits &&') == 1, 'the lever needs the MoltenVK hook')
    performance = (source / 'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    line = performance[performance.index('"COREPROF RPASS655 session=%llu'):performance.index('scope=process_window_counters",', performance.index('"COREPROF RPASS655 session=%llu'))]
    require(line.count('%') == 11, 'the RPASS655 format has eleven conversions')
    for name in files:
        require(core636.lf_sha(source / name) == increment['files_after_sha256'][name], name + ' is not the reviewed Core 655 file')
    return {'files': len(files), 'patch_sha256': increment['patch_sha256'], 'added_code_lines': len(code)}


def core652_tree(source: Path, work: Path) -> Path:
    increment = json.loads(RECORD.read_text())['increment_from_core652']
    tree = work / 'core652'
    shutil.copytree(source, tree, ignore=shutil.ignore_patterns('.git', '3rdparty'), symlinks=True)
    subprocess.run(['git', 'init', '-q'], cwd=tree, check=True)
    result = subprocess.run(['git', 'apply', '-R', '--whitespace=nowarn', str(DELTA)], cwd=tree,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    require(result.returncode == 0, 'the Core 652 tree cannot be rebuilt: ' + result.stdout[-2000:])
    for name, digest in increment['files_before_sha256'].items():
        require(core636.lf_sha(tree / name) == digest, name + ' reverted does not match its pinned Core 652 SHA-256')
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
    with tempfile.TemporaryDirectory(prefix='core655-') as temporary:
        work = Path(temporary)
        print('increment')
        report['increment'] = check_increment(source)
        tree652 = core652_tree(source, work)
        require(MARK not in (tree652 / FILES[3]).read_text('utf-8', 'surrogateescape'), 'the Core 652 tree already has the change')
        print('in-pass read transitions: real code, control 652 and candidate 655')
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'test/rpcs3_in_pass_read_transition655_test.py'), '--candidate', str(source),
                                 '--control', str(tree652), '--cxx', args.cxx, '--report', str(work / 'in-pass.json')],
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=1800)
        require(result.returncode == 0, 'in-pass read transition test fails:\n' + result.stdout[-3000:])
        report['inPassReadTransitions'] = json.loads((work / 'in-pass.json').read_text())
        print('core 652 suite on the reverted tree')
        command = [sys.executable, str(ROOT / 'test/rpcs3_core652_test.py'), '--source', str(tree652), '--cxx', args.cxx,
                   '--report', str(work / 'core652.json')] + (['--no-sanitizers'] if not sanitize else [])
        result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=7200)
        print('  ' + '\n  '.join(result.stdout.strip().splitlines()[-3:]))
        require(result.returncode == 0 and 'PASS: Core 652' in result.stdout, 'the Core 652 suite fails on the reverted tree:\n' + result.stdout[-3000:])
        report['core652'] = json.loads((work / 'core652.json').read_text())
    print('PASS: Core 655 increment reverts to Core 652; read transitions of non-attachments stay inside the open pass '
          '(every other case ends it as Core 652; barriers identical); the Core 652 suite on that tree')
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
