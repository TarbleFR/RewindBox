#!/usr/bin/env python3
"""Compiler-free negative controls for the new contract and atomic adapters."""
import copy,hashlib,importlib,json,sys,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'build-utils/melonx'))
import verify_occlusion_core as candidate
v=candidate.contract();assert len(candidate.preparation_inputs())==108
assert len(v['preparedMembers'])==148 and len(v['productionChanges'])==15
assert len(v['gates'])==3 and len(v['adapters'])==3
controls=0
original=candidate.CONTRACT
with tempfile.TemporaryDirectory(prefix='melonx-occlusion-contract-')as temp:
 p=Path(temp)/'contract.json';candidate.CONTRACT=p
 for relative in v['inputs']:
  broken=copy.deepcopy(v);broken['inputs'][relative]='0'*64;p.write_text(json.dumps(broken))
  try:candidate.contract()
  except (RuntimeError,AssertionError):controls+=1
  else:raise AssertionError('Changed input accepted: '+relative)
 candidate.CONTRACT=original
 # Adapter preflight is all-or-nothing: corrupting the final source input
 # must be rejected before even the first file can be changed.
 for name,manifest in [('adapt_occlusion_reports','occlusion-adapter-contract'),('adapt_query_batching','query-batching-adapter-contract'),('adapt_jit_single_attempt','jit-single-attempt-adapter-contract')]:
  spec=json.loads((ROOT/'build-utils/melonx'/f'{manifest}.json').read_text());work=Path(temp)/name;work.mkdir()
  for relative,h in spec['before'].items():
   if h is None:continue
   target=work/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('deliberate drift')
  before={str(p.relative_to(work)):p.read_bytes()for p in work.rglob('*')if p.is_file()}
  try:importlib.import_module(name).apply(work)
  except RuntimeError:controls+=1
  else:raise AssertionError('Adapter accepted drift: '+name)
  assert before=={str(p.relative_to(work)):p.read_bytes()for p in work.rglob('*')if p.is_file()}
try:candidate.historical.preparation_inputs()
except (RuntimeError,AssertionError):controls+=1
else:raise AssertionError('Frozen Core87 verifier accepted newer preparation')
print(f'108 inputs, 148 adapted members, 15 production paths; {controls} rejection controls; no compiler or historical test replay.')
