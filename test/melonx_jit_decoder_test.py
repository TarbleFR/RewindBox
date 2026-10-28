#!/usr/bin/env python3
"""Decode and compile guest A64 code with the real LightningJit, with and without adapt_jit_decoder.

Usage: melonx_jit_decoder_test.py <pinned MeloNX checkout>

Both variants build the real Ryujinx.Cpu, ARMeilleure, Ryujinx.Memory and
Ryujinx.Common projects from the pinned source and generate host ARM64 code;
nothing is executed. A translation unit must end after a call that the next
function follows, after trap padding, and at a jump past 64 or more
instructions nothing in the unit enters (the other cases of a switch);
ordinary calls, known branch targets, loops, rotated loops and short skips
keep the upstream units. The layout case is clang's: functions that
end with a no-return call, back to back; the upstream decoder translates every
following function again for each entry point. With translations already
starting inside the code, a unit ends before the first of them and tail-calls
it, unless the code from there branches back into the unit within 1,024
instructions (a loop stays in one unit; for code reached without a branch,
back past it) or a forward branch of the unit passes over it by fewer than
64 instructions; without them, nothing changes. A unit ends before a page
that is not mapped, where upstream fails the whole translation.
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
TRANSLATOR = 'src/Ryujinx.Cpu/LightningJit/Translator.cs'


def build_variant(work: Path, adapted: bool) -> dict:
    source = work / 'source'
    (source / 'src').mkdir(parents=True)
    for name in ['Directory.Build.props', 'Directory.Packages.props', 'global.json', 'nuget.config']:
        if (SOURCE / name).exists():
            shutil.copyfile(SOURCE / name, source / name)
    for project in PROJECTS:
        shutil.copytree(SOURCE / 'src' / project, source / 'src' / project, ignore=shutil.ignore_patterns('bin', 'obj'))
    if adapted:
        assert [p.relative_to(source).as_posix() for p in apply(source)] == [DECODER, TRANSLATOR]
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
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>{'<DefineConstants>$(DefineConstants);ADAPTED</DefineConstants>' if adapted else ''}
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
    for name in ('callThenCode', 'callBeforeTarget', 'trapBeforeTarget', 'loop', 'rotatedLoop', 'shortSkip', 'enteredSkip'):
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
    expect(adapted['rotatedLoop']['guestInstructions'] == 73 and adapted['shortSkip']['guestInstructions'] == 22 and
           adapted['enteredSkip']['guestInstructions'] == 81,
           f'rotated loops, short skips and skips an earlier branch enters keep their unit: {adapted}')
    u, a = upstream['switchCase'], adapted['switchCase']
    expect(u['guestInstructions'] == 82 and a['guestInstructions'] == 6 and not a['truncated'] and u['hostBytes'] > 5 * a['hostBytes'],
           f'a switch case ends with its jump past the other cases: {u} {a}')
    u, a = upstream['layout'], adapted['layout']
    # The last function is followed by the frameless helper's RET, which it still includes.
    expect(a['guestInstructions'] == 300 * 12 + 1, f'adapted: each entry translates its own function: {a}')
    expect(u['guestInstructions'] > 50 * a['guestInstructions'] and u['hostBytes'] > 20 * a['hostBytes'],
           f'upstream: each entry translates the following functions too: {u} vs {a}')
    u, a = upstream['knownRunOn'], adapted['knownRunOn']
    expect(u['guestInstructions'] == 41 and not u['truncated'] and a['guestInstructions'] == 20 and a['truncated'] and
           not a['emptyLastBlock'], f'a unit ends before an instruction another translation starts at: {u} {a}')
    u, a = upstream['knownBlockStart'], adapted['knownBlockStart']
    expect(u['guestInstructions'] == 12 and a['guestInstructions'] == 2 and a['truncated'] and a['emptyLastBlock'],
           f'at a block start the unit ends with an empty block: {u} {a}')
    u, a = upstream['knownAfterLoop'], adapted['knownAfterLoop']
    expect(u['guestInstructions'] == 11 and a['guestInstructions'] == 5 and a['truncated'],
           f'a translation after a loop ends the unit there: {u} {a}')
    for name in ('knownInLoop', 'ownEntry'):
        u, a = dict(upstream[name]), dict(adapted[name])
        size = abs(u.pop('hostBytes') - a.pop('hostBytes'))
        expect(u == a and size <= 16 and not a['truncated'],
               f'{name}: a loop through a translated entry stays in its unit: {upstream[name]} {adapted[name]}')
    u, a = upstream['farLoop'], adapted['farLoop']
    expect(u['guestInstructions'] == 1203 and a['guestInstructions'] == 100 and a['truncated'],
           f'a branch back farther than 1,024 instructions does not keep the unit going: {u} {a}')
    u, a = upstream['continuationInLoop'], adapted['continuationInLoop']
    expect(u['guestInstructions'] == 10 and a['guestInstructions'] == 10 and not a['truncated'],
           f'a continuation inside a loop keeps the loop body through a translated entry: {u} {a}')
    u, a = upstream['unmappedAfterCall'], adapted['unmappedAfterCall']
    expect(u.get('throws') and not a.get('throws') and a['guestInstructions'] == 1024 and a['truncated'] and
           a['emptyLastBlock'] and a['hostCalls'] == 1,
           f'upstream fails the translation at the unmapped page; adapted ends the unit before it: {u} {a}')
    u, a = upstream['silentUnmappedAfterCall'], adapted['silentUnmappedAfterCall']
    expect(u.get('guestInstructions', 0) > 5 * 1024 and u['truncated'] and a['guestInstructions'] == 1024 and
           a['truncated'] and a['emptyLastBlock'] and a['hostCalls'] == 1 and u['hostBytes'] > 50 * a['hostBytes'],
           f'reading an unmapped page as zeros (HostTracked), upstream decodes on into it; adapted ends before it: {u} {a}')
    u, a = dict(upstream['unmappedLongJump']), dict(adapted['unmappedLongJump'])
    size = abs(u.pop('hostBytes', 0) - a.pop('hostBytes', 0))
    expect(not u.get('throws') and u == a and size <= 16 and a['guestInstructions'] == 1011,
           f'a long jump to an unmapped page decodes as upstream: {upstream["unmappedLongJump"]} {adapted["unmappedLongJump"]}')
    for name in ('knownSwitchCases', 'knownSkippedThen'):
        u, a = dict(upstream[name]), dict(adapted[name])
        size = abs(u.pop('hostBytes') - a.pop('hostBytes'))
        expect(u == a and size <= 16 and not a['truncated'],
               f'{name}: code a short forward branch passes over stays in the unit: {upstream[name]} {adapted[name]}')
    u, a = upstream['framelessLayout'], adapted['framelessLayout']
    expect(a['guestInstructions'] == 300 * 12 + 1 and u['guestInstructions'] > 50 * a['guestInstructions'] and
           u['hostBytes'] > 20 * a['hostBytes'],
           f'functions without a frame stop at the next translated function start: {u} vs {a}')
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
               upstreamInputs={p: hashlib.sha256((SOURCE / p).read_bytes()).hexdigest() for p in (DECODER, TRANSLATOR)})
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
      f"known targets and loops unchanged; a switch case stops at its jump past the other cases. Frameless functions "
      f"with translated starts: upstream {upstream['framelessLayout']['guestInstructions']} / adapted "
      f"{adapted['framelessLayout']['guestInstructions']} guest instructions; units end where another translation starts, "
      f"loops through it stay whole.")
