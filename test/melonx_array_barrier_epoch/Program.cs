// Fixture of adapt_array_barrier_epoch. Production members spliced by melonx_array_barrier_epoch_test.py from one tree
// (control or candidate): TextureStorage's barrier state fields, AddStoreOpUsage, QueueLoadOpBarrier and
// QueueWriteToReadBarrier; TextureArray's storage set fields, SetTextures, SetDirty(bool) and QueueWriteToReadBarriers
// (and the candidate's BarrierText). Here: the renderer around them (the barrier batch records every queued barrier;
// the in-pass deferral decides as PipelineBase.TryDeferInPassReadBarrier does, with RenderPassHolder's forced fences
// inserted at each flush), views and images. A seeded script of render passes (attachments loaded at the begin, stored
// at the end), array passes for a stage, single-texture reads, flushes, element changes (another view of the same
// storage, another storage, none), disposals and command buffer changes; every queued barrier, deferral, feedback refusal
// and write-to-read note is logged with the final state of every storage.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Silk.NET.Vulkan;

namespace Ryujinx.Graphics.GAL
{
    public enum Format { R8G8B8A8Unorm, D32Float, D24UnormS8Uint }
    public interface ITexture { }
    public interface ITextureArray { }
}

namespace Ryujinx.Graphics.Vulkan
{
    using Format = Ryujinx.Graphics.GAL.Format;
    using ITexture = Ryujinx.Graphics.GAL.ITexture;
    using ITextureArray = Ryujinx.Graphics.GAL.ITextureArray;

    static class World
    {
        public static readonly List<string> Log = new();
        public static void Note(string line) => Log.Add(line);
    }

    static class EnumConversion
    {
        public static ImageAspectFlags ConvertAspectFlags(this Format format) => format switch
        {
            Format.D32Float => ImageAspectFlags.DepthBit,
            Format.D24UnormS8Uint => ImageAspectFlags.DepthBit | ImageAspectFlags.StencilBit,
            _ => ImageAspectFlags.ColorBit,
        };
    }

    struct CommandBufferScoped { public int CommandBufferIndex; }
    struct DisposableImage { public Image Value; }
    struct DisposableImageView : IDisposable { public ImageView Value; public void Dispose() { } }
    struct DisposableSampler : IDisposable { public Silk.NET.Vulkan.Sampler Value; public void Dispose() { } }

    sealed class Auto<T>
    {
        private readonly T _value;
        private readonly string _name;
        public Auto(T value, string name) { _value = value; _name = name; }
        public T Get(CommandBufferScoped cbs) { World.Note("ref " + _name + " cb" + cbs.CommandBufferIndex); return _value; }
    }

    struct TextureCreateInfo
    {
        public Format Format;
        public int Levels;
        public int Layers;
        public int GetLayers() => Layers;
    }

    static class RenderDetail
    {
        public static void NoteWriteToRead(PipelineStageFlags stages, bool later) => World.Note("note " + (int)stages + (later ? " later" : " first"));
    }

    sealed class RenderPassHolder
    {
        public readonly int Id;
        public readonly TextureStorage[] Attachments;
        public readonly bool[] Depth;
        private readonly List<(TextureStorage Texture, PipelineStageFlags StageFlags)> _forcedFences = new();

        public RenderPassHolder(int id, TextureStorage[] attachments, bool[] depth) { Id = id; Attachments = attachments; Depth = depth; }

        public bool ContainsAttachment(TextureStorage storage) => Array.IndexOf(Attachments, storage) >= 0;

        // RenderPassHolder.AddForcedFence: one entry per storage.
        public void AddForcedFence(TextureStorage storage, PipelineStageFlags stageFlags)
        {
            if (_forcedFences.Any(f => f.Texture == storage)) return;
            _forcedFences.Add((storage, stageFlags));
        }

        // RenderPassHolder.InsertForcedFences (BarrierBatch.Flush with this holder).
        public void InsertForcedFences(CommandBufferScoped cbs)
        {
            for (int i = 0; i < _forcedFences.Count; i++)
            {
                if (_forcedFences[i].Texture.Disposed) { _forcedFences.RemoveAt(i--); continue; }
                _forcedFences[i].Texture.QueueWriteToReadBarrier(cbs, AccessFlags.ShaderReadBit, _forcedFences[i].StageFlags);
            }
        }
    }

    sealed class PipelineInternal
    {
        public VulkanRenderer Gd;
        public bool DeferPolicy, IsTBDR, RenderPassActive;
        public RenderPassHolder Holder;

        // PipelineBase.TryDeferInPassReadBarrier.
        internal bool TryDeferInPassReadBarrier(TextureStorage storage, PipelineStageFlags dstStageFlags)
        {
            if (!DeferPolicy || !RenderPassActive || !Gd.IsMoltenVk || !IsTBDR || Holder == null || !Gd.MoltenVkTracksArgumentBufferHazards)
            {
                return false;
            }

            if (Holder.ContainsAttachment(storage))
            {
                World.Note("feedback s" + storage.Id);
                return false;
            }

            Holder.AddForcedFence(storage, dstStageFlags);
            World.Note("deferred s" + storage.Id + " " + (int)dstStageFlags);
            return true;
        }

        public void ForceTextureDirty() { }
        public void ForceImageDirty() { }
    }

    sealed class BarrierBatch
    {
        public void QueueBarrier(ImageMemoryBarrier barrier, TextureStorage resource, PipelineStageFlags srcStageFlags, PipelineStageFlags dstStageFlags)
        {
            World.Note($"barrier s{resource.Id} {(int)barrier.SrcAccessMask}->{(int)barrier.DstAccessMask} {(int)srcStageFlags}->{(int)dstStageFlags} aspect {(int)barrier.SubresourceRange.AspectMask} layers {barrier.SubresourceRange.LayerCount} levels {barrier.SubresourceRange.LevelCount}");
        }
    }

    sealed class VulkanRenderer
    {
        public PipelineInternal PipelineInternal;
        public readonly BarrierBatch Barriers = new();
        public bool IsMoltenVk;
        internal bool MoltenVkTracksArgumentBufferHazards;
    }

    sealed class TextureBuffer : ITexture { }

    sealed class TextureView : ITexture
    {
        private readonly Auto<DisposableImageView> _view;
        public TextureStorage Storage { get; }
        public TextureView(TextureStorage storage, string name) { Storage = storage; _view = new Auto<DisposableImageView>(default, name); }
        public Auto<DisposableImageView> GetImageView() => _view;

        // TextureView.GetImageBarrier, the fields a barrier is logged with.
        public static ImageMemoryBarrier GetImageBarrier(Image image, AccessFlags srcAccessMask, AccessFlags dstAccessMask,
            ImageAspectFlags aspectFlags, int firstLayer, int firstLevel, int layers, int levels)
        {
            return new()
            {
                SrcAccessMask = srcAccessMask,
                DstAccessMask = dstAccessMask,
                Image = image,
                SubresourceRange = new ImageSubresourceRange(aspectFlags, (uint)firstLevel, (uint)levels, (uint)firstLayer, (uint)layers),
            };
        }
    }

    sealed class TextureStorage
    {
        public readonly int Id;
        private readonly VulkanRenderer _gd;
        private readonly Auto<DisposableImage> _imageAuto;
        private TextureCreateInfo _info;
        public TextureCreateInfo Info => _info;
        public bool Disposed { get; set; }

        public TextureStorage(int id, VulkanRenderer gd, Format format, int levels, int layers)
        {
            Id = id;
            _gd = gd;
            _imageAuto = new Auto<DisposableImage>(new DisposableImage { Value = new Image((ulong)(id + 1)) }, "s" + id);
            _info = new TextureCreateInfo { Format = format, Levels = levels, Layers = layers };
        }

        public string State() =>
            $"s{Id} m {(int)_lastModificationAccess}/{(int)_lastModificationStage} r {(int)_lastReadAccess}/{(int)_lastReadStage} " +
            $"c {(int)_readCoverageAccess}/{(int)_readCoverageStage}/{(int)_readCoveredStages} d {(Disposed ? 1 : 0)}";

//__STORAGE_FIELDS__
//__STORAGE_METHODS__
    }

    class ResourceArray
    {
        protected void SetDirty(VulkanRenderer gd, bool isImage) { }
    }

    sealed class TextureArray : ResourceArray, ITextureArray
    {
        private readonly VulkanRenderer _gd;
        private readonly TextureView[] _views;
        private readonly TextureBuffer[] _bufferTextureRefs;
        private readonly bool _isBuffer;
        private readonly bool _incremental; // EncodingPolicy.IncrementalArrayDescriptors off: the element references are not counted
        private bool _referencesInvalid = true;
        private Dictionary<Auto<DisposableImageView>, int> _viewReferences;
        private List<Auto<DisposableImageView>> _newViewReferences;
        private const int LargeChange = 4096;
        private int _cachedCommandBufferIndex;

        public TextureArray(VulkanRenderer gd, int size) { _gd = gd; _views = new TextureView[size]; }

        private static void SwapReference<T>(Dictionary<Auto<T>, int> counts, Auto<T> previous, Auto<T> current, ref List<Auto<T>> added)
            where T : IDisposable => throw new InvalidOperationException("references are not counted in this fixture");

        private void RecordChange(int start, int count) => throw new InvalidOperationException("no change log in this fixture");

        public int Length => _views.Length;

//__ARRAY_FIELDS__
//__ARRAY_METHODS__
    }
}

public static class Program
{
    private static readonly PipelineStageFlags[] Stages =
    {
        PipelineStageFlags.FragmentShaderBit, PipelineStageFlags.VertexShaderBit, PipelineStageFlags.ComputeShaderBit,
        PipelineStageFlags.FragmentShaderBit, PipelineStageFlags.FragmentShaderBit,
    };

    public static int Main(string[] args)
    {
        int seed = int.Parse(args[0]);
        int operations = int.Parse(args[1]);
        string logPath = args[2];
        bool moltenVk = args[3][0] == '1', tracks = args[3][1] == '1', defer = args[3][2] == '1';
        var random = new Random(seed);
        var gd = new Ryujinx.Graphics.Vulkan.VulkanRenderer { IsMoltenVk = moltenVk, MoltenVkTracksArgumentBufferHazards = tracks };
        var pipeline = new Ryujinx.Graphics.Vulkan.PipelineInternal { Gd = gd, DeferPolicy = defer, IsTBDR = true };
        gd.PipelineInternal = pipeline;

        const int StorageCount = 64;
        var storages = new Ryujinx.Graphics.Vulkan.TextureStorage[StorageCount];
        var views = new List<Ryujinx.Graphics.Vulkan.TextureView>[StorageCount];
        for (int i = 0; i < StorageCount; i++)
        {
            var format = i % 9 == 0 ? Ryujinx.Graphics.GAL.Format.D32Float : i % 13 == 0 ? Ryujinx.Graphics.GAL.Format.D24UnormS8Uint : Ryujinx.Graphics.GAL.Format.R8G8B8A8Unorm;
            storages[i] = new Ryujinx.Graphics.Vulkan.TextureStorage(i, gd, format, 1 + i % 4, 1 + i % 3);
            views[i] = new List<Ryujinx.Graphics.Vulkan.TextureView> { new(storages[i], "v" + i + "a"), new(storages[i], "v" + i + "b") };
        }

        var holders = new List<Ryujinx.Graphics.Vulkan.RenderPassHolder>();
        for (int i = 0; i < 10; i++)
        {
            int colors = 1 + random.Next(2);
            var attachments = new List<Ryujinx.Graphics.Vulkan.TextureStorage>();
            var depth = new List<bool>();
            for (int c = 0; c < colors; c++) { attachments.Add(storages[random.Next(StorageCount)]); depth.Add(false); }
            if (random.Next(2) == 0) { attachments.Add(storages[random.Next(StorageCount)]); depth.Add(true); }
            holders.Add(new Ryujinx.Graphics.Vulkan.RenderPassHolder(i, attachments.ToArray(), depth.ToArray()));
        }

        var arrays = new[] { new Ryujinx.Graphics.Vulkan.TextureArray(gd, 8), new Ryujinx.Graphics.Vulkan.TextureArray(gd, 64), new Ryujinx.Graphics.Vulkan.TextureArray(gd, 512) };
        Ryujinx.Graphics.Vulkan.TextureView RandomView()
        {
            int pick = random.Next(20);
            if (pick == 0) return null;
            var list = views[random.Next(StorageCount)];
            return list[random.Next(list.Count)];
        }
        foreach (var array in arrays)
        {
            var textures = new Ryujinx.Graphics.GAL.ITexture[array.Length];
            for (int i = 0; i < textures.Length; i++) textures[i] = RandomView();
            array.SetTextures(0, textures);
        }

        var cbs = new Ryujinx.Graphics.Vulkan.CommandBufferScoped { CommandBufferIndex = 0 };
        Ryujinx.Graphics.Vulkan.RenderPassHolder active = null;
        var counts = new Dictionary<string, int>();
        void Count(string name) => counts[name] = counts.TryGetValue(name, out int n) ? n + 1 : 1;

        for (int op = 0; op < operations; op++)
        {
            Ryujinx.Graphics.Vulkan.World.Note("op " + op);
            int roll = random.Next(100);
            if (roll < 8)
            {
                if (active != null) continue;
                // PipelineBase.BeginRenderPass: FramebufferParams.InsertLoadOpBarriers, then the pass is active.
                active = holders[random.Next(holders.Count)];
                for (int i = 0; i < active.Attachments.Length; i++) active.Attachments[i].QueueLoadOpBarrier(cbs, active.Depth[i]);
                pipeline.RenderPassActive = true;
                pipeline.Holder = active;
                Count("begin");
            }
            else if (roll < 15)
            {
                if (active == null) continue;
                // PipelineBase.EndRenderPass: FramebufferParams.AddStoreOpUsage.
                for (int i = 0; i < active.Attachments.Length; i++) active.Attachments[i].AddStoreOpUsage(active.Depth[i]);
                pipeline.RenderPassActive = false;
                active = null;
                Count("end");
            }
            else if (roll < 55)
            {
                var array = arrays[random.Next(arrays.Length)];
                array.QueueWriteToReadBarriers(cbs, Stages[random.Next(Stages.Length)]);
                Count("arrayPass");
            }
            else if (roll < 67)
            {
                // A single texture read (TextureView.PrepareForUsage) or another array's storage read.
                storages[random.Next(StorageCount)].QueueWriteToReadBarrier(cbs, AccessFlags.ShaderReadBit, Stages[random.Next(Stages.Length)]);
                Count("directRead");
            }
            else if (roll < 77)
            {
                active?.InsertForcedFences(cbs);
                Count("flush");
            }
            else if (roll < 91)
            {
                var array = arrays[random.Next(arrays.Length)];
                int count = 1 + random.Next(Math.Min(6, array.Length));
                int start = random.Next(array.Length - count + 1);
                var textures = new Ryujinx.Graphics.GAL.ITexture[count];
                for (int i = 0; i < count; i++) textures[i] = RandomView();
                array.SetTextures(start, textures);
                Count("setTextures");
            }
            else if (roll < 98)
            {
                cbs = new Ryujinx.Graphics.Vulkan.CommandBufferScoped { CommandBufferIndex = (cbs.CommandBufferIndex + 1) % 4 };
                Count("commandBuffer");
            }
            else
            {
                storages[random.Next(StorageCount)].Disposed = true;
                Count("dispose");
            }
        }

        foreach (var storage in storages) Ryujinx.Graphics.Vulkan.World.Note(storage.State());

        var log = Ryujinx.Graphics.Vulkan.World.Log;
        File.WriteAllLines(logPath, log);
        string digest = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(string.Join("\n", log))));
        var report = new Dictionary<string, object>
        {
            ["seed"] = seed, ["operations"] = operations, ["config"] = args[3], ["logLines"] = log.Count, ["logSha256"] = digest,
            ["barriers"] = log.Count(l => l.StartsWith("barrier ")), ["deferred"] = log.Count(l => l.StartsWith("deferred ")),
            ["counts"] = counts,
        };
        // The candidate's window counters (absent from the control).
        var arrayType = typeof(Ryujinx.Graphics.Vulkan.TextureArray);
        foreach (string name in new[] { "_barrierPasses", "_barrierSkips", "_barrierStorages", "_barrierRebuilds" })
        {
            FieldInfo field = arrayType.GetField(name, BindingFlags.NonPublic | BindingFlags.Static);
            if (field != null) report[name.TrimStart('_')] = (long)field.GetValue(null);
        }
        MethodInfo text = arrayType.GetMethod("BarrierText", BindingFlags.NonPublic | BindingFlags.Static);
        if (text != null) report["barrierText"] = (string)text.Invoke(null, null);
        Console.WriteLine(JsonSerializer.Serialize(report));
        return 0;
    }
}
