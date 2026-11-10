#!/usr/bin/env python3
"""Even present pacing of a steady 30 fps guest on the iPhone (adapt_present_pacing), before and after.

Usage: melonx_present_pacing_test.py <base prepared MeloNX tree (Core 649 with the pending lot)>
       melonx_present_pacing_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the base preparation, candidate adds the adapter. For each, the production Ryujinx.Graphics.Vulkan assembly
is built (and the candidate's Ryujinx.Library, whose launch wiring the adapter changes). The fixture
(test/melonx_present_pacing/Program.cs) LOADS each variant's production Ryujinx.Graphics.Vulkan.dll: the candidate's
compiled PresentPacer decides every frame's desiredPresentTime and is fed back, as Window feeds it from
vkGetPastPresentationTimingGOOGLE, the on-glass time of the frames already shown; the control assembly has no
PresentPacer (asserted) and its Present chains no timing, so its frames are shown as soon as they are ready. Identical
frame-ready inputs for both. Measured: a scenario calibrated to the device histogram, the worst phase, display drift
both ways, GPU tails, 120 Hz latch, Core Animation rounding to the first or nearest refresh or one refresh late, pacing
not allowed, a 60 fps guest, an unstable cadence, a hitch; a sweep of jitter shape x GPU tail x rounding x 9 display
phases x 5 seeds compared run by run with the control (no regression); CAMetalLayer drawable waits; the bytes the
decision and the feedback allocate. Static checks bind the Present wiring, the Library's VSync gate, the iOS-only
extension, the clock and the calibration log line. When the MoltenVK 1.4.2 sources are present (/home/user/work/mvk or
$MOLTENVK_SOURCE), the presentAtTime / presentedTime path is checked there too. No device. Writes
dist/melonx/present-pacing-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_present_pacing', _HOLD)
import adapt_present_pacing  # noqa: E402
from adapt_present_pacing import apply, BASELINE  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
WINDOW = VULKAN + 'Window.cs'
INITIALIZATION = VULKAN + 'VulkanInitialization.cs'
RENDERER = VULKAN + 'VulkanRenderer.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
MOLTENVK = Path(os.environ.get('MOLTENVK_SOURCE', '/home/user/work/mvk/MoltenVK'))
# The maintainer's IPA 650 S1 gameplay on-glass gap counts (17 / 33 / 50 ms of 615 gaps; aggregate only).
DEVICE_S1 = {'17': 47, '33': 508, '50': 45, 'total': 615}
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def run(command, cwd, timeout=2400):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, env=environment, cwd=cwd)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    return result


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the base preparation: ' + name)

# The adapter's replacements, recorded on a scratch copy: the candidate must be the control with exactly these.
replacements = []
with tempfile.TemporaryDirectory(prefix='melonx-present-pacing-record-') as scratch:
    for name in BASELINE:
        (Path(scratch) / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / name, Path(scratch) / name)
    original_once = adapt_present_pacing.once

    def recording_once(path, old, new):
        replacements.append((path.relative_to(scratch).as_posix(), old, new))
        original_once(path, old, new)

    adapt_present_pacing.once = recording_once
    try:
        apply(Path(scratch))
    finally:
        adapt_present_pacing.once = original_once

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
texts, reports, assemblies = {}, {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-present-pacing-') as temporary:
    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_present_pacing/Program.cs', fixture / 'Program.cs')
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><Optimize>true</Optimize></PropertyGroup></Project>\n')
    check(run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'], fixture,
              900).returncode == 0, 'fixture builds')

    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                # Files a later adapter also edits (Core 658: adapt_present_drawable_residency in Window) are proven by
                # control_source's forward check; the others must be the final preparation's bytes here.
                later = files_edited_later('adapt_present_pacing')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
        check(run([DOTNET, 'build', str(work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release', '-nologo', '-m:1',
                   '-p:NuGetAudit=false'], work).returncode == 0, variant + ' production Vulkan assembly builds')
        if variant == 'candidate':
            check(run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo', '-m:1',
                       '-p:NuGetAudit=false'], work).returncode == 0, 'candidate Ryujinx.Library builds (launch wiring)')
        built = sorted((work / VULKAN / 'bin').rglob('Ryujinx.Graphics.Vulkan.dll'))
        check(len(built) == 1, variant + ': one production Ryujinx.Graphics.Vulkan.dll: ' + str(built))
        assemblies[variant] = hashlib.sha256(built[0].read_bytes()).hexdigest()
        print(variant + ': production assemblies built', flush=True)
        result = run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant, str(built[0])], fixture, 1800)
        check(result.returncode == 0, variant + ': fixture ran on the production assembly')
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))

c, k = reports['control'], reports['candidate']
cs, ks = c['scenarios'], k['scenarios']


def share(scenario, gap):
    return scenario['gaps'].get(gap, 0) / sum(scenario['gaps'].values())


def summary(s):
    keys = ('gaps', 'alternations17_50', 'alternationsPerSecond', 'nominalShare', 'pacedFrames', 'meanAddedMs', 'maxAddedMs',
            'drawableStalls', 'maxDrawableStallMs', 'misses', 'latticeShifts', 'reanchors', 'standDowns', 'finalMarginMs')
    return {key: s[key] for key in keys}


for name in cs:
    print('%-20s control %4d pairs %.3f at period | candidate %4d pairs %.3f, %4d paced, +%.2f ms mean (max %.2f), '
          'stalls %d->%d, misses %d, moves %d, stand-downs %d' % (
              name, cs[name]['alternations17_50'], cs[name]['nominalShare'], ks[name]['alternations17_50'], ks[name]['nominalShare'],
              ks[name]['pacedFrames'], ks[name]['meanAddedMs'], ks[name]['maxAddedMs'], cs[name]['drawableStalls'],
              ks[name]['drawableStalls'], ks[name]['misses'], ks[name]['latticeShifts'], ks[name]['standDowns']), flush=True)

check(c['pacer'] is False and k['pacer'] is True, 'control assembly without PresentPacer, candidate with it')
check(c['assembly'] == k['assembly'] == 'Ryujinx.Graphics.Vulkan', 'the production assemblies were loaded')
check(sorted(cs) == sorted(ks), 'same scenarios')
for name in cs:
    check(cs[name]['inputHash'] == ks[name]['inputHash'], name + ': identical frame-ready inputs')
    check(cs[name]['pacedFrames'] == 0 and cs[name]['maxAddedMs'] == 0, name + ': control never paces')
    check(ks[name]['notEarlierThanUnpaced'] and ks[name]['orderKept'], name + ': never shown earlier than unpaced, order kept')
    check(ks[name]['holdBounded'], name + ': each target at most margin + two refreshes after readiness')
    check(sum(cs[name]['gaps'].values()) == sum(ks[name]['gaps'].values()) == cs[name]['frames'] - 1, name + ': no frame lost')

# The device case: the control reproduces the S1 histogram; the candidate removes the alternation.
d_c, d_k = cs['deviceS1'], ks['deviceS1']
for gap in ('17', '33', '50'):
    check(abs(share(d_c, gap) - DEVICE_S1[gap] / DEVICE_S1['total']) <= 0.015,
          'deviceS1 control calibrated to the device histogram at %s ms: %.3f vs %.3f' % (gap, share(d_c, gap), DEVICE_S1[gap] / DEVICE_S1['total']))
check(1.5 <= d_c['alternationsPerSecond'] <= 5, 'deviceS1 control alternation rate in the device range: %s/s' % d_c['alternationsPerSecond'])
check(d_k['alternations17_50'] <= 3 and d_k['nominalShare'] >= 0.99, 'deviceS1 candidate steady: ' + json.dumps(summary(d_k)))
for name in ('boundary60', 'boundary60Nearest'):
    check(cs[name]['alternations17_50'] >= 100 and ks[name]['alternations17_50'] <= 3 and ks[name]['nominalShare'] >= 0.99,
          name + ': worst phase 17/50 alternation removed: ' + json.dumps(summary(ks[name])))
for name in ('drift60', 'drift60Nearest', 'drift60GpuTail', 'drift60GpuTail10'):
    check(ks[name]['alternations17_50'] * 10 <= cs[name]['alternations17_50'] and ks[name]['alternations17_50'] <= 15,
          '%s: only phase slips remain: %d -> %d' % (name, cs[name]['alternations17_50'], ks[name]['alternations17_50']))
check(ks['drift60GpuTail10']['finalMarginMs'] > 4, 'a 10 ms GPU tail raises the margin: ' + str(ks['drift60GpuTail10']['finalMarginMs']))
s_k = ks['drift60Slow']
check(s_k['alternations17_50'] <= 10 and s_k['latticeShifts'] >= 1 and s_k['meanAddedMs'] < 8.4,
      'slower display: the lattice moves earlier too: ' + json.dumps(summary(s_k)))
for name in ('promotion120', 'promotion120Nearest', 'reports120Latches60'):
    check(cs[name]['nominalShare'] < 0.6 and ks[name]['nominalShare'] >= 0.99, name + ': %.3f -> %.3f at 33 ms' % (
        cs[name]['nominalShare'], ks[name]['nominalShare']))
l_c, l_k = cs['boundary60LateByOne'], ks['boundary60LateByOne']
check(l_k['standDowns'] >= 1 and l_k['alternations17_50'] <= l_c['alternations17_50'] and l_k['nominalShare'] >= l_c['nominalShare'],
      'targets shown a refresh late: stands down, never worse: ' + json.dumps(summary(l_k)))
for name in ('notAllowed', 'guest60'):
    check(ks[name]['pacedFrames'] == 0 and ks[name]['gaps'] == cs[name]['gaps'] and ks[name]['meanAddedMs'] == 0,
          name + ': never paced, identical to the control')
u_c, u_k = cs['unstable'], ks['unstable']
check(u_k['alternations17_50'] <= u_c['alternations17_50'] and u_k['nominalShare'] >= u_c['nominalShare'],
      'unstable cadence not worse: ' + json.dumps(summary(u_k)))
h_c, h_k = cs['hitch'], ks['hitch']
check(h_k['reanchors'] >= 1 and h_k['pacedAfterHitch'] >= 580 and h_k['nominalShare'] >= 0.99 > h_c['nominalShare'],
      'hitch: re-anchored, steady again: ' + json.dumps(summary(h_k)))
for name in cs:
    if 'LateByOne' not in name:
        check(ks[name]['drawableStalls'] <= cs[name]['drawableStalls'], name + ': no new wait for a CAMetalLayer drawable')

# The sweep, run by run against the control of the same inputs.
sweep_rows, worse_runs, total_runs = [], 0, 0
by_key = {}
for row_c, row_k in zip(c['sweep'], k['sweep']):
    key = (row_c['rounding'], row_c['jitter'], row_c['jitterMs'], row_c['tailMs'])
    check(key == (row_k['rounding'], row_k['jitter'], row_k['jitterMs'], row_k['tailMs']) and row_c['inputHash'] == row_k['inputHash'],
          'sweep row inputs identical: ' + str(key))
    runs = list(zip(row_c['perRun'], row_k['perRun']))
    worse = sum(1 for a, b in runs if b[0] > a[0])
    excess = max(b[0] - a[0] for a, b in runs)
    smooth = [(a, b) for a, b in runs if a[0] <= 2]
    smooth_added = sum(b[2] for a, b in smooth) / len(smooth) if smooth else 0.0
    worse_runs += worse
    total_runs += len(runs)
    check(row_k['pairs'] <= row_c['pairs'], 'sweep %s: fewer pairs than the control: %d -> %d' % (key, row_c['pairs'], row_k['pairs']))
    off_excess = max(b[1] - a[1] for a, b in runs)
    if key[0] == 'lateByOne':
        # Each engagement shows a few frames a refresh late, then stands down for 30 s (doubling up to 4 min): a 900-frame run
        # holds exactly one probe. Pairs are bounded below (row total, per run); the probe's off-period gaps here.
        check(off_excess <= 10, 'sweep %s: a probe costs at most 10 gaps off the guest period: %d' % (key, off_excess))
    else:
        check(row_k['nonNominalGaps'] <= row_c['nonNominalGaps'],
              'sweep %s: fewer gaps off the guest period: %d -> %d' % (key, row_c['nonNominalGaps'], row_k['nonNominalGaps']))
    # Per run: at most 2 more pairs than the control of the same inputs (3 when every timed frame is shown a refresh late).
    check(excess <= (3 if key[0] == 'lateByOne' else 2), 'sweep %s: no run much worse than its control: +%d pairs' % (key, excess))
    check(all(b[0] <= a[0] + 1 for a, b in smooth) and smooth_added <= 2.0,
          'sweep %s: where the control is smooth, no pair added and <= 2 ms mean delay: %.2f' % (key, smooth_added))
    check(row_k['drawableStalls'] <= row_c['drawableStalls'] * 1.2 + 10 or row_c['rounding'] == 'lateByOne',
          'sweep %s: drawable waits %d -> %d' % (key, row_c['drawableStalls'], row_k['drawableStalls']))
    by_key[key] = row_k['pairs']
    sweep_rows.append(dict(rounding=key[0], jitter=key[1], jitterMs=key[2], tailMs=key[3], tailJitterMs=row_c['tailJitterMs'],
                           runs=len(runs), controlPairs=row_c['pairs'], candidatePairs=row_k['pairs'],
                           controlOffPeriodGaps=row_c['nonNominalGaps'], candidateOffPeriodGaps=row_k['nonNominalGaps'],
                           runsWorse=worse, worstRunExcessPairs=excess, worstRunExcessOffPeriodGaps=off_excess, controlSmoothRuns=len(smooth),
                           meanAddedMsWhereControlSmooth=round(smooth_added, 3), meanAddedMs=row_k['meanAddedMs'],
                           maxAddedMs=row_k['maxAddedMs'], pacedShare=row_k['pacedShare'], standDowns=row_k['standDowns'],
                           controlDrawableStalls=row_c['drawableStalls'], candidateDrawableStalls=row_k['drawableStalls']))
    print('sweep %-9s %-7s %4.1f ms tail %4.1f: pairs %5d -> %5d (worse runs %d/%d, max +%d), off-period %5d -> %5d, '
          '+%.2f ms mean, smooth-control runs %d +%.2f ms, stand-downs %d' % (
              key[0], key[1], key[2], key[3], row_c['pairs'], row_k['pairs'], worse, len(runs), excess, row_c['nonNominalGaps'],
              row_k['nonNominalGaps'], row_k['meanAddedMs'], len(smooth), smooth_added, row_k['standDowns']), flush=True)
for (rounding, jitter, amplitude, tail), pairs in by_key.items():
    if rounding == 'ceil':
        check(by_key[('nearest', jitter, amplitude, tail)] == pairs,
              'the same result whether Core Animation takes the first or the nearest refresh: %s %s %s' % (jitter, amplitude, tail))
allocation = k['decisionAllocation']
check(allocation['calls'] == 100000 and allocation['bytes'] == 0 and allocation['paced'] > 0, 'decision and feedback allocate nothing')

# Static: the candidate is the control plus exactly the adapter's replacements.
for name in BASELINE:
    text = texts['candidate'][name]
    for path, old, new in replacements:
        if path == name:
            check(text.count(new) == 1, 'replacement present once: ' + name)
            text = text.replace(new, old)
    check(text == texts['control'][name], 'unchanged but the adapter: ' + name)
window_k, window_c = texts['candidate'][WINDOW], texts['control'][WINDOW]
present_k = member(window_k, 'public unsafe override void Present(')
block = present_k[present_k.index('            // RewindBox (adapt_present_pacing): a guest'):present_k.index('            long queuePresentStart')]
check(present_k.replace(block, '') == member(window_c, 'public unsafe override void Present('), 'Present unchanged but the pacing block')
check(present_k.count('presentInfo.PNext = &presentTimes;') == 1 and
      re.search(r'if \(_presentPacer != null\)\s*\{\s*PacePresent\(&presentTime\);\s*if \(_presentPacer\.Tracking\)\s*\{\s*'
                r'presentInfo\.PNext = &presentTimes;', block), 'timing chained only with a pacer and pacing allowed')
check(present_k.index('PacePresent(&presentTime);') < present_k.index('lock (_gd.QueueLock)') <
      present_k.index('_gd.SwapchainApi.QueuePresent(_gd.Queue, in presentInfo);'), 'decided just before vkQueuePresentKHR')
check('SwapchainCount = 1,' in block and 'PTimes = &presentTime,' in block and 'PresentTimeGOOGLE presentTime = default;' in block,
      'present times for one swapchain, zero without a decision')
pace = member(window_k, 'private unsafe void PacePresent(')
check('_presentPacer.Next(now, _gd.PresentPacingAllowed && _vSyncMode == VSyncMode.Switch)' in pace,
      'paced only when the session allows it (Library VSync) and Window is at VSync Switch')
check(pace.index('_getPastPresentationTiming(_device, _swapchain, &count, timings)') < pace.index('_presentPacer.Observe(') <
      pace.index('_presentPacer.Next('), 'the frames MoltenVK has shown are fed back before the decision')
check('timings[i].PresentID, (long)timings[i].ActualPresentTime' in pace and 'presentTime->PresentID = _presentPacer.FrameId;' in pace,
      'feedback keyed by presentID')
check('_getRefreshCycleDuration(_device, _swapchain, &refreshCycle)' in pace and '_presentPacer.SetRefresh(' in pace,
      'display refresh queried per swapchain')
check('Present pacing over ' in pace and 'gaps 17/33/50/other ms' in pace and 'present call to glass mean' in pace and
      '5_000_000_000L' in pace and 'p.TakeWindow();' in pace, 'one calibration line per 5 s window: on-glass gaps and latency')
check('"vkGetPastPresentationTimingGOOGLE"' in window_k and '"vkGetRefreshCycleDurationGOOGLE"' in window_k and
      '_presentPacer = _getPastPresentationTiming != null && _getRefreshCycleDuration != null ? new PresentPacer() : null;' in window_k and
      'if (gd.SupportsPresentTiming && PresentClock.TryInitialize())' in window_k, 'pacer only with the extension, its entry points and clock')
clock = member(window_k, 'static partial class PresentClock')
check('"/usr/lib/libSystem.B.dylib"' in clock and 'mach_absolute_time()' in clock and 'mach_timebase_info(out' in clock and
      'ticks / _denom * _numer + ticks % _denom * _numer / _denom' in clock, 'presentAtTime time base: mach_absolute_time in ns')
pacer_class = member(window_k, 'sealed class PresentPacer')
for method in ('public ulong Next(long now, bool enabled)', 'public void Observe(uint presentId, long actual)'):
    code = re.sub(r'//[^\n]*', '', member(pacer_class, method))
    check(not re.search(r'\bnew\b|stackalloc|\$"|\.ToString\(', code), 'allocation free (no new, no string): ' + method)
check('return (ulong)(target - _refresh / 4);' in pacer_class, 'target a quarter refresh before the aimed slot (either rounding)')
renderer_k = texts['candidate'][RENDERER]
check('public bool PresentPacingAllowed { get; set; }' in renderer_k, 'renderer carries the session VSync choice')
check(renderer_k.index('SupportsPresentTiming = VulkanInitialization.UsesPresentTiming(_physicalDevice);') <
      renderer_k.index('_window = new Window(this, _surface,'), 'support known before the window exists')
library_k = texts['candidate'][LIBRARY]
gate = ('if (renderer is VulkanRenderer pacedVulkan) pacedVulkan.PresentPacingAllowed = !options.DisableVSync && '
        'options.VSyncMode == Ryujinx.Common.Configuration.VSyncMode.Switch;')
check(library_k.count(gate) == 1 and library_k.index(gate) < library_k.index('renderer = renderer.TryMakeThreaded(options.BackendThreading);'),
      'Library sets PresentPacingAllowed from the launch VSync choice, before the renderer is wrapped')
check('ChangeVSyncMode' not in library_k and library_k.count('options.DisableVSync ? Ryujinx.Common.Configuration.VSyncMode.Unbounded : options.VSyncMode') == 1,
      'the Library never changes Window VSync: the gate is the only carrier of the session choice')
init_k = texts['candidate'][INITIALIZATION]
check('internal const string PresentTimingExtension = "VK_GOOGLE_display_timing";' in init_k and
      'OperatingSystem.IsIOS() && physicalDevice.IsDeviceExtensionPresent(PresentTimingExtension);' in init_k,
      'extension enabled on iOS only, when exposed')
init_c = texts['control'][INITIALIZATION]
check(init_k[init_k.index('_desirableExtensions ='):init_k.index('_requiredExtensions =')] ==
      init_c[init_c.index('_desirableExtensions ='):init_c.index('_requiredExtensions =')], 'desirable extensions unchanged')

# MoltenVK 1.4.2: the path the change relies on.
moltenvk = {}
if (MOLTENVK / 'MoltenVK/GPUObjects/MVKImage.mm').is_file():
    files = {'api': 'MoltenVK/API/mvk_private_api.h', 'extensions': 'MoltenVK/Layers/MVKExtensions.def',
             'image': 'MoltenVK/GPUObjects/MVKImage.mm', 'queue': 'MoltenVK/GPUObjects/MVKQueue.mm',
             'swapchain': 'MoltenVK/GPUObjects/MVKSwapchain.mm', 'clock': '../Common/MVKOSExtensions.mm'}
    mvk = {key: (MOLTENVK / path).read_text(errors='replace') for key, path in files.items()}
    check(re.search(r'MVK_VERSION_MINOR\s+4\b', mvk['api']) and re.search(r'MVK_VERSION_PATCH\s+2\b', mvk['api']), 'MoltenVK 1.4.2 sources')
    check(re.search(r'MVK_EXTENSION\(GOOGLE_display_timing,\s+GOOGLE_DISPLAY_TIMING,\s+DEVICE,\s+10\.11,\s+8\.0', mvk['extensions']),
          'MoltenVK exposes VK_GOOGLE_display_timing on iOS 8.0+')
    check(re.search(r'if \(presentInfo\.desiredPresentTime\) \{\s*\[mtlDrwbl presentAtTime: \(double\)presentInfo\.desiredPresentTime \* 1\.0e-9\];'
                    r'\s*\} else \{\s*\[mtlDrwbl present\];', mvk['image']),
          'MoltenVK: a non-zero desiredPresentTime is presentAtTime (s), zero is the plain present')
    check('endPresentation(presentInfo, signaler, mtlDrwbl.presentedTime * 1.0e9);' in mvk['image'],
          'MoltenVK reports the drawable presentedTime (s -> ns)')
    check('presentInfo.presentIDGoogle = pPresentTimes[scIdx].presentID;' in mvk['queue'] and
          'presentInfo.desiredPresentTime = pPresentTimes[scIdx].desiredPresentTime;' in mvk['queue'], 'MoltenVK reads the chained times')
    check('_presentTimingHistory[_presentHistoryIndex].presentID = presentInfo.presentIDGoogle;' in mvk['swapchain'] and
          '_presentTimingHistory[_presentHistoryIndex].actualPresentTime = actualPresentTime;' in mvk['swapchain'] and
          'VkResult MVKSwapchain::getPastPresentationTiming(' in mvk['swapchain'], 'MoltenVK keeps presentID -> actualPresentTime for every present')
    check('mach_absolute_time() * _mvkMachTimebase.numer / _mvkMachTimebase.denom' in mvk['clock'], 'MoltenVK fallback time is mach ns too')
    moltenvk = {path: hashlib.sha256((MOLTENVK / path).read_bytes()).hexdigest() for path in files.values()}

inputs = ['build-utils/melonx/adapt_present_pacing.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_present_pacing_test.py', 'test/melonx_present_pacing/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
measurements = {name: dict(control=summary(cs[name]), candidate=summary(ks[name])) for name in cs}
measurements['deviceS1Histogram'] = dict(device={g: round(DEVICE_S1[g] / DEVICE_S1['total'], 4) for g in ('17', '33', '50')},
                                         control={g: round(share(d_c, g), 4) for g in ('17', '33', '50')})
measurements['sweep'] = sweep_rows
measurements['sweepRunsWorseThanControl'] = dict(worse=worse_runs, runs=total_runs)
measurements['decisionAllocation'] = allocation
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'basePreparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               measurements=measurements, sdk=sdk, physicalDeviceTested=False,
               productionVulkanAssemblyExecuted=True, productionAssemblySha256=assemblies, candidateLibraryBuilt=True,
               presentWiringExecuted=False, moltenVkSourceChecked=bool(moltenvk), moltenVkSources=moltenvk, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='The decision code executed is the compiled PresentPacer of the production Ryujinx.Graphics.Vulkan.dll; '
                          'Window.Present (vkGetPastPresentationTimingGOOGLE drain, PresentTimesInfoGOOGLE chaining, the Library '
                          'VSync gate) is bound by static checks only, and on glass is simulated: Core Animation honouring '
                          'presentAtTime at the first or nearest refresh (or one refresh late, where the pacer stands down), '
                          'presentedTime a refresh time, recorded-like ready times (uniform, Gaussian, late-exponential jitter), '
                          'GPU tails 1.5 to 20 ms, 3 CAMetalLayer drawables held until replaced on glass. The device-side '
                          '"Present pacing over" line (MoltenVK on-glass gaps, present-call-to-glass latency, misses) is what '
                          'confirms or refutes the model on the iPhone. The calibrated scenario adds about 15 ms mean on glass: '
                          'smoothness there needs the later refresh for every frame.')
out = ROOT / 'dist/melonx/present-pacing-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, sweepRunsWorse=worse_runs, sweepRuns=total_runs)))
