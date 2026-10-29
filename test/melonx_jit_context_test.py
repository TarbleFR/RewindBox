#!/usr/bin/env python3
"""Exercise emitted NEON context transfers and the production code-page reader.

No emulated game or generated ARM64 code is executed. This builds the exact
adapted compiler methods with the pinned real assembler and independently
decodes its memory instructions, checking every live slot and no extra slot.
The exact adapted CodeReader executes against a memory-manager double.
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
from adapt_jit_context import apply as context_apply
from adapt_jit_decoder import apply as decoder_apply


def member(text, declaration):
    start = text.index(declaration)
    opening = text.index('{', start)
    depth = 1
    for index in range(opening + 1, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(declaration)


pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
assert subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip() == pin['revision']
compiler = 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Compiler.cs'
decoder = 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs'
translator = 'src/Ryujinx.Cpu/LightningJit/Translator.cs'
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', compiler, decoder, translator], text=True).strip()
with tempfile.TemporaryDirectory(prefix='melonx-context-') as temporary:
    work = Path(temporary)
    adapted = work / 'source'
    for path in (compiler, decoder, translator):
        target = adapted / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / path, target)
    context_apply(adapted)
    decoder_apply(adapted)
    wrappers = []
    for name, path in [('Baseline', SOURCE / compiler), ('Adapted', adapted / compiler)]:
        text = path.read_text(encoding='utf-8-sig')
        methods = '\n'.join(member(text, f'private void {op}FpSimd{direction}Context')
                            for op, direction in [('Load', 'From'), ('Store', 'To')])
        register = member(text, 'private static Operand Register')
        wrappers.append(f'''sealed class {name} {{
            private static class RegisterAllocator {{ public const int FixedContextRegister = 19; }}
            {methods}
            {register}
            public uint[] Emit(bool load, uint mask, int offset) {{
                CodeWriter writer = new(); Assembler asm = new(writer);
                if (load) LoadFpSimdFromContext(ref asm, mask, offset);
                else StoreFpSimdToContext(ref asm, mask, offset);
                return writer.AsSpan().ToArray();
            }}
        }}''')
    reader = member((adapted / decoder).read_text(), 'private sealed class CodeReader')
    wrappers.append('''sealed class ReaderProbe {
        private readonly CodeReader _reader;
        public ReaderProbe(IMemoryManager memory) { _reader = CodeReader.For(memory); }
        public uint Read(ulong address) => _reader.Read(address);
        public bool EndsBefore(ulong address) => _reader.EndsBefore(address);
        ''' + reader + '\n}')
    imports = '''using System;
using System.Collections.Generic;
using System.Linq;
using System.Numerics;
using System.Runtime.InteropServices;
using System.Text.Json;
using Ryujinx.Cpu.LightningJit;
using Ryujinx.Cpu.LightningJit.CodeGen;
using Ryujinx.Cpu.LightningJit.CodeGen.Arm64;
'''
    (work / 'ProductionMethods.cs').write_text(imports + '\n'.join(wrappers))
    files = [*sorted((SOURCE / 'src/Ryujinx.Cpu/LightningJit/CodeGen').glob('*.cs')),
             *(SOURCE / ('src/Ryujinx.Cpu/LightningJit/CodeGen/Arm64/' + name)
               for name in ['Assembler.cs', 'ArmCondition.cs', 'ArmExtensionType.cs', 'ArmShiftType.cs', 'CodeGenCommon.cs']),
             SOURCE / 'src/Ryujinx.Cpu/LightningJit/CodeWriter.cs']
    for path in files:
        shutil.copyfile(path, work / path.name)
    shutil.copyfile(ROOT / 'test/melonx_jit_context/Program.cs', work / 'Program.cs')
    (work / 'ContextProbe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally><NuGetAudit>false</NuGetAudit>
</PropertyGroup><ItemGroup><Compile Remove="source/**/*.cs" /></ItemGroup></Project>''')
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'latestFeature'}}))
    result = subprocess.run(['dotnet', 'run', '--project', str(work), '-c', 'Release', '-v', 'q'],
                            capture_output=True, text=True, timeout=180)
    if result.returncode:
        print(result.stdout, result.stderr)
        result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    report.update(result='passed', generatedArm64Executed=False, physicalDeviceTested=False,
                  upstreamRevision=pin['revision'],
                  inputs={str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in [ROOT / 'build-utils/melonx/adapt_jit_context.py',
                                       ROOT / 'build-utils/melonx/adapt_jit_decoder.py', Path(__file__),
                                       ROOT / 'test/melonx_jit_context/Program.cs']},
                  upstreamInputs={str(path.relative_to(SOURCE)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in [SOURCE / compiler, SOURCE / decoder, SOURCE / translator, *files]})
    output = ROOT / 'dist/melonx/jit-context-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
