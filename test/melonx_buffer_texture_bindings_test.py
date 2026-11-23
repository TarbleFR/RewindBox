#!/usr/bin/env python3
"""Bound buffer textures resolved once while valid (adapt_buffer_texture_bindings), control against candidate, real engine.

Usage: melonx_buffer_texture_bindings_test.py <final preparation containing the adapter>
       melonx_buffer_texture_bindings_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the final preparation with the adapter reversed (melonx_adapter_control), candidate the adapter applied to
it, which must be the final preparation byte for byte. Static: only TextureBindingsManager.cs differs, each replacement
once, reversed it gives the control; the existing fast paths and the full path keep their text.
Built: the production Ryujinx.Graphics.Gpu of the candidate (its project and closure, unmodified). Then, for control and
candidate, the same closure with a test-only InternalsVisibleTo and four counters (texture lookups for a binding, sampler
lookups, descriptor reads from guest memory; the same lines in both) and test/melonx_buffer_texture_bindings/Program.cs,
which drives GpuContext through GPFifo with guest command buffers shaped like the measured title's frames (see its
header), on the recording GAL double of Recorder.cs; the shaders are Maxwell code translated by the real translator.
Executed:
- verify: every renderer, pipeline and resource call, in order with its arguments and data (creation numbers for
  objects, handles for buffers, bytes for data), hashed whole and at each draw and dispatch; the bytes of every bound
  uniform, storage, vertex and index range at each draw and dispatch hashed; every bound uniform, vertex and index range
  compared at each draw with guest memory at its address. Control and candidate must give the same hashes, counts and
  bytes, and no range may differ from guest memory. The stream must hold its invalidation events (pool rewrites, moved
  buffer textures, handle rewrites, unmap and remap to other memory, buffer merges), buffer textures, buffer images
  and dispatches.
- mutant: the candidate with the fast path's texture checks removed (the moved sequence and the pool item) must give
  other hashes than the control: the stream does reach states where they decide.
- timed: control and candidate alternately, five runs each (20 measured frames of 2,000 draws after 4): the GPU thread's
  CPU time in DispatchCalls, its allocations, the engine's own gpuWork lines (bindings, compute, bufLoad) and the
  counters. The candidate must make fewer texture lookups for a binding and fewer descriptor reads, the same sampler
  lookups or fewer, allocate no more, and not take more CPU time (best and median runs, with a margin for a shared
  host).
No device: the GPU thread time on an iPhone is known only from the next build's gpuWork lines. Writes
dist/melonx/buffer-texture-bindings-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, statistics, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_buffer_texture_bindings', _HOLD)
import adapt_buffer_texture_bindings as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_buffer_texture_bindings'
GPU = 'src/Ryujinx.Graphics.Gpu/'
IMAGE = GPU + 'Image/'
RUNS = 5
VERIFY = ('4', '1500')
TIMED = ('24', '2000')
# Shared host (other jobs on the same cores): the candidate's best and median CPU times may exceed the control's by this
# factor before the gate calls it slower.
TIME_MARGIN = 1.10
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, cwd, timeout=2400, env=None):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                            env=env or dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1'))
    if result.returncode:
        errors = [line for line in result.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), result.stdout[-4000:], result.stderr[-3000:], sep='\n', flush=True)
    return result


def project_closure(src, project):
    seen, pending = set(), [project]
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        text = (src / name / (name + '.csproj')).read_text(encoding='utf-8-sig')
        pending += re.findall(r'ProjectReference Include="\.\.\\([^\\"]+)\\', text)
    return sorted(seen)


def insert(path, anchor, addition):
    text = path.read_text(encoding='utf-8-sig')
    check(text.count(anchor) == 1, 'counter anchor in ' + path.name + ': ' + anchor.strip()[:70])
    path.write_text(text.replace(anchor, anchor + addition), encoding='utf-8')


COUNTERS = '''namespace Ryujinx.Graphics.Gpu
{
    // Test-only (melonx_buffer_texture_bindings_test.py): lookups made by the pools, read by the probe.
    public static class ProbeCounters
    {
        public static long TextureLookups, FormatLookups, SamplerLookups, DescriptorReads;
    }
}
'''


def stage(tree, target, projects, counted):
    """The GPU closure of a tree; counted: with the probe's InternalsVisibleTo and the lookup counters."""
    for name in ('Directory.Build.props', 'Directory.Packages.props', 'global.json', 'nuget.config'):
        if (tree / name).exists():
            shutil.copy2(tree / name, target / name)
    for name in projects:
        shutil.copytree(tree / 'src' / name, target / 'src' / name, ignore=shutil.ignore_patterns('bin', 'obj'), symlinks=True)
    if not counted:
        return
    project = target / (GPU + 'Ryujinx.Graphics.Gpu.csproj')
    text = project.read_text(encoding='utf-8-sig')
    check(text.count('</Project>') == 1, 'GPU project file')
    project.write_text(text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="GpuThreadProbe" /></ItemGroup>\n</Project>'), encoding='utf-8')
    (target / (GPU + 'ProbeCounters.cs')).write_text(COUNTERS)
    insert(target / (IMAGE + 'TexturePool.cs'), '        public ref readonly TextureDescriptor GetForBinding(int id, bool srgbSampler, out Texture texture)\n        {\n',
           '            global::Ryujinx.Graphics.Gpu.ProbeCounters.TextureLookups++;\n')
    insert(target / (IMAGE + 'TexturePool.cs'), '        public ref readonly TextureDescriptor GetForBinding(int id, FormatInfo formatInfo, out Texture texture)\n        {\n',
           '            global::Ryujinx.Graphics.Gpu.ProbeCounters.FormatLookups++;\n')
    insert(target / (IMAGE + 'SamplerPool.cs'), '        public override Sampler Get(int id)\n        {\n',
           '            global::Ryujinx.Graphics.Gpu.ProbeCounters.SamplerLookups++;\n')
    insert(target / (IMAGE + 'Pool.cs'), '        public ref readonly T2 GetDescriptorRefAddress(ulong address)\n        {\n',
           '            global::Ryujinx.Graphics.Gpu.ProbeCounters.DescriptorReads++;\n')


def probe(base, closure, name):
    directory = base / ('probe-' + name)
    directory.mkdir()
    for file in ('Program.cs', 'Recorder.cs'):
        shutil.copyfile(FIXTURE / file, directory / file)
    (directory / 'GpuThreadProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632;CS0649</NoWarn><NuGetAudit>false</NuGetAudit>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><InvariantGlobalization>true</InvariantGlobalization>
    <TieredCompilation>false</TieredCompilation>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{closure}/src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj" />
    <ProjectReference Include="{closure}/src/Ryujinx.Cpu/Ryujinx.Cpu.csproj" />
  </ItemGroup>
</Project>
''')
    for extra in ('global.json', 'nuget.config'):
        if (closure / extra).exists():
            shutil.copyfile(closure / extra, directory / extra)
    build = run([DOTNET, 'build', str(directory / 'GpuThreadProbe.csproj'), '-c', 'Release', '-nologo', '-m:2', '-p:NuGetAudit=false'], cwd=directory)
    check(build.returncode == 0, 'probe builds against the ' + name + ' engine')
    return directory / 'bin/Release/net10.0/GpuThreadProbe.dll'


def execute(dll, name, mode, frames, draws):
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_TieredCompilation='0',
                       DOTNET_TieredPGO='0', DOTNET_gcServer='0')
    result = run([DOTNET, str(dll), name, mode, frames, draws], cwd=dll.parent, timeout=1800, env=environment)
    check(result.returncode == 0, name + ' ' + mode + ' run')
    return json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))


# --- static ---
check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in adapter.BASELINE.items():
    check(sha(SOURCE / name) == expected, 'control is the adapter\'s pinned preparation: ' + name)
check(sorted(adapter.BASELINE) == [adapter.BINDINGS] and sorted(adapter.FILE_PAIRS) == [adapter.BINDINGS], 'the adapter declares one file')
check(not files_edited_later('adapt_buffer_texture_bindings'), 'no later adapter edits the file')
before = (SOURCE / adapter.BINDINGS).read_text(encoding='utf-8-sig')
after = (FINAL_SOURCE / adapter.BINDINGS).read_text(encoding='utf-8-sig')
restored = after
for old, new in reversed(adapter.PAIRS):
    check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:70])
    restored = restored.replace(new, old)
check(restored == before, 'reversed, the candidate file is the control')
check(after.count(adapter.TAG) == sum(new.count(adapter.TAG) for _, new in adapter.PAIRS) >= 8 and before.count(adapter.TAG) == 0, 'every edit is tagged')
for unchanged in ('''                if (!poolModified &&
                    state.TextureHandle == textureId &&
                    state.SamplerHandle == samplerId &&
                    state.CachedTexture != null &&
                    state.CachedTexture.InvalidatedSequence == state.InvalidatedSequence &&
                    state.CachedSampler?.IsDisposed != true)''', '''                if (!poolModified &&
                    state.TextureHandle == textureId &&
                    state.ImageFormat == bindingInfo.FormatInfo.Format &&
                    state.CachedTexture != null &&
                    state.CachedTexture.InvalidatedSequence == state.InvalidatedSequence)''',
                  '                    // Cache is not used for buffer texture, it must always rebind.\n                    state.CachedTexture = null;',
                  '        public void Rebind()\n        {\n            Array.Clear(_textureState);\n            Array.Clear(_imageState);\n        }'):
    check(after.count(unchanged) == before.count(unchanged) >= 1, 'existing path unchanged: ' + unchanged.strip().splitlines()[0][:60])
check(after.count('_channel.BufferManager.SetBufferTextureStorage(') == 4 and before.count('_channel.BufferManager.SetBufferTextureStorage(') == 2,
      'one storage call per new fast path, the full paths keep theirs')
check(after.count('_context.Renderer.Pipeline.') == before.count('_context.Renderer.Pipeline.'), 'no backend call added or removed')
check(after.count('state.BufferTexture = null; // ' + adapter.TAG) == 2, 'the other branch of each full path forgets the buffer texture')

reports = {}
receipt_builds = {}
with tempfile.TemporaryDirectory(prefix='melonx-buffer-texture-bindings-') as temporary:
    base = Path(temporary).resolve()
    candidate_tree = base / 'candidate-tree'
    shutil.copytree(SOURCE, candidate_tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
    changed = adapter.apply(candidate_tree)
    check([str(p.relative_to(candidate_tree)) for p in changed] == [adapter.BINDINGS], 'adapter changed one file')
    check((candidate_tree / adapter.BINDINGS).read_bytes() == (FINAL_SOURCE / adapter.BINDINGS).read_bytes(), 'final preparation is the adapter')
    try:
        adapter.apply(candidate_tree)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    different, compared = [], 0
    for path in sorted((SOURCE / 'src').rglob('*')):
        relative = path.relative_to(SOURCE)
        if path.is_file() and not path.is_symlink() and not {'bin', 'obj', 'MeloNX'} & set(relative.parts):
            compared += 1
            if not (candidate_tree / relative).is_file() or (candidate_tree / relative).read_bytes() != path.read_bytes():
                different.append(relative.as_posix())
    check(compared > 3000 and different == [adapter.BINDINGS], 'only the adapter\'s file differs: ' + str(different[:6]))

    projects = sorted(set(project_closure(candidate_tree / 'src', 'Ryujinx.Graphics.Gpu')) | set(project_closure(candidate_tree / 'src', 'Ryujinx.Cpu')))
    # The production project of the candidate, as it is.
    production = base / 'production'
    production.mkdir()
    stage(candidate_tree, production, projects, counted=False)
    build = run([DOTNET, 'build', str(production / (GPU + 'Ryujinx.Graphics.Gpu.csproj')), '-c', 'Release', '-nologo', '-m:2',
                 '-p:NuGetAudit=false'], cwd=production)
    check(build.returncode == 0, 'candidate production assembly builds: Ryujinx.Graphics.Gpu')
    warnings = sorted({line.strip() for line in build.stdout.splitlines() if 'warning' in line and 'TextureBindingsManager.cs' in line})
    check(not warnings, 'no compiler warning in the edited file: ' + '\n'.join(warnings[:4]))
    shutil.rmtree(production)

    # The mutant: the fast paths without the moved-sequence and pool-item checks of their texture.
    mutant_text = after
    for condition, weakened in (('''                    state.BufferTexture.InvalidatedSequence == state.BufferInvalidatedSequence &&
                    state.BufferSampler?.IsDisposed != true &&
                    texturePool.GetCachedItem(textureId) == state.BufferPoolItem)''', '''                    state.BufferSampler?.IsDisposed != true)'''),
                                ('''                    state.BufferTexture.InvalidatedSequence == state.BufferInvalidatedSequence &&
                    pool.GetCachedItem(textureId) == state.BufferPoolItem)''', '''                    true)''')):
        check(mutant_text.count(condition) == 1, 'mutant anchor')
        mutant_text = mutant_text.replace(condition, weakened)
    dlls = {}
    for name, tree in (('control', SOURCE), ('candidate', candidate_tree), ('mutant', candidate_tree)):
        closure = base / ('closure-' + name)
        closure.mkdir()
        stage(tree, closure, projects, counted=True)
        if name == 'mutant':
            (closure / adapter.BINDINGS).write_text(mutant_text, encoding='utf-8')
        receipt_builds[name] = {p: sha(closure / p) for p in (adapter.BINDINGS, IMAGE + 'TexturePool.cs', IMAGE + 'SamplerPool.cs', IMAGE + 'Pool.cs')}
        dlls[name] = probe(base, closure, name)

    for name in ('control', 'candidate', 'mutant'):
        reports[name + '-verify'] = execute(dlls[name], name, 'verify', *VERIFY)
        print(json.dumps({name: {k: reports[name + '-verify'][k] for k in ('callHash', 'drawHash', 'contentHash', 'drawPoints', 'events')}}), flush=True)
    timed = {'control': [], 'candidate': []}
    for index in range(RUNS):
        for name in (('control', 'candidate') if index % 2 == 0 else ('candidate', 'control')):
            report = execute(dlls[name], name, 'timed', *TIMED)
            timed[name].append(report)
            print(json.dumps({name: {k: report[k] for k in ('gpuCpuMs', 'gpuMs', 'allocatedBytes', 'lookups')} | {'work': report['work']}}), flush=True)

control_verify, candidate_verify, mutant_verify = reports['control-verify'], reports['candidate-verify'], reports['mutant-verify']
SAME = ('callHash', 'drawHash', 'contentHash', 'drawPoints', 'dataBytes', 'counts', 'draws', 'dispatches', 'inlineWrites', 'cbData', 'events')
for key in SAME:
    check(control_verify[key] == candidate_verify[key], 'control and candidate differ in ' + key + ': ' + str((control_verify[key], candidate_verify[key])))
for name, report in (('control', control_verify), ('candidate', candidate_verify)):
    errors = [e for e in report['oracleErrors'] if 'is no cached buffer' not in e]
    check(not errors, name + ': every bound range holds the bytes of guest memory: ' + '; '.join(errors[:3]))
    check(report['oracleRanges'] > 10000 and report['oracleBytes'] > 1 << 20, name + ': the bound ranges were compared with guest memory')
counts = control_verify['counts']
events = control_verify['events']
check(all(events[key] > 0 for key in ('poolWrites', 'shiftedTextures', 'handleWrites', 'remaps', 'overlaps')), 'the invalidation events ran: ' + str(events))
check(counts.get('TextureSetStorage', 0) > 4 * control_verify['draws'] and counts.get('SetImage', 0) >= control_verify['dispatches'] > 100 and
      counts.get('SetTextureArraySeparate', 0) > 0 and counts.get('DeleteBuffer', 0) > 0 and counts.get('SetBufferData', 0) > 0,
      'buffer textures, buffer images, texture arrays, merged buffers and buffer uploads in the stream: ' + str(counts))
check(control_verify['drawPoints'] == control_verify['draws'] + control_verify['dispatches'], 'every draw and dispatch hashed')
check(any(mutant_verify[key] != control_verify[key] for key in ('callHash', 'drawHash', 'contentHash')),
      'without its texture checks the fast path changes what the backend receives (the stream reaches those states)')

def median(values):
    return statistics.median(values)

control_cpu = [r['gpuCpuMs'] for r in timed['control']]
candidate_cpu = [r['gpuCpuMs'] for r in timed['candidate']]
for name in ('control', 'candidate'):
    check(len({json.dumps(r['lookups'], sort_keys=True) for r in timed[name]}) == 1, name + ': the counters are the same at every run')
    check(all(r['draws'] == timed['control'][0]['draws'] and r['frames'] == 20 for r in timed[name]), name + ': same timed stream')
lc, lk = timed['control'][0]['lookups'], timed['candidate'][0]['lookups']
check(all(v >= 0 for v in lc.values()) and lc['TextureLookups'] > 0, 'the counters were compiled in: ' + str(lc))
check(lk['TextureLookups'] < lc['TextureLookups'] and lk['DescriptorReads'] < lc['DescriptorReads'] and lk['SamplerLookups'] <= lc['SamplerLookups'] and
      lk['FormatLookups'] <= lc['FormatLookups'], 'the candidate looks up fewer textures and reads fewer descriptors: ' + str((lc, lk)))
check(median([r['allocatedBytes'] for r in timed['candidate']]) <= median([r['allocatedBytes'] for r in timed['control']]) + 65536, 'no more allocation')
check(min(candidate_cpu) <= min(control_cpu) * TIME_MARGIN and median(candidate_cpu) <= median(control_cpu) * TIME_MARGIN,
      'the candidate takes no more CPU time: ' + str((sorted(control_cpu), sorted(candidate_cpu))))


def work(name, key):
    rows = [r['work'].get(key, [0, 0, 0]) for r in timed[name]]
    return dict(calls=rows[0][0], medianMs=median([row[1] for row in rows]), kib=rows[0][2])

summary = dict(
    draws=timed['control'][0]['draws'], dispatches=timed['control'][0]['dispatches'], measuredFrames=timed['control'][0]['frames'],
    gpuThreadCpuMs=dict(control=sorted(control_cpu), candidate=sorted(candidate_cpu),
                        medianRatio=round(median(candidate_cpu) / median(control_cpu), 3), bestRatio=round(min(candidate_cpu) / min(control_cpu), 3)),
    allocatedBytes=dict(control=sorted(r['allocatedBytes'] for r in timed['control']), candidate=sorted(r['allocatedBytes'] for r in timed['candidate'])),
    lookups=dict(control=lc, candidate=lk),
    gpuWork={key: dict(control=work('control', key), candidate=work('candidate', key)) for key in ('bindings', 'compute', 'bufLoad', 'draw', 'i2m')},
    verify={key: control_verify[key] for key in ('callHash', 'drawHash', 'contentHash', 'drawPoints', 'dataBytes', 'events', 'oracleRanges', 'oracleBytes')},
    rendererCalls=counts, mutantDiffers=True)
print(json.dumps(summary, indent=1), flush=True)
inputs = ['build-utils/melonx/adapt_buffer_texture_bindings.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_buffer_texture_bindings_test.py',
          'test/melonx_buffer_texture_bindings/Program.cs', 'test/melonx_buffer_texture_bindings/Recorder.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, physicalDeviceTested=False, fpsGainProven=False,
               sourceKind='finalPreparationWithReversedControl', productionGpuAssemblyBuilt=True, rendererDoubled=True,
               host=platform.system() + ' ' + platform.machine() + ' managed Release, TieredCompilation off', sdk=sdk,
               sourceBaseline={p: sha(SOURCE / p) for p in adapter.BASELINE}, postimages={p: sha(FINAL_SOURCE / p) for p in adapter.BASELINE},
               compiledSourceInputs=receipt_builds, summary=summary,
               limits=['host CPU time on a shared x86-64 host, not Apple timing; the lookup counters are exact',
                       'the stream is shaped from counts (shader cache survey, journal ratios), not a capture of the game'],
               inputs={p: sha(ROOT / p) for p in inputs})
out = ROOT / 'dist/melonx/buffer-texture-bindings-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
