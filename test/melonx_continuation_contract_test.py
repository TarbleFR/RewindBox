#!/usr/bin/env python3
"""Check the exact remaining-lots delta without reexecuting native historical suites."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];c=json.loads((ROOT/'build-utils/melonx/continuation-core-contract.json').read_text());checks=0

def check(v,message):
 global checks;checks+=1;assert v,message
for p,h in c['inputs'].items():check(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,'Changed review input: '+p)
old=json.loads((ROOT/'build-utils/melonx/occlusion-core-contract.json').read_text())
check(c['baselinePreparationInputs']==old['preparationInputs'],'Exact immediate baseline inputs')
check(c['baselinePreparedMembers']==old['preparedMembers'],'Exact immediate baseline prepared source')
a,b=c['baselinePreparationInputs'],c['preparationInputs'];check(set(b)-set(a)==set(c['addedPreparationInputs']),'Added Core inputs')
check(not(set(a)-set(b)),'No removed Core input')
check({p for p in a if a[p]!=b[p]}==set(c['changedPreparationInputs']),'Changed Core inputs')
for p,v in c['changedPreparationInputs'].items():check(a[p]==v['before']and b[p]==v['after'],'Reviewed pre/post input: '+p)
old,new=c['baselinePreparedMembers'],c['preparedMembers'];changed={p for p in old if old[p]!=new[p]}|set(new)-set(old)
check(changed==set(c['productionChanges']),'Only reviewed new production changes')
check(not(set(old)-set(new)),'No removed production member')
check(len(b)==114 and len(new)==151,'Expected current preparation counts')
check(c['baseline']['source']=='e7143e566462bf6e3d9c143ce24532c1ad7aeb10'and c['baseline']['artifact']==12953505421,'Immediate verified core')
check(c['adapters']==['adapt_sized_jit','adapt_texture_readback_bounds'],'Only affected new adapters')
check('dotnet-version: 10.0.100'in(ROOT/'.github/workflows/melonx-core.yml').read_text(),'Unchanged SDK')
print(json.dumps(dict(result='passed',checks=checks,preparationInputs=len(b),preparedMembers=len(new),nativeTestsExecuted=0)))
