#!/usr/bin/env python3
"""Compiled fixture of the syncpoint increments queued behind their occlusion reports (Hogwarts policy, Core 631).

Compiles with the .NET SDK and executes the C# that adapt_queued_syncpoints writes, with the occlusion members it relies
on (adapt_occlusion_reports, adapt_counter_report_compaction), against the guarantees of the delivered blocking path:
increments in command order, every report published before its increment, GPU syncpoint waits, the 50 ms age bound,
the 3D engine's increments, the renderer barrier before a blocking wait, disposal and invalidated reports, logging and a
concurrent consumer (scenarios in test/melonx_queued_syncpoints/Program.cs).

Compiled regions: GpuContext from SynchronizeOcclusionReports to the queue's log and its Dispose hunk, CounterCache's
pending reports, DeferredCounterReport whole, GPFifoClass.Syncpointb, GPFifoDevice.WaitForCommands,
ThreedClass.IncrementSyncpoint and the Library assignment. Doubles (Boundaries.cs): host sync, threaded renderer,
syncpoint manager, logger, the FIFO's event and the backend counter events.

Final preparation (after IPA 800, adapt_hogwarts_steady_render and adapt_fifo_channel_retirement edit the compiled regions):
under the pacing policy the Library sets for the same title (GpuContext.PaceStrictHostSyncs), the forced sync of an
increment's reports is kept on the open command buffer when a strict submission ran less than 4 ms before, and the queue
submits it after 4 ms or at once before a blocking read. The host sync double therefore follows the production
CreateHostSyncIfNeeded (only a Strict sync submits; the production StrictSyncPacer, compiled whole, for the paced sites;
the two fields the queue reads are noted on a Strict submission), and the paced scenarios (counted apart, receipt field
pacedReportScenarios) execute that path: no report is waited for before its submission ran, order and leases as above.

Two input modes, the same regions and scenarios:
- default, adapter text: shells holding upstream's method frames around the exact anchors (reconstructed from the
  anchors: upstream is not read in this mode), the occlusion adapters' texts read from their sources, then the real
  adapters applied (adapt_counter_report_compaction, adapt_queued_syncpoints);
- --source <prepared tree>: the regions extracted from the prepared files (upstream's own frames, every adapter applied).

DMA Core plan gate queued-3d-syncpoints: <control> --candidate-source <final preparation> runs the --source mode on the
final preparation, after melonx_adapter_control.control_source proved it is the pinned preparation plus
adapt_queued_3d_syncpoints exactly (its replacements reversed give its BASELINE, re-applied give the final bytes). The
control argument is the plan's common one and is not read: the delivered tree has neither queue (adapt_queued_syncpoints
is later), so the scenarios have nothing to run on it. The receipt binds the final post-images of the compiled files
(dist/melonx/queued-3d-syncpoints-checks.json).

No Vulkan, GPU, iPhone or FPS claim.
"""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
ADAPTERS = ROOT / 'build-utils/melonx'
FIXTURE = ROOT / 'test/melonx_queued_syncpoints'
sys.path.insert(0, str(ADAPTERS))
sys.dont_write_bytecode = True
import adapt_counter_report_compaction as compaction  # noqa: E402
import adapt_queued_syncpoints as queued  # noqa: E402
import adapt_queued_3d_syncpoints as queued_3d  # noqa: E402
from adapt_occlusion_reports import REPORT  # noqa: E402

THREED = queued.THREED_CLASS
FILES = [queued.GPU_CONTEXT, queued.COUNTER_CACHE, queued.DEFERRED_REPORT, queued.GPFIFO_CLASS, queued.GPFIFO_DEVICE,
         THREED, queued.LIBRARY, queued_3d.SEMAPHORE]
INPUTS = ['test/melonx_queued_syncpoints_fixture_test.py', 'test/melonx_queued_syncpoints/Program.cs',
          'test/melonx_queued_syncpoints/Boundaries.cs', 'build-utils/melonx/adapt_queued_syncpoints.py',
          'build-utils/melonx/adapt_occlusion_reports.py', 'build-utils/melonx/adapt_occlusion_completion.py',
          'build-utils/melonx/adapt_counter_report_compaction.py', 'build-utils/melonx/adapt_performance_diagnostics.py',
          'build-utils/melonx/adapt_queued_3d_syncpoints.py', 'test/melonx_adapter_control.py']

# Upstream frames around the anchors (adapter-text mode only). The anchors inside them are the adapters' own texts.
UPSTREAM_SYNCPOINTB = '''        public void Syncpointb(int argument)
        {
            SyncpointbOperation operation = _state.State.SyncpointbOperation;

            uint syncpointId = (uint)_state.State.SyncpointbSyncptIndex;

            if (operation == SyncpointbOperation.Wait)
            {
                uint threshold = (uint)_state.State.SyncpointaPayload;

                _context.Synchronization.WaitOnSyncpoint(syncpointId, threshold, Timeout.InfiniteTimeSpan);
            }
            else if (operation == SyncpointbOperation.Incr)
            {
                // "Unbind" render targets since a syncpoint increment might indicate future CPU access for the textures.
                _parent.TextureManager.RefreshModifiedTextures();

                _context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);
                _context.Synchronization.IncrementSyncpoint(syncpointId);
            }

            _context.AdvanceSequence();
        }
'''
UPSTREAM_WAIT_LINE = '            return !_commandBufferQueue.IsEmpty || (_event.WaitOne(8) && !_commandBufferQueue.IsEmpty);'
UPSTREAM_WAIT = '        public bool WaitForCommands()\n        {\n' + UPSTREAM_WAIT_LINE + '\n        }\n'
UPSTREAM_INCREMENT = '''        public void IncrementSyncpoint(int argument)
        {
            uint syncpointId = (uint)argument & 0xFFFF;

            _context.AdvanceSequence();
            _context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);
            _context.Renderer.UpdateCounters(); // Poll the query counters, the game may want an updated result.
            _context.Synchronization.IncrementSyncpoint(syncpointId);
        }
'''


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return Path(path).read_text(encoding='utf-8-sig')


def once(text, old, new):
    if text.count(old) != 1:
        raise SystemExit('fixture: anchor not found exactly once: ' + old[:70])
    return text.replace(old, new)


def adapter_literal(module, function, anchor):
    """The replacement that a `function(path, anchor, replacement)` call of an adapter writes, read from its source."""
    tree = ast.parse((ADAPTERS / module).read_text(encoding='utf-8'))
    found = [node.args[2].value for node in ast.walk(tree)
             if isinstance(node, ast.Call) and getattr(node.func, 'id', None) == function and len(node.args) >= 3
             and isinstance(node.args[1], ast.Constant) and node.args[1].value == anchor
             and isinstance(node.args[2], ast.Constant)]
    if len(found) != 1:
        raise SystemExit(f'fixture: {module} has {len(found)} {function}() calls on anchor {anchor[:60]!r}')
    return found[0]


def adapter_pair(module, key):
    """The (old, new) pair a dictionary of an adapter holds for one file, read from its source."""
    tree = ast.parse((ADAPTERS / module).read_text(encoding='utf-8'))
    found = [tuple(element.value for element in value.elts) for node in ast.walk(tree) if isinstance(node, ast.Dict)
             for name, value in zip(node.keys, node.values)
             if isinstance(name, ast.Constant) and name.value == key and isinstance(value, ast.Tuple)]
    if len(found) != 1:
        raise SystemExit(f'fixture: {module} has {len(found)} entries for {key}')
    return found[0]


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def shells(tree):
    """Pre-adapter shells: upstream frames, the earlier adapters' texts, then the real adapters of the queue applied."""
    context = '''using System;
using System.Collections.Generic;
using Ryujinx.Graphics.Gpu.Memory;

namespace Ryujinx.Graphics.Gpu
{
    public partial class GpuContext
    {
        private bool _pendingSync;

        public void Dispose()
        {
            GPFifo.Dispose();
        }
    }
}
'''
    for anchor in ('        private bool _pendingSync;', '            GPFifo.Dispose();'):
        context = once(context, anchor, adapter_literal('adapt_occlusion_reports.py', 'change', anchor))
    write(tree / queued.GPU_CONTEXT, context)
    items = '        private readonly List<CounterEntry> _items;'
    cache = ('using System.Collections.Generic;\n\nnamespace Ryujinx.Graphics.Gpu.Memory\n{\n    partial class CounterCache\n    {\n'
             + items + '\n    }\n}\n')
    write(tree / queued.COUNTER_CACHE, once(cache, items, adapter_literal('adapt_occlusion_reports.py', 'change', items)))
    write(tree / queued.DEFERRED_REPORT, REPORT)
    increment = ('                _context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);\n'
                 '                _context.Synchronization.IncrementSyncpoint(syncpointId);')
    syncpointb = once(UPSTREAM_SYNCPOINTB, increment, adapter_literal('adapt_occlusion_reports.py', 'change', increment))
    write(tree / queued.GPFIFO_CLASS, 'namespace Ryujinx.Graphics.Gpu.Engine.GPFifo\n{\n    class GPFifoClass\n    {\n'
          + syncpointb + '    }\n}\n')
    wait = once(UPSTREAM_WAIT, UPSTREAM_WAIT_LINE, adapter_literal('adapt_performance_diagnostics.py', 'once', UPSTREAM_WAIT_LINE))
    write(tree / queued.GPFIFO_DEVICE, 'namespace Ryujinx.Graphics.Gpu.Engine.GPFifo\n{\n    class GPFifoDevice\n    {\n'
          + wait + '    }\n}\n')
    old, new = adapter_pair('adapt_occlusion_completion.py', THREED)
    write(tree / THREED, 'namespace Ryujinx.Graphics.Gpu.Engine.Threed\n{\n    class ThreedClass\n    {\n'
          + once(UPSTREAM_INCREMENT, old, new) + '    }\n}\n')
    write(tree / queued.LIBRARY, 'namespace Ryujinx.Headless\n{\n    public static class Library\n    {\n'
          '        private static void ApplyPolicies(bool hogwarts)\n        {\n'
          '            Ryujinx.Graphics.Vulkan.EncodingPolicy.IncrementalArrayDescriptors = hogwarts;\n        }\n    }\n}\n')
    compaction.apply(tree)
    queued.apply(tree)
    # adapt_queued_3d_syncpoints on the shells that hold its anchors (the 3D increment, the queue, the report); its
    # CounterCache, GPFifoDevice and SemaphoreUpdater parts are compiled from a prepared tree only (--source).
    for relative, old, new in queued_3d.PAIRS:
        if relative in (queued_3d.THREED, queued_3d.CONTEXT, queued_3d.REPORT):
            write(tree / relative, once(read(tree / relative), old, new))


def method(text, signature):
    """One whole method, from the start of its signature's line to its closing brace."""
    if text.count(signature) != 1:
        raise SystemExit('fixture: method not found exactly once: ' + signature)
    at = text.index(signature)
    start = text.rindex('\n', 0, at) + 1
    i = text.index('{', at) + 1
    depth = 1
    while depth:
        depth += {'{': 1, '}': -1}.get(text[i], 0)
        i += 1
    return text[start:i] + '\n'


def hunk(relative, index):
    return queued.HUNKS[relative][index][1]


def regions(tree, prepared=False):
    """The compiled regions, extracted the same way from shells or from a prepared tree."""
    context = read(tree / queued.GPU_CONTEXT)
    start = context.index('        public bool SynchronizeOcclusionReports { get; set; }')
    end_marker = 'oldest {_oldestQueuedSyncpointMs:F1} ms");\n'
    members = context[start:context.index(end_marker, start) + len(end_marker)]
    for required in ('internal bool FlushCounterReports()', 'internal bool QueueSyncpointBehindReports(uint syncpoint, '):
        if members.count(required) != 1:
            raise SystemExit('fixture: GpuContext region lacks ' + required)
    dispose = hunk(queued.GPU_CONTEXT, 1)
    if context.count(dispose) != 1:
        raise SystemExit('fixture: GpuContext disposal hunk not found exactly once')
    cache = read(tree / queued.COUNTER_CACHE)
    cancel = method(cache, 'internal void CancelPendingReports()')
    cache_start = cache.index('        private readonly object _gate = new();')
    pending = cache[cache_start:cache.index(cancel, cache_start) + len(cancel)]
    library = hunk(queued.LIBRARY, 0)
    if read(tree / queued.LIBRARY).count(library) != 1:
        raise SystemExit('fixture: Library assignment not found exactly once')
    sources = {
        'Context.cs': 'using System;\nusing System.Collections.Generic;\nusing Ryujinx.Graphics.Gpu.Memory;\n\n'
                      'namespace Ryujinx.Graphics.Gpu\n{\n    public partial class GpuContext\n    {\n' + members +
                      '\n        public void Dispose()\n        {\n' + dispose + '\n        }\n    }\n}\n',
        'Cache.cs': 'using System.Collections.Generic;\nusing PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n\n'
                    'namespace Ryujinx.Graphics.Gpu.Memory\n{\n    partial class CounterCache\n    {\n' + pending + '    }\n}\n',
        'DeferredCounterReport.cs': read(tree / queued.DEFERRED_REPORT),
        'FifoClass.cs': 'using System;\nusing System.Threading;\n\nnamespace Ryujinx.Graphics.Gpu\n{\n    partial class FifoClassProbe\n    {\n'
                        + method(read(tree / queued.GPFIFO_CLASS), 'public void Syncpointb(') + '    }\n}\n',
        'FifoDevice.cs': 'using System;\nusing PD = Ryujinx.Common.EmbeddedPerformanceDiagnostics;\n\n'
                         'namespace Ryujinx.Graphics.Gpu\n{\n    partial class FifoDeviceProbe\n    {\n'
                         + method(read(tree / queued.GPFIFO_DEVICE), 'public bool WaitForCommands(') + '    }\n}\n',
        'Threed.cs': 'using System;\n\nnamespace Ryujinx.Graphics.Gpu\n{\n    partial class ThreedProbe\n    {\n'
                     + method(read(tree / THREED), 'public void IncrementSyncpoint(') + '    }\n}\n',
        'Library.cs': 'namespace Ryujinx.Graphics.Gpu\n{\n    static class LibraryProbe\n    {\n'
                      '        public static void Assign(bool hogwarts)\n        {\n' + library + '\n        }\n    }\n}\n',
    }
    if prepared:
        # The whole CounterCache (AddOrUpdate, BinarySearch, HasQueuedReportAt), the report guard of
        # SemaphoreUpdater.ReportCounter and the block GPFifoDevice runs after each GPFIFO entry (adapt_queued_3d_syncpoints).
        sources['Cache.cs'] = once(cache, '    class CounterCache\n', '    partial class CounterCache\n')
        sources['Guard.cs'] = guard_region(tree)
        # The production pacer (adapt_paced_strict_syncs), whole, when the prepared GpuContext.cs has one: the host sync
        # double runs it for the paced sites, as the production CreateHostSyncIfNeeded does.
        if PACER in context:
            sources['Pacer.cs'] = 'namespace Ryujinx.Graphics.Gpu\n{\n' + context[context.index(PACER):context.rindex('}')] + '}\n'
    return sources


PACER = '    internal struct StrictSyncPacer'
# adapt_hogwarts_steady_render's report submissions under the pacing policy (the final preparation): the queue keeps a
# report sync on the open command buffer within 4 ms of a strict submission and submits it itself later.
DEFERRED = '        private void SubmitDeferredReports(bool demanded)'


def defines(sources):
    """Compilation symbols: the prepared regions, the production pacer and the deferred report submissions they hold."""
    symbols = ['PREPARED_SOURCE']
    if 'Pacer.cs' in sources:
        symbols.append('STRICT_SYNC_PACER')
    if DEFERRED in sources['Context.cs']:
        if 'Pacer.cs' not in sources or sources['Context.cs'].count(DEFERRED) != 1:
            raise SystemExit('fixture: deferred report submissions without the pacing policy they belong to')
        symbols.append('DEFERRED_REPORT_SUBMISSIONS')
    return symbols


def guard_region(tree):
    """adapt_queued_3d_syncpoints' report guard and per-entry block, from the prepared files, in two probes."""
    semaphore = read(tree / queued_3d.SEMAPHORE)
    start = semaphore.index('            if (_context.HasQueuedSyncpoints && _channel.MemoryManager.CounterCache.HasQueuedReportAt(gpuVa))')
    end = semaphore.index('            if (_context.SynchronizeOcclusionReports && type == ReportCounterType.SamplesPassed)', start)
    device = read(tree / queued.GPFIFO_DEVICE)
    block = device.index('                    if (_context.HasQueuedSyncpoints)\n')
    block_end = device.index('                }\n                finally', block)
    return ('using System;\nusing Ryujinx.Graphics.Gpu.Memory;\n\nnamespace Ryujinx.Graphics.Gpu\n{\n    partial class ReportProbe\n    {\n'
            '        public void ReportCounter(ulong gpuVa, DeferredCounterReport report)\n        {\n' + semaphore[start:end] +
            '            _channel.MemoryManager.CounterCache.AddOrUpdate(gpuVa, report);\n'
            '            _context.TrackCounterReports(_channel.MemoryManager.CounterCache);\n        }\n    }\n\n'
            '    partial class EntryProbe\n    {\n        public void AfterEntry()\n        {\n' + device[block:block_end] +
            '        }\n    }\n}\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('control', type=Path, nargs='?', help='plan gate: the control tree (not read)')
    parser.add_argument('--source', type=Path, help='prepared MeloNX tree (default: adapter-text shells)')
    parser.add_argument('--candidate-source', type=Path, help='plan gate: the final preparation (adapt_queued_3d_syncpoints applied)')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    gate = args.candidate_source is not None
    if gate:
        if args.source:
            raise SystemExit('fixture: --source and --candidate-source are exclusive')
        sys.path.insert(0, str(ROOT / 'test'))
        from melonx_adapter_control import control_source
        holder = []
        args.source = args.candidate_source.resolve()
        _, bound = control_source(args.source, 'adapt_queued_3d_syncpoints', holder)
        for temporary in holder:
            temporary.cleanup()
        if not bound:
            raise SystemExit('fixture: the candidate is not a final preparation containing adapt_queued_3d_syncpoints')
    if args.report is None:
        args.report = ROOT / ('dist/melonx/queued-3d-syncpoints-checks.json' if gate else 'dist/melonx/queued-syncpoints-fixture-checks.json')
    dotnet = os.environ.get('DOTNET', 'dotnet')
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
    with tempfile.TemporaryDirectory(prefix='melonx-queued-syncpoints-') as temporary:
        work = Path(temporary)
        if args.source:
            tree = args.source.resolve()
            prepared = {relative: sha((tree / relative).read_bytes()) for relative in FILES}
        else:
            tree = work / 'shells'
            shells(tree)
            prepared = None
        project = work / 'probe'
        sources = regions(tree, prepared=bool(args.source))
        symbols = defines(sources) if args.source else []
        if gate and 'DEFERRED_REPORT_SUBMISSIONS' not in symbols:
            raise SystemExit('fixture: the final preparation lacks the deferred report submissions this gate executes')
        for name, text in sources.items():
            write(project / name, text)
        for name in ('Boundaries.cs', 'Program.cs'):
            shutil.copyfile(FIXTURE / name, project / name)
        write(project / 'Probe.csproj', '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
              '<TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable><ImplicitUsings>disable</ImplicitUsings>'
              '<EnableDefaultCompileItems>false</EnableDefaultCompileItems><TreatWarningsAsErrors>false</TreatWarningsAsErrors>'
              '<NoWarn>CS0169;CS0414;CS0649</NoWarn><NuGetAudit>false</NuGetAudit>'
              + ('<DefineConstants>' + ';'.join(symbols) + '</DefineConstants>' if symbols else '') + '</PropertyGroup>'
              '<ItemGroup><Compile Include="*.cs" /></ItemGroup></Project>')
        # The gates' SDK is 10.0.100; a later patch of the same band is accepted and recorded.
        write(project / 'global.json', json.dumps({'sdk': {'version': '10.0.100', 'rollForward': 'latestPatch'}}))
        write(project / 'NuGet.Config', '<configuration><packageSources><clear /></packageSources></configuration>')
        sdk = subprocess.run([dotnet, '--version'], cwd=project, env=environment, text=True, capture_output=True, check=True).stdout.strip()
        build = subprocess.run([dotnet, 'build', str(project), '-c', 'Release', '-nologo'], cwd=project, env=environment,
                               text=True, capture_output=True, timeout=900)
        if build.returncode:
            print(build.stdout[-8000:], build.stderr[-4000:])
            raise SystemExit('fixture: the compiled regions do not build')
        run = subprocess.run([dotnet, str(project / 'bin/Release/net10.0/Probe.dll')], cwd=project, env=environment,
                             text=True, capture_output=True, timeout=600)
        lines = [line for line in run.stdout.splitlines() if line.startswith('{')]
        if not lines:
            print(run.stdout[-4000:], run.stderr[-4000:])
            raise SystemExit('fixture: no result')
        outcome = json.loads(lines[-1])
        compiled = {name: sha((project / name).read_bytes()) for name in sorted(sources) + ['Boundaries.cs', 'Program.cs']}
    paced = outcome.get('pacedScenarios', 0)
    passed = (run.returncode == 0 and not outcome['failed'] and len(outcome['passed']) == outcome['scenarios'] + paced and
              (paced > 0) == ('DEFERRED_REPORT_SUBMISSIONS' in symbols))
    report = dict(result='passed' if passed else 'failed', inputMode='preparedSource' if args.source else 'adapterTextShells',
                  sdk=sdk, physicalDeviceTested=False, gameplayTested=False, fpsGainProven=False,
                  checks=outcome['checks'], scenarios=outcome['scenarios'], passed=outcome['passed'], failed=outcome['failed'],
                  pacedReportScenarios=paced, compilationSymbols=symbols,
                  compiledSourceInputs=compiled, preparedFiles=prepared,
                  inputs={path: sha((ROOT / path).read_bytes()) for path in INPUTS})
    if gate:
        # Plan gate: the compiled files are the final preparation's (control_source reproduced them from the pinned
        # preparation plus adapt_queued_3d_syncpoints); the guarantee is executed on them, not only compiled.
        report.update(finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl', postimages=prepared,
                      limitation='Compiled regions of the final preparation with doubles for the host sync, the renderer, '
                                 'the syncpoint manager and the counter events; no Vulkan, GPU thread of a real title or '
                                 'device. Whether Hogwarts Legacy waits less on its occlusion reports is known only from a '
                                 'device run.')
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    for name in outcome['failed']:
        print('FAILED: ' + name)
    print(f"{report['result'].upper()}: {len(outcome['passed'])}/{outcome['scenarios']} + {paced} paced scenarios, {outcome['checks']} checks, "
          f"{report['inputMode']}, SDK {sdk}; report {args.report}")
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
