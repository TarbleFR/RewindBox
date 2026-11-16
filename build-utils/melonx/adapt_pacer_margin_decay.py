"""The present pacer's margin wears off after a transient lateness instead of holding the latency high for the session.

IPA 749 / Core 030cc14f, Hogwarts Legacy (private journals, pid 12613, the 5 s "Present pacing over" windows; counts and
times only), against IPA 740 (Core da2525a1), where the margin stayed at 4.0 ms for the whole session:
- 4.0 ms until 04:59:57, then 30.9 ms after a single late paced frame that follows a 350 ms freeze;
- back to 4.0 ms at 05:00:18, only because the pacer stood down (4 misses, 1 stand-down in that window);
- 45.0 ms at 05:00:59 with no late frame: an unstable probe (the probe path raises the margin one guest period above the
  lead, adapt_present_pacer_fixes);
- 61.7 ms at 05:01:10 after 4 late paced frames right after the host pause of 05:01:00-04 (Control Center), then 59.7 to
  61.7 ms until the end: 30 of the 42 windows have a margin of 30.9 ms or more;
- present call to glass, weighted: 31.7 ms (740) -> 43.7 ms (749); 52 to 73 ms in 12 paced windows against an unpaced
  p50 of 28 to 33 ms; drawable waits over 10 ms in 18 of 129 lines (15 of them after 05:01:08), 1 of 85 in 740.

Mechanism (Window.cs PresentPacer as prepared for Core 030cc14f):
- a paced frame ready in time by the estimate but shown after its slot (half a refresh or more) raises the margin to
  min(cap, max(margin + 1 ms, slot - ready + 1 ms)), cap = max(33.3 ms, p90 + 16.7 ms): one late frame is enough to move
  the margin from 4 ms to the lead that frame had;
- the margin decays by 0.5 ms only every 300 fitting frames on their slot: about 34,500 paced frames (19 minutes at
  30 fps) from 61.7 ms back to 4 ms;
- the margin is never reset when pacing resumes: Next(enabled = false) and a second with nothing on glass reset the
  lattice, not _margin, so a margin raised before a host pause, or just after it, holds for the rest of the session.
The lead of a paced frame is max(margin, p90 - 8.3 ms), so a high margin delays every paced frame by margin - lead floor.

Change (Window.cs, PresentPacer only; plan 748 rank 10):
1. decay: MarginDecayHits 300 -> 30. After 30 paced frames in a row shown by their slot (any paced frame shown after its
   slot restarts the count), the margin gives back an eighth of its excess over the start margin, at least 0.5 ms:
   margin = max(4 ms, margin - max(0.5 ms, (margin - 4 ms) / 8)). From 61.7 ms: 28 steps (840 paced frames, about 28 s
   at 30 fps) back to 4 ms; from 30.9 ms: 23 steps. _hitsSinceMiss still counts the fitting frames on their slot, so the
   stand-down length reset after 600 of them is unchanged;
2. raise: a frame ready in time but late raises the margin only when shown about a whole refresh or more after its
   slot (actual - slot > 7/8 refresh, so noise around one refresh never flips a real miss); a frame half to seven
   eighths of a refresh late still counts as a miss (lattice, miss run,
   stand-down) but leaves the margin. The raise itself and its cap are unchanged;
3. probe: the probe path's raise keeps the same cap as the miss path (MarginCapNanoseconds on both, already so in the
   prepared source: no replacement); the margin it raises now decays as in 1 once the offset is learned;
4. reset: the first paced frame after enabled = false, or after a second with nothing on glass (how a host pause reaches
   the pacer: the render loop stops presenting; Next already stops pacing then), starts from the start margin (4 ms).
   A stall of a second or more resets it too: the pacer cannot tell it from a pause.
No cap of 33.3 ms is set: it would contradict the lead floor p90 - 8.3 ms. Not changed: the cadence rule, the lattice,
its moves and re-anchors, the hit window, the calibration, the probes and the learned offset, the stand-down rules and
lengths, the VSync gate, the window line (its "margin" field reads the change), the journal. No allocation is added.

Scope: every title with present pacing (iOS, VK_GOOGLE_display_timing, VSync Switch): pacing state only, no draw,
quality or synchronisation is touched, and the guest sees nothing. Expected on the device, in the existing window line:
after a raise, "margin" back near 4.0 ms within about 30 s of paced play (instead of staying near 60 ms), 4.0 ms in the
first paced window after a host pause; "present call to glass mean" of paced windows closer to the unpaced p90; fewer
drawable waits over 10 ms. "slots missed" may rise a little (a shorter margin), bounded by the existing stand-down.
Bound (from the logs, not measured): at most 8 to 29 ms less latency per paced frame in the 11 windows shown at 52 ms or
more, 18.4 ms weighted over the windows with a margin of 30 ms or more; no FPS gain. Not measured on an iPhone.
Simulated in test/melonx_present_pacer_fixes_test.py (the final Window.cs and the same without this adapter, each compiled
PresentPacer on identical simulated inputs; no device, not a measurement): after a paced frame 100 ms late the margin is
back at 4 ms after 601 paced frames (25.6 ms, 20 steps) where the control keeps it; 4.0 ms at the first paced frame after a
4 s pause or 60 frames not allowed; a frame 6.25 ms late raises nothing; the probe's raise is unchanged and under the cap.
The cost the plan names shows there too: once the margin has worn off, the calibrated lead alone misses more slots
(device658 32 -> 63 adjacent 17/50 pairs, 540 unpaced; device658Nearest 8 -> 94, 538; device sweep 49,905 -> 52,908
pairs), with no added stand-down and no higher mean added latency.
Runs after every current adapter (Window.cs as adapt_submit_causes leaves it, after adapt_present_pacer_fixes and
adapt_async_regenerated_targets). Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

WINDOW = 'src/Ryujinx.Graphics.Vulkan/Window.cs'
BASELINE = {WINDOW: 'bafe13acdb6496143e0c37d59e7dfa7758fd3d6c59914ba9af7485a7eeca5f26'}

CONSTANT_OLD = '''        private const long MarginDecayNanoseconds = 500_000;
        private const int MarginDecayHits = 300;
'''
CONSTANT_NEW = '''        private const long MarginDecayNanoseconds = 500_000;
        // RewindBox (adapt_pacer_margin_decay): a decay step after 30 paced frames in a row shown by their slot (was 300
        // fitting frames for a 0.5 ms step).
        private const int MarginDecayHits = 30;
'''

FIELDS_OLD = '''        private int _hitsSinceMiss;
        private int _missRun;
'''
FIELDS_NEW = '''        private int _hitsSinceMiss;
        // RewindBox (adapt_pacer_margin_decay): paced frames shown by their slot since the last late one or decay step, and
        // the next paced frame starts from the start margin (after enabled = false, or a second with nothing on glass).
        private int _decayHits;
        private bool _resumeAtStartMargin;
        private int _missRun;
'''

DECAY_OLD = '''                if (_fits[slot] && ++_hitsSinceMiss % MarginDecayHits == 0)
                {
                    _margin = Math.Max(MinMarginNanoseconds, _margin - MarginDecayNanoseconds);
                }
'''
DECAY_NEW = '''                if (_fits[slot])
                {
                    _hitsSinceMiss++;
                }

                // RewindBox (adapt_pacer_margin_decay): after 30 paced frames in a row shown by their slot, the margin gives
                // back an eighth of its excess over the start margin (at least 0.5 ms): a transient lateness wears off.
                if (++_decayHits >= MarginDecayHits)
                {
                    _decayHits = 0;
                    _margin = Math.Max(MinMarginNanoseconds, _margin - Math.Max(MarginDecayNanoseconds, (_margin - MinMarginNanoseconds) / 8));
                }
'''

RAISE_OLD = '''                if (_fits[slot])
                {
                    // Ready in time by the estimate, yet shown later: the GPU tail is longer than the margin.
                    _margin = Math.Min(MarginCapNanoseconds, Math.Max(_margin + MarginStepNanoseconds,
                        expected - _readyTimes[slot] + MarginStepNanoseconds));
                    _hitsSinceMiss = 0;
                }
'''
RAISE_NEW = '''                // RewindBox (adapt_pacer_margin_decay): a paced frame shown after its slot restarts the decay count.
                _decayHits = 0;

                if (_fits[slot])
                {
                    // Ready in time by the estimate, yet shown later: the GPU tail is longer than the margin.
                    // RewindBox (adapt_pacer_margin_decay): raised only when shown about a whole refresh or more after its
                    // slot (more than seven eighths of one, so timestamp noise around one refresh cannot flip a real miss).
                    if (actual - expected > _refresh - _refresh / 8)
                    {
                        _margin = Math.Min(MarginCapNanoseconds, Math.Max(_margin + MarginStepNanoseconds,
                            expected - _readyTimes[slot] + MarginStepNanoseconds));
                    }

                    _hitsSinceMiss = 0;
                }
'''

DISABLED_OLD = '''            if (!enabled)
            {
                _count = 0;
                _next = 0;
'''
DISABLED_NEW = '''            if (!enabled)
            {
                // RewindBox (adapt_pacer_margin_decay): pacing resumes at the start margin.
                _resumeAtStartMargin = true;
                _count = 0;
                _next = 0;
'''

RESUME_OLD = '''            if (Multiple == 0 || _glass == 0 || now - _glass > 1_000_000_000L || _latencyFilled < LatencyMinSamples)
            {
                _latticeTime = 0;

                return 0;
            }
'''
RESUME_NEW = '''            if (Multiple == 0 || _glass == 0 || now - _glass > 1_000_000_000L || _latencyFilled < LatencyMinSamples)
            {
                // RewindBox (adapt_pacer_margin_decay): nothing on glass for a second (a host pause, or a stall as long):
                // pacing resumes at the start margin.
                if (_glass != 0 && now - _glass > 1_000_000_000L)
                {
                    _resumeAtStartMargin = true;
                }

                _latticeTime = 0;

                return 0;
            }

            // RewindBox (adapt_pacer_margin_decay): the first frame paced again after enabled = false or a second with
            // nothing on glass starts from the start margin, with a new decay count.
            if (_resumeAtStartMargin)
            {
                _resumeAtStartMargin = false;
                _margin = MinMarginNanoseconds;
                _decayHits = 0;
            }
'''

PAIRS = ((CONSTANT_OLD, CONSTANT_NEW), (FIELDS_OLD, FIELDS_NEW), (DECAY_OLD, DECAY_NEW), (RAISE_OLD, RAISE_NEW),
         (DISABLED_OLD, DISABLED_NEW), (RESUME_OLD, RESUME_NEW))


def apply(source):
    path = source / WINDOW
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, WINDOW
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
