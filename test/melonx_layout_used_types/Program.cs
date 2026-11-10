using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Gpu;
using Ryujinx.Graphics.Gpu.Shader;
using Ryujinx.Graphics.Shader;

// Runs the prepared tree's ShaderInfoBuilder (BuildForCache, as a program created or loaded from the cache) for each
// program of the input JSON ({"name", "stages": [{"stage": "Vertex"|"Fragment", "cbuffers": [[set, binding]],
// "sbuffers": [...], "textures": [[set, binding, dim, arrayLength, separate(0/1)]], "images": [...]}]}) and writes one
// layout file per program: "set binding vkDescriptorType count vkShaderStageFlags" per descriptor (the Vulkan backend's
// conversions: EnumConversion.Convert of ResourceType and ResourceStages).
static class Program
{
    static SamplerType Sampler(int dim, bool array) => (dim switch
    {
        0 => SamplerType.Texture1D, 1 => SamplerType.Texture2D, 2 => SamplerType.Texture3D, 3 => SamplerType.TextureCube,
        5 => SamplerType.TextureBuffer, _ => throw new ArgumentException("dim " + dim),
    }) | (array ? SamplerType.Array : SamplerType.None);

    static int Vk(ResourceType type) => type switch
    {
        ResourceType.Sampler => 0, ResourceType.TextureAndSampler => 1, ResourceType.Texture => 2, ResourceType.Image => 3,
        ResourceType.BufferTexture => 4, ResourceType.BufferImage => 5, ResourceType.UniformBuffer => 6, ResourceType.StorageBuffer => 7,
        _ => throw new ArgumentException(type.ToString()),
    };

    static int VkStages(ResourceStages stages)
    {
        int flags = 0;
        if (stages.HasFlag(ResourceStages.Vertex)) flags |= 1;
        if (stages.HasFlag(ResourceStages.TessellationControl)) flags |= 2;
        if (stages.HasFlag(ResourceStages.TessellationEvaluation)) flags |= 4;
        if (stages.HasFlag(ResourceStages.Geometry)) flags |= 8;
        if (stages.HasFlag(ResourceStages.Fragment)) flags |= 16;
        if (stages.HasFlag(ResourceStages.Compute)) flags |= 32;
        return flags;
    }

    static TextureDescriptor[] Textures(JsonElement list, bool image) => list.EnumerateArray().Select(t =>
    {
        int[] v = t.EnumerateArray().Select(x => x.GetInt32()).ToArray();
        bool separate = v[4] != 0;
        SamplerType type = v[2] == -1 ? SamplerType.None : Sampler(v[2], false);
        return new TextureDescriptor(v[0], v[1], type, TextureFormat.Unknown, 0, 0, v[3], separate,
            image ? TextureUsageFlags.ImageStore : TextureUsageFlags.None);
    }).ToArray();

    static BufferDescriptor[] Buffers(JsonElement list) =>
        list.EnumerateArray().Select(b => new BufferDescriptor(b[0].GetInt32(), b[1].GetInt32(), 0)).ToArray();

    static void Main(string[] args)
    {
        using JsonDocument input = JsonDocument.Parse(File.ReadAllText(args[0]));
        Directory.CreateDirectory(args[1]);
        int programs = 0;
        foreach (JsonElement program in input.RootElement.EnumerateArray())
        {
            var stages = new List<CachedShaderStage>();
            foreach (JsonElement stage in program.GetProperty("stages").EnumerateArray())
            {
                ShaderStage kind = Enum.Parse<ShaderStage>(stage.GetProperty("stage").GetString());
                stages.Add(new CachedShaderStage
                {
                    Info = new ShaderProgramInfo(Buffers(stage.GetProperty("cbuffers")), Buffers(stage.GetProperty("sbuffers")),
                        Textures(stage.GetProperty("textures"), false), Textures(stage.GetProperty("images"), true),
                        kind, 0, 0, 0, false, false, false, false, 0, kind == ShaderStage.Fragment ? 1 : 0),
                });
            }

            ShaderInfo info = ShaderInfoBuilder.BuildForCache(new GpuContext(), stages, null, tfEnabled: false);
            var lines = new List<string>();
            for (int set = 0; set < info.ResourceLayout.Sets.Count; set++)
            {
                foreach (ResourceDescriptor d in info.ResourceLayout.Sets[set].Descriptors.OrderBy(d => d.Binding))
                {
                    lines.Add($"{set} {d.Binding} {Vk(d.Type)} {d.Count} {VkStages(d.Stages)}");
                }
            }

            File.WriteAllLines(Path.Combine(args[1], program.GetProperty("name").GetString() + ".l"), lines);
            programs++;
        }

        Console.WriteLine(JsonSerializer.Serialize(new { programs }));
    }
}
