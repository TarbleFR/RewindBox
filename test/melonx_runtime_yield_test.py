#!/usr/bin/env python3
"""adapt_runtime_yield on the final preparation, against its predecessor as control.

Usage: melonx_runtime_yield_test.py <predecessor preparation> [--candidate-source <final preparation containing the adapter>]

IPA 759 / Core 127b72b9, Hogwarts Legacy: 97 of 640 and 109 of 753 running samples of the six busiest threads in
swtch_pri under the runtime's own Thread.Yield (Lock.TryEnterSlow, LowLevelLock.WaitAndAcquire) in the two profiles
taken under 26 FPS, one in each of the two taken at 30 FPS. On Apple platforms sched_yield is swtch_pri(0).

Static: only Ryujinx.Library.csproj changes, by exactly the adapter's target before the closing tag, and
RewindBoxRuntimeYield.c is the adapter's text; the C file defines a hidden sched_yield that returns 0 after
swtch_pri(0), the system library's own yield, while the runtime's RhpTrapThreads (threads being stopped or stopped)
or the collector's gc_background_running (a background collection) is not zero, and after thread_switch with no
thread, no option and no time otherwise; build_core.sh refuses a library that still imports sched_yield, does not
import thread_switch and swtch_pri, or lacks the marker.
Executed with this host's clang, llvm-nm and Mach-O lld (no Apple SDK is read: the C file includes nothing): the C
file built for this host with stand-ins of the two calls and of the two flags makes each call with its arguments
under the flags' values; the final project's target, taken out of the project into a stub that provides the two
NativeAOT targets it hooks, is run by MSBuild for ios-arm64 and iossimulator-arm64 and is refused for another runtime
identifier; each object defines _sched_yield and leaves only the two calls and the two flags undefined; a dylib
linked from a caller of sched_yield that holds the flags, that object and a stub libSystem imports _thread_switch and
_swtch_pri and no longer _sched_yield (the control link, without the object, imports _sched_yield), exports nothing
more, and keeps the marker through dead stripping.
Not executed here: the NativeAOT link on macOS (build_core.sh checks its result) and anything on a device. What it
changes on the iPhone is read from the next IPA's [MeloNX:hot] lines.
Writes dist/melonx/runtime-yield-checks.json.
"""
from pathlib import Path
import hashlib, json, os, shutil, subprocess, sys, tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
SOURCE = Path(sys.argv[sys.argv.index('--candidate-source') + 1] if '--candidate-source' in sys.argv else sys.argv[1]).resolve()
sys.path.insert(0, str(ROOT / 'build-utils/melonx'))
sys.path.insert(0, str(ROOT / 'test'))
from melonx_adapter_control import control_source  # noqa: E402
_HOLD = []
FINAL_SOURCE = SOURCE
SOURCE, FINAL_PREPARATION = control_source(SOURCE, 'adapt_runtime_yield', _HOLD)
import adapt_runtime_yield as adapter  # noqa: E402

DOTNET = os.environ.get('DOTNET', 'dotnet')
TRIPLES = {'ios-arm64': 'arm64-apple-ios12.2-macho', 'iossimulator-arm64': 'arm64-apple-ios14.0-simulator'}
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


def run(arguments, cwd, expect=0):
    result = subprocess.run(arguments, cwd=cwd, capture_output=True, text=True, timeout=600,
                            env=dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1'))
    if (result.returncode == 0) != (expect == 0):
        print(result.stdout[-4000:], result.stderr[-2000:], flush=True)
    return result


CLANG, NM, LLD = tool('clang', 'clang-18'), tool('llvm-nm', 'llvm-nm-18'), tool('ld64.lld', 'ld64.lld-18')
check(sha(SOURCE / adapter.PROJECT) == adapter.BASELINE[adapter.PROJECT], 'the control project is the pinned preparation')
with tempfile.TemporaryDirectory(prefix='melonx-runtime-yield-') as temporary:
    work = Path(temporary).resolve()
    applied = work / 'applied'
    (applied / adapter.PROJECT).parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / adapter.PROJECT, applied / adapter.PROJECT)
    before = (applied / adapter.PROJECT).read_text(encoding='utf-8-sig')
    changed = adapter.apply(applied)
    check([path.relative_to(applied).as_posix() for path in changed] == [adapter.PROJECT, adapter.C_FILE], 'the adapter edits the project and writes the C file')
    after = (applied / adapter.PROJECT).read_text(encoding='utf-8-sig')
    check(before.count(adapter.TAIL) == 1 and before.rstrip().endswith(adapter.TAIL) and
          after == before.replace(adapter.TAIL, adapter.TAIL[:-len('</Project>')] + adapter.TARGET) and
          after.replace(adapter.TARGET, '</Project>') == before,
          'the project gains exactly the target before its closing tag')
    c_source = (applied / adapter.C_FILE).read_text()
    check(c_source == adapter.C_SOURCE, 'the C file is the adapter text')
    if FINAL_PREPARATION:
        check((FINAL_SOURCE / adapter.PROJECT).read_bytes() == (applied / adapter.PROJECT).read_bytes() and
              (FINAL_SOURCE / adapter.C_FILE).read_bytes() == (applied / adapter.C_FILE).read_bytes(),
              'the final preparation holds the adapter postimages')
    try:
        adapter.apply(applied)
        second = None
    except AssertionError as error:
        second = error
    check(second is not None, 'a second application is refused')
    check('#include' not in c_source and c_source.count('int sched_yield(void)') == 1 and
          c_source.count('(void)thread_switch(0u, 0, 0u);') == 1 and c_source.count('(void)swtch_pri(0);') == 1 and
          c_source.count('if (RhpTrapThreads != 0u || rewindbox_gc_background_running != 0) {') == 1 and
          c_source.count('extern volatile unsigned int RhpTrapThreads;') == 1 and
          c_source.count('extern volatile int rewindbox_gc_background_running __asm__("' + adapter.BACKGROUND_FLAG + '");') == 1 and
          adapter.BACKGROUND_FLAG == '__ZN3WKS7gc_heap21gc_background_runningE' and
          c_source.index('if (RhpTrapThreads != 0u || rewindbox_gc_background_running != 0) {') < c_source.index('(void)swtch_pri(0);') < c_source.index('} else {') <
          c_source.index('(void)thread_switch(0u, 0, 0u);') and c_source.count('return 0;') == 1 and
          '__attribute__((visibility("hidden")))\nint sched_yield(void)' in c_source and adapter.MARKER in c_source,
          'the C file is a hidden sched_yield: swtch_pri(0) during a suspension or a background collection, thread_switch(0, 0, 0) otherwise')
    # The branch, on this host: stand-ins of the two calls and of the runtime's two flags.
    host = work / 'host'
    host.mkdir()
    shutil.copyfile(applied / adapter.C_FILE, host / 'RewindBoxRuntimeYield.c')
    (host / 'harness.c').write_text('''#include <stdio.h>
volatile unsigned int RhpTrapThreads;
volatile int background __asm__("''' + adapter.BACKGROUND_FLAG + '''");
static int switches, depressions, option = -1, priority = -1;
static unsigned int name = 1u, time = 1u;
int thread_switch(unsigned int thread_name, int thread_option, unsigned int option_time) { switches++; name = thread_name; option = thread_option; time = option_time; return 0; }
int swtch_pri(int pri) { depressions++; priority = pri; return 0; }
int sched_yield(void);
static void state(unsigned int trap, int collecting)
{
    RhpTrapThreads = trap;
    background = collecting;
    int result = sched_yield();
    printf("%u %d: %d %d %u %d %u %d %d\\n", trap, collecting, switches, depressions, name, option, time, priority, result);
}
int main(void)
{
    state(0u, 0);
    state(1u, 0);
    state(0u, 1);
    state(2u, 1);
    state(0u, 0);
    return 0;
}
''')
    check(run([CLANG, '-O2', '-Wall', '-Werror', 'harness.c', 'RewindBoxRuntimeYield.c', '-o', 'harness'], host).returncode == 0, 'the C file builds for this host')
    branch = run([str(host / 'harness')], host).stdout.split('\n')[:5]
    check(branch == ['0 0: 1 0 0 0 0 -1 0', '1 0: 1 1 0 0 0 0 0', '0 1: 1 2 0 0 0 0 0', '2 1: 1 3 0 0 0 0 0', '0 0: 2 3 0 0 0 0 0'],
          'thread_switch(0, 0, 0) with both flags clear, swtch_pri(0) with either set, 0 returned: ' + str(branch))
    target = adapter.TARGET[:-len('</Project>')]
    check(target.count('BeforeTargets="LinkNative" DependsOnTargets="SetupOSSpecificProps"') == 1 and
          target.count('<LinkerArg Include=') == 1 and target.count('<Exec Command=') == 1 and target.count('<Error Condition=') == 5,
          'one compile, one link input, five refusals, before the native link')
    # The target as the final project holds it, in a stub that provides the two NativeAOT targets it hooks.
    project = work / 'stub'
    project.mkdir()
    shutil.copyfile(applied / adapter.C_FILE, project / 'RewindBoxRuntimeYield.c')
    conditions = ''.join(f'''      <TargetTriple Condition=" '$(RuntimeIdentifier)' == '{rid}' ">{triple}</TargetTriple>\n''' for rid, triple in TRIPLES.items())
    (project / 'stub.proj').write_text('''<Project>
  <PropertyGroup>
    <IntermediateOutputPath>obj\\Release\\net10.0\\$(RuntimeIdentifier)\\</IntermediateOutputPath>
    <CppLinker>''' + CLANG + '''</CppLinker>
  </PropertyGroup>
  <Target Name="SetupOSSpecificProps">
    <PropertyGroup>
''' + conditions + '''      <TargetTriple Condition=" '$(RuntimeIdentifier)' == 'osx-arm64' ">arm64-apple-macos12.0</TargetTriple>
    </PropertyGroup>
    <ItemGroup><LinkerArg Include="--target=$(TargetTriple)" /></ItemGroup>
  </Target>
  <Target Name="LinkNative" DependsOnTargets="SetupOSSpecificProps">
    <WriteLinesToFile File="$(MSBuildProjectDirectory)/link-$(RuntimeIdentifier).txt" Lines="@(LinkerArg)" Overwrite="true" />
  </Target>
''' + target + '</Project>\n')
    objects = {}
    for rid, triple in TRIPLES.items():
        result = run([DOTNET, 'msbuild', 'stub.proj', '-t:LinkNative', f'-p:RuntimeIdentifier={rid}', '-v:m', '-nologo'], project)
        check(result.returncode == 0, 'the target runs for ' + rid)
        produced = project / 'obj/Release/net10.0' / rid / 'RewindBoxRuntimeYield.o'
        check(produced.is_file(), 'the object is under the intermediate directory, forward slashes: ' + rid)
        lines = (project / f'link-{rid}.txt').read_text().split()
        check(lines == ['--target=' + triple, '"' + str(produced) + '"'], 'the link inputs gain exactly the object: ' + rid)
        symbols = run([NM, str(produced)], project).stdout.split('\n')
        defined = sorted(line.split()[-1] for line in symbols if ' T ' in line or ' S ' in line)
        undefined = sorted(line.split()[-1] for line in symbols if line.strip().startswith('U '))
        check(defined == ['_rewindbox_runtime_yield_marker', '_sched_yield'] and
              undefined == sorted(['_RhpTrapThreads', adapter.BACKGROUND_FLAG, '_swtch_pri', '_thread_switch']),
              f'the object defines sched_yield and the marker, and needs only the two calls and the two flags: {rid} {defined} {undefined}')
        objects[rid] = dict(triple=triple, sha256=sha(produced), bytes=produced.stat().st_size)
    refused = run([DOTNET, 'msbuild', 'stub.proj', '-t:LinkNative', '-p:RuntimeIdentifier=osx-arm64', '-v:m', '-nologo'], project, expect=1)
    check(refused.returncode != 0 and 'no reviewed target for RuntimeIdentifier' in refused.stdout + refused.stderr and
          not (project / 'obj/Release/net10.0/osx-arm64/RewindBoxRuntimeYield.o').exists(), 'another runtime identifier is refused before the compile')
    # A Mach-O link: the image's own definition replaces the import of the system library.
    link = work / 'link'
    link.mkdir()
    (link / 'caller.c').write_text('extern int sched_yield(void);\nvolatile unsigned int RhpTrapThreads;\n'
                                   'volatile int background __asm__("' + adapter.BACKGROUND_FLAG + '");\n'
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
    check(run([CLANG, '--target=' + TRIPLES['ios-arm64'], '-O2', '-c', 'caller.c', '-o', 'caller.o'], link).returncode == 0, 'the caller compiles')
    common = [LLD, '-dylib', '-arch', 'arm64', '-platform_version', 'ios', '12.2', '12.2', '-exported_symbols_list', 'exports.txt', '-dead_strip', 'caller.o']
    own = str(project / 'obj/Release/net10.0/ios-arm64/RewindBoxRuntimeYield.o')
    check(run([*common, 'libSystem.tbd', '-o', 'control.dylib'], link).returncode == 0, 'the control links')
    check(run([*common, own, 'libSystem.tbd', '-o', 'candidate.dylib'], link).returncode == 0, 'the candidate links')
    imports = {name: sorted(run([NM, '-u', name + '.dylib'], link).stdout.split()) for name in ('control', 'candidate')}
    check('_sched_yield' in imports['control'] and '_thread_switch' not in imports['control'] and '_swtch_pri' not in imports['control'],
          'the control imports sched_yield: ' + str(imports['control']))
    check('_sched_yield' not in imports['candidate'] and '_thread_switch' in imports['candidate'] and '_swtch_pri' in imports['candidate'],
          'the candidate imports thread_switch and swtch_pri and no longer sched_yield: ' + str(imports['candidate']))
    exported = sorted(line.split()[-1] for line in run([NM, '-gU', 'candidate.dylib'], link).stdout.split('\n') if line.strip())
    check(exported == ['_pal_switch_to_thread'], 'the candidate exports nothing more: ' + str(exported))
    marker = adapter.MARKER.encode()
    check(marker in (link / 'candidate.dylib').read_bytes() and marker not in (link / 'control.dylib').read_bytes(), 'the marker survives dead stripping')
build = (ROOT / 'build-utils/melonx/build_core.sh').read_text()
check(build.count('YIELD_IMPORTS="$(xcrun nm -u "$CORE")"') == 1 and build.count("_sched_yield$' <<<\"$YIELD_IMPORTS\"") == 1 and
      build.count('for YIELD_IMPORT in _thread_switch _swtch_pri; do') == 1 and
      build.count('if ! grep -Eq "(^|[[:space:]])${YIELD_IMPORT}\\$" <<<"$YIELD_IMPORTS"; then') == 1 and
      build.count("grep -aq '" + adapter.MARKER + "' \"$CORE\"") == 1 and
      build.index("'dotnet', 'publish'") < build.index('YIELD_IMPORTS=') < build.index("(root / 'dist/melonx/identity.json').write_text"),
      'build_core.sh reads the linked library before it writes the identity')
inputs = ['build-utils/melonx/adapt_runtime_yield.py', 'build-utils/melonx/adapt_session.py', 'build-utils/melonx/build_core.sh',
          'test/melonx_runtime_yield_test.py', 'test/melonx_adapter_control.py']
sdk = subprocess.run([DOTNET, '--version'], capture_output=True, text=True, check=True).stdout.strip()
receipt = dict(result='passed', checks=checks, finalPreparationBound=FINAL_PREPARATION,
               sourceKind='finalPreparationWithReversedControl' if FINAL_PREPARATION else 'predecessorPreparation',
               postimages={name: sha(FINAL_SOURCE / name) for name in (adapter.PROJECT, adapter.C_FILE)} if FINAL_PREPARATION else {},
               sdk=sdk, physicalDeviceTested=False, sourceBaseline=adapter.BASELINE, objectsBuilt=len(objects), objects=objects,
               systemImportReplaced=True, systemYieldKeptWhileThreadsStopped=True, systemYieldKeptDuringBackgroundCollection=True,
               controlImports=imports['control'],
               candidateImports=imports['candidate'],
               nativeAotLinkExecuted=False,
               inputs={path: sha(ROOT / path) for path in inputs},
               limitation='The NativeAOT link runs on macOS only (build_core.sh checks the linked library there); the link here is a '
                          'Mach-O lld link of a stand-in caller. No device: the effect is read from the next [MeloNX:hot] profiles.')
out = ROOT / 'dist/melonx/runtime-yield-checks.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(receipt, indent=2) + '\n')
print(json.dumps(dict(result='passed', checks=checks, sdk=sdk, objects=objects)))
