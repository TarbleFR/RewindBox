#!/usr/bin/env python3
"""Compare the exact old/new split methods using the pinned real Block and CFG code."""
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
from adapt_jit_block_split import apply


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
decoder = 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs'
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', decoder], text=True).strip()
with tempfile.TemporaryDirectory(prefix='melonx-block-split-') as temporary:
    work = Path(temporary)
    adapted = work / 'source'
    target = adapted / decoder
    target.parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / decoder, target)
    apply(adapted)
    wrappers = []
    for name, path in [('Baseline', SOURCE / decoder), ('Adapted', target)]:
        text = path.read_text(encoding='utf-8-sig')
        methods = [member(text, declaration) for declaration in [
            'private static void SplitBlocks(', 'private static void NumberAndLinkBlocks(',
            'private static bool TryGetBranchTarget(Block ', 'private static bool TryGetBranchTarget(InstName ']]
        if name == 'Adapted':
            methods.append(member(text, 'private static void SplitBlocksUnordered('))
        wrappers.append(f'''static class {name} {{
            {chr(10).join(methods)}
            public static void Split(List<Block> blocks, List<ulong> targets) => SplitBlocks(blocks, targets);
            public static void Link(List<Block> blocks) => NumberAndLinkBlocks(blocks);
        }}''')
    imports = '''using System;
using System.Collections.Generic;
using System.Diagnostics;
using Ryujinx.Cpu.LightningJit;
using Ryujinx.Cpu.LightningJit.Arm64;
using Ryujinx.Cpu.LightningJit.Graph;
'''
    (work / 'ProductionMethods.cs').write_text(imports + '\n'.join(wrappers))
    files = [SOURCE / ('src/Ryujinx.Cpu/LightningJit/' + name) for name in [
        'Arm64/Block.cs', 'Arm64/InstInfo.cs', 'Arm64/InstName.cs', 'Arm64/InstFlags.cs',
        'AddressForm.cs', 'Arm64/ImmUtils.cs', 'Graph/IBlock.cs', 'Graph/RegisterUse.cs', 'Graph/RegisterMask.cs']]
    for path in files:
        shutil.copyfile(path, work / path.name)
    shutil.copyfile(ROOT / 'test/melonx_jit_block_split/Program.cs', work / 'Program.cs')
    (work / 'SplitProbe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
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
                          for path in [ROOT / 'build-utils/melonx/adapt_jit_block_split.py', Path(__file__),
                                       ROOT / 'test/melonx_jit_block_split/Program.cs']},
                  upstreamInputs={str(path.relative_to(SOURCE)): hashlib.sha256(path.read_bytes()).hexdigest()
                                  for path in [SOURCE / decoder, *files]})
    output = ROOT / 'dist/melonx/jit-block-split-checks.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report))
