#include <algorithm>
#include <array>
#include <bit>
#include <cassert>
#include <cstdint>
#include <functional>
#include <iostream>
#include <stdexcept>
#include <vector>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using uint=unsigned;
constexpr u32 RAW_SPU_BASE_ADDR=0xe0000000,umax=0xffffffff;
constexpr u64 operator""_u64(const char*,std::size_t){return 0;}
template<u64>struct perf_meter{explicit perf_meter(int){}operator bool()const{return false;}void restart(){}};
template<class T,std::size_t Align=alignof(T)>struct atomic_t{
 T value{};T load()const{return value;}void store(T v){value=v;}void release(T v){value=v;}
 operator T()const{return value;}
};
enum cpu_flag{wait=1,temp=2};
struct cpu_thread{unsigned state=0;unsigned checked=0;static cpu_thread* get_current(){static cpu_thread c;return &c;}void check_state(){++checked;}};
static unsigned faults=0,waits=0;static std::vector<u32>fault_addresses;
static std::function<void()> on_wait;
void busy_wait(unsigned){++waits;if(on_wait)on_wait();}
namespace utils{void trigger_write_page_fault(void* p){++faults;fault_addresses.push_back(u32(reinterpret_cast<std::uintptr_t>(p)));throw std::runtime_error("guest page fault");}}
namespace rsx::constants{constexpr u32 local_mem_base=0xc0000000;}
template<class F>void reset_probes(F&& f){faults=waits=0;fault_addresses.clear();on_wait=std::forward<F>(f);}
