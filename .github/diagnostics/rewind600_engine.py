"""Authenticate the compiled remaining-lots MeloNX core for private IPA600.

Only the new component, its current host boundary and its immutable producer
receipts are checked. No compiler, simulator or historical fixture is executed.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile
import rewind596_engine as parsing

ROOT=Path(__file__).resolve().parents[2]
NEW=ROOT/'dist/melonx'
BUILD=600
BASELINE=599
BASELINE_SOURCE='00e372238ade33f3d58157aece54d89df7d630e7'
BASELINE_RUN=41024302714
BASELINE_IPA_SHA256='c7d4337016c7db77ae130e43708141bf68bb8010c8cbe39f1555ddd1b0c27939'
BASELINE_RECEIPT='docs/evidence/rewind599-delivery.json'
BASELINE_RECEIPT_SHA256='441db7d2a556ba024383c941d53c72a9661628cf1c814e92a0ffd3ac0e76c863'
MELONX_SOURCE='827f4653e0dee5b86258f598373255d179638bdb'
MELONX_VALIDATION_SOURCE=MELONX_SOURCE
MELONX_RUN=41028130487
MELONX_JOB=123971057648
MELONX_WORKFLOW='.github/workflows/melonx-core.yml'
MELONX_COMPILE_RUN=MELONX_RUN
MELONX_COMPILE_JOB=MELONX_JOB
MELONX_ARTIFACT_ID=12964518860
MELONX_ARTIFACT_NAME='MeloNX-engine-'+MELONX_SOURCE
MELONX_ARTIFACT_BYTES=87580969
MELONX_ARTIFACT_SHA256='3d94e1bd81c5b710af7668068ff339799749a426f6e9d4d155bea781c07689f7'
MELONX_ARTIFACT=(MELONX_ARTIFACT_ID,MELONX_ARTIFACT_SHA256)
PACKAGED_ID=parsing.PACKAGED_ID
EXPORTS=parsing.EXPORTS
check_image=parsing.check_image
image_info=parsing.image_info
normalized_payload_fingerprint=parsing.normalized_payload_fingerprint
PACKAGED_FINGERPRINT='08f76a792f50196e947837208e9cd0e8299aad372a94111bf59b68d0e4bdfbc7'
BINARY_SHA256={'ios-arm64': 'b4beb50452ab3a36ad71e0415c4a775249bddf92c7db222899f3da2fc43521c4', 'iossimulator-arm64': '63d623af21f654c512f436748665b075897f1faca7f710051b6c692a3607cb7c'}
BINARY_BYTES={'ios-arm64': 37618008, 'iossimulator-arm64': 37928536}
IDENTITY_SHA256={'ios-arm64': 'ab8f37dfd7799246baf3d24995760a888f7930ef36d52b96c6e29054dfe96370', 'iossimulator-arm64': '763361dde4cbcfadad91584ee29213dd2d560edc24ab21b42d38b424a1159ad6'}
ENGINE_STEPS={'Verify Apple ARM64, exact SDK and reviewed remaining-lots preparation inputs',
              'Run three affected Apple gates and authenticate32 scoped historical results',
              'Compile NativeAOT library and verify exported ABI',
              'Bind both new libraries to reviewed sources and gate receipts',
              'Exercise this exact rebuilt engine in an ARM64 iOS app',
              'Verify fresh guest execution, teardown and backing release'}


def require(condition,message):
 if not condition:raise ValueError(message)


def sha(data):return hashlib.sha256(data).hexdigest()


def api(endpoint):return json.loads(subprocess.check_output(['gh','api','repos/TarbleFR/RewindBox/'+endpoint],cwd=ROOT,timeout=120))


def baseline_component():
 raw=(ROOT/BASELINE_RECEIPT).read_bytes();require(sha(raw)==BASELINE_RECEIPT_SHA256,'Delivered599 receipt drift')
 value=json.loads(raw)
 require(value['result']=='passed'and value['source']==BASELINE_SOURCE and value['run']['id']==BASELINE_RUN and value['ipa']['sha256']==BASELINE_IPA_SHA256,'Wrong immediate baseline')
 require(value['melonx']['source']=='e7143e566462bf6e3d9c143ce24532c1ad7aeb10' and value['melonx']['originalPayloadMatched']is True,'Unexpected prior MeloNX selection')
 return value['melonx']


def _query_engine_run():
 baseline_component();run=api(f'actions/runs/{MELONX_RUN}');job=api(f'actions/jobs/{MELONX_JOB}');artifact=api(f'actions/artifacts/{MELONX_ARTIFACT_ID}')
 require(run['head_sha']==MELONX_SOURCE and run['path']==MELONX_WORKFLOW and run['run_attempt']==1 and run['conclusion']=='success'and run['status']=='completed','Wrong new engine producer')
 require(job['run_id']==MELONX_RUN and job['head_sha']==MELONX_SOURCE and job['conclusion']=='success'and job['run_attempt']==1,'Wrong new engine job')
 require(ENGINE_STEPS<={s['name']for s in job['steps']if s['conclusion']=='success'},'Missing successful new engine steps')
 require(artifact['id']==MELONX_ARTIFACT_ID and artifact['name']==MELONX_ARTIFACT_NAME and artifact['size_in_bytes']==MELONX_ARTIFACT_BYTES and artifact['digest']=='sha256:'+MELONX_ARTIFACT_SHA256 and not artifact['expired']and artifact['workflow_run']['id']==MELONX_RUN and artifact['workflow_run']['head_sha']==MELONX_SOURCE,'Wrong engine archive metadata')
 return dict(result='passed',source=MELONX_SOURCE,run=MELONX_RUN,job=MELONX_JOB,runAttempt=1,compileRun=MELONX_RUN,originalRunConclusion='success',validationSource=MELONX_SOURCE,artifact=MELONX_ARTIFACT_ID,artifactSHA256=MELONX_ARTIFACT_SHA256,engineRecompiled=False,priorGatesReexecuted=False)


def engine_run():
 sys.path.insert(0,str(ROOT/'build-utils'))
 from delivery_contract_memo import reuse
 return reuse('600-melonx-run',_query_engine_run)


def engine_identity(runtime='ios-arm64'):
 require(runtime in BINARY_SHA256,'Unknown runtime')
 raw=(NEW/runtime/'identity.json').read_bytes();require(sha(raw)==IDENTITY_SHA256[runtime],'Original compiled identity drift')
 identity=json.loads(raw)
 require(identity['host']==MELONX_SOURCE and identity['runtimeIdentifier']==runtime and identity['sha256']==BINARY_SHA256[runtime]and identity['size']==BINARY_BYTES[runtime],'Compiled engine identity mismatch')
 require(identity['source']==json.loads((ROOT/'build-utils/melonx/source.json').read_bytes())and identity['embeddedLibraryAbi']==2 and identity['embeddedSessionDeviceVerified']is False and sorted(identity['exports'])==sorted(EXPORTS),'Host/Core boundary mismatch')
 require(len(identity['adaptations'])==114,'Wrong compiled input count')
 for path,h in identity['adaptations'].items():require(sha((ROOT/path).read_bytes())==h,'Changed engine preparation input: '+path)
 return identity


def engine_evidence():
 metadata=engine_run();identity=engine_identity();raw=(NEW/'ios-arm64/Ryujinx.Library.dylib').read_bytes()
 require(len(raw)==BINARY_BYTES['ios-arm64']and sha(raw)==BINARY_SHA256['ios-arm64'],'Wrong iOS payload')
 image=check_image(raw,'ios-arm64');fingerprint=normalized_payload_fingerprint(raw)
 require(fingerprint==PACKAGED_FINGERPRINT,'Wrong original compiled payload fingerprint')
 result=json.loads((NEW/'core-validation/result.json').read_bytes());gates=json.loads((NEW/'core-validation/gates.json').read_bytes());preflight=json.loads((NEW/'core-validation/preflight.json').read_bytes())
 execution=dict(source=MELONX_SOURCE,run=MELONX_RUN,attempt=1,url='https://github.com/TarbleFR/RewindBox/actions/runs/'+str(MELONX_RUN))
 for item in (result,gates,preflight):require(item['result']=='passed'and item['execution']==execution,'Wrong producer receipt')
 require(result['freshAppleGates']==3 and result['reusedAppleGates']==32 and result['homebrewSimulatorSessions']==result['releasedBackingSessions']==2,'Wrong execution/reuse or teardown scope')
 require(result['physicalDeviceTested']is False and result['gameplayTested']is False and result['nativeDependenciesRecompiled']is False,'Mis-scoped producer proof')
 require(sha((NEW/'core-validation/gates.json').read_bytes())==result['gateReceiptSha256'],'Changed gate receipt')
 require(json.loads((NEW/'embedded-inputs.json').read_bytes())==identity['adaptations'],'Compiled preparation mismatch')
 contract_bytes=(ROOT/'build-utils/melonx/continuation-core-contract.json').read_bytes();contract=json.loads(contract_bytes)
 require(sha(contract_bytes)==result['continuationContractSha256']and contract['preparationInputs']==identity['adaptations'],'Wrong reviewed core contract')
 for name,h in result['inputs'].items():require(sha((ROOT/name).read_bytes())==h,'Changed producer recipe boundary: '+name)
 for name,h in gates['receipts'].items():require(sha((NEW/name).read_bytes())==h,'Changed producer gate report')
 with zipfile.ZipFile(NEW/'embedded-adapted-source.zip')as z:
  require(len(z.namelist())==len(set(z.namelist()))==151,'Wrong prepared source count')
  require({name:sha(z.read(name))for name in z.namelist()}==contract['preparedMembers'],'Prepared source mismatch')
 smoke_bytes=(NEW/'runtime-smoke/actual-runtime.json').read_bytes();smoke=json.loads(smoke_bytes)
 require(sha(smoke_bytes)==result['runtimeSmokeSha256']and smoke['result']=='passed'and smoke['actualNativeAOT']is True and smoke['coreSha256']==BINARY_SHA256['iossimulator-arm64'],'Wrong actual simulator validation')
 require(smoke['homebrewSimulatorSessions']==smoke['actualCoreDonatedBackingSessions']==2 and smoke['gameplayTested']is False and smoke['iphoneGuestExecutionTested']is False,'Wrong simulator scope')
 for p,h in preflight['smokeInputs'].items():require(sha((ROOT/p).read_bytes())==h,'Changed host runtime boundary: '+p)
 for runtime in BINARY_SHA256:
  engine_identity(runtime)
  require(sha((NEW/runtime/'Ryujinx.Library.dylib').read_bytes())==BINARY_SHA256[runtime],'Wrong compiled runtime: '+runtime)
 return dict(result='passed',build=BUILD,baseline=BASELINE,source=MELONX_SOURCE,run=MELONX_RUN,job=MELONX_JOB,compileRun=MELONX_RUN,originalRunConclusion='success',validationSource=MELONX_SOURCE,metadata=metadata,artifact=MELONX_ARTIFACT_ID,expectedArchiveSHA256=MELONX_ARTIFACT_SHA256,
             images={'ios-arm64':dict(sha256=identity['sha256'],bytes=len(raw),identitySHA256=IDENTITY_SHA256['ios-arm64'],platform=image['platform'],requiredExports=len(EXPORTS))},
             baselineReceipt=dict(path=BASELINE_RECEIPT,sha256=BASELINE_RECEIPT_SHA256,source=BASELINE_SOURCE,run=BASELINE_RUN,ipaSHA256=BASELINE_IPA_SHA256),
             authoritativePayload='ios-arm64/Ryujinx.Library.dylib',originalPayloadFingerprint=fingerprint,originalCompileIdentitiesPreserved=True,
             freshAppleGatesInProducer=3,reusedAppleGatesInProducer=32,producerSimulatorSessions=2,engineRecompiled=False,priorGatesReexecuted=False,
             physicalDeviceTested=False,gameTested=False,fpsGainMeasured=False)
