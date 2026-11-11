"""Require the reviewed artifact boundary in every checked-in workflow."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
PIN = '3bd75a37a4056eb9324987c76f32b002a89d58cb'
GUARD = 'TarbleFR/RewindBox/.github/actions/upload-protected-artifact@' + PIN
LOCAL_GUARD = './.github/actions/upload-protected-artifact'
UPLOAD_PIN = 'actions/upload-artifact@ea165f8d65b6e75b540449e92b4886f43607fa02'


def errors(root=ROOT):
    failures = []
    workflows = list((root/'.github/workflows').glob('*.yml')) + list((root/'.github/workflows').glob('*.yaml'))
    for path in workflows:
        text = path.read_text(encoding='utf-8')
        for match in re.finditer(r'\buses\s*:\s*[\'\"]?([^\s\'\"}]+)', text):
            action = match.group(1)
            if 'actions/upload-artifact@' in action:
                failures.append(str(path.relative_to(root)) + ': direct artifact upload bypasses the IPA guard')
            if 'upload-protected-artifact' in action and action != GUARD:
                if not (path.name == 'private-ipa-policy.yml' and action == LOCAL_GUARD):
                    failures.append(str(path.relative_to(root)) + ': unreviewed artifact guard reference')
    action = (root/'.github/actions/upload-protected-artifact/action.yml').read_text(encoding='utf-8')
    if UPLOAD_PIN not in action or "steps.guard.outcome == 'success'" not in action:
        failures.append('Shared action no longer gates the pinned uploader on successful inspection')
    legacy = (root/'.github/workflows/neoswap-ipa.yml').read_text(encoding='utf-8')
    if re.search(r'path:\s*build/private-test/', legacy):
        failures.append('Legacy NeoSwap workflow exposes its plaintext staging directory')
    if 'delivery_cipher.py artifact build/private-test build/encrypted-private-test' not in legacy:
        failures.append('Legacy NeoSwap workflow is missing the encryption boundary')
    return failures


if __name__ == '__main__':
    found = errors()
    if found:
        print('\n'.join(found), file=sys.stderr)
        raise SystemExit(1)
    print('Every workflow artifact upload uses the reviewed IPA boundary; releases are unchanged.')
