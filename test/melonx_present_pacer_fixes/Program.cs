// The present pacer before/after adapt_present_pacer_fixes, on recorded-like frame-ready times (extends the
// adapt_present_pacing fixture, test/melonx_present_pacing/Program.cs, to the device-like latencies of the IPA 658 logs).
// The production Ryujinx.Graphics.Vulkan.dll of the variant is loaded (args[1]); its compiled PresentPacer (reflection,
// closed delegates: the production code itself) decides each frame's desiredPresentTime and is fed back, as Window feeds
// it from vkGetPastPresentationTimingGOOGLE, the on-glass time of each frame shown before the frame's present. Control:
// the Core 658 pacer. Candidate: the same plus the adapter. Both also report the frames shown as soon as ready (unpaced).
// On glass, a frame with no target is shown CompositorRefreshes refreshes after the first display refresh at or after its
// GPU completion (ready + GPU tail): Core Animation's compositor. With a target, Core Animation's choice of refresh is
// the first refresh at or after the target ("ceil"), the nearest refresh ("nearest") or one refresh after the first at
// or after it ("lateByOne"), then TimedLateRefreshes more refreshes (the device hypothesis: a timed frame is shown about
// one refresh after its requested refresh), plus 0 to 2 refreshes at random per frame when TimedLateRandom (an offset
// that never settles); never before the unpaced time, one frame per refresh (FIFO).
// The drawable model: CAMetalLayer's 3 drawables, each held from its acquisition (just before the present call) until
// the next frame replaces it on glass; an acquisition with 3 held waits (render-thread stall).
using System;
using System.Collections.Generic;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text;

static class Program
{
    const long Ms = 1_000_000;
    const long GuestVsync = 1_000_000_000L / 60;
    static readonly CultureInfo Inv = CultureInfo.InvariantCulture;

    sealed class Pacer
    {
        public Func<long, bool, ulong> Next;
        public Action<uint, long> Observe;
        public Action<long> SetRefresh;
        public Func<uint> FrameId;
        public Func<long> PacedFrames, Misses, LatticeShifts, Reanchors, StandDowns, Margin, Hits, LatencyCount, LatencySum;
        // The adapter's (absent from the control pacer: null).
        public Func<bool> SessionOff, OffsetKnown;
        public Func<long> Offset, ProbeRuns, MarginCap;

        static T Get<T>(Type type, object instance, string name) where T : Delegate =>
            (T)Delegate.CreateDelegate(typeof(T), instance, type.GetMethod(name, BindingFlags.Public | BindingFlags.Instance)
                ?? throw new MissingMethodException(type.FullName, name));

        static T Optional<T>(Type type, object instance, string name) where T : Delegate =>
            type.GetMethod(name, BindingFlags.Public | BindingFlags.Instance) is MethodInfo method
                ? (T)Delegate.CreateDelegate(typeof(T), instance, method) : null;

        public static Pacer Create(Type type)
        {
            object instance = Activator.CreateInstance(type, nonPublic: true);
            return new Pacer
            {
                Next = Get<Func<long, bool, ulong>>(type, instance, "Next"),
                Observe = Get<Action<uint, long>>(type, instance, "Observe"),
                SetRefresh = Get<Action<long>>(type, instance, "SetRefresh"),
                FrameId = Get<Func<uint>>(type, instance, "get_FrameId"),
                PacedFrames = Get<Func<long>>(type, instance, "get_PacedFrames"),
                Misses = Get<Func<long>>(type, instance, "get_Misses"),
                LatticeShifts = Get<Func<long>>(type, instance, "get_LatticeShifts"),
                Reanchors = Get<Func<long>>(type, instance, "get_Reanchors"),
                StandDowns = Get<Func<long>>(type, instance, "get_StandDowns"),
                Margin = Get<Func<long>>(type, instance, "get_MarginNanoseconds"),
                Hits = Get<Func<long>>(type, instance, "get_WindowHits"),
                LatencyCount = Get<Func<long>>(type, instance, "get_LatencyCount"),
                LatencySum = Get<Func<long>>(type, instance, "get_LatencySum"),
                SessionOff = Optional<Func<bool>>(type, instance, "get_SessionOff"),
                OffsetKnown = Optional<Func<bool>>(type, instance, "get_OffsetKnown"),
                Offset = Optional<Func<long>>(type, instance, "get_OffsetNanoseconds"),
                ProbeRuns = Optional<Func<long>>(type, instance, "get_ProbeRuns"),
                MarginCap = Optional<Func<long>>(type, instance, "get_MarginCapNanoseconds"),
            };
        }
    }

    sealed class Scenario
    {
        public string Name;
        public int Frames = 900;
        public double DisplayHz = 60.0;      // the refresh grid frames are latched on
        public double ReportedHz = 60.0;     // vkGetRefreshCycleDurationGOOGLE (UIScreen maximumFramesPerSecond)
        public double GuestFrameMs = 2 * 1000.0 / 60;
        public string Jitter = "uniform";    // uniform (+-JitterMs), gauss (sigma JitterMs), late (exponential, mean JitterMs, late only)
        public double JitterMs = 2.5;
        public double TailMs = 1.5;          // GPU completion after the present call, uniform +- TailJitterMs
        public double TailJitterMs = 0.3;
        public double PhaseMs;               // refresh boundary at nominal ready + TailMs + PhaseMs
        public string Rounding = "ceil";
        public int CompositorRefreshes;      // refreshes between the latch after GPU completion and glass (any frame)
        public int TimedLateRefreshes;       // refreshes a timed frame is shown after its requested refresh
        public bool TimedLateRandom;         // plus 0..2 refreshes at random per timed frame
        public bool Allowed = true;          // Window: PresentPacingAllowed && VSync Switch
        public int Seed = 650;
        public double LongFrameShare;        // share of frames taking one more guest period (unstable cadence)
        public int HitchFrame = -1;          // this frame and the following ones come 70 ms later
        public double HandlerMs = 2.0;       // presented handler -> history -> drained at the next present call
    }

    sealed class Result
    {
        public int Frames, Pairs, UnpacedPairs, Paced, Stalls, StallsUnpaced, InstantStandDowns, UnpacedNominal;
        public double Seconds, Share, UnpacedShare, MeanAdded, MaxAdded, MaxStallMs, MaxStallUnpacedMs, UnpacedLatencyMean, UnpacedLatencyMax;
        public long Misses, Hits, Shifts, Reanchors, StandDowns, Margin, Offset = long.MinValue, ProbeRuns = -1;
        public int SessionOff = -1, OffsetKnown = -1;
        public string InputHash;
        public SortedDictionary<int, int> Gaps = new();
        public List<int> Episodes = new();
        public List<double> MarginsAfterStandDown = new();
        public bool OrderKept, NotEarlier, HoldBounded;
        public int PacedInHitchWindow = -1, PacedAfterHitch = -1;
    }

    static double Gauss(Random random)
    {
        double u1 = 1 - random.NextDouble(), u2 = random.NextDouble();
        return Math.Sqrt(-2 * Math.Log(u1)) * Math.Cos(2 * Math.PI * u2);
    }

    static (int pairs, SortedDictionary<int, int> gaps, double share, bool order) Gaps(long[] shown, Scenario s, double refresh, long period)
    {
        var gaps = new SortedDictionary<int, int>();
        int pairs = 0, previous = 0;
        bool order = true;
        for (int k = 1; k < shown.Length; k++)
        {
            long gap = shown[k] - shown[k - 1];
            order &= gap > 0;
            int name = (int)Math.Round(Math.Round(gap / 1e6 / (1000.0 / 120)) * (1000.0 / 120));
            gaps[name] = gaps.TryGetValue(name, out int count) ? count + 1 : 1;
            // An alternation: a gap shorter than the guest period next to one longer (17/50 at 60 Hz, 25/42 at 120 Hz).
            int side = gap < period - refresh / 2 ? -1 : gap > period + refresh / 2 ? 1 : 0;
            if (k > 1 && side != 0 && side == -previous)
            {
                pairs++;
            }
            previous = side;
        }
        int nominalName = (int)Math.Round(s.GuestFrameMs);
        double share = gaps.TryGetValue(nominalName, out int nominalCount) ? nominalCount / (double)(shown.Length - 1) : 0;
        return (pairs, gaps, share, order);
    }

    static Result Run(Scenario s, Type pacerType)
    {
        var random = new Random(s.Seed);
        var lateRandom = new Random(s.Seed ^ 0x5eed);
        long start = 10_000 * Ms;
        long guestFrame = (long)Math.Round(s.GuestFrameMs * Ms);
        long[] ready = new long[s.Frames];
        long[] done = new long[s.Frames];
        long nominal = start;
        for (int k = 0; k < s.Frames; k++)
        {
            if (k > 0)
            {
                nominal += guestFrame;
                if (s.LongFrameShare > 0 && random.NextDouble() < s.LongFrameShare)
                {
                    nominal += GuestVsync;
                }
                if (k == s.HitchFrame)
                {
                    nominal += 70 * Ms;
                }
            }
            double jitter = s.Jitter switch
            {
                "uniform" => (random.NextDouble() * 2 - 1) * s.JitterMs,
                "gauss" => Gauss(random) * s.JitterMs,
                "late" => -Math.Log(1 - random.NextDouble()) * s.JitterMs,
                _ => throw new ArgumentException(s.Jitter),
            };
            ready[k] = nominal + (long)Math.Round(jitter * Ms);
            done[k] = ready[k] + (long)Math.Round(Math.Max(0.1, s.TailMs + (random.NextDouble() * 2 - 1) * s.TailJitterMs) * Ms);
        }

        double refresh = 1e9 / s.DisplayHz;
        double gridBase = start + (s.TailMs + s.PhaseMs) * Ms;
        long Latch(long t) => (long)Math.Ceiling(gridBase + Math.Ceiling((t - gridBase) / refresh - 1e-9) * refresh);
        long Nearest(long t) => (long)Math.Ceiling(gridBase + Math.Round((t - gridBase) / refresh) * refresh);
        long Later(long t, int refreshes) => refreshes == 0 ? t : Latch(t + (long)Math.Round((refreshes - 0.5) * refresh));

        Pacer pacer = pacerType != null ? Pacer.Create(pacerType) : null;
        pacer?.SetRefresh((long)(1e9 / s.ReportedHz));
        long[] desired = new long[s.Frames];
        long[] shown = new long[s.Frames];
        long[] unpaced = new long[s.Frames];
        uint[] ids = new uint[s.Frames];
        int observed = 0;
        var r = new Result { Frames = s.Frames, OrderKept = true, NotEarlier = true, HoldBounded = true };
        long standDowns = 0;
        int pacedInEpisode = 0;
        bool awaitingActivation = false;
        for (int k = 0; k < s.Frames; k++)
        {
            if (pacer != null)
            {
                // Window drains vkGetPastPresentationTimingGOOGLE before deciding: the frames already on glass.
                while (observed < k && shown[observed] + (long)(s.HandlerMs * Ms) <= ready[k])
                {
                    pacer.Observe(ids[observed], shown[observed]);
                    observed++;
                }
                desired[k] = (long)pacer.Next(ready[k], s.Allowed);
                ids[k] = s.Allowed ? pacer.FrameId() : 0;

                // Pacing episodes: paced frames between stand-downs; the margin the first paced frame after a stand-down uses.
                long nowStandDowns = pacer.StandDowns();
                if (nowStandDowns != standDowns)
                {
                    for (long i = standDowns; i < nowStandDowns; i++)
                    {
                        r.Episodes.Add(pacedInEpisode);
                        if (i > 0 && pacedInEpisode <= 2)
                        {
                            r.InstantStandDowns++;
                        }
                        pacedInEpisode = 0;
                    }
                    standDowns = nowStandDowns;
                    awaitingActivation = true;
                }
                if (desired[k] != 0)
                {
                    pacedInEpisode++;
                    if (awaitingActivation)
                    {
                        r.MarginsAfterStandDown.Add(pacer.Margin() / 1e6);
                        awaitingActivation = false;
                    }
                }
            }

            long earliest = Later(Latch(done[k]), s.CompositorRefreshes);
            if (desired[k] == 0)
            {
                shown[k] = earliest;
            }
            else
            {
                long aimed = s.Rounding switch
                {
                    "ceil" => Latch(desired[k]),
                    "nearest" => Nearest(desired[k]),
                    "lateByOne" => Latch(Latch(desired[k]) + 1),
                    _ => throw new ArgumentException(s.Rounding),
                };
                aimed = Later(aimed, s.TimedLateRefreshes + (s.TimedLateRandom ? lateRandom.Next(3) : 0));
                shown[k] = Math.Max(aimed, earliest);
            }
            unpaced[k] = earliest;
            if (k > 0)
            {
                shown[k] = Math.Max(shown[k], Latch(shown[k - 1] + 1));
                unpaced[k] = Math.Max(unpaced[k], Latch(unpaced[k - 1] + 1));
            }
        }
        if (pacer != null)
        {
            r.Episodes.Add(pacedInEpisode);
        }

        long period = guestFrame;
        (r.Pairs, r.Gaps, r.Share, r.OrderKept) = Gaps(shown, s, refresh, period);
        SortedDictionary<int, int> unpacedGaps;
        bool unpacedOrder;
        (r.UnpacedPairs, unpacedGaps, r.UnpacedShare, unpacedOrder) = Gaps(unpaced, s, refresh, period);
        r.Seconds = (shown[^1] - shown[0]) / 1e9;

        long addedSum = 0, maxAdded = 0, latencySum = 0, latencyMax = 0;
        long cap = pacer?.MarginCap != null ? pacer.MarginCap() : PresentPacerMaxMargin;
        for (int k = 0; k < s.Frames; k++)
        {
            long added = shown[k] - unpaced[k];
            r.NotEarlier &= added >= 0;
            addedSum += added;
            maxAdded = Math.Max(maxAdded, added);
            latencySum += unpaced[k] - ready[k];
            latencyMax = Math.Max(latencyMax, unpaced[k] - ready[k]);
            if (desired[k] != 0)
            {
                r.Paced++;
                // A target is at most the margin cap plus two guest periods after readiness.
                r.HoldBounded &= desired[k] - ready[k] <= Math.Max(cap, PresentPacerMaxMargin) + 2 * GuestVsync;
                if (s.HitchFrame >= 0 && k >= s.HitchFrame && k < s.HitchFrame + 8)
                {
                    r.PacedInHitchWindow = Math.Max(r.PacedInHitchWindow, 0) + 1;
                }
                if (s.HitchFrame >= 0 && k >= s.HitchFrame + 8)
                {
                    r.PacedAfterHitch = Math.Max(r.PacedAfterHitch, 0) + 1;
                }
            }
        }
        if (s.HitchFrame >= 0)
        {
            r.PacedInHitchWindow = Math.Max(r.PacedInHitchWindow, 0);
            r.PacedAfterHitch = Math.Max(r.PacedAfterHitch, 0);
        }
        r.MeanAdded = addedSum / 1e6 / s.Frames;
        r.MaxAdded = maxAdded / 1e6;
        r.UnpacedLatencyMean = latencySum / 1e6 / s.Frames;
        r.UnpacedLatencyMax = latencyMax / 1e6;
        (r.Stalls, r.MaxStallMs) = Drawables(ready, shown);
        (r.StallsUnpaced, r.MaxStallUnpacedMs) = Drawables(ready, unpaced);
        if (pacer != null)
        {
            r.Misses = pacer.Misses();
            r.Hits = pacer.Hits();
            r.Shifts = pacer.LatticeShifts();
            r.Reanchors = pacer.Reanchors();
            r.StandDowns = pacer.StandDowns();
            r.Margin = pacer.Margin();
            if (pacer.SessionOff != null)
            {
                r.SessionOff = pacer.SessionOff() ? 1 : 0;
                r.OffsetKnown = pacer.OffsetKnown() ? 1 : 0;
                r.Offset = pacer.Offset();
                r.ProbeRuns = pacer.ProbeRuns();
            }
        }

        ulong hash = 1469598103934665603UL;
        for (int k = 0; k < s.Frames; k++)
        {
            hash = (hash ^ (ulong)ready[k]) * 1099511628211UL;
            hash = (hash ^ (ulong)done[k]) * 1099511628211UL;
        }
        r.InputHash = hash.ToString("x16");
        return r;
    }

    const long PresentPacerMaxMargin = 2 * GuestVsync;

    // CAMetalLayer's 3 drawables: frame k's drawable is acquired 1 ms before its present call and released when frame
    // k + 1 replaces it on glass. Returns the acquisitions that would wait and the longest wait.
    static (int, double) Drawables(long[] ready, long[] shown)
    {
        int stalls = 0;
        long longest = 0;
        for (int k = 2; k < ready.Length; k++)
        {
            long acquire = ready[k] - Ms;
            // Held at the acquisition: frame k - 1 (not replaced yet) and k - 2 while frame k - 1 is not on glass.
            int held = 1 + (shown[k - 1] > acquire ? 1 : 0) + (k >= 3 && shown[k - 2] > acquire ? 1 : 0);
            if (held >= 3)
            {
                stalls++;
                longest = Math.Max(longest, shown[k - 2] - acquire);
            }
        }
        return (stalls, longest / 1e6);
    }

    static string D(double value) => value.ToString("0.###", Inv);

    static string Json(string name, Result r)
    {
        var json = new StringBuilder();
        json.Append('"').Append(name).Append("\":{");
        json.Append("\"frames\":").Append(r.Frames);
        json.Append(",\"inputHash\":\"").Append(r.InputHash).Append('"');
        json.Append(",\"gaps\":{").Append(string.Join(",", r.Gaps.Select(p => "\"" + p.Key + "\":" + p.Value))).Append('}');
        json.Append(",\"alternations17_50\":").Append(r.Pairs);
        json.Append(",\"unpacedAlternations17_50\":").Append(r.UnpacedPairs);
        json.Append(",\"alternationsPerSecond\":").Append(D(r.Pairs / r.Seconds));
        json.Append(",\"nominalShare\":").Append(r.Share.ToString("0.####", Inv));
        json.Append(",\"unpacedNominalShare\":").Append(r.UnpacedShare.ToString("0.####", Inv));
        json.Append(",\"seconds\":").Append(D(r.Seconds));
        json.Append(",\"pacedFrames\":").Append(r.Paced);
        json.Append(",\"pacedShare\":").Append((r.Paced / (double)r.Frames).ToString("0.####", Inv));
        json.Append(",\"maxAddedMs\":").Append(D(r.MaxAdded));
        json.Append(",\"meanAddedMs\":").Append(D(r.MeanAdded));
        json.Append(",\"unpacedLatencyMeanMs\":").Append(D(r.UnpacedLatencyMean));
        json.Append(",\"unpacedLatencyMaxMs\":").Append(D(r.UnpacedLatencyMax));
        json.Append(",\"drawableStalls\":").Append(r.Stalls);
        json.Append(",\"maxDrawableStallMs\":").Append(D(r.MaxStallMs));
        json.Append(",\"drawableStallsUnpaced\":").Append(r.StallsUnpaced);
        json.Append(",\"hits\":").Append(r.Hits);
        json.Append(",\"misses\":").Append(r.Misses);
        json.Append(",\"latticeShifts\":").Append(r.Shifts);
        json.Append(",\"reanchors\":").Append(r.Reanchors);
        json.Append(",\"standDowns\":").Append(r.StandDowns);
        json.Append(",\"episodes\":[").Append(string.Join(",", r.Episodes)).Append(']');
        json.Append(",\"instantStandDowns\":").Append(r.InstantStandDowns);
        json.Append(",\"marginsAfterStandDownMs\":[").Append(string.Join(",", r.MarginsAfterStandDown.Select(D))).Append(']');
        json.Append(",\"finalMarginMs\":").Append(D(r.Margin / 1e6));
        json.Append(",\"sessionOff\":").Append(r.SessionOff);
        json.Append(",\"offsetKnown\":").Append(r.OffsetKnown);
        json.Append(",\"offsetMs\":").Append(r.Offset == long.MinValue ? "null" : D(r.Offset / 1e6));
        json.Append(",\"probeRuns\":").Append(r.ProbeRuns);
        json.Append(",\"notEarlierThanUnpaced\":").Append(r.NotEarlier ? "true" : "false");
        json.Append(",\"orderKept\":").Append(r.OrderKept ? "true" : "false");
        json.Append(",\"holdBounded\":").Append(r.HoldBounded ? "true" : "false");
        json.Append(",\"pacedInHitchWindow\":").Append(r.PacedInHitchWindow);
        json.Append(",\"pacedAfterHitch\":").Append(r.PacedAfterHitch);
        json.Append('}');
        return json.ToString();
    }

    static string SweepRow(string label, IEnumerable<Scenario> runs, Type pacerType)
    {
        long pairs = 0, unpacedPairs = 0, nonNominal = 0, stalls = 0, paced = 0, frames = 0, standDowns = 0, instant = 0, sessionOff = 0;
        int count = 0;
        double addedSum = 0, maxAdded = 0;
        var hashes = new StringBuilder();
        var perRun = new List<string>();
        foreach (Scenario scenario in runs)
        {
            Result result = Run(scenario, pacerType);
            hashes.Append(result.InputHash);
            pairs += result.Pairs;
            unpacedPairs += result.UnpacedPairs;
            long nn = (scenario.Frames - 1) - (long)Math.Round(result.Share * (scenario.Frames - 1));
            nonNominal += nn;
            stalls += result.Stalls;
            paced += result.Paced;
            frames += scenario.Frames;
            standDowns += result.StandDowns;
            instant += result.InstantStandDowns;
            sessionOff += result.SessionOff == 1 ? 1 : 0;
            addedSum += result.MeanAdded;
            maxAdded = Math.Max(maxAdded, result.MaxAdded);
            count++;
            // Per run [pairs, gaps not at the guest period, mean ms added, paced frames, unpaced pairs].
            perRun.Add("[" + result.Pairs + "," + nn + "," + result.MeanAdded.ToString("0.##", Inv) + "," + result.Paced + "," + result.UnpacedPairs + "]");
        }
        return "{" + label + ",\"runs\":" + count + ",\"pairs\":" + pairs + ",\"unpacedPairs\":" + unpacedPairs + ",\"nonNominalGaps\":" + nonNominal +
               ",\"pacedShare\":" + (paced / (double)frames).ToString("0.###", Inv) + ",\"meanAddedMs\":" + D(addedSum / count) +
               ",\"maxAddedMs\":" + D(maxAdded) + ",\"drawableStalls\":" + stalls + ",\"standDowns\":" + standDowns +
               ",\"instantStandDowns\":" + instant + ",\"sessionOffRuns\":" + sessionOff +
               ",\"perRun\":[" + string.Join(",", perRun) + "],\"inputHash\":\"" + Hash(hashes.ToString()) + "\"}";
    }

    static int Main(string[] args)
    {
        string variant = args[0];
        Assembly vulkan = Assembly.LoadFrom(args[1]);
        Type pacerType = vulkan.GetType("Ryujinx.Graphics.Vulkan.PresentPacer", throwOnError: false);

        var scenarios = new List<Scenario>
        {
            // The adapt_present_pacing scenarios, unchanged (no compositor latency, Core Animation honouring the target).
            new() { Name = "deviceS1", Frames = 1800, Jitter = "gauss", JitterMs = 2.0, PhaseMs = 2.9, Seed = 1742 },
            new() { Name = "boundary60" },
            new() { Name = "boundary60Nearest", Rounding = "nearest" },
            new() { Name = "drift60", Frames = 3600, DisplayHz = 60.03, JitterMs = 2.0, Seed = 643 },
            new() { Name = "drift60Nearest", Frames = 3600, DisplayHz = 60.03, JitterMs = 2.0, Seed = 643, Rounding = "nearest" },
            new() { Name = "drift60Slow", Frames = 3600, DisplayHz = 59.97, JitterMs = 2.0, Seed = 645 },
            new() { Name = "drift60GpuTail", Frames = 3600, DisplayHz = 60.03, JitterMs = 2.0, TailMs = 5.0, TailJitterMs = 2.0, Seed = 644 },
            new() { Name = "drift60GpuTail10", Frames = 3600, DisplayHz = 60.03, JitterMs = 2.0, TailMs = 10.0, TailJitterMs = 4.0, Seed = 646 },
            new() { Name = "promotion120", DisplayHz = 120.0, ReportedHz = 120.0, Seed = 120 },
            new() { Name = "promotion120Nearest", DisplayHz = 120.0, ReportedHz = 120.0, Seed = 121, Rounding = "nearest" },
            new() { Name = "reports120Latches60", ReportedHz = 120.0, Seed = 122 },
            new() { Name = "boundary60LateByOne", Rounding = "lateByOne" },
            new() { Name = "notAllowed", Allowed = false },
            new() { Name = "guest60", GuestFrameMs = 1000.0 / 60, JitterMs = 2.0, Seed = 60 },
            new() { Name = "unstable", LongFrameShare = 0.3, JitterMs = 2.0, Seed = 7 },
            new() { Name = "hitch", HitchFrame = 300, Seed = 300 },
            // Device-like (IPA 658 logs): refresh reported 8.33 ms, the panel at 60 Hz, a compositor refresh between the
            // latch after GPU completion and glass (unpaced present call to glass about 22 ms, 39 ms when a frame slips),
            // a timed frame shown one refresh after its requested refresh; 4 minutes, so the stand-down cycle shows.
            new() { Name = "device658", Frames = 7200, ReportedHz = 120.0, Jitter = "gauss", JitterMs = 2.0, TailMs = 3.0, TailJitterMs = 1.0,
                    PhaseMs = 2.9, CompositorRefreshes = 1, TimedLateRefreshes = 1, Seed = 658 },
            // The same with the target honoured at its refresh (compositor latency only), two refreshes late, nearest rounding.
            new() { Name = "device658Honoured", Frames = 7200, ReportedHz = 120.0, Jitter = "gauss", JitterMs = 2.0, TailMs = 3.0, TailJitterMs = 1.0,
                    PhaseMs = 2.9, CompositorRefreshes = 1, TimedLateRefreshes = 0, Seed = 659 },
            new() { Name = "device658LateByTwo", Frames = 7200, ReportedHz = 120.0, Jitter = "gauss", JitterMs = 2.0, TailMs = 3.0, TailJitterMs = 1.0,
                    PhaseMs = 2.9, CompositorRefreshes = 1, TimedLateRefreshes = 2, Seed = 660 },
            new() { Name = "device658Nearest", Frames = 7200, ReportedHz = 120.0, Jitter = "gauss", JitterMs = 2.0, TailMs = 3.0, TailJitterMs = 1.0,
                    PhaseMs = 2.9, CompositorRefreshes = 1, TimedLateRefreshes = 1, Rounding = "nearest", Seed = 661 },
            // A longer, more variable GPU tail (present call to glass 25 to 45 ms).
            new() { Name = "device658GpuTail", Frames = 7200, ReportedHz = 120.0, Jitter = "gauss", JitterMs = 2.0, TailMs = 8.0, TailJitterMs = 3.0,
                    PhaseMs = 2.0, CompositorRefreshes = 1, TimedLateRefreshes = 1, Seed = 662 },
            // A timed frame shown 0 to 2 refreshes after its requested one at random: the offset never settles.
            new() { Name = "device658Unsettled", Frames = 7200, ReportedHz = 120.0, Jitter = "gauss", JitterMs = 2.0, TailMs = 3.0, TailJitterMs = 1.0,
                    PhaseMs = 2.9, CompositorRefreshes = 1, TimedLateRefreshes = 0, TimedLateRandom = true, Seed = 663 },
        };

        var reports = new List<string>();
        foreach (Scenario scenario in scenarios)
        {
            reports.Add(Json(scenario.Name, Run(scenario, pacerType)));
        }

        // The adapt_present_pacing sweep: jitter shape and amplitude x GPU tail x Core Animation rounding, each over 9
        // display phases x 5 seeds.
        var rows = new List<string>();
        var jitters = new (string, double)[] { ("uniform", 1.0), ("uniform", 2.5), ("uniform", 6.0), ("gauss", 2.5), ("gauss", 4.0), ("gauss", 8.0), ("late", 2.5), ("late", 4.0) };
        var tails = new (double, double)[] { (1.5, 0.3), (5.0, 2.0), (10.0, 4.0), (20.0, 5.0) };
        foreach (string rounding in new[] { "ceil", "nearest", "lateByOne" })
        {
            foreach (var (shape, amplitude) in jitters)
            {
                foreach (var (tail, tailJitter) in tails)
                {
                    var runs = new List<Scenario>();
                    for (int phase = 0; phase < 9; phase++)
                    {
                        for (int seed = 1; seed <= 5; seed++)
                        {
                            runs.Add(new Scenario
                            {
                                Name = "sweep", Frames = 900, Jitter = shape, JitterMs = amplitude, TailMs = tail, TailJitterMs = tailJitter,
                                PhaseMs = phase * 1000.0 / 60 / 9, Rounding = rounding, Seed = seed * 1000 + phase,
                            });
                        }
                    }
                    rows.Add(SweepRow("\"rounding\":\"" + rounding + "\",\"jitter\":\"" + shape + "\",\"jitterMs\":" + amplitude.ToString(Inv) +
                                      ",\"tailMs\":" + tail.ToString(Inv) + ",\"tailJitterMs\":" + tailJitter.ToString(Inv), runs, pacerType));
                }
            }
        }

        // The device sweep: the device model x timed-late refreshes (0, 1, 2) x GPU tail x jitter, over 9 display phases x
        // 4 seeds of 2 minutes.
        var deviceRows = new List<string>();
        foreach (int late in new[] { 0, 1, 2 })
        {
            foreach (var (tail, tailJitter) in new (double, double)[] { (3.0, 1.0), (8.0, 3.0) })
            {
                foreach (double sigma in new[] { 1.5, 2.5, 4.0 })
                {
                    var runs = new List<Scenario>();
                    for (int phase = 0; phase < 9; phase++)
                    {
                        for (int seed = 1; seed <= 4; seed++)
                        {
                            runs.Add(new Scenario
                            {
                                Name = "deviceSweep", Frames = 3600, ReportedHz = 120.0, Jitter = "gauss", JitterMs = sigma, TailMs = tail,
                                TailJitterMs = tailJitter, PhaseMs = phase * 1000.0 / 60 / 9, CompositorRefreshes = 1, TimedLateRefreshes = late,
                                Seed = 6580 + seed * 100 + phase,
                            });
                        }
                    }
                    deviceRows.Add(SweepRow("\"timedLateRefreshes\":" + late + ",\"tailMs\":" + tail.ToString(Inv) + ",\"tailJitterMs\":" +
                                            tailJitter.ToString(Inv) + ",\"jitterMs\":" + sigma.ToString(Inv), runs, pacerType));
                }
            }
        }

        string allocation = MeasureAllocation(pacerType);
        Console.WriteLine("{\"variant\":\"" + variant + "\",\"pacer\":" + (pacerType != null ? "true" : "false") +
                          ",\"fixes\":" + (pacerType?.GetMethod("get_SessionOff") != null ? "true" : "false") +
                          ",\"assembly\":\"" + vulkan.GetName().Name + "\",\"decisionAllocation\":" + allocation +
                          ",\"scenarios\":{" + string.Join(",", reports) + "},\"sweep\":[" + string.Join(",", rows) +
                          "],\"deviceSweep\":[" + string.Join(",", deviceRows) + "]}");
        return 0;
    }

    static string Hash(string text)
    {
        ulong hash = 1469598103934665603UL;
        foreach (char c in text)
        {
            hash = (hash ^ c) * 1099511628211UL;
        }
        return hash.ToString("x16");
    }

    // Bytes the per-frame decision and the feedback allocate on the render thread (after construction), with unpaced
    // frames (latency ring, percentile sort), probes, paced frames and stand-downs mixed in.
    static string MeasureAllocation(Type pacerType)
    {
        Pacer pacer = Pacer.Create(pacerType);
        pacer.SetRefresh(GuestVsync / 2);
        long now = 10_000 * Ms;
        for (int i = 0; i < 1000; i++)
        {
            now += 33_333_333;
            pacer.Next(now, true);
            pacer.Observe(pacer.FrameId(), now + 22 * Ms);
        }
        long before = GC.GetAllocatedBytesForCurrentThread();
        ulong sink = 0;
        long latency = 0;
        for (int i = 0; i < 100_000; i++)
        {
            now += 33_333_333 + (i % 5 - 2) * Ms;
            sink += pacer.Next(now, (i % 5000) != 0);
            // Every 10,000 frames, 60 frames shown 6 periods late: misses, a stand-down, unpaced frames feeding the latency
            // ring (and its sort), then a new probe.
            long glass = now + 22 * Ms + (i % 7 == 0 ? GuestVsync : 0) + (i % 10_000 is >= 2000 and < 2060 ? 6 * GuestVsync : 0);
            pacer.Observe(pacer.FrameId(), glass);
            latency += pacer.MarginCap != null ? pacer.MarginCap() : 0;
        }
        long after = GC.GetAllocatedBytesForCurrentThread();
        return "{\"calls\":100000,\"bytes\":" + (after - before) + ",\"paced\":" + pacer.PacedFrames() + ",\"standDowns\":" + pacer.StandDowns() +
               ",\"probeRuns\":" + (pacer.ProbeRuns != null ? pacer.ProbeRuns() : 0) +
               ",\"sessionOff\":" + (pacer.SessionOff != null && pacer.SessionOff() ? "true" : "false") + ",\"sink\":" + (sink != 0 ? "true" : "false") + "}";
    }
}
