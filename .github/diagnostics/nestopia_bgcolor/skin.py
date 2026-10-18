"""Focused integration of the corrected core with unchanged production skins/session."""
import argparse,json,os,re,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'test'));sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import libretro_simulator_probe as probe
import libretro_nestopia_skin_stability_probe as original
import libretro_skin_press_probe as press
from libretro_simulator_device import pick_notched_device
def compile_with_poison(sources,sdk,work,app):
 dylib=app/'Frameworks/libNestopiaPoison.dylib';original_run=probe.run
 original_run(['xcrun','--sdk','iphonesimulator','clang++','-target',probe.TARGET,'-isysroot',sdk,
               '-O1','-std=c++17','-dynamiclib',Path(__file__).parent/'poison.cpp',
               '-Wl,-install_name,@rpath/libNestopiaPoison.dylib','-o',dylib])
 original_run(['codesign','--force','--sign','-','--timestamp=none',dylib])
 def link_with_poison(command,**kwargs):
  if str(app/'Probe') in [str(x) for x in command] and '-c' not in command:
   command=list(command)+[str(dylib),'-Wl,-u,_nestopia_poisoned_allocations','-lc++']
  return original_run(command,**kwargs)
 probe.run=link_with_poison
 try:original_compile(sources,sdk,work,app)
 finally:probe.run=original_run
original_compile=probe.compile_probe
def main():
 p=argparse.ArgumentParser()
 for key in ('cores','inputs','evidence','label'):p.add_argument('--'+key,required=True)
 a=p.parse_args();a.sources=None;a.only=[];a.lot1=a.lot2=a.official_shaders=False
 probe.REAL_CORES=('nestopia',);probe.pick_device=pick_notched_device
 probe.compile_probe=compile_with_poison
 selected=original.scenarios()
 probe.SCENARIOS=[selected[0],selected[1],selected[2],selected[80],selected[81],selected[-2]]
 for s in probe.SCENARIOS:
  s['runSeconds']=2.0;s['optionDefaults']={'nestopia_blargg_ntsc_filter':'composite'}
 evidence=Path(a.evidence);evidence.mkdir(parents=True,exist_ok=True)
 os.environ['SIMCTL_CHILD_MallocPreScribble']='1'
 with tempfile.TemporaryDirectory(prefix='nestopia-reset-skin-') as tmp:
  app,scenarios=probe.assemble(a,probe.BRIDGE,Path(tmp))
  path=app/'probe-config.json';config=json.loads(path.read_text());config['forceLandscape']=True
  # assemble adds catalogue defaults; explicitly select the affected real filter.
  for s in config['scenarios']:s['optionDefaults']['nestopia_blargg_ntsc_filter']='composite'
  path.write_text(json.dumps(config));original.original_skin(app);original.make_roms(app)
  press.REFERENCES=tuple(x for x in press.REFERENCES if x[0]==original.SECONDARY);press.fixtures(app)
  probe.run(['codesign','--force','--sign','-','--timestamp=none',app])
  outcome=probe.run_in_simulator(app,evidence,240)
 report=json.loads((evidence/'probe.json').read_text())
 failures=probe.evaluate(report,scenarios)
 poisoned=len(re.findall(r'NESTOPIA_CPP_POISON allocation=',(evidence/'probe-console.log').read_text()))
 if not poisoned:failures.append('deterministic Nestopia allocation poisoning was not active')
 if not outcome['finished']:failures.append('focused sessions did not finish')
 for row in report['results']:
  log=row.get('journal','')
  for marker in ('602x224','pitch=2408','video: frame=1 begin','metal: completed status=4'):
   if marker not in log:failures.append(row['name']+': missing '+marker)
  if 'default' not in row['name'] and original.ORIGINAL_ID not in log:failures.append('original skin missing')
  failures += [row['name']+': '+c['name'] for c in row.get('lifetimeChecks',[]) if not c.get('passed')]
 verdict={'result':'failed' if failures else 'passed','source':a.label,'sessions':len(report['results']),
          'cppPoisonLogEntries':poisoned,'failures':failures,'physicalDeviceValidated':False,'outcome':outcome}
 (evidence/'verdict.json').write_text(json.dumps(verdict,indent=2)+'\n');print(json.dumps(verdict),flush=True)
 if failures:raise SystemExit(1)
if __name__=='__main__':main()
