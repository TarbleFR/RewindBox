#!/usr/bin/env python3
"""adapt_released_texture_flush on the final preparation, against the Core 689 files as control.

Usage: melonx_released_texture_flush_test.py <control> --candidate-source <final preparation containing the adapter>
       melonx_released_texture_flush_test.py <Core 689 prepared MeloNX tree>

IPA 688 (PID 31473) and IPA 690 (PID 32980): signal 11 at 0x111 in MVKCmdBufferImageCopy<1>::setContent under
vkCmdCopyImageToBuffer, on a guest thread flushing a texture: the copy received a null image handle, the value a
destroyed Auto<DisposableImage> returns. For each variant the production GPU and Vulkan assemblies are built, then the
real Auto.cs and the real PersistentFlushBuffer.GetTextureData overloads (with the candidate's AcquireImage) and the
Texture.GetTextureDataFromGpu / GetTextureDataSliceFromGpu wrappers are compiled with doubles
(test/melonx_released_texture_flush/Program.cs). The control must record a copy with a null handle for a released
view (the crash condition); the candidate none, and must keep an image released during recording alive until the copy
completes; a live view copies with its handle in both. No device. Writes dist/melonx/released-texture-flush-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_released_texture_flush', _HOLD)
import adapt_released_texture_flush as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
AUTO = 'src/Ryujinx.Graphics.Vulkan/Auto.cs'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.index(signature)
    start = text.rindex('\n', 0, start) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def extract(tree):
    flush = (tree / adapter.FLUSH).read_text(encoding='utf-8-sig')
    gal = (tree / adapter.GAL).read_text(encoding='utf-8-sig')
    texture = (tree / adapter.TEXTURE).read_text(encoding='utf-8-sig')
    methods = [member(flush, 'public Span<byte> GetTextureData(CommandBufferPool cbp, TextureView view, int size)'),
               member(flush, 'public Span<byte> GetTextureData(CommandBufferPool cbp, TextureView view, int size, int layer, int level)')]
    if 'private static Auto<DisposableImage> AcquireImage(' in flush:
        methods.append(member(flush, 'private static Auto<DisposableImage> AcquireImage('))
    parts = {'FLUSH': '\n'.join(methods) + '\n'}
    if 'class TextureReleasedException' in gal:
        parts['GAL'] = member(gal, 'public sealed class TextureReleasedException') + '\n'
        parts['TEXTURE'] = '\n'.join([member(texture, 'private void GetTextureDataFromGpu('),
                                      member(texture, 'public void GetTextureDataSliceFromGpu('),
                                      member(texture, 'private static void NoteReleasedFlush(')]) + \
            '\n        private static long _releasedFlushes;\n'
    else:
        # Control: no exception type in the engine, and the flush calls the host texture unguarded.
        parts['GAL'] = '    public sealed class TextureReleasedException : System.InvalidOperationException { }\n'
        parts['TEXTURE'] = ('        private void GetTextureDataFromGpu(Span<byte> output, bool blacklist, ITexture texture = null) =>\n'
                            '            GetTextureDataFromGpuUnguarded(output, blacklist, texture);\n'
                            '        public void GetTextureDataSliceFromGpu(Span<byte> output, int layer, int level, bool blacklist, ITexture texture = null) =>\n'
                            '            GetTextureDataSliceFromGpuUnguarded(output, layer, level, blacklist, texture);\n')
    return parts


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 689 preparation: ' + name)

texts, reports = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-released-texture-flush-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = adapter.apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                for name in adapter.BASELINE:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
        for project in ('src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj', 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'):
            result = subprocess.run([DOTNET, 'build', str(work / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
                                    capture_output=True, text=True, timeout=1800, env=environment, cwd=work)
            if result.returncode:
                print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
            check(result.returncode == 0, variant + ' production assembly builds: ' + project)

        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        program = (ROOT / 'test/melonx_released_texture_flush/Program.cs').read_text()
        for key, value in extract(work).items():
            program = program.replace('//__' + key + '__\n', value)
        (fixture / 'Program.cs').write_text(program)
        shutil.copyfile(work / AUTO, fixture / 'Auto.cs')
        shutil.copyfile(work / 'src/Ryujinx.Graphics.Vulkan/BitMapStruct.cs', fixture / 'BitMapStruct.cs')
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><TreatWarningsAsErrors>false</TreatWarningsAsErrors>'
            '<AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CS0169;CS0414;CS0649;CS8632;CS0436</NoWarn></PropertyGroup>'
            '<ItemGroup><ProjectReference Include="' + str(work / 'src/Ryujinx.Common/Ryujinx.Common.csproj') + '" /></ItemGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
check(c['live'] == k['live'] == {'outcome': 'copied', 'copies': [0x1A11]}, 'a live view copies with its handle in both')
for name in ('releasedFull', 'releasedSlice'):
    check(c[name]['outcome'] == 'copied' and c[name]['nullHandleCopies'] == 1, 'control records a null-handle copy (the crash): ' + name)
    check(k[name] == {'outcome': 'released', 'copies': [], 'nullHandleCopies': 0}, 'candidate records nothing: ' + name)
check(k['releasedDuring']['outcome'] == 'copied' and k['releasedDuring']['copies'] == [0x3C33] and
      not k['releasedDuring']['destroyedBeforeCompletion'] and k['releasedDuring']['destroyedAfterCompletion'],
      'candidate: a release during recording waits for the copy to complete')
for name in ('gpuFull', 'gpuSlice'):
    check(c[name]['released'] == 'threw', 'control: the exception reaches the flush caller: ' + name)
    check(k[name]['released'] == 'returned' and k[name]['output'] == '1,2,3,4' and k[name]['liveOutput'] == '7,7,7,7',
          'candidate: guest memory left unchanged, a live texture still written: ' + name)
check(k['gpuSlice']['lines'] == 1, 'one log line for the first released flush')

tk = texts['candidate']
view = member(tk[adapter.VIEW], 'public void CopyTo(BufferRange range, int layer, int level, int stride)')
check(view.index('if (image.Handle == 0)') < view.index('CopyFromOrToBuffer('), 'CopyTo skips a destroyed image before the copy')
check(texts['control'][adapter.VIEW].count('CmdCopyImageToBuffer') == tk[adapter.VIEW].count('CmdCopyImageToBuffer'), 'no copy added')

inputs = ['build-utils/melonx/adapt_released_texture_flush.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_released_texture_flush_test.py', 'test/melonx_released_texture_flush/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core689Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionAssembliesBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Real Auto.cs and extracted methods with doubles for MoltenVK and the command buffer pool; whether the '
                          'device crash is gone is known only after a device run.')
out = ROOT / 'dist/melonx/released-texture-flush-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
