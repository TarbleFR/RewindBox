#!/usr/bin/env python3
"""Reproduce the real CMake recipe and prove exact host-only change scope.

No CMake/LLVM executable, network request, Core build or game is run. The one
unmaterialized LLVM backend digest is reused from authenticated 597 evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
from run_late_snr import braced

CPP='rpcs3/Emu/Cell/SPUThread.cpp'
COMPAT='rpcs3/Emu/CPU/JITCacheCompatibility.cmake'
CMAKE='rpcs3/Emu/CMakeLists.txt'
sha=lambda b:hashlib.sha256(b).hexdigest()

def aliases_from(text):
    return {(path,actual):compatible for path,actual,compatible in re.findall(
        r'(?:if|elseif)\(source STREQUAL "([^"]+)" AND\s*actual STREQUAL "([0-9a-f]{64})"\)\s*'
        r'set\(\$\{output\} "([0-9a-f]{64})" PARENT_SCOPE\)',text)}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args();tree=args.source.resolve();baseline=args.baseline.resolve();repo=args.repo.resolve()
    evidence_path=repo/'docs/evidence/rpcs3-continuation-20261030/codegen-identity.json'
    evidence=json.loads(evidence_path.read_text())
    cmake=(tree/CMAKE).read_text();compat=(tree/COMPAT).read_text();baseline_compat=(baseline/COMPAT).read_text()
    assert (tree/CMAKE).read_bytes()==(baseline/CMAKE).read_bytes()
    aliases=aliases_from(baseline_compat);candidate_aliases=aliases_from(compat)
    assert len(aliases)==5 and len(candidate_aliases)==6
    assert all(candidate_aliases[key]==value for key,value in aliases.items())
    assert sha(baseline_compat.encode())=='acf9518ceed92ca6024939054a83060b9fdc9dce2f1281dbfed0bebda040a4db'
    before=(baseline/CPP).read_text();after=(tree/CPP).read_text()
    old_hash,new_hash=sha(before.encode()),sha(after.encode())
    assert old_hash=='4d138e76afc25d12d8eff04a5794153cbe9a4562c8dcbe5d9eac274ab4c927d3'
    restored=after
    changed_methods={}
    for signature in ['bool spu_thread::process_mfc_cmd()', 'void spu_thread::do_dma_transfer(', 'bool spu_thread::do_list_transfer(']:
        old,new=braced(before,signature),braced(after,signature)
        restored=restored.replace(new,old,1)
        changed_methods[signature]={'before':sha(old.encode()),'after':sha(new.encode())}
    helper=braced(after,'static void ios_publish_mfc_snapshot(')
    start=restored.index('#ifdef RPCS3_IOS\n// Called only by the SPU owner')
    end=restored.index('\n#endif\n\n',start)+len('\n#endif\n\n')
    restored=restored[:start]+restored[end:]
    restored=restored.replace('#include "ios/IOSSignalTrace.h"\n','',1)
    assert restored==before
    mapped=aliases[('Cell/SPUThread.cpp',old_hash)]
    assert ('Cell/SPUThread.cpp',new_hash) not in aliases
    assert set(candidate_aliases)-set(aliases)=={('Cell/SPUThread.cpp',new_hash)}
    assert candidate_aliases[('Cell/SPUThread.cpp',new_hash)]==mapped
    addition=compat[compat.index('    # Device597 follow-up:'):compat.index('    # CELL559:')]
    assert compat.replace(addition,'',1)==baseline_compat
    assert 'else()\n        set(${output} "${actual}" PARENT_SCOPE)' in compat
    inputs={};external=[];borrowed=[]
    for name,record in evidence['inputs'].items():
        if name=='../../3rdparty/llvm/llvm/llvm/lib/Target/AArch64/AArch64FrameLowering.cpp':
            assert record['before']==record['after']
            inputs[name]={'before':record['after'],'after':record['after'],'source':'authenticated unchanged LLVM backend digest'};external.append(name);continue
        old_path=baseline/'rpcs3/Emu'/name
        assert sha(old_path.read_bytes())==record['after'],('baseline',name)
        path=tree/'rpcs3/Emu'/name
        if not path.is_file():path=old_path;borrowed.append(name)
        actual=sha(path.read_bytes())
        assert actual==(new_hash if name=='Cell/SPUThread.cpp' else record['after']),name
        inputs[name]={'before':record['after'],'after':actual,'source':str(path.resolve())}

    def identity(kind,which,table):
        names=re.search(r'foreach\(NEOSTATION_'+kind+r'_CODEGEN_SOURCE IN ITEMS\s+(.*?)\)',cmake,re.S).group(1).split()
        assert f'neostation_codegen_compatible_hash("${{NEOSTATION_{kind}_CODEGEN_SOURCE}}" "${{NEOSTATION_{kind}_CODEGEN_FILE_SHA256}}" NEOSTATION_{kind}_CODEGEN_FILE_SHA256)' in cmake
        digest=''.join(name+':'+table.get((name,inputs[name][which]),inputs[name][which])+';' for name in names)
        return sha(digest.encode())[:16],names

    baseline_ids={kind:identity(kind,'before',aliases)[0] for kind in ['PPU','SPU']}
    no_alias={kind:identity(kind,'after',aliases)[0] for kind in ['PPU','SPU']}
    final_ids={kind:identity(kind,'after',candidate_aliases)[0] for kind in ['PPU','SPU']}
    assert baseline_ids==evidence['identities']['after']=={'PPU':'a987639e9f838d1c','SPU':'477a3fa442d27917'}
    assert final_ids==baseline_ids and no_alias['PPU']==baseline_ids['PPU'] and no_alias['SPU']!=baseline_ids['SPU']
    future_hash=sha((after+' ').encode())
    assert candidate_aliases.get(('Cell/SPUThread.cpp',future_hash),future_hash)==future_hash
    assert candidate_aliases.get(('Cell/SPUThread.cpp.future',new_hash),new_hash)==new_hash
    inputs['Cell/SPUThread.cpp']['after']=future_hash
    future_id=identity('SPU','after',candidate_aliases)[0]
    inputs['Cell/SPUThread.cpp']['after']=new_hash
    assert future_id!=final_ids['SPU']
    checks={}
    for name in ['rpcs3/Emu/Cell/SPUThread.h','rpcs3/Emu/Cell/SPULLVMRecompiler.cpp','rpcs3/Emu/CPU/CPUTranslator.h',
                 'rpcs3/Emu/Cell/SPUCommonRecompiler.cpp','Utilities/JITLLVM.cpp',CMAKE]:
        raw=(tree/name).read_bytes();assert raw==(baseline/name).read_bytes(),name;checks[name]=sha(raw)
    translator=(tree/'rpcs3/Emu/Cell/SPULLVMRecompiler.cpp').read_text()
    helpers={signature:sha(braced(translator,signature).encode()) for signature in
        ['static void exec_wrch(', 'static void exec_wrch_result(', 'static void exec_mfc_wrch(', 'static void exec_mfc_cmd(']}
    call=braced((tree/'rpcs3/Emu/CPU/CPUTranslator.h').read_text(),'llvm::CallInst* call(std::string_view lame,')
    assert 'getOrInsertFunction' in call and 'updateGlobalMapping' in call and 'CreateCall' in call
    assert 'call("spu_write_channel", &exec_wrch' in translator
    record={
        'passed':True,'recommendation':'Preserve only the immediate delivered597 identity with the implemented exact new-file alias.',
        'sourceScope':'Only three host SPU method bodies, their diagnostic include and the new owner-only snapshot helper differ. Restoring/removing exactly those regions recovers every delivered597 SPUThread.cpp byte. Header/layout, translator, helper call signatures and linkage bodies are unchanged.',
        'changedHostMethods':changed_methods,'newOwnerHelperSHA256':sha(helper.encode()),'traceHeaderSHA256':sha((tree/'rpcs3/ios/IOSSignalTrace.h').read_bytes()),
        'baselineSourceSHA256':old_hash,'candidateSourceSHA256':new_hash,'compatibleEffectiveSHA256':mapped,
        'baselineCompatibilitySHA256':sha(baseline_compat.encode()),'candidateCompatibilitySHA256':sha(compat.encode()),
        'existingAliasCount':len(aliases),'candidateAliasCount':len(candidate_aliases),'allExistingAliasesUnchanged':True,
        'identityRecipe':'Ordered real CMake foreach paths; SHA256 raw bytes; exact compatibility mapping; concatenate path:effective_sha256; SHA256 and first 16 hex characters.',
        'baselineIdentities':baseline_ids,'candidateWithoutAlias':no_alias,'candidateWithExactAlias':final_ids,'futureSpuIdentity':future_id,
        'sourceCounts':{kind:len(identity(kind,'after',candidate_aliases)[1]) for kind in ['PPU','SPU']},
        'inputs':inputs,'externalInputs':external,'unmodifiedInputsBorrowedFromBaseline':borrowed,'canonicalUnchangedSources':checks,'unchangedNativeHelperSHA256':helpers,
        'externalCallTemplateSHA256':sha(call.encode()),
        'runtimeRelocationEvidence':'CPUTranslator::call declares a named external function, maps its current native address and emits CreateCall. Full-queue WRCH uses spu_write_channel/exec_wrch -> current set_ch_value/process_mfc_cmd. Cached objects do not embed these host bodies.',
        'exactAliasCases':[
            {'source':'Cell/SPUThread.cpp','actual':new_hash,'mapped':candidate_aliases[('Cell/SPUThread.cpp',new_hash)]},
            {'source':'Cell/SPUThread.cpp.future','actual':new_hash,'mapped':candidate_aliases.get(('Cell/SPUThread.cpp.future',new_hash),new_hash)},
            {'source':'Cell/SPUThread.cpp','actual':future_hash,'mapped':candidate_aliases.get(('Cell/SPUThread.cpp',future_hash),future_hash)},
            {'source':'Cell/SPUThread.cpp','actual':old_hash,'mapped':candidate_aliases[('Cell/SPUThread.cpp',old_hash)]}],
        'cmakeBinaryExecuted':False,'nativeObjectEmissionCompared':False,'llvmSubmoduleFetched':False,
        'limits':'Source-equivalence and recipe reproduction; no Apple binary or freshly emitted LLVM object comparison. Fixed LLVM pin, backend patch, toolchain and runtime feature/settings keys remain required.',
        'scriptSHA256':sha(Path(__file__).read_bytes()),'inputEvidenceSHA256':sha(evidence_path.read_bytes()),
    }
    args.report.parent.mkdir(parents=True,exist_ok=True);args.report.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps({k:v for k,v in record.items() if k not in ['inputs','canonicalUnchangedSources','unchangedNativeHelperSHA256']},indent=2))

if __name__=='__main__':main()
