"""Gate the refined bodies and reuse exact successful global Core programs.

Source/receipt checks never run historical native suites or CMake. A future
explicit Core request runs only the changed programs and new lookup checks.
"""
import copy
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'test'))
import rpcs3_refinement_delta as delta
import rpcs3_runtime_refinement_test as tests
import rpcs3runtime_global_core as previous
import rpcs3runtime_bo2_warm_core as pipeline

OUT, PROOF = previous.OUT, previous.PROOF
MANIFEST, ENTRY, WORKFLOW = previous.MANIFEST, previous.ENTRY, previous.WORKFLOW
GATE = '.github/diagnostics/rpcs3runtime_refinement_core.py'
PREFIX = 'docs/evidence/rpcs3-global-20261029/apple-core/success-5b2a5614/'
OLD_PROOF = PREFIX+'preflight/runtime592-proof.json'
OLD_RECEIPT = PREFIX+'artifact-verification.json'
CODEGEN = tests.EVIDENCE+'/codegen.json'
SCRIPT = 'test/rpcs3_runtime_refinement_test.py'
SUPERSEDED = {'spu-timer','descriptor-bind','texture-hash-reuse','rsx-write-sampler'}
TESTS = {
    'refined-timer':('timer',('plain','asan-ubsan')),
    'refined-descriptor':('descriptor',('plain','asan-ubsan')),
    'refined-hash':('hash',('plain','asan-ubsan','tsan')),
    'refined-lookup':('lookup',('plain','asan-ubsan')),
    'rsx-write-sampler':('rsx-write-sampler',('plain','asan-ubsan')),
}
sha,command = previous.sha,previous.command


def input_paths():
    proof = json.loads((ROOT/OLD_PROOF).read_bytes())
    return previous.input_paths() | {GATE,SCRIPT,'test/rpcs3_refinement_delta.py',delta.FIXTURE,
        'test/rpcs3_refinement_contract_test.py',
        'test/native/rpcs3_refinement_timer_edges.inc',OLD_PROOF,OLD_RECEIPT,CODEGEN} | {
        PREFIX+'diagnostics/'+key+suffix for key in proof['tests']
        for suffix in ('-result.json','-output.txt')}


def inputs():
    return {p:sha((ROOT/p).read_bytes()) for p in sorted(input_paths())}


def baselines(source,directory,authenticated=None):
    before = directory/'beforeRefinement'
    oldproof = json.loads((ROOT/OLD_PROOF).read_bytes())
    manifest,record,parent = delta.reconstruct(source,before,oldproof['supplemental_native_sha256'])
    oldauth = (parent,parent[previous.delta.KEY],json.loads(previous.delta.committed_bytes(MANIFEST)))
    roots = previous.baselines(before,directory,oldauth)
    return dict(beforeRefinement=before,**roots)


def unchanged_programs(source,roots):
    baseline = roots['beforeRefinement']
    old = previous.expected_results(baseline,roots)
    current = previous.previous.expected_results(source,roots)
    for name in ('spu-mfc','neoswap-discard','viewport-scissor'):
        before = roots['beforeWarm'] if name=='viewport-scissor' else roots['beforeGlobal']
        current[name] = previous.modules()[name].expected(source,before)
    changed_metadata = {}
    for name in set(old)-SUPERSEDED:
        changed_metadata[name] = previous.rehash_metadata(current[name],old[name],baseline,delta.PATHS)
    # The seven still older programs (16 Apple modes) retain exact production
    # programs as well. Only their whole-file metadata may be rebound.
    older_before = previous.passed_programs(baseline,roots)
    older_after = previous.passed_programs(source,roots)
    assert len(older_before)==7
    older = {n:previous.rehash_metadata(older_after[n],e,baseline,delta.PATHS) for n,e in older_before.items()}
    return old,changed_metadata,older


def source_contract(source,require_committed=True):
    source = Path(source)
    current = inputs()
    with tempfile.TemporaryDirectory(prefix='refinement-contract-') as temporary:
        roots = baselines(source,Path(temporary))
        before = roots['beforeRefinement']
        manifest = json.loads((ROOT/MANIFEST).read_bytes())
        parent = json.loads(delta.original(MANIFEST))
        record = manifest[delta.KEY]
        assert record['codegen'] == tests.cache.KNOWN_IDS
        route = """    if 'runtime_refinement_20261029' in manifest():
        from rpcs3runtime_refinement_core import main as refinement_main
        refinement_main(a)
        raise SystemExit
"""
        entry = delta.original(ENTRY).decode()
        anchor = "    if 'runtime_global_20261029' in manifest():\n"
        assert entry.count(anchor)==1
        assert (ROOT/ENTRY).read_text()==entry.replace(anchor,route+anchor,1)
        extra_paths=[GATE,'test/rpcs3_refinement_delta.py',SCRIPT,
            'test/native/rpcs3_refinement_timer_edges.inc',delta.FIXTURE,CODEGEN]
        workflow=delta.original(WORKFLOW).decode()
        anchor="      - '.github/diagnostics/rpcs3runtime_global_core.py'\n"
        assert workflow.count(anchor)==1
        assert (ROOT/WORKFLOW).read_text()==workflow.replace(anchor,anchor+''.join("      - '"+p+"'\n" for p in extra_paths),1)
        pin=delta.original('test/neo_swap_core_pin_test.py').decode()
        assert (ROOT/'test/neo_swap_core_pin_test.py').read_text()==pin.replace(parent['patch_sha256'],manifest['patch_sha256'])
        assert command('git','-C',str(source),'rev-parse','HEAD').decode().strip()==manifest['upstream_commit']
        # Bind the prior independently verified Apple proof to its immutable
        # source commit, all original validation inputs, reports and outputs.
        raw = (ROOT/OLD_PROOF).read_bytes()
        oldproof = json.loads(raw)
        artifact = json.loads((ROOT/OLD_RECEIPT).read_bytes())
        assert (ROOT/OLD_RECEIPT).read_bytes()==delta.original(OLD_RECEIPT)
        assert artifact['passed'] and artifact['all_three_archive_bytes_verified']
        assert artifact['canonical_patch_sha256']==parent['patch_sha256']
        assert artifact['files_sha256']['runtime592-proof.json']==sha(raw)
        assert oldproof['source']==artifact['source']=='5b2a5614f634221ea896607b4686ad2afdd5ada3'
        assert oldproof['all_tests_passed'] and len(oldproof['tests'])==26
        assert oldproof['native_source_sha256']==parent['files_sha256']
        assert len(oldproof['input_sha256'])==269
        for path,digest in oldproof['input_sha256'].items():
            assert sha(command('git','show',oldproof['source']+':'+path))==digest,path
            if path not in {MANIFEST,'build-utils/rpcs3/embedded-core.patch','test/neo_swap_core_pin_test.py',ENTRY,WORKFLOW}:
                assert sha((ROOT/path).read_bytes())==digest,('Historical validator changed',path)
        for path,digest in oldproof['supplemental_native_sha256'].items():
            assert sha((before/path).read_bytes())==digest,path
        oldexpected,rebound,older = unchanged_programs(source,roots)
        for name,(_,modes) in previous.all_tests().items():
            for mode in modes:
                key=name+'-'+mode; state=oldproof['tests'][key]
                assert state['passed'] and state['returncode']==0
                for suffix,field in (('-result.json','report_sha256'),('-output.txt','output_sha256')):
                    assert sha((ROOT/(PREFIX+'diagnostics/'+key+suffix)).read_bytes())==state[field],key
                payload=json.loads((ROOT/(PREFIX+'preflight/'+key+'-result.json')).read_bytes())
                previous.validate_result(name,mode,payload,oldexpected,oldproof['host']['compiler'])
        assert sum(len(previous.all_tests()[n][1]) for n in rebound)==17
        proof = tests.codegen_proof(source,before)
        cached = json.loads((ROOT/CODEGEN).read_bytes())
        assert cached['passed'] and not cached['physicalDeviceTested'] and cached['case']=='codegen'
        tests.validate('codegen',cached['results'])
        assert cached['codegenProof']==proof
        extras={path:sha((source/path).read_bytes()) for path in oldproof['supplemental_native_sha256']}
        historical=dict(coreSource=oldproof['source'],coreSHA256=artifact['core_sha256'],
            proofSHA256=sha(raw),artifactReceiptSHA256=sha((ROOT/OLD_RECEIPT).read_bytes()),
            unchangedGlobalModes=17,unchangedOlderModes=16,supersededGlobalModes=9,
            rehashedWholeFileMetadata=rebound,olderRehashedWholeFileMetadata=older,
            nativeSuitesReplayed=False,coreBinaryReused=False)
    if require_committed:
        pipeline.committed_inputs(current)
    assert current==inputs()
    return (manifest,record,parent),current,historical,proof,extras


def all_tests():
    return {name:(SCRIPT,modes) for name,(_,modes) in TESTS.items()}


def baseline_commits():
    return dict(beforeRefinement=delta.BASELINE,**previous.baseline_commits())


def expected_results(source,roots):
    result={name:tests.expected(case,source,roots['beforeRefinement'])
            for name,(case,_) in TESTS.items() if case!='rsx-write-sampler'}
    result['rsx-write-sampler']=previous.previous.previous.bo2.expected_results(source,roots)['rsx-write-sampler']
    return result


def runner_command(name,mode,source,roots,compiler):
    if name=='rsx-write-sampler':
        return previous.runner_command(name,mode,source,roots,compiler)
    case=TESTS[name][0]
    argv=['python3',SCRIPT,str(source),'--baseline',str(roots['beforeRefinement']),
          '--case',case,'--compiler',compiler]
    if mode!='plain':
        argv+=['--sanitizer','thread' if mode=='tsan' else 'address,undefined']
    elif case in ('timer','descriptor','lookup'):
        argv+=['--benchmark']
    return argv+['--report',str(OUT/(name+'-'+mode+'-result.json'))]


def validate_result(name,mode,payload,expected,compiler):
    if name=='rsx-write-sampler':
        assert payload['compiler']==compiler
        return previous.validate_delta_result(name,mode,payload,expected)
    assert payload['passed'] and payload['case']==TESTS[name][0]
    # prepare()/verify() require the Apple compiler at the pipeline boundary.
    # This same semantic validator also authenticates honest Linux receipts.
    assert payload['compiler']==compiler
    assert payload['physicalDeviceTested'] is False and payload['gameplayMeasured'] is False
    assert payload['gpuExecuted'] is False and payload['coreBuilt'] is False
    assert payload['tsanSuppressions']==[]
    assert payload['sanitizer']==('' if mode=='plain' else 'thread' if mode=='tsan' else 'address,undefined')
    assert '-UNDEBUG' in payload['compilerFlags'] and not any(x.startswith('-DNDEBUG') for x in payload['compilerFlags'])
    assert ('-fsanitize=address,undefined' in payload['compilerFlags'])==(mode=='asan-ubsan')
    assert ('-fsanitize=thread' in payload['compilerFlags'])==(mode=='tsan')
    for key,value in expected[name].items():
        assert payload[key]==value,(name,key)
    tests.validate(TESTS[name][0],payload['results'])


def main(args):
    if args.write_core_identity:
        pipeline.identity(args.write_core_identity,gate=sys.modules[__name__])
    elif args.verify_reuse:
        pipeline.verify(args.verify_reuse,args.source,gate=sys.modules[__name__])
    elif args.source:
        pipeline.prepare(args.source.resolve(),gate=sys.modules[__name__])
    else:
        raise ValueError('A source or preflight proof is required')
