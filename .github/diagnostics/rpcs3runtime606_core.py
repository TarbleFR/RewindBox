"""Authenticate the successful a4d0c9a5 RPCS3 iPhone Core for private IPA606.

This delivery reuses the actual compiled archive. The original two Apple modes, ten reused Apple modes, and historical 28
retain their producer scope. Only three reviewed host journal paths may differ.
The third is the exact concurrent bridge delta for bounded cache milestones;
it does not select or modify the retained Core or its MoltenVK runtime.
No native tests or Core compilation execute in this delivery wrapper.
"""
from functools import lru_cache
from pathlib import Path
import argparse, ast, hashlib, io, json, re, subprocess, sys, tempfile, zipfile

ROOT=Path(__file__).resolve().parents[2]
for part in ("build-utils","packages/dolphin_internal_bridge/ci","test"):
    sys.path.insert(0,str(ROOT/part))
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho
from validate_rpcs3_embedded_core import validate_core

DELIVERY_BASELINE=605
CORE_SOURCE="a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a"
CORE_NATIVE_SOURCE=CORE_SOURCE
CORE_RUN=41117115264
CORE_JOB=124274114161
CORE_ID="@rpath/libRPCS3Core.dylib"
CORE_TYPE="rpcs3-ios-device601-followup"
CORE_WORKFLOW=".github/workflows/rpcs3-runtime592-core.yml"
PIN_PATH="docs/evidence/rpcs3-core604/apple-core.json"
PIN=json.loads((ROOT/PIN_PATH).read_bytes())
CORE_SHA256=PIN["coreSHA256"]
IDENTITY_SHA256=PIN["identitySHA256"]
PROOF_SHA256=PIN["proofSHA256"]
PATCH_SHA256="70d694bb3ef812b87b8839e53335376028aa16476893512d012b77ef1952fd79"
SOURCE_CONTRACT_SHA256="657aa623d118644888ec9fe588db68882bc61cacc794de26d4cfc2878cfba77d"
SOURCE_CONTRACT="docs/evidence/rpcs3-device601-20261030/source-contract.json"
CODEGEN={"PPU":"a987639e9f838d1c","SPU":"477a3fa442d27917"}
FRESH={"mfc-decrementer-plain", "mfc-decrementer-asan-ubsan"}
REUSED={name+"-"+mode for name in ("tiny-vertex", "vertex-range", "exitspawn-worker",
                                  "savestate-completion", "color-feedback")
        for mode in ("plain", "asan-ubsan")}
CORE_STEPS=(
    "Authenticate historical Core and execute only the candidate delta on ARM64",
    "Compile actual iPhone Core from the verified source",
    "Verify source candidate, exact exports, passive loading and source identity",
    "Upload source candidate without a delivery number",
)
CORE_FILES=("identity.json","runtime592-proof.json","libRPCS3Core.dylib",
            "RPCS3_SOURCE_COMMIT.txt","RPCS3_IOS_ABI.txt","libRPCS3Core.dylib.sha256")
CORE_MARKERS=(
 b"Automatic enables it for God of War III, Call of Duty: Black Ops II, Bladestorm and Assassin's Creed;",
 b"COREPROF OPT587",b"canary=%s confirmed=%u exec_queues=%u",
 b"MoltenVK asynchronous submits: encoding queue recorded; acquisitions wait for the last queued present",
 b"rewindbox-mvk-async-587.txt",b"MoltenVK asynchronous submits enabled for this boot",
 b"MoltenVK asynchronous submits stay off for %s: its last asynchronous boot did not finish (crash or forced exit)",
 b"COREPROF SIGNALCAUSE",b"COREPROF RENDERCAUSE",b"COREPROF FRAMECAUSE",
)
MANIFEST="build-utils/rpcs3/canonical-source.json"
PATCH="build-utils/rpcs3/embedded-core.patch"
HOST_STORE="native/neoswap-storage/Store.cpp"
HOST_STORE_SHA256="87df68227cf9e113af51ec2ea8968d8af88170834611d560ce711cf168f1ca46"
HOST_LOGGER="packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm"
ARCHIVES={key:PIN[key] for key in ("artifact", "diagnosticsArtifact", "preflightArtifact")}

def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def configuration():
 require(PIN["conclusion"]=="success" and PIN["run"]==CORE_RUN and
         PIN["source"]==CORE_SOURCE and PIN["job"]==CORE_JOB and PIN["runAttempt"]==1,
         "A completed successful Apple Core artifact is required")
 return dict(run=dict(id=CORE_RUN,run_attempt=1),coreSHA256=CORE_SHA256,
             identitySHA256=IDENTITY_SHA256,proofSHA256=PROOF_SHA256,
             sourcePatchSHA256=PATCH_SHA256,core=dict(bytes=PIN["coreBytes"]),
             inputCount=41,coreInputCount=92,compiledInputCount=126,nativePostimageCount=326,
             codegen=CODEGEN,**ARCHIVES)
def api(endpoint):
 return json.loads(subprocess.check_output(["gh","api","repos/TarbleFR/RewindBox/"+endpoint],cwd=ROOT,timeout=120))
@lru_cache(maxsize=256)
def compiled_source_bytes(path):
 require(not Path(path).is_absolute() and ".." not in Path(path).parts,"Invalid compiled source path")
 return subprocess.check_output(["git","show",CORE_SOURCE+":"+path],cwd=ROOT,timeout=60)

def _query_core_run():
 configuration()
 run=api(f"actions/runs/{CORE_RUN}")
 require(run["head_sha"]==CORE_SOURCE and run["path"]==CORE_WORKFLOW and
         run["status"]=="completed" and run["conclusion"]=="success" and run["run_attempt"]==1,
         "Wrong RPCS3 Apple producer")
 jobs=api(f"actions/runs/{CORE_RUN}/jobs?per_page=100")
 found=set()
 for job in jobs["jobs"]:
  if job["id"]!=CORE_JOB:continue
  require(job["run_id"]==CORE_RUN and job["conclusion"]=="success","Wrong Core job")
  for step in job["steps"]:
   if step["name"] in CORE_STEPS and step["status"]=="completed" and step["conclusion"]=="success":
    found.add(step["name"])
 require(found==set(CORE_STEPS),"Actual iPhone Core/validation steps did not all succeed")
 for key,expected in ARCHIVES.items():
  artifact=api(f"actions/artifacts/{expected['id']}")
  require(artifact["id"]==expected["id"] and artifact["name"]==expected["name"] and
          artifact["digest"]==expected["digest"] and artifact["size_in_bytes"]==expected["bytes"] and
          not artifact["expired"] and artifact["workflow_run"]["id"]==CORE_RUN and
          artifact["workflow_run"]["head_sha"]==CORE_SOURCE,"Wrong Core producer artifact: "+key)
 return dict(run=CORE_RUN,source=CORE_SOURCE,job=CORE_JOB,successfulSteps=sorted(found),
             artifacts=ARCHIVES,oldCoreReused=False,engineRecompiledForDelivery=False)

def core_run():
 from delivery_contract_memo import reuse
 return reuse("604-rpcs3-core",_query_core_run)

@lru_cache(maxsize=None)
def _archive(key):
 core_run()
 item=ARCHIVES[key]
 dest=ROOT/"build/runtime604-core"/(str(item["id"])+".zip")
 dest.parent.mkdir(parents=True,exist_ok=True)
 if not dest.is_file() or dest.stat().st_size!=item["bytes"] or "sha256:"+sha(dest.read_bytes())!=item["digest"]:
  with tempfile.NamedTemporaryFile(dir=dest.parent,delete=False) as stream:
   scratch=Path(stream.name)
   try: subprocess.run(["gh","api",f"repos/TarbleFR/RewindBox/actions/artifacts/{item['id']}/zip"],
                       stdout=stream,cwd=ROOT,check=True,timeout=600)
   except BaseException:
    scratch.unlink(missing_ok=True);raise
  try:
   require(scratch.stat().st_size==item["bytes"] and "sha256:"+sha(scratch.read_bytes())==item["digest"],
           "Core download archive digest mismatch")
   scratch.replace(dest)
  finally:scratch.unlink(missing_ok=True)
 return dest

def _input_paths():
 tree=ast.parse(compiled_source_bytes("test/neo_swap_core_pin_test.py"))
 for node in tree.body:
  if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=="CORE_INPUTS" for t in node.targets):
   paths=ast.literal_eval(node.value)
   require(isinstance(paths,tuple) and len(paths)==93 and len(set(paths))==92,"Wrong original compiler input path set")
   return set(paths)
 raise ValueError("Missing original compiler input path set")

def _check_reports(proof,record):
 with zipfile.ZipFile(_archive("diagnosticsArtifact")) as diagnostics:
  names=diagnostics.namelist()
  require(len(names)==len(set(names)) and diagnostics.testzip() is None,"Invalid diagnostics archive")
  require(sha(diagnostics.read("identity.json"))==IDENTITY_SHA256 and
          sha(diagnostics.read("runtime592-proof.json"))==PROOF_SHA256,"Core and diagnostics disagree")
  for job in record["apple_validation_jobs"]:
   item=proof["tests"][job["name"]]
   for field in ("report", "output", "compile_trace"):
    require(sha(diagnostics.read(item[field]))==item[field+"_sha256"],"Original Apple measurement changed")
   report=json.loads(diagnostics.read(item["report"]))
   for check in job["checks"]:
    value=report
    for key in check["path"]:value=value[key]
    require(type(value) is type(check["equals"]) and value==check["equals"],"Original Apple measurement failed")
   for member,digest in item.get("captured_input_sha256",{}).items():
    require(sha(diagnostics.read(member))==digest,"Reused Apple compiler capture changed")
 return True

def _validate_contract(identity,proof):
 manifest=json.loads(compiled_source_bytes(MANIFEST))
 record=json.loads(compiled_source_bytes(SOURCE_CONTRACT))
 require(sha(compiled_source_bytes(SOURCE_CONTRACT))==SOURCE_CONTRACT_SHA256 and
         manifest["device601_20261030"]==dict(source_contract=SOURCE_CONTRACT,source_contract_sha256=SOURCE_CONTRACT_SHA256),
         "Original source contract changed")
 require(identity["type"]==CORE_TYPE and identity["schema_version"]==1 and
         identity["host_commit"]==CORE_SOURCE and identity["native_source_commit"]==CORE_SOURCE and
         identity["source_commit"]==manifest["upstream_commit"] and
         identity["source_patch_sha256"]==PATCH_SHA256 and identity["sha256"]==CORE_SHA256 and
         identity["abi_version"]==30 and identity["architectures"]==["arm64"] and identity["codegen"]==CODEGEN,
         "Compiled Core identity mismatch")
 require(len(identity["exported_symbols"])==len(set(identity["exported_symbols"]))==88,
         "Compiled export manifest not ABI30/88")
 require(len(manifest["files_sha256"])==326 and
         manifest["files_sha256"]==identity["native_source_sha256"]==proof["native_source_sha256"] and
         sha(compiled_source_bytes(PATCH))==manifest["patch_sha256"]==record["canonical_patch_sha256"]==PATCH_SHA256,
         "Canonical source postimages or patch differ from compiled artifact")
 validation_inputs=proof["input_sha256"]
 expected_inputs=dict(record["repository_inputs"])
 for name in (SOURCE_CONTRACT,MANIFEST,PATCH):expected_inputs[name]=sha(compiled_source_bytes(name))
 require(validation_inputs==expected_inputs and len(validation_inputs)==41 and
         identity["device601_input_sha256"]==validation_inputs,"Validation source closure changed")
 core_inputs=identity["core_input_sha256"]
 require(set(core_inputs)==_input_paths(),"Compiler input closure changed")
 inputs=dict(validation_inputs)
 for name,digest in core_inputs.items():
  require(name not in inputs or inputs[name]==digest,"Compiler and validation sources disagree")
  inputs[name]=digest
 require(len(inputs)==126,"Wrong combined compiled source closure")
 for name,digest in inputs.items():
  require(sha(compiled_source_bytes(name))==digest,"Immutable Core source input differs: "+name)
 require(proof["schema"]==1 and proof["type"]=="device601_20261030" and proof["source"]==CORE_SOURCE and
         proof["source_patch_sha256"]==PATCH_SHA256 and proof["codegen"]==CODEGEN and
         proof["exported_symbols"]==identity["exported_symbols"] and proof["all_tests_passed"]is True and
         proof["host"]["system"]=="Darwin" and proof["host"]["machine"]=="arm64" and
         proof["host"]["compiler"]=="Homebrew clang version 22.1.8","Original Apple proof changed")
 require(all(item[field]is False for item in (identity,proof) for field in
             ("physical_device_tested","gameplay_measured","public_release","neoswap_host_component_packaged")),
         "Original proof scope changed")
 require(identity["native_modes_executed_now"]==proof["native_modes_executed_now"]==2 and
         identity["native_modes_reused"]==proof["native_modes_reused"]==10 and
         identity["native_reuse"]==proof["native_reuse"],"Current and historical native counts changed")
 reuse=proof["native_reuse"]
 require(reuse["source"]=="532ca40efc91730a6770db63879e9db759c7867d" and
         reuse["run"]==41113741373 and reuse["artifact"]==13005716946 and
         reuse["archive_sha256"]=="14bf88f0c5fb2698b82656932c174886b42778d55c562a38c17f5c1742a4bb74" and
         reuse["proof_sha256"]=="138526c6a87ba56a2c08302bcd87d0949776989e877e3274d7289c1fbd67e07c" and
         set(reuse["reused_native_modes"])==REUSED and set(reuse["new_native_modes"])==FRESH and
         reuse["old_core_built"]is False and reuse["previous_build_failed_at_ios_syntax"]is True and
         reuse["compiler_identity_equal"]is True and reuse["current_programs_equal"]is True and
         reuse["unchanged_modes_replayed"]is False and reuse["historical_378_modes_replayed"]is False,
         "Reused Apple modes lost original scope")
 historical=proof["historical"]
 require(historical["source"]=="378509e82d360bc2cb2fcc9fb23d4d9d98787506" and
         historical["run"]==41033511090 and historical["original_native_modes"]==28 and
         historical["native_executed_now"]==0 and historical["archives_authenticated"]is True and
         historical["validates_new_paths"]is False and historical["old_binary_reused"]is False,
         "Historical Apple validation scope changed")
 require(set(proof["tests"])=={j["name"] for j in record["apple_validation_jobs"]}==FRESH|REUSED,
         "Incorrect Apple test coverage")
 for job in record["apple_validation_jobs"]:
  name=job["name"];item=proof["tests"][name]
  require(item["passed"]is True and item["mode"]==job["mode"] and
          item["native_executed_now"]is (name in FRESH),"Apple mode relabeled or failed")
  if name in REUSED:
   require(item["reused_from"]==dict(source=reuse["source"],run=reuse["run"],artifact=reuse["artifact"]) and
           item["current_relevance"]["compiler_executed"]is False and
           item["current_relevance"]["native_executed"]is False,"Reused mode has incorrect provenance")
 return manifest,inputs,identity,proof

@lru_cache(maxsize=1)
def _core_contract():
 configuration()
 with zipfile.ZipFile(_archive("artifact")) as archive:
  require(archive.testzip() is None,"Invalid Core archive CRC")
  require(set(archive.namelist())==set(CORE_FILES) and len(archive.namelist())==len(CORE_FILES),
          "Missing or duplicate immutable Core artifact members")
  rawid=archive.read("identity.json");rawproof=archive.read("runtime592-proof.json")
 require(sha(rawid)==IDENTITY_SHA256 and sha(rawproof)==PROOF_SHA256,
         "Original Apple Core identity or proof changed")
 result=_validate_contract(json.loads(rawid),json.loads(rawproof))
 _check_reports(result[3],json.loads(compiled_source_bytes(SOURCE_CONTRACT)))
 return result

@lru_cache(maxsize=1)
def compatibility():
 manifest,inputs,identity,proof=_core_contract()
 bridge=ROOT/"packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm"
 m=re.search(r"\bkExpectedAbi\s*=\s*(\d+)\s*;",bridge.read_text())
 require(m is not None and int(m.group(1))==identity["abi_version"]==30,"Host/Core ABI differs")
 pairs=[("packages/neo_swap/ios/Classes/"+n,"rpcs3/ios/"+n,True)
        for n in ("NeoSwap.h","NeoSwapCompilerAPI.h","NeoSwapClientStats.h","NeoSwapRelay.h")]
 pairs.append(("native/neoswap/NeoSwapClient.h","rpcs3/ios/NeoSwapClient.h",True))
 pairs.extend(("native/neoswap-storage/"+n,"rpcs3/ios/NeoSwapStorage/"+n,False)
               for n in ("StorageABI.h","Client.h","ShaderKey.h","SourceABI.h","SourceClient.h",
                         "SourceClient.cpp","FrameClient.h","VideoBuffer.h"))
 headers={}
 for host,source,normalize in pairs:
  data=(ROOT/host).read_bytes()
  if normalize:data=data.replace(b"\r\n",b"\n")
  require(sha(data)==manifest["files_sha256"][source],"Compiled Core host ABI boundary changed: "+host)
  headers[host]=sha(data)
 require(sha((ROOT/HOST_STORE).read_bytes())==HOST_STORE_SHA256,
         "Reviewed NeoSwap Store host source drift")
 from rewind606_baseline import reviewed_routing, BASE, original
 routing=reviewed_routing()
 for path,change in routing.items():
  require(sha(compiled_source_bytes(path))==change["before"]==sha(original(BASE,path)),
          "RPCS3 journal exception does not begin at the exact compiled host source: "+path)
  require(sha((ROOT/path).read_bytes())==change["after"],"Unreviewed RPCS3 journal source: "+path)
 return dict(abiVersion=30,hostCoreHeadersSHA256=headers,hostLoggerSHA256=sha((ROOT/HOST_LOGGER).read_bytes()),
             neoswapStoreSHA256=HOST_STORE_SHA256,brokerCompiledIntoHostOnly=True,
             reviewedHostJournalRouting=routing,coreModified=False,
             physicalDeviceTested=False)

@lru_cache(maxsize=1)
def _bundle():
 manifest,inputs,identity,proof=_core_contract()
 compatibility()
 with zipfile.ZipFile(_archive("artifact")) as archive:
  data={n:archive.read(n) for n in CORE_FILES}
 raw=data["libRPCS3Core.dylib"]
 require(len(raw)==PIN["coreBytes"] and sha(raw)==CORE_SHA256 and
         data["libRPCS3Core.dylib.sha256"].decode().split()[0]==CORE_SHA256 and
         data["RPCS3_SOURCE_COMMIT.txt"].decode().strip()==manifest["upstream_commit"] and
         data["RPCS3_IOS_ABI.txt"].decode().strip()=="30","Original Core binary/metadata bytes changed")
 validate_core(raw)
 image=macho(raw)
 require(image["platform"]==2 and image["fileType"]==6 and image["id"]==CORE_ID and
         set(image["definedSymbols"])==set(identity["exported_symbols"]) and
         len(image["definedSymbols"])==88,
         "Core architecture, platform, ABI or symbols differ from Apple producer")
 for marker in CORE_MARKERS:
  require(marker in raw,"Original core runtime marker not present: "+repr(marker))
 return dict(identity=identity,proof=proof,files=data,raw=raw,fingerprint=payload_fingerprint(raw),
             tested=sorted(proof["tests"]))

def changed_core_paths():
 record=json.loads(compiled_source_bytes(SOURCE_CONTRACT))
 require(len(record["native_changes"])==8,"Expected exactly the reviewed eight Core source paths")
 return sorted(record["native_changes"])

def validate_rpc_core_identity(identity):
 require(identity==_bundle()["identity"],"Core identity not original verified Apple binary")

def validate_rpc_core_pin(source,paths):
 require(source==CORE_SOURCE,"Wrong Core producer source")
 _,inputs,_,_=_core_contract()
 require(bool(paths) and set(paths)<=set(inputs),"Unrecognized Core input paths")

def core_receipt():
 manifest,inputs,identity,proof=_core_contract()
 bundle=_bundle()
 return dict(baselineDelivery=605,type=CORE_TYPE,coreSource=CORE_SOURCE,
             coreNativeSource=CORE_SOURCE,coreRun=CORE_RUN,coreSHA256=CORE_SHA256,
             corePayloadFingerprint=bundle["fingerprint"],identitySHA256=IDENTITY_SHA256,
             proofSHA256=PROOF_SHA256,**ARCHIVES,sourcePatchSHA256=PATCH_SHA256,codegen=CODEGEN,
             changedPaths=changed_core_paths(),canonicalPostimages=326,coreInputCount=92,validationInputCount=41,compiledInputCount=126,
             tests=bundle["tested"],appleModes=dict(executedInOriginalProducer=2,reusedExactAppleModesInOriginalProducer=10,historicalNativeModes=28,sourceAuditInOriginalProducer=1,executedForDelivery=0,historicalReplayed=False),
             nativeReuse=proof["native_reuse"],
             inputs=inputs,compatibility=compatibility(),
             sourceReceipt=dict(commit=CORE_SOURCE,artifact=ARCHIVES["artifact"]["id"],member="runtime592-proof.json",
                                sha256=PROOF_SHA256),
             historicalTestsReplayed=False,candidateTestsReplayed=False,
             compiledSourceInputsAreHistorical=True,currentRpcCandidateCompiled=True,coreRecompiledForDelivery=False,
             hostRuntime=dict(path=HOST_STORE,sha256=HOST_STORE_SHA256,compiledIntoHostOnly=True,testsReplayed=False),
             physicalDeviceTested=False,gameplayMeasured=False,fpsGainMeasured=False)

def validate_core_identity(core_data,identity_path,expected_host_commit):
 require(expected_host_commit==CORE_SOURCE,"Wrong Core delivery source/run")
 require(Path(identity_path).read_bytes()==_bundle()["files"]["identity.json"],"Core identity rewritten")
 from validate_rpcs3_core604_ipa import compare_core
 compare_core(core_data,_bundle()["raw"],signed=False)
 return _bundle()["identity"]

def download_core(destination=None):
 directory=Path(destination) if destination else ROOT/"dist/rpcs3-native"
 directory.mkdir(parents=True,exist_ok=True)
 for name,data in _bundle()["files"].items():
  (directory/name).write_bytes(data)
 (directory/"libRPCS3Core.dylib").chmod(0o755)
 return dict(destination=str(directory),**core_receipt())

def raw_core():return _bundle()["raw"]

def embed_compiled_source(app):
 manifest,inputs,identity,proof=_core_contract()
 folder=Path(app)/"Legal/RPCS3-current-core"
 folder.mkdir(parents=True,exist_ok=True)
 buffer=io.BytesIO()
 with zipfile.ZipFile(buffer,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
  for path,digest in sorted(inputs.items()):
   original=compiled_source_bytes(path)
   require(sha(original)==digest,"Original compiled source changed: "+path)
   archive.writestr(path,original)
 raw=buffer.getvalue()
 (folder/"compiled-host-inputs.zip").write_bytes(raw)
 report=dict(coreSource=CORE_SOURCE,coreRun=CORE_RUN,coreSHA256=CORE_SHA256,
             sourcePatchSHA256=PATCH_SHA256,compiledInputCount=len(inputs),
             inputs=inputs,compiledInputsZipSHA256=sha(raw),
             currentBranchRpcCandidateCompiled=True,coreRecompiledForDelivery=False,
             upstreamRepository="https://github.com/XITRIX/rpcs3",upstreamCommit=manifest["upstream_commit"],
             correspondingPatchMember=PATCH,actualCoreIncludesDevice597Fixes=True,actualCoreIncludesDevice601Followup=True)
 (folder/"actual-compiled-source.json").write_text(json.dumps(report,indent=2)+"\n")
 return report

if __name__=="__main__":
 parser=argparse.ArgumentParser()
 parser.add_argument("--embed-source",type=Path)
 args=parser.parse_args()
 require(args.embed_source is not None,"Missing --embed-source")
 print(json.dumps(embed_compiled_source(args.embed_source),indent=2))
