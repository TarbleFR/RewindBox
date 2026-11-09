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
    long before = new FileInfo(JournalPath(name)).Length;
    scheduler.Dispose();
    WaitUntil(() => target.InFlight == 0, 3000);
    Thread.Sleep(200);
    int executed = target.Executions.Values.Sum();
    Thread.Sleep(200);
    report["close"] = new Dictionary<string, object>
    {
        ["planned"] = 40, ["executed"] = executed, ["executedAfterClose"] = target.Executions.Values.Sum() - executed,
        ["failedMarked"] = s2.ReplayFailed, ["fileGrew"] = new FileInfo(JournalPath(name)).Length != before,
    };
}

{
    // Failure: a state whose creation fails is marked failed, not replayed at the next launch; a draw creating it late
    // afterwards counts as "failed before". Device memory at 5 %: nothing is scheduled; at 60 %: replays resume.
    var scheduler = NewScheduler();
    string name = "failure";
    var s1 = Open(name);
    s1.NoteLate(0xDDDD, Variant(900), 70, false);
    s1.NoteLate(0xDDDD, Variant(901), 70, false);
    WaitFile(JournalPath(name), 16 + 2 * 40);
    ulong failing = PipelineVariantJournal.Checksum64(Variant(900));
    var target = new Target { Scheduler = scheduler, Order = new(), Executions = new(), Cost = r => (10, r.Id == failing) };
    var s2 = Open(name);
    s2.Offer(0xDDDD, target);
    WaitUntil(() => s2.Replayed + s2.ReplayFailed == 2, 3000);
    s2.NoteLate(0xDDDD, Variant(900), 70, false);
    Thread.Sleep(100);
    var s3 = Open(name);
    int device = 5;
    var s4 = Open(name, () => device);
    var target4 = new Target { Scheduler = scheduler, Order = new(), Executions = new() };
    s4.Offer(0xDDDD, target4);
    Thread.Sleep(150);
    int whileShort = target4.Executions.Values.Sum();
    device = 60;
    s4.Pump();
    WaitUntil(() => s4.Replayed == 1, 2000);
    report["failure"] = new Dictionary<string, object>
    {
        ["session2Replayed"] = s2.Replayed, ["session2Failed"] = s2.ReplayFailed, ["lateAfterFailed"] = s2.LateAfterFailed,
        ["session3Planned"] = s3.Loaded, ["deviceShortExecuted"] = whileShort, ["deviceBackReplayed"] = s4.Replayed,
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
        ["replayed"] = s2.Replayed, ["maxInFlightOnceCostly"] = target.MaxInFlight, ["joined"] = s2.Joined, ["joinedMs"] = s2.JoinedMs,
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
    public BackgroundCompilationScheduler Scheduler;
    public ConcurrentQueue<string> Order;
    public ConcurrentDictionary<string, int> Executions;
    public ConcurrentDictionary<ulong, Task> Queued = new();
    public int InFlight, MaxInFlight;
    public bool Closing;

    public Task<long> Schedule(PipelineVariantJournal.Record record)
    {
        if (Closing) return null;
        (int ms, bool fail) = Cost(record);
        long compileMs = -1;
        string name = $"{record.Program:X}/{record.Id:X}";
        Task compile = Scheduler.SchedulePipelineCompile(_ =>
        {
            int now = Interlocked.Increment(ref InFlight);
            lock (this) MaxInFlight = Math.Max(MaxInFlight, now);
            Executions.AddOrUpdate(name, 1, (_, c) => c + 1);
            Order.Enqueue(name);
            Thread.Sleep(ms);
            Interlocked.Decrement(ref InFlight);
            if (!fail) compileMs = ms;
        }, highPriority: false);
        Queued[record.Id] = compile;
        return compile.ContinueWith(t => { Queued.TryRemove(record.Id, out _); t.GetAwaiter().GetResult(); return compileMs; }, TaskScheduler.Default);
    }
}
