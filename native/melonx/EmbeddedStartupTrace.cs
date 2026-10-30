using System;
using System.Diagnostics;
using System.Threading;

namespace Ryujinx.Common;

// Startup scopes only: no per-frame tracing, cache edits or timing-dependent
// recovery. A scope end is not a successful renderer/session result.
public sealed class EmbeddedStartupTrace : IDisposable
{
    private readonly string _stage;
    private readonly long _begin;
    private int _ended;

    public EmbeddedStartupTrace(string stage)
    {
        _stage = stage;
        _begin = Stopwatch.GetTimestamp();
        Record("scopeBegin", "");
    }

    private void Record(string status, string detail)
    {
        try { EmbeddedLaunchDiagnostics.Record("gpuStartup", status, detail: _stage + detail); }
        catch { } // A diagnostic failure must never replace a renderer error.
    }

    public void Dispose()
    {
        if (Interlocked.Exchange(ref _ended, 1) != 0) return;
        double ms = Stopwatch.GetElapsedTime(_begin).TotalMilliseconds;
        Record("scopeEnd", FormattableString.Invariant($"; elapsedMs={ms:F3}"));
    }
}
