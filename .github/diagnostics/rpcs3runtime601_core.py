"""Authenticate and reuse the verified device597 RPCS3 iPhone Core for private IPA601.

The immutable Core archive is built on Apple ARM64 in run 41033511090.
All 28 fresh Apple native modes, codegen audit, ABI 30 and 88 exports are
read from its original proof, not replayed or relabelled in this delivery.
"""
from functools import lru_cache
from pathlib import Path
import argparse, hashlib, io, json, re, subprocess, sys, tempfile, zipfile

ROOT=Path(__file__).resolve().parents[2]
for part in ("build-utils","packages/dolphin_internal_bridge/ci","test"):
    sys.path.insert(0,str(ROOT/part))
from delivery_benchmark import payload_fingerprint
from verify_ipa import macho
from validate_rpcs3_embedded_core import validate_core

DELIVERY_BASELINE=600
CORE_SOURCE="378509e82d360bc2cb2fcc9fb23d4d9d98787506"
CORE_NATIVE_SOURCE=CORE_SOURCE
CORE_RUN=41033511090
CORE_JOB=123988660858
CORE_ID="@rpath/libRPCS3Core.dylib"
CORE_TYPE="rpcs3-ios-device597-source-candidate"
CORE_WORKFLOW=".github/workflows/rpcs3-runtime592-core.yml"
CORE_SHA256="973f59bf02a1c51989dc880aefb8d4be8c4df6c27c2f1f1a63c240b7341d2bf8"
IDENTITY_SHA256="67fd2e23d0e4c7ba816b7f7dbaabad3c884a324d9b309d5b854d49561231f55e"
PROOF_SHA256="efd54d52f585f1f8144a7b328442c5e2164928a6f7b02170e0de38f90ff3b671"
PATCH_SHA256="68234e0ead31d40c61c2b3b29c0c962f89d8687407e0cc60eb45d60b68dd71e8"
SOURCE_CONTRACT_SHA256="b4bd7cba3f3175c48d5ce2b33638e234b07380e4c4f8b2b23fdca2966c750d14"
CODEGEN={"PPU":"a987639e9f838d1c","SPU":"477a3fa442d27917"}
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
ARCHIVES={
 "artifact":dict(id=12968555534,name="RPCS3Core-"+CORE_SOURCE,bytes=29273074,digest="sha256:7d3b26e3d6709855997ebb9e20c737b2839a8aff72eb7edae78c2f7c5f0d7099"),
 "diagnosticsArtifact":dict(id=12968066519,name="RPCS3Core-diagnostics-"+CORE_SOURCE,bytes=122845035,digest="sha256:d5673b00f33020bdb2f222a85d9a5ea37e248485024dcd8074274f6e0e867341"),
 "preflightArtifact":dict(id=12967426340,name="RPCS3Core-preflight-"+CORE_SOURCE,bytes=141846,digest="sha256:b5a1cd09b5da5d3b0ac6cd69c50f5ff7324da6476c6f61a7683a28c5f2a0ea56"),
}

def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def configuration():
 return dict(run=dict(id=CORE_RUN,run_attempt=1),coreSHA256=CORE_SHA256,
             identitySHA256=IDENTITY_SHA256,proofSHA256=PROOF_SHA256,
             sourcePatchSHA256=PATCH_SHA256,core=dict(bytes=77392480),
             inputCount=209,coreInputCount=92,nativePostimageCount=325,
             codegen=CODEGEN,**ARCHIVES)
def api(endpoint):
 return json.loads(subprocess.check_output(["gh","api","repos/TarbleFR/RewindBox/"+endpoint],cwd=ROOT,timeout=120))
@lru_cache(maxsize=256)
def compiled_source_bytes(path):
 require(not Path(path).is_absolute() and ".." not in Path(path).parts,"Invalid compiled source path")
 return subprocess.check_output(["git","show",CORE_SOURCE+":"+path],cwd=ROOT,timeout=60)

def _query_core_run():
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
 return reuse("601-rpcs3-core",_query_core_run)

@lru_cache(maxsize=None)
def _archive(key):
 core_run()
 item=ARCHIVES[key]
 dest=ROOT/"build/runtime601-core"/(str(item["id"])+".zip")
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

@lru_cache(maxsize=1)
def _core_contract():
 with zipfile.ZipFile(_archive("artifact")) as archive:
  require(archive.testzip() is None,"Invalid Core archive CRC")
  require(set(archive.namelist())==set(CORE_FILES) and len(archive.namelist())==len(CORE_FILES),
          "Missing or duplicate immutable Core artifact members")
  rawid=archive.read("identity.json");rawproof=archive.read("runtime592-proof.json")
 require(sha(rawid)==IDENTITY_SHA256 and sha(rawproof)==PROOF_SHA256,
         "Original Apple Core identity or proof changed")
 identity=json.loads(rawid);proof=json.loads(rawproof)
 manifest=json.loads(compiled_source_bytes(MANIFEST))
 require(identity["type"]==CORE_TYPE and identity["schema_version"]==1 and
         identity["host_commit"]==CORE_SOURCE and identity["native_source_commit"]==CORE_SOURCE and
         identity["source_commit"]==manifest["upstream_commit"] and
         identity["source_patch_sha256"]==PATCH_SHA256 and identity["sha256"]==CORE_SHA256 and
         identity["abi_version"]==30 and identity["architectures"]==["arm64"] and identity["codegen"]==CODEGEN,
         "Compiled Core identity mismatch")
 require(len(identity["exported_symbols"])==len(set(identity["exported_symbols"]))==88,
         "Compiled export manifest not ABI30/88")
 require(len(manifest["files_sha256"])==325 and
         manifest["files_sha256"]==identity["native_source_sha256"]==proof["native_source_sha256"] and
         sha(compiled_source_bytes(PATCH))==manifest["patch_sha256"]==PATCH_SHA256,
         "Canonical reviewed source patch or postimages do not match compiled artifact")
 inputs=proof["input_sha256"]
 require(len(inputs)==209 and identity["device597_input_sha256"]==inputs and
         len(identity["core_input_sha256"])==92 and
         all(inputs.get(k)==v for k,v in identity["core_input_sha256"].items()),
         "Original compiler/repository inputs changed")
 for name,digest in inputs.items():
  require(sha(compiled_source_bytes(name))==digest,"Immutable Core source input differs: "+name)
 require(proof["type"]=="rpcs3-device597-20261030" and proof["source"]==CORE_SOURCE and
         proof["source_patch_sha256"]==PATCH_SHA256 and
         proof["source_contract_sha256"]==SOURCE_CONTRACT_SHA256 and proof["codegen"]==CODEGEN and
         proof["exported_symbols"]==identity["exported_symbols"] and proof["all_tests_passed"]is True and
         proof["host"]["system"]=="Darwin" and proof["host"]["machine"]=="arm64" and
         "22." in proof["host"]["compiler"],"Original Apple proof changed")
 required_jobs=manifest["device597_20261030"]["apple_validation"]["jobs"]
 require(len(required_jobs)==29 and set(proof["tests"])=={j["name"] for j in required_jobs},
         "Incorrect Apple test coverage")
 for j in required_jobs:
  test=proof["tests"][j["name"]]
  require(test["passed"]is True and test["kind"]==j.get("kind","native") and
          test["native_executed_now"]is (j.get("kind","native")=="native"),
          "Apple test missing its original executed scope")
 require(sum(v["native_executed_now"] for v in proof["tests"].values())==28,
         "Missing one of 28 required Apple native modes")
 receipt=ROOT/"docs/evidence/rpcs3-device597-20261030/apple-core.json"
 source_receipt=json.loads(receipt.read_bytes())
 require(source_receipt["conclusion"]=="success" and source_receipt["run"]==CORE_RUN and
         source_receipt["job"]==CORE_JOB and source_receipt["source"]==CORE_SOURCE and
         source_receipt["canonicalPatchSHA256"]==PATCH_SHA256 and
         source_receipt["core"]["sha256"]==CORE_SHA256 and
         source_receipt["core"]["identitySHA256"]==IDENTITY_SHA256 and
         source_receipt["core"]["proofSHA256"]==PROOF_SHA256 and
         source_receipt["validation"]["freshAppleNativeModes"]==28 and
         source_receipt["validation"]["allPassed"]is True,
         "Independent recorded Apple delivery receipt differs")
 return manifest,inputs,identity,proof

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
 require(sha((ROOT/HOST_LOGGER).read_bytes())==sha(compiled_source_bytes(HOST_LOGGER)),
         "New RPCS3 causes logger differs from reviewed Core host source")
 return dict(abiVersion=30,hostCoreHeadersSHA256=headers,hostLoggerSHA256=sha((ROOT/HOST_LOGGER).read_bytes()),
             neoswapStoreSHA256=HOST_STORE_SHA256,brokerCompiledIntoHostOnly=True,
             physicalDeviceTested=False)

@lru_cache(maxsize=1)
def _bundle():
 manifest,inputs,identity,proof=_core_contract()
 compatibility()
 with zipfile.ZipFile(_archive("artifact")) as archive:
  data={n:archive.read(n) for n in CORE_FILES}
 raw=data["libRPCS3Core.dylib"]
 require(len(raw)==77392480 and sha(raw)==CORE_SHA256 and
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
    delta=compiled_source_bytes("test/rpcs3_device597/core-delta.patch")
    paths=re.findall(rb"^diff --git a/(\S+) b/\1\r?$",delta,re.MULTILINE)
    require(len(paths)==20 and len(set(paths))==20,"Expected exactly the reviewed 20 Core source paths")
    return sorted(path.decode("utf8") for path in paths)

def validate_rpc_core_identity(identity):
 require(identity==_bundle()["identity"],"Core identity not original verified Apple binary")

def validate_rpc_core_pin(source,paths):
 require(source==CORE_SOURCE,"Wrong Core producer source")
 _,inputs,_,_=_core_contract()
 require(bool(paths) and set(paths)<=set(inputs),"Unrecognized Core input paths")

def core_receipt():
 manifest,inputs,identity,proof=_core_contract()
 bundle=_bundle()
 return dict(baselineDelivery=600,type=CORE_TYPE,coreSource=CORE_SOURCE,
             coreNativeSource=CORE_SOURCE,coreRun=CORE_RUN,coreSHA256=CORE_SHA256,
             corePayloadFingerprint=bundle["fingerprint"],identitySHA256=IDENTITY_SHA256,
             proofSHA256=PROOF_SHA256,**ARCHIVES,sourcePatchSHA256=PATCH_SHA256,codegen=CODEGEN,
             changedPaths=changed_core_paths(),canonicalPostimages=325,coreInputCount=92,validationInputCount=209,
             tests=bundle["tested"],appleModes=dict(executedNow=28,sourceAudit=1,historicalReplayed=False),
             inputs=inputs,compatibility=compatibility(),
             sourceReceipt=dict(commit=CORE_SOURCE,artifact=ARCHIVES["artifact"]["id"],member="runtime592-proof.json",
                                sha256=PROOF_SHA256),
             historicalTestsReplayed=False,candidateTestsReplayed=False,
             compiledSourceInputsAreHistorical=True,currentRpcCandidateCompiled=True,
             hostRuntime=dict(path=HOST_STORE,sha256=HOST_STORE_SHA256,compiledIntoHostOnly=True,testsReplayed=False),
             physicalDeviceTested=False,gameplayMeasured=False,fpsGainMeasured=False)

def validate_core_identity(core_data,identity_path,expected_host_commit):
 require(expected_host_commit==CORE_SOURCE,"Wrong Core delivery source/run")
 require(Path(identity_path).read_bytes()==_bundle()["files"]["identity.json"],"Core identity rewritten")
 from validate_rpcs3_core601_ipa import compare_core
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
             currentBranchRpcCandidateCompiled=True,
             upstreamRepository="https://github.com/XITRIX/rpcs3",upstreamCommit=manifest["upstream_commit"],
             correspondingPatchMember=PATCH,actualCoreIncludesDevice597Fixes=True)
 (folder/"actual-compiled-source.json").write_text(json.dumps(report,indent=2)+"\n")
 return report

if __name__=="__main__":
 parser=argparse.ArgumentParser()
 parser.add_argument("--embed-source",type=Path)
 args=parser.parse_args()
 require(args.embed_source is not None,"Missing --embed-source")
 print(json.dumps(embed_compiled_source(args.embed_source),indent=2))
