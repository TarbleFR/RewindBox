"""The RPCS3 Core 589 binding for a delivery recipe (Core commit d802611, Core run on 99a57a6).

Core 589 (CELL589_TITLE_LEVERS) replaces the Core 587 (a8a7ce1) of the
delivered 586: Assassin's Creed (BLES00158, BLUS30089) joins the Automatic
mode of texture validation per FIFO batch (559) and scoped revalidation (573).
A recipe that ships it imports this module for the Core binding, as the 586
recipe does with rpcs3cell587_delivery_core.py:

* CORE_SOURCE, CORE_RUN, CORE_WORKFLOW, CORE_STEPS: the Core run (dispatched
  on 99a57a6, the profile commit right after the Core commit d802611);
* CELL589: the files of the Core commit, to pin at CORE_SOURCE;
* PROFILE_SOURCE, PROFILE589: the app profile commit (Assassin's Creed relaxed
  SPU reservations) and its two files;
* CORE589_MARKERS: texts the signed Core must hold, besides the 587 ones;
* validate_rpc_core_identity, validate_rpc_core_pin, core_receipt, core_run.

It reads its own evidence (docs/evidence/rpcs3-cell589-host-linux.json,
docs/evidence/rpcs3-cell589-macos.json) and the 587 binding for the Cores
under it.
"""
import hashlib,json,subprocess,sys
from pathlib import Path
import rpcs3cell589_core as native
import rpcs3cell587_delivery_core as d587
ROOT=Path(__file__).resolve().parents[2]

CORE587_SOURCE,CORE587_RUN=d587.CORE_SOURCE,d587.CORE_RUN
CORE_COMMIT='d802611ef0df34a1050854f3bb8c93e7a09db7a6'
CORE_SOURCE='99a57a663eed1a1e455e6c7baf7e9be621cb4b00'
CORE_RUN=40778765122
CORE_WORKFLOW='.github/workflows/rpcs3-cell589-core.yml'
CORE_STEPS=['Authenticate the 587 Core and execute every 589 case on ARM64',
            'Compile actual iPhone Core from the verified source',
            'Verify actual Core, exact exports, passive loading and 589 identity',
            'Upload source-built589 Core']
HOST_EVIDENCE='docs/evidence/rpcs3-cell589-host-linux.json'
MAC_EVIDENCE='docs/evidence/rpcs3-cell589-macos.json'
PROFILE_SOURCE=CORE_SOURCE
PROFILE589=['lib/services/rpcs3_game_profile_service.dart','test/rpcs3_game_profile_service_test.dart']
# The Core commit's files (Core recipe, tests, evidence and docs); the docs of later commits may add to them.
CELL589=['.github/diagnostics/rpcs3cell589_core.py','.github/workflows/rpcs3-cell589-core.yml',
         '.github/workflows/rpcs3-core.yml','AGENTS.md','build-utils/build_rpcs3_embedded_core.sh',
         'build-utils/rpcs3/canonical-source.json','build-utils/rpcs3/embedded-core.patch',
         'docs/AI_TASK_BOARD.md','docs/evidence/rpcs3-cell589-host-linux.json','docs/rpcs3-cell589.md',
         'test/fixtures/rpcs3_cell589.diff','test/neo_swap_core_pin_test.py','test/rpcs3_cell589_test.py']
# Besides the 587 markers (rpcs3cell587_delivery_core.CORE587_MARKERS), which Core 589 keeps.
CORE589_MARKERS=(b"Automatic enables it for God of War III, Call of Duty: Black Ops II, Bladestorm and Assassin's Creed;",)
# Each earlier Core, with its own run and Mac evidence.
EARLIER=dict(d587.EARLIER)
EARLIER[587]=(CORE587_SOURCE,CORE587_RUN,d587.MAC_EVIDENCE)

def sha(p):
 return hashlib.sha256((ROOT/p).read_bytes()).hexdigest()

def at(source,p):
 return subprocess.check_output(['git','show',source+':'+p],cwd=ROOT)

def validate_rpc_core_identity(identity):
 """The 589 Core identity, bound to its own run: the canonical delta, every
 Core source and every recorded input equal the blobs of the run's commit and
 this checkout."""
 assert identity['host_commit']==CORE_SOURCE and identity['abi_version']==30
 assert identity['cpu_baseline']=='armv8.4-a' and not identity['legacy_core_bundled']
 assert not identity['device_runtime_tested']
 manifest=native.manifest()
 assert identity['source_patch_sha256']==manifest['patch_sha256']
 assert identity['native_source_sha256']==manifest['files_sha256']
 assert identity['core_input_sha256']==native.pin_module().core_input_hashes()
 # The identity names this Core's inputs, not an earlier Core's.
 earlier={'cell%d_input_sha256'%b for b in (551,555,559,560,561,563,565,567,569,571,573,575,579,581,583,585,587)}
 assert not earlier&set(identity),set(identity)&earlier
 recorded=identity['cell589_input_sha256'];current=native.inputs()
 assert set(recorded)==set(current),set(recorded)^set(current)
 for p,h in recorded.items():
  assert hashlib.sha256(at(CORE_SOURCE,p)).hexdigest()==h,p
  assert current[p]==h,p
 # The Core run's commit carries the Core commit's files unchanged (it adds the profile only).
 for p in CELL589:
  assert at(CORE_COMMIT,p)==at(CORE_SOURCE,p),p

def validate_rpc_core_pin(source,paths):
 assert source==CORE_SOURCE
 assert paths and set(paths)<=set(native.inputs()),set(paths)-set(native.inputs())
 for p in paths:assert at(source,p)==(ROOT/p).read_bytes(),p

def core_receipt():
 """The 589 Core: its host evidence names the canonical delta and fixture of
 this checkout, its Mac evidence the Core the run built from them; the Cores
 under it each passed their own Core run."""
 local=json.loads((ROOT/HOST_EVIDENCE).read_bytes())
 mac=json.loads((ROOT/MAC_EVIDENCE).read_bytes())
 manifest=native.manifest();record=manifest['cell589']
 assert local['build']==589 and local['passed'] and local['result']=='passed'
 assert local['physicalDeviceTested'] is False and local['gameplayMeasured'] is False
 assert local['sourceContract']['baseline']==record['baseline']==CORE587_SOURCE
 assert local['sourceContract']['fixtureSHA256']==record['fixture_sha256']==sha(native.FIXTURE)
 assert local['sourceContract']['sourceSHA256']==record['after_sha256']
 assert local['codegenIdentity']['unchangedFrom587'] and not local['codegenIdentity']['coldCompileRequiredByThisChange']
 policy=local['policy']
 assert policy['passed'] and policy['before587']['passed'] and policy['newlyAutomatic']==['BLES00158','BLUS30089'] and policy['prehashUnchanged']
 assert mac['build']==589 and mac['result']=='passed' and mac['source']==CORE_SOURCE and mac['run']==CORE_RUN
 assert mac['physicalDeviceTested'] is False and mac['gameplayMeasured'] is False
 assert mac['core']['sourcePatchSHA256']==manifest['patch_sha256']==sha('build-utils/rpcs3/embedded-core.patch')
 assert mac['core']['moltenvkArchive']==manifest['cell587']['moltenvk_archive']['patched_sha256']
 earlier={}
 for build,(source,run,path) in EARLIER.items():
  evidence=json.loads((ROOT/path).read_bytes())
  assert evidence['build']==build and evidence['result']=='passed' and evidence['source']==source and evidence['run']==run,build
  assert evidence['physicalDeviceTested'] is False and manifest['cell%d'%build]['device_tested'] is False,build
  earlier[build]=dict(source=source,run=run,coreSHA256=evidence['core']['sha256'])
 assert record['device_tested'] is False and record['game_performance_measured'] is False
 assert record['codegen']==manifest['cell587']['codegen']==manifest['cell567']['codegen']
 assert record['core_baseline']=='cell587' and record['core_baseline_run']==CORE587_RUN
 assert record['core_baseline_sha256']==earlier[587]['coreSHA256']
 cells=('cell567','cell569','cell571','cell573','cell575','cell579','cell581','cell583','cell585','cell587','cell589')
 runs={f'core{b}Source':source for b,(source,_,_) in earlier.items()}
 runs.update({f'core{b}Run':run for b,(_,run,_) in earlier.items()})
 return dict(runs,coreSource=CORE_SOURCE,coreCommit=CORE_COMMIT,coreRun=CORE_RUN,core587Source=CORE587_SOURCE,core587Run=CORE587_RUN,
  sourcePatchSHA256=manifest['patch_sha256'],fixtureSHA256=record['fixture_sha256'],codegen=record['codegen'],
  optimizations={k:v for cell in cells for k,v in manifest[cell]['optimizations'].items()},
  qosKeep=manifest['cell569']['qos_keep'],textureResidency=manifest['cell573']['texture_residency'],
  scopedTextureRevalidation=manifest['cell573']['scoped_texture_revalidation'],
  passiveLockFairness=manifest['cell571']['passive_lock_fairness'],titleLevers=manifest['cell575']['title_levers'],
  changes579=manifest['cell579']['changes'],changes581=manifest['cell581']['changes'],changes583=manifest['cell583']['changes'],
  changes585=manifest['cell585']['changes'],changes587=manifest['cell587']['changes'],changes589=record['changes'],
  moltenvkArchive=manifest['cell587']['moltenvk_archive'],
  earlierCores=earlier,coreSHA256=mac['core']['sha256'],inputs=native.inputs(),
  hostEvidence=local,macEvidence=mac,physicalDeviceTested=False,fpsGainMeasured=False)

def core_run():
 """The Core run: the exact commit, its own workflow, each Core step passed."""
 state=d587.d585.previous.api(f'actions/runs/{CORE_RUN}')
 assert state['head_sha']==CORE_SOURCE and state['path']==CORE_WORKFLOW,(state['head_sha'],state['path'])
 return d587.d585.previous.completed(CORE_RUN,CORE_SOURCE,CORE_STEPS)

if __name__=='__main__':
 print(json.dumps(dict(source=CORE_SOURCE,run=CORE_RUN,receipt=core_receipt()['coreSHA256']),indent=2))
