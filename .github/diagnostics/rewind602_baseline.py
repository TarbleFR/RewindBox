"""Private IPA602: compiled RPCS3 378509e8 and MeloNX 827f4653.

Preserve the delivered601 product sources except the exact helper initialization relocation and all unaffected native
components. Use previously compiled, independently validated Core artifacts;
do not silently recompile engines or ship an unbuilt RPCS3 branch candidate.
"""
import argparse,hashlib,json,os,re,subprocess,sys
from pathlib import Path
import rewind600_baseline as previous
from rewind597_baseline import COMPONENT_PINS as OLD_PINS

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"build-utils/melonx"))
BUILD="602"
SOURCE="db7aa6e820769542fdeb45733998a53c4ab5d73d"
BASE_SOURCE="d042eefbaf5544e58faac91bf1680f7ff2f6dc93"
BASE_TREE="d694c3f508e8e4f8033ef89f37486f0e66d93411"
BASE_PRODUCTS={'lib': '9296876c195b848340efcf53f2ecec904d720b7a', 'native': '277fce2eecdf3a2389b617d5a9ea84af0a3764da', 'packages': 'a122a5c68e90c1360532831cbd243c634d33e374', 'assets': 'fb15f670844075f22dd667b370961a69371d9589', 'pubspec.yaml': '4060a4840b2332a4ef1b492bfb3c4bc4140acf26', 'pubspec.lock': '719ea3b6767c10e60209e144a4e7793520a88b54'}
PRODUCTS={'lib': '9296876c195b848340efcf53f2ecec904d720b7a', 'native': '277fce2eecdf3a2389b617d5a9ea84af0a3764da', 'packages': '6e40b266828b38664b763286300b1c8f86fc839a', 'assets': 'fb15f670844075f22dd667b370961a69371d9589', 'pubspec.yaml': '4060a4840b2332a4ef1b492bfb3c4bc4140acf26', 'pubspec.lock': '719ea3b6767c10e60209e144a4e7793520a88b54'}
PRODUCT_DELTA=['packages/melonx_jit_helper/ios/Resources/melonx-universal.js']
BASELINE_RUN=41074846925
COMPONENT_PINS=dict(OLD_PINS)
COMPONENT_PINS.update(RPCS3_CORE_HOST_SHA="378509e82d360bc2cb2fcc9fb23d4d9d98787506",
                      RPCS3_CORE_RUN_ID="41033511090")
STORE_PATH=previous.STORE_PATH
STORE_SHA256=previous.STORE_SHA256
RECIPE={'.github/diagnostics/rewind602_baseline_delivery.py', 'build-utils/validate_hogwarts602_ipa.py', 'build-utils/delivery-602-recipient.pem', '.github/diagnostics/rewind602_engine.py', '.github/diagnostics/rewind602_checks.py', '.github/diagnostics/rewind602_baseline.py', 'build-utils/validate_rpcs3_core602_ipa.py', 'build-utils/validate_melonx_engine602_ipa.py', 'test/rewind602_delivery_contract_test.py', '.github/workflows/rewind602-jit-helper-delivery.yml'}

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
 assert os.environ.get("BUILD_NUMBER",BUILD)==BUILD,"Wrong private build number"
 assert not git("diff","--name-only"),"Tracked source changed after checkout"
 assert git("write-tree")==git("rev-parse","HEAD^{tree}"),"Staged tree changed"
 subprocess.run(["git","merge-base","--is-ancestor",SOURCE,"HEAD"],cwd=ROOT,check=True,timeout=60)
 assert git("rev-parse",BASE_SOURCE+"^{tree}")==BASE_TREE,"Historical 601 source tree changed"
 assert products(BASE_SOURCE)==BASE_PRODUCTS,"Compiled 601 production trees changed"
 assert products(SOURCE)==products("HEAD")==PRODUCTS,"Product trees differ from the reviewed helper correction"
 assert git("diff-tree","--no-commit-id","--name-only","-r",BASE_SOURCE,"HEAD","--",*PRODUCTS).splitlines()==PRODUCT_DELTA, "Unexpected host source delta"
 from helper_initialization import verify as helper_verify
 helper_verify()
 changes=git("diff-tree","--no-commit-id","--name-only","-r",SOURCE,"HEAD").splitlines()
 assert all(p in RECIPE or p=="AGENTS.md" or p.startswith("docs/") for p in changes),changes
 assert RECIPE <= set(git("ls-files","-z").split("\0")),"New delivery inputs absent from immutable checkout"
 assert component_pins((ROOT/".github/workflows/rewind602-jit-helper-delivery.yml").read_text())==COMPONENT_PINS
 assert hashlib.sha256((ROOT/STORE_PATH).read_bytes()).hexdigest()==STORE_SHA256,"NeoSwap Store drift"
 return dict(build=602,source=git("rev-parse","HEAD"),tree=git("write-tree"),
             reviewedSource=SOURCE,baseline=dict(build=601,source=BASE_SOURCE,tree=BASE_TREE,run=BASELINE_RUN),
             productTrees=PRODUCTS,unchangedProductTrees=[p for p in PRODUCTS if PRODUCTS[p]==BASE_PRODUCTS[p]],
             componentPins=COMPONENT_PINS,
             recipeSHA256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(RECIPE)},
             changedProductPaths=PRODUCT_DELTA,compiledEngineCountForDelivery=0,privateDelivery=True)

def verify():
 sys.path.insert(0,str(ROOT/"build-utils"))
 sys.path.insert(0,str(ROOT/"build-utils/melonx"))
 from delivery_contract_memo import reuse
 return reuse(BUILD,source_contract)

def pin():
 data=verify()
 f=ROOT/"build/delivery/host-tree602.json"
 f.parent.mkdir(parents=True,exist_ok=True)
 f.write_text(json.dumps(data,indent=2)+"\n")
 return data

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--pin",action="store_true")
 a=ap.parse_args()
 print(json.dumps(pin() if a.pin else verify(),indent=2))
