"""Immediate delivered598 baseline plus the reviewed host-only Hogwarts activation."""
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
import rewind597_baseline as pins
ROOT=Path(__file__).resolve().parents[2]
BUILD='599'
SOURCE='153e0ec997f76db9808ca21d6eb2c900ad965173'
BASE_SOURCE='1c30df6870e4c45bbc4b405e7bc8e1ba5dd5d2e4'
BASE_TREE='c5e117c273394987ae430ec6559a3a95e7e1faee'
BASE_IPA_SHA256='27cc3ce633a3378949d88448792b48691f99e313e6be723063f7be958272325b'
BASE_RECEIPT_SHA256='33b855e0be9c137cfde43f396d52dc0f2d6a86adf6fe3e71118474ffa430e345'
PRODUCTS={'lib': '19a49c340ae1ed9d37d65be19c0587d82e76a3a7', 'native': '608d3ce80c309e07e445b018c72ea43505779b90', 'packages': '6837aa129fc0bec97d46389e945643988b80fb40', 'assets': 'fb15f670844075f22dd667b370961a69371d9589', 'pubspec.yaml': '4060a4840b2332a4ef1b492bfb3c4bc4140acf26', 'pubspec.lock': '719ea3b6767c10e60209e144a4e7793520a88b54'}
BASE_PRODUCTS={'lib': '9208336d76655b98972d11e519cd0d3337666e41', 'native': '608d3ce80c309e07e445b018c72ea43505779b90', 'packages': '6164ff03871a384267e5f20f6734225a1aaed5c4', 'assets': 'fb15f670844075f22dd667b370961a69371d9589', 'pubspec.yaml': '4060a4840b2332a4ef1b492bfb3c4bc4140acf26', 'pubspec.lock': '719ea3b6767c10e60209e144a4e7793520a88b54'}
PRODUCT_DELTA=['lib/l10n/melonx_library_locale.dart', 'lib/widgets/melonx_hogwarts_graphics_options.dart', 'lib/widgets/melonx_internal_playlist_actions.dart', 'packages/melonx_internal_bridge/ios/Classes/MeloNXHogwartsGraphics.swift', 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift']
RECIPE=set(['.github/workflows/rewind599-baseline-delivery.yml', '.github/diagnostics/rewind599_baseline.py', '.github/diagnostics/rewind599_baseline_delivery.py', '.github/diagnostics/rewind599_engine.py', 'build-utils/validate_melonx_engine599_ipa.py', 'build-utils/validate_rpcs3_core599_ipa.py', 'build-utils/validate_hogwarts599_ipa.py', 'build-utils/delivery-599-recipient.pem', 'test/rewind599_delivery_contract_test.py'])
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
 raw=(ROOT/'docs/evidence/rewind598-delivery.json').read_bytes();assert hashlib.sha256(raw).hexdigest()==BASE_RECEIPT_SHA256
 b=json.loads(raw);assert b['result']=='passed'and b['source']==BASE_SOURCE and b['run']['id']==41010479756 and b['run']['conclusion']=='success'and b['ipa']['sha256']==BASE_IPA_SHA256 and b['productTrees']==BASE_PRODUCTS
 assert products(BASE_SOURCE)==BASE_PRODUCTS and products(SOURCE)==products('HEAD')==PRODUCTS
 assert git('diff-tree','--no-commit-id','--name-only','-r',BASE_SOURCE,'HEAD','--',*PRODUCTS).splitlines()==PRODUCT_DELTA
 changes=git('diff-tree','--no-commit-id','--name-only','-r',SOURCE,'HEAD').splitlines()
 assert all(p in RECIPE or p=='AGENTS.md'or p.startswith('docs/')for p in changes),changes
 assert RECIPE<=set(git('ls-files','-z').split('\0'))
 assert component_pins((ROOT/'.github/workflows/rewind599-baseline-delivery.yml').read_text())==COMPONENT_PINS
 assert hashlib.sha256((ROOT/STORE_PATH).read_bytes()).hexdigest()==STORE_SHA256
 return dict(build=599,head=git('rev-parse','HEAD'),tree=git('write-tree'),reviewedSource=SOURCE,baseline=dict(build=598,source=BASE_SOURCE,tree=BASE_TREE,run=41010479756,ipaSHA256=BASE_IPA_SHA256),productTrees=PRODUCTS,unchangedProductTrees=[n for n in PRODUCTS if PRODUCTS[n]==BASE_PRODUCTS[n]],reviewedHostProductDelta=PRODUCT_DELTA,retainedHostStore=dict(path=STORE_PATH,sha256=STORE_SHA256),componentPins=COMPONENT_PINS,recipeSHA256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in sorted(RECIPE)},engineRecompiled=False,nativeTestsReplayed=False,restoredOlderCheckout=False)
def verify():
 sys.path.insert(0,str(ROOT/'build-utils'));from delivery_contract_memo import reuse
 return reuse(BUILD,source_contract)
def pin():
 r=verify();p=ROOT/'build/delivery/host-tree599.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(r,indent=2)+'\n');return r
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--pin',action='store_true');a=p.parse_args();print(json.dumps(pin()if a.pin else verify(),indent=2))
