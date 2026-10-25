#!/usr/bin/env python3
"""Execute the actual FXO header, bounded tracer and saved-HLE range check."""
import argparse,json,os,shlex,subprocess,tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
ROOT=Path(__file__).resolve().parents[1]
def run(source,report):
 with tempfile.TemporaryDirectory(prefix='restore523-') as d:
  w=Path(d)
  text=(source/'rpcs3/Emu/savestate_utils.cpp').read_text()
  trace=text[text.index('\tstruct restore_trace_state'):text.index('\n#endif',text.index('\tstruct restore_trace_state'))]
  (w/'trace.inc').write_text(trace)
  (w/'range.inc').write_text(braced((source/'rpcs3/Emu/Cell/PPUModule.cpp').read_text(),'static bool ppu_restore_functions_fit('))
  cxx=shlex.split(os.environ.get('CXX','c++'))
  if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
  common=cxx+['-std=c++20','-O1','-g','-pthread','-DRPCS3_IOS','-I'+str(w),'-I'+str(source/'rpcs3'),str(ROOT/'test/native/rpcs3_restore523.cpp')]
  subprocess.run(common+['-fsanitize=address,undefined','-fno-omit-frame-pointer','-o',str(w/'test')],check=True)
  r=subprocess.run([str(w/'test')],capture_output=True,text=True,timeout=60,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  if r.returncode:print(r.stderr,flush=True);r.check_returncode()
  subprocess.run(common+['-fno-exceptions','-fsyntax-only'],check=True)
  system=(source/'rpcs3/Emu/System.cpp').read_text()
  assert system.count('stx::serial_restore_trace_reset();')==2
  failure=system[system.index('const bool loaded_ppu ='):system.index('// Overlay (OVL) executable')]
  assert failure.index('if (!loaded_ppu)')<failure.index('return game_boot_result::savestate_corrupted;')
  result=dict(passed=True,stdout=r.stdout.strip(),actualFXOHeader=True,actualBoundedTrace=True,actualRangePolicy=True,
    sanitizers=True,scope='production template/trace/range; portable archive/page-map/log adapters; no game restore')
  if report:report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args();run(a.source.resolve(),a.report)
