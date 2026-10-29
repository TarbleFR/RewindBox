"""Detach retired texture handles after their replacement inherits state.

ReplaceHandles previously disposed only the old CPU RegionHandles. Inherit
creates replacement copy links transitively, so leaving the old links attached
kept every retired TextureGroupHandle in a growing dependency clique. Repeated
texture remaps retained obsolete tracking graphs and increased notifications.

Detach reciprocal dependency links only after all replacement inheritance and
the existing region disposal. Keep pending GPU sync actions, deferred-copy
pointers, modified flags and their callbacks unchanged: those can still own a
retired handle until the already scheduled work completes. Final handle disposal
uses the same detach operation and also releases its own obsolete link list.

Fragmented tracking can inherit the same old handle more than once. The second
pass can encounter the replacement through the transitive graph. Reject a copy
dependency to self: it has no data to transfer, and signalling it would clear
its own Modified flag via DeferCopy.
"""
from adapt_session import once


def apply(source):
    group = source / 'src/Ryujinx.Graphics.Gpu/Image/TextureGroup.cs'
    once(group, '''                foreach (TextureGroupHandle oldGroup in _handles)
                {
                    foreach (RegionHandle oldHandle in oldGroup.Handles)
                    {
                        oldHandle.Dispose();
                    }
                }
''', '''                foreach (TextureGroupHandle oldGroup in _handles)
                {
                    foreach (RegionHandle oldHandle in oldGroup.Handles)
                    {
                        oldHandle.Dispose();
                    }

                    // All new handles have inherited before any old links are
                    // removed. Pending sync actions retain their own lifetime.
                    oldGroup.DetachDependencies();
                }
''')
    handle = source / 'src/Ryujinx.Graphics.Gpu/Image/TextureGroupHandle.cs'
    once(handle, '''        public void CreateCopyDependency(TextureGroupHandle other, bool copyToOther = false)
        {
            // Does this dependency already exist?
''', '''        public void CreateCopyDependency(TextureGroupHandle other, bool copyToOther = false)
        {
            // Repeated inheritance can encounter this replacement through a
            // transitive link. Self-links would discard our own Modified flag.
            if (other == this)
            {
                return;
            }

            // Does this dependency already exist?
''')
    once(handle, '''        /// <summary>
        /// Dispose this texture group handle, removing all its dependencies and disposing its memory tracking handles.
''', '''        /// <summary>
        /// Removes reciprocal copy links after this handle is retired.
        /// Pending sync actions and deferred copies keep their existing lifetime.
        /// </summary>
        internal void DetachDependencies()
        {
            foreach (TextureDependency dependency in Dependencies.ToArray())
            {
                dependency.Other.Handle.RemoveDependency(dependency.Other);
            }

            Dependencies.Clear();
        }

        /// <summary>
        /// Dispose this texture group handle, removing all its dependencies and disposing its memory tracking handles.
''')
    once(handle, '''        public void Dispose()
        {
            foreach (RegionHandle handle in Handles)
            {
                handle.Dispose();
            }

            foreach (TextureDependency dependency in Dependencies.ToArray())
            {
                dependency.Other.Handle.RemoveDependency(dependency.Other);
            }
        }
''', '''        public void Dispose()
        {
            foreach (RegionHandle handle in Handles)
            {
                handle.Dispose();
            }

            DetachDependencies();
        }
''')
    return [group, handle]
