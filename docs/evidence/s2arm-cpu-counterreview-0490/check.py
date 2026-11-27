from pathlib import Path
import argparse,json,os,statistics,subprocess,shutil
parser=argparse.ArgumentParser(description="Extract and compare the actual S2Arm session-table methods on .NET 10.")
parser.add_argument('--reference',type=Path,required=True,help='Dispatcher.cs before 0493')
parser.add_argument('--candidate',type=Path,required=True,help='Dispatcher.cs with 0493')
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--dotnet',default=shutil.which('dotnet') or 'dotnet')
parser.add_argument('--generate-only',action='store_true',help='Generate C# sources without building or running')
ARGS=parser.parse_args()
ROOT=ARGS.output.resolve();ROOT.mkdir(parents=True,exist_ok=True)
DOTNET=ARGS.dotnet
SRC=ARGS.candidate
BEFORE=ARGS.reference
TAIL=r'''
internal (int count, int capacity, int hint) Snapshot() {lock(_sessionLock)return(_sessionCount,_sessions.Length,_freeHint);}
internal bool IsLocked()=>System.Threading.Monitor.IsEntered(_sessionLock);
}
sealed class SessionTarget {
 internal int id, closed;
 internal Dispatcher owner;
 internal SessionTarget(int id,Dispatcher owner){this.id=id;this.owner=owner;}
 internal void Closed(){if(owner.IsLocked())throw new Exception("callback under table lock");if(Interlocked.Increment(ref closed)!=1)throw new Exception("duplicate close");}
}
static class Program {
 static ulong hash=14695981039346656037UL;
 static void Mix(ulong x){unchecked{hash=(hash^x)*1099511628211UL;}}
 static void Require(bool ok,string msg){if(!ok)throw new Exception(msg);}
 static SessionTarget Add(Dispatcher d,int id,List<(ulong c,SessionTarget t)> live){var t=new SessionTarget(id,d);ulong c=d.AddSession(t);Require(c!=0&&ReferenceEquals(d.GetSession(c),t),"create ownership");live.Add((c,t));Mix(c);Mix((ulong)id);return t;}
 static void Remove(Dispatcher d,List<(ulong c,SessionTarget t)> live,int i){var(c,t)=live[i];Require(ReferenceEquals(d.GetSession(c),t),"pre-close ownership");d.RemoveSession(c);Require(t.closed==1,"close once");Require(d.GetSession(c)==null,"gone");d.RemoveSession(c);Require(t.closed==1,"invalid repeat no-op");live[i]=live[^1];live.RemoveAt(live.Count-1);Mix(c);Mix((ulong)t.id);}
 static void Trace(){
  var d=new Dispatcher();var live=new List<(ulong,SessionTarget)>();var rng=new Random(4049);int id=0,ops=0;
  for(int i=0;i<2500;i++){Add(d,++id,live);ops++;}
  for(int i=0;i<100000;i++){
   int kind=rng.Next(4);
   if(kind<2&&live.Count<3500||live.Count==0)Add(d,++id,live);
   else if(kind==2)Remove(d,live,rng.Next(live.Count));
   else {var(c,t)=live[rng.Next(live.Count)];Require(ReferenceEquals(d.GetSession(c),t),"get ownership");Mix(c);Mix((ulong)t.id);}
   var s=d.Snapshot();Require(s.count==live.Count,"count");Mix((ulong)s.count);Mix((ulong)s.capacity);Mix((ulong)s.hint);ops++;
   if(i%31==0){d.RemoveSession(0);d.RemoveSession(ulong.MaxValue);Require(d.GetSession(0)==null&&d.GetSession(ulong.MaxValue)==null,"invalid cookie");}
  }
  while(live.Count>0)Remove(d,live,live.Count-1);
  Require(d.Snapshot().count==0,"empty");
  Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new{test="trace",ops,objects=id,digest=hash.ToString("x16"),capacity=d.Snapshot().capacity}));
 }
 static void Concurrent(){
  var d=new Dispatcher();int errors=0,closes=0;var failures=new System.Collections.Concurrent.ConcurrentQueue<string>();
  Parallel.For(0,8,worker=>{try{for(int i=0;i<16000;i++){
   var t=new SessionTarget(worker*16000+i,d);ulong c=d.AddSession(t);
   if((i&7)==0)Thread.Yield();
   Require(ReferenceEquals(d.GetSession(c),t),"concurrent ownership");
   d.RemoveSession(c);Require(t.closed==1,"concurrent close");Interlocked.Increment(ref closes);
  }}catch(Exception e){Interlocked.Increment(ref errors);failures.Enqueue(e.Message);}});
  Require(errors==0,string.Join(",",failures));Require(closes==128000&&d.Snapshot().count==0,"concurrent final");
  Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new{test="concurrent",workers=8,operations=closes,errors}));
 }
 static void Bench(int filled){
  var d=new Dispatcher();for(int i=0;i<filled;i++)d.AddSession(new SessionTarget(i,d));var t=new SessionTarget(0,d);ulong sink=0;
  for(int i=0;i<20000;i++){ulong c=d.AddSession(t);d.RemoveSession(c);sink+=c;t.closed=0;}
  const int loops=200000;
  var sw=Stopwatch.StartNew();
  for(int i=0;i<loops;i++){ulong c=d.AddSession(t);d.RemoveSession(c);sink+=c;t.closed=0;}
  sw.Stop();
  Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new{test="bench",filled,ns=sw.Elapsed.TotalNanoseconds/loops,sink}));
 }
 static void Main(string[]args){if(args.Length>0&&args[0]=="bench")Bench(int.Parse(args[1]));else{Trace();Concurrent();}}
}
'''

def project(name,p):
 s=p.read_text();start=s.index('        internal ulong AddSession(');end=s.index('        // 给游戏发一个会话句柄',start)
 methods=s[start:end]
 flag=next((line+'\n' for line in s.splitlines() if 'private static readonly bool RbSessionScan =' in line),'') if 'RbSessionScan' in methods else ''
 code='using System;using System.Collections.Generic;using System.Threading;using System.Threading.Tasks;using System.Diagnostics;\nsealed class Dispatcher {\n'+flag+'private readonly object _sessionLock = new(); private SessionTarget[] _sessions = new SessionTarget[1024]; private int _sessionCount; private int _freeHint;\n'+methods+TAIL
 folder=ROOT/name;folder.mkdir(exist_ok=True)
 (folder/'Program.cs').write_text(code)
 (folder/'bench.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable><Optimize>true</Optimize></PropertyGroup></Project>')
 (folder/'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
 if ARGS.generate_only:return folder/'bin/Release/net10.0/bench.dll'
 proc=subprocess.run([DOTNET,'build','-c','Release','--nologo'],cwd=folder,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 (folder/'build.log').write_text(proc.stdout)
 if proc.returncode:raise RuntimeError(proc.stdout)
 return folder/'bin/Release/net10.0/bench.dll'

def run(dll,flag,*args):
 env=os.environ.copy();env['S2A_RB_SESSION_SCAN']=str(flag);env['DOTNET_TieredCompilation']='0';env['DOTNET_CLI_TELEMETRY_OPTOUT']='1'
 r=subprocess.run([DOTNET,str(dll),*map(str,args)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
 if r.returncode:raise RuntimeError(r.stdout)
 return [json.loads(x) for x in r.stdout.splitlines() if x.startswith('{')]

before=project('before',BEFORE);after=project('after',SRC)
if ARGS.generate_only:raise SystemExit(0)
proof=[]
for name,dll,flag in [('reference0479',before,1),('0493_flag0',after,0),('0493_flag1',after,1)]:
 result=run(dll,flag);proof.append({'variant':name,'results':result})
assert len({p['results'][0]['digest'] for p in proof})==1
(ROOT/'correctness.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps(proof,indent=2),flush=True)
rows=[]
for filled in [0,512,1023]:
 for pair in range(6):
  choices=[('reference0479',before,1),('0493_flag0',after,0),('0493_flag1',after,1)]
  if pair%2:choices.reverse()
  for name,dll,flag in choices:
   row=run(dll,flag,'bench',filled)[0];row.update(variant=name,pair=pair);rows.append(row)
(ROOT/'timing.json').write_text(json.dumps(rows,indent=2)+'\n')
summary=[]
for filled in [0,512,1023]:
 summary.append({'filled':filled,**{name:statistics.median(r['ns'] for r in rows if r['filled']==filled and r['variant']==name)for name in ['reference0479','0493_flag0','0493_flag1']}})
(ROOT/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
