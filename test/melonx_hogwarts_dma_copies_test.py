#!/usr/bin/env python3
"""Check adapt_hogwarts_dma_copies on the delivered sources, and run its attribution method.

Usage: melonx_hogwarts_dma_copies_test.py <prepared tree without this adapter> [--candidate-source <final tree>]

1. The adapter is applied to copies of its three delivered files (DmaClass.cs, GraphicsConfig.cs,
   Library.cs). Every change is checked: the policy flag defaults to off; the Library assigns it
   for every session from the launched title only, before the renderer is made threaded, with the
   query policy unchanged; the GPU-side copy condition admits R16G16B16A16Float and
   R32G32B32A32Float sources only under the flag, and nothing else in it moves; the attribution
   call sits immediately before the read through guest memory. The adapted files differ from the
   delivered ones only by these hunks, and each anchor altered makes the adapter fail.
   With --candidate-source the composition must equal the final prepared files.
2. The real NoteGuestMemoryCopy method and its enum are extracted from the adapted DmaClass.cs and
   compiled with doubles (logger, texture): at most 24 signatures are logged once each, the counts
   per reason are logged every 1024 copies, and with the signature set full a copy allocates
   nothing. The whole GPU assembly compiles in the fragmented-reads gate.
"""
import argparse
from pathlib import Path
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('source', type=Path)
parser.add_argument('--candidate-source', type=Path)
args = parser.parse_args()
SOURCE = args.source.resolve()
CANDIDATE = args.candidate_source.resolve() if args.candidate_source else None
DOTNET = os.environ.get('DOTNET', 'dotnet')
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
import adapt_hogwarts_dma_copies as adapter  # noqa: E402

checks = 0


def check(value, message):
    global checks
    assert value, message
    checks += 1


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def compose(target):
    for relative in adapter.NAMES:
        (target / relative).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / relative, target / relative)
    adapter.apply(target)


with tempfile.TemporaryDirectory(prefix='melonx-hogwarts-dma-') as temporary:
    temporary = Path(temporary)
    work = temporary / 'composed'
    compose(work)
    before = {p: (SOURCE / p).read_text(encoding='utf-8-sig') for p in adapter.NAMES}
    after = {p: (work / p).read_text(encoding='utf-8-sig') for p in adapter.NAMES}
    postimages = {p: sha(work / p) for p in adapter.NAMES}
    if CANDIDATE:
        check(postimages == {p: sha(CANDIDATE / p) for p in adapter.NAMES}, 'composition differs from the final prepared source')

    config = after[adapter.CONFIG]
    check(re.search(r'public static bool HogwartsFloatDmaGpuCopy \{ get; set; \}\n', config) is not None,
          'the policy flag exists without an initializer (off by default)')
    check(config.replace(adapter.CONFIG_NEW, adapter.CONFIG_ANCHOR) == before[adapter.CONFIG], 'GraphicsConfig: only the flag added')

    library = after[adapter.LIBRARY]
    init = library[library.index('private static Switch InitializeEmulationContext'):]
    init = init[:init.index('renderer = renderer.TryMakeThreaded(options.BackendThreading);')]
    check('bool hogwarts = EmbeddedIsHogwarts(options.InputPath);' in init and
          'bool querySync = EmbeddedGraphics.OcclusionQuerySync && hogwarts;' in init and
          'Ryujinx.Graphics.Gpu.GraphicsConfig.HogwartsFloatDmaGpuCopy = hogwarts;' in init,
          'the flag is assigned for every session from the launched title, before the renderer is threaded')
    check(library.count('HogwartsFloatDmaGpuCopy') == 1, 'the Library assigns the flag in one place only')
    check(library.replace(adapter.LIBRARY_NEW, adapter.LIBRARY_OLD) == before[adapter.LIBRARY], 'Library: only the policy hunk')

    dma = after[adapter.DMA]
    check('bool floatPolicy = floatFormat && GraphicsConfig.HogwartsFloatDmaGpuCopy && !dstLinear && srcBpp == dstBpp;' in dma and
          'source.Info.FormatInfo.Format is Format.R32G32B32A32Float or Format.R16G16B16A16Float' in dma,
          'only the two float formats depend on the flag, into block-linear destinations of the same element size')
    check('if (source != null && source.Height == yCount && (!floatFormat || floatPolicy))' in dma,
          'the other GPU-copy conditions are unchanged')
    check('floatPolicy ? xCount * srcBpp : xCount,' in dma, 'the policy sizes the target in bytes; other formats as delivered')
    check('if (target == null)' in dma and 'goto GuestMemoryCopy;' in dma and dma.count('GuestMemoryCopy:') == 1,
          'a missing destination falls back to the guest-memory copy')
    slow = dma.index('NoteGuestMemoryCopy(slowReason, slowSource')
    read = dma.index('using ReadOnlyRegion srcRegion = memoryManager.GetReadOnlyRegion(srcGpuVa + (ulong)srcBaseOffset, srcSize, true);')
    check(0 < read - slow < 200, 'the attribution sits immediately before the read through guest memory')
    restored = dma
    for old, new in ((adapter.METHOD_ANCHOR, adapter.METHOD_NEW), (adapter.SLOW_OLD, adapter.SLOW_NEW),
                     (adapter.TARGET_OLD, adapter.TARGET_NEW), (adapter.FAST_OLD, adapter.FAST_NEW),
                     (adapter.USING_OLD, adapter.USING_NEW)):
        restored = restored.replace(new, old)
    check(restored == before[adapter.DMA], 'DmaClass: only the adapter hunks')
    check(dma.count('GraphicsConfig.HogwartsFloatDmaGpuCopy') == 1, 'one use of the policy')
    summary = dma.index('/// Performs a buffer to buffer, or buffer to texture copy.')
    check(dma.index('private void DmaCopy(int argument)') - summary < 200 and
          dma.index('private enum DmaSlowPath') < summary, 'DmaCopy keeps its own documentation')

    # Drift: altering any anchor stops the adapter.
    for relative, anchor in ((adapter.CONFIG, adapter.CONFIG_ANCHOR), (adapter.LIBRARY, adapter.LIBRARY_OLD),
                             (adapter.DMA, adapter.FAST_OLD), (adapter.DMA, adapter.TARGET_OLD), (adapter.DMA, adapter.SLOW_OLD),
                             (adapter.DMA, adapter.METHOD_ANCHOR)):
        drift = temporary / ('drift-' + hashlib.sha256((relative + anchor).encode()).hexdigest()[:8])
        for name in adapter.NAMES:
            (drift / name).parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(SOURCE / name, drift / name)
        text = (drift / relative).read_text(encoding='utf-8-sig')
        indent = len(anchor) - len(anchor.lstrip())
        (drift / relative).write_text(text.replace(anchor, anchor[:indent] + 'Z' + anchor[indent:], 1), encoding='utf-8')
        try:
            adapter.apply(drift)
            check(False, 'drifted anchor accepted: ' + relative)
        except AssertionError as error:
            check('drifted anchor accepted' not in str(error), 'drift detection')

    # The real attribution method, extracted and run with doubles.
    start = dma.index('        /// <summary>\n        /// Why a 2D copy goes through guest memory')
    end = dma.index(adapter.METHOD_ANCHOR)
    method = dma[start:end]
    program = '''using System;
using System.Collections.Generic;
using Ryujinx.Common.Logging;
namespace Ryujinx.Common.Logging
{
    enum LogClass { Gpu }
    sealed class Sink { public readonly List<string> Lines = new(); public void Print(LogClass c, string m) => Lines.Add(m); }
    static class Logger { public static Sink Warning; }
}
namespace Image
{
    enum Format { R8G8B8A8Unorm, R16G16B16A16Float }
    sealed class FormatInfo { public Format Format; }
    sealed class Info { public FormatInfo FormatInfo = new(); public int Width, Height; }
    sealed class Texture { public Info Info = new(); }
}
sealed class Dma
{
''' + method + '''
    public void Run(int reason, Image.Texture source, int x) =>
        NoteGuestMemoryCopy((DmaSlowPath)reason, source, false, true, x, 16, 8, x * 128);
}
static class Program
{
    static void Main()
    {
        var sink = new Sink();
        Logger.Warning = sink;
        var dma = new Dma();
        var texture = new Image.Texture();
        texture.Info.FormatInfo.Format = Image.Format.R16G16B16A16Float;
        texture.Info.Width = 1280; texture.Info.Height = 720;
        // 10 distinct signatures per reason: 8 per reason are logged.
        for (int i = 0; i < 60; i++) dma.Run(i % 6, i % 2 == 0 ? texture : null, 100 + i);
        int signatures = sink.Lines.FindAll(l => l.StartsWith("DMA guest-memory copy #")).Count;
        // 60 + 1989 = 2049 copies: the summaries of 1024 and 2048 are behind; the next one is at 3072.
        for (int i = 0; i < 1989; i++) dma.Run(5, texture, 100);
        long before = GC.GetAllocatedBytesForCurrentThread();
        for (int i = 0; i < 1000; i++) dma.Run(5, texture, 100);
        long allocated = GC.GetAllocatedBytesForCurrentThread() - before;
        int summaries = sink.Lines.FindAll(l => l.StartsWith("DMA guest-memory copies: ")).Count;
        string last = sink.Lines.FindLast(l => l.StartsWith("DMA guest-memory copies: "));
        // Many more copies: the summaries stop at 32 per session.
        for (int i = 0; i < 40000; i++) dma.Run(1, null, 100);
        int capped = sink.Lines.FindAll(l => l.StartsWith("DMA guest-memory copies: ")).Count;
        Console.WriteLine(System.Text.Json.JsonSerializer.Serialize(new { signatures, summaries, allocated, last, capped,
            first = sink.Lines[0] }));
    }
}
'''
    harness = temporary / 'harness'
    harness.mkdir()
    (harness / 'Program.cs').write_text(program)
    (harness / 'harness.csproj').write_text('''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>
<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
<ImplicitUsings>disable</ImplicitUsings><NuGetAudit>false</NuGetAudit><NoWarn>0649;0414</NoWarn>
</PropertyGroup></Project>''')
    (harness / 'global.json').write_text(json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'disable'}}))
    (harness / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    run = subprocess.run([DOTNET, 'run', '--project', str(harness / 'harness.csproj'), '-c', 'Release'], cwd=harness,
                         capture_output=True, text=True, timeout=900, env=environment)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-3000:])
    run.check_returncode()
    result = json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{')))
    check(result['signatures'] == 48, f'8 signatures per reason, each logged once: {result}')
    check(result['capped'] == 32, f'at most 32 summaries per session: {result}')
    check(result['summaries'] == 2 and ' 2048 (' in result['last'], f'a summary every 1024 copies: {result}')
    check(result['allocated'] == 0, f'no allocation per copy once the signature set is full: {result}')
    check('floatFormat ' in result['last'] and 'reason=Incomplete source=R16G16B16A16Float 1280x720' in result['first'],
          f'reasons and source formats are reported: {result}')

inputs = ['build-utils/melonx/adapt_hogwarts_dma_copies.py', 'test/melonx_hogwarts_dma_copies_test.py']
receipt = dict(result='passed', checks=checks, physicalDeviceTested=False, fpsGainProven=False,
               sourceKind='deliveredPreparedWithFinalCandidate' if CANDIDATE else 'deliveredPreparedComposed',
               finalPreparedSourceBound=bool(CANDIDATE), attribution=result,
               inputs={p: sha(ROOT / p) for p in inputs},
               preimages={p: sha(SOURCE / p) for p in adapter.NAMES}, postimages=postimages)
out = ROOT / 'dist/melonx/hogwarts-dma-copies-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, attribution=result), indent=1))
