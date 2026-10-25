"""Execute changed import paths and bind the successful checks to their inputs."""
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/diagnostics'))
from melonximport535_delivery import IMPORT_INPUTS, TEST_INPUTS

def run(*args):
    subprocess.run(args, cwd=ROOT, check=True)

run('flutter', 'analyze', '--no-pub', '--no-fatal-infos', *sorted(IMPORT_INPUTS),
    'test/melonx_import_completion_test.dart')
# Reintroduce only the old awaited whole-library scan. The same real widget
# test must detect extra ROM reads; a compile error is not a negative control.
with tempfile.TemporaryDirectory(prefix='.melonx-import-control-',dir=ROOT/'test') as td:
    work=Path(td)
    widget=(ROOT/'lib/widgets/melonx_internal_playlist_actions.dart').read_text()
    assert widget.count('await onLibraryChanged();') == 1
    widget=widget.replace('await onLibraryChanged();',
        'await MelonxLibraryScanner.refresh(config);\n        await onLibraryChanged();')
    widget=re.sub(r"import '../([^']+)';",r"import 'package:neostation/\1';",widget)
    widget=re.sub(r"import '(\w+\.dart)';",r"import 'package:neostation/widgets/\1';",widget)
    (work/'old_widget.dart').write_text(widget)
    test=(ROOT/'test/melonx_import_completion_test.dart').read_text()
    test=test.replace("'package:neostation/widgets/melonx_internal_playlist_actions.dart'", "'old_widget.dart'")
    test=test.replace("'database_test_helper.dart'", "'../database_test_helper.dart'")
    (work/'old_test.dart').write_text(test)
    result=subprocess.run(['flutter','test','--no-pub','--reporter=expanded',
        '--plain-name','game appears immediately without re-scanning all existing ROM bytes',
        str(work/'old_test.dart')],cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    assert result.returncode != 0 and 'Only the selected game should be inspected' in result.stdout, result.stdout
    print('Negative control passed: the old post-import scan reopens unrelated ROM files.',flush=True)
tests = ['test/melonx_import_completion_test.dart',
         'test/melonx_presentation_widgets_test.dart',
         'test/melonx_library_files_test.dart', 'test/melonx_transfer_test.dart']
run('flutter', 'test', '--no-pub', '--reporter=expanded', *tests)
out = ROOT / 'build/delivery/melonx-import535-tests.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(dict(
    result='passed', tests=tests,
    negativeControl='old post-import scan reopens unrelated ROM files',
    source=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
    run=os.environ.get('GITHUB_RUN_ID'),
    inputs={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
            for p in sorted(IMPORT_INPUTS | TEST_INPUTS)},
    physicalDeviceTested=False, nativeContentInspectionMocked=True,
), indent=2)+'\n')
