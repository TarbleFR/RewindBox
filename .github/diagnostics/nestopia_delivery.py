"""Reuse Build 470's unchanged app evidence and require the new Nestopia witness.

This candidate has one changed core. No arbitrary product-file exemptions and
no automatic rerun of successful unrelated tests on a failed provenance check.
"""
import argparse,hashlib,json,os,re,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE_REF='a43a570412ed2bf382d2df3acc0a9ce9ca88c27c'
BASE_RUN=39078262825
CORE_REF='a518034e826258b1e2aa20f7abddb00d750411b4'
CORE_BINARY_REF='c3408821b2b9c47c6e31ae25b45c113aa9fd3f74'
CORE_RUN=39081741396
DELIVERY_ONLY={'.github/workflows/retroarch-delivery.yml',
               '.github/diagnostics/nestopia_delivery.py','.github/diagnostics/nestopia_delivery_test.py',
               'docs/build471-nestopia-reset.md','AGENTS.md'}
def command(args):return subprocess.check_output(args,cwd=ROOT,text=True).strip()
def api(path):return json.loads(command(['gh','api','repos/TarbleFR/neostation-ios/'+path]))
def validate_changed_paths(paths):
 invalid=set(paths)-DELIVERY_ONLY
 if invalid:raise ValueError('Unvalidated product or core recipe changes: '+', '.join(sorted(invalid)))
def source_closure():
 paths=command(['git','diff','--name-only',CORE_REF,'HEAD']).splitlines()
 validate_changed_paths(paths)
 # Also reject unstaged/staged edits in every pinned file on the runner.
 paths=command(['git','diff','--name-only',CORE_REF]).splitlines()
 validate_changed_paths(paths)
 command(['git','diff','--exit-code',BASE_REF,CORE_REF,'--','lib','packages','assets','test','pubspec.yaml','pubspec.lock','build-utils'])
 command(['git','diff','--exit-code',CORE_BINARY_REF,CORE_REF,'--','native/nestopia','.github/diagnostics/nestopia_bgcolor/build.py','build-utils/libretro'])
 return {p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
         command(['git','ls-files']).splitlines() if p not in DELIVERY_ONLY and (ROOT/p).is_file()}
def validate_verdicts(core,skin):
 if (core.get('result')!='passed' or core.get('source')!=CORE_REF
     or core.get('physicalDeviceValidated') is not False or core.get('baselineMatchesDeviceFault') is not True):
  raise ValueError('Missing actual core regression witness')
 rows=core.get('results',[]);base=[r for r in rows if r.get('label')=='baseline'];fixed=[r for r in rows if r.get('label')=='fixed']
 if (len(rows)!=6 or len(base)!=1 or base[0].get('faultOffset')!='0x45cc8'
     or 'FIRST_FRAME' in base[0].get('log','') or 'fatal signal=' not in base[0].get('fault','')
     or any(not isinstance(r.get('cppAllocationsPoisoned'),int) or r['cppAllocationsPoisoned']<1 for r in rows)):
  raise ValueError('Old iPhone fault was not reproduced with a nonzero heap')
 if ({r.get('filter') for r in fixed}!={'composite','svideo','rgb','monochrome','disabled'}
     or any(r.get('fault') or not re.search(r'^EXIT=0$',r.get('log',''),re.M) or not re.search(r'\bframes=120$',r.get('log',''),re.M) for r in fixed)):
  raise ValueError('Corrected first-frame/reset coverage incomplete')
 if (skin.get('result')!='passed' or skin.get('source')!=CORE_REF or skin.get('sessions')!=6
     or skin.get('failures')!=[] or not isinstance(skin.get('cppPoisonLogEntries'),int) or skin['cppPoisonLogEntries']<1
     or skin.get('physicalDeviceValidated') is not False or skin.get('outcome',{}).get('finished') is not True):
  raise ValueError('Actual original-skin integration did not pass')
 return {'core':core,'skin':skin}
def successful_run(run_id,ref,path,required):
 run=api(f'actions/runs/{run_id}')
 if (run.get('head_sha')!=ref or run.get('path')!=path or run.get('status')!='completed' or run.get('conclusion')!='success'):
  raise ValueError('Wrong or unsuccessful CI provenance: '+str(run_id))
 jobs=api(f'actions/runs/{run_id}/jobs?per_page=100')['jobs']
 for name in required:
  match=[j for j in jobs if j['name']==name]
  if len(match)!=1 or match[0].get('head_sha')!=ref or match[0].get('conclusion')!='success':
   raise ValueError('Required validated job missing: '+name)
 return jobs
def evidence():
 successful_run(BASE_RUN,BASE_REF,'.github/workflows/retroarch-delivery.yml',['checks','native','Release device build • cold'])
 jobs=successful_run(CORE_RUN,CORE_REF,'.github/workflows/nestopia-bgcolor.yml',['nestopia-reset'])
 required={'Reuse unchanged production frontend and all unrelated cores','Verify and reuse the already compiled Nestopia correction',
           'Reproduce the exact old iPhone fault and exercise corrected NTSC modes','Run corrected core with original skin and nonzero heap initialization'}
 if not required<={s['name'] for s in jobs[0]['steps'] if s.get('conclusion')=='success'}:
  raise ValueError('Targeted proof steps incomplete')
 with tempfile.TemporaryDirectory(prefix='nestopia-witness-') as tmp:
  subprocess.run(['gh','run','download',str(CORE_RUN),'--repo','TarbleFR/neostation-ios',
                  '--name','nestopia-reset-proof-'+CORE_REF,'--dir',tmp],check=True)
  records={}
  for part in ('core','skin'):
   paths=[p for p in Path(tmp).rglob('verdict.json') if p.parent.name=='nestopia-'+part]
   if len(paths)!=1:raise ValueError('Ambiguous or absent '+part+' verdict')
   records[part]=json.loads(paths[0].read_text())
  return validate_verdicts(records['core'],records['skin'])
def main():
 p=argparse.ArgumentParser();p.add_argument('--dart-evidence',action='store_true');p.add_argument('--libretro-evidence',action='store_true')
 p.add_argument('--skin-session-evidence',action='store_true');p.add_argument('--scope',default='full',choices=['full'])
 p.add_argument('--output',default='build/delivery/reused-validation.json');a=p.parse_args()
 hashes=source_closure();witness=evidence()
 record={'result':'passed','testedSHA':BASE_REF,'validationWasReused':True,'reusedFromRun':BASE_RUN,
         'unchangedInputsSHA256':hashes,'compiledCoreSource':CORE_BINARY_REF,'targetedCoreSource':CORE_REF,'targetedCoreRun':CORE_RUN,
         'targetedCoreEvidence':witness,'deviceGameplayValidated':False}
 if a.dart_evidence:record.update(key=os.environ['DART_VALIDATION_KEY'],tool='Flutter 3.47.2, Ubuntu 24.04')
 if a.libretro_evidence:
  xcode=command(['xcodebuild','-version']);sdk=command(['xcrun','--sdk','iphoneos','--show-sdk-version'])
  if xcode!='Xcode 26.3\nBuild version 17C529' or sdk!='26.2':raise ValueError('Changed native toolchain')
  record.update(xcode=xcode,iphoneSDK=sdk)
 out=ROOT/a.output;out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(record,indent=2)+'\n')
 print('Reused successful Build 470 app/skin/cheat checks; required the exact new Nestopia fault reproduction and corrected-core tests.')
if __name__=='__main__':main()
