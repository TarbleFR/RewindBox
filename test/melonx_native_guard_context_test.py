#!/usr/bin/env python3
"""Run the historical dispatch-context checks and the final candidate's bounded PTE retry."""
from pathlib import Path
import shutil
import tempfile
from melonx_native_bounds_probe import ROOT, JIT, TABLE, arguments, report, run

inputs = ['test/melonx_native_guard_context_test.py', 'test/melonx_native_bounds/GuardChecks.cs',
          'test/melonx_guard_context/Program.cs']
args = arguments()
interface = JIT + 'NativeInterface.cs'
text = (args.candidate_source / TABLE).read_text(encoding='utf-8-sig')


def section(begin, end):
    return text[text.index(begin):text.index(end, text.index(begin))]


with tempfile.TemporaryDirectory(prefix='melonx-native-guard-') as temporary:
    work = Path(temporary)
    body = section('        private ulong VirtualMemoryEvent(', '        private void Dispose(')
    contains = section('        internal static bool Contains(', '        private readonly TrackingEventDelegate')
    validate = section('        internal void ValidatePageRange(', '        public void Map(')
    (work / 'Guard.cs').write_text('using System; using Ryujinx.Memory; using LightningJit = Ryujinx.Cpu.LightningJit;\n'
                                  'partial class GuardProbe {\n' + contains + validate + body + '}\n')
    shutil.copyfile(args.candidate_source / interface, work / 'NativeInterface.cs')
    for name in inputs[1:]:
        shutil.copyfile(ROOT / name, work / Path(name).name)
    historical, bounds = run(work, 'GuardChecks')
historical['checks'] += bounds['boundaryChecks']
historical.update(bounds)
report(args, historical, inputs, [TABLE, interface])
