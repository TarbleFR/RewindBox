using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Ryujinx.Common;

// A bounded, caller-polled journal, independent of console redirection. Never
// retain key values, decrypted buffers, logger Data objects or register dumps.
public static partial class EmbeddedLaunchDiagnostics
{
    private static readonly object Gate = new();
    private static readonly Queue<(long Id, string Stage, string Status, int Code, string Detail)> Events = new();
    private static long Sequence;
    private static string JournalPath;
    private static string JournalFailure = "";
    [LibraryImport("libc", EntryPoint = "open", SetLastError = true, StringMarshalling = StringMarshalling.Utf8)]
    private static partial int OpenJournal(string path, int flags);
    [LibraryImport("libc", EntryPoint = "write", SetLastError = true)]
    private static unsafe partial nint WriteJournal(int descriptor, byte* record, nuint length);
    [LibraryImport("libc", EntryPoint = "close")]
    private static partial int CloseJournal(int descriptor);
    public static string Stage { get; private set; } = "nativeAot";
    public static string ErrorCode { get; private set; } = "";
    public static string ErrorDetail { get; private set; } = "";

    public static void ConfigureJournal(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path) ||
            Path.GetFileName(path) != "app.log") throw new ArgumentException("Invalid application journal path.");
        // Darwin's open mode is a variadic argument. Let the runtime create
        // the file with its platform ABI, then append via the two-argument call.
        using (var file = new FileStream(path, FileMode.OpenOrCreate, FileAccess.Write, FileShare.ReadWrite)) { }
        lock (Gate) { JournalPath = path; JournalFailure = ""; }
    }

    private static unsafe void Persist(long sequence, string stage, string status, int code, string detail)
    {
        if (JournalPath == null) return;
        try
        {
            using var memory = new MemoryStream();
            using (var json = new Utf8JsonWriter(memory))
            {
                json.WriteStartObject();
                json.WriteString("timestamp", DateTime.UtcNow.ToString("O"));
                json.WriteNumber("pid", Environment.ProcessId);
                json.WriteNumber("sequence", sequence);
                json.WriteString("stage", stage); json.WriteString("status", status);
                json.WriteNumber("nativeStatus", code); json.WriteString("diagnostic", detail);
                json.WriteEndObject();
            }
            var file = new FileInfo(JournalPath);
            if (file.Exists && file.Length >= 5 * 1024 * 1024) return;
            byte[] prefix = Encoding.UTF8.GetBytes("[MeloNX:core] ");
            byte[] record = new byte[prefix.Length + memory.Length + 1];
            prefix.CopyTo(record, 0);
            memory.GetBuffer().AsSpan(0, (int)memory.Length).CopyTo(record.AsSpan(prefix.Length));
            record[^1] = (byte)'\n';
            // Use a real O_APPEND write, not a seek-to-end/pwrite pair. Swift
            // and Dart may append to this file at the same time. The syscall
            // returns before control reaches the next native operation.
            bool darwin = OperatingSystem.IsIOS() || OperatingSystem.IsMacOS() || OperatingSystem.IsMacCatalyst();
            int descriptor = OpenJournal(JournalPath, 1 | (darwin ? 0x8 : 0x400));
            if (descriptor < 0) { JournalFailure = "open errno=" + Marshal.GetLastPInvokeError(); return; }
            try
            {
                nint count;
                fixed (byte* bytes = record)
                {
                    do { count = WriteJournal(descriptor, bytes, (nuint)record.Length); }
                    while (count < 0 && Marshal.GetLastPInvokeError() == 4); // EINTR
                }
                if (count != record.Length) JournalFailure = "write errno=" + Marshal.GetLastPInvokeError();
            }
            finally { CloseJournal(descriptor); }
        }
        catch (Exception error) { JournalFailure = Safe(error.GetType().Name + ": " + error.Message); }
    }

    public static string Safe(string value)
    {
        value ??= "";
        // Redact complete personal key/rights values, including exception text.
        value = Regex.Replace(value, @"(?i)\b[0-9a-f]{32,}\b", "[redacted]");
        value = Regex.Replace(value, @"(?im)^\s*[a-z0-9_]+\s*=\s*[^\r\n]+", "[redacted key entry]");
        return value.Length > 4096 ? value[..4096] : value;
    }

    public static void Begin()
    {
        lock (Gate) { ErrorCode = ""; ErrorDetail = ""; }
    }

    public static void Record(string stage, string status, int code = 0, string detail = "")
    {
        lock (Gate)
        {
            if (status == "begin") Stage = stage;
            string safeDetail = Safe(detail);
            Events.Enqueue((++Sequence, stage, status, code, safeDetail));
            while (Events.Count > 64) Events.Dequeue();
            Persist(Sequence, stage, status, code, safeDetail);
        }
    }

    public static string Classify(Exception error)
    {
        string text = error.Message ?? "";
        if (error.GetType().Name == "MissingKeyException") return "missingKey";
        if (text.Contains("HeaderKey", StringComparison.OrdinalIgnoreCase) ||
            text.Contains("decrypt", StringComparison.OrdinalIgnoreCase)) return "ncaDecryption";
        if (text.Contains("profileUnavailable", StringComparison.Ordinal)) return "profileUnavailable";
        if (error is FileNotFoundException) return Stage == "gpu" || Stage == "frameworks" ? "runtimeUnavailable" : "localGameRequired";
        return "nativeFailure";
    }

    public static void Fail(string stage, string code, Exception error, int status = 1)
    {
        lock (Gate)
        {
            Stage = stage; ErrorCode = code; ErrorDetail = Safe(error.ToString());
            Record(stage, "failed", status, ErrorDetail);
        }
    }

    // The snapshot is written manually: NativeAOT cannot assume reflection
    // metadata for anonymous objects or JsonSerializer's reflection fallback.
    public static byte[] Snapshot()
    {
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
                json.WriteEndArray(); json.WriteEndObject();
            }
            return memory.ToArray();
        }
    }
}
