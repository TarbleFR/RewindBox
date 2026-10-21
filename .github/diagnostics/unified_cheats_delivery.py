"""Compose the delivered 473 baseline with exact, already executed cheat proofs.

This gate reads CI evidence; it never reruns suites or rebuilds a core. Failed
historical jobs are accepted only for their explicitly successful components.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[2]
BASE = '881c8df6bcffbdd0e4c3f5a32fd66492830f6dd1'
CATALOGUE = 'fabbdebda0761cb819cd250baee6dfc8f686fb25'
NATIVE_FINAL = 'b157f557fe13b077d92afdd4ef1146c60982235d'
APP_FINAL = 'f7c2d70b9e97c59d03f357185308e19399364d64'
MANUAL_RUN = 39101802667
RUNTIME_FINAL = '6b56a8b5bb7b1b0c13e232f61e48c41908c840d2'
SDK_SOURCE = '2ae6ec849c9e4b122a1fae62bc9715cbdcc64691'
RUNTIME_RUN = 39101251790
RPC_SOURCE = 'c9ba99fb81dc7e9dd79d17dde845a22628924bdb'
DELIVERY_ONLY = {
    '.github/diagnostics/unified_cheats_delivery.py',
    '.github/workflows/retroarch-delivery.yml',
    'build-utils/validate_unified_cheats_ipa.py',
    'build-utils/delivery-474-recipient.pem',
    'docs/build474-unified-cheats.md', 'docs/build475-direct-cheats.md', 'AGENTS.md',
    'docs/unified-cheats-direct-build475.md', 'docs/evidence/unified-cheats-direct475.json',
}


def command(args):
    return subprocess.check_output(args, cwd=ROOT, text=True).strip()


def api(path, raw=False):
    args = ['gh', 'api', 'repos/TarbleFR/RewindBox/' + path]
    if raw:
        # Recent gh versions reject ANSI-bearing job logs by default. The
        # bytes are captured privately for exact evidence checks, not emitted.
        args.append('--allow-escape-sequences')
    data = command(args)
    return data if raw else json.loads(data)


def source_closure():
    for args in (['git','diff','--name-only',APP_FINAL,'HEAD'], ['git','diff','--name-only',APP_FINAL]):
        extra=set(command(args).splitlines())-DELIVERY_ONLY
        if extra: raise ValueError('Unvalidated changes after final direct-cheat proofs: '+', '.join(sorted(extra)))
    command(['git','diff','--exit-code',BASE,'--','lib','assets','native/neoswap','native/neoswap-relay',
             'native/neoswap-donation','native/nestopia','build-utils/libretro','packages/neo_swap',
             'packages/external_display','packages/external_folder_access'])
    # Every shipped product/data input equals the published UI/data snapshot.
    command(['git','diff','--exit-code',APP_FINAL,'--','packages'])
    command(['git','diff','--exit-code',CATALOGUE,'--','native/cheats/catalogue','tools/cheats'])
    expected={'packages/neo_cheat_catalog/ios/Classes/NeoUnifiedCheatList.m',
              'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz',
              'packages/neo_cheat_catalog/ios/Resources/labels.json',
              'packages/neo_cheat_catalog/ios/Resources/gow3-0100-LICENSE.txt',
              'packages/neo_cheat_catalog/ios/neo_cheat_catalog.podspec'}
    changed=set(command(['git','diff','--name-only',NATIVE_FINAL,CATALOGUE,'--','packages']).splitlines())
    if changed!=expected: raise ValueError('Unproved native/source composition: '+', '.join(sorted(changed)))
    data=(ROOT/'packages/neo_cheat_catalog/ios/Resources/manifest.json.gz').read_bytes()
    if hashlib.sha256(data).hexdigest()!='ff64b3b92225f5ab6960e1931fadaf4509665864a4470fb36908cc2faf22d792':
        raise ValueError('Final direct-cheat index differs from Apple preflight')
    report=(ROOT/'native/cheats/catalogue/VALIDATION.json').read_bytes()
    if hashlib.sha256(report).hexdigest()!='032950997212a242fb584db4f6de72dc562522c532c8ad9336f79b2d04b4b93f':
        raise ValueError('Final full active-pack audit changed')
    return {'base':BASE,'catalogueAndFinalUI':CATALOGUE,'nativeAdapters':NATIVE_FINAL,'manualImport':APP_FINAL,
            'retiredMemberContract':RUNTIME_FINAL,'protectedComponentsUnchanged':True}


@contextmanager
def rpc_core_input_view(pin):
    """Preserve the authentic Core identity; isolate host-only declarations.

    Every published Core input is still checked byte-for-byte. Only a temporary
    view of the host header removes the exact, separately SDK-tested optional
    declarations. The compiled main API layout must equal the pinned original.
    Neither the live header nor the downloaded identity is rewritten.
    """
    sys.path.insert(0, str(ROOT / 'test'))
    import neo_swap_core_pin_test as core
    if pin != 'dcf0df67b3edf923d5dd54071f5228e6cf6882b6':
        raise ValueError('Unexpected RPCS3 Core pin')
    path = 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreABI.h'
    current = (ROOT / path).read_bytes()
    tested = subprocess.check_output(['git', 'show', SDK_SOURCE + ':' + path], cwd=ROOT)
    original = subprocess.check_output(['git', 'show', pin + ':' + path], cwd=ROOT)
    if current != tested:
        raise ValueError('Optional RPCS3 declarations differ from their SDK proof')
    start = current.index(b'// Optional functions already exported by the pinned ABI-30 Core.')
    end = current.index(b'typedef enum rpcs3_ios_performance_metric_bits', start)
    normalized = current[:start] + current[end:]
    if normalized != original:
        raise ValueError('Main RPCS3 ABI changed outside the proved optional declarations')
    folder = ROOT / 'build'
    folder.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='rpc-core-input-view-', dir=folder) as tmp:
        view = Path(tmp)
        # Read the same immutable objects, with paths relative to this view.
        # No index/ref operation is performed in the temporary repository view.
        git_dir = command(['git', 'rev-parse', '--absolute-git-dir'])
        (view / '.git').write_text('gitdir: ' + git_dir + '\n')
        for relative in core.CORE_INPUTS:
            destination = view / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, destination)
        (view / path).write_bytes(normalized)
        yield core, view


def validate_rpc_core_identity(identity):
    with rpc_core_input_view(identity['host_commit']) as (core, view):
        core.validate_core_input_identity(identity, root=view)


def validate_rpc_core_pin(pin, paths):
    with rpc_core_input_view(pin) as (core, view):
        if len(paths) != len(core.CORE_INPUTS) or set(paths) != set(core.CORE_INPUTS):
            raise ValueError('Delivery omitted or duplicated a published Core input')
        core.validate_source_contract()
        core.validate_exact_pin(pin, root=view)
    print('PASS all authentic RPCS3 Core inputs; only exact optional host declarations isolated')


def successful_run(run_id, ref, names):
    run = api(f'actions/runs/{run_id}')
    if run['head_sha'] != ref or run['status'] != 'completed' or run['conclusion'] != 'success':
        raise ValueError('Missing successful run: ' + str(run_id))
    jobs = api(f'actions/runs/{run_id}/jobs?per_page=100')['jobs']
    for name in names:
        matching = [j for j in jobs if j['name'] == name]
        if len(matching) != 1 or matching[0]['conclusion'] != 'success':
            raise ValueError('Missing successful component: ' + name)
    return {'run': run_id, 'source': ref, 'jobs': names, 'conclusion': 'success'}


def component_run(run_id, ref, names, overall):
    run=api(f'actions/runs/{run_id}')
    if run['head_sha']!=ref or run['status']!='completed' or run['conclusion']!=overall:
        raise ValueError('Wrong run identity/status: '+str(run_id))
    jobs=api(f'actions/runs/{run_id}/jobs?per_page=100')['jobs']
    for name in names:
        selected=[job for job in jobs if job['name']==name]
        if len(selected)!=1 or selected[0]['conclusion']!='success':
            raise ValueError('Unsuccessful required component: '+name)
    return {'run':run_id,'source':ref,'jobs':names,'overallConclusion':overall,
            'scope':'successful named components only' if overall!='success' else 'successful run'}


def evidence():
    records=[successful_run(39088132898,BASE,['checks','native','Release device build • cold']),
             successful_run(39097173122,'b3c83af81e362718a63c73b048d797d8c21654cf',['checks','native','Release device build • cold']),
             successful_run(39100669248,NATIVE_FINAL,['additional-proofs']),
             component_run(39101181611,CATALOGUE,['index','final-ui'],'failure'),
             successful_run(RUNTIME_RUN,RUNTIME_FINAL,['runtime-contract']),
             successful_run(MANUAL_RUN,APP_FINAL,['manual-import'])]
    job=api('actions/jobs/117594585948')
    if job['head_sha']!='c3e690914b5103d19d9a2ab0dcc611f4b2498991':raise ValueError('Wrong initial direct native source')
    required={'Changed Foundation and shared iPhone SDK','Host routing, native startup and option isolation',
              'Three native menus and actual disabled import stores','Compile and link changed Libretro bridge'}
    if not required<={step['name'] for step in job['steps'] if step.get('conclusion')=='success'}:
        raise ValueError('Missing successful direct native components')
    log=api('actions/jobs/117594585948/logs',raw=True)
    import re
    passed=set(re.findall(r"Test Case '-\[UnifiedCatalogueBrowserTests (\w+)\]' passed",log))
    failed=set(re.findall(r"Test Case '-\[UnifiedCatalogueBrowserTests (\w+)\]' failed",log))
    expected_failures={'testDirectListLateImportAfterPopCannotEnableACode',
        'testExclusiveGroupsAcrossTogglesIncludeLegacyAndRestoreIsAtomic',
        'testMGBARestoreRefusesAUTOCombinationWithoutChangingAnyPriorState'}
    if len(passed)!=31 or failed!=expected_failures:raise ValueError('Initial UIKit results do not match the retained component evidence')
    records.append({'run':39100149182,'source':job['head_sha'],'job':job['id'],
        'scope':'four successful native steps and 31 UIKit cases only; three failed cases corrected in later successful gates',
        'passedUIKitCases':sorted(passed),'logSHA256':hashlib.sha256(log.encode()).hexdigest()})
    data_job=api('actions/jobs/117597604157')
    if data_job['head_sha']!=CATALOGUE:raise ValueError('Wrong published data source')
    if not any(step['name']=='Changed PNACH identities, complete groups and PS3 source' and step.get('conclusion')=='success' for step in data_job['steps']):
        raise ValueError('Missing 42 source/format regression successes')
    log=api('actions/jobs/117597604157/logs',raw=True)
    import gzip
    totals=json.loads(gzip.decompress((ROOT/'native/cheats/catalogue/manifest.json.gz').read_bytes()))['totals']
    observed=[]
    for line in log.splitlines():
        try:observed.append(json.loads(line.split('Z ',1)[1]))
        except (ValueError,IndexError):pass
    if totals not in observed or 'Ran 42 tests' not in log or 'line 60' not in log:
        raise ValueError('Missing complete published validator result before the retired-member fixture failure')
    records.append({'run':39101181611,'source':CATALOGUE,'job':data_job['id'],
        'scope':'42 successful format tests and complete CLI validation; later old active-only fixture failed, corrected by runtime-contract gate',
        'validatedTotals':totals,'logSHA256':hashlib.sha256(log.encode()).hexdigest()})
    receipts={}
    for name in ('core-effects','fbneo-native','publication','published-data'):
        path='docs/evidence/unified-cheats-'+name+'.json';raw=(ROOT/path).read_bytes();json.loads(raw)
        receipts[path]=hashlib.sha256(raw).hexdigest()
    return records,receipts


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source-only', action='store_true')
    p.add_argument('--dart-evidence', action='store_true')
    p.add_argument('--libretro-evidence', action='store_true')
    p.add_argument('--skin-session-evidence', action='store_true')
    p.add_argument('--scope', default='full', choices=['full'])
    p.add_argument('--output', default='build/delivery/reused-validation.json')
    p.add_argument('--rpc-core-inputs')
    p.add_argument('core_paths', nargs='*')
    a = p.parse_args()
    closure = source_closure()
    if a.rpc_core_inputs:
        validate_rpc_core_pin(a.rpc_core_inputs, a.core_paths)
        return
    if a.source_only:
        print('PASS final direct-cheat product/data source closure and retained components')
        return
    records, receipts = evidence()
    record = {'result': 'passed', 'testedSHA': CATALOGUE, 'candidateSHA': command(['git', 'rev-parse', 'HEAD']),
              'validationWasReused': True, 'sourceClosure': closure,
              'reusedEvidence': records, 'receiptSHA256': receipts,
              'deviceGameplayValidated': False, 'coreRebuilt': False}
    if a.dart_evidence:
        record.update(key=os.environ['DART_VALIDATION_KEY'], tool='Flutter 3.47.2, Ubuntu 24.04')
    if a.libretro_evidence:
        xcode = command(['xcodebuild', '-version'])
        sdk = command(['xcrun', '--sdk', 'iphoneos', '--show-sdk-version'])
        if xcode != 'Xcode 26.3\nBuild version 17C529' or sdk != '26.2':
            raise ValueError('Changed native toolchain')
        record.update(xcode=xcode, iphoneSDK=sdk)
    out = ROOT / a.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(record, indent=2) + '\n')
    print('PASS closed baseline + direct-cheat component evidence; no suites rerun')


if __name__ == '__main__':
    main()
