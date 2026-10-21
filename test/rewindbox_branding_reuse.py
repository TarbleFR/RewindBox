"""Reuse passed components only when their entire repository input stays identical."""
import json, os, re, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO='TarbleFR/RewindBox'
PINS=[('5aa37461e048a37d311b295ad21cb1b0d4438502',119297551844,True),
      ('6cf406a5939dd0c95eac7dea1adbfa93774769c8',119298293420,False)]
CHANGED={'test/rewindbox_wordmark_test.dart','test/libretro_bios_check_service_test.dart',
         'test/rewindbox_branding_reuse.py','.github/workflows/rewindbox-branding-check.yml',
         'docs/evidence/rewindbox-followup-2026-10-21.json'}
FAILED={'rewindbox_wordmark_test.dart','libretro_bios_check_service_test.dart'}
def output(reused):
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
        f.write('reused='+str(reused).lower()+'\n')
def command(*args): return subprocess.check_output(args,cwd=ROOT,text=True,encoding='utf-8')
def job_log(job):
    args=['gh','api',f'repos/{REPO}/actions/jobs/{job}/logs']
    result=subprocess.run(args,cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    if result.returncode and 'pass --allow-escape-sequences' in result.stderr:
        # Capture as data only. Never print or execute terminal control bytes.
        result=subprocess.run(args+['--allow-escape-sequences'],cwd=ROOT,capture_output=True,text=True,encoding='utf-8')
    if result.returncode: raise RuntimeError('Cannot retrieve the prior job evidence')
    return result.stdout

def main():
    for source,job,skin in PINS:
        if subprocess.run(['git','merge-base','--is-ancestor',source,'HEAD'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            continue
        changed=set(command('git','diff','--name-only',source,'HEAD').splitlines())
        if not changed <= CHANGED:
            print('Inputs changed outside the reviewed fixture repair; execute the complete targeted suite.')
            output(False); return
        metadata=json.loads(command('gh','api',f'repos/{REPO}/actions/jobs/{job}'))
        assert metadata['head_sha']==source and metadata['status']=='completed'
        assert metadata['conclusion']=='failure', 'Retain the actual failed overall outcome'
        assert any(s['name']=='Analyze the complete application' and s['conclusion']=='success' for s in metadata['steps'])
        log=job_log(job)
        failures=set(re.findall(r'##\[group\].*❌[^\n]*/test/([^:\n]+\.dart):',log))
        assert failures==FAILED, ('Unexpected failed test files',failures)
        assert re.search(r'\d+ tests passed, 12 failed\.',log), 'Incomplete previous run'
        retained=['libretro_bios_checker_screen_test.dart','startup_locale_test.dart','app_locale_ko_test.dart','legal_credits_dialog_test.dart']
        if skin: retained.append('libretro_skin_catalogs_test.dart')
        for name in retained:
            assert re.search(r'✅[^\n]*/test/'+re.escape(name)+r':',log), ('No passing evidence',name)
            assert (ROOT/'test'/name).is_file()
        print(json.dumps({'reused_successful_components_from_failed_job':job,'tested_source':source,
              'retained_test_files':retained,'all_other_repository_inputs_identical':True,
              'rerun_files':sorted(FAILED),'old_job_is_not_reclassified_as_success':True}))
        output(True); return
    print('No reviewed ancestor: execute the complete targeted suite.')
    output(False)
if __name__=='__main__': main()
