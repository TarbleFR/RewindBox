// Fixture of test/melonx_diagnostics_snapshot_reuse_test.py: the side's real EmbeddedLaunchDiagnostics.cs and its real
// neostation_melonx_diagnostics export (Export.cs, generated from the side's EmbeddedRuntime.cs), called through the
// unmanaged entry point as the host calls it.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using Ryujinx.Common;

public static unsafe class Program
{
    private const int Capacity = 524288; // the host's buffer (MeloNXRuntimeAPI.diagnostics)
    private static readonly byte* Output = (byte*)NativeMemory.Alloc(Capacity);
    private static readonly delegate* unmanaged<byte*, int, int> Diagnostics = &Ryujinx.Library.Export.EmbeddedDiagnostics;

    private static int Poll(out int length)
    {
        int status = Diagnostics(Output, Capacity);
        length = 0;
        if (status == 0) while (Output[length] != 0) length++;
        return status;
    }

    private static string PollText()
    {
        int status = Poll(out int length);
        return status == 0 ? Encoding.UTF8.GetString(Output, length) : "status " + status;
    }

    // Timestamps and the process id differ between two runs: everything else must not.
    private static string Normal(string json) =>
        Regex.Replace(Regex.Replace(json, "\"timestamp\":\"[^\"]*\"", "\"timestamp\":\"T\""), "\"pid\":\\d+", "\"pid\":0");

    private static string LongDetail(int index) =>
        "LogRenderWork " + index + ": " + string.Concat(Enumerable.Range(0, 60).Select(part => "CreateBufferAccess " + (index * 31 + part) + " calls 12.5 ms; "));

    public static int Main(string[] arguments)
    {
        string variant = arguments[0];
        var report = new Dictionary<string, object> { ["variant"] = variant };
        string directory = Path.Combine(Path.GetTempPath(), "melonx-snapshot-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        string journal = Path.Combine(directory, "MeloNX-core.log");

        // --- Functional: after every step, the export's bytes (and Snapshot()'s, which must be the same) ---
        using var chain = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        int steps = 0, exportAndSnapshotEqual = 0, parsed = 0, unparsed = 0, statusNotZero = 0, maxEvents = 0, maxBytes = 0;
        var firstDifference = new List<string>();
        // The answers after these steps, one by one (what a stale snapshot would get wrong first).
        var watched = new Dictionary<string, object>();
        string[] watch = { "file begin", "begin again", "performance refused", "performance sample", "long 149" };
        void Step(string name, Action action)
        {
            action();
            steps++;
            string text = PollText();
            string again = PollText();
            string managed;
            try { managed = Encoding.UTF8.GetString(EmbeddedLaunchDiagnostics.Snapshot()); }
            catch (Exception error) { managed = "throws " + error.GetType().Name; }
            if (text.StartsWith("status ")) statusNotZero++;
            if (text == again && (text == managed || (text.StartsWith("status ") && managed.StartsWith("throws ")))) exportAndSnapshotEqual++;
            else if (firstDifference.Count < 3) firstDifference.Add(name);
            if (!text.StartsWith("status "))
            {
                try
                {
                    using var document = JsonDocument.Parse(text);
                    parsed++;
                    maxEvents = Math.Max(maxEvents, document.RootElement.GetProperty("events").GetArrayLength());
                    maxBytes = Math.Max(maxBytes, Encoding.UTF8.GetByteCount(text));
                }
                catch (JsonException) { unparsed++; }
            }
            chain.AppendData(Encoding.UTF8.GetBytes(name + "\n" + Normal(text) + "\n"));
            if (watch.Contains(name)) watched[name] = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(Normal(text)))).ToLowerInvariant()[..16];
        }

        Step("empty", () => { });
        Step("begin", EmbeddedLaunchDiagnostics.Begin);
        Step("file begin", () => EmbeddedLaunchDiagnostics.Record("file", "begin"));
        Step("file passed", () => EmbeddedLaunchDiagnostics.Record("file", "passed", detail: "opened"));
        Step("journal configured", () => EmbeddedLaunchDiagnostics.ConfigureJournal(journal));
        Step("keys begin", () => EmbeddedLaunchDiagnostics.Record("keys", "begin"));
        Step("fail", () => EmbeddedLaunchDiagnostics.Fail("keys", "missingKey", new InvalidOperationException("title key absent"), 7));
        // Begin clears the error code and detail without a new record: the snapshot must follow.
        Step("begin again", EmbeddedLaunchDiagnostics.Begin);
        Step("gpu begin", () => EmbeddedLaunchDiagnostics.Record("gpu", "begin"));
        // A performance record of a generation that is not the current one is refused, but its "begin" moves the stage.
        Step("performance refused", () => EmbeddedLaunchDiagnostics.Record("performance", "begin", performanceGeneration: 3));
        Step("performance generation", () => EmbeddedLaunchDiagnostics.BeginPerformance(3));
        Step("performance sample", () => EmbeddedLaunchDiagnostics.Record("performance", "sample", detail: "{\"windowMs\":5000}", performanceGeneration: 3));
        Step("performance sample 2", () => EmbeddedLaunchDiagnostics.Record("performance", "sample", detail: "{\"windowMs\":5100}", performanceGeneration: 3));
        Step("performance final", () => EmbeddedLaunchDiagnostics.Record("performance", "final", detail: "{\"windowMs\":900}", performanceGeneration: 3));
        Step("performance old generation", () => EmbeddedLaunchDiagnostics.Record("performance", "sample", detail: "late", performanceGeneration: 2));
        for (int index = 0; index < 20; index++)
        {
            int captured = index;
            Step("engine warning " + index, () => EmbeddedLaunchDiagnostics.RecordEngine(false, "repeated warning " + (captured % 2)));
        }
        Step("secret redacted", () => EmbeddedLaunchDiagnostics.Record("keys", "note", detail: "key 0123456789abcdef0123456789abcdef and\nheader_key = 00112233"));
        // A text the JSON writer may refuse: both sides must answer alike, then recover once it has left the ring.
        Step("lone surrogate", () => EmbeddedLaunchDiagnostics.Record("gpu", "engineWarning", detail: "bad \ud800 text"));
        Step("after surrogate", () => EmbeddedLaunchDiagnostics.Record("gpu", "engineWarning", detail: "next"));
        for (int index = 0; index < 150; index++)
        {
            int captured = index;
            Step("long " + index, () => EmbeddedLaunchDiagnostics.Record("gpu", "engineWarning", captured, LongDetail(captured)));
        }
        Step("journal reconfigured", () => EmbeddedLaunchDiagnostics.ConfigureJournal(journal));
        Step("crash record", () => EmbeddedLaunchDiagnostics.RecordCrash(new InvalidOperationException("fixture")));
        Step("generation 4", () => EmbeddedLaunchDiagnostics.BeginPerformance(4));
        Step("performance 4", () => EmbeddedLaunchDiagnostics.Record("performance", "sample", detail: "{\"windowMs\":5000}", performanceGeneration: 4));
        report["functional"] = new Dictionary<string, object>
        {
            ["steps"] = steps, ["digest"] = Convert.ToHexString(chain.GetHashAndReset()).ToLowerInvariant(),
            ["exportTwiceAndSnapshotEqual"] = exportAndSnapshotEqual, ["parsed"] = parsed, ["unparsed"] = unparsed, ["statusNotZero"] = statusNotZero,
            ["maxEvents"] = maxEvents, ["maxBytes"] = maxBytes, ["firstDifferences"] = firstDifference, ["watched"] = watched,
            ["journalLines"] = File.ReadAllLines(journal).Length,
        };

        // --- Capacity: the export's answers at the edges ---
        Poll(out int size);
        byte* small = (byte*)NativeMemory.Alloc((nuint)size + 2);
        new Span<byte>(small, size + 2).Fill(0xEE);
        int exact = Diagnostics(small, size), untouched = small[0];
        int room = Diagnostics(small, size + 1);
        report["capacity"] = new Dictionary<string, object>
        {
            ["size"] = size, ["nullOutput"] = Diagnostics(null, Capacity), ["zeroCapacity"] = Diagnostics(small, 0),
            ["capacityOfTheSize"] = exact, ["untouchedWhenRefused"] = untouched == 0xEE,
            ["capacityOfTheSizePlusOne"] = room, ["terminated"] = small[size] == 0 && small[size + 1] == 0xEE,
            ["sameBytes"] = new Span<byte>(small, size).SequenceEqual(new Span<byte>(Output, size)),
        };
        NativeMemory.Free(small);

        // --- Allocations of the polling thread (the ring holds 64 long records) ---
        for (int warm = 0; warm < 4; warm++) Poll(out _);
        (long written, long kept) = Counts();
        long before = GC.GetAllocatedBytesForCurrentThread();
        const int QuietPolls = 1000;
        for (int poll = 0; poll < QuietPolls; poll++) Poll(out _);
        long quiet = GC.GetAllocatedBytesForCurrentThread() - before;
        (long writtenAfter, long keptAfter) = Counts();
        // One new record before each poll: only the polls are measured.
        long changing = 0;
        const int ChangingPolls = 200;
        for (int poll = 0; poll < ChangingPolls; poll++)
        {
            EmbeddedLaunchDiagnostics.Record("gpu", "engineWarning", poll, LongDetail(1000 + poll));
            before = GC.GetAllocatedBytesForCurrentThread();
            Poll(out _);
            changing += GC.GetAllocatedBytesForCurrentThread() - before;
        }
        (long writtenEnd, long keptEnd) = Counts();
        report["allocations"] = new Dictionary<string, object>
        {
            ["snapshotBytes"] = size, ["quietPolls"] = QuietPolls, ["quietBytesPerPoll"] = quiet / QuietPolls,
            ["changingPolls"] = ChangingPolls, ["changingBytesPerPoll"] = changing / ChangingPolls,
            ["quietWritten"] = writtenAfter - written, ["quietKept"] = keptAfter - kept,
            ["changingWritten"] = writtenEnd - writtenAfter, ["changingKept"] = keptEnd - keptAfter,
        };

        // --- The observer is still asked at every poll, and cannot break one ---
        int observed = 0;
        EmbeddedLaunchDiagnostics.PerformanceObserver = () => { observed++; if (observed % 3 == 0) throw new InvalidOperationException("observer"); };
        int observerStatus = 0;
        for (int poll = 0; poll < 30; poll++) observerStatus |= Poll(out _);
        EmbeddedLaunchDiagnostics.PerformanceObserver = null;
        report["observer"] = new Dictionary<string, object> { ["calls"] = observed, ["status"] = observerStatus };

        // --- Writers and a poller together: every answer is a whole snapshot of a state that existed ---
        int invalid = 0, unordered = 0, overfull = 0, backwards = 0, polls = 0;
        long lastSeen = 0;
        using var start = new ManualResetEventSlim();
        var writers = Enumerable.Range(0, 4).Select(writer => new Thread(() =>
        {
            start.Wait();
            for (int index = 0; index < 1500; index++)
                EmbeddedLaunchDiagnostics.Record("gpu", "engineWarning", writer, "writer " + writer + " record " + index + " " + new string('x', index % 300));
        })).ToArray();
        foreach (Thread thread in writers) thread.Start();
        var poller = new Thread(() =>
        {
            byte* own = (byte*)NativeMemory.Alloc(Capacity);
            start.Wait();
            while (writers.Any(thread => thread.IsAlive) || polls < 500)
            {
                polls++;
                if (Diagnostics(own, Capacity) != 0) { invalid++; continue; }
                int length = 0;
                while (own[length] != 0) length++;
                try
                {
                    using var document = JsonDocument.Parse(new ReadOnlyMemory<byte>(new Span<byte>(own, length).ToArray()));
                    long previous = 0, last = 0;
                    int count = 0;
                    foreach (JsonElement item in document.RootElement.GetProperty("events").EnumerateArray())
                    {
                        last = item.GetProperty("sequence").GetInt64();
                        if (last <= previous) unordered++;
                        previous = last;
                        count++;
                    }
                    if (count > 64) overfull++;
                    if (last < lastSeen) backwards++;
                    lastSeen = last;
                }
                catch (JsonException) { invalid++; }
            }
            NativeMemory.Free(own);
        });
        poller.Start();
        start.Set();
        foreach (Thread thread in writers) thread.Join();
        poller.Join();
        string final = PollText();
        report["concurrent"] = new Dictionary<string, object>
        {
            ["polls"] = polls >= 500, ["invalid"] = invalid, ["unordered"] = unordered, ["overfull"] = overfull, ["backwards"] = backwards,
            ["finalEqualsSnapshot"] = final == Encoding.UTF8.GetString(EmbeddedLaunchDiagnostics.Snapshot()),
            ["finalEvents"] = EventCount(final),
        };

        Directory.Delete(directory, true);
        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }

    private static int EventCount(string json)
    {
        try { using var document = JsonDocument.Parse(json); return document.RootElement.GetProperty("events").GetArrayLength(); }
        catch (JsonException) { return -1; }
    }

    // The candidate's own counts (absent from the control).
    private static (long, long) Counts()
    {
        var property = typeof(EmbeddedLaunchDiagnostics).GetProperty("SnapshotCounts");
        if (property == null) return (0, 0);
        var value = ((long Written, long Kept))property.GetValue(null);
        return (value.Written, value.Kept);
    }
}
