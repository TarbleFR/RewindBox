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

tests = ['test/melonx_import_completion_test.dart',
         'test/melonx_presentation_widgets_test.dart',
         'test/melonx_library_files_test.dart', 'test/melonx_transfer_test.dart']
# The first CI run completed all 39 unchanged tests and the product analyzer.
# Its only failures were two new test callbacks using guarded expect() during
# pump(). The corrected callback uses expectSync(); no product source changed.
# Authenticate that evidence and rerun the changed test file, not those suites.
prior_source='6ddf9d7c8d33de468dae75cdc210073990620f3d'
prior_run=40184536490
prior_job=121142416733
for path in IMPORT_INPUTS | set(tests[1:]):
    assert subprocess.check_output(['git','show',prior_source+':'+path],cwd=ROOT) == (ROOT/path).read_bytes(), path
state=json.loads(subprocess.check_output(['gh','api',f'repos/TarbleFR/RewindBox/actions/runs/{prior_run}']))
assert state['head_sha']==prior_source and state['status']=='completed' and state['conclusion']=='failure'
logs=subprocess.check_output(['gh','api',f'repos/TarbleFR/RewindBox/actions/jobs/{prior_job}/logs'],text=True)
assert re.search(r'\+45 -2: Some tests failed',logs)
failures=logs.split('Failing tests:',1)[1].split('Traceback',1)[0]
failed_tests=re.findall(r'test/([^\n\r]+\.dart): ([^\n\r]+)',failures)
assert set(failed_tests)=={
    ('melonx_import_completion_test.dart','picker return and app resume cannot start recovery during an import'),
    ('melonx_import_completion_test.dart','update completion is explicit and does not start a library scan'),
},failed_tests
assert 'Negative control passed: the old post-import scan reopens unrelated ROM files.' in logs
print('Reusing the exact product analysis and 39 completed unchanged tests from',prior_run,flush=True)
run('flutter','analyze','--no-pub','--no-fatal-infos','test/melonx_import_completion_test.dart')
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
run('flutter', 'test', '--no-pub', '--reporter=expanded', tests[0])
out = ROOT / 'build/delivery/melonx-import535-tests.json'
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(dict(
    result='passed', tests=tests,
    negativeControl='old post-import scan reopens unrelated ROM files',
    retainedSuites=dict(source=prior_source,run=prior_run,job=prior_job,
                       tests=tests[1:],passedTests=39),
    source=subprocess.check_output(['git','rev-parse','HEAD'], cwd=ROOT, text=True).strip(),
    run=os.environ.get('GITHUB_RUN_ID'),
    inputs={p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
            for p in sorted(IMPORT_INPUTS | TEST_INPUTS)},
    physicalDeviceTested=False, nativeContentInspectionMocked=True,
), indent=2)+'\n')
