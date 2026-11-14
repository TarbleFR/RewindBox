#!/usr/bin/env python3
"""adapt_array_sync_epochs on the final preparation, against its predecessor as control.

Usage: melonx_array_sync_epochs_test.py <predecessor preparation> [--candidate-source <final preparation containing the adapter>]

IPA 729 Hogwarts Legacy: arrayDelta 459-1 136 ms per 5 s window of the GPU thread, 0.9 ms per call when play starts and
2.8-6.7 ms after 100 s: every update of a bound texture array walks all its textures three times (one
SynchronizeMemory walk, two ValidateTextures walks), whatever changed.

Static: only Texture.cs and TextureBindingsArrayCache.cs change, each replacement once and reversing to the control.
What makes the skipped walks no-ops is read in the source: a texture's dirty flag is written true by its initialiser
and by SignalGroupDirty only, and Texture.SynchronizeMemory of a texture that is not dirty only stamps LastUseEpoch;
that clock is in seconds; a scale mode is written by the constructors, BlacklistScale and AssignScaleMode only, the
last signalling a texture that leaves the blacklist; every InvalidatedSequence move goes through one method; the
writers count themselves in flight around the flag (or sequence) and the epoch; the array's texture set is written at
five places, the three outside the delta path after a Reset.
Built: the production Ryujinx.Graphics.Gpu of the candidate.
Executed (test/melonx_array_sync_epochs/Program.cs: the production cache, threaded array producers and commands of the
control and of the candidate; pools, textures, memory and the renderer transport doubled, the texture double with the
dirty flag, the use clock and the writers' protocol):
- 72 random scenarios (texture, sampler and image arrays; stores; scale blacklist; format views; threaded or not) with
  pool writes, removals, invalidations, scaling, CPU writes to texture memory, dirty signals on any texture, scale
  modes leaving the blacklist and ticks of the use clock, the shared-entry, texture buffer, removal, failure, log overflow, invalidation, replaced-storage
  and quiet scenarios of the bindless gate: at every step the control and the candidate leave the same backend
  contents, the same store set, the same uploaded textures and the same state in every texture (dirty flag, use
  stamp, uploads, scale mode, pending upload);
- 24 scenarios where a synchronisation signals another texture during the walk: the same state once settled;
- a writer in flight (flag set, epoch not moved yet), for the dirty flag and for a sequence: the candidate walks;
- an array of 3 200 bound textures: synchronisations and sequence reads per update, control against candidate.
No device: the GPU thread time is the device's to show. Writes dist/melonx/array-sync-epochs-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
import adapt_array_sync_epochs as adapter  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_array_sync_epochs', _HOLD)

DOTNET = os.environ.get('DOTNET', 'dotnet')
GAL = 'src/Ryujinx.Graphics.GAL'
MULTI = GAL + '/Multithreading'
# The production files the fixture compiles (the bindless array gate's list).
FILES = [adapter.CACHE, 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingInfo.cs', 'src/Ryujinx.Graphics.Gpu/Engine/Types/SamplerIndex.cs',
         'src/Ryujinx.Graphics.Shader/TextureHandle.cs', 'src/Ryujinx.Graphics.Shader/TextureUsageFlags.cs',
         'src/Ryujinx.Graphics.Shader/ShaderStage.cs', GAL + '/Target.cs', GAL + '/ITextureArray.cs', GAL + '/IImageArray.cs',
         MULTI + '/Model/TableRef.cs', MULTI + '/Model/ThreadedArrayPool.cs', MULTI + '/Commands/IGALCommand.cs',
         MULTI + '/Resources/ThreadedTextureArray.cs', MULTI + '/Resources/ThreadedImageArray.cs',
         MULTI + '/Commands/TextureArray/TextureArraySetTexturesCommand.cs', MULTI + '/Commands/TextureArray/TextureArraySetSamplersCommand.cs',
         MULTI + '/Commands/TextureArray/TextureArrayDisposeCommand.cs', MULTI + '/Commands/ImageArray/ImageArraySetImagesCommand.cs',
         MULTI + '/Commands/ImageArray/ImageArrayDisposeCommand.cs']
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


def ordered(text, *parts):
    position = -1
    for part in parts:
        position = text.find(part, position + 1)
        if position < 0:
            return False
    return True


with tempfile.TemporaryDirectory(prefix='melonx-array-sync-epochs-') as temporary:
    base = Path(temporary).resolve()
    ignore = shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX')
    control, candidate = base / 'control-tree', base / 'candidate-tree'
    shutil.copytree(SOURCE, control, ignore=ignore, symlinks=True)
    shutil.copytree(SOURCE, candidate, ignore=ignore, symlinks=True)
    for name, expected in adapter.BASELINE.items():
        check(sha(control / name) == expected, 'control is the pinned preparation: ' + name)
    before = {name: (control / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
    changed = adapter.apply(candidate)
    check(sorted(str(p.relative_to(candidate)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
    try:
        adapter.apply(candidate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    after = {name: (candidate / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
    for name, pairs in adapter.FILE_PAIRS.items():
        restored = after[name]
        for old, new in reversed(pairs):
            check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[-1][:70])
            restored = restored.replace(new, old)
        check(restored == before[name], 'nothing else changes in ' + name)
    for relative in FILES[1:]:
        check(sha(candidate / relative) == sha(control / relative), 'compiled dependency not touched: ' + relative)

    postimages = {}
    if FINAL_PREPARATION:
        # The tree built and executed as the candidate is the final preparation itself (later adapters included).
        # IPA 736, second lot: adapt_array_dirty_log edits both files after this adapter (the rings in Texture.cs, the
        # walks' fast paths in the cache). Its replacements are undone for the static reading of this adapter's own
        # text; the fixture below compiles and executes the final cache, rings included.
        import adapt_array_dirty_log as _log  # noqa: E402
        check(files_edited_later('adapt_array_sync_epochs') == set(adapter.BASELINE), 'the later adapter edits these two files')
        own = {}
        for name, pairs in adapter.FILE_PAIRS.items():
            final_text = (FINAL_SOURCE / name).read_text(encoding='utf-8-sig')
            # IPA 740 lot: adapt_array_log_membership then adds the membership flag to both files: undone first.
            import adapt_array_log_membership as _membership  # noqa: E402
            for file, old, new in reversed(_membership.PAIRS):
                if file == name:
                    check(final_text.count(new) == 1, 'the later adapter\'s replacement, once: ' + new.strip().splitlines()[0][:70])
                    final_text = final_text.replace(new, old)
            for old, new in reversed(_log.FILE_PAIRS[name]):
                check(final_text.count(new) == 1, 'the later adapter\'s replacement, once: ' + new.strip().splitlines()[0][:70])
                final_text = final_text.replace(new, old)
            for _, new in pairs:
                check(final_text.count(new) == 1, 'replacement in the final preparation: ' + new.strip().splitlines()[-1][:70])
            check(final_text == after[name], 'final preparation is the adapter (later adapter undone): ' + name)
            own[name] = final_text
        shutil.rmtree(candidate)
        shutil.copytree(FINAL_SOURCE, candidate, ignore=ignore, symlinks=True)
        after = own
        postimages = {name: sha(candidate / name) for name in adapter.BASELINE}

    # --- what makes a skipped walk a no-op, read in the source ---
    texture, cache = after[adapter.TEXTURE], after[adapter.CACHE]
    old_texture = before[adapter.TEXTURE]
    check(len(re.findall(r'\b_dirty = true;', old_texture)) == 2 and 'private bool _dirty = true;' in old_texture and
          '_dirty = true;' in member(old_texture, 'public void SignalGroupDirty()') and
          len(re.findall(r'\b_dirty = true;', texture)) == 2,
          'a texture is made dirty by its initialiser and by SignalGroupDirty only')
    sync = member(texture, 'public void SynchronizeMemory()')
    check(ordered(sync, 'LastUseEpoch = _context.TextureUseEpoch;', 'if (Target == Target.TextureBuffer)', 'if (!_dirty)', 'return;', '_dirty = false;') and
          sync == member(old_texture, 'public void SynchronizeMemory()'),
          'the synchronisation of a texture that is not dirty only stamps its last use; unchanged by the adapter')
    context = (candidate / 'src/Ryujinx.Graphics.Gpu/GpuContext.cs').read_text(encoding='utf-8-sig')
    check('TextureUseEpoch = (int)(now / 1000);' in context and context.count('TextureUseEpoch =') == 1, 'the use clock counts seconds, set at one place')
    # A scale mode is written by the two constructors (a new texture), by BlacklistScale (into the blacklist) and by
    # SetScale, which gives a view its storage's mode and a storage its view's: those four assignments go through
    # AssignScaleMode, which signals a texture that leaves the blacklist. No other file writes a scale mode.
    scale = member(texture, 'public void SetScale(float scale)')
    assign = member(texture, 'private static void AssignScaleMode(Texture texture, TextureScaleMode mode)')
    check(len(re.findall(r'\bScaleMode = ', old_texture)) == 7 and len(re.findall(r'\bScaleMode = ', member(old_texture, 'public void SetScale(float scale)'))) == 4 and
          not re.search(r'\bScaleMode = ', scale) and scale.count('AssignScaleMode(') == 4 and len(re.findall(r'\bScaleMode = ', texture)) == 4 and
          texture.count('ScaleMode = scaleMode;') == 2 and texture.count('ScaleMode = TextureScaleMode.Blacklisted;') == 1,
          'the scale mode is assigned by the constructors, BlacklistScale and AssignScaleMode only')
    check(ordered(assign, 'bool leavesBlacklist = texture.ScaleMode == TextureScaleMode.Blacklisted && mode != TextureScaleMode.Blacklisted;',
                  'Interlocked.Increment(ref DirtyWriters);', 'texture.ScaleMode = mode;', 'Interlocked.Increment(ref DirtyEpoch);',
                  'Interlocked.Decrement(ref DirtyWriters);'), 'a texture that leaves the blacklist is signalled after its mode is written')
    others = [str(path.relative_to(candidate)) for path in (candidate / 'src/Ryujinx.Graphics.Gpu').rglob('*.cs')
              if path.name != 'Texture.cs' and re.search(r'\.ScaleMode = ', path.read_text(encoding='utf-8-sig', errors='replace'))]
    check(not others, 'no other file of the GPU project writes a scale mode: %s' % others)
    signal = member(texture, 'public void SignalGroupDirty()')
    check(ordered(signal, 'Interlocked.Increment(ref DirtyWriters);', '_dirty = true;', 'Interlocked.Increment(ref DirtyEpoch);',
                  'Interlocked.Decrement(ref DirtyWriters);'), 'SignalGroupDirty: counted in flight; the epoch moves after the flag is set')
    move = member(texture, 'private void MoveInvalidatedSequence()')
    check(ordered(move, 'Interlocked.Increment(ref InvalidationWriters);', 'InvalidatedSequence++;', 'Interlocked.Increment(ref InvalidationEpoch);',
                  'Interlocked.Decrement(ref InvalidationWriters);') and texture.count('InvalidatedSequence++;') == 1 and
          old_texture.count('InvalidatedSequence++;') == 3 and texture.count('MoveInvalidatedSequence(); // RewindBox') == 3 and
          texture.count('Interlocked.Increment(ref InvalidationEpoch);') == 1,
          'the three sequence moves go through one method, counted in flight, the epoch moved after the sequence')
    entry = cache[cache.index('        private class CacheEntry'):cache.index('        private class CacheEntryFromBuffer') if 'private class CacheEntryFromBuffer' in cache
                  else cache.index('            public bool TexturePoolModified()')]
    writes = re.findall(r'\bTextures(?:\.(?:Add|TryAdd|Remove|Clear)\(|\[[^\]]+\] = )', cache)
    check(sorted(writes) == sorted(['Textures.Remove(', 'Textures[texture] = ', 'Textures.Clear(', 'Textures[texture] = ', 'Textures[texture] = ']),
          'the texture set is written at five places: %s' % writes)
    check(ordered(cache, 'Textures[texture] = sequence;\n                        NoteTextureAdded(texture);') and
          ordered(cache, 'Textures.Clear();\n                ForgetWalks();'),
          'a texture added by a delta is noted; a cleared set forgets its walks')
    for position in (m.start() for m in re.finditer(r'entry\.Textures\[texture\] = texture\.InvalidatedSequence;', cache)):
        method_start = max(cache.rfind('        private void UpdateFromPool(', 0, position), cache.rfind('        private void UpdateFromBuffer(', 0, position))
        check(method_start > 0 and 'entry.Reset();' in cache[method_start:position], 'a whole rebuild fills the set after a Reset (or into a new entry)')
    check(len(re.findall(r'entry\.Textures\[texture\] = texture\.InvalidatedSequence;', cache)) == 2, 'two whole-rebuild fills')
    walk = member(cache, 'public void SynchronizeMemory(bool isStore, bool blacklistScale)')
    check(ordered(walk, 'bool quiet = Volatile.Read(ref Texture.DirtyWriters) == 0;', 'int dirtyEpoch = Volatile.Read(ref Texture.DirtyEpoch);',
                  'if (!isStore && _syncCurrent && (!blacklistScale || _syncedBlacklisted) &&',
                  'quiet && dirtyEpoch == _syncedDirtyEpoch && _syncSource.ContextUseEpoch == _syncedUseEpoch)',
                  'if (!Textures.ContainsKey(added))', 'added.SynchronizeMemory();',
                  'if (Volatile.Read(ref Texture.DirtyWriters) == 0 && Volatile.Read(ref Texture.DirtyEpoch) == dirtyEpoch)',
                  'dirtyEpoch = Volatile.Read(ref Texture.DirtyEpoch);', 'foreach (Texture texture in Textures.Keys)',
                  'useEpoch = texture.ContextUseEpoch; // read before the first stamp', 'texture.SynchronizeMemory();',
                  'texture.SignalModified();', 'texture.BlacklistScale();', '_syncedDirtyEpoch = dirtyEpoch;'),
          'the walk is skipped only for a non-store access with no writer in flight, an unmoved epoch read before any flag, the '
          'same second and the blacklist already applied; the textures added since are synchronised; the complete walk is the control\'s')
    old_walk = member(before[adapter.CACHE], 'public void SynchronizeMemory(bool isStore, bool blacklistScale)')
    loop = old_walk[old_walk.index('texture.SynchronizeMemory();'):old_walk.rindex('}', 0, old_walk.rindex('}'))]
    check(loop.strip() and loop in walk, 'the complete walk does to each texture what the control does')
    validate = member(cache, 'public bool ValidateTextures()')
    check(ordered(validate, 'bool quiet = Volatile.Read(ref Texture.InvalidationWriters) == 0;', 'int epoch = Volatile.Read(ref Texture.InvalidationEpoch);',
                  'if (quiet && _validationCurrent && epoch == _validatedEpoch)', 'foreach ((Texture texture, int invalidatedSequence) in Textures)',
                  'if (texture.InvalidatedSequence != invalidatedSequence)', '_validationCurrent = false;', 'return false;',
                  '_validatedEpoch = epoch;', '_validationCurrent = quiet;'),
          'the validation walk is skipped only with no writer in flight and the epoch read before the last complete walk')
    check('GC.' not in ''.join(new for _, new in adapter.PAIRS) and 'lock (' not in ''.join(new for _, new in adapter.PAIRS), 'no lock, no collection')

    # --- executed ---
    build = run([DOTNET, 'build', str(candidate / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'), '-c', 'Release', '-nologo', '-m:1',
                 '-p:NuGetAudit=false'], candidate)
    check(build.returncode == 0, 'production Ryujinx.Graphics.Gpu builds')
    reports, compiled = {}, {}
    for variant, tree in (('control', control), ('candidate', candidate)):
        work = base / variant
        for relative in FILES:
            (work / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(tree / relative, work / relative)
        compiled[variant] = sha(work / adapter.CACHE)
        shutil.copyfile(ROOT / 'test/melonx_array_sync_epochs/Program.cs', work / 'Program.cs')
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable><ServerGarbageCollection>false</ServerGarbageCollection>
<EnableNETAnalyzers>false</EnableNETAnalyzers><NuGetAudit>false</NuGetAudit><NoWarn>0649;0162;0168;0219;8981</NoWarn>
<DefineConstants>ADAPTED</DefineConstants>
</PropertyGroup></Project>''')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        result = run([DOTNET, 'run', '--project', str(work / 'test.csproj'), '-c', 'Release'], work, 1800)
        check(result.returncode == 0, f'fixture built and ran on the {variant}')
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    if os.environ.get('MELONX_TEST_REPORTS'):
        Path(os.environ['MELONX_TEST_REPORTS']).write_text(json.dumps(reports))
    check(compiled['control'] == adapter.BASELINE[adapter.CACHE] and compiled['candidate'] == sha(candidate / adapter.CACHE) != compiled['control'],
          'the fixture compiled the control\'s cache and the candidate\'s')
    # The check has teeth: the candidate's cache with a texture double whose scale mode leaves the blacklist without the
    # signal (the first version of the adapter assumed it could not) must fail the fixture.
    silent = base / 'candidate'
    project = silent / 'test.csproj'
    project.write_text(project.read_text().replace('<DefineConstants>ADAPTED</DefineConstants>', '<DefineConstants>ADAPTED;NO_SCALE_SIGNAL</DefineConstants>'))
    wrong = subprocess.run([DOTNET, 'run', '--project', str(project), '-c', 'Release'], capture_output=True, text=True, timeout=1800, cwd=silent,
                           env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1'))
    silent_fails = wrong.returncode != 0 and 'blacklisted' in (wrong.stdout + wrong.stderr)
    check(silent_fails, 'a scale mode that leaves the blacklist unsignalled is caught by the fixture: rc %s %s' % (wrong.returncode, (wrong.stdout + wrong.stderr)[-300:]))

c, k = reports['control'], reports['candidate']
# IPA 736, second lot (adapt_array_dirty_log): a synchronisation that signals another texture is followed in the same
# update by the candidate (it reads the ring again), so a cascade can settle in fewer updates and run fewer per-update
# checks; every other group runs the same checks.
check(c['checks'] >= k['checks'] > 1_000_000, 'the same checks ran on both, cascades apart: %s / %s' % (c['checks'], k['checks']))
groups = ('scenarios', 'shared', 'buffers', 'removals', 'failures', 'syncs', 'overflows', 'invalidations', 'quiet')
for group in groups:
    check(c[group] == k[group] and len(c[group]) >= 2, f'{group}: the same backend contents, stores, uploads and texture states at every step')
check(len(c['scenarios']) == 72 and c['counters'] == k['counters'] and c['deltaPasses'] == k['deltaPasses'],
      '72 random scenarios; the same elements rebuilt, visited and changed, the same delta passes')
settled = lambda cascades: [{key: value for key, value in s.items() if key != 'mostUpdates'} for s in cascades]
check(settled(c['cascades']) == settled(k['cascades']) and len(c['cascades']) == 24 and max(s['mostUpdates'] for s in c['cascades']) > 1 and
      all(ks['mostUpdates'] <= cs['mostUpdates'] for cs, ks in zip(c['cascades'], k['cascades'])),
      'a synchronisation that signals another texture: the same state once settled, in no more updates')
for cw, kw in zip(c['writers'], k['writers']):
    n = kw['boundTextures']
    check(cw['quietSyncCalls'] == n and cw['quietSequenceReads'] == 2 * n, 'control: every quiet update walks the textures three times: %s' % cw)
    check(kw['quietSyncCalls'] == 0 and kw['quietSequenceReads'] == 0 and kw['quietAgainSyncCalls'] == 0 and kw['quietAgainSequenceReads'] == 0,
          'candidate: a quiet update walks nothing: %s' % kw)
    # IPA 736, second lot (adapt_array_dirty_log): the update after the writer's epoch moved reads its ring entry (one
    # synchronisation, of the texture it signalled) instead of walking again.
    check(kw['synchronisedWhileInFlight'] is True and kw['inFlightSyncCalls'] == n and kw['afterEpochSyncCalls'] == 1,
          'candidate: a dirty writer in flight makes the update walk, and the update after its epoch moved reads its entry: %s' % kw)
    check(kw['inFlightSequenceReads'] == 2 * n and kw['afterWriterSequenceReads'] == n,
          'candidate: a sequence writer in flight makes both validations walk, the next one re-establishes: %s' % kw)
visits = []
for cv, kv in zip(c['visits'], k['visits']):
    check(cv['digest'] == kv['digest'] and cv['boundElements'] == kv['boundElements'] >= 6000,
          'visits: the same backend contents and texture states after each of the 60 updates')
    check(cv['syncCallsPerUpdate'] >= 3000 and cv['sequenceReadsPerUpdate'] >= 6000, 'control: an update walks the 3 200 textures three times: %s' % cv)
    if not cv['cpuWrites']:
        limit = 2 * cv['changes'] + 2
        check(kv['syncCallsPerUpdate'] <= limit and kv['maxSyncCallsInOneUpdate'] <= limit and kv['sequenceReadsPerUpdate'] <= limit,
              'candidate: an update visits what changed (%s changes): %s' % (cv['changes'], kv))
    else:
        check(kv['maxSyncCallsInOneUpdate'] >= 3000 and kv['syncCallsPerUpdate'] <= cv['syncCallsPerUpdate'] / 4,
              'candidate: a CPU write or a tick of the clock makes the next update walk, the others not: %s' % kv)
    visits.append({'threaded': cv['threaded'], 'changes': cv['changes'], 'touched': cv['touched'], 'cpuWritesAndClock': cv['cpuWrites'],
                   'controlSyncCallsPerUpdate': cv['syncCallsPerUpdate'], 'candidateSyncCallsPerUpdate': round(kv['syncCallsPerUpdate'], 2),
                   'controlSequenceReadsPerUpdate': cv['sequenceReadsPerUpdate'], 'candidateSequenceReadsPerUpdate': round(kv['sequenceReadsPerUpdate'], 2),
                   'controlMicrosecondsPerUpdate': round(cv['microsecondsPerUpdate'], 1), 'candidateMicrosecondsPerUpdate': round(kv['microsecondsPerUpdate'], 1)})
print(json.dumps(visits, indent=1), flush=True)

inputs = ['build-utils/melonx/adapt_array_sync_epochs.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_array_sync_epochs_test.py',
          'test/melonx_array_sync_epochs/Program.cs', 'test/melonx_adapter_control.py']
report = {
    'result': 'passed', 'checks': checks, 'fixtureChecks': k['checks'], 'finalPreparationBound': FINAL_PREPARATION,
    'sourceKind': 'finalPreparationWithReversedControl' if FINAL_PREPARATION else 'pinnedPreparationPlusAdapter',
    'postimages': postimages, 'physicalDeviceTested': False, 'productionGpuAssemblyBuilt': True,
    'productionCacheAndCommandsCompiled': True, 'poolsTexturesAndTransportDoubled': True,
    'sourceBaseline': adapter.BASELINE, 'compiledCache': compiled,
    'scenariosWithIdenticalStates': sum(len(c[g]) for g in groups) + len(c['cascades']),
    'quietUpdateSyncCallsControl': c['visits'][0]['syncCallsPerUpdate'], 'quietUpdateSyncCallsCandidate': k['visits'][0]['syncCallsPerUpdate'],
    'quietUpdateSequenceReadsControl': c['visits'][0]['sequenceReadsPerUpdate'],
    'quietUpdateSequenceReadsCandidate': k['visits'][0]['sequenceReadsPerUpdate'],
    'visits': visits, 'writers': k['writers'], 'unsignalledScaleModeCaught': silent_fails,
    'deviceEvidence': 'IPA 729 Hogwarts Legacy (private journal, pid 58475): gpuWork arrayDelta 170-534 calls and 459-1 136 ms per 5 s '
                      'window during play, bindings 956-1 773 ms',
    'inputs': {path: sha(ROOT / path) for path in inputs},
    'limitation': 'Host: the production cache against doubled pools and textures; host microseconds are not device time. Other threads '
                  'signal textures on the device: the writers-in-flight protocol is exercised by its states, not by a race.',
}
out = ROOT / 'dist/melonx/array-sync-epochs-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS {checks} array sync epochs checks')
