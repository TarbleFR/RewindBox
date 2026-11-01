#!/usr/bin/env python3
"""Execute the real A57 decoder, liveness masks, dataflow and context transfers.

Baseline is the delivered ae78b4b preparation of these sources (vector-mask,
context and dataflow adapters applied). Candidate adds adapt_register_liveness.
Both keep the pinned production table, RegisterUtils, Block/MultiBlock/DataFlow,
context-transfer methods and ARM64 assembler. Emitted words are decoded
independently; generated ARM64 is not executed and no device is involved.
"""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_vector_register_masks import apply as vector_apply
from adapt_jit_context import apply as context_apply
from adapt_jit_dataflow import apply as dataflow_apply
from adapt_register_liveness import apply as liveness_apply


def member(text, declaration):
    start = text.index(declaration)
    opening = text.index('{', start)
    depth = 1
    for end in range(opening + 1, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            return text[start:end + 1]
    raise AssertionError(declaration)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


BASE = 'src/Ryujinx.Cpu/LightningJit/'
REGISTERS = BASE + 'Arm64/RegisterUtils.cs'
COMPILER = BASE + 'Arm64/Target/Arm64/Compiler.cs'
TABLE = BASE + 'Arm64/Target/Arm64/InstTable.cs'
DECODER = BASE + 'Arm64/Target/Arm64/Decoder.cs'
DATAFLOW = BASE + 'Graph/DataFlow.cs'
# Decoder.DecodeMulti's PSTATE liveness, replicated by the fixture.
PSTATE = '''                if (flags.HasFlag(InstFlags.Nzcv) || IsMrsNzcv(encoding))
                {
                    instPStateReadMask = NzcvFlags;
                }
                else if (flags.HasFlag(InstFlags.C))
                {
                    instPStateReadMask = CFlag;
                }

                if (flags.HasFlag(InstFlags.S) || IsMsrNzcv(encoding))
                {
                    instPStateWriteMask = NzcvFlags;
                }'''
PSTATE_HELPERS = ['return (encoding & ~0x1fu) == 0xd53b4200u;', 'return (encoding & ~0x1fu) == 0xd51b4200u;',
                  'private const uint NzcvFlags = 0xfu << 28;', 'private const uint CFlag = 0x1u << 29;']

pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
decoder = (SOURCE / DECODER).read_text(encoding='utf-8-sig')
assert decoder.count(PSTATE) == 1 and all(decoder.count(line) == 1 for line in PSTATE_HELPERS), 'Decoder PSTATE logic drifted'

with tempfile.TemporaryDirectory(prefix='melonx-register-liveness-') as temporary:
    work = Path(temporary).resolve()
    trees = {}
    for kind in ('baseline', 'candidate'):
        tree = work / kind
        for name in (REGISTERS, COMPILER, TABLE, DATAFLOW):
            path = tree / name
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, path)
        vector_apply(tree); context_apply(tree); dataflow_apply(tree)
        trees[kind] = tree
    liveness_apply(trees['candidate'])
    try:
        liveness_apply(trees['candidate'])
    except AssertionError:
        reapplied = False
    else:
        reapplied = True
    assert not reapplied, 'Liveness adapter must refuse to apply twice'
    project = work / 'probe'
    project.mkdir()
    baseline, candidate = trees['baseline'], trees['candidate']
    (project / 'BaselineRegisterUtils.cs').write_text(
        (baseline / REGISTERS).read_text().replace('static class RegisterUtils', 'static class BaselineRegisterUtils', 1))
    (project / 'BaselineInstTable.cs').write_text(
        (baseline / TABLE).read_text().replace('static class InstTable', 'static class BaselineInstTable', 1)
        .replace('static InstTable()', 'static BaselineInstTable()', 1))
    shutil.copyfile(candidate / REGISTERS, project / 'RegisterUtils.cs')
    shutil.copyfile(candidate / TABLE, project / 'InstTable.cs')
    shutil.copyfile(candidate / DATAFLOW, project / 'DataFlow.cs')
    compiler = (candidate / COMPILER).read_text()
    assert compiler == (baseline / COMPILER).read_text(), 'Adapter must not change context transfers'
    methods = '\n'.join(member(compiler, f'private void {operation}{kind}{direction}Context')
                        for kind in ('FpSimd', 'PState') for operation, direction in (('Load', 'From'), ('Store', 'To')))
    (project / 'ContextTransfers.cs').write_text('''using System;using System.Numerics;
using Ryujinx.Cpu.LightningJit;using Ryujinx.Cpu.LightningJit.CodeGen;using Ryujinx.Cpu.LightningJit.CodeGen.Arm64;
sealed class ContextTransfers {
 // Production methods address the context through X19 and borrow one temp.
 private static class RegisterAllocator {
  public const int FixedContextRegister = 19;
  public static int AllocateTempGprRegister() => 17;
  public static void FreeTempGprRegister(int register) { }
 }
''' + methods + '\n' + member(compiler, 'private static Operand Register') + '''
 public uint[] EmitFp(bool load, uint mask, int offset) {
  CodeWriter writer = new(); Assembler asm = new(writer);
  if (load) LoadFpSimdFromContext(ref asm, mask, offset); else StoreFpSimdToContext(ref asm, mask, offset);
  return writer.AsSpan().ToArray(); }
 public uint[] EmitFlags(bool load, uint mask, int offset) {
  CodeWriter writer = new(); Assembler asm = new(writer);
  if (load) LoadPStateFromContext(ref asm, mask, offset); else StorePStateToContext(ref asm, mask, offset);
  return writer.AsSpan().ToArray(); }
}
namespace Ryujinx.Cpu.LightningJit.Arm64 {
 // Only required to compile the unrelated register remap helper.
 sealed class RegisterAllocator { public int RemapReservedGprRegister(int index) => index; }
}
''')
    names = ['Arm64/InstFlags.cs', 'Arm64/InstName.cs', 'Arm64/InstInfo.cs', 'Arm64/Block.cs', 'Arm64/MultiBlock.cs',
             'IsaVersion.cs', 'IsaFeature.cs', 'AddressForm.cs', 'CodeWriter.cs', 'CpuPreset.cs', 'CpuPresets.cs',
             'CodeGen/Arm64/Assembler.cs', 'CodeGen/Arm64/ArmCondition.cs', 'CodeGen/Arm64/ArmExtensionType.cs',
             'CodeGen/Arm64/ArmShiftType.cs', 'CodeGen/Arm64/CodeGenCommon.cs']
    files = [SOURCE / (BASE + name) for name in names]
    for folder in ('Graph', 'Table', 'CodeGen'):
        files += sorted(path for path in (SOURCE / (BASE + folder)).glob('*.cs') if path.name != 'DataFlow.cs')
    for path in files:
        shutil.copyfile(path, project / path.name)
    shutil.copyfile(ROOT / 'test/melonx_register_liveness/Program.cs', project / 'Program.cs')
    (project / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit>
</PropertyGroup></Project>''')
    (project / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
    result = subprocess.run(['dotnet', 'run', '--project', str(project), '-c', 'Release', '-v', 'q'],
                            capture_output=True, text=True, timeout=300)
    if result.returncode:
        print(result.stdout, result.stderr)
        result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    report.update(result='passed', generatedArm64Executed=False, physicalDeviceTested=False,
                  hogwartsCrashCauseProven=False, adapterRefusesReapplication=True, upstreamRevision=pin['revision'],
                  inputs={str(path.relative_to(ROOT)): digest(path) for path in [
                      Path(__file__), ROOT / 'test/melonx_register_liveness/Program.cs',
                      ROOT / 'build-utils/melonx/adapt_register_liveness.py',
                      ROOT / 'build-utils/melonx/adapt_vector_register_masks.py',
                      ROOT / 'build-utils/melonx/adapt_jit_context.py', ROOT / 'build-utils/melonx/adapt_jit_dataflow.py']},
                  upstreamInputs={str(path.relative_to(SOURCE)): digest(path) for path in
                                  [SOURCE / REGISTERS, SOURCE / COMPILER, SOURCE / TABLE, SOURCE / DECODER,
                                   SOURCE / DATAFLOW, *files]},
                  preimages={name: digest(baseline / name) for name in (REGISTERS, TABLE)},
                  postimages={name: digest(candidate / name) for name in (REGISTERS, TABLE)})
    out = ROOT / 'dist/melonx/register-liveness-checks.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
