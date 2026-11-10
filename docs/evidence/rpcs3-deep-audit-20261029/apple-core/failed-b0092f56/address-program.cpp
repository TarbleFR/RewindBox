#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <list>
#include <memory>
#include <random>
#include <span>
#include <string>
#include <tuple>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <vector>
#ifdef NDEBUG
#error "Assertions must remain enabled."
#endif
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using usz=std::size_t;
constexpr u32 umax=~u32{0};
// Host allocator observation is active only in a dedicated untimed lookup pass.
inline bool count_allocations=false;inline u64 allocations=0;
[[gnu::noinline]] void* operator new(std::size_t bytes){if(count_allocations)++allocations;if(void* p=std::malloc(bytes?bytes:1))return p;throw std::bad_alloc();}
[[gnu::noinline]] void operator delete(void* p)noexcept{std::free(p);}
[[gnu::noinline]] void operator delete(void* p,std::size_t)noexcept{std::free(p);}
[[gnu::noinline]] void* operator new[](std::size_t bytes){return ::operator new(bytes);}
[[gnu::noinline]] void operator delete[](void* p)noexcept{std::free(p);}
[[gnu::noinline]] void operator delete[](void* p,std::size_t)noexcept{std::free(p);}
template<class T>using atomic_t=std::atomic<T>;
#define ensure(x, ...) assert(x)
#define AUDIT(x) assert(x)
namespace fmt {
template<class...T>std::string format(const char* f,T...v){int n=std::snprintf(nullptr,0,f,v...);std::vector<char>b(n+1);std::snprintf(b.data(),b.size(),f,v...);return std::string(b.data(),n);}
template<class...T>[[noreturn]]void throw_exception(const char*,T...){std::abort();}
}
namespace utils {constexpr u32 get_page_size(){return 4096;}enum class protection{rw,ro,no};inline u64 get_tsc(){return 0;}}
namespace rpcs3::ios::texture_validation {inline std::atomic<u64> trim_calls{0},trim_sections{0},trim_bytes{0},trim_ticks{0},dirty_releases{0},dirty_release_bytes{0};}
namespace rpcs3::ios::texture_residency {inline u64 current_frame(){return 1;}}


namespace utils
{
	template <typename T>
	class address_range_vector;

	/**
	 * Helpers
	 */
	template <typename T>
	T page_start(T addr)
	{
		return addr & ~static_cast<T>(get_page_size() - 1);
	}

	template <typename T>
	static inline T next_page(T addr)
	{
		return page_start(addr) + static_cast<T>(get_page_size());
	}

	template <typename T>
	static inline T page_end(T addr)
	{
		return next_page(addr) - 1;
	}

	template <typename T>
	static inline T is_page_aligned(T val)
	{
		return (val & static_cast<T>(get_page_size() - 1)) == 0;
	}


	/**
	 * Address Range utility class
	 */
	template <typename T>
	class address_range
	{
	public:
		T start = umax; // First address in range
		T end = 0; // Last address

		using signed_type_t = std::make_signed<T>::type;

	private:
		// Helper constexprs
		static constexpr inline bool range_overlaps(T start1, T end1, T start2, T end2)
		{
			return (start1 <= end2 && start2 <= end1);
		}

		static constexpr inline bool address_overlaps(T address, T start, T end)
		{
			return (start <= address && address <= end);
		}

		static constexpr inline bool range_inside_range(T start1, T end1, T start2, T end2)
		{
			return (start1 >= start2 && end1 <= end2);
		}

		constexpr address_range(T _start, T _end) : start(_start), end(_end) {}

	public:
		// Constructors
		constexpr address_range() = default;

		static constexpr address_range start_length(T _start, T _length)
		{
			if (!_length)
			{
				return {};
			}

			const T _end = static_cast<T>(_start + _length - 1);
			return {_start, _end};
		}

		static constexpr address_range start_end(T _start, T _end)
		{
			return {_start, _end};
		}

		// Length
		T length() const
		{
			AUDIT(valid());
			return end - start + 1;
		}

		void set_length(const T new_length)
		{
			end = start + new_length - 1;
			ensure(valid());
		}

		T next_address() const
		{
			return end + 1;
		}

		T prev_address() const
		{
			return start - 1;
		}

		// Overlapping checks
		bool overlaps(const address_range<T>& other) const
		{
			AUDIT(valid() && other.valid());
			return range_overlaps(start, end, other.start, other.end);
		}

		bool overlaps(const T addr) const
		{
			AUDIT(valid());
			return address_overlaps(addr, start, end);
		}

		bool inside(const address_range<T>& other) const
		{
			AUDIT(valid() && other.valid());
			return range_inside_range(start, end, other.start, other.end);
		}

		inline bool inside(const address_range_vector<T>& vec) const;
		inline bool overlaps(const address_range_vector<T>& vec) const;

		bool touches(const address_range<T>& other) const
		{
			AUDIT(valid() && other.valid());
			// returns true if there is overlap, or if sections are side-by-side
			return overlaps(other) || other.start == next_address() || other.end == prev_address();
		}

		// Utilities
		signed_type_t signed_distance(const address_range<T>& other) const
		{
			if (touches(other))
			{
				return 0;
			}

			// other after this
			if (other.start > end)
			{
				return static_cast<signed_type_t>(other.start - end - 1);
			}

			// this after other
			AUDIT(start > other.end);
			return -static_cast<signed_type_t>(start - other.end - 1);
		}

		T distance(const address_range<T>& other) const
		{
			if (touches(other))
			{
				return 0;
			}

			// other after this
			if (other.start > end)
			{
				return (other.start - end - 1);
			}

			// this after other
			AUDIT(start > other.end);
			return (start - other.end - 1);
		}

		address_range<T> get_min_max(const address_range<T>& other) const
		{
			return {
				std::min(valid() ? start : umax, other.valid() ? other.start : umax),
				std::max(valid() ? end : 0, other.valid() ? other.end : 0)
			};
		}

		void set_min_max(const address_range<T>& other)
		{
			*this = get_min_max(other);
		}

		bool is_page_range() const
		{
			return (valid() && is_page_aligned(start) && is_page_aligned(length()));
		}

		address_range<T> to_page_range() const
		{
			AUDIT(valid());
			return { page_start(start), page_end(end) };
		}

		void page_align()
		{
			AUDIT(valid());
			start = page_start(start);
			end = page_end(end);
			AUDIT(is_page_range());
		}

		address_range<T> get_intersect(const address_range<T>& clamp) const
		{
			if (!valid() || !clamp.valid())
			{
				return {};
			}

			return { std::max(start, clamp.start), std::min(end, clamp.end) };
		}

		void intersect(const address_range<T>& clamp)
		{
			if (!clamp.valid())
			{
				invalidate();
			}
			else
			{
				start = std::max(start, clamp.start);
				end = std::min(end, clamp.end);
			}
		}

		// Validity
		bool valid() const
		{
			return (start <= end);
		}

		void invalidate()
		{
			start = umax;
			end = 0;
		}

		// Comparison Operators
		bool operator ==(const address_range<T>& other) const
		{
			return (start == other.start && end == other.end);
		}

		/**
		 * Debug
		 */
		std::string str() const
		{
			return fmt::format("{0x%x->0x%x}", start, end);
		}
	};

	using address_range16 = address_range<u16>;
	using address_range32 = address_range<u32>;
	using address_range64 = address_range<u64>;

	template <typename T>
	static inline address_range<T> page_for(T addr)
	{
		return address_range<T>::start_end(page_start(addr), page_end(addr));
	}


	/**
	 * Address Range Vector utility class
	 *
	 * Collection of address_range<T> objects. Allows for merging and removing ranges from the set.
	 */
	template <typename T>
	class address_range_vector
	{
	public:
		using vector_type = std::vector<address_range<T>>;
		using iterator = vector_type::iterator;
		using const_iterator = vector_type::const_iterator;
		using size_type = vector_type::size_type;

	private:
		vector_type data;

	public:
		// Wrapped functions
		inline void reserve(usz nr) { data.reserve(nr); }
		inline void clear() { data.clear(); }
		inline size_type size() const { return data.size(); }
		inline bool empty() const { return data.empty(); }
		inline address_range<T>& operator[](size_type n) { return data[n]; }
		inline const address_range<T>& operator[](size_type n) const { return data[n]; }
		inline iterator begin() { return data.begin(); }
		inline const_iterator begin() const { return data.begin(); }
		inline iterator end() { return data.end(); }
		inline const_iterator end() const { return data.end(); }

		// Search for ranges that touch new_range. If found, merge instead of adding new_range.
		// When adding a new range, re-use invalid ranges whenever possible
		void merge(const address_range<T>& new_range)
		{
			// Note the case where we have
			//   AAAA  BBBB
			//      CCCC
			// If we have data={A,B}, and new_range=C, we have to merge A with C, then B with A and invalidate B

			if (!new_range.valid())
			{
				return;
			}

			address_range<T> *found = nullptr;
			address_range<T> *invalid = nullptr;

			for (auto &existing : data)
			{
				if (!existing.valid())
				{
					invalid = &existing;
					continue;
				}

				// range1 overlaps, is immediately before, or is immediately after range2
				if (existing.touches(new_range))
				{
					if (found != nullptr)
					{
						// Already found a match, merge and invalidate "existing"
						found->set_min_max(existing);
						existing.invalidate();
					}
					else
					{
						// First match, merge "new_range"
						existing.set_min_max(new_range);
						found = &existing;
					}
				}
			}

			if (found != nullptr)
			{
				return;
			}

			if (invalid != nullptr)
			{
				*invalid = new_range;
			}
			else
			{
				data.push_back(new_range);
			}

			AUDIT(check_consistency());
		}

		void merge(const address_range_vector<T>& other)
		{
			for (const address_range<T>& new_range : other)
			{
				merge(new_range);
			}
		}

		// Exclude a given range from data
		void exclude(const address_range<T>& exclusion)
		{
			// Note the case where we have
			//    AAAAAAA
			//      EEE
			// where data={A} and exclusion=E.
			// In this case, we need to reduce A to the head (before E starts), and then create a new address_range<T> B for the tail (after E ends), i.e.
			//    AA   BB
			//      EEE

			if (!exclusion.valid())
			{
				return;
			}

			address_range<T> *invalid = nullptr; // try to re-use an invalid range instead of calling push_back

			// We use index access because we might have to push_back within the loop, which could invalidate the iterators
			size_type _size = data.size();
			for (size_type n = 0; n < _size; ++n)
			{
				address_range<T>& existing = data[n];

				if (!existing.valid())
				{
					// Null
					invalid = &existing;
					continue;
				}

				if (!existing.overlaps(exclusion))
				{
					// No overlap, skip
					continue;
				}

				const bool head_excluded = exclusion.overlaps(existing.start); // This section has its start inside excluded range
				const bool tail_excluded = exclusion.overlaps(existing.end); // This section has its end inside excluded range

				if (head_excluded && tail_excluded)
				{
					// Cannot be salvaged, fully excluded
					existing.invalidate();
					invalid = &existing;
				}
				else if (head_excluded)
				{
					// Head overlaps, truncate head
					existing.start = exclusion.next_address();
				}
				else if (tail_excluded)
				{
					// Tail overlaps, truncate tail
					existing.end = exclusion.prev_address();
				}
				else
				{
					// Section sits in the middle (see comment above function header)
					AUDIT(exclusion.inside(existing));
					const auto tail_end = existing.end;

					// Head
					existing.end = exclusion.prev_address();

					// Tail
					if (invalid != nullptr)
					{
						invalid->start = exclusion.next_address();
						invalid->end = tail_end;
						invalid = nullptr;
					}
					else
					{
						// IMPORTANT: adding to data invalidates "existing". This must be done last!
						data.push_back(address_range<T>::start_end(exclusion.next_address(), tail_end));
					}
				}
			}
			AUDIT(check_consistency());
			AUDIT(!overlaps(exclusion));
		}

		void exclude(const address_range_vector<T>& other)
		{
			for (const address_range<T>& exclusion : other)
			{
				exclude(exclusion);
			}
		}

		// Checks the consistency of this vector.
		// Will fail if ranges within the vector overlap our touch each-other
		bool check_consistency() const
		{
			const usz _size = data.size();

			for (usz i = 0; i < _size; ++i)
			{
				const auto &r1 = data[i];
				if (!r1.valid())
				{
					continue;
				}

				for (usz j = i + 1; j < _size; ++j)
				{
					const auto &r2 = data[j];
					if (!r2.valid())
					{
						continue;
					}

					if (r1.touches(r2))
					{
						return false;
					}
				}
			}
			return true;
		}

		// Test for overlap with a given range
		bool overlaps(const address_range<T>& range) const
		{
			return std::any_of(data.cbegin(), data.cend(), [&range](const address_range<T>& cur)
			{
				return cur.valid() && cur.overlaps(range);
			});
		}

		// Test for overlap with a given address_range<T> vector
		bool overlaps(const address_range_vector<T>& other) const
		{
			for (const address_range<T>& rng1 : data)
			{
				if (!rng1.valid())
				{
					continue;
				}

				for (const address_range<T>& rng2 : other.data)
				{
					if (!rng2.valid())
					{
						continue;
					}

					if (rng1.overlaps(rng2))
					{
						return true;
					}
				}
			}
			return false;
		}

		// Test if a given range is fully contained inside this vector
		bool contains(const address_range<T>& range) const
		{
			return std::any_of(this->begin(), this->end(), [&range](const address_range<T>& cur)
			{
				return cur.valid() && cur.inside(range);
			});
		}

		// Test if all ranges in this vector are full contained inside a specific range
		bool inside(const address_range<T>& range) const
		{
			return std::all_of(this->begin(), this->end(), [&range](const address_range<T>& cur)
			{
				return !cur.valid() || cur.inside(range);
			});
		}

		// Count valid entries
		usz valid_count() const
		{
			usz count = 0;
			for (const auto& e : data)
			{
				if (e.valid())
				{
					count++;
				}
			}
			return count;
		}
	};


	// These declarations must be done after address_range_vector has been defined
	template <typename T>
	bool address_range<T>::inside(const address_range_vector<T>& vec) const
	{
		return vec.contains(*this);
	}

	template <typename T>
	bool address_range<T>::overlaps(const address_range_vector<T>& vec) const
	{
		return vec.overlaps(*this);
	}

	using address_range_vector16 = address_range_vector<u16>;
	using address_range_vector32 = address_range_vector<u32>;
	using address_range_vector64 = address_range_vector<u64>;

} // namespace utils


namespace std
{
	static_assert(sizeof(usz) >= 2 * sizeof(u32), "usz must be at least twice the size of u32");

	template <>
	struct hash<utils::address_range32>
	{
		usz operator()(const utils::address_range32& k) const
		{
			// we can guarantee a unique hash since our type is 64 bits and usz as well
			return (usz{ k.start } << 32) | usz{ k.end };
		}
	};
}
using utils::address_range32;using utils::address_range_vector32;
struct Log {template<class...T>void warning(const char*,T...){} } rsx_log;
namespace rsx {
enum section_bounds {full_range,locked_range,confirmed_range};
enum class texture_upload_context{shader_read,blit_engine_src,blit_engine_dst,framebuffer_storage,dma};
enum class memory_read_flags{flush_once,flush_always};
enum class component_order{default_};
enum class texture_dimension_extended{texture_dimension_2d};
enum class section_protection_strategy{lock,hash};
inline section_protection_strategy default_texture_protection_strategy(u32){return section_protection_strategy::hash;}
inline u64 visits=0;inline bool tracing=true,count_visits=true;inline std::vector<u32> validations;
struct buffered_section {
 address_range32 cpu_range,locked_range,confirmed_range;
 utils::protection protection=utils::protection::rw;
 section_protection_strategy protection_strat=section_protection_strategy::hash;
 u64 mem_hash=0,validated_epoch=0;bool prehash_bypass=false,locked=false;
 bool memory_valid=true;u32 id=0;
 void init_lockable_range(const address_range32& r){locked_range=r.to_page_range();}
 void reset(const address_range32&);void invalidate_range();void discard();
 const address_range32& get_bounds(section_bounds)const;
 bool valid_range()const{return cpu_range.valid();}
 u32 get_section_base()const{return cpu_range.start;}
 u32 get_section_size()const{return valid_range()?cpu_range.length():0;}
 const address_range32& get_section_range()const{return cpu_range;}
 const address_range32& get_confirmed_range()const{return confirmed_range.valid()?confirmed_range:cpu_range;}
 bool is_locked(bool=false)const{return locked;}
 bool overlaps(const address_range32& range,section_bounds bounds)const{return get_bounds(bounds).overlaps(range);}
 bool matches(const address_range32& range)const{return valid_range()&&cpu_range==range;}
 bool sync()const{if(tracing)validations.push_back(id);return memory_valid;}
};
void buffered_section::reset(const address_range32& memory_range)
	{
		ensure(memory_range.valid() && locked == false);

		cpu_range = address_range32(memory_range);
		confirmed_range.invalidate();
		locked_range.invalidate();

		protection = utils::protection::rw;
		protection_strat = default_texture_protection_strategy(memory_range.length());
		locked = false;

		init_lockable_range(cpu_range);

		if (protection_strat == section_protection_strategy::hash)
		{
			mem_hash = 0;
		}
#ifdef RPCS3_IOS
		validated_epoch = 0;
		prehash_bypass = false;
#endif
	}
void buffered_section::invalidate_range()
	{
		ensure(!locked);

		cpu_range.invalidate();
		confirmed_range.invalidate();
		locked_range.invalidate();
	}
void buffered_section::discard()
	{
#ifdef TEXTURE_CACHE_DEBUG
		if (locked)
			tex_cache_checker.remove(locked_range, protection);
#endif

		protection = utils::protection::rw;
		confirmed_range.invalidate();
		locked = false;
#ifdef RPCS3_IOS
		validated_epoch = 0;
#endif
	}
const address_range32& buffered_section::get_bounds(section_bounds bounds) const
	{
		switch (bounds)
		{
		case section_bounds::full_range:
			return cpu_range;
		case section_bounds::locked_range:
			return locked_range;
		case section_bounds::confirmed_range:
			return confirmed_range.valid() ? confirmed_range : cpu_range;
		default:
			fmt::throw_exception("Unreachable");
		}
	}

}
namespace before {
using namespace rsx;
template <typename section_storage_type, usz array_size>
class ranged_storage_block_list
	{
		static_assert(array_size > 0, "array_elements must be positive non-zero");

	public:
		using value_type = section_storage_type;
		using array_type = std::array<value_type, array_size>;
		using list_type = std::list<array_type>;
		using size_type = u32;

		// Iterator
		template <typename T, typename block_list, typename list_iterator>
		class iterator_tmpl
		{
		public:
			// Traits
			using value_type = T;
			using pointer = T * ;
			using difference_type = int;
			using reference = T & ;
			using iterator_category = std::forward_iterator_tag;

			// Constructors
			iterator_tmpl() = default;
			iterator_tmpl(block_list *_block) :
				block(_block),
				list_it(_block->m_data.begin()),
				idx(0)
			{
				if (_block->empty())
					idx = u32{umax};
			}

		public:
			// Members
			block_list* block = nullptr;
			list_iterator list_it = {};
			size_type idx = u32{umax};
			size_type array_idx = 0;

			inline void next()
			{
				++idx;
				if (idx >= block->size())
				{
					idx = u32{umax};
					return;
				}

				++array_idx;
				if (array_idx >= array_size)
				{
					array_idx = 0;
					list_it++;
				}
			}

		public:
			inline reference operator*() const { return (*list_it)[array_idx]; }
			inline pointer operator->() const { return &((*list_it)[array_idx]); }
			inline reference operator++() { next(); return **this; }
			inline reference operator++(int) { auto &res = **this;  next(); return res; }
			inline bool operator==(const iterator_tmpl &rhs) const { return idx == rhs.idx; }
		};

		using iterator = iterator_tmpl<value_type, ranged_storage_block_list, typename list_type::iterator>;
		using const_iterator = iterator_tmpl<const value_type, const ranged_storage_block_list, typename list_type::const_iterator>;

		// Members
		size_type m_size = 0;
		list_type m_data;
		typename list_type::iterator m_data_it;
		size_type m_array_idx;
		size_type m_capacity;

		// Helpers
		inline void next_array()
		{
			if (m_data_it == m_data.end() || ++m_data_it == m_data.end())
			{
				m_data_it = m_data.emplace(m_data_it);
				m_capacity += array_size;
			}

			m_array_idx = 0;
		}

	public:
		// Constructor, Destructor
		ranged_storage_block_list() :
			m_data_it(m_data.end()),
			m_array_idx(-1),
			m_capacity(0)
		{}

		// Iterator
		inline iterator begin() noexcept { return { this }; }
		inline const_iterator begin() const noexcept { return { this }; }
		constexpr iterator end() noexcept { return {}; }
		constexpr const_iterator end() const noexcept { return {}; }

		// Operators
		inline value_type& front()
		{
			AUDIT(!empty());
			return m_data.front()[0];
		}

		inline value_type& back()
		{
			AUDIT(m_data_it != m_data.end() && m_array_idx < array_size);
			return (*m_data_it)[m_array_idx];
		}

		// Other operations on data
		inline size_type size() const { return m_size; }
		inline size_type capacity() const { return m_capacity; }
		inline bool empty() const { return m_size == 0; }

#ifdef RPCS3_IOS
		size_type index_of(const value_type& value) const
		{
			const auto address = reinterpret_cast<std::uintptr_t>(&value);
			size_type index = 0;
			for (const auto& array : m_data)
			{
				// Integer subtraction is defined even for unrelated allocations.
				// Table membership, not allocation address order, determines rank.
				const auto offset = address - reinterpret_cast<std::uintptr_t>(array.data());
				if (offset < sizeof(array_type))
				{
					ensure(offset % sizeof(value_type) == 0);
					index += static_cast<size_type>(offset / sizeof(value_type));
					ensure(index < m_size);
					return index;
				}
				index += array_size;
			}
			ensure(false);
			return umax;
		}
#endif

		inline void clear()
		{
			m_size = 0;
			m_array_idx = 0;
			m_data_it = m_data.begin();
		}

		inline void free()
		{
			m_size = 0;
			m_array_idx = 0;
			m_capacity = 0;
			m_data.clear();
			m_data_it = m_data.end();
		}

		inline void reserve(size_type new_size)
		{
			if (new_size <= m_capacity) return;
			size_type new_num_arrays = ((new_size - 1) / array_size) + 1;
			m_data.reserve(new_num_arrays);
			m_capacity = new_num_arrays * array_size;
		}

		template <typename ...Args>
		inline value_type& emplace_back(Args&&... args)
		{
			if (m_array_idx >= array_size)
			{
				next_array();
			}

			ensure(m_capacity > 0 && m_array_idx < array_size && m_data_it != m_data.end());

			value_type *dest = &((*m_data_it)[m_array_idx++]);
			new (dest) value_type(std::forward<Args>(args)...);
			++m_size;
			return *dest;
		}
	};
template <typename _ranged_storage_type>
class ranged_storage_block
	{
	public:
		using ranged_storage_type = _ranged_storage_type;
		using section_storage_type = typename ranged_storage_type::section_storage_type;
		using texture_cache_type = typename ranged_storage_type::texture_cache_type;

		//using block_container_type = std::list<section_storage_type>;
		using block_container_type = ranged_storage_block_list<section_storage_type, 64>;
		using iterator = typename block_container_type::iterator;
		using const_iterator = typename block_container_type::const_iterator;

		using size_type = typename block_container_type::size_type;

		static constexpr u32 num_blocks = ranged_storage_type::num_blocks;
		static constexpr u32 block_size = ranged_storage_type::block_size;

		using unowned_container_type = std::unordered_set<section_storage_type*>;
		using unowned_iterator = typename unowned_container_type::iterator;
		using unowned_const_iterator = typename unowned_container_type::const_iterator;
#ifdef RPCS3_IOS
		struct address_entry
		{
			u32 address;
			u32 order;
			section_storage_type* section;
		};
		static constexpr u32 address_index_threshold = 16;
#endif

	public:
		u32 index = 0;
		address_range32 range = {};
		block_container_type sections = {};
		unowned_container_type unowned; // pointers to sections from other blocks that overlap this block
		atomic_t<u32> exists_count = 0;
		atomic_t<u32> locked_count = 0;
		atomic_t<u32> unreleased_count = 0;
		ranged_storage_type *m_storage = nullptr;
#ifdef RPCS3_IOS
		// Sections live in stable list-of-array slots. Index only their addresses;
		// dirty/protection/format checks remain at the lookup site.
		std::vector<address_entry> m_address_index;

		static bool address_less(const address_entry& lhs, const address_entry& rhs)
		{
			return lhs.address < rhs.address || (lhs.address == rhs.address && lhs.order < rhs.order);
		}

		void remove_address_entry(section_storage_type& section)
		{
			if (m_address_index.empty()) return;
			// The old range is retired before reset publishes a new address.
			const address_entry entry{section.get_section_base(), sections.index_of(section), &section};
			const auto it = std::lower_bound(m_address_index.begin(), m_address_index.end(), entry, address_less);
			if (it != m_address_index.end() && it->section == &section) m_address_index.erase(it);
		}

		void add_address_entry(section_storage_type& section)
		{
			if (sections.size() <= address_index_threshold) return;
			const address_entry entry{section.get_section_base(), sections.index_of(section), &section};
			const auto pos = std::lower_bound(m_address_index.begin(), m_address_index.end(), entry, address_less);
			m_address_index.insert(pos, entry);
		}
#endif

		inline void add_owned_section_overlaps(section_storage_type &section)
		{
			u32 end = section.get_section_range().end;
			for (auto *block = next_block(); block != nullptr && end >= block->get_start(); block = block->next_block())
			{
				block->add_unowned_section(section);
			}
		}

		inline void remove_owned_section_overlaps(section_storage_type &section)
		{
			u32 end = section.get_section_range().end;
			for (auto *block = next_block(); block != nullptr && end >= block->get_start(); block = block->next_block())
			{
				block->remove_unowned_section(section);
			}
		}

	public:
		// Construction
		ranged_storage_block() = default;

		void initialize(u32 _index, ranged_storage_type *storage)
		{
			ensure(m_storage == nullptr && storage != nullptr);
			AUDIT(index < num_blocks);

			m_storage = storage;
			index = _index;
			range = address_range32::start_length(index * block_size, block_size);

			AUDIT(range.is_page_range() && get_start() / block_size == index);
		}

		/**
		 * Wrappers
		 */
		constexpr iterator begin() noexcept { return sections.begin(); }
		constexpr const_iterator begin() const noexcept { return sections.begin(); }
		inline iterator end() noexcept { return sections.end(); }
		inline const_iterator end() const noexcept { return sections.end(); }
		inline bool empty() const { return sections.empty(); }
		inline size_type size() const { return sections.size(); }
		inline u32 get_exists_count() const { return exists_count; }
		inline u32 get_locked_count() const { return locked_count; }
		inline u32 get_unreleased_count() const { return unreleased_count; }

		/**
		 * Utilities
		 */
		ranged_storage_type& get_storage() const
		{
			AUDIT(m_storage != nullptr);
			return *m_storage;
		}

		texture_cache_type& get_texture_cache() const
		{
			return get_storage().get_texture_cache();
		}

		inline section_storage_type& create_section()
		{
			auto &res = sections.emplace_back(this);
#ifdef RPCS3_IOS
			if (sections.size() == address_index_threshold + 1)
			{
				// Build once on crossing the small-block threshold, before callers
				// can search the larger block (even if this new slot stays empty).
				m_address_index.reserve(sections.size());
				u32 order = 0;
				for (auto& section : sections)
				{
					if (section.valid_range())
						m_address_index.push_back({section.get_section_base(), order, &section});
					++order;
				}
				std::sort(m_address_index.begin(), m_address_index.end(), address_less);
			}
#endif
			return res;
		}

#ifdef RPCS3_IOS
		std::span<const address_entry> find_address(u32 address) const
		{
			const auto first = std::lower_bound(m_address_index.begin(), m_address_index.end(), address,
				[](const address_entry& entry, u32 value) { return entry.address < value; });
			const auto last = std::upper_bound(first, m_address_index.end(), address,
				[](u32 value, const address_entry& entry) { return value < entry.address; });
			return {first, last};
		}
#endif

		inline void clear()
		{
#ifdef RPCS3_IOS
			// Bulk clear owns the cache lock. Drop this index before callbacks so
			// destroying N sections does not perform N vector compactions.
			m_address_index.clear();
#endif
			for (auto &section : *this)
			{
				if (section.is_locked())
					section.unprotect();

				section.destroy();
#ifdef RPCS3_IOS
				// Resource-less sections may still belong to adjacent blocks.
				section.invalidate_range();
#endif
			}

			AUDIT(exists_count == 0);
			AUDIT(unreleased_count == 0);
			AUDIT(locked_count == 0);
			sections.clear();
		}

		inline bool is_first_block() const
		{
			return index == 0;
		}

		inline bool is_last_block() const
		{
			return index == num_blocks - 1;
		}

		inline ranged_storage_block* prev_block() const
		{
			if (is_first_block()) return nullptr;
			return &get_storage()[index - 1];
		}

		inline ranged_storage_block* next_block() const
		{
			if (is_last_block()) return nullptr;
			return &get_storage()[index + 1];
		}

		// Address range
		inline const address_range32& get_range() const { return range; }
		inline u32 get_start() const { return range.start; }
		inline u32 get_end() const { return range.end; }
		inline u32 get_index() const { return index; }
		inline bool overlaps(const section_storage_type& section, section_bounds bounds = full_range) const { return section.overlaps(range, bounds); }
		inline bool overlaps(const address_range32& _range) const { return range.overlaps(_range); }

		/**
		 * Section callbacks
		 */
		inline void on_section_protected(const section_storage_type &section)
		{
			(void)section; // silence unused warning without _AUDIT
			AUDIT(section.is_locked());
			locked_count++;
		}

		inline void on_section_unprotected(const section_storage_type &section)
		{
			(void)section; // silence unused warning without _AUDIT
			AUDIT(!section.is_locked());
			u32 prev_locked = locked_count--;
			ensure(prev_locked > 0);
		}

		inline void on_section_range_valid(section_storage_type &section)
		{
			AUDIT(section.valid_range());
			AUDIT(range.overlaps(section.get_section_base()));
			add_owned_section_overlaps(section);
#ifdef RPCS3_IOS
			add_address_entry(section);
#endif
		}

		inline void on_section_range_invalid(section_storage_type &section)
		{
			AUDIT(section.valid_range());
			AUDIT(range.overlaps(section.get_section_base()));
			remove_owned_section_overlaps(section);
#ifdef RPCS3_IOS
			remove_address_entry(section);
#endif
		}

		inline void on_section_resources_created(const section_storage_type &section)
		{
			(void)section; // silence unused warning without _AUDIT
			AUDIT(section.exists());

			u32 prev_exists = exists_count++;

			if (prev_exists == 0)
			{
				m_storage->on_ranged_block_first_section_created(*this);
			}
		}

		inline void on_section_resources_destroyed(const section_storage_type &section)
		{
			(void)section; // silence unused warning without _AUDIT
			AUDIT(!section.exists());

			u32 prev_exists = exists_count--;
			ensure(prev_exists > 0);

			if (prev_exists == 1)
			{
				m_storage->on_ranged_block_last_section_destroyed(*this);
			}
		}

		void on_section_released(const section_storage_type &/*section*/)
		{
			u32 prev_unreleased = unreleased_count--;
			ensure(prev_unreleased > 0);
		}

		void on_section_unreleased(const section_storage_type &/*section*/)
		{
			unreleased_count++;
		}


		/**
		 * Overlapping sections
		 */
		inline bool contains_unowned(section_storage_type &section) const
		{
			return (unowned.find(&section) != unowned.end());
		}

		inline void add_unowned_section(section_storage_type &section)
		{
			AUDIT(overlaps(section));
			AUDIT(section.get_section_base() < range.start);
			AUDIT(!contains_unowned(section));
			unowned.insert(&section);
		}

		inline void remove_unowned_section(section_storage_type &section)
		{
			AUDIT(overlaps(section));
			AUDIT(section.get_section_base() < range.start);
			AUDIT(contains_unowned(section));
			unowned.erase(&section);
		}

		inline unowned_iterator unowned_begin() { return unowned.begin(); }
		inline unowned_const_iterator unowned_begin() const { return unowned.begin(); }
		inline unowned_iterator unowned_end() { return unowned.end(); }
		inline unowned_const_iterator unowned_end() const { return unowned.end(); }
		inline bool unowned_empty() const { return unowned.empty(); }
	};
template <typename traits>
class ranged_storage
	{
	public:
		static constexpr u32 block_size = 0x100000;
		static_assert(block_size % 4096u == 0, "block_size must be a multiple of the page size");
		static constexpr u32 num_blocks = u32{0x100000000ull / block_size};
		static_assert((num_blocks > 0) && (u64{num_blocks} *block_size == 0x100000000ull), "Invalid block_size/num_blocks");

		using section_storage_type = typename traits::section_storage_type;
		using texture_cache_type   = typename traits::texture_cache_base_type;
		using block_type           = ranged_storage_block<ranged_storage>;

	public:
		block_type blocks[num_blocks];
		texture_cache_type *m_tex_cache;
		std::unordered_set<block_type*> m_in_use;

	public:
		atomic_t<u32> m_unreleased_texture_objects = { 0 }; //Number of invalidated objects not yet freed from memory
		atomic_t<u64> m_texture_memory_in_use = { 0 };

		// Constructor
		ranged_storage(texture_cache_type *tex_cache) :
			m_tex_cache(tex_cache)
		{
			// Initialize blocks
			for (u32 i = 0; i < num_blocks; i++)
			{
				blocks[i].initialize(i, this);
			}
		}

		/**
		 * Iterators
		 */

		constexpr auto begin() { return std::begin(blocks); }
		constexpr auto begin() const { return std::begin(blocks); }
		constexpr auto end() { return std::end(blocks); }
		constexpr auto end() const { return std::end(blocks); }

		/**
		 * Utilities
		 */
		inline block_type& block_for(u32 address)
		{
			return blocks[address / block_size];
		}

		inline const block_type& block_for(u32 address) const
		{
			return blocks[address / block_size];
		}

		inline block_type& block_for(const address_range32 &range)
		{
			AUDIT(range.valid());
			return block_for(range.start);
		}

		inline block_type& block_for(const section_storage_type &section)
		{
			return block_for(section.get_section_base());
		}

		inline block_type& operator[](usz pos)
		{
			AUDIT(pos < num_blocks);
			return blocks[pos];
		}

		inline texture_cache_type& get_texture_cache() const
		{
			AUDIT(m_tex_cache != nullptr);
			return *m_tex_cache;
		}


		/**
		 * Blocks
		 */

		void clear()
		{
			for (auto &block : *this)
			{
				block.clear();
			}

			m_in_use.clear();

			AUDIT(m_unreleased_texture_objects == 0);
			AUDIT(m_texture_memory_in_use == 0);
		}

		void purge_unreleased_sections()
		{
			std::vector<section_storage_type*> textures_to_remove;

			// Reclaims all graphics memory consumed by dirty textures
			// Do not destroy anything while iterating or you will end up with stale iterators
			for (auto& block : m_in_use)
			{
				if (block->get_unreleased_count() > 0)
				{
					for (auto& tex : *block)
					{
						if (!tex.is_unreleased())
							continue;

						ensure(!tex.is_locked());
						textures_to_remove.push_back(&tex);
					}
				}
			}

			for (auto& tex : textures_to_remove)
			{
				tex->destroy();
			}

			AUDIT(m_unreleased_texture_objects == 0);
		}

		bool purge_unlocked_sections()
		{
			// Reclaims all graphics memory consumed by unlocked textures
			// Do not destroy anything while iterating or you will end up with stale iterators
			std::vector<section_storage_type*> textures_to_remove;

			for (auto& block : m_in_use)
			{
				if (block->get_exists_count() > block->get_locked_count())
				{
					for (auto& tex : *block)
					{
						if (tex.get_context() == rsx::texture_upload_context::framebuffer_storage ||
							tex.is_locked() ||
							!tex.exists())
						{
							continue;
						}

						ensure(!tex.is_locked() && tex.exists());
						textures_to_remove.push_back(&tex);
					}
				}
			}

			for (auto& tex : textures_to_remove)
			{
				tex->destroy();
			}

			return !textures_to_remove.empty();
		}

		void trim_sections()
		{
#ifdef RPCS3_IOS
			// One timer pair per maintenance pass, never per texture. On-demand
			// validation remains unchanged; these observations distinguish it
			// from the full maintenance walk before changing its memory policy.
			const auto trim_begin = utils::get_tsc();
			u64 observed_sections = 0, observed_bytes = 0;
#endif
			for (auto it = m_in_use.begin(); it != m_in_use.end(); it++)
			{
				auto* block = *it;
				if (block->get_locked_count() > 256)
				{
					for (auto& tex : *block)
					{
						if (tex.is_locked() && !tex.is_locked(true))
						{
#ifdef RPCS3_IOS
							++observed_sections;
							observed_bytes += tex.get_confirmed_range().length();
							// CELL573_TEXTURE_RESIDENCY: a maintenance validation is not a use.
							tex.sync_protection_untouched();
#else
							tex.sync_protection();
#endif
						}
					}
				}
			}
#ifdef RPCS3_IOS
			rpcs3::ios::texture_validation::trim_calls.fetch_add(1, std::memory_order_relaxed);
			rpcs3::ios::texture_validation::trim_sections.fetch_add(observed_sections, std::memory_order_relaxed);
			rpcs3::ios::texture_validation::trim_bytes.fetch_add(observed_bytes, std::memory_order_relaxed);
			rpcs3::ios::texture_validation::trim_ticks.fetch_add(utils::get_tsc() - trim_begin, std::memory_order_relaxed);
#endif
		}


		/**
		 * Callbacks
		 */
		void on_section_released(const section_storage_type &/*section*/)
		{
			u32 prev_unreleased = m_unreleased_texture_objects--;
			ensure(prev_unreleased > 0);
		}

		void on_section_unreleased(const section_storage_type &/*section*/)
		{
			m_unreleased_texture_objects++;
		}

		void on_section_resources_created(const section_storage_type &section)
		{
			m_texture_memory_in_use += section.get_section_size();
		}

		void on_section_resources_destroyed(const section_storage_type &section)
		{
			u64 size = section.get_section_size();
			u64 prev_size = m_texture_memory_in_use.fetch_sub(size);
			ensure(prev_size >= size);
		}

		void on_ranged_block_first_section_created(block_type& block)
		{
			AUDIT(m_in_use.find(&block) == m_in_use.end());
			m_in_use.insert(&block);
		}

		void on_ranged_block_last_section_destroyed(block_type& block)
		{
			AUDIT(m_in_use.find(&block) != m_in_use.end());
			m_in_use.erase(&block);
		}

		/**
		 * Ranged Iterator
		 */
		 // Iterator
		template <typename T, typename unowned_iterator, typename section_iterator, typename block_type, typename parent_type>
		class range_iterator_tmpl
		{
		public:
			// Traits
			using value_type = T;
			using pointer = T * ;
			using difference_type = int;
			using reference = T & ;
			using iterator_category = std::forward_iterator_tag;

			// Constructors
			range_iterator_tmpl() = default; // end iterator

			explicit range_iterator_tmpl(parent_type &storage, const address_range32 &_range, section_bounds _bounds, bool _locked_only)
				: range(_range)
				, bounds(_bounds)
				, block(&storage.block_for(range.start))
				, unowned_remaining(true)
				, unowned_it(block->unowned_begin())
				, cur_block_it(block->begin())
				, locked_only(_locked_only)
			{
				// do a "fake" iteration to ensure the internal state is consistent
				next(false);
			}

		public:
			// Members
			address_range32 range;
			section_bounds bounds {};

			block_type* block = nullptr;
			bool needs_overlap_check = true;
			bool unowned_remaining = false;
			unowned_iterator unowned_it = {};
			section_iterator cur_block_it = {};
			pointer obj = nullptr;
			bool locked_only = false;

			inline void next(bool iterate = true)
			{
				AUDIT(block != nullptr);

				if (unowned_remaining)
				{
					do
					{
						// Still have "unowned" sections from blocks before the range to loop through
						auto blk_end = block->unowned_end();
						if (iterate && unowned_it != blk_end)
						{
							++unowned_it;
						}

						if (unowned_it != blk_end)
						{
							obj = *unowned_it;
							if (obj->valid_range() && (!locked_only || obj->is_locked()) && obj->overlaps(range, bounds))
								return;

							iterate = true;
							continue;
						}

						// No more unowned sections remaining
						unowned_remaining = false;
						iterate = false;
						break;

					} while (true);
				}

				// Go to next block
				do
				{
					// Iterate current block
					do
					{
						auto blk_end = block->end();
						if (iterate && cur_block_it != blk_end)
						{
							++cur_block_it;
						}

						if (cur_block_it != blk_end)
						{
							obj = &(*cur_block_it);
							if (obj->valid_range() && (!locked_only || obj->is_locked()) && (!needs_overlap_check || obj->overlaps(range, bounds)))
								return;

							iterate = true;
							continue;
						}
						break;

					} while (true);

					// Move to next block(s)
					do
					{
						block = block->next_block();
						if (block == nullptr || block->get_start() > range.end) // Reached end
						{
							block = nullptr;
							obj = nullptr;
							return;
						}

						needs_overlap_check = (block->get_end() > range.end);
						cur_block_it = block->begin();
						iterate = false;
					} while (locked_only && block->get_locked_count() == 0); // find a block with locked sections

				} while (true);
			}

		public:
			inline reference operator*() const { return *obj; }
			inline pointer operator->() const { return obj; }
			inline reference operator++() { next(); return *obj; }
			inline reference operator++(int) { auto *ptr = obj; next(); return *ptr; }
			inline bool operator==(const range_iterator_tmpl &rhs) const { return obj == rhs.obj && unowned_remaining == rhs.unowned_remaining; }

			inline void set_end(u32 new_end)
			{
				range.end = new_end;

				// If we've exceeded the new end, invalidate iterator
				if (block->get_start() > range.end)
				{
					block = nullptr;
				}
			}

			inline block_type& get_block() const
			{
				AUDIT(block != nullptr);
				return *block;
			}

			inline section_bounds get_bounds() const
			{
				return bounds;
			}
		};

		using range_iterator = range_iterator_tmpl<section_storage_type, typename block_type::unowned_iterator, typename block_type::iterator, block_type, ranged_storage>;
		using range_const_iterator = range_iterator_tmpl<const section_storage_type, typename block_type::unowned_const_iterator, typename block_type::const_iterator, const block_type, const ranged_storage>;

		inline range_iterator range_begin(const address_range32 &range, section_bounds bounds, bool locked_only = false) {
			return range_iterator(*this, range, bounds, locked_only);
		}

		inline range_const_iterator range_begin(const address_range32 &range, section_bounds bounds, bool locked_only = false) const {
			return range_const_iterator(*this, range, bounds, locked_only);
		}

		inline range_const_iterator range_begin(u32 address, section_bounds bounds, bool locked_only = false) const {
			return range_const_iterator(*this, address_range32::start_length(address, 1), bounds, locked_only);
		}

		constexpr range_iterator range_end()
		{
			return range_iterator();
		}

		constexpr range_const_iterator range_end() const
		{
			return range_const_iterator();
		}

		/**
		 * Debug
		 */
#ifdef TEXTURE_CACHE_DEBUG
		void verify_protection(bool recount = false)
		{
			if (recount)
			{
				// Reset calculated part of the page_info struct
				tex_cache_checker.reset_refcount();

				// Go through all blocks and update calculated values
				for (auto &block : *this)
				{
					for (auto &tex : block)
					{
						if (tex.is_locked())
						{
							tex_cache_checker.add(tex.get_locked_range(), tex.get_protection());
						}
					}
				}
			}

			// Verify
			tex_cache_checker.verify();
		}
#endif //TEXTURE_CACHE_DEBUG

	};

struct Cache;struct Section;struct Traits{using section_storage_type=Section;using texture_cache_base_type=Cache;};
struct Predictor{};
struct Section:rsx::buffered_section {
 using ranged_storage_type=ranged_storage<Traits>;
 using ranged_storage_block_type=ranged_storage_block<ranged_storage_type>;
 ranged_storage_block_type* m_block=nullptr;ranged_storage_type* m_storage=nullptr;Cache* m_tex_cache=nullptr;Predictor* m_predictor=nullptr;
 bool dirty=true,resources=false,triggered_exists_callbacks=false,triggered_unreleased_callbacks=false;
 u16 width=0,height=0,depth=0,mipmaps=0;u32 real_pitch=0,rsx_pitch=0,gcm_format=0;
 bool pack_unpack_swap_bytes=false,swizzled=false,synchronized=false,flushed=false,speculatively_flushed=false,deferred_commit=false;
 u64 sync_timestamp=0,cache_tag=0,last_write_tag=0,last_use_frame=0;void* m_predictor_entry=nullptr;
 memory_read_flags readback_behaviour=memory_read_flags::flush_once;component_order view_flags=component_order::default_;
 texture_upload_context context=texture_upload_context::shader_read;texture_dimension_extended image_type=texture_dimension_extended::texture_dimension_2d;
 std::vector<address_range32> flush_exclusions;
 Section()=default;explicit Section(ranged_storage_block_type* b){initialize(b);}
 Section* derived(){return this;}
 void initialize(ranged_storage_block_type*);void reset(const address_range32&);void notify_range_valid();void invalidate_range();
 void on_section_resources_created();void on_section_resources_destroyed();void set_dirty(bool);void update_unreleased();bool is_unreleased()const;
 bool sync_protection();bool matches(u32,u32,u32,u32,u32)const;bool matches(u32,u32,u32,u32,u32,u32)const;
 bool is_dirty()const{if(rsx::count_visits)++rsx::visits;return dirty;}
 bool exists()const{return resources||(context==texture_upload_context::dma&&locked);}
 bool is_managed()const{return true;}
 texture_upload_context get_context()const{return context;}
 void destroy(){if(resources){resources=false;on_section_resources_destroyed();}}
 void unprotect();
 void discard(bool make_dirty);
 bool sync_protection_untouched(){return sync_protection();}
};
struct Cache {
 using Storage=ranged_storage<Traits>;using ranged_storage_block=typename Storage::block_type;using section_storage_type=Section;
 Storage m_storage{this};Predictor predictor;
 Predictor& get_predictor(){return predictor;}
 void on_memory_read_flags_changed(Section&,memory_read_flags){}
 ~Cache(){m_storage.clear();}
 template <bool check_unlocked=false>
section_storage_type *find_texture_from_dimensions(u32 rsx_address, u32 format, u16 width = 0, u16 height = 0, u16 depth = 0, u16 mipmaps = 0)
		{
			auto &block = m_storage.block_for(rsx_address);
#ifdef RPCS3_IOS
			// The compressed lookup holds the cache reader lock. Presentation
			// uses check_unlocked=true without that lock and keeps its old walk.
			if constexpr (!check_unlocked)
			{
				if (block.size() > ranged_storage_block::address_index_threshold)
				{
					// Same-address candidates retain their original slot order. The
					// index never certifies contents, dimensions or protection.
					for (const auto& entry : block.find_address(rsx_address))
					{
						auto& tex = *entry.section;
						if constexpr (check_unlocked)
						{
							if (!tex.is_locked()) continue;
						}
						if (!tex.is_dirty() && tex.matches(rsx_address, format, width, height, depth, mipmaps) && tex.sync_protection())
							return &tex;
					}
					return nullptr;
				}
			}
#endif
			for (auto &tex : block)
			{
				if constexpr (check_unlocked)
				{
					if (!tex.is_locked())
					{
						continue;
					}
				}

				if (!tex.is_dirty() &&
					tex.matches(rsx_address, format, width, height, depth, mipmaps) &&
					tex.sync_protection())
				{
					return &tex;
				}
			}

			return nullptr;
		}
};
void Section::unprotect(){if(locked){locked=false;m_block->on_section_unprotected(*this);set_dirty(true);}}
void Section::discard(bool make_dirty){if(locked){rsx::buffered_section::discard();m_block->on_section_unprotected(*this);}if(make_dirty)set_dirty(true);}
void Section::initialize(ranged_storage_block_type* block)
		{
			ensure(m_block == nullptr && m_tex_cache == nullptr && m_storage == nullptr);
			m_block = block;
			m_storage = &block->get_storage();
			m_tex_cache = &block->get_texture_cache();
			m_predictor = &m_tex_cache->get_predictor();

			update_unreleased();
		}
void Section::reset(const address_range32& memory_range)
		{
			AUDIT(memory_range.valid());
			AUDIT(!is_locked());

			// Destroy if necessary
			destroy();
#ifdef RPCS3_IOS
			// destroy() can leave a resource-less range valid. Retire its index
			// and adjacent-block memberships before replacing that range.
			invalidate_range();
#endif

			// Superclass
			rsx::buffered_section::reset(memory_range);

			// Reset member variables to the default
			width = 0;
			height = 0;
			depth = 0;
			mipmaps = 0;

			real_pitch = 0;
			rsx_pitch = 0;

			gcm_format = 0;
			pack_unpack_swap_bytes = false;
			swizzled = false;

			sync_timestamp = 0ull;
			synchronized = false;
			flushed = false;
			speculatively_flushed = false;
#ifdef RPCS3_IOS
			deferred_commit = false;
#endif

			cache_tag = 0ull;
			last_write_tag = 0ull;
#ifdef RPCS3_IOS
			last_use_frame = rpcs3::ios::texture_residency::current_frame();
#endif

			m_predictor_entry = nullptr;

			readback_behaviour = rsx::memory_read_flags::flush_once;
			view_flags = rsx::component_order::default_;
			context = rsx::texture_upload_context::shader_read;
			image_type = rsx::texture_dimension_extended::texture_dimension_2d;

			flush_exclusions.clear();

			// Set to dirty
			set_dirty(true);

			// Notify that our CPU range is now valid
			notify_range_valid();
		}
void Section::notify_range_valid()
		{
			AUDIT(valid_range());

			// Callbacks
			m_block->on_section_range_valid(*derived());
			//m_storage->on_section_range_valid(*derived());

			// Reset texture_cache m_flush_always_cache
			if (readback_behaviour == memory_read_flags::flush_always)
			{
				m_tex_cache->on_memory_read_flags_changed(*derived(), memory_read_flags::flush_always);
			}
		}
void Section::invalidate_range()
		{
			if (!valid_range())
				return;

			// Reset texture_cache m_flush_always_cache
			if (readback_behaviour == memory_read_flags::flush_always)
			{
				m_tex_cache->on_memory_read_flags_changed(*derived(), memory_read_flags::flush_once);
			}

			// Notify the storage block that we are now invalid
			m_block->on_section_range_invalid(*derived());
			//m_storage->on_section_range_invalid(*derived());

			m_predictor_entry = nullptr;
			speculatively_flushed = false;
			buffered_section::invalidate_range();
		}
void Section::on_section_resources_created()
		{
			AUDIT(exists());
			AUDIT(valid_range());

			if (triggered_exists_callbacks) return;
			triggered_exists_callbacks = true;

			// Callbacks
			m_block->on_section_resources_created(*derived());
			m_storage->on_section_resources_created(*derived());
		}
void Section::on_section_resources_destroyed()
		{
			if (!triggered_exists_callbacks) return;
			triggered_exists_callbacks = false;

			AUDIT(valid_range());
			ensure(!is_locked());
			ensure(is_managed());

			// Set dirty
			set_dirty(true);

			// Trigger callbacks
			m_block->on_section_resources_destroyed(*derived());
			m_storage->on_section_resources_destroyed(*derived());

			// Invalidate range
			invalidate_range();
		}
void Section::set_dirty(bool new_dirty)
		{
			if (new_dirty == false && !is_locked() && context == texture_upload_context::shader_read)
				return;

			dirty = new_dirty;

			AUDIT(dirty || exists());

			update_unreleased();
		}
void Section::update_unreleased()
		{
			bool unreleased = is_unreleased();

			if (unreleased && !triggered_unreleased_callbacks)
			{
				triggered_unreleased_callbacks = true;
				m_block->on_section_unreleased(*derived());
				m_storage->on_section_unreleased(*derived());
			}
			else if (!unreleased && triggered_unreleased_callbacks)
			{
				triggered_unreleased_callbacks = false;
				m_block->on_section_released(*derived());
				m_storage->on_section_released(*derived());
			}
		}
bool Section::is_unreleased() const
		{
			return exists() && is_dirty() && !is_locked();
		}
bool Section::sync_protection()
		{
#ifdef RPCS3_IOS
			// CELL559_DIRTY_HASH_SKIP: a dirty section is never sampled before it
			// is recreated, so validating it can only decide its release. Under the
			// hash strategy release it as a mismatch would, without hashing memory
			// that cannot make it valid again. Page-locked sections are unchanged.
			if (is_dirty() && is_locked() && !is_locked(true))
			{
				rpcs3::ios::texture_validation::dirty_releases.fetch_add(1, std::memory_order_relaxed);
				rpcs3::ios::texture_validation::dirty_release_bytes.fetch_add(get_confirmed_range().length(), std::memory_order_relaxed);
				discard(true);
				return false;
			}
#endif
			if (!buffered_section::sync())
			{
				discard(true);
				ensure(is_dirty());
				return false;
			}

#ifdef RPCS3_IOS
			last_use_frame = rpcs3::ios::texture_residency::current_frame();
#endif
			return true;
		}
bool Section::matches(u32 format, u32 width, u32 height, u32 depth, u32 mipmaps) const
		{
			if (!valid_range())
				return false;

			if (format && gcm_format != format)
				return false;

			if (!width && !height && !depth && !mipmaps)
				return true;

			if (width && width != this->width)
				return false;

			if (height && height != this->height)
				return false;

			if (depth && depth != this->depth)
				return false;

			if (mipmaps && mipmaps > this->mipmaps)
				return false;

			return true;
		}
bool Section::matches(u32 rsx_address, u32 format, u32 width, u32 height, u32 depth, u32 mipmaps) const
		{
			if (!valid_range())
				return false;

			if (rsx_address != get_section_base())
				return false;

			return matches(format, width, height, depth, mipmaps);
		}
}
namespace after {
using namespace rsx;
template <typename section_storage_type, usz array_size>
class ranged_storage_block_list
	{
		static_assert(array_size > 0, "array_elements must be positive non-zero");

	public:
		using value_type = section_storage_type;
		using array_type = std::array<value_type, array_size>;
		using list_type = std::list<array_type>;
		using size_type = u32;

		// Iterator
		template <typename T, typename block_list, typename list_iterator>
		class iterator_tmpl
		{
		public:
			// Traits
			using value_type = T;
			using pointer = T * ;
			using difference_type = int;
			using reference = T & ;
			using iterator_category = std::forward_iterator_tag;

			// Constructors
			iterator_tmpl() = default;
			iterator_tmpl(block_list *_block) :
				block(_block),
				list_it(_block->m_data.begin()),
				idx(0)
			{
				if (_block->empty())
					idx = u32{umax};
			}

		public:
			// Members
			block_list* block = nullptr;
			list_iterator list_it = {};
			size_type idx = u32{umax};
			size_type array_idx = 0;

			inline void next()
			{
				++idx;
				if (idx >= block->size())
				{
					idx = u32{umax};
					return;
				}

				++array_idx;
				if (array_idx >= array_size)
				{
					array_idx = 0;
					list_it++;
				}
			}

		public:
			inline reference operator*() const { return (*list_it)[array_idx]; }
			inline pointer operator->() const { return &((*list_it)[array_idx]); }
			inline reference operator++() { next(); return **this; }
			inline reference operator++(int) { auto &res = **this;  next(); return res; }
			inline bool operator==(const iterator_tmpl &rhs) const { return idx == rhs.idx; }
		};

		using iterator = iterator_tmpl<value_type, ranged_storage_block_list, typename list_type::iterator>;
		using const_iterator = iterator_tmpl<const value_type, const ranged_storage_block_list, typename list_type::const_iterator>;

		// Members
		size_type m_size = 0;
		list_type m_data;
		typename list_type::iterator m_data_it;
		size_type m_array_idx;
		size_type m_capacity;

		// Helpers
		inline void next_array()
		{
			if (m_data_it == m_data.end() || ++m_data_it == m_data.end())
			{
				m_data_it = m_data.emplace(m_data_it);
				m_capacity += array_size;
			}

			m_array_idx = 0;
		}

	public:
		// Constructor, Destructor
		ranged_storage_block_list() :
			m_data_it(m_data.end()),
			m_array_idx(-1),
			m_capacity(0)
		{}

		// Iterator
		inline iterator begin() noexcept { return { this }; }
		inline const_iterator begin() const noexcept { return { this }; }
		constexpr iterator end() noexcept { return {}; }
		constexpr const_iterator end() const noexcept { return {}; }

		// Operators
		inline value_type& front()
		{
			AUDIT(!empty());
			return m_data.front()[0];
		}

		inline value_type& back()
		{
			AUDIT(m_data_it != m_data.end() && m_array_idx < array_size);
			return (*m_data_it)[m_array_idx];
		}

		// Other operations on data
		inline size_type size() const { return m_size; }
		inline size_type capacity() const { return m_capacity; }
		inline bool empty() const { return m_size == 0; }

#ifdef RPCS3_IOS
		size_type index_of(const value_type& value) const
		{
			const auto address = reinterpret_cast<std::uintptr_t>(&value);
			size_type index = 0;
			for (const auto& array : m_data)
			{
				// Integer subtraction is defined even for unrelated allocations.
				// Table membership, not allocation address order, determines rank.
				const auto offset = address - reinterpret_cast<std::uintptr_t>(array.data());
				if (offset < sizeof(array_type))
				{
					ensure(offset % sizeof(value_type) == 0);
					index += static_cast<size_type>(offset / sizeof(value_type));
					ensure(index < m_size);
					return index;
				}
				index += array_size;
			}
			ensure(false);
			return umax;
		}
#endif

		inline void clear()
		{
			m_size = 0;
			m_array_idx = 0;
			m_data_it = m_data.begin();
		}

		inline void free()
		{
			m_size = 0;
			m_array_idx = 0;
			m_capacity = 0;
			m_data.clear();
			m_data_it = m_data.end();
		}

		inline void reserve(size_type new_size)
		{
			if (new_size <= m_capacity) return;
			size_type new_num_arrays = ((new_size - 1) / array_size) + 1;
			m_data.reserve(new_num_arrays);
			m_capacity = new_num_arrays * array_size;
		}

		template <typename ...Args>
		inline value_type& emplace_back(Args&&... args)
		{
			if (m_array_idx >= array_size)
			{
				next_array();
			}

			ensure(m_capacity > 0 && m_array_idx < array_size && m_data_it != m_data.end());

			value_type *dest = &((*m_data_it)[m_array_idx++]);
			new (dest) value_type(std::forward<Args>(args)...);
			++m_size;
			return *dest;
		}
	};
template <typename _ranged_storage_type>
class ranged_storage_block
	{
	public:
		using ranged_storage_type = _ranged_storage_type;
		using section_storage_type = typename ranged_storage_type::section_storage_type;
		using texture_cache_type = typename ranged_storage_type::texture_cache_type;

		//using block_container_type = std::list<section_storage_type>;
		using block_container_type = ranged_storage_block_list<section_storage_type, 64>;
		using iterator = typename block_container_type::iterator;
		using const_iterator = typename block_container_type::const_iterator;

		using size_type = typename block_container_type::size_type;

		static constexpr u32 num_blocks = ranged_storage_type::num_blocks;
		static constexpr u32 block_size = ranged_storage_type::block_size;

		using unowned_container_type = std::unordered_set<section_storage_type*>;
		using unowned_iterator = typename unowned_container_type::iterator;
		using unowned_const_iterator = typename unowned_container_type::const_iterator;
#ifdef RPCS3_IOS
		struct address_entry
		{
			u32 address;
			u32 order;
			section_storage_type* section;
		};
		static constexpr u32 address_index_threshold = 16;
#endif

	public:
		u32 index = 0;
		address_range32 range = {};
		block_container_type sections = {};
		unowned_container_type unowned; // pointers to sections from other blocks that overlap this block
		atomic_t<u32> exists_count = 0;
		atomic_t<u32> locked_count = 0;
		atomic_t<u32> unreleased_count = 0;
		ranged_storage_type *m_storage = nullptr;
#ifdef RPCS3_IOS
		// Sections live in stable list-of-array slots. Index only their addresses;
		// dirty/protection/format checks remain at the lookup site.
		std::vector<address_entry> m_address_index;

		static bool address_less(const address_entry& lhs, const address_entry& rhs)
		{
			return lhs.address < rhs.address || (lhs.address == rhs.address && lhs.order < rhs.order);
		}

		void remove_address_entry(section_storage_type& section)
		{
			if (m_address_index.empty()) return;
			// The old range is retired before reset publishes a new address.
			const address_entry entry{section.get_section_base(), sections.index_of(section), &section};
			const auto it = std::lower_bound(m_address_index.begin(), m_address_index.end(), entry, address_less);
			if (it != m_address_index.end() && it->section == &section) m_address_index.erase(it);
		}

		void add_address_entry(section_storage_type& section)
		{
			if (sections.size() <= address_index_threshold) return;
			const address_entry entry{section.get_section_base(), sections.index_of(section), &section};
			const auto pos = std::lower_bound(m_address_index.begin(), m_address_index.end(), entry, address_less);
			m_address_index.insert(pos, entry);
		}
#endif

		inline void add_owned_section_overlaps(section_storage_type &section)
		{
			u32 end = section.get_section_range().end;
			for (auto *block = next_block(); block != nullptr && end >= block->get_start(); block = block->next_block())
			{
				block->add_unowned_section(section);
			}
		}

		inline void remove_owned_section_overlaps(section_storage_type &section)
		{
			u32 end = section.get_section_range().end;
			for (auto *block = next_block(); block != nullptr && end >= block->get_start(); block = block->next_block())
			{
				block->remove_unowned_section(section);
			}
		}

	public:
		// Construction
		ranged_storage_block() = default;

		void initialize(u32 _index, ranged_storage_type *storage)
		{
			ensure(m_storage == nullptr && storage != nullptr);
			AUDIT(index < num_blocks);

			m_storage = storage;
			index = _index;
			range = address_range32::start_length(index * block_size, block_size);

			AUDIT(range.is_page_range() && get_start() / block_size == index);
		}

		/**
		 * Wrappers
		 */
		constexpr iterator begin() noexcept { return sections.begin(); }
		constexpr const_iterator begin() const noexcept { return sections.begin(); }
		inline iterator end() noexcept { return sections.end(); }
		inline const_iterator end() const noexcept { return sections.end(); }
		inline bool empty() const { return sections.empty(); }
		inline size_type size() const { return sections.size(); }
		inline u32 get_exists_count() const { return exists_count; }
		inline u32 get_locked_count() const { return locked_count; }
		inline u32 get_unreleased_count() const { return unreleased_count; }

		/**
		 * Utilities
		 */
		ranged_storage_type& get_storage() const
		{
			AUDIT(m_storage != nullptr);
			return *m_storage;
		}

		texture_cache_type& get_texture_cache() const
		{
			return get_storage().get_texture_cache();
		}

		inline section_storage_type& create_section()
		{
			auto &res = sections.emplace_back(this);
#ifdef RPCS3_IOS
			if (sections.size() == address_index_threshold + 1)
			{
				// Build once on crossing the small-block threshold, before callers
				// can search the larger block (even if this new slot stays empty).
				m_address_index.reserve(sections.size());
				u32 order = 0;
				for (auto& section : sections)
				{
					if (section.valid_range())
						m_address_index.push_back({section.get_section_base(), order, &section});
					++order;
				}
				std::sort(m_address_index.begin(), m_address_index.end(), address_less);
			}
#endif
			return res;
		}

#ifdef RPCS3_IOS
		std::span<const address_entry> find_address(u32 address) const
		{
			const auto first = std::lower_bound(m_address_index.begin(), m_address_index.end(), address,
				[](const address_entry& entry, u32 value) { return entry.address < value; });
			if (first == m_address_index.end() || first->address != address)
			{
				return {first, first};
			}
			// Most addresses name one section. Avoid a second binary search for
			// that case; duplicate addresses retain their exact ordered range.
			const auto next = first + 1;
			if (next == m_address_index.end() || next->address != address)
			{
				return {first, next};
			}
			const auto last = std::upper_bound(next + 1, m_address_index.end(), address,
				[](u32 value, const address_entry& entry) { return value < entry.address; });
			return {first, last};
		}
#endif

		inline void clear()
		{
#ifdef RPCS3_IOS
			// Bulk clear owns the cache lock. Drop this index before callbacks so
			// destroying N sections does not perform N vector compactions.
			m_address_index.clear();
#endif
			for (auto &section : *this)
			{
				if (section.is_locked())
					section.unprotect();

				section.destroy();
#ifdef RPCS3_IOS
				// Resource-less sections may still belong to adjacent blocks.
				section.invalidate_range();
#endif
			}

			AUDIT(exists_count == 0);
			AUDIT(unreleased_count == 0);
			AUDIT(locked_count == 0);
			sections.clear();
		}

		inline bool is_first_block() const
		{
			return index == 0;
		}

		inline bool is_last_block() const
		{
			return index == num_blocks - 1;
		}

		inline ranged_storage_block* prev_block() const
		{
			if (is_first_block()) return nullptr;
			return &get_storage()[index - 1];
		}

		inline ranged_storage_block* next_block() const
		{
			if (is_last_block()) return nullptr;
			return &get_storage()[index + 1];
		}

		// Address range
		inline const address_range32& get_range() const { return range; }
		inline u32 get_start() const { return range.start; }
		inline u32 get_end() const { return range.end; }
		inline u32 get_index() const { return index; }
		inline bool overlaps(const section_storage_type& section, section_bounds bounds = full_range) const { return section.overlaps(range, bounds); }
		inline bool overlaps(const address_range32& _range) const { return range.overlaps(_range); }

		/**
		 * Section callbacks
		 */
		inline void on_section_protected(const section_storage_type &section)
		{
			(void)section; // silence unused warning without _AUDIT
			AUDIT(section.is_locked());
			locked_count++;
		}

		inline void on_section_unprotected(const section_storage_type &section)
		{
			(void)section; // silence unused warning without _AUDIT
			AUDIT(!section.is_locked());
			u32 prev_locked = locked_count--;
			ensure(prev_locked > 0);
		}

		inline void on_section_range_valid(section_storage_type &section)
		{
			AUDIT(section.valid_range());
			AUDIT(range.overlaps(section.get_section_base()));
			add_owned_section_overlaps(section);
#ifdef RPCS3_IOS
			add_address_entry(section);
#endif
		}

		inline void on_section_range_invalid(section_storage_type &section)
		{
			AUDIT(section.valid_range());
			AUDIT(range.overlaps(section.get_section_base()));
			remove_owned_section_overlaps(section);
#ifdef RPCS3_IOS
			remove_address_entry(section);
#endif
		}

		inline void on_section_resources_created(const section_storage_type &section)
		{
			(void)section; // silence unused warning without _AUDIT
			AUDIT(section.exists());

			u32 prev_exists = exists_count++;

			if (prev_exists == 0)
			{
				m_storage->on_ranged_block_first_section_created(*this);
			}
		}

		inline void on_section_resources_destroyed(const section_storage_type &section)
		{
			(void)section; // silence unused warning without _AUDIT
			AUDIT(!section.exists());

			u32 prev_exists = exists_count--;
			ensure(prev_exists > 0);

			if (prev_exists == 1)
			{
				m_storage->on_ranged_block_last_section_destroyed(*this);
			}
		}

		void on_section_released(const section_storage_type &/*section*/)
		{
			u32 prev_unreleased = unreleased_count--;
			ensure(prev_unreleased > 0);
		}

		void on_section_unreleased(const section_storage_type &/*section*/)
		{
			unreleased_count++;
		}


		/**
		 * Overlapping sections
		 */
		inline bool contains_unowned(section_storage_type &section) const
		{
			return (unowned.find(&section) != unowned.end());
		}

		inline void add_unowned_section(section_storage_type &section)
		{
			AUDIT(overlaps(section));
			AUDIT(section.get_section_base() < range.start);
			AUDIT(!contains_unowned(section));
			unowned.insert(&section);
		}

		inline void remove_unowned_section(section_storage_type &section)
		{
			AUDIT(overlaps(section));
			AUDIT(section.get_section_base() < range.start);
			AUDIT(contains_unowned(section));
			unowned.erase(&section);
		}

		inline unowned_iterator unowned_begin() { return unowned.begin(); }
		inline unowned_const_iterator unowned_begin() const { return unowned.begin(); }
		inline unowned_iterator unowned_end() { return unowned.end(); }
		inline unowned_const_iterator unowned_end() const { return unowned.end(); }
		inline bool unowned_empty() const { return unowned.empty(); }
	};
template <typename traits>
class ranged_storage
	{
	public:
		static constexpr u32 block_size = 0x100000;
		static_assert(block_size % 4096u == 0, "block_size must be a multiple of the page size");
		static constexpr u32 num_blocks = u32{0x100000000ull / block_size};
		static_assert((num_blocks > 0) && (u64{num_blocks} *block_size == 0x100000000ull), "Invalid block_size/num_blocks");

		using section_storage_type = typename traits::section_storage_type;
		using texture_cache_type   = typename traits::texture_cache_base_type;
		using block_type           = ranged_storage_block<ranged_storage>;

	public:
		block_type blocks[num_blocks];
		texture_cache_type *m_tex_cache;
		std::unordered_set<block_type*> m_in_use;

	public:
		atomic_t<u32> m_unreleased_texture_objects = { 0 }; //Number of invalidated objects not yet freed from memory
		atomic_t<u64> m_texture_memory_in_use = { 0 };

		// Constructor
		ranged_storage(texture_cache_type *tex_cache) :
			m_tex_cache(tex_cache)
		{
			// Initialize blocks
			for (u32 i = 0; i < num_blocks; i++)
			{
				blocks[i].initialize(i, this);
			}
		}

		/**
		 * Iterators
		 */

		constexpr auto begin() { return std::begin(blocks); }
		constexpr auto begin() const { return std::begin(blocks); }
		constexpr auto end() { return std::end(blocks); }
		constexpr auto end() const { return std::end(blocks); }

		/**
		 * Utilities
		 */
		inline block_type& block_for(u32 address)
		{
			return blocks[address / block_size];
		}

		inline const block_type& block_for(u32 address) const
		{
			return blocks[address / block_size];
		}

		inline block_type& block_for(const address_range32 &range)
		{
			AUDIT(range.valid());
			return block_for(range.start);
		}

		inline block_type& block_for(const section_storage_type &section)
		{
			return block_for(section.get_section_base());
		}

		inline block_type& operator[](usz pos)
		{
			AUDIT(pos < num_blocks);
			return blocks[pos];
		}

		inline texture_cache_type& get_texture_cache() const
		{
			AUDIT(m_tex_cache != nullptr);
			return *m_tex_cache;
		}


		/**
		 * Blocks
		 */

		void clear()
		{
			for (auto &block : *this)
			{
				block.clear();
			}

			m_in_use.clear();

			AUDIT(m_unreleased_texture_objects == 0);
			AUDIT(m_texture_memory_in_use == 0);
		}

		void purge_unreleased_sections()
		{
			std::vector<section_storage_type*> textures_to_remove;

			// Reclaims all graphics memory consumed by dirty textures
			// Do not destroy anything while iterating or you will end up with stale iterators
			for (auto& block : m_in_use)
			{
				if (block->get_unreleased_count() > 0)
				{
					for (auto& tex : *block)
					{
						if (!tex.is_unreleased())
							continue;

						ensure(!tex.is_locked());
						textures_to_remove.push_back(&tex);
					}
				}
			}

			for (auto& tex : textures_to_remove)
			{
				tex->destroy();
			}

			AUDIT(m_unreleased_texture_objects == 0);
		}

		bool purge_unlocked_sections()
		{
			// Reclaims all graphics memory consumed by unlocked textures
			// Do not destroy anything while iterating or you will end up with stale iterators
			std::vector<section_storage_type*> textures_to_remove;

			for (auto& block : m_in_use)
			{
				if (block->get_exists_count() > block->get_locked_count())
				{
					for (auto& tex : *block)
					{
						if (tex.get_context() == rsx::texture_upload_context::framebuffer_storage ||
							tex.is_locked() ||
							!tex.exists())
						{
							continue;
						}

						ensure(!tex.is_locked() && tex.exists());
						textures_to_remove.push_back(&tex);
					}
				}
			}

			for (auto& tex : textures_to_remove)
			{
				tex->destroy();
			}

			return !textures_to_remove.empty();
		}

		void trim_sections()
		{
#ifdef RPCS3_IOS
			// One timer pair per maintenance pass, never per texture. On-demand
			// validation remains unchanged; these observations distinguish it
			// from the full maintenance walk before changing its memory policy.
			const auto trim_begin = utils::get_tsc();
			u64 observed_sections = 0, observed_bytes = 0;
#endif
			for (auto it = m_in_use.begin(); it != m_in_use.end(); it++)
			{
				auto* block = *it;
				if (block->get_locked_count() > 256)
				{
					for (auto& tex : *block)
					{
						if (tex.is_locked() && !tex.is_locked(true))
						{
#ifdef RPCS3_IOS
							++observed_sections;
							observed_bytes += tex.get_confirmed_range().length();
							// CELL573_TEXTURE_RESIDENCY: a maintenance validation is not a use.
							tex.sync_protection_untouched();
#else
							tex.sync_protection();
#endif
						}
					}
				}
			}
#ifdef RPCS3_IOS
			rpcs3::ios::texture_validation::trim_calls.fetch_add(1, std::memory_order_relaxed);
			rpcs3::ios::texture_validation::trim_sections.fetch_add(observed_sections, std::memory_order_relaxed);
			rpcs3::ios::texture_validation::trim_bytes.fetch_add(observed_bytes, std::memory_order_relaxed);
			rpcs3::ios::texture_validation::trim_ticks.fetch_add(utils::get_tsc() - trim_begin, std::memory_order_relaxed);
#endif
		}


		/**
		 * Callbacks
		 */
		void on_section_released(const section_storage_type &/*section*/)
		{
			u32 prev_unreleased = m_unreleased_texture_objects--;
			ensure(prev_unreleased > 0);
		}

		void on_section_unreleased(const section_storage_type &/*section*/)
		{
			m_unreleased_texture_objects++;
		}

		void on_section_resources_created(const section_storage_type &section)
		{
			m_texture_memory_in_use += section.get_section_size();
		}

		void on_section_resources_destroyed(const section_storage_type &section)
		{
			u64 size = section.get_section_size();
			u64 prev_size = m_texture_memory_in_use.fetch_sub(size);
			ensure(prev_size >= size);
		}

		void on_ranged_block_first_section_created(block_type& block)
		{
			AUDIT(m_in_use.find(&block) == m_in_use.end());
			m_in_use.insert(&block);
		}

		void on_ranged_block_last_section_destroyed(block_type& block)
		{
			AUDIT(m_in_use.find(&block) != m_in_use.end());
			m_in_use.erase(&block);
		}

		/**
		 * Ranged Iterator
		 */
		 // Iterator
		template <typename T, typename unowned_iterator, typename section_iterator, typename block_type, typename parent_type>
		class range_iterator_tmpl
		{
		public:
			// Traits
			using value_type = T;
			using pointer = T * ;
			using difference_type = int;
			using reference = T & ;
			using iterator_category = std::forward_iterator_tag;

			// Constructors
			range_iterator_tmpl() = default; // end iterator

			explicit range_iterator_tmpl(parent_type &storage, const address_range32 &_range, section_bounds _bounds, bool _locked_only)
				: range(_range)
				, bounds(_bounds)
				, block(&storage.block_for(range.start))
				, unowned_remaining(true)
				, unowned_it(block->unowned_begin())
				, cur_block_it(block->begin())
				, locked_only(_locked_only)
			{
				// do a "fake" iteration to ensure the internal state is consistent
				next(false);
			}

		public:
			// Members
			address_range32 range;
			section_bounds bounds {};

			block_type* block = nullptr;
			bool needs_overlap_check = true;
			bool unowned_remaining = false;
			unowned_iterator unowned_it = {};
			section_iterator cur_block_it = {};
			pointer obj = nullptr;
			bool locked_only = false;

			inline void next(bool iterate = true)
			{
				AUDIT(block != nullptr);

				if (unowned_remaining)
				{
					do
					{
						// Still have "unowned" sections from blocks before the range to loop through
						auto blk_end = block->unowned_end();
						if (iterate && unowned_it != blk_end)
						{
							++unowned_it;
						}

						if (unowned_it != blk_end)
						{
							obj = *unowned_it;
							if (obj->valid_range() && (!locked_only || obj->is_locked()) && obj->overlaps(range, bounds))
								return;

							iterate = true;
							continue;
						}

						// No more unowned sections remaining
						unowned_remaining = false;
						iterate = false;
						break;

					} while (true);
				}

				// Go to next block
				do
				{
					// Iterate current block
					do
					{
						auto blk_end = block->end();
						if (iterate && cur_block_it != blk_end)
						{
							++cur_block_it;
						}

						if (cur_block_it != blk_end)
						{
							obj = &(*cur_block_it);
							if (obj->valid_range() && (!locked_only || obj->is_locked()) && (!needs_overlap_check || obj->overlaps(range, bounds)))
								return;

							iterate = true;
							continue;
						}
						break;

					} while (true);

					// Move to next block(s)
					do
					{
						block = block->next_block();
						if (block == nullptr || block->get_start() > range.end) // Reached end
						{
							block = nullptr;
							obj = nullptr;
							return;
						}

						needs_overlap_check = (block->get_end() > range.end);
						cur_block_it = block->begin();
						iterate = false;
					} while (locked_only && block->get_locked_count() == 0); // find a block with locked sections

				} while (true);
			}

		public:
			inline reference operator*() const { return *obj; }
			inline pointer operator->() const { return obj; }
			inline reference operator++() { next(); return *obj; }
			inline reference operator++(int) { auto *ptr = obj; next(); return *ptr; }
			inline bool operator==(const range_iterator_tmpl &rhs) const { return obj == rhs.obj && unowned_remaining == rhs.unowned_remaining; }

			inline void set_end(u32 new_end)
			{
				range.end = new_end;

				// If we've exceeded the new end, invalidate iterator
				if (block->get_start() > range.end)
				{
					block = nullptr;
				}
			}

			inline block_type& get_block() const
			{
				AUDIT(block != nullptr);
				return *block;
			}

			inline section_bounds get_bounds() const
			{
				return bounds;
			}
		};

		using range_iterator = range_iterator_tmpl<section_storage_type, typename block_type::unowned_iterator, typename block_type::iterator, block_type, ranged_storage>;
		using range_const_iterator = range_iterator_tmpl<const section_storage_type, typename block_type::unowned_const_iterator, typename block_type::const_iterator, const block_type, const ranged_storage>;

		inline range_iterator range_begin(const address_range32 &range, section_bounds bounds, bool locked_only = false) {
			return range_iterator(*this, range, bounds, locked_only);
		}

		inline range_const_iterator range_begin(const address_range32 &range, section_bounds bounds, bool locked_only = false) const {
			return range_const_iterator(*this, range, bounds, locked_only);
		}

		inline range_const_iterator range_begin(u32 address, section_bounds bounds, bool locked_only = false) const {
			return range_const_iterator(*this, address_range32::start_length(address, 1), bounds, locked_only);
		}

		constexpr range_iterator range_end()
		{
			return range_iterator();
		}

		constexpr range_const_iterator range_end() const
		{
			return range_const_iterator();
		}

		/**
		 * Debug
		 */
#ifdef TEXTURE_CACHE_DEBUG
		void verify_protection(bool recount = false)
		{
			if (recount)
			{
				// Reset calculated part of the page_info struct
				tex_cache_checker.reset_refcount();

				// Go through all blocks and update calculated values
				for (auto &block : *this)
				{
					for (auto &tex : block)
					{
						if (tex.is_locked())
						{
							tex_cache_checker.add(tex.get_locked_range(), tex.get_protection());
						}
					}
				}
			}

			// Verify
			tex_cache_checker.verify();
		}
#endif //TEXTURE_CACHE_DEBUG

	};

struct Cache;struct Section;struct Traits{using section_storage_type=Section;using texture_cache_base_type=Cache;};
struct Predictor{};
struct Section:rsx::buffered_section {
 using ranged_storage_type=ranged_storage<Traits>;
 using ranged_storage_block_type=ranged_storage_block<ranged_storage_type>;
 ranged_storage_block_type* m_block=nullptr;ranged_storage_type* m_storage=nullptr;Cache* m_tex_cache=nullptr;Predictor* m_predictor=nullptr;
 bool dirty=true,resources=false,triggered_exists_callbacks=false,triggered_unreleased_callbacks=false;
 u16 width=0,height=0,depth=0,mipmaps=0;u32 real_pitch=0,rsx_pitch=0,gcm_format=0;
 bool pack_unpack_swap_bytes=false,swizzled=false,synchronized=false,flushed=false,speculatively_flushed=false,deferred_commit=false;
 u64 sync_timestamp=0,cache_tag=0,last_write_tag=0,last_use_frame=0;void* m_predictor_entry=nullptr;
 memory_read_flags readback_behaviour=memory_read_flags::flush_once;component_order view_flags=component_order::default_;
 texture_upload_context context=texture_upload_context::shader_read;texture_dimension_extended image_type=texture_dimension_extended::texture_dimension_2d;
 std::vector<address_range32> flush_exclusions;
 Section()=default;explicit Section(ranged_storage_block_type* b){initialize(b);}
 Section* derived(){return this;}
 void initialize(ranged_storage_block_type*);void reset(const address_range32&);void notify_range_valid();void invalidate_range();
 void on_section_resources_created();void on_section_resources_destroyed();void set_dirty(bool);void update_unreleased();bool is_unreleased()const;
 bool sync_protection();bool matches(u32,u32,u32,u32,u32)const;bool matches(u32,u32,u32,u32,u32,u32)const;
 bool is_dirty()const{if(rsx::count_visits)++rsx::visits;return dirty;}
 bool exists()const{return resources||(context==texture_upload_context::dma&&locked);}
 bool is_managed()const{return true;}
 texture_upload_context get_context()const{return context;}
 void destroy(){if(resources){resources=false;on_section_resources_destroyed();}}
 void unprotect();
 void discard(bool make_dirty);
 bool sync_protection_untouched(){return sync_protection();}
};
struct Cache {
 using Storage=ranged_storage<Traits>;using ranged_storage_block=typename Storage::block_type;using section_storage_type=Section;
 Storage m_storage{this};Predictor predictor;
 Predictor& get_predictor(){return predictor;}
 void on_memory_read_flags_changed(Section&,memory_read_flags){}
 ~Cache(){m_storage.clear();}
 template <bool check_unlocked=false>
section_storage_type *find_texture_from_dimensions(u32 rsx_address, u32 format, u16 width = 0, u16 height = 0, u16 depth = 0, u16 mipmaps = 0)
		{
			auto &block = m_storage.block_for(rsx_address);
#ifdef RPCS3_IOS
			// The compressed lookup holds the cache reader lock. Presentation
			// uses check_unlocked=true without that lock and keeps its old walk.
			if constexpr (!check_unlocked)
			{
				if (block.size() > ranged_storage_block::address_index_threshold)
				{
					// Same-address candidates retain their original slot order. The
					// index never certifies contents, dimensions or protection.
					for (const auto& entry : block.find_address(rsx_address))
					{
						auto& tex = *entry.section;
						if constexpr (check_unlocked)
						{
							if (!tex.is_locked()) continue;
						}
						if (!tex.is_dirty() && tex.matches(rsx_address, format, width, height, depth, mipmaps) && tex.sync_protection())
							return &tex;
					}
					return nullptr;
				}
			}
#endif
			for (auto &tex : block)
			{
				if constexpr (check_unlocked)
				{
					if (!tex.is_locked())
					{
						continue;
					}
				}

				if (!tex.is_dirty() &&
					tex.matches(rsx_address, format, width, height, depth, mipmaps) &&
					tex.sync_protection())
				{
					return &tex;
				}
			}

			return nullptr;
		}
};
void Section::unprotect(){if(locked){locked=false;m_block->on_section_unprotected(*this);set_dirty(true);}}
void Section::discard(bool make_dirty){if(locked){rsx::buffered_section::discard();m_block->on_section_unprotected(*this);}if(make_dirty)set_dirty(true);}
void Section::initialize(ranged_storage_block_type* block)
		{
			ensure(m_block == nullptr && m_tex_cache == nullptr && m_storage == nullptr);
			m_block = block;
			m_storage = &block->get_storage();
			m_tex_cache = &block->get_texture_cache();
			m_predictor = &m_tex_cache->get_predictor();

			update_unreleased();
		}
void Section::reset(const address_range32& memory_range)
		{
			AUDIT(memory_range.valid());
			AUDIT(!is_locked());

			// Destroy if necessary
			destroy();
#ifdef RPCS3_IOS
			// destroy() can leave a resource-less range valid. Retire its index
			// and adjacent-block memberships before replacing that range.
			invalidate_range();
#endif

			// Superclass
			rsx::buffered_section::reset(memory_range);

			// Reset member variables to the default
			width = 0;
			height = 0;
			depth = 0;
			mipmaps = 0;

			real_pitch = 0;
			rsx_pitch = 0;

			gcm_format = 0;
			pack_unpack_swap_bytes = false;
			swizzled = false;

			sync_timestamp = 0ull;
			synchronized = false;
			flushed = false;
			speculatively_flushed = false;
#ifdef RPCS3_IOS
			deferred_commit = false;
#endif

			cache_tag = 0ull;
			last_write_tag = 0ull;
#ifdef RPCS3_IOS
			last_use_frame = rpcs3::ios::texture_residency::current_frame();
#endif

			m_predictor_entry = nullptr;

			readback_behaviour = rsx::memory_read_flags::flush_once;
			view_flags = rsx::component_order::default_;
			context = rsx::texture_upload_context::shader_read;
			image_type = rsx::texture_dimension_extended::texture_dimension_2d;

			flush_exclusions.clear();

			// Set to dirty
			set_dirty(true);

			// Notify that our CPU range is now valid
			notify_range_valid();
		}
void Section::notify_range_valid()
		{
			AUDIT(valid_range());

			// Callbacks
			m_block->on_section_range_valid(*derived());
			//m_storage->on_section_range_valid(*derived());

			// Reset texture_cache m_flush_always_cache
			if (readback_behaviour == memory_read_flags::flush_always)
			{
				m_tex_cache->on_memory_read_flags_changed(*derived(), memory_read_flags::flush_always);
			}
		}
void Section::invalidate_range()
		{
			if (!valid_range())
				return;

			// Reset texture_cache m_flush_always_cache
			if (readback_behaviour == memory_read_flags::flush_always)
			{
				m_tex_cache->on_memory_read_flags_changed(*derived(), memory_read_flags::flush_once);
			}

			// Notify the storage block that we are now invalid
			m_block->on_section_range_invalid(*derived());
			//m_storage->on_section_range_invalid(*derived());

			m_predictor_entry = nullptr;
			speculatively_flushed = false;
			buffered_section::invalidate_range();
		}
void Section::on_section_resources_created()
		{
			AUDIT(exists());
			AUDIT(valid_range());

			if (triggered_exists_callbacks) return;
			triggered_exists_callbacks = true;

			// Callbacks
			m_block->on_section_resources_created(*derived());
			m_storage->on_section_resources_created(*derived());
		}
void Section::on_section_resources_destroyed()
		{
			if (!triggered_exists_callbacks) return;
			triggered_exists_callbacks = false;

			AUDIT(valid_range());
			ensure(!is_locked());
			ensure(is_managed());

			// Set dirty
			set_dirty(true);

			// Trigger callbacks
			m_block->on_section_resources_destroyed(*derived());
			m_storage->on_section_resources_destroyed(*derived());

			// Invalidate range
			invalidate_range();
		}
void Section::set_dirty(bool new_dirty)
		{
			if (new_dirty == false && !is_locked() && context == texture_upload_context::shader_read)
				return;

			dirty = new_dirty;

			AUDIT(dirty || exists());

			update_unreleased();
		}
void Section::update_unreleased()
		{
			bool unreleased = is_unreleased();

			if (unreleased && !triggered_unreleased_callbacks)
			{
				triggered_unreleased_callbacks = true;
				m_block->on_section_unreleased(*derived());
				m_storage->on_section_unreleased(*derived());
			}
			else if (!unreleased && triggered_unreleased_callbacks)
			{
				triggered_unreleased_callbacks = false;
				m_block->on_section_released(*derived());
				m_storage->on_section_released(*derived());
			}
		}
bool Section::is_unreleased() const
		{
			return exists() && is_dirty() && !is_locked();
		}
bool Section::sync_protection()
		{
#ifdef RPCS3_IOS
			// CELL559_DIRTY_HASH_SKIP: a dirty section is never sampled before it
			// is recreated, so validating it can only decide its release. Under the
			// hash strategy release it as a mismatch would, without hashing memory
			// that cannot make it valid again. Page-locked sections are unchanged.
			if (is_dirty() && is_locked() && !is_locked(true))
			{
				rpcs3::ios::texture_validation::dirty_releases.fetch_add(1, std::memory_order_relaxed);
				rpcs3::ios::texture_validation::dirty_release_bytes.fetch_add(get_confirmed_range().length(), std::memory_order_relaxed);
				discard(true);
				return false;
			}
#endif
			if (!buffered_section::sync())
			{
				discard(true);
				ensure(is_dirty());
				return false;
			}

#ifdef RPCS3_IOS
			last_use_frame = rpcs3::ios::texture_residency::current_frame();
#endif
			return true;
		}
bool Section::matches(u32 format, u32 width, u32 height, u32 depth, u32 mipmaps) const
		{
			if (!valid_range())
				return false;

			if (format && gcm_format != format)
				return false;

			if (!width && !height && !depth && !mipmaps)
				return true;

			if (width && width != this->width)
				return false;

			if (height && height != this->height)
				return false;

			if (depth && depth != this->depth)
				return false;

			if (mipmaps && mipmaps > this->mipmaps)
				return false;

			return true;
		}
bool Section::matches(u32 rsx_address, u32 format, u32 width, u32 height, u32 depth, u32 mipmaps) const
		{
			if (!valid_range())
				return false;

			if (rsx_address != get_section_base())
				return false;

			return matches(format, width, height, depth, mipmaps);
		}
}

struct Query {u32 address,format=0;u16 width=0,height=0,depth=0,mips=0;bool locked=false;};
template<class Cache>int query(Cache& c,const Query& q){
 auto* r=q.locked?c.template find_texture_from_dimensions<true>(q.address,q.format,q.width,q.height,q.depth,q.mips):c.template find_texture_from_dimensions<false>(q.address,q.format,q.width,q.height,q.depth,q.mips);
 return r?static_cast<int>(r->id):-1;
}
template<class Section>void reset(Section& s,u32 base,u32 length,bool resources){
 s.unprotect();s.reset(address_range32::start_length(base,length));
 s.width=32;s.height=32;s.depth=1;s.mipmaps=4;s.gcm_format=7;s.memory_valid=true;
 if(resources){s.resources=true;s.on_section_resources_created();}
 // Host equivalent of completed GPU upload/protection, without guest mapping.
 s.context=rsx::texture_upload_context::blit_engine_dst;s.set_dirty(!resources);
}
template<class Cache>auto& add(Cache& c,u32 address,u32 length,u32 id,bool resources=true){
 auto& s=c.m_storage.block_for(address).create_section();s.id=id;reset(s,address,length,resources);return s;
}
struct Counters{u64 queries=0,old_visits=0,new_visits=0,mutations=0;};
void compare(before::Cache& a,after::Cache& b,const Query& q,Counters& counts){
 rsx::validations.clear();rsx::visits=0;const int old=query(a,q);const auto old_validation=rsx::validations;const auto old_visits=rsx::visits;counts.old_visits+=old_visits;
 rsx::validations.clear();rsx::visits=0;const int now=query(b,q);counts.new_visits+=rsx::visits;
 assert(old==now&&old_validation==rsx::validations);if(q.locked)assert(old_visits==rsx::visits);++counts.queries;
}
void compare_overlaps(before::Cache& a,after::Cache& b,address_range32 range){
 auto collect=[&](auto& c){std::vector<u32> ids;for(auto it=c.m_storage.range_begin(range,rsx::full_range,false);it!=c.m_storage.range_end();it++)ids.push_back(it->id);std::sort(ids.begin(),ids.end());return ids;};
 assert(collect(a)==collect(b));
}
Counters correctness(){
 auto a=std::make_unique<before::Cache>();auto b=std::make_unique<after::Cache>();Counters c;
 std::vector<before::Section*> old;std::vector<after::Section*> now;
 // Four chunks exercise construction order, duplicate addresses, resource-less
 // slots, mismatched dimensions and dirty/hash-failed earlier versions.
 for(u32 i=0;i<256;++i){const u32 addr=0x100000+(i%128)*4096;old.push_back(&add(*a,addr,128,i,i%7));now.push_back(&add(*b,addr,128,i,i%7));
  if(i==15||i==16)for(u32 j=0;j<=i;++j)compare(*a,*b,{old[j]->get_section_base()},c);
 }
 for(u32 i=0;i<256;++i){old[i]->gcm_format=now[i]->gcm_format=7+i/128;old[i]->width=now[i]->width=32+(i%3);}
 for(u32 i=0;i<128;++i)for(u32 fmt:{0u,7u,8u,9u})for(u16 mip:{u16{0},u16{3},u16{5}})compare(*a,*b,{0x100000+i*4096,fmt,0,0,0,mip},c);
 // Recycling the older duplicate later must not move it behind the newer one.
 reset(*old[16],0x110000,128,true);reset(*now[16],0x110000,128,true);
 old[144]->gcm_format=now[144]->gcm_format=7;
 compare(*a,*b,{0x110000},c);assert(query(*b,{0x110000})==16);
 old[16]->memory_valid=now[16]->memory_valid=false;
 compare(*a,*b,{0x110000},c);assert(query(*b,{0x110000})==144);
 for(u32 i=0;i<64;++i){old[i]->memory_valid=now[i]->memory_valid=false;compare(*a,*b,{old[i]->get_section_base()},c);}
 std::mt19937 rng(20261029);
 for(u32 i=0;i<20000;++i){u32 id=rng()%256;auto& x=*old[id];auto& y=*now[id];
  switch(rng()%7){
   case 0:x.set_dirty(true);y.set_dirty(true);break;
   case 1:x.memory_valid=y.memory_valid=(rng()%2);break;
   case 2:{u32 addr=0x100000+(rng()%192)*4096;reset(x,addr,128,false);reset(y,addr,128,false);++c.mutations;break;}
   case 3:{u32 addr=0x100000+(rng()%192)*4096;reset(x,addr,128,true);reset(y,addr,128,true);++c.mutations;break;}
   case 4:x.unprotect();y.unprotect();x.destroy();y.destroy();x.invalidate_range();y.invalidate_range();x.invalidate_range();y.invalidate_range();++c.mutations;break;
   case 5:x.width=y.width=16+(rng()%3)*16;x.mipmaps=y.mipmaps=rng()%8;break;
   case 6:if(x.valid_range()){x.context=y.context=rsx::texture_upload_context::dma;if(x.exists()){x.set_dirty(false);y.set_dirty(false);}}break;
  }
  Query q{static_cast<u32>(0x100000+(rng()%192)*4096)};if(i%3==0)q.format=7;if(i%5==0)q.width=32;if(i%7==0)q.mips=3;
  compare(*a,*b,q,c);if(i%31==0)compare(*a,*b,{q.address,0,0,0,0,0,true},c);
 }
 // Crossing a block boundary affects overlap iteration but never changes the
 // owning block of an exact-base lookup. Repeated retags remain ordered.
 for(u32 i=0;i<20;++i){u32 addr=0x200000+i*512;add(*a,addr,128,500+i);add(*b,addr,128,500+i);}
 for(u32 i=0;i<3;++i){u32 addr=0x2ff000;add(*a,addr,0x4000,300+i);add(*b,addr,0x4000,300+i);}
 compare(*a,*b,{0x2ff000},c);compare(*a,*b,{0x300000},c);compare_overlaps(*a,*b,address_range32::start_length(0x300000,0x2000));
 // Indexed edge blocks, including address zero and the last byte of 4GiB.
 for(u32 base:{0u,0xfff00000u}){
  for(u32 i=0;i<20;++i){u32 addr=base+i*512;add(*a,addr,128,600+i);add(*b,addr,128,600+i);}
  compare(*a,*b,{base},c);compare(*a,*b,{base+19*512},c);
 }
 add(*a,0xfffff000,4096,700);add(*b,0xfffff000,4096,700);compare(*a,*b,{0xfffff000},c);
 compare_overlaps(*a,*b,address_range32::start_length(0xfffffff0,16));
 // The 17th slot may remain invalid. Existing entries must already be indexed.
 for(u32 i=0;i<16;++i){add(*a,0x400000+i*512,128,800+i);add(*b,0x400000+i*512,128,800+i);}
 a->m_storage.block_for(0x400000).create_section();b->m_storage.block_for(0x400000).create_section();
 for(u32 i=0;i<16;++i)compare(*a,*b,{0x400000+i*512},c);
 // DMA-only valid range without a GPU image remains eligible when protected.
 auto& dx=add(*a,0x400000+30*512,128,900,false);auto& dy=add(*b,0x400000+30*512,128,900,false);
 dx.context=dy.context=rsx::texture_upload_context::dma;dx.locked=dy.locked=true;
 dx.m_block->on_section_protected(dx);dy.m_block->on_section_protected(dy);dx.set_dirty(false);dy.set_dirty(false);
 compare(*a,*b,{dx.get_section_base(),0,0,0,0,0,true},c);assert(query(*b,{dy.get_section_base()})==900);
 // Clear must also remove the resource-less entries left valid by destroy().
 a->m_storage.clear();b->m_storage.clear();for(u32 i=0;i<128;++i)compare(*a,*b,{0x100000+i*4096},c);
 for(u32 i=0;i<160;++i){u32 addr=0x100000+(159-i)*4096;add(*a,addr,256,i,false);add(*b,addr,256,i,false);}
 for(u32 i=0;i<160;++i)compare(*a,*b,{0x100000+i*4096},c);
 // Create resources later without resetting the previously indexed range.
 auto ai=a->m_storage.block_for(0x100000).begin();auto bi=b->m_storage.block_for(0x100000).begin();
 for(u32 i=0;i<160;++i,ai++,bi++){ai->resources=bi->resources=true;ai->on_section_resources_created();bi->on_section_resources_created();ai->set_dirty(false);bi->set_dirty(false);}
 for(u32 i=0;i<160;++i)compare(*a,*b,{0x100000+i*4096},c);
 return c;
}
template<class Fn>double median(Fn fn,u32 count){std::array<double,7> t{};u64 sum=0;for(auto& n:t){auto start=std::chrono::steady_clock::now();for(u32 i=0;i<count;++i){asm volatile("":::"memory");sum+=fn(i)+1;}n=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/count;}assert(sum);std::sort(t.begin(),t.end());return t[3];}
template<class Cache>auto measured_index_bytes(Cache& c){usz total=0;for(auto& block:c.m_storage){if constexpr(requires{block.m_address_index;})total+=block.m_address_index.capacity()*sizeof(typename Cache::Storage::block_type::address_entry);}return total;}
void benchmark(){
 rsx::tracing=false;std::cout<<",\"benchmarks\":[";bool first=true;
 for(u32 size:{8,16,17,64,256,1024}){
 auto a=std::make_unique<before::Cache>();auto b=std::make_unique<after::Cache>();std::vector<before::Section*> x;std::vector<after::Section*> y;
 for(u32 i=0;i<size;++i){u32 addr=0x100000+i*512;x.push_back(&add(*a,addr,128,i));y.push_back(&add(*b,addr,128,i));}
 auto run=[&](auto& cache,bool miss){return median([&](u32 i){const int found=query(cache,{0x100000+((i*131)%size)*512+(miss?256u:0u)});return static_cast<u32>(found+1);},30000);};
 // Deterministic work counts are separate from all timed loops.
 rsx::count_visits=true;rsx::visits=0;for(u32 i=0;i<30000;++i)query(*a,{0x100000+((i*131)%size)*512});const u64 old=rsx::visits;
 rsx::visits=0;for(u32 i=0;i<30000;++i)query(*b,{0x100000+((i*131)%size)*512});const u64 now=rsx::visits;
 rsx::count_visits=false;const double hb=run(*a,false),ha=run(*b,false);
 const double mb=run(*a,true),ma=run(*b,true);
 const double first_before=median([&](u32){return static_cast<u32>(query(*a,{0x100000})+1);},30000);
 const double first_after=median([&](u32){return static_cast<u32>(query(*b,{0x100000})+1);},30000);
 allocations=0;count_allocations=true;
 for(u32 i=0;i<30000;++i)query(*b,{0x100000+((i*131)%size)*512});
 count_allocations=false;assert(allocations==0);
 auto change=[&](auto& slots){return median([&](u32 i){auto& s=*slots[(i*131)%size];reset(s,0x100000+((i*131)%size)*512+(i%2)*128,128,true);return s.get_section_base();},10000);};
 const double cb=change(x),ca=change(y);
 if(!first)std::cout<<",";
 first=false;
 std::cout<<"{\"sections\":"<<size<<",\"hitBeforeNs\":"<<hb<<",\"hitAfterNs\":"<<ha<<",\"missBeforeNs\":"<<mb<<",\"missAfterNs\":"<<ma<<",\"firstSlotBeforeNs\":"<<first_before<<",\"firstSlotAfterNs\":"<<first_after<<",\"lookupAllocations\":0,\"recycleBeforeNs\":"<<cb<<",\"recycleAfterNs\":"<<ca<<",\"baselineDirtyPredicateCalls\":"<<old<<",\"indexedDirtyPredicateCalls\":"<<now<<",\"allocatedIndexBytes\":"<<measured_index_bytes(*b)<<"}";
 }std::cout<<"],\"indexHeadersBytes\":"<<(sizeof(after::Cache::Storage)-sizeof(before::Cache::Storage))<<",\"hostAdapterSectionBytes\":"<<sizeof(after::Section);rsx::tracing=rsx::count_visits=true;
}
int main(int argc,char**){const auto c=correctness();std::cout<<"{\"queries\":"<<c.queries<<",\"mutations\":"<<c.mutations<<",\"baselineDirtyPredicateCalls\":"<<c.old_visits<<",\"indexedDirtyPredicateCalls\":"<<c.new_visits<<",\"sameFirstMatch\":true,\"sameValidationOrder\":true,\"sameOverlapMembership\":true,\"clearAndResourceLessRetags\":true,\"sectionLayoutUnchanged\":true,\"presentationWalkUnchanged\":true";if(argc>1)benchmark();std::cout<<"}\n";}
