"""Private543 component identity validation; host and other engines preserved."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
import melonxaudio537_delivery as previous
import rpcs3cell543_core as native
ROOT=Path(__file__).resolve().parents[2]
BASE='ca5c96a021a089f3db698ffb503cea53103c9efe'
RETAINED_SOURCE='309af73d147c11bb11e278a231f05f839b9b021f'
MELONX_SOURCE=BASE
MELONX_RUN=40195252399
BASE_RUN=40190818310
CORE_SOURCE='d3689eb2ce3ced1a6086c82f50a3c67e6f398874'
CORE_RUN=40212465374
HOST=previous.HOST
validate_psp_core_identity=previous.validate_psp_core_identity
command=previous.command

def validate_rpc_core_identity(identity):
 assert identity['host_commit']==CORE_SOURCE and identity['abi_version']==30
 assert identity['cpu_baseline']=='armv8.4-a' and not identity['legacy_core_bundled']
 assert not identity['device_runtime_tested']
 assert identity['source_patch_sha256']==native.manifest()['patch_sha256']
 assert identity['native_source_sha256']==native.manifest()['files_sha256']
 assert identity['cell543_input_sha256']==native.inputs()
 for p,h in identity['cell543_input_sha256'].items():
  assert hashlib.sha256(subprocess.check_output(['git','show',CORE_SOURCE+':'+p],cwd=ROOT)).hexdigest()==h,p

def validate_rpc_core_pin(source,paths):
 assert source==CORE_SOURCE
 for p in paths:assert subprocess.check_output(['git','show',source+':'+p],cwd=ROOT)==(ROOT/p).read_bytes(),p

