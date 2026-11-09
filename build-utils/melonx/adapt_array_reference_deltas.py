"""A texture array changed again in the same command buffer references only the views and samplers it did not hold at its
last reference pass, instead of all its distinct views and samplers (Core 715, lot 8, every title).

IPA 694 (Hogwarts Legacy 1x, pid 40200, Core 699, 108 frames at 5 005 ms): texture array reference passes 33 268 for
about 3 490 submissions, 2 094 605 references, 241.1 ms on the render thread (EncodingPolicy.IncrementalArrayDescriptors,
TextureArray.AddReferences). A pass runs once per command buffer and change: after an element change in the same command
buffer it calls Get(cbs) again on every distinct view and sampler of the array (about 63 per pass), although each one
counted at the previous pass of this command buffer is already referenced by it.

Why skipping them is exact: Auto.Get(cbs) adds a command buffer reference once per command buffer (its ownership bit),
so a second Get in the same command buffer and submission adds nothing; a resource that command buffer references is
not destroyed before it completes (Auto reference count), so its handle cannot have become 0 since. The only views and
samplers that may lack a reference are those counted since the last pass: SwapReference records each one that enters
the counts (at most 1 024 per array; more, or a recount, takes the delivered whole pass). A recorded entry no longer
counted is not referenced (as the delivered pass, which walks the counts only). A destroyed one found among them is
handled as the delivered pass does (counted again without it). The dummies were referenced by the earlier pass.

Change: AddReferences, in the command buffer and submission of its last pass and with the counts valid, references the
recorded entries still counted and clears them; every other case is the delivered pass, which also clears them.
Counted on the existing pass detail line (array reference passes and references added). Fail closed on drift: the file
must be the Core 713 preparation's.
"""
import hashlib
from adapt_session import once

ARRAY = 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'
BASELINE = {
    ARRAY: '1e73e46318cbcd689b9436e289515f3e1f3afcb48920c8a497f17517c4b50d49',
}

FIELDS_OLD = '''        private Auto<DisposableSampler> _dummySampler;
'''
FIELDS_NEW = '''        private Auto<DisposableSampler> _dummySampler;
        // RewindBox (adapt_array_reference_deltas): views and samplers counted since the last reference pass (bounded; one
        // more than the bound means the next pass is whole).
        private const int MaxNewReferences = 1024;
        private List<Auto<DisposableImageView>> _newViewReferences;
        private List<Auto<DisposableSampler>> _newSamplerReferences;
'''

SAMPLER_CALL_OLD = '''                    SwapReference(_samplerReferences, previous, current);
'''
SAMPLER_CALL_NEW = '''                    SwapReference(_samplerReferences, previous, current, ref _newSamplerReferences);
'''
VIEW_CALL_OLD = '''                        SwapReference(_viewReferences, previous?.GetImageView(), view.GetImageView());
'''
VIEW_CALL_NEW = '''                        SwapReference(_viewReferences, previous?.GetImageView(), view.GetImageView(), ref _newViewReferences);
'''
NULL_CALL_OLD = '''                        SwapReference(_viewReferences, previous?.GetImageView(), null);
'''
NULL_CALL_NEW = '''                        SwapReference(_viewReferences, previous?.GetImageView(), null, ref _newViewReferences);
'''

SWAP_OLD = '''        private static void SwapReference<T>(Dictionary<Auto<T>, int> counts, Auto<T> previous, Auto<T> current) where T : IDisposable
        {
'''
SWAP_NEW = '''        private static void SwapReference<T>(Dictionary<Auto<T>, int> counts, Auto<T> previous, Auto<T> current, ref List<Auto<T>> added) where T : IDisposable
        {
'''
SWAP_ADD_OLD = '''            if (current != null)
            {
                CollectionsMarshal.GetValueRefOrAddDefault(counts, current, out _)++;
            }
        }
'''
SWAP_ADD_NEW = '''            // RewindBox (adapt_array_reference_deltas): an entry the counts did not hold is recorded for the next pass.
            if (current != null && ++CollectionsMarshal.GetValueRefOrAddDefault(counts, current, out _) == 1 &&
                (added ??= []).Count <= MaxNewReferences)
            {
                added.Add(current);
            }
        }
'''

EARLY_OLD = '''            if (!_referencesInvalid && cbs.CommandBufferIndex == _referencesCommandBuffer && submission == _referencesSubmission &&
                _referencesSequence == _changeSequence)
            {
                return;
            }
'''
EARLY_NEW = '''            if (!_referencesInvalid && cbs.CommandBufferIndex == _referencesCommandBuffer && submission == _referencesSubmission &&
                (_referencesSequence == _changeSequence || AddNewReferences(cbs)))
            {
                return;
            }
'''

END_OLD = '''            _referencesCommandBuffer = cbs.CommandBufferIndex;
            _referencesSubmission = submission;
            _referencesSequence = _changeSequence;
            RenderDetail.ArrayReferenceTicks += RenderStageTimer.Now() - start;
        }
'''
END_NEW = '''            _newViewReferences?.Clear(); // RewindBox (adapt_array_reference_deltas): this whole pass referenced them
            _newSamplerReferences?.Clear();
            _referencesCommandBuffer = cbs.CommandBufferIndex;
            _referencesSubmission = submission;
            _referencesSequence = _changeSequence;
            RenderDetail.ArrayReferenceTicks += RenderStageTimer.Now() - start;
        }

        /// <summary>
        /// RewindBox (adapt_array_reference_deltas): in the command buffer and submission of the last pass, every view and
        /// sampler counted then is referenced by it and alive until it completes (Auto), so only those counted since are
        /// referenced. False when more were recorded than the bound: the caller makes the whole pass.
        /// </summary>
        private bool AddNewReferences(CommandBufferScoped cbs)
        {
            int views = _newViewReferences?.Count ?? 0;
            int samplers = _newSamplerReferences?.Count ?? 0;

            if (views > MaxNewReferences || samplers > MaxNewReferences)
            {
                return false;
            }

            long start = RenderStageTimer.Now();
            bool destroyed = false;
            int added = 0;

            for (int index = 0; index < views; index++)
            {
                Auto<DisposableImageView> view = _newViewReferences[index];

                if (_viewReferences.ContainsKey(view))
                {
                    destroyed |= view.Get(cbs).Value.Handle == 0;
                    added++;
                }
            }

            for (int index = 0; index < samplers; index++)
            {
                Auto<DisposableSampler> sampler = _newSamplerReferences[index];

                if (_samplerReferences.ContainsKey(sampler))
                {
                    destroyed |= sampler.Get(cbs).Value.Handle == 0;
                    added++;
                }
            }

            _newViewReferences?.Clear();
            _newSamplerReferences?.Clear();
            RenderDetail.ArrayReferencePasses++;
            RenderDetail.ArrayReferencesAdded += added;

            if (destroyed)
            {
                // As the whole pass: counted again without it, its elements take the dummy.
                RebuildReferences();
            }

            _referencesSequence = _changeSequence;
            RenderDetail.ArrayReferenceTicks += RenderStageTimer.Now() - start;

            return true;
        }
'''


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    path = paths[ARRAY]
    for old, new in ((FIELDS_OLD, FIELDS_NEW), (SAMPLER_CALL_OLD, SAMPLER_CALL_NEW), (VIEW_CALL_OLD, VIEW_CALL_NEW),
                     (NULL_CALL_OLD, NULL_CALL_NEW), (SWAP_OLD, SWAP_NEW), (SWAP_ADD_OLD, SWAP_ADD_NEW),
                     (EARLY_OLD, EARLY_NEW), (END_OLD, END_NEW)):
        once(path, old, new)
    return list(paths.values())
