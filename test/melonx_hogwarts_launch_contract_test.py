#!/usr/bin/env python3
"""Freeze only the reviewed delta on the verified Core827f source."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];c=json.loads((ROOT/'build-utils/melonx/hogwarts-launch-core-contract.json').read_text());checks=0
def check(value,message):
 global checks;checks+=1;assert value,message
prior=json.loads((ROOT/'build-utils/melonx/continuation-core-contract.json').read_text())
check(c['baselinePreparationInputs']==prior['preparationInputs'],'Retain exact114 input baseline')
check(c['baselinePreparedMembers']==prior['preparedMembers'],'Retain exact151 prepared members')
a,b=c['baselinePreparationInputs'],c['preparationInputs']
check(len(a)==114 and len(b)==117,'Only three added preparation inputs')
check(not(set(a)-set(b)),'No removed preparation input')
check({p for p in a if a[p]!=b[p]}=={'build-utils/melonx/prepare_embedded.py'},'Only recipe changes among old inputs')
check(set(b)-set(a)==set(c['addedPreparationInputs']),'Added input inventory')
old,new=c['baselinePreparedMembers'],c['preparedMembers']
check(not(set(old)-set(new))and len(new)==154,'No removed prepared source')
check(({p for p in old if old[p]!=new[p]}|set(new)-set(old))==set(c['productionChanges']),'Reviewed production delta')
for p,h in {**b,**c['inputs']}.items():check(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,'Changed reviewed input: '+p)
check(c['baseline']['source']=='827f4653e0dee5b86258f598373255d179638bdb','Immediate successful Core')
check(c['adapters']==['adapt_literal_memory','adapt_startup_trace'],'Only literal correction and diagnostics')
check(c['gates']==[['test/melonx_startup_trace_test.py','startup-trace-checks.json',True]],'Only changed trace gate reexecutes')
check(c['reusedLiteralGate']['source']=='8a82bb25c968a2e06a4f2ef3a6c7830f76560659','Exact successful literal proof producer')
print(json.dumps(dict(result='passed',checks=checks,preparationInputs=len(b),preparedMembers=len(new),nativeTestsExecuted=0)))
