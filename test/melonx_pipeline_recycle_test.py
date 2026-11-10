#!/usr/bin/env python3
"""Execute the complete cache manager with real files and a Vulkan cache double.

Budget fields are shortened only in the harness to force recycling with tiny
blobs. Merge unions are modeled by bits; no driver timings are claimed.
"""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_pipeline_cache import apply_cache_manager
from adapt_pipeline_recycle import apply

path = 'src/Ryujinx.Graphics.Vulkan/PipelineCacheManager.cs'
reports = []
with tempfile.TemporaryDirectory(prefix='melonx-recycle-') as temporary:
    for adapted in (False, True):
        work = Path(temporary) / ('fixed' if adapted else 'control')
        source = work / 'source'
        target = source / path
        target.parent.mkdir(parents=True)
        shutil.copyfile(SOURCE / path, target)
        apply_cache_manager(target)
        if adapted:
            apply(source)
        shutil.copyfile(target, work / 'PipelineCacheManager.cs')
        double = (ROOT / 'test/melonx_pipeline_cache/Double.cs').read_text()
        double = double.replace('public int Exports, Merges;',
                                'public int Exports, Merges; public Action BeforeMerge;')
        double = double.replace('public bool FailNextMerge;', 'public bool FailNextMerge; public bool ExpandNextMerge;')
        # Empty driver caches have a small header; nonempty blobs overflow our
        # shortened worker budget. Keep the real production budgets unchanged.
        double = double.replace('*size = (nuint)source.Length;',
                                'int length = Array.TrueForAll(source, b => b == 0) ? 4 : source.Length; *size = (nuint)length;')
        double = double.replace('source.AsSpan().CopyTo(new Span<byte>(bytes, source.Length));',
                                'source.AsSpan(0, length).CopyTo(new Span<byte>(bytes, length));')
        double = double.replace('            Merges++;', '            Merges++; BeforeMerge?.Invoke();')
        before = 'for (int i = 0; i < count; i++) Data[destination] = (byte[])Data[sources[i]].Clone();'
        assert double.count(before) == 1
        double = double.replace(before, '''for (int i = 0; i < count; i++)
                for (int b = 0; b < Data[sources[i]].Length; b++) Data[destination][b] |= Data[sources[i]][b];
            if (ExpandNextMerge) {
                ExpandNextMerge = false;
                byte[] expanded = new byte[128];
                Data[destination].CopyTo(expanded, 0);
                Data[destination] = expanded;
            }''')
        (work / 'Double.cs').write_text(double)
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<NoWarn>CS0649;CS0414</NoWarn></PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        (work / 'Program.cs').write_text(r'''
using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Threading;
using Ryujinx.Common.Configuration;
using Ryujinx.Graphics.Vulkan;
using Silk.NET.Vulkan;
bool fixedMode = Environment.GetCommandLineArgs().Last()=="fixed";
int checks=0;
void Check(bool ok, string message) { checks++; if(!ok) throw new Exception(message); }
object State(PipelineCacheManager manager, bool main) {
 return main ? typeof(PipelineCacheManager).GetField("_mainState", BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(manager)!
             : ((Array)typeof(PipelineCacheManager).GetField("_workerStates", BindingFlags.Instance|BindingFlags.NonPublic)!.GetValue(manager)!).GetValue(0)!;
}
void Budget(object state, long budget) => state.GetType().GetField("Budget")!.SetValue(state,budget);
long Generation(object state) => (long)state.GetType().GetField("Generation")!.GetValue(state)!;
string root=Path.Combine(Path.GetTempPath(),"recycle-cases-"+Guid.NewGuid());
Directory.CreateDirectory(root);
try {
 for(int scenario=0;scenario<5;scenario++) {
  AppDataManager.BaseDirPath=Path.Combine(root,scenario.ToString());
  VulkanRenderer.PipelineCacheScope=()=>"0100f7e00c70e000";
  var api=new Vk(); var gate=new Lock();
  using var cache=new PipelineCacheManager(api,new(),new(),1,gate);
  Budget(State(cache,false),8); Budget(State(cache,true),scenario==1?16:64);
  api.Set(cache.MainCache,1); cache.NotifyMainPipelineCreated();
  cache.MergeAndSave();
  string[] files=Directory.GetFiles(Path.Combine(AppDataManager.BaseDirPath,"cache","vulkan"),"*.vkpc");
  string mainFile=files.Single(p=>!p.Contains(".worker"));
  Check(File.ReadAllBytes(mainFile).All(b=>b==1),"Initial persisted main");
  api.BeforeMerge=()=>Check(gate.IsHeldByCurrentThread,"Main merge must hold creation lock");
  PipelineCache previous=cache.GetWorkerCache(0);
  api.Set(previous,2);
  if(scenario==2) api.FailNextMerge=true;
  if(scenario==4 && fixedMode) api.ExpandNextMerge=true;
  long generation=Generation(State(cache,true));
  cache.NotifyWorkerPipelineCreated(0); // Measured16 > worker budget8 => recycle.
  Check(cache.GetWorkerCache(0)!=previous,"Worker did not recycle");
  Check(!api.Data.ContainsKey(previous),"Old worker cache retained");
  Check(api.Data[cache.GetWorkerCache(0)].All(b=>b==0),"Replacement cache is not empty");
  bool preserved=fixedMode && scenario!=1 && scenario!=2;
  Check(api.Data[cache.MainCache].Take(16).All(b=>b==(preserved?3:1)),"Recycled data / fallback");
  Check(Generation(State(cache,true))==generation+(preserved?1:0),"Main generation");
  Check(File.ReadAllBytes(mainFile).All(b=>b==1),"Worker exported main during recycle");
  if(scenario==4 && fixedMode) {
   Check(api.Data[cache.MainCache].Length==128,"Driver growth case not exercised");
   int merges=api.Merges; previous=cache.GetWorkerCache(0); api.Set(previous,4);
   cache.NotifyWorkerPipelineCreated(0);
   Check(api.Merges==merges,"More preservation merges after actual soft-budget overshoot");
   Check(!api.Data.ContainsKey(previous),"Oversized main stopped bounded worker recycling");
  }
  cache.MergeAndSave();
  Check(File.ReadAllBytes(mainFile).All(b=>b==(preserved && scenario!=4?3:1)),"Close persistence/soft-budget refusal");
  if(scenario==3) {
   // Successive recycles accumulate useful data, retire every old worker and
   // leave disk writes for the existing normal close path.
   previous=cache.GetWorkerCache(0);api.Set(previous,4);cache.NotifyWorkerPipelineCreated(0);
   Check(!api.Data.ContainsKey(previous),"Second old cache retained");
   Check(api.Data[cache.MainCache].All(b=>b==(fixedMode?7:1)),"Repeated recycle union");
   cache.MergeAndSave();
   Check(File.ReadAllBytes(mainFile).All(b=>b==(fixedMode?7:1)),"Second close persistence");
  }
 }
 // Keep a useful checkpoint when its replacement saw no work before close.
 {
  AppDataManager.BaseDirPath=Path.Combine(root,"checkpoint");
  var api=new Vk(); using var cache=new PipelineCacheManager(api,new(),new(),1,new Lock());
  Budget(State(cache,true),64); Budget(State(cache,false),32);
  api.Set(cache.MainCache,1);cache.NotifyMainPipelineCreated();cache.MergeAndSave();
  api.Set(cache.GetWorkerCache(0),4);cache.NotifyWorkerPipelineCreated(0);
  string file=Directory.GetFiles(Path.Combine(AppDataManager.BaseDirPath,"cache","vulkan"),"*.worker0.vkpc").Single();
  Check(File.ReadAllBytes(file).All(b=>b==4),"Worker checkpoint setup");
  Budget(State(cache,false),8);api.Set(cache.GetWorkerCache(0),6);cache.NotifyWorkerPipelineCreated(0);
  cache.MergeAndSave();
  Check(File.ReadAllBytes(file).All(b=>b==(fixedMode?4:0)),"Empty replacement overwrote valid checkpoint");
 }
 // A rejected worker snapshot must still be replaced, even after recycling.
 {
  AppDataManager.BaseDirPath=Path.Combine(root,"rejected-worker");
  string dir=Path.Combine(AppDataManager.BaseDirPath,"cache","vulkan");Directory.CreateDirectory(dir);
  string file=Path.Combine(dir,"pipeline-00000001-00000002-00000003-0100f7e00c70e000.worker0.vkpc");
  File.WriteAllBytes(file,Enumerable.Repeat((byte)42,16).ToArray());
  var api=new Vk {RejectNextSnapshot=true};
  using var cache=new PipelineCacheManager(api,new(),new(),1,new Lock());
  Budget(State(cache,true),64);Budget(State(cache,false),8);
  api.Set(cache.GetWorkerCache(0),2);cache.NotifyWorkerPipelineCreated(0);
  cache.MergeAndSave();
  Check(File.ReadAllBytes(file).All(b=>b==0),"Rejected worker snapshot incorrectly preserved");
 }
 Console.WriteLine(JsonSerializer.Serialize(new { checks, mode=fixedMode?"fixed":"control",
  recycledDataPreserved=fixedMode, budgetFallbackVerified=true, failedMergeFallbackVerified=true,
  opaqueMergeGrowthCovered=true, nativeCachesDoubled=true, physicalDeviceTested=false }));
} finally {Directory.Delete(root,true);}
''')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'Probe.csproj'),
                                 '-c', 'Release', '--', 'fixed' if adapted else 'control'],
                                capture_output=True, text=True, timeout=120)
        if result.returncode:
            print(result.stdout, result.stderr)
            result.check_returncode()
        reports.append(json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{'))))
inputs = ['build-utils/melonx/adapt_pipeline_cache.py', 'build-utils/melonx/adapt_pipeline_recycle.py',
          'test/melonx_pipeline_recycle_test.py', 'test/melonx_pipeline_cache/Double.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={path: hashlib.sha256((SOURCE / path).read_bytes()).hexdigest()})
output = ROOT / 'dist/melonx/pipeline-recycle-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2)+'\n')
print(json.dumps(receipt))
