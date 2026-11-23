// Recording GAL double: no GPU. Every renderer, pipeline and resource call the production GPU code makes is mixed, in
// order and with its arguments (objects by creation number, buffers by handle, data by content), into one running hash
// and counted per kind. In verify mode the double also keeps every host buffer's bytes (SetBufferData, CopyBuffer,
// ClearBuffer) and, at each draw and dispatch, hashes the bytes of every bound uniform, storage, vertex and index range:
// the data that draw would read. Nothing here ships.
using Ryujinx.Common.Configuration;
using Ryujinx.Common.Memory;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Ryujinx.Graphics.Shader.Translation;
using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

public enum Op
{
    Barrier, BeginTransformFeedback, ClearBuffer, ClearRtColor, ClearRtDepth, CommandBufferBarrier, CopyBuffer, Dispatch, Draw,
    DrawIndexed, DrawIndexedIndirect, DrawIndexedIndirectCount, DrawIndirect, DrawIndirectCount, DrawTexture, EndTransformFeedback,
    SetAlphaTest, SetBlendStateAdvanced, SetBlendState, SetDepthBias, SetDepthClamp, SetDepthMode, SetDepthTest, SetFaceCulling,
    SetFrontFace, SetIndexBuffer, SetImage, SetImageArray, SetImageArraySeparate, SetLineParameters, SetLogicOpState,
    SetMultisampleState, SetPatchParameters, SetPointParameters, SetPolygonMode, SetPrimitiveRestart, SetPrimitiveTopology,
    SetProgram, SetRasterizerDiscard, SetRenderTargetColorMasks, SetRenderTargets, SetScissors, SetStencilTest, SetStorageBuffers,
    SetTextureAndSampler, SetTextureArray, SetTextureArraySeparate, SetTransformFeedbackBuffers, SetUniformBuffers,
    SetUserClipDistance, SetVertexAttribs, SetVertexBuffers, SetViewports, TextureBarrier, TextureBarrierTiled,
    TryHostConditionalRendering, EndHostConditionalRendering,
    CreateBuffer, CreateBufferHost, CreateBufferSparse, CreateImageArray, CreateProgram, CreateSampler, CreateTexture,
    CreateTextureArray, CreateSync, DeleteBuffer, GetBufferData, SetBufferData, UpdateCounters, PreFrame, ReportCounter,
    ResetCounter, WaitSync, TextureCopy, TextureCopyToBuffer, TextureView, TextureGetData, TextureSetData, TextureSetStorage,
    TextureRelease, SamplerDispose, ProgramDispose, ArraySetTextures, ArraySetSamplers, ArraySetImages, ArrayDispose,
    Count,
}

public static class Rec
{
    public const ulong Seed = 14695981039346656037UL;
    public static bool Verify;
    public static ulong Hash = Seed;
    public static ulong ContentHash = Seed;
    public static readonly long[] Counts = new long[(int)Op.Count];
    public static long DataBytes;
    public static int NextObject;
    public static ulong NextBuffer;
    public static readonly Dictionary<ulong, byte[]> Buffers = new();
    public static readonly Dictionary<int, BufferRange> Uniform = new(), Storage = new();
    public static readonly VertexBufferDescriptor[] Vertex = new VertexBufferDescriptor[32];
    public static BufferRange Index;
    public static RecProgram Program;
    // The uniform and storage bindings the current program declares (its resource layout).
    public static bool Uses(ResourceType type, int binding)
    {
        if (Program == null) return false;
        foreach (ResourceUsageCollection set in Program.Info.ResourceLayout.SetUsages)
        {
            foreach (ResourceUsage usage in set.Usages)
            {
                if (usage.Type == type && usage.Binding == binding) return true;
            }
        }
        return false;
    }
    public static readonly List<ulong> DrawHashes = new(), DrawContent = new();
    // Per draw: the bytes of every bound uniform range (verify mode), for the guest-memory oracle in Program.
    public static Action<int> OnDraw;

    public static void Reset(bool verify)
    {
        Verify = verify;
        Hash = Seed;
        ContentHash = Seed;
        Array.Clear(Counts);
        DataBytes = 0;
        NextObject = 0;
        NextBuffer = 0;
        Buffers.Clear();
        Uniform.Clear();
        Storage.Clear();
        Array.Clear(Vertex);
        Index = default;
        Program = null;
        DrawHashes.Clear();
        DrawContent.Clear();
    }

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static void Mix(ulong value) => Hash = (Hash ^ value) * 1099511628211UL;

    [MethodImpl(MethodImplOptions.AggressiveInlining)]
    public static void Call(Op op)
    {
        Counts[(int)op]++;
        Mix((ulong)op + 0x9E37UL);
    }

    public static ulong HashBytes(ReadOnlySpan<byte> data, ulong hash)
    {
        ReadOnlySpan<ulong> words = MemoryMarshal.Cast<byte, ulong>(data);
        foreach (ulong word in words)
        {
            hash = (hash ^ word) * 1099511628211UL;
        }
        for (int i = words.Length * 8; i < data.Length; i++)
        {
            hash = (hash ^ data[i]) * 1099511628211UL;
        }
        return (hash ^ (ulong)data.Length) * 1099511628211UL;
    }

    public static void Data(ReadOnlySpan<byte> data)
    {
        DataBytes += data.Length;
        if (Verify)
        {
            Hash = HashBytes(data, Hash);
        }
        else
        {
            Mix((ulong)data.Length);
        }
    }

    public static ulong Handle(BufferHandle handle) => Unsafe.As<BufferHandle, ulong>(ref handle);

    public static void Range(BufferRange range)
    {
        Mix(Handle(range.Handle));
        Mix((ulong)(uint)range.Offset | ((ulong)(uint)range.Size << 32));
        Mix(range.Write ? 1UL : 0UL);
    }

    public static void Object(object value) => Mix(value is IRecorded recorded ? (ulong)recorded.Id + 1 : value == null ? 0UL : 0xDEADUL);

    // Rare struct arguments: their public and private instance fields, by reflection.
    private static readonly Dictionary<Type, FieldInfo[]> FieldCache = new();

    public static void Struct(object value)
    {
        if (value == null)
        {
            Mix(0);
            return;
        }
        Type type = value.GetType();
        if (type.IsPrimitive || type.IsEnum)
        {
            Mix(Convert.ToUInt64(type.IsEnum ? Convert.ChangeType(value, Enum.GetUnderlyingType(type)) : value is float f ? BitConverter.SingleToUInt32Bits(f) : value is double d ? (object)BitConverter.DoubleToUInt64Bits(d) : value is bool b ? (b ? 1 : 0) : value) );
            return;
        }
        if (!FieldCache.TryGetValue(type, out FieldInfo[] fields))
        {
            fields = type.GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            Array.Sort(fields, (a, b) => string.CompareOrdinal(a.Name, b.Name));
            FieldCache[type] = fields;
        }
        foreach (FieldInfo field in fields)
        {
            Struct(field.GetValue(value));
        }
    }

    public static void Content(BufferRange range)
    {
        ulong handle = Handle(range.Handle);
        ContentHash = (ContentHash ^ handle) * 1099511628211UL;
        if (handle != 0 && Buffers.TryGetValue(handle, out byte[] data))
        {
            int offset = Math.Clamp(range.Offset, 0, data.Length);
            int size = Math.Clamp(range.Size, 0, data.Length - offset);
            ContentHash = HashBytes(data.AsSpan(offset, size), ContentHash);
        }
    }

    public static void DrawPoint()
    {
        if (!Verify)
        {
            return;
        }
        ContentHash = Seed;
        foreach (KeyValuePair<int, BufferRange> pair in Sorted(Uniform))
        {
            if (!Uses(ResourceType.UniformBuffer, pair.Key)) continue;
            ContentHash = (ContentHash ^ (ulong)pair.Key) * 1099511628211UL;
            Content(pair.Value);
        }
        foreach (KeyValuePair<int, BufferRange> pair in Sorted(Storage))
        {
            if (!Uses(ResourceType.StorageBuffer, pair.Key)) continue;
            ContentHash = (ContentHash ^ (ulong)pair.Key + 1000) * 1099511628211UL;
            Content(pair.Value);
        }
        for (int i = 0; i < Vertex.Length; i++)
        {
            if (Handle(Vertex[i].Buffer.Handle) != 0)
            {
                ContentHash = (ContentHash ^ (ulong)i + 2000) * 1099511628211UL;
                Content(Vertex[i].Buffer);
            }
        }
        Content(Index);
        DrawHashes.Add(Hash);
        DrawContent.Add(ContentHash);
        OnDraw?.Invoke(DrawContent.Count - 1);
    }

    private static List<KeyValuePair<int, BufferRange>> Sorted(Dictionary<int, BufferRange> map)
    {
        var list = new List<KeyValuePair<int, BufferRange>>(map);
        list.Sort((a, b) => a.Key.CompareTo(b.Key));
        return list;
    }

    public static byte[] BufferBytes(BufferRange range)
    {
        if (Buffers.TryGetValue(Handle(range.Handle), out byte[] data))
        {
            int offset = Math.Clamp(range.Offset, 0, data.Length);
            int size = Math.Clamp(range.Size, 0, data.Length - offset);
            return data.AsSpan(offset, size).ToArray();
        }
        return null;
    }
}

public interface IRecorded
{
    int Id { get; }
}

public sealed class RecTexture : ITexture, IRecorded
{
    public int Id { get; } = Rec.NextObject++;
    public readonly TextureCreateInfo Info;
    public RecTexture(TextureCreateInfo info) => Info = info;
    public int Width => Info.Width;
    public int Height => Info.Height;
    public void CopyTo(ITexture destination, int firstLayer, int firstLevel) { Rec.Call(Op.TextureCopy); Rec.Object(this); Rec.Object(destination); Rec.Mix((ulong)firstLayer << 16 | (uint)firstLevel); }
    public void CopyTo(ITexture destination, int srcLayer, int dstLayer, int srcLevel, int dstLevel) { Rec.Call(Op.TextureCopy); Rec.Object(this); Rec.Object(destination); Rec.Mix((ulong)srcLayer << 48 | (ulong)dstLayer << 32 | (ulong)srcLevel << 16 | (uint)dstLevel); }
    public void CopyTo(ITexture destination, Extents2D srcRegion, Extents2D dstRegion, bool linearFilter) { Rec.Call(Op.TextureCopy); Rec.Object(this); Rec.Object(destination); Rec.Struct(srcRegion); Rec.Struct(dstRegion); Rec.Mix(linearFilter ? 1UL : 0); }
    public void CopyTo(BufferRange range, int layer, int level, int stride) { Rec.Call(Op.TextureCopyToBuffer); Rec.Object(this); Rec.Range(range); Rec.Mix((ulong)layer << 32 | (uint)level); Rec.Mix((ulong)stride); }
    public ITexture CreateView(TextureCreateInfo info, int firstLayer, int firstLevel) { Rec.Call(Op.TextureView); Rec.Object(this); Rec.Struct(info); Rec.Mix((ulong)firstLayer << 32 | (uint)firstLevel); var view = new RecTexture(info); Rec.Object(view); return view; }
    public PinnedSpan<byte> GetData() { Rec.Call(Op.TextureGetData); Rec.Object(this); return PinnedSpan<byte>.UnsafeFromSpan(new byte[Math.Max(1, Info.Width * Info.Height * 4)]); }
    public PinnedSpan<byte> GetData(int layer, int level) { Rec.Call(Op.TextureGetData); Rec.Object(this); Rec.Mix((ulong)layer << 32 | (uint)level); return PinnedSpan<byte>.UnsafeFromSpan(new byte[Math.Max(1, Info.Width * Info.Height * 4)]); }
    public void SetData(MemoryOwner<byte> data) { Rec.Call(Op.TextureSetData); Rec.Object(this); Rec.Data(data.Span); data.Dispose(); }
    public void SetData(MemoryOwner<byte> data, int layer, int level) { Rec.Call(Op.TextureSetData); Rec.Object(this); Rec.Mix((ulong)layer << 32 | (uint)level); Rec.Data(data.Span); data.Dispose(); }
    public void SetData(MemoryOwner<byte> data, int layer, int level, Rectangle<int> region) { Rec.Call(Op.TextureSetData); Rec.Object(this); Rec.Mix((ulong)layer << 32 | (uint)level); Rec.Struct(region); Rec.Data(data.Span); data.Dispose(); }
    public void SetStorage(BufferRange buffer) { Rec.Call(Op.TextureSetStorage); Rec.Object(this); Rec.Range(buffer); }
    public void Release() { Rec.Call(Op.TextureRelease); Rec.Object(this); }
}

public sealed class RecSampler : ISampler, IRecorded
{
    public int Id { get; } = Rec.NextObject++;
    public void Dispose() { Rec.Call(Op.SamplerDispose); Rec.Object(this); }
}

public sealed class RecProgram : IProgram, IRecorded
{
    public int Id { get; } = Rec.NextObject++;
    public readonly ShaderInfo Info;
    public RecProgram(ShaderInfo info) => Info = info;
    public bool CanBindWhileIncomplete => true;
    public ProgramLinkStatus CheckProgramLink(bool blocking) => ProgramLinkStatus.Success;
    public byte[] GetBinary() => [];
    public void Dispose() { Rec.Call(Op.ProgramDispose); Rec.Object(this); }
}

public sealed class RecTextureArray : ITextureArray, IImageArray, IRecorded
{
    public int Id { get; } = Rec.NextObject++;
    public void SetSamplers(int index, ISampler[] samplers) { Rec.Call(Op.ArraySetSamplers); Rec.Object(this); Rec.Mix((ulong)index); foreach (ISampler s in samplers) Rec.Object(s); }
    public void SetTextures(int index, ITexture[] textures) { Rec.Call(Op.ArraySetTextures); Rec.Object(this); Rec.Mix((ulong)index); foreach (ITexture t in textures) Rec.Object(t); }
    public void SetImages(int index, ITexture[] images) { Rec.Call(Op.ArraySetImages); Rec.Object(this); Rec.Mix((ulong)index); foreach (ITexture t in images) Rec.Object(t); }
    public void Dispose() { Rec.Call(Op.ArrayDispose); Rec.Object(this); }
}

public sealed class RecCounterEvent : ICounterEvent
{
    public bool Invalid { get; set; }
    public bool ReserveForHostAccess() => true;
    public void Flush() { }
    public void Dispose() { }
}

public sealed class RecWindow : IWindow
{
    public void Present(ITexture texture, ImageCrop crop, Action swapBuffersCallback) => swapBuffersCallback?.Invoke();
    public void SetSize(int width, int height) { }
    public void ChangeVSyncMode(VSyncMode vSyncMode) { }
    public void SetAntiAliasing(AntiAliasing antialiasing) { }
    public void SetScalingFilter(ScalingFilter type) { }
    public void SetScalingFilterLevel(float level) { }
    public void SetMetalFxUpscaleFactor(float factor) { }
    public void SetColorSpacePassthrough(bool colorSpacePassThroughEnabled) { }
}

public sealed class RecPipeline : IPipeline
{
    private static void Ranges(ReadOnlySpan<BufferAssignment> buffers, Dictionary<int, BufferRange> bound)
    {
        Rec.Mix((ulong)buffers.Length);
        foreach (BufferAssignment assignment in buffers)
        {
            Rec.Mix((ulong)assignment.Binding);
            Rec.Range(assignment.Range);
            if (Rec.Verify)
            {
                bound[assignment.Binding] = assignment.Range;
            }
        }
    }

    public void Barrier() => Rec.Call(Op.Barrier);
    public void BeginTransformFeedback(PrimitiveTopology topology) { Rec.Call(Op.BeginTransformFeedback); Rec.Mix((ulong)topology); }
    public void ClearBuffer(BufferHandle destination, int offset, int size, uint value)
    {
        Rec.Call(Op.ClearBuffer); Rec.Mix(Rec.Handle(destination)); Rec.Mix((ulong)(uint)offset << 32 | (uint)size); Rec.Mix(value);
        if (Rec.Verify && Rec.Buffers.TryGetValue(Rec.Handle(destination), out byte[] data))
        {
            MemoryMarshal.Cast<byte, uint>(data.AsSpan(offset, size)).Fill(value);
        }
    }
    public void ClearRenderTargetColor(int index, int layer, int layerCount, uint componentMask, ColorF color) { Rec.Call(Op.ClearRtColor); Rec.Mix((ulong)index << 40 | (ulong)layer << 20 | (uint)layerCount); Rec.Mix(componentMask); Rec.Struct(color); }
    public void ClearRenderTargetDepthStencil(int layer, int layerCount, float depthValue, bool depthMask, int stencilValue, int stencilMask) { Rec.Call(Op.ClearRtDepth); Rec.Mix((ulong)layer << 32 | (uint)layerCount); Rec.Mix(BitConverter.SingleToUInt32Bits(depthValue)); Rec.Mix(depthMask ? 1UL : 0); Rec.Mix((ulong)(uint)stencilValue << 32 | (uint)stencilMask); }
    public void CommandBufferBarrier() => Rec.Call(Op.CommandBufferBarrier);
    public void CopyBuffer(BufferHandle source, BufferHandle destination, int srcOffset, int dstOffset, int size)
    {
        Rec.Call(Op.CopyBuffer); Rec.Mix(Rec.Handle(source)); Rec.Mix(Rec.Handle(destination)); Rec.Mix((ulong)(uint)srcOffset << 32 | (uint)dstOffset); Rec.Mix((ulong)size);
        if (Rec.Verify && Rec.Buffers.TryGetValue(Rec.Handle(source), out byte[] from) && Rec.Buffers.TryGetValue(Rec.Handle(destination), out byte[] to))
        {
            Buffer.BlockCopy(from, srcOffset, to, dstOffset, size);
        }
    }
    public void DispatchCompute(int groupsX, int groupsY, int groupsZ) { Rec.Call(Op.Dispatch); Rec.Mix((ulong)groupsX << 40 | (ulong)groupsY << 20 | (uint)groupsZ); Rec.DrawPoint(); }
    public void Draw(int vertexCount, int instanceCount, int firstVertex, int firstInstance) { Rec.Call(Op.Draw); Rec.Mix((ulong)(uint)vertexCount << 32 | (uint)instanceCount); Rec.Mix((ulong)(uint)firstVertex << 32 | (uint)firstInstance); Rec.DrawPoint(); }
    public void DrawIndexed(int indexCount, int instanceCount, int firstIndex, int firstVertex, int firstInstance) { Rec.Call(Op.DrawIndexed); Rec.Mix((ulong)(uint)indexCount << 32 | (uint)instanceCount); Rec.Mix((ulong)(uint)firstIndex << 32 | (uint)firstVertex); Rec.Mix((ulong)firstInstance); Rec.DrawPoint(); }
    public void DrawIndexedIndirect(BufferRange indirectBuffer) { Rec.Call(Op.DrawIndexedIndirect); Rec.Range(indirectBuffer); Rec.DrawPoint(); }
    public void DrawIndexedIndirectCount(BufferRange indirectBuffer, BufferRange parameterBuffer, int maxDrawCount, int stride) { Rec.Call(Op.DrawIndexedIndirectCount); Rec.Range(indirectBuffer); Rec.Range(parameterBuffer); Rec.Mix((ulong)maxDrawCount << 32 | (uint)stride); Rec.DrawPoint(); }
    public void DrawIndirect(BufferRange indirectBuffer) { Rec.Call(Op.DrawIndirect); Rec.Range(indirectBuffer); Rec.DrawPoint(); }
    public void DrawIndirectCount(BufferRange indirectBuffer, BufferRange parameterBuffer, int maxDrawCount, int stride) { Rec.Call(Op.DrawIndirectCount); Rec.Range(indirectBuffer); Rec.Range(parameterBuffer); Rec.Mix((ulong)maxDrawCount << 32 | (uint)stride); Rec.DrawPoint(); }
    public void DrawTexture(ITexture texture, ISampler sampler, Extents2DF srcRegion, Extents2DF dstRegion) { Rec.Call(Op.DrawTexture); Rec.Object(texture); Rec.Object(sampler); Rec.Struct(srcRegion); Rec.Struct(dstRegion); }
    public void EndTransformFeedback() => Rec.Call(Op.EndTransformFeedback);
    public void SetAlphaTest(bool enable, float reference, CompareOp op) { Rec.Call(Op.SetAlphaTest); Rec.Mix(enable ? 1UL : 0); Rec.Mix(BitConverter.SingleToUInt32Bits(reference)); Rec.Mix((ulong)op); }
    public void SetBlendState(AdvancedBlendDescriptor blend) { Rec.Call(Op.SetBlendStateAdvanced); Rec.Struct(blend); }
    public void SetBlendState(int index, BlendDescriptor blend) { Rec.Call(Op.SetBlendState); Rec.Mix((ulong)index); Rec.Struct(blend); }
    public void SetDepthBias(PolygonModeMask enables, float factor, float units, float clamp) { Rec.Call(Op.SetDepthBias); Rec.Mix((ulong)enables); Rec.Mix(BitConverter.SingleToUInt32Bits(factor)); Rec.Mix(BitConverter.SingleToUInt32Bits(units)); Rec.Mix(BitConverter.SingleToUInt32Bits(clamp)); }
    public void SetDepthClamp(bool clamp) { Rec.Call(Op.SetDepthClamp); Rec.Mix(clamp ? 1UL : 0); }
    public void SetDepthMode(DepthMode mode) { Rec.Call(Op.SetDepthMode); Rec.Mix((ulong)mode); }
    public void SetDepthTest(DepthTestDescriptor depthTest) { Rec.Call(Op.SetDepthTest); Rec.Struct(depthTest); }
    public void SetFaceCulling(bool enable, Face face) { Rec.Call(Op.SetFaceCulling); Rec.Mix(enable ? 1UL : 0); Rec.Mix((ulong)face); }
    public void SetFrontFace(FrontFace frontFace) { Rec.Call(Op.SetFrontFace); Rec.Mix((ulong)frontFace); }
    public void SetIndexBuffer(BufferRange buffer, IndexType type) { Rec.Call(Op.SetIndexBuffer); Rec.Range(buffer); Rec.Mix((ulong)type); Rec.Index = buffer; }
    public void SetImage(ShaderStage stage, int binding, ITexture texture) { Rec.Call(Op.SetImage); Rec.Mix((ulong)stage << 32 | (uint)binding); Rec.Object(texture); }
    public void SetImageArray(ShaderStage stage, int binding, IImageArray array) { Rec.Call(Op.SetImageArray); Rec.Mix((ulong)stage << 32 | (uint)binding); Rec.Object(array); }
    public void SetImageArraySeparate(ShaderStage stage, int setIndex, IImageArray array) { Rec.Call(Op.SetImageArraySeparate); Rec.Mix((ulong)stage << 32 | (uint)setIndex); Rec.Object(array); }
    public void SetLineParameters(float width, bool smooth) { Rec.Call(Op.SetLineParameters); Rec.Mix(BitConverter.SingleToUInt32Bits(width)); Rec.Mix(smooth ? 1UL : 0); }
    public void SetLogicOpState(bool enable, LogicalOp op) { Rec.Call(Op.SetLogicOpState); Rec.Mix(enable ? 1UL : 0); Rec.Mix((ulong)op); }
    public void SetMultisampleState(MultisampleDescriptor multisample) { Rec.Call(Op.SetMultisampleState); Rec.Struct(multisample); }
    public void SetPatchParameters(int vertices, ReadOnlySpan<float> defaultOuterLevel, ReadOnlySpan<float> defaultInnerLevel) { Rec.Call(Op.SetPatchParameters); Rec.Mix((ulong)vertices); Rec.Data(MemoryMarshal.AsBytes(defaultOuterLevel)); Rec.Data(MemoryMarshal.AsBytes(defaultInnerLevel)); }
    public void SetPointParameters(float size, bool isProgramPointSize, bool enablePointSprite, Origin origin) { Rec.Call(Op.SetPointParameters); Rec.Mix(BitConverter.SingleToUInt32Bits(size)); Rec.Mix((isProgramPointSize ? 1UL : 0) | (enablePointSprite ? 2UL : 0)); Rec.Mix((ulong)origin); }
    public void SetPolygonMode(PolygonMode frontMode, PolygonMode backMode) { Rec.Call(Op.SetPolygonMode); Rec.Mix((ulong)frontMode << 32 | (uint)backMode); }
    public void SetPrimitiveRestart(bool enable, int index) { Rec.Call(Op.SetPrimitiveRestart); Rec.Mix(enable ? 1UL : 0); Rec.Mix((ulong)(uint)index); }
    public void SetPrimitiveTopology(PrimitiveTopology topology) { Rec.Call(Op.SetPrimitiveTopology); Rec.Mix((ulong)topology); }
    public void SetProgram(IProgram program) { Rec.Call(Op.SetProgram); Rec.Object(program); Rec.Program = program as RecProgram; }
    public void SetRasterizerDiscard(bool discard) { Rec.Call(Op.SetRasterizerDiscard); Rec.Mix(discard ? 1UL : 0); }
    public void SetRenderTargetColorMasks(ReadOnlySpan<uint> componentMask) { Rec.Call(Op.SetRenderTargetColorMasks); Rec.Data(MemoryMarshal.AsBytes(componentMask)); }
    public void SetRenderTargets(Span<ITexture> colors, ITexture depthStencil) { Rec.Call(Op.SetRenderTargets); Rec.Mix((ulong)colors.Length); foreach (ITexture color in colors) Rec.Object(color); Rec.Object(depthStencil); }
    public void SetScissors(ReadOnlySpan<Rectangle<int>> regions) { Rec.Call(Op.SetScissors); Rec.Data(MemoryMarshal.AsBytes(regions)); }
    public void SetStencilTest(StencilTestDescriptor stencilTest) { Rec.Call(Op.SetStencilTest); Rec.Struct(stencilTest); }
    public void SetStorageBuffers(ReadOnlySpan<BufferAssignment> buffers) { Rec.Call(Op.SetStorageBuffers); Ranges(buffers, Rec.Storage); }
    public void SetTextureAndSampler(ShaderStage stage, int binding, ITexture texture, ISampler sampler) { Rec.Call(Op.SetTextureAndSampler); Rec.Mix((ulong)stage << 32 | (uint)binding); Rec.Object(texture); Rec.Object(sampler); }
    public void SetTextureArray(ShaderStage stage, int binding, ITextureArray array) { Rec.Call(Op.SetTextureArray); Rec.Mix((ulong)stage << 32 | (uint)binding); Rec.Object(array); }
    public void SetTextureArraySeparate(ShaderStage stage, int setIndex, ITextureArray array) { Rec.Call(Op.SetTextureArraySeparate); Rec.Mix((ulong)stage << 32 | (uint)setIndex); Rec.Object(array); }
    public void SetTransformFeedbackBuffers(ReadOnlySpan<BufferRange> buffers) { Rec.Call(Op.SetTransformFeedbackBuffers); foreach (BufferRange range in buffers) Rec.Range(range); }
    public void SetUniformBuffers(ReadOnlySpan<BufferAssignment> buffers) { Rec.Call(Op.SetUniformBuffers); Ranges(buffers, Rec.Uniform); }
    public void SetUserClipDistance(int index, bool enableClip) { Rec.Call(Op.SetUserClipDistance); Rec.Mix((ulong)index); Rec.Mix(enableClip ? 1UL : 0); }
    public void SetVertexAttribs(ReadOnlySpan<VertexAttribDescriptor> vertexAttribs) { Rec.Call(Op.SetVertexAttribs); Rec.Mix((ulong)vertexAttribs.Length); foreach (VertexAttribDescriptor attrib in vertexAttribs) Rec.Struct(attrib); }
    public void SetVertexBuffers(ReadOnlySpan<VertexBufferDescriptor> vertexBuffers)
    {
        Rec.Call(Op.SetVertexBuffers);
        Rec.Mix((ulong)vertexBuffers.Length);
        for (int i = 0; i < vertexBuffers.Length; i++)
        {
            Rec.Range(vertexBuffers[i].Buffer);
            Rec.Mix((ulong)(uint)vertexBuffers[i].Stride << 32 | (uint)vertexBuffers[i].Divisor);
            if (Rec.Verify)
            {
                Rec.Vertex[i] = vertexBuffers[i];
            }
        }
    }
    public void SetViewports(ReadOnlySpan<Viewport> viewports) { Rec.Call(Op.SetViewports); Rec.Mix((ulong)viewports.Length); foreach (Viewport viewport in viewports) Rec.Struct(viewport); }
    public void TextureBarrier() => Rec.Call(Op.TextureBarrier);
    public void TextureBarrierTiled() => Rec.Call(Op.TextureBarrierTiled);
    public bool TryHostConditionalRendering(ICounterEvent value, ulong compare, bool isEqual) { Rec.Call(Op.TryHostConditionalRendering); return false; }
    public bool TryHostConditionalRendering(ICounterEvent value, ICounterEvent compare, bool isEqual) { Rec.Call(Op.TryHostConditionalRendering); return false; }
    public void EndHostConditionalRendering() => Rec.Call(Op.EndHostConditionalRendering);
}

public sealed class RecRenderer : IRenderer
{
    public event EventHandler<ScreenCaptureImageInfo> ScreenCaptured { add { } remove { } }
    public bool PreferThreading => false;
    public IPipeline Pipeline { get; } = new RecPipeline();
    public IWindow Window { get; } = new RecWindow();
    public uint ProgramCount => 0;
    public void BackgroundContextAction(Action action, bool alwaysBackground = false) => action();

    private static BufferHandle NewHandle(int size)
    {
        ulong value = ++Rec.NextBuffer;
        if (Rec.Verify)
        {
            Rec.Buffers[value] = new byte[size];
        }
        Rec.Mix(value);
        Rec.Mix((ulong)size);
        return Unsafe.As<ulong, BufferHandle>(ref value);
    }

    public BufferHandle CreateBuffer(int size, BufferAccess access = BufferAccess.Default) { Rec.Call(Op.CreateBuffer); Rec.Mix((ulong)access); return NewHandle(size); }
    public BufferHandle CreateBuffer(nint pointer, int size) { Rec.Call(Op.CreateBufferHost); return NewHandle(size); }
    public BufferHandle CreateBufferSparse(ReadOnlySpan<BufferRange> storageBuffers) { Rec.Call(Op.CreateBufferSparse); int size = 0; foreach (BufferRange range in storageBuffers) { Rec.Range(range); size += range.Size; } return NewHandle(size); }
    public IImageArray CreateImageArray(int size, bool isBuffer) { Rec.Call(Op.CreateImageArray); Rec.Mix((ulong)size); Rec.Mix(isBuffer ? 1UL : 0); var array = new RecTextureArray(); Rec.Object(array); return array; }
    public IProgram CreateProgram(ShaderSource[] shaders, ShaderInfo info) { Rec.Call(Op.CreateProgram); Rec.Mix((ulong)shaders.Length); var program = new RecProgram(info); Rec.Object(program); return program; }
    public ISampler CreateSampler(SamplerCreateInfo info) { Rec.Call(Op.CreateSampler); Rec.Struct(info); var sampler = new RecSampler(); Rec.Object(sampler); return sampler; }
    public ITexture CreateTexture(TextureCreateInfo info) { Rec.Call(Op.CreateTexture); Rec.Struct(info); var texture = new RecTexture(info); Rec.Object(texture); return texture; }
    public ITextureArray CreateTextureArray(int size, bool isBuffer) { Rec.Call(Op.CreateTextureArray); Rec.Mix((ulong)size); Rec.Mix(isBuffer ? 1UL : 0); var array = new RecTextureArray(); Rec.Object(array); return array; }
    public bool PrepareHostMapping(nint address, ulong size) => false;
    public void CreateSync(ulong id, bool strict) { Rec.Call(Op.CreateSync); Rec.Mix(id); Rec.Mix(strict ? 1UL : 0); }
    public void DeleteBuffer(BufferHandle buffer) { Rec.Call(Op.DeleteBuffer); Rec.Mix(Rec.Handle(buffer)); Rec.Buffers.Remove(Rec.Handle(buffer)); }
    public PinnedSpan<byte> GetBufferData(BufferHandle buffer, int offset, int size)
    {
        Rec.Call(Op.GetBufferData); Rec.Mix(Rec.Handle(buffer)); Rec.Mix((ulong)(uint)offset << 32 | (uint)size);
        byte[] copy = new byte[size];
        if (Rec.Buffers.TryGetValue(Rec.Handle(buffer), out byte[] data))
        {
            data.AsSpan(offset, size).CopyTo(copy);
        }
        return PinnedSpan<byte>.UnsafeFromSpan(copy);
    }
    public Capabilities GetCapabilities() => new(
        api: TargetApi.Vulkan, vendorName: "Apple", memoryType: SystemMemoryType.UnifiedMemory, hasFrontFacingBug: false, hasVectorIndexingBug: false,
        needsFragmentOutputSpecialization: true, reduceShaderPrecision: true, supportsAstcCompression: true, supportsBc123Compression: false,
        supportsBc45Compression: false, supportsBc67Compression: false, supportsEtc2Compression: true, supports3DTextureCompression: true,
        supportsBgraFormat: true, supportsR4G4Format: false, supportsR4G4B4A4Format: true, supportsScaledVertexFormats: false,
        supportsSnormBufferTextureFormat: true, supports5BitComponentFormat: true, supportsSparseBuffer: false, supportsBlendEquationAdvanced: false,
        supportsFragmentShaderInterlock: false, supportsFragmentShaderOrderingIntel: false, supportsGeometryShader: false,
        supportsGeometryShaderPassthrough: false, supportsTransformFeedback: false, supportsImageLoadFormatted: true,
        supportsLayerVertexTessellation: true, supportsMismatchingViewFormat: true, supportsCubemapView: true,
        supportsNonConstantTextureOffset: false, supportsQuads: false, supportsSeparateSampler: true, supportsShaderBallot: false,
        supportsShaderBarrierDivergence: true, supportsShaderFloat64: false, supportsTextureGatherOffsets: false, supportsTextureShadowLod: false,
        supportsVertexStoreAndAtomics: true, supportsViewportIndexVertexTessellation: true, supportsViewportMask: false,
        supportsViewportSwizzle: false, supportsIndirectParameters: true, supportsDepthClipControl: false, uniformBufferSetIndex: 0,
        storageBufferSetIndex: 1, textureSetIndex: 2, imageSetIndex: 3, extraSetBaseIndex: 4, maximumExtraSets: 4,
        maximumUniformBuffersPerStage: 18, maximumStorageBuffersPerStage: 16, maximumTexturesPerStage: 64, maximumImagesPerStage: 16,
        maximumComputeSharedMemorySize: 32768, maximumSupportedAnisotropy: 16, shaderSubgroupSize: 32, storageBufferOffsetAlignment: 16,
        textureBufferOffsetAlignment: 16, gatherBiasPrecision: 0, maximumGpuMemory: 6UL << 30);
    public ulong GetCurrentSync() => 0;
    public HardwareInfo GetHardwareInfo() => new("Apple", "Recording double", "none");
    public IProgram LoadProgramBinary(byte[] programBinary, bool hasFragmentShader, ShaderInfo info) => new RecProgram(info);
    public void SetBufferData(BufferHandle buffer, int offset, ReadOnlySpan<byte> data)
    {
        Rec.Call(Op.SetBufferData); Rec.Mix(Rec.Handle(buffer)); Rec.Mix((ulong)(uint)offset); Rec.Data(data);
        if (Rec.Verify && Rec.Buffers.TryGetValue(Rec.Handle(buffer), out byte[] model))
        {
            data.CopyTo(model.AsSpan(offset));
        }
    }
    public void UpdateCounters() => Rec.Call(Op.UpdateCounters);
    public void PreFrame() => Rec.Call(Op.PreFrame);
    public ICounterEvent ReportCounter(CounterType type, EventHandler<ulong> resultHandler, float divisor, bool hostReserved) { Rec.Call(Op.ReportCounter); resultHandler?.Invoke(this, 0); return new RecCounterEvent(); }
    public void ResetCounter(CounterType type) { Rec.Call(Op.ResetCounter); Rec.Mix((ulong)type); }
    public void WaitSync(ulong id) { Rec.Call(Op.WaitSync); Rec.Mix(id); }
    public void Initialize(GraphicsDebugLevel logLevel) { }
    public void SetInterruptAction(Action<Action> interruptAction) { }
    public void Screenshot() { }
    public void Dispose() { }
}
