#!/usr/bin/env python3
"""Layer binders released at SurfaceFlinger.Dispose, and the sessionRetention probe (adapt_binder_teardown).

Usage: melonx_binder_teardown_test.py <Core 649 prepared MeloNX tree>
       melonx_binder_teardown_test.py <control> --candidate-source <final preparation containing the adapter>

Applies the adapter to a copy of the Core 649 preparation and builds the production Ryujinx.Library (with Ryujinx.HLE)
for the control and the candidate. Static checks bind that the only behavioural change is one
UnregisterBinderObject(layer.ProducerBinderId) after each PrepareForExit in SurfaceFlinger.Dispose (no lock, no clearing
of _layers), that the binder server gains only a read-only count, and that Library gains only weak references taken
after the session's fields are cleared and one durable "sessionRetention" line after the existing final collection
(never "begin", no added collection). Behaviour (test/melonx_binder_teardown/Program.cs): the REAL HOSBinderDriverServer.cs
and the REAL SurfaceFlinger members (CreateLayerFromId, DestroyManagedLayer, CloseLayer, Dispose, ...) run with doubles
keeping the production chain registry -> producer -> queue -> KEvent -> KernelContext -> Switch: a closed session whose
guest destroyed one of three layers is disposed (twice) while another session stays live; after a full collection the
control keeps the closed Switch reachable through two registry entries, the candidate leaves only the live session's
entry and the closed Switch and GpuContext are collected. For the candidate the REAL probe methods extracted from
Library.cs report the closed session released, and a session held by another root retained. No device.
Writes dist/melonx/binder-teardown-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_binder_teardown', _HOLD)
from adapt_binder_teardown import apply, BASELINE  # noqa: E402

FLINGER = 'src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/SurfaceFlinger.cs'
SERVER = 'src/Ryujinx.HLE/HOS/Services/SurfaceFlinger/HOSBinderDriverServer.cs'
LIBRARY = 'src/Ryujinx.Library/Library.cs'
DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.rindex('\n', 0, text.index(signature)) + 1
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the Core 649 preparation: ' + name)


def use_authenticated_libhac_feed(tree):
    """The HLE closure needs Ryujinx.LibHac. A tree still declaring the unreachable upstream feed (a prepared source that
    build_libhac.py did not configure) uses the authenticated local package instead: dist/melonx/libhac-feed holding the
    pinned package whose SHA-256 is the build_libhac identity receipt's (build_libhac.configure_feed). Otherwise unchanged."""
    lock = json.loads((ROOT / 'build-utils/melonx/source.json').read_text())['libHac']
    feed = ROOT / 'dist/melonx/libhac-feed'
    package = feed / (lock['package'] + '.' + lock['version'] + '.nupkg')
    receipt = ROOT / 'dist/melonx/libhac-identity.json'
    config = (tree / 'nuget.config').read_text(encoding='utf-8-sig')
    if 'https://starforgejo.dev/api/packages/Ryulynx/nuget/index.json' not in config or not package.is_file() or not receipt.is_file():
        return
    identity = json.loads(receipt.read_text())
    check(identity['source'] == lock and hashlib.sha256(package.read_bytes()).hexdigest() == identity['packageSha256'],
          'the local LibHac package is the authenticated one')
    from build_libhac import configure_feed
    configure_feed(tree, feed, lock['package'])


# Lines the adapter adds; everything else must be the preparation's bytes.
FLINGER_ADDED = '''                // RewindBox (adapt_binder_teardown): the static binder registry otherwise keeps this producer, and
                // through its queue's kernel events the whole closed Switch, reachable for the rest of the process.
                HOSBinderDriverServer.UnregisterBinderObject(layer.ProducerBinderId);
'''
PROBE_CALL = '''            // RewindBox (adapt_binder_teardown): journal only, after the final collection.
            RecordSessionRetention();
'''
NOTE_CALL = '''                // RewindBox (adapt_binder_teardown): weak references only, for the sessionRetention journal line.
                if (context != null) NoteReleasedSession(context);
'''
PROBE_START = '        // RewindBox (adapt_binder_teardown): whether a closed session'

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
texts, reports = {}, {}
with tempfile.TemporaryDirectory(prefix='melonx-binder-teardown-') as temporary:
    for variant in ('control', 'candidate'):
        work = Path(temporary).resolve() / variant
        shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
        use_authenticated_libhac_feed(work)
        if variant == 'candidate':
            changed = apply(work)
            check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'adapter changed other files')
            if FINAL_PREPARATION:
                # Files a later adapter also edits (Core 656: adapt_present_pacing in Library) are proven by control_source's
                # forward check; the others must be the final preparation's bytes here.
                later = files_edited_later('adapt_binder_teardown')
                for name in BASELINE:
                    if name not in later:
                        check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
        texts[variant] = {name: (work / name).read_text(encoding='utf-8-sig') for name in BASELINE}
        result = subprocess.run([DOTNET, 'build', str(work / 'src/Ryujinx.Library/Ryujinx.Library.csproj'), '-c', 'Release', '-nologo',
                                 '-m:1', '-p:NuGetAudit=false'], capture_output=True, text=True, timeout=2400, env=environment, cwd=work)
        if result.returncode:
            print(result.stdout[-5000:], result.stderr[-2000:], flush=True)
        check(result.returncode == 0, variant + ' production Ryujinx.Library (with Ryujinx.HLE) builds')
        print(variant + ': production Ryujinx.Library built', flush=True)

    control, candidate = texts['control'], texts['candidate']

    # SurfaceFlinger: one unregister per remaining layer, after its PrepareForExit; nothing else.
    flinger = candidate[FLINGER]
    check(flinger.count(FLINGER_ADDED) == 1 and flinger.replace(FLINGER_ADDED, '') == control[FLINGER],
          'SurfaceFlinger unchanged but the unregister in Dispose')
    dispose_c, dispose_k = member(control[FLINGER], 'public void Dispose()'), member(flinger, 'public void Dispose()')
    check(dispose_k.index('_isRunning = false;') < dispose_k.index('layer.Core.PrepareForExit();') <
          dispose_k.index('HOSBinderDriverServer.UnregisterBinderObject(layer.ProducerBinderId);'), 'unregistered after PrepareForExit')
    check(not re.search(r'lock\s*\(|_layers\.(Clear|Remove)|RegisterBinderObject\(', dispose_k.replace('UnregisterBinderObject(', '')),
          'Dispose takes no lock and keeps _layers')
    check(flinger.count('HOSBinderDriverServer.UnregisterBinderObject(') == 3 and
          control[FLINGER].count('HOSBinderDriverServer.UnregisterBinderObject(') == 2, 'one unregister added beside the guest paths')
    for signature in ('private void CreateLayerFromId(', 'public Vi.ResultCode DestroyManagedLayer(long layerId)',
                      'public Vi.ResultCode DestroyStrayLayer(long layerId)', 'private void CloseLayer(long layerId, Layer layer)'):
        check(member(flinger, signature) == member(control[FLINGER], signature), 'unchanged: ' + signature)

    # HOSBinderDriverServer: a read-only count under its lock, and its public accessor.
    server = candidate[SERVER]
    accessor = ('        // RewindBox (adapt_binder_teardown): registered binder count, for the sessionRetention journal line.\n' +
                member(server, 'internal static int RegisteredBinderCount') + '\n\n')
    diagnostics_start = server.index('\n    // RewindBox (adapt_binder_teardown): read-only')
    diagnostics = server[diagnostics_start:server.index('    }\n', diagnostics_start) + len('    }\n')]
    check(server.count(accessor) == 1 and server.replace(accessor, '').replace(diagnostics, '') == control[SERVER],
          'binder server unchanged but the count and its accessor')
    check('lock (_lock)' in accessor and 'return _registeredBinderObjects.Count;' in accessor and
          not re.search(r'\.(Add|Remove|Clear)\(|=\s', accessor + diagnostics.replace('=>', '')), 'the count only reads')
    check('public static class BinderRegistryDiagnostics' in diagnostics and
          'public static int RegisteredBinderCount => HOSBinderDriverServer.RegisteredBinderCount;' in diagnostics, 'public accessor')

    # Library: weak references after the fields are cleared, one line after the final collection; journal only.
    library = candidate[LIBRARY]
    probe_start = library.index(PROBE_START)
    probe_end = library.index(member(library, 'private static void RecordSessionRetention()')) + \
        len(member(library, 'private static void RecordSessionRetention()')) + 1
    probe = library[probe_start:probe_end]
    check(library.count(PROBE_CALL) == 1 and library.count(NOTE_CALL) == 1 and library[probe_start - 1] == '\n' and
          library.replace(PROBE_CALL, '').replace(NOTE_CALL, '').replace('\n' + probe, '') == control[LIBRARY],
          'Library unchanged but the probe')
    load = member(library, 'static void Load(Options option)')
    check(load.index('GC.Collect(2, GCCollectionMode.Aggressive, blocking: true, compacting: true);') <
          load.index('GC.WaitForPendingFinalizers();') < load.rindex('GC.Collect();') < load.index('RecordSessionRetention();'),
          'probe after the final collection')
    owner = member(library, 'private static bool LoadApplication(Options options)')
    check(owner.index('context?.Dispose();') < owner.index('window?.Dispose();') < owner.index('_emulationContext = null;') <
          owner.index('_window = null;') < owner.index('NoteReleasedSession(context);') and
          owner.index('NoteReleasedSession(context);') > owner.index('finally'), 'weak references taken once the session is released')
    check(not re.search(r'GC\.(Collect|WaitForPendingFinalizers|KeepAlive|GetTotalMemory\(true\))|GCHandle|Dispose\(|_emulationContext|_window\b', probe),
          'probe adds no collection and touches no session state')
    fields = re.findall(r'private static (?:readonly )?([^\n=]+?) _\w+ = ', probe)
    check(fields == ['List<(WeakReference Device, WeakReference Gpu)>', 'object'], 'only weak references are kept: ' + str(fields))
    statuses = re.findall(r'EmbeddedLaunchDiagnostics\.Record\("(\w+)",\s*(.*?),\s*devices', probe, flags=re.S)
    check(len(statuses) == 1 and statuses[0][0] == 'sessionRetention' and 'begin' not in probe and
          set(re.findall(r'"(none|retained|released)"', statuses[0][1])) == {'none', 'retained', 'released'},
          'one sessionRetention line, never begin: ' + str(statuses))
    check(library.count('EmbeddedLaunchDiagnostics.Record(') == control[LIBRARY].count('EmbeddedLaunchDiagnostics.Record(') + 1,
          'one journal line added')

    # Behaviour: real binder server and SurfaceFlinger members, with doubles.
    program = (ROOT / 'test/melonx_binder_teardown/Program.cs').read_text()
    for variant in ('control', 'candidate'):
        fixture = Path(temporary).resolve() / ('fixture-' + variant)
        fixture.mkdir()
        source = texts[variant]
        members = '\n\n'.join(member(source[FLINGER], signature) for signature in (
            'private class Layer', 'private void CreateLayerFromId(', 'public Vi.ResultCode DestroyManagedLayer(long layerId)',
            'private void CloseLayer(long layerId, Layer layer)', 'public void SetRenderLayer(long layerId)',
            'private Layer GetLayerByIdLocked(long layerId)', 'public void Dispose()'))
        check(member(source[FLINGER], 'public void Dispose()') in members, variant + ' fixture runs the real Dispose')
        text = program.replace('//__FLINGER_MEMBERS__\n', members + '\n')
        text = text.replace('//__PROBE__\n', probe if variant == 'candidate' else '')
        (fixture / 'Program.cs').write_text(text)
        (fixture / 'HOSBinderDriverServer.cs').write_text(source[SERVER])
        (fixture / 'Fixture.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CS0067;CS0414;CS0649;CS8321</NoWarn>'
            + ('<DefineConstants>$(DefineConstants);PROBE</DefineConstants>' if variant == 'candidate' else '') +
            '</PropertyGroup></Project>\n')
        for command in ([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'],
                        [DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll')]):
            result = subprocess.run(command, capture_output=True, text=True, timeout=900, env=environment, cwd=fixture)
            if result.returncode:
                print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
                result.check_returncode()
        reports[variant] = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
        print(variant + ': ' + json.dumps(reports[variant])[:2000], flush=True)

control_report, candidate_report = reports['control'], reports['candidate']
for name, report in reports.items():
    check(report['registeredBefore'] == 1 and report['registeredWithA'] == 4 and report['guestDestroy'] == 'Success' and
          report['afterGuestDestroy'] == 3 and not report['destroyedIdRegistered'], name + ': guest destroy path unregisters as before')
    check(report['prepareForExitCalls'] == 4 and report['coresInactive'] and report['composerStopped'], name + ': Dispose prepares every layer')
    check(report['liveSessionBinderKept'] and report['liveSwitchAlive'] and report['errors'] == [], name + ': live session untouched')
check(control_report['afterDispose'] == 3 and control_report['registryAfter'] == 3 and control_report['closedSwitchAlive'] and
      control_report['closedGpuAlive'] and control_report['publicAccessor'] is None and control_report['journal'] == [],
      'control: the closed Switch stays reachable through the registry')
check(candidate_report['afterDispose'] == 1 and candidate_report['afterSecondDispose'] == 1 and candidate_report['registryAfter'] == 1,
      'candidate: only the live session stays registered, a second Dispose changes nothing')
check(not candidate_report['closedSwitchAlive'] and not candidate_report['closedGpuAlive'], 'candidate: the closed Switch and GpuContext are collected')
check(candidate_report['publicAccessor'] == 1, 'candidate: public count matches the registry')
journal = candidate_report['journal']
check(len(journal) == 2 and journal[0].startswith(
    'sessionRetention released 0 after the final collection: closed sessions tracked 1; Switch still reachable 0/1 (latest no); '
    'GpuContext still reachable 0/1 (latest no); binder registry entries 1; managed heap ') and journal[0].endswith(' MB'),
      'probe reports the closed session released: ' + str(journal))
check(journal[1].startswith('sessionRetention retained 1 after the final collection: closed sessions tracked 2; Switch still reachable '
                            '1/2 (latest yes); GpuContext still reachable 1/2 (latest yes); binder registry entries 1; '),
      'probe reports a session held by another root: ' + str(journal))

inputs = ['build-utils/melonx/adapt_binder_teardown.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_binder_teardown_test.py', 'test/melonx_binder_teardown/Program.cs', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'core649Preparation',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE} if FINAL_PREPARATION else {},
               reports=reports, sdk=sdk, physicalDeviceTested=False, productionLibraryBuilt=True, productionHleAssemblyBuilt=True,
               sourceBaseline=BASELINE, inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Removes the static binder-registry root proven in code; whether another root keeps a closed session '
                          'reachable on the device, and the heap a next session starts from, are known only from the '
                          'sessionRetention line of a device run with two sessions. The probe is journal only.')
out = ROOT / 'dist/melonx/binder-teardown-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
