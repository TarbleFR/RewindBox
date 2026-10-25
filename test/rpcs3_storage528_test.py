"""Run actual storage/archive regression campaign with sanitizers."""
import argparse,json,subprocess,tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--report',type=Path,required=True);a=p.parse_args()
root=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory() as d:
 subprocess.run(['python3',str(root/'native/neoswap-storage/run_source_validation.py'),'--output',d],check=True)
 report=json.loads((Path(d)/'source-archive.json').read_bytes());assert report['passed']
 a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
