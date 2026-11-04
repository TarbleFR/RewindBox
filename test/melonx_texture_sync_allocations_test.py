#!/usr/bin/env python3
"""Texture synchronization allocations: in-place BCn -> ETC2/EAC transcoding and the upload pool (adapt_texture_sync_allocations).

Usage: melonx_texture_sync_allocations_test.py <Core 649 prepared MeloNX tree (the lot's base tree)>
       melonx_texture_sync_allocations_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the preparation and builds the production Ryujinx.Library (with Ryujinx.Graphics.Gpu,
Ryujinx.Graphics.Texture and Ryujinx.Common) for the control and the candidate. Static checks bind that undoing the
adapter's replacements gives the preparation back byte for byte, that ConvertToHostCompatibleFormat no longer calls a
renting transcoder and hands the transcoded linear buffer on (disposed only if transcoding throws), that every other
Texture member is unchanged, that the transcoders' renting entry points keep their signatures and their two rents,
that the block loops no longer read the previous INPUT block, and that the pool keeps its 64 MiB / 3 s spare budget.

Behaviour and measurement (test/melonx_texture_sync_allocations/Program.cs, compiled with each variant's REAL
Ryujinx.Graphics.Gpu sources against that variant's real Texture, GAL, Common and Cpu assemblies, the guest memory
being the real software memory manager with its write tracking; doubles: the host renderer and its textures, which hash
each upload then dispose it as the Vulkan backend does): the real Texture.SynchronizeMemory of block-linear and linear
textures of 16 formats/sizes (mip chains, arrays, partial synchronization through mip/layer views), on a host with BC
and on one without (ETC2/EAC transcoding, as on iPhones whose Metal device lacks BC), uploads the same bytes in the
same order in both variants; a scene transition of 156 textures (cold pool, then warm) with 32 or 256 uploads held by
the host, and the same scene through the REAL ThreadedRenderer (GPU thread + render thread, ownership of each buffer
passing with the TextureSetData command), give identical upload hashes and fewer GPU-thread bytes; the in-place
transcoders equal the renting ones on odd sizes, mip chains, layers and runs; the real pool under a mixed rent/return
load never hands one array to two holders and stays within its spare budget. No device.
Writes dist/melonx/texture-sync-allocations-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control  # noqa: E402
from melonx_adapter_control import use_authenticated_libhac_feed  # noqa: E402
import adapt_texture_sync_allocations  # noqa: E402
from adapt_texture_sync_allocations import apply, BASELINE  # noqa: E402

NAME = 'adapt_texture_sync_allocations'
TEXTURE = 'src/Ryujinx.Graphics.Gpu/Image/Texture.cs'
ETC2 = 'src/Ryujinx.Graphics.Texture/ETC2Transcoder.cs'
OWNER = 'src/Ryujinx.Common/Memory/MemoryOwner.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


_HOLD = []
FINAL_SOURCE = SOURCE
if all(sha(SOURCE / name) == expected for name, expected in BASELINE.items()):
    FINAL_PREPARATION = False
elif NAME in melonx_adapter_control.ORDER:
    SOURCE, FINAL_PREPARATION = melonx_adapter_control.control_source(SOURCE, NAME, _HOLD)
else:
    # Not yet run by prepare_embedded.py: reverse exactly this adapter's replacements, then require the forward
    # application to reproduce the given tree.
    temporary = tempfile.TemporaryDirectory(prefix='melonx-texture-sync-control-')
    _HOLD.append(temporary)
    control_tree = Path(temporary.name) / 'control'
    shutil.copytree(SOURCE, control_tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    melonx_adapter_control._reverse(NAME, control_tree)
    forward = Path(temporary.name) / 'forward'
    for name in BASELINE:
        (forward / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(control_tree / name, forward / name)
    apply(forward)
    for name in BASELINE:
        check((forward / name).read_bytes() == (SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    SOURCE, FINAL_PREPARATION = control_tree, True

for name, expected in BASELINE.items():
    check(sha(SOURCE / name) == expected, 'not the pinned preparation: ' + name)

FIXTURE_PROJECT = '''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType>
    <TargetFramework>net10.0</TargetFramework>
    <LangVersion>preview</LangVersion>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks>
    <Nullable>disable</Nullable>
    <NuGetAudit>false</NuGetAudit>
    <EnableDefaultCompileItems>false</EnableDefaultCompileItems>
    <ServerGarbageCollection>false</ServerGarbageCollection>
    <ConcurrentGarbageCollection>false</ConcurrentGarbageCollection>
    <NoWarn>$(NoWarn);CS1591;CS0618;CS8632;CS0067;CS0414;CS0649;CS0162</NoWarn>
    <TreeSrc>$(MSBuildThisFileDirectory)../src</TreeSrc>
    DEFINES
  </PropertyGroup>
  <ItemGroup>
    <Compile Include="Program.cs" />
    <!-- The variant's REAL Ryujinx.Graphics.Gpu sources, compiled into the fixture for access to its internal types. -->
    <Compile Include="$(TreeSrc)/Ryujinx.Graphics.Gpu/**/*.cs" Exclude="$(TreeSrc)/Ryujinx.Graphics.Gpu/bin/**;$(TreeSrc)/Ryujinx.Graphics.Gpu/obj/**" />
    <ProjectReference Include="$(TreeSrc)/Ryujinx.Cpu/Ryujinx.Cpu.csproj" />
    <ProjectReference Include="$(TreeSrc)/Ryujinx.Graphics.Device/Ryujinx.Graphics.Device.csproj" />
    <ProjectReference Include="$(TreeSrc)/Ryujinx.Graphics.GAL/Ryujinx.Graphics.GAL.csproj" />
    <ProjectReference Include="$(TreeSrc)/Ryujinx.Common/Ryujinx.Common.csproj" />
    <ProjectReference Include="$(TreeSrc)/Ryujinx.Graphics.Texture/Ryujinx.Graphics.Texture.csproj" />
    <ProjectReference Include="$(TreeSrc)/Ryujinx.Graphics.Shader/Ryujinx.Graphics.Shader.csproj" />
  </ItemGroup>
</Project>
'''

RUNS = [('transcoders',), ('pool',), ('cases', 'nobc'), ('cases', 'bc'), ('scene', 'nobc', '32'), ('scene', 'bc', '32'),
        ('scene', 'nobc', '256'), ('scene', 'bc', '256'), ('threaded', 'nobc'), ('threaded', 'bc')]

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
texts, reports = {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-texture-sync-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work, ROOT)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                for name in BASELINE:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo',
                                 '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.Library builds')
        print(variant + ': production Ryujinx.Library built', flush=True)

        fixture = work / 'TextureSyncFixture'
        fixture.mkdir()
        shutil.copyfile(ROOT / 'test/melonx_texture_sync_allocations/Program.cs', fixture / 'Program.cs')
        (fixture / 'Fixture.csproj').write_text(FIXTURE_PROJECT.replace(
            'DEFINES', '<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if variant == 'candidate' else ''))
        result = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                                capture_output=True, text=True, timeout=1800, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ' fixture with the real Gpu sources builds')
        reports[variant] = {}
        for run in RUNS:
            result = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), *run], capture_output=True, text=True,
                                    timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
            reports[variant][' '.join(run)] = json.loads(result.stdout.strip().splitlines()[-1])
            print(variant + ' ' + ' '.join(run) + ': ' + json.dumps(reports[variant][' '.join(run)])[:600], flush=True)

    control, candidate = texts['control'], texts['candidate']

    # Undoing exactly the adapter's replacements gives the preparation back: nothing else changed.
    reverse = Path(temporary).resolve() / 'reverse'
    for name in BASELINE:
        (reverse / name).parent.mkdir(parents=True, exist_ok=True)
        (reverse / name).write_text(candidate[name], encoding='utf-8')
    melonx_adapter_control._reverse(NAME, reverse)
    for name in BASELINE:
        check(sha(reverse / name) == BASELINE[name], 'only the adapter replacements differ: ' + name)

# Texture: the transcoded linear buffer is handed on; nothing else in Texture changes.
texture_c, texture_k = control[TEXTURE], candidate[TEXTURE]
convert_c = member(texture_c, 'public MemoryOwner<byte> ConvertToHostCompatibleFormat(')
convert_k = member(texture_k, 'public MemoryOwner<byte> ConvertToHostCompatibleFormat(')
check(len(re.findall(r'ETC2Transcoder\.Transcode\w+\(', convert_c)) == 6 and
      not re.search(r'ETC2Transcoder\.Transcode\w+\(', convert_k), 'no renting transcoder left in ConvertToHostCompatibleFormat')
check(convert_k.count('return TranscodedInPlace(result, width, height, sliceDepth, levels, layers);') == 6, 'six in-place hand-overs')
for decoder in ('BCnDecoder.DecodeBC1', 'BCnDecoder.DecodeBC2', 'BCnDecoder.DecodeBC3', 'BCnDecoder.DecodeBC4', 'BCnDecoder.DecodeBC5',
                'BCnDecoder.DecodeBC6', 'BCnDecoder.DecodeBC7', 'AstcDecoder.TryDecodeToRgba8P', 'ETC2Decoder.DecodeRgba',
                'PixelConverter.ConvertR16G16B16A16FloatToR11G11B10Float', 'Recompress('):
    check(convert_k.count(decoder) == convert_c.count(decoder), 'decode/recompress branches kept: ' + decoder)
check(convert_k.count('using (result)') == convert_c.count('using (result)'), 'each decode branch still disposes the linear buffer')
helper = member(texture_k, 'private MemoryOwner<byte> TranscodedInPlace(')
check(helper.count('return linear;') == 1 and helper.count('linear.Dispose();') == 1 and
      helper.index('catch') < helper.index('linear.Dispose();') and 'Rent(' not in helper, 'handed on; disposed only when transcoding throws')
check(sorted(re.findall(r'ETC2Transcoder\.(\w+)\(', helper)) == sorted(
    ['TranscodeBC1ToEtc2PtaInPlace', 'TranscodeBC2ToEtc2RgbaInPlace', 'TranscodeBC3ToEtc2RgbaInPlace', 'TranscodeBC4ToEacR11InPlace',
     'TranscodeBC5ToEacRG11InPlace', 'TranscodeBC7ToEtc2RgbaInPlace']), 'one in-place transcoder per BC format')
for signature in ('public void SynchronizeMemory()', 'public void SynchronizeFull()', 'public void SetData(MemoryOwner<byte> data)',
                  'public void SetData(MemoryOwner<byte> data, int layer, int level)', 'private MemoryOwner<byte> Recompress(',
                  'public ReadOnlySpan<byte> ConvertFromHostCompatibleFormat('):
    check(member(texture_k, signature) == member(texture_c, signature), 'Texture unchanged: ' + signature)

# ETC2Transcoder: renting entry points kept; the block loops no longer read the previous input block.
etc2_c, etc2_k = control[ETC2], candidate[ETC2]
renting = r'public static MemoryOwner<byte> (Transcode\w+)\(([^)]*)\)'
check(re.findall(renting, etc2_k) == re.findall(renting, etc2_c) and len(re.findall(renting, etc2_c)) == 6, 'renting entry points kept')
check(etc2_c.count('input[i - 1]') == 2 and etc2_k.count('input[i - 1]') == 0 and etc2_k.count('previous = block;') == 2 and
      etc2_k.count('block == previous') == 2, 'BC1/BC4 loops keep the previous input block in a local')
check(etc2_k.count('MemoryOwner<byte>.Rent(') == etc2_c.count('MemoryOwner<byte>.Rent(') == 2, 'no new rent')
for in_place in re.findall(r'public static void (Transcode\w+InPlace)\(', etc2_k):
    body = member(etc2_k, 'public static void ' + in_place + '(')
    check('Rent(' not in body and re.search(r'Transcode(Rgba)?Into\(data, data,', body), in_place + ' writes over its input')
check(len(re.findall(r'public static void (Transcode\w+InPlace)\(', etc2_k)) == 6, 'six in-place entry points')
rgba_into = member(etc2_k, 'private static void TranscodeRgbaInto(')
check(rgba_into.count('Parallel.For(') == 1 and 'checked(blocksPerSlice * depth * layers)' in rgba_into, 'one parallel loop per call')
check(etc2_c.count('Parallel.For(') == 2 and etc2_k.count('Parallel.For(') == 2, 'parallel loops: TranscodeInto and TranscodeRgbaInto')
for signature in ('private static void TranscodeRgbaBlocks(', 'private static uint ConvertRgb565ToRgb888(', 'private static uint Lerp3('):
    check(member(etc2_k, signature) == member(etc2_c, signature), 'ETC2Transcoder unchanged: ' + signature)

# MemoryOwner: spares from 4,096 bytes and the best fit; the budget, release, return and dispose paths unchanged.
owner_c, owner_k = control[OWNER], candidate[OWNER]
check('private const long MinSpareBytes = 85000;' in owner_c and 'private const long MinSpareBytes = 4096;' in owner_k, 'spare floor')
for constant in ('private const long MaxSpareBytes = 64L * 1024 * 1024;', 'private const int SpareIdleMilliseconds = 3000;',
                 'private const int MaxSkipCount = 50;'):
    check(constant in owner_c and constant in owner_k, 'unchanged: ' + constant)
for signature in ('public static Holder Get(int minimumSize)', 'public static void Return(Holder holder)', 'private static void KeepSpareLocked(',
                  'private static void ReleaseIdleArrays(', 'private static void ReleaseIdleSpares(', 'public void Dispose()'):
    check(member(owner_k, signature) == member(owner_c, signature), 'MemoryOwner unchanged: ' + signature)
search = member(owner_k, 'private static int BinarySearch(List<Holder> list, int size)')
check('list[mid].SkipCount++;' in search and 'list[min].CompareTo(size) == 0 ? min : ~min' in search, 'smallest fitting array, skips counted')

# Behaviour: identical uploads; fewer bytes.
rc, rk = reports['control'], reports['candidate']
transcoders_c, transcoders_k = rc['transcoders'], rk['transcoders']
check(len(transcoders_k) == 48 and [t['digest'] for t in transcoders_k] == [t['digest'] for t in transcoders_c],
      'renting transcoders: same output in both variants')
check(all(t['inPlaceEqual'] is True for t in transcoders_k) and all(t['inPlaceEqual'] is None for t in transcoders_c),
      'in-place transcoders equal the renting ones (odd sizes, mips, layers, 3D, runs)')
for run in RUNS[2:]:
    key = ' '.join(run)
    check(rk[key]['digest'] == rc[key]['digest'] and rk[key]['uploads'] == rc[key]['uploads'], 'same uploads, same order: ' + key)
check(rc['cases nobc']['partialUploads'] == 6 and rk['cases nobc']['partialUploads'] == 6, 'partial synchronization exercised')
check(rc['cases nobc']['digest'] != rc['cases bc']['digest'], 'the two hosts take different conversion paths')
for capability in ('nobc', 'bc'):
    key = 'threaded ' + capability
    check(rk[key]['uploads'] == rk[key]['calls'] == 156 and rc[key]['uploads'] == 156,
          'threaded renderer: every upload reached the host after the GPU thread moved on: ' + capability)
check(rk['threaded nobc']['bytesPerSync'] < rc['threaded nobc']['bytesPerSync'], 'threaded, no BC: fewer GPU-thread bytes')
check(rk['pool']['errors'] == 0 and rc['pool']['errors'] == 0, 'the pool never hands one array to two holders')
check(0 < rk['pool']['maxSpareBytes'] <= 64 * 1024 * 1024, 'spares within the 64 MiB budget')
check(rk['pool']['warmPhaseBytes'] < rc['pool']['warmPhaseBytes'], 'pool: fewer bytes allocated under a mixed load')
measurements = {}
for run in RUNS[4:8]:
    key = ' '.join(run)
    control_rounds = [r['gpuThreadBytes'] for r in rc[key]['rounds']]
    candidate_rounds = [r['gpuThreadBytes'] for r in rk[key]['rounds']]
    measurements[key] = dict(controlBytes=control_rounds, candidateBytes=candidate_rounds,
                             controlBytesPerSync=[r['bytesPerSync'] for r in rc[key]['rounds']],
                             candidateBytesPerSync=[r['bytesPerSync'] for r in rk[key]['rounds']])
    check(sum(candidate_rounds) < sum(control_rounds), 'scene: fewer GPU-thread bytes: ' + key)
    check(candidate_rounds[1] < control_rounds[1], 'warm scene: fewer GPU-thread bytes: ' + key)
    if run[2] == '256':
        check(candidate_rounds[1] * 4 < control_rounds[1], 'warm scene, 256 uploads in flight: under a quarter of the bytes: ' + key)
check(rk['scene nobc 32']['rounds'][0]['gpuThreadBytes'] < rc['scene nobc 32']['rounds'][0]['gpuThreadBytes'],
      'cold scene without BC: fewer bytes (one buffer per transcoded upload)')
measurements['threaded nobc'] = dict(controlBytesPerSync=rc['threaded nobc']['bytesPerSync'], candidateBytesPerSync=rk['threaded nobc']['bytesPerSync'])
measurements['threaded bc'] = dict(controlBytesPerSync=rc['threaded bc']['bytesPerSync'], candidateBytesPerSync=rk['threaded bc']['bytesPerSync'])
measurements['pool'] = dict(controlWarmBytes=rc['pool']['warmPhaseBytes'], candidateWarmBytes=rk['pool']['warmPhaseBytes'],
                            candidateMaxSpareBytes=rk['pool']['maxSpareBytes'])
measurements['cases steady bytesPerSync'] = {
    capability: {c['name']: [c['bytesPerSync'], k['bytesPerSync']]
                 for c, k in zip(rc['cases ' + capability]['perCase'], rk['cases ' + capability]['perCase'])}
    for capability in ('nobc', 'bc')}

inputs = ['build-utils/melonx/adapt_texture_sync_allocations.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_texture_sync_allocations_test.py', 'test/melonx_texture_sync_allocations/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core649Preparation',
               postimages={p: sha(FINAL_SOURCE / p) for p in BASELINE} if FINAL_PREPARATION else {},
               measurements=measurements, reports=reports, sdk=sdk, physicalDeviceTested=False, productionLibraryBuilt=True,
               sourceBaseline=BASELINE, inputs={p: sha(ROOT / p) for p in inputs},
               limitation='GPU-thread bytes of the real synchronization code on a host (x86-64 .NET, not NativeAOT on iOS) with a '
                          'host-renderer double; the scene is a model (156 textures, 12 MB of guest data), not Hogwarts Legacy\'s, '
                          'and how far the render thread lags on the device is not known (32 and 256 uploads in flight are '
                          'measured). The cold allocation of a scene\'s first uploads remains. GC pause effect on the device '
                          'is known only from the core-performance windows of a device run.')
out = ROOT / 'dist/melonx/texture-sync-allocations-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, measurements={k: v for k, v in measurements.items() if k.startswith('scene') or k.startswith('threaded')})))
