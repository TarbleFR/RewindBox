#!/usr/bin/env python3
"""adapt_npad_config_snapshot on the final preparation, against the Core 735 preparation as control, on the real engine.

Usage: melonx_npad_config_snapshot_test.py <Core 735 prepared tree>
       melonx_npad_config_snapshot_test.py <control> --candidate-source <final preparation containing the adapter>

IPA 726 (12 Nov; private journals, not in the repository): closing a Switch game ended with "Collection was modified;
enumeration operation may not execute." in Ryujinx.Input.HLE.NpadManager.Update, on the window's main loop, two seconds
after the host began the close (which detaches its pads); the engine could not prove the session's end, the close was
quarantined, and every later launch of every engine was refused until RewindBox was restarted. Upstream, the manager
keeps and enumerates the library's own List<InputConfig>, which the library changes under another lock.

Static: the control is the Core 735 NpadManager.cs; the candidate differs by the adapter's two replacements and in no
other file; ReloadConfiguration copies the caller's list under the manager's lock, reads its entries from the copy and
keeps it; `_inputConfig` is assigned only an empty list (constructor) and that copy; no exception is caught or
reclassified; every enumeration of the manager (Update, RefreshInputConfigForHLE, UnblockInputUpdates,
GetPlayerInputConfigByIndex) reads `_inputConfig`; the library's sequences the fixture replays are the control's
(RemoveAll before ReloadConfiguration in AttachGamepadCore and DetachGamepadCore, under inputConfigurationLock); a
drifted file is refused.
Executed: the production Ryujinx.Input (with Ryujinx.HLE) builds from the control and from the candidate; then
(test-only InternalsVisibleTo) test/melonx_npad_config_snapshot/Program.cs drives each engine's real NpadManager and
NpadController with driver doubles. Required:
 1. interleaved (the device's failure): while the manager enumerates its configuration under its lock, the library's
    change to its list (a detach, an attach, the last pad's detach with the keyboard fallback, the session's Clear) is
    made on another thread, which then calls ReloadConfiguration. The control throws
    System.InvalidOperationException "Collection was modified" from the enumeration in every case, the exception of
    the device; the candidate never throws, and its state afterwards is the one of the same operations made one after
    the other (sequential scene), on the control as on the candidate (the session's Clear aside: no reload follows it,
    and the control's manager then sees an empty list while the candidate's keeps the last configuration it was given;
    the window ends with the session, so no frame reads it);
 2. sequence: a seeded script of 400 steps (attach, attach of an absent pad, detach, detach of an unknown pad, driver
    disconnect and connect events, unblock, detach of every pad with the keyboard fallback) gives the same digest at
    every step on both engines: the controller of each slot (id and driver), the configuration found for each player,
    the manager's configuration entries in order, the blocked flag and every call made to the drivers (opens, closes,
    configurations, clears) in order. The control's manager holds the library's list object from the first attach on;
    the candidate's never does and holds the same entries at every step;
 3. sensitivity: wrong variants built from the adapter's own text are caught: the copy not kept (the manager keeps the
    caller's list again: requirement 1 fails) and the valid entries kept instead of the copy (requirement 2 fails).
Nothing here depends on time or thread scheduling: the interleaving is forced by events (the second thread changes the
list while the first waits inside the enumeration), with a bound of 60 s that fails the run; no duration is measured.
Not an iPhone: the device's next closes will show whether the quarantine after "Collection was modified" is gone.
Writes dist/melonx/npad-config-snapshot-checks.json.
"""
from pathlib import Path
import hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
CONTROL_SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_npad_config_snapshot', _HOLD)
import adapt_npad_config_snapshot as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
HARNESS = ROOT / 'test/melonx_npad_config_snapshot'
INPUT = 'src/Ryujinx.Input/Ryujinx.Input.csproj'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
PROBE = 'MeloNXNpadConfigProbe'
STEPS, SEED = 400, 20261112
OPS = ('detach', 'attach', 'detachLast', 'clear')
MODIFIED = 'System.InvalidOperationException: Collection was modified; enumeration operation may not execute.'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def text(tree, name):
    return (tree / name).read_text(encoding='utf-8-sig')


def member(source, signature):
    assert source.count(signature) == 1, signature
    start = source.rindex('\n', 0, source.index(signature)) + 1
    depth, index = 0, source.index('{', start)
    for index in range(index, len(source)):
        depth += (source[index] == '{') - (source[index] == '}')
        if depth == 0:
            return source[start:index + 1]
    raise AssertionError(signature)


# --- Static: the exact scope ---
NPAD = adapter.NPAD
control = text(CONTROL_SOURCE, NPAD)
check(sha(CONTROL_SOURCE / NPAD) == adapter.BASELINE[NPAD], 'control is the Core 735 NpadManager.cs')
check(list(adapter.BASELINE) == [NPAD] and [pair[0] for pair in adapter.PAIRS] == [NPAD, NPAD], 'two replacements, both in NpadManager.cs, and no other file')
candidate_text = control
for _, old, new in adapter.PAIRS:
    check(control.count(old) == 1 and candidate_text.count(old) == 1, 'one site in the control for each replacement')
    candidate_text = candidate_text.replace(old, new)
check(adapter.MARKER in adapter.RELOAD_NEW, 'the replacement carries the adapter\'s marker')
reload = member(candidate_text, '        public void ReloadConfiguration(List<InputConfig> inputConfig, bool enableKeyboard, bool enableMouse)')
check(reload.index('lock (_lock)') < reload.index('List<InputConfig> ownedConfig = new(inputConfig);') <
      reload.index('foreach (InputConfig inputConfigEntry in ownedConfig)') < reload.index('_inputConfig = ownedConfig;') and
      len(re.findall(r'\binputConfig\b', reload)) == 2,
      'ReloadConfiguration copies the caller\'s list under the lock, reads the copy and keeps it; the caller\'s list is read once')
assignments = re.findall(r'_inputConfig = ([^;]+);', candidate_text)
check(assignments == ['[]', 'ownedConfig'], 'the manager\'s list is only ever an empty list or its own copy: ' + repr(assignments))
check(re.findall(r'_inputConfig = ([^;]+);', control) == ['[]', 'inputConfig'], 'the control keeps the caller\'s list')
for signature in ('        public void Update(float aspectRatio = 1)', '        private void RefreshInputConfigForHLE()',
                  '        public void UnblockInputUpdates()', '        internal InputConfig GetPlayerInputConfigByIndex(int index)'):
    body = member(candidate_text, signature)
    check(body == member(control, signature) and '_inputConfig' in body and body.count('lock (_lock)') == 1,
          signature.strip() + ': unchanged, reads the manager\'s list under its lock')
check('catch' not in adapter.RELOAD_NEW + adapter.STORE_NEW and candidate_text.count('catch') == control.count('catch'),
      'no exception is caught or reclassified')
library = text(CONTROL_SOURCE, LIBRARY)
attach = member(library, '        private static nint AttachGamepadCore(string name, nint idPtr, int playerIndex, ControllerType controllerType)')
detach = member(library, '        private static void DetachGamepadCore(nint idPtr)')
check(attach.index('lock (inputConfigurationLock)') < attach.index('_inputConfiguration.RemoveAll(c => c.PlayerIndex == assignedIndex || c.Id == inputId);') <
      attach.index('_inputConfiguration.Add(config);') < attach.index('EnsureKeyboardFallback();') <
      attach.index('_window?.NpadManager.ReloadConfiguration(_inputConfiguration, _enableKeyboard, _enableMouse);'),
      'the control\'s AttachGamepadCore is the sequence the fixture replays (RemoveAll, Add, keyboard fallback, reload with its own list)')
check(detach.index('lock (inputConfigurationLock)') < detach.index('_inputConfiguration?.RemoveAll(c => c.Id == inputId)') <
      detach.index('if (removed > 0)') < detach.index('EnsureKeyboardFallback();') < detach.index('_window?.NpadManager.ReloadConfiguration('),
      'the control\'s DetachGamepadCore is the sequence the fixture replays (RemoveAll, then reload only when an entry was removed)')
check(library.count('_window.Initialize(_emulationContext, _inputConfiguration, _enableKeyboard, _enableMouse);') == 1,
      'the library hands its own list to the window (and so to the manager)')
drift = Path(tempfile.mkdtemp(prefix='melonx-npad-config-snapshot-drift-'))
(drift / NPAD).parent.mkdir(parents=True, exist_ok=True)
shutil.copyfile(CONTROL_SOURCE / NPAD, drift / NPAD)
(drift / NPAD).write_bytes((drift / NPAD).read_bytes() + b'\n// unreviewed drift\n')
try:
    adapter.apply(drift)
    refused = False
except AssertionError:
    refused = True
shutil.rmtree(drift)
check(refused, 'a drifted NpadManager.cs is refused')
if FINAL_PREPARATION:
    from melonx_adapter_control import files_edited_later  # noqa: E402
    check(not files_edited_later('adapt_npad_config_snapshot'), 'no later adapter edits NpadManager.cs')
    check(candidate_text == text(FINAL_SOURCE, NPAD), 'the final preparation is the control plus the adapter\'s replacements')

# --- Executed: the real engine of both sides ---
environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1')
WORK = Path(tempfile.mkdtemp(prefix='melonx-npad-config-snapshot-')).resolve()


def dotnet(*arguments, cwd):
    result = subprocess.run([DOTNET, *arguments], capture_output=True, text=True, timeout=2400, env=environment, cwd=cwd)
    if result.returncode:
        errors = [line for line in result.stdout.splitlines() if ': error ' in line]
        print('\n'.join(dict.fromkeys(errors[:40])), result.stdout[-4000:], result.stderr[-2000:], sep='\n', flush=True)
    return result


def build_probe(side):
    directory = WORK / ('probe-' + side)
    build = dotnet('build', str(directory / (PROBE + '.csproj')), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false', cwd=directory)
    check(build.returncode == 0, 'the fixture builds against the ' + side + ' engine')


def run_probe(side, *arguments):
    directory = WORK / ('probe-' + side)
    run = subprocess.run([DOTNET, str(directory / ('bin/Release/net10.0/' + PROBE + '.dll')), *map(str, arguments)],
                         capture_output=True, text=True, timeout=600, env=environment, cwd=directory)
    if run.returncode:
        print(run.stdout[-4000:], run.stderr[-4000:], flush=True)
    check(run.returncode == 0, side + ' ' + ' '.join(map(str, arguments)) + ': the fixture runs')
    return json.loads(next(line for line in run.stdout.splitlines() if line.startswith('{"scene"')))


def run_all(side):
    report = dict(sequence=run_probe(side, 'sequence', STEPS, SEED))
    for op in OPS:
        report['interleaved-' + op] = run_probe(side, 'interleaved', op)
        report['sequential-' + op] = run_probe(side, 'sequential', op)
    return report


trees = {}
for side in ('control', 'candidate'):
    tree = trees[side] = WORK / side
    shutil.copytree(CONTROL_SOURCE, tree, ignore=shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX'), symlinks=True)
    if side == 'candidate':
        changed = adapter.apply(tree)
        check([str(p.relative_to(tree)) for p in changed] == [NPAD], 'the adapter changed NpadManager.cs only')
        check(text(tree, NPAD) == candidate_text, 'candidate is the control plus the adapter\'s replacements')
        if FINAL_PREPARATION:
            check((tree / NPAD).read_bytes() == (FINAL_SOURCE / NPAD).read_bytes(), 'final preparation is the adapter')
    use_authenticated_libhac_feed(tree, ROOT)
    build = dotnet('build', str(tree / INPUT), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false', cwd=tree)
    check(build.returncode == 0, side + ': production Ryujinx.Input builds')
    if side == 'candidate':
        warnings = sorted({line for line in build.stdout.splitlines() if 'warning' in line and 'NpadManager.cs(' in line})
        check(not warnings, 'no compiler warning in NpadManager.cs: ' + '\n'.join(warnings[:5]))
    print(side + ': production Ryujinx.Input built', flush=True)
    project = tree / INPUT
    project_text = project.read_text(encoding='utf-8-sig')
    project.write_text(project_text.replace('</Project>', '  <ItemGroup><InternalsVisibleTo Include="' + PROBE + '" /></ItemGroup>\n</Project>'))
    probe = WORK / ('probe-' + side)
    probe.mkdir()
    shutil.copyfile(HARNESS / 'Program.cs', probe / 'Program.cs')
    (probe / (PROBE + '.csproj')).write_text(f'''<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework><Nullable>disable</Nullable>
    <AllowUnsafeBlocks>true</AllowUnsafeBlocks><NoWarn>CA1416;CS8632</NoWarn><NuGetAudit>false</NuGetAudit>
    <ManagePackageVersionsCentrally>false</ManagePackageVersionsCentrally>
  </PropertyGroup>
  <ItemGroup>
    <ProjectReference Include="{tree}/src/Ryujinx.Input/Ryujinx.Input.csproj" />
  </ItemGroup>
</Project>
''')
    for extra in ('global.json', 'nuget.config'):
        if (tree / extra).exists():
            shutil.copyfile(tree / extra, probe / extra)
    build_probe(side)

reports = dict(control=run_all('control'), candidate=run_all('candidate'))
reports['controlAgain'] = dict(sequence=run_probe('control', 'sequence', STEPS, SEED))

# Sensitivity: the candidate's NpadManager.cs altered from the adapter's text, the fixture rebuilt against it.
VARIANTS = {
    'copyNotKept': (adapter.STORE_NEW, adapter.STORE_OLD),
    'validEntriesKept': (adapter.STORE_NEW, adapter.STORE_NEW.replace('_inputConfig = ownedConfig;', '_inputConfig = validInputs;')),
}
npad_path = trees['candidate'] / NPAD
for variant, (old, new) in VARIANTS.items():
    check(candidate_text.count(old) == 1 and old != new, variant + ': one site to alter in the adapter\'s text')
    npad_path.write_text(candidate_text.replace(old, new), encoding='utf-8')
    build_probe('candidate')
    reports[variant] = run_all('candidate')
shutil.rmtree(WORK)
if os.environ.get('MELONX_TEST_REPORTS'):
    Path(os.environ['MELONX_TEST_REPORTS']).write_text(json.dumps(reports, indent=1))


def first_difference(a, b):
    for x, y in zip(a['steps'], b['steps'], strict=True):
        if x['d'] != y['d']:
            return dict(step=x['i'], kind=x['k'], differs=sorted(name for name in x['d'] if x['d'][name] != y['d'][name]))
    return None


def interleaving_failures(report):
    """The operations whose interleaved enumeration threw, or whose state differs from the sequential reference."""
    found = {}
    for op in OPS:
        inter, seq = report['interleaved-' + op], report['sequential-' + op]
        if inter['enumerationError'] is not None or inter['reloadError'] is not None or inter['digest'] != seq['digest']:
            found[op] = inter['enumerationError'] or inter['reloadError'] or 'state'
    return found


c, k = reports['control'], reports['candidate']

# --- 1. the device's interleaving ---
interleaved = {}
for op in OPS:
    ci, ki, cs, ks = c['interleaved-' + op], k['interleaved-' + op], c['sequential-' + op], k['sequential-' + op]
    check(ci['enumerationError'] == MODIFIED and ci['reloadError'] is None,
          op + ': the control throws the device\'s exception from the enumeration: ' + repr(ci['enumerationError']))
    check(cs['enumerationError'] is None and cs['reloadError'] is None and ks['enumerationError'] is None and ks['reloadError'] is None,
          op + ': nothing throws when the change is not interleaved')
    check(ki['enumerationError'] is None and ki['reloadError'] is None, op + ': the candidate never throws: ' + repr(ki['enumerationError']))
    check(ki['digest'] == ks['digest'], op + ': the candidate ends as in the sequential order')
    check(ci['sharesLibraryList'] is True and ki['sharesLibraryList'] is False and cs['sharesLibraryList'] is True and ks['sharesLibraryList'] is False,
          op + ': the control\'s manager enumerates the library\'s list object, the candidate\'s its own')
    if op == 'clear':
        same = {name: cs['digest'][name] == ks['digest'][name] for name in cs['digest']}
        check(same == dict(controllers=True, byPlayer=False, config=False, blocked=True, driverLog=True) and cs['digest']['config'] == [] and
              len(ks['digest']['config']) == 3 and ks['holdsLibraryEntries'] is False,
              'clear (no reload follows): the controllers, the flag and the driver calls are the same; only the control\'s manager sees the empty list: ' + json.dumps(same))
    else:
        check(cs['digest'] == ks['digest'] and ks['holdsLibraryEntries'] is True and ki['holdsLibraryEntries'] is True,
              op + ': the sequential state is the same on both engines and the candidate holds the library\'s entries')
    interleaved[op] = dict(control=ci['enumerationError'], candidate=ki['enumerationError'],
                           controllersAfter=ki['digest']['controllers'], blockedAfter=ki['digest']['blocked'])
check(c['interleaved-detach']['digest']['blocked'] is True and k['interleaved-detach']['digest']['blocked'] is False,
      'the control\'s enumeration stops at the exception (the manager stays blocked); the candidate\'s completes')

# --- 2. the seeded sequence ---
sc, sk = c['sequence'], k['sequence']
check(len(sc['steps']) == len(sk['steps']) == STEPS and sc['seed'] == sk['seed'] == SEED and sc['kinds'] == sk['kinds'], 'the same script on both engines')
check(all(sc['kinds'].get(kind, 0) >= 5 for kind in ('attach', 'attachAbsent', 'detach', 'detachUnknown', 'driverDisconnect', 'driverConnect',
                                                    'unblock', 'detachAll')), 'every kind of step occurs: ' + json.dumps(sc['kinds']))
check(first_difference(sc, reports['controlAgain']['sequence']) is None, 'the control is deterministic')
difference = first_difference(sc, sk)
check(difference is None, 'control and candidate digests differ: ' + json.dumps(difference))
first_attach = next(step['i'] for step in sc['steps'] if step['k'] in ('attach', 'attachAbsent'))
check(all(step['shares'] for step in sc['steps'][first_attach:]), 'the control\'s manager holds the library\'s list from the first attach on')
check(not any(step['shares'] for step in sk['steps']), 'the candidate\'s manager never holds the library\'s list')
check(all(step['holds'] for step in sk['steps'][first_attach:]), 'the candidate\'s manager holds the library\'s entries at every step')
check(sum(len(step['d']['driverLog']) for step in sc['steps']) > 400 and
      sum(any(entry.startswith('open') and entry.endswith('absent') for entry in step['d']['driverLog']) for step in sc['steps']) >= 10 and
      sum(any(c != '-' for c in step['d']['controllers']) for step in sc['steps']) >= STEPS // 2 and
      sum(any(c.endswith('@keyboard') for c in step['d']['controllers']) for step in sc['steps']) >= 5,
      'the script assigns pads and the keyboard fallback, and meets absent pads')

# --- 3. sensitivity ---
sensitivity = {}
for variant in VARIANTS:
    wrong = reports[variant]
    sensitivity[variant] = dict(interleavingFailures=interleaving_failures(wrong), sequenceDifference=first_difference(sc, wrong['sequence']))
check(set(sensitivity['copyNotKept']['interleavingFailures']) == set(OPS) and
      all(v == MODIFIED for v in sensitivity['copyNotKept']['interleavingFailures'].values()),
      'copyNotKept: caught by the interleaving (the device\'s exception again): ' + json.dumps(sensitivity['copyNotKept']))
check(sensitivity['validEntriesKept']['sequenceDifference'] is not None, 'validEntriesKept: caught by the sequence: ' + json.dumps(sensitivity['validEntriesKept']))
check(interleaving_failures(k) == {}, 'the candidate passes every interleaving')

inputs = ['build-utils/melonx/adapt_npad_config_snapshot.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_npad_config_snapshot_test.py', 'test/melonx_npad_config_snapshot/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core735Preparation',
               postimages={NPAD: sha(FINAL_SOURCE / NPAD)} if FINAL_PREPARATION else {},
               productionInputAssemblyBuilt=True, interleaved=interleaved,
               sequence=dict(steps=STEPS, seed=SEED, kinds=sc['kinds'], digestsEqual=sum(x['d'] == y['d'] for x, y in zip(sc['steps'], sk['steps'])),
                             controlStepsSharingLibraryList=sum(step['shares'] for step in sc['steps']),
                             candidateStepsSharingLibraryList=sum(step['shares'] for step in sk['steps'])),
               sensitivity=sensitivity, sensitivityVariantsFailed=len(VARIANTS), sdk=sdk, host=platform.system(), physicalDeviceTested=False,
               deviceEvidence='IPA 726 (12 Nov; private journals): System.InvalidOperationException "Collection was modified" at '
                              'Ryujinx.Input.HLE.NpadManager.Update on the window main loop during a close; close quarantined; every later launch refused',
               inputs={name: sha(ROOT / name) for name in inputs},
               limitation='Driver doubles and the library\'s sequences replayed by the fixture: Update itself is not executed (it needs a '
                          'running Switch device); it reads the same field under the same lock, unchanged. The device\'s next closes decide '
                          'whether the quarantine is gone.')
out = ROOT / 'dist/melonx/npad-config-snapshot-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
