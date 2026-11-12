"""Each command buffer submission is counted by what called for it, and each host sync by the GPU-side site that created it
(diagnostics only, every title).

IPA 727, Hogwarts Legacy (Core 737, pid 56836, 12 Nov; private journals, aggregates only): in play the render thread submits
2 048-2 067 command buffers per 5 s window for 82-84 frames (about 25 per frame; Smash: fewer than 3), 316-373 ms of
submission per window, and the texture array reference passes (18 055-19 994 per window, 1.59-1.61 M references,
282-306 ms) and barrier passes run once per array per command buffer: their cost follows the command buffer count. What
calls for the submissions is not journaled: the draw auto-flushes are counted (889-897 per window), the presents too (84),
the rest (about 1 090) is not; CreateSync runs 1 277-1 990 times per window on the render thread, and only a strict sync
submits (SyncManager.Create), the GPU-side sites that ask for one being GPFifoClass (a syncpoint increment, SetReference),
ThreedClass (a syncpoint increment), GpuContext (counter reports, Hogwarts policy), DmaClass (a GPU read-back) and
TextureGroupHandle. Any change to the submission count waits for that split (no sync semantics change on a guess).

Change (Vulkan backend and GpuContext.cs, every title; counters and log text only):
- every caller of a submission (FlushAllCommands, FlushCommandsImpl) names its cause just before the call: strict sync,
  sync wait (a sync waited on before its command buffer was submitted: the interrupt flush), draw auto-flush, attachment
  auto-flush, query, disposed resources (the weight flush), buffer read, texture read, staging buffer full, helper shader,
  present; FlushCommandsImpl counts the submission under it and resets it to "other";
- SyncManager.Create counts the syncs that submit at once and those that wait for the command buffer; the auto-flush policy
  counts the frames it spent in its fast flush mode (the mode in which draws flush every 1.5 ms) and the sync wait time
  that decides the mode;
- the render thread's 5 s "Vulkan render stages" line ends with "; submits by cause: ...; syncs created ...; fast flush
  mode ... frames, sync waits ... ms" after its existing text, which is unchanged (tools/melonx/frame_report.py parses it);
- GpuContext.CreateHostSyncIfNeeded takes its caller's name ([CallerMemberName], every call site unchanged) and counts each
  host sync it creates by site, strict or not; about every 5 s the GPU thread logs "Host syncs created over N ms: strict
  T (GPFifo syncpoint a, 3D syncpoint b, SetReference c, counter reports d, queued syncpoints e, DMA read-back f, DMA buffer
  read-back g, texture unbind h, WaitForIdle i, other j); not strict ..." as a Gpu warning (the durable engine journal).
No submission, sync, flush decision, draw or pipeline changes: every edit adds a counter or text. Rollback: remove this
adapter. Fail closed on drift: the files must be the Core 741 preparation's.
"""
import hashlib
from adapt_session import once

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
BASE = VULKAN + 'PipelineBase.cs'
FULL = VULKAN + 'PipelineFull.cs'
SYNC = VULKAN + 'SyncManager.cs'
AUTO = VULKAN + 'AutoFlushCounter.cs'
BUFFER = VULKAN + 'BufferHolder.cs'
STAGING = VULKAN + 'StagingBuffer.cs'
VIEW = VULKAN + 'TextureView.cs'
HELPER = VULKAN + 'HelperShader.cs'
WINDOW = VULKAN + 'Window.cs'
CONTEXT = 'src/Ryujinx.Graphics.Gpu/GpuContext.cs'
BASELINE = {
    BASE: 'a801fc74c66fb54de5ffc1902069476b9ffcad0f025720e01c7af40820e250a4',
    FULL: '359e31758ce45482abd64688b74e38bb65a4f2997086f8d6b995247580381a83',
    SYNC: 'b55b9c3c1fb941198d0240172dc205d8c916c6d38be82649c9e703c1c79bd6b3',
    AUTO: 'd7c0ec0ce5014d76244a703d7645fcc6587d3bd94f0101532455f3aa63581a7d',
    BUFFER: '4de2cceb304550b192f2c37d89d84aea109012aadefddf2fe1527a5e942a778d',
    STAGING: '6701eadf10f1645afeb5a6c122b57282047cff978aaae346a81c87e1f403e08d',
    VIEW: 'a639dc480573123265307e260441a51f21e42a53131e2cb99af738707d0ec51d',
    HELPER: '127af8755f1146b7dfce42df84adcd61bd066d141bab4280687c534bcc9ada35',
    WINDOW: '89ca8a5dd885bd886f08f2d5093ad64222f0bc2b50c928a121799faaa0cbc87b',
    CONTEXT: '0a480f36de42cfda0a750fd93aafc17229b23e5de9ed58aa7a8517aefdf51253',
}
TAG = 'RewindBox (adapt_submit_causes)'


def cause(name, indent):
    return indent + 'RenderStageTimer.NextSubmitCause = RenderStageTimer.SubmitCause.' + name + '; // ' + TAG + '\n'


TIMER_OLD = '''        public static long SubmitTicks, Submits, QueueTicks;
'''
TIMER_NEW = '''        public static long SubmitTicks, Submits, QueueTicks;

        // RewindBox (adapt_submit_causes): what each submission was for (named by its caller just before the call), the
        // syncs created on the render thread (those that submit at once apart), and the frames the auto-flush policy spent
        // in its fast flush mode with the sync waits that decide it. Diagnostics only; the render thread updates them.
        public enum SubmitCause
        {
            Other, StrictSync, SyncWait, DrawAutoFlush, AttachmentAutoFlush, Query, DisposedWeight, BufferRead, TextureRead,
            StagingFull, Helper, Present, Count,
        }

        public static SubmitCause NextSubmitCause;
        private static readonly long[] _submitsByCause = new long[(int)SubmitCause.Count];
        public static long SubmittingSyncs, WaitingSyncs;
        private static long _fastFlushFrames, _flushModeFrames, _syncWaitTicks;

        public static void NoteSubmit()
        {
            _submitsByCause[(int)NextSubmitCause]++;
            NextSubmitCause = SubmitCause.Other;
        }

        public static void NoteFlushMode(bool fastFlushMode, long syncWaitTicks)
        {
            _flushModeFrames++;
            _fastFlushFrames += fastFlushMode ? 1 : 0;
            _syncWaitTicks += syncWaitTicks;
        }

        private static long Submitted(SubmitCause cause) => _submitsByCause[(int)cause];

        private static string SubmitCausesText()
        {
            string text = "; submits by cause: strict sync " + Submitted(SubmitCause.StrictSync) + ", sync wait " +
                Submitted(SubmitCause.SyncWait) + ", draw auto-flush " + Submitted(SubmitCause.DrawAutoFlush) +
                ", attachment auto-flush " + Submitted(SubmitCause.AttachmentAutoFlush) + ", query " + Submitted(SubmitCause.Query) +
                ", disposed resources " + Submitted(SubmitCause.DisposedWeight) + ", buffer read " + Submitted(SubmitCause.BufferRead) +
                ", texture read " + Submitted(SubmitCause.TextureRead) + ", staging buffer full " + Submitted(SubmitCause.StagingFull) +
                ", helper " + Submitted(SubmitCause.Helper) + ", present " + Submitted(SubmitCause.Present) + ", other " +
                Submitted(SubmitCause.Other) + "; syncs created submitting " + SubmittingSyncs + ", waiting for the command buffer " +
                WaitingSyncs + "; fast flush mode " + _fastFlushFrames + " of " + _flushModeFrames + " frames, sync waits " +
                Ms(_syncWaitTicks) + " ms";
            Array.Clear(_submitsByCause);
            SubmittingSyncs = WaitingSyncs = _fastFlushFrames = _flushModeFrames = _syncWaitTicks = 0;

            return text;
        }
'''
LOG_OLD = '''                "; not ready by cause: async skips " + AsyncSkips + ", unavailable pipelines " + UnavailablePipelines;
'''
LOG_NEW = '''                "; not ready by cause: async skips " + AsyncSkips + ", unavailable pipelines " + UnavailablePipelines +
                SubmitCausesText(); // RewindBox (adapt_submit_causes)
'''
DRAW_OLD = '''                long flushStart = RenderStageTimer.Now();
                Gd.FlushAllCommands();
'''
DRAW_NEW = '''                long flushStart = RenderStageTimer.Now();
''' + cause('DrawAutoFlush', '                ') + '''                Gd.FlushAllCommands();
'''

PENDING_QUERY_OLD = '''            if (AutoFlush.ShouldFlushQuery())
            {
                FlushCommandsImpl();
'''
PENDING_QUERY_NEW = '''            if (AutoFlush.ShouldFlushQuery())
            {
''' + cause('Query', '                ') + '''                FlushCommandsImpl();
'''
WEIGHT_OLD = '''                if (_byteWeight >= MinByteWeightForFlush)
                {
                    FlushCommandsImpl();
'''
WEIGHT_NEW = '''                if (_byteWeight >= MinByteWeightForFlush)
                {
''' + cause('DisposedWeight', '                    ') + '''                    FlushCommandsImpl();
'''
COPY_QUERY_OLD = '''            if (AutoFlush.RegisterPendingQuery())
            {
                FlushCommandsImpl();
'''
COPY_QUERY_NEW = '''            if (AutoFlush.RegisterPendingQuery())
            {
''' + cause('Query', '                ') + '''                FlushCommandsImpl();
'''
ATTACHMENT_OLD = '''            if (AutoFlush.ShouldFlushAttachmentChange(DrawCount))
            {
                FlushCommandsImpl();
'''
ATTACHMENT_NEW = '''            if (AutoFlush.ShouldFlushAttachmentChange(DrawCount))
            {
''' + cause('AttachmentAutoFlush', '                ') + '''                FlushCommandsImpl();
'''
SUBMIT_OLD = '''            RenderStageTimer.SubmitTicks += RenderStageTimer.Now() - start;
            RenderStageTimer.Submits++;
'''
SUBMIT_NEW = '''            RenderStageTimer.SubmitTicks += RenderStageTimer.Now() - start;
            RenderStageTimer.Submits++;
            RenderStageTimer.NoteSubmit(); // RewindBox (adapt_submit_causes): counted under its cause, then "other" again
'''

CREATE_OLD = '''            if (strict || _gd.InterruptAction == null)
            {
                _gd.FlushAllCommands();
                _gd.CommandBufferPool.AddWaitable(waitable);
            }
            else
            {
'''
CREATE_NEW = '''            if (strict || _gd.InterruptAction == null)
            {
                RenderStageTimer.SubmittingSyncs++; // RewindBox (adapt_submit_causes)
''' + cause('StrictSync', '                ') + '''                _gd.FlushAllCommands();
                _gd.CommandBufferPool.AddWaitable(waitable);
            }
            else
            {
                RenderStageTimer.WaitingSyncs++; // RewindBox (adapt_submit_causes)
'''
REQUEST_OLD = '''                if (handle.NeedsFlush(_flushId))
                {
                    _gd.FlushAllCommands();
'''
REQUEST_NEW = '''                if (handle.NeedsFlush(_flushId))
                {
''' + cause('SyncWait', '                    ') + '''                    _gd.FlushAllCommands();
'''

MODE_OLD = '''            _syncWaitHistory[_syncWaitHistoryIndex] = _gd.SyncManager.GetAndResetWaitTicks();
'''
MODE_NEW = '''            _syncWaitHistory[_syncWaitHistoryIndex] = _gd.SyncManager.GetAndResetWaitTicks();
            RenderStageTimer.NoteFlushMode(_fastFlushMode, _syncWaitHistory[_syncWaitHistoryIndex]); // RewindBox (adapt_submit_causes)
'''

BUFFER_OLD = '''            if (_gd.CommandBufferPool.OwnedByCurrentThread)
            {
                _gd.FlushAllCommands();

                result = resource.GetFlushBuffer().GetBufferData(_gd.CommandBufferPool, this, offset, size);
'''
BUFFER_NEW = '''            if (_gd.CommandBufferPool.OwnedByCurrentThread)
            {
''' + cause('BufferRead', '                ') + '''                _gd.FlushAllCommands();

                result = resource.GetFlushBuffer().GetBufferData(_gd.CommandBufferPool, this, offset, size);
'''
STAGING_OLD = '''                        if (isRender)
                        {
                            _gd.FlushAllCommands();
'''
STAGING_NEW = '''                        if (isRender)
                        {
''' + cause('StagingFull', '                            ') + '''                            _gd.FlushAllCommands();
'''
VIEW_OLD = '''                _gd.FlushAllCommands();

                return PinnedSpan<byte>.UnsafeFromSpan(GetData(_gd.CommandBufferPool, resources.GetFlushBuffer()));
'''
VIEW_NEW = cause('TextureRead', '                ') + VIEW_OLD
VIEW_LAYER_OLD = '''                _gd.FlushAllCommands();

                return PinnedSpan<byte>.UnsafeFromSpan(GetData(_gd.CommandBufferPool, resources.GetFlushBuffer(), layer, level));
'''
VIEW_LAYER_NEW = cause('TextureRead', '                ') + VIEW_LAYER_OLD
HELPER_BLIT_OLD = '''            bool clearAlpha = false)
        {
            gd.FlushAllCommands();
'''
HELPER_BLIT_NEW = '''            bool clearAlpha = false)
        {
''' + cause('Helper', '            ') + '''            gd.FlushAllCommands();
'''
HELPER_COLOR_OLD = '''            ComponentType type,
            Rectangle<int> scissor)
        {
            const int ClearColorBufferSize = 16;

            gd.FlushAllCommands();
'''
HELPER_COLOR_NEW = '''            ComponentType type,
            Rectangle<int> scissor)
        {
            const int ClearColorBufferSize = 16;

''' + cause('Helper', '            ') + '''            gd.FlushAllCommands();
'''
HELPER_FORMAT_OLD = '''            VkFormat dstFormat,
            Rectangle<int> scissor)
        {
            const int ClearColorBufferSize = 16;

            gd.FlushAllCommands();
'''
HELPER_FORMAT_NEW = '''            VkFormat dstFormat,
            Rectangle<int> scissor)
        {
            const int ClearColorBufferSize = 16;

''' + cause('Helper', '            ') + '''            gd.FlushAllCommands();
'''
PRESENT_OLD = '''            long acquired = RenderStageTimer.Now();

            _gd.FlushAllCommands();
'''
PRESENT_NEW = '''            long acquired = RenderStageTimer.Now();

''' + cause('Present', '            ') + '''            _gd.FlushAllCommands();
'''
CAPTURE_OLD = '''                        null);
                    _gd.FlushAllCommands();
                    cbs.GetFence().Wait();
'''
CAPTURE_NEW = '''                        null);
''' + cause('Present', '                    ') + '''                    _gd.FlushAllCommands();
                    cbs.GetFence().Wait();
'''

SIGNATURE_OLD = '''        internal void CreateHostSyncIfNeeded(HostSyncFlags flags)
'''
SIGNATURE_NEW = '''        internal void CreateHostSyncIfNeeded(HostSyncFlags flags, [System.Runtime.CompilerServices.CallerMemberName] string caller = "")
'''
CONTEXT_MEMBERS_OLD = '''        /// <summary>
        /// Creates a host sync object if there are any pending sync actions. The actions will then be called.
'''
CONTEXT_MEMBERS_NEW = '''        // RewindBox (adapt_submit_causes): host syncs created per GPU-side site over about 5 s, the strict ones (the render
        // thread submits its command buffer for each) apart; the site is the calling method. GPU thread; diagnostics only.
        private static readonly string[] HostSyncSiteNames =
        {
            "GPFifo syncpoint", "3D syncpoint", "SetReference", "counter reports", "queued syncpoints", "DMA read-back",
            "DMA buffer read-back", "texture unbind", "WaitForIdle", "other",
        };
        private readonly long[] _hostSyncsStrict = new long[10];
        private readonly long[] _hostSyncsRelaxed = new long[10];
        private long _hostSyncWindowStart;

        internal static int HostSyncSite(string caller) => caller switch
        {
            "Syncpointb" => 0,
            "IncrementSyncpoint" => 1,
            "SetReference" => 2,
            "FlushCounterReports" => 3,
            "QueueSyncpointBehindReports" => 4,
            "TryReadBackGpuRegion" => 5,
            "TryReadBackIntoBuffer" => 6,
            "SignalModifying" => 7,
            "CreatePendingSyncs" => 8,
            _ => 9,
        };

        private void NoteHostSync(string caller, bool strict)
        {
            (strict ? _hostSyncsStrict : _hostSyncsRelaxed)[HostSyncSite(caller)]++;
            long now = System.Diagnostics.Stopwatch.GetTimestamp();

            if (_hostSyncWindowStart == 0)
            {
                _hostSyncWindowStart = now;

                return;
            }

            if (now - _hostSyncWindowStart < System.Diagnostics.Stopwatch.Frequency * 5)
            {
                return;
            }

            System.Text.StringBuilder text = new("Host syncs created over ");
            text.Append((now - _hostSyncWindowStart) * 1000 / System.Diagnostics.Stopwatch.Frequency).Append(" ms: strict");
            AppendHostSyncs(text, _hostSyncsStrict);
            text.Append("; not strict");
            AppendHostSyncs(text, _hostSyncsRelaxed);
            text.Append(" (adapt_submit_causes)");
            Array.Clear(_hostSyncsStrict);
            Array.Clear(_hostSyncsRelaxed);
            _hostSyncWindowStart = now;
            Logger.Warning?.Print(LogClass.Gpu, text.ToString());
        }

        private static void AppendHostSyncs(System.Text.StringBuilder text, long[] counts)
        {
            long total = 0;

            foreach (long count in counts)
            {
                total += count;
            }

            text.Append(' ').Append(total).Append(" (");

            for (int site = 0; site < counts.Length; site++)
            {
                text.Append(site == 0 ? "" : ", ").Append(HostSyncSiteNames[site]).Append(' ').Append(counts[site]);
            }

            text.Append(')');
        }

        /// <summary>
        /// Creates a host sync object if there are any pending sync actions. The actions will then be called.
'''
NOTE_OLD = '''                Renderer.CreateSync(SyncNumber, strict);
'''
NOTE_NEW = '''                NoteHostSync(caller, strict); // RewindBox (adapt_submit_causes)
                Renderer.CreateSync(SyncNumber, strict);
'''

PAIRS = [
    (BASE, TIMER_OLD, TIMER_NEW), (BASE, LOG_OLD, LOG_NEW), (BASE, DRAW_OLD, DRAW_NEW),
    (FULL, PENDING_QUERY_OLD, PENDING_QUERY_NEW), (FULL, WEIGHT_OLD, WEIGHT_NEW), (FULL, COPY_QUERY_OLD, COPY_QUERY_NEW),
    (FULL, ATTACHMENT_OLD, ATTACHMENT_NEW), (FULL, SUBMIT_OLD, SUBMIT_NEW),
    (SYNC, CREATE_OLD, CREATE_NEW), (SYNC, REQUEST_OLD, REQUEST_NEW),
    (AUTO, MODE_OLD, MODE_NEW),
    (BUFFER, BUFFER_OLD, BUFFER_NEW), (STAGING, STAGING_OLD, STAGING_NEW),
    (VIEW, VIEW_OLD, VIEW_NEW), (VIEW, VIEW_LAYER_OLD, VIEW_LAYER_NEW),
    (HELPER, HELPER_BLIT_OLD, HELPER_BLIT_NEW), (HELPER, HELPER_COLOR_OLD, HELPER_COLOR_NEW),
    (HELPER, HELPER_FORMAT_OLD, HELPER_FORMAT_NEW),
    (WINDOW, PRESENT_OLD, PRESENT_NEW), (WINDOW, CAPTURE_OLD, CAPTURE_NEW),
    (CONTEXT, SIGNATURE_OLD, SIGNATURE_NEW), (CONTEXT, CONTEXT_MEMBERS_OLD, CONTEXT_MEMBERS_NEW), (CONTEXT, NOTE_OLD, NOTE_NEW),
]
# The caller method names HostSyncSite maps, each the method that holds a CreateHostSyncIfNeeded call.
SITES = {
    'Syncpointb': 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs',
    'IncrementSyncpoint': 'src/Ryujinx.Graphics.Gpu/Engine/Threed/ThreedClass.cs',
    'SetReference': 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs',
    'FlushCounterReports': CONTEXT,
    'QueueSyncpointBehindReports': CONTEXT,
    'TryReadBackGpuRegion': 'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs',
    'TryReadBackIntoBuffer': 'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs',
    'SignalModifying': 'src/Ryujinx.Graphics.Gpu/Image/TextureGroupHandle.cs',
    'CreatePendingSyncs': 'src/Ryujinx.Graphics.Gpu/Engine/GPFifo/GPFifoClass.cs',
}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
