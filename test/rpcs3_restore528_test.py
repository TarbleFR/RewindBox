#!/usr/bin/env python3
"""Execute delivered527/candidate FD constructors and the real FXO template.

Guest file/mount adapters substitute filesystem access; archive bytes/layouts
and production constructors are exact. No guest restore or phone is claimed.
"""
import argparse, hashlib, json, os, shlex, subprocess, tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
ROOT=Path(__file__).resolve().parents[1]
BASE='6c6604a70a6837b4d461618b90a791934d6c65b3'
FS='rpcs3/Emu/Cell/lv2/sys_fs.cpp'

def main():
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--report',type=Path);a=p.parse_args();src=a.source.resolve()
 cxx=shlex.split(os.environ.get('CXX','c++'))
 if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
 env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1')
 before_manifest=json.loads(subprocess.check_output(['git','show',BASE+':build-utils/rpcs3/canonical-source.json'],cwd=ROOT))
 results={}
 with tempfile.TemporaryDirectory(prefix='restore528-') as temp:
  w=Path(temp);base=w/'native527';f=base/FS;f.parent.mkdir(parents=True)
  f.write_bytes(subprocess.check_output(['git','show',before_manifest['upstream_commit']+':'+FS],cwd=src))
  patch=w/'before.patch';patch.write_bytes(subprocess.check_output(['git','show',BASE+':build-utils/rpcs3/embedded-core.patch'],cwd=ROOT))
  subprocess.run(['git','apply','--include',FS,str(patch)],cwd=base,check=True)
  assert hashlib.sha256(f.read_bytes()).hexdigest()==before_manifest['files_sha256'][FS]
  headers={'layout.inc':braced((src/'Utilities/File.h').read_text(),'\tstruct stat_t\n')+';\n',
   'enum.inc':braced((src/'rpcs3/Emu/Cell/lv2/sys_fs.h').read_text(),'enum class lv2_file_type\n')+';\n'+braced((src/'rpcs3/Emu/Cell/ErrorCodes.h').read_text(),'enum CellError : u32\n')+';\n',
   'open-result.inc':braced((src/'rpcs3/Emu/Cell/lv2/sys_fs.h').read_text(),'\tstruct open_result_t\n')+';\n'}
  for name,text in headers.items():(w/name).write_text(text)
  for name,text in [('before',f.read_text()),('after',(src/FS).read_text())]:
   body='\n'.join(braced(text,t) for t in ['static auto lv2_fs_restore_name(','static u64 lv2_fs_restore_path_class(','lv2_fs_object::lv2_fs_object(utils::serial& ar, bool)','lv2_file::lv2_file(utils::serial& ar)'])
   (w/(name+'.inc')).write_text(body)
  harness=(ROOT/'test/native/rpcs3_fs_diagnostic526.cpp').read_text()
  harness=harness.replace('#include "util/types.hpp"','#include "util/types.hpp"\n#include "ios/IOSRestoreFailure.h"')
  harness=harness.replace('#ifdef FS_BASELINE\n#include "before.inc"','#ifdef RESTORE_REFERENCE\n#include "before.inc"')
  harness=harness.replace('    events.clear();lookups=opens=errors=successes=0;', '    rpcs3::ios::restore_failure::reset();\n    events.clear();lookups=opens=errors=successes=0;')
  old='observed_archive=&ar;saved_archive=ar.data;lv2_file file(ar);return 99;'
  new='''observed_archive=&ar;saved_archive=ar.data;lv2_file file(ar);
#ifndef RESTORE_REFERENCE
        if(failure_mode.starts_with("unavailable-")) {
            const auto& missing=rpcs3::ios::restore_failure::current;
            ensure(missing.active&&missing.id==3&&missing.error==CELL_ENOENT);
            ensure(std::string_view(missing.disc_path.data())=="/dev_bdvd/PS3_GAME/USRDIR/test.bin");
            ensure(ar.data==saved_archive&&ar.pos==saved_archive.size()-8);
            ensure(!file.file&&file.file.seek_pos==-1&&!has("file_seek_begin")&&!has("file_ready"));
            ensure(opens==1&&lookups==1&&errors==2&&successes==0);
            std::cout<<"PASS recoverable missing disc FD; original bytes unchanged; no seek, fallback or guest resume\\n";return 0;
        }
#endif
        return 99;'''
  assert old in harness;harness=harness.replace(old,new)
  (w/'fs.cpp').write_text(harness)
  common=cxx+['-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-DRPCS3_IOS','-I'+str(w),'-I'+str(src/'rpcs3')]
  for variant in ['before','after']:
   cmd=common+(['-DRESTORE_REFERENCE'] if variant=='before' else [])+[str(w/'fs.cpp')];exe=w/variant
   subprocess.run(cmd+['-fsanitize=address,undefined','-fno-omit-frame-pointer','-o',str(exe)],check=True)
   records={}
   for mode in [None,'unavailable-regular','unavailable-sdata','unavailable-edata','unterminated','truncated-seek','truncated-memory']:
    out=subprocess.run([str(exe)]+([mode] if mode else []),capture_output=True,text=True,timeout=60,env=env)
    expected=0 if mode is None or (variant=='after' and mode.startswith('unavailable-')) else 91 if mode.startswith('unavailable-') else 88 if mode=='unterminated' else 92
    assert out.returncode==expected,(variant,mode,out.returncode,out.stdout,out.stderr)
    assert 'AddressSanitizer' not in out.stderr and 'runtime error:' not in out.stderr,out.stderr
    records[mode or 'valid']={'exit':out.returncode,'stdout':out.stdout,'stderr':out.stderr}
   subprocess.run(cmd+['-fno-exceptions','-fsyntax-only'],check=True);results[variant]=records
  assert json.loads(results['before']['valid']['stdout'])==json.loads(results['after']['valid']['stdout'])
  # The production header is compiled, not an adapter for its ordering or flags.
  subprocess.run(common+['-pthread',str(ROOT/'test/native/rpcs3_fxo528.cpp'),'-fsanitize=address,undefined','-fno-omit-frame-pointer','-o',str(w/'fxo')],check=True)
  fxo=subprocess.run([str(w/'fxo')],capture_output=True,text=True,timeout=60,env=env);assert fxo.returncode==0,(fxo.stdout,fxo.stderr)
  subprocess.run(common+['-pthread',str(ROOT/'test/native/rpcs3_fxo528.cpp'),'-fno-exceptions','-fsyntax-only'],check=True)
  # Compile the unchanged reference header with the new fixture as a negative
  # control: it reads the next tag/constructs later objects before reporting.
  old_fixed=w/'reference/util/fixed_typemap.hpp';old_fixed.parent.mkdir(parents=True)
  text=subprocess.check_output(['git','show',before_manifest['upstream_commit']+':rpcs3/util/fixed_typemap.hpp'],cwd=src)
  old_fixed.write_bytes(text);
  # Delivered527 template differs from upstream; reconstruct it through its exact delta.
  old_fixed.write_bytes(subprocess.check_output(['git','show',before_manifest['upstream_commit']+':rpcs3/util/fixed_typemap.hpp'],cwd=src))
  native_old=base/'rpcs3/util/fixed_typemap.hpp';native_old.parent.mkdir(parents=True,exist_ok=True);native_old.write_bytes(old_fixed.read_bytes())
  subprocess.run(['git','apply','--include','rpcs3/util/fixed_typemap.hpp',str(patch)],cwd=base,check=True)
  assert hashlib.sha256(native_old.read_bytes()).hexdigest()==before_manifest['files_sha256']['rpcs3/util/fixed_typemap.hpp']
  old_fixed.write_bytes(native_old.read_bytes())
  subprocess.run(cxx+['-I'+str(w/'reference')]+common[len(cxx):]+['-DRESTORE_REFERENCE','-pthread',str(ROOT/'test/native/rpcs3_fxo528.cpp'),'-o',str(w/'fxo-old')],check=True)
  negative=subprocess.run([str(w/'fxo-old')],capture_output=True,text=True,timeout=60);assert negative.returncode==17,(negative.returncode,negative.stdout,negative.stderr)
  report={'passed':True,'baseline':BASE,'physicalDeviceTested':False,'realGameRestored':False,'sanitized':True,'noExceptionsSyntaxVerified':True,'fdCases':results,'fxo':fxo.stdout,'fxoNegativeControl':negative.stdout,'scope':'production constructors and actual FXO header; controlled filesystem/serial/thread-op adapters; native Core build and iPhone follow-up still required'}
  for name in ['rpcs3/util/fixed_typemap.hpp','rpcs3/Emu/IdManager.h','rpcs3/Emu/System.cpp','rpcs3/Emu/Cell/PPUModule.cpp']:
   assert 'restore_failure::failed()' in (src/name).read_text(),name
 if a.report:a.report.parent.mkdir(parents=True,exist_ok=True);a.report.write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report,indent=2))
if __name__=='__main__':main()
