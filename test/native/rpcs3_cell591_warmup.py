#!/usr/bin/env python3
"""Execute the actual shader-cache load/FP-read bodies with joined host workers.

The adapters replace Vulkan and the game's file index. The real lf_fifo and
RSXFragmentProgram ownership helpers are extracted verbatim from upstream.
No iPhone memory/FPS result is inferred.
"""
from pathlib import Path
import argparse, hashlib, json, os, re, subprocess, tempfile

ROOT = Path(__file__).resolve().parents[2]

def braced(text, start):
    assert text.count(start) == 1, start
    a = text.index(start); b = text.index('{', a) + 1; depth = 1
    while depth:
        depth += (text[b] == '{') - (text[b] == '}'); b += 1
    return text[a:b]

PREFIX = r'''
#define RPCS3_IOS 1
#include <algorithm>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>
using usz=std::size_t;using u64=std::uint64_t;using u32=std::uint32_t;using u8=std::uint8_t;
#define ensure(x) assert(x)
template<class T> T narrow(auto x) { assert(x <= std::numeric_limits<T>::max());return static_cast<T>(x); }
inline u32 size32(const auto& x) { return narrow<u32>(x.size()); }
// Serialized atomic API adapter. raw() is used only during destruction after joins.
template<class T> class atomic_t {
 mutable std::mutex mutex; T value{};
public:
 atomic_t()=default; atomic_t(T v):value(v) {}
 T load() const { std::lock_guard lock(mutex);return value; }
 operator T() const {return load();}
 T& raw() {return value;}
 T fetch_add(T n) { std::lock_guard lock(mutex);return std::exchange(value,value+n); }
 T compare_and_swap(T before,T after) { std::lock_guard lock(mutex);T old=value;if(old==before)value=after;return old; }
 template<class F> auto atomic_op(F f) { std::lock_guard lock(mutex);return f(value); }
};
'''

ADAPTER = r'''
namespace fs {
struct dir_entry { std::string name;bool is_directory=false; };
struct dir {
 std::vector<dir_entry> entries;
 explicit dir(const std::string& path) { if(std::filesystem::is_directory(path)) for(auto& e:std::filesystem::directory_iterator(path)) entries.push_back({e.path().filename().string(),e.is_directory()}); }
 explicit operator bool() const { return true; }
 auto begin() {return entries.begin();} auto end() {return entries.end();} void rewind() {}
};
inline void create_path(const std::string& p) {std::filesystem::create_directories(p);}
inline void remove_file(const std::string& p) {std::filesystem::remove(p);}
struct file {
 std::ifstream f;explicit file(const std::string& p):f(p,std::ios::binary) {}
 explicit operator bool() const {return f.is_open();}
 u64 size() {auto pos=f.tellg();f.seekg(0,std::ios::end);auto n=f.tellg();f.seekg(pos);return static_cast<u64>(n);}
 u64 read(void* p,usz n) {f.read(static_cast<char*>(p),n);return static_cast<u64>(f.gcount());}
 void close() {f.close();}
};
}
namespace fmt {
inline const char* printable(const std::string& s) {return s.c_str();}
template<class T> auto printable(T v) {if constexpr(std::is_integral_v<T>) return static_cast<unsigned long long>(v);else return v;}
template<class... T> std::string format(const char* pattern,const T&... v) {char out[1024];std::snprintf(out,sizeof(out),pattern,printable(v)...);return out;} }
enum class video_renderer {vulkan};
inline struct {struct {video_renderer renderer=video_renderer::vulkan;}video;}g_cfg;
namespace utils {inline unsigned get_thread_count() {return 4;}}
inline struct {bool stopped=false;bool IsStopped() const {return stopped;}}Emu;
struct shader_loading_dialog {void create(auto&&...) {}void set_limit(auto&&...) {}void update_msg(auto&&...) {}void set_value(auto&&...) {}void refresh() {}void close() {}};
inline std::string get_message(auto&&...) {return {};}
struct Fragment {
 // DATA_HELPER
 mutable data_storage_helper data{};u32 ucode_length=0;
 // GET_DATA
 // CLONE_DATA
};
struct borrowed {Fragment fp;std::vector<u8> expected;};
using unpacked_type=std::vector<borrowed>;
class Cache {
 std::string version_prefix="test",root_path,pipeline_class_name="vulkan";
 lf_fifo<std::unique_ptr<u8[]>,100> fragment_program_data;
 static constexpr u64 maximum_raw_shader_size=0x100000;
public:
 std::vector<Fragment> owned_programs;
 unsigned workers_joined=0, reads=0;bool cancelled=false;
 explicit Cache(std::string path):root_path(std::move(path)) {}
 // LOAD_FP
 void load_shaders(unsigned,unpacked_type& unpacked,std::string&,std::vector<fs::dir_entry>& entries,u32,shader_loading_dialog*) {
   std::mutex result_mutex;
   std::vector<std::thread> workers;
   for(unsigned w=0;w<4;++w) workers.emplace_back([&,w] {
     for(usz n=w;n<entries.size();n+=4) {
       auto f=load_fp_raw(n%3+1);assert(f.ucode_length==8192);
       auto* p=static_cast<const u8*>(f.get_data());std::vector<u8> expected(p,p+f.ucode_length);
       // Actual ownership operation made by search_fragment_program before Compile.
       Fragment clone=f;clone.clone_data();
       std::lock_guard lock(result_mutex);owned_programs.push_back(std::move(clone));unpacked.push_back({std::move(f),std::move(expected)});
     }
   });
   for(auto& worker:workers) { worker.join(); }
   ++workers_joined;
   if(cancelled)Emu.stopped=true;
 }
 template<class... A> void compile_shaders(unsigned,unpacked_type& unpacked,u32,shader_loading_dialog*,A&&...) {
   std::vector<std::thread> workers;
   for(unsigned w=0;w<4;++w) workers.emplace_back([&,w] {
     for(usz n=w;n<unpacked.size();n+=4) {
       auto& b=unpacked[n];std::this_thread::sleep_for(std::chrono::microseconds(50));
       // The inline pipeline build may still read every borrowed byte.
       assert(!std::memcmp(b.fp.get_data(),b.expected.data(),b.expected.size()));
     }
   });
   for(auto& worker:workers) { worker.join(); }
   ++workers_joined;
 }
 usz held() {usz n=0;fragment_program_data.for_each([&](auto& b){n+=bool(b);});return n;}
 u32 queue_size() const {return fragment_program_data.size();}
 // LOAD
 void verify_owned() const {for(auto& f:owned_programs){auto* p=static_cast<const u8*>(f.get_data());assert(p&&f.ucode_length==8192);for(usz i=0;i<f.ucode_length;++i) assert(p[i]==u8((p[0]+i)%251));}}
};
'''

def namespace(name, cache, fifo, fragment):
    text = ADAPTER.replace('// DATA_HELPER', braced(fragment, 'struct data_storage_helper\n')+';')
    text = text.replace('// GET_DATA', braced(fragment, 'void* get_data() const'))
    text = text.replace('// CLONE_DATA', braced(fragment, 'void clone_data() const'))
    text = text.replace('// LOAD_FP', braced(cache, 'RSXFragmentProgram load_fp_raw(').replace('RSXFragmentProgram','Fragment'))
    text = text.replace('// LOAD', braced(cache, 'void load(shader_loading_dialog* dlg, Args&& ...args)'))
    # The omitted template prefix is restored exactly at the extracted method boundary.
    text = text.replace('void load(shader_loading_dialog* dlg, Args&& ...args)', 'template<class... Args> void load(shader_loading_dialog* dlg, Args&& ...args)')
    return 'namespace '+name+' {\n'+fifo+'\n'+text+'\n}\n'

def run(before,after,base,output):
    lockless=(base/'Utilities/lockless.h').read_text()
    fifo=braced(lockless,'class lf_array\n')+';\n'+braced(lockless,'class lf_fifo : public lf_array<T, N>')+';\n'
    fifo='template<class T,usz N>\n'+fifo.replace('class lf_fifo :','template<class T,usz N>\nclass lf_fifo :')
    fp=(base/'rpcs3/Emu/RSX/Program/RSXFragmentProgram.h').read_text()
    old,new=before.read_text(),after.read_text()
    assert new.count('CELL591_SHADER_WARMUP_SCRATCH')==1
    load=braced(new,'void load(shader_loading_dialog* dlg, Args&& ...args)')
    assert load.index('fragment_program_data.for_each')>load.index('compile_shaders(nb_workers')>load.index('load_shaders(nb_workers')
    main=r'''
int main(int argc,char** argv) {
 assert(argc==2);std::string root=argv[1];
 for(auto& sub:{"raw","pipelines/vulkan/test"})std::filesystem::create_directories(root+sub);
 for(unsigned i=1;i<=3;++i){std::vector<u8> bytes(8192);for(usz n=0;n<bytes.size();++n)bytes[n]=u8((i+n)%251);std::ofstream f(root+"raw/"+std::to_string(i)+".fp",std::ios::binary);f.write(reinterpret_cast<const char*>(bytes.data()),bytes.size());}
 for(unsigned i=0;i<48;++i){std::ofstream(root+"pipelines/vulkan/test/"+std::to_string(i)+".bin").put('x');}
 before::Cache old(root);old.load(nullptr);assert(old.held()==48&&old.queue_size()==48);old.verify_owned();
 after::Cache now(root);for(unsigned pass=0;pass<4;++pass){now.load(nullptr);assert(now.held()==0&&now.queue_size()==0);now.verify_owned();}assert(now.workers_joined==8);
 after::Cache cancelled(root);cancelled.cancelled=true;cancelled.load(nullptr);assert(cancelled.held()==0&&cancelled.queue_size()==0&&cancelled.workers_joined==2);cancelled.verify_owned();
 std::printf("{\"passed\":true,\"beforeRetainedBuffers\":48,\"afterRetainedBuffers\":0,\"bytesReleasedAfterOneLoad\":393216,\"repeatedLoads\":4,\"cancellationJoined\":true,\"compiledCopiesValid\":true}\n");
}
'''
    before_code=PREFIX+namespace('before',old,fifo,fp)
    code=before_code+namespace('after',new,fifo,fp)+main
    with tempfile.TemporaryDirectory(prefix='warmup-scratch-') as td:
        w=Path(td);cpp=w/'test.cpp';cpp.write_text(code);results={}
        for label,flags in [('plain',[]),('asanUbsan',['-fsanitize=address,undefined','-fno-omit-frame-pointer'])]:
            exe=w/label;subprocess.run(['c++','-std=c++20','-O1','-g','-Wall','-Wextra','-pthread',*flags,str(cpp),'-o',str(exe)],check=True)
            d=w/(label+'files');d.mkdir()
            r=subprocess.run([str(exe),str(d)+'/'],check=True,stdout=subprocess.PIPE,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
            results[label]=json.loads(r.stdout)
        # Reject both retained scratch and premature reclamation while pipeline
        # workers still read it; this is not a test that merely mirrors reset().
        release=re.search(r'#ifdef RPCS3_IOS\n\s*// CELL591_SHADER_WARMUP_SCRATCH:.*?#endif\n',new,re.S).group()
        compile_call='\t\t\tcompile_shaders(nb_workers, unpacked, entry_count, dlg, std::forward<Args>(args)...);'
        mutations={
            'releaseOmitted':new.replace(release,''),
            'releaseBeforeCompile':new.replace(release,'').replace(compile_call,release+'\n'+compile_call,1),
        }
        rejected={}
        for name,mutated in mutations.items():
            cpp.write_text(before_code+namespace('after',mutated,fifo,fp)+main)
            exe=w/name;subprocess.run(['c++','-std=c++20','-O1','-g','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(cpp),'-o',str(exe)],check=True)
            d=w/(name+'files');d.mkdir()
            r=subprocess.run([str(exe),str(d)+'/'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0',UBSAN_OPTIONS='halt_on_error=1'))
            assert r.returncode!=0,name
            reason='retained-buffer assertion' if name=='releaseOmitted' else 'AddressSanitizer: heap-use-after-free'
            assert ('now.held()==0' in r.stderr) if name=='releaseOmitted' else ('heap-use-after-free' in r.stderr),r.stderr
            rejected[name]={'rejected':True,'reason':reason}
    report={'passed':True,'source':str(after),'sourceSHA256':hashlib.sha256(after.read_bytes()).hexdigest(),'testHarnessSHA256':hashlib.sha256(code.encode()).hexdigest(),'results':results,'mutations':rejected,'deviceRuntimeTested':False,'gameplayGainClaimed':False}
    output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--before',type=Path,default=ROOT/'before/rpcs3/Emu/RSX/rsx_cache.h');p.add_argument('--after',type=Path,default=ROOT/'source/rpcs3/Emu/RSX/rsx_cache.h');p.add_argument('--base',type=Path,default=ROOT/'upstream');p.add_argument('--report',type=Path,default=ROOT/'warmup-scratch-result.json');a=p.parse_args();run(a.before,a.after,a.base,a.report)
