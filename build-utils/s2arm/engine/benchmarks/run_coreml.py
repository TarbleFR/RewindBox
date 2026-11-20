#!/usr/bin/env python3
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parent
subprocess.run(["bash",str(root/"coreml/run_macos.sh"),str(Path("proof/race-benchmarks/coreml").resolve())],check=True)
