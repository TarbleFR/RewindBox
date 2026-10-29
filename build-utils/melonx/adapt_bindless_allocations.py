"""Remove two temporary reference arrays from repeated bindless updates.

The GPU bindings cache used to allocate fresh texture/sampler arrays, the
threaded producer copied each one, and the consumer projected that private
copy into another array. The consumer now unwraps its private snapshot in
place. ThreadedImageArray must first take the same private snapshot as
ThreadedTextureArray: images previously queued the caller's array directly.

The GPU cache keeps up to four exact-length arrays per element type, at most
4096 entries each (256 KiB of reference slots in total on a 64-bit host).
Rented arrays leave that cache until the caller returns them, so a nested
update cannot overwrite an active lease. Every return clears all references,
including on exceptions and for arrays too large to retain. All OpenGL and
Vulkan SetTextures/SetSamplers/SetImages implementations consume the array
synchronously; the threaded implementation owns its copy before returning.

No descriptor count, order, null entry, command ordering or resource lifetime
is changed. These are allocation reductions, not measured iPhone FPS gains.
The adapter fails closed if the pinned upstream code has drifted.
"""
from adapt_session import once


COMMANDS = (
    ('TextureArray', 'Textures', 'ITexture', 'ThreadedTexture'),
    ('TextureArray', 'Samplers', 'ISampler', 'ThreadedSampler'),
    ('ImageArray', 'Images', 'ITexture', 'ThreadedTexture'),
)


def method(text, signature):
    """Return a complete method; these audited methods contain no brace strings."""
    assert text.count(signature) == 1, signature
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    end = opening + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def apply(source):
    gal = source / 'src/Ryujinx.Graphics.GAL/Multithreading'
    changed = []
    for array, plural, element, wrapper in COMMANDS:
        path = gal / f'Commands/{array}/{array}Set{plural}Command.cs'
        variable = array[0].lower() + array[1:]
        values = plural.lower()
        item = 'sampler' if plural == 'Samplers' else 'texture'
        old = (f'            {variable}.Base.Set{plural}(command._index, '
               f'command._{values}.Get(threaded).Select({item} => '
               f'(({wrapper}){item})?.Base).ToArray());')
        new = f'''            // The producer owns this exact-length snapshot until this command runs.
            {element}[] {values} = command._{values}.Get(threaded);

            for (int i = 0; i < {values}.Length; i++)
            {{
                {values}[i] = (({wrapper}){values}[i])?.Base;
            }}

            {variable}.Base.Set{plural}(command._index, {values});'''
        once(path, old, new)
        once(path, 'using System.Linq;\n', '')
        changed.append(path)

    textures = gal / 'Resources/ThreadedTextureArray.cs'
    for plural, element in (('Textures', 'ITexture'), ('Samplers', 'ISampler')):
        values = plural.lower()
        once(textures,
             f'            _renderer.New<TextureArraySet{plural}Command>()->Set(Ref(this), index, Ref({values}.ToArray()));',
             f'''            // Capture before reserving command/table slots; a failed copy owns no queue state.
            {element}[] snapshot = {values}.ToArray();
            _renderer.New<TextureArraySet{plural}Command>()->Set(Ref(this), index, Ref(snapshot));''')
    changed.append(textures)

    images = gal / 'Resources/ThreadedImageArray.cs'
    once(images, 'using Ryujinx.Graphics.GAL.Multithreading.Model;\n',
         'using Ryujinx.Graphics.GAL.Multithreading.Model;\nusing System.Linq;\n')
    once(images,
         '            _renderer.New<ImageArraySetImagesCommand>()->Set(Ref(this), index, Ref(images));',
         '''            // The caller may reuse its array as soon as this method returns.
            ITexture[] snapshot = images.ToArray();
            _renderer.New<ImageArraySetImagesCommand>()->Set(Ref(this), index, Ref(snapshot));''')
    changed.append(images)

    cache = source / 'src/Ryujinx.Graphics.Gpu/Image/TextureBindingsArrayCache.cs'
    once(cache, '        private int _currentTimestamp;\n', '''        private int _currentTimestamp;

        // Exact lengths matter: the GAL array API consumes the entire array.
        // Keep a few common lengths without retaining any bound GPU resources.
        private const int BindingScratchSlots = 4;
        private const int MaxBindingScratchLength = 4096;
        private readonly ITexture[][] _textureBindingScratch = new ITexture[BindingScratchSlots][];
        private readonly ISampler[][] _samplerBindingScratch = new ISampler[BindingScratchSlots][];
        private int _nextTextureBindingScratch;
        private int _nextSamplerBindingScratch;

        private static T[] RentBindingScratch<T>(T[][] cache, int length)
        {
            if (length == 0)
            {
                return Array.Empty<T>();
            }

            for (int i = 0; i < cache.Length; i++)
            {
                T[] scratch = cache[i];

                if (scratch != null && scratch.Length == length)
                {
                    // Do not lend an array twice, including during a nested update.
                    cache[i] = null;
                    return scratch;
                }
            }

            return new T[length];
        }

        private static void ReturnBindingScratch<T>(T[][] cache, T[] scratch, ref int next)
        {
            if (scratch == null)
            {
                return;
            }

            Array.Clear(scratch);

            if (scratch.Length == 0 || scratch.Length > MaxBindingScratchLength)
            {
                return;
            }

            int empty = -1;

            for (int i = 0; i < cache.Length; i++)
            {
                if (cache[i] == null)
                {
                    empty = i;
                }
                else if (cache[i].Length == scratch.Length)
                {
                    // A nested update may already have returned this length.
                    return;
                }
            }

            if (empty >= 0)
            {
                cache[empty] = scratch;
            }
            else
            {
                cache[next] = scratch;
                next = (next + 1) % cache.Length;
            }
        }
''')
    allocations = '''            ISampler[] samplers = isImage ? null : new ISampler[bindingInfo.ArrayLength];
            ITexture[] textures = new ITexture[bindingInfo.ArrayLength];
'''
    for name in ('UpdateFromPool', 'UpdateFromBuffer'):
        old = method(cache.read_text(), f'        private void {name}(')
        assert old.count(allocations) == 1, name
        prefix, body = old.split(allocations)
        assert body.endswith('        }'), name
        body = body[:-len('        }')].strip('\n')
        indented = '\n'.join('    ' + line if line else '' for line in body.splitlines())
        new = prefix + '''            ISampler[] samplers = null;
            ITexture[] textures = null;

            try
            {
                samplers = isImage ? null : RentBindingScratch(_samplerBindingScratch, bindingInfo.ArrayLength);
                textures = RentBindingScratch(_textureBindingScratch, bindingInfo.ArrayLength);

''' + indented + '''
            }
            finally
            {
                // Direct backends have consumed these; threaded backends own a private copy.
                ReturnBindingScratch(_textureBindingScratch, textures, ref _nextTextureBindingScratch);
                ReturnBindingScratch(_samplerBindingScratch, samplers, ref _nextSamplerBindingScratch);
            }
        }'''
        once(cache, old, new)
    changed.append(cache)
    return changed
