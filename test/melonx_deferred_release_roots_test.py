#!/usr/bin/env python3
"""The device release left to the cache's loading thread keeps no closed session (adapt_deferred_release_roots).

Usage: melonx_deferred_release_roots_test.py <final preparation containing the adapter>
       melonx_deferred_release_roots_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control), candidate is the adapter applied to it,
which must be the final preparation byte for byte. For each, the production Vulkan assembly is built, and the real end
of VulkanRenderer.Dispose (from the adapt_pipeline_cache_background comment to the end of the method) and, in the
candidate, the real VulkanRenderer.DeviceRelease run with doubles (test/melonx_deferred_release_roots): eleven sessions
are closed while the load of each still runs, so each loading thread keeps its action; after three blocking compacting
collections the control keeps the eleven renderers and their 8 MiB sessions reachable (IPA 816-820: "renderer 1/1;
Switch still reachable"), the candidate keeps none. In both, nothing is destroyed before a load returns, each load then
destroys the device, the debug messenger and the instance in that order, once, and a close with no load running
destroys them at once. Static checks bind that the method is static and reads no instance member. No device.
Writes dist/melonx/deferred-release-roots-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_deferred_release_roots', _HOLD)
from adapt_deferred_release_roots import apply, BASELINE, OLD, NEW  # noqa: E402

VULKAN = 'src/Ryujinx.Graphics.Vulkan/'
RENDERER = VULKAN + 'VulkanRenderer.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_deferred_release_roots'
MARK = '            // RewindBox (adapt_pipeline_cache_background): while MoltenVK still loads the main snapshot'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the adapter\'s preparation: ' + name)

reports, texts = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-deferred-release-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            later = files_edited_later('adapt_deferred_release_roots')
            for name in BASELINE:
                if name not in later:
                    check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        result = subprocess.run([DOTNET, 'build', str(work / (VULKAN + 'Ryujinx.Graphics.Vulkan.csproj')), '-c', 'Release', '-nologo',
                                 '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Vulkan assembly builds')

        renderer = (work / RENDERER).read_text(encoding='utf-8-sig')
        texts[variant] = renderer
        dispose = member(renderer, 'public unsafe void Dispose()')
        check(dispose.count(MARK) == 1, variant + ': the deferred release is the end of Dispose')
        tail = dispose[dispose.index(MARK):]
        methods = member(renderer, 'private static unsafe Action DeviceRelease(') if 'Action DeviceRelease(' in renderer else ''
        check(bool(methods) == (variant == 'candidate'), variant + ': the static builder only in the candidate')
        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        template = (FIXTURE / 'Double.cs').read_text()
        for mark, code in (('/* DISPOSE_TAIL */', tail), ('/* RENDERER_METHODS */', methods)):
            check(template.count(mark) == 1, 'fixture mark ' + mark)
            template = template.replace(mark, code)
        (fixture / 'Double.cs').write_text(template)
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks>'
            '<TieredPGO>false</TieredPGO><NoWarn>CS0649;CS0414;CS0169;CS8321</NoWarn></PropertyGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
order = ['device 7', 'messenger', 'instance']
check(c['closed'] == k['closed'] == 11, 'eleven sessions closed during their load')
check(c['renderersAlive'] == 11 and c['sessionsAlive'] == 11, 'control: every closed session stays reachable while its load runs: ' +
      str((c['renderersAlive'], c['sessionsAlive'])))
check(k['renderersAlive'] == 0 and k['sessionsAlive'] == 0, 'candidate: no closed session is kept: ' + str((k['renderersAlive'], k['sessionsAlive'])))
check(c['callsBeforeLoadEnd'] == k['callsBeforeLoadEnd'] == 0, 'nothing is destroyed before a load returns')
check(c['deferredCalls'] == k['deferredCalls'] == order * 11, 'each load destroys the device, the messenger and the instance, in that order, once')
check(c['sessionsAliveAfterLoads'] == k['sessionsAliveAfterLoads'] == 0, 'nothing is kept once the loads have returned')
check(c['immediateCalls'] == k['immediateCalls'] == order and not c['immediateDeferred'] and not k['immediateDeferred'],
      'with no load running the release runs at once')

control, candidate = texts['control'], texts['candidate']
check(candidate.replace(NEW, OLD) == control and candidate.count(NEW) == 1, 'VulkanRenderer unchanged but the release action')
builder = member(candidate, 'private static unsafe Action DeviceRelease(')
check(re.search(r'\b(this|_device|_debugMessenger|_instance|Api|SurfaceApi|_surface|_window|_getSurface)\b', builder) is None,
      'the builder reads no instance member')
check(builder.index('api.DestroyDevice(device, null);') < builder.index('debugMessenger.Dispose();') < builder.index('instance.Dispose();'),
      'the same three calls in the same order')
dispose = member(candidate, 'public unsafe void Dispose()')
check('void ReleaseDevice()' not in dispose and dispose.count('DeviceRelease(Api, _device, _debugMessenger, _instance)') == 1 and
      dispose.index('SurfaceApi.DestroySurface(') < dispose.index('DeviceRelease(Api, _device, _debugMessenger, _instance)') <
      dispose.index('PipelineCacheManager.DeferDeviceRelease(releaseDevice)') < dispose.index('releaseDevice();'),
      'Dispose builds the action after the surface is destroyed and defers or runs it as before')

inputs = ['build-utils/melonx/adapt_deferred_release_roots.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_deferred_release_roots_test.py', 'test/melonx_deferred_release_roots/Double.cs',
          'test/melonx_deferred_release_roots/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionVulkanAssemblyBuilt=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host reachability of the action with doubles for the renderer\'s members; whether a closed session is '
                          'released on an iPhone is read from the sessionRetention and retentionChain lines of a device run.')
out = ROOT / 'dist/melonx/deferred-release-roots-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
