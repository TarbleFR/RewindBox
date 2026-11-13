#!/usr/bin/env python3
"""Optional Xenia C/C++ launcher configuration and cold fallback."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class XeniaBuildCacheTest(unittest.TestCase):
    def test_xenia_launchers_opt_in_and_missing_tool(self):
        script = (ROOT / 'build-utils/xenia/build_core.sh').read_text()
        self.assertEqual(script.count('${XENIA_CMAKE_CACHE_ARGS[@]+"${XENIA_CMAKE_CACHE_ARGS[@]}"}'), 2)
        self.assertIn('python3 "$ROOT/build-utils/xenia/verify_core.py"', script)
        subprocess.run(['bash', '-n', str(ROOT / 'build-utils/xenia/build_core.sh')], check=True)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake = root / 'ccache'
            fake.write_text('#!/bin/bash\nexit 0\n')
            fake.chmod(0o755)
            helper = ROOT / 'build-utils/xenia/ccache.sh'
            for enabled, available, count in [('1', True, 2), ('0', True, 0), ('1', False, 0)]:
                environment = dict(os.environ, XENIA_CCACHE=enabled, PATH=str(root) if available else '/nonexistent')
                # mkdir is the only external utility used by cache configuration.
                if not (root / 'mkdir').exists():
                    (root / 'mkdir').symlink_to('/bin/mkdir')
                command = f'set -euo pipefail; ROOT={root}; source {helper}; set -- ${{XENIA_CMAKE_CACHE_ARGS[@]+"${{XENIA_CMAKE_CACHE_ARGS[@]}}"}}; echo ARGS=$#; printf "%s\\n" "$@"; echo CHECK=${{CCACHE_COMPILERCHECK:-}} SLOPPINESS=${{CCACHE_SLOPPINESS:-}}'
                result = subprocess.run(['/bin/bash', '-c', command], env=environment, text=True, capture_output=True, check=True)
                self.assertIn(f'ARGS={count}', result.stdout)
                if count:
                    self.assertIn('-DCMAKE_C_COMPILER_LAUNCHER=', result.stdout)
                    self.assertIn('-DCMAKE_CXX_COMPILER_LAUNCHER=', result.stdout)
                    self.assertIn('CHECK=content SLOPPINESS=\n', result.stdout)
                    self.assertIn('elapsed seconds:', result.stdout)


if __name__ == '__main__':
    unittest.main()
