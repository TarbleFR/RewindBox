"""Process oversized direct uniform packets in bounded, scalar-equivalent batches.

The FIFO's existing complete-packet fast path can pass up to 8191 words, but
the updater has space for only 512. Keep the existing <=512-word path exactly
as before. Larger packets fill the current cache and flush at the same points
as individual Update(int) calls, using a span copy for each bounded batch.
Offset/address wrap and the zero-address sentinel retain the scalar path.
No FIFO register/shadow effects are bypassed by this adapter.
"""
import hashlib
from adapt_session import once


RELATIVE = 'src/Ryujinx.Graphics.Gpu/Engine/Threed/ConstantBufferUpdater.cs'
BASELINE = '6232f9d4520689f08b67549efdca9d812e3fbe83607d54445f518aa5fba44ffc'


def apply(source):
    path = source / RELATIVE
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE, str(path)
    once(path, '''        public void Update(ReadOnlySpan<int> data)
        {
            UniformBufferState uniformBuffer = _state.State.UniformBufferState;''', '''        public void Update(ReadOnlySpan<int> data)
        {
            if (data.Length > UniformDataCacheSize)
            {
                UpdateLarge(data);
                return;
            }

            UniformBufferState uniformBuffer = _state.State.UniformBufferState;''')
    once(path, '''            _state.State.UniformBufferState.Offset += data.Length * 4;
        }
''', '''            _state.State.UniformBufferState.Offset += data.Length * 4;
        }

        private void UpdateLarge(ReadOnlySpan<int> data)
        {
            while (!data.IsEmpty)
            {
                UniformBufferState uniformBuffer = _state.State.UniformBufferState;
                ulong baseAddress = uniformBuffer.Address.Pack();
                ulong offset = (uint)uniformBuffer.Offset;
                int count = Math.Min(data.Length, UniformDataCacheSize);
                if (_ubIndex < UniformDataCacheSize)
                {
                    count = Math.Min(count, UniformDataCacheSize - _ubIndex);
                }
                ulong byteCount = (ulong)count * 4;

                // Batch only inside an already-open, nonwrapping cache range.
                // A scalar word handles each flush/restart first, preserving
                // callbacks that change registers and the zero-address sentinel.
                if (_ubIndex >= UniformDataCacheSize || _ubFollowUpAddress == 0 ||
                    offset + byteCount > uint.MaxValue ||
                    baseAddress > ulong.MaxValue - offset ||
                    baseAddress + offset > ulong.MaxValue - byteCount ||
                    _ubFollowUpAddress != baseAddress + offset)
                {
                    Update(data[0]);
                    data = data.Slice(1);
                    continue;
                }

                Update(data.Slice(0, count));
                data = data.Slice(count);
            }
        }
''')
    return [path]
