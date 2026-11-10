#!/usr/bin/env python3
"""Execute real A64 decoding/liveness and decode its emitted context transfers.

The regression preserves original and corrected RegisterUtils in one assembly.
The pinned instruction table, dataflow graph, context methods and assembler
are production sources. Emitted ARM64 is independently decoded, not executed.
"""
from pathlib import Path
import hashlib,json,shutil,subprocess,sys,tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(sys.argv[1]).resolve()
sys.path.insert(0,str(ROOT/'build-utils/melonx'))
from adapt_vector_register_masks import apply
from adapt_jit_context import apply as context_apply
from adapt_jit_dataflow import apply as dataflow_apply

def member(text,declaration):
    start=text.index(declaration); opening=text.index('{',start); depth=1
    for end in range(opening+1,len(text)):
        depth+=(text[end]=='{')-(text[end]=='}')
        if depth==0:return text[start:end+1]
    raise AssertionError(declaration)

base='src/Ryujinx.Cpu/LightningJit/'
registers=base+'Arm64/RegisterUtils.cs'
compiler=base+'Arm64/Target/Arm64/Compiler.cs'
table=base+'Arm64/Target/Arm64/InstTable.cs'
pin=json.loads((ROOT/'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git','-C',str(SOURCE),'rev-parse','HEAD'],text=True).strip()==pin['revision']
with tempfile.TemporaryDirectory(prefix='melonx-vector-masks-') as temporary:
    work=Path(temporary).resolve(); adapted=work/'source'
    for name in (registers,compiler,table,base+'Graph/DataFlow.cs'):
        path=adapted/name;path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(SOURCE/name,path)
    original=(SOURCE/registers).read_text()
    apply(adapted);context_apply(adapted);dataflow_apply(adapted)
    (work/'BaselineRegisterUtils.cs').write_text(original.replace('static class RegisterUtils','static class BaselineRegisterUtils',1))
    (work/'BaselineInstTable.cs').write_text((SOURCE/table).read_text().replace('static class InstTable','static class BaselineInstTable',1).replace('static InstTable()', 'static BaselineInstTable()',1))
    shutil.copyfile(adapted/registers,work/'RegisterUtils.cs')
    text=(adapted/compiler).read_text()
    methods='\n'.join(member(text,f'private void {op}FpSimd{direction}Context')for op,direction in [('Load','From'),('Store','To')])
    wrapper='''using System;using System.Numerics;
using Ryujinx.Cpu.LightningJit;using Ryujinx.Cpu.LightningJit.CodeGen;using Ryujinx.Cpu.LightningJit.CodeGen.Arm64;
sealed class ContextTransfers {
 private static class RegisterAllocator { public const int FixedContextRegister=19; }
'''+methods+'\n'+member(text,'private static Operand Register')+'''
 public uint[] Emit(bool load,uint mask) {
 CodeWriter writer=new();Assembler asm=new(writer);
 if(load)LoadFpSimdFromContext(ref asm,mask,256);else StoreFpSimdToContext(ref asm,mask,256);
 return writer.AsSpan().ToArray(); }
}
namespace Ryujinx.Cpu.LightningJit.Arm64 {
 // Only required to compile the unrelated public remap helper. Mask functions
 // and the real instruction table do not invoke this test double.
 sealed class RegisterAllocator { public int RemapReservedGprRegister(int index)=>index; }
}
'''
    (work/'ContextTransfers.cs').write_text(wrapper)
    names=['Arm64/InstFlags.cs','Arm64/InstName.cs','Arm64/InstInfo.cs','Arm64/Block.cs','Arm64/MultiBlock.cs',
           'Arm64/Target/Arm64/InstTable.cs','IsaVersion.cs','IsaFeature.cs','AddressForm.cs','CodeWriter.cs',
           'CodeGen/Arm64/Assembler.cs','CodeGen/Arm64/ArmCondition.cs','CodeGen/Arm64/ArmExtensionType.cs',
           'CodeGen/Arm64/ArmShiftType.cs','CodeGen/Arm64/CodeGenCommon.cs']
    files=[SOURCE/(base+n)for n in names]
    for folder in ('Graph','Table','CodeGen'):files+=sorted((SOURCE/(base+folder)).glob('*.cs'))
    for path in files:shutil.copyfile(path,work/path.name)
    shutil.copyfile(adapted/(base+'Graph/DataFlow.cs'),work/'DataFlow.cs')
    shutil.copyfile(adapted/table,work/'InstTable.cs')
    shutil.copyfile(ROOT/'test/melonx_vector_register_masks/Program.cs',work/'Program.cs')
    (work/'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit>
</PropertyGroup><ItemGroup><Compile Remove="source/**/*.cs" /></ItemGroup></Project>''')
    (work/'global.json').write_text(json.dumps({'sdk':{'version':pin['dotnet'],'rollForward':'disable'}}))
    result=subprocess.run(['dotnet','run','--project',str(work),'-c','Release','-v','q'],capture_output=True,text=True,timeout=180)
    if result.returncode:print(result.stdout,result.stderr);result.check_returncode()
    report=json.loads(next(line for line in result.stdout.splitlines()if line.startswith('{')))
    report.update(result='passed',generatedArm64Executed=False,physicalDeviceTested=False,hogwartsCrashCauseProven=False,
        upstreamRevision=pin['revision'],
        inputs={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [Path(__file__),ROOT/'test/melonx_vector_register_masks/Program.cs',ROOT/'build-utils/melonx/adapt_vector_register_masks.py',ROOT/'build-utils/melonx/adapt_jit_context.py',ROOT/'build-utils/melonx/adapt_jit_dataflow.py']},
        upstreamInputs={str(p.relative_to(SOURCE)):hashlib.sha256(p.read_bytes()).hexdigest()for p in [SOURCE/registers,SOURCE/compiler,*files]},
        postimageSHA256=hashlib.sha256((adapted/registers).read_bytes()).hexdigest(),
        postimages={p:hashlib.sha256((adapted/p).read_bytes()).hexdigest()for p in (registers,table)})
    out=ROOT/'dist/melonx/vector-register-mask-checks.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report))
