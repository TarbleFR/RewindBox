"""The texture use clock (GpuContext.TextureUseEpoch) counts seconds of play, not the host's uptime (all titles, iOS).

IPA 740 / Core da2525a1, Hogwarts Legacy (private journals, pid 5954): adapt_cold_texture_release ages the pool-only
textures on TextureUseEpoch, which CheckHostMemory set to Environment.TickCount64 / 1000. That clock runs on while the
app is in the background or paused (the render loop waits in WaitUntilResumed: no frame, no check), so at the first
check after a resume every texture is older by the whole pause. The launch journal has 4 pauses, about 14 s in all,
within 31 s (the video shows a resume). The session's stderr has 13 cold release passes (device 4 to 10 % available,
age 60 s), each with 0 cold texture and 0 released, 0.7 to 13.8 ms each, and 5 pool-only reports (0, 1 978, 7 978,
7 834 and 7 145 textures; 0, 64, 185, 199 and 200 MiB; 0 cold). Its last pass falls in the second the first pause
begins, and it ends about 1 s after the first of the four resumes, before the other three: no pass after a resume is
journaled. Bound on paper: the first pass after those pauses applied the 60 s age as about 46 s of play. The buffer
cache's cold trim (adapt_cold_buffer_trim) already counts seconds of play.

Change (GpuContext.cs, CheckHostMemory): each check adds the host time since the previous check, at most two check
intervals (2 000 ms), to a play time in milliseconds (_texturePlayMilliseconds); TextureUseEpoch is its whole seconds.
A check runs only 1 000 ms or more after the previous one, so each check still moves the epoch, by 1 or 2 (by 1 or
more before): one tick per check, as the fast path of adapt_array_sync_epochs assumes (it compares the epoch for
equality only). A late check counts its real delay; only a gap over 2 s counts 2 s: a pause, a background, or a GPU
thread without a frame for that long. Every reader keeps one unit, seconds of play: the stamps
(Texture.SynchronizeMemory, TexturePool.GetInternal), the age (ScanColdTextures, 60 to 480 s), the reload window and
its pruning (NoteColdReload, PruneColdReleases, 300 s), the 30 s measurement (MeasurePoolTextures) and the texture
arrays' tick test (TextureBindingsArrayCache, Texture.ContextUseEpoch). The 10 s pass interval, the device-short trim
and the reports stay on host milliseconds (now). No trim reads the texture stamps (TextureCache, AutoDeleteCache).

Scope: where host memory is tracked (iOS); elsewhere TextureUseEpoch stays 0 as before. Hygiene, not the grey-frame
fix: the release only drops textures whose data is in guest memory and re-creates them at the next fetch. Expected on
the device: nothing measurable (0 texture released in the 13 journaled passes); after a pause, the "Cold texture
release" and pool-only lines count textures unused for 60 s of play ("unused for 60 s" now reads as seconds of play).
Textures stay longer after a pause or a stall over 2 s; otherwise their age is the host time between checks, as before
(both clocks round to the second). Not measured on an iPhone. Applied after adapt_pool_slot_copy (end of ORDER); its
BASELINE is the Core bacdcacd preparation. Rollback: drop this adapter from prepare_embedded.py, ORDER and the DMA
plan's addedPreparationInputs, then refreeze. Fail closed on drift.
"""
import hashlib
from adapt_session import once

CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
BASELINE = {CONTEXT: '768d47acca7958fc801e6a7833a42711f9ef2e06000c5c46d76facc170eae7d3'}

FIELD_OLD = '''        private long _lastHostMemoryCheck;
        private long _lastDeviceShortTrim;
        private long _lastHostMemoryReport;
'''
FIELD_NEW = '''        private long _lastHostMemoryCheck;
        private long _lastDeviceShortTrim;
        private long _lastHostMemoryReport;
        // RewindBox (adapt_texture_play_clock): the play time behind TextureUseEpoch, in milliseconds. GPU thread only.
        private long _texturePlayMilliseconds;
'''

PLAY_OLD = '''            _lastHostMemoryCheck = now;

            int device = HostMemoryBudget.DeviceAvailablePercent;
'''
PLAY_NEW = '''            // RewindBox (adapt_texture_play_clock): of the host time since the last check, at most two intervals count
            // as play: a pause or a background (no frame, no check) ages no texture by more than that.
            _texturePlayMilliseconds += Math.Min(now - _lastHostMemoryCheck, 2 * HostMemoryCheckIntervalMs);
            _lastHostMemoryCheck = now;

            int device = HostMemoryBudget.DeviceAvailablePercent;
'''

EPOCH_OLD = '''            TextureUseEpoch = (int)(now / 1000);
'''
EPOCH_NEW = '''            TextureUseEpoch = (int)(_texturePlayMilliseconds / 1000);
'''

DOC_OLD = '''        /// Seconds clock (Environment.TickCount64 / 1000) set once a second on the GPU thread by CheckHostMemory; textures
        /// record it at each use (Texture.LastUseEpoch). It stays 0 where host memory is not tracked: nothing ages there.
'''
DOC_NEW = '''        /// Seconds of play (adapt_texture_play_clock: the host time between two checks, at most two intervals each),
        /// set once a second on the GPU thread by CheckHostMemory; textures record it at each use (Texture.LastUseEpoch).
        /// It stays 0 where host memory is not tracked: nothing ages there.
'''

# The epoch's own line first: its anchor is gone from the post-image, so once() refuses a second apply before any write
# (the field and play anchors stay inside their replacements).
PAIRS = ((EPOCH_OLD, EPOCH_NEW), (DOC_OLD, DOC_NEW), (PLAY_OLD, PLAY_NEW), (FIELD_OLD, FIELD_NEW))


def apply(source):
    path = source / CONTEXT
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for _, expected in digests:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, CONTEXT
    for old, new in PAIRS:
        once(path, old, new)
    return [path]
