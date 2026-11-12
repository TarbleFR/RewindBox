#!/usr/bin/env python3
"""Checks how a built RewindBox app ships Apple's Metal Shader Converter runtime.

Agreement EA1844 (assets/legal/metal-shader-converter/, the maintainer's
dossier docs/evidence/xenia-metal-shader-converter/README.md):
- 2.B: the runtime serves shader conversion only: XeniaCore is the only
  image of the app that loads @rpath/libmetalirconverter.dylib;
- 2.E: shipped unmodified: its signature-free digest equals the pinned
  mirror asset's (build-utils/xenia/source.json), so only the code signature
  iOS requires may differ (no install_name_tool, strip, lipo or patch);
- 2.D and 13: Apple's agreement and acknowledgements ship with it, as the
  app's Legal/MetalShaderConverter folder (embed_legal_bundle.py).
An app without the XeniOS engine has neither the runtime nor XeniaCore and
passes unchanged; one of the two without the other is refused.
Usage: check_app_shader_converter.py <Runner.app>
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'build-utils' / 'xenia'))
sys.path.insert(0, str(ROOT / 'packages' / 'dolphin_internal_bridge' / 'ci'))
import validate_shader_converter as converter  # noqa: E402

RUNTIME = 'Frameworks/libmetalirconverter.dylib'
CORE = 'Frameworks/XeniaCore.framework/XeniaCore'
DEPENDENCY = '@rpath/libmetalirconverter.dylib'
LEGAL = 'Legal/MetalShaderConverter'
NOTICES = ROOT / 'assets' / 'legal' / 'metal-shader-converter' / 'license-sources.json'
MACHO = (b'\xcf\xfa\xed\xfe', b'\xca\xfe\xba\xbe', b'\xca\xfe\xba\xbf')


def pinned_digest() -> str:
    source = json.loads((ROOT / 'build-utils' / 'xenia' / 'source.json').read_text())
    return source['shader_converter']['upstream_mirror']['signature_free_sha256']


def dependencies(data: bytes) -> list[str]:
    from verify_ipa import macho
    return [item['path'] for item in macho(data)['dependencies']]


def check(app: Path, expected_digest: str | None = None) -> list[str]:
    runtime, core = app / RUNTIME, app / CORE
    if not runtime.exists() and not core.exists():
        return []
    if runtime.exists() != core.exists():
        return [f'{RUNTIME} and {CORE} ship together or not at all']
    failures = []
    try:
        digest = converter.signature_free_digest(runtime.read_bytes())
    except ValueError as error:
        return [f'{RUNTIME}: {error}']
    if digest != (expected_digest or pinned_digest()):
        failures.append(f'{RUNTIME} differs from the pinned runtime beyond its code signature (EA1844 2.E)')
    if DEPENDENCY not in dependencies(core.read_bytes()):
        failures.append(f'{CORE} does not load {DEPENDENCY}')
    for path in sorted(app.rglob('*')):
        if not path.is_file() or path.is_symlink() or path in (runtime, core):
            continue
        with path.open('rb') as handle:
            if handle.read(4) not in MACHO:
                continue
        try:
            if DEPENDENCY in dependencies(path.read_bytes()):
                failures.append(f'{path.relative_to(app)} loads the shader converter: only XeniaCore may (EA1844 2.B)')
        except Exception:  # not an image the parser reads (object files, resources)
            continue
    manifest = json.loads(NOTICES.read_text())
    for component in manifest['components']:
        for entry in component['files']:
            shipped = app / LEGAL / entry['path']
            if not shipped.is_file() or hashlib.sha256(shipped.read_bytes()).hexdigest() != entry['sha256']:
                failures.append(f'{LEGAL}/{entry["path"]} missing or changed (EA1844 2.D and 13)')
    return failures


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print(__doc__)
        return 2
    app = Path(argv[0])
    failures = check(app)
    if failures:
        print('Shader converter use: REFUSED\n- ' + '\n- '.join(failures))
        return 1
    print('Shader converter use: OK' if (app / RUNTIME).exists()
          else 'Shader converter use: OK (no XeniOS engine in this app)')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
