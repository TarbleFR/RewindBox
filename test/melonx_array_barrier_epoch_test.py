#!/usr/bin/env python3
"""adapt_array_barrier_epoch on the final preparation, against the Core 721 preparation as control.

Usage: melonx_array_barrier_epoch_test.py <control> [--candidate-source <final preparation containing the adapter>]

IPA 718 Hogwarts in play (97-frame window): SetTextureArraySeparate 50 841 calls, 248.6 ms per 5 s on the render
thread; each array change passes every distinct storage of the array for write-to-read barriers (and walks every
element first after a storage change). The candidate skips a pass when no attachment was loaded or stored since a pass
over the same storage set covering the same stages.

Static: only the adapter's replacements; TextureStorage.QueueWriteToReadBarrier (every barrier decision) is the
preparation's byte for byte; the epoch is incremented first thing in QueueLoadOpBarrier and AddStoreOpUsage and nowhere
else; every assignment of the seven barrier state fields of TextureStorage is inside QueueLoadOpBarrier, AddStoreOpUsage
or QueueWriteToReadBarrier (the premise of the skip), and TextureStorage is not partial; the production
Ryujinx.Graphics.Vulkan assembly builds. Executed (test/melonx_array_barrier_epoch/Program.cs): the production
members of each tree (TextureStorage's state fields and three methods; TextureArray's set fields, SetTextures,
SetDirty(bool), QueueWriteToReadBarriers) under a seeded script of render passes, array passes, single reads, forced
fence flushes, element changes, disposals and command buffer changes, in three renderer configurations (MoltenVK
without argument-buffer hazard tracking as on the iPhone, MoltenVK with tracking and in-pass deferral, another
driver), three seeds of 60 000 operations: the candidate's log of every barrier, deferral, feedback refusal and
write-to-read note and the final state of every storage are the control's byte for byte, with passes skipped. Four
variants (no epoch on load, no epoch on store, no stage check, a rebuilt set treated as the same) must diverge. No
device, no MoltenVK. Writes dist/melonx/array-barrier-epoch-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_array_barrier_epoch', _HOLD)
import adapt_array_barrier_epoch as adapter  # noqa: E402
from adapt_descriptor_updates import method  # noqa: E402

FIXTURE = ROOT / 'test/melonx_array_barrier_epoch'
DOTNET = os.environ.get('DOTNET', 'dotnet')
STATE_FIELDS = ('_lastModificationAccess', '_lastModificationStage', '_lastReadAccess', '_lastReadStage', '_readCoverageAccess',
                '_readCoverageStage', '_readCoveredStages')
STORAGE_METHODS = ('        public void AddStoreOpUsage(bool depthStencil)',
                   '        public void QueueLoadOpBarrier(CommandBufferScoped cbs, bool depthStencil)',
                   '        public void QueueWriteToReadBarrier(CommandBufferScoped cbs, AccessFlags dstAccessFlags, PipelineStageFlags dstStageFlags)')
ARRAY_METHODS = ('        public void SetTextures(int index, ITexture[] textures)', '        private void SetDirty(bool storageChanged)',
                 '        public void QueueWriteToReadBarriers(CommandBufferScoped cbs, PipelineStageFlags stageFlags)')
CONFIGS = {'101': 'MoltenVK, argument-buffer hazards not tracked (iPhone, MoltenVK 1.4.2)',
           '111': 'MoltenVK tracking hazards: in-pass deferral and forced fences', '001': 'another driver'}
SEEDS = (11, 23, 47)
OPERATIONS = 60000
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def between(text, start, end_line):
    """From the line starting `start` to the line holding `end_line`, inclusive."""
    first = text.index(start)
    last = text.index(end_line, first) + len(end_line)
    return text[first:text.index('\n', last) + 1]


def spans(text, signatures):
    found = []
    for signature in signatures:
        body = method(text, signature)
        start = text.index(body)
        found.append((start, start + len(body)))
    return found


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 721 preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
runs = {}
with tempfile.TemporaryDirectory(prefix='melonx-array-barrier-epoch-') as temporary:
    temporary = Path(temporary).resolve()
    candidate_tree = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, candidate_tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(candidate_tree, ROOT)
    changed = adapter.apply(candidate_tree)
    check(sorted(p.relative_to(candidate_tree).as_posix() for p in changed) == sorted(adapter.BASELINE),
          'the adapter changes TextureStorage.cs and TextureArray.cs only')
    duplicate = temporary / 'duplicate'
    for name in adapter.BASELINE:
        (duplicate / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(candidate_tree / name, duplicate / name)
    try:
        adapter.apply(duplicate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    texts = {}
    for name, pairs in adapter.PAIRS.items():
        control_text, candidate_text = read(SOURCE, name), read(candidate_tree, name)
        texts[name] = (control_text, candidate_text)
        undone = candidate_text
        for old, new in reversed(pairs):
            check(undone.count(new) == 1, 'each replacement once: ' + new.strip().splitlines()[0][:60])
            undone = undone.replace(new, old)
        check(undone == control_text, name + ' is the preparation but the adapter\'s replacements')
        if FINAL_PREPARATION and name not in files_edited_later('adapt_array_barrier_epoch'):
            check((candidate_tree / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    storage_control, storage_candidate = texts[adapter.STORAGE]
    array_control, array_candidate = texts[adapter.ARRAY]
    check(storage_candidate.count(adapter.TAG) == 3 and array_candidate.count(adapter.TAG) == 4, 'commented')

    # Static premise: the barrier decision is the preparation's; the epoch moves with every other state change.
    q = STORAGE_METHODS[2]
    check(method(storage_candidate, q) == method(storage_control, q), 'QueueWriteToReadBarrier is the preparation\'s byte for byte')
    check(storage_candidate.count('AttachmentEpoch++') == 2 and
          method(storage_candidate, STORAGE_METHODS[0]).split('{', 1)[1].lstrip().startswith('AttachmentEpoch++;') and
          method(storage_candidate, STORAGE_METHODS[1]).split('{', 1)[1].lstrip().startswith('AttachmentEpoch++;') and
          array_candidate.count('TextureStorage.AttachmentEpoch') == 1,
          'the epoch is incremented first in AddStoreOpUsage and QueueLoadOpBarrier only, and read by the array pass only')
    allowed = spans(storage_candidate, STORAGE_METHODS)
    writes = [m.start() for m in re.finditer(r'\b(' + '|'.join(STATE_FIELDS) + r')\s*(\|=|&=|=(?!=))', storage_candidate)]
    check(len(writes) >= 10 and all(any(a <= w < b for a, b in allowed) for w in writes),
          'every write of the barrier state is in QueueLoadOpBarrier, AddStoreOpUsage or QueueWriteToReadBarrier: %d writes' % len(writes))
    sources = list((candidate_tree / 'src').rglob('*.cs'))
    check(not any(re.search(r'\bpartial\s+class\s+TextureStorage\b', p.read_text(encoding='utf-8-sig', errors='replace')) for p in sources) and
          sum(p.read_text(encoding='utf-8-sig', errors='replace').count('AttachmentEpoch') for p in sources) == 4,
          'TextureStorage is not partial; the epoch appears only in the adapter\'s lines')
    passes = method(array_candidate, ARRAY_METHODS[2])
    check(passes.index('if (_isBuffer)') < passes.index('_barrierSkips++;') < passes.index('storages.Add(storage);') <
          passes.index('storage.QueueWriteToReadBarrier(cbs, AccessFlags.ShaderReadBit, stageFlags);') < passes.index('_barrierEpoch = epoch;'),
          'buffer arrays first, the skip before the rebuild and the pass, the record after the pass')

    result = subprocess.run([DOTNET, 'build', str(candidate_tree / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                            env=environment, cwd=candidate_tree)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')

    variants = {
        'control': (storage_control, array_control),
        'candidate': (storage_candidate, array_candidate),
        'noLoadEpoch': (storage_candidate.replace(adapter.LOAD_NEW, adapter.LOAD_OLD), array_candidate),
        'noStoreEpoch': (storage_candidate.replace(adapter.STORE_NEW, adapter.STORE_OLD), array_candidate),
        'noStageCheck': (storage_candidate, array_candidate.replace(' && (stageFlags & ~_barrierStages) == 0)', ')')),
        'rebuiltAsSame': (storage_candidate, array_candidate.replace('bool sameSet = _storages != null && !_storagesDirty;',
                                                                     'bool sameSet = _storages != null;')),
    }
    for variant, (storage_text, array_text) in variants.items():
        if variant not in ('control', 'candidate'):
            check(variants[variant] != variants['candidate'], variant + ': the mutation applies')
    program = (FIXTURE / 'Program.cs').read_text()
    member_hashes = {}
    for variant, (storage_text, array_text) in variants.items():
        storage_fields = between(storage_text, '        private AccessFlags _lastModificationAccess;', 'private PipelineStageFlags _readCoveredStages;')
        array_fields = between(array_text, '        private HashSet<TextureStorage> _storages;', 'private bool _storagesDirty = true;')
        if 'private long _barrierEpoch = -1;' in array_text:
            array_fields = between(array_text, '        private HashSet<TextureStorage> _storages;', '_barrierTicks, _barrierSkips;')
        storage_members = [method(storage_text, s) for s in STORAGE_METHODS]
        array_members = [method(array_text, s) for s in ARRAY_METHODS]
        if 'private static string BarrierText()' in array_text:
            array_members.append(method(array_text, '        private static string BarrierText()'))
        member_hashes[variant] = hashlib.sha256('\n'.join([storage_fields, array_fields] + storage_members + array_members).encode()).hexdigest()
        work = temporary / variant
        work.mkdir()
        (work / 'Program.cs').write_text(program.replace('//__STORAGE_FIELDS__\n', storage_fields)
                                         .replace('//__STORAGE_METHODS__\n', '\n\n'.join(storage_members) + '\n')
                                         .replace('//__ARRAY_FIELDS__\n', array_fields)
                                         .replace('//__ARRAY_METHODS__\n', '\n\n'.join(array_members) + '\n'))
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
        for config in CONFIGS:
            for seed in SEEDS:
                log = work / f'log-{config}-{seed}.txt'
                result = subprocess.run([DOTNET, str(work / 'bin/Release/net10.0/Probe.dll'), str(seed), str(OPERATIONS), str(log), config],
                                        cwd=work, capture_output=True, text=True, timeout=900, env=environment)
                if result.returncode:
                    print(result.stdout[-4000:], result.stderr[-3000:], flush=True)
                check(result.returncode == 0, f'{variant} {config} {seed}: script ran')
                report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
                report['log'] = log
                runs[variant][(config, seed)] = report

    def first_difference(a, b):
        left, right = a.read_text().splitlines(), b.read_text().splitlines()
        for index, (x, y) in enumerate(zip(left, right)):
            if x != y:
                return index, left[max(0, index - 3):index + 2], right[max(0, index - 3):index + 2]
        return min(len(left), len(right)), left[-2:], right[-2:]

    summary = {}
    for key, control in runs['control'].items():
        candidate = runs['candidate'][key]
        same = candidate['logSha256'] == control['logSha256'] and candidate['logLines'] == control['logLines']
        if not same:
            print('first difference', key, first_difference(control['log'], candidate['log']), flush=True)
        check(same, 'candidate = control, every barrier, deferral, note and final state: %s %s' % key)
        check(control['barriers'] > 500 and control['counts']['arrayPass'] > 15000 and control['counts']['setTextures'] > 5000,
              'the script exercises barriers, array passes and element changes: %s' % {k: control[k] for k in ('barriers', 'counts')})
        check(candidate['barrierSkips'] > 0 and candidate['barrierPasses'] + candidate['barrierSkips'] == control['counts']['arrayPass'],
              'every array pass is run or skipped, some are skipped: %s %s' % (key, {k: candidate[k] for k in ('barrierPasses', 'barrierSkips')}))
        summary['%s/%d' % key] = dict(barriers=control['barriers'], deferred=control['deferred'], arrayPasses=control['counts']['arrayPass'],
                                      run=candidate['barrierPasses'], skipped=candidate['barrierSkips'], rebuilds=candidate['barrierRebuilds'],
                                      storagesVisited=candidate['barrierStorages'], logSha256=control['logSha256'])
    device = [summary['101/%d' % seed] for seed in SEEDS]
    check(all(s['skipped'] * 4 >= s['arrayPasses'] for s in device), 'on the iPhone configuration a quarter of the passes or more are skipped: ' + str(device))
    check(all(summary['111/%d' % seed]['deferred'] > 0 for seed in SEEDS), 'the tracking configuration defers in-pass barriers (forced fences exercised)')
    text = runs['candidate'][('101', SEEDS[0])]['barrierText']
    check(re.fullmatch(r'; texture array barrier passes \d+ \(storages visited \d+, sets rebuilt \d+ over \d+ elements, \d+\.\d ms\), skipped unchanged \d+', text),
          'the detail line part: ' + text)
    sensitivity = {}
    for variant in ('noLoadEpoch', 'noStoreEpoch', 'noStageCheck', 'rebuiltAsSame'):
        differing = [key for key, control in runs['control'].items() if runs[variant][key]['logSha256'] != control['logSha256']]
        sensitivity[variant] = ['%s/%d' % key for key in differing]
        check(differing, variant + ': the variant misses a barrier the control queues (some log differs)')

inputs = ['build-utils/melonx/adapt_array_barrier_epoch.py', 'build-utils/melonx/adapt_session.py', 'build-utils/melonx/adapt_descriptor_updates.py',
          'test/melonx_array_barrier_epoch_test.py', 'test/melonx_array_barrier_epoch/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core721Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               configurations=CONFIGS, seeds=SEEDS, operations=OPERATIONS, runs=summary, sensitivity=sensitivity,
               comparison=dict(sameBarrierLog=True, sameFinalStates=True, barrierDecisionUnchanged=True, stateWritesOnlyInThreeMethods=True,
                               variantsDiverge=sorted(sensitivity)),
               productionMemberHashes=member_hashes, sdk=sdk, physicalDeviceTested=False,
               productionAssembliesBuilt=['Ryujinx.Graphics.Vulkan'], sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Production barrier members with the renderer doubled; the render-thread time saved in Hogwarts Legacy is '
                          'known only from a device run (the detail line counts the passes run and skipped).')
out = ROOT / 'dist/melonx/array-barrier-epoch-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, device=device, sensitivity=sensitivity)))
