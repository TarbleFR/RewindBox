using System;
using System.Collections.Generic;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.Shader;
using Silk.NET.Vulkan;

namespace Ryujinx.Graphics.Vulkan
{
    // Only the native endpoint is replaced. Full production
    // DescriptorSetCollection fixes and forwards its real Silk structs here.
    readonly record struct NativeWrite(uint Binding, DescriptorType Type, uint Count,
        ulong Image, ulong Sampler, ImageLayout Layout, ulong View, ulong Buffer, ulong Offset, ulong Range);

    sealed class NativeApi
    {
        public static NativeApi Current = new();
        public readonly List<NativeWrite> Writes = new();
        public bool Capture = true;
        public int Calls, ThrowAt;
        public Action OnUpdate;
        public ulong Digest = 14695981039346656037;
        void Record(ulong value) => Digest = unchecked((Digest ^ value) * 1099511628211);
        public unsafe void UpdateDescriptorSets(Device device, uint writeCount, in WriteDescriptorSet write,
            uint copyCount, CopyDescriptorSet* copies)
        {
            if (writeCount != 1 || copyCount != 0 || copies != null || write.SType != StructureType.WriteDescriptorSet ||
                write.DstSet.Handle != 77 || write.DstArrayElement != 0)
                throw new InvalidOperationException("unexpected real descriptor write metadata");
            Calls++;
            if (Calls == ThrowAt) throw new NativeBoundaryException();
            // Even a nested managed test update cannot invalidate the outer
            // invocation's scratch. Consume synchronously before returning.
            Action nested = OnUpdate; OnUpdate = null; nested?.Invoke();
            Record(write.DstBinding); Record((ulong)write.DescriptorType); Record(write.DescriptorCount);
            for (int i = 0; i < write.DescriptorCount; i++)
            {
                NativeWrite item;
                if (write.PImageInfo != null)
                {
                    var info = write.PImageInfo[i];
                    item = new(write.DstBinding, write.DescriptorType, write.DescriptorCount,
                        info.ImageView.Handle, info.Sampler.Handle, info.ImageLayout, 0, 0, 0, 0);
                }
                else if (write.PTexelBufferView != null)
                    item = new(write.DstBinding, write.DescriptorType, write.DescriptorCount, 0, 0, 0,
                        write.PTexelBufferView[i].Handle, 0, 0, 0);
                else if (write.PBufferInfo != null)
                {
                    var info = write.PBufferInfo[i];
                    item = new(write.DstBinding, write.DescriptorType, write.DescriptorCount,
                        0, 0, 0, 0, info.Buffer.Handle, info.Offset, info.Range);
                }
                else throw new InvalidOperationException("missing real descriptor pointer");
                if (Capture) Writes.Add(item);
                Record(item.Image); Record(item.Sampler); Record((ulong)item.Layout); Record(item.View);
                Record(item.Buffer); Record(item.Offset); Record(item.Range);
            }
        }
    }
    sealed class NativeBoundaryException : Exception { }
    static class DescriptorSetManager
    {
        public sealed class DescriptorPoolHolder
        {
            public readonly NativeApi Api = NativeApi.Current;
            public Device Device;
            public void FreeDescriptorSets(DescriptorSetCollection collection) { }
        }
    }
    partial class DescriptorSetUpdater
    {
        public void Fallback(int set = PipelineBase.TextureSetIndex)
            => UpdateAndBind(default, set, PipelineBindPoint.Graphics);
        public void ArrayAt(int binding, TextureArray array)
        {
            _textureArrayRefs[binding] = new(ShaderStage.Fragment, array);
            SignalDirty(DirtyFlags.Texture);
        }
        public void InitializeFixture(int set)
        {
            var collection = _program.GetNewDescriptorSetCollection(set, out _).Get(default);
            Initialize(default, set, collection);
        }
    }
}
