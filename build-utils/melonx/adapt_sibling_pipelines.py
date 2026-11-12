"""Graphics programs made of the same code share the pipelines they hold (Core 747 candidate).

IPA 729 / Core 743, Hogwarts Legacy 1x (pid 58475), pipelineVariants summary after 165 s of play: 1 786 recorded states
rebuilt by the launch's replays, 1 355 of them bound by a first draw, and 49 states still created on the render thread
(356 ms), of which "built but missed" 13: the journal holds the state as built in this session, yet the draw found no
pipeline and created it. Super Smash Bros. Ultimate in the same process: 0.

Cause read in the source. The journal names a state by its program's code (ShaderCollection.StableHash) and its
pipeline key (PipelineState.WriteVariant, which TryReadVariant reads back to the same PipelineUid: 3 000 random states
in the pipeline-variant-replay gate). A pipeline, though, lives in the table of one ShaderCollection object, and the
GPU side makes several objects out of one code: ShaderSpecializationState.MatchesGraphics compares the whole attribute
type table, the fragment output types of every render target (NeedsFragmentOutputSpecialization on MoltenVK) and other
state whether or not the stages read it, so a guest program drawn under a second such state is translated again, to
the same code, as a second host program. PipelineVariantJournal.Offer hands a code's recorded states to the first
object that offers it (_plan.Remove), and no pipeline of the session is ever removed before its program is disposed
(programs are disposed with the whole shader cache): the second object therefore creates on the render thread a state
the first one already holds, in every session.

Change (ShaderCollection.cs only). Guest graphics programs join a group by pipeline layout entry (the same
PipelineLayoutCacheEntry object, so the same VkPipelineLayout and descriptor set layouts) and code identity (128 bits
of the stage codes, the stage kinds, their count and total length). TryGetGraphicsPipeline, on a state this program
lacks, takes the pipeline a member of its group holds for the same key: one more reference on the same
Auto<DisposablePipeline>, kept in this program's table, given back when this program is disposed (the owner still
disposes it once; the pipeline is destroyed with its last reference). A program with no sibling runs the control's
lookup: one field read more. Nothing is drawn differently: the pipeline taken is the one this program would have
created (same modules' code, same layout, same key).
A journal line (pipelineSiblings) is written at the 1st, 8th, 64th... pipeline taken: it is the device proof that such
programs exist and that the states come from them.

Expected on the device (same save and route, second launch): "built but missed" 13 -> 2 or fewer and the late creations
fall by as much; a pipelineSiblings line with a count above zero. Refuted if "built but missed" stays and no
pipelineSiblings line appears (the duplicate programs then do not share a layout entry, or the cause is elsewhere).
Not treated: a state a draw needs before its sibling's replay built it ("planned not built yet" 5).
Rollback: drop this adapter from prepare_embedded.py and the plan. Not measured on an iPhone. Fail closed on drift.
"""
import hashlib
from adapt_session import once

PROGRAM = 'src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs'
BASELINE = {PROGRAM: 'c721da2bbaa47c6b37d0dcfd46dc3fab890f7e5cc41f4d0cd935ab464a67b1de'}

FIELD_OLD = '''        private readonly PipelineLayoutCacheEntry _plce;
'''
FIELD_NEW = '''        private readonly PipelineLayoutCacheEntry _plce;

        // RewindBox (adapt_sibling_pipelines): the live guest graphics programs made of this program's code on its pipeline
        // layout entry (one guest program translated again for a specialization that left its code unchanged). They are
        // the same host program: a pipeline one of them holds for a state serves the others (TryGetGraphicsPipeline).
        private PipelineSiblings<ShaderCollection>.Group _siblings;
        private PipelineLoans<DisposablePipeline> _loans; // pipelines taken from a sibling; under _pipelineCacheLock
'''

CTOR_OLD = '''            _recordsVariants = !IsCompute;
'''
CTOR_NEW = '''            _recordsVariants = !IsCompute;

            if (!IsCompute)
            {
                // RewindBox (adapt_sibling_pipelines)
                _siblings = PipelineSiblings<ShaderCollection>.Join(_plce, ComputeCodeIdentity(sources), this);
            }
'''

LOOKUP_OLD = '''        public bool TryGetGraphicsPipeline(ref PipelineUid key, out Auto<DisposablePipeline> pipeline)
        {
            lock (_pipelineCacheLock)
            {
                if (_graphicsPipelineCache == null)
                {
                    pipeline = default;
                    return false;
                }

                if (!_graphicsPipelineCache.TryGetValue(ref key, out pipeline))
                {
                    if (!CompilesInBackground && _firstBackgroundUse)
'''
LOOKUP_NEW = '''        public bool TryGetGraphicsPipeline(ref PipelineUid key, out Auto<DisposablePipeline> pipeline)
        {
            // RewindBox (adapt_sibling_pipelines): a state this program lacks is taken from a sibling that holds it, before
            // the miss is reported and the caller creates it.
            PipelineSiblings<ShaderCollection>.Group siblings = _siblings;

            if (siblings == null || siblings.Count < 2)
            {
                return TryGetOwnGraphicsPipeline(ref key, out pipeline, reportMiss: true);
            }

            if (TryGetOwnGraphicsPipeline(ref key, out pipeline, reportMiss: false))
            {
                return true;
            }

            TakeSiblingGraphicsPipeline(siblings, ref key);

            return TryGetOwnGraphicsPipeline(ref key, out pipeline, reportMiss: true);
        }

        // RewindBox (adapt_sibling_pipelines): the first sibling holding a pipeline for the key lends it (a reference taken
        // under its lock); it enters this program's table unless the state arrived here meanwhile or this program is being
        // disposed, in which case the reference is given back. No lock of one program is taken inside another's.
        private void TakeSiblingGraphicsPipeline(PipelineSiblings<ShaderCollection>.Group siblings, ref PipelineUid key)
        {
            foreach (ShaderCollection sibling in siblings.Members)
            {
                if (ReferenceEquals(sibling, this))
                {
                    continue;
                }

                Auto<DisposablePipeline> lent = sibling.LendGraphicsPipeline(ref key);

                if (lent == null)
                {
                    continue;
                }

                bool kept;

                lock (_pipelineCacheLock)
                {
                    kept = !_loans.Closed && (_graphicsPipelineCache == null || !_graphicsPipelineCache.TryGetValue(ref key, out _));

                    if (kept)
                    {
                        _graphicsPipelineBackgroundFailures?.Remove(ref key);
                        (_graphicsPipelineCache ??= new()).Add(ref key, lent);
                        _loans.Take(lent);
                    }
                }

                if (!kept)
                {
                    lent.DecrementReferenceCount();

                    return;
                }

                // One the sibling's replay built is used now: its record counts as ready before its first draw.
                sibling.NotePipelineBound(lent.GetUnsafe().Value.Handle);
                PipelineSiblingsJournal.NoteTaken(siblings.Count);

                return;
            }
        }

        // RewindBox (adapt_sibling_pipelines): this program's pipeline for the key with one more reference, for a sibling;
        // null when it has none, when its creation failed, or when it is being destroyed.
        private Auto<DisposablePipeline> LendGraphicsPipeline(ref PipelineUid key)
        {
            lock (_pipelineCacheLock)
            {
                return !_loans.Closed && _graphicsPipelineCache != null &&
                    _graphicsPipelineCache.TryGetValue(ref key, out Auto<DisposablePipeline> pipeline) &&
                    PipelineLoans<DisposablePipeline>.TryLend(pipeline) ? pipeline : null;
            }
        }

        // RewindBox (adapt_sibling_pipelines): 128 bits of the stage codes with their kinds, the stage count and the code's
        // total length: programs equal on all four, on one pipeline layout entry, are the same host program.
        private static PipelineCodeIdentity ComputeCodeIdentity(ShaderSource[] shaders)
        {
            ulong first = 0xCBF29CE484222325UL;
            ulong second = 0x9E3779B97F4A7C15UL;
            long length = 0;

            foreach (ShaderSource shader in shaders)
            {
                byte[] code = shader.BinaryCode ?? System.Text.Encoding.UTF8.GetBytes(shader.Code ?? string.Empty);
                Ryujinx.Common.Hash128 part = Ryujinx.Common.Hash128.ComputeHash(code);

                first = ((first ^ part.Low ^ (ulong)shader.Stage) * 0x100000001B3UL) ^ part.High;
                second = ((second ^ part.High) * 0xFF51AFD7ED558CCDUL) ^ (part.Low + (ulong)shader.Stage);
                length += code.Length;
            }

            return new PipelineCodeIdentity(first, second, shaders.Length, length);
        }

        private bool TryGetOwnGraphicsPipeline(ref PipelineUid key, out Auto<DisposablePipeline> pipeline, bool reportMiss)
        {
            lock (_pipelineCacheLock)
            {
                if (_graphicsPipelineCache == null)
                {
                    pipeline = default;
                    return false;
                }

                if (!_graphicsPipelineCache.TryGetValue(ref key, out pipeline))
                {
                    if (reportMiss && !CompilesInBackground && _firstBackgroundUse)
'''

LEAVE_OLD = '''                if (!_gd.Shaders.Remove(this))
                {
                    return;
                }
'''
LEAVE_NEW = '''                _siblings?.Leave(this); // RewindBox (adapt_sibling_pipelines): lends nothing from here on

                if (!_gd.Shaders.Remove(this))
                {
                    return;
                }
'''

RELEASE_OLD = '''                    if (_graphicsPipelineCache != null)
                    {
                        foreach (Auto<DisposablePipeline> pipeline in _graphicsPipelineCache.Values)
                        {
                            pipeline?.Dispose();
                        }
                    }
'''
RELEASE_NEW = '''                    _loans.Close(); // RewindBox (adapt_sibling_pipelines): nothing is lent or taken after this

                    if (_graphicsPipelineCache != null)
                    {
                        foreach (Auto<DisposablePipeline> pipeline in _graphicsPipelineCache.Values)
                        {
                            // RewindBox (adapt_sibling_pipelines): a pipeline taken from a sibling gives back the reference
                            // taken for it; its owner disposes it.
                            if (pipeline != null && !_loans.Return(pipeline))
                            {
                                pipeline.Dispose();
                            }
                        }
                    }
'''

TAIL_OLD = '''        public void Dispose()
        {
            Dispose(true);
        }
    }
}
'''
TAIL_NEW = '''        public void Dispose()
        {
            Dispose(true);
        }
    }

    // RewindBox (adapt_sibling_pipelines): what makes two programs on one pipeline layout entry the same host program.
    internal readonly record struct PipelineCodeIdentity(ulong First, ulong Second, int Stages, long Length);

    // RewindBox (adapt_sibling_pipelines): the live programs of one code on one pipeline layout entry. The table holds
    // its layout entries weakly and a group only its live members: a disposed program is reachable from nothing here.
    internal static class PipelineSiblings<TProgram> where TProgram : class
    {
        internal sealed class Group
        {
            private readonly Dictionary<PipelineCodeIdentity, Group> _owner;
            private readonly PipelineCodeIdentity _identity;
            private TProgram[] _members = Array.Empty<TProgram>();

            internal Group(Dictionary<PipelineCodeIdentity, Group> owner, PipelineCodeIdentity identity)
            {
                _owner = owner;
                _identity = identity;
            }

            /// <summary>The members at this instant; the array is never modified.</summary>
            public TProgram[] Members => Volatile.Read(ref _members);
            public int Count => Members.Length;

            internal void Add(TProgram program)
            {
                TProgram[] members = _members;
                TProgram[] grown = new TProgram[members.Length + 1];

                members.CopyTo(grown, 0);
                grown[^1] = program;
                Volatile.Write(ref _members, grown);
            }

            public void Leave(TProgram program)
            {
                lock (_owner)
                {
                    TProgram[] members = _members;
                    int index = Array.IndexOf(members, program);

                    if (index < 0)
                    {
                        return;
                    }

                    TProgram[] fewer = new TProgram[members.Length - 1];

                    Array.Copy(members, 0, fewer, 0, index);
                    Array.Copy(members, index + 1, fewer, index, fewer.Length - index);
                    Volatile.Write(ref _members, fewer);

                    if (fewer.Length == 0 && _owner.TryGetValue(_identity, out Group current) && ReferenceEquals(current, this))
                    {
                        _owner.Remove(_identity);
                    }
                }
            }
        }

        private static readonly System.Runtime.CompilerServices.ConditionalWeakTable<object, Dictionary<PipelineCodeIdentity, Group>> _byLayout = new();

        public static Group Join(object layout, PipelineCodeIdentity identity, TProgram program)
        {
            Dictionary<PipelineCodeIdentity, Group> groups = _byLayout.GetOrCreateValue(layout);

            lock (groups)
            {
                if (!groups.TryGetValue(identity, out Group group))
                {
                    groups[identity] = group = new Group(groups, identity);
                }

                group.Add(program);

                return group;
            }
        }
    }

    // RewindBox (adapt_sibling_pipelines): the pipelines a program took from a sibling. Each holds one reference taken by
    // TryLend, given back by Return (its owner disposes it once; it is destroyed with its last reference). The caller
    // serializes every call on one instance (the program's pipeline table lock).
    internal struct PipelineLoans<T> where T : IDisposable
    {
        private HashSet<Auto<T>> _taken;

        public bool Closed { get; private set; }
        public readonly int Count => _taken?.Count ?? 0;

        /// <summary>One more reference on a pipeline its owner still holds; false for none, or one being destroyed.</summary>
        public static bool TryLend(Auto<T> pipeline) => pipeline != null && pipeline.TryIncrementReferenceCount();

        public void Take(Auto<T> pipeline) => (_taken ??= new()).Add(pipeline);

        /// <summary>True for a pipeline taken from a sibling: its reference is given back and it is not to be disposed here.</summary>
        public bool Return(Auto<T> pipeline)
        {
            if (_taken == null || !_taken.Remove(pipeline))
            {
                return false;
            }

            pipeline.DecrementReferenceCount();

            return true;
        }

        public void Close() => Closed = true;
    }

    // RewindBox (adapt_sibling_pipelines): counted per process; one journal line at the 1st, 8th, 64th... pipeline taken.
    internal static class PipelineSiblingsJournal
    {
        private static long _taken;
        private static int _largestGroup;

        public static long Taken => Interlocked.Read(ref _taken);

        public static void NoteTaken(int groupSize)
        {
            long taken = Interlocked.Increment(ref _taken);
            int largest;

            while ((largest = Volatile.Read(ref _largestGroup)) < groupSize &&
                   Interlocked.CompareExchange(ref _largestGroup, groupSize, largest) != largest)
            {
            }

            if (IsReportCount(taken))
            {
                Ryujinx.Common.EmbeddedLaunchDiagnostics.Record("pipelineSiblings", "taken", detail:
                    $"{taken} pipelines taken from a program of the same code instead of being created (process total; largest " +
                    $"group {Volatile.Read(ref _largestGroup)} programs) (adapt_sibling_pipelines)");
            }
        }

        /// <summary>1, 8, 64, 512...</summary>
        internal static bool IsReportCount(long count) => count > 0 && (count & (count - 1)) == 0 &&
            System.Numerics.BitOperations.TrailingZeroCount((ulong)count) % 3 == 0;
    }
}
'''

PAIRS = ((FIELD_OLD, FIELD_NEW), (CTOR_OLD, CTOR_NEW), (LOOKUP_OLD, LOOKUP_NEW), (LEAVE_OLD, LEAVE_NEW),
         (RELEASE_OLD, RELEASE_NEW), (TAIL_OLD, TAIL_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for old, new in PAIRS:
        once(paths[PROGRAM], old, new)
    return list(paths.values())
