"""Private IPA601: compiled RPCS3 378509e8 and MeloNX 827f4653.

Preserve the exact delivered600 product sources and all unaffected native
components. Use previously compiled, independently validated Core artifacts;
do not silently recompile engines or ship an unbuilt RPCS3 branch candidate.
"""
import argparse,hashlib,json,os,re,subprocess,sys
from pathlib import Path
import rewind600_baseline as previous
from rewind597_baseline import COMPONENT_PINS as OLD_PINS

ROOT=Path(__file__).resolve().parents[2]
BUILD="601"
SOURCE="831782a08c24ed52e419da4ed747fd03761dbc7d"
BASE_SOURCE="9ea4a42006e1574dcef7ba2163571d70849c547c"
BASE_TREE="3cd32cd20075eadcb3509d9b677c23f44637ea67"
BASE_PRODUCTS=dict(previous.PRODUCTS)
PRODUCTS=dict(previous.PRODUCTS)
PRODUCT_DELTA=[]
BASELINE_RUN=41030015941
COMPONENT_PINS=dict(OLD_PINS)
COMPONENT_PINS.update(RPCS3_CORE_HOST_SHA="378509e82d360bc2cb2fcc9fb23d4d9d98787506",
                      RPCS3_CORE_RUN_ID="41033511090")
STORE_PATH=previous.STORE_PATH
STORE_SHA256=previous.STORE_SHA256
RECIPE={
 ".github/workflows/rewind601-dual-core-delivery.yml",
 ".github/diagnostics/rewind601_baseline.py",
 ".github/diagnostics/rewind601_baseline_delivery.py",
 ".github/diagnostics/rewind601_engine.py",
 ".github/diagnostics/rpcs3runtime601_core.py",
 "build-utils/validate_rpcs3_core601_ipa.py",
 "build-utils/validate_melonx_engine601_ipa.py",
 "build-utils/validate_hogwarts601_ipa.py",
 "build-utils/delivery-601-recipient.pem",
 "test/rewind601_delivery_contract_test.py",
}

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
 assert git("rev-parse",BASE_SOURCE+"^{tree}")==BASE_TREE,"Historical 600 source tree changed"
 assert products(BASE_SOURCE)==BASE_PRODUCTS,"Compiled 600 production trees changed"
 assert products(SOURCE)==products("HEAD")==PRODUCTS,"Production trees changed since delivered600"
 assert git("diff-tree","--no-commit-id","--name-only","-r",BASE_SOURCE,"HEAD","--",*PRODUCTS)=="" , "Unexpected host source delta"
 changes=git("diff-tree","--no-commit-id","--name-only","-r",SOURCE,"HEAD").splitlines()
 assert all(p in RECIPE or p=="AGENTS.md" or p.startswith("docs/") for p in changes),changes
 assert RECIPE <= set(git("ls-files","-z").split("\0")),"New delivery inputs absent from immutable checkout"
 assert component_pins((ROOT/".github/workflows/rewind601-dual-core-delivery.yml").read_text())==COMPONENT_PINS
 assert hashlib.sha256((ROOT/STORE_PATH).read_bytes()).hexdigest()==STORE_SHA256,"NeoSwap Store drift"
 return dict(build=601,source=git("rev-parse","HEAD"),tree=git("write-tree"),
             reviewedSource=SOURCE,baseline=dict(build=600,source=BASE_SOURCE,tree=BASE_TREE,run=BASELINE_RUN),
             productTrees=PRODUCTS,unchangedProductTrees=list(PRODUCTS),
             componentPins=COMPONENT_PINS,
             recipeSHA256={p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in sorted(RECIPE)},
             changedProductPaths=[],compiledEngineCountForDelivery=0,privateDelivery=True)

def verify():
 sys.path.insert(0,str(ROOT/"build-utils"))
 from delivery_contract_memo import reuse
 return reuse(BUILD,source_contract)

def pin():
 data=verify()
 f=ROOT/"build/delivery/host-tree601.json"
 f.parent.mkdir(parents=True,exist_ok=True)
 f.write_text(json.dumps(data,indent=2)+"\n")
 return data

if __name__=="__main__":
 ap=argparse.ArgumentParser()
 ap.add_argument("--pin",action="store_true")
 a=ap.parse_args()
 print(json.dumps(pin() if a.pin else verify(),indent=2))
