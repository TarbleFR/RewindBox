// Present pacing before/after (adapt_present_pacing) on recorded-like frame-ready times.
// The production Ryujinx.Graphics.Vulkan.dll of the variant is loaded (args[1]). Candidate: its compiled PresentPacer
// (reflection, closed delegates: the production code itself) decides each frame's desiredPresentTime and is fed back,
// as Window feeds it from vkGetPastPresentationTimingGOOGLE, the on-glass time of each frame shown before the frame's
// present. Control: the assembly has no PresentPacer and Present chains no timing, so every frame is presented as soon
// as it is ready (desiredPresentTime 0).
// On glass, a frame with no target is shown at the first display refresh at or after its GPU completion (ready + GPU
// tail). With a target, Core Animation's choice of refresh is modelled three ways: the first refresh at or after the
// target ("ceil"), the nearest refresh ("nearest"), and one refresh after the first at or after it ("lateByOne", a
// pessimistic model the pacer must survive); never before the GPU completion, one frame per refresh (FIFO).
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
        public Func<long> PacedFrames, Misses, LatticeShifts, Reanchors, StandDowns, Margin;

        static T Get<T>(Type type, object instance, string name) where T : Delegate =>
            (T)Delegate.CreateDelegate(typeof(T), instance, type.GetMethod(name, BindingFlags.Public | BindingFlags.Instance)
                ?? throw new MissingMethodException(type.FullName, name));

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
        public bool Allowed = true;          // Window: PresentPacingAllowed && VSync Switch
        public int Seed = 650;
        public double LongFrameShare;        // share of frames taking one more guest period (unstable cadence)
        public int HitchFrame = -1;          // this frame and the following ones come 70 ms later
        public double HandlerMs = 2.0;       // presented handler -> history -> drained at the next present call
    }

    sealed class Result
    {
        public int Frames, Pairs, Paced, Stalls, StallsUnpaced;
        public double Seconds, Share, MeanAdded, MaxAdded, MaxStallMs, MaxStallUnpacedMs;
        public long Misses, Shifts, Reanchors, StandDowns, Margin;
        public string InputHash;
        public SortedDictionary<int, int> Gaps = new();
        public bool OrderKept, NotEarlier, HoldBounded;
        public int PacedInHitchWindow = -1, PacedAfterHitch = -1;
    }

    static double Gauss(Random random)
    {
        double u1 = 1 - random.NextDouble(), u2 = random.NextDouble();
        return Math.Sqrt(-2 * Math.Log(u1)) * Math.Cos(2 * Math.PI * u2);
    }

    static Result Run(Scenario s, Type pacerType)
    {
        var random = new Random(s.Seed);
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

        Pacer pacer = pacerType != null ? Pacer.Create(pacerType) : null;
        pacer?.SetRefresh((long)(1e9 / s.ReportedHz));
        long[] desired = new long[s.Frames];
        long[] shown = new long[s.Frames];
        long[] unpaced = new long[s.Frames];
        uint[] ids = new uint[s.Frames];
        int observed = 0;
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
            }

            long earliest = Latch(done[k]);
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
                shown[k] = Math.Max(aimed, earliest);
            }
            unpaced[k] = earliest;
            if (k > 0)
            {
                shown[k] = Math.Max(shown[k], Latch(shown[k - 1] + 1));
                unpaced[k] = Math.Max(unpaced[k], Latch(unpaced[k - 1] + 1));
            }
        }

        var r = new Result { Frames = s.Frames, OrderKept = true, NotEarlier = true, HoldBounded = true };
        long period = guestFrame;
        int previous = 0;
        for (int k = 1; k < s.Frames; k++)
        {
            long gap = shown[k] - shown[k - 1];
            r.OrderKept &= gap > 0;
            int name = (int)Math.Round(Math.Round(gap / 1e6 / (1000.0 / 120)) * (1000.0 / 120));
            r.Gaps[name] = r.Gaps.TryGetValue(name, out int count) ? count + 1 : 1;
            // An alternation: a gap shorter than the guest period next to one longer (17/50 at 60 Hz, 25/42 at 120 Hz).
            int side = gap < period - refresh / 2 ? -1 : gap > period + refresh / 2 ? 1 : 0;
            if (k > 1 && side != 0 && side == -previous)
            {
                r.Pairs++;
            }
            previous = side;
        }
        int nominalName = (int)Math.Round(s.GuestFrameMs);
        r.Share = r.Gaps.TryGetValue(nominalName, out int nominalCount) ? nominalCount / (double)(s.Frames - 1) : 0;
        r.Seconds = (shown[^1] - shown[0]) / 1e9;

        long addedSum = 0, maxAdded = 0;
        for (int k = 0; k < s.Frames; k++)
        {
            long added = shown[k] - unpaced[k];
            r.NotEarlier &= added >= 0;
            addedSum += added;
            maxAdded = Math.Max(maxAdded, added);
            if (desired[k] != 0)
            {
                r.Paced++;
                // A target is at most the margin plus two guest periods after readiness.
                r.HoldBounded &= desired[k] - ready[k] <= PresentPacerMaxMargin + 2 * GuestVsync;
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
        (r.Stalls, r.MaxStallMs) = Drawables(ready, shown);
        (r.StallsUnpaced, r.MaxStallUnpacedMs) = Drawables(ready, unpaced);
        if (pacer != null)
        {
            r.Misses = pacer.Misses();
            r.Shifts = pacer.LatticeShifts();
            r.Reanchors = pacer.Reanchors();
            r.StandDowns = pacer.StandDowns();
            r.Margin = pacer.Margin();
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

    static string Json(string name, Result r)
    {
        var json = new StringBuilder();
        json.Append('"').Append(name).Append("\":{");
        json.Append("\"frames\":").Append(r.Frames);
        json.Append(",\"inputHash\":\"").Append(r.InputHash).Append('"');
        json.Append(",\"gaps\":{").Append(string.Join(",", r.Gaps.Select(p => "\"" + p.Key + "\":" + p.Value))).Append('}');
        json.Append(",\"alternations17_50\":").Append(r.Pairs);
        json.Append(",\"alternationsPerSecond\":").Append((r.Pairs / r.Seconds).ToString("0.###", Inv));
        json.Append(",\"nominalShare\":").Append(r.Share.ToString("0.####", Inv));
        json.Append(",\"seconds\":").Append(r.Seconds.ToString("0.###", Inv));
        json.Append(",\"pacedFrames\":").Append(r.Paced);
        json.Append(",\"maxAddedMs\":").Append(r.MaxAdded.ToString("0.###", Inv));
        json.Append(",\"meanAddedMs\":").Append(r.MeanAdded.ToString("0.###", Inv));
        json.Append(",\"drawableStalls\":").Append(r.Stalls);
        json.Append(",\"maxDrawableStallMs\":").Append(r.MaxStallMs.ToString("0.###", Inv));
        json.Append(",\"drawableStallsUnpaced\":").Append(r.StallsUnpaced);
        json.Append(",\"misses\":").Append(r.Misses);
        json.Append(",\"latticeShifts\":").Append(r.Shifts);
        json.Append(",\"reanchors\":").Append(r.Reanchors);
        json.Append(",\"standDowns\":").Append(r.StandDowns);
        json.Append(",\"finalMarginMs\":").Append((r.Margin / 1e6).ToString("0.###", Inv));
        json.Append(",\"notEarlierThanUnpaced\":").Append(r.NotEarlier ? "true" : "false");
        json.Append(",\"orderKept\":").Append(r.OrderKept ? "true" : "false");
        json.Append(",\"holdBounded\":").Append(r.HoldBounded ? "true" : "false");
        json.Append(",\"pacedInHitchWindow\":").Append(r.PacedInHitchWindow);
        json.Append(",\"pacedAfterHitch\":").Append(r.PacedAfterHitch);
        json.Append('}');
        return json.ToString();
    }

    static int Main(string[] args)
    {
        string variant = args[0];
        Assembly vulkan = Assembly.LoadFrom(args[1]);
        Type pacerType = vulkan.GetType("Ryujinx.Graphics.Vulkan.PresentPacer", throwOnError: false);
        bool sweepOnly = args.Length > 2 && args[2] == "--sweep-only";

        var scenarios = new List<Scenario>
        {
            // Calibrated to the device histogram of S1 gameplay (7.6 % 17 ms, 82.6 % 33 ms, 7.3 % 50 ms on glass):
            // Gaussian ready jitter, the refresh boundary 1.45 sigma after the nominal completion.
            new() { Name = "deviceS1", Frames = 1800, Jitter = "gauss", JitterMs = 2.0, PhaseMs = 2.9, Seed = 1742 },
            // The worst phase: ready times jittering +-2.5 ms around a 60 Hz refresh boundary.
            new() { Name = "boundary60" },
            // The same under Core Animation's two plausible roundings of presentAtTime.
            new() { Name = "boundary60Nearest", Rounding = "nearest" },
            // A display slightly faster than the host clock: the phase sweeps every boundary in two minutes.
            new() { Name = "drift60", Frames = 3600, DisplayHz = 60.03, JitterMs = 2.0, Seed = 643 },
            new() { Name = "drift60Nearest", Frames = 3600, DisplayHz = 60.03, JitterMs = 2.0, Seed = 643, Rounding = "nearest" },
            // A display slightly slower than the host clock (the lattice must move earlier, not only later).
            new() { Name = "drift60Slow", Frames = 3600, DisplayHz = 59.97, JitterMs = 2.0, Seed = 645 },
            // The same drift with a longer and more variable GPU tail after the present call.
            new() { Name = "drift60GpuTail", Frames = 3600, DisplayHz = 60.03, JitterMs = 2.0, TailMs = 5.0, TailJitterMs = 2.0, Seed = 644 },
            new() { Name = "drift60GpuTail10", Frames = 3600, DisplayHz = 60.03, JitterMs = 2.0, TailMs = 10.0, TailJitterMs = 4.0, Seed = 646 },
            // The layer latched at 120 Hz (ProMotion with CADisableMinimumFrameDurationOnPhone).
            new() { Name = "promotion120", DisplayHz = 120.0, ReportedHz = 120.0, Seed = 120 },
            new() { Name = "promotion120Nearest", DisplayHz = 120.0, ReportedHz = 120.0, Seed = 121, Rounding = "nearest" },
            // ProMotion reporting 120 Hz while the layer is latched at 60 Hz.
            new() { Name = "reports120Latches60", ReportedHz = 120.0, Seed = 122 },
            // Core Animation showing a timed frame one refresh later than modelled: the pacer must not make it worse.
            new() { Name = "boundary60LateByOne", Rounding = "lateByOne" },
            // Pacing not allowed (VSync Unbounded/Custom at launch, or Window at VSync not Switch): never paced.
            new() { Name = "notAllowed", Allowed = false },
            // A 60 fps guest: multiple 1, never paced.
            new() { Name = "guest60", GuestFrameMs = 1000.0 / 60, JitterMs = 2.0, Seed = 60 },
            // A guest alternating between 30 and 20 fps frames: unstable cadence.
            new() { Name = "unstable", LongFrameShare = 0.3, JitterMs = 2.0, Seed = 7 },
            // A 70 ms hitch at frame 300 in a steady 30 fps run.
            new() { Name = "hitch", HitchFrame = 300, Seed = 300 },
        };

        var reports = new List<string>();
        if (!sweepOnly)
        {
            foreach (Scenario scenario in scenarios)
            {
                reports.Add(Json(scenario.Name, Run(scenario, pacerType)));
            }
        }

        // The sweep: jitter shape and amplitude x GPU tail x Core Animation rounding, each over 9 display phases x 5 seeds.
        var rows = new List<string>();
        var jitters = new (string, double)[] { ("uniform", 1.0), ("uniform", 2.5), ("uniform", 6.0), ("gauss", 2.5), ("gauss", 4.0), ("gauss", 8.0), ("late", 2.5), ("late", 4.0) };
        var tails = new (double, double)[] { (1.5, 0.3), (5.0, 2.0), (10.0, 4.0), (20.0, 5.0) };
        foreach (string rounding in new[] { "ceil", "nearest", "lateByOne" })
        {
            foreach (var (shape, amplitude) in jitters)
            {
                foreach (var (tail, tailJitter) in tails)
                {
                    long pairs = 0, nonNominal = 0, stalls = 0, paced = 0, frames = 0, standDowns = 0;
                    int runs = 0;
                    double addedSum = 0, maxAdded = 0;
                    var hashes = new StringBuilder();
                    for (int phase = 0; phase < 9; phase++)
                    {
                        for (int seed = 1; seed <= 5; seed++)
                        {
                            var scenario = new Scenario
                            {
                                Name = "sweep", Frames = 900, Jitter = shape, JitterMs = amplitude, TailMs = tail, TailJitterMs = tailJitter,
                                PhaseMs = phase * 1000.0 / 60 / 9, Rounding = rounding, Seed = seed * 1000 + phase,
                            };
                            Result result = Run(scenario, pacerType);
                            hashes.Append(result.InputHash);
                            pairs += result.Pairs;
                            long nn = (scenario.Frames - 1) - (long)Math.Round(result.Share * (scenario.Frames - 1));
                            nonNominal += nn;
                            stalls += result.Stalls;
                            paced += result.Paced;
                            frames += scenario.Frames;
                            standDowns += result.StandDowns;
                            addedSum += result.MeanAdded;
                            maxAdded = Math.Max(maxAdded, result.MaxAdded);
                            // Per run [pairs, gaps not at the guest period, mean ms added]: compared with the control run of
                            // the same inputs (the control variant's output, same order) by the test.
                            runs++;
                            rowRuns.Add((result.Pairs, nn, result.MeanAdded));
                        }
                    }
                    rows.Add("{\"rounding\":\"" + rounding + "\",\"jitter\":\"" + shape + "\",\"jitterMs\":" + amplitude.ToString(Inv) +
                             ",\"tailMs\":" + tail.ToString(Inv) + ",\"tailJitterMs\":" + tailJitter.ToString(Inv) + ",\"runs\":" + runs +
                             ",\"pairs\":" + pairs + ",\"nonNominalGaps\":" + nonNominal + ",\"pacedShare\":" + (paced / (double)frames).ToString("0.###", Inv) +
                             ",\"meanAddedMs\":" + (addedSum / runs).ToString("0.###", Inv) + ",\"maxAddedMs\":" + maxAdded.ToString("0.###", Inv) +
                             ",\"drawableStalls\":" + stalls + ",\"standDowns\":" + standDowns +
                             ",\"perRun\":[" + string.Join(",", rowRuns.Select(p => "[" + p.Item1 + "," + p.Item2 + "," + p.Item3.ToString("0.##", Inv) + "]")) + "]" +
                             ",\"inputHash\":\"" + Hash(hashes.ToString()) + "\"}");
                    rowRuns.Clear();
                }
            }
        }

        string allocation = MeasureAllocation(pacerType);
        Console.WriteLine("{\"variant\":\"" + variant + "\",\"pacer\":" + (pacerType != null ? "true" : "false") +
                          ",\"assembly\":\"" + vulkan.GetName().Name + "\",\"decisionAllocation\":" + allocation +
                          ",\"scenarios\":{" + string.Join(",", reports) + "},\"sweep\":[" + string.Join(",", rows) + "]}");
        return 0;
    }

    static readonly List<(int, long, double)> rowRuns = new();

    static string Hash(string text)
    {
        ulong hash = 1469598103934665603UL;
        foreach (char c in text)
        {
            hash = (hash ^ c) * 1099511628211UL;
        }
        return hash.ToString("x16");
    }

    // Bytes the per-frame decision and the feedback allocate on the render thread (after construction).
    static string MeasureAllocation(Type pacerType)
    {
        if (pacerType == null)
        {
            return "{\"calls\":0,\"bytes\":0}";
        }
        Pacer pacer = Pacer.Create(pacerType);
        pacer.SetRefresh(GuestVsync);
        long now = 10_000 * Ms;
        long glass = 0;
        for (int i = 0; i < 1000; i++)
        {
            now += 33_333_333;
            pacer.Next(now, true);
            pacer.Observe(pacer.FrameId(), now + 10 * Ms);
        }
        long before = GC.GetAllocatedBytesForCurrentThread();
        ulong sink = 0;
        for (int i = 0; i < 100_000; i++)
        {
            now += 33_333_333 + (i % 5 - 2) * Ms;
            sink += pacer.Next(now, (i % 5000) != 0);
            glass = now + 10 * Ms + (i % 7 == 0 ? GuestVsync : 0);
            pacer.Observe(pacer.FrameId(), glass);
        }
        long after = GC.GetAllocatedBytesForCurrentThread();
        return "{\"calls\":100000,\"bytes\":" + (after - before) + ",\"paced\":" + pacer.PacedFrames() + ",\"sink\":" + (sink != 0 ? "true" : "false") + "}";
    }
}
