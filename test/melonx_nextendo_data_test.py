#!/usr/bin/env python3
"""adapt_nextendo_data on the final preparation, against its predecessor as control.

Usage: melonx_nextendo_data_test.py <predecessor preparation> --candidate-source <final preparation>

Static: only Horizon's BCAT ServiceCreator.cs and ManagerServer.cs change; the replacements applied once to the control
give the final files and reverse to them; the served storage is asked for before LibHac's in both creation commands,
bcat:u keeps LibHac's PermissionDenied for another application's storage, and the id_token takes the version
NoteVersion passes through; the native files (EmbeddedOnline.cs, EmbeddedDeliveryCache.cs) are the prepared copies.
Static, host side: the bridge forwards bcatDirectory, nsa and acceptedVersions only through its validating builder;
inspectUpdate (EmbeddedAddons.cs) answers the update's display version from its Control NCA without throwing.
Built and executed: test/melonx_nextendo_data/Program.cs against the candidate's production Ryujinx.HLE and
Ryujinx.Horizon (the BCAT folder read and served with LibHac's results, MD5 digests, content and limits; the request's
optional parts; the NSA as account id). No device. Writes dist/melonx/nextendo-data-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
import adapt_nextendo_data as adapter  # noqa: E402

FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_nextendo_data', _HOLD)
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_nextendo_data/Program.cs'
# Checks of the fixture, pinned: a fixture that skips a part does not pass.
FIXTURE_CHECKS = 102
NATIVE = {'native/melonx/EmbeddedOnline.cs': 'src/Ryujinx.HLE/EmbeddedOnline.cs',
          'native/melonx/EmbeddedDeliveryCache.cs': 'src/Ryujinx.Horizon/EmbeddedDeliveryCache.cs'}
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


check(FINAL_PREPARATION, 'the candidate is the final preparation containing the adapter')
for name, expected in adapter.BASELINE.items():
    check(sha(SOURCE / name) == expected, 'control is the predecessor preparation: ' + name)
for native, prepared in NATIVE.items():
    check((FINAL_SOURCE / prepared).read_bytes() == (ROOT / native).read_bytes(), 'the prepared copy is the native file: ' + native)

texts = {}
for name in adapter.BASELINE:
    final = (FINAL_SOURCE / name).read_text(encoding='utf-8-sig')
    control_text = (SOURCE / name).read_text(encoding='utf-8-sig')
    forward = control_text
    for file, old, new in adapter.PAIRS:
        if file == name:
            check(forward.count(old) == 1, 'each replacement once: ' + name)
            forward = forward.replace(old, new)
    check(forward == final, 'the control plus the adapter is the final file: ' + name)
    reverted = final
    for file, old, new in reversed(adapter.PAIRS):
        if file == name:
            check(reverted.count(new) == 1, 'each replacement reverses once: ' + name)
            reverted = reverted.replace(new, old)
    check(reverted == control_text, 'the replacements reverse to the control: ' + name)
    texts[name] = final

creator = texts[adapter.SERVICE_CREATOR]
process = creator[creator.index('public Result CreateDeliveryCacheStorageService('):creator.index('public Result CreateDeliveryCacheStorageServiceWithApplicationId(')]
check(process.index('EmbeddedDeliveryCache.TryCreateForProcess(pid, out service)') < process.index('_libHacService.Get.CreateDeliveryCacheStorageService('),
      'by process: the served storage is asked for before LibHac')
application = creator[creator.index('public Result CreateDeliveryCacheStorageServiceWithApplicationId('):creator.index('public void Dispose()')]
check('_permissionLevel != BcatServicePermissionLevel.User && EmbeddedDeliveryCache.TryCreateForApplication(applicationId.Id, out service)' in application and
      application.index('TryCreateForApplication') < application.index('_libHacService.Get.CreateDeliveryCacheStorageServiceWithApplicationId('),
      'by application id: served only on ports allowed to mount another storage, before LibHac')
manager = texts[adapter.MANAGER]
check('GenerateIdToken(Ryujinx.HLE.EmbeddedOnline.Enabled ? Ryujinx.HLE.EmbeddedOnline.NoteVersion(context.Device.Processes.ActiveApplication.ProgramIdText, '
      'context.Device.Processes.ActiveApplication.DisplayVersion) : null)' in manager, 'the id_token takes the version NoteVersion passes through')

online = (ROOT / 'native/melonx/EmbeddedOnline.cs').read_text()
check('return settings == null ? offline : settings.Nsa ?? settings.Pid;' in online, 'the account id is the NSA when given, the PID otherwise')
check('Ryujinx.Horizon.Bcat.Ipc.EmbeddedDeliveryCache.Serve(settings?.BcatDirectory, out string reason)' in online and
      'Ryujinx.Horizon.Bcat.Ipc.EmbeddedDeliveryCache.Clear();' in online, 'the session hands its folder to the delivery cache and Clear stops serving')
check('NexToken' not in online[online.index('public static string NoteVersion('):online.index('public static IPAddress Redirect(')],
      'the journal line writes no token')
cache = (ROOT / 'native/melonx/EmbeddedDeliveryCache.cs').read_text()
check('MD5.HashData(data)' in cache and 'MaxDirectories = 100' in cache and 'MaxFilesPerDirectory = 100' in cache and 'MaxOpenCount = 8' in cache,
      "LibHac's limits and the MD5 digest")
check(cache.count('FileAccess.Read') == 1 and 'FileAccess.Write' not in cache and 'File.Write' not in cache and 'File.Delete' not in cache,
      'the folder is only read')

bridge = (ROOT / 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift').read_text()
builder = bridge[bridge.index('static func onlineRequest('):bridge.index('private func startDiagnostics(')]
check('withJSONObject:Self.onlineRequest(online,token:token,pid:pid,server:server,nat:nat)' in bridge,
      'the bridge sends the request its validating builder makes')
for key in ('bcatDirectory', 'nsa', 'acceptedVersions'):
    check(f'online["{key}"]' in builder and f'request["{key}"]' in builder, 'the bridge forwards ' + key + ' after its check')
check('resolvingSymlinksInPath()' in builder and 'lowerHex16' in builder and 'versions.count <= 16' in builder,
      'the bridge checks the folder under its BCAT root, the NSA and the versions')
check(not re.search(r'detail:[^\n]*\\\((path|nsa|versions|value)', builder), 'the bridge journals no value')

addons = (ROOT / 'native/melonx/EmbeddedAddons.cs').read_text()
method = addons[addons.index('internal static string UpdateDisplayVersion('):]
check('"/control.nacp"' in method and 'DisplayVersionString' in method and 'catch (Exception)' in method and 'TrimEnd' in method,
      'inspectUpdate reads the update Control NCA /control.nacp display version and never throws for it')
check('if (displayVersion != null) json.WriteString("displayVersion", displayVersion);' in addons,
      'inspectUpdate writes displayVersion only when read')

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-nextendo-data-') as temporary:
    temporary = Path(temporary).resolve()
    tree = temporary / 'candidate'
    shutil.copytree(FINAL_SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(tree, ROOT)
    fixture = temporary / 'fixture'
    fixture.mkdir()
    shutil.copyfile(FIXTURE, fixture / 'Program.cs')
    (fixture / 'Data.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup>'
        '<ItemGroup><ProjectReference Include="' + str(tree / 'src/Ryujinx.HLE/Ryujinx.HLE.csproj') + '" /></ItemGroup></Project>')
    for config in ('nuget.config', 'Directory.Packages.props', 'Directory.Build.props', 'global.json'):
        if (tree / config).exists():
            shutil.copyfile(tree / config, fixture / config)
    build = subprocess.run([DOTNET, 'build', str(fixture / 'Data.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                           cwd=fixture, env=environment, text=True, capture_output=True, timeout=3600)
    if build.returncode:
        print(build.stdout[-6000:], build.stderr[-2000:], flush=True)
    check(build.returncode == 0, 'the fixture builds against the production Ryujinx.HLE and Ryujinx.Horizon')
    work = temporary / 'work'
    work.mkdir()
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Data.dll'), str(work)], cwd=fixture, env=environment,
                         text=True, capture_output=True, timeout=600)
    if run.returncode:
        failure = work / 'failure.txt'
        print(run.stdout[-3000:], run.stderr[-4000:], failure.read_text()[-4000:] if failure.exists() else '', flush=True)
    check(run.returncode == 0, 'the fixture passes')
    report = json.loads((work / 'report.json').read_text())
    check(report['checks'] == FIXTURE_CHECKS, f"the fixture ran its {FIXTURE_CHECKS} checks: {report['checks']}")
    check(report['servedFiles'] == 4 and report['directories'] == ['line_news', 'popup_news', 'present2'], 'the SSBU-shaped folder served')

inputs = ['build-utils/melonx/adapt_nextendo_data.py', 'build-utils/melonx/prepare_embedded.py', 'test/melonx_adapter_control.py',
          'test/melonx_nextendo_data_test.py', 'test/melonx_nextendo_data/Program.cs', 'native/melonx/EmbeddedOnline.cs',
          'native/melonx/EmbeddedDeliveryCache.cs', 'native/melonx/EmbeddedAddons.cs',
          'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, fixtureChecks=report['checks'], finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl',
               postimages={p: sha(FINAL_SOURCE / p) for p in [*adapter.BASELINE, *NATIVE.values()]}, sdk=sdk, report=report,
               nextendoData=dict(executed=True, servedFiles=report['servedFiles'], digest='md5'),
               physicalDeviceTested=False, productionAssembliesBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Host CoreCLR on Linux; the arp lookup of a client process is replaced in the fixture (production reads '
                          'arp:r); LibHac\'s own path is checked statically; the Swift builder and inspectUpdate are checked '
                          'statically (no iOS toolchain here); no device')
out = ROOT / 'dist/melonx/nextendo-data-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, fixtureChecks=report['checks'], sdk=sdk)))
