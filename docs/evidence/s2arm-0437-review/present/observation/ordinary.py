from pathlib import Path
import argparse,itertools,os,subprocess
p=argparse.ArgumentParser();p.add_argument("reference",type=Path);p.add_argument("ordinary",type=Path);a=p.parse_args()
modes=[({},1,0,1),({},1,1,1),({},0,0,1),({},-1,0,1),({},1,1,0),({},2,2,1),({},3,2,1),
       ({"DM_PRESENT_FI_DUP":"1"},1,0,1),({"DM_PRESENT_FI_NOVT":"1"},1,0,1),
       ({"DM_PRESENT_FI_DUP":"0"},1,0,1),({"DM_PRESENT_FI_NOVT":"0"},1,0,1)]
env0={**os.environ,"ASAN_OPTIONS":"detect_leaks=0","UBSAN_OPTIONS":"halt_on_error=1"}
for key in ["DM_PRESENT_FI_DUP","DM_PRESENT_FI_NOVT","S2A_RB_FI_PRESENT_STATS"]:env0.pop(key,None)
pairs=0
for repeat,order,runtime_flag,case in itertools.product(range(5),(0,1),(0,1),modes):
    extra,shown,cut,allowed=case;env={**env0,**extra,"S2A_RB_FI_PRESENT_STATS":str(runtime_flag)}
    outputs=[]
    for exe in (a.reference,a.ordinary):
        result=subprocess.check_output([exe,*map(str,(shown,cut,allowed,order,30))],env=env,text=True).splitlines()
        if len(result)!=2 or not result[1].startswith("elapsed_ns="):raise ValueError("Observer present in standard build")
        outputs.append(result[0])
    if outputs[0]!=outputs[1]:raise ValueError((case,outputs))
    pairs+=1
print(f"{pairs} reference/ordinary comparisons, 5 repeats, both callback orders and both runtime switch values; identical HUD and original counters")
