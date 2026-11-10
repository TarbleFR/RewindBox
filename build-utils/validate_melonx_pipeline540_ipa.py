"""Bind pipeline regression proofs and actual compiled source to private IPA540."""
import argparse,hashlib,json,subprocess,zipfile
from pathlib import Path
import validate_melonx_graphics539_ipa as journal
from melonxpipeline540_delivery import MELONX_SOURCE,MELONX_RUN

ROOT=Path(__file__).resolve().parents[1]
IDENTITY='MeloNX-pipeline540-identity.json'
ADAPTER='build-utils/melonx/adapt_pipeline.py'
PREPARE='build-utils/melonx/prepare_embedded.py'
# Reuse prior feature validators with the new source-built engine. Their source
# input comparisons and old host/audio assertions remain active.
journal.MELONX_SOURCE=MELONX_SOURCE
journal.MELONX_RUN=MELONX_RUN
journal.previous.proof.MELONX_SOURCE=MELONX_SOURCE
journal.previous.proof.MELONX_RUN=MELONX_RUN
journal.previous.retained.proof.MELONX_SOURCE=MELONX_SOURCE
journal.previous.retained.proof.MELONX_RUN=MELONX_RUN

def expected():
 receipt=json.loads((ROOT/'dist/melonx/pipeline-failure-checks.json').read_bytes())
 assert receipt['result']=='passed' and receipt['vulkanDouble'] and not receipt['physicalDeviceTested']
 assert [r['mode'] for r in receipt['reports']]==['control','fixed']
 assert all(r['passed'] and r['checks']==29 for r in receipt['reports'])
 assert receipt['reports'][0]['reproducedPoisonedProgram'] and not receipt['reports'][1]['reproducedPoisonedProgram']
 for p,h in receipt['inputs'].items():
  assert hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h,p
  assert (ROOT/p).read_bytes()==subprocess.check_output(['git','show',MELONX_SOURCE+':'+p],cwd=ROOT),p
 with zipfile.ZipFile(ROOT/'dist/melonx/embedded-adapted-source.zip') as z:
  shaders=z.read('src/Ryujinx.Graphics.Vulkan/ShaderCollection.cs').decode('utf-8-sig')
  assert 'catch (VulkanException e) when (e.ResultCode is not' in shaders
  assert 'Background Compilation failed:' not in shaders
  pipeline=z.read('src/Ryujinx.Graphics.Vulkan/PipelineState.cs').decode('utf-8-sig')
  assert 'Graphics pipeline creation failed:' in pipeline
 return dict(coreSource=MELONX_SOURCE,coreRun=MELONX_RUN,regression=receipt,
  sourceArchiveSHA256=hashlib.sha256((ROOT/'dist/melonx/embedded-adapted-source.zip').read_bytes()).hexdigest(),
  physicalDeviceTested=False,personaVisualFixConfirmed=False)

def embed(app):
 journal.embed(app)
 (app/IDENTITY).write_text(json.dumps(expected(),indent=2)+'\n')

def validate(ipa,build):
 result=journal.validate(ipa,build)
 with zipfile.ZipFile(ipa) as z:
  root=next(n[:-10] for n in z.namelist() if n.startswith('Payload/') and len(n.split('/'))==3 and n.endswith('.app/Info.plist'))
  receipt=json.loads(z.read(root+IDENTITY));assert receipt==expected()
  identity=json.loads(z.read(root+'MeloNX-native-identity.json'))['sourceCoreIdentity']
  assert identity['host']==MELONX_SOURCE
  for p in [ADAPTER,PREPARE]:assert identity['adaptations'][p]==hashlib.sha256((ROOT/p).read_bytes()).hexdigest(),p
  core=z.read(root+'Frameworks/MeloNXCore.framework/MeloNXCore')
  assert journal.previous.contains(core,'Graphics pipeline creation failed:')
  assert not journal.previous.contains(core,'Background Compilation failed:')
 return dict(result,pipelineRecovery=receipt,compiledPipelineCorrectionVerified=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('ipa',nargs='?',type=Path);p.add_argument('--embed',type=Path)
 p.add_argument('--build-number',type=int,default=540);p.add_argument('--report',type=Path);a=p.parse_args()
 if a.embed:embed(a.embed)
 else:
  assert a.ipa and a.report
  result=validate(a.ipa,a.build_number);a.report.parent.mkdir(parents=True,exist_ok=True)
  a.report.write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
