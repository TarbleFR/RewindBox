#!/usr/bin/env python3
"""Authenticate refined sources/receipts and reject corrupt claims, without compiling."""
import argparse
import copy
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'.github/diagnostics'))
import rpcs3runtime_refinement_core as gate


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source',type=Path)
    ap.add_argument('--uncommitted',action='store_true')
    ap.add_argument('--report',required=True,type=Path)
    args=ap.parse_args()
    source=args.source.resolve()
    authenticated,inputs,history,codegen,extras=gate.source_contract(source,not args.uncommitted)
    reports={}
    with tempfile.TemporaryDirectory(prefix='refinement-receipts-') as directory:
        roots=gate.baselines(source,Path(directory),authenticated)
        expected=gate.expected_results(source,roots)
        payloads={}
        for name,(case,modes) in gate.TESTS.items():
            for mode in modes:
                path=gate.tests.EVIDENCE+'/'+case+'-'+mode+'.json'
                raw=(ROOT/path).read_bytes();payload=json.loads(raw)
                gate.validate_result(name,mode,payload,expected,payload['compiler'])
                key=name+'-'+mode
                payloads[key]=payload
                reports[key]=dict(path=path,sha256=gate.sha(raw),compiler=payload['compiler'],sanitizer=payload['sanitizer'])
        invalid=[
            ('false-success','refined-timer-plain',lambda p:p.update(passed=False)),
            ('invented-device','refined-timer-plain',lambda p:p.update(physicalDeviceTested=True)),
            ('invented-gpu','refined-descriptor-plain',lambda p:p.update(gpuExecuted=True)),
            ('disabled-assertions','refined-descriptor-plain',lambda p:p['compilerFlags'].append('-DNDEBUG')),
            ('wrong-program','refined-descriptor-plain',lambda p:p['programSHA256'].update(candidate='0'*64)),
            ('missing-sanitizer','refined-timer-asan-ubsan',lambda p:p['compilerFlags'].remove('-fsanitize=address,undefined')),
            ('lost-timer-notifications','refined-timer-plain',lambda p:p['results']['functional'].update(notifications=0)),
            ('missing-overflow-cases','refined-timer-plain',lambda p:p['results']['functional'].update(arithmeticEdgeCases=0)),
            ('broken-binding-key','refined-descriptor-plain',lambda p:p['results']['candidate'].update(mismatches=1)),
            ('stale-hash','refined-hash-plain',lambda p:p['results']['candidate'].update(overlapChangedRejected=0)),
            ('no-accepted-stress','refined-hash-tsan',lambda p:p['results']['candidate'].update(stressAcceptedMatches=0)),
            ('hidden-race','refined-hash-tsan',lambda p:p['tsanSuppressions'].append('race:*')),
            ('lost-sequence-check','refined-lookup-plain',lambda p:p['results']['candidate'].update(interleavedEpochRejected=False)),
            ('scoped-stale-payload','rsx-write-sampler-plain',lambda p:p['samplerBindings'].update(candidateStaleGpuPayloads=1)),
        ]
        rejected=[]
        for label,key,mutate in invalid:
            payload=copy.deepcopy(payloads[key]);mutate(payload)
            name,mode=next((n,m) for n,(_,modes) in gate.TESTS.items() for m in modes if n+'-'+m==key)
            try:gate.validate_result(name,mode,payload,expected,payload['compiler'])
            except (AssertionError,KeyError,ValueError):rejected.append(label)
            else:raise AssertionError('Invalid report accepted: '+label)
    assert inputs==gate.inputs()
    result=dict(passed=True,kind='runtime-refinement-source-and-receipt-contract',
        source=gate.command('git','rev-parse','HEAD').decode().strip(),
        committedInputsRequired=not args.uncommitted,inputSHA256=inputs,nativeSourceSHA256=authenticated[0]['files_sha256'],
        supplementalNativeSHA256=extras,codegenProof=codegen,historical=history,
        nativeReports=reports,rejectedCorruptReports=rejected,nativeTestsExecuted=False,
        cmakeExecuted=False,coreBuilt=False,physicalDeviceTested=False,gameplayMeasured=False)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(dict(passed=True,inputs=len(inputs),nativeReports=len(reports),negativeControls=len(rejected),historical=history)))


if __name__=='__main__':main()
