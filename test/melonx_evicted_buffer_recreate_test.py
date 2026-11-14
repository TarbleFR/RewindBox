#!/usr/bin/env python3
"""adapt_evicted_buffer_recreate on the final preparation, against the Core 675 postimage as control.

A buffer evicted from the GPU buffer cache is recreated when a binding uses it again, in both host memory budget
settings (with tracking off the lookup returned null: IPA 674 Hogwarts abort in BufferCache.GetBuffer). Control: the
final preparation with the adapter reversed (melonx_adapter_control), which must be the Core 675 bytes. Executed
(test/melonx_evicted_buffer_recreate) for control and candidate on the variant's real BufferCache.cs members: cache
bookkeeping, eviction, buffer creation entry points and binding lookups; the physical buffer, the range list and the
aligned and multi-range creation bodies are doubles. Writes dist/melonx/evicted-buffer-recreate-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import melonx_adapter_control as control_tools  # noqa: E402
import adapt_evicted_buffer_recreate as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
CACHE = 'src/Ryujinx.Graphics.Gpu/Memory/BufferCache.cs'
RANGES = ['src/Ryujinx.Memory/Range/MultiRange.cs', 'src/Ryujinx.Memory/Range/MemoryRange.cs']
HARNESS = ROOT / 'test/melonx_evicted_buffer_recreate'
MEMBERS = [
    'private void AddBuffer(Buffer buffer)',
    'private void RemoveBufferTracking(Buffer buffer)',
    'private void Touch(Buffer buffer)',
    'private void EnforceCapacity(Buffer protectedBuffer)',
    'private void EnforceCapacity(Buffer protectedBuffer, ulong target)',
    'public void CreateBuffer(ulong address, ulong size, BufferStage stage)',
    'public void CreateBuffer(ulong address, ulong size, BufferStage stage, ulong alignment)',
    'private void CreateMultiRangeBuffer(MultiRange range, BufferStage stage)',
    'public BufferRange GetBufferRangeAligned(MultiRange range, BufferStage stage, bool write = false)',
    'private Buffer GetOrCreateBuffer(ulong address, ulong size, BufferStage stage)',
    'private Buffer GetBuffer(ulong address, ulong size, BufferStage stage, bool write = false)',
    'private Buffer GetOrCreateSparseBuffer(ulong address, ulong size, BufferStage stage)',
]
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
    assert text.count(signature) == 1, signature
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


temporary = tempfile.TemporaryDirectory(prefix='melonx-evicted-buffer-recreate-')
WORK = Path(temporary.name).resolve()
CONTROL = WORK / 'control'
# Core 731: adapt_cold_buffer_trim edits BufferCache.cs after this adapter (a stamp in AddBuffer and Touch, the end of
# Trim, added members). POST is this adapter's own postimage (the later adapters reversed); the static comparison reads
# it; the executed candidate is the final preparation, which must still hold this adapter's three replacements.
POST = WORK / 'post'
LATER = control_tools.postimage('adapt_evicted_buffer_recreate', FINAL_SOURCE, POST)
# IPA 736 lot: adapt_buffer_last_hit edits it after that (a memo of the last buffers returned, read by GetOrCreateBuffer
# and emptied by RemoveBufferTracking): the executed candidate takes the members it adds with the real ones.
import adapt_buffer_last_hit as _hit  # noqa: E402
# IPA 740 lot: adapt_buffer_hit_sets then turns that memo into two-way sets emptied per removed buffer.
import adapt_buffer_hit_sets as _sets  # noqa: E402
check(LATER in ([], ['adapt_cold_buffer_trim'], ['adapt_cold_buffer_trim', 'adapt_buffer_last_hit'],
                ['adapt_cold_buffer_trim', 'adapt_buffer_last_hit', 'adapt_buffer_hit_sets']),
      'the later adapters sharing the file are known: %s' % LATER)
_ADDED = _hit.ADDED.replace(_sets.TABLE_OLD, _sets.TABLE_NEW) if 'adapt_buffer_hit_sets' in LATER else _hit.ADDED
check(_sets.TABLE_OLD in _hit.ADDED, 'the two-way sets replace the last-hit members')
for name in adapter.BASELINE:
    (CONTROL / name).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(POST / name, CONTROL / name)

# --- Control: the adapter reversed must be the Core 675 bytes; forward reproduces the final preparation ---
control_tools._reverse('adapt_evicted_buffer_recreate', CONTROL)
for name, expected in adapter.BASELINE.items():
    check(sha(CONTROL / name) == expected, 'control is the Core 675 postimage: ' + name)
forward = WORK / 'forward'
shutil.copytree(POST, forward)
for name in adapter.BASELINE:
    shutil.copyfile(CONTROL / name, forward / name)
changed = sorted(str(p.relative_to(forward)) for p in adapter.apply(forward))
check(changed == sorted(adapter.BASELINE), 'the adapter changes only its files')
for name in adapter.BASELINE:
    check((forward / name).read_bytes() == (POST / name).read_bytes(), 'the postimage is the adapter: ' + name)
for later in LATER:
    __import__(later).apply(forward)
for path in sorted(p for p in forward.rglob('*') if p.is_file()):
    name = str(path.relative_to(forward))
    check(path.read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter and the later ones: ' + name)
drift = WORK / 'drift'
(drift / CACHE).parent.mkdir(parents=True, exist_ok=True)
(drift / CACHE).write_bytes((CONTROL / CACHE).read_bytes() + b'\n// unreviewed drift\n')
try:
    adapter.apply(drift)
    drift_refused = False
except AssertionError:
    drift_refused = True
check(drift_refused, 'a drifted BufferCache.cs is refused')

# --- Static: the exact scope ---
final, control, shipped = read(POST, CACHE), read(CONTROL, CACHE), read(FINAL_SOURCE, CACHE)
for new in (adapter.MULTI_NEW, adapter.LOOKUP_NEW, adapter.SPARSE_NEW):
    # IPA 740 lot: adapt_buffer_hit_sets edits GetOrCreateBuffer's first lookup after this adapter; its postimage holds the
    # replacement and the forward check above proves the later adapters give the final preparation.
    check((final if new == adapter.LOOKUP_NEW and 'adapt_buffer_hit_sets' in LATER else shipped).count(new) == 1,
          'the final preparation holds this adapter\'s replacement')
check(control.count('GraphicsConfig.EnableHostMemoryBudgetTracking') == 5 and final.count('GraphicsConfig.EnableHostMemoryBudgetTracking') == 2,
      'only the three lookup/suppression conditions are removed')
check('EnableHostMemoryBudgetTracking' in member(final, 'public ulong Trim(MemoryPressureLevel level)') and
      'EnableHostMemoryBudgetTracking' in member(final, 'public void Initialize(ulong cpuMemorySize)'),
      'pressure trimming and the limit basis still follow the setting')
for signature in ('private Buffer GetOrCreateBuffer(ulong address, ulong size, BufferStage stage)',
                  'private Buffer GetOrCreateSparseBuffer(ulong address, ulong size, BufferStage stage)',
                  'private void CreateMultiRangeBuffer(MultiRange range, BufferStage stage)'):
    check('EnableHostMemoryBudgetTracking' not in member(final, signature), 'unconditional in both settings: ' + signature)
restored = final
for old, new in ((adapter.MULTI_OLD, adapter.MULTI_NEW), (adapter.LOOKUP_OLD, adapter.LOOKUP_NEW), (adapter.SPARSE_OLD, adapter.SPARSE_NEW)):
    restored = restored.replace(new, old)
check(restored == control, 'BufferCache.cs differs only by the three replacements')

# --- Executed: control and candidate fixtures on the real members ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
reports, compiled = {}, {}
for variant in ('control', 'candidate'):
    text = control if variant == 'control' else shipped
    fixture = WORK / ('fixture-' + variant)
    fixture.mkdir()
    members = '\n\n'.join(member(text, signature) for signature in MEMBERS)
    if variant == 'candidate' and 'adapt_buffer_last_hit' in LATER:
        check(shipped.count(_ADDED) == 1, 'the final preparation holds the last-hit members once')
        members += '\n' + _ADDED
    (fixture / 'Members.cs').write_text(
        'using Ryujinx.Memory.Range;\nusing System;\nusing System.Collections.Generic;\n\n'
        'namespace Ryujinx.Graphics.Gpu.Memory\n{\n    public partial class BufferCache\n    {\n' + members + '\n    }\n}\n')
    for name in RANGES:
        shutil.copyfile(FINAL_SOURCE / name, fixture / Path(name).name)
    shutil.copyfile(HARNESS / 'Program.cs', fixture / 'Program.cs')
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit>'
        '<NoWarn>CS0649;CS0414;CS0169;CS0067;CS8321;CS0162;CS8632</NoWarn></PropertyGroup></Project>\n')
    build = subprocess.run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                           capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
    if build.returncode:
        print('\n'.join(line for line in build.stdout.splitlines() if ': error ' in line)[:6000], flush=True)
    check(build.returncode == 0, variant + ' fixture builds with the real BufferCache.cs members')
    run = subprocess.run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), variant],
                         capture_output=True, text=True, timeout=600, env=environment, cwd=fixture)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, variant + ' fixture runs')
    reports[variant] = json.loads(run.stdout.strip().splitlines()[-1])
    compiled[variant] = {p.name: sha(p) for p in sorted(fixture.glob('*.cs'))}
    print(variant + ': ' + json.dumps(reports[variant]), flush=True)

c, k = reports['control'], reports['candidate']
co, ko = c['trackingOff'], k['trackingOff']
check(co['evictedBinding'] == {'exception': 'NullReferenceException'},
      'control (Core 675), tracking off: a binding of an evicted buffer dereferences null (the IPA 674 abort)')
check(ko['evictedBinding'] == {'contained': True, 'disposed': False, 'resident': True, 'evictedBefore': True, 'cachedBytesWithinLimit': True},
      'candidate, tracking off: the evicted buffer is recreated, contains the range and the limit holds')
check(co['partialAfterEviction'].get('contained') is False and ko['partialAfterEviction'] == {'contained': True, 'disposed': False, 'resident': True},
      'tracking off: a buffer that only partly covers the range is no longer returned')
check(co['sparseAfterEviction'] == {'found': False, 'contained': False} and ko['sparseAfterEviction'] == {'found': True, 'contained': True},
      'tracking off: the sparse-aligned lookup recreates an evicted buffer')
check(co['multiRange']['subBuffersEvictedDuringCreation'] >= 1 and ko['multiRange'] == {'subBuffersEvictedDuringCreation': 0, 'cachedBytesWithinLimitAfter': True},
      'tracking off: no sub-buffer is evicted before its multi-range buffer exists; the limit is enforced after')
check(co['resident'] == ko['resident'] == {'sameBuffer': True, 'created': 0}, 'tracking off: a resident buffer is used as before, nothing created')
check(c['trackingOn'] == k['trackingOn'], 'tracking on: identical behaviour in every scenario')
check(k['trackingOn'] == k['trackingOff'], 'candidate: both settings behave the same')

inputs = ['build-utils/melonx/adapt_evicted_buffer_recreate.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_evicted_buffer_recreate_test.py',
          'test/melonx_evicted_buffer_recreate/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
               postimages={n: sha(FINAL_SOURCE / n) for n in adapter.BASELINE}, reports=reports, compiledSources=compiled, sdk=sdk,
               host=platform.system(), physicalDeviceTested=False, gameTested=False, inputs={n: sha(ROOT / n) for n in inputs},
               limitation='Host fixture of the real BufferCache.cs members with doubles for the physical buffer, the range list and '
                          'the creation bodies. The IPA 674 abort is known only from a device run.')
out = ROOT / 'dist/melonx/evicted-buffer-recreate-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
