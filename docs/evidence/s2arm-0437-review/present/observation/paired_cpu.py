import argparse,csv,os,random,re,statistics,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description="Compare per-thread CPU time and wall time for synthetic FI jobs")
p.add_argument("reference",type=Path);p.add_argument("intermediate",type=Path);p.add_argument("candidate",type=Path)
p.add_argument("csv",type=Path);p.add_argument("--jobs",type=int,default=150000);p.add_argument("--rounds",type=int,default=36)
a=p.parse_args()
if hasattr(os,"sched_getaffinity"): os.sched_setaffinity(0,{max(os.sched_getaffinity(0))})
states={"A":(a.reference,False),"A2":(a.reference,False),"I0":(a.intermediate,False),"I1":(a.intermediate,True),"F0":(a.candidate,False),"F1":(a.candidate,True)}
def run(st):
 path,on=states[st]
 env={**os.environ};env["S2A_RB_FI_PRESENT_STATS"]=str(int(on))
 out=subprocess.check_output([path,"1","0","1","0",str(a.jobs)],env=env,text=True)
 match=re.search(r"^elapsed_ns=(\d+) cpu_ns=(\d+)$",out,re.M)
 return tuple(int(v)/a.jobs for v in match.groups())
for st in states: run(st)
orders=[]
rng=random.Random(195)
while len(orders)<a.rounds:
 labels=list(states);rng.shuffle(labels)
 permutations=[labels[i:]+labels[:i] for i in range(len(labels))];rng.shuffle(permutations)
 orders.extend(permutations)
rows=[]
with a.csv.open("w",newline="") as f:
 w=csv.writer(f);w.writerow(["round","position","arm","wall_ns_per_job","thread_cpu_ns_per_job"])
 for i,order in enumerate(orders[:a.rounds]):
  vals={}
  for j,st in enumerate(order):
   vals[st]=run(st);w.writerow([i+1,j+1,st,*vals[st]])
  rows.append(vals);f.flush()
for st in states:
 print(f"{st} median wall={statistics.median(r[st][0] for r in rows):.2f} CPU={statistics.median(r[st][1] for r in rows):.2f} ns/job")
for left,right in [("A2","A"),("I0","A"),("I1","I0"),("F0","A"),("F1","F0"),("F0","I0")]:
 v=[r[left][1]/r[right][1]-1 for r in rows]; rr=random.Random(390)
 boot=sorted(statistics.median(rr.choices(v,k=len(v))) for _ in range(6000))
 print(f"{left}/{right} median paired CPU {100*statistics.median(v):+.2f}% (95% bootstrap [{100*boot[150]:+.2f}%, {100*boot[5849]:+.2f}%]); slower {sum(x>0 for x in v)}/{len(v)}")
