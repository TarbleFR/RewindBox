
#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <iostream>
#include <limits>
#include <memory>
#include <stdexcept>
#include <unordered_map>
#include <utility>
#include <vector>
using u8=std::uint8_t; using u16=std::uint16_t; using u32=std::uint32_t;
using u64=std::uint64_t; using uptr=std::uintptr_t; using usz=std::size_t;
constexpr u32 umax=~0u;
// SPDX-License-Identifier: GPL-2.0-only


#include <array>
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <mutex>

// Bounded observations of corrected renderer decisions. No guest-memory reads,
// driver calls, allocations or logging. The RSX producer never waits for the
// reporting thread. Counts include events rejected at capacity; contention is
// separately counted because its kind/reasons could not be safely attributed.
namespace rpcs3::ios::renderer_causality
{
enum class Kind : std::uint32_t { vertex_range, sampler_refresh, sampler_cyclic_fast, count };
enum Reason : std::uint32_t
{
    source_range = 1u << 0,
    validity = 1u << 1,
    coordinates = 1u << 2,
    clamp = 1u << 3,
    dimension = 1u << 4,
    samples = 1u << 5,
    format = 1u << 6,
    cyclic = 1u << 7,
};
inline constexpr std::size_t reason_count = 8;
inline constexpr std::size_t event_capacity = 8;
// Reserve observations for both defects even when one dominates a window.
inline constexpr std::array<std::size_t, 3> event_budgets{2, 4, 2};

struct SamplerState
{
    // Bit patterns of scale[3], bias[3], active clamp_min[2]/clamp_max[2].
    // Inactive clamp values are zero; no uninitialized descriptor bytes are read.
    std::array<std::uint32_t, 10> coordinates{};
    std::uint32_t dimension = 0, format_class = 0, format_features = 0, texel_remap_control = 0;
    std::uint8_t samples = 1;
    bool cyclic = false, clamp = false, valid = false;

    template <typename State>
    static SamplerState from(const State& state) noexcept
    {
        return {state.coordinates, state.dimension, state.format_class,
            state.format_features, state.texel_remap_control, state.samples,
            state.cyclic, state.clamp, state.valid};
    }
};

template <typename State>
inline std::uint32_t changed_reasons(const State& before, const State& after, bool vertex) noexcept
{
    if (before.valid != after.valid) return validity;
    if (!before.valid) return 0;
    std::uint32_t result = 0;
    if (before.dimension != after.dimension) result |= dimension;
    if (before.format_class != after.format_class) result |= format;
    if (before.samples != after.samples) result |= samples;
    if (vertex) return result;
    if (before.cyclic != after.cyclic) result |= cyclic;
    for (std::size_t i = 0; i < 6; ++i)
        if (before.coordinates[i] != after.coordinates[i]) result |= coordinates;
    if (before.clamp != after.clamp) result |= clamp;
    if (before.clamp && after.clamp)
        for (std::size_t i = 6; i < before.coordinates.size(); ++i)
            if (before.coordinates[i] != after.coordinates[i]) result |= clamp;
    if (before.format_features != after.format_features ||
        before.texel_remap_control != after.texel_remap_control) result |= format;
    return result;
}

struct Event
{
    std::uint64_t session = 0, monotonic_us = 0, frame = 0;
    Kind kind{};
    std::uint32_t reasons = 0, draw = 0, fragment_offset = 0, vertex_start = 0;
    std::uint32_t slot = 0, old_resource = 0, new_resource = 0;
    bool vertex = false;
    // vertex_range describes differing cache keys, not proven visible corruption.
    std::uint32_t legacy_address = 0, actual_address = 0, bytes = 0;
    std::uint32_t draw_first = 0, source_first = 0, count = 0, stride = 0;
    bool cache_hit = false;
    SamplerState before{}, after{};
};

class Profile final
{
    std::mutex mutex_;
    std::uint64_t session_ = 0;
    std::array<Event, event_capacity> events_{};
    std::size_t size_ = 0;
    std::array<std::uint64_t, static_cast<std::size_t>(Kind::count)> counts_{};
    std::array<std::size_t, static_cast<std::size_t>(Kind::count)> kept_{};
    std::array<std::uint64_t, reason_count> reasons_{};
    std::uint64_t full_dropped_ = 0;
    std::atomic<std::uint64_t> contended_{0};

public:
    struct Snapshot
    {
        bool captured = false;
        std::uint64_t session = 0;
        std::array<Event, event_capacity> events{};
        std::size_t size = 0;
        std::array<std::uint64_t, static_cast<std::size_t>(Kind::count)> counts{};
        std::array<std::uint64_t, reason_count> reasons{};
        std::uint64_t dropped = 0, contended = 0;
    };

    template <typename Fill>
    bool record(Kind kind, std::uint32_t reasons, Fill&& fill) noexcept
    {
        reasons &= (1u << reason_count) - 1;
        if (!reasons || kind >= Kind::count) return false;
        std::unique_lock lock(mutex_, std::try_to_lock);
        if (!lock)
        {
            contended_.fetch_add(1, std::memory_order_relaxed);
            return false;
        }
        if (!session_) return false;
        const auto index = static_cast<std::size_t>(kind);
        ++counts_[index];
        for (std::size_t bit = 0; bit < reason_count; ++bit)
            reasons_[bit] += bool(reasons & (1u << bit));
        if (size_ == events_.size() || kept_[index] == event_budgets[index])
        {
            ++full_dropped_;
            return false;
        }
        auto& event = events_[size_++];
        ++kept_[index];
        event = {};
        event.session = session_;
        event.kind = kind;
        event.reasons = reasons;
        // Only retained events pay for a clock read or the caller's context copy.
        event.monotonic_us = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count());
        fill(event);
        return true;
    }

    // Called from the profiler's session reset, outside the RSX hot path.
    // All retained events and attributed counts are cleared together. A
    // concurrent rejected attempt can straddle the reset only in contended.
    void reset(std::uint64_t session) noexcept
    {
        std::lock_guard lock(mutex_);
        session_ = session;
        size_ = 0;
        counts_ = {};
        kept_ = {};
        reasons_ = {};
        full_dropped_ = 0;
        contended_.store(0, std::memory_order_relaxed);
    }

    Snapshot take() noexcept
    {
        std::unique_lock lock(mutex_, std::try_to_lock);
        if (!lock) return {};
        Snapshot result;
        result.captured = true;
        result.session = session_;
        result.events = events_;
        result.size = size_;
        result.counts = counts_;
        result.reasons = reasons_;
        result.contended = contended_.exchange(0, std::memory_order_relaxed);
        result.dropped = full_dropped_ + result.contended;
        size_ = 0;
        counts_ = {};
        kept_ = {};
        reasons_ = {};
        full_dropped_ = 0;
        return result;
    }
};
inline constinit Profile profile;
}

#define FORCE_INLINE inline
#define ensure(x) assert(x)
template<class T> using be_t=T;
template<class T> T read_from_ptr_unsafe(const std::byte* p,usz at) { T r; std::memcpy(&r,p+at,sizeof(r)); return r; }
alignas(64) std::array<std::byte,1<<20> guest;
u64 reads=0,copied=0,copies=0;
namespace utils {
template<class T> T add_saturate(T a,T b) {return a>std::numeric_limits<T>::max()-b?std::numeric_limits<T>::max():a+b;}
template<class T,class U> T* bless(U* p) {return reinterpret_cast<T*>(p);}
}
namespace vm {
template<class T> T* get_super_ptr(u32 at) {++reads;if(at>=guest.size())throw std::out_of_range("guest address");return reinterpret_cast<T*>(guest.data()+at);}
template<class T> T* _ptr(u32 at) {return get_super_ptr<T>(at);}
}
constexpr u32 CELL_GCM_LOCATION_LOCAL=1;
u32 get_location(u32) {return 0;}
namespace rsx {
template<class A,class B> using unordered_map=std::unordered_map<A,B>;
namespace constants {constexpr u32 local_mem_base=0xc0000000;}
namespace limits {constexpr u32 vertex_count=16;}
enum class draw_command {array,indexed,inlined_array};
enum class index_array_type {u16,u32};
struct draw_clause {draw_command command=draw_command::array;bool is_immediate_draw=false;};
struct regs_t {
    draw_clause current_draw_clause;
    rsx::index_array_type index_type() const{return rsx::index_array_type::u32;}
    bool restart_index_enabled() const{return false;}
    u32 restart_index() const{return ~0u;}
    u32 index_array_address() const{return 0;}
    u32 index_array_location() const{return 0;}
    u32 transform_program_start() const{return 19;}
} method_registers;
u32 get_address(u32 at,u32) {return at;}
struct processor_t {std::vector<u32> indices;const auto& element_push_buffer() const{return indices;}};
struct renderer_t {u32 local_mem_size=1<<20;processor_t processor;processor_t* draw_processor(){return &processor;}} renderer;
renderer_t* get_current_renderer(){return &renderer;}
struct interleaved_attribute_t {u8 index;bool modulo;u16 frequency;};
struct interleaved_range_info {
    bool interleaved=true,single_vertex=false;
    u32 base_offset=0,real_offset_address=0;u8 memory_location=0,attribute_stride=16;
    std::pair<u32,u32> vertex_range{};
    std::vector<interleaved_attribute_t> locations;
    std::pair<u32,u32> calculate_required_range(u32 first,u32 count);
std::pair<u32, u32> get_required_range(u32 first, u32 count)
		{
			if (vertex_range.second)
				return vertex_range;
			return calculate_required_range(first, count);
		}
};
struct vertex_input_layout {
    std::vector<interleaved_range_info*> interleaved_blocks;
    u32 calculate_interleaved_memory_requirements(u32 first,u32 count) const {
        u32 total=0;for(auto* b:interleaved_blocks)total+=b->calculate_required_range(first,count).second*b->attribute_stride;
        return total;
    }
};
struct dma_manager {void copy(void* dst,const void* src,u32 n){std::memcpy(dst,src,n);copied+=n;++copies;}};
}
struct fxo_t {rsx::dma_manager dma;template<class T> T& get(){return dma;}} fxo;
fxo_t* g_fxo=&fxo;
std::pair<u32, u32> rsx::interleaved_range_info::calculate_required_range(u32 first, u32 count)
	{
		if (vertex_range.second)
		{
			// Cached result
			return vertex_range;
		}

		if (single_vertex)
		{
			return { 0, 1 };
		}

		const u32 max_index = (first + count) - 1;
		u32 _max_index = 0;
		u32 _min_index = first;

		u32 frequencies[rsx::limits::vertex_count];
		u32 freq_count = rsx::method_registers.current_draw_clause.command == rsx::draw_command::indexed ? 0 : u32{umax};
		u32 max_result_by_division = 0; // Guaranteed maximum

		for (const auto &attrib : locations)
		{
			if (attrib.frequency <= 1) [[likely]]
			{
				freq_count = umax;
				_max_index = max_index;
			}
			else
			{
				if (attrib.modulo)
				{
					if (max_index >= attrib.frequency)
					{
						// Actually uses the modulo operator
						_min_index = 0;
						_max_index = std::max<u32>(_max_index, attrib.frequency - 1);

						if (max_result_by_division < _max_index)
						{
							if (freq_count != umax)
							{
								if (std::find(frequencies, frequencies + freq_count, attrib.frequency) == frequencies + freq_count)
								{
									frequencies[freq_count++] = attrib.frequency;
								}
							}
						}
					}
					else
					{
						// Same as having no modulo
						_max_index = max_index;
						freq_count = umax;
					}
				}
				else
				{
					// Division operator: match the shader's integer vertex-ID division.
					// Rounding up reads an extra instance and can cross local memory.
					_min_index = std::min(_min_index, first / attrib.frequency);
					const u32 divided_max = max_index / attrib.frequency;
					_max_index = std::max(_max_index, divided_max);
					max_result_by_division = std::max(max_result_by_division, divided_max);

					if (freq_count > 0 && freq_count != umax)
					{
						// Discard lower frequencies because it has been proven that there are indices higher than them
						const usz discard_cnt = frequencies + freq_count - std::remove_if(frequencies, frequencies + freq_count, [&max_result_by_division](u32 freq)
						{
							return freq <= max_result_by_division;
						});

						freq_count -= static_cast<u32>(discard_cnt);
					}
				}
			}
		}

		while (freq_count > 0 && freq_count != umax)
		{
			const rsx::index_array_type index_type = rsx::method_registers.current_draw_clause.is_immediate_draw ?
				rsx::index_array_type::u32 :
				rsx::method_registers.index_type();

			const u32 index_size = index_type == rsx::index_array_type::u32 ? 4 : 2;

			const auto render = rsx::get_current_renderer();

			// If we can access a bit a more memory than required - do it
			// The alternative would be re-iterating again over all of them
			if (get_location(real_offset_address) == CELL_GCM_LOCATION_LOCAL)
			{
				if (utils::add_saturate<u32>(real_offset_address - rsx::constants::local_mem_base, (_max_index + 1) * attribute_stride) <= render->local_mem_size)
				{
					break;
				}
			}
			else if (real_offset_address % 0x100000 + (_max_index + 1) * attribute_stride <= 0x100000)//(vm::check_addr(real_offset_address, vm::page_readable, (_max_index + 1) * attribute_stride))
			{
				break;
			}

			// Tightening modulo bounds must retain the divided attributes' range.
			_max_index = max_result_by_division;

			const auto re_evaluate = [&] <typename T> (const std::byte* ptr, T)
			{
				const u64 restart = rsx::method_registers.restart_index_enabled() ? rsx::method_registers.restart_index() : u64{umax};

				for (u32 _index = first; _index < first + count; _index++)
				{
					const auto value = read_from_ptr_unsafe<be_t<T>>(ptr, _index * sizeof(T));

					if (value == restart)
					{
						continue;
					}

					for (u32 freq_it = 0; freq_it < freq_count; freq_it++)
					{
						const auto res = value % frequencies[freq_it];

						if (res > _max_index)
						{
							_max_index = res;
						}
					}
				}
			};

			const auto element_push_buffer = render->draw_processor()->element_push_buffer();
			if (index_size == 4)
			{
				if (!element_push_buffer.empty()) [[unlikely]]
				{
					// Indices provided via immediate mode
					re_evaluate(reinterpret_cast<const std::byte*>(element_push_buffer.data()), u32{});
				}
				else
				{
					const u32 address = (0 - index_size) & get_address(rsx::method_registers.index_array_address(), rsx::method_registers.index_array_location());
					re_evaluate(vm::get_super_ptr<std::byte>(address), u32{});
				}
			}
			else
			{
				if (!element_push_buffer.empty()) [[unlikely]]
				{
					// Indices provided via immediate mode
					re_evaluate(reinterpret_cast<const std::byte*>(element_push_buffer.data()), u16{});
				}
				else
				{
					const u32 address = (0 - index_size) & get_address(rsx::method_registers.index_array_address(), rsx::method_registers.index_array_location());
					re_evaluate(vm::get_super_ptr<std::byte>(address), u16{});
				}
			}

			break;
		}

		ensure(_max_index >= _min_index);
		vertex_range = { _min_index, (_max_index - _min_index) + 1 };
		return vertex_range;
	}
namespace rsx {
namespace vertex_cache
	{
		// A null vertex cache
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

		// A weak vertex cache with no data checks or memory range locks
		// Of limited use since contents are only guaranteed to be valid once per frame
		// Supports upto 1GiB block lengths if typed and full 4GiB otherwise.
		// Using a 1:1 hash-value with robin-hood is 2x faster than what we had before with std-map-of-arrays.
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
				if (data_length >= sizeof(result))
				{
					// Keep the common path a single fixed-width load.
					std::memcpy(&result, vm::get_super_ptr<char>(local_addr), sizeof(result));
				}
				else if (data_length)
				{
					std::memcpy(&result, vm::get_super_ptr<char>(local_addr), data_length);
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
}
struct heap_t {
    std::vector<std::byte> bytes=std::vector<std::byte>(1<<20);
    u32 next=0;
    template<u32 alignment> u32 alloc(u32 n){next=(next+alignment-1)&~(alignment-1);u32 off=next;next+=n;assert(next<bytes.size());return off;}
};
struct upload_t {
    rsx::vertex_input_layout m_vertex_layout;
    rsx::vertex_cache::weak_vertex_cache cache;
    rsx::vertex_cache::default_vertex_cache<rsx::vertex_cache::uploaded_range>* m_vertex_cache=&cache;
    heap_t m_attrib_ring_info;
    struct {u32 vertex_cache_request_count=0,vertex_cache_miss_count=0,draw_calls=17;} m_frame_stats;
    u64 int_flip_index=23;
    struct {u32 offset=0x20000;}current_fragment_program;
    u32 upload(u32 vertex_base,u32 vertex_count) {
        auto required=std::pair{m_vertex_layout.calculate_interleaved_memory_requirements(vertex_base,vertex_count),0u};
        u32 persistent_range_base=-1;
        usz persistent_offset=static_cast<u32>(-1);
if (required.first > 0)
	{
		//Check if cacheable
		//Only data in the 'persistent' block may be cached
		//TODO: make vertex cache keep local data beyond frame boundaries and hook notify command
		bool in_cache = false;
		bool to_store = false;
		u32  storage_address = -1;

		m_frame_stats.vertex_cache_request_count++;

		if (m_vertex_layout.interleaved_blocks.size() == 1 &&
			rsx::method_registers.current_draw_clause.command != rsx::draw_command::inlined_array)
		{
			const auto data_offset = (vertex_base * m_vertex_layout.interleaved_blocks[0]->attribute_stride);
			storage_address = m_vertex_layout.interleaved_blocks[0]->real_offset_address + data_offset;

			if (auto cached = m_vertex_cache->find_vertex_range(storage_address, required.first))
			{
				ensure(cached->local_address == storage_address);

				in_cache = true;
				persistent_range_base = cached->offset_in_heap;
			}
			else
			{
				to_store = true;
			}
		}

		if (!in_cache)
		{
			m_frame_stats.vertex_cache_miss_count++;

			persistent_offset = static_cast<u32>(m_attrib_ring_info.alloc<256>(required.first));
			persistent_range_base = static_cast<u32>(persistent_offset);

			if (to_store)
			{
				//store ref in vertex cache
				m_vertex_cache->store_range(storage_address, required.first, static_cast<u32>(persistent_offset));
			}
		}
	}
        if(persistent_offset!=umax)copy(m_attrib_ring_info.bytes.data()+persistent_offset,vertex_base,vertex_count);
        return persistent_range_base;
    }
    void copy(void* persistent_data,u32 first_vertex,u32 vertex_count) const {
        char* persistent=static_cast<char*>(persistent_data);
        const auto& layout=m_vertex_layout;
for (rsx::interleaved_range_info* block : layout.interleaved_blocks)
			{
				auto range = block->get_required_range(first_vertex, vertex_count);

				const u32 data_size = range.second * block->attribute_stride;
				const u32 vertex_base = range.first * block->attribute_stride;

				g_fxo->get<rsx::dma_manager>().copy(persistent, vm::_ptr<char>(block->real_offset_address) + vertex_base, data_size);
				persistent += data_size;
			}
    }
    bool agrees_with_uncached(u32 first,u32 count) {
        namespace cause=rpcs3::ios::renderer_causality;
        cause::profile.reset(101);
        u32 off=upload(first,count);
        u32 len=m_vertex_layout.calculate_interleaved_memory_requirements(first,count);
        std::vector<std::byte> expected(len);
        copy(expected.data(),first,count);
        const auto observation=cause::profile.take();
#ifdef CANDIDATE
        const auto* b=m_vertex_layout.interleaved_blocks[0];
        const auto source_first=b->vertex_range.first;
        assert((observation.size!=0)==(first!=source_first));
        if(observation.size){
            assert(observation.size==1&&observation.dropped==0);
            const auto& event=observation.events[0];
            assert(event.kind==cause::Kind::vertex_range&&event.reasons==cause::source_range);
            assert(event.frame==23&&event.draw==17&&event.session==101&&event.vertex);
            assert(event.fragment_offset==0x20000&&event.vertex_start==19);
            assert(event.legacy_address==b->real_offset_address+first*b->attribute_stride);
            assert(event.actual_address==b->real_offset_address+source_first*b->attribute_stride);
            assert(event.bytes==len&&event.count==count&&event.stride==b->attribute_stride);
        }
#else
        assert(observation.size==0);
#endif
        return std::memcmp(expected.data(),m_attrib_ring_info.bytes.data()+off,len)==0;
    }
};

int main() {
    for(usz i=0;i<guest.size();++i)guest[i]=std::byte((i*37+(i/16)*13)%251);
    u64 cases=0,mismatches=0,ordinary_mismatches=0,reuse_uploads=0;
    for(u32 stride:{8u,16u,32u,64u})
    for(u32 first:{8u,16u,32u,64u})
    for(u32 freq:{2u,4u,8u})
    for(u32 kind=0;kind<3;++kind)
    for(u32 reverse=0;reverse<2;++reverse) {
        upload_t r;
        rsx::interleaved_range_info ordinary,frequency;
        ordinary.real_offset_address=4096;ordinary.attribute_stride=stride;
        ordinary.locations.push_back({0,false,1});
        frequency=ordinary;frequency.single_vertex=(kind==0);
        frequency.locations[0]={0,kind==2,static_cast<u16>(freq)};
        const u32 n=kind==2?freq:1;
        const u32 frequency_n=kind==0?freq:kind==1?freq:n;
        r.m_vertex_layout.interleaved_blocks={reverse?&frequency:&ordinary};
        bool first_ok=r.agrees_with_uncached(first,reverse?frequency_n:n);++cases;assert(first_ok);
        r.m_vertex_layout.interleaved_blocks={reverse?&ordinary:&frequency};
        bool second_ok=r.agrees_with_uncached(first,reverse?n:frequency_n);++cases;mismatches+=!second_ok;
    }
    // The fingerprint must examine the range that was copied, not a distant draw index.
    for(u32 stride:{8u,16u,32u,64u})for(u32 freq:{2u,4u,8u}) {
        upload_t r;rsx::interleaved_range_info b;b.real_offset_address=8192;b.attribute_stride=stride;
        b.locations.push_back({0,false,static_cast<u16>(freq)});
        r.m_vertex_layout.interleaved_blocks={&b};
        assert(r.agrees_with_uncached(32,freq));++cases;
        const auto at=b.real_offset_address+b.get_required_range(32,freq).first*stride;
        guest[at]^=std::byte{127};
        bool ok=r.agrees_with_uncached(32,freq);++cases;mismatches+=!ok;
        guest[at]^=std::byte{127};
    }
    // Different draw indices that use the exact same source range should share it.
    for(u32 kind=0;kind<2;++kind)for(u32 stride:{8u,16u,32u,64u}) {
        upload_t r;rsx::interleaved_range_info b;b.real_offset_address=12288;b.attribute_stride=stride;
        b.single_vertex=(kind==0);b.locations.push_back({0,false,4});r.m_vertex_layout.interleaved_blocks={&b};
        for(u32 first=32;first<36;++first){b.vertex_range={};assert(r.agrees_with_uncached(first,1));++cases;}
        reuse_uploads+=r.m_frame_stats.vertex_cache_miss_count;
    }
    // Unmodified ordinary arrays retain the same hits, and first-byte writes miss.
    for(u32 stride:{8u,16u,32u,64u})for(u32 first=0;first<64;++first) {
        upload_t r;rsx::interleaved_range_info b;b.real_offset_address=16384;b.attribute_stride=stride;b.locations.push_back({0,false,1});
        r.m_vertex_layout.interleaved_blocks={&b};
        for(u32 pass=0;pass<3;++pass){ordinary_mismatches+=!r.agrees_with_uncached(first,8);++cases;}
        assert(r.m_frame_stats.vertex_cache_miss_count==1);
        guest[b.real_offset_address+first*stride]^=std::byte{91};
        ordinary_mismatches+=!r.agrees_with_uncached(first,8);++cases;assert(r.m_frame_stats.vertex_cache_miss_count==2);
        guest[b.real_offset_address+first*stride]^=std::byte{91};
    }
    assert(ordinary_mismatches==0);
#ifdef CANDIDATE
    assert(mismatches==0);assert(reuse_uploads==8);
#else
    assert(mismatches>0);assert(reuse_uploads==32);
#endif
    std::cout<<"{\"cases\":"<<cases<<",\"wrong_range_reuses\":"<<mismatches
      <<",\"ordinary_mismatches\":"<<ordinary_mismatches<<",\"equivalent_range_uploads\":"<<reuse_uploads
      <<",\"weak_first_eight_byte_validation_unchanged\":true}"<<std::endl;
}
