#!/usr/bin/env python3
"""Production Auto ownership (core87 auto-ownership proof) on the final command-buffer ownership, against the delivered one.

Usage: melonx_auto_ownership_final_test.py <delivered control tree> --candidate-source <final preparation>

The historical receipt auto-ownership-checks.json (core87, test/melonx_auto_ownership_test.py) proved the complete
production Auto, its ownership bitmaps and CommandBufferScoped against a doubled command transport. The IPA 740 lot
(adapt_command_buffer_ownership, then adapt_signalled_fence_release on CommandBufferPool.cs) changes Auto.cs and
CommandBufferPool.cs: the objects an Auto references get only their command-buffer bit and their waitable
(AddCommandBufferOwnership), cleared (ClearCommandBufferOwnership) before the owner's release, and the dependants are
stored as struct DependantEntry. This gate reruns that proof on the final source, with one fixture for both variants
(test/melonx_auto_ownership_final, FINAL defined for the candidate):
- control: Auto.cs and CommandBufferPool.cs of the delivered tree (Core da2525a1);
- candidate: the same two files of the final preparation;
- both: BitMap.cs, BitMapStruct.cs, CommandBufferScoped.cs, IArray.cs and StructArrayHelpers.cs of the final preparation
  (byte-identical to the delivered ones), Auto.cs compiled whole; from the variant's CommandBufferPool.cs, AddDependant,
  the dependant release loop of WaitAndDecrementRef and (candidate) the DependantEntry struct are inserted verbatim.
Static: the final preparation is the delivered tree plus adapt_command_buffer_ownership and adapt_signalled_fence_release
in these files (melonx_adapter_control.control_source, each replacement once, the control exactly the final with them
undone). Executed: every historical scenario, plus the diamond (root.Get, and the leaf used first), and a child disposed
by its user while in flight through its parent: identical bits, waitables and lifetimes in both variants; only the
dependants per slot differ, as documented (DEPENDANTS). No Vulkan driver, no device; no FPS claim.
Writes dist/melonx/auto-ownership-checks.json.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
import adapt_command_buffer_ownership as ownership  # noqa: E402
import adapt_signalled_fence_release as signalled  # noqa: E402
from melonx_adapter_control import _NoDigests, control_source, files_edited_later, later_sharing  # noqa: E402

MODULE = 'adapt_command_buffer_ownership'
AUTO, POOL = ownership.AUTO, ownership.POOL
SHARED = ('src/Ryujinx.Graphics.Vulkan/BitMap.cs', 'src/Ryujinx.Graphics.Vulkan/BitMapStruct.cs',
          'src/Ryujinx.Graphics.Vulkan/CommandBufferScoped.cs', 'src/Ryujinx.Common/Memory/IArray.cs',
          'src/Ryujinx.Common/Memory/StructArrayHelpers.cs')
FIXTURE = ROOT / 'test/melonx_auto_ownership_final'
BOM = b'\xef\xbb\xbf'
SCENARIOS = ['slotsAndDisposal', 'dependencyGraph', 'mirrorAndUses', 'concurrentReferenceCounts', 'diamondDisposedInFlight',
             'diamondDisposedAfterCompletion', 'diamondLeafFirstDisposedInFlight', 'diamondLeafFirstDisposedAfterCompletion',
             'childDisposedInFlight']
# Dependants per command-buffer slot. Control: every object of a reference chain is a dependant of its own. Final: only
# the objects used directly; the diamond's left, right and leaf get their bit through root (1), the leaf used directly
# before root stays a dependant (2), a child used only through its parent has its bit (1). Unchanged without references.
DEPENDANTS = {
    'control': {'slotsAndDisposal': 1, 'dependencyGraph': 4, 'mirrorAndUses': 2, 'diamond': 5, 'diamondLeafFirst': 5,
                'childThroughParent': 3},
    'final': {'slotsAndDisposal': 1, 'dependencyGraph': 1, 'mirrorAndUses': 2, 'diamond': 1, 'diamondLeafFirst': 2,
              'childThroughParent': 1},
}
WAITABLES = {'dependencyGraph': 1, 'mirrorAndUses': 2, 'diamond': 1, 'diamondLeafFirst': 1, 'childThroughParent': 1}
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text_sha(text):
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def method(text, signature):
    """The member starting at `signature` (once in `text`) through its closing brace, as the historical runner extracts."""
    check(text.count(signature) == 1, 'one ' + signature.strip())
    start = text.index(signature)
    index = text.index('{', start)
    depth = 1
    end = index + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def release_loop(pool_text):
    """The loop of WaitAndDecrementRef that releases the slot's dependants, verbatim (its lines, closing brace included)."""
    wait = method(pool_text, '        private void WaitAndDecrementRef(')
    lines = wait.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.lstrip().startswith('foreach (') and line.rstrip().endswith(' in entry.Dependants)')]
    check(len(starts) == 1, 'one dependant release loop in WaitAndDecrementRef')
    indent = lines[starts[0]][:len(lines[starts[0]]) - len(lines[starts[0]].lstrip())]
    end = next(i for i in range(starts[0] + 1, len(lines)) if lines[i] == indent + '}\n')
    return ''.join(lines[starts[0]:end + 1])


def production_parts(pool_text, final):
    """What the fixture's pool double takes verbatim from the variant's production CommandBufferPool.cs."""
    parts = {'addDependant': method(pool_text, '        public void AddDependant(int cbIndex, IAuto dependant)'),
             'releaseLoop': release_loop(pool_text)}
    if final:
        parts['dependantEntry'] = method(pool_text, '        private readonly struct DependantEntry')
        check(parts['dependantEntry'] + '\n' in ownership.ENTRY_NEW, 'the final DependantEntry is the adapter\'s')
        check(ownership.ADD_NEW in parts['addDependant'] and parts['releaseLoop'] == ownership.LOOP_NEW,
              'the final AddDependant and release loop store and release DependantEntry')
    else:
        check('DependantEntry' not in pool_text, 'the delivered pool has no DependantEntry')
        check(ownership.ADD_OLD in parts['addDependant'] and parts['releaseLoop'] == ownership.LOOP_OLD,
              'the delivered AddDependant and release loop store and release IAuto')
    return parts


def replacements(module):
    """The (file, old, new) replacements module.apply makes, in its order, recorded instead of applied."""
    recorded = []
    original, baseline = module.once, module.BASELINE
    anchor = Path('/nonexistent-melonx-tree')
    module.once = lambda path, old, new: recorded.append((path.relative_to(anchor).as_posix(), old, new))
    module.BASELINE = _NoDigests(baseline)
    try:
        module.apply(anchor)
    finally:
        module.once, module.BASELINE = original, baseline
    return recorded


def undo(text, pairs, label):
    for _, old, new in reversed(pairs):
        check(text.count(new) == 1, label + ': replacement present once: ' + new.strip().splitlines()[0][:80])
        text = text.replace(new, old)
    return text


def same_bytes(raw, text):
    return raw in (text.encode('utf-8'), BOM + text.encode('utf-8'))


def run_variant(work, variant, auto_text, pool_text, shared):
    """Build and run the fixture for one variant ('control' or 'final') in `work`; return (report, compiled, extracted).

    `auto_text` is the Auto.cs compiled whole, `pool_text` the CommandBufferPool.cs the double takes its parts from,
    `shared` {relative path: bytes} the other production sources. A failing scenario raises CalledProcessError."""
    final = variant == 'final'
    work.mkdir(parents=True, exist_ok=True)
    for relative, raw in shared.items():
        (work / relative).parent.mkdir(parents=True, exist_ok=True)
        (work / relative).write_bytes(raw)
    (work / AUTO).parent.mkdir(parents=True, exist_ok=True)
    (work / AUTO).write_text(auto_text, encoding='utf-8')
    parts = production_parts(pool_text, final)
    program = (FIXTURE / 'Program.cs').read_text(encoding='utf-8')
    boundaries = (FIXTURE / 'Boundaries.cs').read_text(encoding='utf-8')
    for marker in ('        /* PRODUCTION_ADD_DEPENDANT */', '/* PRODUCTION_RELEASE_LOOP */\n',
                   '        /* PRODUCTION_DEPENDANT_ENTRY */'):
        check(boundaries.count(marker) == 1, 'one insertion point ' + marker.strip())
    boundaries = boundaries.replace('        /* PRODUCTION_ADD_DEPENDANT */', parts['addDependant'])
    boundaries = boundaries.replace('/* PRODUCTION_RELEASE_LOOP */\n', parts['releaseLoop'])
    boundaries = boundaries.replace('        /* PRODUCTION_DEPENDANT_ENTRY */', parts.get('dependantEntry', ''))
    (work / 'Program.cs').write_text(program, encoding='utf-8')
    (work / 'Boundaries.cs').write_text(boundaries, encoding='utf-8')
    sources = [*SHARED, AUTO, 'Program.cs', 'Boundaries.cs']
    compiled = {p: sha(work / p) for p in sources}
    includes = ''.join(f'<Compile Include="{p}" />' for p in sources)
    defines = '<DefineConstants>$(DefineConstants);FINAL</DefineConstants>' if final else ''
    (work / 'Probe.csproj').write_text('<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup>'
        '<OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<AllowUnsafeBlocks>true</AllowUnsafeBlocks><Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit>'
        '<EnableDefaultCompileItems>false</EnableDefaultCompileItems>' + defines +
        '</PropertyGroup><ItemGroup>' + includes + '</ItemGroup></Project>')
    pin = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())
    (work / 'global.json').write_text(json.dumps({'sdk': {'version': pin['dotnet'], 'rollForward': 'disable'}}))
    (work / 'NuGet.Config').write_text('<configuration><packageSources><clear /></packageSources></configuration>')
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    build = subprocess.run([DOTNET, 'build', 'Probe.csproj', '-c', 'Release', '--nologo', '-v', 'quiet'], cwd=work,
                           text=True, capture_output=True, timeout=600, env=environment)
    if build.returncode:
        print(build.stdout[-6000:], build.stderr[-3000:], flush=True)
    build.check_returncode()
    result = subprocess.run([DOTNET, 'bin/Release/net10.0/Probe.dll'], cwd=work, text=True, capture_output=True,
                            timeout=600, env=environment)
    if result.returncode:
        print(variant, 'fixture failed:', result.stderr.strip().splitlines()[:3], flush=True)
    result.check_returncode()
    report = json.loads(result.stdout.strip().splitlines()[-1])
    extracted = {name: text_sha(value) for name, value in parts.items()}
    return report, compiled, extracted


def main():
    check('--candidate-source' in sys.argv and len(sys.argv) == 4, 'usage: <delivered control> --candidate-source <final preparation>')
    control = Path(sys.argv[1]).resolve()
    final_source = Path(sys.argv[sys.argv.index('--candidate-source') + 1]).resolve()
    hold = []

    # --- static: the final preparation is the delivered files plus this adapter and the later one sharing the pool ---
    later = later_sharing(MODULE)
    check(later == ['adapt_signalled_fence_release'] and files_edited_later(MODULE) == {POOL},
          'adapt_signalled_fence_release is the only later adapter editing these files, CommandBufferPool.cs only')
    prepared, final_bound = control_source(final_source, MODULE, hold)
    check(final_bound, 'the candidate is the final preparation (it contains adapt_command_buffer_ownership)')
    for name in (AUTO, POOL):
        check(sha(control / name) == ownership.BASELINE[name] == sha(prepared / name),
              'the delivered file is the preparation the adapter pins: ' + name)
    own_pairs = replacements(ownership)
    check(own_pairs == [(name, old, new) for name, old, new in ownership.PAIRS], 'the adapter applies exactly its PAIRS')
    later_pairs = replacements(signalled)
    check(len(later_pairs) == 2 and all(name == POOL for name, _, _ in later_pairs), 'the later adapter edits the pool twice')
    final_auto = (final_source / AUTO).read_text(encoding='utf-8-sig')
    final_pool = (final_source / POOL).read_text(encoding='utf-8-sig')
    for name, _, new in own_pairs + later_pairs:
        check((final_auto if name == AUTO else final_pool).count(new) == 1, 'final replacement once: ' + name + ': ' +
              new.strip().splitlines()[0][:80])
    control_auto = undo(final_auto, [p for p in own_pairs if p[0] == AUTO], AUTO)
    control_pool = undo(undo(final_pool, later_pairs, POOL), [p for p in own_pairs if p[0] == POOL], POOL)
    check(same_bytes((control / AUTO).read_bytes(), control_auto), 'the delivered Auto.cs is the final one with the replacements undone')
    check(same_bytes((control / POOL).read_bytes(), control_pool),
          'the delivered CommandBufferPool.cs is the final one with both adapters\' replacements undone')
    for relative in SHARED:
        check((control / relative).read_bytes() == (final_source / relative).read_bytes(), 'unchanged shared source: ' + relative)
    # The adapter's own premises, on the final Vulkan backend: Auto<T> the only IAutoPrivate, WaitAndDecrementRef the
    # only caller of DecrementReferenceCount(cbIndex), ReservedCommandBuffer.Dependants read nowhere else.
    for path in sorted((final_source / 'src/Ryujinx.Graphics.Vulkan').rglob('*.cs')):
        text = path.read_text(encoding='utf-8-sig')
        if path.name != 'Auto.cs':
            check('IAutoPrivate' not in text, 'IAutoPrivate outside Auto.cs: ' + path.name)
            check('DecrementReferenceCount(cbIndex)' not in text or path.name == 'CommandBufferPool.cs',
                  'DecrementReferenceCount(cbIndex) outside the pool: ' + path.name)
        if path.name != 'CommandBufferPool.cs':
            check('.Dependants' not in text, '.Dependants outside the pool: ' + path.name)
    shared = {relative: (final_source / relative).read_bytes() for relative in SHARED}

    # --- executed ---
    reports, compiled, extracted = {}, {}, {}
    with tempfile.TemporaryDirectory(prefix='melonx-auto-ownership-final-') as temporary:
        base = Path(temporary)
        for variant, auto_text, pool_text in (('control', (control / AUTO).read_text(encoding='utf-8-sig'),
                                               (control / POOL).read_text(encoding='utf-8-sig')),
                                              ('final', final_auto, final_pool)):
            reports[variant], compiled[variant], extracted[variant] = run_variant(base / variant, variant, auto_text,
                                                                                  pool_text, shared)
            print(json.dumps({variant: reports[variant]}, sort_keys=True), flush=True)
        sdk = subprocess.run([DOTNET, '--version'], cwd=base / 'final', text=True, capture_output=True).stdout.strip()

    for variant, report in reports.items():
        check(report['variant'] == variant and report['scenarios'] == SCENARIOS, variant + ': every scenario passed')
        check(report['dependantsPerSlot'] == DEPENDANTS[variant], variant + ': documented dependants per slot: ' +
              json.dumps(report['dependantsPerSlot']))
        check(report['waitablesPerSlot'] == WAITABLES, variant + ': one waitable per slot where the graph has one')
        check(report['nativeDriverTested'] is False, variant + ': doubled native completion')
    same = {key for key in reports['control'] if key not in ('variant', 'dependantsPerSlot')}
    for key in sorted(same):
        check(reports['control'][key] == reports['final'][key], 'identical in both variants: ' + key)
    check(reports['final']['bitsChecked'] > 0 and reports['final']['lifetimeChecks'] > 0, 'bits and lifetimes checked')
    check(compiled['control'][AUTO] == sha(control / AUTO) and compiled['final'][AUTO] == sha(final_source / AUTO),
          'each variant compiles its production Auto.cs byte for byte')
    for relative in (*SHARED, 'Program.cs'):
        check(compiled['control'][relative] == compiled['final'][relative], 'the same compiled source in both variants: ' + relative)

    inputs = ['build-utils/melonx/adapt_command_buffer_ownership.py', 'build-utils/melonx/adapt_signalled_fence_release.py',
              'build-utils/melonx/adapt_session.py', 'test/melonx_auto_ownership_final_test.py',
              'test/melonx_auto_ownership_final/Program.cs', 'test/melonx_auto_ownership_final/Boundaries.cs',
              'test/melonx_adapter_control.py']
    receipt = dict(
        result='passed', checks=checks, finalPreparationBound=True, sourceKind='finalPreparationWithReversedControl',
        physicalDeviceTested=False, nativeDriverTested=False, completeProductionAuto=True, completeProductionBitmaps=True,
        commandTransportAndNativeCompletionDoubled=True, concurrentOwnershipMutationsTested=False,
        concurrentAtomicRefcountsTested=True, laterAdapters=later,
        preimages={AUTO: sha(control / AUTO), POOL: sha(control / POOL)},
        postimages={AUTO: sha(final_source / AUTO), POOL: sha(final_source / POOL)},
        compiledSources=compiled, extractedFromPool=extracted, reports=reports,
        dependantsPerSlot={variant: reports[variant]['dependantsPerSlot'] for variant in reports},
        waitablesPerSlot=reports['final']['waitablesPerSlot'], bitsChecked=reports['final']['bitsChecked'],
        lifetimeChecks=reports['final']['lifetimeChecks'], scenarios=SCENARIOS, sdk=sdk,
        inputs={p: sha(ROOT / p) for p in inputs},
        supersedes='core87 auto-ownership-checks.json (upstream Auto and pool, adapt_auto_ownership); this rerun takes '
                   'the delivered Auto.cs and CommandBufferPool.cs as control and the final ones as candidate')
    out = ROOT / 'dist/melonx/auto-ownership-checks.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(receipt, indent=2) + '\n')
    print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, dependantsPerSlot=receipt['dependantsPerSlot'],
                          bitsChecked=receipt['bitsChecked'], lifetimeChecks=receipt['lifetimeChecks'])))


if __name__ == '__main__':
    main()
