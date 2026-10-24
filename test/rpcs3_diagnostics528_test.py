"""Foundation concurrency, selective history, capture-clock and rotation behavior."""
import argparse,json,subprocess,sys
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('source');p.add_argument('--report',type=Path,required=True);a=p.parse_args();assert sys.platform=='darwin','Real Foundation execution required'
subprocess.run(['python3','test/rpcs3_diagnostics_native_test.py'],check=True)
a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(dict(passed=True,physicalDeviceTested=False,scope='actual Foundation logger; selective history survives verbose restore rotation; bounded two-file history and bracketed capture clocks'))+'\n')
