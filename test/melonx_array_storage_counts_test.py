#!/usr/bin/env python3
"""adapt_array_storage_counts on the final preparation, against the Core 739 preparation as control.

Usage: melonx_array_storage_counts_test.py <control> [--candidate-source <final preparation containing the adapter>]

IPA 727 Hogwarts Legacy in play (pid 56836, 97-122-frame windows): texture array barrier passes 240-290 ms per 5 s on the
render thread, "sets rebuilt 806-1 125 over 61-64 million elements": an element change that replaces a storage empties
the array's storage set and the next pass walks every element again. The candidate keeps the set up to date from the
change (a count per storage) under EncodingPolicy.IncrementalArrayDescriptors (Hogwarts Legacy only).

Static: only the adapter's replacements in TextureArray.cs; TextureStorage.cs untouched (the barrier decision is the
preparation's); the production Ryujinx.Graphics.Vulkan assembly builds. Executed (test/melonx_array_storage_counts/
Program.cs, derived from the adapt_array_barrier_epoch fixture): the production members of each tree (TextureStorage's
barrier state and three methods; TextureArray's set fields, SetTextures, SetDirty(bool), MoveStorage,
QueueWriteToReadBarriers, BarrierText) under a seeded script of render passes, array passes, single reads, forced fence
flushes, element changes (mostly small, now and then larger than LargeChange), disposals and command buffer changes, over
four arrays (8 to 8 192 elements), three renderer configurations and three seeds of 60 000 operations, with the policy
off and on. Required:
 1. policy off (every title but Hogwarts Legacy): the candidate's log of every barrier, deferral, feedback refusal and
    write-to-read note and the final state of every storage are the control's byte for byte;
 2. policy on: within every operation the candidate queues the same barriers, deferrals and notes as the control (the
    order of the storages a pass visits may differ: compared per operation as a multiset), the same final states, and
    after every pass its storage set is exactly the distinct non-null storages of the elements (no mismatch); it walks
    far fewer elements (rebuilds only after a large change or before the first pass);
 3. sensitivity: wrong variants built from the adapter's text diverge: a storage reaching zero kept in the set, a new
    storage not added, a changed set skipped by the epoch check.
Nothing depends on time or scheduling (one thread, no clock compared). No device, no MoltenVK.
Writes dist/melonx/array-storage-counts-checks.json.
"""
from pathlib import Path
import collections, hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_array_storage_counts', _HOLD)
import adapt_array_storage_counts as adapter  # noqa: E402
from adapt_descriptor_updates import method  # noqa: E402

FIXTURE = ROOT / 'test/melonx_array_storage_counts'
DOTNET = os.environ.get('DOTNET', 'dotnet')
STORAGE = 'src/Ryujinx.Graphics.Vulkan/TextureStorage.cs'
STORAGE_METHODS = ('        public void AddStoreOpUsage(bool depthStencil)',
                   '        public void QueueLoadOpBarrier(CommandBufferScoped cbs, bool depthStencil)',
                   '        public void QueueWriteToReadBarrier(CommandBufferScoped cbs, AccessFlags dstAccessFlags, PipelineStageFlags dstStageFlags)')
ARRAY_METHODS = ('        public void SetTextures(int index, ITexture[] textures)', '        private void SetDirty(bool storageChanged)',
                 '        public void QueueWriteToReadBarriers(CommandBufferScoped cbs, PipelineStageFlags stageFlags)',
                 '        private static string BarrierText()')
MOVE = '        private void MoveStorage(TextureStorage previous, TextureStorage current)'
CONFIGS = {'101': 'MoltenVK, argument-buffer hazards not tracked (iPhone, MoltenVK 1.4.2)',
           '111': 'MoltenVK tracking hazards: in-pass deferral and forced fences', '001': 'another driver'}
POLICIES = ('off', 'incremental')
SEEDS = (11, 23, 47)
OPERATIONS = 60000
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def between(text, start, end_line):
    first = text.index(start)
    last = text.index(end_line, first) + len(end_line)
    return text[first:text.index('\n', last) + 1]


A = adapter.ARRAY
check(list(adapter.BASELINE) == [A] and all(p[0] == A for p in adapter.PAIRS), 'the adapter edits TextureArray.cs only')
check(sha(SOURCE / A) == adapter.BASELINE[A], 'control is the Core 739 preparation: ' + A)
control_array = read(SOURCE, A)
candidate_array = control_array
for _, old, new in adapter.PAIRS:
    check(control_array.count(old) == 1 and candidate_array.count(old) == 1, 'one site in the control for each replacement')
    candidate_array = candidate_array.replace(old, new)
check(candidate_array.count(adapter.TAG) == len(adapter.PAIRS) == 10, 'every changed place carries the adapter\'s tag')
check(method(candidate_array, '        public void SetSamplers(int index, ISampler[] samplers)') ==
      method(control_array, '        public void SetSamplers(int index, ISampler[] samplers)'), 'SetSamplers is unchanged')
storage_text = read(SOURCE, STORAGE)
if FINAL_PREPARATION:
    # IPA 740 lot: adapt_pool_slot_copy edits TextureArray.cs after this adapter (a large array's slot copied from its
    # latest slot; nothing of the storage counts): its replacements are undone from the final text before the comparison.
    import adapt_pool_slot_copy as slot_copy  # noqa: E402
    check(files_edited_later('adapt_array_storage_counts') == {A}, 'the only later edit of TextureArray.cs is adapt_pool_slot_copy\'s')
    final_array = read(FINAL_SOURCE, A)
    for old, new in reversed(slot_copy.PAIRS):
        check(final_array.count(new) == 1, 'the later adapter\'s replacement, once')
        final_array = final_array.replace(new, old)
    check(final_array == candidate_array, 'the final preparation is the control plus the adapter\'s replacements')
    check(read(FINAL_SOURCE, STORAGE) == storage_text, 'TextureStorage.cs is untouched')

# Wrong variants of the candidate's text.
WRONG = {
    'zeroKept': (adapter.MOVE_NEW, adapter.MOVE_NEW.replace('                    _storages.Remove(previous);\n', '')),
    'newNotAdded': (adapter.MOVE_NEW, adapter.MOVE_NEW.replace('                    _storages.Add(current);\n', '')),
    'changedSetSkipped': (adapter.SAME_NEW, adapter.SAME_OLD),
}
variants = {'control': control_array, 'candidate': candidate_array}
for name, (old, new) in WRONG.items():
    check(candidate_array.count(old) == 1 and old != new, name + ': one site to alter')
    variants[name] = candidate_array.replace(old, new)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
runs = {}
with tempfile.TemporaryDirectory(prefix='melonx-array-storage-counts-') as temporary:
    temporary = Path(temporary).resolve()
    tree = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
    use_authenticated_libhac_feed(tree, ROOT)
    changed = adapter.apply(tree)
    check([p.relative_to(tree).as_posix() for p in changed] == [A], 'the adapter changed TextureArray.cs only')
    check(read(tree, A) == candidate_array, 'applied tree is the candidate text')
    drift = temporary / 'drift'
    (drift / A).parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / A, drift / A)
    (drift / A).write_bytes((drift / A).read_bytes() + b'\n// unreviewed drift\n')
    try:
        adapter.apply(drift)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'a drifted TextureArray.cs is refused')
    result = subprocess.run([DOTNET, 'build', str(tree / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=tree)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')
    warnings = sorted({line for line in result.stdout.splitlines() if 'warning' in line and 'TextureArray.cs(' in line})
    check(not warnings, 'no compiler warning in TextureArray.cs: ' + '\n'.join(warnings[:5]))

    program = (FIXTURE / 'Program.cs').read_text()
    storage_fields = between(storage_text, '        private AccessFlags _lastModificationAccess;', 'private PipelineStageFlags _readCoveredStages;')
    storage_members = [method(storage_text, s) for s in STORAGE_METHODS]
    member_hashes = {}
    for variant, array_text in variants.items():
        array_fields = between(array_text, '        private HashSet<TextureStorage> _storages;', '_barrierTicks, _barrierSkips;')
        members = [method(array_text, s) for s in ARRAY_METHODS]
        if MOVE in array_text:
            members.append(method(array_text, MOVE))
        member_hashes[variant] = hashlib.sha256('\n'.join([array_fields] + members).encode()).hexdigest()
        work = temporary / variant
        work.mkdir()
        (work / 'Program.cs').write_text(program.replace('//__STORAGE_FIELDS__\n', storage_fields)
                                         .replace('//__STORAGE_METHODS__\n', '\n\n'.join(storage_members) + '\n')
                                         .replace('//__ARRAY_FIELDS__\n', array_fields)
                                         .replace('//__ARRAY_METHODS__\n', '\n\n'.join(members) + '\n'))
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><EnableNETAnalyzers>false</EnableNETAnalyzers><NoWarn>0649;0162;0169;0414;8500;CS0649;CS0169</NoWarn>
<NuGetAudit>false</NuGetAudit></PropertyGroup>
<ItemGroup><PackageReference Include="Silk.NET.Vulkan" Version="2.22.0" /></ItemGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        result = subprocess.run([DOTNET, 'build', str(work / 'Probe.csproj'), '-c', 'Release', '-nologo'], cwd=work,
                                capture_output=True, text=True, timeout=900, env=environment)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ': fixture builds with the production members')
        runs[variant] = {}
        policies = POLICIES if variant in ('control', 'candidate') else ('incremental',)
        for policy in policies:
            for config in CONFIGS:
                for seed in SEEDS:
                    log = work / f'log-{policy}-{config}-{seed}.txt'
                    result = subprocess.run([DOTNET, str(work / 'bin/Release/net10.0/Probe.dll'), str(seed), str(OPERATIONS), str(log), config, policy],
                                            cwd=work, capture_output=True, text=True, timeout=900, env=environment)
                    if result.returncode:
                        print(result.stdout[-4000:], result.stderr[-3000:], flush=True)
                    check(result.returncode == 0, f'{variant} {policy} {config} {seed}: script ran')
                    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
                    lines = log.read_text().splitlines()
                    blocks, current = [], []
                    for line in lines:
                        if line.startswith('op ') and current:
                            blocks.append(current)
                            current = []
                        current.append(line)
                    blocks.append(current)
                    report['canonical'] = hashlib.sha256('\n'.join('|'.join(sorted(b)) for b in blocks).encode()).hexdigest()
                    report['barrierCounter'] = collections.Counter(l.split(' ')[0] for l in lines)
                    runs[variant][(policy, config, seed)] = report

summary = {}
for key, control in runs['control'].items():
    policy = key[0]
    candidate = runs['candidate'][key]
    label = '%s/%s/%d' % key
    check(control['mismatches'] == 0, label + ': the control\'s set always equals its elements\' storages')
    check(control['barriers'] > 500 and control['counts']['arrayPass'] > 15000 and control['counts']['setTextures'] > 5000,
          label + ': the script exercises barriers, array passes and element changes')
    if policy == 'off':
        check(candidate['logSha256'] == control['logSha256'] and candidate['logLines'] == control['logLines'],
              label + ': policy off, the candidate is the control byte for byte')
    else:
        check(candidate['canonical'] == control['canonical'] and candidate['barrierCounter'] == control['barrierCounter'],
              label + ': policy on, the same barriers, deferrals, notes and final states in every operation')
        check(candidate['mismatches'] == 0, label + ': policy on, the candidate\'s set always equals its elements\' storages')
        check(candidate['barrierRebuildElements'] * 5 < control['barrierRebuildElements'],
              label + ': policy on, far fewer elements walked: %d vs %d' % (candidate['barrierRebuildElements'], control['barrierRebuildElements']))
    summary[label] = dict(barriers=control['barriers'], arrayPasses=control['counts']['arrayPass'], setTextures=control['counts']['setTextures'],
                          controlRebuilds=control['barrierRebuilds'], candidateRebuilds=candidate['barrierRebuilds'],
                          controlElementsWalked=control['barrierRebuildElements'], candidateElementsWalked=candidate['barrierRebuildElements'],
                          controlSkips=control['barrierSkips'], candidateSkips=candidate['barrierSkips'])
sensitivity = {}
for variant in WRONG:
    differing = [k for k, r in runs[variant].items() if r['canonical'] != runs['control'][k]['canonical'] or r['mismatches'] > 0]
    sensitivity[variant] = ['%s/%s/%d' % k for k in differing]
    check(differing, variant + ': the variant diverges from the control (a barrier or a set member differs)')

on = [v for k, v in summary.items() if k.startswith('incremental/')]
inputs = ['build-utils/melonx/adapt_array_storage_counts.py', 'build-utils/melonx/adapt_session.py', 'build-utils/melonx/adapt_descriptor_updates.py',
          'test/melonx_array_storage_counts_test.py', 'test/melonx_array_storage_counts/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core739Preparation',
               postimages={A: sha(FINAL_SOURCE / A)} if FINAL_PREPARATION else {},
               configurations=CONFIGS, seeds=SEEDS, operations=OPERATIONS, policies=POLICIES, runs=summary, sensitivity=sensitivity,
               comparison=dict(policyOffByteIdentical=True, policyOnSameBarriersPerOperation=True, setAlwaysExact=True,
                               elementsWalked=dict(control=sum(v['controlElementsWalked'] for v in on), candidate=sum(v['candidateElementsWalked'] for v in on)),
                               sensitivityVariantsFailed=len(WRONG)),
               productionMemberHashes=member_hashes, sdk=sdk, physicalDeviceTested=False, productionAssembliesBuilt=['Ryujinx.Graphics.Vulkan'],
               sourceBaseline=adapter.BASELINE, inputs={p: sha(ROOT / p) for p in inputs},
               deviceEvidence='IPA 727 Hogwarts Legacy pid 56836 (private journals): texture array barrier passes 240-290 ms per 5 s, '
                              'sets rebuilt 806-1 125 over 61-64 million elements',
               limitation='Production barrier and set members with the renderer doubled; the render-thread time saved in Hogwarts Legacy '
                          'is known only from a device run (sets rebuilt, elements walked, barrier pass ms in the detail line).')
out = ROOT / 'dist/melonx/array-storage-counts-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, elementsWalked=receipt['comparison']['elementsWalked'], sensitivity=sensitivity)))
