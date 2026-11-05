#!/usr/bin/env python3
"""Core 667 fixes on the final preparation, against the Core 663 preparation as control.

- adapt_buffer_array_barriers: buffer TextureArray/ImageArray arrays queue no image barrier (IPA 666: the render worker's
  NullReferenceException in TextureArray.QueueWriteToReadBarriers ended a Hogwarts session).
- adapt_hogwarts_precise_math: MVKInitialization.Initialize() writes FastMathEnabled = !PreciseMath (MeloNX: always true).
- adapt_shader_save_journal: counters of the shader disk-cache saves, journaled at each 64th write and at disposal.
- core667_native (native/melonx EmbeddedRuntime.cs, EmbeddedLaunchPreflight.cs): the JIT code arena chosen at the first
  launch of a process, a larger need refused before the launch; the launch title selects the math mode.

Control: the final preparation with these three adapters reversed (melonx_adapter_control) and the two native files
reversed (core667_native), which must be the Core 663 bytes. Candidate: the final preparation. Both build the production
Ryujinx.Graphics.Vulkan and Ryujinx.Graphics.Gpu with one probe (test/melonx_core667_fixes/Program.cs) that runs the
real array barrier calls, the real MVKInitialization.Initialize() against a test double of MoltenVK's configuration
entry points (StubMoltenVK.c), the real ShaderCache save loop and disposal, and (candidate) the native Core 667 members
as delivered. No device, no GPU, no MoltenVK. Writes dist/melonx/core667-fixes-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
from melonx_adapter_control import use_authenticated_libhac_feed  # noqa: E402
import core667_native  # noqa: E402
import adapt_buffer_array_barriers, adapt_hogwarts_precise_math, adapt_shader_save_journal  # noqa: E402,E401

DOTNET = os.environ.get('DOTNET', 'dotnet')
ADAPTERS = [adapt_buffer_array_barriers, adapt_hogwarts_precise_math, adapt_shader_save_journal]
NAMES = ['adapt_buffer_array_barriers', 'adapt_hogwarts_precise_math', 'adapt_shader_save_journal']
TEXTURE_ARRAY, IMAGE_ARRAY = 'src/Ryujinx.Graphics.Vulkan/TextureArray.cs', 'src/Ryujinx.Graphics.Vulkan/ImageArray.cs'
MVK, SHADER_CACHE = 'src/Ryujinx.Graphics.Vulkan/MoltenVK/MVKInitialization.cs', 'src/Ryujinx.Graphics.Gpu/Shader/ShaderCache.cs'
RUNTIME, PREFLIGHT = core667_native.RUNTIME, core667_native.PREFLIGHT
# The Core 663 preparation of the native files (pin 89e1c361, source 9022c1a1).
CORE663_NATIVE = {RUNTIME: 'a6609a8557be5145f6f8b988d14761e4e7f3031e38da4ee450f0b1ced252d699'}
HARNESS = ROOT / 'test/melonx_core667_fixes'
POSTIMAGES = [TEXTURE_ARRAY, IMAGE_ARRAY, MVK, SHADER_CACHE, RUNTIME, PREFLIGHT]
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
    # As the other Core gates copy a MeloNX tree: no build outputs, and not the iOS app sources (src/MeloNX).
    def ignore(directory, names):
        skipped = {'.git', 'bin', 'obj'} & set(names)
        if Path(directory).resolve() == (Path(base) / 'src').resolve() and 'MeloNX' in names:
            skipped.add('MeloNX')
        return skipped
    return ignore


def git_show(path):
    return subprocess.run(['git', '-C', str(ROOT), 'show', core667_native.CORE663_SOURCE + ':' + path],
                          capture_output=True, text=True, check=True).stdout


holder = []
temporary = tempfile.TemporaryDirectory(prefix='melonx-core667-')
holder.append(temporary)
# Resolved, as every gate: on macOS /var is a link to /private/var, and MSBuild must see each project under one path.
WORK = Path(temporary.name).resolve()
CONTROL = WORK / 'control'
shutil.copytree(FINAL_SOURCE, CONTROL, ignore=ignore_tree(FINAL_SOURCE), symlinks=True)

# --- Control: the adapters reversed (latest first), the native files reversed; both must be the Core 663 bytes ---
for name in reversed(NAMES):
    control_tools._reverse(name, CONTROL)
for module in ADAPTERS:
    for name, expected in module.BASELINE.items():
        check(sha(CONTROL / name) == expected, 'control is the Core 663 preparation: ' + name)
for name, native in core667_native.NATIVE.items():
    final_text = read(FINAL_SOURCE, name)
    check(final_text == (ROOT / native).read_text(encoding='utf-8'), 'final preparation holds this checkout\'s ' + native)
    restored = core667_native.reverse(final_text, name)
    check(restored == git_show(native), 'reversed ' + native + ' is the Core 663 source (9022c1a1)')
    check(core667_native.apply(restored, name) == final_text, 'the Core 667 edits applied to Core 663 give ' + native)
    (CONTROL / name).write_text(restored, encoding='utf-8')
for name, expected in CORE663_NATIVE.items():
    check(sha(CONTROL / name) == expected, 'control native file is the Core 663 preparation: ' + name)

# --- Forward: each adapter applied to the control reproduces the final preparation byte for byte ---
forward = WORK / 'forward'
for module in ADAPTERS:
    for name in module.BASELINE:
        (forward / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CONTROL / name, forward / name)
for module in ADAPTERS:
    changed = sorted(str(p.relative_to(forward)) for p in module.apply(forward))
    check(changed == sorted(module.BASELINE), module.__name__ + ' changes only its files')
for module in ADAPTERS:
    for name in module.BASELINE:
        check((forward / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapters: ' + name)

# --- Static: the exact scope of each change ---
for name, signature, guard in ((TEXTURE_ARRAY, 'public void QueueWriteToReadBarriers(', adapt_buffer_array_barriers.TEXTURE_NEW),
                               (IMAGE_ARRAY, 'public void QueueWriteToReadBarriers(', adapt_buffer_array_barriers.IMAGE_NEW)):
    final_method, control_method = member(read(FINAL_SOURCE, name), signature), member(read(CONTROL, name), signature)
    first = final_method.split('{', 1)[1].lstrip()
    check(first.startswith('// RewindBox (adapt_buffer_array_barriers)') and 'if (_isBuffer)\n            {\n                return;\n            }'
          in final_method.split('HashSet<TextureStorage> storages = _storages;')[0], name + ': the buffer guard is the first statement')
    check(final_method.replace(guard, adapt_buffer_array_barriers.TEXTURE_OLD if name == TEXTURE_ARRAY else adapt_buffer_array_barriers.IMAGE_OLD)
          == control_method, name + ': the rest of QueueWriteToReadBarriers is the Core 663 method')
    check('_isBuffer = isBuffer;' in read(FINAL_SOURCE, name) and read(FINAL_SOURCE, name).count('_isBuffer =') == 1,
          name + ': _isBuffer is set once, by the constructor')
initialize = member(read(FINAL_SOURCE, MVK), 'public static void Initialize()')
check(initialize.count('config.FastMathEnabled = !PreciseMath;') == 1 and 'config.FastMathEnabled = true;' not in initialize and
      initialize.index('config.FastMathEnabled = !PreciseMath;') < initialize.index('vkSetMoltenVKConfigurationMVK('),
      'Initialize writes FastMathEnabled = !PreciseMath before setting the configuration')
check(member(read(CONTROL, MVK), 'public static void Initialize()').replace(adapt_hogwarts_precise_math.MATH_OLD, adapt_hogwarts_precise_math.MATH_NEW)
      == initialize, 'Initialize is the Core 663 method but the math mode and its journal line')
vulkan = read(FINAL_SOURCE, 'src/Ryujinx.Graphics.Vulkan/VulkanRenderer.cs')
check('MVKInitialization.Initialize();' in member(vulkan, 'public VulkanRenderer(Vk api,') and vulkan.count('MVKInitialization.Initialize()') == 1,
      'every VulkanRenderer applies the configuration in its constructor, once')
runtime = read(FINAL_SOURCE, RUNTIME)
prepare = member(runtime, 'public static int EmbeddedPrepareJit()')
check(prepare.index('EmbeddedJitArenaRequest(EmbeddedJitArenaHint, mappedArena') < prepare.index('PrepareEmbeddedMapping()') and
      'RequestedArenaSize = arenaRequest;' in prepare and 'RequestedArenaSize = EmbeddedJitArenaHint' not in prepare,
      'the arena is decided before the mapping and the mapping asks for the decision')
refusal = prepare[prepare.index('if (!EmbeddedJitArenaRequest('):prepare.index('try\n')]
check('EmbeddedJitQuarantined' not in refusal and '"jitRestartRequired"' in refusal and 'return 1;' in refusal,
      'a refused arena fails the launch with the restart status and does not quarantine the JIT')
preflight = read(FINAL_SOURCE, PREFLIGHT)
check(preflight.index('EmbeddedNoteLaunchTitle(0);') < preflight.index('EmbeddedLaunchDiagnostics.Record("file", "begin");') and
      preflight.index('EmbeddedJitArenaHint = EmbeddedJitArenaFor(entry.Key, program);') <
      preflight.index('EmbeddedNoteLaunchTitle(entry.Key);') < preflight.index('programFound = true;'),
      'the preflight resets the title choice before any check and notes the title it opens')
note = member(runtime, 'private static void EmbeddedNoteLaunchTitle(')
check('PreciseMath = titleId == 0x0100F7E00C70E000UL;' in note, 'precise math for Hogwarts Legacy only')
save = member(read(FINAL_SOURCE, SHADER_CACHE), 'public void ProcessShaderCacheQueue()')
check(save.count('_cacheWriter.AddShader(') == 1 and save.count('_programsToSaveQueue.Dequeue();') == 1 and save.count('break;') == 1,
      'the save loop still writes, dequeues and stops at an incomplete head as before')

# --- Executed: control and candidate probes ---
stub = WORK / ('libstubmvk.dylib' if platform.system() == 'Darwin' else 'libstubmvk.so')
subprocess.run(['cc', '-shared', '-fPIC', '-O2', '-o', str(stub), str(HARNESS / 'StubMoltenVK.c')], check=True, timeout=300)
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
reports, feeds = {}, {}
for variant in ('control', 'candidate'):
    tree = WORK / ('tree-' + variant)
    origin = CONTROL if variant == 'control' else FINAL_SOURCE
    shutil.copytree(origin, tree, ignore=ignore_tree(origin), symlinks=True)
    # The upstream nuget.config still names the LibHac feed (unreachable): the authenticated local package, as every gate.
    feeds[variant] = use_authenticated_libhac_feed(tree, ROOT)
    for project in ('src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj', 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'):
        text = (tree / project).read_text(encoding='utf-8-sig')
        check(text.count('</Project>') == 1, 'project ' + project)
        # Test-only access to the internal production types; the production build is made without it.
        (tree / project).write_text(text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXCore667Probe" /></ItemGroup>\n</Project>'))
    out = WORK / ('probe-' + variant)
    out.mkdir()
    program = (HARNESS / 'Program.cs').read_text()
    if variant == 'candidate':
        delivered = core667_native.ARENA_BLOCK + core667_native.NOTE_BLOCK
        check(delivered in runtime, 'the probe compiles the delivered native members')
        program = program.replace('//__CORE667_RUNTIME__\n', delivered)
    (out / 'Program.cs').write_text(program)
    (out / 'MeloNXCore667Probe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
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
    # A configured package source that is down (starforgejo.dev answered 403 on 2026-11-05) must not fail the restore of
    # packages the local cache or the authenticated feed already holds.
    build = subprocess.run([DOTNET, 'build', str(out / 'MeloNXCore667Probe.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false',
                            '-p:RestoreIgnoreFailedSources=true'],
                           capture_output=True, text=True, timeout=3000, env=environment, cwd=out)
    if build.returncode:
        errors = [line for line in build.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), build.stdout[-4000:], build.stderr[-2000:], sep='\n', flush=True)
    check(build.returncode == 0, variant + ' probe builds against the production Vulkan and GPU projects')
    run = subprocess.run([DOTNET, str(out / 'bin/Release/net10.0/MeloNXCore667Probe.dll'), str(stub)],
                         capture_output=True, text=True, timeout=600, env=environment, cwd=out)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' probe runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
    print(variant + ': probe ran', flush=True)

control, candidate = reports['control'], reports['candidate']
nre = 'System.NullReferenceException'
check(control['barriers'] == {'bufferTexture': nre, 'bufferImage': nre, 'emptyTexture': 'none', 'emptyImage': 'none', 'bufferTextureTwice': nre},
      'control (Core 663): a buffer array\'s first barrier queue throws NullReferenceException (the IPA 666 render worker)')
check(candidate['barriers'] == {k: 'none' for k in control['barriers']}, 'candidate: buffer arrays return, view arrays as before')
check(control['configurationDefault'] == candidate['configurationDefault'] == candidate['configurationFast'],
      'fast math (every title but Hogwarts) writes the same MoltenVK configuration as Core 663')
offset, size = candidate['fastMathOffset'], candidate['configurationSize']
fast, precise = bytes.fromhex(candidate['configurationFast']), bytes.fromhex(candidate['configurationPrecise'])
check(len(fast) == size and fast[:offset] == precise[:offset] and fast[offset + 4:] == precise[offset + 4:],
      'precise math changes no configuration member but FastMathEnabled')
check(int.from_bytes(fast[offset:offset + 4], 'little') == 1 and int.from_bytes(precise[offset:offset + 4], 'little') == 0,
      'FastMathEnabled: 1 (MVK_CONFIG_FAST_MATH_ALWAYS) for fast, 0 (NEVER) for precise')
check(candidate['journal'].count('"mathMode"') == 3 and candidate['journal'].count('MoltenVK math mode precise (Inf and NaN kept)') == 1 and
      '"mathMode"' not in control['journal'], 'one durable math-mode line per configuration, candidate only')
if platform.system() == 'Darwin':
    check(candidate['notedPreciseMath'] == {'hogwarts': True, 'smash': False, 'reset': False}, 'the launch title selects precise math for Hogwarts only')
else:
    check(candidate['notedPreciseMath'] == {'hogwarts': False, 'smash': False, 'reset': False},
          'off Apple the title note leaves the default (the member is guarded to iOS/macOS); the Apple Core runner executes the choice')
check(candidate['arenaDecisions'] == [
    '0,0,6655 -> accept 1024', '0,0,4096 -> accept 0', '1024,0,4096 -> accept 1024', '1024,0,6655 -> accept 1024',
    '0,0,6144 -> accept 1024', '0,512,6655 -> accept 0', '1024,512,6655 -> refuse 1024', '1024,1024,6655 -> accept 1024',
    '0,1024,6655 -> accept 0', '1024,768,6655 -> refuse 1024', '512,0,6655 -> accept 1024'],
    'arena decisions: the first launch maps 1 GiB where the process may use 6 GiB; a mapped arena is final; a larger need is refused')
for variant in reports:
    saves = reports[variant]['shaderSaves']
    check(saves['pending'] == [2, 2, 0, 0] and saves['writerReceived'] == 64,
          variant + ': the save queue stops at an incomplete head, resumes in order, drops a failed link and writes 64 programs')
check(candidate['shaderSaves']['written'] == 64 and candidate['shaderSaves']['failed'] == 1 and candidate['shaderSaves']['longestHeadWaitMs'] >= 30,
      'candidate counters: 64 written, 1 dropped, the held head\'s wait measured')
check(control['shaderSaves']['written'] is None, 'control has no counters')
journal = candidate['journal']
check(journal.count('"shaderCache"') == 2 and 'written: programs made in play queued 0, written 64, dropped after a failed link 1, still queued 0' in journal
      and 'disposed: programs made in play queued 0, written 64, dropped after a failed link 1, still queued 0' in journal,
      'durable save lines at the 64th write and at disposal')
check('"shaderCache"' not in control['journal'], 'control journals no save line')

inputs = ['build-utils/melonx/adapt_buffer_array_barriers.py', 'build-utils/melonx/adapt_hogwarts_precise_math.py',
          'build-utils/melonx/adapt_shader_save_journal.py', 'build-utils/melonx/core667_native.py', 'build-utils/melonx/adapt_session.py',
          'native/melonx/EmbeddedRuntime.cs', 'native/melonx/EmbeddedLaunchPreflight.cs', 'test/melonx_core667_fixes_test.py',
          'test/melonx_core667_fixes/Program.cs', 'test/melonx_core667_fixes/StubMoltenVK.c', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               postimages={p: sha(FINAL_SOURCE / p) for p in POSTIMAGES}, reports=reports, sdk=sdk, host=platform.system(),
               libHacFeedSwitched=feeds,
               physicalDeviceTested=False, gameTested=False, productionAssembliesBuilt=['Ryujinx.Graphics.Vulkan', 'Ryujinx.Graphics.Gpu'],
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Host probe: the production array barrier calls, MoltenVK configuration write (test double of '
                          'MoltenVK), shader save loop and native arena decision. Whether Hogwarts Legacy\'s black sky blocks '
                          'go with precise math, its GPU cost, and the in-play shader saves are known only from a device run.')
out = ROOT / 'dist/melonx/core667-fixes-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
