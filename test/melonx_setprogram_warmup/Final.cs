// Doubles of melonx_setprogram_warmup_test.py for its third variant only, the final preparation (lot after IPA 747:
// adapt_compute_warmup_demand is in the preparation order). That variant compiles the REAL members of the final source:
// ShaderCollection's two constructors (the base one without its descriptor-layout part) and every member the control and
// candidate compile, its sibling lookup (TryGetOwnGraphicsPipeline, TakeSiblingGraphicsPipeline, LendGraphicsPipeline,
// ComputeCodeIdentity) with the real PipelineCodeIdentity, PipelineSiblings, PipelineLoans and PipelineSiblingsJournal,
// Shader, VulkanRenderer.CreateProgram, PipelineBase.SetProgram/CreatePipeline, and the final
// BackgroundCompilationScheduler.cs whole. Only what the final members call into the variant journal and the render stage
// counters is a double here: the journal (adapt_pipeline_variant_replay, adapt_variant_journal_room,
// adapt_queued_variant_record) records nothing and replays nothing (pipeline-variant-replay executes the real one);
// the stage counters are plain fields (submit-causes and pipeline-variant-replay execute the real RenderStageTimer).
using System;
using System.Threading;
using System.Threading.Tasks;

namespace Ryujinx.Common
{
    static class EmbeddedLaunchDiagnostics
    {
        public static void Record(string category, string name, string detail = null) { }
    }

    // Identity only (StableHash, the sibling code identity): a 64-bit FNV-1a in both halves.
    struct Hash128
    {
        public ulong Low, High;

        public static Hash128 ComputeHash(ReadOnlySpan<byte> data)
        {
            ulong hash = 0xCBF29CE484222325UL;
            foreach (byte value in data) hash = (hash ^ value) * 0x100000001B3UL;
            return new Hash128 { Low = hash, High = ~hash };
        }
    }
}

namespace Ryujinx.Graphics.Vulkan
{
    sealed class PipelineVariantJournal
    {
        internal enum State { Recorded, Planned, Scheduled, Built, Failed }
        internal sealed class Record { public ulong Program; public ulong Id; public byte[] Variant; public State Status; }
        internal interface ITarget { Task<long> Schedule(Record record); }
    }

    // A draw's framebuffer as QueueBackgroundGraphicsPipeline reads it (one colour attachment in slot 0).
    class FramebufferParams
    {
        public int[] AttachmentIndices { get; } = [0];
        public int ColorAttachmentsCount => 1;
    }

    static class RenderStageTimer
    {
        public static long AsyncSkips, AsyncQueuedSkips, UnavailablePipelines;
        // The stage clock, as the real one: the final CreatePipeline times a skippable draw's short wait with it.
        public static long Now() => System.Diagnostics.Stopwatch.GetTimestamp();
    }

    // The final ShaderCollection declares which descriptor sets hold buffer views (adapt_hogwarts_steady_render); it is
    // assigned in the descriptor-layout part of the constructor, which this fixture leaves out. The type only.
    class DescriptorSetUpdater
    {
        [Flags]
        internal enum DirtyFlags { None = 0 }
    }

    partial class PipelineCacheManager
    {
        // The final manager's per-thread wait for the main cache's load (adapt_queued_variant_record); none here.
        [ThreadStatic] internal static long WorkerLoadWaitTicks;
    }

    partial class PipelineBase
    {
        protected FramebufferParams FramebufferParams = new();
    }

    partial class ShaderCollection
    {
        // Calls into the journal, counted only.
        public static int LateNotes, QueuedNotes, BoundNotes, Offers;

        Task<long> PipelineVariantJournal.ITarget.Schedule(PipelineVariantJournal.Record record) => null;

        private Task OfferRecordedVariants()
        {
            Interlocked.Increment(ref Offers);
            return Task.CompletedTask;
        }

        private void CancelVariantReplays() { }

        internal void NoteLateVariant(ref PipelineState state, FramebufferParams framebuffer, TimeSpan elapsed, bool joined, ulong pipelineHandle) =>
            Interlocked.Increment(ref LateNotes);

        private void NoteQueuedVariant(ref PipelineState state, Auto<DisposablePipeline> pipeline, int[] colorSlots, long compileTicks) =>
            Interlocked.Increment(ref QueuedNotes);

        internal void NotePipelineBound(ulong pipelineHandle) => Interlocked.Increment(ref BoundNotes);
    }
}
