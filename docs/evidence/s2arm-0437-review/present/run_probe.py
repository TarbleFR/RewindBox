import pathlib,sys,re,tempfile,subprocess,os
here=pathlib.Path(__file__).resolve().parent
base=pathlib.Path(sys.argv[1])/'graphics/nvn/gfx/nvn'
file=pathlib.Path(sys.argv[2]) if len(sys.argv)>2 else base/'nvn_present_fi.inc'
prefix=os.environ.get('BLOCKS_PREFIX')
src=file.read_text()
with tempfile.TemporaryDirectory() as tmp:
    tmp=pathlib.Path(tmp)
    start=src.index('// Each slot either reads') if '// Each slot either reads' in src else src.rindex('API_AVAILABLE',0,src.index('static int fi_commit'))
    end=src.find('} }',src.index('static void fi_job'))+3
    job=src[start:end]
    # GNU ObjC lacks native Apple autorelease pools. Fixture owns its objects for the full run.
    job=job.replace('@autoreleasepool {','{')
    (tmp/'job.inc').write_text(job)
    (tmp/'rule.h').write_bytes((base/'nvn_fi_rule.h').read_bytes())
    m=(base/'nvn_mtl.m').read_text()
    s=m.index('static void rb_present_complete(')
    (tmp/'complete.inc').write_text(m[s:m.index('\n}',s)+2])
    session=(base/'nvn_session.inc').read_text()
    sh=session[session.index("    struct timespec dl = session_deadline();"):session.index("    link_join();")]
    (tmp/'stop.inc').write_text(sh)
    stall=m[m.index("        while (g_pq_inflight || g_rb_present_encoding)"):]; stall=stall[:stall.index('        RB_WAKE_CALL("present.broadcast"')]
    (tmp/'stall.inc').write_text(stall)
    gcc=subprocess.check_output(['gcc','-print-file-name=include'],text=True).strip()
    inc=[] if not prefix else ['-I'+prefix+'/include']
    lib=['-lBlocksRuntime'] if not prefix else [prefix+'/lib/x86_64-linux-gnu/libBlocksRuntime.a']
    cmd=['clang','-DHAS_PARTS='+str(int('fi_finish_read_locked' in src)),'-O2','-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer','-fblocks','-isystem',gcc,*inc,'-I'+str(tmp),str(here/'probe.m'),*lib,'-lobjc','-lm','-lpthread','-o',str(tmp/'probe')]
    subprocess.run(cmd,check=True)
    if os.environ.get("BENCH_BINARY"):
        import shutil
        binary=pathlib.Path(os.environ["BENCH_BINARY"])
        # Timings use an optimized build. Verification uses both sanitizers.
        subprocess.run([v for v in cmd[:-1] if not v.startswith("-fsanitize")]+[str(tmp/"bench-probe")],check=True)
        shutil.copy2(tmp/"bench-probe",binary)
    sys.exit(subprocess.run([str(tmp/'probe')],env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0','UBSAN_OPTIONS':'halt_on_error=1'}).returncode)
