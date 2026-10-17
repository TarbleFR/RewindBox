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
  if (!sMemoryOwners[key]) sMemoryOwners[key] = [NSHashTable weakObjectsHashTable];
  if (object) [sMemoryOwners[key] addObject:object];
}
static void MemoryTrackSession(LibretroSession *session) {
  MemoryTrack(@"session", session);
  for (NSString *key in @[@"controller", @"presenter", @"audio", @"host", @"input", @"cheatMenu"])
    MemoryTrack(key, MemoryValue(session, key));
  id menu = MemoryValue(session, @"cheatMenu");
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ('cores', 'inputs', 'evidence', 'label'):
        parser.add_argument('--' + key, required=True)
    parser.add_argument('--mode', choices=('baseline','pools','no-prewarm'), default='baseline')
    args = parser.parse_args()
    args.sources = None
    args.only = []
    args.lot1 = args.lot2 = args.official_shaders = False
    probe.REAL_CORES = ('nestopia',)
    probe.pick_device = pick_notched_device
    probe.SCENARIOS = [dict(name=f'memory-{i+1:02d}', core='nestopia', console='nes',
                            content='content/nes-skin-loop-a.nes', expect='run', runSeconds=1.0,
                            skinSelection=stability.ORIGINAL_ID if i < 10 else 'default', lifetimeProbe=True)
                       for i in range(20)]
    evidence = Path(args.evidence)
    evidence.mkdir(parents=True, exist_ok=True)
    original_run = probe.run
    original_subprocess_run = subprocess.run
    original_source = ROOT / 'test/libretro_simulator/probe.m'
    with tempfile.TemporaryDirectory(prefix='libretro-memory-') as temporary:
        work = Path(temporary)
        sources = probe.BRIDGE
        variant_files = []
        if args.mode != 'baseline':
            sources = work / 'variant-bridge'
            shutil.copytree(probe.BRIDGE, sources)
            if args.mode == 'pools':
                for name in ('LibretroCheatMenu.m','LibretroCheatCatalog.m'):
                    path = sources / 'Classes' / name
                    before = path.read_text()
                    old = 'dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL,'
                    assert before.count(old) == 1
                    path.write_text(before.replace(old, 'dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL_WITH_AUTORELEASE_POOL,'))
                    variant_files.append(name)
            else:
                path = sources / 'Classes/LibretroSession.m'
                before = path.read_text()
                old = '// Prepare identity and catalogues after launch; never wait on the emulation queue.\n    [self cheatsPage];'
                assert before.count(old) == 1
                path.write_text(before.replace(old, '// CI isolation only: omit eager catalogue preparation.'))
                variant_files.append(path.name)
            with (evidence / 'nonshipping-variant.patch').open('w') as output:
                for name in variant_files:
                    subprocess.run(['diff','-u',str(probe.BRIDGE/'Classes'/name),str(sources/'Classes'/name)],stdout=output)
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
    report = json.loads((evidence / 'probe.json').read_text()) if (evidence / 'probe.json').exists() else {'results':[]}
    problems = probe.evaluate(report, scenarios)
    if not outcome['finished']:
        problems.append('memory probe process did not finish')
    records = []
    for index, row in enumerate(report['results']):
        if index < 10:
            required = f'"event":"active","identifier":"{stability.ORIGINAL_ID}"'
            if required not in row.get('journal','') or '"display":"edgeToEdge"' not in row.get('journal',''):
                problems.append(row['name'] + ': original edgeToEdge skin activation missing')
        snapshot = row.get('memoryAfterStop')
        if not snapshot:
            problems.append(row['name'] + ': no post-release memory snapshot')
            continue
        records.append({'name':row['name'], **snapshot})
        for owner in ('session','controller','presenter','audio','host','input','skinRenderer','overlay','cheatMenu','cheatCatalog'):
            if snapshot['owners'].get(owner) != 0:
                problems.append(row['name'] + ': retained owner ' + owner + '=' + str(snapshot['owners'].get(owner)))
        print('MEMORY', json.dumps(records[-1]), flush=True)
    verdict = {'source':args.label, 'productionSource':'2e877872a919c119fb3d10f47699218cc1a34e96',
               'mode':args.mode,'nonshippingVariantFiles':variant_files,
               'outcome':outcome,'records':records,'problems':problems,'physicalDeviceValidated':False,
               'notes':'No RSS threshold asserted; weak application owners, malloc statistics and VM categories identify what remains.'}
    (evidence / 'memory-verdict.json').write_text(json.dumps(verdict,indent=2))
    if problems:
        raise SystemExit('\n'.join(problems))
    print('PASS: 20 complete sessions; all tracked application owners released; memory diagnosis captured.',flush=True)

if __name__ == '__main__':
    main()
