namespace Ryujinx.Graphics.Vulkan
{
    // Final-source runs only (build 631): the encoding policy flags of PipelineBase.cs, which the test checks are declared
    // there with these names and without initializers, and the template fallback counters of the detail line.
    public static class EncodingPolicy
    {
        public static bool BindingSizedDescriptorScratch { get; set; }
        public static bool IncrementalArrayDescriptors { get; set; }
    }

    static class RenderDetail
    {
        public static readonly long[] TemplateFallbacks = new long[4];
    }
}
