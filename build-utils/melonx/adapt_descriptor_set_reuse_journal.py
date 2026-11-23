"""Measure, without changing anything, how many descriptor set writes a reuse of the sets already written would spare.

IPA 822, 23 November 2026 (private journals; counts and durations only), Hogwarts Legacy, one window of 5 375.5 ms and
85 frames: draw prepare 145 191 calls, descriptors 872.6 ms; compute prepare 5 476 calls, descriptors 290.3 ms (5 306
calls of programs with at most 32 bindings in sets 0 to 3, 288.6 ms, 53 us each); descriptor sets written 133 881 /
38 671 / 109 726 / 7 809 (uniform, storage, texture, image; 5 959 778 descriptors); texture arrays: reference passes
28 027 (223.1 ms), write time 45.9 ms; 1 241 command buffers. A dirty set is always a new set written whole and bound;
some are dirty without any change of what they hold (a program with another layout, each compute/graphics switch, a
bound texture array's element change, a buffer texture program set again, an empty assignment). How many, the journals
do not say, nor where a compute update's 53 us go: a reuse of those sets was measured on the host only, on a modelled
stream (6.8 % of the sets), which is not enough to change what the engine binds.

Change, DescriptorSetUpdater only, measurement only, for the main pipeline (not the helper shaders' or effects'):
- In one command buffer of eight (ReuseSampleEvery; each start counts: a new command buffer, the restore after a helper
  shader), each template write of sets 0 to 3 without an array is resolved into a scratch laid out as the template's
  data, then copied into the template data: the same bytes, written by the same call. Its bytes are compared with those
  of the set bound at that (bind point, set index) and of the last four sets this command buffer wrote for it (same
  template, so the same program and set layout; a 64-bit summary first), as a reuse of the set would compare them; the
  sets that would have been kept bound or bound again, and their descriptors, are counted. So are the array sets bound
  again where that same set is bound. Bound sets are followed per bind point with the pipeline layout of the last bind
  there (a bind with another layout forgets them); a new command buffer, CopyFrom and an update by another pipeline's
  updater forget everything. Nothing found is used: the sets taken, written and bound, the resources referenced and the
  order of every call are the control's.
- Timed: every compute update, sets 0-3 split into resolving and writing and binding, then the array sets; the draw
  updates of the sampled command buffers, sets 0-3 and array sets as wholes (TextureArray's reference passes and writes
  are in the array part).
- Journal, through the engine's Logger (a warning: also the core journal's engineWarning record, through
  EmbeddedLaunchDiagnostics.Safe), every 5 s of the main pipeline's updates, the line starting with "Vulkan descriptor
  set reuse measured (not applied) over".

Not changed: anything the GPU reads; layouts, templates, pipeline cache keys. Not measured on an iPhone. Fail closed on
drift: the file must be the 152-adapter preparation's (prep827).
"""
import hashlib
from adapt_session import once

UPDATER = 'src/Ryujinx.Graphics.Vulkan/DescriptorSetUpdater.cs'
BASELINE = {
    UPDATER: 'bc6a4355e79898d66b622cee6a0621c789341dd89f05a18873a6697af552ff94',
}
TAG = 'RewindBox (adapt_descriptor_set_reuse_journal)'
MEMBERS_BEGIN = '        // RewindBox (adapt_descriptor_set_reuse_journal), members: begin.\n'
MEMBERS_END = '        // RewindBox (adapt_descriptor_set_reuse_journal), members: end.\n'
JOURNAL_BEGIN = '    // RewindBox (adapt_descriptor_set_reuse_journal), journal: begin.\n'
JOURNAL_END = '    // RewindBox (adapt_descriptor_set_reuse_journal), journal: end.\n'

MEMBERS = MEMBERS_BEGIN + '''        // Measurement only, for the main pipeline: in one command buffer start of ReuseSampleEvery, each template write of
        // sets 0 to 3 without an array is resolved into a scratch laid out as the template's data, copied into the template
        // data (the same bytes, the same write), and compared with the set bound at that (bind point, set index) and with the
        // last four sets the same command buffer wrote for it, as a reuse of the set would compare them. The matches are
        // counted for the journal, never used: what the updater takes, writes, binds and references, and in what order, is
        // the control's. Bound sets are followed per bind point with the layout of the last bind there; a new command
        // buffer, CopyFrom and an update by another pipeline's updater forget everything.
        internal static int ReuseSampleEvery = 8;
        private const int ReuseEntries = 4;
        private const int ReuseSlots = 2 * PipelineBase.DescriptorSetLayouts;

        private sealed class WrittenSet
        {
            public DescriptorSetTemplate Template;
            public byte[] Bytes = [];
            public int Length;
            public ulong Fingerprint;
            public long Epoch = -1;
            public int Generation;
        }

        private readonly WrittenSet[] _writtenSets = new WrittenSet[ReuseSlots * ReuseEntries];
        private readonly int[] _writtenNext = new int[ReuseSlots];
        private readonly WrittenSet[] _boundSets = new WrittenSet[ReuseSlots];
        private readonly int[] _boundGenerations = new int[ReuseSlots];
        private readonly ulong[][] _boundArraySets = new ulong[2][];
        private readonly PipelineLayout[] _boundLayouts = new PipelineLayout[2];
        private byte[] _reusePending = new byte[1024];
        private ulong _reuseFingerprint;
        private WrittenSet _reuseMatch;
        private long _reuseEpoch;
        private nint _reuseCommandBuffer;
        private long _reuseForeignUpdates;
        private bool _reuseStale = true, _reuseSampled, _reuseTimed, _reuseSetsTimed;

        // The main pipeline's updater (Initialize(isMainPipeline) gives it the hazard list).
        private bool ReuseSets => FeedbackLoopHazards != null;

        private static int ReuseSlot(PipelineBindPoint pbp, int setIndex)
        {
            return (pbp == PipelineBindPoint.Compute ? PipelineBase.DescriptorSetLayouts : 0) + setIndex;
        }

        private void ResetReuse()
        {
            _reuseEpoch++;
            _reuseSampled = ReuseSampleEvery > 0 && _reuseEpoch % ReuseSampleEvery == 0;
            DescriptorReuseJournal.Starts++;
            DescriptorReuseJournal.SampledStarts += _reuseSampled ? 1 : 0;
            Array.Clear(_boundSets);
            Array.Clear(_boundLayouts);
            _boundArraySets[0]?.AsSpan().Clear();
            _boundArraySets[1]?.AsSpan().Clear();
            _reuseMatch = null;

            foreach (WrittenSet entry in _writtenSets)
            {
                if (entry != null)
                {
                    entry.Template = null;
                }
            }
        }

        private long BeginReuse(CommandBufferScoped cbs, PipelineBindPoint pbp)
        {
            if (!ReuseSets)
            {
                // Another pipeline's updater writes and binds: the main pipeline's updater forgets what it followed.
                System.Threading.Interlocked.Increment(ref DescriptorReuseJournal.ForeignUpdates);
                _reuseTimed = _reuseSetsTimed = false;

                return 0;
            }

            long foreign = System.Threading.Volatile.Read(ref DescriptorReuseJournal.ForeignUpdates);

            if (_reuseStale || cbs.CommandBuffer.Handle != _reuseCommandBuffer || foreign != _reuseForeignUpdates)
            {
                ResetReuse();
                _reuseStale = false;
                _reuseCommandBuffer = cbs.CommandBuffer.Handle;
                _reuseForeignUpdates = foreign;
            }

            DescriptorReuseJournal.LogIfDue();
            // Timed: every compute update, set by set; the draw updates of a sampled command buffer, as a whole.
            _reuseSetsTimed = pbp == PipelineBindPoint.Compute;
            _reuseTimed = _reuseSampled || _reuseSetsTimed;

            return _reuseTimed ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;
        }

        private void EndReuse(long start, long arrayStart, PipelineBindPoint pbp)
        {
            if (start != 0)
            {
                int point = pbp == PipelineBindPoint.Compute ? 1 : 0;
                DescriptorReuseJournal.TimedUpdates[point]++;
                DescriptorReuseJournal.SetTicks[point] += arrayStart - start;
                DescriptorReuseJournal.ArrayTicks[point] += System.Diagnostics.Stopwatch.GetTimestamp() - arrayStart;
            }

            _reuseTimed = _reuseSetsTimed = false;
        }

        // A bind at this bind point, in a sampled command buffer: with another pipeline layout than the last bind there,
        // what was bound there is forgotten (it may be disturbed); then the set bound at this index is recorded.
        private void NoteBind(PipelineBindPoint pbp, int setIndex, PipelineLayout layout, WrittenSet entry = null, ulong arraySet = 0)
        {
            if (!_reuseSampled)
            {
                return;
            }

            int point = pbp == PipelineBindPoint.Compute ? 1 : 0;

            if (_boundLayouts[point].Handle != layout.Handle)
            {
                _boundLayouts[point] = layout;
                Array.Clear(_boundSets, point * PipelineBase.DescriptorSetLayouts, PipelineBase.DescriptorSetLayouts);
                _boundArraySets[point]?.AsSpan().Clear();
            }

            if (setIndex < PipelineBase.DescriptorSetLayouts)
            {
                int slot = ReuseSlot(pbp, setIndex);
                _boundSets[slot] = entry;
                _boundGenerations[slot] = entry?.Generation ?? 0;
            }
            else
            {
                int index = setIndex - PipelineBase.DescriptorSetLayouts;
                ref ulong[] arraySets = ref _boundArraySets[point];

                if (arraySets == null || arraySets.Length <= index)
                {
                    Array.Resize(ref arraySets, index + 4);
                }

                arraySets[index] = arraySet;
            }
        }

        private static bool HasArraySegment(ResourceBindingSegment[] segments)
        {
            foreach (ResourceBindingSegment segment in segments)
            {
                if (segment.IsArray)
                {
                    return true;
                }
            }

            return false;
        }

        private DescriptorSetTemplateWriter BeginMeasured(DescriptorSetTemplate template)
        {
            if (_reusePending.Length < template.Size)
            {
                _reusePending = new byte[(template.Size + 1023) & ~1023];
            }

            return new DescriptorSetTemplateWriter(_reusePending.AsSpan(0, template.Size));
        }

        // A 64-bit summary of the template data: only a set whose summary matches is compared byte for byte.
        private static ulong Fingerprint(ReadOnlySpan<byte> data)
        {
            ReadOnlySpan<ulong> words = MemoryMarshal.Cast<byte, ulong>(data);
            ulong a = (ulong)data.Length, b = 0, c = 0, d = 0;
            int i = 0;

            for (; i + 4 <= words.Length; i += 4)
            {
                a = System.Numerics.BitOperations.RotateLeft(a, 9) ^ words[i];
                b = System.Numerics.BitOperations.RotateLeft(b, 9) ^ words[i + 1];
                c = System.Numerics.BitOperations.RotateLeft(c, 9) ^ words[i + 2];
                d = System.Numerics.BitOperations.RotateLeft(d, 9) ^ words[i + 3];
            }

            for (; i < words.Length; i++)
            {
                a = System.Numerics.BitOperations.RotateLeft(a, 9) ^ words[i];
            }

            for (int j = words.Length * sizeof(ulong); j < data.Length; j++)
            {
                b = System.Numerics.BitOperations.RotateLeft(b, 9) ^ data[j];
            }

            return a ^ System.Numerics.BitOperations.RotateLeft(b, 17) ^ System.Numerics.BitOperations.RotateLeft(c, 33) ^
                System.Numerics.BitOperations.RotateLeft(d, 49);
        }

        // Would the set bound at this (bind point, set index), or one this command buffer wrote for it, have held these
        // descriptors? Counted; the write goes on as before.
        private void MeasureReuse(DescriptorSetTemplate template, ResourceBindingSegment[] segments, int setIndex, PipelineBindPoint pbp)
        {
            ReadOnlySpan<byte> pending = new(_reusePending, 0, template.Size);
            ulong fingerprint = _reuseFingerprint = Fingerprint(pending);
            int point = pbp == PipelineBindPoint.Compute ? 1 : 0;
            int slot = ReuseSlot(pbp, setIndex);
            WrittenSet bound = _boundSets[slot];
            _reuseMatch = null;

            if (bound != null && bound.Fingerprint == fingerprint && bound.Generation == _boundGenerations[slot] &&
                bound.Epoch == _reuseEpoch && ReferenceEquals(bound.Template, template) &&
                _boundLayouts[point].Handle == _program.PipelineLayout.Handle &&
                pending.SequenceEqual(new ReadOnlySpan<byte>(bound.Bytes, 0, bound.Length)))
            {
                DescriptorReuseJournal.Note(DescriptorReuseJournal.WouldKeep, setIndex, segments);
                _reuseMatch = bound;

                return;
            }

            for (int i = 0; i < ReuseEntries; i++)
            {
                WrittenSet entry = _writtenSets[slot * ReuseEntries + i];

                if (entry != null && entry.Fingerprint == fingerprint && entry.Epoch == _reuseEpoch &&
                    ReferenceEquals(entry.Template, template) && pending.SequenceEqual(new ReadOnlySpan<byte>(entry.Bytes, 0, entry.Length)))
                {
                    DescriptorReuseJournal.Note(DescriptorReuseJournal.WouldBindAgain, setIndex, segments);
                    _reuseMatch = entry;

                    return;
                }
            }
        }

        // A set written and bound by the template path, in a sampled command buffer: followed as a reuse would follow it
        // (a matching set as the one bound here, otherwise a record of these bytes; the scratch becomes the record's).
        private void NoteSetWritten(PipelineBindPoint pbp, int setIndex, DescriptorSetTemplate template, ResourceBindingSegment[] segments, bool measured)
        {
            if (!_reuseSampled)
            {
                return;
            }

            DescriptorReuseJournal.Written[setIndex]++;

            foreach (ResourceBindingSegment segment in segments)
            {
                DescriptorReuseJournal.DescriptorsWritten += segment.Count;
            }

            WrittenSet entry = null;

            if (measured && _reuseMatch != null)
            {
                entry = _reuseMatch;
                _reuseMatch = null;
            }
            else if (measured)
            {
                int slot = ReuseSlot(pbp, setIndex);
                int index = slot * ReuseEntries + _writtenNext[slot];
                _writtenNext[slot] = (_writtenNext[slot] + 1) % ReuseEntries;

                entry = _writtenSets[index] ??= new WrittenSet();
                entry.Generation++;
                entry.Template = template;
                entry.Epoch = _reuseEpoch;
                (entry.Bytes, _reusePending) = (_reusePending, entry.Bytes);
                entry.Length = template.Size;
                entry.Fingerprint = _reuseFingerprint;
            }

            NoteBind(pbp, setIndex, _program.PipelineLayout, entry);
        }

        // An array set about to be bound, in a sampled command buffer: counted when that same set is bound there already.
        private void NoteArraySet(PipelineBindPoint pbp, int setIndex, DescriptorSet[] sets)
        {
            if (!_reuseSampled)
            {
                return;
            }

            int point = pbp == PipelineBindPoint.Compute ? 1 : 0;
            int index = setIndex - PipelineBase.DescriptorSetLayouts;
            ulong[] arraySets = _boundArraySets[point];
            DescriptorReuseJournal.ArraySetBinds++;

            if (arraySets != null && index < arraySets.Length && arraySets[index] != 0 && arraySets[index] == sets[0].Handle &&
                _boundLayouts[point].Handle == _program.PipelineLayout.Handle)
            {
                DescriptorReuseJournal.ArraySetsWouldKeep++;
            }

            NoteBind(pbp, setIndex, _program.PipelineLayout, arraySet: sets[0].Handle);
        }
''' + MEMBERS_END + '\n'

JOURNAL = JOURNAL_BEGIN + '''    /// <summary>
    /// RewindBox (adapt_descriptor_set_reuse_journal): in the sampled command buffers of the main pipeline, the template set
    /// writes, those a reuse would have spared, and the parts of the timed updates; one line every 5 s of updates (render
    /// thread), through the engine's Logger.
    /// </summary>
    static class DescriptorReuseJournal
    {
        public static readonly long[] Written = new long[PipelineBase.DescriptorSetLayouts];
        public static readonly long[] WouldKeep = new long[PipelineBase.DescriptorSetLayouts];
        public static readonly long[] WouldBindAgain = new long[PipelineBase.DescriptorSetLayouts];
        public static readonly long[] TimedUpdates = new long[2], SetTicks = new long[2], ArrayTicks = new long[2];
        public static long ComputeResolveTicks, ComputeWriteTicks;
        public static long Starts, SampledStarts, DescriptorsWritten, DescriptorsSpared, ArraySetBinds, ArraySetsWouldKeep, ForeignUpdates;
        private static long _windowStart, _calls;

        public static long StampIf(bool timed) => timed ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;

        public static long StampAfter(long start) => start != 0 ? System.Diagnostics.Stopwatch.GetTimestamp() : 0;

        public static void Note(long[] counts, int setIndex, ResourceBindingSegment[] segments)
        {
            counts[setIndex]++;

            foreach (ResourceBindingSegment segment in segments)
            {
                DescriptorsSpared += segment.Count;
            }
        }

        public static void NoteTimes(long resolveStart, long resolveEnd, long writeStart, PipelineBindPoint pbp)
        {
            if (resolveStart != 0)
            {
                ComputeResolveTicks += resolveEnd - resolveStart;
                ComputeWriteTicks += System.Diagnostics.Stopwatch.GetTimestamp() - writeStart;
            }
        }

        public static void LogIfDue()
        {
            if ((++_calls & 1023) != 0)
            {
                return;
            }

            long now = System.Diagnostics.Stopwatch.GetTimestamp();

            if (_windowStart == 0)
            {
                _windowStart = now;

                return;
            }

            if (now - _windowStart < 5 * System.Diagnostics.Stopwatch.Frequency)
            {
                return;
            }

            string text = TakeText(now - _windowStart);
            _windowStart = now;
            Ryujinx.Common.Logging.Logger.Warning?.Print(Ryujinx.Common.Logging.LogClass.Gpu, text);
        }

        public static string TakeText(long elapsedTicks)
        {
            string text = "Vulkan descriptor set reuse measured (not applied) over " + Ms(elapsedTicks) + " ms in " + SampledStarts +
                " of " + Starts + " command buffer starts: sets written " + Counts(Written) + ", would be kept bound " +
                Counts(WouldKeep) + ", would be bound again without a write " + Counts(WouldBindAgain) +
                " (uniform/storage/texture/image), descriptors that would not be written " + DescriptorsSpared + " of " +
                DescriptorsWritten + ", array sets that would be kept bound " + ArraySetsWouldKeep + " of " + ArraySetBinds +
                "; draw updates timed " + TimedUpdates[0] + " (sets 0-3 " + Ms(SetTicks[0]) + " ms, array sets " + Ms(ArrayTicks[0]) +
                " ms); compute updates timed " + TimedUpdates[1] + " (sets 0-3 " + Ms(SetTicks[1]) + " ms: resolving " +
                Ms(ComputeResolveTicks) + " ms, writing and binding " + Ms(ComputeWriteTicks) + " ms; array sets " + Ms(ArrayTicks[1]) + " ms)";

            Array.Clear(Written);
            Array.Clear(WouldKeep);
            Array.Clear(WouldBindAgain);
            Array.Clear(TimedUpdates);
            Array.Clear(SetTicks);
            Array.Clear(ArrayTicks);
            ComputeResolveTicks = ComputeWriteTicks = 0;
            Starts = SampledStarts = DescriptorsWritten = DescriptorsSpared = ArraySetBinds = ArraySetsWouldKeep = 0;

            return text;
        }

        private static string Counts(long[] counts) => counts[0] + "/" + counts[1] + "/" + counts[2] + "/" + counts[3];

        private static string Ms(long ticks) =>
            (ticks * 1000.0 / System.Diagnostics.Stopwatch.Frequency).ToString("F1", System.Globalization.CultureInfo.InvariantCulture);
    }
''' + JOURNAL_END

T = '// RewindBox (adapt_descriptor_set_reuse_journal)'
PAIRS = (
    ('''        public void UpdateAndBindDescriptorSets(CommandBufferScoped cbs, PipelineBindPoint pbp)
        {
''', MEMBERS + '''        public void UpdateAndBindDescriptorSets(CommandBufferScoped cbs, PipelineBindPoint pbp)
        {
'''),
    ('''            var program = _program;

            if (_dirty.HasFlag(DirtyFlags.Uniform))
''', '''            var program = _program;

            long reuseStart = BeginReuse(cbs, pbp); ''' + T + '''

            if (_dirty.HasFlag(DirtyFlags.Uniform))
'''),
    ('''            if (program.BindingSegments.Length > PipelineBase.DescriptorSetLayouts)
            {
                // Setters for scalar bindings cannot replace an independently bound array. Buffer
                // views may change without a setter and are always visited inside BindExtraSets.
                BindExtraSets(cbs, program, pbp);
            }

            _dirty = DirtyFlags.None;
''', '''            long reuseArrayStart = DescriptorReuseJournal.StampAfter(reuseStart); ''' + T + '''

            if (program.BindingSegments.Length > PipelineBase.DescriptorSetLayouts)
            {
                // Setters for scalar bindings cannot replace an independently bound array. Buffer
                // views may change without a setter and are always visited inside BindExtraSets.
                BindExtraSets(cbs, program, pbp);
            }

            EndReuse(reuseStart, reuseArrayStart, pbp); ''' + T + '''
            _dirty = DirtyFlags.None;
'''),
    # The template path: in a sampled command buffer a set without an array is resolved into the scratch, measured, and
    # copied into the template data before the same write.
    ('''            DescriptorSetTemplate template = program.Templates[setIndex];

            DescriptorSetTemplateWriter tu = _templateUpdater.Begin(template);
''', '''            DescriptorSetTemplate template = program.Templates[setIndex];

            // RewindBox (adapt_descriptor_set_reuse_journal): measured in a sampled command buffer (same bytes written below).
            long reuseResolveStart = DescriptorReuseJournal.StampIf(_reuseSetsTimed);
            bool measured = _reuseSampled && !HasArraySegment(bindingSegments);

            DescriptorSetTemplateWriter tu = measured ? BeginMeasured(template) : _templateUpdater.Begin(template);
'''),
    ('''            var sets = dsc.GetSets();
            _templateUpdater.Commit(_gd, _device, sets[0]);
''', '''            long reuseResolveEnd = DescriptorReuseJournal.StampAfter(reuseResolveStart); ''' + T + '''

            if (measured)
            {
                MeasureReuse(template, bindingSegments, setIndex, pbp);
                DescriptorSetTemplateWriter written = _templateUpdater.Begin(template);
                written.Push<byte>(_reusePending.AsSpan(0, template.Size));
            }

            long reuseWriteStart = DescriptorReuseJournal.StampAfter(reuseResolveStart);

            var sets = dsc.GetSets();
            _templateUpdater.Commit(_gd, _device, sets[0]);
'''),
    ('''            _gd.Api.CmdBindDescriptorSets(cbs.CommandBuffer, pbp, _program.PipelineLayout, (uint)setIndex, 1, sets, 0, ReadOnlySpan<uint>.Empty);
        }

        private void UpdateAndBindTexturesWithoutTemplate(''', '''            _gd.Api.CmdBindDescriptorSets(cbs.CommandBuffer, pbp, _program.PipelineLayout, (uint)setIndex, 1, sets, 0, ReadOnlySpan<uint>.Empty);
            DescriptorReuseJournal.NoteTimes(reuseResolveStart, reuseResolveEnd, reuseWriteStart, pbp); ''' + T + '''
            NoteSetWritten(pbp, setIndex, template, bindingSegments, measured);
        }

        private void UpdateAndBindTexturesWithoutTemplate('''),
    # Every other bind of the file is followed.
    ('''            _gd.Api.CmdBindDescriptorSets(cbs.CommandBuffer, pbp, _program.PipelineLayout, (uint)setIndex, 1, sets, 0, ReadOnlySpan<uint>.Empty);
        }


        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private void UpdateAndBind(CommandBufferScoped cbs, int setIndex, PipelineBindPoint pbp)
''', '''            _gd.Api.CmdBindDescriptorSets(cbs.CommandBuffer, pbp, _program.PipelineLayout, (uint)setIndex, 1, sets, 0, ReadOnlySpan<uint>.Empty);
            NoteBind(pbp, setIndex, _program.PipelineLayout); ''' + T + '''
        }


        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private void UpdateAndBind(CommandBufferScoped cbs, int setIndex, PipelineBindPoint pbp)
'''),
    ('''            _gd.Api.CmdBindDescriptorSets(cbs.CommandBuffer, pbp, _program.PipelineLayout, (uint)setIndex, 1, sets, 0, ReadOnlySpan<uint>.Empty);
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private void UpdateAndBindUniformBufferPd(CommandBufferScoped cbs)
''', '''            _gd.Api.CmdBindDescriptorSets(cbs.CommandBuffer, pbp, _program.PipelineLayout, (uint)setIndex, 1, sets, 0, ReadOnlySpan<uint>.Empty);
            NoteBind(pbp, setIndex, _program.PipelineLayout); ''' + T + '''
        }

        [MethodImpl(MethodImplOptions.AggressiveInlining)]
        private void UpdateAndBindUniformBufferPd(CommandBufferScoped cbs)
'''),
    ('''                _templateUpdater.CommitPushDescriptor(_gd, cbs, template, _program.PipelineLayout);
            }
''', '''                _templateUpdater.CommitPushDescriptor(_gd, cbs, template, _program.PipelineLayout);
                NoteBind(PipelineBindPoint.Graphics, PipelineBase.UniformSetIndex, _program.PipelineLayout); ''' + T + '''
            }
'''),
    ('''                    if (sets != null)
                    {
                        _gd.Api.CmdBindDescriptorSets(cbs.CommandBuffer, pbp, _program.PipelineLayout, (uint)setIndex, 1, sets, 0, ReadOnlySpan<uint>.Empty);
                    }
''', '''                    if (sets != null)
                    {
                        NoteArraySet(pbp, setIndex, sets); ''' + T + '''
                        _gd.Api.CmdBindDescriptorSets(cbs.CommandBuffer, pbp, _program.PipelineLayout, (uint)setIndex, 1, sets, 0, ReadOnlySpan<uint>.Empty);
                    }
'''),
    # A command buffer change and CopyFrom: everything followed is forgotten at the next update.
    ('''            _uniformSet.Clear();
            _storageSet.Clear();
            AdvancePdSequence();
        }
''', '''            _uniformSet.Clear();
            _storageSet.Clear();
            AdvancePdSequence();
            _reuseStale = true; ''' + T + '''
        }
'''),
    ('''            _updateDescriptorCacheCbIndex = true;
            _dirty = DirtyFlags.All;

            if (FeedbackLoopHazards != null)
''', '''            _updateDescriptorCacheCbIndex = true;
            _dirty = DirtyFlags.All;
            _reuseStale = true; ''' + T + '''

            if (FeedbackLoopHazards != null)
'''),
    ('''            Dispose(true);
        }
    }
}
''', '''            Dispose(true);
        }
    }

''' + JOURNAL + '''}
'''),
)


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[UPDATER], old, new)
    return list(paths.values())
