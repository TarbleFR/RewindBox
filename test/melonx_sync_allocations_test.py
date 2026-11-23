#!/usr/bin/env python3
"""Compile full production sync/bitmap classes against controlled Vulkan boundaries.

Core gate form (Core 743): melonx_sync_allocations_test.py <delivered prepared tree> --candidate-source <final
preparation>. adapt_submit_causes adds counters to SyncManager.Create (the syncs that submit at once, those that wait for
the command buffer, and the cause of the submission) and names the cause of the interrupt flush. The delivered sync manager
and the final one are compiled whole with the same fixture and run the same cases: the final file is the delivered one
plus those replacements, its functional digest, checks, scenarios and allocations are the delivered one's. RenderStageTimer
is a counting double here (the production timer's own gate is submit-causes); its counts are printed at exit and must show
both kinds of sync for the final file, none for the delivered one.
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
from adapt_sync_allocations import apply

FILES = {
    'src/Ryujinx.Graphics.Vulkan/SyncManager.cs': 'fcbee4e89cf44eba0b4a39fbd5b6331d29b25126a3dd9a0ed17ab9cd095bdfec',
    'src/Ryujinx.Graphics.Vulkan/BufferUsageBitmap.cs': 'f205e7787ecd8699117bc32771218191c3617861888afda260c1bf28411ea663',
    'src/Ryujinx.Graphics.Vulkan/BitMap.cs': '21c19bf38cee4ccdf01480b59b09e63b9d81d32a848fac18f35dbac4aac71230',
}
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())


def run_probe(work):
    (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
<NuGetAudit>false</NuGetAudit><EnableNETAnalyzers>false</EnableNETAnalyzers></PropertyGroup></Project>''')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
    (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    environment = os.environ.copy()
    environment.update(DOTNET_TieredCompilation='0', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work), '-c', 'Release'],
        cwd=work, env=environment, capture_output=True, text=True, timeout=600)
    if result.returncode:
        print(result.stdout, result.stderr)
    result.check_returncode()
    return [json.loads(line) for line in result.stdout.splitlines() if line.startswith('{')]


if '--candidate-source' in sys.argv:
    import adapt_submit_causes as causes
    FINAL = Path(sys.argv[sys.argv.index('--candidate-source') + 1]).resolve()
    SYNC = 'src/Ryujinx.Graphics.Vulkan/SyncManager.cs'
    digest = lambda path: hashlib.sha256(Path(path).read_bytes()).hexdigest()
    delivered, final = (SOURCE / SYNC).read_text(encoding='utf-8-sig'), (FINAL / SYNC).read_text(encoding='utf-8-sig')
    pairs = [(old, new) for name, old, new in causes.PAIRS if name == SYNC]
    rebuilt = delivered
    for old, new in pairs:
        assert rebuilt.count(old) == 1, old[:60]
        rebuilt = rebuilt.replace(old, new)
    assert len(pairs) == 2 and rebuilt == final, 'the final sync manager is the delivered one plus the submission counters'
    assert causes.TAG in final and causes.TAG not in delivered
    for relative in FILES:
        if relative != SYNC:
            assert digest(SOURCE / relative) == digest(FINAL / relative), 'support file differs: ' + relative
    DOUBLE = '''namespace Ryujinx.Graphics.Vulkan
{
    // Counting double of the production RenderStageTimer's submission counters (its gate is submit-causes).
    static class RenderStageTimer
    {
        public enum SubmitCause { Other, StrictSync, SyncWait, DrawAutoFlush, AttachmentAutoFlush, Query, DisposedWeight, BufferRead,
            TextureRead, StagingFull, Helper, Present, Count }
        public static SubmitCause NextSubmitCause;
        public static long SubmittingSyncs, WaitingSyncs;

        [System.Runtime.CompilerServices.ModuleInitializer]
        internal static void Report() => System.AppDomain.CurrentDomain.ProcessExit += (_, _) => System.Console.WriteLine(
            "{\\"stageTimerDouble\\":{\\"submittingSyncs\\":" + SubmittingSyncs + ",\\"waitingSyncs\\":" + WaitingSyncs + "}}");
    }
}
'''
    reports, doubles, compiled = {}, {}, {}
    with tempfile.TemporaryDirectory(prefix='melonx-sync-allocations-core-') as temporary:
        for side, tree in (('delivered', SOURCE), ('final', FINAL)):
            work = Path(temporary).resolve() / side
            for relative in FILES:
                (work / relative).parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(tree / relative, work / relative)
            for name in ('Program.cs', 'Boundaries.cs'):
                shutil.copyfile(ROOT / 'test/melonx_sync_allocations' / name, work / name)
            (work / 'RenderStageTimerDouble.cs').write_text(DOUBLE)
            compiled[side] = {str(p.relative_to(work)): digest(p) for p in work.rglob('*.cs')}
            lines = run_probe(work)
            reports[side] = next(line for line in lines if 'functionalDigest' in line)
            doubles[side] = next(line['stageTimerDouble'] for line in lines if 'stageTimerDouble' in line)
            print(side, json.dumps(reports[side]), json.dumps(doubles[side]), flush=True)
    d, f = reports['delivered'], reports['final']
    for key in ('functionalDigest', 'checks', 'scenarios', 'sink'):
        assert d[key] == f[key], key
    for old, new in zip(d['allocation'], f['allocation'], strict=True):
        assert old['mode'] == new['mode'] and old['calls'] == new['calls'] and old['allocatedBytes'] == new['allocatedBytes'], (old, new)
    assert all(item['allocatedBytes'] == 0 for report in reports.values() for item in report['bitmap'])
    assert doubles['delivered'] == {'submittingSyncs': 0, 'waitingSyncs': 0}, 'the delivered file has no counter'
    assert doubles['final']['submittingSyncs'] > 0 and doubles['final']['waitingSyncs'] > 0, 'the final file counts both kinds'
    inputs = ['build-utils/melonx/adapt_submit_causes.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_sync_allocations_test.py',
              'test/melonx_sync_allocations/Program.cs', 'test/melonx_sync_allocations/Boundaries.cs']
    report = dict(result='passed', finalPreparationBound=True, sourceKind='deliveredPreparedWithFinalCandidate', physicalDeviceTested=False,
                  completeProductionSyncAndBitmapClasses=True, sameFunctionalDigest=True, sameAllocations=True, checks=f['checks'],
                  scenarios=f['scenarios'], reports=reports, stageTimerDouble=doubles, sdk=pin['dotnet'], tieredCompilation=False,
                  boundaries='native fences and command buffers doubled; RenderStageTimer is a counting double',
                  preimages={SYNC: digest(SOURCE / SYNC)}, postimages={SYNC: digest(FINAL / SYNC)},
                  supportInputs={p: digest(FINAL / p) for p in FILES if p != SYNC}, compiledSourceInputs=compiled,
                  inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs})
    output = ROOT / 'dist/melonx/sync-allocation-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(result='passed', checks=f['checks'], scenarios=f['scenarios'])))
    raise SystemExit(0)

assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
for relative, expected in FILES.items():
    assert hashlib.sha256((SOURCE / relative).read_bytes()).hexdigest() == expected, relative
reports, postimages, compiled = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-sync-allocations-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary) / variant
        for relative in FILES:
            target = work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / relative, target)
        if variant == 'candidate':
            changed = apply(work)
            postimages = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest() for p in changed}
        for name in ('Program.cs', 'Boundaries.cs'):
            shutil.copyfile(ROOT / 'test/melonx_sync_allocations' / name, work / name)
        compiled[variant] = {str(p.relative_to(work)): hashlib.sha256(p.read_bytes()).hexdigest() for p in work.rglob('*.cs')}
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
<NuGetAudit>false</NuGetAudit><EnableNETAnalyzers>false</EnableNETAnalyzers></PropertyGroup></Project>''')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        environment = os.environ.copy()
        environment.update(DOTNET_TieredCompilation='0', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
        result = subprocess.run([os.environ.get('DOTNET', 'dotnet'), 'run', '--project', str(work), '-c', 'Release'],
            cwd=work, env=environment, capture_output=True, text=True, timeout=180)
        if result.returncode:
            print(result.stdout, result.stderr)
        result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(variant, json.dumps(reports[variant]), flush=True)
for key in ('functionalDigest', 'checks', 'scenarios', 'sink'):
    assert reports['control'][key] == reports['candidate'][key], key
for old, new in zip(reports['control']['allocation'], reports['candidate']['allocation'], strict=True):
    assert old['mode'] == new['mode'] and old['calls'] == new['calls']
    if new['mode'] != 'interrupt':
        assert old['allocatedBytes'] > 0 and new['allocatedBytes'] == 0, (old, new)
    else:
        assert old['allocatedBytes'] == new['allocatedBytes'] > 0, (old, new)
for report in reports.values():
    assert all(item['allocatedBytes'] == 0 for item in report['bitmap'])
inputs = ['build-utils/melonx/adapt_sync_allocations.py', 'build-utils/melonx/adapt_session.py',
          'build-utils/melonx/source.json', 'test/melonx_sync_allocations_test.py',
          'test/melonx_sync_allocations/Program.cs', 'test/melonx_sync_allocations/Boundaries.cs']
report = dict(result='passed', upstreamRevision=pin['revision'], sdk=pin['dotnet'], reports=reports,
    physicalDeviceTested=False, completeProductionSyncAndBitmapClasses=True,
    nativeFenceAndCommandBufferBoundariesDoubled=True, tieredCompilation=False,
    inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
    upstreamInputs=FILES, postimages=postimages, compiledSourceInputs=compiled)
output = ROOT / 'dist/melonx/sync-allocation-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(report, indent=2) + '\n')
print('Production sync lifetime, callback allocation and bitmap query checks passed.')
