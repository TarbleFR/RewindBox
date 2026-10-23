"""Execute selected production regions with explicit portable I/O/SDK adapters.

These are host behavioral fixtures, not an iPhone or full emulator test.
"""
import argparse
import json
import hashlib
import shlex
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

BASE = Path(__file__).resolve().parent
FIXTURE = BASE / 'fixtures/rpcs3_gow3_restore.diff'
EXPECTED = {'rpcs3/Loader/TAR.cpp': {'beforeSHA256': '21694ca8a4a512bbf3764d1d3c714984fce700f622e3d9f0231d558ee43f0432', 'proposedSHA256': '8a77b61d7a6bc292e22cb14170737a1780e9b30ba8b493c2bdbd041e671b4c8a'}, 'rpcs3/ios/RPCS3IOSPerformance.cpp': {'beforeSHA256': 'ce0b1cc7f6aab878f9a6a239d1ba2a9c08294eac696fb5e5efc26df94866ff51', 'proposedSHA256': 'a2b96ba798ec5a8cf946129dfea64ff8d7ae45d9f4e8be11e9d7928ad20aa800'}, 'rpcs3/ios/RPCS3IOSProfilerHelpers.h': {'beforeSHA256': '82124f62d099b22702f57caa0656becbec7913772ca5859e95fe639ab9df620e', 'proposedSHA256': 'd11297d9ac5025a8335b4ff18215a0222f63a90f8f95c4c6bc4ee72bb740ea83'}}

def braced(text, start):
    first = text.index('{', start)
    depth = 1
    end = first + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

PREAMBLE = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <functional>
#include <iostream>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <thread>
#include <utility>
#include <vector>
using usz=std::size_t; using u8=std::uint8_t;
template<class T> using atomic_t=std::atomic<T>;
namespace utils { template<class T> T aligned_div(T a,T b){return a/b+(a%b!=0);} }
#define ensure(x) assert(x)
namespace thread_ctrl { void wait_for(usz us){std::this_thread::sleep_for(std::chrono::microseconds(us));} }
template<class F> struct named_thread {
 std::thread thread;
 named_thread(std::string_view,F f):thread(std::move(f)){}
 void operator()(){if(thread.joinable())thread.join();}
 ~named_thread(){operator()();}
};
static u8 pattern(usz offset){return static_cast<u8>((offset*13+(offset>>12)*7)%251);}
struct reader {
 usz pos=0, data_offset=0, total, peak=0, releases=0;
 std::vector<u8> data;
 explicit reader(usz n):total(n){}
 usz get_size() const{return total;}
 usz try_read(std::span<u8> output){
  if(output.size()>total-pos)return output.size()-(total-pos);
  if(pos+output.size()>data_offset+data.size()){
   const usz required=pos+output.size()-data_offset;
   const usz size=std::min(total-data_offset,std::max(data.capacity(),required+output.size()/2));
   usz previous=data.size();data.resize(size);
   for(usz i=previous;i<size;i++)data[i]=pattern(data_offset+i);
   peak=std::max(peak,data.capacity());
  }
  if(output.size())std::memcpy(output.data(),data.data()+pos-data_offset,output.size());
  pos+=output.size();return 0;
 }
 // Portable adapter for the production serial::breathe guard and zstd reader's
 // consumed-prefix policy. It keeps actual vector bytes; no physical-RSS claim.
 void breathe(bool forced=false){
  if(!forced && data.size()<0x1000000 && pos>=data_offset)return;
  ++releases;const usz limit=data_offset+data.size();
  if(pos>data_offset && pos<limit){
   const usz consumed=pos-data_offset, left=limit-pos;
   if(consumed>=0x500000 || (consumed>=0x200000 && left/consumed<3)){
    data_offset+=consumed;data.erase(data.begin(),data.begin()+consumed);
    if(data.capacity()>=0x2000000)data.shrink_to_fit();
   }
   return;
  }
  data_offset+=data.size();assert(pos>=data_offset);data.clear();
  if(data.capacity()>=0x2000000)data.shrink_to_fit();
 }
};
struct sink {
 usz pos=0;
 void write(const u8* data,usz n){for(usz i=0;i<n;i++)assert(data[i]==pattern(pos+i));pos+=n;}
};
'''

def tar_program(root, fixed):
    text=(root/'rpcs3/Loader/TAR.cpp').read_text()
    start=text.index('#ifdef RPCS3_IOS\n\t\t\t// REWINDBOX_GOW3_TAR_WINDOW_V1') if fixed else text.index('\t\t\tconstexpr usz chunk_size =')
    end=text.index('\n\n\t\t\tif (should_ignore)',start)
    constants=text[start:end]
    start=text.index('for (usz i = 0; i < std::min<usz>(utils::aligned_div<usz>(filesize, chunk_size), chunk_count); i++)')
    allocate=braced(text,start)
    start=text.index('std::unique_ptr<named_thread<std::function<void()>>> async_reader;')
    end=text.index('\n\t\t\t\tfile.close();',start)
    loop=text[start:end]
    return PREAMBLE + '\nvoid run(usz filesize,bool streaming){\n' + r'''
 std::vector<std::vector<u8>> filedata_buffers;
 auto file_data=std::make_unique<reader>(filesize);
 bool should_ignore=false;void* m_ar=streaming?reinterpret_cast<void*>(1):nullptr;
 sink file;
''' + constants + '\n' + allocate + '\n' + loop + r'''
 assert(file.pos==filesize);assert(file_data->pos==filesize);
 usz ring=0;for(auto& item:filedata_buffers)ring+=item.size();
#if defined(RPCS3_IOS) && defined(FIXED)
 assert(ring<=4*1024*1024);
 if(streaming){assert(file_data->peak<=16*1024*1024);if(filesize)assert(file_data->releases>0);}
 else assert(file_data->releases==0);
#else
 assert(file_data->releases==0);
 if(filesize>=64*1024*1024)assert(file_data->peak>=filesize);
#endif
 if(filesize>=64*1024*1024)std::cout<<"retained_serial_capacity="<<file_data->peak<<" ring_bytes="<<ring<<" releases="<<file_data->releases<<" streaming="<<streaming<<"\n";
}
int main(){
 for(auto n:{usz{0},usz{1},usz{1048575},usz{1048576},usz{1048577},usz{4194304},usz{4194321},usz{8388608},usz{8388625}})run(n,true);
 run(64*1024*1024+123,true);
#if defined(RPCS3_IOS) && defined(FIXED)
 run(257*1024*1024+123,true);
 run(17*1024*1024+31,false);
#endif
 std::cout<<"PASS production TAR ring/read loop: bytes, chunk boundaries, wraparound, scope and retained-buffer bound\n";
}
'''

def profiler_program(root, fixed):
    text=(root/'rpcs3/ios/RPCS3IOSPerformance.cpp').read_text()
    function=braced(text,text.index('core_group classify_thread('))
    return PREAMBLE + '#include "'+str(root/'rpcs3/ios/RPCS3IOSProfilerHelpers.h')+'"\n'+r'''
enum class core_group{ppu,spu,rsx,jit,other,count};
''' + function + r'''
int main(){
 using namespace rpcs3::ios::profiler;
#ifdef FIXED
 assert(classify_thread("LLVM JIT")==core_group::jit);assert(is_transient_compile_thread("LLVM JIT"));
#else
 assert(classify_thread("LLVM JIT")==core_group::other);assert(!is_transient_compile_thread("LLVM JIT"));
#endif
 for(auto name:{"PPUW.1","PPU Exec 1","PPU Symbol 1","SPU Worker 1"}){assert(classify_thread(name)==core_group::jit);assert(is_transient_compile_thread(name));}
 for(auto name:{"SPUW.1","SPU LLVM","RSX.W1"}){assert(classify_thread(name)==core_group::jit);assert(!is_transient_compile_thread(name));}
 assert(classify_thread("PPU[0x1000000]")==core_group::ppu);
 assert(classify_thread("SPU[0x2000000]")==core_group::spu);
 assert(classify_thread("RawSPU 1")==core_group::spu);
 assert(classify_thread("rsx::thread")==core_group::rsx);
 assert(classify_thread("RSX Worker 1")==core_group::rsx);
 assert(classify_thread("TAR Extract File Thread")==core_group::other);
 assert(classify_thread("LLVM unrelated utility")==core_group::other);
 std::cout<<"PASS production CPU classifier and transient-worker helper\n";
}
'''

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--sanitize',action='store_true')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    candidate=args.source.resolve()
    results=[]
    with tempfile.TemporaryDirectory() as temporary:
        temp=Path(temporary)
        before=temp/'before'
        for relative, expected in EXPECTED.items():
            data=(candidate/relative).read_bytes()
            assert hashlib.sha256(data).hexdigest()==expected['proposedSHA256'], relative
            dest=before/relative
            dest.parent.mkdir(parents=True,exist_ok=True)
            dest.write_bytes(data)
        subprocess.run(['git','apply','--reverse',str(FIXTURE)],cwd=before,check=True)
        for relative,expected in EXPECTED.items():
            assert hashlib.sha256((before/relative).read_bytes()).hexdigest()==expected['beforeSHA256'], relative
        for name,root,fixed,ios in [('before',before,False,True),('candidate-ios',candidate,True,True),('candidate-desktop',candidate,True,False)]:
            programs=[('tar',tar_program(root,fixed))]
            if name!='candidate-desktop': programs.append(('profiler',profiler_program(root,fixed)))
            for kind,program in programs:
                source=temp/(name+'-'+kind+'.cpp');binary=source.with_suffix('');source.write_text(program)
                compiler=os.environ.get('CXX') or shutil.which('clang++') or shutil.which('g++')
                assert compiler, 'A C++20 compiler is required'
                cmd=shlex.split(compiler)+['-std=c++20','-O1','-g','-pthread',str(source),'-o',str(binary)]
                if os.environ.get('HOST_MACOS_SDK'): cmd+=['-isysroot',os.environ['HOST_MACOS_SDK']]
                if fixed:cmd+=['-DFIXED']
                if ios:cmd+=['-DRPCS3_IOS']
                if args.sanitize:cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
                subprocess.run(cmd,check=True,timeout=90)
                result=subprocess.run([str(binary)],check=True,timeout=90,text=True,stdout=subprocess.PIPE)
                results.append({'variant':name,'fixture':kind,'stdout':result.stdout.strip()})
    record={'passed':True,'scope':'production excerpts; portable SDK/I-O doubles; no full emulator/device validation',
        'sanitizers':args.sanitize,'testedRuntimeSourceHashes':{p:v['proposedSHA256'] for p,v in EXPECTED.items()},'cases':results}
    if args.report:
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.write_text(json.dumps(record,indent=2)+'\n')
    print(json.dumps(record,indent=2))
    print('PASS God of War III restore/profiler regressions')

if __name__=='__main__':main()
