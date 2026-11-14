"""A command buffer holds one reference per object it uses, not one per object in its reference chain (every title).

IPA 740 / Core da2525a1, Hogwarts Legacy (private journal, pid 5954, [MeloNX:hot] profiles of the render thread in the
world): the chain Auto.AddCommandBufferDependencies -> CommandBufferPool.AddDependant -> List<IAuto>.Add, with the
covariant array-store check of List<IAuto> (StelemRef_Helper and its cast cache, 39 own samples, all under that chain),
and the matching DecrementReferenceCount(cbIndex) loop of WaitAndDecrementRef. The first use of a texture view in a
command buffer added three dependants: the view, its image and the image's memory (TextureView.cs creates the view's
Auto with the image's Auto as referenced object, TextureStorage.cs the image's with the memory's; buffers and
framebuffers follow the same pattern). Each took an interlocked reference and an element of the list, and each was
interlocked-released when the command buffer completed. The image and the memory are already kept alive for the view's
whole lifetime by the reference the view's constructor took on them (Auto's constructor; released only when the view
is destroyed), and the view is kept alive by the command buffer's reference, so their own command-buffer references
were redundant. What the rest of the backend reads of them is their command-buffer bit (HasCommandBufferDependency:
TextureStorage, TextureView, PipelineFull.FlushCommandsIfWeightExceeding, BufferHolder) and their waitable.

Change:
- Auto.cs: the objects an Auto references get their command-buffer bit and their waitable registered
  (AddCommandBufferOwnership), without a reference or a dependant entry; when the command buffer completes, the Auto
  clears their bits (ClearCommandBufferOwnership) before releasing its own reference, which may destroy it and release
  them. An object used directly in the command buffer first is still a dependant of its own, as before; one used
  directly after it was reached through a view finds its bit set and adds nothing, as before.
- CommandBufferPool.cs: the dependants are stored as a struct wrapping the IAuto (List<DependantEntry>), so adding one
  is a plain store, without the covariance check of an interface-typed array.

Same bits set and cleared for the same command buffers, same waitables, same lifetimes; fewer interlocked operations
and list elements per command buffer. Expected on the device: AddCommandBufferDependencies, AddDependant and
StelemRef_Helper lower in the render thread's profile. Not measured on an iPhone. Rollback: drop this adapter from
prepare_embedded.py and ORDER. Fail closed on drift.
"""
import hashlib
from adapt_session import once

AUTO = 'src/Ryujinx.Graphics.Vulkan/Auto.cs'
POOL = 'src/Ryujinx.Graphics.Vulkan/CommandBufferPool.cs'
BASELINE = {
    AUTO: '5d9b1513bff4e2e306032a0f9e0299f3cfd24da37a46b2b1d385bdd820887731',
    POOL: 'beb73c36e5ae5313781d224798375ff4870961b9777e608eb52205bdeb3f5cd5',
}

INTERFACE_OLD = '''    interface IAutoPrivate : IAuto
    {
        void AddCommandBufferDependencies(CommandBufferScoped cbs);
    }
'''
INTERFACE_NEW = '''    interface IAutoPrivate : IAuto
    {
        void AddCommandBufferDependencies(CommandBufferScoped cbs);
        void AddCommandBufferOwnership(CommandBufferScoped cbs);
        void ClearCommandBufferOwnership(int cbIndex);
    }
'''

CHAIN_OLD = '''                // We need to add a dependency on the command buffer to all objects this object
                // references aswell.
                if (_referencedObjs != null)
                {
                    for (int i = 0; i < _referencedObjs.Length; i++)
                    {
                        _referencedObjs[i].AddCommandBufferDependencies(cbs);
                    }
                }
            }
        }
'''
CHAIN_NEW = '''                // RewindBox (adapt_command_buffer_ownership): the objects this one references are kept alive by the
                // reference its constructor took on them, released only when it is destroyed, and it is kept alive by
                // the command buffer: they only get their command-buffer bit and their waitable, no reference.
                if (_referencedObjs != null)
                {
                    for (int i = 0; i < _referencedObjs.Length; i++)
                    {
                        _referencedObjs[i].AddCommandBufferOwnership(cbs);
                    }
                }
            }
        }

        public void AddCommandBufferOwnership(CommandBufferScoped cbs)
        {
            if (_cbOwnership.Set(cbs.CommandBufferIndex))
            {
                if (_waitable != null)
                {
                    cbs.AddWaitable(_waitable);
                }

                if (_referencedObjs != null)
                {
                    for (int i = 0; i < _referencedObjs.Length; i++)
                    {
                        _referencedObjs[i].AddCommandBufferOwnership(cbs);
                    }
                }
            }
        }

        public void ClearCommandBufferOwnership(int cbIndex)
        {
            if (_cbOwnership.IsSet(cbIndex))
            {
                _cbOwnership.Clear(cbIndex);

                if (_referencedObjs != null)
                {
                    for (int i = 0; i < _referencedObjs.Length; i++)
                    {
                        _referencedObjs[i].ClearCommandBufferOwnership(cbIndex);
                    }
                }
            }
        }
'''

RELEASE_OLD = '''        public void DecrementReferenceCount(int cbIndex)
        {
            _cbOwnership.Clear(cbIndex);
            DecrementReferenceCount();
        }
'''
RELEASE_NEW = '''        public void DecrementReferenceCount(int cbIndex)
        {
            _cbOwnership.Clear(cbIndex);

            // RewindBox (adapt_command_buffer_ownership): the bits set through this object, before the release that may
            // destroy it and release the objects it references.
            if (_referencedObjs != null)
            {
                for (int i = 0; i < _referencedObjs.Length; i++)
                {
                    _referencedObjs[i].ClearCommandBufferOwnership(cbIndex);
                }
            }

            DecrementReferenceCount();
        }
'''

ENTRY_OLD = '''        private struct ReservedCommandBuffer
        {
'''
ENTRY_NEW = '''        // RewindBox (adapt_command_buffer_ownership): a struct element, so that adding a dependant is a plain store
        // (List<IAuto>.Add paid the covariant array-store check for each Auto<T>).
        private readonly struct DependantEntry
        {
            public readonly IAuto Value;

            public DependantEntry(IAuto value)
            {
                Value = value;
            }
        }

        private struct ReservedCommandBuffer
        {
'''

FIELD_OLD = '''            public List<IAuto> Dependants;
'''
FIELD_NEW = '''            public List<DependantEntry> Dependants;
'''

ADD_OLD = '''            _commandBuffers[cbIndex].Dependants.Add(dependant);
'''
ADD_NEW = '''            _commandBuffers[cbIndex].Dependants.Add(new DependantEntry(dependant));
'''

LOOP_OLD = '''            foreach (IAuto dependant in entry.Dependants)
            {
                dependant.DecrementReferenceCount(cbIndex);
            }
'''
LOOP_NEW = '''            foreach (DependantEntry dependant in entry.Dependants)
            {
                dependant.Value.DecrementReferenceCount(cbIndex);
            }
'''

PAIRS = ((AUTO, INTERFACE_OLD, INTERFACE_NEW), (AUTO, CHAIN_OLD, CHAIN_NEW), (AUTO, RELEASE_OLD, RELEASE_NEW),
         (POOL, ENTRY_OLD, ENTRY_NEW), (POOL, FIELD_OLD, FIELD_NEW), (POOL, ADD_OLD, ADD_NEW), (POOL, LOOP_OLD, LOOP_NEW))


def apply(source):
    paths = {name: source / name for name in BASELINE}
    digests = list(BASELINE.items())  # empty when the adapter control reverses this adapter
    for name, expected in digests:
        assert hashlib.sha256(paths[name].read_bytes()).hexdigest() == expected, name
    vulkan = source / 'src/Ryujinx.Graphics.Vulkan' if digests else None
    # Auto<T> is the only IAutoPrivate, WaitAndDecrementRef the only caller of DecrementReferenceCount(int), and
    # ReservedCommandBuffer.Dependants is read nowhere else.
    for path in (vulkan.rglob('*.cs') if vulkan else ()):
        text = path.read_text(encoding='utf-8-sig')
        if path.name != 'Auto.cs':
            assert 'IAutoPrivate' not in text, str(path)
            assert 'DecrementReferenceCount(cbIndex)' not in text or path.name == 'CommandBufferPool.cs', str(path)
        if path.name != 'CommandBufferPool.cs':
            assert '.Dependants' not in text, str(path)
    for name, old, new in PAIRS:
        once(paths[name], old, new)
    return list(paths.values())
