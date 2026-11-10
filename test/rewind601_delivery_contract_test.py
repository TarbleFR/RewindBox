#!/usr/bin/env python3
"""Check only the new private-delivery binding; no native compiler/test replay."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import rewind601_baseline as tree
import rewind601_engine as engine

checks=0

def check(value,message):
 global checks
 checks+=1
 assert value,message

check(tree.products(tree.BASE_SOURCE)==tree.BASE_PRODUCTS,'Verified private600 product roots')
check(tree.products(tree.SOURCE)==tree.PRODUCTS,'Reviewed new core product roots')
check(tree.git('diff-tree','--no-commit-id','--name-only','-r',tree.BASE_SOURCE,tree.SOURCE,'--',*tree.PRODUCTS).splitlines()==tree.PRODUCT_DELTA,'No host product differences from verified 600 source')
workflow=(ROOT/'.github/workflows/rewind601-dual-core-delivery.yml').read_text()
check(tree.component_pins(workflow)==tree.COMPONENT_PINS,'Retained component pins')
check("BUILD_NUMBER: '601'"in workflow and 'delivery-601-recipient.pem'in workflow,'Private delivery number/recipient')
check('build_core.sh'not in workflow and 'dotnet publish'not in workflow,'No engine rebuild')
check('actions/setup-dotnet'not in workflow,'No unneeded NativeAOT compiler setup')
check('rpcs3runtime601_core'in workflow,'Authenticate fresh compiled RPCS3 binding')
check('validate_melonx_engine601_ipa.py'in workflow and 'validate_rpcs3_core601_ipa.py'in workflow,'New explicit delivery validators')
check('release:'not in workflow and 'gh release'not in workflow,'No public release')

run=dict(head_sha=engine.MELONX_SOURCE,path=engine.MELONX_WORKFLOW,run_attempt=1,conclusion='success',status='completed')
job=dict(run_id=engine.MELONX_RUN,head_sha=engine.MELONX_SOURCE,conclusion='success',run_attempt=1,steps=[dict(name=n,conclusion='success')for n in engine.ENGINE_STEPS])
artifact=dict(id=engine.MELONX_ARTIFACT_ID,name=engine.MELONX_ARTIFACT_NAME,size_in_bytes=engine.MELONX_ARTIFACT_BYTES,digest='sha256:'+engine.MELONX_ARTIFACT_SHA256,expired=False,workflow_run=dict(id=engine.MELONX_RUN,head_sha=engine.MELONX_SOURCE))
values={f'actions/runs/{engine.MELONX_RUN}':run,f'actions/jobs/{engine.MELONX_JOB}':job,f'actions/artifacts/{engine.MELONX_ARTIFACT_ID}':artifact}
original=engine.api
try:
 engine.api=lambda path:values[path]
 check(engine._query_engine_run()['source']==engine.MELONX_SOURCE,'Exact producer accepted')
 for target,key,bad in [(run,'head_sha','0'*40),(run,'conclusion','failure'),(run,'run_attempt',2),(job,'conclusion','failure'),(job,'steps',[]),(artifact,'digest','sha256:'+'0'*64),(artifact,'expired',True),(artifact,'size_in_bytes',1)]:
  before=target[key];target[key]=bad
  try:engine._query_engine_run()
  except ValueError:checks+=1
  else:raise AssertionError('Changed producer metadata accepted: '+key)
  finally:target[key]=before
finally:engine.api=original

# The public key is intentionally the only key committed to the repository.
key=(ROOT/'build-utils/delivery-601-recipient.pem').read_text()
check(key.startswith('-----BEGIN PUBLIC KEY-----')and 'PRIVATE KEY'not in key,'Public recipient only')
report=dict(result='passed',checks=checks,build=601,baseline=600,retainedCore=engine.MELONX_SOURCE,coreRecompiled=False,nativeTestsExecuted=0,producerMetadataDoubledInNegativeControls=True,
            inputs={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in sorted(tree.RECIPE)})
out=ROOT/'build/delivery/delivery601-contract-checks.json';out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
