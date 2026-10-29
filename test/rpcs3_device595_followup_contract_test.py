#!/usr/bin/env python3
"""Authenticate source, six new native results, six unchanged results and JIT IDs.

No compiler, native program, CMake or historical gate is reexecuted.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import rpcs3_device595_test as previous
import rpcs3_texture_address_index_test as address
import rpcs3_surface_coverage_test as coverage
import rpcs3_temporary_remap_test as remap
import rpcs3_spu_timer_reuse_test as timer
import rpcs3_spu_timer_reuse_codegen_test as codegen

ROOT=Path(__file__).resolve().parents[1]
EVIDENCE=ROOT/'docs/evidence/rpcs3-device595-followup-20261029'
digest=lambda raw:hashlib.sha256(raw).hexdigest()
sha=previous.sha

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('source',type=Path)
    p.add_argument('--baseline',type=Path,required=True);p.add_argument('--original-baseline',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True);a=p.parse_args()
    source=a.source.resolve();baseline=a.baseline.resolve();original=a.original_baseline.resolve()
    manifest=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_text())
    record=json.loads((EVIDENCE/'source-record.json').read_text())
    assert record==manifest['device595_followup_20261029']
    old=json.loads(subprocess.check_output(['git','show',record['baseline_commit']+':build-utils/rpcs3/canonical-source.json'],cwd=ROOT))
    assert old['patch_sha256']==record['baseline_patch_sha256']
    assert digest((ROOT/'build-utils/rpcs3/embedded-core.patch').read_bytes())==manifest['patch_sha256']
    for root,expected in [(source,manifest['files_sha256']),(baseline,old['files_sha256'])]:
        for path,h in expected.items():assert sha(root/path)==h,path
    changed={path for path,h in manifest['files_sha256'].items() if old['files_sha256'].get(path)!=h}
    assert changed==set(record['files_after_sha256']) and len(changed)==5
    assert len(manifest['files_sha256'])==314
    fixture=ROOT/record['delta_fixture'];assert sha(fixture)==record['delta_sha256']
    with tempfile.TemporaryDirectory(prefix='rpcs3-followup-contract-') as temp:
        for path in changed:
            dst=Path(temp)/path;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/path,dst)
        subprocess.run(['git','apply','--reverse',str(fixture)],cwd=temp,check=True)
        for path in changed:assert sha(Path(temp)/path)==sha(baseline/path)==record['files_before_sha256'][path]
    proofs={}
    def check(path,program,before):
        proof=json.loads(path.read_text());assert proof['passed']
        assert not proof['physicalDeviceTested'] and not proof['gameplayMeasured']
        assert proof['harnessSHA256']==digest(program.encode()),path
        assert '-UNDEBUG' in proof['compilerFlags'] and '-DNDEBUG' not in proof['compilerFlags']
        assert ('-fsanitize=address,undefined' in proof['compilerFlags'])==('asan' in path.name)
        for tree,key in [(source,'sourceSHA256'),(before,'baselineSHA256')]:
            for name,h in proof[key].items():assert sha(tree/name)==h,name
        proofs[str(path.relative_to(ROOT))]=sha(path)
        return proof
    for name,module,folder in [('surface-coverage',coverage,EVIDENCE),('spu-timer-reuse',timer,EVIDENCE),
            ('',remap,ROOT/'docs/evidence/rpcs3-temporary-remap-20261029')]:
        program=module.harness(source,baseline)
        for mode in ['plain','asan']:
            filename=(f'{name}-' if name else '')+mode+'.json'
            proof=check(folder/filename,program,baseline)
            if module is timer:
                expected=timer.expected(source,baseline)
                assert all(proof[k]==v for k,v in expected.items())
    # The previous six programs and all their actual inputs remain exact.
    for name in ['array','temporary','address']:
        program=(address.harness(source,original) if name=='address' else getattr(previous,'make_'+name)(source,original)[0])
        for mode in ['plain','asan']:
            check(ROOT/f'docs/evidence/rpcs3-device595-20261029/{name}-{mode}.json',program,original)
    path=EVIDENCE/'spu-timer-reuse-codegen.json';proof=json.loads(path.read_text())
    identity=codegen.proof(source,baseline);assert proof['codegenProof']==identity and proof['passed']
    assert proof['scriptSHA256']==digest(Path(codegen.__file__).read_bytes())
    script=codegen.cache.cmake_script(source,baseline,identity)
    script=script.replace(str(source/codegen.cache.COMPAT),'@SOURCE_COMPAT@').replace(str(baseline/codegen.cache.COMPAT),'@BASELINE_COMPAT@')
    assert proof['harnessSHA256']==digest(script.encode())
    codegen.cache.verify_counts(proof['results'])
    assert identity['codegen']==record['codegen_identity']
    proofs[str(path.relative_to(ROOT))]=sha(path)
    result=dict(passed=True,canonicalPostimages=314,unchangedPostimages=309,newNativeModes=6,reusedPreviousNativeModes=6,
        authenticatedProofs=proofs,codegenIdentity=identity['codegen'],nativeOrCmakeReexecuted=False,
        reverseDeltaMatchesBaseline=True,physicalDeviceTested=False,gameplayMeasured=False)
    a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
