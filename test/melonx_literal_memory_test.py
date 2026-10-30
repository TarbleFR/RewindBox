#!/usr/bin/env python3
"""Execute exact literal-lowering bodies with the real pinned A64 assembler."""
import hashlib,json,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(ROOT/'build-utils/melonx'))
from adapt_literal_memory import apply

def member(s,declaration,start=0):
 a=s.index(declaration,start);b=s.index('{',a);depth=1
 for i in range(b+1,len(s)):
  depth+=(s[i]=='{')-(s[i]=='}')
  if depth==0:return s[a:i+1],i+1
 raise AssertionError(declaration)

path='src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/InstEmitMemory.cs'
pin=json.loads((ROOT/'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git','-C',str(ROOT/'.native-sources/MeloNX'),'rev-parse','HEAD'],text=True).strip()==pin['revision']
assert (SOURCE/path).read_bytes()==(ROOT/'.native-sources/MeloNX'/path).read_bytes()
with tempfile.TemporaryDirectory(prefix='melonx-literal-')as tmp:
 w=Path(tmp);a=w/'source';p=a/path;p.parent.mkdir(parents=True);shutil.copyfile(SOURCE/path,p);apply(a)
 imports='''using System; using System.Diagnostics; using Ryujinx.Cpu.LightningJit;
using ARMeilleure.Memory; using Ryujinx.Cpu.LightningJit.CodeGen;
using Ryujinx.Cpu.LightningJit.CodeGen.Arm64; using Ryujinx.Cpu.LightningJit.Arm64;
'''
 wrappers=[]
 for name,s in [('Baseline',(SOURCE/path).read_text(encoding='utf-8-sig')),('Candidate',p.read_text())]:
  bodies=[member(s,'private static void RewriteLiteralMemoryInstruction')[0],member(s,'private static void WriteAddConstant')[0]]
  start=0
  for _ in range(3):body,start=member(s,'private static void WriteAddressTranslation',start);bodies.append(body)
  wrappers.append('static class '+name+' { '+''.join(bodies)+'''
public static int LastLeases;
public static uint[] Emit(MemoryManagerType mm, InstName name, uint encoding) {
 var writer=new Ryujinx.Cpu.LightningJit.CodeWriter(); var ra=new RegisterAllocator();
 RewriteLiteralMemoryInstruction(39,mm,writer,ra,name,0x400000,encoding);
 LastLeases=ra.Leases; return writer.AsSpan().ToArray(); }
}''')
 (w/'Methods.cs').write_text(imports+'\n'.join(wrappers)+'''
namespace ARMeilleure.Memory {
 enum MemoryManagerType { HostMappedUnsafe, HostMapped, HostTrackedUnsafe, HostTracked }
 static class MemoryManagerExt { extension(MemoryManagerType m) {
 public bool IsHostTracked => m is MemoryManagerType.HostTracked or MemoryManagerType.HostTrackedUnsafe;
 public bool IsHostMapped => m is MemoryManagerType.HostMapped or MemoryManagerType.HostMappedUnsafe; } }
}
namespace Ryujinx.Cpu.LightningJit.Arm64 { enum InstName { Adr,Adrp,LdrLitGen,LdrswLit,LdrLitFpsimd,PrfmLit } }
static class RegisterUtils { public const int ZrIndex=31; }
sealed class RegisterAllocator { public int Leases; public int FixedPageTableRegister=>19;
 public int AllocateTempGprRegister()=>20+Leases++;
 public void FreeTempGprRegister(int r) { if(r!=19+Leases)throw new Exception("Scratch order"); Leases--; } }
''')
 files=[*sorted((SOURCE/'src/Ryujinx.Cpu/LightningJit/CodeGen').glob('*.cs')),
  *(SOURCE/('src/Ryujinx.Cpu/LightningJit/CodeGen/Arm64/'+n)for n in ['Assembler.cs','ArmCondition.cs','ArmExtensionType.cs','ArmShiftType.cs','CodeGenCommon.cs']),
  SOURCE/'src/Ryujinx.Cpu/LightningJit/CodeWriter.cs']
 for p in files:shutil.copyfile(p,w/p.name)
 shutil.copyfile(ROOT/'test/melonx_literal_memory/Program.cs',w/'Program.cs')
 (w/'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion><ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit></PropertyGroup><ItemGroup><Compile Remove="source/**/*.cs" /></ItemGroup></Project>''')
 (w/'global.json').write_text(json.dumps({'sdk':{'version':pin['dotnet'],'rollForward':'disable'}}))
 r=subprocess.run(['dotnet','run','--project',str(w),'-c','Release','-v','q'],capture_output=True,text=True,timeout=180)
 if r.returncode:print(r.stdout,r.stderr);r.check_returncode()
 report=json.loads(next(l for l in r.stdout.splitlines()if l.startswith('{')))
 report.update(physicalDeviceTested=False,upstreamRevision=pin['revision'],inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path(__file__),ROOT/'test/melonx_literal_memory/Program.cs',ROOT/'build-utils/melonx/adapt_literal_memory.py']},upstreamInputs={str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE/path,*files]})
 out=ROOT/'dist/melonx/literal-memory-checks.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
