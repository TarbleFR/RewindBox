#!/usr/bin/env python3
"""Compile the real bindless array cache before and after adapt_bindless_array_deltas.

Usage: melonx_bindless_array_deltas_test.py <prepared MeloNX tree (as delivered in Core b99e754d)>
       [--candidate-source <final prepared tree>]

The production TextureBindingsArrayCache, the threaded array producers and their
commands are compiled unchanged; only pools, textures, memory and the renderer
transport are doubled. Every update of random pool writes, identical rewrites,
invalidations with and without pool removal, sampler replacement and quiet passes
is checked against the pools, and control and candidate must produce identical
backend contents and store/synchronisation sets at every step. Then the cost of a
pool-sized array with the pool written before every dispatch is measured.

The whole adapter is also applied to copies of its delivered files (the delivered
collector being the current native one, which prepare_embedded copies before this
adapter runs). With --candidate-source that composition must equal the final
prepared files, and the candidate build compiles the final cache itself.
"""
import argparse
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path, help='delivered prepared tree (control)')
parser.add_argument('--candidate-source', type=Path, help='actual final prepared tree')
args = parser.parse_args()
SOURCE = args.source.resolve()
CANDIDATE = args.candidate_source.resolve() if args.candidate_source else None
DOTNET = os.environ.get('DOTNET', 'dotnet')
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_bindless_array_deltas import apply, apply_array_cache, ARRAY_CACHE, DIAGNOSTICS, NAMES
import importlib  # noqa: E402
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import ORDER, apply_present  # noqa: E402

GAL = 'src/Ryujinx.Graphics.GAL'
MULTI = GAL + '/Multithreading'
FILES = [
    'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs',
    'src/Ryujinx.Graphics.Gpu/Image/TextureBindingInfo.cs',
    'src/Ryujinx.Graphics.Gpu/Engine/Types/SamplerIndex.cs',
    'src/Ryujinx.Graphics.Shader/TextureHandle.cs',
    'src/Ryujinx.Graphics.Shader/TextureUsageFlags.cs',
    'src/Ryujinx.Graphics.Shader/ShaderStage.cs',
    GAL + '/Target.cs', GAL + '/ITextureArray.cs', GAL + '/IImageArray.cs',
    MULTI + '/Model/TableRef.cs', MULTI + '/Model/ThreadedArrayPool.cs', MULTI + '/Commands/IGALCommand.cs',
    MULTI + '/Resources/ThreadedTextureArray.cs',
    MULTI + '/Resources/ThreadedImageArray.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetTexturesCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArraySetSamplersCommand.cs',
    MULTI + '/Commands/TextureArray/TextureArrayDisposeCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArraySetImagesCommand.cs',
    MULTI + '/Commands/ImageArray/ImageArrayDisposeCommand.cs',
]

checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


# native/melonx/EmbeddedPerformanceDiagnostics.cs as delivered in Cores 614 to 649 (the Core 611 control holds it unedited).
DELIVERED_NATIVE_COLLECTOR = '95732befcbfe919f6f5a16c40621dfd7ee9b94c47d510806aebf020ef761ca39'


reports, compiled = {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-bindless-array-deltas-') as temporary:
    temporary = Path(temporary).resolve()
    # The complete adapter in preparation order: after the collector copy, on the delivered files.
    composed = temporary / 'composed'
    for relative in NAMES:
        (composed / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, composed / relative)
    # The delivered (Core 611) collector is the native collector of Cores 614 to 649, pinned by digest; since Core 654 the
    # checked-in native collector also writes the gcEvent lines (the gc-events gate binds that difference to inserted
    # lines only), so the composition starts, as prepare_embedded does, from the checked-in native collector.
    check(sha(SOURCE / DIAGNOSTICS) == DELIVERED_NATIVE_COLLECTOR,
          'delivered collector differs from the native collector of Cores 614 to 649 that prepare_embedded copied')
    shutil.copyfile(ROOT / 'native/melonx/EmbeddedPerformanceDiagnostics.cs', composed / DIAGNOSTICS)
    apply(composed)
    adapted = {p: sha(composed / p) for p in NAMES}
    check(all(adapted[p] != sha(SOURCE / p) for p in NAMES), 'adapter left a file unchanged')
    # Core 656: later preparation steps edit some of these files (adapt_array_rebuild_allocations: the cache's whole
    # rebuilds and ThreadedArrayPool). They are applied to the composition in preparation order, so it still equals the
    # final source exactly, and the fixture below compiles that final source.
    later = [name for name in ORDER if set(importlib.import_module(name).BASELINE) & (set(NAMES) | set(FILES))] if CANDIDATE else []
    for name in later:
        apply_present(composed, name, only=set(NAMES))
    # The compiled dependencies of the cache: the delivered files plus exactly those later steps' edits.
    dependencies = temporary / 'dependencies'
    for relative in FILES:
        (dependencies / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, dependencies / relative)
    for name in later:
        apply_present(dependencies, name, only=set(FILES) - {ARRAY_CACHE})
    postimages = {p: sha(composed / p) for p in NAMES}
    if CANDIDATE:
        check(postimages == {p: sha(CANDIDATE / p) for p in NAMES}, 'composition differs from the final prepared source')
    for variant in ('control', 'candidate'):
        work = temporary / variant
        origin = CANDIDATE if variant == 'candidate' and CANDIDATE else SOURCE
        for relative in FILES:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(origin / relative, target)
        if variant == 'candidate':
            if CANDIDATE:
                check(all(sha(work / p) == sha(dependencies / p) for p in FILES if p != ARRAY_CACHE),
                      'final source changed a compiled dependency of the cache beyond the later reviewed steps')
            else:
                apply_array_cache(work)
            check(sha(work / ARRAY_CACHE) == postimages[ARRAY_CACHE] if CANDIDATE else adapted[ARRAY_CACHE],
                  'candidate cache is not the composed final cache')
        compiled[variant] = {p: sha(work / p) for p in FILES}
        shutil.copyfile(ROOT / 'test/melonx_bindless_array_deltas/Program.cs', work / 'Program.cs')
        define = '<DefineConstants>ADAPTED</DefineConstants>' if variant == 'candidate' else ''
        (work / 'test.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable><ServerGarbageCollection>false</ServerGarbageCollection>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit><NoWarn>0649;0162;0168;0219;8981</NoWarn>{define}
</PropertyGroup></Project>''')
        # The same pinned SDK and no package source as the other final-source fixtures.
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        environment = os.environ.copy()
        environment.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
        result = subprocess.run([DOTNET, 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'],
                                cwd=work, capture_output=True, text=True, timeout=1200, env=environment)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-4000:], flush=True)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

control, candidate = reports['control'], reports['candidate']

check(not control['adapted'] and candidate['adapted'], 'variants swapped')
check(len(control['scenarios']) == len(candidate['scenarios']) == 72, 'scenario inventory')
for old, new in zip(control['scenarios'], candidate['scenarios'], strict=True):
    check({k: v for k, v in old.items() if k != 'digest'} == {k: v for k, v in new.items() if k != 'digest'}, 'scenario pairing')
    check(old['digest'] == new['digest'], f'backend state or synchronisation differs: {new}')
check(len(candidate['shared']) == 4, 'shared-entry inventory')
for old, new in zip(control['shared'], candidate['shared'], strict=True):
    check(old == new, f'bindings sharing one entry (formats, store, scaling) differ: {old} {new}')
for old, new in zip(control['buffers'], candidate['buffers'], strict=True):
    check(old == new and new['lookupsPerUpdate'] == 64, f'TextureBuffer arrays must keep the full rebuild: {old} {new}')
# Delivered defects the candidate must not keep (the delivered rows are recorded, not required).
check(len(candidate['removals']) == 4 and all(r['correctAtOnce'] for r in candidate['removals']),
      'a texture removed by a lookup of the same pass is rebound in that update')
check(len(candidate['failures']) == 4 and all(f['correctWithoutWrite'] for f in candidate['failures']),
      'after a failed update (delta or full) the next update rebuilds without a pool write')
check(len(candidate['syncs']) == 4 and all(r['correctAtOnce'] for r in candidate['syncs']),
      'a synchronisation that replaces a bound texture storage never leaves the released host bound')
check([r['correctAtOnce'] for r in control['syncs']] == [False, False, True, True],
      'delivered: released host bound on the cache hit only')
check(len(candidate['overflows']) == 2, 'log overflow scenarios ran')
# Core 697 (adapt_array_delta_invalidated): an invalidated bound texture re-resolves its elements only, in place.
check(len(candidate['invalidations']) == 2 and all(r['invalidated'] and r['correctAtOnce'] and not r['rebuilt'] and
      r['remapPeeks'] < r['length'] // 4 and r['removePeeks'] < r['length'] // 4 and r['duringPeeks'] < r['length'] // 4
      for r in candidate['invalidations']),
      'invalidated bound textures: no whole scan, no rebuild: ' + json.dumps(candidate['invalidations']))
check(len(candidate['quiet']) == 4 and all(q['refreshes'] <= 1 for q in candidate['quiet']),
      'quiet updates come back to cache hits after the blacklisting rebuild')
rows = []
for old, new in zip(control['measures'], candidate['measures'], strict=True):
    key = {k: old[k] for k in ('threaded', 'kind', 'length', 'changes', 'scattered')}
    check(key == {k: new[k] for k in key}, 'measure pairing')
    check(old['lookupsPerUpdate'] == old['length'], f'control walks the whole pool on every written pool: {old}')
    check(new['lookupsPerUpdate'] <= max(1, new['changes']), f'candidate resolves only changed elements: {new}')
    if new['kind'] != 'Sampler':
        # No texture is invalidated in these updates: one comparison scan, no verification scan.
        check(new['peeksPerUpdate'] <= new['length'] + new['changes'], f'candidate scans the pool once: {new}')
        # Descriptor writes only: the pass visits the logged ids, not the array.
        check(new['peeksPerUpdate'] <= 2 * new['changes'] + 2, f'candidate visits only the logged ids: {new}')
    if old['threaded'] and old['length'] > 4096:
        check(old['producerBytesPerUpdate'] >= 16 * old['length'], f'control allocates per element: {old}')
    check(new['producerBytesPerUpdate'] <= 64 * (new['changes'] + 1) + 4096, f'candidate allocation bounded by changes: {new}')
    rows.append(dict(key, controlBytes=old['producerBytesPerUpdate'], candidateBytes=new['producerBytesPerUpdate'],
                     controlLookups=old['lookupsPerUpdate'], candidateLookups=new['lookupsPerUpdate'],
                     controlBackendElements=old['backendElementsPerUpdate'], candidateBackendElements=new['backendElementsPerUpdate'],
                     candidateBackendCalls=new['backendCallsPerUpdate'],
                     controlMicroseconds=round(old['producerMicrosecondsPerUpdate'], 1),
                     candidateMicroseconds=round(new['producerMicrosecondsPerUpdate'], 1)))

inputs = ['build-utils/melonx/adapt_bindless_array_deltas.py', 'test/melonx_bindless_array_deltas_test.py',
          'test/melonx_bindless_array_deltas/Program.cs', 'native/melonx/EmbeddedPerformanceDiagnostics.cs']
receipt = dict(result='passed', checks=checks, programChecks=dict(control=control['checks'], candidate=candidate['checks']),
               invalidations=candidate['invalidations'],
               deliveredDefects=dict(removals=control['removals'], failures=control['failures'], syncs=control['syncs']),
               measures=rows, candidateCounters=candidate['counters'], physicalDeviceTested=False, fpsGainProven=False,
               poolsTexturesAndTransportDoubled=True, productionCacheAndCommandsCompiled=True,
               sourceKind='deliveredPreparedWithFinalCandidate' if CANDIDATE else 'deliveredPreparedComposed',
               finalPreparedSourceBound=bool(CANDIDATE),
               inputs={p: sha(ROOT / p) for p in inputs},
               upstreamInputs={p: sha(SOURCE / p) for p in FILES},
               preimages={p: sha(SOURCE / p) for p in NAMES}, postimages=postimages, compiledSourceInputs=compiled,
               compilationScope='TextureBindingsArrayCache with the threaded array producers and commands (pools doubled); '
                                'the pool and the collector are bound by exact composition (the full GPU assembly compiles '
                                'in the fragmented-reads gate, the collector runs in the performance-diagnostics gate).')
out = ROOT / 'dist/melonx/bindless-array-delta-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, measures=rows), indent=1))
