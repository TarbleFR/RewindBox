#!/usr/bin/env python3
"""adapt_nan_scrub on the final preparation, against the Core 670 preparation as control.

Hogwarts Legacy's colour and image writes are made finite in the translated SPIR-V (NaN -> 0, +/-Inf -> +/-65504),
title-gated by SpirvNanScrub.Enabled (set by the native launch title note), with fast math kept; the host shader cache
version differs while it is enabled, so a cache made without the scrub is translated again once.

Control: the final preparation with adapt_nan_scrub reversed (melonx_adapter_control), which must be the Core 670 bytes.
Candidate: the final preparation. Both build the production Ryujinx.Graphics.Vulkan and Ryujinx.Graphics.Gpu with one
probe (test/melonx_nan_scrub/Program.cs) that reads the real cache code-generation version and, for the candidate,
emits the real scrub into a SPIR-V function and evaluates the emitted words on edge inputs, then runs the delivered
native title note. No device, no GPU, no MoltenVK. Writes dist/melonx/nan-scrub-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, struct, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
from melonx_adapter_control import use_authenticated_libhac_feed  # noqa: E402
import core667_native  # noqa: E402
import adapt_nan_scrub  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
GENERATOR = 'src/Ryujinx.Graphics.Shader/CodeGen/Spirv/SpirvGenerator.cs'
INSTRUCTIONS = 'src/Ryujinx.Graphics.Shader/CodeGen/Spirv/Instructions.cs'
STORAGE = 'src/Ryujinx.Graphics.Gpu/Shader/DiskCache/DiskCacheHostStorage.cs'
RUNTIME, PREFLIGHT = core667_native.RUNTIME, core667_native.PREFLIGHT
HARNESS = ROOT / 'test/melonx_nan_scrub'
POSTIMAGES = [GENERATOR, INSTRUCTIONS, STORAGE, RUNTIME]
HOGWARTS = 0x0100F7E00C70E000
CORE670_VERSION = 7353 + 0x5242_0002  # adapt_bindless, adapt_bindless_sources
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def ignore_tree(base):
    def ignore(directory, names):
        skipped = {'.git', 'bin', 'obj'} & set(names)
        if Path(directory).resolve() == (Path(base) / 'src').resolve() and 'MeloNX' in names:
            skipped.add('MeloNX')
        return skipped
    return ignore


def expected_scrub(bits):
    if bits & 0x7F800000 != 0x7F800000:
        return bits
    if bits & 0x007FFFFF:
        return 0
    return (bits & 0x80000000) | 0x477FE000


temporary = tempfile.TemporaryDirectory(prefix='melonx-nan-scrub-')
WORK = Path(temporary.name).resolve()  # resolved: on macOS /var is a link to /private/var
CONTROL = WORK / 'control'
shutil.copytree(FINAL_SOURCE, CONTROL, ignore=ignore_tree(FINAL_SOURCE), symlinks=True)

# --- Control: the adapter reversed must be the Core 670 bytes; forward reproduces the final preparation ---
control_tools._reverse('adapt_nan_scrub', CONTROL)
for name, expected in adapt_nan_scrub.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 670 preparation: ' + name)
forward = WORK / 'forward'
for name in adapt_nan_scrub.BASELINE:
    (forward / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CONTROL / name, forward / name)
changed = sorted(str(p.relative_to(forward)) for p in adapt_nan_scrub.apply(forward))
check(changed == sorted(adapt_nan_scrub.BASELINE), 'adapt_nan_scrub changes only its files')
for name in adapt_nan_scrub.BASELINE:
    check((forward / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)

# --- Static: the exact scope ---
instructions, control_instructions = read(FINAL_SOURCE, INSTRUCTIONS), read(CONTROL, INSTRUCTIONS)
store = member(instructions, 'private static OperationResult GenerateLoadOrStore(')
check(store.count('SpirvNanScrub.Scrub(context, value)') == 1 and 'IoVariable.FragmentOutputColor' in store and
      'varType == AggregateType.FP32' in store and 'StorageKind.Output' in store and 'SpirvNanScrub.Enabled' in store,
      'only FP32 colour output stores are scrubbed, and only while enabled')
image = member(instructions, 'private static OperationResult GenerateImageStore(')
check(image.count('SpirvNanScrub.Scrub(context, cElems[i])') == 1 and 'componentType == AggregateType.FP32' in image and
      image.index('SpirvNanScrub.Scrub') < image.index('context.ImageWrite('), 'FP32 image stores are scrubbed before the write')
check(instructions.count('SpirvNanScrub') == 4 and 'SpirvNanScrub' not in control_instructions,
      'no other translator path changes')
check(instructions.replace(adapt_nan_scrub.STORE_NEW, adapt_nan_scrub.STORE_OLD).replace(adapt_nan_scrub.IMAGE_NEW, adapt_nan_scrub.IMAGE_OLD)
      == control_instructions, 'Instructions.cs differs from Core 670 only by the two stores')
scrub = member(read(FINAL_SOURCE, GENERATOR), 'public static SpvInstruction Scrub(')
for word in ('IEqual', 'INotEqual', 'BitwiseAnd', 'BitwiseOr', 'Bitcast', 'LogicalAnd', 'Select'):
    check('module.' + word + '(' in scrub, 'scrub built from integer and select operations: ' + word)
for word in ('IsNan', 'IsInf', 'FOrd', 'FUnord', 'FMul', 'FAdd'):
    check(word not in scrub, 'no float operation that fast math could assume away: ' + word)
storage = read(FINAL_SOURCE, STORAGE)
check('private const uint CodeGenVersion' not in storage and storage.count('CodeGenVersion =>') == 1 and
      storage.count('header.CodeGenVersion == CodeGenVersion') == 1, 'the cache version follows the scrub')
runtime = read(FINAL_SOURCE, RUNTIME)
note = member(runtime, 'private static void EmbeddedNoteLaunchTitle(')
check('SpirvNanScrub.Enabled = titleId == 0x0100F7E00C70E000UL;' in note, 'the launch title enables the scrub for Hogwarts Legacy only')
check(runtime == (ROOT / core667_native.NATIVE[RUNTIME]).read_text(encoding='utf-8'), 'final preparation holds this checkout\'s runtime')
preflight = read(FINAL_SOURCE, PREFLIGHT)
check(preflight.count('EmbeddedNoteLaunchTitle(0);') == 1 and preflight.count('EmbeddedNoteLaunchTitle(entry.Key);') == 1,
      'the preflight resets the title choice and notes the opened title before the session starts')

# --- Executed: control and candidate probes ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
reports, feeds = {}, {}
for variant in ('control', 'candidate'):
    tree = WORK / ('tree-' + variant)
    origin = CONTROL if variant == 'control' else FINAL_SOURCE
    shutil.copytree(origin, tree, ignore=ignore_tree(origin), symlinks=True)
    feeds[variant] = use_authenticated_libhac_feed(tree, ROOT)
    out = WORK / ('probe-' + variant)
    out.mkdir()
    program = (HARNESS / 'Program.cs').read_text()
    if variant == 'candidate':
        start = runtime.index('    // Titles whose shaders Metal compiles without fast math')
        end = runtime.index('    [UnmanagedCallersOnly(EntryPoint = "neostation_melonx_prepare_jit")]')
        delivered = runtime[start:end]
        check('EmbeddedNoteLaunchTitle' in delivered and 'EmbeddedPreciseMathTitles' in delivered, 'the probe compiles the delivered note')
        program = program.replace('//__CORE671_RUNTIME__\n', delivered)
    (out / 'Program.cs').write_text(program)
    (out / 'MeloNXNanScrubProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632;CS0162</NoWarn><NuGetAudit>false</NuGetAudit>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
    {'<DefineConstants>$(DefineConstants);CANDIDATE</DefineConstants>' if variant == 'candidate' else ''}
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{tree}/src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj" />
    <ProjectReference Include="{tree}/src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj" />
  </ItemGroup>
</Project>
''')
    for name in ('global.json', 'nuget.config'):
        if (tree / name).exists():
            shutil.copyfile(tree / name, out / name)
    build = subprocess.run([DOTNET, 'build', str(out / 'MeloNXNanScrubProbe.csproj'), '-c', 'Release', '-nologo', '-m:1',
                            '-p:NuGetAudit=false', '-p:RestoreIgnoreFailedSources=true'],
                           capture_output=True, text=True, timeout=3000, env=environment, cwd=out)
    if build.returncode:
        errors = [line for line in build.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), build.stdout[-4000:], build.stderr[-2000:], sep='\n', flush=True)
    check(build.returncode == 0, variant + ' probe builds against the production Vulkan and GPU projects')
    run = subprocess.run([DOTNET, str(out / 'bin/Release/net10.0/MeloNXNanScrubProbe.dll')],
                         capture_output=True, text=True, timeout=600, env=environment, cwd=out)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' probe runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
    print(variant + ': probe ran', flush=True)

control, candidate = reports['control'], reports['candidate']
check(control['codeGenVersion'] == CORE670_VERSION and control['scrubType'] is False, 'control (Core 670): its cache version, no scrub')
check(candidate['codeGenVersionOff'] == CORE670_VERSION, 'scrub off: the same cache version as Core 670 (every other title keeps its cache)')
check(candidate['codeGenVersionOn'] == CORE670_VERSION + 0x0001_0000, 'scrub on: another cache version, so Hogwarts\' translations are made again once')
results = candidate['scrub']
check(len(results) == 15, 'fifteen edge inputs evaluated')
for text, got in results.items():
    bits = int(text, 16)
    check(int(got, 16) == expected_scrub(bits), f'scrub of {text}: {got}')
finite = [k for k in results if int(k, 16) & 0x7F800000 != 0x7F800000]
check(len(finite) == 9 and all(results[k] == k for k in finite), 'finite values (zeros, normals, max, denormal) pass unchanged')
check(results['7FC00000'] == results['FFFFFFFF'] == results['7F800001'] == '00000000', 'quiet, signalling and negative NaN become 0')
check(results['7F800000'] == '477FE000' and results['FF800000'] == 'C77FE000' and
      struct.unpack('<f', struct.pack('<I', 0x477FE000))[0] == 65504.0, '+/-Inf become +/-65504')
check(set(candidate['opcodes']) == {'Bitcast', 'BitwiseAnd', 'BitwiseOr', 'IEqual', 'INotEqual', 'LogicalAnd', 'Select'},
      'the emitted function uses only integer, logical and select opcodes')
check(candidate['notedNanScrub'] == {'hogwarts': True, 'smash': False, 'reset': False}, 'the title note enables the scrub for Hogwarts only')

inputs = ['build-utils/melonx/adapt_nan_scrub.py', 'build-utils/melonx/core667_native.py', 'build-utils/melonx/adapt_session.py',
          'native/melonx/EmbeddedRuntime.cs', 'native/melonx/EmbeddedLaunchPreflight.cs', 'test/melonx_nan_scrub_test.py',
          'test/melonx_nan_scrub/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               postimages={p: sha(FINAL_SOURCE / p) for p in POSTIMAGES}, reports=reports, sdk=sdk, host=platform.system(),
               libHacFeedSwitched=feeds, physicalDeviceTested=False, gameTested=False,
               productionAssembliesBuilt=['Ryujinx.Graphics.Vulkan', 'Ryujinx.Graphics.Gpu'],
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Host probe: the emitted scrub evaluated by an interpreter of its own opcodes, the cache version and '
                          'the title note. Whether the black sky blocks go, how Metal compiles the scrub under fast math on '
                          'the iPhone, and the one-time translation cost are known only from a device run.')
out = ROOT / 'dist/melonx/nan-scrub-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
