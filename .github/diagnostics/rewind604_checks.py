"""Authenticate exact scoped Apple/Flutter execution receipts; never replay native fixtures."""
import hashlib,io,json,subprocess,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'docs/evidence/melonx-jit-helper-init-20261030'
OUT=ROOT/'build/delivery'
HELPER_SOURCE='db7aa6e820769542fdeb45733998a53c4ab5d73d'
HOST_SOURCE='d3a75178a445ff7a1cf6a16109f9b388b10ff610'
POLICY_SOURCE='d042eefbaf5544e58faac91bf1680f7ff2f6dc93'
FRESH_HOST_SOURCE='3c47542cd3a732d60f11a97fe9e6baf42e483539'
FRESH_HOST_RUN=41119381432  # Actual tests passed; original receipt parser failed
FRESH_HOST_JOB=124281873638
FRESH_HOST_ARTIFACT=13008895566
FRESH_HOST_ARTIFACT_BYTES=6148
FRESH_HOST_ARTIFACT_SHA256='618cf64968a41b554ca691499a645590fca03d85972035064ab6246a59b31b30'
RECOVERED_HOST_RESULT_SHA256='04b37e3a9fd1797a6d5e2bc6b96ee2645bfae2c88d8fbb4af9d4f0f0e24a22d4'
HOST_PARSER_PATH='.github/diagnostics/melonx_unreal_completion_host.py'
HOST_PARSER_SHA256='dba832faf18734f16e1c9d2ae93fce6820d5220596f425b4977fd4679dd2932d'
CHANGED_HOST_PATHS={
 'lib/l10n/melonx_unreal_profile_locale.dart',
 'lib/widgets/melonx_unreal_profile_dialog.dart',
 'lib/widgets/melonx_internal_playlist_actions.dart',
 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
}
PRESENTATION_PATH='packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift'
CHANGED_HOST_TEST_PATHS={
 'test/melonx_unreal_profile_dialog_test.dart',
 'test/melonx_unreal_profile_locale_test.dart',
}
FRESH_HOST_STEPS={
 'Pin affected host inputs before execution',
 'Test translated consent and error presentation',
 'Analyze the changed dialog, catalogue and entry point',
 'Exercise the changed presentation in actual UIKit',
}
PINS={'apple.json': 'ece77fceb03e4068d60e4b17c12cd74080f9ed436aa0548b8bc7fff8568c31f9', 'apple-origin.json': 'c01c6c874b6aeff7ec31ad8fcbdf8c0ab29b4ed0d65d08a3bf07390dd0f1350a', 'policy601.json': 'd7e3769b6e3b54940f88069458a3196b05e42448b4112584e6d68e014c8da2c6'}


def sha(raw):return hashlib.sha256(raw).hexdigest()
def read(path):return json.loads(path.read_bytes())
def api(path):return json.loads(subprocess.check_output(['gh','api','repos/TarbleFR/RewindBox/'+path],cwd=ROOT))
def original(path,digest,source):
 assert sha((ROOT/path).read_bytes())==digest
 assert sha(subprocess.check_output(['git','show',source+':'+path],cwd=ROOT))==digest


def require_run(run_id,job_id,source,steps):
 run=api('actions/runs/'+str(run_id));job=api('actions/jobs/'+str(job_id))
 assert run['head_sha']==job['head_sha']==source and run['run_attempt']==job['run_attempt']==1
 assert run['conclusion']==job['conclusion']=='success' and run['status']==job['status']=='completed'
 assert job['run_id']==run_id
 assert set(steps)<={s['name']for s in job['steps']if s['conclusion']=='success'}
 return dict(source=source,run=run_id,job=job_id,attempt=1,testsReexecuted=False)


def fresh_host():
 assert sha((ROOT/HOST_PARSER_PATH).read_bytes())==HOST_PARSER_SHA256, 'Reviewed receipt parser changed'
 run=api('actions/runs/'+str(FRESH_HOST_RUN))
 jobs=api('actions/runs/'+str(FRESH_HOST_RUN)+'/jobs?per_page=100')['jobs']
 selected=[item for item in jobs if item['id']==FRESH_HOST_JOB]
 assert len(selected)==1
 job=selected[0]
 assert run['head_sha']==job['head_sha']==FRESH_HOST_SOURCE and run['run_attempt']==job['run_attempt']==1
 assert run['path']=='.github/workflows/melonx-completion-host.yml'
 assert run['conclusion']==job['conclusion']=='failure' and run['status']==job['status']=='completed'
 assert job['run_id']==FRESH_HOST_RUN
 assert FRESH_HOST_STEPS <= {item['name']for item in job['steps']if item['conclusion']=='success'}
 assert {item['name']for item in job['steps']if item['conclusion']=='failure'}=={'Bind fresh host results to exact source inputs'}
 artifact=api('actions/artifacts/'+str(FRESH_HOST_ARTIFACT))
 assert artifact['name']=='MeloNX-completion-host-'+FRESH_HOST_SOURCE and not artifact['expired']
 assert artifact['digest']=='sha256:'+FRESH_HOST_ARTIFACT_SHA256 and artifact['size_in_bytes']==FRESH_HOST_ARTIFACT_BYTES
 assert artifact['workflow_run']['id']==FRESH_HOST_RUN and artifact['workflow_run']['head_sha']==FRESH_HOST_SOURCE
 raw=subprocess.check_output(['gh','api','repos/TarbleFR/RewindBox/actions/artifacts/'+str(FRESH_HOST_ARTIFACT)+'/zip'],cwd=ROOT,timeout=300)
 assert len(raw)==FRESH_HOST_ARTIFACT_BYTES and sha(raw)==FRESH_HOST_ARTIFACT_SHA256
 with zipfile.ZipFile(io.BytesIO(raw))as archive:
  expected={'preflight.json','flutter-tests.jsonl','analyzer.txt','analyzer-stderr.txt','analyzer-execution.json','presentation.json'}
  assert len(archive.namelist())==len(expected) and set(archive.namelist())==expected and archive.testzip()is None
  outputs={name:archive.read(name)for name in expected}
  preflight=json.loads(outputs['preflight.json'])
  assert preflight['result']=='prepared' and preflight['execution']==dict(source=FRESH_HOST_SOURCE,run=FRESH_HOST_RUN,attempt=1)
  from melonx_unreal_completion_host import INPUT_PATHS,result_from_outputs
  assert set(preflight['inputs'])==set(INPUT_PATHS)
  for path,digest in preflight['inputs'].items():
   assert sha(subprocess.check_output(['git','show',FRESH_HOST_SOURCE+':'+path],cwd=ROOT))==digest,path
   if path!=HOST_PARSER_PATH:assert sha((ROOT/path).read_bytes())==digest,path
  assert set(preflight['productPaths'])==CHANGED_HOST_PATHS and set(preflight['testPaths'])==CHANGED_HOST_TEST_PATHS
  # Parsing is recovered here; the actual Flutter/analyzer/UIKit execution stays
  # attributed to the original run, whose overall failure is never relabeled.
  result=result_from_outputs(preflight,outputs)
  assert sha((json.dumps(result,indent=2)+'\n').encode())==RECOVERED_HOST_RESULT_SHA256
  assert result['tests']==19 and result['sidebandEvents']=={'test.startedProcess':2}
  assert result['dependencyPreambleLines']==83 and result['presentation']['reports'][0]['checks']==14
  assert result['analyzerDiagnostics']['errors']==result['analyzerDiagnostics']['warnings']==0
  evidence=OUT/'melonx-completion-host-original'
  evidence.mkdir(parents=True,exist_ok=True)
  for name,data in outputs.items():(evidence/name).write_bytes(data)
 recovery=dict(originalRunConclusion='failure',failedStep='Bind fresh host results to exact source inputs',
               successfulExecutionSteps=sorted(FRESH_HOST_STEPS),receiptOnly=True,testsReexecuted=False,
               parser=HOST_PARSER_PATH,parserSHA256=HOST_PARSER_SHA256,recoveredResultSHA256=RECOVERED_HOST_RESULT_SHA256)
 return dict(result,producer=dict(source=FRESH_HOST_SOURCE,run=FRESH_HOST_RUN,job=FRESH_HOST_JOB,artifact=FRESH_HOST_ARTIFACT,artifactSHA256=FRESH_HOST_ARTIFACT_SHA256,originalRunConclusion='failure'),receiptRecovery=recovery,testsReexecutedForDelivery=False)


def verify():
 for p,h in PINS.items():assert sha((EVIDENCE/p).read_bytes())==h,p
 helper=read(EVIDENCE/'apple.json')
 assert helper['result']=='passed' and helper['appleJavaScriptCore']['result']=='passed'
 assert helper['appleJavaScriptCore']['sessions']==14 and helper['wholeScript']['checks']==99 and helper['isolatedProtocol']['checks']==101
 assert helper['exactBlockRelocation']is True and helper['physicalDeviceTested']is False
 for path,h in helper['inputs'].items():original(path,h,HELPER_SOURCE)
 helper_origin=require_run(41083688288,124159148692,HELPER_SOURCE,['Reproduce delivered601 failure and execute complete corrected script in JavaScriptCore'])
 artifact=api('actions/artifacts/12991205870')
 assert artifact['digest']=='sha256:54f0e01ba6b19610d9dbcfd766d95faeacf25cfb7b664f06842c70d23fc8f570'
 assert artifact['size_in_bytes']==2523 and not artifact['expired'] and artifact['workflow_run']['head_sha']==HELPER_SOURCE
 policy=read(EVIDENCE/'policy601.json')
 assert policy['result']=='passed' and policy['swiftExecuted']is True and policy['swiftChecks']==3342
 for path,h in policy['inputs'].items():
  historical=subprocess.check_output(['git','show',POLICY_SOURCE+':'+path],cwd=ROOT)
  assert sha(historical)==h,path
  if path!=PRESENTATION_PATH:assert sha((ROOT/path).read_bytes())==h,path
  else:
   old=b'                        presenter.present(view,animated:true) {'
   new=b'                        // The engine starts in viewDidAppear, after its Metal view is attached.\n                        // Avoid putting the modal animation on every game\'s launch path.\n                        presenter.present(view,animated:false) {'
   current=(ROOT/path).read_bytes()
   assert historical.count(old)==1 and historical.replace(old,new)==current,'Unreviewed change in historical policy plugin boundary'
   historical_scope=historical.split(b'private func launch(',1)[1].split(b'try runtime.prepareJit(',1)[0]
   current_scope=current.split(b'private func launch(',1)[1].split(b'try runtime.prepareJit(',1)[0]
   assert historical_scope==current_scope,'Preflight, title policy and graphics handoff changed'
   assert current_scope.index(b'let preflight = try runtime.content')<current_scope.index(b'MeloNXHogwartsGraphics.resolve')<current_scope.index(b'try runtime.prepareGraphics(settings')
   policy_scope_digest=sha(current_scope)
 policy_origin=require_run(41074846925,124128167471,POLICY_SOURCE,['Execute the actual title-gated Hogwarts policy on Apple','Exercise Hogwarts graphics switches and durable opt-outs','Analyze the changed profile service and UI'])
 host_path=ROOT/'docs/evidence/melonx-hogwarts-lots-20261030/apple-host.json'
 assert sha(host_path.read_bytes())=='c15c076205b5af5002fd65863f9af4cd4179f4a5587d99281974579b289e4563'
 host=read(host_path);assert host['result']=='passed' and host['tests']==23 and host['analyzer']=='passed'
 for path,h in host['sourceSHA256'].items():
  assert sha(subprocess.check_output(['git','show',HOST_SOURCE+':'+path],cwd=ROOT))==h
  if path not in CHANGED_HOST_PATHS|CHANGED_HOST_TEST_PATHS:assert sha((ROOT/path).read_bytes())==h,path
 # Close the historical Dart boundary: only the freshly tested dialog/catalogue
 # and its entry-point label may differ. Service and graphics suites are reused.
 delta=set(subprocess.check_output(['git','diff','--name-only',HOST_SOURCE,'HEAD','--','*.dart','**/pubspec.yaml','pubspec.yaml','pubspec.lock'],cwd=ROOT,text=True).splitlines())
 assert delta=={path for path in CHANGED_HOST_PATHS if path.endswith('.dart')}|CHANGED_HOST_TEST_PATHS,delta
 fresh=fresh_host()
 host_origin=require_run(41029226263,123974653945,HOST_SOURCE,['Test actual profile files, conflicts, recovery and experimental consent','Analyze the changed profile service and UI'])
 OUT.mkdir(parents=True,exist_ok=True)
 def save(name,value):(OUT/name).write_text(json.dumps(value,indent=2)+'\n')
 save('melonx-jit-helper-init.json',helper)
 save('hogwarts604-policy-checks.json',dict(policy,reusedFrom=policy_origin,testsReexecuted=False,historicalFullPluginInputSuperseded=True,retainedLaunchPolicyPrefixSHA256=policy_scope_digest,currentPresentation=fresh['presentation'],currentPresentationSHA256=fresh['presentationSHA256']))
 save('unreal604-fresh-host.json',fresh)
 save('hogwarts604-flutter-checks.json',dict(result='passed',tests=21+fresh['tests'],historicalTests=23,historicalUnchangedTests=21,historicalSupersededDialogTests=2,freshTests=fresh['tests'],reusedFrom=host_origin,freshProducer=fresh['producer'],testsReexecuted=False))
 report=dict(result='passed',build=604,helper=helper_origin,policy=policy_origin,flutter=host_origin,freshFlutter=fresh['producer'],historicalFlutterTests=23,unchangedFlutterTests=21,supersededHistoricalDialogTests=2,freshFlutterTests=fresh['tests'],
             originalAppleHelperReceiptSHA256=sha((EVIDENCE/'apple.json').read_bytes()),
             wholeScriptChecks=99,protocolChecks=101,appleJavaScriptCoreSessions=14,testsReexecuted=False,
             nativeCoreRecompiled=False,physicalDeviceTested=False)
 save('host604-reuse.json',report)
 return report


if __name__=='__main__':print(json.dumps(verify(),indent=2))
