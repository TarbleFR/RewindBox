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

Two input modes, the same regions and scenarios:
- default, adapter text: shells holding upstream's method frames around the exact anchors (reconstructed from the
  anchors: upstream is not read in this mode), the occlusion adapters' texts read from their sources, then the real
  adapters applied (adapt_counter_report_compaction, adapt_queued_syncpoints);
- --source <prepared tree>: the regions extracted from the prepared files (upstream's own frames, every adapter applied).

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
from adapt_occlusion_reports import REPORT  # noqa: E402

THREED = queued.THREED_CLASS
FILES = [queued.GPU_CONTEXT, queued.COUNTER_CACHE, queued.DEFERRED_REPORT, queued.GPFIFO_CLASS, queued.GPFIFO_DEVICE,
         THREED, queued.LIBRARY]
INPUTS = ['test/melonx_queued_syncpoints_fixture_test.py', 'test/melonx_queued_syncpoints/Program.cs',
          'test/melonx_queued_syncpoints/Boundaries.cs', 'build-utils/melonx/adapt_queued_syncpoints.py',
          'build-utils/melonx/adapt_occlusion_reports.py', 'build-utils/melonx/adapt_occlusion_completion.py',
          'build-utils/melonx/adapt_counter_report_compaction.py', 'build-utils/melonx/adapt_performance_diagnostics.py']

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
                _context.CreateHostSyncIfNeeded(HostSyncFlags.StrictSyncpoint);
                _context.Synchronization.IncrementSyncpoint(syncpointId);
            }

            _context.AdvanceSequence();
        }
'''
UPSTREAM_WAIT_LINE = '            return !_commandBufferQueue.IsEmpty || (_event.WaitOne(8) && !_commandBufferQueue.IsEmpty);'
UPSTREAM_WAIT = '        public bool WaitForCommands()\n        {\n' + UPSTREAM_WAIT_LINE + '\n        }\n'
UPSTREAM_INCREMENT = '''        private void IncrementSyncpoint(int argument)
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


def regions(tree):
    """The compiled regions, extracted the same way from shells or from a prepared tree."""
    context = read(tree / queued.GPU_CONTEXT)
    start = context.index('        public bool SynchronizeOcclusionReports { get; set; }')
    end_marker = 'oldest {_oldestQueuedSyncpointMs:F1} ms");\n'
    members = context[start:context.index(end_marker, start) + len(end_marker)]
    for required in ('internal bool FlushCounterReports()', 'internal bool QueueSyncpointBehindReports(uint syncpoint)'):
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
    return {
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
                     + method(read(tree / THREED), 'private void IncrementSyncpoint(') + '    }\n}\n',
        'Library.cs': 'namespace Ryujinx.Graphics.Gpu\n{\n    static class LibraryProbe\n    {\n'
                      '        public static void Assign(bool hogwarts)\n        {\n' + library + '\n        }\n    }\n}\n',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--source', type=Path, help='prepared MeloNX tree (default: adapter-text shells)')
    parser.add_argument('--report', type=Path, default=ROOT / 'dist/melonx/queued-syncpoints-fixture-checks.json')
    args = parser.parse_args()
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
        sources = regions(tree)
        for name, text in sources.items():
            write(project / name, text)
        for name in ('Boundaries.cs', 'Program.cs'):
            shutil.copyfile(FIXTURE / name, project / name)
        write(project / 'Probe.csproj', '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType>'
              '<TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable><ImplicitUsings>disable</ImplicitUsings>'
              '<EnableDefaultCompileItems>false</EnableDefaultCompileItems><TreatWarningsAsErrors>false</TreatWarningsAsErrors>'
              '<NoWarn>CS0169;CS0414;CS0649</NoWarn><NuGetAudit>false</NuGetAudit></PropertyGroup>'
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
    passed = run.returncode == 0 and not outcome['failed']
    report = dict(result='passed' if passed else 'failed', inputMode='preparedSource' if args.source else 'adapterTextShells',
                  sdk=sdk, physicalDeviceTested=False, gameplayTested=False, fpsGainProven=False,
                  checks=outcome['checks'], scenarios=outcome['scenarios'], passed=outcome['passed'], failed=outcome['failed'],
                  compiledSourceInputs=compiled, preparedFiles=prepared,
                  inputs={path: sha((ROOT / path).read_bytes()) for path in INPUTS})
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + '\n')
    for name in outcome['failed']:
        print('FAILED: ' + name)
    print(f"{report['result'].upper()}: {len(outcome['passed'])}/{outcome['scenarios']} scenarios, {outcome['checks']} checks, "
          f"{report['inputMode']}, SDK {sdk}; report {args.report}")
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
