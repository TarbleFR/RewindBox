#!/usr/bin/env python3
"""Run only the fixed-upload consumers with historical versus final Slice."""
from pathlib import Path
import runpy
import sys

assert len(sys.argv) == 2, 'Usage: melonx_fragmented_upload_slice_test.py <pinned MeloNX checkout>'
driver = Path(__file__).with_name('melonx_fragmented_uploads_test.py')
sys.argv = [str(driver), sys.argv[1], '--slice-composition']
runpy.run_path(str(driver), run_name='__main__')
