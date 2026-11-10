using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Ryujinx.Common.Configuration {
    static class AppDataManager { public static string BaseDirPath; }
}
namespace Ryujinx.Common.Logging {
    enum LogClass { Gpu }
    class Sink { public void PrintMsg(LogClass c, string message) { } }
    static class Logger { public static Sink Notice = new(), Warning = new(), Info = new(); }
}
namespace Silk.NET.Vulkan {
    readonly record struct Result(int Value) {
        public static Result Success => new(0);
        public static Result ErrorUnknown => new(-1);
        public bool IsError => Value < 0;
    }
    enum PipelineCacheCreateFlags { ExternallySynchronizedBitExt = 1 }
    enum StructureType { PipelineCacheCreateInfo }
    record struct PipelineCache(ulong Handle);
    struct Device { }
    struct PhysicalDeviceProperties { public uint VendorID, DeviceID, DriverVersion; }
    unsafe struct PipelineCacheCreateInfo {
        public StructureType SType;
        public PipelineCacheCreateFlags Flags;
        public nuint InitialDataSize;
        public void* PInitialData;
    }
    unsafe class Vk {
        private ulong _next;
        public readonly Dictionary<PipelineCache, byte[]> Data = new();
        public int Exports, Merges;
        public bool FailNextMerge;
        public bool RejectNextSnapshot;
        public Result CreatePipelineCache(Device d, in PipelineCacheCreateInfo info, void* allocator, out PipelineCache cache) {
            if (RejectNextSnapshot && info.InitialDataSize != 0) {
                RejectNextSnapshot = false;
                cache = default;
                return Result.ErrorUnknown;
            }
            cache = new(++_next);
            Data[cache] = info.InitialDataSize == 0 ? new byte[16] : new ReadOnlySpan<byte>(info.PInitialData, (int)info.InitialDataSize).ToArray();
            return Result.Success;
        }
        public void Set(PipelineCache cache, byte value) { Array.Fill(Data[cache], value); }
        public void DestroyPipelineCache(Device d, PipelineCache cache, void* allocator) { Data.Remove(cache); }
        public Result GetPipelineCacheData(Device d, PipelineCache cache, nuint* size, void* bytes) {
            byte[] source = Data[cache];
            *size = (nuint)source.Length;
            if (bytes != null) { source.AsSpan().CopyTo(new Span<byte>(bytes, source.Length)); Exports++; }
            return Result.Success;
        }
        public Result MergePipelineCaches(Device d, PipelineCache destination, uint count, PipelineCache* sources) {
            Merges++;
            if (FailNextMerge) { FailNextMerge = false; return Result.ErrorUnknown; }
            for (int i = 0; i < count; i++) Data[destination] = (byte[])Data[sources[i]].Clone();
            return Result.Success;
        }
    }
}
namespace Ryujinx.Graphics.Vulkan {
    using Silk.NET.Vulkan;
    class VulkanPhysicalDevice {
        public PhysicalDeviceProperties PhysicalDeviceProperties => new() { VendorID = 1, DeviceID = 2, DriverVersion = 3 };
        public bool SupportsPipelineCreationCacheControl(Vk api) => true;
    }
    static class VulkanRenderer { public static Func<string> PipelineCacheScope; }
    static class VulkanResultExtensions {
        public static void ThrowOnError(this Result result) {
            if (result != Result.Success) throw new VulkanException(result);
        }
    }
    class VulkanException : Exception { public VulkanException(Result result) : base(result.ToString()) { } }
}
