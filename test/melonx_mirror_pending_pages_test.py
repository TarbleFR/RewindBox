#!/usr/bin/env python3
"""adapt_mirror_pending_pages on the final preparation, against the Core 721/723 preparation as control.

Usage: melonx_mirror_pending_pages_test.py <control> [--candidate-source <final preparation containing the adapter>]

IPA 718 Hogwarts in play: the large object heap stays at about 507 MiB with 213-267 MiB of holes; on a tile-based GPU
(every Apple GPU) a host-mapped buffer updated while the GPU may read it kept its pending bytes in `new byte[Size]`, a
managed copy of the whole buffer for its lifetime. The candidate keeps them in 16 KiB pages rented from the shared pool,
returned as soon as no pending range overlaps them.

Static: BufferHolder.cs only, the adapter's replacements only; no full-size copy left (no `new byte[Size]`, no
`_pendingData.AsSpan(`), every Remove of pending ranges followed by the pages' Release, the disposal returns every page;
the page class rents and returns through ArrayPool<byte>.Shared only and journals at most 16 lines. The production
Ryujinx.Graphics.Vulkan assembly builds. Executed (test/melonx_mirror_pending_pages/Program.cs): the candidate's own
PendingPages class (extracted from its BufferHolder.cs) with the production BufferMirrorRangeList.cs against the
delivered model (a byte[Size] copy and BufferMirrorRangeList.FillData), driven by the production call order of each
BufferHolder path (mirror write, direct write, mirror fill, upload): 400 random buffers and a 32 MiB buffer with
partial updates; every mirror fill, upload and remaining pending byte identical, the pages exactly those the pending
ranges overlap after every operation, every page returned at the end; a variant whose Release does nothing breaks
that invariant. No device. Writes dist/melonx/mirror-pending-pages-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_mirror_pending_pages', _HOLD)
import adapt_mirror_pending_pages as adapter  # noqa: E402
from adapt_descriptor_updates import method  # noqa: E402

HOLDER = adapter.HOLDER
RANGES = 'src/Ryujinx.Graphics.Vulkan/BufferMirrorRangeList.cs'
FIXTURE = ROOT / 'test/melonx_mirror_pending_pages'
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def read(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


for name, expected in adapter.BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the pinned preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-mirror-pending-pages-') as temporary:
    temporary = Path(temporary).resolve()
    candidate_tree = temporary / 'candidate-tree'
    shutil.copytree(SOURCE, candidate_tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    use_authenticated_libhac_feed(candidate_tree, ROOT)
    changed = adapter.apply(candidate_tree)
    check(sorted(p.relative_to(candidate_tree).as_posix() for p in changed) == [HOLDER], 'the adapter changes BufferHolder.cs only')
    duplicate = temporary / 'duplicate'
    (duplicate / HOLDER).parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(candidate_tree / HOLDER, duplicate / HOLDER)
    try:
        adapter.apply(duplicate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    control_text, candidate_text = read(SOURCE, HOLDER), read(candidate_tree, HOLDER)
    undone = candidate_text
    for old, new in reversed(adapter.PAIRS):
        check(undone.count(new) == 1, 'each replacement once: ' + new.strip().splitlines()[0][:60])
        undone = undone.replace(new, old)
    check(undone == control_text, 'BufferHolder.cs is the preparation but the adapter\'s replacements')
    if FINAL_PREPARATION and HOLDER not in files_edited_later('adapt_mirror_pending_pages'):
        check((candidate_tree / HOLDER).read_bytes() == (FINAL_SOURCE / HOLDER).read_bytes(), 'final preparation is the adapter')

    # Static: the copy is gone, every removal releases, the disposal returns everything, the pool is the only source.
    check('_pendingData = new byte[Size];' in control_text and 'new byte[Size]' not in candidate_text and
          '_pendingData.AsSpan(' not in candidate_text and 'private PendingPages _pendingData;' in candidate_text,
          'no full-size copy of the buffer is kept')
    outside = candidate_text[:candidate_text.index('        internal sealed class PendingPages')]
    removes = outside.count('_pendingDataRanges.Remove(')
    check(removes == control_text.count('_pendingDataRanges.Remove(') and
          outside.count('_pendingData.Release(_pendingDataRanges, ') == removes,
          'every removal of pending ranges releases the pages they no longer cover: %d removals' % removes)
    check('_pendingData?.ReleaseAll(); // RewindBox (adapt_mirror_pending_pages)' in method(candidate_text, '        public void Dispose()'),
          'the disposal returns every page')
    pages = method(candidate_text, '        internal sealed class PendingPages')
    write = method(pages, '            public void Write(int offset, ReadOnlySpan<byte> data)')
    gather = method(pages, '            public byte[] Gather(List<BufferMirrorRangeList.Range> ranges, int offset, int size)')
    check(pages.count('System.Buffers.ArrayPool<byte>.Shared.Rent(') == 2 and write.count('System.Buffers.ArrayPool<byte>.Shared.Rent(PageSize)') == 1 and
          gather.count('System.Buffers.ArrayPool<byte>.Shared.Rent(') == 1 and pages.count('System.Buffers.ArrayPool<byte>.Shared.Return(') == 2 and
          'new byte[' not in pages and 'private const int MaxReports = 16;' in pages and
          outside.count('System.Buffers.ArrayPool<byte>.Shared.Return(gathered);') == 1,
          'pages (Write) and the gathered upload array (Gather, returned by the upload) come from the shared pool only; at most 16 lines')
    check(pages.count('Ryujinx.Common.EmbeddedLaunchDiagnostics.Record(') == 1, 'one journal line kind')

    result = subprocess.run([DOTNET, 'build', str(candidate_tree / 'src/Ryujinx.Graphics.Vulkan/Ryujinx.Graphics.Vulkan.csproj'), '-c', 'Release',
                             '-nologo', '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400,
                            env=environment, cwd=candidate_tree)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-2000:], flush=True)
    check(result.returncode == 0, 'production Ryujinx.Graphics.Vulkan builds with the adapter')

    release_body = method(pages, '            public void Release(in BufferMirrorRangeList ranges, int offset, int size)')
    variants = {'candidate': pages,
                'noRelease': pages.replace(release_body, '            public void Release(in BufferMirrorRangeList ranges, int offset, int size)\n            {\n            }')}
    check(variants['noRelease'] != pages, 'the release is removable for the sensitivity variant')
    for variant, text in variants.items():
        work = temporary / variant
        work.mkdir()
        (work / 'Pages.cs').write_text('using System;\nusing System.Collections.Generic;\nusing System.Threading;\n\n'
                                       'namespace Ryujinx.Graphics.Vulkan\n{\n    static class BufferHolderPages\n    {\n' + text +
                                       '\n    }\n}\n')
        shutil.copyfile(candidate_tree / RANGES, work / 'BufferMirrorRangeList.cs')
        (work / 'Diagnostics.cs').write_text('''using System.Collections.Generic;

namespace Ryujinx.Common
{
    public static class EmbeddedLaunchDiagnostics
    {
        public static readonly List<string> Records = new();
        public static void Record(string stage, string status, int code = 0, string detail = "", long performanceGeneration = 0)
        {
            lock (Records) Records.Add(stage + "/" + status + ": " + detail);
        }
    }
}
''')
        shutil.copyfile(FIXTURE / 'Program.cs', work / 'Program.cs')
        (work / 'Probe.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><AllowUnsafeBlocks>true</AllowUnsafeBlocks>
<Nullable>disable</Nullable><ImplicitUsings>disable</ImplicitUsings><EnableNETAnalyzers>false</EnableNETAnalyzers>
<NuGetAudit>false</NuGetAudit></PropertyGroup></Project>''')
        (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
        (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
        result = subprocess.run([DOTNET, 'run', '--project', str(work / 'Probe.csproj'), '-c', 'Release', '--', variant],
                                cwd=work, capture_output=True, text=True, timeout=900, env=environment)
        if result.returncode:
            print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        check(result.returncode == 0, variant + ': the scenarios ran')
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(variant, json.dumps({k: v for k, v in reports[variant].items() if k not in ('failures', 'journal')})[:1500], flush=True)

k, n = reports['candidate'], reports['noRelease']
check(not k['failures'] and k['invariantFailures'] == 0 and k['missingPages'] == 0,
      'candidate: every fill, upload and pending byte identical, the pages exactly those the ranges overlap: ' + str(k['failures'][:3]))
check(k['operations'] >= 120000 and k['compared'] >= 30000 and k['invariantChecks'] == k['operations'],
      'the scenarios ran their operations and comparisons: %s' % {x: k[x] for x in ('operations', 'compared', 'invariantChecks')})
check(k['pageBytesAfter'] == 0 and k['fullBytesAfter'] == 0, 'every page returned and every buffer counted out at the end')
partial = k['partialUpdates']
# Measured (10 Nov), not a gain claim: with random partial updates the 32 MiB buffer keeps about 70 % of its size in pages
# and the 400 random buffers about 81 % of their full copies; a buffer under 16 KiB pays a whole page. The pages never
# outlive their ranges (invariant above); the gain needs the settle step (see the adapter).
check(partial['peakPageBytes'] <= partial['bufferBytes'], 'a 32 MiB buffer never holds more in pages than its size: ' + str(partial))
check(len(k['journal']) <= 16 and all(re.fullmatch(r'bufferMirrors/pendingPages: \d+ buffers with pending mirror data: full copies would hold '
                                                   r'[\d.]+ MiB; pages hold [\d.]+ MiB \(adapt_mirror_pending_pages\)', line) for line in k['journal']),
      'journal lines bounded and in their format: ' + str(k['journal'][:2]))
check(n['invariantFailures'] > 0, 'sensitivity: without Release the pages outlive their ranges')

inputs = ['build-utils/melonx/adapt_mirror_pending_pages.py', 'build-utils/melonx/adapt_session.py', 'build-utils/melonx/adapt_descriptor_updates.py',
          'test/melonx_mirror_pending_pages_test.py', 'test/melonx_mirror_pending_pages/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'preparationControl',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in adapter.BASELINE} if FINAL_PREPARATION else {},
               comparison=dict(sameMirrorFills=True, sameUploads=True, pagesFollowRanges=True, allPagesReturned=True,
                               partialUpdatePeakPageBytes=partial['peakPageBytes'], partialUpdateBufferBytes=partial['bufferBytes'],
                               randomPeakPageBytes=k['random']['peakPageBytesSum'], randomFullCopyBytes=k['random']['fullCopyBytesSum'],
                               sensitivityVariantFailed=True),
               reports={v: {x: y for x, y in r.items() if x != 'failures'} for v, r in reports.items()},
               sdk=sdk, physicalDeviceTested=False, productionAssembliesBuilt=['Ryujinx.Graphics.Vulkan'], sourceBaseline=adapter.BASELINE,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Pages follow the pending ranges; a range is written to the buffer only when rewritten or forced out, so '
                          'a ring of per-frame data rewritten in place keeps about as many pages as the copy held (the device line '
                          'bufferMirrors pendingPages gives both figures). Not measured on an iPhone.')
out = ROOT / 'dist/melonx/mirror-pending-pages-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, partialUpdates=partial)))
