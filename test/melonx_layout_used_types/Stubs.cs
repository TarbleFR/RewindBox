// Boundaries of ShaderInfoBuilder.cs (compiled from the prepared tree): the GPU context's capabilities as the Vulkan
// backend reports them (VulkanRenderer.GetCapabilities: sets 0-3, Constants 18/16/32/16), the async-compile switch and
// the cached stage type. GpuAccessorBase.GetStageIndex is the prepared tree's own method, inserted by the test driver.
using Ryujinx.Graphics.Shader;

namespace Ryujinx.Graphics.Gpu
{
    sealed class CapabilitiesBoundary
    {
        public int UniformBufferSetIndex = 0, StorageBufferSetIndex = 1, TextureSetIndex = 2, ImageSetIndex = 3;
        public bool SupportsTransformFeedback = true;
        public uint MaximumUniformBuffersPerStage = 18, MaximumStorageBuffersPerStage = 16, MaximumTexturesPerStage = 32, MaximumImagesPerStage = 16;
    }

    sealed class GpuContext
    {
        public CapabilitiesBoundary Capabilities = new();
    }

    static class GraphicsConfig
    {
        public static bool EnableAsyncShaderCompilation = false;
    }
}

namespace Ryujinx.Graphics.Gpu.Shader
{
    sealed class CachedShaderStage
    {
        public ShaderProgramInfo Info;
    }

    static partial class GpuAccessorBase
    {
    }
}
