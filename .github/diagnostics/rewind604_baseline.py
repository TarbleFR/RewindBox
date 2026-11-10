"""Private IPA604: corrected MeloNX core and validated RPCS3 a4d0c9a5.

Preserve four delivered603 product roots exactly. The lib root changes only
for the reviewed Unreal dialog, twelve-language catalogue and entry-point label;
the packages root changes only for the measured-scope UIKit entry path. Both separately compiled engine updates are authenticated. Use previously compiled, independently validated Core artifacts;
do not silently recompile engines or ship an unbuilt RPCS3 branch candidate.
"""
import argparse,hashlib,json,os,re,subprocess,sys
from pathlib import Path
import rewind600_baseline as previous
from rewind597_baseline import COMPONENT_PINS as OLD_PINS

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"build-utils/melonx"))
BUILD="604"
SOURCE='510e683a149e811e68ea6ab5e766e85c44ab1057'  # Reviewed host boundary; engine producer is independently pinned
BASE_SOURCE='808b64e16bb0f5112a2a7b5a07b400c19bb9cfbd'
BASE_TREE='d701c1580ccc1bca05e828a64ef2059c31e07e61'
BASE_PRODUCTS={'lib': '9296876c195b848340efcf53f2ecec904d720b7a', 'native': '9ff87f370b91fe45924857bdc76d789fe883e496', 'packages': '6e40b266828b38664b763286300b1c8f86fc839a', 'assets': 'fb15f670844075f22dd667b370961a69371d9589', 'pubspec.yaml': '4060a4840b2332a4ef1b492bfb3c4bc4140acf26', 'pubspec.lock': '719ea3b6767c10e60209e144a4e7793520a88b54'}
PRODUCTS=dict(BASE_PRODUCTS)
PRODUCTS['lib']='9ce47bc9ad641f399246b085d3f9ebeb8e37d81e'
PRODUCTS['packages']='e94bd0301d4427f950d94947cfeb53ff4241191c'
PRODUCT_DELTA=[
 'lib/l10n/melonx_unreal_profile_locale.dart',
 'lib/widgets/melonx_internal_playlist_actions.dart',
 'lib/widgets/melonx_unreal_profile_dialog.dart',
 'packages/melonx_internal_bridge/ios/Classes/MeloNXInternalBridgePlugin.swift',
]
BASELINE_RUN=41102769156
COMPONENT_PINS=dict(OLD_PINS)
COMPONENT_PINS.update(RPCS3_CORE_HOST_SHA="a4d0c9a5e00ace8d2036c62ef1a653e50bb79a3a",
                      RPCS3_CORE_RUN_ID="41117115264")
STORE_PATH=previous.STORE_PATH
STORE_SHA256=previous.STORE_SHA256
RECIPE={'.github/diagnostics/rewind604_baseline_delivery.py', 'build-utils/validate_hogwarts604_ipa.py', 'build-utils/delivery-604-recipient.pem', '.github/diagnostics/rewind604_engine.py', '.github/diagnostics/rewind604_checks.py', '.github/diagnostics/rewind604_baseline.py', 'build-utils/validate_rpcs3_core604_ipa.py', 'build-utils/validate_melonx_engine604_ipa.py', 'test/rewind604_delivery_contract_test.py', '.github/diagnostics/rpcs3runtime604_core.py', 'test/rpcs3_core604_contract_test.py', 'docs/evidence/rpcs3-core604/apple-core.json', '.github/workflows/rewind604-hogwarts-core-delivery.yml'}

def git(*argv):
 return subprocess.check_output(["git",*argv],cwd=ROOT,text=True,timeout=120).strip()
def products(ref):
 return {p:git("rev-parse",ref+":"+p) for p in PRODUCTS}
def component_pins(workflow):
 got={}
 for name,expected in COMPONENT_PINS.items():
  values=re.findall(r"^      "+re.escape(name)+r":\s*([^\r\n]+)$",workflow,re.MULTILINE)
  assert len(values)==1 and values[0].strip().strip("'\"")==expected,"Wrong component pin "+name
  got[name]=expected
 return got

def source_contract():
 assert isinstance(SOURCE,str) and re.fullmatch(r'[0-9a-f]{40}',SOURCE),'Pending validated Core producer/source boundary'
 assert all(isinstance(value,str) and re.fullmatch(r'[0-9a-f]{40}',value) for value in PRODUCTS.values()),'Pending reviewed product tree pins'
 assert os.environ.get("BUILD_NUMBER",BUILD)==BUILD,"Wrong private build number"
 assert not git("diff","--name-only"),"Tracked source changed after checkout"
 assert git("write-tree")==git("rev-parse","HEAD^{tree}"),"Staged tree changed"
 subprocess.run(["git","merge-base","--is-ancestor",SOURCE,"HEAD"],cwd=ROOT,check=True,timeout=60)
 assert git("rev-parse",BASE_SOURCE+"^{tree}")==BASE_TREE,"Historical603 source tree changed"
 assert products(BASE_SOURCE)==BASE_PRODUCTS,"Compiled603 production trees changed"
 assert products(SOURCE)==products("HEAD")==PRODUCTS,"Product trees differ from reviewed603 plus the four reviewed host changes"
 assert git("diff-tree","--no-commit-id","--name-only","-r",BASE_SOURCE,"HEAD","--",*PRODUCTS).splitlines()==PRODUCT_DELTA, "Unexpected host source delta"
 from helper_initialization import verify as helper_verify
 helper_verify()
 changes=git("diff-tree","--no-commit-id","--name-only","-r",SOURCE,"HEAD").splitlines()
 assert all(p in RECIPE or p=="AGENTS.md" or p.startswith("docs/") for p in changes),changes
 assert RECIPE <= set(git("ls-files","-z").split("\0")),"New delivery inputs absent from immutable checkout"
 assert component_pins((ROOT/".github/workflows/rewind604-hogwarts-core-delivery.yml").read_text())==COMPONENT_PINS
 assert hashlib.sha256((ROOT/STORE_PATH).read_bytes()).hexdigest()==STORE_SHA256,"NeoSwap Store drift"
 return dict(build=604,source=git("rev-parse","HEAD"),tree=git("write-tree"),
             reviewedSource=SOURCE,baseline=dict(build=603,source=BASE_SOURCE,tree=BASE_TREE,run=BASELINE_RUN),
             productTrees=PRODUCTS,unchangedProductTrees=[p for p in PRODUCTS if PRODUCTS[p]==BASE_PRODUCTS[p]],
             componentPins=COMPONENT_PINS,
             recipeSHA256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(RECIPE)},
             changedProductPaths=PRODUCT_DELTA,compiledEngineCountForDelivery=0,installedRpcS3Source=COMPONENT_PINS["RPCS3_CORE_HOST_SHA"],
             privateDelivery=True)

def verify():
 sys.path.insert(0,str(ROOT/"build-utils"))
 sys.path.insert(0,str(ROOT/"build-utils/melonx"))
 from delivery_contract_memo import reuse
 return reuse(BUILD,source_contract)

def pin():
 data=verify()
 f=ROOT/"build/delivery/host-tree604.json"
 f.parent.mkdir(parents=True,exist_ok=True)
 f.write_text(json.dumps(data,indent=2)+"\n")
 return data

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--pin",action="store_true")
 a=ap.parse_args()
 print(json.dumps(pin() if a.pin else verify(),indent=2))
