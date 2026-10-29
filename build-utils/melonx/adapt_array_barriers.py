"""Reuse bounded Vulkan array storage sets without changing descriptor invalidation.

Texture/sampler updates still invalidate descriptor sets and command-buffer
ownership exactly as upstream. Rebuild the storage deduplication set only when
an actual storage identity changes. Changed views and samplers still invalidate
descriptors. Removed storage references are cleared immediately; rebuilding
reuses the same bounded set on the next barrier request.
"""
from adapt_session import once


def apply(source):
    paths = [source / 'src/Ryujinx.Graphics.Vulkan' / (name + '.cs')
             for name in ('TextureArray', 'ImageArray')]
    for path in paths:
        once(path, '        private HashSet<TextureStorage> _storages;\n',
             '        private HashSet<TextureStorage> _storages;\n'
             '        private bool _storagesDirty = true;\n')
        setter = 'SetTextures(int index, ITexture[] textures)' if path.name == 'TextureArray.cs' else 'SetImages(int index, ITexture[] images)'
        once(path, f'        public void {setter}\n        {{\n',
             f'        public void {setter}\n        {{\n            bool storageChanged = false;\n\n')
        once(path, '                    _textureRefs[index + i].Storage = view.Storage;\n',
             '                    storageChanged |= !ReferenceEquals(_textureRefs[index + i].Storage, view.Storage);\n'
             '                    _textureRefs[index + i].Storage = view.Storage;\n')
        once(path, '                    _textureRefs[index + i].Storage = null;\n',
             '                    storageChanged |= _textureRefs[index + i].Storage != null;\n'
             '                    _textureRefs[index + i].Storage = null;\n')
        if path.name == 'TextureArray.cs':
            once(path, '''            SetDirty();
        }

        public void SetTextures''', '''            SetDirty(storageChanged: false);
        }

        public void SetTextures''')
            once(path, '''        private void SetDirty()
        {
            _cachedCommandBufferIndex = -1;
            _storages = null;
            SetDirty(_gd, isImage: false);
        }''', '''        private void SetDirty(bool storageChanged)
        {
            _cachedCommandBufferIndex = -1;

            if (storageChanged)
            {
                // Drop removed resources now, even if no further draw follows.
                // Retain only the set's bounded capacity for the next update.
                _storages?.Clear();
                _storagesDirty = true;
            }

            SetDirty(_gd, isImage: false);
        }''')
        else:
            once(path, '        private void SetDirty()\n', '        private void SetDirty(bool storageChanged)\n')
            once(path, '''            _cachedCommandBufferIndex = -1;
            _storages = null;
            SetDirty(_gd, isImage: true);''', '''            _cachedCommandBufferIndex = -1;

            if (storageChanged)
            {
                // Removed image storage must not stay rooted until the next draw.
                _storages?.Clear();
                _storagesDirty = true;
            }

            SetDirty(_gd, isImage: true);''')
        once(path, '            SetDirty();\n', '            SetDirty(storageChanged);\n')
        once(path, '''            if (storages == null)
            {
                storages = [];

                for (int index = 0; index < _textureRefs.Length; index++)''', '''            if (storages == null)
            {
                storages = [];
                _storages = storages;
            }

            if (_storagesDirty)
            {
                for (int index = 0; index < _textureRefs.Length; index++)''')
        once(path, '''                _storages = storages;
            }

            foreach (TextureStorage storage in storages)''', '''                _storagesDirty = false;
            }

            foreach (TextureStorage storage in storages)''')
    return paths
