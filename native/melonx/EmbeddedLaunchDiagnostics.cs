using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace Ryujinx.Common;

// A bounded, caller-polled journal, independent of console redirection. Never
// retain key values, decrypted buffers, logger Data objects or register dumps.
public static class EmbeddedLaunchDiagnostics
{
    private static readonly object Gate = new();
    private static readonly Queue<(long Id, string Stage, string Status, int Code, string Detail)> Events = new();
    private static long Sequence;
    public static string Stage { get; private set; } = "nativeAot";
    public static string ErrorCode { get; private set; } = "";
    public static string ErrorDetail { get; private set; } = "";

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
            Events.Enqueue((++Sequence, stage, status, code, Safe(detail)));
            while (Events.Count > 64) Events.Dequeue();
        }
    }

    public static string Classify(Exception error)
    {
        string text = error.Message ?? "";
        if (error.GetType().Name == "MissingKeyException") return "missingKey";
        if (text.Contains("HeaderKey", StringComparison.OrdinalIgnoreCase) ||
            text.Contains("decrypt", StringComparison.OrdinalIgnoreCase)) return "ncaDecryption";
        if (text.Contains("profileUnavailable", StringComparison.Ordinal)) return "profileUnavailable";
        if (error is FileNotFoundException) return "localGameRequired";
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
