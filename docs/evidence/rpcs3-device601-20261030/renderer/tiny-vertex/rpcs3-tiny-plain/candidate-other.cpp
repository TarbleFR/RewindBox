
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

namespace rsx::vertex_cache {
template <typename storage_type>
		class default_vertex_cache
		{
		public:
			virtual ~default_vertex_cache() = default;
			virtual const storage_type* find_vertex_range(u32 /*local_addr*/, u32 /*data_length*/) { return nullptr; }
			virtual void store_range(u32 /*local_addr*/, u32 /*data_length*/, u32 /*offset_in_heap*/) {}
			virtual void purge() {}
		};
struct uploaded_range
		{
			uptr local_address;
			u32 offset_in_heap;
			u32 data_length;
			u64 fingerprint;
		};
class weak_vertex_cache : public default_vertex_cache<uploaded_range>
		{
			using storage_type = uploaded_range;

		private:
			rsx::unordered_map<uptr, storage_type> vertex_ranges;

			FORCE_INLINE u64 hash(u32 local_addr, u32 data_length) const
			{
				return u64(local_addr) | (u64(data_length) << 32);
			}

#ifdef RPCS3_IOS
			static u64 prefix_fingerprint(u32 local_addr, u32 data_length)
			{
				// Constant/short vertex attributes may occupy fewer than eight
				// bytes. Validate those bytes too, without reading beyond their
				// guest range; larger uploads retain the existing weak prefix.
				u64 result = 0;
				if (data_length)
				{
					std::memcpy(&result, vm::get_super_ptr<char>(local_addr), std::min<u32>(data_length, sizeof(result)));
				}
				return result;
			}
#endif

		public:

			const storage_type* find_vertex_range(u32 local_addr, u32 data_length) override
			{
				const auto key = hash(local_addr, data_length);
				const auto found = vertex_ranges.find(key);

				if (found == vertex_ranges.end())
				{
					return nullptr;
				}

				// Check if data in local_address changed vs what was stored in the vertex_cache
#ifdef RPCS3_IOS
				if (found->second.fingerprint != prefix_fingerprint(local_addr, data_length))
#else
				if (auto sudo_ptr = vm::get_super_ptr<char>(local_addr);
					data_length >= 8 && found->second.fingerprint != *utils::bless<u64>(sudo_ptr))
#endif
				{
					vertex_ranges.erase(key);
					return nullptr;
				}

				return std::addressof(found->second);
			}

			void store_range(u32 local_addr, u32 data_length, u32 offset_in_heap) override
			{
				storage_type v = {};
				v.data_length = data_length;
				v.local_address = local_addr;
				v.offset_in_heap = offset_in_heap;

#ifdef RPCS3_IOS
				v.fingerprint = prefix_fingerprint(local_addr, data_length);
#else
				if (auto sudo_ptr = vm::get_super_ptr<char>(local_addr); data_length >= 8)
				{
					v.fingerprint = *utils::bless<u64>(sudo_ptr);
				}
#endif

				const auto key = hash(local_addr, data_length);
				vertex_ranges[key] = v;
			}

			void purge() override
			{
				vertex_ranges.clear();
			}
		};
}

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
