"""Match speculative vertex strides to the draw path's real buffer bindings.

Vulkan binding zero is the synthetic zero buffer; ProgramPipelineState's buffer
indices do not include it. The old upper-bound test excluded the final real
buffer, and unused real buffers retained scalar alignment zero. AlignUp(n, 0)
then produced stride zero on non-NVIDIA devices. The draw path treats zero
alignment as no rewrite, effectively alignment one: although VertexBufferState
constructors initialize one, PipelineBase's initially zeroed array and its
saved/restored previous alignment can retain zero. Explicit scalar attributes
replace that value when they are used. The converter's minimum one therefore
matches fresh unused bindings without changing draw-time state. Historically
used but now unused buffers can retain an older alignment; that remaining key
difference is outside this fix. Preserve formats, topology and cache equality.
"""
import hashlib
from adapt_session import once


BASELINE = '041966bf0cff2fa9e8d1743c8a53b93affca271b279586b25515623dee98b61b'


def apply(source):
    path = source / 'src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == BASELINE, str(path)
    once(path, '''            Span<int> vbScalarSizes = stackalloc int[vbCount];
''', '''            Span<int> vbScalarSizes = stackalloc int[vbCount];
            // VertexBufferState starts at scalar alignment one, including
            // enabled buffers that no vertex attribute references.
            vbScalarSizes.Fill(1);
''')
    once(path, '''                if (!attribute.IsZero && bufferIndex < vbCount)
                {
                    vbScalarSizes[bufferIndex - 1] = Math.Max(attribute.Format.ScalarSize, vbScalarSizes[bufferIndex - 1]);
                }''', '''                if (!attribute.IsZero && (uint)attribute.BufferIndex < (uint)vbCount)
                {
                    int rawIndex = attribute.BufferIndex;
                    vbScalarSizes[rawIndex] = Math.Max(attribute.Format.ScalarSize, vbScalarSizes[rawIndex]);
                }''')
    return [path]
