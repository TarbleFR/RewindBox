#!/usr/bin/env python3
"""MemoryOwner's large buffers in native memory (adapt_large_buffer_native), before and after, the production file.

Usage: melonx_large_buffer_native_test.py <final preparation containing the adapter>
       melonx_large_buffer_native_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control); candidate is the adapter applied to it.
Static: each replacement once and reversible, the adapter fails closed on an adapted file, the final preparation is the
control plus the adapter; in the candidate the only allocation of elements is NewHolder's (an array, or native memory at
85 000 bytes or more for an element type without references), native memory is freed in one place, every holder the pool
lets go passes through ReleaseLocked, and a holder moved between the pool's lists does not.
Built: the production Ryujinx.Common assembly of the candidate, with no warning in the edited file.
Executed (test/melonx_large_buffer_native/Program.cs, the production MemoryOwner.cs of each variant next to it):
- with the host CoreCLR and its segments GC library (libclrgc.so: iOS NativeAOT has no regions), GCConserveMemory 5 and
  HighMemoryPercent 99 as the Core: a texture-upload-shaped workload (6 streaming bursts of 60 textures of 64 to 2048
  texels, 3.5 s of play frames between them uploading two smaller ones, a guest copy, a linear layout and one transcode in
  three per texture, a render thread copying each buffer into a staging ring and disposing it, a background gen2 every
  2 s, a live heap of small objects and long-lived large objects made during the bursts): the data the render thread
  copied is the same bit for bit; the large object heap's allocations (GCAllocationTick), its peak and its size and free
  space after a quiet period, committed memory, gen2 count; the candidate's native bytes;
- the candidate's contract (span, memory, pin, hit and miss data, RentCleared, RentCopy, element types, idle release,
  quarantine of a buffer let go at its return and of a leaked owner, concurrency, the spares' bound), with CoreCLR and
  with a NativeAOT build of the candidate (the host's NativeAOT runs the regions GC: a functional check only).
No device. Writes dist/melonx/large-buffer-native-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_large_buffer_native', _HOLD)
from adapt_large_buffer_native import apply, BASELINE, OWNER, PAIRS  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_large_buffer_native'
MIB = 1024 * 1024
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.index(signature)
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def run(command, cwd, environment, timeout=1800):
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        raise SystemExit('FAILED: ' + ' '.join(map(str, command[:4])))
    return result.stdout


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the adapter\'s preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-large-buffer-native-') as temporary:
    temporary = Path(temporary).resolve()
    work = temporary / 'candidate'
    work.mkdir()
    for entry in SOURCE.iterdir():
        if entry.is_file():
            shutil.copyfile(entry, work / entry.name)
    shutil.copytree(SOURCE / 'src/Ryujinx.Common', work / 'src/Ryujinx.Common', ignore=shutil.ignore_patterns('bin', 'obj'))
    use_authenticated_libhac_feed(work, ROOT)
    changed = apply(work)
    check([str(p.relative_to(work)) for p in changed] == [OWNER], 'the adapter changes MemoryOwner.cs only')
    if OWNER not in files_edited_later('adapt_large_buffer_native'):
        check((work / OWNER).read_bytes() == (FINAL_SOURCE / OWNER).read_bytes(), 'the final preparation is the control plus the adapter')
    try:
        apply(work)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted file is refused')
    control = (SOURCE / OWNER).read_text(encoding='utf-8-sig')
    candidate = (work / OWNER).read_text(encoding='utf-8-sig')
    for old, new in PAIRS:
        check(control.count(old) == 1 and candidate.count(new) == 1, 'each replacement is exact and reversible: ' + new.strip()[:60])

    # --- static ---
    pooling = candidate[candidate.index('private static class ArrayPooling'):candidate.index('private readonly int _length;')]
    check(control.count('new T[') == 1 and candidate.count('new T[') == 1 and 'return new Holder(new T[length]);' in member(candidate, 'private static Holder NewHolder(int length)'),
          'the only allocation of elements is NewHolder\'s')
    new_holder = member(candidate, 'private static Holder NewHolder(int length)')
    check('_nativeEligible && (long)length * Unsafe.SizeOf<T>() >= NativeMinimumBytes' in new_holder and
          'public const long NativeMinimumBytes = 85000;' in candidate and
          '!RuntimeHelpers.IsReferenceOrContainsReferences<T>()' in candidate, 'native at 85 000 bytes or more, element types without references only')
    check(candidate.count('NativeMemory.AllocZeroed(') == 1 and candidate.count('NativeMemory.Free(') == 1 and
          'NativeMemory.Free(' in member(candidate, 'private static unsafe void FreeNative(nint pointer, long bytes)'),
          'native memory is zeroed at allocation (as a new array) and freed in one place')
    check(candidate.count('FreeNative(') == 3 and 'FreeNative(' in member(candidate, 'private static void ReleaseLocked(Holder holder)') and
          'FreeNative(' in member(candidate, 'private static long FreeQuarantinedLocked(long now)'),
          'freed only by ReleaseLocked (a buffer idle for the quarantine\'s time) and by the quarantine')
    release = member(candidate, 'private static void ReleaseLocked(Holder holder)')
    check('Environment.TickCount64 - holder.Returned >= QuarantineMilliseconds' in release and 'QuarantineLocked(pointer, bytes, holder.Returned)' in release,
          'a buffer is freed QuarantineMilliseconds after its last return at the earliest')
    check(pooling.count('RemoveSpareLocked(') == 6 and pooling.count('ReleaseLocked(') == 8,
          'every spare removed outside Get is released, every holder dropped is released: %d / %d' %
          (pooling.count('RemoveSpareLocked('), pooling.count('ReleaseLocked(')))
    get = member(candidate, 'public static Holder Get(int minimumSize)')
    check('ReleaseLocked(' not in get and 'RemoveSpareLocked(spare);\n                            _pool[index] = spare;' in get,
          'a spare moved into the pool by a rent is not released')
    check(re.search(r'#pragma warning disable CA2015\s*~NativeBuffer\(\)', candidate) is not None and 'NativeMemory.Free' not in member(candidate, '~NativeBuffer()') and
          'QuarantineLocked(pointer, Bytes, Environment.TickCount64)' in member(candidate, '~NativeBuffer()'),
          'a leaked owner\'s buffer is quarantined by its finalizer, never freed there')
    check(re.findall(r'^using ([\w.]+);', candidate, re.M) == re.findall(r'^using ([\w.]+);', control, re.M),
          'no new namespace: the file still builds alone (the streaming-memory gate compiles it so)')
    check('Ryujinx.' not in candidate.replace('namespace Ryujinx.Common.Memory', ''), 'no reference to another engine type')
    for signature in ('public static MemoryOwner<T> Rent(int length)', 'public void Dispose()', 'public int Length'):
        check(member(candidate, signature) == member(control, signature), 'unchanged: ' + signature)
    check('result.Span.Clear();' in member(candidate, 'public static MemoryOwner<T> RentCleared(int length)') and
          'buffer.CopyTo(result.Span);' in member(candidate, 'public static MemoryOwner<T> RentCopy(ReadOnlySpan<T> buffer)'),
          'RentCleared and RentCopy act on the rented length, as before')

    # --- built ---
    out = run([DOTNET, 'build', str(work / 'src/Ryujinx.Common/Ryujinx.Common.csproj'), '-c', 'Release', '-nologo', '-m:1',
               '-p:NuGetAudit=false'], work, environment, timeout=2400)
    warned = sorted(set(line.strip() for line in out.splitlines() if 'MemoryOwner.cs' in line and 'warning' in line))
    check(not warned, 'no warning in the edited file: ' + str(warned[:2]))
    shutil.rmtree(work)

    # --- executed ---
    programs = {}
    for variant, text in (('control', control), ('candidate', candidate)):
        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        (fixture / 'MemoryOwner.cs').write_text(text, encoding='utf-8')
        (fixture / 'Probe.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit>'
            '<ServerGarbageCollection>false</ServerGarbageCollection><ConcurrentGarbageCollection>true</ConcurrentGarbageCollection>'
            '<NoWarn>CS8632;CS0162</NoWarn><DefineConstants>$(DefineConstants)' + (';CANDIDATE' if variant == 'candidate' else '') +
            '</DefineConstants></PropertyGroup></Project>\n')
        run([DOTNET, 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'], fixture, environment, timeout=900)
        programs[variant] = fixture / 'bin/Release/net10.0/Probe.dll'

    gc_library = 'libclrgc.dylib' if platform.system() == 'Darwin' else 'libclrgc.so'
    gc_environment = dict(environment, DOTNET_GCName=gc_library, DOTNET_GCConserveMemory='5', DOTNET_GCHighMemPercent='63')

    def json_line(text):
        return json.loads(next(line for line in reversed(text.splitlines()) if line.startswith('{')))

    for variant in ('control', 'candidate'):
        reports[variant] = json_line(run([DOTNET, str(programs[variant]), variant, 'main', '6'], temporary, gc_environment, timeout=600))
        print(json.dumps(reports[variant]), flush=True)
    reports['candidateContract'] = json_line(run([DOTNET, str(programs['candidate']), 'candidate', 'checks'], temporary, gc_environment, timeout=600))

    aot = temporary / 'aot'
    aot.mkdir()
    shutil.copyfile(FIXTURE / 'Program.cs', aot / 'Program.cs')
    (aot / 'MemoryOwner.cs').write_text(candidate, encoding='utf-8')
    (aot / 'Probe.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><PublishAot>true</PublishAot>'
        '<InvariantGlobalization>true</InvariantGlobalization><RuntimeIdentifier>linux-x64</RuntimeIdentifier>'
        '<ServerGarbageCollection>false</ServerGarbageCollection><ConcurrentGarbageCollection>true</ConcurrentGarbageCollection>'
        '<NoWarn>CS8632;CS0162</NoWarn><DefineConstants>$(DefineConstants);CANDIDATE;AOT</DefineConstants></PropertyGroup>'
        '<ItemGroup><RuntimeHostConfigurationOption Include="System.GC.ConserveMemory" Value="5" />'
        '<RuntimeHostConfigurationOption Include="System.GC.HighMemoryPercent" Value="99" /></ItemGroup></Project>\n')
    publish = run([DOTNET, 'publish', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q', '-o', 'out'], aot, environment, timeout=1800)
    check(' error ' not in publish, 'the candidate builds with NativeAOT')
    reports['aotContract'] = json_line(run([str(aot / 'out/Probe'), 'candidate', 'checks'], temporary, environment, timeout=600))
    reports['aotWorkload'] = json_line(run([str(aot / 'out/Probe'), 'candidate', 'main', '2'], temporary, environment, timeout=600))

c, k = reports['control'], reports['candidate']
check(c['gcName'] == k['gcName'] == gc_library, 'the segments GC library ran: ' + c['gcName'])
check(c['uploads'] == k['uploads'] > 800 and c['uploadBytes'] == k['uploadBytes'] > 600 * MIB and c['hash'] == k['hash'],
      'the same uploads and the same data copied by the render thread, bit for bit: %s %s' % (c['hash'], k['hash']))
# The large objects that are not texture data: the 24 MiB staging ring and the bursts' long-lived objects (6 x 6.3 MB).
others = 24 * MIB + 6 * sum((n + 1) * 300_000 for n in range(6))
check(c['lohAllocatedBytes'] >= others + 300 * MIB, 'control: the texture data allocates large objects: %d MiB' % (c['lohAllocatedBytes'] // MIB))
check(k['lohAllocatedBytes'] <= others + 16 * MIB, 'candidate: only the other large objects: %d MiB (others %d MiB)' %
      (k['lohAllocatedBytes'] // MIB, others // MIB))
check(k['nativeAllocatedBytes'] >= c['lohAllocatedBytes'] - others - 64 * MIB and k['nativeAllocations'] < 200,
      'the same misses, in native memory: %d MiB in %d buffers' % (k['nativeAllocatedBytes'] // MIB, k['nativeAllocations']))
check(k['maxLohBytes'] * 2 < c['maxLohBytes'], 'the large object heap\'s peak: %d -> %d MiB' % (c['maxLohBytes'] // MIB, k['maxLohBytes'] // MIB))
# After the quiet period a blocking gen2 runs: with ConserveMemory 5 the collector compacts the control's LOH itself when
# its fragmentation passes 50 % (adapt_bgc_fragmentation_guard), which no play-time collection of the device does: the
# control's holes after it are reported, not asserted; the candidate has none to leave either way.
check(k['lohFreeAfterBytes'] <= 4 * MIB, 'after the quiet period the candidate leaves no hole: %d MiB (control %d MiB)' %
      (k['lohFreeAfterBytes'] // MIB, c['lohFreeAfterBytes'] // MIB))
check(k['nativeLiveBytes'] == 0 and k['nativeQuarantinedBytes'] == 0 and k['nativeFrees'] == k['nativeAllocations'] and k['nativeLeaked'] == 0,
      'every native buffer is freed once the pool let it go: %s' % {key: k[key] for key in ('nativeLiveBytes', 'nativeFrees', 'nativeAllocations')})
check(k['committedAfterBytes'] + k['nativeLiveBytes'] <= c['committedAfterBytes'] + 4 * MIB,
      'committed after the quiet period, no more than the control\'s: %d -> %d MiB' %
      (c['committedAfterBytes'] // MIB, (k['committedAfterBytes'] + k['nativeLiveBytes']) // MIB))
check(k['maxCommittedBytes'] + k['nativePeakBytes'] <= c['maxCommittedBytes'] + 32 * MIB and k['nativePeakBytes'] <= 160 * MIB,
      'the peak: managed committed plus native at most the control\'s (+32 MiB): %d + %d against %d MiB' %
      (k['maxCommittedBytes'] // MIB, k['nativePeakBytes'] // MIB, c['maxCommittedBytes'] // MIB))
check(k['gen2Collections'] <= c['gen2Collections'], 'no more gen2 collections: %d -> %d' % (c['gen2Collections'], k['gen2Collections']))
for name in ('candidateContract', 'aotContract'):
    check(reports[name]['contractChecks'] == 25 and reports[name]['leaked'] == 1 and reports[name]['frees'] == reports[name]['allocations'],
          name + ': the contract holds, every buffer freed: %s' % reports[name])
w = reports['aotWorkload']
check(w['uploads'] > 250 and w['nativeLiveBytes'] == 0 and w['nativeFrees'] == w['nativeAllocations'] and w['lohFreeAfterBytes'] <= 4 * MIB,
      'NativeAOT runs the workload: %s' % {key: w[key] for key in ('uploads', 'nativeAllocations', 'nativeFrees', 'lohFreeAfterBytes')})

inputs = ['build-utils/melonx/adapt_large_buffer_native.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_large_buffer_native_test.py', 'test/melonx_large_buffer_native/Program.cs']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               physicalDeviceTested=False, productionAssemblyBuilt='Ryujinx.Common', nativeAotExecuted=True,
               gcLibrary=gc_library, postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               sourceBaseline=BASELINE, reports=reports, sdk=sdk,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host run of the production MemoryOwner.cs under a texture-shaped workload: CoreCLR with the segments GC '
                          'library (the iPhone runs NativeAOT with the segments build of the same gc.cpp) for the heap figures, '
                          'NativeAOT with the regions build for the contract. Host bytes and counts, not an iPhone\'s footprint: '
                          'what iOS compresses or decompresses is read from the device journal.')
out = ROOT / 'dist/melonx/large-buffer-native-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
