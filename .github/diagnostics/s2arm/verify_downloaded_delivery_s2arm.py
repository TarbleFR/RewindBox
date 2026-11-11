#!/usr/bin/env python3
"""Offline verification of a downloaded Switch 2 (S2Arm) test IPA delivery.

build-utils/verify_downloaded_delivery.py, unchanged, run on the recipe module configured for this line
(.github/diagnostics/s2arm/standard_delivery_s2arm.py): the saved run must be a run of this line's
workflow on this line's branch requesting the build with this line's tag, and the base is authenticated
on the branch of the line that delivered it. Same arguments as the common verifier:

    python3 -B .github/diagnostics/s2arm/verify_downloaded_delivery_s2arm.py --build 801 --parts DIR \\
        --api DIR --key /private/delivery-801.key --work EMPTY_DIR --report REPORT.json

After the common checks pass, the decrypted IPA is checked for the delta of this line: the Info.plist
boolean RewindBoxS2ArmProbe, no RewindBoxS2ArmProbeMapped, the probe class and entry points defined in
the Runner executable, no separate probe image. The result is added to the report under "s2armProbe".
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import standard_delivery_s2arm as line  # noqa: E402


def load_verifier():
    """The common verifier, bound to the recipe module configured for this line."""
    sd = line.configure()
    line.check_verifier_inventory()
    for part in ('build-utils', 'build-utils/s2arm'):
        if str(ROOT / part) not in sys.path:
            sys.path.insert(0, str(ROOT / part))
    verifier = importlib.import_module('verify_downloaded_delivery')
    line.require(verifier.sd is sd and verifier.sd.BRANCH == line.DELIVERY_BRANCH and
                 verifier.sd.WORKFLOW == line.WORKFLOW, 'The verifier is not bound to the configured recipe')
    return verifier


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument('--build', type=int)
    parser.add_argument('--work', type=Path)
    parser.add_argument('--report', type=Path)
    known, _ = parser.parse_known_args(argv)
    verifier = load_verifier()
    sys.argv = [sys.argv[0], *argv]
    verifier.main()
    probe = importlib.import_module('set_probe_key')
    report = json.loads(known.report.read_bytes())
    ipa = known.work / 'delivery' / report['ipa']['name']
    try:
        result = probe.check_ipa(ipa)
    except probe.ProbeError as error:
        raise SystemExit('VERIFICATION FAILED: ' + str(error))
    report['s2armProbe'] = dict(result, ipa=report['ipa']['name'], ipaSHA256=report['ipa']['sha256'])
    known.report.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(dict(s2armProbe=report['s2armProbe']), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
