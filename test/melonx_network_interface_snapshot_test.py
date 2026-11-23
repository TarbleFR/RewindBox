#!/usr/bin/env python3
"""One enumeration of the host's interfaces for 5 s, and no enumeration for an answer already known
(adapt_network_interface_snapshot), before and after, the production NetworkHelpers.cs.

Usage: melonx_network_interface_snapshot_test.py <final preparation containing the adapter>
       melonx_network_interface_snapshot_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control); candidate is the adapter applied to it.
Static: each replacement once and reversible, fail closed, the final preparation is the control plus the adapter; nifm's
two availability checks use NetworkHelpers', nothing else of IGeneralService changes; the snapshot's loop is the
runtime's (NetworkInterfacePal.Bsd and .Linux of dotnet/runtime v10.0.0: neither loopback nor tunnel, up); the shortcut
answers only with no interface named, outside Windows, when the resolver file does not exist; DNS, sockets, TLS and the
Nextendo files are not touched.
Built: the production Ryujinx.HLE assembly (with Ryujinx.Common), no warning in the edited files.
Executed (test/melonx_network_interface_snapshot/Program.cs): the production NetworkHelpers.cs of each variant and the
two nifm call sites as IGeneralService makes them, 60 status and address requests in 6 s and 400 from 8 threads, with
/etc/resolv.conf hidden (an LD_PRELOAD shim answering ENOENT, as in the iOS sandbox) and present: first-chance exceptions,
answers. The host's runtime is Linux's (one /etc/resolv.conf read per enumeration, not iOS's two per interface): the
counts are the host's. No device. Writes dist/melonx/network-interface-snapshot-checks.json.
"""
from pathlib import Path
import hashlib, json, os, re, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source, files_edited_later, use_authenticated_libhac_feed  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_network_interface_snapshot', _HOLD)
from adapt_network_interface_snapshot import apply, BASELINE, FILE_PAIRS, GENERAL, HELPERS  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_network_interface_snapshot'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def member(text, signature):
    start = text.index(signature)
    depth, index = 0, text.index('{', start)
    for index in range(index, len(text)):
        depth += (text[index] == '{') - (text[index] == '}')
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def run(command, cwd, environment, timeout=1800):
    result = subprocess.run(command, cwd=cwd, env=environment, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        print(result.stdout[-6000:], result.stderr[-3000:], flush=True)
        raise SystemExit('FAILED: ' + ' '.join(map(str, command[:4])))
    return result


check(FINAL_PREPARATION, 'the source is a final preparation containing the adapter')
for name, expected in BASELINE.items():
    check(hashlib.sha256((SOURCE / name).read_bytes()).hexdigest() == expected, 'not the adapter\'s preparation: ' + name)

environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
reports = {}
with tempfile.TemporaryDirectory(prefix='melonx-network-interface-snapshot-') as temporary:
    temporary = Path(temporary).resolve()
    work = temporary / 'candidate'
    shutil.copytree(SOURCE, work, ignore=shutil.ignore_patterns('.git', 'bin', 'obj'), symlinks=True)
    changed = apply(work)
    check(sorted(str(p.relative_to(work)) for p in changed) == sorted(BASELINE), 'the adapter changes its two files only')
    later = files_edited_later('adapt_network_interface_snapshot')
    for name in BASELINE:
        if name not in later:
            check((work / name).read_bytes() == (FINAL_SOURCE / name).read_bytes(), 'the final preparation is the control plus the adapter: ' + name)
    try:
        apply(work)
        refused = False
    except AssertionError:
        refused = True
    check(refused, 'fail closed: an adapted file is refused')
    texts = {}
    for name, pairs in FILE_PAIRS.items():
        control, candidate = (SOURCE / name).read_text(encoding='utf-8-sig'), (work / name).read_text(encoding='utf-8-sig')
        texts[name] = (control, candidate)
        for old, new in pairs:
            check(control.count(old) == 1 and candidate.count(new) == 1, 'each replacement is exact and reversible: ' + new.strip()[:60])

    # --- static ---
    helpers_control, helpers = texts[HELPERS]
    general_control, general = texts[GENERAL]
    check(general_control.count('NetworkInterface.GetIsNetworkAvailable()') == 2 and 'NetworkInterface.GetIsNetworkAvailable()' not in general and
          general.count('NetworkHelpers.GetIsNetworkAvailable()') == 2, 'nifm\'s two availability checks use NetworkHelpers\'')
    check(general.replace('NetworkHelpers.GetIsNetworkAvailable()', 'NetworkInterface.GetIsNetworkAvailable()').replace(
        '            // RewindBox (adapt_network_interface_snapshot): over the 5 s enumeration.\n', '') == general_control,
          'nothing else of IGeneralService changes (its cache and the network watch included)')
    available = member(helpers, 'public static bool GetIsNetworkAvailable()')
    check('if (OperatingSystem.IsWindows())\n            {\n                return NetworkInterface.GetIsNetworkAvailable();' in available and
          'adapter.NetworkInterfaceType == NetworkInterfaceType.Loopback || adapter.NetworkInterfaceType == NetworkInterfaceType.Tunnel' in available and
          'if (adapter.OperationalStatus == OperationalStatus.Up)' in available and 'foreach (NetworkInterface adapter in GetAllNetworkInterfaces())' in available,
          'the runtime\'s loop outside Windows, over the snapshot; the runtime\'s call on Windows')
    snapshot = member(helpers, 'public static NetworkInterface[] GetAllNetworkInterfaces()')
    check('lock (_snapshotLock)' in snapshot and 'now - _snapshotAt >= SnapshotMilliseconds' in snapshot and
          snapshot.count('NetworkInterface.GetAllNetworkInterfaces()') == 1 and 'public const long SnapshotMilliseconds = 5000;' in helpers,
          'one enumeration for 5 s, under a lock')
    search = member(helpers, 'public static (IPInterfaceProperties, UnicastIPAddressInformation) GetLocalInterface(string lanInterfaceId = "0")')
    old_search = member(helpers_control, 'public static (IPInterfaceProperties, UnicastIPAddressInformation) GetLocalInterface(string lanInterfaceId = "0")')
    check(re.search(r'if \(lanInterfaceId == "0" && !OperatingSystem\.IsWindows\(\) && !File\.Exists\(ResolverConfiguration\)\)\s*\{\s*return \(null, null\);', search)
          is not None and 'private const string ResolverConfiguration = "/etc/resolv.conf";' in helpers,
          'the shortcut: no interface named, outside Windows, no resolver file: "none"')
    tail = lambda text: text[text.index('            IPInterfaceProperties targetProperties = null;'):]
    check(tail(search).replace('GetAllNetworkInterfaces();', 'NetworkInterface.GetAllNetworkInterfaces();', 1).replace(
        'NetworkInterface.NetworkInterface.', 'NetworkInterface.') == tail(old_search),
          'the search itself is unchanged (over the snapshot)')
    check(member(helpers, 'private static (IPInterfaceProperties, UnicastIPAddressInformation) GetLocalInterface(NetworkInterface adapter, bool isPreferred)') ==
          member(helpers_control, 'private static (IPInterfaceProperties, UnicastIPAddressInformation) GetLocalInterface(NetworkInterface adapter, bool isPreferred)'),
          'the per-interface condition (a gateway and a DNS address, or the interface named) is unchanged')
    for path in ('src/Ryujinx.HLE/HOS/Services/Sockets/Sfdnsres/IResolver.cs', 'src/Ryujinx.HLE/HOS/Services/Sockets/Sfdnsres/Proxy/DnsMitmResolver.cs',
                 'src/Ryujinx.HLE/HOS/Services/Sockets/Bsd/IClient.cs', 'src/Ryujinx.HLE/EmbeddedOnline.cs',
                 'src/Ryujinx.HLE/HOS/Services/Ssl/SslService/SslManagedSocketConnection.cs'):
        check((work / path).read_bytes() == (SOURCE / path).read_bytes() == (FINAL_SOURCE / path).read_bytes(), 'not touched: ' + path)
        check('NetworkHelpers.GetAllNetworkInterfaces' not in (work / path).read_text(encoding='utf-8-sig'), 'no new reader: ' + path)

    # --- built ---
    use_authenticated_libhac_feed(work, ROOT)
    out = run([DOTNET, 'build', str(work / 'src/Ryujinx.HLE/Ryujinx.HLE.csproj'), '-c', 'Release', '-nologo', '-m:1', '-p:NuGetAudit=false'],
              work, environment, timeout=3000).stdout
    warned = sorted(set(line.strip()[:200] for line in out.splitlines() if ': warning ' in line and
                        ('NetworkHelpers.cs' in line or 'IGeneralService.cs' in line)))
    check(not warned, 'no warning in the edited files: %s' % warned[:2])
    shutil.rmtree(work)

    # --- executed ---
    shim = temporary / 'hide.so'
    run(['cc', '-shared', '-fPIC', '-O2', '-o', str(shim), str(FIXTURE / 'HideResolvConf.c'), '-ldl'], temporary, environment, timeout=300)
    for variant in ('control', 'candidate'):
        fixture = temporary / ('fixture-' + variant)
        fixture.mkdir()
        shutil.copyfile(FIXTURE / 'Program.cs', fixture / 'Program.cs')
        (fixture / 'NetworkHelpers.cs').write_text(texts[HELPERS][0 if variant == 'control' else 1], encoding='utf-8')
        (fixture / 'Probe.csproj').write_text(
            '<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><OutputType>Exe</OutputType><TargetFramework>net10.0</TargetFramework>'
            '<Nullable>disable</Nullable><NuGetAudit>false</NuGetAudit><NoWarn>CA1416</NoWarn><DefineConstants>$(DefineConstants)' +
            (';CANDIDATE' if variant == 'candidate' else '') + '</DefineConstants></PropertyGroup></Project>\n')
        run([DOTNET, 'build', 'Probe.csproj', '-c', 'Release', '-nologo', '-v', 'q'], fixture, environment, timeout=900)
        for resolver in ('hidden', 'present'):
            env = dict(environment, LD_PRELOAD=str(shim)) if resolver == 'hidden' else environment
            result = run([DOTNET, str(fixture / 'bin/Release/net10.0/Probe.dll'), variant], temporary, env, timeout=300)
            report = json.loads(next(line for line in result.stdout.splitlines() if line.startswith('{')))
            if resolver == 'hidden':
                report['shim'] = json.loads(next(line for line in result.stderr.splitlines() if line.startswith('{"hiddenOpensAndStats"')))
            reports[variant + '-' + resolver] = report
            print(json.dumps(report)[:800], flush=True)

ch, kh, cp, kp = reports['control-hidden'], reports['candidate-hidden'], reports['control-present'], reports['candidate-present']
check(not ch['resolverPresent'] and not kh['resolverPresent'] and cp['resolverPresent'] and kp['resolverPresent'] and
      ch['shim']['hiddenOpensAndStats'] > 0, 'the shim hides the resolver file, only where asked')
check(ch['fileNotFound'] >= ch['calls'] * 2 and ch['exceptions'] == ch['fileNotFound'],
      'control, no resolver file: every request throws (%d FileNotFoundException for %d requests)' % (ch['fileNotFound'], ch['calls']))
check(kh['enumerations'] <= kh['elapsedMs'] // 5000 + 1 and kh['fileNotFound'] <= 2 * kh['enumerations'] and kh['exceptions'] == kh['fileNotFound'],
      'candidate: one enumeration per 5 s (%d in %d ms), %d exceptions' % (kh['enumerations'], kh['elapsedMs'], kh['exceptions']))
check(ch['parallelExceptions'] >= 400 and kh['parallelExceptions'] == 0,
      '400 requests from 8 threads: %d exceptions, then %d' % (ch['parallelExceptions'], kh['parallelExceptions']))
check(cp['exceptions'] == kp['exceptions'] == 0, 'with the resolver file: no exception either way')
for resolver in ('hidden', 'present'):
    c, k = reports['control-' + resolver], reports['candidate-' + resolver]
    check(c['answers'] == k['answers'] and c['parallelAnswers'] == k['parallelAnswers'] == c['answers'] and len(c['answers']) == 1 and
          c['runtimeAvailable'] == k['runtimeAvailable'] and c['interfaces'] == k['interfaces'],
          resolver + ': the same answers: %s / %s' % (c['answers'], k['answers']))
    check(k['answers'][0].startswith('up|' if k['runtimeAvailable'] else 'down|'), resolver + ': availability as the runtime answers it')
    check(k['sameSnapshot'] and k['refreshed'], resolver + ': one snapshot for 5 s, a fresh one after')
check(kh['answers'] == ['up|none'] and kp['answers'][0] != 'up|none',
      'no resolver file: no interface has a DNS address, so "none", as the control answers (with the file, this host\'s interface)')

inputs = ['build-utils/melonx/adapt_network_interface_snapshot.py', 'build-utils/melonx/adapt_session.py',
          'test/melonx_network_interface_snapshot_test.py', 'test/melonx_network_interface_snapshot/Program.cs',
          'test/melonx_network_interface_snapshot/HideResolvConf.c']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION, sourceKind='finalPreparationWithReversedControl',
               physicalDeviceTested=False, productionAssemblyBuilt='Ryujinx.HLE',
               postimages={p: hashlib.sha256((FINAL_SOURCE / p).read_bytes()).hexdigest() for p in BASELINE},
               sourceBaseline=BASELINE, reports=reports, sdk=sdk,
               inputs={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in inputs},
               limitation='Host run on Linux (the runtime reads /etc/resolv.conf once per enumeration here, twice per interface on iOS): '
                          'host counts. The device count is read from the Vulkan detail lines\' exceptions of the next build.')
out = ROOT / 'dist/melonx/network-interface-snapshot-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk)))
