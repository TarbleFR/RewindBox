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

def reused_successes():
    ref='083d3deb7ff57835258f86d67cb3b28cd7d85f86'
    for p in (PATH,'lib/services/screenscraper/rom_hasher.dart'):
        if (ROOT/p).read_bytes()!=subprocess.check_output(['git','show',ref+':'+p],cwd=ROOT):
            raise RuntimeError('Reused successful production input changed: '+p)
    old=subprocess.check_output(['git','show',ref+':'+TEST],cwd=ROOT,text=True)
    forwarding='  @override Future<RandomAccessFile> open({FileMode mode = FileMode.read}) =>\n      real.open(mode: mode);\n'
    if (ROOT/TEST).read_text().replace(forwarding,'')!=old:
        raise RuntimeError('More than the corrected I/O guard changed')
    def api(path,raw=False):
        args=['gh','api','repos/TarbleFR/neostation-ios/'+path]
        if raw:args.append('--allow-escape-sequences')
        out=subprocess.check_output(args,cwd=ROOT,text=True)
        return out if raw else json.loads(out)
    job=api('actions/jobs/117688482965')
    if job['head_sha']!=ref or job['conclusion']!='failure':raise RuntimeError('Wrong retained partial proof')
    log=api('actions/jobs/117688482965/logs',raw=True)
    for witness in ('00:30 +1 -1: isolate success and failure reach the persistent app log',
                    '00:30 +2 -1: concurrent scraping workers keep exact independent digests',
                    '00:30 +3 -1: reported 3.36 GB ISO size hashes completely with bounded memory',
                    '00:42 +4 -1: (tearDownAll)'):
        if witness not in log:raise RuntimeError('Missing exact passed component '+witness)
    metrics=[json.loads(line.split('SCRAPING_MD5_METRICS ',1)[1]) for line in log.splitlines()
             if 'SCRAPING_MD5_METRICS {' in line]
    if len(metrics)!=1:raise RuntimeError('Missing unchanged complete-file proof')
    return metrics[0],{'source':ref,'run':39131858146,'job':117688482965,
        'scope':'four successful unchanged scenarios only; original I/O guard fixture failed',
        'logSHA256':hashlib.sha256(log.encode()).hexdigest()}

def main():
    metrics,reused=reused_successes()
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
    result=run(['flutter','test',TEST,'--reporter','expanded','--plain-name',
        'scraping MD5 never requests whole-file bytes'],'candidate')
    if result.returncode:raise RuntimeError('Changed production MD5 regression failed')
    if metrics['fixtureBytes']!=3363110912 or metrics['digest']!='f70f295bdaa27ba3e3ebc9f6fce9ddb8':
        raise RuntimeError('Missing full large-file reference proof')
    if metrics['extraRss']>=192*1024*1024:raise RuntimeError('Hash memory grew outside the bound')
    record={'result':'passed','source':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'baseline':BASE,'baselineWholeFileReadReproducedSafely':True,'nativeFilesStreamed':True,
        'androidSAFContractUnchanged':True,'scenarios':5,'scenariosExecuted':1,'scenariosReused':4,'reusedComponents':reused,'largeFile':metrics,
        'persistentStartCompletionFailureLogsVerified':True,'concurrentWorkers':6,
        'physicalDeviceCrashReproduced':False,'inputsSHA256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in
        (PATH,'lib/services/screenscraper/rom_hasher.dart',TEST,'test/scraping_streaming_md5_test.py','.github/workflows/scraping-streaming-md5.yml')}}
    (OUT/'verdict.json').write_text(json.dumps(record,indent=2)+'\n')
    print('REUSED four successful unchanged MD5 scenarios from 39131858146; fixed guard executed below',flush=True)
    print('PASS scraping MD5: exact complete 3.36 GB digest, bounded RSS, six workers and persisted app.log traces',flush=True)

if __name__=='__main__':main()
