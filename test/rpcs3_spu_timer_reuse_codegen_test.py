#!/usr/bin/env python3
"""Authenticate the timer scratch-only SPU change and execute one CMake proof.

All 40 physical codegen inputs are read; the unchanged LLVM backend digest is
reused from the committed baseline proof after verifying its pin and patch.
No Core configuration, translation, native suite or historical CMake is replayed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile

import rpcs3_spu_runtime_cache_test as cache
import rpcs3_spu_timer_runtime_test as timer
import rpcs3_spu_timer_reuse_test as reuse

ROOT=Path(__file__).resolve().parents[1]
BASELINE='c0df3394d81d957eb7b28c85802278b69cc0f71b'
HISTORY='docs/evidence/rpcs3-runtime-refinement-20261029/codegen.json'


def sha(raw):return hashlib.sha256(raw).hexdigest()


def committed(path):return subprocess.check_output(['git','show',BASELINE+':'+path],cwd=ROOT)


def proof(source,baseline):
    before=sha((baseline/cache.CPP).read_bytes());after=sha((source/cache.CPP).read_bytes())
    old_compat=(baseline/cache.COMPAT).read_text();new_compat=(source/cache.COMPAT).read_text()
    assert new_compat.count(after)==1 and new_compat.replace(after,before,1)==old_compat
    old_alias,new_alias=cache.aliases(old_compat),cache.aliases(new_compat)
    assert old_alias[('Cell/SPUThread.cpp',before)]==new_alias[('Cell/SPUThread.cpp',after)]==cache.SPU_EQUIVALENT
    assert ('Cell/SPUThread.cpp',before) not in new_alias
    runtime=timer.scope_proof(source,baseline)
    assert runtime['changedBodies']['baseline']['mask']==runtime['changedBodies']['candidate']['mask']
    reuse.harness(source,baseline) # Exact worker/sweep/publication extraction guards.
    cmake=(source/cache.CMAKE).read_text();assert cmake==(baseline/cache.CMAKE).read_text()
    original_manifest=json.loads(committed('build-utils/rpcs3/canonical-source.json'))
    current_manifest=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_text())
    for relative in (cache.CPP,cache.COMPAT,cache.CMAKE):
        assert sha((baseline/relative).read_bytes())==original_manifest['files_sha256'][relative]
    historical=committed(HISTORY)
    assert (ROOT/HISTORY).read_bytes()==historical
    authenticated=json.loads(historical)['codegenProof']
    backend=original_manifest['llvm_aarch64_ghc_patch']
    assert current_manifest['llvm_aarch64_ghc_patch']==backend
    patch=ROOT/'build-utils/rpcs3/llvm-aarch64-ghc-emergency-spill.patch'
    assert sha(patch.read_bytes())==backend['patch_sha256']
    inputs={};names={};ids={};unaliased={};changed=set()
    for kind in ('PPU','SPU'):
        names[kind]=re.search(r'foreach\(NEOSTATION_'+kind+r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)',cmake,re.S).group(1).split()
        assert names[kind]==authenticated['sourceLists'][kind]
        oldparts=[];newparts=[];rawparts=[]
        for name in names[kind]:
            external=name.endswith('/AArch64FrameLowering.cpp')
            if external:old=new=backend['postimage_sha256']
            else:old,new=(sha((tree/'rpcs3/Emu'/name).read_bytes()) for tree in (baseline,source))
            assert old==authenticated['inputs'][name]['sourceSHA256'],name
            if old!=new:changed.add(name)
            inputs[name]=dict(baselineSHA256=old,sourceSHA256=new,externalManifestPostimage=external)
            oldparts.append(f'{name}:{old_alias.get((name,old),old)};')
            newparts.append(f'{name}:{new_alias.get((name,new),new)};')
            rawparts.append(f'{name}:{old_alias.get((name,new),new)};')
        ids[kind]=sha(''.join(newparts).encode())[:16]
        unaliased[kind]=sha(''.join(rawparts).encode())[:16]
        assert sha(''.join(oldparts).encode())[:16]==ids[kind]==cache.KNOWN_IDS[kind]
    assert len(inputs)==41 and changed=={'Cell/SPUThread.cpp'}
    assert unaliased['SPU']!=ids['SPU'] and unaliased['PPU']==ids['PPU']
    return dict(inputs=inputs,sourceLists=names,codegen=ids,withoutUpdatedAlias=unaliased,
                alias=dict(actualSHA256=after,baselineSHA256=before,compatibleSHA256=cache.SPU_EQUIVALENT),
                runtimeScope=runtime,physicalCodegenInputs=40,externalLLVMBackendMaterialized=False,
                changedCodegenInputs=sorted(changed),baselineCommit=BASELINE,
                reusedHistoricalProofSHA256=sha(historical),llvmPatchSHA256=sha(patch.read_bytes()))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('source',type=Path);p.add_argument('--baseline',type=Path,required=True)
    p.add_argument('--cmake',default='cmake');p.add_argument('--report',type=Path,required=True)
    a=p.parse_args();source=a.source.resolve();baseline=a.baseline.resolve();identity=proof(source,baseline)
    script=cache.cmake_script(source,baseline,identity)
    with tempfile.TemporaryDirectory(prefix='rpcs3-timer-reuse-codegen-') as temp:
        path=Path(temp)/'verify.cmake';path.write_text(script)
        output=subprocess.check_output([a.cmake,'-P',str(path)],text=True,stderr=subprocess.STDOUT)
    result={mode:dict(re.findall(mode+r'_(PPU|SPU)=([a-f0-9]{16})',output)) for mode in ('baseline','unaliased','candidate','future')}
    result.update(passed=True,wrongPathAndFutureRejected='wrong_path_and_future_rejected=1' in output,cmakeScriptInvocations=1,coreConfigured=False)
    cache.verify_counts(result);assert identity==proof(source,baseline)
    script=script.replace(str(source/cache.COMPAT),'@SOURCE_COMPAT@').replace(str(baseline/cache.COMPAT),'@BASELINE_COMPAT@')
    report=dict(passed=True,results=result,codegenProof=identity,
                sourceSHA256={p:sha((source/p).read_bytes()) for p in cache.SOURCE+cache.SUPPORT},
                baselineSHA256={p:sha((baseline/p).read_bytes()) for p in cache.SOURCE+cache.SUPPORT},
                harnessSHA256=sha(script.encode()),scriptSHA256=sha(Path(__file__).read_bytes()),
                cmake=subprocess.check_output([a.cmake,'--version'],text=True).splitlines()[0],
                generatedObjectsRecompiled=False,historicalNativeSuitesReplayed=False,physicalDeviceTested=False)
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(passed=True,results=result,sourceSHA256=report['sourceSHA256']),indent=2))


if __name__=='__main__':main()
