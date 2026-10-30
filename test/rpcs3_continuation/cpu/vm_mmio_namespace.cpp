enum range_lock_flags:u64{range_locked=4ull<<61,range_full_mask=7ull<<61,range_bits=3};
static std::array<atomic_t<u64>,65536>g_shmem;
static std::array<u8,1u<<20>g_pages;
static std::array<atomic_t<u64,128>,64>g_range_lock_set;
static atomic_t<u64,128>g_range_lock_bits[2];
constexpr u8 page_readable=1;
static u64 get_range_lock_bits(bool){return g_range_lock_bits[1].load();}
static bool check_addr(u32 addr,u8 flag=page_readable,u32 size=1){
 if(!size||u64(addr)+size>0x100000000ull)return false;
 for(u32 p=addr/4096;p<=(u64(addr)+size-1)/4096;++p)if(!(g_pages[p]&flag))return false;
 return true;
}
static void* base(u32 addr){return reinterpret_cast<void*>(std::uintptr_t(addr));}
template<class F>static u64 for_all_range_locks(u64 input,F func);
#define FORCE_INLINE inline
static void reset(){g_shmem={};g_pages={};g_range_lock_set={};g_range_lock_bits[0].store(0);g_range_lock_bits[1].store(0);}
