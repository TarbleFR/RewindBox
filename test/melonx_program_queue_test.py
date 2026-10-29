#!/usr/bin/env python3
"""Run the real program queue with eight occupied compiler slots.

Only the backend completion/clock is doubled; no GPU or gameplay claim.
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
from adapt_shader_waits import apply

paths = ['src/Ryujinx.Graphics.GAL/Multithreading/Resources/ProgramQueue.cs',
         'src/Ryujinx.Graphics.Vulkan/PipelineConverter.cs']
reports = []
with tempfile.TemporaryDirectory(prefix='melonx-program-queue-') as temporary:
    for adapted in (False, True):
        work = Path(temporary) / ('fixed' if adapted else 'control')
        source = work / 'source'
        for path in paths:
            target = source / path
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / path, target)
        if adapted:
            apply(source)
        shutil.copyfile(source / paths[0], work / 'ProgramQueue.cs')
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<TargetFramework>net10.0</TargetFramework><OutputType>Exe</OutputType>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        (work / 'Program.cs').write_text(r'''
using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Diagnostics;
using System.Text.Json;
using Ryujinx.Graphics.GAL;
using Ryujinx.Graphics.GAL.Multithreading.Resources;
using Ryujinx.Graphics.GAL.Multithreading.Resources.Programs;
namespace Ryujinx.Graphics.GAL {
 enum ProgramLinkStatus { Incomplete, Success, Failure }
 interface IProgram { ProgramLinkStatus CheckProgramLink(bool blocking); }
 interface IRenderer {}
}
namespace Ryujinx.Graphics.GAL.Multithreading.Resources {
 class ThreadedProgram { public IProgram Base; public bool Compiled; }
}
namespace Ryujinx.Graphics.GAL.Multithreading.Resources.Programs {
 interface IProgramRequest { ThreadedProgram Threaded { get; set; } IProgram Create(IRenderer renderer); }
}
class Backend : IProgram {
 public int Polls, Complete;
 public ProgramLinkStatus CheckProgramLink(bool blocking) {
  if(blocking) throw new Exception("Must not block on one arbitrary compiler slot");
  Polls++;
  return Volatile.Read(ref Complete)!=0 ? ProgramLinkStatus.Success : ProgramLinkStatus.Incomplete;
 }
}
class Request : IProgramRequest {
 public ThreadedProgram Threaded { get; set; } = new();
 public Backend Backend = new(); public int Created;
 public IProgram Create(IRenderer renderer) { Created++; return Backend; }
}
class Probe {
 static void Main() {
  var queue=new ProgramQueue(null);
  var requests=Enumerable.Range(0,9).Select(_=>new Request()).ToArray();
  foreach(var request in requests) queue.Add(request);
  queue.ProcessQueue();
  if(requests.Take(8).Any(r=>r.Created!=1) || requests[8].Created!=0) throw new Exception("Compile cap");
  using var done=new ManualResetEventSlim();
  using var started=new ManualResetEventSlim();
  var completion=Task.Run(()=> {
   started.Set();
   if(done.Wait(100)) throw new Exception("Target created before a slot became free");
   // Slot 0 remains busy: waiting for it would stall although slot 7 is free.
   Volatile.Write(ref requests[7].Backend.Complete,1);
  });
  started.Wait();
  var timer=Stopwatch.StartNew();
  queue.EnsureProgramCreated(requests[8].Threaded);
  done.Set();
  completion.GetAwaiter().GetResult();
  timer.Stop();
  if(!requests[7].Threaded.Compiled || requests[0].Threaded.Compiled || requests[8].Created!=1 ||
     requests.Any(r=>r.Created!=1)) throw new Exception("First available slot/order/one create");
  queue.EnsureProgramCreated(requests[8].Threaded);
  Console.WriteLine(JsonSerializer.Serialize(new {
   polls=requests.Sum(r=>r.Backend.Polls), milliseconds=timer.Elapsed.TotalMilliseconds,
   checks=5, deviceTested=false
  }));
 }
}
''')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'Probe.csproj'),
                                 '-c', 'Release'], capture_output=True, text=True, timeout=120)
        if result.returncode:
            print(result.stdout, result.stderr)
            result.check_returncode()
        reports.append(json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{'))))
    assert reports[1]['polls'] < 2000, reports
inputs = ['build-utils/melonx/adapt_shader_waits.py', 'test/melonx_program_queue_test.py']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in paths})
output = ROOT / 'dist/melonx/program-queue-checks.json'
output.parent.mkdir(parents=True, exist_ok=True)
output.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(receipt))
