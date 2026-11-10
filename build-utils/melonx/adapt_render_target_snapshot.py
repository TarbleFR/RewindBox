"""Release threaded render-target snapshots after consumption or a failed draw.

The static GAL array pool previously retained unwrapped backend textures after
each command. A conversion or backend exception also abandoned the rented
array. Preserve reference consumption and renderer-call order while returning
the private snapshot cleared from a finally block. No GAL ABI or backend API
changes, and no new allocation is introduced on the normal command path.
"""
import hashlib
from adapt_session import once


RELATIVE = 'src/Ryujinx.Graphics.GAL/Multithreading/Commands/SetRenderTargetsCommand.cs'
UPSTREAM = '0942f2702976e6cadac11cbf24a1cf955f7a28fb7b299d58982524774efec193'


def apply(source):
    command = source / RELATIVE
    assert hashlib.sha256(command.read_bytes()).hexdigest() == UPSTREAM, str(command)
    once(command, '''            Span<ITexture> colorsSpan = colors.AsSpan(0, command._colorsCount);

            for (int i = 0; i < colorsSpan.Length; i++)
            {
                colorsSpan[i] = ((ThreadedTexture)colorsSpan[i])?.Base;
            }
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
            renderer.Pipeline.SetRenderTargets(colorsSpan, command._depthStencil.GetAs<ThreadedTexture>(threaded)?.Base);
\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20\x20
            ArrayPool.Return(colors);''', '''            try
            {
                Span<ITexture> colorsSpan = colors.AsSpan(0, command._colorsCount);

                for (int i = 0; i < colorsSpan.Length; i++)
                {
                    colorsSpan[i] = ((ThreadedTexture)colorsSpan[i])?.Base;
                }

                renderer.Pipeline.SetRenderTargets(colorsSpan, command._depthStencil.GetAs<ThreadedTexture>(threaded)?.Base);
            }
            finally
            {
                // Neither the pool nor a failed command should retain backend
                // texture graphs after the snapshot's synchronous consumption.
                ArrayPool.Return(colors, clearArray: true);
            }''')
    return [command]
