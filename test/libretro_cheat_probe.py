#!/usr/bin/env python3
"""Real pinned Nestopia/Snes9x cheats plus Ignited on Nestopia; no commercial ROMs."""
import argparse
import os
import struct
import json
import tempfile
import shutil
import urllib.request
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
    # DeSmuME executes Action Replay from its ARM7 VBlank IRQ hook
    # (NDSSystem.cpp execHardware_hstart_vblankStart), not every bare loop.
    # Enable the hook in our own ARM7 program; no commercial firmware/ROM.
    probe.build_nds(folder / 'cheat-probe.nds')
    nds = bytearray((folder / 'cheat-probe.nds').read_bytes())
    arm7 = [0xE59F0008, 0xE3A01008, 0xE1C010B0, 0xEAFFFFFE, 0x04000004]
    # ldr r0,[pc,#8]; mov r1,#8; strh r1,[r0]; b .; DISPSTAT address
    struct.pack_into('<' + 'I' * len(arm7), nds, 0x204, *arm7)
    struct.pack_into('<IIII', nds, 0x030, 0x204, 0x02380000, 0x02380000, len(arm7) * 4)
    struct.pack_into('<H', nds, 0x15E, probe.crc16(nds[:0x15E]))
    (folder / 'cheat-probe.nds').write_bytes(nds)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ['cores', 'inputs', 'evidence', 'label']: parser.add_argument('--' + flag, required=True)
    args = parser.parse_args()
    args.sources = None; args.only = []; args.lot1 = False; args.lot2 = False; args.official_shaders = False
    probe.REAL_CORES = ('nestopia', 'snes9x', 'desmume')
    probe.SCENARIOS = [
        {'name':'ignited-nestopia', 'core':'nestopia', 'console':'nes', 'content':'content/cheat-probe.nes', 'skinPress':'press-complex', 'expect':'run'},
        {'name':'cheats-nestopia', 'core':'nestopia', 'console':'nes', 'content':'content/cheat-probe.nes', 'cheatProbe':True, 'expect':'run'},
        {'name':'overlay-previews', 'core':'nestopia', 'console':'nes', 'content':'content/cheat-probe.nes', 'previewProbe':True, 'expect':'run'},
        {'name':'cheats-desmume', 'core':'desmume', 'console':'nds', 'content':'content/cheat-probe.nds', 'cheatProbe':True, 'expect':'run'},
        {'name':'cheats-snes9x', 'core':'snes9x', 'console':'snes', 'content':'content/cheat-probe.sfc', 'cheatProbe':True, 'expect':'run'},
    ]
    evidence = Path(args.evidence); evidence.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='libretro-cheats-') as temporary:
        app, scenarios = probe.assemble(args, probe.BRIDGE, Path(temporary))
        # Only the original pinned Ignited archive, not all unrelated fixture skins.
        skins.REFERENCES = tuple(f for f in skins.REFERENCES if f[0] == 'press-complex')
        skins.fixtures(app)
        content(app / 'content')
        for name in ('ff7-usa-original.cht', 'digimon-world-original.cht'):
            shutil.copyfile(probe.ROOT / 'test/fixtures/libretro_cheats' / name, app / name)
        # Exact production Dart conversion, exported by the preceding Flutter test.
        for directory in sorted(Path('evidence/overlay-layouts').glob('*')):
            if not directory.is_dir(): continue
            target = app / 'SkinFixtures' / directory.name
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(directory / 'info.json', target / 'info.json')
            for local, remote in json.loads((directory / 'resources.json').read_text()).items():
                url = 'https://raw.githubusercontent.com/libretro/common-overlays/42c21b99889468a8e77fd7f002229ec16e2f9fa2/' + remote
                with urllib.request.urlopen(url, timeout=30) as response:
                    data = response.read(16 * 1024 * 1024 + 1)
                assert len(data) <= 16 * 1024 * 1024
                file = target / local; file.parent.mkdir(parents=True, exist_ok=True); file.write_bytes(data)

        probe.run(['codesign', '--force', '--sign', '-', '--timestamp=none', app])
        outcome = probe.run_in_simulator(app, evidence, 180)
        (evidence/'outcome.json').write_text(json.dumps(outcome, indent=2))
        report = json.loads((evidence/'probe.json').read_text()) if (evidence/'probe.json').exists() else {'results':[]}
        restart_evidence = evidence / 'process-restart'; restart_evidence.mkdir()
        os.environ['SIMCTL_CHILD_NEOSTATION_CHEAT_RESTART'] = '1'
        try:
            restarted = probe.run_in_simulator(app, restart_evidence, 180, reset=False)
        finally:
            os.environ.pop('SIMCTL_CHILD_NEOSTATION_CHEAT_RESTART', None)
        restart_report = json.loads((restart_evidence/'probe.json').read_text()) if (restart_evidence/'probe.json').exists() else {'results':[]}
        restart_scenarios = [s for s in scenarios if s['name'] == 'cheats-nestopia']
        restart_problems = probe.evaluate(restart_report, restart_scenarios)
        if not restarted['finished']: restart_problems.append('second process did not finish')
        (restart_evidence/'outcome.json').write_text(json.dumps(restarted, indent=2))
        problems = probe.evaluate(report, scenarios) + restart_problems
        for result in report.get('results', []) + restart_report.get('results', []):
            checks = result.get('cheatChecks', result.get('skinChecks', result.get('previewChecks', [])))
            print(json.dumps({'name':result['name'], 'checks':len(checks), 'failures':[x for x in checks if not x['passed']]}))
    (evidence/'verdict.json').write_text(json.dumps({'source':args.label,'problems':problems,'physicalDeviceValidated':False}, indent=2))
    if problems: raise SystemExit('\n'.join(problems))
    print('Pinned real-core cheat effects and Ignited/Nestopia checks passed on Simulator.')

if __name__ == '__main__': main()
