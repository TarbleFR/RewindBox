"""Make the present pacer (adapt_present_pacing) engage on the iPhone: calibrate it to the device, learn where a timed frame
is really shown, and stop the stand-down that re-arms itself.

IPA 658, 5 November 2026, maintainer's iPhone (ProMotion, refresh reported 8.33 ms), Hogwarts Legacy, one session of
about 11 minutes (private logs, not in the repository; counts and times only): the 123 "Present pacing over" windows
sum to 14,623 frames of which 24 were paced, 0 shown on their slot and 24 missed, 6 lattice moves and 5 stand-downs.
Pacing was allowed and the cadence was steady (2 x 16.67 ms) most of the time, so the pacer was off for more than 99 %
of the frames, the steady 30 fps phases it was made for included (6 to 13 adjacent 17/50 ms pairs per second while
standing down). The paced episodes were 7, 1, 7, 2 and 7 frames; the margin shown just after the 1st, 3rd and 5th
stand-down was 33.3 ms, after the 2nd and 4th 4.0 ms. Present call to glass of unpaced frames: mean 21.0 to 31.1 ms
per window, maximum 34 to 46 ms, about 22 ms in a steady window (MoltenVK's own statistics: present on GPU at least
17 ms). Paced frames aimed at about ready + 27 ms, and ready + 38 ms after the second lattice move, were still shown
after their slot, with present-to-glass maxima of 50 to 62 ms against 36 to 46 ms in the neighbouring windows.

Mechanism (read in the Core 658 preparation, Window.cs PresentPacer):
- StandDown() resets _margin to 4 ms but leaves _slots and _fits of the frames already decided and still in flight.
  Observe() then takes their misses as current information and raises _margin = min(33.3, slot - ready + 1 ms). The
  next activation (30 s, 1, 2 and 4 min later) aims its first frame at least 33.3 ms after it is ready; that frame is
  late too, `implausible` (slot - ready >= MaxMarginNanoseconds, 33.3 ms) holds at once, and the pacer stands down
  again after 1 or 2 frames, doubling the next stand-down. This is the 7/1/7/2/7 pattern and the 33.3/4.0 margins.
- The margin starts at 4 ms ("GPU tail after the present call") and the slot is the first refresh at or after
  ready + margin. On this device a frame reaches glass 17 ms or more after its GPU work (Core Animation's compositor),
  so the first slot is always one or two refreshes too early, and the 33.3 ms cap and `implausible` limit sit below the
  device's ordinary present-to-glass latency.
- desiredPresentTime is slot - refresh / 4 on the assumption that Core Animation shows a timed frame at the refresh
  at or nearest after the requested time. The frames shown about one refresh after their slot whatever the slot (27 or
  38 ms after ready, where unpaced frames take 27 to 30 ms) fit a constant offset between the requested time and the
  refresh shown, which the pacer could not learn: it only moves the lattice later and raises the margin.

Change (Window.cs only, PresentPacer and its log lines in PacePresent; every title, since it changes pacing state only:
no draw, quality or synchronisation is touched, and pacing stays limited to VSync Switch sessions):
- a stand-down voids every frame already decided: Observe only measures them (window latency), no margin, lattice,
  miss or offset change; and the margin is back at its start value when the stand-down ends;
- the present-call-to-glass latency of the last 64 unpaced frames is kept in a fixed ring (allocation free; sorted in a
  preallocated copy only after it changed; percentiles by rounded-up rank, so a few samples give their maximum). Pacing
  waits for 8 of them. The first slot is the refresh nearest to ready + p90 (ready + max(margin, p90 - 8.33 ms), rounded
  up to the grid), the margin cap is max(33.3, p90 + 16.67 ms) and a miss is `implausible` only at
  slot - ready >= max(33.3, p99 + 16.67 ms);
- before any slot is held, 8 probe frames measure the signed offset between the refresh they are shown at and their
  slot. When 6 of the 8 agree within a quarter guest period (4.17 ms), their median becomes the learned offset and the
  following frames request slot - refresh / 4 - offset (offset bounded to -16.67 .. +41.7 ms); the probes change no
  margin or lattice and count no hit or miss. Every stand-down relearns, starting from the last offset (probes then hit
  when it still holds). An unstable probe is repeated at once one guest period later (frames late for their slot spread
  it too), then after a stand-down; after 4 unstable probes in a row pacing stops for the rest of the session with one
  journal line, instead of 8-frame probes repeated every 30 s to 4 min that each delay frames;
- the 5 s window line adds the unpaced latency p50/p90/p99, the probe frames and the learned offset with its state.

Not changed: the cadence rule, the lattice and its moves, re-anchoring after a hitch, the hit window, the margin
steps after a locked miss, the stand-down lengths, the VSync gate, the extension wiring, the clock, the 120 Hz
refresh value (only used for the lead and the hit window; the effective 60 Hz grid with 4.17 ms-offset transitions
the logs suggest is not modelled). Production 50 ms gaps (frames late from the guest or the GPU) are out of scope.

Measured effect (test/melonx_present_pacer_fixes_test.py, SDK 10.0.100, 783 checks; the production
Ryujinx.Graphics.Vulkan.dll of the Core 658 preparation (control) and of it plus this adapter (candidate) are built and
loaded, each one's compiled PresentPacer decides every frame on identical inputs; every number is in
dist/melonx/present-pacer-fixes-checks.json). Device-calibrated scenario (refresh reported 8.33 ms, a 60 Hz panel, one
compositor refresh after GPU completion, a timed frame shown one refresh after its requested refresh, 4 minutes at
30 fps; unpaced present call to glass mean 23.9 ms, maximum 37.3 ms): the control reproduces the logs' failure (13 of
7200 frames paced, 0 hits, episodes 7/2/2/2, margin 33.3 ms at every reactivation, 3 instant stand-downs); the
candidate learns a 16.67 ms offset with one probe, paces 7171 frames, 7136 on their slot, no stand-down, and the
adjacent 17/50 pairs fall from 539 to 32 (unpaced 540), at 14.8 ms mean added latency (about one refresh). Nearest
rounding 538 -> 8, a longer GPU tail 1282 -> 7, two refreshes late 569 -> 3 (offset 33.3 ms), targets honoured
24 -> 20 (offset 0). An offset that never settles (0 to 2 refreshes at random): pacing off for the session after 4
probes (36 paced frames), 533 -> 545 pairs against 531 unpaced. The adapt_present_pacing scenarios: no more pairs and
no fewer gaps at the guest period than the control in any of them; a refresh-late Core Animation is learned
(246 -> 1) instead of stood down; drift60Slow keeps its pairs (1) at 11.9 ms mean delay instead of 6.4 (one early
lattice move fewer in two minutes: the calibrated slot is more conservative). Sweep of 4320 runs: 326,708 -> 208,395
pairs; no row more than 2 pairs worse over 45 runs (one: uniform 2.5 ms jitter, 1.5 ms tail, 9 -> 11), no run more
than 6 worse. Device sweep (0/1/2 refreshes late x 2 GPU tails x 3 jitters x 36 runs of 2 min): 183,020 -> 49,905
pairs, fewer in every row; 350 instant stand-downs in the control, 0 in the candidate. The decision and the feedback
allocate 0 bytes over 100,000 frames (probes, stand-downs, latency sorts and the session stop included).
Not measured on an iPhone: the device model (a compositor refresh after GPU completion, a timed frame shown one refresh
after its requested refresh) is inferred from the logs above; the window line's offset and unpaced p50/p90/p99 confirm
or refute it on the device.
Fail closed on drift: Window.cs must be the Core 658 preparation's (adapt_present_pacing, then
adapt_present_drawable_residency).
"""
import hashlib
from adapt_session import once

BASELINE = {
    'src/Ryujinx.Graphics.Vulkan/Window.cs': 'ba3a2c8500460695747eb80a94c14eaf0cb0e1bbcf62c1bdf98f4a82aee3403a',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    window = paths['src/Ryujinx.Graphics.Vulkan/Window.cs']

    # Window: the once-per-session line when the offset never settles.
    once(window, '''        private bool _presentPacingLogged;
''', '''        private bool _presentPacingLogged;
        // RewindBox (adapt_present_pacer_fixes): the journal line when pacing stops for the session.
        private bool _presentPacingOffLogged;
''')

    once(window, '''            if (_presentPacingWindowStart == 0)
            {
                _presentPacingWindowStart = now;
            }
''', '''            // RewindBox (adapt_present_pacer_fixes): one line when the requested-to-shown offset never settled.
            if (_presentPacer.SessionOff && !_presentPacingOffLogged)
            {
                _presentPacingOffLogged = true;
                Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, FormattableString.Invariant(
                    $"Present pacing off for the session: the refresh a timed frame is shown at did not settle against its requested time over {_presentPacer.ProbeRuns} probes of 8 frames; frames are presented as soon as ready (adapt_present_pacer_fixes)"));
            }

            if (_presentPacingWindowStart == 0)
            {
                _presentPacingWindowStart = now;
            }
''')

    once(window, '''margin {p.MarginNanoseconds / 1e6:F1} ms, refresh {p.RefreshNanoseconds / 1e6:F2} ms"));''',
         '''margin {p.MarginNanoseconds / 1e6:F1} ms, refresh {p.RefreshNanoseconds / 1e6:F2} ms; unpaced present call to glass p50/p90/p99 {p.UnpacedLatencyP50 / 1e6:F1}/{p.UnpacedLatencyP90 / 1e6:F1}/{p.UnpacedLatencyP99 / 1e6:F1} ms, probe frames {p.WindowProbes}, shown-after-requested offset {p.OffsetNanoseconds / 1e6:F1} ms ({(p.SessionOff ? "pacing off for the session" : p.OffsetKnown ? "learned" : "learning")})"));''')

    # PresentPacer: constants, state and properties.
    once(window, '''        private const int History = 32;
''', '''        private const int History = 32;
        // RewindBox (adapt_present_pacer_fixes): the present-call-to-glass latency of the last 64 unpaced frames (Core
        // Animation's compositor included) places the first slot a frame can make; pacing waits for 8 of them.
        private const int LatencyRing = 64;
        private const int LatencyMinSamples = 8;
        // The offset between a timed frame's slot and the refresh it is shown at is learned from 8 probe frames, 6 of them
        // within a quarter guest period, before any slot is held. An unstable probe is repeated at once one guest period
        // later (late frames spread it too), then after a stand-down; four in a row: no pacing for the session.
        private const int ProbeFrames = 8;
        private const int ProbeAgree = 6;
        private const int MaxUnstableProbes = 4;
        // What a decided frame is when it comes back: unpaced (its latency calibrates), a probe, paced on a learned offset,
        // or void (decided before a stand-down: only measured).
        private const byte KindUnpaced = 0;
        private const byte KindProbe = 1;
        private const byte KindPaced = 2;
        private const byte KindVoid = 3;
''')

    once(window, '''        private int _standDownLength = StandDownFrames;
''', '''        private int _standDownLength = StandDownFrames;

        // RewindBox (adapt_present_pacer_fixes): calibration and the learned offset (no allocation after construction).
        private readonly byte[] _kinds = new byte[History];
        private readonly long[] _latencies = new long[LatencyRing];
        private readonly long[] _sortedLatencies = new long[LatencyRing];
        private int _latencyNext;
        private int _latencyFilled;
        private bool _latencyDirty;
        private long _latencyP50;
        private long _latencyP90;
        private long _latencyP99;
        private readonly long[] _probes = new long[ProbeFrames];
        private int _probeCount;
        private long _offset;
        private bool _offsetKnown;
        private int _unstableProbes;
''')

    once(window, '''        public long LatencyMax { get; private set; }
''', '''        public long LatencyMax { get; private set; }

        // RewindBox (adapt_present_pacer_fixes): calibration, probes and the learned offset, for the window line.
        public long WindowProbes { get; private set; }
        public long ProbeRuns { get; private set; }
        public bool SessionOff { get; private set; }
        public bool OffsetKnown => _offsetKnown;
        public long OffsetNanoseconds => _offset;
        public long MarginCapNanoseconds => Math.Max(MaxMarginNanoseconds, CalibratedLatency(90) + GuestVsyncNanoseconds);
        public long UnpacedLatencyP50 => CalibratedLatency(50);
        public long UnpacedLatencyP90 => CalibratedLatency(90);
        public long UnpacedLatencyP99 => CalibratedLatency(99);
''')

    once(window, '''            LatencyCount = LatencySum = LatencyMax = 0;
        }
''', '''            LatencyCount = LatencySum = LatencyMax = 0;
            WindowProbes = 0;
        }
''')

    # Observe: what the frame was decided as.
    once(window, '''            long expected = _slots[slot];

            if (expected == 0)
            {
                return;
            }
''', '''            long expected = _slots[slot];

            // RewindBox (adapt_present_pacer_fixes): an unpaced frame calibrates the latency; a probe measures the offset
            // (a late one spreads it); a frame decided before a stand-down is only measured.
            byte kind = _kinds[slot];

            if (kind == KindUnpaced)
            {
                _latencies[_latencyNext] = latency;
                _latencyNext = (_latencyNext + 1) % LatencyRing;
                _latencyFilled = Math.Min(_latencyFilled + 1, LatencyRing);
                _latencyDirty = true;

                return;
            }

            if (kind != KindPaced)
            {
                if (kind == KindProbe)
                {
                    Probe(actual - expected);
                }

                return;
            }
''')

    once(window, '''                    _margin = Math.Min(MaxMarginNanoseconds, Math.Max(_margin + MarginStepNanoseconds,''',
         '''                    _margin = Math.Min(MarginCapNanoseconds, Math.Max(_margin + MarginStepNanoseconds,''')

    once(window, '''                bool implausible = _fits[slot] && expected - _readyTimes[slot] >= MaxMarginNanoseconds;
''', '''                // RewindBox (adapt_present_pacer_fixes): implausible beyond the device's own p99 latency plus a guest period.
                bool implausible = _fits[slot] && expected - _readyTimes[slot] >=
                    Math.Max(MaxMarginNanoseconds, CalibratedLatency(99) + GuestVsyncNanoseconds);
''')

    # Next: registration, stand-down end, session off, calibration gate, need, the request.
    once(window, '''            _fits[slot] = false;
            _lateWindow = (_lateWindow << 1) & 0xFF;
''', '''            _fits[slot] = false;
            _kinds[slot] = KindUnpaced;
            _lateWindow = (_lateWindow << 1) & 0xFF;
''')

    once(window, '''            if (_standDown > 0)
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
''', '''            // RewindBox (adapt_present_pacer_fixes): no pacing for the session once the offset never settled.
            if (SessionOff)
            {
                _latticeTime = 0;

                return 0;
            }

            if (_standDown > 0)
            {
                // RewindBox (adapt_present_pacer_fixes): the margin is back at its start value when the stand-down ends.
                if (--_standDown == 0)
                {
                    _margin = MinMarginNanoseconds;
                }

                _latticeTime = 0;

                return 0;
            }

            // RewindBox (adapt_present_pacer_fixes): not before 8 unpaced latencies are known.
            if (Multiple == 0 || _glass == 0 || now - _glass > 1_000_000_000L || _latencyFilled < LatencyMinSamples)
            {
                _latticeTime = 0;

                return 0;
            }

            // RewindBox (adapt_present_pacer_fixes): the first slot is the refresh nearest to ready + p90 of the unpaced
            // present-call-to-glass latency, or ready + margin when later.
            long need = now + Math.Max(_margin, CalibratedLatency(90) - GuestVsyncNanoseconds / 2);
''')

    once(window, '''            _slots[slot] = target;
            _fits[slot] = need <= target;
            PacedFrames++;
            WindowPaced++;

            return (ulong)(target - _refresh / 4);
        }
''', '''            _slots[slot] = target;
            _fits[slot] = need <= target;
            PacedFrames++;
            WindowPaced++;

            // RewindBox (adapt_present_pacer_fixes): a probe until the offset is learned; the request is moved earlier by the
            // learned offset between a slot and the refresh a frame aimed at it is shown at.
            _kinds[slot] = _offsetKnown ? KindPaced : KindProbe;
            WindowProbes += _offsetKnown ? 0 : 1;

            return (ulong)Math.Max(1, target - _refresh / 4 - _offset);
        }

        // RewindBox (adapt_present_pacer_fixes): a probe frame shown `residual` after its slot (aimed with the last offset).
        private void Probe(long residual)
        {
            if (_offsetKnown || SessionOff)
            {
                return;
            }

            _probes[_probeCount++] = residual;

            if (_probeCount < ProbeFrames)
            {
                return;
            }

            _probeCount = 0;
            ProbeRuns++;
            Array.Sort(_probes);

            int best = 0;
            long spread = long.MaxValue;

            for (int i = 0; i + ProbeAgree <= ProbeFrames; i++)
            {
                long width = _probes[i + ProbeAgree - 1] - _probes[i];

                if (width < spread)
                {
                    spread = width;
                    best = i;
                }
            }

            long offset = _offset + (_probes[best + ProbeAgree / 2 - 1] + _probes[best + ProbeAgree / 2]) / 2;

            if (spread < GuestVsyncNanoseconds / 4 && offset >= -GuestVsyncNanoseconds && offset <= 2 * GuestVsyncNanoseconds + GuestVsyncNanoseconds / 2)
            {
                _offset = offset;
                _offsetKnown = true;
                _unstableProbes = 0;

                return;
            }

            if (++_unstableProbes >= MaxUnstableProbes)
            {
                SessionOff = true;
                _latticeTime = 0;
                VoidDecided();

                return;
            }

            if (_unstableProbes % 2 == 1)
            {
                // Frames late for their slot also spread the probe: probe again at once, one guest period later.
                _margin = Math.Min(MarginCapNanoseconds, Math.Max(_margin, CalibratedLatency(90) - GuestVsyncNanoseconds / 2) + GuestVsyncNanoseconds);
                _latticeTime = 0;
                VoidDecided();

                return;
            }

            StandDown();
        }

        // RewindBox (adapt_present_pacer_fixes): the frames decided so far are only measured when they come back.
        private void VoidDecided()
        {
            for (int i = 0; i < History; i++)
            {
                if (_kinds[i] != KindUnpaced)
                {
                    _kinds[i] = KindVoid;
                }
            }
        }

        // RewindBox (adapt_present_pacer_fixes): a percentile (rounded-up rank) of the unpaced latency ring, 0 until 8 are
        // known; sorted in a preallocated copy, only after the ring changed.
        private long CalibratedLatency(int percentile)
        {
            if (_latencyDirty)
            {
                _latencyDirty = false;

                if (_latencyFilled >= LatencyMinSamples)
                {
                    Array.Copy(_latencies, _sortedLatencies, _latencyFilled);
                    Array.Sort(_sortedLatencies, 0, _latencyFilled);
                    _latencyP50 = _sortedLatencies[((_latencyFilled - 1) * 50 + 99) / 100];
                    _latencyP90 = _sortedLatencies[((_latencyFilled - 1) * 90 + 99) / 100];
                    _latencyP99 = _sortedLatencies[((_latencyFilled - 1) * 99 + 99) / 100];
                }
            }

            if (_latencyFilled < LatencyMinSamples)
            {
                return 0;
            }

            return percentile >= 99 ? _latencyP99 : percentile >= 90 ? _latencyP90 : _latencyP50;
        }
''')

    once(window, '''            _margin = MinMarginNanoseconds;
            _missRun = 0;
            Array.Clear(_shiftFrames);
        }
''', '''            _margin = MinMarginNanoseconds;
            _missRun = 0;
            Array.Clear(_shiftFrames);
            // RewindBox (adapt_present_pacer_fixes): frames already decided and in flight are only measured (their misses
            // raised the margin back to its cap after the reset above), and the next activation relearns the offset.
            VoidDecided();
            _offsetKnown = false;
            _probeCount = 0;
        }
''')
    return [window]
