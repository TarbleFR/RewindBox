"""Delivered599 baseline plus all remaining MeloNX lots; concurrent RPCS3 host diagnostics preserved."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
import rewind597_baseline as pins
ROOT=Path(__file__).resolve().parents[2]
BUILD='600'
SOURCE='144f2a3329c954ef84aee6a5791a16e759b9a4c4'
BASE_SOURCE='00e372238ade33f3d58157aece54d89df7d630e7'
BASE_TREE='f5b07496a60ab58db8b94a979cc409798bf45e78'
BASE_IPA_SHA256='c7d4337016c7db77ae130e43708141bf68bb8010c8cbe39f1555ddd1b0c27939'
BASE_RECEIPT_SHA256='441db7d2a556ba024383c941d53c72a9661628cf1c814e92a0ffd3ac0e76c863'
PRODUCTS={'lib': '9296876c195b848340efcf53f2ecec904d720b7a', 'native': '277fce2eecdf3a2389b617d5a9ea84af0a3764da', 'packages': 'a122a5c68e90c1360532831cbd243c634d33e374', 'assets': 'fb15f670844075f22dd667b370961a69371d9589', 'pubspec.yaml': '4060a4840b2332a4ef1b492bfb3c4bc4140acf26', 'pubspec.lock': '719ea3b6767c10e60209e144a4e7793520a88b54'}
BASE_PRODUCTS={'lib': '19a49c340ae1ed9d37d65be19c0587d82e76a3a7', 'native': '608d3ce80c309e07e445b018c72ea43505779b90', 'packages': '6837aa129fc0bec97d46389e945643988b80fb40', 'assets': 'fb15f670844075f22dd667b370961a69371d9589', 'pubspec.yaml': '4060a4840b2332a4ef1b492bfb3c4bc4140acf26', 'pubspec.lock': '719ea3b6767c10e60209e144a4e7793520a88b54'}
PRODUCT_DELTA=['lib/services/melonx_unreal_profiles.dart', 'lib/widgets/melonx_internal_playlist_actions.dart', 'lib/widgets/melonx_unreal_profile_dialog.dart', 'native/melonx/EmbeddedContent.cs', 'native/melonx/EmbeddedUnrealContent.cs', 'native/melonx/EmbeddedUnrealProjectProbe.cs', 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift', 'packages/melonx_jit_helper/ios/Resources/melonx-universal.js', 'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.mm']
RECIPE=set(['.github/workflows/rewind600-baseline-delivery.yml', '.github/diagnostics/rewind600_baseline.py', '.github/diagnostics/rewind600_baseline_delivery.py', '.github/diagnostics/rewind600_engine.py', 'build-utils/validate_melonx_engine600_ipa.py', 'build-utils/validate_rpcs3_core600_ipa.py', 'build-utils/validate_hogwarts600_ipa.py', 'build-utils/delivery-600-recipient.pem', 'test/rewind600_delivery_contract_test.py', '.github/diagnostics/rpcs3runtime600_retained_core.py'])
COMPONENT_PINS=pins.COMPONENT_PINS
component_pins=pins.component_pins
STORE_PATH='native/neoswap-storage/Store.cpp'
STORE_SHA256='87df68227cf9e113af51ec2ea8968d8af88170834611d560ce711cf168f1ca46'
def git(*args):return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()
def products(ref):return {n:git('rev-parse',ref+':'+n)for n in PRODUCTS}
def source_contract():
 assert os.environ.get('BUILD_NUMBER',BUILD)==BUILD
 assert not git('diff','--name-only') and git('write-tree')==git('rev-parse','HEAD^{tree}')
 subprocess.run(['git','merge-base','--is-ancestor',SOURCE,'HEAD'],cwd=ROOT,check=True)
 raw=(ROOT/'docs/evidence/rewind599-delivery.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==BASE_RECEIPT_SHA256
 b=json.loads(raw);assert b['result']=='passed'and b['source']==BASE_SOURCE and b['run']['id']==41024302714 and b['run']['conclusion']=='success'and b['ipa']['sha256']==BASE_IPA_SHA256 and b['productTrees']==BASE_PRODUCTS
 assert products(BASE_SOURCE)==BASE_PRODUCTS and products(SOURCE)==products('HEAD')==PRODUCTS
 assert git('diff-tree','--no-commit-id','--name-only','-r',BASE_SOURCE,'HEAD','--',*PRODUCTS).splitlines()==PRODUCT_DELTA
 changes=git('diff-tree','--no-commit-id','--name-only','-r',SOURCE,'HEAD').splitlines()
 assert all(p in RECIPE or p=='AGENTS.md'or p.startswith('docs/')for p in changes),changes
 assert RECIPE<=set(git('ls-files','-z').split('\0'))
 assert component_pins((ROOT/'.github/workflows/rewind600-baseline-delivery.yml').read_text())==COMPONENT_PINS
 assert hashlib.sha256((ROOT/STORE_PATH).read_bytes()).hexdigest()==STORE_SHA256
 return dict(build=600,head=git('rev-parse','HEAD'),tree=git('write-tree'),reviewedSource=SOURCE,baseline=dict(build=599,source=BASE_SOURCE,tree=BASE_TREE,run=41024302714,ipaSHA256=BASE_IPA_SHA256),productTrees=PRODUCTS,unchangedProductTrees=[n for n in PRODUCTS if PRODUCTS[n]==BASE_PRODUCTS[n]],reviewedHostProductDelta=PRODUCT_DELTA,retainedHostStore=dict(path=STORE_PATH,sha256=STORE_SHA256),componentPins=COMPONENT_PINS,recipeSHA256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in sorted(RECIPE)},engineRecompiled=False,nativeTestsReplayed=False,restoredOlderCheckout=False)
def verify():
 sys.path.insert(0,str(ROOT/'build-utils'));from delivery_contract_memo import reuse
 return reuse(BUILD,source_contract)
def pin():
 r=verify();p=ROOT/'build/delivery/host-tree600.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+'\n');return r
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--pin',action='store_true');a=p.parse_args();print(json.dumps(pin()if a.pin else verify(),indent=2))
