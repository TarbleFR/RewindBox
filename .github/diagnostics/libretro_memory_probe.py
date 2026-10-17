#!/usr/bin/env python3
"""CI-only owner/heap/VM diagnosis; production sources remain unchanged."""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'test'))
import libretro_simulator_probe as probe
import libretro_nestopia_skin_stability_probe as stability
import libretro_cheat_probe as cheats
from libretro_simulator_device import pick_notched_device

OWNERSHIP = r'''
#include <malloc/malloc.h>
static NSMutableDictionary<NSString *, NSHashTable *> *sMemoryOwners;
static id MemoryValue(id object, NSString *key) {
  if (object == nil) return nil;
  @try { return [object valueForKey:key]; }
  @catch (NSException *error) { Progress(@"memory key %@ unavailable: %@", key, error.reason); return nil; }
}
static void MemoryTrack(NSString *key, id object) {
  if (!sMemoryOwners) sMemoryOwners = [NSMutableDictionary dictionary];
  if (!sMemoryOwners[key]) sMemoryOwners[key] = [NSHashTable hashTableWithOptions:
    NSPointerFunctionsWeakMemory | NSPointerFunctionsObjectPointerPersonality];
  if (object) [sMemoryOwners[key] addObject:object];
}
static void MemoryTrackSession(LibretroSession *session) {
  MemoryTrack(@"session", session);
  for (NSString *key in @[@"controller", @"presenter", @"audio", @"host", @"input", @"cheatMenu"])
    MemoryTrack(key, MemoryValue(session, key));
  id menu = MemoryValue(session, @"cheatMenu");
  MemoryTrack(@"cheatRootPage", MemoryValue(menu, @"_rootPage"));
  MemoryTrack(@"cheatCatalog", MemoryValue(menu, @"catalog"));
  for (id document in [MemoryValue(menu, @"installed") allValues]) MemoryTrack(@"catalogDocument", document);
  id controller = MemoryValue(session, @"controller");
  for (NSString *key in @[@"skinRenderer", @"overlay", @"metalLayer", @"view"])
    MemoryTrack(key, MemoryValue(controller, key));
  id audio = MemoryValue(session, @"audio");
  for (NSString *key in @[@"engine", @"source"])
    MemoryTrack([@"audio." stringByAppendingString:key], MemoryValue(audio, key));

}
static NSDictionary *MemorySnapshot(void) {
  task_vm_info_data_t memory = {0};
  mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
  kern_return_t status = task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&memory, &count);
  malloc_statistics_t heap = {0};
  malloc_zone_statistics(NULL, &heap);
  NSMutableDictionary *owners = [NSMutableDictionary dictionary];
  for (NSString *key in sMemoryOwners) owners[key] = @(sMemoryOwners[key].allObjects.count);
  thread_act_array_t threads = NULL;
  mach_msg_type_number_t threadCount = 0;
  task_threads(mach_task_self(), &threads, &threadCount);
  for (mach_msg_type_number_t i = 0; i < threadCount; i++) mach_port_deallocate(mach_task_self(), threads[i]);
  if (threads) vm_deallocate(mach_task_self(), (vm_address_t)threads, threadCount * sizeof(thread_t));
  return @{@"pid":@(getpid()), @"footprint":@((uint64_t)memory.phys_footprint), @"taskInfoStatus":@(status),
    @"mallocInUse":@((uint64_t)heap.size_in_use), @"mallocAllocated":@((uint64_t)heap.size_allocated),
    @"mallocBlocks":@((uint64_t)heap.blocks_in_use), @"threads":@(threadCount), @"owners":owners};
}
'''



def verify_ownership(evidence):
    """Compile the actual declarations and only the changed iPhone source."""
    evidence = Path(evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    path = 'packages/libretro_internal_bridge/ios/Classes/LibretroCheatMenu.m'
    baseline = subprocess.check_output(['git','show','69f2194acb415a4d68f7898428d42262ab2149da:' + path], cwd=ROOT, text=True)
    current = (ROOT / path).read_text()
    pattern = r'^\s*__weak LibretroMenuPage \*[^;]+;'
    old = '\n'.join(re.findall(pattern, baseline, re.M))
    new = '\n'.join(re.findall(pattern, current, re.M))
    assert old and new
    with tempfile.TemporaryDirectory(prefix='libretro-arc-') as temporary:
        source = Path(temporary) / 'ownership.m'
        source.write_text('__attribute__((objc_root_class)) @interface Root @end\n'
            '@interface LibretroMenuPage:Root @end\n'
            '@interface Original:Root {\n' + old + '\n} @end\n'
            '@interface Candidate:Root {\n' + new + '\n} @end\n')
        ast = subprocess.check_output(['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.4',
            '-fobjc-arc','-Xclang','-ast-dump','-fsyntax-only',str(source)], text=True)
    roots = re.findall(r"ObjCIvarDecl[^\n]*_rootPage 'LibretroMenuPage \*__(strong|weak)'", ast)
    visible = re.findall(r"ObjCIvarDecl[^\n]*_visiblePage 'LibretroMenuPage \*__(strong|weak)'", ast)
    assert roots == ['strong','weak'] and visible == ['weak','weak'], ast
    sdk = subprocess.check_output(['xcrun','--sdk','iphoneos','--show-sdk-path'],text=True).strip()
    subprocess.run(['xcrun','--sdk','iphoneos','clang','-target','arm64-apple-ios17.4','-isysroot',sdk,
        '-fobjc-arc','-fmodules','-Werror','-Wno-deprecated-declarations','-fsyntax-only',str(ROOT/path)],check=True)
    (evidence/'ownership-proof.json').write_text(json.dumps({'baselineRootOwnership':roots[0],
        'candidateRootOwnership':roots[1],'visibleOwnership':visible,'actualSourcePath':path,
        'changedIPhoneSourceCompiled':True,'ast':ast},indent=2))
    print('PASS: Apple Clang proves 469 root is strong, candidate root is weak; changed iPhone source compiles.',flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('cores', 'inputs', 'evidence', 'label'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    args.sources = None
    args.only = []
    args.lot1 = args.lot2 = args.official_shaders = False
    probe.REAL_CORES = ('nestopia',)
    probe.pick_device = pick_notched_device
    probe.SCENARIOS = [dict(name=f'memory-{i+1:02d}', core='nestopia', console='nes',
                            content='content/nes-skin-loop-a.nes', expect='run', runSeconds=1.0,
                            skinSelection=stability.ORIGINAL_ID if i < 10 else 'default', lifetimeProbe=True)
                       for i in range(20)] + [dict(name='cheats-nestopia', core='nestopia', console='nes',
                            content='content/cheat-probe.nes', expect='run', cheatProbe=True)]
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    original_run = probe.run
    original_subprocess_run = subprocess.run
    original_source = ROOT / 'test/libretro_simulator/probe.m'
    with tempfile.TemporaryDirectory(prefix='libretro-memory-') as temporary:
        work = Path(temporary)
        sources = probe.BRIDGE
        variant_files = []
        instrumented = work / 'probe-memory.m'
        source = original_source.read_text()
        marker = '@interface ProbeAppDelegate : UIResponder <UIApplicationDelegate>'
        assert source.count(marker) == 1
        source = source.replace(marker, OWNERSHIP + '\n' + marker)
        marker = '                          if ([scenario[@"stabilityActions"] boolValue]) {'
        assert source.count(marker) == 1
        source = source.replace(marker, '                          MemoryTrackSession(session);\n' + marker)
        marker = '      if (result[@"lifetimeChecks"] != nil) {'
        assert source.count(marker) == 1
        source = source.replace(marker, '      result[@"memoryAfterStop"] = MemorySnapshot();\n' + marker)
        instrumented.write_text(source)

        compiled_probes = []
        def compile_run(command, *a, **kw):
            values = [str(x) for x in command]
            if str(original_source) in values:
                assert '-c' in values, 'unexpected probe source command'
                values = [str(instrumented) if x == str(original_source) else x for x in values]
                values += ['-I', str(original_source.parent)]
                compiled_probes.append(str(instrumented))
            return original_subprocess_run(values, *a, **kw)
        # assemble compiles translation units with subprocess.run directly.
        # Intercept that boundary and prove injection occurred before launch.
        subprocess.run = compile_run
        try:
            app, scenarios = probe.assemble(args, sources, work)
        finally:
            subprocess.run = original_subprocess_run
        assert compiled_probes == [str(instrumented)], compiled_probes
        (evidence / 'instrumentation.json').write_text(json.dumps({
            'compiledInstrumentedProbeCount': len(compiled_probes),
            'weakOwnersAndMallocSnapshots': True}))
        config_file = app / 'probe-config.json'
        config = json.loads(config_file.read_text())
        config['forceLandscape'] = True
        config_file.write_text(json.dumps(config))
        stability.original_skin(app)
        stability.make_roms(app)
        cheats.content(app / 'content')
        for name in ('ff7-usa-original.cht', 'digimon-world-original.cht'):
            shutil.copyfile(ROOT / 'test/fixtures/libretro_cheats' / name, app / name)
        # Match the successful 100-session app's normal simulator signature.
        # VM tooling permission failures are preserved as diagnostic output.
        original_run(['codesign', '--force', '--sign', '-', '--timestamp=none', app])

        def capture_before_termination(command, *a, **kw):
            if len(command) >= 3 and [str(x) for x in command[:3]] == ['xcrun', 'simctl', 'terminate']:
                report_file = evidence / 'capture-pid-source.json'
                # The live application journal is written directly; unlike
                # simctl's buffered console line it provides a reliable PID.
                try:
                    container = Path(probe.output(['xcrun','simctl','get_app_container',command[3],probe.BUNDLE_ID,'data']).strip())
                    journal = (container / 'Documents/Libretro/Logs/session.log').read_text()
                    match = re.search(r'\bpid=(\d+)\b', journal)
                    if match:
                        pid = match.group(1)
                        report_file.write_text(json.dumps({'pid':pid,'source':'live journal'}))
                        for name, cmd in [('vmmap-summary', ['vmmap','-summary',pid]),
                                          ('leaks', ['leaks','-nocontext',pid]),
                                          ('heap', ['heap','-sortBySize',pid]),
                                          ('sample', ['sample',pid,'3'])]:
                            with (evidence / (name + '.txt')).open('w') as out:
                                try:
                                    result = original_subprocess_run(cmd, stdout=out, stderr=subprocess.STDOUT, timeout=45)
                                    out.write('\nexitCode=' + str(result.returncode) + '\n')
                                except subprocess.TimeoutExpired:
                                    out.write('\ndiagnostic command exceeded 45 s\n')
                except Exception as error:
                    report_file.write_text(json.dumps({'error':str(error)}))
            return original_subprocess_run(command, *a, **kw)
        subprocess.run = capture_before_termination
        try:
            outcome = probe.run_in_simulator(app, evidence, 900)
        finally:
            subprocess.run = original_subprocess_run
        restart_evidence = evidence / 'process-restart'
        restart_evidence.mkdir()
        os.environ['SIMCTL_CHILD_NEOSTATION_CHEAT_RESTART'] = '1'
        try:
            restarted = probe.run_in_simulator(app, restart_evidence, 180, reset=False)
        finally:
            os.environ.pop('SIMCTL_CHILD_NEOSTATION_CHEAT_RESTART', None)
    report = json.loads((evidence / 'probe.json').read_text()) if (evidence / 'probe.json').exists() else {'results':[]}
    problems = probe.evaluate(report, scenarios)
    if not outcome['finished']:
        problems.append('memory probe process did not finish')
    records = []
    for index, row in enumerate(report['results']):
        if index >= 20:
            continue
        if index < 10:
            required = f'"event":"active","identifier":"{stability.ORIGINAL_ID}"'
            if required not in row.get('journal','') or '"display":"edgeToEdge"' not in row.get('journal',''):
                problems.append(row['name'] + ': original edgeToEdge skin activation missing')
        snapshot = row.get('memoryAfterStop')
        if not snapshot:
            problems.append(row['name'] + ': no post-release memory snapshot')
            continue
        records.append({'name':row['name'], **snapshot})
        for owner in ('session','controller','presenter','audio','host','input','skinRenderer','overlay','cheatMenu','cheatCatalog','catalogDocument','cheatRootPage'):
            if snapshot['owners'].get(owner) != 0:
                problems.append(row['name'] + ': retained owner ' + owner + '=' + str(snapshot['owners'].get(owner)))
        print('MEMORY', json.dumps(records[-1]), flush=True)
    if len(records) != 20:
        problems.append('expected exactly 20 ownership regression records')
    restart_file = restart_evidence / 'probe.json'
    restart_report = json.loads(restart_file.read_text()) if restart_file.exists() else {'results':[]}
    problems += probe.evaluate(restart_report, [scenarios[-1]])
    if not restarted['finished']:
        problems.append('cheat persistence process did not finish')
    functional = next((row.get('cheatChecks',[]) for row in report['results'] if row['name']=='cheats-nestopia'), [])
    persistence = next((row.get('cheatChecks',[]) for row in restart_report['results'] if row['name']=='cheats-nestopia'), [])
    if len(functional) != 99 or any(not row['passed'] for row in functional):
        problems.append('99 actual NES cheat/menu checks did not all pass')
    if len(persistence) != 4 or any(not row['passed'] for row in persistence):
        problems.append('4 actual second-process cheat checks did not all pass')
    verdict = {'source':args.label, 'productionSource':'6b1aaba9dd8b6e7cdb50de5730fbd6f51dd0a9eb',
               'outcome':outcome,'restartOutcome':restarted,'records':records,
               'functionalCheatChecks':len(functional),'persistenceCheatChecks':len(persistence),
               'problems':problems,'physicalDeviceValidated':False,
               'notes':'Targeted weak-owner regression and unchanged cheat functionality; no shipping variants or arbitrary memory threshold.'}
    (evidence / 'memory-verdict.json').write_text(json.dumps(verdict,indent=2))
    if problems:
        raise SystemExit('\n'.join(problems))
    print('PASS: 20 sessions release every tracked owner; 99 cheat checks and 4 second-process checks pass.',flush=True)

if __name__ == '__main__':
    main()
