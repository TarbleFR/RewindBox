#!/usr/bin/env python3
"""Compile/run only the new anonymous provider resolver on macOS Foundation."""
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]


def main():
    if sys.platform != 'darwin':
        print('The native host resolver test requires macOS Foundation.', file=sys.stderr)
        return 77
    out = ROOT / 'build/hd-direct400/texture_host_resolver_test'
    out.parent.mkdir(parents=True, exist_ok=True)
    classes = ROOT / 'packages/neo_texture_catalog/ios/Classes'
    subprocess.run(['xcrun', 'clang', '-fobjc-arc', '-fblocks', '-Wall', '-Wextra',
                    '-Wno-unused-parameter', '-framework', 'Foundation', '-I', str(classes),
                    str(ROOT / 'test/texture_host_resolver_test.m'), str(classes / 'NeoTextureHostResolver.m'),
                    '-o', str(out)], check=True, cwd=ROOT)
    subprocess.run([str(out)], check=True, cwd=ROOT, timeout=60)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
