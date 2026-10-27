#!/usr/bin/env python3
"""Decode and compile guest A64 code with the real LightningJit, with and without adapt_jit_decoder.

Usage: melonx_jit_decoder_test.py <pinned MeloNX checkout>

Both variants build the real Ryujinx.Cpu, ARMeilleure, Ryujinx.Memory and
Ryujinx.Common projects from the pinned source and generate host ARM64 code;
nothing is executed. A translation unit must end after a call that the next
function follows and after trap padding; ordinary calls, known branch targets
and loops keep the upstream units. The layout case is clang's: functions that
end with a no-return call, back to back; the upstream decoder translates every
following function again for each entry point.
"""
from pathlib import Path
import hashlib, json, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
from adapt_jit_decoder import apply

PIN = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
actual = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
assert actual == PIN['revision'], (actual, PIN['revision'])
assert not subprocess.check_output(['git', '-C', str(SOURCE), 'status', '--porcelain', '--', 'src/Ryujinx.Cpu',
                                    'src/ARMeilleure', 'src/Ryujinx.Memory'], text=True).strip()

PROJECTS = ['Ryujinx.Cpu', 'ARMeilleure', 'Ryujinx.Memory', 'Ryujinx.Common']
DECODER = 'src/Ryujinx.Cpu/LightningJit/Arm64/Target/Arm64/Decoder.cs'


def build_variant(work: Path, adapted: bool) -> dict:
    source = work / 'source'
    (source / 'src').mkdir(parents=True)
    for name in ['Directory.Build.props', 'Directory.Packages.props', 'global.json', 'nuget.config']:
        if (SOURCE / name).exists():
            shutil.copyfile(SOURCE / name, source / name)
    for project in PROJECTS:
        shutil.copytree(SOURCE / 'src' / project, source / 'src' / project, ignore=shutil.ignore_patterns('bin', 'obj'))
    if adapted:
        assert [p.relative_to(source).as_posix() for p in apply(source)] == [DECODER]
    cpu = source / 'src/Ryujinx.Cpu/Ryujinx.Cpu.csproj'
    text = cpu.read_text(encoding='utf-8-sig')
    assert text.count('</Project>') == 1
    # Test-only access to the internal decoder and compiler; product unchanged.
    cpu.write_text(text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="MeloNXJitDecoderProbe" /></ItemGroup>\n</Project>'))
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': PIN['dotnet'], 'rollForward': 'latestFeature'}}))
    probe = work / 'probe'
    probe.mkdir()
    shutil.copyfile(ROOT / 'test/melonx_jit_decoder/Program.cs', probe / 'Program.cs')
    (probe / 'MeloNXJitDecoderProbe.csproj').write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{source}/src/Ryujinx.Cpu/Ryujinx.Cpu.csproj" />
  </ItemGroup>
</Project>
''')
    build = subprocess.run(['dotnet', 'build', str(probe), '-c', 'Release', '-nologo', '-v', 'q'],
                           capture_output=True, text=True, timeout=900)
    if build.returncode:
        errors = [line for line in build.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), build.stdout[-3000:], build.stderr[-3000:], sep='\n')
        build.check_returncode()
    run = subprocess.run(['dotnet', str(probe / 'bin/Release/net10.0/MeloNXJitDecoderProbe.dll')],
                         capture_output=True, text=True, timeout=600)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], sep='\n', flush=True)
        run.check_returncode()
    return json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))


def check(upstream: dict, adapted: dict):
    failures = []

    def expect(condition, message):
        if not condition:
            failures.append(message)

    u, a = upstream['callThenFunction'], adapted['callThenFunction']
    expect(u['guestInstructions'] == 47, f'upstream translates the next function after a call: {u}')
    expect(a['guestInstructions'] == 3 and a['truncated'] and a['emptyLastBlock'] and a['hostCalls'] == 1,
           f'adapted: the unit ends after the call, which keeps its host call and return check: {a}')
    u, a = upstream['callNopsThenFunction'], adapted['callNopsThenFunction']
    expect(u['guestInstructions'] == 48 and a['guestInstructions'] == 3 and a['emptyLastBlock'],
           f'NOP padding before the next frame: {u} {a}')
    for name in ('callThenCode', 'callBeforeTarget', 'trapBeforeTarget', 'loop'):
        # Host addresses (function table slots) are process-specific and change
        # how many MOVK instructions a constant takes: compare the units, and
        # the code size within a few instructions.
        u, a = dict(upstream[name]), dict(adapted[name])
        size = abs(u.pop('hostBytes') - a.pop('hostBytes'))
        expect(u == a and size <= 16, f'{name} unchanged: {upstream[name]} {adapted[name]}')
    expect(adapted['callThenCode']['guestInstructions'] == 45 and adapted['callBeforeTarget']['guestInstructions'] == 46,
           f'ordinary calls and known targets keep their unit: {adapted["callThenCode"]} {adapted["callBeforeTarget"]}')
    u, a = upstream['tailJump'], adapted['tailJump']
    expect(u['guestInstructions'] == 49 and a['guestInstructions'] == 4 and not a['truncated'],
           f'a tail jump to the next function ends the unit with the jump: {u} {a}')
    u, a = upstream['trapPadding'], adapted['trapPadding']
    expect(u['guestInstructions'] == 144 and a['guestInstructions'] == 3 and a['truncated'] and not a['emptyLastBlock'],
           f'trap padding: upstream decodes through it, adapted stops at the first trap: {u} {a}')
    u, a = upstream['layout'], adapted['layout']
    # The last function is followed by the frameless helper's RET, which it still includes.
    expect(a['guestInstructions'] == 300 * 12 + 1, f'adapted: each entry translates its own function: {a}')
    expect(u['guestInstructions'] > 50 * a['guestInstructions'] and u['hostBytes'] > 20 * a['hostBytes'],
           f'upstream: each entry translates the following functions too: {u} vs {a}')
    return failures


with tempfile.TemporaryDirectory(prefix='melonx-jit-decoder-') as temporary:
    work = Path(temporary).resolve()
    upstream = build_variant(work / 'upstream', False)
    adapted = build_variant(work / 'adapted', True)
failures = check(upstream, adapted)
inputs = ['build-utils/melonx/adapt_jit_decoder.py', 'test/melonx_jit_decoder_test.py', 'test/melonx_jit_decoder/Program.cs']
receipt = dict(result='failed' if failures else 'passed', failures=failures, upstream=upstream, adapted=adapted,
               executed=False, physicalDeviceTested=False, upstreamRevision=PIN['revision'],
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               upstreamInputs={DECODER: hashlib.sha256((SOURCE / DECODER).read_bytes()).hexdigest()})
out = ROOT / 'dist/melonx/jit-decoder-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
if failures:
    print('\n'.join(failures))
    sys.exit(1)
u, a = upstream['layout'], adapted['layout']
print(f"MeloNX JIT decoder: 300 back-to-back functions ending in a no-return call — upstream {u['guestInstructions']} guest "
      f"instructions / {u['hostBytes'] // 1024} KiB host code translated, adapted {a['guestInstructions']} / "
      f"{a['hostBytes'] // 1024} KiB; units end after calls followed by a frame and after traps; ordinary calls, "
      f"known targets and loops unchanged.")
