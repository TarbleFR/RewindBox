#!/usr/bin/env python3
"""Production owned worker + continuation + reload path; explicit Core/UI doubles."""
import argparse,hashlib,json,os,shlex,subprocess,tempfile
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
  assert shutdown.index('lock.unlock();')<shutdown.index('restore_jobs().close();')<shutdown.index('lock.lock();')<shutdown.index('g_lifecycle.finish_shutdown(joined);')
  cxx=shlex.split(os.environ.get('CXX','c++'))
  if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
  common=cxx+['-std=c++20','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-DRPCS3_IOS','-I'+str(work),'-I'+str(source/'rpcs3'),str(ROOT/'test/native/rpcs3_restore_executor523.cpp'),'-fsanitize=address,undefined','-fno-omit-frame-pointer','-o',str(work/'test')]
  fixture=ROOT/'test/fixtures/rpcs3_shutdown523_before.inc';previous_shutdown=fixture.read_text()
  assert '40f0337122e8bd83a22b10acfb515ee56638600d' in previous_shutdown
  prior=json.loads(subprocess.check_output(['git','show','40f0337122e8bd83a22b10acfb515ee56638600d:build-utils/rpcs3/canonical-source.json'],cwd=ROOT))
  reconstructed=api.replace(shutdown,braced(previous_shutdown,'extern "C" rpcs3_ios_status rpcs3_ios_shutdown'))
  assert hashlib.sha256(reconstructed.encode()).hexdigest()==prior['files_sha256']['rpcs3/ios/RPCS3IOS.cpp']
  results=[]
  for variant,text in [('candidate',shutdown),('before-join-negative-control',previous_shutdown)]:
   (work/'shutdown.inc').write_text(text);subprocess.run(common,check=True)
   r=subprocess.run([str(work/'test')],capture_output=True,text=True,timeout=90,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
   if variant=='candidate':
    if r.returncode:print(r.stderr,flush=True);r.check_returncode()
   else:assert r.returncode and 'rpcs3_ios_shutdown()==RPCS3_IOS_INVALID_STATE' in r.stderr,r.stderr
   results.append(dict(variant=variant,exit=r.returncode,stdout=r.stdout.strip(),stderr=r.stderr.strip()))
  result=dict(passed=True,cases=results,actualExecutor=True,actualContinuation=True,actualReloadPath=True,actualShutdownAPI=True,actualLifecycle=True,originalAutoSaveBodyPreserved=True,negativeControlSHA256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
    sanitizers=True,scope='real owned native worker and production methods; Core/UI/filesystem doubles; no guest/device restore')
  if report:report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--before',type=Path);p.add_argument('--report',type=Path);a=p.parse_args();run(a.source.resolve(),a.before,a.report)
