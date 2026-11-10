"""A texture array no longer passes its storages for write-to-read barriers again when nothing they depend on changed
(Core 723 candidate, render thread).

IPA 718, Hogwarts Legacy in play (pid 44597, the 97-frame window of 03:41:20): the render thread ran
SetTextureArraySeparate 50 841 times for 248.6 ms per 5 s (its third command after DrawIndexed and DispatchCompute), and
the GPU thread waited 519.6 ms for the render thread. Each change of the array bound to an extra set calls
TextureArray.QueueWriteToReadBarriers, as does InsertBindingBarriers after a program switch (21 634 per 5 s); the pass
calls TextureStorage.QueueWriteToReadBarrier for every distinct storage of the array (Hogwarts' bindless pool arrays
have up to 524 288 elements; three are over 4096) and, after an element change that replaced a storage, first walks
every element to rebuild that set.

A second QueueWriteToReadBarrier(S) on a storage does nothing (its pending modification was consumed by the first; its
read stages and covered stages already hold S), and calls for other stages only extend what is covered. Its state is
otherwise changed by QueueLoadOpBarrier (an attachment loaded at a render pass begin: pending modification set, read
tracking reset) and AddStoreOpUsage (stored at its end) alone. So when no attachment was loaded or stored since a pass
of the array over the same set of storages that covered the stages S, every call of a new pass for S is a no-op.

Change (every title):
- TextureStorage: a static AttachmentEpoch, incremented on entry to QueueLoadOpBarrier and AddStoreOpUsage;
- TextureArray.QueueWriteToReadBarriers: returns at once when its storage set was not rebuilt since its last pass, the
  epoch is that pass's and the stages are among those its passes covered in that epoch; otherwise the delivered pass,
  after which the epoch and stages are recorded (stages added while the epoch and the set stay the same);
- counters (passes, storages visited, sets rebuilt and elements walked, pass time, passes skipped) appended to the
  bindless inventory part of the "Vulkan pass and GPU detail" line (TextureArray.InventoryText) and reset each window.
Unchanged: every barrier decision (TextureStorage.QueueWriteToReadBarrier is not modified), buffer arrays, image arrays,
single textures (TextureView.PrepareForUsage), forced fences, the storage set rebuild. Not measured on an iPhone. Fail
closed on drift: the files must be the Core 721 preparation's.
"""
import hashlib
from adapt_session import once

STORAGE = 'src/Ryujinx.Graphics.Vulkan/TextureStorage.cs'
ARRAY = 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs'
BASELINE = {
    STORAGE: 'af1ae06375c24a3d6434913de9773534037069b936a4fa1e6317e792c520bf81',
    ARRAY: 'be0e5a59a2cd8c7715648b3ab6e8d09ec5c571ed8ebee71446e46b769f6475bd',
}
TAG = 'RewindBox (adapt_array_barrier_epoch)'

EPOCH_OLD = '''        private AccessFlags _lastModificationAccess;
        private PipelineStageFlags _lastModificationStage;
        private AccessFlags _lastReadAccess;
        private PipelineStageFlags _lastReadStage;
'''
EPOCH_NEW = '''        private AccessFlags _lastModificationAccess;
        private PipelineStageFlags _lastModificationStage;
        private AccessFlags _lastReadAccess;
        private PipelineStageFlags _lastReadStage;

        // RewindBox (adapt_array_barrier_epoch): incremented by every attachment load (QueueLoadOpBarrier) and store
        // (AddStoreOpUsage), the only changes of a storage's modification and read state outside QueueWriteToReadBarrier.
        // A texture array passes its storages again after it (TextureArray.QueueWriteToReadBarriers). Render thread.
        internal static long AttachmentEpoch;
'''

STORE_OLD = '''        public void AddStoreOpUsage(bool depthStencil)
        {
'''
STORE_NEW = '''        public void AddStoreOpUsage(bool depthStencil)
        {
            AttachmentEpoch++; // RewindBox (adapt_array_barrier_epoch)

'''

LOAD_OLD = '''        public void QueueLoadOpBarrier(CommandBufferScoped cbs, bool depthStencil)
        {
'''
LOAD_NEW = '''        public void QueueLoadOpBarrier(CommandBufferScoped cbs, bool depthStencil)
        {
            AttachmentEpoch++; // RewindBox (adapt_array_barrier_epoch)

'''

FIELDS_OLD = '''        private HashSet<TextureStorage> _storages;
        private bool _storagesDirty = true;
'''
FIELDS_NEW = '''        private HashSet<TextureStorage> _storages;
        private bool _storagesDirty = true;

        // RewindBox (adapt_array_barrier_epoch): the attachment epoch of this array's last pass over its storages (-1:
        // none), and the stages its passes covered in that epoch over the same storage set; the passes of every array
        // in the window (run, storages visited, sets rebuilt and elements walked, time) and those skipped.
        private long _barrierEpoch = -1;
        private PipelineStageFlags _barrierStages;
        private static long _barrierPasses, _barrierStorages, _barrierRebuilds, _barrierRebuildElements, _barrierTicks, _barrierSkips;
'''

PASS_OLD = '''            if (_isBuffer)
            {
                return;
            }

            HashSet<TextureStorage> storages = _storages;

            if (storages == null)
            {
                storages = [];
                _storages = storages;
            }

            if (_storagesDirty)
            {
                for (int index = 0; index < _views.Length; index++)
                {
                    // RewindBox (adapt_bindless_retention): the storage of the element's view.
                    TextureStorage storage = _views[index]?.Storage;

                    if (storage != null)
                    {
                        storages.Add(storage);
                    }
                }

                _storagesDirty = false;
            }

            foreach (TextureStorage storage in storages)
            {
                storage.QueueWriteToReadBarrier(cbs, AccessFlags.ShaderReadBit, stageFlags);
            }
        }
'''
PASS_NEW = '''            if (_isBuffer)
            {
                return;
            }

            // RewindBox (adapt_array_barrier_epoch): no attachment was loaded or stored since a pass over this same storage
            // set that covered these stages: each storage's QueueWriteToReadBarrier would find no pending modification and
            // only covered stages, and do nothing.
            long epoch = TextureStorage.AttachmentEpoch;
            bool sameSet = _storages != null && !_storagesDirty;

            if (sameSet && epoch == _barrierEpoch && (stageFlags & ~_barrierStages) == 0)
            {
                _barrierSkips++;
                return;
            }

            long passStart = System.Diagnostics.Stopwatch.GetTimestamp();

            HashSet<TextureStorage> storages = _storages;

            if (storages == null)
            {
                storages = [];
                _storages = storages;
            }

            if (_storagesDirty)
            {
                for (int index = 0; index < _views.Length; index++)
                {
                    // RewindBox (adapt_bindless_retention): the storage of the element's view.
                    TextureStorage storage = _views[index]?.Storage;

                    if (storage != null)
                    {
                        storages.Add(storage);
                    }
                }

                _storagesDirty = false;
                _barrierRebuilds++;
                _barrierRebuildElements += _views.Length;
            }

            foreach (TextureStorage storage in storages)
            {
                storage.QueueWriteToReadBarrier(cbs, AccessFlags.ShaderReadBit, stageFlags);
            }

            // RewindBox (adapt_array_barrier_epoch): what the passes of this epoch over this set have covered.
            _barrierStages = sameSet && epoch == _barrierEpoch ? _barrierStages | stageFlags : stageFlags;
            _barrierEpoch = epoch;
            _barrierPasses++;
            _barrierStorages += storages.Count;
            _barrierTicks += System.Diagnostics.Stopwatch.GetTimestamp() - passStart;
        }
'''

TEXT_OLD = '''            return FormattableString.Invariant($"; bindless pool arrays held: entries {System.Threading.Interlocked.Read(ref TextureArrayInventory.PoolEntries)} (not updated for 30 s or more {System.Threading.Interlocked.Read(ref TextureArrayInventory.PoolEntriesIdle)}), per-element delta state {System.Threading.Interlocked.Read(ref TextureArrayInventory.PoolEntryBytes) / MiB:F1} MiB; backend texture arrays over {TextureArrayInventory.LargeLength} elements {System.Threading.Interlocked.Read(ref TextureArrayInventory.LargeBackendArrays)}, element arrays {System.Threading.Interlocked.Read(ref TextureArrayInventory.LargeBackendBytes) / MiB:F1} MiB");
        }
'''
TEXT_NEW = '''            return FormattableString.Invariant($"; bindless pool arrays held: entries {System.Threading.Interlocked.Read(ref TextureArrayInventory.PoolEntries)} (not updated for 30 s or more {System.Threading.Interlocked.Read(ref TextureArrayInventory.PoolEntriesIdle)}), per-element delta state {System.Threading.Interlocked.Read(ref TextureArrayInventory.PoolEntryBytes) / MiB:F1} MiB; backend texture arrays over {TextureArrayInventory.LargeLength} elements {System.Threading.Interlocked.Read(ref TextureArrayInventory.LargeBackendArrays)}, element arrays {System.Threading.Interlocked.Read(ref TextureArrayInventory.LargeBackendBytes) / MiB:F1} MiB") + BarrierText();
        }

        /// <summary>
        /// RewindBox (adapt_array_barrier_epoch): the texture array barrier passes of the window, then reset.
        /// </summary>
        private static string BarrierText()
        {
            string text = FormattableString.Invariant($"; texture array barrier passes {_barrierPasses} (storages visited {_barrierStorages}, sets rebuilt {_barrierRebuilds} over {_barrierRebuildElements} elements, {_barrierTicks * 1000.0 / System.Diagnostics.Stopwatch.Frequency:F1} ms), skipped unchanged {_barrierSkips}");
            _barrierPasses = _barrierStorages = _barrierRebuilds = _barrierRebuildElements = _barrierTicks = _barrierSkips = 0;
            return text;
        }
'''

PAIRS = {STORAGE: ((EPOCH_OLD, EPOCH_NEW), (STORE_OLD, STORE_NEW), (LOAD_OLD, LOAD_NEW)),
         ARRAY: ((FIELDS_OLD, FIELDS_NEW), (PASS_OLD, PASS_NEW), (TEXT_OLD, TEXT_NEW))}


def apply(source):
    paths = {name: source / name for name in BASELINE}
    for name, expected in BASELINE.items():
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    for name, pairs in PAIRS.items():
        for old, new in pairs:
            once(paths[name], old, new)
    return list(paths.values())
