using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;
using Ryujinx.Graphics.GAL;
using Silk.NET.Vulkan;

// Doubles for the delivered and final Vulkan TextureArray and ResourceArray, compiled whole. Silk structures keep the
// fields the arrays use; the Vulkan calls, the command buffers, the manual descriptor set cache of the pipeline layout and
// resource ownership are modelled in World, which checks every descriptor write and keeps the sets' contents.
namespace Ryujinx.Graphics.GAL
{
    public interface ITexture { }
    public interface ISampler { }
    public interface ITextureArray { }
    public enum ResourceType { UniformBuffer, StorageBuffer, Texture, Sampler, TextureAndSampler, Image, BufferTexture, BufferImage }
}

namespace Silk.NET.Vulkan
{
    public enum PipelineStageFlags { VertexShaderBit = 8, FragmentShaderBit = 128, ComputeShaderBit = 2048 }
    public enum AccessFlags { ShaderReadBit = 32 }
    public enum ImageLayout { Undefined = 0, General = 1 }
    public enum DescriptorType { Sampler = 0, CombinedImageSampler = 1, SampledImage = 2, StorageImage = 3, UniformTexelBuffer = 4, StorageTexelBuffer = 5 }
    public enum StructureType { WriteDescriptorSet = 35 }
    public struct ImageView { public ulong Handle; public ImageView(ulong handle) { Handle = handle; } }
    public struct Sampler { public ulong Handle; public Sampler(ulong handle) { Handle = handle; } }
    public struct BufferView { public ulong Handle; public BufferView(ulong handle) { Handle = handle; } }
    public struct DescriptorSet { public ulong Handle; public DescriptorSet(ulong handle) { Handle = handle; } }
    public struct Device { }
    public struct CopyDescriptorSet { }
    public struct DescriptorImageInfo
    {
        public Sampler Sampler;
        public ImageView ImageView;
        public ImageLayout ImageLayout;
    }
    public unsafe struct WriteDescriptorSet
    {
        public StructureType SType;
        public void* PNext;
        public DescriptorSet DstSet;
        public uint DstBinding;
        public uint DstArrayElement;
        public uint DescriptorCount;
        public DescriptorType DescriptorType;
        public DescriptorImageInfo* PImageInfo;
    }
}

namespace Ryujinx.Graphics.Vulkan
{
    public static class EncodingPolicy
    {
        public static bool BindingSizedDescriptorScratch { get; set; }
        public static bool IncrementalArrayDescriptors { get; set; }
    }

    static class RenderDetail
    {
        public static long ArrayWholeWrites, ArrayWholeElements, ArrayRangeWrites, ArrayRangeElements, ArrayElementsKept;
        public static long ArrayWriteTicks, ArrayReferencePasses, ArrayReferencesAdded, ArrayReferenceTicks;
        public static long ArrayCurrentBinds, ArraySlotsAdded, ArrayFallbacks;
        // Core 654 (adapt_artifact_counters): declared so the final TextureArray compiles; counted, not compared here.
        public static long ArrayDestroyedViewWalkElements, ArrayDestroyedViewRefreshElements;
    }

    static class RenderStageTimer
    {
        public static long Now() => System.Diagnostics.Stopwatch.GetTimestamp();
    }

    static class EnumConversion
    {
        public static DescriptorType Convert(this ResourceType type) => type switch
        {
            ResourceType.Sampler => DescriptorType.Sampler,
            ResourceType.Texture => DescriptorType.SampledImage,
            ResourceType.TextureAndSampler => DescriptorType.CombinedImageSampler,
            ResourceType.Image => DescriptorType.StorageImage,
            ResourceType.BufferTexture => DescriptorType.UniformTexelBuffer,
            ResourceType.BufferImage => DescriptorType.StorageTexelBuffer,
            _ => throw new ArgumentOutOfRangeException(nameof(type)),
        };
    }

    public readonly struct ResourceBindingSegment
    {
        public readonly int Binding;
        public readonly int Count;
        public readonly ResourceType Type;
        public readonly bool IsArray;

        public ResourceBindingSegment(int binding, int count, ResourceType type, bool isArray)
        {
            Binding = binding;
            Count = count;
            Type = type;
            IsArray = isArray;
        }
    }

    public struct CommandBufferScoped { public int CommandBufferIndex; }

    // Every Auto the fixture made; a completed command buffer ends its ownership of each.
    public interface IOwned
    {
        int Gets { get; }
        bool OwnedBy(int commandBuffer);
        void Release(int commandBuffer);
    }

    public sealed class Auto<T> : IOwned where T : IDisposable
    {
        private T _value;
        private readonly HashSet<int> _owners = new();
        public bool Destroyed { get; private set; }
        public int Gets { get; private set; }

        public Auto(T value)
        {
            _value = value;
            World.Owned.Add(this);
        }

        // As production: a destroyed object adds no command buffer dependency and gives its default value.
        public T Get(CommandBufferScoped cbs)
        {
            Gets++;

            if (!Destroyed)
            {
                _owners.Add(cbs.CommandBufferIndex);
            }

            return _value;
        }

        public T GetUnsafe() => _value;

        public bool OwnedBy(int commandBuffer) => _owners.Contains(commandBuffer);

        public void Release(int commandBuffer) => _owners.Remove(commandBuffer);

        // Production destroys an object only once no command buffer holds it.
        public void Destroy()
        {
            if (_owners.Count != 0)
            {
                throw new InvalidOperationException("destroyed while a command buffer holds it");
            }

            Destroyed = true;
            _value = default;
        }
    }

    public struct DisposableImageView : IDisposable
    {
        public ImageView Value;
        public void Dispose() { }
    }

    public struct DisposableSampler : IDisposable
    {
        public Silk.NET.Vulkan.Sampler Value;
        public void Dispose() { }
    }

    public sealed class TextureStorage
    {
        public int Barriers;
        public void QueueWriteToReadBarrier(CommandBufferScoped cbs, AccessFlags access, PipelineStageFlags stage) => Barriers++;
    }

    public sealed class TextureView : ITexture
    {
        public readonly TextureStorage Storage = new();
        public readonly Auto<DisposableImageView> View;
        public TextureView(ulong handle) { View = new(new DisposableImageView { Value = new ImageView(handle) }); }
        public Auto<DisposableImageView> GetImageView() => View;
    }

    public sealed class SamplerHolder : ISampler
    {
        public readonly Auto<DisposableSampler> Current;
        public SamplerHolder(ulong handle) { Current = new(new DisposableSampler { Value = new Silk.NET.Vulkan.Sampler(handle) }); }
        public Auto<DisposableSampler> GetSampler() => Current;
    }

    public sealed class TextureBuffer : ITexture
    {
        public ulong Handle;
        public BufferView GetBufferView(CommandBufferScoped cbs, bool write) => new(Handle);
    }

    public sealed class PipelineInternal
    {
        public int TextureDirty, ImageDirty;
        public void ForceTextureDirty() => TextureDirty++;
        public void ForceImageDirty() => ImageDirty++;
    }

    public sealed class CommandBufferPool
    {
        public readonly int[] Submissions = new int[16];
        public int GetSubmissionCount(int index) => Submissions[index];
    }

    public sealed class TestApi
    {
        public unsafe void UpdateDescriptorSets(Device device, uint count, WriteDescriptorSet* writes, uint copyCount, CopyDescriptorSet* copies)
        {
            if (copyCount != 0 || copies != null)
            {
                throw new InvalidOperationException("unexpected descriptor copies");
            }

            World.Calls++;

            for (uint index = 0; index < count; index++)
            {
                WriteDescriptorSet write = writes[index];

                if (write.SType != StructureType.WriteDescriptorSet || write.PNext != null || write.PImageInfo == null)
                {
                    throw new InvalidOperationException("unexpected descriptor write");
                }

                World.Write(write.DstSet.Handle, (int)write.DstBinding, write.DescriptorType, (int)write.DstArrayElement,
                    new ReadOnlySpan<DescriptorImageInfo>(write.PImageInfo, (int)write.DescriptorCount));
            }
        }
    }

    public sealed class VulkanRenderer
    {
        public readonly CommandBufferPool CommandBufferPool = new();
        public readonly PipelineInternal PipelineInternal = new();
        public readonly TestApi Api = new();
    }

    public sealed class DescriptorSetCollection : IDisposable
    {
        private readonly DescriptorSet[] _sets;
        public DescriptorSetCollection(DescriptorSet set) { _sets = new[] { set }; }
        public DescriptorSet[] GetSets() => _sets;
        public void Dispose() { }
    }

    // The manual descriptor sets of one pipeline layout (PipelineLayoutCacheEntry), shared by the programs of that layout:
    // an entry is held by the command buffers that took it until they complete, and free once no array uses it and no
    // command buffer holds it.
    public sealed class ManualSetCache
    {
        public sealed class Entry
        {
            public Auto<DescriptorSetCollection> Collection;
            public bool InUse;
            public readonly HashSet<int> Holders = new();
            public ulong Handle => Collection.GetUnsafe().GetSets()[0].Handle;
        }

        public readonly List<Entry> Entries = new();
        public readonly Queue<int> Free = new();
        public int Allocated, Released;

        public ManualSetCache() { World.Caches.Add(this); }

        public void Complete(int commandBuffer)
        {
            for (int index = 0; index < Entries.Count; index++)
            {
                Entry entry = Entries[index];

                if (entry.Holders.Remove(commandBuffer) && !entry.InUse && entry.Holders.Count == 0)
                {
                    Free.Enqueue(index);
                }
            }
        }
    }

    public sealed class DescriptorSetTemplate
    {
        public int Binding;
        public DescriptorType Type;
    }

    public sealed class ShaderCollection
    {
        public readonly DescriptorSetTemplate[] Templates = new DescriptorSetTemplate[8];
        public readonly ResourceBindingSegment[][] BindingSegments = new ResourceBindingSegment[8][];
        public readonly ManualSetCache Cache;

        public ShaderCollection(ManualSetCache cache, int setIndex, ResourceBindingSegment segment)
        {
            Cache = cache;

            for (int index = 0; index < BindingSegments.Length; index++)
            {
                BindingSegments[index] = Array.Empty<ResourceBindingSegment>();
            }

            BindingSegments[setIndex] = new[] { segment };
            Templates[setIndex] = new DescriptorSetTemplate { Binding = segment.Binding, Type = segment.Type.Convert() };
        }

        public Auto<DescriptorSetCollection> GetNewManualDescriptorSetCollection(CommandBufferScoped cbs, int setIndex, out int cacheIndex)
        {
            if (Cache.Free.TryDequeue(out cacheIndex))
            {
                ManualSetCache.Entry entry = Cache.Entries[cacheIndex];

                if (entry.InUse || entry.Holders.Count != 0 || World.IsBound(entry.Handle))
                {
                    World.Violate("a free manual set is still in use");
                }

                entry.InUse = true;
                entry.Holders.Add(cbs.CommandBufferIndex);

                return entry.Collection;
            }

            cacheIndex = Cache.Entries.Count;
            var created = new ManualSetCache.Entry { Collection = new(new DescriptorSetCollection(World.NewSet())), InUse = true };
            created.Holders.Add(cbs.CommandBufferIndex);
            Cache.Entries.Add(created);
            Cache.Allocated++;

            return created.Collection;
        }

        public void UpdateManualDescriptorSetCollectionOwnership(CommandBufferScoped cbs, int setIndex, int cacheIndex)
        {
            Cache.Entries[cacheIndex].Holders.Add(cbs.CommandBufferIndex);
        }

        public void ReleaseManualDescriptorSetCollection(int setIndex, int cacheIndex)
        {
            ManualSetCache.Entry entry = Cache.Entries[cacheIndex];
            entry.InUse = false;
            Cache.Released++;

            if (entry.Holders.Count == 0)
            {
                Cache.Free.Enqueue(cacheIndex);
            }
        }

        public bool IsManualDescriptorSetCollectionIdle(int setIndex, int cacheIndex) => Cache.Entries[cacheIndex].Holders.Count == 0;
    }

    public readonly struct DescriptorSetTemplateWriter
    {
        private readonly DescriptorSetTemplateUpdater _owner;
        public DescriptorSetTemplateWriter(DescriptorSetTemplateUpdater owner) { _owner = owner; }
        public void Push<T>(ReadOnlySpan<T> values) where T : unmanaged => _owner.Pushed(values);
    }

    // The template writes the pushed elements from the first one of the template's binding.
    public sealed class DescriptorSetTemplateUpdater
    {
        private DescriptorSetTemplate _template;
        private readonly List<DescriptorImageInfo> _images = new();

        public DescriptorSetTemplateWriter Begin(DescriptorSetTemplate template)
        {
            _template = template;
            _images.Clear();

            return new DescriptorSetTemplateWriter(this);
        }

        public void Pushed<T>(ReadOnlySpan<T> values) where T : unmanaged
        {
            if (typeof(T) != typeof(DescriptorImageInfo))
            {
                throw new InvalidOperationException("unexpected template data");
            }

            foreach (DescriptorImageInfo info in MemoryMarshal.Cast<T, DescriptorImageInfo>(values))
            {
                _images.Add(info);
            }
        }

        public void Commit(VulkanRenderer gd, Device device, DescriptorSet set)
        {
            World.TemplateCommits++;
            World.Write(set.Handle, _template.Binding, _template.Type, 0, CollectionsMarshal.AsSpan(_images));
        }
    }

    // The sets' contents, the command buffers that bound them and have not completed, and every write, hashed.
    public static class World
    {
        public static readonly List<IOwned> Owned = new();
        public static readonly List<ManualSetCache> Caches = new();
        public static readonly Dictionary<ulong, DescriptorImageInfo[]> Sets = new();
        private static readonly Dictionary<ulong, HashSet<int>> _bound = new();
        public static int Capacity;
        public static long Calls, TemplateCommits, Descriptors, Violations;
        public static string FirstViolation;
        public static ulong Trace = 14695981039346656037UL;
        private static ulong _nextSet = 100;

        public static void Record(ulong value) => Trace = unchecked((Trace ^ value) * 1099511628211UL);

        public static void Violate(string message)
        {
            Violations++;
            FirstViolation ??= message;
        }

        public static DescriptorSet NewSet()
        {
            ulong handle = _nextSet++;
            Sets[handle] = new DescriptorImageInfo[Capacity];

            return new DescriptorSet(handle);
        }

        public static bool IsBound(ulong set) => _bound.TryGetValue(set, out HashSet<int> holders) && holders.Count != 0;

        public static void Write(ulong set, int binding, DescriptorType type, int first, ReadOnlySpan<DescriptorImageInfo> values)
        {
            Descriptors += values.Length;
            Record(set);
            Record((ulong)binding);
            Record((ulong)type);
            Record((ulong)first);
            Record((ulong)values.Length);

            foreach (DescriptorImageInfo info in values)
            {
                Record(info.ImageView.Handle);
                Record(info.Sampler.Handle);
                Record((ulong)info.ImageLayout);
            }

            if (IsBound(set))
            {
                Violate("a set written while a pending command buffer uses it");
            }

            DescriptorImageInfo[] storage = Sets[set];

            if (first < 0 || first + values.Length > storage.Length)
            {
                Violate("a write outside the set");

                return;
            }

            values.CopyTo(storage.AsSpan(first));
        }

        public static void Bind(ulong set, int commandBuffer)
        {
            if (!_bound.TryGetValue(set, out HashSet<int> holders))
            {
                _bound[set] = holders = new HashSet<int>();
            }

            holders.Add(commandBuffer);
        }

        public static ManualSetCache.Entry Find(ulong set)
        {
            foreach (ManualSetCache cache in Caches)
            {
                foreach (ManualSetCache.Entry entry in cache.Entries)
                {
                    if (entry.Handle == set)
                    {
                        return entry;
                    }
                }
            }

            return null;
        }

        public static void Complete(int commandBuffer)
        {
            foreach (HashSet<int> holders in _bound.Values)
            {
                holders.Remove(commandBuffer);
            }

            foreach (IOwned owned in Owned)
            {
                owned.Release(commandBuffer);
            }

            foreach (ManualSetCache cache in Caches)
            {
                cache.Complete(commandBuffer);
            }
        }
    }
}
