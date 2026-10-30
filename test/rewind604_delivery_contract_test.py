#!/usr/bin/env python3
"""Check the new private delivery binding without replaying native tests."""
from pathlib import Path
import hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.github/diagnostics'),str(ROOT/'build-utils/melonx')]
import rewind604_baseline as tree
import rewind604_engine as engine
from helper_initialization import verify
verify()
assert tree.products(tree.BASE_SOURCE)==tree.BASE_PRODUCTS
assert tree.products(tree.SOURCE)==tree.PRODUCTS
assert tree.git('diff-tree','--no-commit-id','--name-only','-r',tree.BASE_SOURCE,tree.SOURCE,'--',*tree.PRODUCTS).splitlines()==tree.PRODUCT_DELTA
assert tree.PRODUCT_DELTA==[
 'lib/l10n/melonx_unreal_profile_locale.dart',
 'lib/widgets/melonx_internal_playlist_actions.dart',
 'lib/widgets/melonx_unreal_profile_dialog.dart',
 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
]
assert [path for path in tree.PRODUCTS if tree.PRODUCTS[path]!=tree.BASE_PRODUCTS[path]]==['lib','packages']
workflow=(ROOT/'.github/workflows/rewind604-hogwarts-core-delivery.yml').read_text()
assert tree.component_pins(workflow)==tree.COMPONENT_PINS
assert "BUILD_NUMBER: '604'"in workflow and 'delivery-604-recipient.pem'in workflow
assert '[rewind604-delivery]'in workflow and 'rpcs3runtime604_core'in workflow
assert 'build_core.sh'not in workflow and 'dotnet publish'not in workflow
assert 'flutter test'not in workflow and 'test/melonx_session_host_test.py --sdk-only'not in workflow
assert engine.MELONX_SOURCE=='ada4058f5738465ac882934bb87224b637bcd0a1'
assert tree.SOURCE is not None
subprocess.run(['git','merge-base','--is-ancestor',engine.MELONX_SOURCE,tree.SOURCE],cwd=ROOT,check=True)
contract_path='build-utils/melonx/guard-core-contract.json'
contract_raw=(ROOT/contract_path).read_bytes()
assert subprocess.check_output(['git','show',engine.MELONX_SOURCE+':'+contract_path],cwd=ROOT)==contract_raw
contract=json.loads(contract_raw)
assert len(contract['preparationInputs'])==engine.PREPARATION_INPUT_COUNT==120
assert len(contract['preparedMembers'])==engine.PREPARED_MEMBER_COUNT==160
for path,digest in contract['preparationInputs'].items():
 assert hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest,path
 assert hashlib.sha256(subprocess.check_output(['git','show',engine.MELONX_SOURCE+':'+path],cwd=ROOT)).hexdigest()==digest,path
assert engine.BINARY_SHA256 and len(engine.BINARY_SHA256['ios-arm64'])==64
assert engine.BASELINE==603 and engine.BUILD==604
key=(ROOT/'build-utils/delivery-604-recipient.pem').read_text()
assert key.startswith('-----BEGIN PUBLIC KEY-----')and'PRIVATE KEY'not in key
print(json.dumps(dict(result='passed',build=604,applicationBaseline=603,productDelta=tree.PRODUCT_DELTA,coreRecompiled=False,nativeFixturesReplayed=False)))
