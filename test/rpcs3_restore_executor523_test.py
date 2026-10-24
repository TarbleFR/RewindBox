#!/usr/bin/env python3
"""Production owned worker + continuation + reload path; explicit Core/UI doubles."""
import argparse,json,os,shlex,subprocess,tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
ROOT=Path(__file__).resolve().parents[1]
def run(source,before,report):
 api=(source/'rpcs3/ios/RPCS3IOS.cpp').read_text();savestate=(source/'rpcs3/Emu/savestate_utils.cpp').read_text()
 with tempfile.TemporaryDirectory(prefix='restore-executor523-') as d:
  work=Path(d)
  if not before:
   import shutil
   before=work/'before'
   for p in json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_text())['cell523']['paths']:
    dest=before/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/p,dest)
   subprocess.run(['git','apply','--unidiff-zero','--reverse',str(ROOT/'test/fixtures/rpcs3_restore523.diff')],cwd=before,check=True)
  original=(before/'rpcs3/Emu/savestate_utils.cpp').read_text();old_api=(before/'rpcs3/ios/RPCS3IOS.cpp').read_text()
  methods=api.split('// REWINDBOX_RESTORE_EXECUTOR_BEGIN:')[1].split('\n',1)[1].split('// REWINDBOX_RESTORE_EXECUTOR_END')[0]
  (work/'executor.inc').write_text(methods)
  (work/'continuation.inc').write_text(braced(api,'std::uint64_t savestate_restore_generation() noexcept')+'\n'+braced(api,'bool defer_savestate_restore('))
  for name,text in [('before',original),('after',savestate)]:
   (work/(name+'.inc')).write_text(braced(text,'bool boot_current_game_savestate(bool testing, u32 index)'))
  # Preserve the complete original committed-write/restart/error body.
  old=braced(old_api,'Emu.after_kill_callback = [requested_slot]()')
  new=braced(api,'if (!rpcs3::ios::defer_savestate_restore([requested_slot]()')
  body=lambda s:'\n'.join(x.strip() for x in s[s.index('{')+1:-1].splitlines() if x.strip())
  assert body(old)==body(new)
  for sig in ['extern "C" rpcs3_ios_status rpcs3_ios_stop_emulation','extern "C" rpcs3_ios_status rpcs3_ios_shutdown']:
   f=braced(api,sig);assert f.index('current.read().active')<f.index('restore_jobs().cancel()')
  shutdown=braced(api,'extern "C" rpcs3_ios_status rpcs3_ios_shutdown')
  assert shutdown.index('lock.unlock();')<shutdown.index('restore_jobs().close();')
  cxx=shlex.split(os.environ.get('CXX','c++'))
  if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
  subprocess.run(cxx+['-std=c++20','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-DRPCS3_IOS','-I'+str(work),'-I'+str(source/'rpcs3'),str(ROOT/'test/native/rpcs3_restore_executor523.cpp'),'-fsanitize=address,undefined','-fno-omit-frame-pointer','-o',str(work/'test')],check=True)
  r=subprocess.run([str(work/'test')],capture_output=True,text=True,timeout=90,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  if r.returncode:print(r.stderr,flush=True);r.check_returncode()
  result=dict(passed=True,stdout=r.stdout.strip(),actualExecutor=True,actualContinuation=True,actualReloadPath=True,originalAutoSaveBodyPreserved=True,
    sanitizers=True,scope='real owned native worker and production methods; Core/UI/filesystem doubles; no guest/device restore')
  if report:report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--before',type=Path);p.add_argument('--report',type=Path);a=p.parse_args();run(a.source.resolve(),a.before,a.report)
