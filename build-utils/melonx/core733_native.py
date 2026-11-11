"""Core 733 edits of two native RewindBox sources, as exact (old, new) pairs on the Core 731 files.

prepare_embedded.py copies native/melonx/EmbeddedLaunchDiagnostics.cs into src/Ryujinx.Common/ and EmbeddedRuntime.cs
into src/Ryujinx.Library/ as they are. Gates whose control is an earlier preparation reverse these pairs first (then the
earlier lots' own: core667_native, the journal's room at the start of a process) to recover the file they compare with,
and the diagnostics-snapshot-reuse gate checks that the pairs applied to the Core 731 files give this checkout's files.

- EmbeddedLaunchDiagnostics.cs: the snapshot's bytes are kept in one buffer and written again only when a new Sequence,
  the number of events or one of the four strings differs; SnapshotTo copies them to the caller's memory; Snapshot()
  still returns a new array (IPA 725, pid 51986: the host polls the snapshot every 300 ms from a utility-class thread;
  a collection its allocation triggered ran at that thread's priority and stopped the game 2.7 s).
- EmbeddedRuntime.cs: the neostation_melonx_diagnostics export copies through SnapshotTo instead of a managed copy.
"""
JOURNAL = 'src/Ryujinx.Common/EmbeddedLaunchDiagnostics.cs'
RUNTIME = 'src/Ryujinx.Library/EmbeddedRuntime.cs'
NATIVE = {JOURNAL: 'native/melonx/EmbeddedLaunchDiagnostics.cs', RUNTIME: 'native/melonx/EmbeddedRuntime.cs'}
# The two files as prepared for Core 731.
CORE731 = {JOURNAL: '803f5b6573ac58a58e9b2478a57a0a8a1d13bba859adfd140a9b02857ad45a7e',
           RUNTIME: 'd40bf48954289a009f57031ccabc650c402b88057e9dfae150942b3103f5315e'}

SNAPSHOT_OLD = '''    // The snapshot is written manually: NativeAOT cannot assume reflection
    // metadata for anonymous objects or JsonSerializer's reflection fallback.
    public static byte[] Snapshot()
    {
        try { Volatile.Read(ref PerformanceObserver)?.Invoke(); }
        catch { } // A diagnostic observer cannot alter the queried engine result.
        lock (Gate)
        {
            using var memory = new MemoryStream();
            using (var json = new Utf8JsonWriter(memory))
            {
                json.WriteStartObject();
                json.WriteString("stage", Stage); json.WriteString("errorCode", ErrorCode);
                json.WriteString("diagnostic", ErrorDetail);
                json.WriteString("journalError", JournalFailure);
                json.WriteStartArray("events");
                foreach (var item in Events)
                {
                    json.WriteStartObject(); json.WriteNumber("sequence", item.Id);
                    json.WriteString("stage", item.Stage); json.WriteString("status", item.Status);
                    json.WriteNumber("nativeStatus", item.Code); json.WriteString("diagnostic", item.Detail);
                    json.WriteEndObject();
                }
                json.WriteEndArray();
                void WritePerformance(string name, (long Id, long Generation, string Stage, string Status, int Code, string Detail, string Timestamp) value)
                {
                    json.WriteStartObject(name); json.WriteNumber("sequence", value.Id);
                    json.WriteNumber("generation", value.Generation);
                    json.WriteNumber("pid", Environment.ProcessId); json.WriteString("timestamp", value.Timestamp);
                    json.WriteString("stage", value.Stage); json.WriteString("status", value.Status);
                    json.WriteNumber("nativeStatus", value.Code); json.WriteString("diagnostic", value.Detail);
                    json.WriteEndObject();
                }
                if (PrecedingPerformance is { } preceding) WritePerformance("precedingPerformance", preceding);
                if (Performance is { } performance) WritePerformance("performance", performance);
                json.WriteEndObject();
            }
            return memory.ToArray();
        }
    }
}
'''
SNAPSHOT_NEW = '''    // The snapshot is written manually: NativeAOT cannot assume reflection
    // metadata for anonymous objects or JsonSerializer's reflection fallback.
    public static byte[] Snapshot()
    {
        try { Volatile.Read(ref PerformanceObserver)?.Invoke(); }
        catch { } // A diagnostic observer cannot alter the queried engine result.
        lock (Gate)
        {
            WriteSnapshot();
            return SnapshotBuffer.WrittenSpan.ToArray();
        }
    }

    // The host polls the snapshot every 300 ms for the whole session, from a utility-class thread. Written anew at
    // every poll (a stream grown to the size of the 64 events, a writer and a copy, most of it in the large object
    // heap once the ring holds long records), it made that thread one of the engine's allocators: in IPA 725
    // (pid 51986) a collection its allocation triggered ran at that thread's priority and stopped the game 2.7 s.
    // The bytes are kept instead: written again, into the same buffer, only when something they hold has changed
    // (every event and performance record takes a new Sequence; the number of events and the four strings are
    // compared), and copied to the host's memory without a managed copy.
    private static readonly System.Buffers.ArrayBufferWriter<byte> SnapshotBuffer = new(64 * 1024);
    private static Utf8JsonWriter SnapshotWriter;
    private static long SnapshotSequence = -1;
    private static int SnapshotEvents;
    private static string SnapshotStage, SnapshotErrorCode, SnapshotErrorDetail, SnapshotJournalFailure;
    private static long SnapshotsWritten, SnapshotsKept;

    /// <summary>Snapshots written, and polls answered with the kept bytes, since the process started.</summary>
    public static (long Written, long Kept) SnapshotCounts { get { lock (Gate) { return (SnapshotsWritten, SnapshotsKept); } } }

    /// <summary>
    /// Copies the snapshot and a terminating zero to <paramref name="output"/>. Returns 0, or minus the snapshot's
    /// length when <paramref name="capacity"/> does not exceed it or there is no output (nothing is copied then).
    /// </summary>
    public static unsafe int SnapshotTo(byte* output, int capacity)
    {
        try { Volatile.Read(ref PerformanceObserver)?.Invoke(); }
        catch { } // A diagnostic observer cannot alter the queried engine result.
        lock (Gate)
        {
            WriteSnapshot();
            ReadOnlySpan<byte> data = SnapshotBuffer.WrittenSpan;
            if (output == null || capacity <= data.Length) return -data.Length;
            data.CopyTo(new Span<byte>(output, capacity)); output[data.Length] = 0;
            return 0;
        }
    }

    // Under Gate: leaves the current snapshot in SnapshotBuffer.
    private static void WriteSnapshot()
    {
        long sequence = Sequence;
        string stage = Stage, errorCode = ErrorCode, errorDetail = ErrorDetail, journalFailure = JournalFailure;
        if (SnapshotWriter != null && SnapshotSequence == sequence && SnapshotEvents == Events.Count && SnapshotStage == stage &&
            SnapshotErrorCode == errorCode && SnapshotErrorDetail == errorDetail && SnapshotJournalFailure == journalFailure)
        {
            SnapshotsKept++;
            return;
        }
        // Not kept until written whole: a write that throws is started again by the next poll.
        SnapshotSequence = -1;
        SnapshotBuffer.ResetWrittenCount();
        if (SnapshotWriter == null) SnapshotWriter = new Utf8JsonWriter(SnapshotBuffer);
        else SnapshotWriter.Reset(SnapshotBuffer);
        Utf8JsonWriter json = SnapshotWriter;
        json.WriteStartObject();
        json.WriteString("stage", stage); json.WriteString("errorCode", errorCode);
        json.WriteString("diagnostic", errorDetail);
        json.WriteString("journalError", journalFailure);
        json.WriteStartArray("events");
        foreach (var item in Events)
        {
            json.WriteStartObject(); json.WriteNumber("sequence", item.Id);
            json.WriteString("stage", item.Stage); json.WriteString("status", item.Status);
            json.WriteNumber("nativeStatus", item.Code); json.WriteString("diagnostic", item.Detail);
            json.WriteEndObject();
        }
        json.WriteEndArray();
        if (PrecedingPerformance is { } preceding) WritePerformance(json, "precedingPerformance", preceding);
        if (Performance is { } performance) WritePerformance(json, "performance", performance);
        json.WriteEndObject();
        json.Flush();
        SnapshotSequence = sequence; SnapshotEvents = Events.Count; SnapshotStage = stage; SnapshotErrorCode = errorCode;
        SnapshotErrorDetail = errorDetail; SnapshotJournalFailure = journalFailure;
        SnapshotsWritten++;
    }

    private static void WritePerformance(Utf8JsonWriter json, string name,
        (long Id, long Generation, string Stage, string Status, int Code, string Detail, string Timestamp) value)
    {
        json.WriteStartObject(name); json.WriteNumber("sequence", value.Id);
        json.WriteNumber("generation", value.Generation);
        json.WriteNumber("pid", Environment.ProcessId); json.WriteString("timestamp", value.Timestamp);
        json.WriteString("stage", value.Stage); json.WriteString("status", value.Status);
        json.WriteNumber("nativeStatus", value.Code); json.WriteString("diagnostic", value.Detail);
        json.WriteEndObject();
    }
}
'''
EXPORT_OLD = '''        try
        {
            byte[] data = EmbeddedLaunchDiagnostics.Snapshot();
            if (output == null || capacity <= data.Length) return -data.Length;
            data.CopyTo(new Span<byte>(output, capacity)); output[data.Length] = 0;
            return 0;
        }
        catch { return -1; }
'''
EXPORT_NEW = '''        // Copied from the bytes the journal keeps while nothing changes (EmbeddedLaunchDiagnostics.SnapshotTo): the
        // host polls this every 300 ms, and the managed copy made here was an allocation of the snapshot's size each time.
        try { return EmbeddedLaunchDiagnostics.SnapshotTo(output, capacity); }
        catch { return -1; }
'''
EDITS = {JOURNAL: [(SNAPSHOT_OLD, SNAPSHOT_NEW)], RUNTIME: [(EXPORT_OLD, EXPORT_NEW)]}


def present(text, name):
    """Whether `text` holds the Core 733 edits of `name` (an earlier preparation's file does not)."""
    return all(text.count(new) == 1 for _, new in EDITS[name])


def apply(text, name):
    for old, new in EDITS[name]:
        assert text.count(old) == 1, (name, old[:80])
        text = text.replace(old, new, 1)
    return text


def reverse(text, name):
    for old, new in reversed(EDITS[name]):
        assert text.count(new) == 1, (name, new[:80])
        text = text.replace(new, old, 1)
    return text
