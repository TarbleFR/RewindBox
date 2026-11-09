// Scenarios for melonx_pipeline_variant_replay_test.py, run against the production Ryujinx.Graphics.Vulkan of the final
// preparation (test-only InternalsVisibleTo): the real PipelineState codec, the real PipelineVariantJournal and the real
// BackgroundCompilationScheduler (its pipeline cache manager is a bare instance whose worker caches are empty handles and
// whose upkeep is off: this host has no Vulkan device). A replay target stands for a program: it schedules each variant on
// the real scheduler at low priority and "creates" it in a given time (or fails), as ShaderCollection's Schedule does
// with CreateGraphicsPipeline. Times are host times, not iPhone times.
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

var report = new Dictionary<string, object>();
var random = new Random(711);
string root = Path.Combine(Path.GetTempPath(), "melonx-variant-replay-" + Environment.ProcessId);
Directory.CreateDirectory(root);
int failures = 0;

void Require(bool condition, string what)
{
    if (!condition)
    {
        failures++;
        Console.Error.WriteLine("REQUIRE FAILED: " + what);
    }
}

// ---------------------------------------------------------------- A. the semantic codec, on the real PipelineState
PropertyInfo[] scalars = typeof(PipelineState).GetProperties(BindingFlags.Public | BindingFlags.Instance)
    .Where(p => p.CanRead && p.CanWrite && p.GetIndexParameters().Length == 0).ToArray();
string[] schemaFields = PipelineVariantJournal.StateFields.Split(';')[0].Split(',');
report["codecFields"] = schemaFields.Length;
report["stateProperties"] = scalars.Length;
Require(schemaFields.Length == scalars.Length && schemaFields.All(f => scalars.Any(p => p.Name == f)), "schema names every key property");

object RandomValue(Type type)
{
    if (type == typeof(float)) return (float)(random.NextDouble() * 64 - 32);
    if (type == typeof(bool)) return random.Next(2) == 1;
    uint raw = (uint)random.NextInt64(0, 1L << 32);
    if (type == typeof(uint)) return raw;
    return Enum.ToObject(type, raw);
}

PipelineState RandomState(out int[] slots)
{
    PipelineState state = new();
    state.Initialize(false);
    object boxed = state;

    foreach (PropertyInfo property in scalars)
    {
        property.SetValue(boxed, RandomValue(property.PropertyType));
    }

    state = (PipelineState)boxed;
    int colorCount = random.Next(0, 9);
    var chosen = Enumerable.Range(0, 8).OrderBy(_ => random.Next()).Take(colorCount).OrderBy(x => x).ToArray();
    slots = chosen;
    state.ColorBlendAttachmentStateCount = colorCount == 0 ? 0u : (uint)(chosen[^1] + 1);
    state.VertexAttributeDescriptionsCount = (uint)random.Next(0, 33);
    state.VertexBindingDescriptionsCount = (uint)random.Next(0, 34);
    state.StagesCount = (uint)random.Next(1, 6);

    for (int i = 0; i < 32; i++)
    {
        state.Internal.VertexAttributeDescriptions[i] = new VertexInputAttributeDescription(
            (uint)random.Next(32), (uint)random.Next(33), (Format)random.Next(200), (uint)random.Next(4096));
    }

    for (int i = 0; i < 33; i++)
    {
        state.Internal.VertexBindingDescriptions[i] = new VertexInputBindingDescription(
            (uint)random.Next(33), (uint)random.Next(512), (VertexInputRate)random.Next(2));
    }

    for (int i = 0; i < 8; i++)
    {
        state.Internal.ColorBlendAttachmentState[i] = new PipelineColorBlendAttachmentState(
            random.Next(2) == 1, (BlendFactor)random.Next(19), (BlendFactor)random.Next(19), (BlendOp)random.Next(5),
            (BlendFactor)random.Next(19), (BlendFactor)random.Next(19), (BlendOp)random.Next(5), (ColorComponentFlags)random.Next(16));
    }

    for (int i = 0; i < 9; i++)
    {
        state.Internal.AttachmentFormats[i] = (Format)random.Next(1, 200);
    }

    state.Internal.AttachmentIntegerFormatMask = (uint)random.Next(256);
    state.Internal.LogicOpsAllowed = random.Next(2) == 1;
    state.HasTessellationControlShader = random.Next(2) == 1;

    // A random value wider than its field spills into the next field's bits through the packed setters; a draw's state never
    // holds such a value. Rebuild the key words from the fields' own values, as a state built by PipelineBase is.
    PipelineState canonical = new();
    canonical.Initialize(false);
    object source = state, target = canonical;

    foreach (PropertyInfo property in scalars)
    {
        property.SetValue(target, property.GetValue(source));
    }

    canonical = (PipelineState)target;
    canonical.Internal.VertexAttributeDescriptions = state.Internal.VertexAttributeDescriptions;
    canonical.Internal.VertexBindingDescriptions = state.Internal.VertexBindingDescriptions;
    canonical.Internal.ColorBlendAttachmentState = state.Internal.ColorBlendAttachmentState;
    canonical.Internal.AttachmentFormats = state.Internal.AttachmentFormats;
    canonical.Internal.AttachmentIntegerFormatMask = state.Internal.AttachmentIntegerFormatMask;
    canonical.Internal.LogicOpsAllowed = state.Internal.LogicOpsAllowed;
    canonical.HasTessellationControlShader = state.HasTessellationControlShader;

    return canonical;
}

int roundTrips = 0, keyEqual = 0, hashEqual = 0, deterministic = 0, slotsEqual = 0, tessEqual = 0;
int maxBytes = 0;

for (int n = 0; n < 3000; n++)
{
    PipelineState state = RandomState(out int[] slots);
    byte[] bytes = state.WriteVariant(slots);
    maxBytes = Math.Max(maxBytes, bytes.Length);
    deterministic += bytes.AsSpan().SequenceEqual(state.WriteVariant(slots)) ? 1 : 0;

    PipelineState read = new();
    read.Initialize(false);
    // Different garbage beyond the counts, as a fresh state of another session would have.
    for (int i = 0; i < 32; i++) read.Internal.VertexAttributeDescriptions[i] = new VertexInputAttributeDescription(99, 99, Format.R8Unorm, 99);

    Span<int> readSlots = stackalloc int[8];

    if (read.TryReadVariant(bytes, readSlots, out int colorCount))
    {
        roundTrips++;
        keyEqual += read.Internal.Equals(ref state.Internal) ? 1 : 0;
        hashEqual += read.Internal.GetHashCode() == state.Internal.GetHashCode() ? 1 : 0;
        slotsEqual += readSlots[..colorCount].SequenceEqual(slots) ? 1 : 0;
        tessEqual += read.HasTessellationControlShader == state.HasTessellationControlShader ? 1 : 0;
    }
}

report["codec"] = new Dictionary<string, object>
{
    ["states"] = 3000, ["readBack"] = roundTrips, ["sameKey"] = keyEqual, ["sameHash"] = hashEqual, ["sameSlots"] = slotsEqual,
    ["sameTessellation"] = tessEqual, ["deterministic"] = deterministic, ["maxBytes"] = maxBytes,
};

bool Rejected(byte[] bytes)
{
    PipelineState read = new();
    read.Initialize(false);
    Span<int> slots = stackalloc int[8];

    return !read.TryReadVariant(bytes, slots, out _);
}

{
    PipelineState state = RandomState(out int[] slots);
    while (slots.Length < 2) state = RandomState(out slots);
    byte[] good = state.WriteVariant(slots);
    int fieldOffset(string name) => Array.IndexOf(schemaFields, name) * 4;
    byte[] With(string name, uint value)
    {
        byte[] copy = (byte[])good.Clone();
        BitConverter.TryWriteBytes(copy.AsSpan(fieldOffset(name), 4), value);
        return copy;
    }

    var rejections = new Dictionary<string, bool>
    {
        ["truncated"] = Rejected(good[..^1]),
        ["extraByte"] = Rejected([.. good, 0]),
        ["empty"] = Rejected([]),
        ["boolTwo"] = Rejected(With("DepthTestEnable", 2)),
        ["topologyTooWide"] = Rejected(With("Topology", 0x10)),
        ["attributesOver32"] = Rejected(With("VertexAttributeDescriptionsCount", 33)),
        ["stagesZero"] = Rejected(With("StagesCount", 0)),
        ["blendCountOver8"] = Rejected(With("ColorBlendAttachmentStateCount", 9)),
    };
    // Colour slots out of order: swap the last two slot values.
    byte[] swapped = (byte[])good.Clone();
    int last = swapped.Length - 4;
    (swapped[last], swapped[last - 4]) = (swapped[last - 4], swapped[last]);
    rejections["slotsOutOfOrder"] = Rejected(swapped);
    byte[] highSlot = (byte[])good.Clone();
    BitConverter.TryWriteBytes(highSlot.AsSpan(highSlot.Length - 4, 4), 8u);
    rejections["slotOverBlendCount"] = Rejected(highSlot);
    report["codecRejects"] = rejections;
    Require(!Rejected(good), "a valid variant is read");
}

// ---------------------------------------------------------------- B. the journal file
string JournalPath(string name) => Path.Combine(root, name, "pipeline-key.variants");
byte[] Variant(int seed)
{
    var local = new Random(seed);
    PipelineState state = new();
    state.Initialize(false);
    state.StagesCount = 2;
    state.ColorBlendAttachmentStateCount = 1;
    state.Topology = (PrimitiveTopology)local.Next(4);
    state.DepthTestEnable = local.Next(2) == 1;
    state.Internal.AttachmentFormats[0] = (Format)(37 + local.Next(40));
    state.LineWidth = 1f + seed;
    return state.WriteVariant([0]);
}

PipelineVariantJournal Open(string name, Func<int> device = null) =>
    new(JournalPath(name), PipelineVariantJournal.Schema, device ?? (() => 60), loadInBackground: false);

string coreLog = Path.Combine(root, "MeloNX-core.log");
Ryujinx.Common.EmbeddedLaunchDiagnostics.ConfigureJournal(coreLog);

string[] Records(Func<string, bool> filter = null)
{
    Thread.Sleep(20);
    using var stream = new FileStream(coreLog, FileMode.Open, FileAccess.Read, FileShare.ReadWrite);
    using var reader = new StreamReader(stream);
    return reader.ReadToEnd().Split('\n').Where(l => l.Contains("pipelineVariants")).Where(filter ?? (_ => true)).ToArray();
}

// The lines are appended off the noting thread: wait until the file holds at least `minimum` bytes and stops growing.
void WaitFile(string path, long minimum)
{
    var watch = Stopwatch.StartNew();
    long last = -1;
    int still = 0;
    while (watch.ElapsedMilliseconds < 10000)
    {
        long length = File.Exists(path) ? new FileInfo(path).Length : 0;
        still = length == last ? still + 1 : 0;
        last = length;
        if (length >= minimum && still >= 15) return;
        Thread.Sleep(10);
    }
}

{
    // Session 1: 6 programs x 3 late states, with times and costs; one state met twice (once per session only).
    var journal = Open("file");
    for (int p = 0; p < 6; p++)
        for (int v = 0; v < 3; v++)
            journal.NoteLate(0x1000UL + (ulong)p, Variant(p * 10 + v), 40 + v * 100, joined: false);
    journal.NoteLate(0x1000UL, Variant(0), 500, joined: false); // second pass in the same session
    WaitFile(JournalPath("file"), 16 + 18 * 40);
    long size1 = new FileInfo(JournalPath("file")).Length;
    int newOnes = journal.LateNew;
    // A torn tail: a line cut by the end of the process.
    using (var stream = new FileStream(JournalPath("file"), FileMode.Append)) stream.Write(new byte[] { 0x40, 0x01, 1, 2, 3 });
    var second = Open("file");
    report["file"] = new Dictionary<string, object>
    {
        ["session1New"] = newOnes, ["session1Bytes"] = size1, ["session2Loaded"] = second.Loaded, ["session2Session"] = second.Session,
        ["loadedLine"] = Records(r => r.Contains("loaded")).LastOrDefault(),
    };
    // Schema change: nothing is read.
    byte[] data = File.ReadAllBytes(JournalPath("file"));
    data[8] ^= 0xFF;
    File.WriteAllBytes(JournalPath("file"), data);
    report["otherSchemaLoaded"] = Open("file").Loaded;
}

{
    // Stale: a variant last met in session 1 is dropped at session 10 (1 + 8 < 10); one met again in session 2 is kept.
    // A session's ordinal is one more than the latest session the journal holds a line of.
    var journal = Open("stale");
    journal.NoteLate(0x2000, Variant(1), 50, false);
    journal.NoteLate(0x2001, Variant(2), 50, false);
    WaitFile(JournalPath("stale"), 16);
    for (int s = 0; s < 8; s++)
    {
        var next = Open("stale");
        if (s == 0) next.NoteLate(0x2001, Variant(2), 50, false);
        next.NoteLate(0x2FFF, Variant(3000 + s), 50, false); // something met late in sessions 2 to 9
        WaitFile(JournalPath("stale"), 16);
    }
    var last = Open("stale");
    report["stale"] = new Dictionary<string, object> { ["loaded"] = last.Loaded, ["session"] = last.Session, ["dropped"] = last.Dropped };
}

{
    // Bounds: 2100 distinct late states in one session keep 2048, and the file stays under 2 MiB.
    var journal = Open("bounds");
    for (int i = 0; i < 2100; i++) journal.NoteLate(0x3000UL + (ulong)(i % 300), Variant(1000 + i), 60, false);
    WaitFile(JournalPath("bounds"), 16 + 2048L * 40);
    var watch = Stopwatch.StartNew();
    var reopened = Open("bounds");
    long loadMs = watch.ElapsedMilliseconds;
    watch.Restart();
    var background = new PipelineVariantJournal(JournalPath("bounds"), PipelineVariantJournal.Schema, () => 60, loadInBackground: true);
    long constructMs = watch.ElapsedMilliseconds;
    report["bounds"] = new Dictionary<string, object>
    {
        ["lateNew"] = journal.LateNew, ["fileBytes"] = new FileInfo(JournalPath("bounds")).Length, ["reloaded"] = reopened.Loaded,
        ["loadMs"] = loadMs, ["backgroundConstructorMs"] = constructMs,
    };
    Thread.Sleep(300);
}

// ---------------------------------------------------------------- C. replay on the real background compile scheduler
BackgroundCompilationScheduler NewScheduler()
{
    var manager = (PipelineCacheManager)RuntimeHelpers.GetUninitializedObject(typeof(PipelineCacheManager));
    Type stateType = typeof(PipelineCacheManager).GetNestedType("CacheState", BindingFlags.NonPublic);
    Array states = Array.CreateInstance(stateType, BackgroundCompilationScheduler.PipelineCacheCount);
    for (int i = 0; i < states.Length; i++)
        states.SetValue(Activator.CreateInstance(stateType, new object[] { default(PipelineCache), null, "worker " + i, 1L << 27, 0L, false }), i);
    typeof(PipelineCacheManager).GetField("_workerStates", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(manager, states);
    typeof(PipelineCacheManager).GetField("_disposed", BindingFlags.Instance | BindingFlags.NonPublic).SetValue(manager, true); // no upkeep
    return new BackgroundCompilationScheduler(manager);
}

var order = new ConcurrentQueue<string>();
var executions = new ConcurrentDictionary<string, int>();

bool WaitUntil(Func<bool> condition, int timeoutMs)
{
    var watch = Stopwatch.StartNew();
    while (watch.ElapsedMilliseconds < timeoutMs) { if (condition()) return true; Thread.Sleep(2); }
    return condition();
}

{
    // Relaunch: session 1 meets 9 states of one program late (different sessions counts via two earlier sessions, first
    // seen times and costs); session 2 replays them ranked, two at a time, behind the scheduler's demand and warm-up work.
    string name = "replay";
    var s1 = Open(name);
    for (int v = 0; v < 9; v++) s1.NoteLate(0xAAAA, Variant(500 + v), 30 + 10 * v, false);
    WaitFile(JournalPath(name), 16 + 9 * 40);
    var s2 = Open(name);
    for (int v = 0; v < 3; v++) s2.NoteLate(0xAAAA, Variant(500 + v), 30, false); // these three met in two sessions
    WaitFile(JournalPath(name), 0);
    Thread.Sleep(100);

    var scheduler = NewScheduler();
    var target = new Target { Scheduler = scheduler, Order = order, Executions = executions };
    var s3 = Open(name);
    var watch = Stopwatch.StartNew();
    s3.Offer(0xAAAA, target);
    long offerMs = watch.ElapsedMilliseconds;
    WaitUntil(() => s3.Replayed == 9, 10000);
    var ranked = order.ToArray();
    // Expected rank: the three seen in two sessions first, then the others by cost (all met at about the same time).
    var expected = new[] { 500, 501, 502 }.Select(v => PipelineVariantJournal.Checksum64(Variant(v))).ToArray();
    report["relaunch"] = new Dictionary<string, object>
    {
        ["planned"] = s3.Loaded, ["replayed"] = s3.Replayed, ["offerMs"] = offerMs, ["maxInFlight"] = target.MaxInFlight,
        ["firstThreeAreTwoSessionStates"] = ranked.Take(3).All(n => expected.Any(e => n.EndsWith($"/{e:X}"))),
        ["executedOnce"] = executions.Values.All(c => c == 1),
        ["summary"] = s3.Summary("test"),
    };
    // Second pass in the same session: the states now exist; a late note of one counts as built but missed.
    s3.NoteLate(0xAAAA, Variant(503), 5, false);
    report["afterReplayLate"] = new Dictionary<string, object> { ["builtButMissed"] = s3.LateAfterBuilt, ["new"] = s3.LateNew };
    scheduler.Dispose();
}

{
    // A demanded state behind a preparation queue: 20 warm-ups (60 ms each) are queued at low priority before the replay of
    // state X; a draw promotes X's compile (as TryWaitForBackgroundGraphicsPipeline does) and waits: X is created before
    // the warm-ups still queued. Eight draws waiting at once share the one compile.
    var scheduler = NewScheduler();
    string name = "priority";
    var s1 = Open(name);
    s1.NoteLate(0xBBBB, Variant(700), 80, false);
    WaitFile(JournalPath(name), 16 + 40);
    var target = new Target { Scheduler = scheduler, Order = new(), Executions = new(), Cost = _ => (40, false) };
    var warmUps = Enumerable.Range(0, 20).Select(i => scheduler.SchedulePipelineCompile(_ => { target.Order.Enqueue("warm-up " + i); Thread.Sleep(60); })).ToArray();
    var s2 = Open(name);
    s2.Offer(0xBBBB, target);
    ulong id = PipelineVariantJournal.Checksum64(Variant(700));
    WaitUntil(() => target.Queued.ContainsKey(id), 2000);
    Task queued = target.Queued[id];
    var watch = Stopwatch.StartNew();
    scheduler.PromotePipelineCompile(queued);
    var waiters = Enumerable.Range(0, 8).Select(_ => Task.Run(() => queued.Wait())).ToArray();
    Task.WaitAll(waiters);
    long waitedMs = watch.ElapsedMilliseconds;
    int warmUpsDoneBefore = target.Order.TakeWhile(n => n.StartsWith("warm-up")).Count();
    Task.WaitAll(warmUps);
    report["priority"] = new Dictionary<string, object>
    {
        ["waitedMs"] = waitedMs, ["warmUpsQueued"] = 20, ["warmUpsBeforeIt"] = warmUpsDoneBefore,
        ["compilesOfIt"] = target.Executions.Values.Sum(), ["waiters"] = waiters.Length,
    };
    scheduler.Dispose();
}

{
    // Close during compilation: 40 planned states of 50 ms, the scheduler disposed after the first ones started. The running
    // compiles finish, the queued ones are cancelled, nothing is marked failed, and no replay is scheduled afterwards.
    var scheduler = NewScheduler();
    string name = "close";
    var s1 = Open(name);
    for (int v = 0; v < 40; v++) s1.NoteLate(0xCCCC, Variant(800 + v), 50, false);
    WaitFile(JournalPath(name), 16 + 40 * 40);
    var target = new Target { Scheduler = scheduler, Order = new(), Executions = new(), Cost = _ => (50, false) };
    var s2 = Open(name);
    s2.Offer(0xCCCC, target);
    WaitUntil(() => s2.Replayed >= 2, 3000);
    scheduler.Dispose();
    WaitUntil(() => target.InFlight == 0, 3000);
    Thread.Sleep(200);
    int executed = target.Executions.Values.Sum();
    Thread.Sleep(200);
    WaitFile(JournalPath(name), 16);
    report["close"] = new Dictionary<string, object>
    {
        ["planned"] = 40, ["executed"] = executed, ["executedAfterClose"] = target.Executions.Values.Sum() - executed,
        ["failedMarked"] = s2.ReplayFailed, ["nextPlanned"] = Open(name).Loaded,
    };
}

{
    // Failures. Deterministic (the creation returns nothing, memory not short): one strike, retried at the next launch; a
    // second failure in a later launch suppresses it; a draw that then creates the state successfully clears the marker.
    // Temporary (the creation fails while device memory is at 8 % or less, or the renderer throws): no strike.
    var scheduler = NewScheduler();
    string name = "failure";
    var s1 = Open(name);
    s1.NoteLate(0xDDDD, Variant(900), 70, false); // fails deterministically
    s1.NoteLate(0xDDDD, Variant(901), 70, false); // fails under memory pressure
    s1.NoteLate(0xDDDD, Variant(902), 70, false); // the renderer throws while creating it
    s1.NoteLate(0xDDDD, Variant(903), 70, false); // builds
    WaitFile(JournalPath(name), 16);
    ulong v900 = PipelineVariantJournal.Checksum64(Variant(900)), v901 = PipelineVariantJournal.Checksum64(Variant(901));
    ulong v902 = PipelineVariantJournal.Checksum64(Variant(902));
    int device = 60;
    PipelineVariantJournal Launch()
    {
        device = 60;
        var journal = Open(name, () => device);
        var local = new Target { Scheduler = scheduler, Order = new(), Executions = new() };
        // 901 fails, and memory is short when it does.
        local.Cost = r => (10, r.Id == v900 || r.Id == v901);
        local.Throw = r => r.Id == v902;
        local.OnStart = r => { if (r.Id == v901) device = 5; };
        local.OnEnd = _ => { };
        journal.Offer(0xDDDD, local);
        WaitUntil(() => journal.Replayed + journal.ReplayFailed + journal.ReplayTemporary >= journal.Loaded, 1500);
        device = 60;
        journal.Pump(); // the minute summary does this on the device
        WaitUntil(() => journal.Replayed + journal.ReplayFailed + journal.ReplayTemporary >= journal.Loaded, 3000);
        Thread.Sleep(50);
        WaitFile(JournalPath(name), 16);
        return journal;
    }
    var l2 = Launch();
    var l3 = Launch();
    var l4 = Launch();
    l4.NoteLate(0xDDDD, Variant(900), 70, false); // a draw creates it successfully
    WaitFile(JournalPath(name), 16);
    var l5 = Open(name);
    report["failure"] = new Dictionary<string, object>
    {
        ["launch2"] = new[] { l2.Loaded, l2.Replayed, l2.ReplayFailed, l2.ReplayTemporary },
        ["launch3"] = new[] { l3.Loaded, l3.Replayed, l3.ReplayFailed, l3.ReplayTemporary },
        ["launch4"] = new[] { l4.Loaded, l4.Replayed, l4.ReplayFailed, l4.ReplayTemporary },
        ["launch4LateAfterFailed"] = l4.LateAfterFailed, ["launch5Planned"] = l5.Loaded,
    };

    // Device memory at 5 %: nothing speculative starts (held), and a queued replay a draw demands still completes.
    device = 5;
    var s6 = Open(name, () => device);
    var target6 = new Target { Scheduler = scheduler, Order = new(), Executions = new() };
    s6.Offer(0xDDDD, target6);
    Thread.Sleep(150);
    int whileShort = target6.Executions.Values.Sum();
    int holds = s6.MemoryHolds;
    var gate = new ManualResetEventSlim();
    var blockers = Enumerable.Range(0, 4).Select(_ => scheduler.SchedulePipelineCompile(_ => gate.Wait(2000))).ToArray();
    device = 60;
    s6.Pump();
    WaitUntil(() => !target6.Queued.IsEmpty, 1000);
    device = 5;
    Task demanded = target6.Queued.Values.First();
    scheduler.PromotePipelineCompile(demanded);
    bool served = demanded.Wait(1500);
    gate.Set();
    Task.WaitAll(blockers);
    report["memory"] = new Dictionary<string, object>
    {
        ["executedWhileShort"] = whileShort, ["holds"] = holds, ["demandedServedWhileShort"] = served && demanded.Status == TaskStatus.RanToCompletion,
    };
    device = 60;
    scheduler.Dispose();
}

{
    // Promotion, taking and cancellation from several threads at once (200 rounds on the real scheduler): each queued compile
    // either runs once (promoted, or taken before the cancel) or is cancelled; its waiter always returns; a running compile
    // cannot be cancelled and keeps its resources to the end.
    var scheduler = NewScheduler();
    int ran = 0, cancelled = 0, inconsistent = 0, hung = 0, refusedWhileRunning = 0, completedWithResource = 0;
    for (int round = 0; round < 200; round++)
    {
        var gate = new ManualResetEventSlim();
        var blockers = Enumerable.Range(0, 4).Select(_ => scheduler.SchedulePipelineCompile(_ => gate.Wait(500))).ToArray();
        int runs = 0;
        Task item = scheduler.SchedulePipelineCompile(_ => Interlocked.Increment(ref runs));
        using var start = new Barrier(3);
        bool cancelResult = false;
        var promoter = Task.Run(() => { start.SignalAndWait(); scheduler.PromotePipelineCompile(item); });
        var canceller = Task.Run(() => { start.SignalAndWait(); cancelResult = scheduler.TryCancelPipelineCompile(item); });
        var waiter = Task.Run(() => { start.SignalAndWait(); try { item.Wait(3000); } catch (AggregateException) { } });
        bool joined = Task.WaitAll(new[] { promoter, canceller, waiter }, 5000);
        gate.Set();
        Task.WaitAll(blockers);
        try { item.Wait(3000); } catch (AggregateException) { }
        if (!joined || !item.IsCompleted) hung++;
        bool wasCancelled = item.IsFaulted && item.Exception.InnerException is ObjectDisposedException;
        if (runs == 1 && !wasCancelled) ran++;
        if (wasCancelled && runs == 0) cancelled++;
        if ((runs > 0 && wasCancelled) || runs > 1 || cancelResult != wasCancelled) inconsistent++;
    }
    for (int round = 0; round < 20; round++)
    {
        var started = new ManualResetEventSlim();
        byte[] resource = new byte[1024];
        bool alive = false;
        Task running = scheduler.SchedulePipelineCompile(_ => { started.Set(); Thread.Sleep(30); alive = resource.Length == 1024; }, highPriority: true);
        started.Wait(2000);
        if (!scheduler.TryCancelPipelineCompile(running)) refusedWhileRunning++;
        running.Wait(2000);
        if (alive && running.Status == TaskStatus.RanToCompletion) completedWithResource++;
    }
    report["race"] = new Dictionary<string, object>
    {
        ["rounds"] = 200, ["ranOnce"] = ran, ["cancelled"] = cancelled, ["inconsistent"] = inconsistent, ["hung"] = hung,
        ["runningRefusedCancel"] = refusedWhileRunning, ["runningCompleted"] = completedWithResource,
    };
    scheduler.Dispose();
}

{
    // Ageing: U is replayed and bound by a draw in every launch (NoteReplayUsed), N is replayed but never used; something
    // else is met late in each launch, so launches count. After 10 launches U is still planned, N has aged out.
    var scheduler = NewScheduler();
    string name = "refresh";
    var s1 = Open(name);
    s1.NoteLate(0x7777, Variant(1200), 90, false);
    s1.NoteLate(0x7777, Variant(1201), 90, false);
    WaitFile(JournalPath(name), 16);
    ulong used = PipelineVariantJournal.Checksum64(Variant(1200));
    int readyBeforeUse = 0;
    for (int s = 0; s < 10; s++)
    {
        var journal = Open(name);
        var target = new Target { Scheduler = scheduler, Order = new(), Executions = new() };
        journal.Offer(0x7777, target);
        int expected = journal.Session <= 1 + PipelineVariantJournal.RecentSessions ? 2 : 1; // N ages out from session 10
        WaitUntil(() => journal.Replayed >= expected, 2000);
        Thread.Sleep(30);
        if (target.Seen.TryGetValue(used, out PipelineVariantJournal.Record record)) journal.NoteReplayUsed(record);
        readyBeforeUse += journal.ReadyBeforeUse;
        journal.NoteLate(0x7778, Variant(1300 + s), 20, false);
        WaitFile(JournalPath(name), 16);
    }
    var last = Open(name);
    var planned = new Target { Scheduler = scheduler, Order = new(), Executions = new() };
    last.Offer(0x7777, planned);
    WaitUntil(() => last.Replayed >= 1, 2000);
    Thread.Sleep(100);
    report["refresh"] = new Dictionary<string, object>
    {
        ["readyBeforeUse"] = readyBeforeUse, ["session"] = last.Session,
        ["usedStillPlanned"] = planned.Seen.ContainsKey(used), ["unusedStillPlanned"] = planned.Seen.ContainsKey(PipelineVariantJournal.Checksum64(Variant(1201))),
    };
    scheduler.Dispose();
}

{
    // Costly replays (400 ms average): one in flight. Joined draws and new states are counted apart.
    var scheduler = NewScheduler();
    string name = "costly";
    var s1 = Open(name);
    for (int v = 0; v < 5; v++) s1.NoteLate(0xEEEE, Variant(950 + v), 400, false);
    WaitFile(JournalPath(name), 16 + 5 * 40);
    var target = new Target { Scheduler = scheduler, Order = new(), Executions = new(), Cost = _ => (400, false) };
    var s2 = Open(name);
    s2.Offer(0xEEEE, target);
    WaitUntil(() => s2.Replayed >= 1, 3000);
    lock (target) target.MaxInFlight = target.InFlight; // from here on: the replays average 400 ms
    WaitUntil(() => s2.Replayed == 5, 8000);
    s2.NoteLate(0xEEEF, Variant(960), 12, joined: true);
    s2.NoteLate(0xEEEF, Variant(961), 25, joined: false);
    report["costly"] = new Dictionary<string, object>
    {
        ["replayed"] = s2.Replayed, ["maxInFlightOnceCostly"] = target.MaxInFlight, ["joinedOther"] = s2.JoinedOther, ["joinedOtherMs"] = s2.JoinedOtherMs,
        ["new"] = s2.LateNew, ["summary"] = s2.Summary("test"),
    };
    scheduler.Dispose();
}

{
    // Per-session cap: 600 planned states of 1 ms replay 512.
    var scheduler = NewScheduler();
    string name = "cap";
    var s1 = Open(name);
    for (int v = 0; v < 600; v++) s1.NoteLate(0xF000UL + (ulong)(v % 50), Variant(2000 + v), 5, false);
    WaitFile(JournalPath(name), 16 + 600L * 40);
    var target = new Target { Scheduler = scheduler, Order = new(), Executions = new(), Cost = _ => (1, false) };
    var s2 = Open(name);
    for (int p = 0; p < 50; p++) s2.Offer(0xF000UL + (ulong)p, target);
    WaitUntil(() => s2.Replayed >= 512, 20000);
    Thread.Sleep(300);
    report["cap"] = new Dictionary<string, object> { ["planned"] = s2.Loaded, ["replayed"] = s2.Replayed, ["executed"] = target.Executions.Values.Sum() };
    scheduler.Dispose();
}

report["requireFailures"] = failures;
Directory.Delete(root, true);
Console.WriteLine(JsonSerializer.Serialize(report));

sealed class Target : PipelineVariantJournal.ITarget
{
    public Func<PipelineVariantJournal.Record, (int Ms, bool Fail)> Cost = _ => (20, false);
    public Func<PipelineVariantJournal.Record, bool> Throw = _ => false;
    public Action<PipelineVariantJournal.Record> OnStart = _ => { }, OnEnd = _ => { };
    public ConcurrentDictionary<ulong, PipelineVariantJournal.Record> Seen = new();
    public BackgroundCompilationScheduler Scheduler;
    public ConcurrentQueue<string> Order;
    public ConcurrentDictionary<string, int> Executions;
    public ConcurrentDictionary<ulong, Task> Queued = new();
    public int InFlight, MaxInFlight;
    public bool Closing;

    public Task<long> Schedule(PipelineVariantJournal.Record record)
    {
        if (Closing) return null;
        Seen[record.Id] = record;
        (int ms, bool fail) = Cost(record);
        long compileMs = -1;
        string name = $"{record.Program:X}/{record.Id:X}";
        Task compile = Scheduler.SchedulePipelineCompile(_ =>
        {
            int now = Interlocked.Increment(ref InFlight);
            lock (this) MaxInFlight = Math.Max(MaxInFlight, now);
            Executions.AddOrUpdate(name, 1, (_, c) => c + 1);
            Order.Enqueue(name);
            OnStart(record);
            Thread.Sleep(ms);
            OnEnd(record);
            Interlocked.Decrement(ref InFlight);
            if (Throw(record)) throw new InvalidOperationException("renderer failure while creating it");
            if (!fail) compileMs = ms;
        }, highPriority: false);
        Queued[record.Id] = compile;
        return compile.ContinueWith(t => { Queued.TryRemove(record.Id, out _); t.GetAwaiter().GetResult(); return compileMs; }, TaskScheduler.Default);
    }
}
