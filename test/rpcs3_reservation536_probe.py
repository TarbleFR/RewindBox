#!/usr/bin/env python3
"""Compare the actual 534 reservation comparator with two Apple NEON candidates."""
import argparse,hashlib,json,os,platform,shlex,statistics,subprocess,tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
ROOT=Path(__file__).resolve().parents[1]
BASE='2fa4ad668446b9166017b434e302836287d015b0'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 a.output.mkdir(parents=True,exist_ok=True)
 path='rpcs3/Emu/Cell/SPUThread.cpp';text=(a.source/path).read_text()
 manifest=json.loads(subprocess.check_output(['git','show',BASE+':build-utils/rpcs3/canonical-source.json'],cwd=ROOT))
 assert sha(text.encode())==manifest['files_sha256'][path], 'Probe must use the unmodified 534 body'
 cxx=shlex.split(os.environ.get('CXX','clang++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
 harness=ROOT/'test/native/rpcs3_reservation536_probe.cpp'
 with tempfile.TemporaryDirectory(prefix='reservation536-') as td:
  work=Path(td);inc=braced(text,'static FORCE_INLINE int16x8_t cmp16_pair_accum_arm64(')+'\n'+braced(text,'extern bool cmp_rdata(')
  (work/'baseline536.inc').write_text(inc)
  flags=['-std=c++20','-O3','-mcpu=apple-m1','-Wall','-Wextra','-Werror','-I'+str(work)]
  subprocess.run([*cxx,*flags,str(harness),'-o',str(work/'probe')],check=True)
  subprocess.run([*cxx,*flags,'-S',str(harness),'-o',str(a.output/'reservation536.s')],check=True)
  raw=subprocess.check_output([str(work/'probe')],text=True,timeout=60)
  (a.output/'raw.jsonl').write_text(raw)
  rows=[json.loads(l) for l in raw.splitlines()];samples=rows[1:]
  medians={str(pairs):{kernel:statistics.median(x['nsPerCall'] for x in samples if x['pairs']==pairs and x['kernel']==kernel) for kernel in ['reference','xor','dual']} for pairs in [32,4096]}
  record=dict(source=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),baseline=BASE,platform=platform.platform(),machine=platform.machine(),compiler=subprocess.check_output(cxx[:1]+['--version'],text=True).strip(),flags=flags[:-1],productionSHA256=sha(text.encode()),extractedBaselineSHA256=sha(inc.encode()),harnessSHA256=sha(harness.read_bytes()),scriptSHA256=sha(Path(__file__).read_bytes()),verifiedCases=rows[0]['verifiedCases'],medianNsPerCall=medians,samples=samples,physicalIPhoneTested=False,gameplayMeasured=False,productionChanged=False,scope='Fixed-size comparison only; rotating order, warmed 8 KiB and 1 MiB pair sets. No reservation or GPU synchronization is removed.')
  (a.output/'probe.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps({k:record[k] for k in ['verifiedCases','medianNsPerCall','physicalIPhoneTested','productionChanged']}))
if __name__=='__main__':main()
