#!/usr/bin/env python3
"""Compare the complete production tracking hierarchy before/after adaptation.

The ownership variant redirects only ArrayPool and counts overlap queries at
their entry point. The timing variant compiles the production sources without
those probes. Native mapping/protection is doubled in both. No guest codegen,
native faults, physical-device frame rates or resident-memory claims are made.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_memory_tracking import apply

PREIMAGES = {
    'src/Ryujinx.Memory/Tracking/AbstractRegion.cs': '1c8e3fa1c4604905121f4972efc553eac71057114cb80e1d5353b0289f2a90d5',
    'src/Ryujinx.Memory/Tracking/BitMap.cs': '4ead1bc5642fe3ba9df278d36e3981d399028ad37d1b0dcc646c5a2413ee3c56',
    'src/Ryujinx.Memory/Tracking/ConcurrentBitmap.cs': '2ebaec4da63c612508ca6eca09a8f28f255b4ca1821d020aa94e83755c64adbd',
    'src/Ryujinx.Memory/Tracking/IMultiRegionHandle.cs': 'cd86b5abce2bb21e2d389c78fac53568f16376e530052e61bf16ddcdbcc86e80',
    'src/Ryujinx.Memory/Tracking/IRegionHandle.cs': 'ebc02aab7407390204445ae892fb22f7f2844d2eb82325c2df5f1d69e38dd98b',
    'src/Ryujinx.Memory/Tracking/MemoryTracking.cs': '0a0128dba3fc59a8f806a975e3b653b054dd5e7a29c6a15be66e22bea94d818b',
    'src/Ryujinx.Memory/Tracking/MultiRegionHandle.cs': '09f5b6505c83f2e3e8823c97d6ef26d0df57ccbe98ea88caf22d3e564def9289',
    'src/Ryujinx.Memory/Tracking/PreciseRegionSignal.cs': 'aeae32278092f332bb48660792907c3e95d865214268daf6e53130856eed64f1',
    'src/Ryujinx.Memory/Tracking/RegionFlags.cs': 'e1afa34bf449aa87675d3a94d2da312305436350fcb42e3f85547b08f399752f',
    'src/Ryujinx.Memory/Tracking/RegionHandle.cs': '770936b7f2b7f1778f6f845b9aa68d263adff365fcf95b52917c6c3669ea02e3',
    'src/Ryujinx.Memory/Tracking/RegionSignal.cs': '6d2e0596c4a25985abf6487a108923b5790c0b08187f0886116f63462734af2c',
    'src/Ryujinx.Memory/Tracking/SmartMultiRegionHandle.cs': 'ecab927033ceef39a05b273178a1b2d5b110a0053fad2f2ad8913de4c5259f4a',
    'src/Ryujinx.Memory/Tracking/VirtualRegion.cs': 'fa42f3b8530060890ba73d8ed150d437c82a1481421ddea6b8d30f823250aa26',
    'src/Ryujinx.Memory/Range/IRange.cs': 'd7b661592c0820bba0e7ff19b7d882383f46fd7fe70a0f5f4e5bdadc6e032651',
    'src/Ryujinx.Memory/Range/INonOverlappingRange.cs': '15d4eb27f4f4e25eb4f3bf369fb6cdc6a68ab1874990505bba0b8dd75eeaac95',
    'src/Ryujinx.Memory/Range/RangeListBase.cs': '32e1108eb72704f942fe62ceb361f60e2df8b6e4450f11dbb6fcb89f04b156e3',
    'src/Ryujinx.Memory/Range/NonOverlappingRangeList.cs': 'cecd0546d26c60f64c62ec3438b71bd64bf4981dbd9c92ef6dbae3a9403adf95',
    'src/Ryujinx.Memory/InvalidAccessHandler.cs': '9d7e4dd6f29723cfa2b79b985ec372c68f09f0d6d72670ab6df08859e39399b0',
    'src/Ryujinx.Memory/InvalidMemoryRegionException.cs': '1b5aa81aea3b452d5ab24c28d32c2257ae8773d9fbec5d64941cdb2cdb3dab85',
    'src/Ryujinx.Memory/MemoryPermission.cs': '215b4518d6c20a0ceb83d240a6ecab68ce9794c7f0b1601d01b259261abf850d',
}
for relative, expected in PREIMAGES.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative

pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
dotnet = os.environ.get('DOTNET', 'dotnet')
reports = {}
postimages = {}
with tempfile.TemporaryDirectory(prefix='melonx-memory-tracking-') as temporary:
    base = Path(temporary).resolve()
    for variant in ('control', 'candidate'):
        reports[variant] = {}
        for mode in ('ownership', 'timing'):
            work = base / variant / mode
            for relative in PREIMAGES:
                target = work / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(SOURCE / relative, target)
            if variant == 'candidate':
                changed = apply(work)
                hashes = {str(path.relative_to(work)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in changed}
                if postimages:
                    assert hashes == postimages, 'Probed and uninstrumented variants must adapt identically'
                postimages = hashes
            if mode == 'ownership':
                # Test boundary probes only. Preserve the full production algorithms.
                for relative in ('src/Ryujinx.Memory/Tracking/MemoryTracking.cs',
                                 'src/Ryujinx.Memory/Range/NonOverlappingRangeList.cs'):
                    path = work / relative
                    text = path.read_text(encoding='utf-8-sig').replace('ArrayPool<', 'TrackingPoolProbe<')
                    if path.name == 'NonOverlappingRangeList.cs':
                        for signature in ('public T[] FindOverlapsAsArray(ulong address, ulong size, out int length)',
                                          'public ReadOnlySpan<T> FindOverlapsAsSpan(ulong address, ulong size)'):
                            old = '        ' + signature + '\n        {\n'
                            assert text.count(old) == 1, signature
                            text = text.replace(old, old + '            TrackingProbe.Searches++;\n')
                    path.write_text(text)
            shutil.copyfile(ROOT / 'test/melonx_memory_tracking/Program.cs', work / 'Program.cs')
            definitions = ';'.join([*(['ADAPTED'] if variant == 'candidate' else []),
                                    *(['POOL_PROBE'] if mode == 'ownership' else [])])
            (work / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit>
<NoWarn>0162</NoWarn><DefineConstants>{definitions}</DefineConstants>
</PropertyGroup></Project>''')
            (work / 'nuget.config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
            (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
            environment = os.environ.copy()
            environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0')
            run = subprocess.run([dotnet, 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
                                 cwd=work, env=environment, capture_output=True, text=True, timeout=180)
            if run.returncode:
                print(run.stdout, run.stderr, flush=True)
            run.check_returncode()
            reports[variant][mode] = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
            print(variant, mode, json.dumps(reports[variant][mode]), flush=True)

assert reports['control']['ownership']['semanticTrace'] == reports['candidate']['ownership']['semanticTrace']
assert reports['control']['ownership']['traceEvents'] == reports['candidate']['ownership']['traceEvents']
inputs = ['build-utils/melonx/adapt_memory_tracking.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/source.json', 'test/melonx_memory_tracking_test.py',
          'test/melonx_memory_tracking/Program.cs']
receipt = dict(result='passed', reports=reports, upstreamRevision=pin['revision'], dotnet=pin['dotnet'],
               physicalDeviceTested=False, nativeMemoryProtectionDoubled=True,
               ownershipPoolBoundaryProbed=True, timingBodiesUninstrumented=True,
               inputs={path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in inputs},
               upstreamInputs=PREIMAGES, postimages=postimages)
output = ROOT / 'dist/melonx/memory-tracking-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print('Memory tracking semantics, snapshot ownership and host timings recorded.', flush=True)
