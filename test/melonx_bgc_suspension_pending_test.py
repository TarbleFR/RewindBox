#!/usr/bin/env python3
"""adapt_bgc_suspension_pending, before and after, on the real NativeAOT 10.0.0 runtime of this host.

Usage: melonx_bgc_suspension_pending_test.py <final preparation containing the adapter>
       melonx_bgc_suspension_pending_test.py <control> --candidate-source <final preparation containing the adapter>

Control is the preparation with the adapter reversed (melonx_adapter_control): RewindBoxRuntimeYield.c as
adapt_runtime_yield wrote it. Candidate is the adapter applied to it, which must be the given tree's file byte for byte.

Static: the adapter edits that C file only, by two insertions (the flag's declaration with a second marker, and the
block at the top of sched_yield); the yield's own branch is the control's text; a second application is refused.
Executed, stand-ins (this host's clang): the flag's value and the call made for the eight combinations of thread
suspension, background collection and flag, control and candidate.
Executed, the real project target: the RewindBoxRuntimeYield target of the tree's Ryujinx.Library.csproj, run by
MSBuild in a stub that provides the two NativeAOT targets it hooks, compiles the candidate file for ios-arm64 and
iossimulator-arm64; each object defines sched_yield and the two markers and needs only the two traps and the three
runtime flags; a Mach-O link (ld64.lld, stand-in caller) imports the two traps, no sched_yield, and keeps both markers
through dead stripping.
Executed, the real runtime (test/melonx_bgc_suspension_pending): a NativeAOT linux-x64 executable is published twice
from the official 10.0.0 runtime pack, with the control's and the candidate's C file among its link inputs (the file
as it is in each tree; only the Mach-O label of gc_background_running takes its ELF spelling; the two Mach traps are
the kernel's sched_yield). 400 MiB of live linked objects and 128 MiB of large ones, two threads allocating small
objects and 256 KiB arrays, a background gen2 requested every 2 s:
- control: ephemeral collections of 250 ms or more that promote under 16 MiB (the wait for the background
  collector), at least three, the longest 400 ms or more; the collector's flag never read above zero;
- candidate (two runs): none of 250 ms, the longest under a third of the control's, less than half its stopped time
  (the allocating threads' iterations are recorded, not required: they vary with the host's load); the flag up in at least 80 % of the samples taken during a background
  collection; at least ten suspensions begun inside a background collection, the longest stop there under a third of
  the control's; the object graph intact;
- candidate with the collector's heap verification (DOTNET_HeapVerify=1, 48 MiB live): foreground collections inside
  background ones, verified at entry and exit, the process ends normally with its graph intact (the same run without
  the variable shows the verification is what slows it);
- no allocating thread, six background gen2s: the candidate's processor time against the control's (the mode changes
  at each allow_fgc), at most 1.35 times plus 300 ms.
Not executed here: the NativeAOT link for iOS (macOS only; the link fails there if the runtime lacks the flag), the
segments build of the collector that iOS uses (this host's pack is the regions build of the same gc.cpp), and anything
on a device. Writes dist/melonx/bgc-suspension-pending-checks.json.
"""
from pathlib import Path
import difflib, hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
FINAL_SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
SOURCE, FINAL_PREPARATION = control_source(FINAL_SOURCE, 'adapt_bgc_suspension_pending', _HOLD)
import adapt_bgc_suspension_pending as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
FIXTURE = ROOT / 'test/melonx_bgc_suspension_pending'
PROJECT = 'src/Ryujinx.Library/Ryujinx.Library.csproj'
TRIPLES = {'ios-arm64': 'arm64-apple-ios12.2-macho', 'iossimulator-arm64': 'arm64-apple-ios14.0-simulator'}
MACH_FLAG = '__ZN3WKS7gc_heap21gc_background_runningE'
LOAD = ['load', '16', '400', '2000']
VERIFIED = ['load', '12', '48', '1500']
QUIET = ['quiet', '6', '400', '2500']
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise SystemExit('FAILED: ' + message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def tool(*names):
    for name in names:
        found = shutil.which(name)
        if found:
            return found
    raise SystemExit('FAILED: none of ' + ', '.join(names) + ' on this host')


def run(arguments, cwd, expect=0, env=None, timeout=900):
    result = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                            env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', **(env or {})))
    if (result.returncode == 0) != (expect == 0):
        print(result.stdout[-4000:], result.stderr[-2000:], flush=True)
    return result


def fields(text, prefix):
    lines = [line for line in text.split('\n') if line.startswith(prefix + ' ')]
    if len(lines) != 1:
        raise SystemExit('FAILED: no single ' + prefix + ' line: ' + text[-600:])
    values = {}
    for part in lines[0].split()[1:]:
        key, _, value = part.partition('=')
        try:
            values[key] = float(value) if '.' in value else int(value)
        except ValueError:
            values[key] = value
    return values


CLANG, NM, LLD = tool('clang', 'clang-18'), tool('llvm-nm', 'llvm-nm-18'), tool('ld64.lld', 'ld64.lld-18')
check(sha(SOURCE / adapter.C_FILE) == adapter.BASELINE[adapter.C_FILE], 'the control C file is the pinned preparation')
control_text = (SOURCE / adapter.C_FILE).read_text()
with tempfile.TemporaryDirectory(prefix='melonx-bgc-suspension-pending-') as temporary:
    work = Path(temporary).resolve()
    applied = work / 'applied'
    (applied / adapter.C_FILE).parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / adapter.C_FILE, applied / adapter.C_FILE)
    changed = adapter.apply(applied)
    check([path.relative_to(applied).as_posix() for path in changed] == [adapter.C_FILE] and list(adapter.BASELINE) == [adapter.C_FILE],
          'the adapter edits the C file only')
    candidate_text = (applied / adapter.C_FILE).read_text()
    if FINAL_PREPARATION:
        check((FINAL_SOURCE / adapter.C_FILE).read_bytes() == (applied / adapter.C_FILE).read_bytes(), 'the given tree holds the adapter postimage')
        check(sha(FINAL_SOURCE / PROJECT) == sha(SOURCE / PROJECT), 'the project is the control\'s')
    try:
        adapter.apply(applied)
        second = None
    except AssertionError as error:
        second = error
    check(second is not None, 'a second application is refused')
    # Two insertions, nothing removed.
    blocks = [block for block in difflib.SequenceMatcher(None, control_text.split('\n'), candidate_text.split('\n'), autojunk=False).get_opcodes() if block[0] != 'equal']
    check([block[0] for block in blocks] == ['insert', 'insert'] and
          sum(block[4] - block[3] for block in blocks) == (adapter.DECLARATION_NEW.count('\n') - adapter.DECLARATION_OLD.count('\n')) +
          (adapter.BODY_NEW.count('\n') - adapter.BODY_OLD.count('\n')), 'the candidate is the control plus two insertions: ' + str(blocks))
    check(candidate_text.replace(adapter.BODY_NEW, adapter.BODY_OLD).replace(adapter.DECLARATION_NEW, adapter.DECLARATION_OLD) == control_text,
          'the two replacements reversed give the control')
    yield_branch = '''    if (RhpTrapThreads != 0u || rewindbox_gc_background_running != 0) {
        /* What sched_yield of the system library does. */
        (void)swtch_pri(0);
    } else {
        /* MACH_PORT_NULL, SWITCH_OPTION_NONE, no time. */
        (void)thread_switch(0u, 0, 0u);
    }
    return 0;
}
'''
    check(control_text.endswith(yield_branch) and candidate_text.endswith(yield_branch), 'the yield\'s own branch is the control\'s text')
    block = candidate_text[candidate_text.index('int sched_yield(void)\n{\n'):candidate_text.index(yield_branch)]
    statements = [line.strip() for line in block.split('\n') if line.strip() and not line.strip().startswith(('/*', '*'))]
    check(statements == ['int sched_yield(void)', '{', 'if (rewindbox_gc_background_running != 0) {', 'if (g_fSuspensionPending == 0) {',
                         'g_fSuspensionPending = 1;', '}', '} else if (g_fSuspensionPending != 0) {', 'g_fSuspensionPending = 0;',
                         'if (rewindbox_gc_background_running != 0) {', 'g_fSuspensionPending = 1;', '}', '}'],
          'the flag follows the background collection, with the second read after a write of 0: ' + str(statements))
    check('#include' not in candidate_text and candidate_text.count('extern volatile int g_fSuspensionPending;') == 1 and
          'g_fSuspensionPending' not in control_text and candidate_text.count(adapter.MARKER) == 1 and adapter.MARKER not in control_text and
          candidate_text.count('RewindBox runtime yield 1: sched_yield is thread_switch(0, 0, 0) outside thread suspension and background collection') == 1 and
          candidate_text.count('extern volatile int rewindbox_gc_background_running __asm__("' + MACH_FLAG + '");') == 1,
          'the flag is declared as the collector defines it, with a second marker beside the first')

    # The flag and the call, for every combination, on stand-ins.
    host = work / 'host'
    host.mkdir()
    (host / 'harness.c').write_text('''#include <stdio.h>
volatile unsigned int RhpTrapThreads;
volatile int background __asm__("''' + MACH_FLAG + '''");
volatile int g_fSuspensionPending;
static int switches, depressions;
int thread_switch(unsigned int thread_name, int thread_option, unsigned int option_time) { switches++; return 0; }
int swtch_pri(int pri) { depressions++; return 0; }
int sched_yield(void);
int main(void)
{
    for (unsigned int trap = 0; trap < 2; trap++)
        for (int collecting = 0; collecting < 2; collecting++)
            for (int flag = 0; flag < 2; flag++) {
                RhpTrapThreads = trap; background = collecting; g_fSuspensionPending = flag; switches = depressions = 0;
                int result = sched_yield();
                printf("%u %d %d: %d %d %d %d\\n", trap, collecting, flag, (int)g_fSuspensionPending, switches, depressions, result);
            }
    return 0;
}
''')
    tables = {}
    for name, text in (('control', control_text), ('candidate', candidate_text)):
        (host / (name + '.c')).write_text(text)
        check(run([CLANG, '-O2', '-Wall', '-Werror', 'harness.c', name + '.c', '-o', name], host).returncode == 0, 'the C file builds for this host: ' + name)
        tables[name] = run([str(host / name)], host).stdout.split('\n')[:8]
    # trap background flag: flag after, thread_switch calls, swtch_pri calls, result
    check(tables['control'] == ['0 0 0: 0 1 0 0', '0 0 1: 1 1 0 0', '0 1 0: 0 0 1 0', '0 1 1: 1 0 1 0',
                                '1 0 0: 0 0 1 0', '1 0 1: 1 0 1 0', '1 1 0: 0 0 1 0', '1 1 1: 1 0 1 0'],
          'control: the flag is never written: ' + str(tables['control']))
    check(tables['candidate'] == ['0 0 0: 0 1 0 0', '0 0 1: 0 1 0 0', '0 1 0: 1 0 1 0', '0 1 1: 1 0 1 0',
                                  '1 0 0: 0 0 1 0', '1 0 1: 0 0 1 0', '1 1 0: 1 0 1 0', '1 1 1: 1 0 1 0'],
          'candidate: the flag is 1 with a background collection and 0 without, the call is the control\'s: ' + str(tables['candidate']))

    # The real target of the tree's project, for the two iOS runtime identifiers.
    project_text = (FINAL_SOURCE / PROJECT).read_text(encoding='utf-8-sig')
    start = project_text.index('  <Target Name="RewindBoxRuntimeYield"')
    target = project_text[start:project_text.index('</Target>', start) + len('</Target>')]
    check(target.count('<Exec Command=') == 1 and target.count('<LinkerArg Include=') == 1 and 'RewindBoxRuntimeYield.c' in target,
          'the project compiles and links that C file in one target')
    stub = work / 'stub'
    stub.mkdir()
    shutil.copyfile(applied / adapter.C_FILE, stub / 'RewindBoxRuntimeYield.c')
    conditions = ''.join(f'''      <TargetTriple Condition=" '$(RuntimeIdentifier)' == '{rid}' ">{triple}</TargetTriple>\n''' for rid, triple in TRIPLES.items())
    (stub / 'stub.proj').write_text('''<Project>
  <PropertyGroup>
    <IntermediateOutputPath>obj\\Release\\net10.0\\$(RuntimeIdentifier)\\</IntermediateOutputPath>
    <CppLinker>''' + CLANG + '''</CppLinker>
  </PropertyGroup>
  <Target Name="SetupOSSpecificProps">
    <PropertyGroup>
''' + conditions + '''    </PropertyGroup>
  </Target>
  <Target Name="LinkNative" DependsOnTargets="SetupOSSpecificProps" />
''' + target + '\n</Project>\n')
    objects = {}
    for rid, triple in TRIPLES.items():
        check(run([DOTNET, 'msbuild', 'stub.proj', '-t:LinkNative', f'-p:RuntimeIdentifier={rid}', '-v:m', '-nologo'], stub).returncode == 0,
              'the project\'s target compiles the candidate for ' + rid)
        produced = stub / 'obj/Release/net10.0' / rid / 'RewindBoxRuntimeYield.o'
        symbols = run([NM, str(produced)], stub).stdout.split('\n')
        defined = sorted(line.split()[-1] for line in symbols if ' T ' in line or ' S ' in line)
        undefined = sorted(line.split()[-1] for line in symbols if line.strip().startswith('U '))
        check(defined == ['_rewindbox_runtime_yield_marker', '_rewindbox_suspension_pending_marker', '_sched_yield'] and
              undefined == sorted(['_RhpTrapThreads', MACH_FLAG, '_g_fSuspensionPending', '_swtch_pri', '_thread_switch']),
              f'the object defines sched_yield and the two markers, and needs only the two traps and the three flags: {rid} {defined} {undefined}')
        objects[rid] = dict(triple=triple, sha256=sha(produced), bytes=produced.stat().st_size)
    link = work / 'link'
    link.mkdir()
    (link / 'caller.c').write_text('extern int sched_yield(void);\nvolatile unsigned int RhpTrapThreads;\nvolatile int g_fSuspensionPending;\n'
                                   'volatile int background __asm__("' + MACH_FLAG + '");\n'
                                   'int pal_switch_to_thread(void) { sched_yield(); return 0; }\n')
    (link / 'libSystem.tbd').write_text('''--- !tapi-tbd
tbd-version: 4
targets: [ arm64-ios ]
install-name: '/usr/lib/libSystem.B.dylib'
current-version: 1
exports:
  - targets: [ arm64-ios ]
    symbols: [ _sched_yield, _thread_switch, _swtch_pri, dyld_stub_binder ]
...
''')
    (link / 'exports.txt').write_text('_pal_switch_to_thread\n')
    (link / 'control.c').write_text(control_text)
    check(run([CLANG, '--target=' + TRIPLES['ios-arm64'], '-O2', '-c', 'caller.c', '-o', 'caller.o'], link).returncode == 0 and
          run([CLANG, '--target=' + TRIPLES['ios-arm64'], '-O2', '-Wall', '-c', 'control.c', '-o', 'control.o'], link).returncode == 0, 'the caller and the control compile')
    common = [LLD, '-dylib', '-arch', 'arm64', '-platform_version', 'ios', '12.2', '12.2', '-exported_symbols_list', 'exports.txt', '-dead_strip', 'caller.o']
    check(run([*common, 'control.o', 'libSystem.tbd', '-o', 'control.dylib'], link).returncode == 0 and
          run([*common, str(stub / 'obj/Release/net10.0/ios-arm64/RewindBoxRuntimeYield.o'), 'libSystem.tbd', '-o', 'candidate.dylib'], link).returncode == 0,
          'the control and the candidate link (Mach-O)')
    imports = {name: sorted(run([NM, '-u', name + '.dylib'], link).stdout.split()) for name in ('control', 'candidate')}
    check(all('_sched_yield' not in imports[name] and '_thread_switch' in imports[name] and '_swtch_pri' in imports[name] for name in imports) and
          imports['control'] == imports['candidate'], 'the candidate imports what the control does: ' + str(imports))
    yield_marker = b'RewindBox runtime yield 1: sched_yield is thread_switch(0, 0, 0) outside thread suspension and background collection'
    images = {name: (link / (name + '.dylib')).read_bytes() for name in ('control', 'candidate')}
    check(yield_marker in images['control'] and yield_marker in images['candidate'] and adapter.MARKER.encode() in images['candidate'] and
          adapter.MARKER.encode() not in images['control'], 'both markers survive dead stripping in the candidate')

    # The real runtime: NativeAOT 10.0.0, official pack, with each tree's C file among the link inputs.
    native = work / 'native'
    native.mkdir()
    check(run([CLANG, '-O2', '-Wall', '-Werror', '-c', str(FIXTURE / 'HostShims.c'), '-o', 'HostShims.o'], native).returncode == 0, 'the host stand-ins compile')
    executables = {}
    for name, text in (('control', control_text), ('candidate', candidate_text)):
        check(text.count('"' + MACH_FLAG + '"') == 1, 'one Mach-O label to respell: ' + name)
        (native / (name + '.c')).write_text(text.replace('"' + MACH_FLAG + '"', '"' + MACH_FLAG[1:] + '"'))
        check(run([CLANG, '-O2', '-Wall', '-Werror', '-c', name + '.c', '-o', name + '.o'], native).returncode == 0, 'the C file compiles for linux-x64: ' + name)
        probe = work / ('probe-' + name)
        shutil.copytree(FIXTURE / 'Probe', probe, ignore=shutil.ignore_patterns('bin', 'obj'))
        published = run([DOTNET, 'publish', 'Probe.csproj', '-c', 'Release', '-o', str(work / ('out-' + name)), '--nologo', '-v', 'q',
                         f'-p:ProbeYieldObject={native / (name + ".o")}', f'-p:ProbeShimObject={native / "HostShims.o"}'], probe)
        check(published.returncode == 0 and (work / ('out-' + name) / 'Probe').is_file(), 'the NativeAOT executable is published: ' + name)
        executables[name] = str(work / ('out-' + name) / 'Probe')
        linked = run([NM, executables[name][:-len('Probe')] + 'Probe.dbg'], native).stdout if (work / ('out-' + name) / 'Probe.dbg').is_file() else run([NM, executables[name]], native).stdout
        names = {line.split()[-1]: line.split()[-2] for line in linked.split('\n') if len(line.split()) >= 3}
        check(names.get('sched_yield') in ('t', 'T') and names.get('swtch_pri') in ('t', 'T') and names.get('g_fSuspensionPending') in ('b', 'B') and
              names.get(MACH_FLAG[1:]) in ('b', 'B') and names.get('RhpTrapThreads') in ('b', 'B'),
              'the executable holds the Core\'s sched_yield and the runtime\'s three flags: ' + name)
        shutil.rmtree(probe, ignore_errors=True)

    def measure(name, arguments, env=None):
        result = run([executables[name], *arguments], work, env=env, timeout=300)
        check(result.returncode == 0, f'{name} {" ".join(arguments)} ends normally (exit {result.returncode}): ' + result.stderr[-300:])
        values = fields(result.stdout, 'RESULT')
        values.update(fields(result.stderr, 'SHIM'))
        values['long'] = [line for line in result.stdout.split('\n') if line.startswith('LONG')][:1]
        return values

    control = measure('control', LOAD)
    check(control['badNodes'] == 0 and control['afterOver250SmallPromotion'] >= 3 and control['afterMaxMs'] >= 400,
          'control: ephemeral collections wait for the background collector: ' + str(control))
    check(control['flagSeen'] == 0 and control['swtchPriWithFlag'] == 0 and control['threadSwitchWithFlag'] == 0 and control['backgroundSamplesWithFlag'] == 0 and
          control['backgroundSamples'] > 100, 'control: the runtime never raises the flag: ' + str(control))
    check(control['longestInsideMs'] >= 400, 'control: the engine\'s threads are held for the wait: ' + str(control))
    candidates = [measure('candidate', LOAD) for _ in range(2)]
    for candidate in candidates:
        check(candidate['badNodes'] == 0 and candidate['afterOver250'] == 0 and candidate['afterMaxMs'] * 3 < control['afterMaxMs'],
              'candidate: no ephemeral collection waits for the background collector: ' + str(candidate))
        check(candidate['afterSumMs'] * 2 < control['afterSumMs'],
              'candidate: less than half the stopped time: ' + str(candidate))
        check(candidate['flagSeen'] == 1 and candidate['backgroundSamples'] > 100 and
              candidate['backgroundSamplesWithFlag'] >= 0.8 * candidate['backgroundSamples'] and candidate['threadSwitchWithFlag'] <= 3,
              'candidate: the flag is up while a background collection runs: ' + str(candidate))
        check(candidate['suspensionsInsideBackground'] >= 10 and candidate['longestInsideMs'] * 3 < control['longestInsideMs'],
              'candidate: foreground collections run inside the background one, none held long: ' + str(candidate))
    plain = measure('candidate', VERIFIED)
    verified = measure('candidate', VERIFIED, env=dict(DOTNET_HeapVerify='1'))
    check(verified['badNodes'] == 0 and verified['afterSeen'] >= 5 and verified['suspensionsInsideBackground'] >= 3 and verified['flagSeen'] == 1,
          'candidate, heap verification on: foreground collections inside background ones, the graph intact: ' + str(verified))
    check(verified['afterMedianMs'] >= 2 * plain['afterMedianMs'], f'the verification runs (median pause {plain["afterMedianMs"]} -> {verified["afterMedianMs"]} ms)')
    quiet = {name: measure(name, QUIET) for name in ('control', 'candidate')}
    check(quiet['candidate']['badNodes'] == 0 and quiet['candidate']['cpuMs'] <= 1.35 * quiet['control']['cpuMs'] + 300,
          'the background collector\'s processor time stays within bounds: ' + str(quiet))

inputs = ['build-utils/melonx/adapt_bgc_suspension_pending.py', 'build-utils/melonx/adapt_session.py', 'test/melonx_bgc_suspension_pending_test.py',
          'test/melonx_bgc_suspension_pending/HostShims.c', 'test/melonx_bgc_suspension_pending/Probe/Program.cs',
          'test/melonx_bgc_suspension_pending/Probe/Probe.csproj', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
keep = ('afterSeen', 'afterSumMs', 'afterMedianMs', 'afterMaxMs', 'afterOver100', 'afterOver250', 'afterOver250SmallPromotion', 'allocatorMaxStallMs',
        'requests', 'backgroundRecords', 'fullBlocking', 'loops', 'badNodes', 'flagSeen', 'suspensionsInsideBackground', 'longestInsideMs',
        'backgroundSamples', 'backgroundSamplesWithFlag', 'swtchPri', 'swtchPriWithFlag', 'threadSwitch', 'threadSwitchWithFlag')
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'predecessorPreparation',
               postimages={adapter.C_FILE: sha(FINAL_SOURCE / adapter.C_FILE)} if FINAL_PREPARATION else {},
               sdk=sdk, runtime='NativeAOT 10.0.0 linux-x64, official runtime pack, workstation concurrent', physicalDeviceTested=False,
               sourceBaseline=adapter.BASELINE, objects=objects,
               load=dict(arguments=LOAD, control={key: control[key] for key in keep}, candidate=[{key: run_[key] for key in keep} for run_ in candidates]),
               heapVerification=dict(arguments=VERIFIED, without={key: plain[key] for key in keep}, withVerification={key: verified[key] for key in keep}),
               quiet=dict(arguments=QUIET, control=dict(cpuMs=quiet['control']['cpuMs'], gen2=quiet['control']['gen2']),
                          candidate=dict(cpuMs=quiet['candidate']['cpuMs'], gen2=quiet['candidate']['gen2'])),
               nativeAotLinkForIosExecuted=False, collectorBuildOnHost='regions', collectorBuildOnDevice='segments',
               inputs={path: sha(ROOT / path) for path in inputs},
               limitation='Host: the regions build of gc.cpp on linux-x64. The iOS link runs on macOS only and the device uses the segments build '
                          'of the same file; the effect on the iPhone is read from the next build\'s gcPause lines.')
out = ROOT / 'dist/melonx/bgc-suspension-pending-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, control=receipt['load']['control'], candidate=receipt['load']['candidate'],
                      heapVerification=receipt['heapVerification']['withVerification'], quiet=receipt['quiet'])))
