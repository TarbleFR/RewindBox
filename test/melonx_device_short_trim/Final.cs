// Plan 748 rank 11 (adapt_device_critical_trim): the members of the final preparation's AutoDeleteCache.cs (with
// adapt_short_cache_reuse's retained list) reads beyond the 631 doubles of Program.cs. Compiled only for the final variant.
namespace Ryujinx.Graphics.GAL
{
    enum Target { Texture2D, TextureBuffer }
}

namespace Ryujinx.Graphics.Gpu.Image
{
    partial class Texture
    {
        public Ryujinx.Graphics.GAL.Target Target => Ryujinx.Graphics.GAL.Target.Texture2D;
        public bool ChangedMapping;
    }
}
