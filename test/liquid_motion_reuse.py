"""Authenticate the unchanged successful Flutter job before two new regressions."""
import json
from pathlib import Path
import subprocess
ROOT=Path(__file__).resolve().parents[1]
BASE='3dfd2d668ae6855094d24789b0ebc4cb683047d8'
ALLOWED={'lib/widgets/native_carousel.dart','test/liquid_motion_test.dart',
    'test/liquid_motion_reuse.py','.github/workflows/motion507-checks.yml'}
changed=set(subprocess.check_output(['git','diff','--name-only',BASE,'HEAD'],text=True).splitlines())
assert not (changed-ALLOWED), sorted(changed-ALLOWED)
job=json.loads(subprocess.check_output(['gh','api','repos/TarbleFR/RewindBox/actions/jobs/120121960951'],text=True))
assert job['head_sha']==BASE and job['conclusion']=='success'
names=['Analyze the complete combined app','Exercise real tabs, console perspective, lifecycle, power and progress states',
       'Check unchanged library, display hook boundary and legal packaging']
steps=[next(s for s in job['steps'] if s['name']==name) for name in names]
assert all(s['conclusion']=='success' for s in steps)
out=ROOT/'build/bubble-review/full-flutter-reuse.json';out.parent.mkdir(parents=True,exist_ok=True)
out.write_text(json.dumps({'source':BASE,'run':39864139925,'job':job['id'],'steps':steps,
    'unchangedPhasesReused':True,'changedCarouselCasesRerun':2},indent=2)+'\n')
print('PASS: original full Flutter phase authenticated; only carousel source/fixture changed.')
