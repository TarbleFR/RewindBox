#!/usr/bin/env python3
"""Build 502: prove StikJIT build tooling does not mutate current host state machines."""
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]
BASE = '69a514390fffb1389977ca8863f0bb03f756db84'
FILES = (
    'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3JitBridgePlugin.mm',
    'packages/armsx2_internal_bridge/ios/Classes/Armsx2JitBridgePlugin.mm',
    'packages/dolphin_internal_bridge/ci/verify_ipa.py',
    'packages/dolphin_jit_helper/ios/Classes/DolphinJITRequestHandlerBase.swift',
)

for path in FILES:
    expected = subprocess.check_output(['git', 'show', f'{BASE}:{path}'], cwd=ROOT)
    actual = (ROOT / path).read_bytes()
    assert actual == expected, f'{path} changed after validated Build 502 product base'

print('PASS: current validated JIT host state machines are byte-exact to Build 502 product base')
