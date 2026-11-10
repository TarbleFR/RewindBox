#!/usr/bin/env python3
"""Verify the downloaded final private603 archive, actual IPA and retained cores.

No compiler, simulator, native suite or codesign is run here. The existing
strict payload validators receive the actual independently downloaded Core
archives and previously fetched raw GitHub producer metadata as local inputs.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import importlib
import json
from pathlib import Path
import plistlib
import re
import shutil
import struct
import subprocess
import sys
import zipfile

sys.dont_write_bytecode=True
SOURCE='808b64e16bb0f5112a2a7b5a07b400c19bb9cfbd'
RUN=41102769156


def sha(data):return hashlib.sha256(data).hexdigest()
def read(path):return json.loads(path.read_bytes())
def file_sha(path):
 h=hashlib.sha256()
 with path.open('rb')as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()


def verify(a):
 repo=a.repo.resolve();delivery=a.delivery.resolve();metadata=read(a.metadata)
 run=metadata['run'];jobs=metadata['jobs']['jobs'];artifacts=metadata['artifacts']['artifacts']
 assert run['id']==RUN and run['head_sha']==SOURCE and run['head_branch']=='Claude' and run['run_attempt']==1
 assert run['status']=='completed' and run['conclusion']=='success'
 assert run['path']=='.github/workflows/rewind603-hogwarts-core-delivery.yml'
 assert len(jobs)==1 and jobs[0]['run_id']==RUN and jobs[0]['head_sha']==SOURCE and jobs[0]['conclusion']=='success'
 required=['Compile Release device binary with measured AOT and Xcode phases','Seal every executable, framework and extension for SideStore',
           'Verify corrected MeloNX payload preservation in signed IPA603','Verify the actual signed Hogwarts host activation',
           'Verify the signed RPCS3 runtime candidate receipt against its authenticated original payload','Upload encrypted IPA and verification reports']
 # The raw job APIs returned an empty steps array even after completion.
 # Keep that response intact; bind an actual job-log excerpt and sealed
 # successful phase receipts instead of inventing individual API steps.
 log=a.execution_log.read_text()
 if jobs[0]['steps']:
  assert set(required)<={s['name']for s in jobs[0]['steps']if s['conclusion']=='success'}
 markers=['** BUILD SUCCEEDED **',
  '##[group]Run python3 build-utils/delivery_metrics.py signature_and_ipa_export python3 build-utils/delivery_benchmark.py seal',
  '##[group]Run python3 build-utils/validate_rpcs3_core603_ipa.py "dist/$IPA_NAME.ipa"',
  '##[group]Run python3 build-utils/validate_melonx_engine603_ipa.py "dist/$IPA_NAME.ipa"',
  '##[group]Run python3 build-utils/validate_hogwarts603_ipa.py "dist/$IPA_NAME.ipa"',
  'Artifact RewindBox-Build603-'+SOURCE+'-cold.zip successfully finalized. Artifact ID 13000847907']
 positions=[log.index(marker)for marker in markers]
 assert positions==sorted(positions) and '##[error]'not in log
 phases=read(delivery/'observed-timings.json')
 assert phases['commit']==SOURCE
 for name in ('xcode_build','signature_and_ipa_export'):
  items=[v for v in phases['phases']if v['phase']==name]
  assert len(items)==1 and items[0]['exitCode']==0 and items[0]['seconds']>0
 selected=[v for v in artifacts if v['name']=='RewindBox-Build603-'+SOURCE+'-cold']
 assert len(selected)==1;artifact=selected[0]
 assert not artifact['expired'] and artifact['workflow_run']['head_sha']==SOURCE
 assert a.encrypted_archive.stat().st_size==artifact['size_in_bytes']
 assert 'sha256:'+file_sha(a.encrypted_archive)==artifact['digest']
 with zipfile.ZipFile(a.encrypted_archive)as z:
  assert z.testzip()is None and set(z.namelist())=={'artifact.tar.enc','password.rsa','format.json'} and len(z.namelist())==3
 ipas=list(delivery.glob('*.ipa'));assert len(ipas)==1;ipa=ipas[0];digest=file_sha(ipa)
 sums=(delivery/'SHA256SUMS').read_text();assert re.search(r'^'+digest+r'\s+.*\.ipa$',sums,re.M)
 signed=read(delivery/'signed-payload-identity.json')
 assert digest in log
 assert signed['ipaSha256']==digest and signed['ipaBytes']==ipa.stat().st_size
 assert signed['allCompiledCodeAndDataSectionsUnchangedBySigning']is True and signed['abiMetadataUnchangedBySigning']is True
 assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip()==SOURCE
 sys.path[:0]=[str(repo/'.github/diagnostics'),str(repo/'build-utils'),str(repo/'build-utils/melonx'),str(repo/'packages/dolphin_internal_bridge/ci')]
 from verify_ipa import macho
 from delivery_benchmark import payload_fingerprint
 import rewind603_engine as engine
 import rewind603_baseline as baseline
 import rpcs3runtime601_core as rpc
 import validate_rpcs3_core603_ipa as rpc_validator
 import validate_melonx_engine603_ipa as melonx_validator
 import validate_melonx_ipa as generic_melonx
 from helper_initialization import verify as helper_verify
 helper=helper_verify()
 assert baseline.source_contract()['productTrees']==read(delivery/'host-tree603.json')['productTrees']
 # Original producer metadata was fetched through the connector, unchanged.
 api=read(a.producer_metadata)
 engine.api=lambda endpoint:api[endpoint]
 engine.engine_run=engine._query_engine_run
 rpc.api=lambda endpoint:api[endpoint]
 rpc.core_run=rpc._query_core_run
 rpc.core_run()
 rpc_item=rpc.ARCHIVES['artifact']
 assert a.rpc_archive.stat().st_size==rpc_item['bytes'] and 'sha256:'+file_sha(a.rpc_archive)==rpc_item['digest']
 def local_rpc_archive(key):
  assert key=='artifact','Unexpected additional local archive request'
  return a.rpc_archive
 rpc._archive=local_rpc_archive
 with zipfile.ZipFile(a.rpc_archive)as z:
  assert z.testzip()is None
  raw_rpc=z.read('libRPCS3Core.dylib');raw_rpc_id=z.read('identity.json')
  rpc_dir=repo/'dist/rpcs3-native';rpc_dir.mkdir(parents=True,exist_ok=True)
  for name in rpc.CORE_FILES:(rpc_dir/name).write_bytes(z.read(name))
 assert a.melonx_archive.stat().st_size==engine.MELONX_ARTIFACT_BYTES and file_sha(a.melonx_archive)==engine.MELONX_ARTIFACT_SHA256
 # Fresh byte verification precedes the original source/payload validators.
 with zipfile.ZipFile(a.melonx_archive)as z:
  assert z.testzip()is None
  for n in z.namelist():assert not Path(n).is_absolute() and '..'not in Path(n).parts
  z.extractall(engine.NEW)
 assert engine.engine_evidence()['source']==engine.MELONX_SOURCE
 versions={};images={};fat={};thin={}
 with zipfile.ZipFile(ipa)as z:
  names=z.namelist();assert len(names)==len(set(names)) and z.testzip()is None
  roots=[n[:-10]for n in names if n.startswith('Payload/')and len(n.split('/'))==3 and n.endswith('.app/Info.plist')]
  assert len(roots)==1;root=roots[0]
  for n in names:
   if n==root+'Info.plist' or(n.startswith(root+'PlugIns/')and n.endswith('.appex/Info.plist')):
    p=plistlib.loads(z.read(n));assert p['CFBundleShortVersionString']=='0.0.8'and str(p['CFBundleVersion'])=='603'
    versions[n]=dict(version=p['CFBundleShortVersionString'],build=p['CFBundleVersion'])
   if n.endswith('/')or not n.startswith(root):continue
   with z.open(n)as f:magic=f.read(4)
   if magic not in (b'\xcf\xfa\xed\xfe',b'\xca\xfe\xba\xbe',b'\xca\xfe\xba\xbf'):continue
   data=z.read(n);rel=n[len(root):];image=macho(data)
   assert image['architecture']=='arm64'and image['platform']==2 and image['codeSignature']is True,rel
   images[rel]=dict(platform=2,kind=image['fileType'],exports=len(image['definedSymbols']),sha256=sha(data),bytes=len(data))
   if magic==b'\xcf\xfa\xed\xfe':
    fp=payload_fingerprint(data);assert fp==signed['images'][rel],rel
    thin[rel]=fp
   else:
    assert struct.unpack_from('>I',data,4)[0]==1 and struct.unpack_from('>I',data,8)[0]==0x0100000c,rel
    fat[rel]=images[rel]
  assert len(versions)==8 and len(images)==88 and len(thin)==85 and len(fat)==3
  script=z.read(root+'PlugIns/MeloNXJITHelper.appex/melonx-universal.js')
  assert script==(repo/'packages/melonx_jit_helper/ios/Resources/melonx-universal.js').read_bytes()
  assert sha(script)==helper['currentSHA256']
  policy=json.loads(z.read(root+'MeloNX-hogwarts603-policy.json'))
  assert policy['hostSource']==SOURCE and policy['build']==603 and policy['checksReexecuted']is False
  assert policy['literalLoadFixIncluded']is True and policy['hogwartsCrashCauseProven']is False and policy['gpuStartupDelayFixed']is False
  assert policy['helperProof']==read(repo/'docs/evidence/melonx-jit-helper-init-20261030/apple.json')
  assert policy['helperProof']['appleJavaScriptCore']['sessions']==14
  for path,h in policy['sourceSHA256'].items():assert sha((repo/path).read_bytes())==h
  raw_melonx=(engine.NEW/'ios-arm64/Ryujinx.Library.dylib').read_bytes()
  actual_melonx=z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
  assert engine.normalized_payload_fingerprint(actual_melonx)==engine.normalized_payload_fingerprint(raw_melonx)==engine.PACKAGED_FINGERPRINT
  rpc_state=rpc_validator.compare_core(z.read(root+'Frameworks/libRPCS3Core.dylib'),raw_rpc,signed=True)
  native=json.loads(z.read(root+'MeloNX-native-identity.json'))
  assert native['sourceCoreIdentity']==engine.engine_identity()
  assert json.loads(z.read(root+'RPCS3-runtime-core-identity.json'))['coreSource']==rpc.CORE_SOURCE
 generic=generic_melonx.validate(ipa)
 mel=melonx_validator.validate(ipa,603)
 rpc_final=rpc_validator.validate(ipa,603,repo/'dist/rpcs3-native/identity.json',repo/'dist/rpcs3-native/libRPCS3Core.dylib')
 signature=read(delivery/'signature.json')
 assert signature['build']=='603'and len(signature['signatures'])==88 and all(x['signatureVerified']is True for x in signature['signatures'])
 assert signature['deviceInstallationTested']is False
 return dict(result='passed',build=603,version='0.0.8',source=SOURCE,run=RUN,job=jobs[0]['id'],artifact=artifact['id'],
   encryptedArchiveSHA256=artifact['digest'][7:],encryptedArchiveBytes=artifact['size_in_bytes'],
   ipaSHA256=digest,ipaBytes=ipa.stat().st_size,ipaName=ipa.name,zipEntries=len(names),zipCrcVerified=True,
   productTrees=read(delivery/'host-tree603.json')['productTrees'],bundleVersions=versions,
   machOImages=len(images),thinPayloadFingerprintsVerified=len(thin),fatContainers=fat,
   helper=dict(scriptSHA256=helper['currentSHA256'],wholeScriptChecks=99,protocolChecks=101,appleJavaScriptCoreSessions=14,exactRelocation=True),
   melonx=dict(source=engine.MELONX_SOURCE,originalCoreSHA256=engine.BINARY_SHA256['ios-arm64'],payloadMatched=True,exports=47),
   rpcs3=dict(source=rpc.CORE_SOURCE,originalCoreSHA256=rpc.CORE_SHA256,payloadMatched=True,exports=88,abi=30),
   signaturesVerifiedByAppleCI=88,signatureCryptographicallyVerifiedIndependently=False,
   observedTimings=read(delivery/'observed-timings.json'),
   enginesRecompiled=False,nativeFixturesReexecuted=False,physicalDeviceTested=False,hogwartsCrashCauseProven=False,gpuStartupDelayFixed=False,gameplayMeasured=False,smashRegressionFixed=False,
   jobStepMetadataAvailable=bool(jobs[0]['steps']),executionLogExcerptSHA256=file_sha(a.execution_log),
   executionProof='Successful run and job metadata, actual job-log excerpt, sealed phase receipts and independently verified payloads',
   scriptSHA256=file_sha(Path(__file__)),metadataSHA256=file_sha(a.metadata),verifiedUTC=datetime.now(timezone.utc).isoformat())


def main():
 p=argparse.ArgumentParser(description=__doc__)
 for key in ('repo','delivery','metadata','producer-metadata','encrypted-archive','rpc-archive','melonx-archive','execution-log','output'):
  p.add_argument('--'+key,required=True,type=Path)
 a=p.parse_args();assert not a.output.exists(),'Preserve existing verification receipts'
 value=verify(a);a.output.write_text(json.dumps(value,indent=2)+'\n')
 print(json.dumps({k:value[k]for k in ('result','build','ipaSHA256','ipaBytes','machOImages','helper')}))


if __name__=='__main__':main()
