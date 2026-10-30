"""Private IPA598 from delivered597, adding only the already verified MeloNX core.

No historical delivery recipe is replayed and no engine is rebuilt. The five
unchanged product roots and the exact new native C# boundary are authenticated.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import rewind597_baseline as previous

ROOT=Path(__file__).resolve().parents[2]
BUILD='598'
SOURCE='93af61a13ef67e45e6be0e313decf4bdf7ca23dc'
BASE_SOURCE='6ce5097737701afb4dc371013889bacdcef15140'
BASE_TREE='0b8afa0d8614e1ceae519f6d2489fa49b9cbf368'
BASE_IPA_SHA256='b9e97907210458dfafe76fe471a3cde58fa18564488324e9adfd04dc7a7bb57d'
BASE_RECEIPT_SHA256='698cd70286bb71dd721785ecc61c657e15c0c9e6423b8a7c0d118c4e194aa6c8'
BASE_PRODUCTS=dict(previous.PRODUCTS)
PRODUCTS=dict(BASE_PRODUCTS,native='608d3ce80c309e07e445b018c72ea43505779b90')
NATIVE_PATH='native/melonx/EmbeddedGraphicsSettings.cs'
NATIVE_BLOB='7e5073177f88f62536f9b5ec00453924378dd9cf'
STORE_PATH=previous.STORE_PATH
STORE_SHA256=previous.STORE_SHA256
RECIPE={'.github/workflows/rewind598-baseline-delivery.yml',
        '.github/diagnostics/rewind598_baseline.py',
        '.github/diagnostics/rewind598_baseline_delivery.py',
        '.github/diagnostics/rewind598_engine.py',
        'build-utils/validate_melonx_engine598_ipa.py',
        'build-utils/validate_rpcs3_core598_ipa.py',
        'build-utils/delivery-598-recipient.pem',
        'test/rewind598_delivery_contract_test.py'}
component_pins=previous.component_pins
COMPONENT_PINS=previous.COMPONENT_PINS


def git(*args):
 return subprocess.check_output(['git',*args],cwd=ROOT,text=True).strip()


def products(ref):return {name:git('rev-parse',ref+':'+name)for name in PRODUCTS}


def source_contract():
 assert os.environ.get('BUILD_NUMBER',BUILD)==BUILD,'Wrong delivery number'
 assert not git('diff','--name-only'),'Tracked working source differs from reviewed checkout'
 assert git('write-tree')==git('rev-parse','HEAD^{tree}'),'Staged source differs from HEAD'
 subprocess.run(['git','merge-base','--is-ancestor',SOURCE,'HEAD'],cwd=ROOT,check=True)
 raw=(ROOT/'docs/evidence/rewind597-delivery.json').read_bytes()
 assert hashlib.sha256(raw).hexdigest()==BASE_RECEIPT_SHA256,'Delivered597 receipt changed'
 receipt=json.loads(raw)
 assert receipt['result']=='passed'and receipt['build']==597 and receipt['source']==BASE_SOURCE
 assert receipt['deliveryTree']==BASE_TREE and receipt['run']['id']==40985625413 and receipt['run']['conclusion']=='success'
 assert receipt['ipa']['sha256']==BASE_IPA_SHA256 and receipt['productTrees']==BASE_PRODUCTS
 assert products(BASE_SOURCE)==BASE_PRODUCTS,'Delivered597 product roots changed'
 assert products(SOURCE)==PRODUCTS and products('HEAD')==PRODUCTS,'Unreviewed product root change'
 delta=git('diff-tree','--no-commit-id','--name-only','-r',BASE_SOURCE,'HEAD','--',*PRODUCTS).splitlines()
 assert delta==[NATIVE_PATH],'Unexpected application product delta since597: '+repr(delta)
 assert git('rev-parse','HEAD:'+NATIVE_PATH)==NATIVE_BLOB,'Wrong new core configuration boundary'
 assert hashlib.sha256((ROOT/STORE_PATH).read_bytes()).hexdigest()==STORE_SHA256,'Latest NeoSwap Store was not retained'
 changes=git('diff-tree','--no-commit-id','--name-only','-r',SOURCE,'HEAD').splitlines()
 assert all(p in RECIPE or p=='AGENTS.md'or p.startswith('docs/')for p in changes),'Unreviewed build/tool/source delta'
 assert RECIPE<=set(git('ls-files','-z').split('\0')),'Missing committed598 recipe input'
 pins=component_pins((ROOT/'.github/workflows/rewind598-baseline-delivery.yml').read_text())
 return dict(build=598,head=git('rev-parse','HEAD'),tree=git('write-tree'),reviewedSource=SOURCE,
             baseline=dict(build=597,source=BASE_SOURCE,tree=BASE_TREE,run=40985625413,ipaSHA256=BASE_IPA_SHA256),
             productTrees=PRODUCTS,unchangedProductTrees=[p for p in PRODUCTS if p!='native'],
             reviewedNativeProductDelta=[NATIVE_PATH],retainedHostStore=dict(path=STORE_PATH,sha256=STORE_SHA256),
             componentPins=pins,recipeSHA256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest()for p in sorted(RECIPE)},
             engineRecompiled=False,historicalContractsReplayed=False,nativeTestsReplayed=False,restoredOlderCheckout=False)


def verify():
 import sys
 sys.path.insert(0,str(ROOT/'build-utils'))
 from delivery_contract_memo import reuse
 return reuse(BUILD,source_contract)


def pin():
 result=verify();p=ROOT/'build/delivery/host-tree598.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(result,indent=2)+'\n');return result


if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--pin',action='store_true');a=p.parse_args();print(json.dumps(pin()if a.pin else verify(),indent=2))
