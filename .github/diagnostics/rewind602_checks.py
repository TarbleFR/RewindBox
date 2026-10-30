"""Authenticate exact successful Apple/Flutter receipts; never replay native fixtures."""
import hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
EVIDENCE=ROOT/'docs/evidence/melonx-jit-helper-init-20261030'
OUT=ROOT/'build/delivery'
HELPER_SOURCE='db7aa6e820769542fdeb45733998a53c4ab5d73d'
HOST_SOURCE='d3a75178a445ff7a1cf6a16109f9b388b10ff610'
POLICY_SOURCE='d042eefbaf5544e58faac91bf1680f7ff2f6dc93'
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
 for path,h in policy['inputs'].items():original(path,h,POLICY_SOURCE)
 policy_origin=require_run(41074846925,124128167471,POLICY_SOURCE,['Execute the actual title-gated Hogwarts policy on Apple','Exercise Hogwarts graphics switches and durable opt-outs','Analyze the changed profile service and UI'])
 host_path=ROOT/'docs/evidence/melonx-hogwarts-lots-20261030/apple-host.json'
 assert sha(host_path.read_bytes())=='c15c076205b5af5002fd65863f9af4cd4179f4a5587d99281974579b289e4563'
 host=read(host_path);assert host['result']=='passed' and host['tests']==23 and host['analyzer']=='passed'
 for path,h in host['sourceSHA256'].items():original(path,h,HOST_SOURCE)
 # Close Dart dependencies transitively, including package Dart and lockfiles.
 assert subprocess.check_output(['git','diff','--name-only',HOST_SOURCE,'HEAD','--','*.dart','**/pubspec.yaml','pubspec.yaml','pubspec.lock'],cwd=ROOT)==b''
 host_origin=require_run(41029226263,123974653945,HOST_SOURCE,['Test actual profile files, conflicts, recovery and experimental consent','Analyze the changed profile service and UI'])
 OUT.mkdir(parents=True,exist_ok=True)
 def save(name,value):(OUT/name).write_text(json.dumps(value,indent=2)+'\n')
 save('melonx-jit-helper-init.json',helper)
 save('hogwarts602-policy-checks.json',dict(policy,reusedFrom=policy_origin,testsReexecuted=False))
 save('hogwarts602-flutter-checks.json',dict(result='passed',tests=23,reusedFrom=host_origin,testsReexecuted=False))
 report=dict(result='passed',build=602,helper=helper_origin,policy=policy_origin,flutter=host_origin,
             originalAppleHelperReceiptSHA256=sha((EVIDENCE/'apple.json').read_bytes()),
             wholeScriptChecks=99,protocolChecks=101,appleJavaScriptCoreSessions=14,testsReexecuted=False,
             nativeCoreRecompiled=False,physicalDeviceTested=False)
 save('host602-reuse.json',report)
 return report


if __name__=='__main__':print(json.dumps(verify(),indent=2))
