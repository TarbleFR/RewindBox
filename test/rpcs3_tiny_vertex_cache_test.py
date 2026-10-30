#!/usr/bin/env python3
"""Extract the real weak cache and test bounded prefix validation, without GPU.

The old cache intentionally samples only eight bytes of larger uploads. Preserve
that scope; exercise the previously unchecked short uploads with per-byte writes
and real guard pages. VM translation and the cache map are explicit adapters.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import platform
import shlex
import subprocess

REL = Path('rpcs3/Emu/RSX/rsx_cache.h')


def block(text, marker):
    start = text.index(marker)
    pos = text.index('{', start)
    depth = 0
    for end in range(pos, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if not depth:
            return text[start:end + 1]
    raise ValueError(marker)


PREFIX = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <memory>
#include <unordered_map>
#include <sys/mman.h>
#include <unistd.h>
using u32=std::uint32_t;using u64=std::uint64_t;using uptr=std::uintptr_t;
#define FORCE_INLINE inline
char* guest=nullptr;u64 translations=0;
namespace vm {template<class T>T* get_super_ptr(u32 at){++translations;return reinterpret_cast<T*>(guest+at);}}
namespace utils {template<class T,class U>T* bless(U* p){return reinterpret_cast<T*>(p);}}
namespace rsx {template<class A,class B>using unordered_map=std::unordered_map<A,B>;}
'''

SUFFIX = r'''
int main(){
    const auto page=static_cast<u32>(sysconf(_SC_PAGESIZE));
    void* allocation=mmap(nullptr,page*2,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS,-1,0);
    assert(allocation!=MAP_FAILED);guest=static_cast<char*>(allocation);
    assert(mprotect(guest+page,page,PROT_NONE)==0);
    rsx::vertex_cache::weak_vertex_cache cache;
    u64 stale_short=0,checks=0;
    for(u32 n=1;n<=7;++n){
        const u32 address=page-n;
        for(u32 changed=0;changed<n;++changed){
            std::memset(guest+address,0x2a,n);
            cache.purge();cache.store_range(address,n,71);
            assert(cache.find_vertex_range(address,n)->offset_in_heap==71);++checks;
            guest[address+changed]^=0x11;
            stale_short+=cache.find_vertex_range(address,n)!=nullptr;++checks;
#ifdef CANDIDATE_IOS
            assert(!cache.find_vertex_range(address,n));++checks;
#endif
        }
    }
    // Larger uploads keep the same first-eight-byte fingerprint and do not
    // silently grow a hash over the full payload. Also cover unaligned input.
    for(u32 n:{8u,9u,16u,1024u})for(u32 unaligned=0;unaligned<2;++unaligned){
        const u32 address=128+unaligned;
        for(u32 changed=0;changed<8;++changed){
            std::memset(guest+address,0x2a,n);cache.purge();cache.store_range(address,n,91);
            assert(cache.find_vertex_range(address,n)->offset_in_heap==91);++checks;
            guest[address+changed]^=0x11;
            assert(!cache.find_vertex_range(address,n));++checks;
        }
        if(n>8){
            std::memset(guest+address,0x2a,n);cache.purge();cache.store_range(address,n,93);
            guest[address+n-1]^=0x11;
            assert(cache.find_vertex_range(address,n)->offset_in_heap==93);++checks;
        }
    }
#ifdef CANDIDATE_IOS
    assert(stale_short==0);
#else
    assert(stale_short==28);
#endif
    // A miss and a purge never read guest payloads.
    cache.purge();auto before=translations;assert(!cache.find_vertex_range(0,4));
    assert(translations==before);++checks;
    assert(munmap(allocation,page*2)==0);
    std::cout<<"{\"checks\":"<<checks<<",\"stale_short\":"<<stale_short
             <<",\"guard_page_lengths\":7,\"gpu_executed\":false}"<<std::endl;
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--baseline', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--sanitizer', action='store_true')
    p.add_argument('--compiler', default=os.environ.get('CXX', 'c++'))
    p.add_argument('--variant', action='append', choices=['baseline-ios', 'candidate-ios', 'candidate-other'])
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=True)
    reports = []
    for name, root, defines in [('baseline-ios', a.baseline, ['RPCS3_IOS']),
                                ('candidate-ios', a.source, ['RPCS3_IOS', 'CANDIDATE_IOS']),
                                ('candidate-other', a.source, [])]:
        if a.variant and name not in a.variant:
            continue
        data = (root / REL).read_text()
        body = '\n'.join(block(data, marker) + ';' for marker in [
            'template <typename storage_type>\n\t\tclass default_vertex_cache',
            'struct uploaded_range', 'class weak_vertex_cache'])
        program = PREFIX + '\nnamespace rsx::vertex_cache {\n' + body + '\n}\n' + SUFFIX
        cpp = a.output / (name + '.cpp')
        exe = a.output / name
        cpp.write_text(program)
        cmd = shlex.split(a.compiler) + ['-std=c++20', '-O2', '-g', '-UNDEBUG',
            '-Wall', '-Wextra', '-Werror', *['-D' + x for x in defines], str(cpp), '-o', str(exe)]
        if sdk := os.environ.get('HOST_MACOS_SDK'):
            cmd += ['-isysroot', sdk]
        if a.sanitizer:
            cmd += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-sanitize-recover=all']
            # Old source uses a direct unaligned u64 load. Test its semantics
            # without claiming that preexisting UB is repaired outside iOS.
            if name != 'candidate-ios':
                cmd += ['-fno-sanitize=alignment']
            if platform.system() == 'Linux':
                cmd += ['-no-pie']
        build = subprocess.run(cmd, text=True, capture_output=True)
        (a.output / (name + '.build.log')).write_text(build.stdout + build.stderr)
        build.check_returncode()
        env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0')
        run = subprocess.run([str(exe.resolve())], env=env, text=True, capture_output=True)
        (a.output / (name + '.run.log')).write_text(run.stdout + run.stderr)
        run.check_returncode()
        reports.append(dict(name=name, result=json.loads(run.stdout), command=cmd,
                            program_sha256=hashlib.sha256(program.encode()).hexdigest(),
                            source_sha256=hashlib.sha256((root / REL).read_bytes()).hexdigest()))
    result = dict(schema=1, sanitizer=a.sanitizer, gpu_executed=False, results=reports)
    (a.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
