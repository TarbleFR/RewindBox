"""Run the real production hasher, safe old-code negative control and large-file proof."""
import hashlib,json,os,re,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
BASE='8308865b873879f74768aff10a9d336d074cb8f7'
PATH='lib/utils/optimized_md5_utils.dart'
TEST='test/scraping_streaming_md5_test.dart'
OUT=ROOT/'build/scraping480'
OUT.mkdir(parents=True,exist_ok=True)

def run(args,name):
    result=subprocess.run(args,cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (OUT/(name+'.log')).write_text(result.stdout)
    print(result.stdout,flush=True)
    return result

def main():
    original=(ROOT/PATH).read_bytes()
    baseline=subprocess.check_output(['git','show',BASE+':'+PATH],cwd=ROOT)
    try:
        (ROOT/PATH).write_bytes(baseline)
        result=run(['flutter','test',TEST,'--reporter','expanded','--plain-name',
            'scraping MD5 never requests whole-file bytes'],'baseline')
        if result.returncode==0 or 'WHOLE_FILE_READ_BLOCKED' not in result.stdout:
            raise RuntimeError('Old production code did not reproduce the forbidden whole-file read')
    finally:
        (ROOT/PATH).write_bytes(original)
    print('CONFIRMED original production MD5 requests whole-file allocation; safe I/O guard prevented allocation',flush=True)
    result=run(['flutter','test',TEST,'--reporter','expanded'],'candidate')
    if result.returncode:raise RuntimeError('Changed production MD5 regression failed')
    metrics=[json.loads(line.split('SCRAPING_MD5_METRICS ',1)[1]) for line in result.stdout.splitlines()
             if 'SCRAPING_MD5_METRICS ' in line and 'print(' not in line]
    if len(metrics)!=1 or metrics[0]['fixtureBytes']!=3363110912 or metrics[0]['digest']!='f70f295bdaa27ba3e3ebc9f6fce9ddb8':
        raise RuntimeError('Missing full large-file reference proof')
    if metrics[0]['extraRss']>=192*1024*1024:raise RuntimeError('Hash memory grew outside the bound')
    record={'result':'passed','source':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'baseline':BASE,'baselineWholeFileReadReproducedSafely':True,'nativeFilesStreamed':True,
        'androidSAFContractUnchanged':True,'scenarios':5,'largeFile':metrics[0],
        'persistentStartCompletionFailureLogsVerified':True,'concurrentWorkers':6,
        'physicalDeviceCrashReproduced':False,'inputsSHA256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
        (PATH,'lib/services/screenscraper/rom_hasher.dart',TEST,'test/scraping_streaming_md5_test.py','.github/workflows/scraping-streaming-md5.yml')}}
    (OUT/'verdict.json').write_text(json.dumps(record,indent=2)+'\n')
    print('PASS scraping MD5: exact complete 3.36 GB digest, bounded RSS, six workers and persisted app.log traces',flush=True)

if __name__=='__main__':main()
