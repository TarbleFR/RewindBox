#!/usr/bin/env python3
"""Execute the Shake X/Y/Z assignment policy on portable hosts and the production
Objective-C++ transaction on macOS (controlled donor menu C ABI).

Neither proves that a game accepts the shake; that remains an iPhone check.
"""
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
TOUCH = ROOT / 'packages/dolphin_internal_bridge/ios/Classes/TouchController'

compiler = shutil.which('c++') or shutil.which('clang++') or shutil.which('g++')
if compiler is None and platform.system() == 'Windows':
    # Windows development hosts have no C++ toolchain; CI (Linux/macOS) runs it.
    print('SKIP: no C++ compiler on this Windows host; the policy runs on Linux/macOS CI')
    raise SystemExit(0)
if compiler is None:
    raise SystemExit('A C++ compiler is required to execute the Shake assignment policy')

with tempfile.TemporaryDirectory() as folder:
    binary = Path(folder) / 'shake-assignment-policy'
    subprocess.run([compiler, '-std=c++17', '-Wall', '-Wextra',
                    str(ROOT / 'test/dolphin_shake_assignment_test.cpp'), '-o', str(binary)], check=True)
    subprocess.run([str(binary)], check=True)
    if platform.system() == 'Darwin':
        binary = Path(folder) / 'shake-assignment-transaction'
        subprocess.run(['clang++', '-std=c++17', '-fobjc-arc', '-Wall', '-framework', 'Foundation',
                        str(TOUCH / 'DolphinShakeAssignment.mm'),
                        str(ROOT / 'test/dolphin_shake_assignment_test.mm'),
                        '-o', str(binary)], check=True)
        subprocess.run([str(binary)], check=True, timeout=120)
    else:
        print('SKIP: production Objective-C++ assignment execution requires macOS Foundation')
