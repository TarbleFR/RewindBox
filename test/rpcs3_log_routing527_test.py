#!/usr/bin/env python3
"""Production Core listener -> unchanged donor-host admission/budget test."""
import argparse, ast, hashlib, json, os, re, shlex, shutil, subprocess, sys, tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path,required=True);p.add_argument('--host',type=Path)
a=p.parse_args();source=a.source.resolve()
host_path=a.host or ROOT/'packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
if not host_path.exists():host_path=ROOT.parent/'RewindBox/packages/rpcs3_internal_bridge/ios/Classes/Rpcs3InternalBridgePlugin.mm'
host=host_path.read_text();core=(source/'rpcs3/ios/RPCS3IOS.cpp').read_text();performance=(source/'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text();levels=(source/'rpcs3/util/logs.hpp').read_text()
def braced(text,start):
    opening=text.index('{',start);depth=1;end=opening+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]
callback=braced(host,host.index('static void RPCS3Log(void* context, int32_t level, const char* message) {'))
admission=callback[callback.index('  const BOOL profiler ='):callback.index('  NSString* text =')].replace('return;','return false;')
assert 'if (level > 2 && !profiler && !videoArchive) return false;' in admission
assert 'if (budgetCount >= 128) allowed = NO;' in admission
assert 'if (!profiler)' in admission
listener=braced(core,core.index('class callback_log_listener final'))+';'
emit=braced(core,core.index('void emit_log(int32_t level, std::string_view message)'))
level_enum=braced(levels,levels.index('enum class level : unsigned char'))+';'
markers=('FRAMEPROF527','WAITPROF527','MEMPROF527','JITPUB527')
formats=[]
for marker in markers:
    matches=[]
    for m in re.finditer(r'ios_core_profiler\.notice\(\s*((?:"(?:\\.|[^"\\])*"\s*)+)',performance):
        fmt=''.join(ast.literal_eval(token) for token in re.findall(r'"(?:\\.|[^"\\])*"',m.group(1)))
        if marker+' ' in fmt:matches.append(fmt)
    assert len(matches)==1,(marker,matches)
    assert matches[0].startswith('COREPROF '+marker+' '),(marker,'native notice must use existing donor-host whitelist')
    formats.append(matches[0])
assert len(formats)==4
milestones='\n'.join(braced(host,host.index(prefix)) for prefix in ('static const char* RPCS3Build487MilestoneStage(', 'static BOOL RPCS3Build487AdmitBoundedLine('))
cxx=shlex.split(os.environ.get('CXX',shutil.which('clang++') or shutil.which('g++') or 'c++'))
with tempfile.TemporaryDirectory(prefix='rpcs3-routing527-') as tmp:
    tmp=Path(tmp)
    (tmp/'host_admission.inc').write_text(admission)
    (tmp/'host_milestones.inc').write_text(milestones)
    (tmp/'core_log_level.inc').write_text(level_enum)
    (tmp/'core_listener.inc').write_text(emit+'\n'+listener)
    (tmp/'core_metric_formats.inc').write_text('static constexpr std::array<std::string_view,4> core_metric_formats{'+','.join(json.dumps(s) for s in formats)+'};\n')
    command=cxx+['-std=c++20','-O2','-Wall','-Wextra','-Werror','-I',str(tmp),str(ROOT/'test/native/rpcs3_log_routing527.cpp'),'-o',str(tmp/'routing')]
    if sdk:=os.environ.get('HOST_MACOS_SDK'):command+=['-isysroot',sdk]
    subprocess.run(command,check=True)
    run=subprocess.run([str(tmp/'routing')],text=True,capture_output=True)
    print(run.stdout,end='');print(run.stderr,end='',file=sys.stderr);run.check_returncode()
    files=[source/'rpcs3/ios/RPCS3IOS.cpp',source/'rpcs3/ios/RPCS3IOSPerformance.cpp',source/'rpcs3/util/logs.hpp',host_path]
    result={'schema':1,'passed':True,'physical_device_tested':False,'notice_level':6,'formats':formats,'core_listener':'production bodies with message-storage/fmt/platform shims','host_admission':'production whitelist, level filter and128/s ordinary budget','milestones':'production stage/bounded-line functions','compiler':subprocess.check_output(cxx+['--version'],text=True),'command':command,'output':run.stdout,'input_sha256':{str(x):hashlib.sha256(x.read_bytes()).hexdigest() for x in files}}
    a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(result,indent=2)+'\n')
