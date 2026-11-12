#!/usr/bin/env python3
"""adapt_nifm_network_watch on the final preparation, against the Core 743 preparation as control.

Usage: melonx_nifm_network_watch_test.py <Core 743 preparation> [--candidate-source <final preparation containing the adapter>]

IPA 729 / Core 743: after each game's close the whole session (Switch, GpuContext, Horizon, kernel, renderer, window,
the eleven ServerBase processes) is still reachable, 1/1 then 2/2. The source subscribes each nifm IGeneralService to
the runtime's static NetworkChange.NetworkAddressChanged event and unsubscribes only in Dispose, which a session the
guest closes never reaches for a domain's objects.

The production Ryujinx.HLE assembly of the control and of the candidate is built, and the candidate's Ryujinx.Library
(the journal line). test/melonx_nifm_network_watch/Program.cs loads each built assembly and, by reflection, gives a
real IGeneralService its real ServerBase (IpcService.TrySetServer) whose KernelContext holds a real Switch
(uninitialized objects: only the references are under test), on the host .NET 10 runtime with its real event:
- a service that is disposed: nothing of its session stays reachable, control and candidate;
- a service left undisposed: after three blocking compacting collections the control keeps the service, server,
  kernel and Switch (4 of 4) and, over eleven sessions in a row, eleven Switches and their 8 MiB payloads; the
  candidate keeps none, and its heap returns to the baseline;
- the cached interface as GetLocalInterface returns it: cached, cached, fresh after an address change (for a service
  read before and after, and for one read only after), refilled once, cached for a service created after the change,
  fresh after a second change: the same sequence in the control (its handler invoked on every subscribed service) and
  in the candidate (its one static handler);
- candidate: five services subscribe the process-wide event once, the handler is static and holds no object; a
  runtime that refuses the subscription fails the creation, as the control's constructor did, and the next creation
  subscribes; the journal text counts creations and disposals.
Static: only the two files change, each replacement is present once and reverses to the control; no instance handler
on the event remains; the two cached fields are read only in GetLocalInterface. Host runtime, not an iPhone: that the
undisposed general service is what held the 729 sessions is shown on the device by the sessionRetention line
(Switch released, created minus disposed above zero). Writes dist/melonx/nifm-network-watch-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later  # noqa: E402
import adapt_nifm_network_watch as adapter  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_nifm_network_watch', _HOLD)

DOTNET = os.environ.get('DOTNET', 'dotnet')
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def run(command, cwd, timeout=1800):
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, cwd=cwd,
                            env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1'))
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
    return result


with tempfile.TemporaryDirectory(prefix='melonx-nifm-network-watch-') as temporary:
    base = Path(temporary).resolve()
    ignore = shutil.ignore_patterns('.git', 'bin', 'obj', 'MeloNX')
    control, candidate = base / 'control', base / 'candidate'
    shutil.copytree(SOURCE, control, ignore=ignore, symlinks=True)
    shutil.copytree(SOURCE, candidate, ignore=ignore, symlinks=True)
    for name, expected in adapter.BASELINE.items():
        check(hashlib.sha256((control / name).read_bytes()).hexdigest() == expected, 'control is the pinned preparation: ' + name)
    before = {name: (control / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
    changed = adapter.apply(candidate)
    check(sorted(str(p.relative_to(candidate)) for p in changed) == sorted(adapter.BASELINE), 'adapter changed other files')
    try:
        adapter.apply(candidate)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted tree is refused')
    after = {name: (candidate / name).read_text(encoding='utf-8-sig') for name in adapter.BASELINE}
    if FINAL_PREPARATION:
        for name in adapter.BASELINE:
            if name not in files_edited_later('adapt_nifm_network_watch'):
                check((candidate / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'final preparation is the adapter: ' + name)
    for name, pairs in ((adapter.SERVICE, adapter.SERVICE_PAIRS), (adapter.LIBRARY, adapter.LIBRARY_PAIRS)):
        restored = after[name]
        for old, new in reversed(pairs):
            check(restored.count(new) == 1, 'replacement present once: ' + new.strip().splitlines()[0][:70])
            restored = restored.replace(new, old)
        check(restored == before[name], 'nothing else changes in ' + name)
    service = after[adapter.SERVICE]
    klass = service[:service.index('    static class NetworkAddressWatch')]
    check(before[adapter.SERVICE].count('NetworkChange.NetworkAddressChanged += LocalInterfaceCacheHandler;') == 1 and
          'NetworkChange.' not in klass and 'LocalInterfaceCacheHandler' not in service and
          service.count('NetworkChange.NetworkAddressChanged') == 1 and
          'static handler => NetworkChange.NetworkAddressChanged += handler;' in service,
          'the control subscribes each service; the candidate subscribes nothing but one static handler')
    reader = klass[klass.index('GetLocalInterface(ServiceCtx context)\n'):klass.index('        protected override void Dispose(bool isDisposing)')]
    for field in ('_targetPropertiesCache', '_targetAddressInfoCache'):
        check(klass.count(field) == reader.count(field) + 1, 'the cached field is read and written only in GetLocalInterface: ' + field)
    check(reader.index('int networkVersion = NetworkAddressWatch.Version;') < reader.index('if (_targetPropertiesCache == null ||') and
          'NetworkAddressWatch.Created();\n            _cacheNetworkVersion = NetworkAddressWatch.Version;' in klass and
          'NetworkAddressWatch.Disposed();' in klass, 'the count is compared before the cache is used; creations and disposals are counted')
    watch = service[service.index('    static class NetworkAddressWatch'):]
    check('lock (' not in watch and 'new Thread' not in watch and 'Timer' not in watch and 'GC.' not in watch and
          'private static void OnAddressChanged(object sender, EventArgs e)' in watch, 'a static handler: no lock, thread, timer or collection')
    check('NifmSessionDiagnostics.Describe()' in after[adapter.LIBRARY] and 'GC.Collect' not in adapter.JOURNAL_NEW, 'journal line only in the Library')

    for tree, project in ((control, 'src/Ryujinx.HLE/Ryujinx.HLE.csproj'), (candidate, 'src/Ryujinx.HLE/Ryujinx.HLE.csproj'),
                          (candidate, 'src/Ryujinx.Library/Ryujinx.Library.csproj')):
        result = run([DOTNET, 'build', str(tree / project), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'], tree)
        check(result.returncode == 0, f'production {Path(project).stem} assembly builds ({tree.name})')

    fixture = base / 'fixture'
    fixture.mkdir()
    shutil.copy(ROOT / 'test/melonx_nifm_network_watch/Program.cs', fixture / 'Program.cs')
    (fixture / 'Fixture.csproj').write_text(
        '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
        '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><ServerGarbageCollection>false</ServerGarbageCollection>'
        '<ConcurrentGarbageCollection>true</ConcurrentGarbageCollection><TieredCompilation>false</TieredCompilation></PropertyGroup></Project>\n')
    check(run([DOTNET, 'build', str(fixture / 'Fixture.csproj'), '-c', 'Release', '-nologo', '-p:NuGetAudit=false'], fixture).returncode == 0, 'fixture builds')

    def execute(tree, *mode):
        result = run([DOTNET, str(fixture / 'bin/Release/net10.0/Fixture.dll'), str(tree / 'src/Ryujinx.HLE/bin/Release/net10.0'), *mode], fixture, 600)
        check(result.returncode == 0, f'fixture ran on the {tree.name}')
        return json.loads(next(line for line in reversed(result.stdout.splitlines()) if line.startswith('{')))

    c, k, seam = execute(control), execute(candidate), execute(candidate, 'seam')

print(json.dumps({'control': c, 'candidate': k, 'seam': seam})[:3000], flush=True)
check(c['candidate'] is False and k['candidate'] is True, 'each engine is the one it is said to be')
check(c['disposedSessionPartsAlive'] == 0 and k['disposedSessionPartsAlive'] == 0, 'a disposed general service releases its session in both')
check(c['abandonedSessionPartsAlive'] == 4 and c['abandonedSwitchAlive'] is True,
      'control: an undisposed general service keeps its server, kernel and Switch after three blocking compacting collections')
check(k['abandonedSessionPartsAlive'] == 0 and k['abandonedSwitchAlive'] is False, 'candidate: nothing of that session stays reachable')
payload = c['payloadBytes']
check(c['sessionsCreated'] == 11 and c['switchesAlive'] == 11 and c['heapAfterElevenBytes'] >= 11 * payload and c['heapAfterOneBytes'] >= payload,
      'control: eleven sessions in a row, eleven Switches and their payloads kept: %d bytes' % c['heapAfterElevenBytes'])
check(k['switchesAlive'] == 0 and abs(k['heapAfterElevenBytes']) < 1024 * 1024 and abs(k['heapAfterOneBytes']) < 1024 * 1024,
      'candidate: none kept, the heap returns to its baseline: %d bytes' % k['heapAfterElevenBytes'])
expected = ['first before:cached', 'first again:cached', 'first after change:fresh', 'second after change:fresh', 'first refilled once:True',
            'third created after the change:cached', 'third after a second change:fresh']
if c['networkAvailable'] and k['networkAvailable']:
    check(c['observations'] == expected, 'control: the cached interface as returned: ' + str(c['observations']))
check(k['observations'] == c['observations'], 'candidate returns what the control returns: ' + str(k['observations']))
check(seam == {'candidate': True, 'mode': 'seam', 'subscriptions': 1, 'handlerTargetIsNull': True, 'handlerIsStatic': True, 'versionStep': 1,
               'refusedSubscriptionThrows': True, 'subscriptionRetried': True},
      'one static subscription for five services, holding no object; a refused subscription fails the creation and is retried: ' + str(seam))
check(k['describe'] == 'Nifm general services created 15, disposed 1' and k['diagnosticsIsPublic'] is True and c['describe'] is None,
      'the journal text counts creations and disposals: ' + str(k['describe']))

report = {
    'result': 'passed', 'checks': checks, 'finalPreparationBound': FINAL_PREPARATION,
    'sourceKind': 'finalPreparationWithReversedControl' if FINAL_PREPARATION else 'pinnedPreparationPlusAdapter',
    'physicalDeviceTested': False, 'productionHleAssemblyBuilt': True, 'productionLibraryAssemblyBuilt': True,
    'controlSwitchesKeptOfEleven': c['switchesAlive'], 'candidateSwitchesKeptOfEleven': k['switchesAlive'],
    'controlHeapAfterElevenBytes': c['heapAfterElevenBytes'], 'candidateHeapAfterElevenBytes': k['heapAfterElevenBytes'],
    'observations': k['observations'], 'networkAvailable': k['networkAvailable'], 'subscriptions': seam['subscriptions'],
}
out = ROOT / 'dist/melonx/nifm-network-watch-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(report, indent=2) + '\n')
print(f'PASS {checks} nifm network watch checks')
