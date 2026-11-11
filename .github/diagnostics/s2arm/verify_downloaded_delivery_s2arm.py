#!/usr/bin/env python3
"""Offline verification of a downloaded Switch 2 (S2Arm) test IPA delivery.

build-utils/verify_downloaded_delivery.py, run on the recipe module configured for this line
(.github/diagnostics/s2arm/standard_delivery_s2arm.py): the saved run must be a run of this line's
workflow on this line's branch requesting the build with this line's tag, and the base is authenticated
on the branch of the line that delivered it. Same arguments as the common verifier:

    python3 -B .github/diagnostics/s2arm/verify_downloaded_delivery_s2arm.py --build 801 --parts DIR \\
        --api DIR --key /private/delivery-801.key --work EMPTY_DIR --report REPORT.json

The common verifier runs unchanged: its count of the application's extensions has its own S2Arm
conditional (an application that carries S2Arm-native-identity.json has S2ArmJITHelper.appex as eighth
extension), so nothing of it is edited in memory.

After the common checks pass, the decrypted IPA is checked for the delta of this line: the Info.plist
boolean RewindBoxS2ArmProbe, no RewindBoxS2ArmProbeMapped, the probe class and entry points defined in
the Runner executable, no separate probe image ("s2armProbe" in the report); and, when the build's
manifest declares the engine (s2arm.engine), the engine frameworks, their packaged identity against the
manifest and the JIT helper against the effective source ("s2armEngine"), with the engine bridge offline
against the manifest's s2arm.prepare and s2arm.sysdata: the preparation library the identity records (run,
archive digest) and its entry points linked into the Runner executable (defined, none left undefined,
rb_s2arm_engine_loaded exported), S2ArmSystemData complete against the SHA256SUMS the manifest names, with
its licences, and S2ArmEngine.framework/S2ArmDirectChain.txt. An IPA and a manifest that disagree on the
engine or on its bridge are refused.
"""
from __future__ import annotations

import argparse
import importlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))

import standard_delivery_s2arm as line  # noqa: E402


def load_verifier():
    """The common verifier, unchanged, bound to the recipe module configured for this line."""
    sd = line.configure()
    line.check_verifier_inventory()
    for part in ('build-utils', 'build-utils/s2arm'):
        if str(ROOT / part) not in sys.path:
            sys.path.insert(0, str(ROOT / part))
    verifier = importlib.import_module('verify_downloaded_delivery')
    line.require(Path(verifier.__file__).resolve() == (ROOT / line.VERIFIER).resolve() and verifier.sd is sd and
                 verifier.sd.BRANCH == line.DELIVERY_BRANCH and verifier.sd.WORKFLOW == line.WORKFLOW,
                 'The verifier is not the common file bound to the configured recipe')
    return verifier


def engine_check(ipa, report, work, repo=None):
    """The engine of a downloaded IPA against the delivered manifest (None when neither carries one)."""
    sd = line.configure()
    manifest = json.loads((repo or sd.Repo(ROOT)).show(report['execution']['source'], report['manifest']['path']))
    with zipfile.ZipFile(ipa) as archive:
        names = archive.namelist()
    carries = 'Payload/NeoStation.app/' + line.PACKAGED_IDENTITY in names
    declared = manifest.get('s2arm', {}).get('engine') is not None
    line.require(carries == declared, f'The IPA {"carries" if carries else "lacks"} the S2Arm engine, its manifest '
                 f'{"declares" if declared else "does not declare"} it')
    if not carries:
        bridge = sorted(key for key in ('prepare', 'sysdata') if manifest.get('s2arm', {}).get(key) is not None)
        line.require(not bridge and not any(name.startswith('Payload/NeoStation.app/' + line.SYSTEM_DATA + '/')
                                            for name in names),
                     'An IPA without the S2Arm engine carries its bridge: S2ArmSystemData in the IPA, or s2arm.prepare '
                     f'or s2arm.sysdata in its manifest {bridge}')
        return None
    script = (Path(work) / 'effective-tree' / line.HELPER_SCRIPT).read_bytes()
    return line.check_engine_ipa(ipa, line.engine_spec(manifest), script, prepare=line.prepare_spec(manifest),
                                 sysdata=line.sysdata_spec(manifest))


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
    try:
        engine = engine_check(ipa, report, known.work)
    except (ValueError, RuntimeError) as error:   # LineError, the validators' DistributionError
        raise SystemExit('VERIFICATION FAILED: ' + str(error))
    if engine is not None:
        report['s2armEngine'] = engine
    known.report.write_text(json.dumps(report, indent=1) + '\n')
    print(json.dumps(dict(s2armProbe=report['s2armProbe'], s2armEngine=engine is not None), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
