#!/usr/bin/env python3
"""Actual verified archive disk I/O, fixed payload; host timing, never iPhone FPS."""
import argparse,json,os,platform,shlex,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];NATIVE=ROOT/'native/neoswap-storage'
def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path,nargs='?');p.add_argument('--report',type=Path);a=p.parse_args()
 cxx=shlex.split(os.environ.get('CXX','c++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
 libs=['-lcompression','-lz'] if platform.system()=='Darwin' else ['-llz4','-lz']
 with tempfile.TemporaryDirectory(prefix='archive528-') as tmp:
  w=Path(tmp);(w/'cache').mkdir();exe=w/'test'
  subprocess.run(cxx+['-std=c++20','-O2','-pthread','-I'+str(NATIVE)]+[str(NATIVE/s) for s in ('Metrics.cpp','Store.cpp','ManagedSwap.cpp','SourceArchive.cpp')]+[str(ROOT/'test/native/neoswap_granularity528.cpp')]+libs+['-o',str(exe)],check=True)
  out=subprocess.check_output([str(exe),str(w/'cache')],text=True,timeout=120)
  rows=[json.loads(line) for line in out.splitlines() if line.startswith('{')]
  assert len(rows)==3 and [row['checkpoints'] for row in rows]==[110,30,10]
  assert [row['restoredChunks'] for row in rows]==[110,30,10]
  report=dict(passed=True,physicalDeviceTested=False,scope='real POSIX files, exact byte roundtrips; compression disabled, rate limit disabled; 1MiB candidate needs 2MiB store RAM and was rejected',rows=rows)
 if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
