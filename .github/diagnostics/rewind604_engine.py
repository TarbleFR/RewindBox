"""Authenticate the compiled guard-diagnostic MeloNX core for private IPA604.

Only the new component, its current host boundary and its immutable producer
receipts are checked. No compiler, simulator or historical fixture is executed.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import zipfile
import rewind596_engine as parsing

ROOT=Path(__file__).resolve().parents[2]
NEW=ROOT/'dist/melonx'
BUILD=604
BASELINE=603
PREPARATION_INPUT_COUNT=120
PREPARED_MEMBER_COUNT=160
FRESH_APPLE_GATES=3
REUSED_APPLE_GATES=36
HISTORICAL_APPLE_RECEIPTS=37
BASELINE_SOURCE='808b64e16bb0f5112a2a7b5a07b400c19bb9cfbd'
BASELINE_RUN=41102769156
BASELINE_IPA_SHA256='4807cba308ec8fd0cf47a912afddaae8c0f781c20c42a8e14e7af61bfe44dddd'
BASELINE_RECEIPT='docs/evidence/rewind603-delivery.json'
BASELINE_RECEIPT_SHA256='743dd950f710d118f81ace9375549ff561cac6e613caf9c4d3e7b8182ce77f4e'
MELONX_SOURCE='ada4058f5738465ac882934bb87224b637bcd0a1'
MELONX_VALIDATION_SOURCE='510e683a149e811e68ea6ab5e766e85c44ab1057'
MELONX_RUN=41121572662  # Actual runtime success remains required
MELONX_JOB=124288787086
MELONX_WORKFLOW='.github/workflows/melonx-guard-runtime-validation.yml'
MELONX_COMPILE_RUN=41118873328
MELONX_COMPILE_JOB=124280125758
MELONX_COMPILE_ARTIFACT=13007577275
MELONX_COMPILE_ARCHIVE_SHA256='93771c1ff47396f841534463ec6ea49ad3657d8a815e8c39c3d63e138c926395'
MELONX_ARTIFACT_ID=13009521221
MELONX_ARTIFACT_NAME='MeloNX-ada4058-runtime-validation-41121572662'
MELONX_ARTIFACT_BYTES=87656173
MELONX_ARTIFACT_SHA256='ed70ba31b1b52fc0fbd55e695b25cc4254d5f90c4f86b930d8bf2958235ac278'
MELONX_ARTIFACT=(MELONX_ARTIFACT_ID,MELONX_ARTIFACT_SHA256)
RUNTIME_CONTRACT_PATH='build-utils/melonx/guard-runtime-validation.json'
RUNTIME_CONTRACT_SHA256='ea8d083817dd697f8498d0ef3c7d88c7fb82e5709285a23b76c96dcfb589098e'
RUNTIME_RESULT_SHA256='3d56f23c61d379728eb62d514449c7ce20d02c5d95f22551a44b44f84efea6c3'
PACKAGED_ID=parsing.PACKAGED_ID
EXPORTS=parsing.EXPORTS
check_image=parsing.check_image
image_info=parsing.image_info
normalized_payload_fingerprint=parsing.normalized_payload_fingerprint
PACKAGED_FINGERPRINT='85cc56d985e6f0a2dcce559dfd099d9f4dd574e61cfb0066c9e715a5bbbf5c7a'
BINARY_SHA256={
 'ios-arm64':'7620fa3009e6df971665e7b8adec1a0bac654e6efa4bc3fceb292daefa6adb55',
 'iossimulator-arm64':'fa3b21ce8e8ecfbfe6c2517ef45236d044a32cffb7e3d999167227741399dc95',
}
BINARY_BYTES={'ios-arm64':37618032,'iossimulator-arm64':37928552}
IDENTITY_SHA256={
 'ios-arm64':'0671f003a26d3b81ee396c156efbad0512b53537b854f1722448c06f679875eb',
 'iossimulator-arm64':'68e73a5df4767e615c0aca5d99c98242b9fdfa776ad89b7e34eb404dcd7b020d',
}
ENGINE_STEPS={
 'Verify primary failure evidence survives diagnostic timeouts',
 'Restore unchanged native dependencies',
 'Authenticate original compiled Core and successful gates',
 'Validate unchanged Core in ARM64 simulator',
 'Preserve original failure and verify fresh runtime proof',
}



def require(condition,message):
 if not condition:raise ValueError(message)


def sha(data):return hashlib.sha256(data).hexdigest()


def api(endpoint):
 for attempt in range(3):
  try:return json.loads(subprocess.check_output(['gh','api','repos/TarbleFR/RewindBox/'+endpoint],cwd=ROOT,timeout=120))
  except subprocess.CalledProcessError:
   if attempt==2:raise
   time.sleep(2**attempt)


def baseline_component():
 raw=(ROOT/BASELINE_RECEIPT).read_bytes();require(sha(raw)==BASELINE_RECEIPT_SHA256,'Delivered603 receipt drift')
 value=json.loads(raw)
 require(value['result']=='passed'and value['source']==BASELINE_SOURCE and value['run']==BASELINE_RUN and value['ipaSHA256']==BASELINE_IPA_SHA256,'Wrong immediate baseline')
 require(value['melonx']['source']=='1630bd0230c9431de92faec9c5e2662262b1ede6'and value['melonx']['payloadMatched']is True,'Unexpected prior MeloNX selection')
 require(value['rpcs3']['source']=='378509e82d360bc2cb2fcc9fb23d4d9d98787506'and value['rpcs3']['payloadMatched']is True,'Changed retained RPCS3 selection')
 return value['melonx']


def runtime_contract():
 raw=(ROOT/RUNTIME_CONTRACT_PATH).read_bytes()
 require(sha(raw)==RUNTIME_CONTRACT_SHA256,'Runtime validation contract changed or pending')
 pin=json.loads(raw)
 require(pin['source']==MELONX_SOURCE and pin['run']==MELONX_COMPILE_RUN and pin['job']==MELONX_COMPILE_JOB and pin['artifact']==MELONX_COMPILE_ARTIFACT and pin['archiveSha256']==MELONX_COMPILE_ARCHIVE_SHA256,'Wrong original compile selection')
 require(pin['binarySha256']==BINARY_SHA256 and pin['identitySha256']==IDENTITY_SHA256,'Changed original compiled bytes')
 for path,digest in {**pin['validationInputs'],RUNTIME_CONTRACT_PATH:RUNTIME_CONTRACT_SHA256}.items():
  require(sha((ROOT/path).read_bytes())==digest,'Changed runtime validation recipe: '+path)
  require(sha(subprocess.check_output(['git','show',MELONX_VALIDATION_SOURCE+':'+path],cwd=ROOT))==digest,'Validation source mismatch: '+path)
 return pin


def _query_engine_run():
 require(all(value is not None for value in (MELONX_VALIDATION_SOURCE,MELONX_RUN,MELONX_JOB,MELONX_ARTIFACT_ID,MELONX_ARTIFACT_BYTES,MELONX_ARTIFACT_SHA256,RUNTIME_CONTRACT_SHA256,RUNTIME_RESULT_SHA256)), 'Pending independently verified runtime validation pins')
 sys.path.insert(0,str(ROOT/'build-utils/melonx'))
 from validate_runtime_reuse import authenticate_metadata
 baseline_component();pin=runtime_contract()
 original_run=api(f'actions/runs/{MELONX_COMPILE_RUN}')
 original_job=api(f'actions/jobs/{MELONX_COMPILE_JOB}')
 original_artifact=api(f'actions/artifacts/{MELONX_COMPILE_ARTIFACT}')
 authenticate_metadata(pin,original_run,original_job,original_artifact)
 run=api(f'actions/runs/{MELONX_RUN}');jobs=api(f'actions/runs/{MELONX_RUN}/jobs?per_page=100')['jobs']
 matches=[item for item in jobs if item['id']==MELONX_JOB]
 require(len(matches)==1,'Missing exact runtime validation job');job=matches[0]
 artifact=api(f'actions/artifacts/{MELONX_ARTIFACT_ID}')
 require(run['head_sha']==MELONX_VALIDATION_SOURCE and run['path']==MELONX_WORKFLOW and run['run_attempt']==1 and run['conclusion']=='success'and run['status']=='completed','Wrong runtime validation run')
 require(job['run_id']==MELONX_RUN and job['head_sha']==MELONX_VALIDATION_SOURCE and job['conclusion']=='success'and job['run_attempt']==1,'Wrong runtime validation job')
 require(ENGINE_STEPS<={s['name']for s in job['steps']if s['conclusion']=='success'},'Missing successful runtime validation steps')
 require(artifact['id']==MELONX_ARTIFACT_ID and artifact['name']==MELONX_ARTIFACT_NAME=='MeloNX-ada4058-runtime-validation-'+str(MELONX_RUN) and artifact['size_in_bytes']==MELONX_ARTIFACT_BYTES and artifact['digest']=='sha256:'+MELONX_ARTIFACT_SHA256 and not artifact['expired']and artifact['workflow_run']['id']==MELONX_RUN and artifact['workflow_run']['head_sha']==MELONX_VALIDATION_SOURCE,'Wrong validated engine archive metadata')
 return dict(result='passed',source=MELONX_SOURCE,run=MELONX_RUN,job=MELONX_JOB,runAttempt=1,compileRun=MELONX_COMPILE_RUN,compileJob=MELONX_COMPILE_JOB,compileArtifact=MELONX_COMPILE_ARTIFACT,originalRunConclusion='failure',originalCompileStepsConclusion='success',validationSource=MELONX_VALIDATION_SOURCE,artifact=MELONX_ARTIFACT_ID,artifactSHA256=MELONX_ARTIFACT_SHA256,engineRecompiled=False,priorGatesReexecuted=False)


def engine_run():
 sys.path.insert(0,str(ROOT/'build-utils'))
 from delivery_contract_memo import reuse
 return reuse('604-melonx-run',_query_engine_run)


def engine_identity(runtime='ios-arm64'):
 require(runtime in BINARY_SHA256,'Unknown runtime')
 raw=(NEW/runtime/'identity.json').read_bytes();require(sha(raw)==IDENTITY_SHA256[runtime],'Original compiled identity drift')
 identity=json.loads(raw)
 require(identity['host']==MELONX_SOURCE and identity['runtimeIdentifier']==runtime and identity['sha256']==BINARY_SHA256[runtime]and identity['size']==BINARY_BYTES[runtime],'Compiled engine identity mismatch')
 require(identity['source']==json.loads((ROOT/'build-utils/melonx/source.json').read_bytes())and identity['embeddedLibraryAbi']==2 and identity['embeddedSessionDeviceVerified']is False and sorted(identity['exports'])==sorted(EXPORTS),'Host/Core boundary mismatch')
 require(len(identity['adaptations'])==PREPARATION_INPUT_COUNT,'Wrong compiled input count')
 for path,h in identity['adaptations'].items():require(sha((ROOT/path).read_bytes())==h,'Changed engine preparation input: '+path)
 return identity


def engine_evidence():
 metadata=engine_run();identity=engine_identity();raw=(NEW/'ios-arm64/Ryujinx.Library.dylib').read_bytes()
 require(len(raw)==BINARY_BYTES['ios-arm64']and sha(raw)==BINARY_SHA256['ios-arm64'],'Wrong iOS payload')
 image=check_image(raw,'ios-arm64');fingerprint=normalized_payload_fingerprint(raw)
 require(fingerprint==PACKAGED_FINGERPRINT,'Wrong original compiled payload fingerprint')
 sys.path.insert(0,str(ROOT/'build-utils/melonx'))
 import validate_guard_runtime as validator
 from validate_runtime_reuse import authenticate_metadata,verify_smoke_report,verify_dependencies,HOST_INPUTS
 pin=runtime_contract()
 result_bytes=(NEW/'runtime-validation/result.json').read_bytes()
 require(sha(result_bytes)==RUNTIME_RESULT_SHA256,'Changed successful runtime validation receipt')
 result=json.loads(result_bytes);preparation=json.loads((NEW/'runtime-validation/preparation.json').read_bytes())
 require(result['result']=='passed'and preparation['result']=='authenticated','Missing runtime validation result')
 for key,value in preparation.items():
  if key!='result':require(result[key]==value,'Runtime preparation changed: '+key)
 expected_validation=dict(source=MELONX_VALIDATION_SOURCE,run=MELONX_RUN,runAttempt=1,url='https://github.com/TarbleFR/RewindBox/actions/runs/'+str(MELONX_RUN),purpose='runtime validation only; original engine was not recompiled')
 require(result['validation']==expected_validation and result['engineSource']==MELONX_SOURCE and result['originalRun']==MELONX_COMPILE_RUN and result['originalJob']==MELONX_COMPILE_JOB and result['originalArtifact']==MELONX_COMPILE_ARTIFACT,'Wrong split producer provenance')
 require(result['originalRunConclusion']=='failure'and result['originalFailedStep']==pin['failedStep']and result['originalSmokeStructuredResultAvailable']is False,'Original failure was relabeled')
 require(result['priorSuccessfulStepsReused']==pin['requiredSuccessfulSteps']and result['compileProofSha256']==pin['compileProofSha256'],'Original compilation proof changed')
 require(result['archiveSha256']==MELONX_COMPILE_ARCHIVE_SHA256 and result['coreContractSha256']==pin['coreContractSha256'],'Original Core contract changed')
 authenticate_metadata(pin,*(json.loads((NEW/('runtime-validation/original-'+name+'.json')).read_bytes())for name in ('run','job','artifact')))
 require(result['engine']==validator.verify_original(NEW,pin,validator.OLD_SMOKE),'Original compiled engine or scoped gate receipts changed')
 require(result['engine']['binaryBytes']==BINARY_BYTES and result['engine']['binarySha256']==BINARY_SHA256 and result['engine']['identitySha256']==IDENTITY_SHA256,'Wrong compiled engine bytes')
 require(result['inputs']=={**pin['validationInputs'],RUNTIME_CONTRACT_PATH:RUNTIME_CONTRACT_SHA256},'Wrong runtime validation source scope')
 require(result['nativeDependencies']==verify_dependencies(pin),'Current native dependency bytes differ from validated simulator')
 require(result['freshAppleGates']==FRESH_APPLE_GATES and result['reusedAppleGates']==REUSED_APPLE_GATES and result['historicalAppleReceipts']==HISTORICAL_APPLE_RECEIPTS,'Wrong original gate scope')
 require(result['homebrewSimulatorSessions']==result['releasedBackingSessions']==2 and result['smokeStepOutcome']=='success'and result['validationError']is None,'Wrong fresh runtime or teardown proof')
 require(all(result[key]is False for key in ('engineRecompiled','priorGatesReexecuted','nativeDependenciesRecompiled','physicalDeviceTested','gameplayTested')),'Mis-scoped runtime proof')
 contract=json.loads((ROOT/'build-utils/melonx/guard-core-contract.json').read_bytes())
 for name,scope in contract['auxiliaryHistoricalReceipts'].items():
  historical=json.loads((NEW/('historical-1630/'+name)).read_bytes())
  require(historical['reports']['candidate']['normal']['checks']==10 and historical['reports']['candidate']['failures']['checks']==138 and scope['currentFullFixtureProof']is False and scope['supersededBy']=='occlusion-completion-checks.json','Overstated historical GAL scope')
  overlap={path:digest for path,digest in historical['compiledProductionFiles'].items()if path in contract['productionChanges']}
  require(overlap==scope['supersededProductionInputs']and len(overlap)==2 and all(contract['preparedMembers'][path]!=digest for path,digest in overlap.items()),'Wrong superseded historical GAL dependencies')
 require(result['correctedSmoke']=='runtime-smoke/actual-runtime.json','Wrong runtime proof path')
 smoke_bytes=(NEW/result['correctedSmoke']).read_bytes();smoke=json.loads(smoke_bytes)
 require(sha(smoke_bytes)==result['correctedSmokeSha256'],'Changed fresh runtime proof')
 verify_smoke_report(smoke,pin,{path:sha((ROOT/path).read_bytes())for path in (*HOST_INPUTS,pin['smoke']['path'])})
 require(smoke['actualNativeAOT']is True and smoke['gameplayTested']is False and smoke['iphoneGuestExecutionTested']is False,'Wrong simulator scope')
 for runtime in BINARY_SHA256:engine_identity(runtime)
 return dict(result='passed',build=BUILD,baseline=BASELINE,source=MELONX_SOURCE,run=MELONX_RUN,job=MELONX_JOB,compileRun=MELONX_COMPILE_RUN,originalRunConclusion='failure',originalCompileStepsConclusion='success',validationSource=MELONX_VALIDATION_SOURCE,metadata=metadata,artifact=MELONX_ARTIFACT_ID,expectedArchiveSHA256=MELONX_ARTIFACT_SHA256,
             images={'ios-arm64':dict(sha256=identity['sha256'],bytes=len(raw),identitySHA256=IDENTITY_SHA256['ios-arm64'],platform=image['platform'],requiredExports=len(EXPORTS))},
             baselineReceipt=dict(path=BASELINE_RECEIPT,sha256=BASELINE_RECEIPT_SHA256,source=BASELINE_SOURCE,run=BASELINE_RUN,ipaSHA256=BASELINE_IPA_SHA256),
             authoritativePayload='ios-arm64/Ryujinx.Library.dylib',originalPayloadFingerprint=fingerprint,originalCompileIdentitiesPreserved=True,
             freshAppleGatesInProducer=FRESH_APPLE_GATES,reusedAppleGatesInProducer=REUSED_APPLE_GATES,historicalAppleReceiptsInProducer=HISTORICAL_APPLE_RECEIPTS,auxiliaryHistoricalGalReceiptCount=1,auxiliaryCurrentFullFixtureProof=False,producerSimulatorSessions=2,engineRecompiled=False,priorGatesReexecuted=False,
             physicalDeviceTested=False,gameTested=False,fpsGainMeasured=False)
