#!/usr/bin/env python3
"""Source-path microbenchmarks, not a game replay or an iPhone FPS claim."""
import json, os, platform, subprocess
from pathlib import Path
root=Path(__file__).resolve().parent
out=Path("proof/race-benchmarks").resolve();out.mkdir(parents=True,exist_ok=True)
def run(args, name=None, env=None):
    p=subprocess.run(list(map(str,args)),capture_output=True,text=True,env=env)
    if name: (out/name).write_text(p.stdout+p.stderr)
    print("COMMAND", *args, "exit",p.returncode,flush=True)
    if p.returncode: print(p.stdout,p.stderr);raise SystemExit(p.returncode)
    return p.stdout
(out/"cpu-environment.json").write_text(json.dumps({"platform":platform.platform(),"machine":platform.machine(),"cc":run(["cc","--version"]),"physicalIPhone":False,"input":"controlled ordinary resident address and push-byte patterns; not session801 replay"},indent=2))
for variant,defs in [("full",[]),("no-timing",["-DNO_TIMING"])]:
    exe=out/("ubo-"+variant)
    run(["cc","-O3","-std=gnu11","-Wall","-Wextra","-pthread",*defs,root/"ubo_bench.c",root/"ga.c","-o",exe])
    for kind,rates in [("direct",[100,95,75,50,0]),("collision",[100,75,0])]:
        for rate in rates:run([exe,kind,rate],f"ubo-{variant}-{kind}-{rate}.csv")
for file,frameworks in [("push_bench.c",[]),("rid_bench.m",["-fobjc-arc","-framework","Foundation","-framework","Metal"])]:
    exe=out/file.split(".")[0]
    run(["cc","-O3","-std=gnu11","-Wall","-Wextra","-DNDEBUG",*frameworks,root/file,"-o",exe])
    run([exe],exe.name+".csv")
print("CPU measurements completed; report per-path costs, never inferred FPS.")

exe=out/"ubo-guard"
run(["cc","-O3","-std=gnu11","-Wall","-Wextra","-pthread",root/"ubo_guard.c",root/"ga_guard.c","-o",exe])
for kind,rate in [("direct",100),("direct",0),("collision",100),("gva",100)]:
    run([exe,kind,rate],f"ubo-guard-{kind}-{rate}.csv")
exe=out/"push-selective"
run(["cc","-O3","-std=gnu11","-Wall","-Wextra","-DNDEBUG",root/"push_selective.c","-o",exe])
env=dict(os.environ,PUSH_VARIANT="selective")
run([exe],"push-selective.csv",env=env)
