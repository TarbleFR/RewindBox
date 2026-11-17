"""Render thread (every title): a texture array's barrier pass calls only the storages that were ever attachments.

IPA 764 / Core a80b212f, Hogwarts Legacy in the castle courtyard (private journals, pid 28682; docs/melonx-ipa764-journals-
2026-11-17.md): in a 5 s window the render thread ran 22 413 texture array barrier passes over 1 053 305 storages (47 per
pass), 119.7 ms in all (258.8 ms in a window under memory pressure), while every source of barriers together queued
9 916 barriers, at most 0.94 % of those calls. adapt_array_barrier_epoch skips a pass when no attachment was loaded or
stored since the last one (22 036 passes skipped), but the epoch is global: the window has 7 346 render passes, and any
attachment of any of them makes every array call all its storages again.

Read in the source (TextureStorage.cs): a storage's modification (_lastModificationAccess) is set only by
AddStoreOpUsage and QueueLoadOpBarrier (an attachment store or load), its read stages are reset only by
QueueLoadOpBarrier, and its covered read (_readCoverageAccess) is only taken from a modification. A storage never used as
an attachment has none of them, so QueueWriteToReadBarrier only adds the stages to _lastReadStage and ShaderRead to
_lastReadAccess; once a full pass over an unchanged set has given it the stages asked, its call changes nothing: no
barrier, no state, no counter.

Change:
- TextureStorage: AttachmentUsed is set at a storage's first attachment store or load; AttachmentPromotions counts those
  storages and PromotionRing keeps the last 64 of them (render thread, as AttachmentEpoch).
- TextureArray.QueueWriteToReadBarriers: a full pass also lists, in the set's order, the storages that were attachments
  (_attachmentMembers) and keeps the stages its full passes over this unchanged set covered (_quietStages) and the
  promotion count. A later pass over the same set, for stages those passes covered, while none of the set's storages
  became an attachment since (every promotion since then is in the ring and none is in the set; more than the ring
  holds: a full pass), calls only those members, in that order. A changed set, a new stage or such a promotion runs the
  full pass as before. Any element change (MoveStorage, SetDirty) forgets the members.
- The barrier line of the detail journal adds the member passes and the storages first used as attachments so far.

Not changed: which barriers are queued, their stages and accesses, their order (the skipped calls queue nothing; the
members keep the order of the set's enumeration, unchanged since the full pass), the epoch skip, draws, descriptors.
Checked outside the repository with a model of both classes (agent A, 17 Nov): 6 000 random sequences of 4 000
operations on three driver configurations give the same barrier log and final states, also with a ring of 4; three
deliberate mutations (no promotion check, no stage check, reversed order) are caught in 86 to 96 % of sequences.

Expected on the device: the barrier line's member passes take most of the passes, the storages visited fall, and the
passes' milliseconds with them (computed 40 to 100 ms per 5 s window in that courtyard, more under memory pressure;
not measured). Rollback: drop this adapter from prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

STORAGE = 'src/Ryujinx.Graphics.Vulkan/TextureStorage.cs'
ARRAY = 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'
# The preparation of Core a80b212f (IPA 764): TextureStorage.cs after adapt_array_barrier_epoch, TextureArray.cs after
# adapt_pool_slot_copy.
BASELINE = {
    STORAGE: 'ea5c4e4671bc97f0cdd94196f0add66b97f9e8d0e77b0e07cfb7845756fed2f0',
    ARRAY: '8f727364cc7d333c5babaee69107c53681bdc58b784de80400751ab288fc7588',
}

STORAGE_FIELDS_OLD = '''        internal static long AttachmentEpoch;
'''
STORAGE_FIELDS_NEW = '''        internal static long AttachmentEpoch;

        // RewindBox (adapt_array_attachment_members): set at this storage's first attachment store or load, the only way a
        // storage gets a modification or a covered read, or has its read stages reset; the count of storages it was set
        // for, and the last PromotionRingSize of them. Render thread, as AttachmentEpoch. A texture array's barrier pass
        // calls the storages it was set for, and the others only in its full passes.
        internal const int PromotionRingSize = 64;
        internal static long AttachmentPromotions;
        internal static readonly TextureStorage[] PromotionRing = new TextureStorage[PromotionRingSize];
        internal bool AttachmentUsed;

        private void NoteAttachmentUse()
        {
            if (!AttachmentUsed)
            {
                AttachmentUsed = true;
                PromotionRing[(int)(AttachmentPromotions & (PromotionRingSize - 1))] = this;
                AttachmentPromotions++;
            }
        }
'''

STORE_OLD = '''        public void AddStoreOpUsage(bool depthStencil)
        {
            AttachmentEpoch++; // RewindBox (adapt_array_barrier_epoch)
'''
STORE_NEW = '''        public void AddStoreOpUsage(bool depthStencil)
        {
            AttachmentEpoch++; // RewindBox (adapt_array_barrier_epoch)
            NoteAttachmentUse(); // RewindBox (adapt_array_attachment_members)
'''

LOAD_OLD = '''        public void QueueLoadOpBarrier(CommandBufferScoped cbs, bool depthStencil)
        {
            AttachmentEpoch++; // RewindBox (adapt_array_barrier_epoch)
'''
LOAD_NEW = '''        public void QueueLoadOpBarrier(CommandBufferScoped cbs, bool depthStencil)
        {
            AttachmentEpoch++; // RewindBox (adapt_array_barrier_epoch)
            NoteAttachmentUse(); // RewindBox (adapt_array_attachment_members)
'''

TEXT_OLD = '''            string text = FormattableString.Invariant($"; texture array barrier passes {_barrierPasses} (storages visited {_barrierStorages}, sets rebuilt {_barrierRebuilds} over {_barrierRebuildElements} elements, {_barrierTicks * 1000.0 / System.Diagnostics.Stopwatch.Frequency:F1} ms), skipped unchanged {_barrierSkips}");
            _barrierPasses = _barrierStorages = _barrierRebuilds = _barrierRebuildElements = _barrierTicks = _barrierSkips = 0;
'''
TEXT_NEW = '''            string text = FormattableString.Invariant($"; texture array barrier passes {_barrierPasses} (storages visited {_barrierStorages}, sets rebuilt {_barrierRebuilds} over {_barrierRebuildElements} elements, {_barrierTicks * 1000.0 / System.Diagnostics.Stopwatch.Frequency:F1} ms), skipped unchanged {_barrierSkips}");
            // RewindBox (adapt_array_attachment_members): the passes that called only the storages that were attachments
            // (their milliseconds are in the figure above), and the storages first used as attachments so far.
            text += FormattableString.Invariant($", attachment member passes {_memberPasses} (storages {_memberStorages}), storages ever attachments {TextureStorage.AttachmentPromotions}");
            _barrierPasses = _barrierStorages = _barrierRebuilds = _barrierRebuildElements = _barrierTicks = _barrierSkips = 0;
            _memberPasses = _memberStorages = 0;
'''

FIELDS_OLD = '''        private static long _barrierPasses, _barrierStorages, _barrierRebuilds, _barrierRebuildElements, _barrierTicks, _barrierSkips;
'''
FIELDS_NEW = '''        private static long _barrierPasses, _barrierStorages, _barrierRebuilds, _barrierRebuildElements, _barrierTicks, _barrierSkips;

        // RewindBox (adapt_array_attachment_members): the storages of the set that were attachments at its last full pass,
        // in the set's order; the promotion count then (-1: none, or forgotten); the stages every full pass over this
        // unchanged set covered; the member passes of every array in the window and the storages they called.
        private List<TextureStorage> _attachmentMembers;
        private long _attachmentMark = -1;
        private PipelineStageFlags _quietStages;
        private static long _memberPasses, _memberStorages;
'''

MOVE_OLD = '''        private void MoveStorage(TextureStorage previous, TextureStorage current)
        {
'''
MOVE_NEW = '''        private void MoveStorage(TextureStorage previous, TextureStorage current)
        {
            // RewindBox (adapt_array_attachment_members): the set changes; the next pass is a full one.
            _attachmentMembers?.Clear();
            _attachmentMark = -1;

'''

DIRTY_OLD = '''                _storageCountsValid = false; // RewindBox (adapt_array_storage_counts)
'''
DIRTY_NEW = '''                _storageCountsValid = false; // RewindBox (adapt_array_storage_counts)
                _attachmentMembers?.Clear(); // RewindBox (adapt_array_attachment_members): the next pass is a full one
                _attachmentMark = -1;
'''

SHORT_OLD = '''            long passStart = System.Diagnostics.Stopwatch.GetTimestamp();

            HashSet<TextureStorage> storages = _storages;
'''
SHORT_NEW = '''            long passStart = System.Diagnostics.Stopwatch.GetTimestamp();

            // RewindBox (adapt_array_attachment_members): a storage never stored or loaded as an attachment has no
            // modification and no covered read, and the full passes over this unchanged set gave it these stages: its call
            // would change nothing. The storages that were attachments at the last full pass are called alone, in the set's
            // order, while none of the set's storages has become an attachment since.
            if (sameSet && (stageFlags & ~_quietStages) == 0 && MembersUnpromoted())
            {
                List<TextureStorage> members = _attachmentMembers;

                for (int i = 0; i < members.Count; i++)
                {
                    members[i].QueueWriteToReadBarrier(cbs, AccessFlags.ShaderReadBit, stageFlags);
                }

                _barrierStages = epoch == _barrierEpoch ? _barrierStages | stageFlags : stageFlags;
                _barrierEpoch = epoch;
                _memberPasses++;
                _memberStorages += members.Count;
                _barrierTicks += System.Diagnostics.Stopwatch.GetTimestamp() - passStart;
                return;
            }

            HashSet<TextureStorage> storages = _storages;
'''

FULL_OLD = '''            foreach (TextureStorage storage in storages)
            {
                storage.QueueWriteToReadBarrier(cbs, AccessFlags.ShaderReadBit, stageFlags);
            }

            // RewindBox (adapt_array_barrier_epoch): what the passes of this epoch over this set have covered.
'''
FULL_NEW = '''            // RewindBox (adapt_array_attachment_members): the storages that were attachments, in the set's order.
            List<TextureStorage> attachmentMembers = _attachmentMembers ??= [];
            attachmentMembers.Clear();

            foreach (TextureStorage storage in storages)
            {
                storage.QueueWriteToReadBarrier(cbs, AccessFlags.ShaderReadBit, stageFlags);

                if (storage.AttachmentUsed)
                {
                    attachmentMembers.Add(storage);
                }
            }

            _quietStages = sameSet ? _quietStages | stageFlags : stageFlags;
            _attachmentMark = TextureStorage.AttachmentPromotions;

            // RewindBox (adapt_array_barrier_epoch): what the passes of this epoch over this set have covered.
'''

END_OLD = '''            _barrierPasses++;
            _barrierStorages += storages.Count;
            _barrierTicks += System.Diagnostics.Stopwatch.GetTimestamp() - passStart;
        }
'''
END_NEW = '''            _barrierPasses++;
            _barrierStorages += storages.Count;
            _barrierTicks += System.Diagnostics.Stopwatch.GetTimestamp() - passStart;
        }

        // RewindBox (adapt_array_attachment_members): none of this set's storages became an attachment since its last full
        // pass (every promotion since then is still in the ring and none is in the set; more than the ring holds: false).
        private bool MembersUnpromoted()
        {
            long promotions = TextureStorage.AttachmentPromotions;

            if (_attachmentMembers == null || _attachmentMark < 0 ||
                promotions - _attachmentMark > TextureStorage.PromotionRingSize)
            {
                return false;
            }

            for (long i = _attachmentMark; i < promotions; i++)
            {
                if (_storages.Contains(TextureStorage.PromotionRing[(int)(i & (TextureStorage.PromotionRingSize - 1))]))
                {
                    return false;
                }
            }

            _attachmentMark = promotions;
            return true;
        }
'''

PAIRS = [
    (STORAGE, STORAGE_FIELDS_OLD, STORAGE_FIELDS_NEW),
    (STORAGE, STORE_OLD, STORE_NEW),
    (STORAGE, LOAD_OLD, LOAD_NEW),
    (ARRAY, TEXT_OLD, TEXT_NEW),
    (ARRAY, FIELDS_OLD, FIELDS_NEW),
    (ARRAY, MOVE_OLD, MOVE_NEW),
    (ARRAY, DIRTY_OLD, DIRTY_NEW),
    (ARRAY, SHORT_OLD, SHORT_NEW),
    (ARRAY, FULL_OLD, FULL_NEW),
    (ARRAY, END_OLD, END_NEW),
]


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
