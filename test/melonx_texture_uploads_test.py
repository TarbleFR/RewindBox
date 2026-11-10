#!/usr/bin/env python3
"""Compare production texture uploads using native transfer doubles.

Real TextureView upload/copy methods, StagingBuffer and TextureCreateInfo run.
Commands read their source bytes only when the test completes their fences,
so premature ring reuse changes the resulting payload hash and fails.
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
from adapt_texture_uploads import apply


def method(text, signature):
    start = text.index(signature)
    brace = text.index('{', start)
    depth, end = 1, brace + 1
    while depth:
        if text[end] == '{': depth += 1
        if text[end] == '}': depth -= 1
        end += 1
    return text[start:end]


texture_path = 'src/Ryujinx.Graphics.Vulkan/TextureView.cs'
manager_path = 'src/Ryujinx.Graphics.Vulkan/BufferManager.cs'
production = ['src/Ryujinx.Graphics.Vulkan/' + p + '.cs' for p in ('StagingBuffer', 'FormatConverter')]
production += ['src/Ryujinx.Graphics.GAL/' + p + '.cs'
               for p in ('TextureCreateInfo', 'Format', 'Target', 'DepthStencilMode', 'SwizzleComponent', 'Rectangle')]
reports = []
with tempfile.TemporaryDirectory(prefix='melonx-texture-uploads-') as temporary:
    for control in (True, False):
        work = Path(temporary) / ('control' if control else 'fixed')
        source = work / 'source'
        target = source / texture_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / texture_path, target)
        shutil.copyfile(SOURCE / manager_path, source / manager_path)
        shutil.copyfile(SOURCE / production[0], source / production[0])
        if not control: apply(source)
        text = target.read_text()
        methods = '\n'.join(method(text, signature) for signature in (
            'private void SetData(ReadOnlySpan<byte> data,',
            'private int GetBufferDataLength(',
            'private void CopyDataToBuffer(',
            'private bool NeedsD24S8Conversion()',
            'public void CopyFromOrToBuffer(',
            'private void CopyFromOrToBuffer(',
            'private static int AlignUpNpot(',
        ))
        template = (ROOT / 'test/melonx_texture_uploads/Double.cs').read_text()
        manager = (source / manager_path).read_text()
        manager = manager[manager.index('class BufferManager'):]
        pool_method = '' if control else method(manager, 'internal StagingBuffer GetTextureStagingBuffer(')
        disposal = '\n'.join(method(manager, signature) for signature in (
            'protected virtual void Dispose(bool disposing)', 'public void Dispose()'))
        (work / 'Double.cs').write_text(template.replace('/* PRODUCTION_METHODS */', methods)
                                     .replace('/* TEXTURE_POOL_METHOD */', pool_method)
                                     .replace('/* MANAGER_DISPOSAL */', disposal))
        for path in production:
            shutil.copyfile(source / path if (source / path).exists() else SOURCE / path,
                            work / Path(path).name)
        shutil.copyfile(ROOT / 'test/melonx_texture_uploads/Program.cs', work / 'Program.cs')
        (work / 'test.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><LangVersion>preview</LangVersion>
<AllowUnsafeBlocks>true</AllowUnsafeBlocks>
</PropertyGroup><ItemGroup><Compile Remove="source/**" /></ItemGroup></Project>''')
        result = subprocess.run(['dotnet', 'run', '--project', str(work / 'test.csproj'),
                                 '-c', 'Release', '--', 'control' if control else 'fixed'],
                                capture_output=True, text=True, timeout=120)
        print(result.stdout, flush=True)
        if result.returncode: print(result.stderr, flush=True)
        result.check_returncode()
        reports.append(json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{'))))
control, fixed = reports
assert control['payloadDigests'] == fixed['payloadDigests'], 'Delayed GPU copies changed their bytes'
assert control['ordinaryUploadsNativeBuffers'] == 1024
assert fixed['ordinaryUploadsNativeBuffers'] == 1
assert control['fullRingFallbackBuffers'] == 4098
assert fixed['fullRingFallbackBuffers'] == 3
inputs = ['build-utils/melonx/adapt_texture_uploads.py', 'test/melonx_texture_uploads_test.py',
          'test/melonx_texture_uploads/Double.cs', 'test/melonx_texture_uploads/Program.cs']
receipt = dict(result='passed', reports=reports, physicalDeviceTested=False, vulkanDouble=True,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest()
                               for p in [texture_path, manager_path, *production]})
out = ROOT / 'dist/melonx/texture-upload-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
