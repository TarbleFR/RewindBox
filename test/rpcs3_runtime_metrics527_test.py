#!/usr/bin/env python3
"""Execute production bounded telemetry helper; no iPhone performance claim."""
import argparse, hashlib, json, os, shlex, shutil, subprocess, sys, tempfile
from pathlib import Path
p=argparse.ArgumentParser(); p.add_argument('source', type=Path); p.add_argument('--report', type=Path, required=True); p.add_argument('--sanitize', action='store_true')
a=p.parse_args(); root=Path(__file__).resolve().parent
cxx=shlex.split(os.environ.get('CXX',shutil.which('clang++') or shutil.which('g++') or 'c++'))
with tempfile.TemporaryDirectory(prefix='metrics527-') as tmp:
    binary=Path(tmp)/'test'
    text=(a.source/'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    methods=[]
    for name in ('record_flip','record_pipeline_job_completed','record_gpu_fence_wait','record_rsx_semaphore_wait'):
        start=text.index('\tvoid '+name+'(')
        opening=text.index('{',start); depth=1; end=opening+1
        while depth:
            depth += (text[end]=='{') - (text[end]=='}'); end+=1
        methods.append(text[start:end])
    (Path(tmp)/'production_methods.inc').write_text('\n'.join(methods))
    command=cxx+['-std=c++20','-O2','-g','-pthread','-Wall','-Wextra','-Werror','-I',str(a.source.resolve()),'-I',tmp,str(root/'native/rpcs3_runtime_metrics527.cpp'),'-o',str(binary)]
    if sdk:=os.environ.get('HOST_MACOS_SDK'): command += ['-isysroot',sdk]
    if a.sanitize: command += ['-fsanitize=address,undefined','-fno-omit-frame-pointer']
    subprocess.run(command,check=True)
    env=os.environ.copy()
    # Linux Work runs can deny LeakSanitizer's /proc task inspection. Address
    # and UB sanitizers remain active; Apple gate keeps its default policy.
    if a.sanitize and sys.platform.startswith('linux'):
        env['ASAN_OPTIONS']=env.get('ASAN_OPTIONS','')+':detect_leaks=0'
    run=subprocess.run([str(binary)],env=env,text=True,capture_output=True)
    print(run.stdout,end='')
    print(run.stderr,end='',file=sys.stderr)
    run.check_returncode()
    result={'schema':1,'passed':True,'sanitized':a.sanitize,'compiler':subprocess.check_output(cxx+['--version'],text=True),'command':command,'output':run.stdout,'stderr':run.stderr,'asan_options':env.get('ASAN_OPTIONS',''),'physical_device_tested':False,'input_sha256':{str(x.relative_to(a.source)):hashlib.sha256(x.read_bytes()).hexdigest() for x in [a.source/'rpcs3/ios/IOSRuntimeMetrics.h',a.source/'rpcs3/ios/RPCS3IOSPerformance.cpp']}}
    a.report.parent.mkdir(parents=True,exist_ok=True); a.report.write_text(json.dumps(result,indent=2)+'\n')
