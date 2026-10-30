#!/usr/bin/env python3
"""Check the exact helper-only product delta and retained Core packaging bindings."""
from pathlib import Path
import importlib,sys,json,subprocess
ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'.github/diagnostics'),str(ROOT/'build-utils/melonx')]
import rewind602_baseline as tree
import rewind602_engine as engine
from helper_initialization import verify
verify()
assert tree.products(tree.BASE_SOURCE)==tree.BASE_PRODUCTS
assert tree.products(tree.SOURCE)==tree.PRODUCTS
assert tree.git('diff-tree','--no-commit-id','--name-only','-r',tree.BASE_SOURCE,tree.SOURCE,'--',*tree.PRODUCTS).splitlines()==tree.PRODUCT_DELTA
workflow=(ROOT/'.github/workflows/rewind602-jit-helper-delivery.yml').read_text()
assert tree.component_pins(workflow)==tree.COMPONENT_PINS
assert "BUILD_NUMBER: '602'" in workflow and 'delivery-602-recipient.pem' in workflow
assert 'build_core.sh'not in workflow and 'dotnet publish'not in workflow
assert 'flutter test'not in workflow and 'test/melonx_session_host_test.py --sdk-only'not in workflow
assert 'rewind602_checks.py' in workflow and 'validate_hogwarts602_ipa.py' in workflow
assert 'rpcs3runtime601_core' in workflow
assert engine.MELONX_SOURCE=='827f4653e0dee5b86258f598373255d179638bdb'
assert engine.BINARY_SHA256['ios-arm64']=='b4beb50452ab3a36ad71e0415c4a775249bddf92c7db222899f3da2fc43521c4'
key=(ROOT/'build-utils/delivery-602-recipient.pem').read_text()
assert key.startswith('-----BEGIN PUBLIC KEY-----') and 'PRIVATE KEY'not in key
print(json.dumps(dict(result='passed',build=602,productDelta=tree.PRODUCT_DELTA,coreRecompiled=False,unchangedSuitesReplayed=False)))
