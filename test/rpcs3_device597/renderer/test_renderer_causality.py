#!/usr/bin/env python3
"""Exercise production bounded renderer observations, including contention/reset.

The callback is the only place an expensive context may be constructed. This
test checks admission budgets, counts, event sessions, silent unchanged inputs,
and an intentionally held recorder lock using a real second producer.
"""
from pathlib import Path
import argparse, hashlib, json, os, platform, shlex, subprocess

PROGRAM = r'''
#include <atomic>
#include <cassert>
#include <cstdlib>
#include <iostream>
#include <new>
#include <semaphore>
#include <thread>
std::atomic<bool> track_allocations{false};
std::atomic<std::uint64_t> allocation_count{0};
void* operator new(std::size_t size) {
    if(track_allocations.load())allocation_count.fetch_add(1);
    if(void* value=std::malloc(size))return value;
    throw std::bad_alloc();
}
void operator delete(void* value)noexcept{std::free(value);}
void operator delete(void* value,std::size_t)noexcept{std::free(value);}
__HEADER__
namespace cause=rpcs3::ios::renderer_causality;
int main(){
    std::uint64_t checks=0;
    auto check=[&](bool value){++checks;assert(value);};
    cause::Profile profile;
    std::uint64_t fills=0;
    check(!profile.record(cause::Kind::vertex_range,cause::source_range,[&](auto&){++fills;}));
    check(fills==0);
    profile.reset(11);
    track_allocations=true;
    for(std::uint32_t kind=0;kind<3;++kind)
        for(std::uint32_t i=0;i<5000;++i){
            const auto reason=kind==0?cause::source_range:kind==1?cause::coordinates|cause::clamp:cause::cyclic;
            profile.record(static_cast<cause::Kind>(kind),reason,[&](cause::Event& event){
                ++fills;event.frame=100+i;event.draw=i;event.fragment_offset=0x20000;
                event.old_resource=0x1000;event.new_resource=0x2000;
                event.before.valid=event.after.valid=true;
                event.before.coordinates[0]=0x3f800000;event.after.coordinates[0]=0x3f000000;
            });
        }
    for(std::uint32_t i=0;i<100;++i){
        check(!profile.record(cause::Kind::sampler_refresh,0,[&](auto&){++fills;}));
        check(!profile.record(cause::Kind::count,cause::source_range,[&](auto&){++fills;}));
    }
    const auto sample=profile.take();
    const auto empty=profile.take();
    track_allocations=false;
    check(allocation_count==0&&fills==8);
    check(sample.captured&&sample.session==11&&sample.size==8);
    check(sample.counts==std::array<std::uint64_t,3>{5000,5000,5000});
    check(sample.dropped==14992&&sample.contended==0);
    check(sample.reasons[0]==5000&&sample.reasons[2]==5000&&sample.reasons[3]==5000&&sample.reasons[7]==5000);
    std::array<std::uint64_t,3> retained{};
    for(std::size_t i=0;i<sample.size;++i){
        const auto& event=sample.events[i];++retained[static_cast<std::size_t>(event.kind)];
        check(event.session==11&&event.monotonic_us!=0&&event.frame==100+event.draw);
        check(event.old_resource==0x1000&&event.new_resource==0x2000);
        check(event.before.coordinates[0]==0x3f800000&&event.after.coordinates[0]==0x3f000000);
    }
    check(retained==std::array<std::uint64_t,3>{2,4,2});
    check(empty.captured&&empty.size==0&&empty.dropped==0&&empty.counts==std::array<std::uint64_t,3>{});
    check(profile.record(cause::Kind::sampler_refresh,cause::validity,[&](auto&){++fills;}));
    profile.reset(12);
    const auto reset=profile.take();
    check(reset.session==12&&reset.size==0&&reset.counts==std::array<std::uint64_t,3>{});
    check(profile.record(cause::Kind::sampler_cyclic_fast,cause::cyclic,[](auto& event){event.frame=777;}));
    const auto next=profile.take();
    check(next.size==1&&next.events[0].session==12&&next.events[0].frame==777);

    cause::SamplerState before,after;
    check(cause::changed_reasons(before,after,false)==0);
    after.coordinates[0]=0x3f800000;
    check(cause::changed_reasons(before,after,false)==0); // Both invalid.
    after.valid=true;
    check(cause::changed_reasons(before,after,false)==cause::validity);
    before=after;
    for(std::size_t i=0;i<6;++i){
        after=before;++after.coordinates[i];
        check(cause::changed_reasons(before,after,false)==cause::coordinates);
        check(cause::changed_reasons(before,after,true)==0);
    }
    for(std::size_t i=6;i<10;++i){
        after=before;++after.coordinates[i];
        check(cause::changed_reasons(before,after,false)==0); // Inactive clamps.
        before.clamp=after.clamp=true;
        check(cause::changed_reasons(before,after,false)==cause::clamp);
        before.clamp=false;
    }
    after=before;after.clamp=true;
    check(cause::changed_reasons(before,after,false)==cause::clamp);
    after=before;after.dimension=2;
    check(cause::changed_reasons(before,after,true)==cause::dimension);
    after=before;after.samples=4;
    check(cause::changed_reasons(before,after,true)==cause::samples);
    after=before;after.format_class=2;
    check(cause::changed_reasons(before,after,true)==cause::format);
    after=before;after.format_features=1;after.texel_remap_control=1;
    check(cause::changed_reasons(before,after,false)==cause::format);
    check(cause::changed_reasons(before,after,true)==0);
    after=before;after.cyclic=true;
    check(cause::changed_reasons(before,after,false)==cause::cyclic);
    check(cause::changed_reasons(before,after,true)==0);

    profile.reset(33);
    std::binary_semaphore ready(0),release(0);
    std::thread held([&]{
        profile.record(cause::Kind::vertex_range,cause::source_range,[&](auto& event){
            event.frame=5;ready.release();release.acquire();
        });
    });
    ready.acquire();
    check(!profile.record(cause::Kind::sampler_refresh,cause::coordinates,[](auto&){assert(false);}));
    check(!profile.take().captured);
    release.release();held.join();
    const auto contention=profile.take();
    check(contention.captured&&contention.size==1&&contention.session==33);
    check(contention.contended==1&&contention.dropped==1);
    check(contention.counts==std::array<std::uint64_t,3>{1,0,0});
    check(contention.events[0].session==33&&contention.events[0].frame==5);
    profile.reset(0);
    check(!profile.record(cause::Kind::vertex_range,cause::source_range,[](auto&){assert(false);}));
    check(profile.take().size==0);
    std::cout<<"{\"checks\":"<<checks<<",\"burst_triggers\":15000,\"retained\":8,\"dropped_at_capacity\":14992,"
      <<"\"retained_by_kind\":[2,4,2],\"context_callbacks\":8,\"allocations_while_recording\":"<<allocation_count.load()
      <<",\"nonblocking_contention_drop\":1,\"session_resets_verified\":3}"<<std::endl;
}
'''

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--source',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--sanitizer',action='store_true')
    ap.add_argument('--compiler',default=os.environ.get('CXX','g++'),help='C++ command; defaults to CXX')
    args=ap.parse_args();args.output.mkdir(parents=True,exist_ok=True)
    header=args.source/'rpcs3/ios/IOSRendererCausality.h'
    data=header.read_bytes();cpp=PROGRAM.replace('__HEADER__',data.decode().replace('#pragma once',''))
    source=args.output/'causality.cpp';source.write_text(cpp);binary=args.output/'causality'
    command=shlex.split(args.compiler)+['-std=c++20','-O2','-g','-UNDEBUG','-Wall','-Wextra','-Werror','-pthread',str(source),'-o',str(binary)]
    if platform.system()=='Darwin' and os.environ.get('HOST_MACOS_SDK'):
        command+=['-isysroot',os.environ['HOST_MACOS_SDK']]
    if args.sanitizer:
        command+=['-fsanitize=address,undefined','-fno-omit-frame-pointer','-fno-sanitize-recover=all']
        if platform.system()=='Linux':command+=['-no-pie']
    build=subprocess.run(command,capture_output=True,text=True)
    (args.output/'build.log').write_text(build.stdout+build.stderr);build.check_returncode()
    run=subprocess.run([str(binary)],capture_output=True,text=True,timeout=45,env=dict(os.environ,ASAN_OPTIONS='detect_leaks=0'))
    (args.output/'run.log').write_text(run.stdout+run.stderr);run.check_returncode()
    result={'scope':'production bounded observation queue and reason classifier; no renderer or GPU',
      'header_sha256':hashlib.sha256(data).hexdigest(),'generated_sha256':hashlib.sha256(cpp.encode()).hexdigest(),
      'sanitizer':args.sanitizer,'command':command,'result':json.loads(run.stdout),'returncode':run.returncode}
    (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
