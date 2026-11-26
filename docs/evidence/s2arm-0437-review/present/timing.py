import os,subprocess,statistics,sys
from pathlib import Path
directory=Path(__file__).resolve().parent
if hasattr(os,"sched_setaffinity"):
    os.sched_setaffinity(0,{min(os.sched_getaffinity(0))})
def measure(name):
    return int(subprocess.check_output([str(directory / (name+".bin")),"bench"]))
with (directory/"timings.tsv").open("w") as f:
    print("pair\tbase_ns\tcandidate_ns\tcontrol_a_ns\tcontrol_b_ns", file=f)
    estimates=[[],[]]
    for i in range(32):
        row=[]
        for j,(a,b) in enumerate([("base","candidate"),("base","base")]):
            if i%2: y,x=measure(b),measure(a)
            else: x,y=measure(a),measure(b)
            estimates[j].append(100*(y/x-1));row.extend([x,y])
        print(i+1,*row,sep="\t",file=f,flush=True)
for v in estimates:
    v.sort()
    print(f"{statistics.median(v):+.2f}% [{v[10]:+.2f}%, {v[-11]:+.2f}%]")
