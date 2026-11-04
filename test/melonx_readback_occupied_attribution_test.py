#!/usr/bin/env python3
"""Occupied read-back attribution (adapt_readback_occupied_attribution) on the real prepared engine.

Usage: melonx_readback_occupied_attribution_test.py <Core 639 prepared MeloNX tree>

Applies the adapter to a copy of the prepared tree and builds the production GPU assembly (Ryujinx.Graphics.Gpu with its
project references) for the control (as prepared) and the candidate. Static checks bind that the change is diagnostics
only: the same decline decisions and returns in TryReadBackGpuRegion and TryReadBackIntoBuffer, the occupied sum counted
as before, each branch counted once, the occupant log bounded to 8 signatures, the summary keeping "occupied N". No device.
Writes dist/melonx/readback-occupied-attribution-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_readback_occupied_attribution import apply, BASELINE

DMA = 'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.index(signature)
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def decisions(body):
    """The decision skeleton: conditions, decline counters and returns, without the attribution lines."""
    lines = [line.strip() for line in body.splitlines()]
    keep = [line for line in lines if line.startswith(('return', '_readBackDeclines['))]
    return keep


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 639 preparation: ' + name)
built = {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-occupied-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = apply(work)
            check([str(p.relative_to(work)) for p in changed] == [DMA], 'adapter changed other files')
        text = (work / DMA).read_text()
        built[variant] = text
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=900,
                                env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' GPU assembly builds')

control, candidate = built['control'], built['candidate']
for method in ('private bool TryReadBackGpuRegion(', 'private bool TryReadBackIntoBuffer('):
    check(decisions(member(control, method)) == decisions(member(candidate, method)), 'same decisions and returns: ' + method)
check(control.count('_readBackDeclines[(int)ReadBackDecline.Occupied]++;') ==
      candidate.count('_readBackDeclines[(int)ReadBackDecline.Occupied]++;') == 2, 'occupied sum counted as before')
region = member(candidate, 'private bool TryReadBackGpuRegion(')
buffer = member(candidate, 'private bool TryReadBackIntoBuffer(')
check(region.count('_readBackOccupiedFragmented++;') == 1 and region.count('_readBackOccupiedOverlaps++;') == 1 and
      buffer.count('_readBackOccupiedSource++;') == 1, 'each branch counted once')
check('ReadBackOccupantSignatureLimit = 8;' in candidate and
      '_readBackOccupantSignatures.Count >= ReadBackOccupantSignatureLimit' in candidate, 'occupant log bounded')
check(re.search(r'occupied \{_readBackDeclines\[2\]\} \(other textures \{_readBackOccupiedOverlaps\}, fragmented', candidate) is not None,
      'summary keeps "occupied N" and adds the split')
inputs = ['build-utils/melonx/adapt_readback_occupied_attribution.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_readback_occupied_attribution_test.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, sdk=sdk, physicalDeviceTested=False, sourceBaseline=BASELINE,
               productionGpuAssemblyBuilt=True,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Diagnostics only; the occupant and branch are known only after a device run.')
out = ROOT / 'dist/melonx/readback-occupied-attribution-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
