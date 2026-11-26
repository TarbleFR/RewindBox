"""Check that counterexamples reproduce in both callback orders."""
from pathlib import Path
import json,os,subprocess,sys
out=Path(sys.argv[1])
q=len(sys.argv)>2
cases=[
  ("MetalFX route", {},[1,0,1,30],(30,30,30,30,0,30,0,0,0)),
  ("scene cut", {},[1,1,1,30],(30,30,30,30,30,0,0,30,0)),
  ("duplicate", {"DM_PRESENT_FI_DUP":"1"},[1,0,1,30],(30,30,0,0,0,0,0,0,30)),
  ("previous", {"DM_PRESENT_FI_NOVT":"1"},[1,0,1,30],(30,30,0,0,0,0,30,0,0)),
  ("duplicate set to zero", {"DM_PRESENT_FI_DUP":"0"},[1,0,1,30],(30,30,0,0,0,0,0,0,30)),
  ("previous set to zero", {"DM_PRESENT_FI_NOVT":"0"},[1,0,1,30],(30,30,0,0,0,0,30,0,0)),
  ("prime cut without midpoint", {},[1,1,0,30],(30,0,1,0,1,0,0,0,0)),
  ("discarded midpoint",{},[0,0,1,30],(30,0,30,30,0,0,0,0,0)),
  ("discard all",{},[-1,0,1,30],(0,0,30,30,0,0,0,0,0)),
  ("same totals clean shown",{},[2,2,1,2],(2,1,2,2,1,1,0,0,0)),
  ("same totals cut shown",{},[3,2,1,2],(2,1,2,2,1,0,0,1,0)),
]
clean=dict(os.environ,ASAN_OPTIONS="detect_leaks=0",UBSAN_OPTIONS="halt_on_error=1")
for v in ["DM_PRESENT_FI_DUP","DM_PRESENT_FI_NOVT","S2A_RB_FI_PRESENT_STATS"]: clean.pop(v,None)
cols="real midpoint fx_request made cuts fx_shown previous cut dup".split()
captured="registered pending failed discarded fx dup prev cut unknown".split()
rows=[]
def check(name,env,params,expected,stats,failure=0):
    states=[]
    show,cut,allow,n=params
    for repeat in range(5):
        for enabled in (False,True):
            for order in (0,1):
                text=subprocess.check_output([out,*map(str,[show,cut,allow,order,n,failure])],
                     env={**clean,**env,"S2A_RB_FI_PRESENT_STATS":str(int(enabled))},text=True)
                print1,elapsed,stat=text.splitlines()
                prefix,hud=print1.split(" hud=")
                current={k:int(v) for k,v in [tok.split("=") for tok in prefix.split()]}
                values={k:float(v) for k,v in [tok.split("=") for tok in stat.split()]}
                if expected is not None and tuple(current[k] for k in cols)!=expected: raise AssertionError((name,current,expected))
                if current["guest"]!=n or int(hud.split()[0])!=n: raise AssertionError((name,hud))
                observed=tuple(values[k] for k in captured)
                if observed!=(stats if enabled else (0,)*len(captured)): raise AssertionError((name,observed,stats))
                if enabled: states.append({**current,"hud_fps":int(hud.split()[0]),"capture":values})
    if any(state!=states[0] for state in states): raise AssertionError(f"{name}: nondeterministic")
    rows.append({"case":name,"repeats":5,"orders":2,"modes":2,**states[0]})
for name,opts,param,expect in cases:
    real,mid,request,made,cuts,fx,prev,cut,dup=expect
    count=param[3] if param[2] else 0
    check(name,opts,param,expect,(count,0,0,count-mid,fx,dup,prev,cut,0))
extra=[
 ("GPU error even if midpoint confirmed",1,(30,0,0,0,0,0,0,0,30)),
 ("missing midpoint drawable",2,(0,0,0,0,0,0,0,0,0)),
 ("encoder fails before submission",3,(30,0,30,0,0,0,0,0,0)),
 ("no feedback options available",4,(30,0,30,0,0,0,0,0,0)),
 ("empty GPU feedback",5,(30,0,0,0,0,0,0,0,30)),
 ("missing display callback then session replaced",6,(30,1,0,0,29,0,0,0,0)),
 ("missing GPU callback then session replaced",7,(30,1,0,0,29,0,0,0,0)),
 ("bounded table + stale, duplicate and invalid timestamp",8,(30,0,0,0,30,0,0,0,0)),
 ("simultaneous GPU and display notifications",9,(30,0,0,0,30,0,0,0,0))]
for name,failure,stats in extra: check(name,{},[1,0,1,30],None,stats,failure)
if q: Path(sys.argv[2]).write_text(json.dumps(rows,indent=2)+"\n")
print(f"{len(rows)} scenarios × 2 orders × 2 modes × 5 repeats = {len(rows)*20} sanitizer runs passed")
