#!/usr/bin/env python3
"""Affected persistent cache contract with real LLVM22 cross-process relocation."""
import argparse,hashlib,json,subprocess
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1]
command=['python3','test/rpcs3_build481_spu_object_cache_test.py',str(a.source),'--require-llvm','--sanitize']
r=subprocess.run(command,cwd=root,capture_output=True,text=True)
print(r.stdout,end='');print(r.stderr,end='');r.check_returncode()
assert 'relocation proof executed' in r.stdout or 'relocation proof LLVM' in r.stdout, r.stdout[-500:]
result=dict(passed=True,command=command,output_sha256=hashlib.sha256((r.stdout+r.stderr).encode()).hexdigest(),physicalDeviceTested=False,scope='Real LLVM22 object persistence and relocation across processes; not guest gameplay.')
if a.report:a.report.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
