using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;

bool control = args[0] == "control";
int checks = 0;
void Check(bool value, string message)
{
    checks++;
    if (!value) throw new Exception(message);
}
var gd = new VulkanRenderer();
var cbs = new CommandBufferScoped { CommandBufferIndex = 3 };
var a = new TextureStorage(1);
var b = new TextureStorage(2);
var av = new TextureView(a, 11);
var bv = new TextureView(b, 12);
var dummy = new TextureView(new TextureStorage(999), 999);
var defaultSampler = new SamplerHolder(100);
var sampler = new SamplerHolder(101);
var array = new TextureArray(gd, 8, false);
array.IncrementBindCount();
array.SetTextures(1, new ITexture[] { av, null, av, bv });
array.SetSamplers(1, new ISampler[] { sampler });
int dirtyCalls = gd.PipelineInternal.TextureDirtyCalls;
array.QueueWriteToReadBarriers(cbs, PipelineStageFlags.VertexShaderBit);
Check(a.Barriers == 1 && b.Barriers == 1, "Distinct storage barriers, including aliased views");
array.QueueWriteToReadBarriers(cbs, PipelineStageFlags.FragmentShaderBit);
Check(a.Barriers == 2 && b.Barriers == 2 && a.LastStage == PipelineStageFlags.FragmentShaderBit,
      "A cached storage list must still queue barriers for each draw/stage");
var info = array.GetImageInfos(gd, cbs, dummy, defaultSampler);
Check(info.Length == 8 && info[0].ImageView.Handle == 999 && info[1].ImageView.Handle == 11 &&
      info[2].ImageView.Handle == 999 && info[3].ImageView.Handle == 11 && info[4].ImageView.Handle == 12,
      "Offsets, duplicate views and null fallback");
Check(info[1].Sampler.Handle == 101 && info[2].Sampler.Handle == 100, "Sampler and null fallback");
int retainedBefore = av.ImageView.Gets;
array.GetImageInfos(gd, cbs, dummy, defaultSampler);
Check(av.ImageView.Gets == retainedBefore, "Same command buffer descriptor cache");
gd.CommandBufferPool.Submission++;
array.GetImageInfos(gd, cbs, dummy, defaultSampler);
Check(av.ImageView.Gets > retainedBefore, "New submission must acquire resource ownership again");

long hashBefore = TextureStorage.HashCalls;
var program = new ShaderCollection();
var updater = new DescriptorSetTemplateUpdater();
var firstSets = array.GetDescriptorSets(default, cbs, updater, program, 0, dummy, defaultSampler);
var retainedSets = array.GetDescriptorSets(default, cbs, updater, program, 0, dummy, defaultSampler);
Check(ReferenceEquals(firstSets, retainedSets) && program.NewSets == 1 && program.OwnershipUpdates == 1,
      "Real ResourceArray reuses descriptors and transfers current-buffer ownership");
array.SetSamplers(1, new ISampler[] { new SamplerHolder(102) });
array.QueueWriteToReadBarriers(cbs, PipelineStageFlags.FragmentShaderBit);
Check(gd.PipelineInternal.TextureDirtyCalls == dirtyCalls + 1 && program.Releases == 1,
      "Sampler updates still release descriptors and mark the bound pipeline dirty");
var changedSets = array.GetDescriptorSets(default, cbs, updater, program, 0, dummy, defaultSampler);
Check(!ReferenceEquals(firstSets, changedSets) && program.NewSets == 2,
      "Changed sampler receives a fresh descriptor set");
Check(TextureStorage.HashCalls - hashBefore == (control ? 3 : 0),
      "Only texture updates rebuild storage deduplication");
Check(array.GetImageInfos(gd, cbs, dummy, defaultSampler)[1].Sampler.Handle == 102,
      "Changed sampler is visible within the same command buffer");
array.SetSamplers(1, new ISampler[] { new SamplerHolder(103) { Fail = true } });
Check(array.GetImageInfos(gd, cbs, dummy, defaultSampler)[1].Sampler.Handle == 100,
      "Failing sampler preserves the existing default fallback");
hashBefore = TextureStorage.HashCalls;
array.SetTextures(1, new ITexture[] { new TextureView(a, 111) });
array.QueueWriteToReadBarriers(cbs, PipelineStageFlags.VertexShaderBit);
Check(TextureStorage.HashCalls - hashBefore == (control ? 3 : 0),
      "Another view of identical storage keeps the storage set");
Check(array.GetImageInfos(gd, cbs, dummy, defaultSampler)[1].ImageView.Handle == 111,
      "New view of identical storage still updates descriptors");

array.SetTextures(1, new ITexture[] { null, null, null, bv });
array.SetTextures(4, new ITexture[] { bv }); // No-change update must retain pending invalidation.
array.SetSamplers(1, new ISampler[] { sampler });
var setField = typeof(TextureArray).GetField("_storages", BindingFlags.NonPublic | BindingFlags.Instance);
var retainedSet = (HashSet<TextureStorage>)setField.GetValue(array);
Check(retainedSet == null || retainedSet.Count == 0, "Removed textures released before another draw");
int aBefore = a.Barriers, bBefore = b.Barriers;
array.QueueWriteToReadBarriers(cbs, PipelineStageFlags.FragmentShaderBit);
Check(a.Barriers == aBefore && b.Barriers == bBefore + 1, "Removed storage never receives a stale barrier");
Check(array.GetImageInfos(gd, cbs, dummy, defaultSampler)[1].ImageView.Handle == 999,
      "Texture update invalidates image infos");
array.SetTextures(0, new ITexture[8]);
array.QueueWriteToReadBarriers(cbs, PipelineStageFlags.VertexShaderBit);
Check(b.Barriers == bBefore + 1, "Empty update drops every storage");

var images = new ImageArray(gd, 5, false);
images.IncrementBindCount();
images.SetImages(1, new ITexture[] { av, av, null, bv });
var imageProgram = new ShaderCollection();
images.GetDescriptorSets(default, cbs, updater, imageProgram, 0, dummy);
int imageDirty = gd.PipelineInternal.ImageDirtyCalls;
aBefore = a.Barriers; bBefore = b.Barriers;
images.QueueWriteToReadBarriers(cbs, PipelineStageFlags.ComputeShaderBit);
Check(a.Barriers == aBefore + 1 && b.Barriers == bBefore + 1, "Image array deduplicates aliased storage");
Check(images.GetImageInfos(gd, cbs, dummy)[1].ImageView.Handle == 1011,
      "Images preserve identity-view descriptor selection");
images.SetImages(1, new ITexture[] { null, null });
images.SetImages(4, new ITexture[] { bv }); // An unchanged trailing update cannot clear dirty.
Check(imageProgram.Releases == 1 && gd.PipelineInternal.ImageDirtyCalls == imageDirty + 2,
      "Image changes release the old descriptor and dirty the bound image state");
var imageSet = (HashSet<TextureStorage>)typeof(ImageArray).GetField("_storages",
    BindingFlags.NonPublic | BindingFlags.Instance).GetValue(images);
Check(imageSet == null || imageSet.Count == 0, "Removed images released without requiring a draw");
images.QueueWriteToReadBarriers(cbs, PipelineStageFlags.ComputeShaderBit);
Check(a.Barriers == aBefore + 1 && b.Barriers == bBefore + 2, "Image update rebuilds the exact live set");
Check(images.GetImageInfos(gd, cbs, dummy)[1].ImageView.Handle == 999,
      "Removed image preserves the existing dummy-view fallback");

var buffers = new TextureArray(gd, 2, true);
var buffer = new TextureBuffer { Handle = 77 };
buffers.SetTextures(0, new ITexture[] { buffer, null });
Check(buffers.GetBufferViews(cbs)[0].Handle == 77, "Buffer texture path retained");
buffer.Handle = 78;
Check(buffers.GetBufferViews(cbs)[0].Handle == 78, "Changed buffer storage remains dynamic");
var bufferImages = new ImageArray(gd, 2, true);
bufferImages.SetImages(0, new ITexture[] { buffer, null });
Check(bufferImages.GetBufferViews(cbs)[0].Handle == 78 && buffer.LastWrite,
      "Buffer images preserve write access");

var measurements = new List<object>();
foreach (int length in new[] { 256, 1024, 4096 })
{
    ITexture[] bindings = Enumerable.Range(0, length)
        .Select(i => (ITexture)new TextureView(new TextureStorage(10000 + i), (ulong)i + 1)).ToArray();
    var large = new TextureArray(gd, length, false);
    var largeImages = new ImageArray(gd, length, false);
    ISampler[] oneSampler = { sampler };
    large.SetTextures(0, bindings);
    largeImages.SetImages(0, bindings);
    large.QueueWriteToReadBarriers(cbs, PipelineStageFlags.FragmentShaderBit);
    largeImages.QueueWriteToReadBarriers(cbs, PipelineStageFlags.ComputeShaderBit);
    const int repetitions = 256;
    hashBefore = TextureStorage.HashCalls;
    long bytes = GC.GetAllocatedBytesForCurrentThread();
    for (int i = 0; i < repetitions; i++)
    {
        large.SetSamplers(0, oneSampler);
        large.QueueWriteToReadBarriers(cbs, PipelineStageFlags.FragmentShaderBit);
    }
    long samplerAllocated = GC.GetAllocatedBytesForCurrentThread() - bytes;
    long samplerHashInsertions = TextureStorage.HashCalls - hashBefore;
    Check(samplerHashInsertions == (control ? (long)repetitions * length : 0),
          "Sampler-only bindless update must retain the storage set");
    Check(control ? samplerAllocated > 0 : samplerAllocated == 0,
          "Steady sampler path allocation count");
    hashBefore = TextureStorage.HashCalls;
    bytes = GC.GetAllocatedBytesForCurrentThread();
    for (int i = 0; i < repetitions; i++)
    {
        large.SetTextures(0, bindings);
        large.QueueWriteToReadBarriers(cbs, PipelineStageFlags.FragmentShaderBit);
        largeImages.SetImages(0, bindings);
        largeImages.QueueWriteToReadBarriers(cbs, PipelineStageFlags.ComputeShaderBit);
    }
    long resourceAllocated = GC.GetAllocatedBytesForCurrentThread() - bytes;
    long resourceHashInsertions = TextureStorage.HashCalls - hashBefore;
    Check(resourceHashInsertions == (control ? (long)repetitions * length * 2 : 0),
          "Unchanged storage arrays keep deduplication while still emitting all barriers");
    Check(control ? resourceAllocated > 0 : resourceAllocated == 0,
          "Stable-capacity texture and image updates reuse their set storage");
    foreach (TextureView view in bindings)
    {
        Check(view.Storage.Barriers == 2 + 3 * repetitions,
              "All required barriers survive both optimized update paths");
    }
    measurements.Add(new { length, repetitions, samplerAllocated, samplerHashInsertions, resourceAllocated, resourceHashInsertions });
}
Console.WriteLine(JsonSerializer.Serialize(new { mode = control ? "control" : "candidate", checks,
    measurements, physicalDeviceTested = false, vulkanCallsDoubled = true }));

namespace Ryujinx.Graphics.GAL
{
    public interface ITexture { }
    public interface ISampler { }
    public interface ITextureArray { }
    public interface IImageArray { }
}
namespace Silk.NET.Vulkan
{
    public enum PipelineStageFlags { VertexShaderBit, FragmentShaderBit, ComputeShaderBit }
    public enum AccessFlags { ShaderReadBit }
    public enum ImageLayout { General }
    public struct ImageView { public ulong Handle; }
    public struct Sampler { public ulong Handle; }
    public struct BufferView { public ulong Handle; }
    public struct DescriptorImageInfo { public ImageLayout ImageLayout; public ImageView ImageView; public Sampler Sampler; }
    public struct DescriptorSet { }
    public struct Device { }
}
namespace Ryujinx.Graphics.Vulkan
{
    public struct CommandBufferScoped { public int CommandBufferIndex; }
    public class TextureStorage
    {
        public static long HashCalls;
        public int Barriers;
        public PipelineStageFlags LastStage;
        private readonly int _id;
        public TextureStorage(int id) => _id = id;
        public override int GetHashCode() { HashCalls++; return _id; }
        public void QueueWriteToReadBarrier(CommandBufferScoped cbs, AccessFlags access, PipelineStageFlags stage)
        { Barriers++; LastStage = stage; }
    }
    public class Auto<T>
    {
        private readonly T _value;
        public int Gets;
        public Auto(T value) => _value = value;
        public T Get(CommandBufferScoped cbs) { Gets++; return _value; }
    }
    public struct DisposableImageView { public ImageView Value; }
    public struct DisposableSampler { public Silk.NET.Vulkan.Sampler Value; }
    public class TextureView : ITexture
    {
        public TextureStorage Storage;
        public readonly Auto<DisposableImageView> ImageView;
        private readonly Auto<DisposableImageView> _identityView;
        public TextureView(TextureStorage storage, ulong handle)
        {
            Storage = storage;
            ImageView = new(new DisposableImageView { Value = new ImageView { Handle = handle } });
            _identityView = new(new DisposableImageView { Value = new ImageView { Handle = handle + 1000 } });
        }
        public Auto<DisposableImageView> GetImageView() => ImageView;
        public Auto<DisposableImageView> GetIdentityImageView() => _identityView;
    }
    public class SamplerHolder : ISampler
    {
        private readonly Auto<DisposableSampler> _sampler;
        public bool Fail;
        public SamplerHolder(ulong handle) => _sampler = new(new DisposableSampler { Value = new Silk.NET.Vulkan.Sampler { Handle = handle } });
        public Auto<DisposableSampler> GetSampler()
        { if (Fail) throw new InvalidOperationException("sampler failure"); return _sampler; }
    }
    public class TextureBuffer : ITexture
    {
        public ulong Handle;
        public bool LastWrite;
        public BufferView GetBufferView(CommandBufferScoped cbs, bool write)
        { LastWrite = write; return new BufferView { Handle = Handle }; }
    }
    public class VulkanRenderer
    {
        public readonly CommandBufferPool CommandBufferPool = new();
        public readonly PipelineInternal PipelineInternal = new();
    }
    public class PipelineInternal
    {
        public int TextureDirtyCalls, ImageDirtyCalls;
        public void ForceTextureDirty() => TextureDirtyCalls++;
        public void ForceImageDirty() => ImageDirtyCalls++;
    }
    public class CommandBufferPool
    {
        public int Submission;
        public int GetSubmissionCount(int index) => Submission;
    }
    public class ShaderCollection
    {
        public DescriptorSetTemplate[] Templates = new DescriptorSetTemplate[1];
        public int NewSets, Releases, OwnershipUpdates;
        public Auto<DescriptorSetCollection> GetNewManualDescriptorSetCollection(CommandBufferScoped cbs, int setIndex, out int index)
        { index = NewSets++; return new(new DescriptorSetCollection()); }
        public void ReleaseManualDescriptorSetCollection(int setIndex, int index) => Releases++;
        public void UpdateManualDescriptorSetCollectionOwnership(CommandBufferScoped cbs, int setIndex, int index) => OwnershipUpdates++;
    }
    public class DescriptorSetCollection
    {
        private readonly DescriptorSet[] _sets = new DescriptorSet[1];
        public DescriptorSet[] GetSets() => _sets;
    }
    public class DescriptorSetTemplate { }
    public struct DescriptorSetTemplateWriter { public void Push<T>(ReadOnlySpan<T> value) { } }
    public class DescriptorSetTemplateUpdater
    {
        public DescriptorSetTemplateWriter Begin(DescriptorSetTemplate value) => default;
        public void Commit(VulkanRenderer gd, Device device, DescriptorSet set) { }
    }
}
