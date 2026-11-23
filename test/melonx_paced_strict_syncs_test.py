#!/usr/bin/env python3
"""adapt_paced_strict_syncs on the final preparation, against its predecessor (the Core 743 preparation plus
adapt_nifm_network_watch) as control.

Usage: melonx_paced_strict_syncs_test.py <predecessor preparation> [--candidate-source <final preparation containing the adapter>]

IPA 729 Hogwarts Legacy: 24-31 command buffers per frame, 1 314-1 335 of 2 014-2 367 per 5 s submitted by a strict host
sync (3D syncpoint 913-1 041, SetReference 213-276), 0-2 syncs per window waited for before their command buffer was
submitted. The adapter paces those two sites and the two voluntary submissions to one per 4 ms, for Hogwarts Legacy only.

Static: only the three files change, each replacement present once and reversing to the control; the final preparation
with the later adapters sharing these files reversed (derived: postimage) is the candidate, byte for byte; of this
adapter's replacements, the final preparation lacks only the constants adapt_hogwarts_frame_budget retuned (one strict
sync per 6 ms instead of 4, voluntary submissions at 6 and 12 ms instead of 4 and 8); the sync is created at
the same place with the same number, only its strict flag changes, and only when it is not forced; no other caller is
paced; SyncManager.cs is not touched and still submits on demand a sync that is waited for before its command buffer was
submitted (the non-strict path the pacing relies on); the Library sets both flags from the Hogwarts test only.
Built: the production Ryujinx.Graphics.Vulkan, Ryujinx.Graphics.Gpu and Ryujinx.Library assemblies of the candidate.
Executed (test/melonx_paced_strict_syncs/Program.cs, fake clock): the production AutoFlushCounter.cs of the control and
of the candidate, whole, and the candidate's StrictSyncPacer replay one Hogwarts frame as IPA 729 measured it (760
draws over 34 ms in 82 render passes, three of them long, 12-13 syncpoint increments, 3-4 SetReference, 1 forced sync):
- control: 24-36 command buffers per frame with the journal's split (strict sync first, then draw auto-flush, few
  attachment auto-flushes; the device journaled 24-31): the replay is of the same order as the measurement, not a
  prediction of it;
- candidate with both flags off: the control's decisions, submission for submission;
- candidate with the policy: at most 14 command buffers and half the control's, no gap between two submissions over
  8.1 ms, every sync still created, the forced ones all submitted; with the syncs paced alone the voluntary
  submissions replace most of them, with the voluntary ones paced alone every strict sync still submits: both halves
  are needed;
- the pacer: first strict, then kept until its interval, other callers and the flag off never paced.
The candidate executed is the final preparation's counter and pacer (6 ms); the adapter alone (4 ms) is executed too,
with the same checks and its own numbers, and the final preparation must not submit more than it.
No device, no MoltenVK: the frame-rate effect is the device's to show. Writes dist/melonx/paced-strict-syncs-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import ORDER, control_source, files_edited_later, later_sharing, postimage  # noqa: E402
import importlib  # noqa: E402
import adapt_paced_strict_syncs as adapter  # noqa: E402
import adapt_texture_play_clock as play_clock  # noqa: E402
import adapt_queued_3d_syncpoints as queued_3d  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_paced_strict_syncs', _HOLD)

DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def run(command, cwd, timeout=1800):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                            env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1'))
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    return result


def clocked(text, frequency, timestamps):
    check(text.count('Stopwatch.Frequency') == frequency and text.count('Stopwatch.GetTimestamp()') == timestamps,
          f'clock reads of the auto-flush counter: {text.count("Stopwatch.Frequency")} / {text.count("Stopwatch.GetTimestamp()")}')
    text = text.replace('Stopwatch.Frequency', 'FakeClock.Frequency').replace('Stopwatch.GetTimestamp()', 'FakeClock.Now')
    check('Stopwatch' not in text, 'every clock read of the auto-flush counter is the fake clock')
    return text


with tempfile.TemporaryDirectory(prefix='melonx-paced-strict-syncs-') as temporary:
    base = Path(temporary).resolve()
    candidate = base / 'candidate'
    shutil.copytree(SOURCE, candidate, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
    for name, expected in adapter.BASELINE.items():
        check(hashlib.sha256((candidate / name).read_bytes()).hexdigest() == expected, 'control is the pinned preparation: ' + name)
    before = {name: (candidate / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
    untouched = {name: hashlib.sha256((candidate / name).read_bytes()).hexdigest() for name in
                 ('src/Ryujinx.Graphics.Vulkan/SyncManager.cs', 'src/Ryujinx.Graphics.Gpu/Engine/Threed/ThreedClass.cs',
                  'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs', 'src/Ryujinx.Graphics.Vulkan/PipelineFull.cs')}
    changed = adapter.apply(candidate)
    check(sorted(str(p.relative_to(candidate)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
    try:
        adapter.apply(candidate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    after = {name: (candidate / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
    if FINAL_PREPARATION:
        for name in adapter.BASELINE:
            if name not in files_edited_later('adapt_paced_strict_syncs'):
                check((candidate / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        # Next lot: adapt_texture_play_clock (CheckHostMemory's texture use clock), then adapt_queued_3d_syncpoints (the
        # queue's call site passed to CreateHostSyncIfNeeded) edit GpuContext.cs after this adapter; plan 748 rank 11:
        # adapt_device_critical_trim (TrimCaches and the periodic trim's escalation). After IPA 800 the Hogwarts lots
        # edit all three files (adapt_hogwarts_frame_budget: the pacing interval and the two voluntary timers;
        # adapt_hogwarts_steady_render: report submissions, the Library's texture storage flag) and
        # adapt_guest_start_during_shader_load edits GpuContext.cs. The expectation is derived instead of listed: the
        # final preparation with every later adapter sharing these files reversed, latest first (postimage: each back to
        # the bytes its BASELINE pins), must be this candidate, byte for byte; control_source() proved that re-applying
        # them gives the final preparation. The three adapters this gate knew stay the first editors, in GpuContext.cs.
        critical_names = ['adapt_device_critical_trim'] if 'adapt_device_critical_trim' in ORDER else []
        editors = [m for m in later_sharing('adapt_paced_strict_syncs') if set(importlib.import_module(m).BASELINE) & set(adapter.BASELINE)]
        known = ['adapt_texture_play_clock', 'adapt_queued_3d_syncpoints'] + critical_names
        check(editors[:len(known)] == known and
              set(play_clock.BASELINE) == {adapter.GPU_CONTEXT} and set(queued_3d.BASELINE) & set(adapter.BASELINE) == {adapter.GPU_CONTEXT} and
              all(set(importlib.import_module(m).BASELINE) & set(adapter.BASELINE) == {adapter.GPU_CONTEXT} for m in critical_names),
              'the first later adapters editing these files are adapt_texture_play_clock, adapt_queued_3d_syncpoints and '
              'adapt_device_critical_trim, in GpuContext.cs: %s' % editors)
        own = base / 'own-postimage'
        check(postimage('adapt_paced_strict_syncs', FINAL_SOURCE, own) == later_sharing('adapt_paced_strict_syncs'),
              'the later adapters reversed are those sharing these files')
        for name in adapter.BASELINE:
            check((own / name).read_bytes() == (candidate / name).read_bytes(), 'final preparation is the adapter, later adapters reversed: ' + name)
    for name, pairs in adapter.FILE_PAIRS.items():
        restored = after[name]
        for old, new in reversed(pairs):
            check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:70])
            restored = restored.replace(new, old)
        check(restored == before[name], 'nothing else changes in ' + name)
    for name, digest in untouched.items():
        check(hashlib.sha256((candidate / name).read_bytes()).hexdigest() == digest, 'not touched: ' + name)
    gpu = after[adapter.GPU_CONTEXT]
    create = gpu[gpu.index('internal void CreateHostSyncIfNeeded('):gpu.index('internal void RunDeferredActions()')]
    check(create.count('Renderer.CreateSync(SyncNumber, strict);') == 1 and create.count('SyncNumber++;') == 1 and
          create.index('_strictSyncPacer.Defer(') < create.index('NoteHostSync(caller, strict);') < create.index('Renderer.CreateSync(SyncNumber, strict);') and
          'if (strict && !force && _strictSyncPacer.Defer(caller,' in create and gpu.count('_strictSyncPacer') == 2 and
          gpu.count('public static bool PaceStrictHostSyncs { get; set; }') == 1 and 'PaceStrictHostSyncs = true' not in gpu,
          'the sync is created at the same place with the same number; only a strict, unforced one may lose its strict flag')
    check('CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint | HostSyncFlags.Force);' in gpu and
          'if (!GpuContext.PaceStrictHostSyncs || (caller != "IncrementSyncpoint" && caller != "SetReference"))' in gpu,
          'counter reports stay forced; only the two guest sites are paced')
    sync = (candidate / 'src/Ryujinx.Graphics.Vulkan/SyncManager.cs').read_text(encoding='utf-8-sig')
    check('_gd.CommandBufferPool.AddInUseWaitable(waitable);' in sync and 'if (result.NeedsFlush(_flushId))\n                {\n                    RequestFlush(result);' in sync and
          'if (handle.NeedsFlush(_flushId))' in sync and sync.count('_gd.FlushAllCommands();') == 2,
          'a sync that is not strict is attached to the open command buffer and submitted on demand when waited for')
    threed = (candidate / 'src/Ryujinx.Graphics.Gpu/Engine/Threed/ThreedClass.cs').read_text(encoding='utf-8-sig')
    fifo = (candidate / 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs').read_text(encoding='utf-8-sig')
    check('public void IncrementSyncpoint(int argument)' in threed and '_context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);' in threed and
          'public void SetReference(int argument)' in fifo and '_context.CreateHostSyncIfNeeded(HostSyncFlags.Strict);' in fifo,
          'the two paced sites are the methods the pacer names')
    library = after[adapter.LIBRARY]
    check(library.count('GpuContext.PaceStrictHostSyncs = hogwarts;') == 1 and library.count('SubmitPacing.Paced = hogwarts;') == 1 and
          'PaceStrictHostSyncs = true' not in library and 'SubmitPacing.Paced = true' not in library, 'both flags follow the Hogwarts Legacy test of the session')
    flush = after[adapter.AUTO_FLUSH]
    check(flush.count('SubmitPacing.Paced ?') == 2 and 'Stopwatch.Frequency / 250;' in flush and 'Stopwatch.Frequency / 125;' in flush and
          flush.count('MinDrawCountForFlush') == before[adapter.AUTO_FLUSH].count('MinDrawCountForFlush'),
          'only the two voluntary intervals depend on the policy (4 ms, 8 ms); the draw-count floor and the query rules are unchanged')

    # Bound to the final preparation: the tree built and executed as the candidate is the final preparation itself, later
    # adapters included (control_source reproduced it from this control); each replacement of this adapter is in it once.
    postimages = {}
    if FINAL_PREPARATION:
        # Each replacement of this adapter is in the final preparation once, as written, but for the constants a later
        # adapter retuned for the same policy. Reviewed: adapt_hogwarts_frame_budget (after IPA 800) paces the strict
        # syncs to one per 6 ms instead of 4 and the two voluntary submissions to 6 and 12 ms instead of 4 and 8 (its
        # reason: fewer command buffers per Hogwarts frame; a sync that is waited for still submits on demand through
        # SyncManager, which this gate reads above and no adapter touches). Exactly these lines of the adapter's
        # replacements are gone from the final preparation, each replaced by the line that follows it here.
        retuned = {
            '        public const double IntervalMs = 4.0;': '        public const double IntervalMs = 6.0;',
            '        // and on draw in fast flush mode (8 ms): the strict syncs paced on the GPU side are not replaced one for one.':
                '        // Wait 6 ms for an attachment change and 12 ms for an opportunistic draw flush.\n'
                '        // A real waiter still submits through SyncManager, irrespective of these timers.',
            '        private readonly static long _pacedFramebufferFlushTimer = Stopwatch.Frequency / 250;':
                '        private readonly static long _pacedFramebufferFlushTimer = Stopwatch.Frequency * 6 / 1000;',
            '        private readonly static long _pacedDrawFlushTimer = Stopwatch.Frequency / 125;':
                '        private readonly static long _pacedDrawFlushTimer = Stopwatch.Frequency * 12 / 1000;',
            '    /// 4 ms and 8 ms instead of 1 ms and 1.5 ms. On a tile-based GPU a submission inside a render pass stores and reloads':
                '    /// 6 ms and 12 ms instead of 1 ms and 1.5 ms. On a tile-based GPU a submission inside a render pass stores and reloads',
        }
        gone = []
        for name, pairs in adapter.FILE_PAIRS.items():
            final_text = (FINAL_SOURCE / name).read_text(encoding='utf-8-sig')
            for _, new in pairs:
                missing = [line for line in new.splitlines() if line.strip() and line not in final_text]
                gone += missing
                for line in missing:
                    check(line in retuned and new.count(line) == 1, 'a replacement line missing from the final preparation is a reviewed retune: ' + line.strip()[:70])
                    new = new.replace(line, retuned[line])
                check(final_text.count(new) == 1, 'replacement in the final preparation: ' + new.strip().splitlines()[0][:70])
        check(sorted(gone) == sorted(retuned) and 'adapt_hogwarts_frame_budget' in editors,
              'the retuned lines are exactly the reviewed ones (adapt_hogwarts_frame_budget): %s' % gone)
        shutil.rmtree(candidate)
        shutil.copytree(FINAL_SOURCE, candidate, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
        postimages = {name: hashlib.sha256((candidate / name).read_bytes()).hexdigest() for name in adapter.BASELINE}
        # The replay below runs the final preparation's auto-flush counter and pacer.
        gpu = (candidate / adapter.GPU_CONTEXT).read_text(encoding='utf-8-sig')
        flush = (candidate / adapter.AUTO_FLUSH).read_text(encoding='utf-8-sig')

    for project in ('src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj', 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj',
                    'src/Ryujinx.Library/Ryujinx.Library.csproj'):
        result = run([DOTNET, 'build', str(candidate / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'], candidate)
        check(result.returncode == 0, f'production {Path(project).stem} assembly builds')

    # Three engines: the control; the adapter alone (the control plus this adapter, when the final preparation differs
    # from it); the candidate, which is the final preparation's auto-flush counter and pacer.
    struct = lambda source: source[source.index('    internal struct StrictSyncPacer'):source.rindex('}')]
    engines = [('control', before[adapter.AUTO_FLUSH], 4, None), ('candidate', flush, 6, struct(gpu))]
    if FINAL_PREPARATION and (flush != after[adapter.AUTO_FLUSH] or struct(gpu) != struct(after[adapter.GPU_CONTEXT])):
        engines.insert(1, ('adapterAlone', after[adapter.AUTO_FLUSH], 6, struct(after[adapter.GPU_CONTEXT])))
    intervals = re.findall(r'public const double IntervalMs = (\d+\.\d+);', struct(gpu))
    check(len(intervals) == 1 and struct(gpu).count(' IntervalMs = ') == 1 and gpu.count('public const double IntervalMs = ') == 1,
          'the pacer declares its interval once')
    interval_ms = float(intervals[0])
    reports = {}
    for engine, text, frequency, pacer in engines:
        fixture = base / ('fixture-' + engine)
        fixture.mkdir()
        shutil.copy(ROOT / 'test/melonx_paced_strict_syncs/Program.cs', fixture / 'Program.cs')
        (fixture / 'AutoFlushCounter.cs').write_text(clocked(text, frequency, 5))
        if pacer is not None:
            (fixture / 'Pacer.cs').write_text('namespace Ryujinx.Graphics.Gpu\n{\n' + pacer + '}\n')
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit>' + ('<DefineConstants>CONTROL</DefineConstants>' if engine == 'control' else '') +
            '</PropertyGroup></Project>\n')
        check(run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'], fixture).returncode == 0,
              'fixture builds: ' + engine)
        result = run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')], fixture, 300)
        check(result.returncode == 0, 'fixture ran: ' + engine)
        reports[engine] = json.loads(next(line for line in reversed(result.stdout.splitlines()) if line.startswith('{')))

c, k = reports['control'], reports['candidate']
print(json.dumps(reports)[:3500], flush=True)
frame = c['frame']
check(24 <= frame['commandBuffers'] <= 36 and 15 <= frame['strictSyncSubmits'] <= 17 and 5 <= frame['drawAutoFlushes'] <= 13 and
      frame['attachmentAutoFlushes'] <= 4 and frame['syncsKeptOnTheOpenCommandBuffer'] == 0 and
      frame['strictSyncSubmits'] > frame['drawAutoFlushes'] > frame['attachmentAutoFlushes'],
      'control: the replayed frame submits in the order of IPA 729 (24-31 command buffers: strict sync, then draw auto-flush): ' + str(frame))
check(k['policyOff'] == c['frame'] and k['policyOffNoFastFlush'] == c['frameNoFastFlush'],
      'candidate with both flags off: the control\'s decisions, submission for submission')
paced = k['frame']
check(paced['commandBuffers'] <= 14 and paced['commandBuffers'] <= frame['commandBuffers'] / 2 and paced['forcedSubmits'] == frame['forcedSubmits'] and
      paced['strictSyncSubmits'] + paced['syncsKeptOnTheOpenCommandBuffer'] == frame['strictSyncSubmits'] and paced['strictSyncSubmits'] <= 9,
      'candidate: at most 14 command buffers and half the control\'s; every sync still created; forced syncs all submitted: ' + str(paced))
check(paced['longestGapMs'] <= 8.1 and k['frameNoFastFlush']['longestGapMs'] <= 8.1 and k['frameNoFastFlush']['commandBuffers'] <= 14,
      'candidate: never more than 8.1 ms between two submissions, with or without fast flush mode: %s / %s' % (paced['longestGapMs'], k['frameNoFastFlush']['longestGapMs']))
check(k['syncsPacedOnly']['commandBuffers'] >= frame['commandBuffers'] - 8 and k['syncsPacedOnly']['drawAutoFlushes'] > frame['drawAutoFlushes'] and
      k['submitsPacedOnly']['strictSyncSubmits'] == frame['strictSyncSubmits'] and k['submitsPacedOnly']['commandBuffers'] > paced['commandBuffers'] + 5,
      'pacing the syncs alone is mostly replaced by voluntary submissions, pacing those alone keeps every strict one: both are needed: %s / %s' %
      (k['syncsPacedOnly']['commandBuffers'], k['submitsPacedOnly']['commandBuffers']))
# The interval is the one the executed source declares: 4 ms as this adapter writes it, 6 ms in the final preparation
# (adapt_hogwarts_frame_budget, reviewed above). The fixture's times follow it; the nine decisions are the same.
check(k['pacer'] == [False, True, True, False, False, False, False, True, False] and k['pacerOff'] == [False, False, False] and
      k['intervalMs'] == interval_ms == (6.0 if 'adapterAlone' in reports else 4.0),
      'the pacer: first strict, kept until its interval, other callers and the flag off never paced: %s, %s ms' % (k['pacer'], k['intervalMs']))
alone = reports.get('adapterAlone')
if alone is not None:
    # The adapter alone, as it was bound when the final preparation was this candidate: the same checks, and its own
    # numbers (10 command buffers for the replayed frame, one strict sync per 4 ms).
    lone = alone['frame']
    check(alone['policyOff'] == c['frame'] and alone['policyOffNoFastFlush'] == c['frameNoFastFlush'],
          'adapter alone with both flags off: the control\'s decisions, submission for submission')
    check(lone['commandBuffers'] == 10 and lone['forcedSubmits'] == frame['forcedSubmits'] and
          lone['strictSyncSubmits'] + lone['syncsKeptOnTheOpenCommandBuffer'] == frame['strictSyncSubmits'] and lone['strictSyncSubmits'] <= 9 and
          lone['longestGapMs'] <= 8.1 and alone['frameNoFastFlush']['longestGapMs'] <= 8.1 and alone['frameNoFastFlush']['commandBuffers'] <= 14,
          'adapter alone: 10 command buffers, every sync still created, forced syncs all submitted, no gap over 8.1 ms: ' + str(lone))
    check(alone['syncsPacedOnly']['commandBuffers'] >= frame['commandBuffers'] - 8 and alone['syncsPacedOnly']['drawAutoFlushes'] > frame['drawAutoFlushes'] and
          alone['submitsPacedOnly']['strictSyncSubmits'] == frame['strictSyncSubmits'] and alone['submitsPacedOnly']['commandBuffers'] > lone['commandBuffers'] + 5,
          'adapter alone: both halves are needed')
    check(alone['pacer'] == [False, True, True, False, False, False, False, True, False] and alone['pacerOff'] == [False, False, False] and
          alone['intervalMs'] == 4.0, 'adapter alone: the pacer keeps a strict sync until 4 ms: ' + str(alone['pacer']))
    # The later retune only goes further the same way: no more command buffers or strict submissions than the adapter alone.
    check(paced['commandBuffers'] <= lone['commandBuffers'] and paced['strictSyncSubmits'] <= lone['strictSyncSubmits'] and
          k['submitsPacedOnly'] == alone['submitsPacedOnly'],
          'final preparation: no more command buffers than the adapter alone (%s / %s); the voluntary submissions paced alone are the same' %
          (paced['commandBuffers'], lone['commandBuffers']))

report = {
    'result': 'passed', 'checks': checks, 'finalPreparationBound': FINAL_PREPARATION,
    'sourceKind': 'finalPreparationWithReversedControl' if FINAL_PREPARATION else 'pinnedPreparationPlusAdapter',
    'physicalDeviceTested': False, 'productionVulkanAssemblyBuilt': True, 'productionGpuAssemblyBuilt': True,
    'productionLibraryAssemblyBuilt': True, 'controlCommandBuffersPerFrame': frame['commandBuffers'],
    'candidateCommandBuffersPerFrame': paced['commandBuffers'], 'candidateLongestGapMs': paced['longestGapMs'],
    'policyOffEqualsControl': True, 'control': c, 'candidate': k,
    'strictSyncIntervalMs': k['intervalMs'], 'adapterAlone': alone, 'adapterAloneExecuted': alone is not None,
    'adapterAloneCommandBuffersPerFrame': alone['frame']['commandBuffers'] if alone is not None else paced['commandBuffers'],
    'laterAdaptersEditingTheseFiles': editors if FINAL_PREPARATION else [],
    'postimages': postimages, 'sourceBaseline': adapter.BASELINE,
    'inputs': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in (
        'build-utils/melonx/adapt_paced_strict_syncs.py', 'build-utils/melonx/adapt_session.py',
        'test/melonx_paced_strict_syncs_test.py', 'test/melonx_paced_strict_syncs/Program.cs', 'test/melonx_adapter_control.py',
        'build-utils/melonx/adapt_texture_play_clock.py', 'build-utils/melonx/adapt_queued_3d_syncpoints.py')},
    'limitation': 'A replay of one frame on the production auto-flush counter with a fake clock; no MoltenVK, no device.',
}
out = ROOT / 'dist/melonx/paced-strict-syncs-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS {checks} paced strict syncs checks')
