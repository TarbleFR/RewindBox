"""The RPCS3 Core 587 binding for a delivery recipe (a8a7ce1, its own Core run).

Core 587 (CELL587_MVK_ENCODE_BARRIER, CELL587_MVK_ASYNC_CANARY) replaces the
Core 585 (2b01363) of the delivered 585 tree: asynchronous MoltenVK submits
with an encode barrier before every swapchain acquisition, the MetalFX
handoff ordered, and a boot canary; Automatic for God of War III. A recipe
that ships it imports this module for the Core binding, as the 585 recipe
does with its own constants and functions:

* CORE_SOURCE, CORE_RUN, CORE_WORKFLOW, CORE_STEPS: the Core run;
* CELL587: the files of the Core commit, to pin at CORE_SOURCE (the Core
  recipe files the 585 tree pins at 2b01363 change with it);
* PROFILE_SOURCE, PROFILE587: the app profile commit (God of War III
  asynchronous submits Automatic, Black Ops II relaxed SPU reservations) and
  its two files, which change the product tree (lib) and its Dart test;
* CORE587_MARKERS: texts the signed Core must hold, besides the 585 ones;
* validate_rpc_core_identity, validate_rpc_core_pin, core_receipt, core_run.

It reads its own evidence (docs/evidence/rpcs3-cell587-host-linux.json,
docs/evidence/rpcs3-cell587-macos.json) and the 585 delivery module for the
Cores under it.
"""
import hashlib,json,subprocess,sys
from pathlib import Path
import rpcs3cell587_core as native
import rpcs3cell585_delivery as d585
ROOT=Path(__file__).resolve().parents[2]

CORE585_SOURCE,CORE585_RUN=d585.CORE_SOURCE,d585.CORE_RUN
CORE_SOURCE='a8a7ce1072c189806f4ddf70552280b3e95a1e17'
CORE_RUN=40718679248
CORE_WORKFLOW='.github/workflows/rpcs3-cell587-core.yml'
CORE_STEPS=['Authenticate the 585 Core and execute every 587 native case on ARM64',
            'Compile actual iPhone Core from the verified source',
            'Verify actual Core, exact exports, passive loading and 587 identity',
            'Upload source-built587 Core']
HOST_EVIDENCE='docs/evidence/rpcs3-cell587-host-linux.json'
MAC_EVIDENCE='docs/evidence/rpcs3-cell587-macos.json'
PROFILE_SOURCE='147af30e5e9aa9e26ef7ef988b0aba699e8aafd7'
PROFILE587=['lib/services/rpcs3_game_profile_service.dart','test/rpcs3_game_profile_service_test.dart']
# The Core commit's files (Core recipe, tests, evidence and docs); the docs of later commits may add to them.
CELL587=['.github/diagnostics/rpcs3cell587_core.py','.github/workflows/rpcs3-cell587-core.yml',
         '.github/workflows/rpcs3-core.yml','AGENTS.md','build-utils/build_rpcs3_embedded_core.sh',
         'build-utils/rpcs3/canonical-source.json','build-utils/rpcs3/embedded-core.patch',
         'build-utils/rpcs3/patch_moltenvk_exec_queue.py','docs/evidence/rpcs3-cell587-host-linux.json',
         'docs/rpcs3-cell587.md','test/fixtures/rpcs3_cell587.diff','test/native/rpcs3_cell587_mvk_exec_test.cpp',
         'test/native/rpcs3_cell587_mvk_gcd_test.cpp','test/neo_swap_core_pin_test.py','test/rpcs3_cell587_test.py']
# Besides the 585 markers (rpcs3cell585_delivery / validate_rpcs3_585_ipa.py), which Core 587 keeps.
CORE587_MARKERS=(b'COREPROF OPT587',b'canary=%s confirmed=%u exec_queues=%u',
                 b'MoltenVK asynchronous submits: encoding queue recorded; acquisitions wait for the last queued present',
                 b'rewindbox-mvk-async-587.txt',
                 b'MoltenVK asynchronous submits stay off for %s: its last asynchronous boot did not finish (crash or forced exit)',
                 b'MoltenVK asynchronous submits enabled for this boot')
# Each earlier Core, with its own run and Mac evidence.
EARLIER=dict(d585.EARLIER)
EARLIER[585]=(CORE585_SOURCE,CORE585_RUN,d585.MAC_EVIDENCE)

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def at(source,p):
 return subprocess.check_output(['git','show',source+':'+p],cwd=ROOT)

def validate_rpc_core_identity(identity):
 """The 587 Core identity, bound to its own commit: the canonical delta,
 every Core source and every recorded input equal the a8a7ce1 blobs and
 this checkout."""
 assert identity['host_commit']==CORE_SOURCE and identity['abi_version']==30
 assert identity['cpu_baseline']=='armv8.4-a' and not identity['legacy_core_bundled']
 assert not identity['device_runtime_tested']
 manifest=native.manifest()
 assert identity['source_patch_sha256']==manifest['patch_sha256']
 assert identity['native_source_sha256']==manifest['files_sha256']
 assert identity['core_input_sha256']==native.pin_module().core_input_hashes()
 # The identity names this Core's inputs, not an earlier Core's.
 assert not {'cell551_input_sha256','cell555_input_sha256','cell559_input_sha256','cell560_input_sha256',
             'cell561_input_sha256','cell563_input_sha256','cell565_input_sha256','cell567_input_sha256',
             'cell569_input_sha256','cell571_input_sha256','cell573_input_sha256','cell575_input_sha256',
             'cell579_input_sha256','cell581_input_sha256','cell583_input_sha256','cell585_input_sha256'}&set(identity),set(identity)
 recorded=identity['cell587_input_sha256'];current=native.inputs()
 assert set(recorded)==set(current),set(recorded)^set(current)
 for p,h in recorded.items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
  assert current[p]==h,p

def validate_rpc_core_pin(source,paths):
 assert source==CORE_SOURCE
 assert paths and set(paths)<=set(native.inputs()),set(paths)-set(native.inputs())
 for p in paths:assert at(source,p)==(ROOT/p).read_bytes(),p

def core_receipt():
 """The 587 Core: its host evidence names the canonical delta and fixture of
 this checkout, its Mac evidence the Core the run built from them, with the
 GCD registry run against the real libdispatch; the Cores under it each
 passed their own Core run."""
 local=json.loads((ROOT/HOST_EVIDENCE).read_bytes())
 mac=json.loads((ROOT/MAC_EVIDENCE).read_bytes())
 manifest=native.manifest();record=manifest['cell587']
 assert local['build']==587 and local['passed'] and local['result']=='passed'
 assert local['physicalDeviceTested'] is False and local['gameplayMeasured'] is False
 assert local['sourceContract']['baseline']==record['baseline']==CORE585_SOURCE
 assert local['sourceContract']['fixtureSHA256']==record['fixture_sha256']==sha(native.FIXTURE)
 assert local['sourceContract']['sourceSHA256']==record['after_sha256']
 assert local['codegenIdentity']['unchangedFrom585'] and not local['codegenIdentity']['coldCompileRequiredByThisChange']
 barrier=local['barrier']
 assert barrier['barrierBeforeAcquire'] and barrier['markerAfterPresent'] and barrier['metalFxOrdered'] and barrier['canaryArmedAtInstance']
 for report in local['native']['exec'].values():
  assert report['model']['hazardsWithBarrier']==0 and report['model']['hazardsWithoutBarrier']>0
 assert local['moltenvkArchive']['patchedSHA256']==record['moltenvk_archive']['patched_sha256']
 assert mac['build']==587 and mac['result']=='passed' and mac['source']==CORE_SOURCE and mac['run']==CORE_RUN
 assert mac['physicalDeviceTested'] is False and mac['gameplayMeasured'] is False
 assert mac['core']['sourcePatchSHA256']==manifest['patch_sha256']==sha('build-utils/rpcs3/embedded-core.patch')
 assert mac['native']['realLibdispatch'] is True
 assert mac['core']['moltenvkArchive']==record['moltenvk_archive']['patched_sha256']
 earlier={}
 for build,(source,run,path) in EARLIER.items():
  evidence=json.loads((ROOT/path).read_bytes())
  assert evidence['build']==build and evidence['result']=='passed' and evidence['source']==source and evidence['run']==run,build
  assert evidence['physicalDeviceTested'] is False and manifest['cell%d'%build]['device_tested'] is False,build
  earlier[build]=dict(source=source,run=run,coreSHA256=evidence['core']['sha256'])
 assert record['device_tested'] is False and record['game_performance_measured'] is False
 assert record['codegen']==manifest['cell585']['codegen']==manifest['cell567']['codegen']
 assert record['core_baseline']=='cell585' and record['core_baseline_run']==CORE585_RUN
 assert record['core_baseline_sha256']==earlier[585]['coreSHA256']
 cells=('cell567','cell569','cell571','cell573','cell575','cell579','cell581','cell583','cell585','cell587')
 runs={f'core{b}Source':source for b,(source,_,_) in earlier.items()}
 runs.update({f'core{b}Run':run for b,(_,run,_) in earlier.items()})
 return dict(runs,coreSource=CORE_SOURCE,coreRun=CORE_RUN,core585Source=CORE585_SOURCE,core585Run=CORE585_RUN,
  sourcePatchSHA256=manifest['patch_sha256'],fixtureSHA256=record['fixture_sha256'],codegen=record['codegen'],
  optimizations={k:v for cell in cells for k,v in manifest[cell]['optimizations'].items()},
  qosKeep=manifest['cell569']['qos_keep'],textureResidency=manifest['cell573']['texture_residency'],
  scopedTextureRevalidation=manifest['cell573']['scoped_texture_revalidation'],
  passiveLockFairness=manifest['cell571']['passive_lock_fairness'],titleLevers=manifest['cell575']['title_levers'],
  changes579=manifest['cell579']['changes'],changes581=manifest['cell581']['changes'],changes583=manifest['cell583']['changes'],
  changes585=manifest['cell585']['changes'],changes587=record['changes'],moltenvkArchive=record['moltenvk_archive'],
  earlierCores=earlier,coreSHA256=mac['core']['sha256'],inputs=native.inputs(),
  hostEvidence=local,macEvidence=mac,physicalDeviceTested=False,fpsGainMeasured=False)

def core_run():
 """The Core run: the exact commit, its own workflow, each Core step passed."""
 state=d585.previous.api(f'actions/runs/{CORE_RUN}')
 assert state['head_sha']==CORE_SOURCE and state['path']==CORE_WORKFLOW,(state['head_sha'],state['path'])
 return d585.previous.completed(CORE_RUN,CORE_SOURCE,CORE_STEPS)

if __name__=='__main__':
 print(json.dumps(dict(source=CORE_SOURCE,run=CORE_RUN,receipt=core_receipt()['coreSHA256']),indent=2))
