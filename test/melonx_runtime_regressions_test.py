#!/usr/bin/env python3
"""Execute adapted production audio methods and fence helpers with deterministic I/O.
No actual SDL device, Vulkan GPU or iPhone gameplay is simulated or claimed.
"""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys, tempfile
ROOT = Path(__file__).resolve().parents[1]
source = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_audio import apply as audio_patch
from adapt_runtime import preserve_fence_errors

def method(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth = 1
    end = brace + 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]

with tempfile.TemporaryDirectory(prefix='melonx-runtime-regressions-') as d:
    w = Path(d)
    paths = ['src/Ryujinx.Audio.Backends.SDL3/SDL3HardwareDeviceSession.cs',
             'src/Ryujinx.Graphics.Vulkan/FenceHelper.cs']
    for p in paths:
        target = w / 'source' / p
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / p, target)
    audio_patch(w / 'source'); preserve_fence_errors(w / 'source')
    audio = (w / 'source' / paths[0]).read_text()
    methods = '\n'.join(method(audio, s) for s in [
        'private unsafe void Update(', 'public override void QueueBuffer(',
        'public override ulong GetPlayedSampleCount(', 'public override bool WasBufferFullyConsumed('])
    methods = methods.replace('public override ', 'public ')
    (w / 'Audio.cs').write_text(r'''using System;
using System.Collections.Concurrent;
using System.Threading;
using System.Collections.Generic;
using System.Linq;
using static FakeSDL;
unsafe struct SDL_AudioStream {}
struct AudioBuffer { public byte[] Data; public ulong HostTag; }
class SDL3AudioBuffer {
 public ulong DriverIdentifier, SampleCount, SamplePlayed;
 public SDL3AudioBuffer(ulong tag, ulong count) { DriverIdentifier=tag; SampleCount=count; }
}
sealed class SpanOwner<T> : IDisposable {
 private T[] data; private SpanOwner(int n) {data=new T[n];}
 public Span<T> Span => data; public static SpanOwner<T> Rent(int n) => new(n);
 public void Dispose() {}
}
class Ring {
 private List<byte> data = new(); public Action AfterPublish;
 public int Length => data.Count;
 public void Write(byte[] bytes, int start, int count) {
  data.AddRange(bytes.Skip(start).Take(count)); AfterPublish?.Invoke();
 }
 public void Read(Span<byte> output, int start, int count) {
  data.Take(count).ToArray().CopyTo(output); data.RemoveRange(0,count);
 }
}
unsafe static class FakeSDL {
 internal static List<byte[]> Puts=new();
 internal static void SDL_MixAudio(byte* dst, byte* src, int format, uint count, float volume) {
  new ReadOnlySpan<byte>(src,(int)count).CopyTo(new Span<byte>(dst,(int)count));
 }
 internal static void SDL_PutAudioStreamData(SDL_AudioStream* stream,nint bytes,int count) {
  Puts.Add(new ReadOnlySpan<byte>((void*)bytes,count).ToArray());
 }
}
unsafe class Audio {
 class Driver { public float Volume=1; }
 private Driver _driver=new(); private float _volume=1; private int _nativeSampleFormat=0;
 private int _bytesPerFrame=4; private ulong _playedSampleCount;
 private ConcurrentQueue<SDL3AudioBuffer> _queuedBuffers=new();
 private Ring _ringBuffer=new(); private ManualResetEvent _updateRequiredEvent=new(false);
 private SDL_AudioStream* _outputStream=(SDL_AudioStream*)1;
 private ulong GetSampleCount(int bytes) => (ulong)(bytes/_bytesPerFrame);
 private ulong GetSampleCount(AudioBuffer b) => GetSampleCount(b.Data.Length);
 private void EnsureAudioStreamSetup(AudioBuffer b) {}
 public void Pull(int bytes) => Update(0,_outputStream,bytes,bytes);
 public bool Updated => _updateRequiredEvent.WaitOne(0);
 public void PullDuringPublication(int bytes) => _ringBuffer.AfterPublish=()=>Pull(bytes);
''' + methods + '\n}\n')
    shutil.copyfile(w / 'source' / paths[1], w / 'FenceHelper.cs')
    (w / 'Vulkan.cs').write_text(r'''using System;using System.Collections.Generic;
namespace Silk.NET.Vulkan {
 enum Result {Success=0,Timeout=2,ErrorDeviceLost=-4,ErrorOutOfDeviceMemory=-2}
 struct Device {} struct Fence {}
 class Vk {
  public Queue<Result> Results=new(); public bool WaitAll;
  public Result WaitForFences(Device d,uint n,ReadOnlySpan<Fence> f,bool all,ulong timeout) {
   WaitAll=all;return Results.Dequeue();
  }
 }
 static class Errors {public static void ThrowOnError(this Result result) {
  if(result!=Result.Success)throw new InvalidOperationException(result.ToString());
 }}
}
''')
    (w / 'Program.cs').write_text(r'''using System;using System.Linq;
using Silk.NET.Vulkan;using Ryujinx.Graphics.Vulkan;
class Program {static void Main() {
 int checks=0;void Check(bool ok){if(!ok)throw new Exception("Regression assertion "+checks);checks++;}
 AudioBuffer Buffer(ulong id,int frames)=>new(){HostTag=id,Data=Enumerable.Repeat((byte)0x51,frames*4).ToArray()};
 var empty=new Audio();empty.Pull(8192);Check(FakeSDL.Puts.Count==0 && empty.Updated);
 var shortRead=new Audio();var a=Buffer(1,240);shortRead.QueueBuffer(a);shortRead.Pull(8192);
 Check(FakeSDL.Puts.Last().Length==960 && FakeSDL.Puts.Last().All(b=>b==0x51));
 Check(shortRead.GetPlayedSampleCount()==240 && shortRead.WasBufferFullyConsumed(a));
 var partial=new Audio();var b=Buffer(2,10);partial.QueueBuffer(b);partial.Pull(5);
 Check(FakeSDL.Puts.Last().Length==4 && partial.GetPlayedSampleCount()==1 && !partial.WasBufferFullyConsumed(b));
 partial.Pull(36);Check(partial.GetPlayedSampleCount()==10 && partial.WasBufferFullyConsumed(b));
 var race=new Audio();race.PullDuringPublication(8192);var c=Buffer(3,240);race.QueueBuffer(c);
 Check(race.GetPlayedSampleCount()==240 && race.WasBufferFullyConsumed(c));
 // This exact callback interleaving loses all 240 played frames before the fix.
 var next=Buffer(4,240);race.QueueBuffer(next);
 Check(race.GetPlayedSampleCount()==480 && race.WasBufferFullyConsumed(next));
 var vk=new Vk();var fences=new[]{new Fence()};
 foreach(bool all in new[]{false,true}) {
  bool Poll()=>all?FenceHelper.AllSignaled(vk,new(),fences,1):FenceHelper.AnySignaled(vk,new(),fences,1);
  vk.Results.Enqueue(Result.Success);Check(Poll() && vk.WaitAll==all);
  vk.Results.Enqueue(Result.Timeout);Check(!Poll());
  foreach(var failure in new[]{Result.ErrorDeviceLost,Result.ErrorOutOfDeviceMemory}) {
   vk.Results.Enqueue(failure);bool threw=false;
   try{Poll();}catch(InvalidOperationException e){threw=e.Message==failure.ToString();}
   Check(threw);
  }
 }
 vk.Results.Enqueue(Result.Timeout);vk.Results.Enqueue(Result.Success);
 FenceHelper.WaitAllIndefinitely(vk,new(),fences);Check(vk.Results.Count==0);
 Console.WriteLine($"PASS {checks} production audio/fence assertions; deterministic I/O doubles, no gameplay claim.");
}}
''')
    (w / 'test.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>')
    result = subprocess.run(['dotnet','run','--project',str(w/'test.csproj'),'-c','Release'],capture_output=True,text=True,timeout=120)
    print(result.stdout);print(result.stderr);result.check_returncode()
    out=ROOT/'dist/melonx/runtime-regressions.json';out.parent.mkdir(parents=True,exist_ok=True)
    inputs=['build-utils/melonx/adapt_audio.py','build-utils/melonx/adapt_runtime.py','test/melonx_runtime_regressions_test.py']
    out.write_text(json.dumps(dict(result='passed',summary=result.stdout,inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in inputs},upstreamInputs={p:hashlib.sha256((source/p).read_bytes()).hexdigest() for p in paths},physicalDeviceTested=False),indent=2)+'\n')
