using System;
using System.Collections.Generic;
using System.Runtime.InteropServices;

namespace Ryujinx.Memory { public interface IVirtualMemoryManager { void Read(ulong p, byte[] b); } }
namespace Ryujinx.Audio { static class Constants { public const uint TargetSampleRate = 48000; } }
namespace Ryujinx.Common.Logging {
    enum LogClass { Audio }
    class Log { public void Print(LogClass c, string s) {} }
    static class Logger { public static Log Debug = new(); }
}
namespace Ryujinx.Common {
    static class EmbeddedLaunchDiagnostics { public static void Record(string stage, string status, int code = 0, string detail = "") {} }
}
namespace Ryujinx.Audio.Backends.Apple.Native {
    internal static unsafe class AVFoundation {
        internal enum AVAudioCommonFormat : ulong { PcmFormatFloat32 = 1 }
        [StructLayout(LayoutKind.Sequential)] internal struct AudioBuffer { public uint NumberChannels, DataByteSize; public nint Data; }
        [StructLayout(LayoutKind.Sequential)] internal struct AudioBufferList { public uint NumberBuffers; public AudioBuffer Buffer; }
        internal delegate void CompletionCallback(nint block);
        internal sealed class Pcm {
            public nint List; public uint Frames; public int Offset; public nint Block;
        }
        static long next;
        static readonly Dictionary<nint, Pcm> pcm = new();
        static readonly Dictionary<nint, (nint Context, CompletionCallback Callback)> blocks = new();
        static readonly Queue<nint> queue = new();
        static readonly Dictionary<nint, uint> channels = new();
        internal static int Now, StartAt = int.MaxValue, EmptyFrames, Plays, Starts, Releases;
        internal static bool Running, Playing;
        internal static bool CanStart = true;
        internal static float Volume = 1;
        internal static readonly List<float> Rendered = new();
        internal static nint Alloc(string name) => (nint)(++next);
        internal static nint Init(nint obj) => obj;
        internal static nint InitAudioFormat(nint obj, AVAudioCommonFormat format, uint rate, uint count) { channels[obj] = count; return obj; }
        internal static void AttachNode(nint e, nint p) {}
        internal static nint MainMixerNode(nint e) => e;
        internal static void Connect(nint e, nint p, nint target, nint format) {}
        internal static void Prepare(nint e) {}
        internal static bool Start(nint e, out nint error) { error = 0; Starts++; if (!CanStart) return false; Running = true; return true; }
        internal static bool IsRunning(nint e) => Running;
        internal static void Play(nint p) { Plays++; Playing = true; StartAt = Now; }
        internal static void PlayBuffered(nint p, double lead) { Plays++; Playing = true; StartAt = Now + (int)Math.Round(lead * 48000); }
        internal static void Pause(nint p) { Playing = false; }
        internal static void Stop(nint p) {
            Playing = false;
            while (queue.TryDequeue(out var b)) { var block = pcm[b].Block; if (blocks.TryGetValue(block, out var c)) c.Callback(block); }
        }
        internal static void SetVolume(nint p, float volume) { Volume = volume; }
        internal static nint InitPcmBuffer(nint obj, nint format, uint frames) {
            uint count = channels[format];
            var list = (AudioBufferList*)NativeMemory.AllocZeroed((nuint)(sizeof(AudioBufferList) + (count - 1) * sizeof(AudioBuffer)));
            list->NumberBuffers = count;
            var buffers = &list->Buffer;
            for (int i = 0; i < count; i++) {
                buffers[i].NumberChannels = 1; buffers[i].DataByteSize = frames * sizeof(float);
                buffers[i].Data = (nint)NativeMemory.AllocZeroed(frames, sizeof(float));
            }
            pcm[obj] = new Pcm { List = (nint)list, Frames = frames }; return obj;
        }
        internal static void SetFrameLength(nint b, uint frames) { pcm[b].Frames = frames; }
        internal static AudioBufferList* GetMutableAudioBufferList(nint b) => (AudioBufferList*)pcm[b].List;
        internal static void ScheduleBuffer(nint p, nint b, nint block) { pcm[b].Block = block; queue.Enqueue(b); }
        internal static void Release(nint obj) {
            if (!pcm.Remove(obj, out var b)) return;
            var list = (AudioBufferList*)b.List; var buffers = &list->Buffer;
            for (int i = 0; i < list->NumberBuffers; i++) NativeMemory.Free((void*)buffers[i].Data);
            NativeMemory.Free(list); Releases++;
        }
        internal static nint CreateCompletionBlock(nint context, CompletionCallback callback, out GCHandle handle) {
            handle = GCHandle.Alloc(callback); nint id = (nint)(++next); blocks[id] = (context, callback); return id;
        }
        internal static nint GetBlockContext(nint block) => blocks[block].Context;
        internal static void DestroyCompletionBlock(nint block, GCHandle handle) { blocks.Remove(block); handle.Free(); }
        internal static void AdvanceTo(int end) {
            for (; Now < end; Now++) {
                if (!Running || !Playing || Now < StartAt) continue;
                if (!queue.TryPeek(out var id)) { EmptyFrames++; continue; }
                var b = pcm[id]; var list = (AudioBufferList*)b.List;
                var buffers = &list->Buffer;
                for (int ch = 0; ch < list->NumberBuffers; ch++) Rendered.Add(((float*)buffers[ch].Data)[b.Offset] * Volume);
                if (++b.Offset == b.Frames) { queue.Dequeue(); blocks[b.Block].Callback(b.Block); }
            }
        }
        internal static void Reset() {
            if (pcm.Count != 0 || queue.Count != 0 || blocks.Count != 0) throw new Exception("Native resources leaked");
            Now = EmptyFrames = Plays = Starts = Releases = 0; StartAt = int.MaxValue; Running = Playing = false;
            Volume = 1; CanStart = true; Rendered.Clear(); channels.Clear();
        }
    }
}
