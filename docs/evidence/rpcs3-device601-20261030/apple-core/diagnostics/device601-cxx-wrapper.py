#!/usr/bin/env python3
import fcntl, hashlib, json, os
from pathlib import Path
import subprocess, sys
args = sys.argv[1:]
compiler = json.loads(os.environ['RPCS3_DEVICE597_REAL_CXX'])
snapshots = Path(os.environ['RPCS3_DEVICE597_COMPILE_INPUTS'])
units = []
for arg in args:
    p = Path(arg)
    if p.suffix in ('.c', '.cc', '.cpp', '.cxx', '.C', '.m', '.mm') and p.is_file():
        raw = p.read_bytes(); digest = hashlib.sha256(raw).hexdigest()
        snapshots.mkdir(parents=True, exist_ok=True)
        saved = snapshots / (digest + p.suffix)
        if not saved.exists(): saved.write_bytes(raw)
        units.append({'path': str(p.resolve()), 'sha256': digest, 'saved': str(saved)})
result = subprocess.run(compiler + args)
event = {'compiler': compiler, 'args': args, 'cwd': str(Path.cwd()),
         'returncode': result.returncode, 'units': units}
with open(os.environ['RPCS3_DEVICE597_CXX_TRACE'], 'a', encoding='utf-8') as trace:
    fcntl.flock(trace, fcntl.LOCK_EX)
    trace.write(json.dumps(event, sort_keys=True) + '\n')
    trace.flush()
    fcntl.flock(trace, fcntl.LOCK_UN)
raise SystemExit(result.returncode)
