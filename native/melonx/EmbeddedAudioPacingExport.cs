using System;
using System.Runtime.InteropServices;
using Ryujinx.Common;

namespace Ryujinx.Library;

partial class Library
{
    // Polled once a second by the host's performance journal during a session.
    // Process-wide cumulative counters (EmbeddedAudioPacing), no generation gate.
    // 0 ok, 1 bad arguments, 3 exception.
    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_audio_pacing")]
    public static unsafe int EmbeddedAudioPacingSnapshot(long* values, int count)
    {
        if (values == null || count != EmbeddedAudioPacing.Count) return 1;
        try
        {
            EmbeddedAudioPacing.Snapshot(new Span<long>(values, count));
            return 0;
        }
        catch { return 3; }
    }
}
