#!/usr/bin/env python3
"""Run actual pinned PPSSPP and Mupen RAM enable/rewrite/disable effects in Simulator.

Uses the existing application probe without altering its tracked source, and an
original N64 VI loop plus the already reviewed pspautotests simple.prx fixture.
No core is rebuilt. It must run on an Apple Silicon macOS CI runner.
"""
import argparse
import hashlib
import json
import os
import shutil
import struct
import sys
import tempfile
from pathlib import Path
import libretro_simulator_probe as probe


def n64_content(path):
    rom = bytearray(1024 * 1024)
    rom[:4] = bytes.fromhex('80371240')
    struct.pack_into('>III', rom, 4, 0x0000000f, 0x80000400, 0x00001444)
    rom[0x20:0x34] = b'NEOSTATION CHEAT TEST'[:20].ljust(20, b' ')
    rom[0x3b:0x3f] = b'NCTE'
    words = [0x3c08a440]  # lui t0,$a440 (VI registers)
    def reg(offset, value):
        words.extend([0x3c090000 | ((value >> 16) & 0xffff),
                      0x35290000 | (value & 0xffff), 0xad090000 | offset])
    reg(0x00, 2)            # VI_STATUS16-bit pixels
    reg(0x04, 0x00100000)   # empty framebuffer, separate from cheat byte
    reg(0x08, 320)
    reg(0x0c, 2)
    reg(0x10, 0)
    reg(0x14, 0x03e52239)
    reg(0x18, 525)
    reg(0x1c, 3093)
    reg(0x20, 0x0c150c15)
    reg(0x24, 0x006c02ec)
    reg(0x28, 0x002501ff)
    reg(0x2c, 0x000e0204)
    reg(0x30, 0x00000200)
    reg(0x34, 0x00000400)
    # The CIC HLE begins the original bootstrap at ROM0x40 in SP DMEM.
    # Never write the target RDRAM byte from this program.
    words.extend([0x1000ffff, 0])
    struct.pack_into('>' + 'I' * len(words), rom, 0x40, *words)
    path.write_bytes(rom)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ('cores', 'inputs', 'evidence', 'label'):
        parser.add_argument('--' + flag, required=True)
    parser.add_argument('--only', choices=('psp', 'n64'), nargs='+',
                        help='Run only the selected real-core effect scenarios.')
    args = parser.parse_args()
    selected = set(args.only or ('psp', 'n64'))
    if sys.platform != 'darwin':
        raise SystemExit('The real-core probe requires Apple Silicon macOS Simulator.')
    expected = {
        'ppsspp': '40d3b6f81a726ff82a89f87df5332f20a5dcdecd9f6473fcae7cade60bcb0cf0',
        'mupen64plus_next': 'afdaff358796de530fa005eb037af68f3e05936442cf07f5f7dde86803f8f115',
    }
    for core, digest in expected.items():
        if ('psp' if core == 'ppsspp' else 'n64') not in selected:
            continue
        binary = Path(args.cores) / 'Frameworks' / f'{core}_libretro.framework' / f'{core}_libretro'
        if hashlib.sha256(binary.read_bytes()).hexdigest() != digest:
            raise SystemExit(f'{core}: input is not the inspected delivered core.')
    args.sources = None
    args.only = []
    args.lot1 = args.lot2 = args.official_shaders = False
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    probe.REAL_CORES = tuple(core for core in expected
                            if ('psp' if core == 'ppsspp' else 'n64') in selected)
    probe.SCENARIOS = [
        {'name':'unified-cheats-psp','core':'ppsspp','console':'psp','content':'content/probe.iso','cheatProbe':True,'expect':'run'},
        {'name':'unified-cheats-n64','core':'mupen64plus_next','console':'n64','content':'content/unified-cheats.z64','cheatProbe':True,'expect':'run',
         # Simulator has no usable OpenGL ES textures. Exercise the delivered
         # software RDP/RSP implementations, not a fake hardware context.
         'optionDefaults':{'mupen64plus-rdp-plugin':'angrylion',
                           'mupen64plus-rsp-plugin':'cxd4',
                           'mupen64plus-cpucore':'cached_interpreter'},
         'noJitOverrides':{'mupen64plus-cpucore':'cached_interpreter'}},
    ]
    probe.SCENARIOS = [item for item in probe.SCENARIOS if item['console'] in selected]
    with tempfile.TemporaryDirectory(prefix='unified-cheats-cores-') as temporary:
        work = Path(temporary)
        # Compile the exact existing probe with only its dispatch function
        # replaced by this test's additional effect observer.
        original_root = probe.ROOT
        stage = work / 'source'
        stage.mkdir()
        for item in original_root.iterdir():
            if item.name == 'test':
                shutil.copytree(item, stage / item.name, symlinks=True,
                                ignore=shutil.ignore_patterns('__pycache__'))
            else:
                (stage / item.name).symlink_to(item, target_is_directory=item.is_dir())
        entry = stage / 'test/libretro_simulator/probe.m'
        source = entry.read_text()
        source = source.replace('#import "cheat_probe.h"',
            '#import "cheat_probe.h"\n#import "../unified_identity_core_probe.h"')
        source = source.replace('RunCheatProbe(session,scenario,result,',
                                'RunUnifiedIdentityCoreProbe(session,scenario,result,')
        entry.write_text(source)
        probe.ROOT = stage
        app, scenarios = probe.assemble(args, probe.BRIDGE, work / 'build')
        # assemble deliberately overwrites scenario settings with the product
        # catalogue's defaults. Apply these Simulator-only software engines
        # after that step, without editing the catalogue or production Host.
        for scenario in scenarios:
            if scenario['core'] == 'mupen64plus_next':
                fixture = next(item for item in probe.SCENARIOS if item['core'] == scenario['core'])
                scenario['optionDefaults'].update(fixture['optionDefaults'])
                scenario['noJitOverrides'].update(fixture['noJitOverrides'])
        config_path = app / 'probe-config.json'
        config = json.loads(config_path.read_text())
        config['scenarios'] = scenarios
        config_path.write_text(json.dumps(config, indent=2) + '\n')
        n64_content(app / 'content/unified-cheats.z64')
        probe.run(['codesign', '--force', '--sign', '-', '--timestamp=none', app])
        outcome = probe.run_in_simulator(app, evidence, 180)
        (evidence / 'outcome.json').write_text(json.dumps(outcome, indent=2))
        report_file = evidence / 'probe.json'
        report = json.loads(report_file.read_text()) if report_file.exists() else {'results':[]}
        problems = probe.evaluate(report, scenarios)
        if not outcome['finished']:
            problems.append('The Simulator process did not finish.')
        (evidence / 'unified-core-effects.json').write_text(json.dumps({
            'label':args.label,'outcome':outcome,'problems':problems,
            'physicalDeviceValidated':False,'coreRebuilt':False,
        }, indent=2))
        if problems:
            raise SystemExit('\n'.join(problems))

if __name__ == '__main__':
    main()
