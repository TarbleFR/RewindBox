#!/usr/bin/env python3
"""Present source attribution (adapt_present_source_attribution) on the real prepared engine. Diagnostics only.

Usage: melonx_present_source_attribution_test.py <Core 642 prepared MeloNX tree>
       melonx_present_source_attribution_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the prepared tree and builds the production GPU assembly (Ryujinx.Graphics.Gpu with
its project references). Static checks bind that Present is unchanged but for one call placed before the texture's
synchronisation, and that the diagnostic only reads state (CheckDirty without consuming; no synchronisation, flush,
signal or texture reference kept). The real NotePresentSource with its fields runs with doubles
(test/melonx_present_source_attribution/Program.cs): a re-created texture, a texture reloaded from guest memory, a
repeated address and a texture not modified but valid are told apart; 8 detail lines at most, a summary every 300
presents at most 64 times, a map of at most 16 addresses. No device. Writes dist/melonx/present-source-attribution-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_present_source_attribution', _HOLD)
from adapt_present_source_attribution import apply, BASELINE  # noqa: E402

WINDOW = 'src/Ryujinx.Graphics.Gpu/Window.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
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


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 642 preparation: ' + name)
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
control = (SOURCE / WINDOW).read_text(encoding='utf-8-sig')
with tempfile.TemporaryDirectory(prefix='melonx-present-source-') as temporary:
    work = Path(temporary).resolve() / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    changed = apply(work)
    check([str(p.relative_to(work)) for p in changed] == [WINDOW], 'adapter changed other files')
    if FINAL_PREPARATION:
        check((work / WINDOW).read_bytes() == (FINAL_SOURCE / WINDOW).read_bytes(), 'final preparation is the adapter')
    candidate = (work / WINDOW).read_text(encoding='utf-8-sig')
    result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800,
                            env=environment, cwd=work)
    if result.returncode:
        print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production GPU assembly builds')

    present_control = member(control, 'public void Present(Action swapBuffersCallback)')
    present = member(candidate, 'public void Present(Action swapBuffersCallback)')
    inserted = '''                // RewindBox (adapt_present_source_attribution): before the synchronisation, diagnostics only.
                NotePresentSource(texture);

'''
    check(present.replace(inserted, '') == present_control and present.count('NotePresentSource(texture);') == 1, 'Present unchanged but one call')
    check(present.index('pt.Cache.Tick();') < present.index('NotePresentSource(texture);') < present.index('texture.SynchronizeMemory();'),
          'recorded before the synchronisation')
    note = member(candidate, 'private void NotePresentSource(')
    check('CheckDirty(texture, false)' in note and not re.search(r'SynchronizeMemory|Flush|Signal|CheckDirty\(texture, true\)', note),
          'reads state only')
    check('Dictionary<ulong, int> _presentedByAddress' in candidate and 'Dictionary<ulong, Image.Texture>' not in candidate,
          'no texture reference kept')
    for other in ('public bool PresentLoop(', 'private void DropFrame(', 'public void SignalFrameReady('):
        check(member(control, other) == member(candidate, other), 'unchanged: ' + other)

    fields = candidate[candidate.index('        private const int PresentSourceLineLimit'):candidate.index('        private int _presentSourceLines, _presentSourceSummaries;\n')]
    fields += '        private int _presentSourceLines, _presentSourceSummaries;\n'
    fixture = Path(temporary).resolve() / 'fixture'
    fixture.mkdir()
    program = (ROOT / 'test/melonx_present_source_attribution/Program.cs').read_text()
    (fixture / 'Program.cs').write_text(program.replace('//__EXTRACTED__\n', fields + note + '\n'))
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit></PropertyGroup></Project>\n')
    for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                    [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
        result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
            result.check_returncode()
    report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
    print(json.dumps(report), flush=True)

details = report['details']
check(len(details) == 8, 'detail lines bounded to 8')
check('present 7 at 0x10000000' in details[0] and 'reloaded from guest memory True, re-created texture True' in details[0],
      'a re-created texture from guest memory: ' + details[0])
check('present 8 at 0x20000000' in details[1] and 'reloaded from guest memory True, re-created texture False, same address as previous False' in details[1],
      'a dirty texture not modified: ' + details[1])
check('present 9 at 0x20000000' in details[2] and 'same address as previous True' in details[2], 'a repeated address')
check(not any('present 10 ' in line for line in details), 'a valid texture not modified is not a detail line')
check(report['firstSummary'] == 'Present sources: 300 presents, from guest memory 3, not GPU-modified 4, re-created textures 1, '
      'same address as previous 1, first at an address 3', 'first summary: ' + report['firstSummary'])
check(report['summaries'] == 64, 'summaries bounded to 64')
check(report['mapCount'] <= 16, 'address map bounded')
check(report['calls'] == ['dirty False', 'modified'], 'only AnyHandleModified and CheckDirty(texture, false) called: ' + str(report['calls']))

inputs = ['build-utils/melonx/adapt_present_source_attribution.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_present_source_attribution_test.py', 'test/melonx_present_source_attribution/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core642Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               candidateWindow=hashlib.sha256(candidate.encode()).hexdigest(), report=report, sdk=sdk, physicalDeviceTested=False,
               productionGpuAssemblyBuilt=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Diagnostics only; where the black launch and the stale frames come from is known only after a device run.')
out = ROOT / 'dist/melonx/present-source-attribution-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
