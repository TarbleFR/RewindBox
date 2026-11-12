#!/usr/bin/env python3
"""DRAFT, not applied on this branch: the source declaration review the probe package needs.

The application's legal gate (build-utils/embed_legal_bundle.py --validate-only, run by the freeze and by
the delivery) reads build-utils/collect_build_source_evidence.py, which binds every source declaration
to a chain of reviews: the root pubspec.yaml is one of them. Adding the probe package to pubspec.yaml is
therefore refused ("Package source/license declaration changed since review: pubspec.yaml") until a
review of that change is chained, the way every earlier pubspec change was (RewindBox Glacier, Pocket
originals): one JSON review under docs/evidence/ and one block of the collector that authenticates it.

This script writes that review from the tree it is given and shows the collector block; `apply` puts
both in place, with the notice line of the handoff (docs/s2arm-trial-ipa-handoff.md section 3) in
docs/LEGAL_AND_CREDITS.md. It changes a file of the common recipe owner (the collector), so it is run
only where that change was reviewed: it was exercised on a scratch copy, never on this branch.

    python3 -B .github/diagnostics/s2arm/legal_overlay.py show  [ROOT]   the review JSON and the block
    python3 -B .github/diagnostics/s2arm/legal_overlay.py apply ROOT     write them into ROOT
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

REVIEW = 'docs/evidence/s2arm-probe-declarations-2026-11-11.json'
COLLECTOR = 'build-utils/collect_build_source_evidence.py'
CREDITS = 'docs/LEGAL_AND_CREDITS.md'
BASELINE = 'docs/evidence/pocket-originals-declarations-2026-11-03.json'   # the last review that moved pubspec.yaml
PACKAGE_AUDIT = 'docs/evidence/package-sources-license-audit-2026-10-21.json'
PODSPEC = 'packages/s2arm_probe/ios/s2arm_probe.podspec'
PACKAGE_PUBSPEC = 'packages/s2arm_probe/pubspec.yaml'
GENERATED_DATA = 'packages/s2arm_probe/ios/Classes/S2ArmSynthModule.h'
S2ARM_COMMIT = '6b6a571553f7a687af46e03e2cdbf8ef4d77f335'
S2ARM_SOURCE = 'https://github.com/jhaizhou-ops/S2Arm'
NOTICE = ('Diagnostic data generated with the S2Arm rewriter (Apache License 2.0, Copyright 2026 S2Arm '
          'contributors, https://github.com/jhaizhou-ops/S2Arm).')
PUBSPEC_LINES = ('  - packages/s2arm_probe\n', '  s2arm_probe:\n    path: packages/s2arm_probe\n')

CONSTANT_ANCHOR = 'ARMSX2_PODSPEC = "packages/armsx2_internal_bridge/ios/armsx2_internal_bridge.podspec"\n'
CONSTANTS = (f'S2ARM_PROBE_REVIEW = "{REVIEW}"\n'
             f'S2ARM_PROBE_PODSPEC = "{PODSPEC}"\n')
# The Pocket originals review is the last one that moved pubspec.yaml: it checks the checked-out file itself,
# so it must let a later review move the file on, as the Glacier review does for it. The final loop of the
# collector still binds every declaration to the checked-out file.
PRIOR_CHECK = '''            if update.get("after") != sha256(read_input(root, root / name)):
                raise SystemExit(f"Pocket originals source/license declaration changed since review: {name}")
'''
PRIOR_CHECK_LATER = '''            # A later review overlay may move pubspec.yaml on (S2Arm probe, private test IPA only).
            if not (root / S2ARM_PROBE_REVIEW).is_file() and \\
                    update.get("after") != sha256(read_input(root, root / name)):
                raise SystemExit(f"Pocket originals source/license declaration changed since review: {name}")
'''
BLOCK_ANCHOR = '    for name, expected in declarations.items():\n'
BLOCK = f'''    # Switch 2 (S2Arm) private test IPA only: the root pubspec.yaml gains the workspace member and the path
    # dependency of the local diagnostic plugin packages/s2arm_probe (RewindBox code; its S2ArmSynthModule.h embeds
    # data generated with the S2Arm rewriter, Apache-2.0). No hosted package, engine, Core or vendored source
    # changes. The review is absent from the common line, where this block does nothing.
    s2arm_path = root / S2ARM_PROBE_REVIEW
    if s2arm_path.is_file():
        s2arm = json.loads(read_input(root, s2arm_path))
        prior_name = "{BASELINE}"
        changes = s2arm.get("dependency_changes", {{}})
        if (s2arm.get("schema") != 1 or s2arm.get("baseline_inventory") != prior_name or
                s2arm.get("baseline_inventory_sha256") != sha256(read_input(root, root / prior_name)) or
                s2arm.get("pubspec_lock_sha256") != package_audit["pubspec_lock_sha256"] or
                s2arm.get("complete_corresponding_source_attested") is not False or
                changes != {{"external_packages_added": [], "external_packages_removed": [],
                            "system_frameworks_added": {{S2ARM_PROBE_PODSPEC: ["Foundation"]}}}}):
            raise SystemExit("S2Arm probe review has a different baseline or dependency scope")
        updates = s2arm.get("declarations", {{}})
        if set(updates) != {{"pubspec.yaml", "{PACKAGE_PUBSPEC}", S2ARM_PROBE_PODSPEC}}:
            raise SystemExit("S2Arm probe declaration review scope changed")
        for name, update in updates.items():
            if update.get("before") != declarations.get(name):
                raise SystemExit(f"Wrong previous declaration identity: {{name}}")
            if update.get("after") != sha256(read_input(root, root / name)):
                raise SystemExit(f"S2Arm probe source/license declaration changed since review: {{name}}")
            declarations[name] = update["after"]
        generated = s2arm.get("embedded_generated_data", {{}})
        if (generated.get("path") != "{GENERATED_DATA}" or generated.get("license") != "Apache-2.0" or
                generated.get("sha256") != sha256(read_input(root, root / generated["path"]))):
            raise SystemExit("S2Arm probe embedded generated data differs from the review")
'''
CREDITS_SECTION = f'''
## Switch 2 (S2Arm) device probe — private test IPA only

The private test IPA of the Switch 2 line links a diagnostic probe, `packages/s2arm_probe` (RewindBox code,
repository licence; no player-facing feature). Its `S2ArmSynthModule.h` embeds, as data, about 600 bytes of AArch64
produced by the S2Arm rewriter (commit `{S2ARM_COMMIT}`) from a synthetic module written for the test. No S2Arm
source, Capstone or LZ4 is linked. {NOTICE}
'''


def require(condition, message):
    if not condition:
        raise SystemExit('legal_overlay: ' + message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def review(root):
    """The review of the probe declarations, computed from the files of `root` (the effective tree)."""
    root = Path(root)
    pubspec = (root / 'pubspec.yaml').read_text()
    before = pubspec
    for text in PUBSPEC_LINES:
        require(before.count(text) == 1, 'pubspec.yaml does not carry the probe line ' + repr(text.strip()))
        before = before.replace(text, '')
    audit = json.loads((root / PACKAGE_AUDIT).read_bytes())
    return dict(
        schema=1, review_date='2026-11-11',
        scope=('Switch 2 (S2Arm) private test IPA only, never the common IPA: the root pubspec.yaml gains the workspace '
               'member and the path dependency of the local plugin packages/s2arm_probe (RewindBox diagnostic code under '
               'the repository licence: S2ArmProbe.c/.h, S2ArmProbeGate.S, S2ArmProbePlugin.h/.m, linked statically into '
               'Runner; the pod needs Apple\'s Foundation only). S2ArmSynthModule.h embeds, as data, about 600 bytes of '
               f'AArch64 produced by the S2Arm rewriter (Apache-2.0, {S2ARM_SOURCE}, commit {S2ARM_COMMIT}) from a '
               'synthetic module written for the test; no S2Arm source, Capstone or LZ4 is linked. No hosted package, '
               'engine, Core or vendored native source change; pubspec.lock is unchanged (a workspace member is not '
               'listed there).'),
        baseline_inventory=BASELINE, baseline_inventory_sha256=sha((root / BASELINE).read_bytes()),
        pubspec_lock_sha256=audit['pubspec_lock_sha256'],
        complete_corresponding_source_attested=False,
        dependency_changes=dict(external_packages_added=[], external_packages_removed=[],
                                system_frameworks_added={PODSPEC: ['Foundation']}),
        declarations={
            'pubspec.yaml': dict(before=sha(before.encode()), after=sha(pubspec.encode())),
            PACKAGE_PUBSPEC: dict(before=None, after=sha((root / PACKAGE_PUBSPEC).read_bytes())),
            PODSPEC: dict(before=None, after=sha((root / PODSPEC).read_bytes())),
        },
        embedded_generated_data=dict(path=GENERATED_DATA, sha256=sha((root / GENERATED_DATA).read_bytes()),
                                     generator='S2Arm rewriter', source=S2ARM_SOURCE, commit=S2ARM_COMMIT,
                                     license='Apache-2.0', notice=NOTICE, notice_in=CREDITS))


def patched_collector(text):
    require(text.count(CONSTANT_ANCHOR) == 1 and text.count(BLOCK_ANCHOR) == 1 and text.count(PRIOR_CHECK) == 1 and
            'S2ARM_PROBE_REVIEW' not in text,
            COLLECTOR + ' is not the collector this draft was written for (anchors missing or already applied)')
    return (text.replace(CONSTANT_ANCHOR, CONSTANT_ANCHOR + CONSTANTS).replace(PRIOR_CHECK, PRIOR_CHECK_LATER)
            .replace(BLOCK_ANCHOR, BLOCK + BLOCK_ANCHOR))


def apply(root):
    root = Path(root)
    collector = root / COLLECTOR
    collector.write_text(patched_collector(collector.read_text()))
    credits = root / CREDITS
    text = credits.read_text()
    require(NOTICE not in text, CREDITS + ' already carries the notice')
    credits.write_text(text.rstrip('\n') + '\n' + CREDITS_SECTION)
    (root / REVIEW).write_text(json.dumps(review(root), indent=1) + '\n')
    return dict(written=[REVIEW, COLLECTOR, CREDITS])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('operation', choices=('show', 'apply'))
    parser.add_argument('root', nargs='?', type=Path)
    args = parser.parse_args(argv)
    if args.operation == 'apply':
        require(args.root is not None, 'apply needs the tree to write into')
        print(json.dumps(apply(args.root), indent=2))
        return 0
    root = args.root or Path(__file__).resolve().parents[3]
    print(json.dumps(review(root), indent=1))
    print('\n# Block inserted in ' + COLLECTOR + ' before its final declaration loop:\n' + CONSTANTS + BLOCK)
    print('# Its Pocket originals check of pubspec.yaml becomes:\n' + PRIOR_CHECK_LATER)
    print('# Section appended to ' + CREDITS + ':' + CREDITS_SECTION)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
