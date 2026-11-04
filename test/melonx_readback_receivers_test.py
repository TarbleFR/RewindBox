#!/usr/bin/env python3
"""Read-back receivers (adapt_readback_receivers) on the real prepared engine, before and after.

Usage: melonx_readback_receivers_test.py <Core 642 prepared MeloNX tree>
       melonx_readback_receivers_test.py <control> --candidate-source <final preparation containing the adapter>

Control is DmaClass.cs as prepared for Core 642 (IPA 643), candidate adds the adapter. For each, the production GPU
assembly (Ryujinx.Graphics.Gpu with its project references) is built, and the real TryReadBackIntoBuffer and
NoteReadBackOverlap (and the candidate's IsReadBackReceiver), with their enum and fields, are extracted from that
DmaClass.cs and run with doubles keeping a byte model of guest memory, the host buffer and the textures
(test/melonx_readback_receivers/Program.cs). The IPA 643 case (a 1x1 R32G32B32A32Float value read back each frame over the
game's 1x1 block-linear texture of that format) must show the control sampling the zeros of guest memory, then a value
older than the frame after a guest read flushes the buffer, and the candidate sampling each frame's value with no
flush and no write signal. Overlaps that cannot receive the source decline in the candidate (guest path); receivers of
other layouts, the unchanged paths and the bounded arrays are checked. No device; no FPS or pixel claim.
Writes dist/melonx/readback-receivers-checks.json.
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
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_readback_receivers', _HOLD)
from adapt_readback_receivers import apply, BASELINE  # noqa: E402

DMA = 'src/Ryujinx.Graphics.Gpu/Engine/Dma/DmaClass.cs'
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
    methods = [member(text, 'private bool TryReadBackIntoBuffer('), member(text, 'private void NoteReadBackOverlap(')]
    if 'private bool IsReadBackReceiver(' in text:
        methods.append(member(text, 'private bool IsReadBackReceiver('))
    return enum + fields + '\n'.join(methods) + '\n'


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 642 preparation: ' + name)

built, reports = {}, {}
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
with tempfile.TemporaryDirectory(prefix='melonx-readback-receivers-') as temporary:
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
        program = (ROOT / 'test/melonx_readback_receivers/Program.cs').read_text()
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
body = member(candidate, 'private bool TryReadBackIntoBuffer(')
check('SignalTextureWrite' not in body and 'SignalTextureWrite(address, size)' in member(control, 'private bool TryReadBackIntoBuffer('),
      'the write signal without data is removed from the read-back into a buffer only')
check(body.index('TryCopyTextureToBuffer(') < body.index('source.HostTexture.CopyTo(receiver.HostTexture, 0, 0);') <
      body.index('receiver.SignalModified();') < body.index('CreateHostSyncIfNeeded('), 'receivers copied after the buffer, before the sync')
check(body.index('receiver.SynchronizeMemory();') < body.index('source.HostTexture.CopyTo(receiver.HostTexture, 0, 0);'),
      'a receiver is synchronised before it is overwritten, as the GPU texture copy does')
check(body.count('return false;') == member(control, 'private bool TryReadBackIntoBuffer(').count('return false;') + 1,
      'one new decline (unreceivable), the others kept')
check(body.count('Array.Clear(_readBackReceivers, 0, textures);') == 5, 'receivers released on every path after they are found')
check(control.count('_readBackDeclines[(int)ReadBackDecline.Occupied]++;') + 1 ==
      candidate.count('_readBackDeclines[(int)ReadBackDecline.Occupied]++;'), 'unreceivable counted in occupied')
check('source group {_readBackOccupiedSource}, unreceivable {_readBackOccupiedUnreceivable}) target' in candidate and
      'copied into receivers {_readBackReceiverCopies}) of {_readBackCandidates}' in candidate, 'summary adds the two counts')
for method in ('private bool TryReadBackGpuRegion(', 'private void NoteReadBackOverlap(', 'private void NoteReadBackOccupant('):
    check(member(control, method) == member(candidate, method), 'unchanged: ' + method)

c, k = reports['control'], reports['candidate']
# A. IPA 643: control samples guest memory's zeros, then after a guest read an older value; candidate each frame's value.
check(c['sampled'] == [0, 0, 0, 3, 3] and k['sampled'] == [1, 2, 3, 4, 5],
      'control reloads stale guest memory; candidate holds the value read back: ' + str((c['sampled'], k['sampled'])))
check(c['gpuReadBacks'] == k['gpuReadBacks'] == [True] * 5, 'every read-back stays on the GPU path')
check(c['guestReadAfterFrame3'] == k['guestReadAfterFrame3'] == 3, 'a guest read sees the value read back in both')
check(k['writeSignals'] == 0 and c['writeSignals'] == 5, 'no write signal in the candidate')
check(k['flushesDuringFrames'] == 0 and c['flushesDuringFrames'] == 0, 'no flush per read-back (GPU wait) in either')
check(k['receiverCopies'] == 5 and c['receiverCopies'] == 0 and k['receiverReloads'] == 0 and c['receiverReloads'] == 5,
      'candidate copies into the receiver; control reloads it from guest memory')
check(c['bufferCopies'] == k['bufferCopies'] == 5 and c['forcedSyncs'] == k['forcedSyncs'] == 5, 'buffer copy and forced sync kept')
# The overlap line's signature includes "modified": the candidate's receiver is GPU-modified from the second read-back.
check(c['declines'] == k['declines'] == '0,0,0,0,0' and c['overlapLines'] == 1 and k['overlapLines'] == 2, 'same declines; overlap lines')
check(k['receiversCleared'], 'receivers released')
# B. Unreceivable overlaps decline (guest path) in the candidate; the control signalled and reloaded stale memory.
for name in ('format', 'size', 'view', 'scale', 'layers', 'offset', 'blockLinearWide', 'linearStride', 'incompatibleOverlaps',
             'hostConverted'):
    kc, cc = k['cases'][name], c['cases'][name]
    check(cc['gpu'] and cc['writeSignals'] == 1 and cc['holds'] == 0, 'control: GPU read-back, signal, stale texture: ' + name)
    check(not kc['gpu'] and kc['bufferCopies'] == 0 and kc['writeSignals'] == 0 and kc['receiverCopies'] == 0 and
          not kc['modified'] and kc['declines'] == '0,0,1,0,0' and kc['unreceivable'] == '1' and kc['receiversCleared'],
          'candidate declines as occupied (unreceivable): ' + name)
# C. Receivers: block-linear prefix and linear of the destination's stride hold the value, GPU-modified.
for name in ('blockLinearPrefix', 'linearSameStride'):
    kc, cc = k['cases'][name], c['cases'][name]
    check(kc['gpu'] and kc['holds'] == 7 and kc['modified'] and kc['receiverCopies'] == 1 and kc['writeSignals'] == 0 and
          kc['unreceivable'] == '0' and kc['receiversCleared'], 'candidate receiver: ' + name)
    check(cc['gpu'] and cc['holds'] == 0 and not cc['modified'], 'control stale: ' + name)
# D/E. Unchanged paths and bounded arrays.
cu, ku = c['unchanged'], k['unchanged']
check(cu['noTexture'] == ku['noTexture'] == {'gpu': True, 'writeSignals': 0, 'bufferCopies': 1, 'forcedSyncs': 1}, 'no texture there')
check(cu['sourceGroup']['gpu'] is ku['sourceGroup']['gpu'] is False and cu['sourceGroup']['declines'] == ku['sourceGroup']['declines'] ==
      '0,0,1,0,0' and ku['sourceGroup']['bufferCopies'] == 0 and ku['sourceGroup']['receiversCleared'], 'source group declines')
check(cu['fragmented']['gpu'] is ku['fragmented']['gpu'] is False and ku['fragmented']['declines'] == '0,1,0,0,0' and
      ku['fragmented']['receiverCopies'] == 0 and ku['fragmented']['receiversCleared'], 'fragmented declines as buffer')
check(cu['bufferRefused']['gpu'] is ku['bufferRefused']['gpu'] is False and ku['bufferRefused']['declines'] == '0,1,0,0,0' and
      not ku['bufferRefused']['receiverModified'] and ku['bufferRefused']['writeSignals'] == 0 and ku['bufferRefused']['receiversCleared'],
      'buffer refused: nothing copied, nothing signalled')
check(ku['nineReceivers'] == {'gpu': True, 'holding': 9, 'receiversCleared': True} and cu['nineReceivers']['holding'] == 0,
      'nine receivers (arrays grow) all hold the value')

inputs = ['build-utils/melonx/adapt_readback_receivers.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_readback_receivers_test.py', 'test/melonx_readback_receivers/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core642Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               candidateDmaClass=hashlib.sha256(candidate.encode()).hexdigest(), reports=reports, sdk=sdk,
               physicalDeviceTested=False, productionGpuAssemblyBuilt=True, sourceBaseline=BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Byte model with doubles around the real methods; whether the 1x1 texture drives the black launch '
                          'and the dark frames of IPA 643 is known only after a device run.')
out = ROOT / 'dist/melonx/readback-receivers-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
