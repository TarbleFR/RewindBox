"""Reuse successful branding components only with identical production inputs."""
import json, os, re, subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPO='TarbleFR/RewindBox'
PINS=[('71beb60d15b4d27d272624fae6b8fa60eb2471bf',119301920768,True),
      ('49399efeb966b9f8b06728e88436b8db5f634e79',119301898341,False)]
CHANGED={'test/rewindbox_branding_reuse.py','test/rewindbox_branding_followup_test.py',
         '.github/workflows/rewindbox-branding-check.yml',
         'docs/evidence/rewindbox-followup-2026-10-21.json',
         'test/library_ui_local_view_test.dart','test/library_ui_sources_view_test.dart',
         'test/libretro_engine_settings_test.dart','test/rpcs3_loader_stability_280_test.py',
         'test/rpcs3_reporter_send_order_test.py','test/neoswap_managed_swap_host_test.py'}
def output(reused):
    with open(os.environ['GITHUB_OUTPUT'],'a',encoding='utf-8') as f:
        f.write('reused='+str(reused).lower()+'\n')
def command(*args): return subprocess.check_output(args,cwd=ROOT,text=True,encoding='utf-8')
def labels(source):
    return '\n'.join(re.sub(r'\bNeoStation(?: iOS)?\b','RewindBox',line,flags=re.I)
        if re.match(r'^\s*(?:-\s*)?(?:name|run-name|ARTIFACT_NAME):',line)
        else line for line in source.split('\n'))
def main():
    for source,job,skin in PINS:
        if subprocess.run(['git','merge-base','--is-ancestor',source,'HEAD'],cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
            continue
        changed=set(command('git','diff','--name-only',source,'HEAD').splitlines())
        extra=changed-CHANGED
        for name in list(extra):
            if name.startswith('.github/workflows/') and name.endswith('.yml'):
                old=command('git','show',source+':'+name)
                if labels(old)==(ROOT/name).read_text(encoding='utf-8'): extra.remove(name)
        workflow='.github/workflows/rewindbox-branding-check.yml'
        pinned="flutter-version: '3.47.2'"
        if extra or pinned not in command('git','show',source+':'+workflow) or pinned not in (ROOT/workflow).read_text(encoding='utf-8'):
            print('Inputs or toolchain changed: execute the complete targeted suite.')
            output(False); return
        metadata=json.loads(command('gh','api',f'repos/{REPO}/actions/jobs/{job}'))
        assert metadata['head_sha']==source and metadata['status']=='completed'
        assert metadata['conclusion']=='success'
        required={'Analyze the complete application','Verify unchanged successful test components','Test corrected wordmark and BIOS fixtures'}
        assert all(any(s['name']==name and s['conclusion']=='success' for s in metadata['steps']) for name in required)
        retained=['rewindbox_wordmark_test.dart','libretro_bios_check_service_test.dart',
                  'libretro_bios_checker_screen_test.dart','startup_locale_test.dart',
                  'app_locale_ko_test.dart','legal_credits_dialog_test.dart']
        if skin: retained.append('libretro_skin_catalogs_test.dart')
        for name in retained:
            assert command('git','show',source+':test/'+name)==(ROOT/'test'/name).read_text(encoding='utf-8')
        print(json.dumps({'reused_successful_job':job,'tested_source':source,
              'retained_test_files':retained,'all_production_inputs_identical':True,
              'new_tests_run_separately':True,'toolchain':'Flutter 3.47.2'}))
        output(True); return
    print('No reviewed ancestor: execute the complete targeted suite.')
    output(False)
if __name__=='__main__': main()
