#!/usr/bin/env python3
"""adapt_sibling_pipelines on the final preparation, against its predecessor (the Core 745 preparation) as control.

Usage: melonx_sibling_pipelines_test.py <predecessor preparation> [--candidate-source <final preparation containing the adapter>]

IPA 729 Hogwarts Legacy: 13 pipeline states "built but missed" in 165 s of play: the journal held them as built by the
launch's replays, yet a draw created them on the render thread. The GPU side translates one guest program again for a
specialization that leaves its code unchanged (ShaderSpecializationState.MatchesGraphics compares the whole attribute
type table and every fragment output type), so two host programs of one code exist, each with its own pipeline table,
and the journal hands a code's recorded states to the first one only.

Static: only ShaderCollection.cs changes, each replacement once and reversing to the control; the specialization
match still compares state the stages may not read and the journal still hands a code's states to the first program
(the cause, read in the control); only guest graphics programs join a group; a program with no sibling runs the
control's lookup; the loan is taken under the lender's lock and kept under the borrower's, never one inside the other;
a program being disposed leaves its group, closes its loans, gives back what it took and disposes only what it owns.
Built: the production Ryujinx.Graphics.Vulkan of the candidate.
Executed (test/melonx_sibling_pipelines/Program.cs on that assembly, test-only InternalsVisibleTo): the production
PipelineSiblings, PipelineLoans, Auto and code identity. Two programs of one code drawing one state: the control's
lookup creates two pipelines, the candidate one, bound by both, destroyed once whichever program goes first and usable
by the borrower after its owner is gone. Not shared: another code, another layout entry, another state, a disposed
owner. A loan that arrives too late (borrower closing, or the state reached it meanwhile) is given back. Eight threads
drawing 40 states on 6 programs while programs are disposed and replaced: every pipeline destroyed exactly once, none
bound after its destruction, fewer creations than the control. Nothing keeps a disposed program or a dropped layout
entry reachable. The code identity: equal for equal code, different for one byte, a stage kind, the order or the count.
No device, no Vulkan object: whether Hogwarts' duplicate programs share a layout entry is the device's to show
(pipelineSiblings journal line). Writes dist/melonx/sibling-pipelines-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
import adapt_sibling_pipelines as adapter  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_sibling_pipelines', _HOLD)

DOTNET = os.environ.get('DOTNET', 'dotnet')
VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(command, cwd, timeout=2400):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                            env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1'))
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    return result


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', text.index(signature))
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


with tempfile.TemporaryDirectory(prefix='melonx-sibling-pipelines-') as temporary:
    base = Path(temporary).resolve()
    ignore = shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX')
    candidate = base / 'candidate'
    shutil.copytree(SOURCE, candidate, ignore=ignore, symlinks=True)
    name = adapter.PROGRAM
    check(sha(candidate / name) == adapter.BASELINE[name], 'control is the pinned preparation: ' + name)
    before = (candidate / name).read_text(encoding='utf-8-sig')
    others = {path: sha(candidate / path) for path in (VULKAN + 'PipelineCacheManager.cs', VULKAN + 'PipelineBase.cs',
                                                        VULKAN + 'PipelineState.cs', VULKAN + 'Auto.cs',
                                                        VULKAN + 'PipelineLayoutCache.cs',
                                                        'src/Ryujinx.Graphics.Gpu/Shader/ShaderSpecializationState.cs')}
    changed = adapter.apply(candidate)
    check([str(p.relative_to(candidate)) for p in changed] == [name], 'adapter changed other files')
    try:
        adapter.apply(candidate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    after = (candidate / name).read_text(encoding='utf-8-sig')
    restored = after
    for old, new in reversed(adapter.PAIRS):
        check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:70])
        restored = restored.replace(new, old)
    check(restored == before, 'nothing else changes in ' + name)
    for path, digest in others.items():
        check(sha(candidate / path) == digest, 'not touched: ' + path)

    postimages = {}
    if FINAL_PREPARATION:
        # The tree built and executed as the candidate is the final preparation itself (later adapters included).
        final_text = (FINAL_SOURCE / name).read_text(encoding='utf-8-sig')
        for _, new in adapter.PAIRS:
            check(final_text.count(new) == 1, 'replacement in the final preparation: ' + new.strip().splitlines()[0][:70])
        if name not in files_edited_later('adapt_sibling_pipelines'):
            check((candidate / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        shutil.rmtree(candidate)
        shutil.copytree(FINAL_SOURCE, candidate, ignore=ignore, symlinks=True)
        after = final_text
        postimages = {name: sha(candidate / name)}

    # --- the cause, read in the control ---
    match = (candidate / 'src/Ryujinx.Graphics.Gpu/Shader/ShaderSpecializationState.cs').read_text(encoding='utf-8-sig')
    graphics = member(match, 'public bool MatchesGraphics(')
    check('!graphicsState.AttributeTypes.AsSpan().SequenceEqual(GraphicsState.AttributeTypes.AsSpan())' in graphics and
          'channel.Capabilities.NeedsFragmentOutputSpecialization && !graphicsState.FragmentOutputTypes.AsSpan().SequenceEqual(' in graphics,
          'a specialization differs on the whole attribute type table and on every fragment output type, read by the stages or not')
    manager = (candidate / (VULKAN + 'PipelineCacheManager.cs')).read_text(encoding='utf-8-sig')
    offer = member(manager, 'public void Offer(ulong program, ITarget target)')
    check('if (!_plan.Remove(program, out List<Record> records))' in offer and '_ready.Add((record, target));' in offer,
          'the journal hands a code\'s recorded states to the first program that offers it')
    check('LateAfterBuilt++; // built this session, yet the draw missed it' in manager, 'the journal counts a state built yet created by a draw')
    control_lookup = member(before, 'public bool TryGetGraphicsPipeline(ref PipelineUid key, out Auto<DisposablePipeline> pipeline)')
    check('sibling' not in before.lower() and '_graphicsPipelineCache.TryGetValue(ref key, out pipeline)' in control_lookup,
          'control: a program looks only in its own table')
    release = before[before.index('protected virtual void Dispose(bool disposing)'):]
    check(len(re.findall(r'_graphicsPipelineCache\.Remove\(', before)) == 0 and 'pipeline?.Dispose();' in release,
          'control: a pipeline leaves its program\'s table only when the program is disposed')

    # --- the candidate's members ---
    lookup = member(after, 'public bool TryGetGraphicsPipeline(ref PipelineUid key, out Auto<DisposablePipeline> pipeline)')
    own = member(after, 'private bool TryGetOwnGraphicsPipeline(ref PipelineUid key, out Auto<DisposablePipeline> pipeline, bool reportMiss)')
    take = member(after, 'private void TakeSiblingGraphicsPipeline(PipelineSiblings<ShaderCollection>.Group siblings, ref PipelineUid key)')
    lend = member(after, 'private Auto<DisposablePipeline> LendGraphicsPipeline(ref PipelineUid key)')
    dispose = member(after, 'protected virtual void Dispose(bool disposing)')
    check(lookup.index('if (siblings == null || siblings.Count < 2)') <
          lookup.index('return TryGetOwnGraphicsPipeline(ref key, out pipeline, reportMiss: true);') <
          lookup.index('if (TryGetOwnGraphicsPipeline(ref key, out pipeline, reportMiss: false))') <
          lookup.index('TakeSiblingGraphicsPipeline(siblings, ref key);') and 'lock' not in lookup,
          'a program with no sibling runs the lookup alone; otherwise its own table first, a sibling only on a miss')
    control_body = control_lookup[control_lookup.index('lock (_pipelineCacheLock)'):]
    own_body = own[own.index('lock (_pipelineCacheLock)'):]
    check(own_body.replace('if (reportMiss && !CompilesInBackground && _firstBackgroundUse)', 'if (!CompilesInBackground && _firstBackgroundUse)') == control_body,
          'the program\'s own lookup is the control\'s, the miss warning kept for the final miss')
    check(take.index('sibling.LendGraphicsPipeline(ref key);') < take.index('lock (_pipelineCacheLock)') and take.count('lock (') == 1 and
          lend.count('lock (') == 1 and 'sibling' not in lend and 'ReferenceEquals(sibling, this)' in take,
          'the loan is taken under the lender\'s lock, kept under the borrower\'s: no lock of one program inside another\'s')
    locked = take[take.index('lock (_pipelineCacheLock)'):take.index('if (!kept)')]
    check('kept = !_loans.Closed && (_graphicsPipelineCache == null || !_graphicsPipelineCache.TryGetValue(ref key, out _));' in locked and
          '_loans.Take(lent);' in locked and '(_graphicsPipelineCache ??= new()).Add(ref key, lent);' in locked and
          'NotePipelineBound' not in locked and 'NoteTaken' not in locked,
          'kept only when this program is not closing and the state did not reach it meanwhile; nothing else under the lock')
    late = take[take.index('if (!kept)'):]
    check(late.index('lent.DecrementReferenceCount();') < late.index('return;') < late.index('sibling.NotePipelineBound(') <
          late.index('PipelineSiblingsJournal.NoteTaken('), 'a loan that is not kept is given back at once')
    check('!_loans.Closed && _graphicsPipelineCache != null' in lend and 'PipelineLoans<DisposablePipeline>.TryLend(pipeline) ? pipeline : null' in lend,
          'a program lends what its table holds, nothing once it is closing, nothing whose creation failed')
    check(dispose.index('_siblings?.Leave(this);') < dispose.index('if (!_gd.Shaders.Remove(this))') and
          dispose.index('_loans.Close();') < dispose.index('if (pipeline != null && !_loans.Return(pipeline))') and
          dispose.count('pipeline.Dispose();') == 1 and
          dispose.index('_loans.Close();') > dispose.index('lock (_pipelineCacheLock)'),
          'a disposed program leaves its group, closes its loans under its lock, gives back what it took, disposes what it owns')
    check(after.count('PipelineSiblings<ShaderCollection>.Join(') == 1 and
          '            if (!IsCompute)\n            {\n                // RewindBox (adapt_sibling_pipelines)\n'
          '                _siblings = PipelineSiblings<ShaderCollection>.Join(_plce, ComputeCodeIdentity(sources), this);' in after and
          after.index('ProgramPipelineState state,\n            bool fromCache,') < after.index('PipelineSiblings<ShaderCollection>.Join('),
          'only guest graphics programs join, by layout entry and code identity')
    helpers = after[after.index('    internal readonly record struct PipelineCodeIdentity('):]
    check('GC.' not in helpers and 'static readonly System.Runtime.CompilerServices.ConditionalWeakTable<object, ' in helpers and
          helpers.count('static ') - helpers.count('static readonly System.Runtime.CompilerServices.ConditionalWeakTable') ==
          helpers.count('public static ') + helpers.count('internal static ') + helpers.count('private static long _taken;') +
          helpers.count('private static int _largestGroup;'),
          'the only static state: a weak table of layout entries and two counters')

    # --- executed ---
    build = run([DOTNET, 'build', str(candidate / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release', '-nologo', '-m:1',
                 '-p:NuGetAudit=false'], candidate)
    check(build.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds')
    warnings = sorted({line.split(': warning ')[1][:80] for line in build.stdout.splitlines()
                       if 'ShaderCollection.cs' in line and ': warning ' in line})
    project = candidate / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')
    project.write_text(project.read_text(encoding='utf-8-sig').replace(
        '</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXSiblingProbe" /></ItemGroup>\n</Project>'))
    probe = base / 'probe'
    probe.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_sibling_pipelines/Program.cs', probe / 'Program.cs')
    (probe / 'MeloNXSiblingProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn><NuGetAudit>false</NuGetAudit>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
    <ServerGarbageCollection>false</ServerGarbageCollection><TieredCompilation>false</TieredCompilation>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{candidate}/src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj" />
  </ItemGroup>
</Project>
''')
    for extra in ('global.json', 'nuget.config'):
        if (candidate / extra).exists():
            shutil.copyfile(candidate / extra, probe / extra)
    check(run([DOTNET, 'build', str(probe / 'MeloNXSiblingProbe.csproj'), '-c', 'Release', '-nologo', '-m:1'], probe).returncode == 0,
          'probe builds against the production Vulkan assembly')
    executed = run([DOTNET, str(probe / 'bin/Release/net10.0/MeloNXSiblingProbe.dll')], probe, 900)
    if executed.returncode or executed.stderr.strip():
        print(executed.stdout[-4000:], executed.stderr[-4000:], flush=True)
    check(executed.returncode == 0, 'probe runs')
    r = json.loads(next(line for line in reversed(executed.stdout.splitlines()) if line.startswith('{')))

print(json.dumps(r)[:5000], flush=True)
check(r['requireFailures'] == 0, 'probe requirements: %s' % r['failed'])
check(all(r['registry'].values()), 'one group per layout entry and code; an emptied group is dropped: %s' % r['registry'])
for order in ('controlOwnerFirst', 'controlBorrowerFirst'):
    c = r[order]
    check(c['same'] is False and c['created'] == 2 and c['loans'] == 0 and c['destroyedMid'] == 1 and c['destroyedEnd'] == 2 and c['twice'] == 0,
          'control lookup: two programs of one code create the state twice (%s): %s' % (order, c))
for order in ('sharedOwnerFirst', 'sharedBorrowerFirst'):
    k = r[order]
    check(k['same'] is True and k['created'] == 1 and k['loans'] == 1 and k['stable'] is True, 'candidate: one pipeline, bound by both (%s): %s' % (order, k))
    check(k['destroyedMid'] == 0 and k['destroyedEnd'] == 1 and k['twice'] == 0,
          'candidate: destroyed once, with its last holder, whichever program goes first (%s): %s' % (order, k))
check(all(value is True for key, value in r['boundaries'].items() if key not in ('created', 'destroyed')) and
      r['boundaries']['created'] == r['boundaries']['destroyed'],
      'not shared across codes, layout entries or states; a disposed owner lends nothing; a late loan is given back: %s' % r['boundaries'])
sc = r['stressControl']
check(sc['finished'] and sc['created'] == sc['destroyed'] and sc['twice'] == 0 and sc['usedDestroyed'] == 0 and sc['exceptions'] == 0 and
      sc['taken'] == 0 and sc['replaced'] > 0, 'control lookup under threads and disposals: %s' % sc)
for ss in r['stressShared']:
    check(ss['finished'] and ss['exceptions'] == 0, 'candidate under threads and disposals: no deadlock, no exception: %s' % ss)
    check(ss['created'] == ss['destroyed'] and ss['twice'] == 0 and ss['usedDestroyed'] == 0,
          'candidate: every pipeline destroyed exactly once, none bound after its destruction: %s' % ss)
    check(ss['taken'] > 0 and ss['replaced'] > 0 and ss['created'] < sc['created'] * 0.6,
          'candidate: states come from siblings; fewer creations than the control (%d against %d)' % (ss['created'], sc['created']))
check(all(r['retention'].values()), 'nothing keeps a disposed program or a dropped layout entry reachable: %s' % r['retention'])
check(all(value is True for key, value in r['identity'].items() if key != 'distinct') and r['identity']['distinct'] == 2000,
      'the code identity: %s' % r['identity'])
check(r['reportCounts'] == [1, 8, 64, 512], 'the journal line is written at the 1st, 8th, 64th, 512th pipeline taken: %s' % r['reportCounts'])

inputs = ['build-utils/melonx/adapt_sibling_pipelines.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_sibling_pipelines_test.py',
          'test/melonx_sibling_pipelines/Program.cs', 'test/melonx_adapter_control.py']
report = {
    'result': 'passed', 'checks': checks, 'finalPreparationBound': FINAL_PREPARATION,
    'sourceKind': 'finalPreparationWithReversedControl' if FINAL_PREPARATION else 'pinnedPreparationPlusAdapter',
    'postimages': postimages, 'physicalDeviceTested': False, 'productionVulkanAssemblyBuilt': True,
    'sourceBaseline': adapter.BASELINE, 'warningsInShaderCollection': warnings,
    'controlCreationsOfOneSharedState': r['controlOwnerFirst']['created'],
    'candidateCreationsOfOneSharedState': r['sharedOwnerFirst']['created'],
    'candidateDestroyedTwice': max(s['twice'] for s in r['stressShared']),
    'candidateBoundAfterDestruction': max(s['usedDestroyed'] for s in r['stressShared']),
    'stressControlCreations': sc['created'], 'stressCandidateCreations': [s['created'] for s in r['stressShared']],
    'probe': r,
    'deviceEvidence': 'IPA 729 Hogwarts Legacy (private journal, pid 58475): pipelineVariants "built but missed 13" of 49 late '
                      'creations (356 ms) after 165 s; Super Smash Bros. Ultimate 0',
    'inputs': {path: sha(ROOT / path) for path in inputs},
    'limitation': 'Host: the sharing protocol on the production helpers with a stand-in program; no Vulkan pipeline is created. '
                  'That Hogwarts\' duplicate programs share a layout entry is shown by the device\'s pipelineSiblings line.',
}
out = ROOT / 'dist/melonx/sibling-pipelines-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS {checks} sibling pipelines checks')
