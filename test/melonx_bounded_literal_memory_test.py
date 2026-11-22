#!/usr/bin/env python3
"""Check literal lowering and bounded tracked translations with the final production ARM64 emitter."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from melonx_native_bounds_probe import ROOT, JIT, TABLE, EMITTER, PIN, arguments, report, run

inputs = ['test/melonx_bounded_literal_memory_test.py', 'test/melonx_native_bounds/LiteralChecks.cs',
          'test/melonx_literal_memory/Program.cs']
args = arguments()
pin = json.loads((ROOT / PIN).read_text())
raw_sha = '3e2cab1b9197d3d8fca9c4fd7c857b683150ea4ba7efeaf0433ff393b2dff483'
original = (args.source / EMITTER).read_bytes()
if hashlib.sha256(original).hexdigest() != raw_sha:
    for tree in [args.source, ROOT / '.native-sources/MeloNX', args.candidate_source]:
        if (tree / '.git').exists():
            original = subprocess.check_output(['git', '-C', str(tree), 'show', pin['revision'] + ':' + EMITTER])
            break
if hashlib.sha256(original).hexdigest() != raw_sha:
    raise ValueError('Missing pinned upstream emitter for literal controls')

compiled = [JIT + name + '.cs' for name in ['CodeWriter', 'AddressForm', 'Arm64/InstName', 'Arm64/InstFlags']]
compiled.extend(JIT + 'CodeGen/' + name + '.cs' for name in ['Operand', 'OperandKind', 'OperandType', 'Register', 'RegisterType'])
compiled.extend(JIT + 'CodeGen/Arm64/' + name + '.cs' for name in ['Assembler', 'ArmCondition', 'ArmExtensionType', 'ArmShiftType', 'CodeGenCommon'])
with tempfile.TemporaryDirectory(prefix='melonx-bounded-literal-') as temporary:
    work = Path(temporary)
    for name in [*compiled, EMITTER]:
        shutil.copyfile(args.candidate_source / name, work / Path(name).name)
    for name in inputs[1:]:
        shutil.copyfile(ROOT / name, work / Path(name).name)
    # Only rename the unadapted class to compile it beside the unchanged final emitter.
    old = original.decode('utf-8-sig')
    assert old.count('static class InstEmitMemory') == 1
    (work / 'OriginalEmitter.cs').write_text(old.replace('static class InstEmitMemory', 'static class OriginalEmitter'))
    guard = (args.candidate_source / TABLE).read_text(encoding='utf-8-sig')
    start = guard.index('        internal static ulong GuardOffset(')
    end = guard.index(';', start) + 1
    (work / 'GuardOffset.cs').write_text('using System; namespace Ryujinx.Cpu.Jit.HostTracked {\n'
        'internal static class NativePageTable {\n' + guard[start:end] + '\n} }\n')
    historical, bounds = run(work, 'LiteralChecks')
historical['checks'] += bounds['boundaryChecks']
historical.update(bounds, upstreamRevision=pin['revision'], upstreamEmitterSha256=raw_sha)
report(args, historical, inputs, [EMITTER, TABLE], compiled)
