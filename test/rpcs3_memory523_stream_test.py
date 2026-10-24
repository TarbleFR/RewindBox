#!/usr/bin/env python3
"""Actual VM methods + actual serial/ZSTD reader; portable file/thread adapters."""
import argparse,json,os,shlex,subprocess,tempfile
from pathlib import Path
from rpcs3_memory523_test import braced
ROOT=Path(__file__).resolve().parents[1]
def program(core,before):
 pre=(ROOT/'test/native/rpcs3_savestate_harness.cpp').read_text().split('// INSERT_PRODUCTION_SERIALIZATION')[0]
 pre=pre.replace('#include <algorithm>','#include <algorithm>\n#include <span>\n#include <bit>')
 pre=pre.replace('using u32 = unsigned int;','using u32 = unsigned int;\nusing u64=std::uint64_t;')
 pre=pre.replace('struct serial {','struct serialization_file_handler;\nstruct serial {')
 pre=pre.replace('  void seek_end() { pos = data_offset + data.size(); }',r'''
  void seek_end() { pos = data_offset + data.size(); }
  serialization_file_handler* m_file_handler=nullptr;
  usz peak_size=0,peak_capacity=0;
  void sample(){peak_size=std::max(peak_size,data.size());peak_capacity=std::max(peak_capacity,data.capacity());}
  template<class F> bool raw_serialize(F&& memory_provider,usz size);
  bool raw_serialize(const void* ptr,usz size){return raw_serialize([&]{return ptr;},size);}
  void operator()(std::span<u8> out){ensure(raw_serialize(static_cast<const void*>(out.data()),out.size()));sample();}
  void operator()(u8& out){ensure(raw_serialize(static_cast<const void*>(&out),1));sample();}
  void breathe(bool forced=false);
''')
 pre=pre.replace('virtual ~serialization_file_handler() = default;','virtual ~serialization_file_handler() = default;\n  virtual bool is_null() const {return false;}')
 serial=(core/'rpcs3/util/serialization.hpp').read_text()
 raw=braced(serial,'bool raw_serialize(Func&& memory_provider, usz size)')
 raw=raw.replace('bool raw_serialize(','template<class Func> bool utils::serial::raw_serialize(',1)
 breathe=braced(serial,'void breathe(bool forced = false)').replace('void breathe(bool forced = false)','void utils::serial::breathe(bool forced)',1)
 hpp=(core/'rpcs3/util/serialization_ext.hpp').read_text();cpp=(core/'rpcs3/util/serialization_ext.cpp').read_text()
 declaration=braced(hpp,'struct compressed_zstd_serialization_file_handler :')+';'
 methods=cpp[cpp.index('struct compressed_zstd_stream_data :'):cpp.index('\nbool null_serialization_file_handler::')]
 vm=(core/'rpcs3/Emu/Memory/vm.cpp').read_text()
 return pre+'\n'+raw+'\n'+breathe+'\nstruct compressed_zstd_stream_data;\n'+declaration+'\n'+methods+r'''
using v128=u64 __attribute__((vector_size(16)));
bool gv_testz(v128 value){return !(value[0]|value[1]);}
template<class T>using le_t=T;
template<class T,class P>T read_from_ptr_unsafe(const P& p,usz o){T v;std::memcpy(&v,reinterpret_cast<const u8*>(p)+o,sizeof(v));return v;}
template<class T>T read_from_ptr(const std::vector<u8>& p,usz o){ensure(o+sizeof(T)<=p.size());return read_from_ptr_unsafe<T>(p.data(),o);}
'''+braced(vm,'static bool check_cache_line_zero(')+'\nnamespace before {\n'+braced(before,'static void serialize_memory_bytes(')+'\n}\nnamespace after {\n'+braced(vm,'static void serialize_memory_bytes(')+'\n}\n'+r'''
using Fn=void(*)(utils::serial&,u8*,usz);
std::vector<u8> image(usz bytes,unsigned pattern){
 std::vector<u8> out(bytes);u32 state=654321;
 for(usz line=0;line<bytes/128;++line)if(pattern==1||(pattern==2&&line%256<255)||(pattern==3&&line%31==0))
  for(usz j=0;j<128;++j){state^=state<<13;state^=state>>17;state^=state<<5;out[line*128+j]=state&255;}
 return out;
}
int main(){
 std::cout<<"{\"passed\":true,\"realZstd\":true,\"realSerialMethods\":true,\"cases\":[";bool comma=false;
 for(usz bytes:{usz{1048576+4096},usz{32*1048576}})for(unsigned pattern:{0u,1u,2u,3u}){
  auto input=image(bytes,pattern);utils::serial old,now;
  before::serialize_memory_bytes(old,input.data(),bytes);after::serialize_memory_bytes(now,input.data(),bytes);ensure(old.data==now.data);
  const usz body=old.data.size();std::vector<u8> suffix(3*1048576+17,0x79);old.data.insert(old.data.end(),suffix.begin(),suffix.end());
  fs::file file;file.bytes.resize(ZSTD_compressBound(old.data.size()));
  const usz compressed=ZSTD_compress(file.bytes.data(),file.bytes.size(),old.data.data(),old.data.size(),1);ensure(!ZSTD_isError(compressed));file.bytes.resize(compressed);
  usz peak[2]{};
  for(unsigned variant=0;variant<2;++variant){
   compressed_zstd_serialization_file_handler codec(file);utils::serial read;read.writing=false;read.m_file_handler=&codec;
   std::vector<u8> output(bytes);(variant?after::serialize_memory_bytes:before::serialize_memory_bytes)(read,output.data(),bytes);
   ensure(output==input&&read.pos==body);peak[variant]=read.peak_capacity;
   std::vector<u8> tail(suffix.size());read(std::span<u8>(tail));ensure(tail==suffix&&read.pos==body+suffix.size()&&codec.is_valid());
  }
  if(comma)std::cout<<',';comma=true;
  std::cout<<"{\"bytes\":"<<bytes<<",\"pattern\":"<<pattern<<",\"beforeBufferCapacity\":"<<peak[0]<<",\"afterBufferCapacity\":"<<peak[1]<<'}';
 }
 ensure(live_decoders==0);std::cout<<"]}\n";
}
'''
def run(core,before,report,sanitize):
 zstd=core/'3rdparty/zstd/zstd/lib';assert (zstd/'zstd.h').is_file()
 cc=shlex.split(os.environ.get('HOST_CC','cc'));cxx=shlex.split(os.environ.get('CXX','c++'))
 sdk=['-isysroot',os.environ['HOST_MACOS_SDK']] if os.environ.get('HOST_MACOS_SDK') else []
 flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer'] if sanitize else []
 with tempfile.TemporaryDirectory(prefix='memory523-stream-') as d:
  w=Path(d)
  if before:baseline=(before/'rpcs3/Emu/Memory/vm.cpp').read_text()
  else:
   import shutil
   baseline_root=w/'before'
   paths=json.loads((ROOT/'build-utils/rpcs3/canonical-source.json').read_text())['cell523']['paths']
   for p in paths:
    dest=baseline_root/p;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(core/p,dest)
   subprocess.run(['git','apply','--unidiff-zero','--reverse',str(ROOT/'test/fixtures/rpcs3_restore523.diff')],cwd=baseline_root,check=True)
   baseline=(baseline_root/'rpcs3/Emu/Memory/vm.cpp').read_text()
  cpp=w/'test.cpp';cpp.write_text(program(core,baseline))
  common=cxx+['-std=c++20','-O1','-g','-pthread','-DRPCS3_IOS','-I'+str(zstd),'-I'+str(core/'rpcs3/ios'),str(cpp)]
  subprocess.run(common+sdk+['-fsyntax-only'],check=True)
  objects=[]
  for src in sorted(zstd.glob('*/*.c')):
   if src.parent.name not in ('common','compress','decompress'):continue
   obj=w/(src.stem+'.o');subprocess.run(cc+['-O1','-g','-DZSTD_DISABLE_ASM','-I'+str(zstd),'-c',str(src),'-o',str(obj)]+sdk+flags,check=True);objects.append(str(obj))
  subprocess.run(common+objects+['-o',str(w/'test')]+sdk+flags,check=True)
  r=subprocess.run([str(w/'test')],capture_output=True,text=True,timeout=120,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
  if r.returncode:print(r.stderr,flush=True);r.check_returncode()
  result=json.loads(r.stdout);result.update(sanitizers=sanitize,scope='real VM+serial+ZSTD; portable files/threads; capacities are not physical RAM')
  if report:report.parent.mkdir(parents=True,exist_ok=True);report.write_text(json.dumps(result,indent=2)+'\n')
  print(json.dumps(result,indent=2))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--before',type=Path);p.add_argument('--report',type=Path);p.add_argument('--sanitize',action='store_true');a=p.parse_args();run(a.source.resolve(),a.before,a.report,a.sanitize)
