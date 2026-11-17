#!/usr/bin/env python3
"""adapt_cheat_report on the final preparation, against its predecessor as control.

Usage: melonx_cheat_report_test.py <predecessor preparation> --candidate-source <final preparation>

Static: only ModLoader.cs, TamperMachine.cs, ProcessLoaderHelper.cs and the prepared EmbeddedContent.cs change; each edit
only adds lines (what is installed, enabled or executed is unchanged); the replacements applied once to the control give
the final files and reverse to them; the report begins before LoadCheats' early return, counts the cheats found and each
cheat skipped for another build id, and is written after LoadCheats with the process's build ids; content operation 0
answers "buildId" only when read, inspectUpdate (native EmbeddedAddons.cs) the update's the same way, neither throwing for
it; the native EmbeddedCheatReport.cs is the prepared copy.
Built and executed: test/melonx_cheat_report/Program.cs against the candidate's production Ryujinx.HLE (a cheats folder
with one file for the running build and two for other builds collected and installed by the real ModLoader into the real
TamperMachine, enabled.txt, the report's Warning line and counts, the main build id of an ExeFS and of the loaded NSOs).
The lines pass the journal's own redaction filter (EmbeddedLaunchDiagnostics.Safe) unchanged. No device. Writes
dist/melonx/cheat-report-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
import adapt_cheat_report as adapter  # noqa: E402

FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_cheat_report', _HOLD)
DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_cheat_report/Program.cs'
# Checks of the fixture, pinned: a fixture that skips a part does not pass.
FIXTURE_CHECKS = 27
NATIVE = {'native/melonx/EmbeddedCheatReport.cs': 'src/Ryujinx.HLE/EmbeddedCheatReport.cs',
          'native/melonx/EmbeddedAddons.cs': 'src/Ryujinx.Library/EmbeddedAddons.cs'}
MATCHING = ('Cheats of 01006a800016e000: main build id 0123456789ABCDEF; found 5, installed 2, enabled 1, skipped for another '
            'build id 3 (1111222233334444, FEDCBA9876543210) (adapt_cheat_report)')
NONE_MATCHING = ('Cheats of 01006a800016e000: main build id 9999888877776666; found 5, installed 0, enabled 0, skipped for '
                 'another build id 5 (0123456789ABCDEF, 1111222233334444, FEDCBA9876543210) (adapt_cheat_report)')
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
for name, old, new in adapter.PAIRS:
    check(new.startswith(old) or new.endswith(old), 'each edit only adds lines: ' + name)

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

loader = texts[adapter.MOD_LOADER]
load = loader[loader.index('internal void LoadCheats('):loader.index('internal static void EnableCheats(')]
check(load.index('EmbeddedCheatReport.Begin(applicationId)') < load.index('mods.Cheats.Count == 0'),
      'the report begins before the early return of a title without cheats')
check(load.index('List<Cheat> cheats = mods.Cheats;') < load.index('EmbeddedCheatReport.Found(cheats.Count)') < load.index('foreach (Cheat cheat in cheats)'),
      'the cheats found are counted before the loop')
skip = load[load.index('Skipping cheat'):]
check(skip.index('EmbeddedCheatReport.Skipped(cheatId)') < skip.index('continue;') < skip.index('InstallAtmosphereCheat'),
      'each cheat skipped for another build id is counted, with its id, before the loop continues')
helper = texts[adapter.HELPER]
check(helper.index('ModLoader.LoadCheats(programId, tamperInfo, device.TamperMachine);') <
      helper.index('EmbeddedCheatReport.Write(programId, Ryujinx.HLE.EmbeddedCheatReport.MainOf(executables), buildIds, device.TamperMachine);'),
      'the line is written after LoadCheats with the process build ids and its main executable')
tamper = texts[adapter.TAMPER]
counts = tamper[tamper.index('internal (int Installed, int Enabled) CheatCounts('):tamper.index('private static bool IsProcessValid(')]
check('_programDictionary' in counts and not re.search(r'IsEnabled\s*=[^=]|_programDictionary\.(Add|TryAdd|Remove|Clear)|_programs\.|Activate\(', counts),
      'CheatCounts only reads the machine')
content = texts[adapter.CONTENT]
check('string mainBuildId = EmbeddedApplicationBuildId(path);\n' in content and 'if (mainBuildId != null) json.WriteString("buildId", mainBuildId);' in content,
      'content operation 0 answers buildId only when read')
addons = (ROOT / 'native/melonx/EmbeddedAddons.cs').read_text()
check('if (updateBuildId != null) json.WriteString("buildId", updateBuildId);' in addons,
      'inspectUpdate answers the update buildId only when read')
for method in ('internal static string UpdateBuildId(', 'internal static string EmbeddedApplicationBuildId('):
    body = addons[addons.index(method):]
    body = body[:body.index('\n    }\n') + 6]
    check('EmbeddedCheatReport.MainBuildId(' in body and 'NcaSectionType.Code' in body and 'catch (Exception)' in body,
          'the main build id of the ExeFS, never throwing: ' + method)
report_source = (ROOT / 'native/melonx/EmbeddedCheatReport.cs').read_text()
check('Logger.Warning?.Print(LogClass.ModLoader, line);' in report_source and report_source.count('Logger.') == 1,
      'one Warning line, in the ModLoader class')

# The journal's own filter: the C# patterns of EmbeddedLaunchDiagnostics.Safe, applied as written.
diagnostics = (ROOT / 'native/melonx/EmbeddedLaunchDiagnostics.cs').read_text()
safe = diagnostics[diagnostics.index('public static string Safe('):]
patterns = re.findall(r'Regex\.Replace\(value, @"((?:[^"]|"")*)"', safe[:safe.index('return value')])
check(len(patterns) == 2, 'the journal filter has its two patterns: ' + str(patterns))

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-cheat-report-') as temporary:
    temporary = Path(temporary).resolve()
    tree = temporary / 'candidate'
    shutil.copytree(FINAL_SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(tree, ROOT)
    fixture = temporary / 'fixture'
    fixture.mkdir()
    shutil.copyfile(FIXTURE, fixture / 'Program.cs')
    (fixture / 'Cheats.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><AllowUnsafeBlocks>true</AllowUnsafeBlocks></PropertyGroup>'
        '<ItemGroup><ProjectReference Include="' + str(tree / 'src/Ryujinx.HLE/Ryujinx.HLE.csproj') + '" /></ItemGroup></Project>')
    for config in ('nuget.config', 'Directory.Packages.props', 'Directory.Build.props', 'global.json'):
        if (tree / config).exists():
            shutil.copyfile(tree / config, fixture / config)
    build = subprocess.run([DOTNET, 'build', str(fixture / 'Cheats.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                           cwd=fixture, env=environment, text=True, capture_output=True, timeout=3600)
    if build.returncode:
        print(build.stdout[-6000:], build.stderr[-2000:], flush=True)
    check(build.returncode == 0, 'the fixture builds against the production Ryujinx.HLE')
    work = temporary / 'work'
    work.mkdir()
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Cheats.dll'), str(work)], cwd=fixture,
                         env=dict(environment, HOME=str(work)), text=True, capture_output=True, timeout=600)
    if run.returncode:
        failure = work / 'failure.txt'
        print(run.stdout[-3000:], run.stderr[-4000:], failure.read_text()[-4000:] if failure.exists() else '', flush=True)
    check(run.returncode == 0, 'the fixture passes')
    report = json.loads((work / 'report.json').read_text())
    check(report['checks'] == FIXTURE_CHECKS, f"the fixture ran its {FIXTURE_CHECKS} checks: {report['checks']}")
    check(report['matching'] == MATCHING, 'one matching file: two installed, one enabled, three skipped with two ids')
    check(report['noneMatching'] == NONE_MATCHING, 'a catalogue for another build: nothing installed, every id listed')
    for key in ('matching', 'noneMatching', 'withoutCheats'):
        line = report[key]
        filtered = line
        for pattern in patterns:
            filtered = re.sub(pattern.replace('""', '"'), '[redacted]', filtered)
        check(filtered == line, 'the journal filter keeps the line as written: ' + key)

inputs = ['build-utils/melonx/adapt_cheat_report.py', 'build-utils/melonx/prepare_embedded.py', 'test/melonx_adapter_control.py',
          'test/melonx_cheat_report_test.py', 'test/melonx_cheat_report/Program.cs', 'native/melonx/EmbeddedCheatReport.cs',
          'native/melonx/EmbeddedAddons.cs', 'native/melonx/EmbeddedLaunchDiagnostics.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, fixtureChecks=report['checks'], finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl',
               postimages={p: sha(FINAL_SOURCE / p) for p in [*adapter.BASELINE, *NATIVE.values()]}, sdk=sdk, report=report,
               cheatReport=dict(executed=True, lines=[report['matching'], report['noneMatching'], report['withoutCheats']]),
               physicalDeviceTested=False, productionAssembliesBuilt=True, sourceBaseline=adapter.BASELINE,
               inputs={p: sha(ROOT / p) for p in inputs},
               limitation='Host CoreCLR on Linux; the process is an uninitialised KProcess (cheats compiled and installed, '
                          'not executed on guest memory); the metadata and inspectUpdate build ids are checked statically '
                          '(no game files or keys here); no device')
out = ROOT / 'dist/melonx/cheat-report-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, fixtureChecks=report['checks'], sdk=sdk)))
