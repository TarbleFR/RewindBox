#!/usr/bin/env python3
"""adapt_occupied_readback_buffers on the final preparation, against the Core 687 DmaClass.cs as control.

Usage: melonx_occupied_readback_buffers_test.py <control> --candidate-source <final preparation containing the adapter>
       melonx_occupied_readback_buffers_test.py <Core 687 prepared MeloNX tree>

IPA 688 (Hogwarts Legacy, async shaders on): 4 391 read-backs declined as "occupied" took the guest path, a texture flush
and a host GPU wait each (texFlushAction 0.4-2.3 s per 5.1 s window). For each variant the production GPU assembly
(Ryujinx.Graphics.Gpu with its project references) is built, and the real TryReadBackGpuRegion, TryReadBackIntoBuffer,
IsReadBackReceiver, NoteReadBackOverlap and NoteReadBackOccupant, with their enum and fields, are extracted from that
DmaClass.cs and run with byte-model doubles (test/melonx_occupied_readback_buffers/Program.cs). The two IPA 688 occupants
(an R32Float texture buffer, the game's 1x1 R32G32B32A32Float block-linear texture) must take the guest path (a flush)
in the control and the GPU path into a buffer in the candidate, with the CPU and the occupant seeing the value read back;
what TryReadBackIntoBuffer cannot keep coherent (unreceivable occupant, the source's group, a partial copy, the buffer
refusing) keeps the guest path in both; fragmented, empty and buffer destinations are unchanged. No device; no FPS claim.
Writes dist/melonx/occupied-readback-buffers-checks.json.
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
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_occupied_readback_buffers', _HOLD)
from adapt_occupied_readback_buffers import apply, BASELINE, DMA  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
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


def extract(text):
    """The read-back enum, fields and methods of the prepared DmaClass.cs, verbatim."""
    enum = re.search(r'^ *private enum ReadBackDecline \{[^}]*\}\n', text, re.M).group(0)
    fields = text[text.index('        private Image.Texture[] _targetOverlaps'):text.index('        private bool _bufferReadBackNoted;\n')]
    fields += '        private bool _bufferReadBackNoted;\n'
    methods = [member(text, 'private bool ' + name + '(') for name in ('TryReadBackGpuRegion', 'TryReadBackIntoBuffer', 'IsReadBackReceiver')]
    methods += [member(text, 'private void ' + name + '(') for name in ('NoteReadBackOverlap', 'NoteReadBackOccupant')]
    return enum + fields + '\n'.join(methods) + '\n'


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 687 preparation: ' + name)

built, reports = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-occupied-readback-buffers-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        if variant == 'candidate':
            changed = apply(work)
            check([str(p.relative_to(work)) for p in changed] == [DMA], 'adapter changed other files')
            if FINAL_PREPARATION:
                check((work / DMA).read_bytes() == (FINAL_SOURCE / DMA).read_bytes(), 'final preparation is the adapter')
        text = (work / DMA).read_text(encoding='utf-8-sig')
        built[variant] = text
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Graphics.Gpu/Ryujinx.Graphics.Gpu.csproj'), '-c', 'Release',
                                 '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=1800,
                                env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production GPU assembly builds')

        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        program = (ROOT / 'test/melonx_occupied_readback_buffers/Program.cs').read_text()
        (fixture / 'Program.cs').write_text(program.replace('//__EXTRACTED__\n', extract(text)))
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><TreatWarningsAsErrors>false</TreatWarningsAsErrors>'
            '<NoWarn>CS0169;CS0414;CS0649;CS8632</NoWarn></PropertyGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(json.dumps(reports[variant]), flush=True)

control, candidate = built['control'], built['candidate']
region_c, region_k = member(control, 'private bool TryReadBackGpuRegion('), member(candidate, 'private bool TryReadBackGpuRegion(')
check(region_k.index('if (occupants != 0 && contiguous)') < region_k.index('if (occupants != 0 || !contiguous)'),
      'the reroute precedes the occupied decline')
check(region_k.count('TryReadBackIntoBuffer(') == region_c.count('TryReadBackIntoBuffer(') + 1, 'one new call into the buffer path')
for method in ('private bool TryReadBackIntoBuffer(', 'private bool IsReadBackReceiver(', 'private void NoteReadBackOverlap(',
               'private void NoteReadBackOccupant(', 'private bool TryCopyGpuRegion('):
    check(member(control, method) == member(candidate, method), 'unchanged: ' + method)
check('unreceivable {_readBackOccupiedUnreceivable}; rerouted into buffers {_readBackOccupiedRerouted}, copied '
      '{_readBackOccupiedReroutedCopies}) target' in candidate, 'summary adds the two counts')

c, k = reports['control']['cases'], reports['candidate']['cases']
# A. The IPA 688 occupants: guest path (a flush) in the control, a GPU copy into a buffer in the candidate.
for name in ('textureBuffer', 'receiver'):
    check(not c[name]['gpu'] and c[name]['guestPathFlushes'] == 1 and c[name]['bufferCopies'] == 0 and
          c[name]['declines'] == '0,0,1,0,0' and c[name]['otherTextures'] == '1' and c[name]['rerouted'] == 'absent',
          'control: occupied decline, guest path: ' + name)
    check(k[name]['gpu'] and k[name]['guestPathFlushes'] == 0 and k[name]['bufferCopies'] == 1 and k[name]['forcedSyncs'] == 1 and
          k[name]['declines'] == '0,0,0,0,0' and k[name]['otherTextures'] == '0' and k[name]['rerouted'] == '1' and
          k[name]['reroutedCopies'] == '1' and k[name]['rerouteLines'] == 1 and k[name]['occupantLines'] == 0 and
          k[name]['writeSignals'] == 0 and k[name]['overlapsCleared'], 'candidate: GPU copy into a buffer: ' + name)
    check(c[name]['cpuReads'] == k[name]['cpuReads'] == 5.0, 'the CPU reads the value read back in both: ' + name)
check(k['receiver']['receiverCopies'] == 1 and k['receiver']['occupantHolds'] == 5.0, 'the receiver holds the value (GPU copy)')
check(k['textureBuffer']['receiverCopies'] == 0, 'a texture buffer is left alone')
# B. What the buffer path cannot keep coherent keeps the guest path in the candidate too.
for name, declines, counter in (('unreceivable', '0,0,1,0,0', ('unreceivable', '1')), ('sourceGroup', '0,0,1,0,0', None),
                                ('partial', '0,0,0,0,1', None), ('bufferRefused', '0,1,0,0,0', None)):
    check(not k[name]['gpu'] and k[name]['guestPathFlushes'] == 1 and k[name]['declines'] == declines and
          k[name]['rerouted'] == '1' and k[name]['reroutedCopies'] == '0' and k[name]['receiverCopies'] == 0 and
          k[name]['writeSignals'] == 0 and k[name]['overlapsCleared'], 'candidate keeps the guest path: ' + name)
    check(not c[name]['gpu'] and c[name]['declines'] == '0,0,1,0,0', 'control declined as occupied: ' + name)
    check(c[name]['cpuReads'] == k[name]['cpuReads'] == 5.0, 'the guest path writes the value: ' + name)
    if counter:
        check(k[name][counter[0]] == counter[1], 'counted: ' + name)
check(k['bufferRefused']['bufferCopies'] == 0, 'nothing copied when the buffer refuses')
# C. Unchanged: occupied and fragmented, empty (linear texture created), empty and fragmented, buffer already there.
for name in ('fragmentedOccupied', 'empty', 'fragmentedEmpty', 'buffer'):
    keys = ('gpu', 'guestPathFlushes', 'cpuReads', 'occupantHolds', 'bufferCopies', 'forcedSyncs', 'receiverCopies', 'created',
            'writeSignals', 'declines', 'otherTextures', 'fragmented', 'unreceivable', 'occupantLines')
    check({x: c[name][x] for x in keys} == {x: k[name][x] for x in keys} and k[name]['rerouted'] == '0', 'unchanged: ' + name)
check(k['empty']['gpu'] and k['empty']['created'] == 1 and k['empty']['cpuReads'] == 5.0, 'empty: linear texture read-back')
check(not k['fragmentedOccupied']['gpu'] and k['fragmentedOccupied']['declines'] == '0,0,1,0,0', 'fragmented occupied declines')
check(k['buffer']['gpu'] and k['buffer']['receiverCopies'] == 1, 'buffer there: receivers fed as before')
# D. 60 frames of the IPA 688 case: one flush per frame in the control, none in the candidate, one log line.
fc, fk = reports['control']['frames'], reports['candidate']['frames']
check(fc['gpu'] == 0 and fc['guestPathFlushes'] == 60, 'control: 60 guest-path flushes (host GPU waits)')
check(fk['gpu'] == 60 and fk['guestPathFlushes'] == 0 and fk['lastCpuRead'] == 60.0 and fk['rerouteLines'] == 1,
      'candidate: 60 GPU read-backs, the CPU sees the last frame, one line')

inputs = ['build-utils/melonx/adapt_occupied_readback_buffers.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_occupied_readback_buffers_test.py', 'test/melonx_occupied_readback_buffers/Program.cs',
          'test/melonx_readback_receivers/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core687Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               candidateDmaClass=hashlib.sha256(candidate.encode()).hexdigest(), reports=reports, sdk=sdk,
               physicalDeviceTested=False, productionGpuAssemblyBuilt=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Byte model with doubles around the real methods; the frame-time gain is known only after a device run.')
out = ROOT / 'dist/melonx/occupied-readback-buffers-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
