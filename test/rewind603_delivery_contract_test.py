#!/usr/bin/env python3
"""Check the new private delivery binding without replaying native tests."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.github/diagnostics'),str(ROOT/'build-utils/melonx')]
import rewind603_baseline as tree
import rewind603_engine as engine
from helper_initialization import verify
verify()
assert tree.products(tree.BASE_SOURCE)==tree.BASE_PRODUCTS
assert tree.products(tree.SOURCE)==tree.PRODUCTS
assert tree.git('diff-tree','--no-commit-id','--name-only','-r',tree.BASE_SOURCE,tree.SOURCE,'--',*tree.PRODUCTS).splitlines()==tree.PRODUCT_DELTA
assert tree.PRODUCT_DELTA==['native/melonx/EmbeddedStartupTrace.cs']
assert [p for p in tree.PRODUCTS if tree.PRODUCTS[p]!=tree.BASE_PRODUCTS[p]]==['native']
workflow=(ROOT/'.github/workflows/rewind603-hogwarts-core-delivery.yml').read_text()
assert tree.component_pins(workflow)==tree.COMPONENT_PINS
assert "BUILD_NUMBER: '603'"in workflow and 'delivery-603-recipient.pem'in workflow
assert '[rewind603-delivery]'in workflow and 'rpcs3runtime601_core'in workflow
assert 'build_core.sh'not in workflow and 'dotnet publish'not in workflow
assert 'flutter test'not in workflow and 'test/melonx_session_host_test.py --sdk-only'not in workflow
assert engine.MELONX_SOURCE=='1630bd0230c9431de92faec9c5e2662262b1ede6'
assert engine.BINARY_SHA256['ios-arm64']=='423f2af029a5c1319d518a67114dc0b963ba5399747960cb6155b44014037ddc'
assert engine.BASELINE==602 and engine.BUILD==603
key=(ROOT/'build-utils/delivery-603-recipient.pem').read_text()
assert key.startswith('-----BEGIN PUBLIC KEY-----')and'PRIVATE KEY'not in key
print(json.dumps(dict(result='passed',build=603,applicationBaseline=602,productDelta=tree.PRODUCT_DELTA,coreRecompiled=False,nativeFixturesReplayed=False)))
