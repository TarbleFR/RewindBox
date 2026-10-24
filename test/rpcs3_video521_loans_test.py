"""Measure production video shelf backing, not physical RAM or game performance."""
import json,os,shlex,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
BASE='a4b2f27775b4038b7bd143d6cf723a6fc56f5a13'
def run():
 cxx=shlex.split(os.environ.get('CXX','c++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
 with tempfile.TemporaryDirectory(prefix='video521-loans-') as temp:
  work=Path(temp);(work/'Relay').symlink_to(ROOT/'native/neoswap-relay',target_is_directory=True)
  baseline=work/'baseline.cpp';baseline.write_bytes(subprocess.check_output(['git','show',BASE+':packages/neo_swap/ios/Classes/NeoSwap.cpp'],cwd=ROOT))
  reports={}
  for name,broker in [('before',baseline),('after',ROOT/'packages/neo_swap/ios/Classes/NeoSwap.cpp')]:
   exe=work/name
   command=[*cxx,'-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-DNEOSWAP_TESTING','-DNEOSWAP_RELAY=1',
    '-fsanitize=address,undefined','-I',str(work),'-I',str(ROOT/'packages/neo_swap/ios/Classes'),'-I',str(ROOT/'native/neoswap'),str(broker),
    str(ROOT/'native/neoswap-relay/Backend.cpp'),str(ROOT/'native/neoswap-donation/Broker.cpp'),str(ROOT/'test/neoswap_relay_loans_test.cpp'),'-o',str(exe)]
   subprocess.run(command,cwd=ROOT,env=env,check=True)
   text=subprocess.check_output([str(exe)],cwd=ROOT,env=dict(env,RPCS3_VIDEO521_SPAN_PROBE='1'),text=True,timeout=45)
   reports[name]=json.loads(text.splitlines()[-1])
   if name=='after':
    subprocess.run([str(exe)],cwd=ROOT,env=env,check=True,timeout=90)
  assert reports['before']['loanBackingBytes']==8*2*1024*1024
  assert reports['after']['loanBackingBytes']==8*((1382400+65535)//65536)*65536
  reports.update(physicalIPhoneTested=False,footprintMeasured=False,payloadIdentityAndGenericBoundsVerified=True)
  out=ROOT/'build/rpcs3-cell521-tests/video-loans.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(reports,indent=2)+'\n');print(out.read_text())
if __name__=='__main__':run()
