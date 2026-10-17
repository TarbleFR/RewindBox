"""Execute real fatal signals in forked children; usable on Linux and macOS."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='libretro-fatal-') as folder:
    folder = Path(folder)
    exe = folder / 'capture'
    subprocess.run(['cc', '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                    '-I', str(root / 'packages/libretro_internal_bridge/ios/Classes'),
                    str(root / 'test/libretro_crash_capture_test.c'), '-o', str(exe)], check=True)
    subprocess.run([str(exe), str(folder / 'native.log')], check=True)
