#!/usr/bin/env python3
"""Execute the audit's production helpers; LLVM proofs require the pinned host SDK."""
import argparse,json,os,shlex,shutil,subprocess,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('source',type=Path);p.add_argument('--require-llvm',action='store_true');a=p.parse_args();core=a.source.resolve()
cxx=shlex.split(os.environ.get('CXX') or shutil.which('clang++') or 'g++')
if sdk:=os.environ.get('HOST_MACOS_SDK'):cxx+=['-isysroot',sdk]
base=[*cxx,'-std=c++20','-O1','-g','-Wall','-Wextra','-Werror','-pthread','-fsanitize=address,undefined','-fno-sanitize-recover=all','-DRPCS3_IOS','-I'+str(core),'-I'+str(core/'rpcs3'),'-I'+str(ROOT/'packages/neo_swap/ios/Classes')]
def run(cmd):subprocess.run(list(map(str,cmd)),check=True,timeout=180)
with tempfile.TemporaryDirectory(prefix='rpcs3-memory-audit-') as temporary:
 work=Path(temporary)
 run([*base,ROOT/'test/native/rpcs3_memory_audit_test.cpp','-lz','-o',work/'policies']);run([work/'policies'])
 # Execute the actual core admission implementation with deterministic kernel
 # samples, including cancellation while another compiler owns the only slot.
 perf=(core/'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text();start=perf.index('namespace {\nstd::atomic<const NeoSwapCompilerAPI*> compiler_api');end=perf.index('\nvoid reset_performance_metrics()',start)
 production=perf[start:end]
 prefix='''#include "ios/IOSCompileAdmission.h"
#include "Utilities/JITPhaseProfile.h"
#include "NeoSwapCompilerBudget.h"
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <thread>
using u64=std::uint64_t;
namespace rpcs3::ios {
std::atomic<u64> footprint{100ull<<20},headroom{2ull<<30};
u64 process_memory_footprint(){return footprint.load();}
u64 available_process_memory_headroom(){return headroom.load();}
'''
 suffix='''
}
int main(){
 using namespace rpcs3::ios;
 std::atomic<bool> stopped{false};
 {
  compile_admission owner(1024,[]{return false;}); assert(owner);
  bool cancelled=false;
  std::thread waiter([&]{compile_admission next(1024,[&]{return stopped.load();}); cancelled=!next;});
  std::this_thread::sleep_for(std::chrono::milliseconds(30)); stopped=true; wake_compile_waiters(); waiter.join(); assert(cancelled);
  footprint=900ull<<20;
  { jit_phase::scope phase(jit_phase::ppu_codegen,+[]()->u64{return 10;}); }
  assert(jit_memory::footprint_peak.load()==900ull<<20);
 }
 assert(jit_memory::active.load()==0);
 assert(observed_compile_cost[10].load()>=800ull<<20);
 static neostation::compiler::budget host;
 static const NeoSwapCompilerAPI api{sizeof(api),NEOSWAP_COMPILER_ABI,+[](u64 cost,u64 room){return host.acquire(cost,room);},+[](u64 id){host.release(id);}};
 assert(rpcs3_ios_set_compiler_budget_api(&api)==0);
 assert(rpcs3_ios_set_compiler_budget_api(nullptr)==-1);
 {compile_admission first(1024,[]{return false;});assert(first);assert(host.reserved()>0);}
 assert(host.reserved()==0);
 std::cout<<"PASS actual compiler wait cancellation, in-phase peak sample, observation feedback and host binding\\n";
}
'''
 (work/'admission.cpp').write_text(prefix+production+suffix)
 run([*base,work/'admission.cpp','-o',work/'admission']);run([work/'admission'])
 # The complete new fault-before-lock prelude and the production fetch_op
 # lambda run with an injected fault that invalidates the reservation.
 spu=(core/'rpcs3/Emu/Cell/SPUThread.cpp').read_text();ppu=(core/'rpcs3/Emu/Cell/PPUThread.cpp').read_text()
 ss=spu.index('// Resolve RSX readback before owning the line;');ss=spu.rfind('#ifdef RPCS3_IOS',0,ss);se=spu.index('\n\t\tif (!_ok)',ss)
 ps=ppu.index('// A page fault may wait on RSX');ps=ppu.rfind('#ifdef RPCS3_IOS',0,ps);pe=ppu.index('\n\t\t\tif (!_ok)',ps)
 pbody=ppu[ps:pe].replace('if (ppu.use_full_rdata) [[unlikely]]\n\t\t{','if (ppu.use_full_rdata) {')+'\nreturn _ok;\n}'
 # Preserve braces: the PPU fragment opens its full-reservation branch.
 prefix='''#include <cassert>
#include <cstdint>
#include <utility>
#include <iostream>
using u64=std::uint64_t;using u32=std::uint32_t;
namespace vm{constexpr u64 rsrv_unique_lock=64;void*base(u32){return nullptr;}}
struct Reservation {u64 value=128;template<class F>auto fetch_op(F f){u64 old=value;return std::pair{old,f(value)};}} res;
u64 rtime=128;bool invalidate=false;int faults=0;
namespace utils{void trigger_write_page_fault(void*){assert(!(res.value&127));++faults;if(invalidate)res.value+=128;}}
bool spu_case(bool accurate){u32 addr=0;
'''
 text=prefix+spu[ss:se]+'\nreturn _ok;\n}\n'+'''bool ppu_case(){struct{bool use_full_rdata=true;}ppu;u32 addr=0;u64 new_data=2,old_data=1;
'''+pbody+'''\nreturn false;}
int main(){for(bool changed:{false,true}){invalidate=changed;res.value=128;assert(spu_case(true)==!changed);res.value=128;assert(ppu_case()==!changed);}assert(faults==4);std::cout<<"PASS production PPU/SPU fault preludes resolve before lock and reject an invalidated reservation\\n";}
'''
 (work/'faults.cpp').write_text(text);run([*base,work/'faults.cpp','-o',work/'faults']);run([work/'faults'])
 llvm=os.environ.get('LLVM_CONFIG') or shutil.which('llvm-config')
 if not llvm:
  if a.require_llvm:raise SystemExit('LLVM is required for the real object/link/ownership proofs')
  print('NOT RUN: LLVM object-window and minimal-link two-process proofs (LLVM SDK absent)')
 else:
  def flags(*args):return shlex.split(subprocess.check_output([llvm,*args],text=True))
  # Compile the actual bounded window, not a reimplementation of its policy.
  jit=(core/'Utilities/JITLLVM.cpp').read_text();start=jit.index('struct object_file_identity');end=jit.index('\n}\n#endif',start)
  window=jit[start:end]
  fixture='''#include <llvm/Support/MemoryBuffer.h>
#include <sys/stat.h>
#include <mutex>
#include <unordered_map>
#include <fstream>
#include <cassert>
#include <cstdio>
'''+window+'''
int main(int argc,char**argv){assert(argc==2);std::string path=argv[1];{std::ofstream f(path);f<<"original";}auto old=object_identity(path);assert(old.valid);auto&cache=validated_objects();auto buffer=llvm::MemoryBuffer::getMemBufferCopy("verified");auto*owner=buffer.get();cache.remember(path,old,std::move(buffer));assert(cache.checked(path,old));auto taken=cache.take(path,old);assert(taken.get()==owner);assert(cache.bytes==0);cache.remember(path,old,std::move(taken));{std::ofstream f(path);f<<"changed-size";}auto changed=object_identity(path);assert(changed!=old);assert(!cache.checked(path,changed));assert(!cache.take(path,changed));for(int i=0;i<20;++i)cache.remember(path+std::to_string(i),old,llvm::WritableMemoryBuffer::getNewUninitMemBuffer(4*1024*1024));assert(cache.bytes<=32*1024*1024);std::puts("PASS production validated-object ownership, file mutation rejection and 32 MiB bound");}
'''
  (work/'window.cpp').write_text(fixture)
  llvm_flags=[*cxx,*flags('--cxxflags'),'-std=c++20','-O1','-g','-I'+str(core)]
  link=flags('--ldflags','--libs','all','--system-libs')
  run([*llvm_flags,work/'window.cpp',*link,'-o',work/'window']);run([work/'window',work/'object'])
  # Existing relocation fixture provides real AArch64 objects, external helper
  # and data symbols, readonly tables and two independent ASLR processes.
  template=(ROOT/'test/native/rpcs3_spu_object_relocation_test.cpp').read_text()
  template='#include "Utilities/JITMinimalObject.h"\n'+template
  begin=template.index('\trun_result run(file_cache&');finish=template.index('\n\tstd::string record_path(',begin)
  original=template[begin:finish]
  tail=original[original.index('\n\t\tconst entry_fn fn'):]
  minimal='''
	run_result minimal_run(file_cache& cache, std::uint64_t* cell, std::uint64_t cell_value, const char* entry_name)
	{
		llvm::LLVMContext context;
		auto empty=std::make_unique<llvm::Module>(k_module,context);
		empty->setTargetTriple(llvm::Triple(k_triple));
		engine e=create(std::move(empty));
		*cell=cell_value;
		auto file=llvm::MemoryBuffer::getFile(cache.path(e.module));
		if(!file) std::exit(30);
		auto buffer=std::move(*file);
		std::string error;
		if(jit_minimal_object::add(*e.ee,buffer,entry_name,{},error) || !buffer) std::exit(31);
		std::unordered_map<std::string,std::uint64_t> bindings{{k_data_symbol,reinterpret_cast<std::uint64_t>(cell)},{k_helper_symbol,reinterpret_cast<std::uint64_t>(&reloc_helper)}};
		if(jit_minimal_object::add(*e.ee,buffer,"missing-entry",bindings,error) || !buffer) std::exit(32);
		cache.bytes=buffer->getBufferSize();
		if(!jit_minimal_object::add(*e.ee,buffer,entry_name,bindings,error)) {std::fprintf(stderr,"minimal: %s\\n",error.c_str());std::exit(33);}
		cache.loaded=true;
		e.ee->finalizeObject();
'''+tail
  template=template[:finish]+minimal+template[finish:]
  template=template.replace('if (mode == "load")','if (mode == "load" || mode == "minimal")')
  template=template.replace('run(cache, &g_cells[47],', '(mode == "minimal" ? minimal_run : run)(cache, &g_cells[47],')
  (work/'minimal.cpp').write_text(template)
  run([*llvm_flags,work/'minimal.cpp',*link,'-o',work/'minimal'])
  directory=work/'objects';directory.mkdir();run([work/'minimal','save',directory]);run([work/'minimal','minimal',directory])
  print('PASS real AArch64 minimal-object relocation without IR bodies across two processes; unknown bindings fail before mutation')
print('PASS audit implementation targeted checks; physical gameplay/performance not tested')
