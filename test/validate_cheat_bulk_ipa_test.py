"""Regression: Build366 passed compilation but a stale365 delivery gate rejected it."""
from pathlib import Path
import json,plistlib,re,subprocess,sys,tempfile,zipfile
ROOT=Path(__file__).resolve().parents[1]
# The gate expects the marketing version of pubspec.yaml (0.0.7 since Build
# 449; the literal 0.0.2 of the earlier fixture is retired with it).
VERSION=re.search(r'^version:\s*(\d+\.\d+\.\d+)\+\d+\s*$',(ROOT/'pubspec.yaml').read_text(),re.M).group(1)
TOKENS=b'cheatImportFromMenu cheatImportPreview batchImport displayDocument: importCheatFilePressed previewEntries'
with tempfile.TemporaryDirectory() as folder:
    directory=Path(folder)
    def run(build,expected=None,missing=False,version=VERSION):
        ipa=directory/'candidate.ipa';report=directory/'report.json';report.unlink(missing_ok=True)
        with zipfile.ZipFile(ipa,'w') as z:
            root='Payload/NeoStation.app/'
            z.writestr(root+'Info.plist',plistlib.dumps({'CFBundleShortVersionString':version,'CFBundleVersion':str(build)}))
            for bridge in ('dolphin_internal_bridge','armsx2_internal_bridge'):
                z.writestr(root+f'Frameworks/{bridge}.framework/{bridge}',TOKENS.replace(b'previewEntries',b'') if missing else TOKENS)
        args=[sys.executable,str(ROOT/'build-utils/validate_cheat_bulk_ipa.py'),str(ipa),'--report',str(report)]
        if expected is not None:args+=['--build-number',str(expected)]
        result=subprocess.run(args,capture_output=True,text=True)
        return result.returncode,json.loads(report.read_text()) if report.exists() else None
    assert run(365)[0]==0
    code,report=run(366,366);assert code==0 and report['build']==366
    assert run(365,366)[0]!=0
    assert run(366)[0]!=0
    assert run(366,366,missing=True)[0]!=0
    assert run(366,366,version='0.0.3')[0]!=0
    assert run(366,366,version='0.0.2')[0]!=0, 'the version of Build 448 and earlier is refused'
    assert run(366,366)[1]['version']==VERSION
print('PASS IPA gate: explicit expected build, legacy365 default, wrong build/version and missing binaries rejected')
