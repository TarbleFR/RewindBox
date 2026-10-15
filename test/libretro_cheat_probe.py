#!/usr/bin/env python3
"""Real pinned Nestopia/Snes9x cheats plus Ignited on Nestopia; no commercial ROMs."""
import argparse
import json
import tempfile
from pathlib import Path
import libretro_simulator_probe as probe
import libretro_skin_press_probe as skins


def content(folder):
    folder.mkdir(parents=True, exist_ok=True)
    prg = bytearray([0xEA] * 16384)
    prg[:4] = bytes.fromhex('78 4c 01 80')  # SEI; JMP $8001 (no RAM writes).
    prg[-6:] = bytes.fromhex('01 80 00 80 01 80')
    (folder / 'cheat-probe.nes').write_bytes(b'NES\x1a\x01\x01' + bytes(10) + prg + bytes(8192))
    rom = bytearray([0xEA] * 32768)
    rom[:4] = bytes.fromhex('78 4c 01 80')
    rom[0x7fc0:0x7fd5] = b'NEOSTATION CHEAT TEST '
    rom[0x7fd5:0x7fdc] = bytes([0x20, 0, 5, 0, 1, 0, 0])
    rom[0x7fdc:0x7fe0] = bytes.fromhex('ff ff 00 00')
    rom[0x7ffa:0x8000] = bytes.fromhex('01 80 00 80 01 80')
    (folder / 'cheat-probe.sfc').write_bytes(rom)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ['cores', 'inputs', 'evidence', 'label']: parser.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    args.sources = None; args.only = []; args.lot1 = False; args.lot2 = False; args.official_shaders = False
    probe.REAL_CORES = ('nestopia', 'snes9x')
    probe.SCENARIOS = [
        {'name':'ignited-nestopia', 'core':'nestopia', 'console':'nes', 'content':'content/cheat-probe.nes', 'skinPress':'press-complex', 'expect':'run'},
        {'name':'cheats-nestopia', 'core':'nestopia', 'console':'nes', 'content':'content/cheat-probe.nes', 'cheatProbe':True, 'expect':'run'},
        {'name':'cheats-snes9x', 'core':'snes9x', 'console':'snes', 'content':'content/cheat-probe.sfc', 'cheatProbe':True, 'expect':'run'},
    ]
    evidence = Path(args.evidence); evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='libretro-cheats-') as temporary:
        app, scenarios = probe.assemble(args, probe.BRIDGE, Path(temporary))
        # Only the original pinned Ignited archive, not all unrelated fixture skins.
        skins.REFERENCES = tuple(f for f in skins.REFERENCES if f[0] == 'press-complex')
        skins.fixtures(app)
        content(app / 'content')
        probe.run(['codesign', '--force', '--sign', '-', '--timestamp=none', app])
        outcome = probe.run_in_simulator(app, evidence, 180)
        (evidence/'outcome.json').write_text(json.dumps(outcome, indent=2))
        report = json.loads((evidence/'probe.json').read_text()) if (evidence/'probe.json').exists() else {'results':[]}
        problems = probe.evaluate(report, scenarios)
        for result in report.get('results', []):
            checks = result.get('cheatChecks', result.get('skinChecks', []))
            print(json.dumps({'name':result['name'], 'checks':len(checks), 'failures':[x for x in checks if not x['passed']]}))
    (evidence/'verdict.json').write_text(json.dumps({'source':args.label,'problems':problems,'physicalDeviceValidated':False}, indent=2))
    if problems: raise SystemExit('\n'.join(problems))
    print('Pinned real-core cheat effects and Ignited/Nestopia checks passed on Simulator.')

if __name__ == '__main__': main()
