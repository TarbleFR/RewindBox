"""Show a steady 30 fps guest every 33.3 ms on the iPhone, instead of alternating 17 ms and 50 ms gaps.

IPA 650 and IPA 643, 4 November 2026, maintainer's iPhone (ProMotion), Hogwarts Legacy, MoltenVK 1.4.2 (private logs, not
in the repository): at a steady guest 30 fps the on-glass gaps are not all 33 ms. S1 gameplay: 508 of 615 gaps at 33 ms,
47 at 17 ms, 45 at 50 ms, at times about five adjacent 17/50 pairs per second (0.8 per second in an IPA 643 session).
A 17 ms gap next to a 50 ms one is a frame shown one display refresh early or late: visible judder, no frame lost.

Mechanism (read in the Core 649 preparation and in MoltenVK 1.4.2): the guest composes on a 60 Hz timer of the host
clock (Ryujinx.HLE SurfaceFlinger, swap interval 2 for a 30 fps game) and the Vulkan backend presents each frame as soon
as it reaches Window.Present: vkQueuePresentKHR without timing, MoltenVK calls [CAMetalDrawable present] and Core
Animation shows the frame at the first refresh after its GPU work completes. The guest timer is not phase locked to the
display; while completions fall near a refresh boundary, a few milliseconds of jitter pick between two refreshes and
33.3 ms of guest cadence become 17 + 50 ms on glass. RewindBox's set_present_target_fps only acts at swap interval 0.
MoltenVK 1.4.2 exposes VK_GOOGLE_display_timing on iOS (MVKExtensions.def: iOS 8.0): a chained desiredPresentTime
(ns) becomes [drawable presentAtTime: t * 1e-9] in the present command buffer's scheduled handler (MVKImage.mm), and
every present, timed or not, records its presentID and actualPresentTime (the drawable's presentedTime, a display
refresh, x 1e9) for vkGetPastPresentationTimingGOOGLE (MVKSwapchain.mm endPresentation, 60 entries). Both are host
times of mach_absolute_time in ns (CACurrentMediaTime; mvkGetRuntimeNanoseconds), PresentClock's base.

Change (Ryujinx.Graphics.Vulkan and the Library's launch wiring):
- VulkanInitialization: on iOS, when the device exposes it, VK_GOOGLE_display_timing is enabled; nowhere else.
- VulkanRenderer: SupportsPresentTiming (same predicate, before the window exists) and PresentPacingAllowed, set by
  Ryujinx.Library at launch to `!DisableVSync && VSyncMode == Switch` (the Library never calls Window.ChangeVSyncMode,
  so Window's own _vSyncMode stays Switch for the session: without this, Unbounded with a 30 fps present target would
  be paced too). Window paces only when both PresentPacingAllowed and its _vSyncMode is Switch.
- Window: PresentPacer (allocation free, render thread only), PresentClock, and the two GOOGLE entry points from
  vkGetDeviceProcAddr. Before each present, the frames MoltenVK has shown are drained from
  vkGetPastPresentationTimingGOOGLE into the pacer (presentID, actualPresentTime), then the pacer decides:
  * cadence: at least 7 of the last 8 present intervals at the same multiple N (2..4) of 16.67 ms;
  * a lattice of on-glass slots N x 16.67 ms apart, anchored on a refresh the display really showed (the 60 Hz grid of
    the last actualPresentTime) at the first slot the frame can make (ready + margin), re-anchored on every frame shown
    on its slot so it follows the display's own clock;
  * desiredPresentTime = slot - refresh / 4 (vkGetRefreshCycleDurationGOOGLE): shown on that slot whether Core
    Animation takes the first refresh at or after the target or the nearest one; a frame not ready for its slot has a
    target already passed and is shown as soon as ready, without moving the lattice (one late outlier);
  * observed misses (shown after the slot) move the lattice one refresh later when two fall within 8 frames, and raise
    the margin (initially 4 ms, the GPU tail after the present call) to what the missed frame needed; the lattice moves
    one refresh earlier only when every frame of a 2 s window would have made it, and not within 10 s of a miss;
  * stand down (no target) for 30 s, doubling up to 4 min, when a frame aimed at least 33 ms (the maximum margin) after
    it was ready is still shown late, after 6 misses in a row or 4 lattice moves within 10 s: the targets are not
    honoured as modelled; and no target for the first 8 frames, at an unstable cadence, after a hitch (re-anchored),
    or when pacing is not allowed. VkPresentTimesInfoGOOGLE is chained whenever pacing is allowed (presentID for the
    feedback; desiredPresentTime 0 makes MoltenVK call [drawable present] exactly as without it), never otherwise.
  * one "Present pacing over N ms" line per 5 s window on iOS: MoltenVK's on-glass gaps (17/33/50/other ms), adjacent
    17/50 pairs, present-call-to-glass latency mean/max, slots hit and missed, lattice moves, stand-downs, margin. These
    are the device-side numbers that calibrate the model below.

Measured effect (test/melonx_present_pacing_test.py, SDK 10.0.100; the production Ryujinx.Graphics.Vulkan.dll of each
variant is built and loaded, its compiled PresentPacer decides each frame and is fed back the simulated on-glass times as
Window feeds it; identical frame-ready inputs; every number is in dist/melonx/present-pacing-checks.json). Adjacent 17/50
pairs, control -> candidate: calibrated to the device histogram (control 8.2/83.6/8.2 % at 17/33/50 ms against the
device's 7.6/82.6/7.3 %, 2.4 pairs/s) 142 -> 1 over 1800 frames, at a mean 15 ms later on glass (every frame must sit
on the later refresh to absorb the 8 % late ones); worst phase 250 -> 1 whether Core Animation takes the first or the
nearest refresh; a display drifting 0.05 % faster 145 -> 12, slower 146 -> 1; GPU tails 5 +- 2 and 10 +- 4 ms
208 -> 12 and 318 -> 11 (margin learned: 6.0 and 13.9 ms); 120 Hz latch 236 -> 3; a hitch 70 -> 1. Sweep of 8 jitter
shapes (uniform 1/2.5/6, Gaussian 2.5/4/8, late-exponential 2.5/4 ms) x 4 GPU tails (1.5 to 20 ms) x 9 display phases x
5 seeds, 1440 runs per rounding: 166,505 -> 80,616 pairs, identical under both roundings; fewer pairs and fewer gaps off
33 ms in every row (Gaussian 8 ms: 10142 -> 9793, the cadence is rarely stable there); 8 runs of 1440 one or two pairs
worse than their control; where the control is already smooth, no pair added and at most 1.24 ms mean delay. If Core
Animation showed timed frames one refresh late: never more pairs than the control, each probe at most 10 off-period
gaps, then stand-down. CAMetalLayer drawable waits (3 drawables): 0 in every named scenario, 69 -> 74 over the sweep
(heaviest jitter with a 20 ms tail). The decision and the feedback allocate 0 bytes over 100,000 frames.

Limits: not measured on an iPhone. The model of Core Animation (presentAtTime honoured at the first or nearest refresh;
presentedTime a refresh time) and the device's GPU tail and jitter shape are what the per-window line verifies; jitter
wider than a refresh period leaves pairs (the pacer then often stands down). Holding a frame on its slot adds latency:
at most two refreshes for an early outlier, half a refresh on average where the control judders at the worst phase.
Fail closed on drift: each file must be the base preparation's (Core 649 with the pending lot).
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/Window.cs': 'e8fc3a7d854279a96f3822570b05812ea302dbb96194a986a96d20e261f09640',
    'src/Ryujinx.Graphics.Vulkan/VulkanInitialization.cs': 'c186f3849f728a3daa309a82ab9a3f674627aebf37414c7c0e8d23880bef8a9d',
    'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs': '8d4a9f8b86b2eb06fd82a3f2b83595bdc41dfed75147e88d5b8048c7eb189cb6',
    'src/Ryujinx.Library/Library.cs': '8fd1ace3ffea04ef5608bc1a9b7f3cd78c5f3921ce8e1ba39946f9e552c0439d',
}

PACER = '''
    // RewindBox (adapt_present_pacing): frame pacing of a guest presenting at a steady multiple of its 60 Hz period.
    // Render thread only; no allocation after construction. Times are nanoseconds of PresentClock, the base of
    // [CAMetalDrawable presentAtTime:] and of MoltenVK's actualPresentTime (presentedTime).
    sealed class PresentPacer
    {
        // The guest composes on a 60 Hz timer of the host clock (SurfaceFlinger); a 30 fps game presents every 2 periods.
        public const long GuestVsyncNanoseconds = 1_000_000_000L / 60;
        public const int CadenceFrames = 8;

        // Initial estimate of the time from the present call to the frame's GPU completion; raised by observed misses.
        public const long MinMarginNanoseconds = 4_000_000;
        public const long MaxMarginNanoseconds = 2 * GuestVsyncNanoseconds;
        private const long MarginStepNanoseconds = 1_000_000;
        private const long MarginDecayNanoseconds = 500_000;
        private const int MarginDecayHits = 300;
        // The lattice moves earlier only when every frame of a 2 s window would have made the refresh before, and not
        // within 10 s of a miss or a later move.
        private const int EarlyWindowFrames = 60;
        private const int QuietFrames = 300;
        // Stand down when the targets are not honoured as modelled: a frame aimed at least the maximum margin after it
        // was ready is still shown late (no plausible GPU tail explains it), or 6 misses in a row on the current lattice.
        private const int MissRun = 6;
        // Lattice shifts this close together mean the targets are not honoured as modelled: stand down for 30 s.
        private const int ShiftBurst = 4;
        private const uint ShiftBurstFrames = 300;
        // Off for 30 s, doubled at each stand-down up to 4 min, back to 30 s after 600 frames shown on their slot.
        private const int StandDownFrames = 900;
        private const int MaxStandDownFrames = 7200;
        private const int StandDownResetHits = 600;
        private const int History = 32;

        private readonly long[] _intervals = new long[CadenceFrames];
        private int _count;
        private int _next;
        private long _lastReady;

        // The frames recently decided (by presentID): ready time and aimed on-glass slot (0: not paced).
        private readonly uint[] _ids = new uint[History];
        private readonly long[] _readyTimes = new long[History];
        private readonly long[] _slots = new long[History];
        private readonly bool[] _fits = new bool[History];
        private readonly uint[] _shiftFrames = new uint[ShiftBurst];
        private int _shiftNext;
        private uint _frame;

        private long _refresh = GuestVsyncNanoseconds;
        private long _glass;
        private long _lastGlass;
        private int _lastGapClass;
        // The lattice: frame _latticeFrame is shown at _latticeTime, each next frame one guest period later.
        private long _latticeTime;
        private uint _latticeFrame;
        private uint _latticeChange;
        private int _latticeMultiple;
        private long _margin = MinMarginNanoseconds;
        private int _lateWindow;
        private int _earlyFrames;
        private long _minSlack = long.MaxValue;
        private int _framesSinceLate;
        private int _hitsSinceMiss;
        private int _missRun;
        private int _standDown;
        private int _standDownLength = StandDownFrames;

        public int Multiple { get; private set; }
        public bool Tracking { get; private set; }
        public uint FrameId => _frame;
        public long MarginNanoseconds => _margin;
        public long RefreshNanoseconds => _refresh;
        public long PacedFrames { get; private set; }
        public long Misses { get; private set; }
        public long LatticeShifts { get; private set; }
        public long Reanchors { get; private set; }
        public long StandDowns { get; private set; }

        // Per log window (reset by TakeWindow): MoltenVK's on-glass gaps and the present-call-to-glass latency.
        public long WindowFrames { get; private set; }
        public long WindowPaced { get; private set; }
        public long WindowHits { get; private set; }
        public long WindowMisses { get; private set; }
        public long WindowShifts { get; private set; }
        public long Gaps17 { get; private set; }
        public long Gaps33 { get; private set; }
        public long Gaps50 { get; private set; }
        public long GapsOther { get; private set; }
        public long Alternations { get; private set; }
        public long LatencyCount { get; private set; }
        public long LatencySum { get; private set; }
        public long LatencyMax { get; private set; }

        // The display refresh (vkGetRefreshCycleDurationGOOGLE); a target a quarter refresh before the aimed refresh is
        // shown at that refresh whether Core Animation takes the first refresh at or after it or the nearest one.
        public void SetRefresh(long refreshNanoseconds)
        {
            _refresh = Math.Clamp(refreshNanoseconds, 4_000_000, GuestVsyncNanoseconds);
        }

        public void TakeWindow()
        {
            WindowFrames = WindowPaced = WindowHits = WindowMisses = WindowShifts = 0;
            Gaps17 = Gaps33 = Gaps50 = GapsOther = Alternations = 0;
            LatencyCount = LatencySum = LatencyMax = 0;
        }

        // A presented frame (vkGetPastPresentationTimingGOOGLE, in presentation order): presentID, actualPresentTime.
        public void Observe(uint presentId, long actual)
        {
            if (actual <= 0)
            {
                return;
            }

            if (_lastGlass != 0 && actual > _lastGlass)
            {
                long gap = actual - _lastGlass;
                int gapClass = (int)((gap + GuestVsyncNanoseconds / 4) / (GuestVsyncNanoseconds / 2));

                if (gapClass == 2)
                {
                    Gaps17++;
                }
                else if (gapClass == 4)
                {
                    Gaps33++;
                }
                else if (gapClass == 6)
                {
                    Gaps50++;
                }
                else
                {
                    GapsOther++;
                }

                if (gapClass != _lastGapClass && gapClass + _lastGapClass == 8 && gapClass != 4)
                {
                    Alternations++;
                }

                _lastGapClass = gapClass;
            }

            _lastGlass = Math.Max(_lastGlass, actual);

            int slot = (int)(presentId % History);

            if (presentId == 0 || _ids[slot] != presentId || actual < _readyTimes[slot] ||
                actual - _readyTimes[slot] > 250_000_000)
            {
                return;
            }

            long latency = actual - _readyTimes[slot];
            LatencyCount++;
            LatencySum += latency;
            LatencyMax = Math.Max(LatencyMax, latency);
            _glass = actual;

            long expected = _slots[slot];

            if (expected == 0)
            {
                return;
            }

            if (actual < expected + _refresh / 2)
            {
                if (actual > expected - _refresh / 2)
                {
                    WindowHits++;

                    // Drift: the lattice follows the display's own refresh times.
                    if (_latticeTime != 0 && SlotOf(presentId) == expected)
                    {
                        _latticeTime = actual;
                        _latticeFrame = presentId;
                    }
                }

                _missRun = 0;

                if (_fits[slot] && ++_hitsSinceMiss % MarginDecayHits == 0)
                {
                    _margin = Math.Max(MinMarginNanoseconds, _margin - MarginDecayNanoseconds);
                }

                if (_hitsSinceMiss == StandDownResetHits)
                {
                    _standDownLength = StandDownFrames;
                }
            }
            else
            {
                // Shown after its slot. A single late frame keeps the lattice; a second within 8 frames moves it. A frame
                // decided before the last lattice change says nothing of the current lattice.
                Misses++;
                WindowMisses++;
                bool current = (int)(presentId - _latticeChange) >= 0;
                _lateWindow |= current ? 1 : 0;
                _framesSinceLate = 0;

                if (_fits[slot])
                {
                    // Ready in time by the estimate, yet shown later: the GPU tail is longer than the margin.
                    _margin = Math.Min(MaxMarginNanoseconds, Math.Max(_margin + MarginStepNanoseconds,
                        expected - _readyTimes[slot] + MarginStepNanoseconds));
                    _hitsSinceMiss = 0;
                }

                bool implausible = _fits[slot] && expected - _readyTimes[slot] >= MaxMarginNanoseconds;

                if (current && (implausible || ++_missRun >= MissRun) && _standDown == 0)
                {
                    StandDown();
                }
            }
        }

        // The desired present time of a frame ready now (0: present as soon as ready, as without pacing).
        public ulong Next(long now, bool enabled)
        {
            Tracking = enabled;
            WindowFrames++;

            if (!enabled)
            {
                _count = 0;
                _next = 0;
                _lastReady = 0;
                _glass = 0;
                _latticeTime = 0;
                _lateWindow = 0;
                _standDown = 0;
                _missRun = 0;
                Multiple = 0;

                return 0;
            }

            if (++_frame == 0)
            {
                _frame = 1;
            }

            if (_lastReady != 0)
            {
                _intervals[_next] = now - _lastReady;
                _next = (_next + 1) % CadenceFrames;
                _count = Math.Min(_count + 1, CadenceFrames);
            }

            _lastReady = now;
            Multiple = StableMultiple();

            int slot = (int)(_frame % History);
            _ids[slot] = _frame;
            _readyTimes[slot] = now;
            _slots[slot] = 0;
            _fits[slot] = false;
            _lateWindow = (_lateWindow << 1) & 0xFF;
            _framesSinceLate++;

            if (_standDown > 0)
            {
                _standDown--;
                _latticeTime = 0;

                return 0;
            }

            if (Multiple == 0 || _glass == 0 || now - _glass > 1_000_000_000L)
            {
                _latticeTime = 0;

                return 0;
            }

            long need = now + _margin;
            long target;

            if (_latticeTime == 0 || _latticeMultiple != Multiple)
            {
                target = Anchor(need);
            }
            else
            {
                target = SlotOf(_frame);

                if (need > target + GuestVsyncNanoseconds || target - need >= 2 * GuestVsyncNanoseconds)
                {
                    // A hitch or a cadence step: a new lattice from this frame.
                    Reanchors++;
                    target = Anchor(need);
                }
                else if (System.Numerics.BitOperations.PopCount((uint)_lateWindow) >= 2)
                {
                    // Two frames shown after their slot within 8 frames: the lattice moves one refresh later.
                    target = Shift(GuestVsyncNanoseconds);
                    _framesSinceLate = 0;
                }
                else
                {
                    // A frame late for its slot is presented with a target already passed: shown as soon as ready.
                    // An early frame is held to its slot; the lattice moves earlier only when the whole window was early.
                    _minSlack = Math.Min(_minSlack, target - need);

                    if (++_earlyFrames >= EarlyWindowFrames)
                    {
                        if (_minSlack >= GuestVsyncNanoseconds && _framesSinceLate >= QuietFrames)
                        {
                            target = Shift(-GuestVsyncNanoseconds);
                        }

                        _earlyFrames = 0;
                        _minSlack = long.MaxValue;
                    }
                }
            }

            if (_standDown > 0)
            {
                return 0;
            }

            _slots[slot] = target;
            _fits[slot] = need <= target;
            PacedFrames++;
            WindowPaced++;

            return (ulong)(target - _refresh / 4);
        }

        private long SlotOf(uint frame) => _latticeTime + (long)(int)(frame - _latticeFrame) * _latticeMultiple * GuestVsyncNanoseconds;

        private long Anchor(long need)
        {
            // The first refresh (on the 60 Hz grid of the last on-glass time) the frame is expected to make.
            long distance = need - _glass;
            long steps = distance > 0 ? (distance + GuestVsyncNanoseconds - 1) / GuestVsyncNanoseconds : -(-distance / GuestVsyncNanoseconds);
            _latticeTime = _glass + steps * GuestVsyncNanoseconds;
            _latticeFrame = _frame;
            _latticeChange = _frame;
            _latticeMultiple = Multiple;
            _lateWindow = 0;
            _earlyFrames = 0;
            _minSlack = long.MaxValue;

            return _latticeTime;
        }

        private long Shift(long by)
        {
            _latticeTime += by;
            _latticeChange = _frame;
            _lateWindow = 0;
            _earlyFrames = 0;
            _minSlack = long.MaxValue;
            LatticeShifts++;
            WindowShifts++;

            uint oldest = _shiftFrames[_shiftNext];
            _shiftFrames[_shiftNext] = _frame;
            _shiftNext = (_shiftNext + 1) % ShiftBurst;

            if (oldest != 0 && _frame - oldest < ShiftBurstFrames)
            {
                StandDown();
            }

            return SlotOf(_frame);
        }

        private void StandDown()
        {
            StandDowns++;
            _standDown = _standDownLength;
            _standDownLength = Math.Min(MaxStandDownFrames, _standDownLength * 2);
            _latticeTime = 0;
            _margin = MinMarginNanoseconds;
            _missRun = 0;
            Array.Clear(_shiftFrames);
        }

        private int StableMultiple()
        {
            if (_count < CadenceFrames)
            {
                return 0;
            }

            // At least 7 of the last 8 intervals at the same multiple: a single outlier keeps the cadence.
            int twos = 0, threes = 0, fours = 0;

            for (int i = 0; i < CadenceFrames; i++)
            {
                long rounded = (_intervals[i] + GuestVsyncNanoseconds / 2) / GuestVsyncNanoseconds;
                twos += rounded == 2 ? 1 : 0;
                threes += rounded == 3 ? 1 : 0;
                fours += rounded == 4 ? 1 : 0;
            }

            return twos >= CadenceFrames - 1 ? 2 : threes >= CadenceFrames - 1 ? 3 : fours >= CadenceFrames - 1 ? 4 : 0;
        }
    }
    // RewindBox (adapt_present_pacing): the host time base of [CAMetalDrawable presentAtTime:] and of MoltenVK's
    // actualPresentTime (CACurrentMediaTime is mach_absolute_time scaled by mach_timebase_info), in nanoseconds.
    static partial class PresentClock
    {
        private const string LibSystem = "/usr/lib/libSystem.B.dylib";

        private struct MachTimebaseInfo
        {
            public uint Numer;
            public uint Denom;
        }

        private static ulong _numer;
        private static ulong _denom;

        [System.Runtime.InteropServices.LibraryImport(LibSystem)]
        private static partial ulong mach_absolute_time();

        [System.Runtime.InteropServices.LibraryImport(LibSystem)]
        private static partial int mach_timebase_info(out MachTimebaseInfo info);

        public static bool TryInitialize()
        {
            try
            {
                if (mach_timebase_info(out MachTimebaseInfo info) != 0 || info.Numer == 0 || info.Denom == 0)
                {
                    return false;
                }

                _numer = info.Numer;
                _denom = info.Denom;
                mach_absolute_time();

                return true;
            }
            catch (Exception)
            {
                return false;
            }
        }

        public static long Nanoseconds()
        {
            ulong ticks = mach_absolute_time();

            return (long)(ticks / _denom * _numer + ticks % _denom * _numer / _denom);
        }
    }
'''

PAST_TIMING = 'delegate* unmanaged<Device, SwapchainKHR, uint*, PastPresentationTimingGOOGLE*, Result>'
REFRESH_CYCLE = 'delegate* unmanaged<Device, SwapchainKHR, RefreshCycleDurationGOOGLE*, Result>'


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name

    initialization = paths['src/Ryujinx.Graphics.Vulkan/VulkanInitialization.cs']
    once(initialization, '''        private static readonly string[] _requiredExtensions =
        [
            KhrSwapchain.ExtensionName
        ];
''', '''        private static readonly string[] _requiredExtensions =
        [
            KhrSwapchain.ExtensionName
        ];

        // RewindBox (adapt_present_pacing): VK_GOOGLE_display_timing (MoltenVK: [CAMetalDrawable presentAtTime:] and the
        // drawables' presentedTime), for the present pacing of Window, on iOS only.
        internal const string PresentTimingExtension = "VK_GOOGLE_display_timing";

        internal static bool UsesPresentTiming(VulkanPhysicalDevice physicalDevice) =>
            OperatingSystem.IsIOS() && physicalDevice.IsDeviceExtensionPresent(PresentTimingExtension);
''')
    once(initialization, '''                    .Where(extension => !OperatingSystem.IsIOS() || extension != ExtExternalMemoryHost.ExtensionName)).ToArray();
''', '''                    .Where(extension => !OperatingSystem.IsIOS() || extension != ExtExternalMemoryHost.ExtensionName)).ToArray();

            // RewindBox (adapt_present_pacing): enabled only where Window may use it.
            if (UsesPresentTiming(physicalDevice))
            {
                enabledExtensions = [.. enabledExtensions, PresentTimingExtension];
            }
''')

    renderer = paths['src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs']
    once(renderer, '''        internal bool IsMoltenVk { get; private set; }
''', '''        internal bool IsMoltenVk { get; private set; }

        // RewindBox (adapt_present_pacing): VK_GOOGLE_display_timing is enabled on the device (iOS only).
        internal bool SupportsPresentTiming { get; private set; }

        // RewindBox (adapt_present_pacing): the session's VSync choice (set by the Library at launch: VSync Switch, not
        // disabled). Window's own VSync mode is only changed by ChangeVSyncMode, which the Library never calls.
        public bool PresentPacingAllowed { get; set; }
''')
    once(renderer, '''                _window = new Window(this, _surface, _physicalDevice.PhysicalDevice, _device);
''', '''                SupportsPresentTiming = VulkanInitialization.UsesPresentTiming(_physicalDevice);
                _window = new Window(this, _surface, _physicalDevice.PhysicalDevice, _device);
''')

    library = paths['src/Ryujinx.Library/Library.cs']
    once(library, '''            if (renderer is VulkanRenderer vulkan) vulkan.RelaxQueryFlushing = querySync && EmbeddedGraphics.RelaxQueryFlushing;
''', '''            if (renderer is VulkanRenderer vulkan) vulkan.RelaxQueryFlushing = querySync && EmbeddedGraphics.RelaxQueryFlushing;
            // RewindBox (adapt_present_pacing): frames paced on glass only at VSync Switch (not with VSync disabled or
            // Unbounded, where the present target, if any, is the user's).
            if (renderer is VulkanRenderer pacedVulkan) pacedVulkan.PresentPacingAllowed = !options.DisableVSync && options.VSyncMode == Ryujinx.Common.Configuration.VSyncMode.Switch;
''')

    window = paths['src/Ryujinx.Graphics.Vulkan/Window.cs']
    once(window, '''        private bool _colorSpacePassthroughEnabled;
''', '''        private bool _colorSpacePassthroughEnabled;

        // RewindBox (adapt_present_pacing): null without VK_GOOGLE_display_timing, its entry points or its clock.
        private readonly PresentPacer _presentPacer;
        private readonly unsafe ''' + PAST_TIMING + ''' _getPastPresentationTiming;
        private readonly unsafe ''' + REFRESH_CYCLE + ''' _getRefreshCycleDuration;
        private SwapchainKHR _presentPacingSwapchain;
        private bool _presentPacingLogged;
        private long _presentPacingWindowStart;
''')
    once(window, '''            _device = device;
            _surface = surface;

            CreateSwapchain();
''', '''            _device = device;
            _surface = surface;

            // RewindBox (adapt_present_pacing): even pacing of a guest at a steady 30 (or 20, 15) fps, iOS only.
            if (gd.SupportsPresentTiming && PresentClock.TryInitialize())
            {
                _getPastPresentationTiming = (''' + PAST_TIMING + ''')(void*)gd.Api.GetDeviceProcAddr(device, "vkGetPastPresentationTimingGOOGLE").Handle;
                _getRefreshCycleDuration = (''' + REFRESH_CYCLE + ''')(void*)gd.Api.GetDeviceProcAddr(device, "vkGetRefreshCycleDurationGOOGLE").Handle;
                _presentPacer = _getPastPresentationTiming != null && _getRefreshCycleDuration != null ? new PresentPacer() : null;
            }

            if (OperatingSystem.IsIOS())
            {
                Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, _presentPacer != null
                    ? "Present pacing available: VK_GOOGLE_display_timing (presentAtTime, presentedTime feedback); allowed " + gd.PresentPacingAllowed
                    : "Present pacing unavailable: VK_GOOGLE_display_timing " + (gd.SupportsPresentTiming ? "enabled but no entry point or host clock" : "not exposed"));
            }

            CreateSwapchain();
''')
    once(window, '''                PResults = &result,
            };

            long queuePresentStart = RenderStageTimer.Now();
''', '''                PResults = &result,
            };

            // RewindBox (adapt_present_pacing): a guest whose recent presents keep a steady multiple of its 60 Hz period
            // is shown on an even lattice of display refreshes learned from MoltenVK's presentedTime; without a pacer
            // (not iOS, no extension) nothing is chained, and when pacing is not allowed nothing is chained either.
            PresentTimeGOOGLE presentTime = default;
            PresentTimesInfoGOOGLE presentTimes = new()
            {
                SType = StructureType.PresentTimesInfoGoogle,
                SwapchainCount = 1,
                PTimes = &presentTime,
            };

            if (_presentPacer != null)
            {
                PacePresent(&presentTime);

                if (_presentPacer.Tracking)
                {
                    presentInfo.PNext = &presentTimes;
                }
            }

            long queuePresentStart = RenderStageTimer.Now();
''')
    once(window, '''        public override void SetAntiAliasing(AntiAliasing effect)
        {''', '''        // RewindBox (adapt_present_pacing): feeds the pacer the frames MoltenVK has shown since the last present (presentID,
        // actualPresentTime), then decides this frame's presentID and desiredPresentTime (0: present as soon as ready).
        private unsafe void PacePresent(PresentTimeGOOGLE* presentTime)
        {
            if (_presentPacingSwapchain.Handle != _swapchain.Handle)
            {
                RefreshCycleDurationGOOGLE refreshCycle;

                if (_getRefreshCycleDuration(_device, _swapchain, &refreshCycle) == Result.Success && refreshCycle.RefreshDuration != 0)
                {
                    _presentPacer.SetRefresh((long)refreshCycle.RefreshDuration);
                }

                _presentPacingSwapchain = _swapchain;
            }

            const int Batch = 16;
            PastPresentationTimingGOOGLE* timings = stackalloc PastPresentationTimingGOOGLE[Batch];

            for (int round = 0; round < 4; round++)
            {
                uint count = Batch;
                Result timingResult = _getPastPresentationTiming(_device, _swapchain, &count, timings);

                if (timingResult != Result.Success && timingResult != Result.Incomplete)
                {
                    break;
                }

                for (uint i = 0; i < count; i++)
                {
                    _presentPacer.Observe(timings[i].PresentID, (long)timings[i].ActualPresentTime);
                }

                if (timingResult != Result.Incomplete)
                {
                    break;
                }
            }

            long now = PresentClock.Nanoseconds();
            presentTime->DesiredPresentTime = _presentPacer.Next(now, _gd.PresentPacingAllowed && _vSyncMode == VSyncMode.Switch);
            presentTime->PresentID = _presentPacer.FrameId;

            if (presentTime->DesiredPresentTime != 0 && !_presentPacingLogged)
            {
                _presentPacingLogged = true;
                Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu,
                    $"Present pacing engaged: guest presents every {_presentPacer.Multiple} x 16.67 ms, shown on an even lattice of display refreshes");
            }

            if (_presentPacingWindowStart == 0)
            {
                _presentPacingWindowStart = now;
            }
            else if (now - _presentPacingWindowStart >= 5_000_000_000L)
            {
                PresentPacer p = _presentPacer;
                double latency = p.LatencyCount != 0 ? p.LatencySum / 1e6 / p.LatencyCount : 0;
                Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, FormattableString.Invariant(
                    $"Present pacing over {(now - _presentPacingWindowStart) / 1e6:F0} ms: {p.WindowFrames} frames, {p.WindowPaced} paced (cadence {p.Multiple} x 16.67 ms, allowed {_gd.PresentPacingAllowed}); on glass (MoltenVK presentedTime) gaps 17/33/50/other ms {p.Gaps17}/{p.Gaps33}/{p.Gaps50}/{p.GapsOther}, adjacent 17/50 {p.Alternations}; present call to glass mean {latency:F1} ms max {p.LatencyMax / 1e6:F1} ms over {p.LatencyCount}; slots hit {p.WindowHits} missed {p.WindowMisses}, lattice moves {p.WindowShifts}, stand-downs {p.StandDowns}, margin {p.MarginNanoseconds / 1e6:F1} ms, refresh {p.RefreshNanoseconds / 1e6:F2} ms"));
                p.TakeWindow();
                _presentPacingWindowStart = now;
            }
        }

        public override void SetAntiAliasing(AntiAliasing effect)
        {''')
    once(window, '''        public override void Dispose()
        {
            Dispose(true);
        }
    }
''', '''        public override void Dispose()
        {
            Dispose(true);
        }
    }
''' + PACER)
    return list(paths.values())
