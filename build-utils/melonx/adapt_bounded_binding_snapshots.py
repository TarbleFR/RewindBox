"""Reuse exact-length threaded binding snapshots in a bounded cleared pool.

The caller still transfers an independent snapshot before reserving a command.
The consumer still resolves wrapper Base identities late and makes one backend
call with the exact logical array length. The backend synchronously consumes
these reviewed arrays. Return snapshots only after that call unwinds. Failed
producer publication never returns a possibly queued array prematurely: normal
renderer failure teardown drops its existing managed references instead.

Two table references remain sufficient: command owner plus snapshot array.
Each closed generic pool keeps at most eight cleared arrays of length2..4096,
so textures+samplers cache at most512KiB of empty reference slots on ARM64.
In-flight commands retain their original independently owned memory contract.
Scalar commands and arrays larger than the cache limit keep their current paths.
"""
import hashlib
from adapt_session import once
from adapt_single_resource_bindings import BACKEND_INPUTS


BASELINE = {
    'Resources/ThreadedTextureArray.cs': '7f20ccd20b12a2eff1a6b459b0dda352a6dd82629d86ff28fd067a6787c24af6',
    'Resources/ThreadedImageArray.cs': 'c5ae3f5a7a42e2571d4777eb28d5605b8c7e914a794740166c3d7cabcd64e2a8',
    'Commands/TextureArray/TextureArraySetTexturesCommand.cs': '3b03a9eb9b22e9b538ebfd6abdf2a6b932a534bd2409aa49fbd4f743b893628d',
    'Commands/TextureArray/TextureArraySetSamplersCommand.cs': '34b4b05a93512287ecfc3626cd4b3afc4ceb69a48f907b6dba4808835164b880',
    'Commands/ImageArray/ImageArraySetImagesCommand.cs': '0e39992874a4674a2e8b48de7b66d78520b21acb6e86ec3f8b1866e2998e99a0',
}

POOL_SOURCE = '''using System;

namespace Ryujinx.Graphics.GAL.Multithreading.Model
{
    // These arrays cross the producer/consumer boundary. A removed cache slot
    // belongs exclusively to its command until synchronous backend consumption.
    static class ThreadedArrayPool<T> where T : class
    {
        private const int CacheSlots = 8;
        private const int MaximumLength = 4096;
        private static readonly T[][] Cache = new T[CacheSlots][];
        private static int _nextEviction;

        public static T[] Copy(T[] source)
        {
            ArgumentNullException.ThrowIfNull(source);
            int length = source.Length;

            if (length == 0)
            {
                return Array.Empty<T>();
            }

            T[] snapshot = null;

            if (length > 1 && length <= MaximumLength)
            {
                lock (Cache)
                {
                    for (int i = 0; i < Cache.Length; i++)
                    {
                        if (Cache[i]?.Length == length)
                        {
                            snapshot = Cache[i];
                            Cache[i] = null;
                            break;
                        }
                    }
                }
            }

            snapshot ??= new T[length];
            // A read-only span accepts covariant caller arrays (for example a
            // ThreadedTexture[] passed as ITexture[]), as Enumerable.ToArray did.
            new ReadOnlySpan<T>(source).CopyTo(snapshot);
            return snapshot;
        }

        public static void Return(T[] snapshot)
        {
            if (snapshot.Length <= 1 || snapshot.Length > MaximumLength)
            {
                return;
            }

            // Clear before publication: cached arrays never root backend resources.
            Array.Clear(snapshot);

            lock (Cache)
            {
                for (int i = 0; i < Cache.Length; i++)
                {
                    if (Cache[i] == null)
                    {
                        Cache[i] = snapshot;
                        return;
                    }
                }

                // A new working length can replace old idle storage. Cache size
                // stays fixed even across many resources, sessions and lengths.
                Cache[_nextEviction] = snapshot;
                _nextEviction = (_nextEviction + 1) % CacheSlots;
            }
        }
    }
}
'''


def apply(source):
    root = source / 'src/Ryujinx.Graphics.GAL/Multithreading'
    for relative, digest in BACKEND_INPUTS.items():
        assert hashlib.sha256((source / relative).read_bytes()).hexdigest() == digest, relative
    for relative, digest in BASELINE.items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == digest, relative
    pool = root / 'Model/ThreadedArrayPool.cs'
    assert not pool.exists(), str(pool)

    for owner in ('ThreadedTextureArray', 'ThreadedImageArray'):
        once(root / f'Resources/{owner}.cs', 'using System.Linq;\n', '')
    for owner, category, plural, element, wrapper in (
        ('ThreadedTextureArray', 'TextureArray', 'Textures', 'ITexture', 'ThreadedTexture'),
        ('ThreadedTextureArray', 'TextureArray', 'Samplers', 'ISampler', 'ThreadedSampler'),
        ('ThreadedImageArray', 'ImageArray', 'Images', 'ITexture', 'ThreadedTexture'),
    ):
        values = plural.lower()
        variable = category[0].lower() + category[1:]
        resource = root / f'Resources/{owner}.cs'
        command = root / f'Commands/{category}/{category}Set{plural}Command.cs'
        once(resource, f'{element}[] snapshot = {values}.ToArray();',
             f'{element}[] snapshot = ThreadedArrayPool<{element}>.Copy({values});')
        old = f'''            for (int i = 0; i < {values}.Length; i++)
            {{
                {values}[i] = (({wrapper}){values}[i])?.Base;
            }}

            {variable}.Base.Set{plural}(command._index, {values});'''
        new = f'''            try
            {{
                for (int i = 0; i < {values}.Length; i++)
                {{
                    {values}[i] = (({wrapper}){values}[i])?.Base;
                }}

                {variable}.Base.Set{plural}(command._index, {values});
            }}
            finally
            {{
                ThreadedArrayPool<{element}>.Return({values});
            }}'''
        once(command, old, new)
    pool.write_text(POOL_SOURCE)
    return [*(root / relative for relative in BASELINE), pool]
