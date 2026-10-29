#!/usr/bin/env python3
"""Production descriptor storage and dispatch queue bodies; no GPU/RAM claim."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

from rpcs3_memory523_test import braced
from rpcs3_cell559_test import without_ios_blocks

ROOT = Path(__file__).resolve().parents[1]
CPP = 'rpcs3/Emu/RSX/VK/vkutils/descriptors.cpp'
HEADER = 'rpcs3/Emu/RSX/VK/vkutils/descriptors.h'
UPSTREAM = '22f1152783cef1f7e04af7b1c895173e28fd5b03'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def generate(source, before):
    code = '''#define VK_NO_PROTOTYPES
#include <vulkan/vulkan.h>
#include <array>
#include <atomic>
#include <algorithm>
#include <cassert>
#include <concepts>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <iterator>
#include <memory>
#include <mutex>
#include <thread>
#include <tuple>
#include <type_traits>
#include <vector>
using usz=std::size_t;using u64=std::uint64_t;using u32=std::uint32_t;
using u8=std::uint8_t;using uchar=unsigned char;
template<class T> using atomic_t=std::atomic<T>;
using shared_mutex=std::mutex;
template<class T> concept UnsignedInt=std::is_integral_v<T> && std::is_unsigned_v<T>;
template<class C> u32 size32(const C& v) {return static_cast<u32>(v.size());}
constexpr u32 umax=~u32{0};
#define FORCE_INLINE inline
#define ensure(c) do {if (!(c)) std::abort();} while(false)
#define AUDIT(c) ensure(c)
#define FN(expr) [&](auto&& x) {return (expr);}
namespace fmt { [[noreturn]] inline void throw_exception(const char*,...) {std::abort();} }
inline u64 allocated_bytes=0,allocated_calls=0;
namespace rsx {
template<class T> using reverse_pointer=std::reverse_iterator<T*>;
namespace aligned_allocator {
template<size_t> [[gnu::noinline]] void* malloc(size_t n) {allocated_bytes+=n;++allocated_calls;return std::malloc(n);}
template<size_t> [[gnu::noinline]] void* realloc(void* p,size_t,size_t n) {allocated_bytes+=n;++allocated_calls;return std::realloc(p,n);}
inline void free(void* p) {std::free(p);}
}}
'''
    array = (source / 'rpcs3/Emu/RSX/Common/simple_array.hpp').read_text()
    code += '\n'.join(l for l in array.splitlines() if not l.startswith(('#include ', '#pragma once')))
    for label, tree in [('before', before), ('after', source)]:
        h = (tree / HEADER).read_text()
        c = (tree / CPP).read_text()
        # Test-only private visibility permits observing actual capacities and
        # queue membership without changing the production object layout.
        klass = braced(h, 'class descriptor_set\n').replace('private:', 'public:')
        manager = braced(c, 'class dispatch_manager\n').replace('private:', 'public:')
        code += '\nnamespace ' + label + ' { namespace vk {\n'
        code += 'class command_buffer; namespace descriptors {class dispatch_manager;}\n'
        code += braced(h, 'struct descriptor_set_dynamic_offset_t\n') + ';\n'
        code += klass + ';\n'
        code += '''
struct Device {
 u64 mask=0;u64 get_descriptor_update_after_bind_support() const {return mask;}
 operator VkDevice() const {return reinterpret_cast<VkDevice>(1);}
};
inline Device device;inline Device* g_render_device=&device;
struct FXO {template<class T> T& get() {static T value;return value;}};
inline FXO fxo;inline FXO* g_fxo=&fxo;
inline std::vector<std::array<u64,8>> driver_writes;
inline void vkUpdateDescriptorSets(VkDevice,u32 count,const VkWriteDescriptorSet* writes,u32 copies,const VkCopyDescriptorSet* copy_commands) {
 for(u32 i=0;i<count;++i) {
  const auto& w=writes[i];
  for(u32 d=0;d<w.descriptorCount;++d) {
   std::array<u64,8> row{reinterpret_cast<uintptr_t>(w.dstSet),w.dstBinding,w.descriptorType,w.dstArrayElement+d,0,0,0,0};
   if(w.pBufferInfo) {const auto& p=w.pBufferInfo[d];row[4]=reinterpret_cast<uintptr_t>(p.buffer);row[5]=p.offset;row[6]=p.range;}
   if(w.pImageInfo) {const auto& p=w.pImageInfo[d];row[4]=reinterpret_cast<uintptr_t>(p.sampler);row[5]=reinterpret_cast<uintptr_t>(p.imageView);row[6]=p.imageLayout;}
   if(w.pTexelBufferView) row[4]=reinterpret_cast<uintptr_t>(w.pTexelBufferView[d]);
   driver_writes.push_back(row);
  }
 }
 for(u32 i=0;i<copies;++i) {
  const auto& c=copy_commands[i];
  driver_writes.push_back({reinterpret_cast<uintptr_t>(c.dstSet),c.dstBinding,~u64{0},c.dstArrayElement,
   reinterpret_cast<uintptr_t>(c.srcSet),c.srcBinding,c.srcArrayElement,c.descriptorCount});
 }
}
namespace descriptors {
'''
        code += manager + ';\n}\n'
        signatures = [
            'descriptor_set::~descriptor_set()', 'void descriptor_set::init(', 'void descriptor_set::swap(',
            'descriptor_set& descriptor_set::operator = (', 'VkDescriptorSet* descriptor_set::ptr()',
            'void descriptor_set::push(const VkBufferView&',
            'void descriptor_set::push(const VkDescriptorBufferInfo&',
            'void descriptor_set::push(const VkDescriptorImageInfo&',
            'void descriptor_set::push(const VkDescriptorImageInfo*',
            'void descriptor_set::push(const rsx::simple_array<VkCopyDescriptorSet>&',
            'void descriptor_set::push(const rsx::simple_array<VkWriteDescriptorSet>&',
            'void descriptor_set::push(const descriptor_set_dynamic_offset_t&',
            'void descriptor_set::on_bind()', 'void descriptor_set::flush()',
        ]
        for signature in signatures:
            code += braced(c, signature) + '\n'
        code += (ROOT / 'test/native/rpcs3_descriptor_reserve_test.inc').read_text()
        code += '\n}}\n'
    code += '''
int main() {
 auto b=before::vk::run();auto a=after::vk::run();
 assert(b.writes==a.writes);
 assert(b.initial_bytes==921088 && a.initial_bytes==0);
 assert(b.buffer_only_bytes==921088 && a.buffer_only_bytes==394752);
 assert(b.queue_entries==10000 && a.queue_entries==1);
 assert(b.flush_entries==10000 && a.flush_entries==1);
 std::cout<<"{\\"productionDriverWritesEqual\\":true,\\"initialReservedBytesBefore\\":"<<b.initial_bytes
 <<",\\"initialReservedBytesAfter\\":"<<a.initial_bytes<<",\\"bufferOnlyReservedBytesBefore\\":"<<b.buffer_only_bytes
 <<",\\"bufferOnlyReservedBytesAfter\\":"<<a.buffer_only_bytes<<",\\"duplicateRegistrations\\":10000,\\"queueEntriesBefore\\":"<<b.queue_entries
 <<",\\"queueEntriesAfter\\":"<<a.queue_entries<<",\\"deferredPointerEntriesTested\\":16448,\\"driverDescriptorElements\\":"<<a.writes.size()
 <<",\\"concurrentQueueLifecyclePassed\\":true,\\"physicalRamMeasured\\":false}\\n";
}
'''
    return code


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('--before', type=Path)
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--sanitize', action='store_true')
    group.add_argument('--thread-sanitize', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    source = args.source.resolve()
    with tempfile.TemporaryDirectory(prefix='descriptor-reserve-') as tmp:
        work = Path(tmp)
        before = args.before.resolve() if args.before else work / 'before'
        if not args.before:
            for p in [CPP, HEADER]:
                target = before / p
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(subprocess.check_output(['git', 'show', UPSTREAM + ':' + p], cwd=source))
        for p in [CPP, HEADER]:
            assert without_ios_blocks((source / p).read_text()) == without_ios_blocks((before / p).read_text()), p
        cpp = work / 'test.cpp'
        cpp.write_text(generate(source, before))
        cxx = shlex.split(os.environ.get('CXX', 'c++'))
        flags = ['-std=c++20', '-g', '-Wall', '-Wextra', '-Werror', '-pthread', '-DRPCS3_IOS', '-UNDEBUG']
        if args.sanitize:
            flags += ['-O1', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
        elif args.thread_sanitize:
            flags += ['-O1', '-fsanitize=thread', '-fno-omit-frame-pointer']
        else:
            flags += ['-O3']
        exe = work / 'test'
        subprocess.run(cxx + flags + ['-I'+str(ROOT / 'packages/libretro_internal_bridge/ios/ThirdParty/include'), str(cpp), '-o', str(exe)], check=True)
        run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=90,
                             env=dict(os.environ, ASAN_OPTIONS='detect_leaks=0', UBSAN_OPTIONS='halt_on_error=1', TSAN_OPTIONS='halt_on_error=1'))
        if run.returncode:
            print(run.stderr)
            run.check_returncode()
        report = dict(passed=True, addressUndefinedSanitized=args.sanitize, threadSanitized=args.thread_sanitize,
                      compiler=subprocess.check_output(cxx+['--version'], text=True).splitlines()[0], compilerFlags=flags,
                      sourceBefore={p: sha(before / p) for p in [CPP, HEADER]},
                      sourceAfter={p: sha(source / p) for p in [CPP, HEADER]},
                      harnessSHA256=sha(cpp), results=json.loads(run.stdout),
                      testInputs={p:sha(ROOT/p) for p in ['test/rpcs3_descriptor_reserve_test.py','test/native/rpcs3_descriptor_reserve_test.inc']},
                      scope='Production descriptor_set, typed stores/pushes/init/flush and dispatch manager; real simple_array; Vulkan driver, device capabilities and outer renderer are adapters. Reserved allocation requests are not physical RAM.')
    if args.report:
        args.report.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
