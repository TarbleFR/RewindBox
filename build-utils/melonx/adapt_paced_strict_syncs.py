"""Hogwarts Legacy: at most one submitting host sync and one voluntary submission per 4 ms (Core 745 candidate).

IPA 729 / Core 743, Hogwarts Legacy 1x (pid 58475), per 5 s window of 77-84 frames: 2 014-2 367 command buffers
(24-31 per frame). "submits by cause": strict sync 1 314-1 335, draw auto-flush 504-814, attachment auto-flush 110-137,
present 77-84, sync wait 0-2. "Host syncs created": strict 1 197-1 409, of which 3D syncpoint 913-1 041 and SetReference
213-276 (counter reports 71-92, which are forced). So two thirds of the command buffers exist because a guest syncpoint
increment or SetReference found a pending sync action and submitted at once, although only 0-2 syncs per window were
ever waited for before their command buffer was submitted. Each command buffer costs the render thread its submission
(0.15 ms), one reference pass and one barrier pass per bound texture array (288-364 ms per window) and the state it
binds again, and on a tile-based GPU each submission inside a render pass stores and reloads the attachments ("same
framebuffer again" 1 526-1 828 per window).

A strict host sync is a latency choice, not a correctness one: GpuContext.CreateHostSyncIfNeeded creates the sync at
the same place in the command stream either way; a strict one submits the open command buffer at once
(SyncManager.Create), the other is attached to it and SyncManager.Wait submits it on demand when a reader waits
before it was submitted (the path WaitForIdle and the DMA buffer read-back already use: 302-386 per window).

Change, set per session for Hogwarts Legacy only (GpuContext.PaceStrictHostSyncs, SubmitPacing.Paced; every other
title keeps the engine's behaviour, and both off give back the control's decisions):
- GpuContext.cs: a strict sync asked by ThreedClass.IncrementSyncpoint or GPFifoClass.SetReference without Force
  stays strict at most once per 4 ms of the GPU thread (StrictSyncPacer); the others are created not strict. Forced
  syncs (counter reports, syncpoints queued behind reports) and every other site are untouched. The existing
  "Host syncs created" line shows them under "not strict", by site.
- AutoFlushCounter.cs: the two voluntary submissions (attachment change after 1 ms, draw in fast flush mode after
  1.5 ms) wait 4 ms and 8 ms: otherwise they would replace the syncs removed, one for one.
4 ms: a command buffer costs the render thread about 0.34 ms (submits 295 ms + auto-flush 93 ms + array reference
passes about 300 ms, over 2 014), so one per 4 ms keeps that under a tenth of its time, and the GPU is never more than
4 ms of recording behind (8 ms inside one render pass), an eighth of a 33 ms frame.

Expected on the device (same save and route): command buffers per frame 24-31 -> 14 or fewer; "strict sync" under 40 %
of its count; "same framebuffer again" halved; texture array reference passes follow the command buffers. Refuted,
and the adapter removed, if "sync waits" exceeds 4 ms per frame or presented frames per second fall. Not measured on
an iPhone. Fail closed on drift: the files must be the Core 743 preparation plus adapt_nifm_network_watch.
"""
import hashlib
from adapt_session import once

GPU_CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
AUTO_FLUSH = 'src/Ryujinx.Graphics.Vulkan/AutoFlushCounter.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
BASELINE = {
    GPU_CONTEXT: '82e42e448addccaa8be3602de2d19e711eac822909cd06ae09da3cda709342e0',
    AUTO_FLUSH: '8ce14d4a0a7e8826f4ae0087da4edd993f92b4d5f70d88f528380d383457990f',
    LIBRARY: '2c16af07aafae49e30acd91e0aca2cce4cdaa1809c93af6ac7fbbd86ea47125e',
}

SYNC_OLD = '''                NoteHostSync(caller, strict); // RewindBox (adapt_submit_causes)
                Renderer.CreateSync(SyncNumber, strict);
'''
SYNC_NEW = '''                // RewindBox (adapt_paced_strict_syncs): Hogwarts policy. A guest syncpoint increment or SetReference submits
                // the open command buffer at most once per StrictSyncPacer.IntervalMs; in between the sync is created on it
                // and a reader that waits for it first has it submitted (SyncManager.Wait), as for every sync that is not
                // strict. A forced sync is never paced.
                if (strict && !force && _strictSyncPacer.Defer(caller, System.Diagnostics.Stopwatch.GetTimestamp(), System.Diagnostics.Stopwatch.Frequency))
                {
                    strict = false;
                }

                NoteHostSync(caller, strict); // RewindBox (adapt_submit_causes)
                Renderer.CreateSync(SyncNumber, strict);
'''

FIELD_OLD = '''        private Thread _gpuThread;
        private bool _pendingSync;
'''
FIELD_NEW = '''        private Thread _gpuThread;
        private bool _pendingSync;
        // RewindBox (adapt_paced_strict_syncs): the strict host syncs of guest syncpoint increments and SetReference submit
        // the open command buffer at most once per 4 ms of the GPU thread; the others are created on it and submitted with
        // it, or when a reader waits for one. Set per session from the launched title (Hogwarts Legacy only).
        public static bool PaceStrictHostSyncs { get; set; }
        private StrictSyncPacer _strictSyncPacer; // GPU thread only
'''

TAIL_OLD = '''                throw new AggregateException(errors);
            }
        }
    }
}
'''
TAIL_NEW = '''                throw new AggregateException(errors);
            }
        }
    }

    // RewindBox (adapt_paced_strict_syncs): which strict host syncs submit at once. With the policy on, the two guest sites
    // that ask for a strict sync at every syncpoint increment or reference (several per render pass in Hogwarts Legacy)
    // submit at most once per IntervalMs; any other caller, and every call with the policy off, is left strict.
    internal struct StrictSyncPacer
    {
        public const double IntervalMs = 4.0;

        private long _lastStrictTicks;
        private bool _any;

        /// <summary>True when this strict sync is to be created without submitting the open command buffer.</summary>
        public bool Defer(string caller, long nowTicks, long ticksPerSecond)
        {
            if (!GpuContext.PaceStrictHostSyncs || (caller != "IncrementSyncpoint" && caller != "SetReference"))
            {
                return false;
            }

            if (_any && nowTicks - _lastStrictTicks < (long)(ticksPerSecond * (IntervalMs / 1000.0)))
            {
                return true;
            }

            _any = true;
            _lastStrictTicks = nowTicks;

            return false;
        }
    }
}
'''

TIMER_OLD = '''        private readonly static long _drawFlushTimer = Stopwatch.Frequency / 666; // (1.5ms)
'''
TIMER_NEW = '''        private readonly static long _drawFlushTimer = Stopwatch.Frequency / 666; // (1.5ms)

        // RewindBox (adapt_paced_strict_syncs): with SubmitPacing.Paced, how often to flush on framebuffer change (4 ms)
        // and on draw in fast flush mode (8 ms): the strict syncs paced on the GPU side are not replaced one for one.
        private readonly static long _pacedFramebufferFlushTimer = Stopwatch.Frequency / 250;
        private readonly static long _pacedDrawFlushTimer = Stopwatch.Frequency / 125;
'''

DRAW_OLD = '''                long flushTimeout = _drawFlushTimer;
'''
DRAW_NEW = '''                long flushTimeout = SubmitPacing.Paced ? _pacedDrawFlushTimer : _drawFlushTimer; // adapt_paced_strict_syncs
'''

ATTACHMENT_OLD = '''            long flushTimeout = _framebufferFlushTimer;
'''
ATTACHMENT_NEW = '''            long flushTimeout = SubmitPacing.Paced ? _pacedFramebufferFlushTimer : _framebufferFlushTimer; // adapt_paced_strict_syncs
'''

CLASS_OLD = '''                Logger.Debug?.PrintMsg(LogClass.Gpu, $"Switched fast flush mode: ({_fastFlushMode})");
            }
        }
    }
}
'''
CLASS_NEW = '''                Logger.Debug?.PrintMsg(LogClass.Gpu, $"Switched fast flush mode: ({_fastFlushMode})");
            }
        }
    }

    /// <summary>
    /// RewindBox (adapt_paced_strict_syncs): the voluntary submissions (attachment change, draw in fast flush mode) wait
    /// 4 ms and 8 ms instead of 1 ms and 1.5 ms. On a tile-based GPU a submission inside a render pass stores and reloads
    /// its attachments. Set per session with GpuContext.PaceStrictHostSyncs (Hogwarts Legacy only).
    /// </summary>
    public static class SubmitPacing
    {
        public static bool Paced { get; set; }
    }
}
'''

LIBRARY_OLD = '''            Ryujinx.Graphics.Vulkan.MoltenVkPolicy.OrderEncoderTransitions = hogwarts;
'''
LIBRARY_NEW = '''            Ryujinx.Graphics.Vulkan.MoltenVkPolicy.OrderEncoderTransitions = hogwarts;
            // RewindBox (adapt_paced_strict_syncs): Hogwarts Legacy increments a syncpoint 11-13 times per frame and each
            // submitted the open command buffer: at most one such submission, and one voluntary one, per 4 ms.
            Ryujinx.Graphics.Gpu.GpuContext.PaceStrictHostSyncs = hogwarts;
            Ryujinx.Graphics.Vulkan.SubmitPacing.Paced = hogwarts;
'''

FILE_PAIRS = {
    GPU_CONTEXT: ((FIELD_OLD, FIELD_NEW), (SYNC_OLD, SYNC_NEW), (TAIL_OLD, TAIL_NEW)),
    AUTO_FLUSH: ((TIMER_OLD, TIMER_NEW), (DRAW_OLD, DRAW_NEW), (ATTACHMENT_OLD, ATTACHMENT_NEW), (CLASS_OLD, CLASS_NEW)),
    LIBRARY: ((LIBRARY_OLD, LIBRARY_NEW),),
}
PAIRS = tuple(pair for pairs in FILE_PAIRS.values() for pair in pairs)


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in FILE_PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
