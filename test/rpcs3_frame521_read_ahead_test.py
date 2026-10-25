"""Targeted production VDEC read-ahead / ownership checks; no game simulation."""
import argparse,json,os,shlex,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def run(source,sanitize):
 text=(source/'rpcs3/Emu/Cell/Modules/cellVdec.cpp').read_text()
 start=text.index('\tvoid prefetch_near_pixels()');opening=text.index('{',start);end=opening+1;depth=1
 while depth:depth+=int(text[end]=='{')-int(text[end]=='}');end+=1
 method=text[start:end]
 assert method.index('next.prefetch();')>method.rindex('\n\t\t}')
 # Production call precedes entry into the decoder queue's lock scope.
 assert '\t\t\t\t\t\t\tprefetch_near_pixels();\n#endif\n\t\t\t\t\t\t\t{' in text
 compiler=shlex.split(os.environ.get('CXX','c++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):compiler+=['-isysroot',sdk]
 for p in ['FrameClient.h','SourceClient.cpp']:
  assert (source/'rpcs3/ios/NeoSwapStorage'/p).read_bytes()==(ROOT/'native/neoswap-storage'/p).read_bytes()
 with tempfile.TemporaryDirectory(prefix='frame521-') as temporary:
  work=Path(temporary);(work/'prefetch-method.inc').write_text(method+'\n')
  common=[*compiler,'-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-I',str(work),'-I',str(source/'rpcs3')]
  flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if sanitize else []
  subprocess.run([*common,*flags,str(ROOT/'test/native/rpcs3_frame521_read_ahead.cpp'),str(source/'rpcs3/ios/NeoSwapStorage/SourceClient.cpp'),'-o',str(work/'test')],check=True)
  report=ROOT/'build/rpcs3-cell521-tests/frame-read-ahead.json';report.parent.mkdir(parents=True,exist_ok=True)
  subprocess.run([str(work/'test'),str(report)],check=True,timeout=30)
  # Compile the actual queue-selection method with production exception mode.
  subprocess.run([*common,'-fno-exceptions','-fsyntax-only',str(ROOT/'test/native/rpcs3_frame521_read_ahead.cpp')],check=True)
  old=subprocess.check_output(['git','show','6432786bfb98aa6eae0888c2d3cf172a38cf9441:native/neoswap-storage/FrameClient.h'],cwd=ROOT)
  (work/'old-FrameClient.h').write_bytes(old)
  (work/'control.cpp').write_text('#include "old-FrameClient.h"\n#include <cassert>\nint main(){assert(!neostation::source_client::frame_can_cool(60,0,1000000,4096,true));}\n')
  subprocess.run([*compiler,'-std=c++20','-I',str(work),'-I',str(ROOT/'native/neoswap-storage'),str(work/'control.cpp'),'-o',str(work/'control')],check=True)
  result=subprocess.run([str(work/'control')],capture_output=True,text=True)
  assert result.returncode!=0 and ('Assertion' in result.stderr or 'assertion' in result.stderr)
  print('PASS pre-fix control archives next-to-display head; current policy retains it')
  print(report.read_text())
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--sanitize',action='store_true');a=p.parse_args();run(a.source.resolve(),a.sanitize)
