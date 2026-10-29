#include <algorithm>
#include <array>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdint>
#include <cstring>
#include <concepts>
#include <iterator>
#include <utility>
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
template<class T>concept UnsignedInt=std::is_integral_v<T> && std::is_unsigned_v<T>;
inline bool count_allocations=false;inline u64 array_allocations=0,array_bytes=0;
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
inline std::vector<u32> warnings;
struct Log {void warning(const char*,u32 address){warnings.push_back(address);} } rsx_log;
namespace rsx {
enum section_bounds {full_range,locked_range,confirmed_range};
enum texture_upload_context : u32 {shader_read=1,blit_engine_dst=2,blit_engine_src=4,framebuffer_storage=8,dma=16};
enum class memory_read_flags{flush_once,flush_always};
enum class component_order{default_};
enum class texture_dimension_extended{texture_dimension_2d};
enum class section_protection_strategy{lock,hash};
inline section_protection_strategy default_texture_protection_strategy(u32){return section_protection_strategy::hash;}
inline u64 range_visits=0;inline std::vector<u32> unprotects,merges;
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
 bool valid_range()const{if(count_visits)++range_visits;return cpu_range.valid();}
 u32 get_section_base()const{return cpu_range.start;}
 u32 get_section_size()const{return valid_range()?cpu_range.length():0;}
 const address_range32& get_section_range()const{return cpu_range;}
 const address_range32& get_confirmed_range()const{return confirmed_range.valid()?confirmed_range:cpu_range;}
 bool is_locked(bool page=false)const{return locked&&(!page||protection_strat==section_protection_strategy::lock);}
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

template<class C>u32 size32(const C& c){return static_cast<u32>(c.size());}
namespace rsx {
template<class T>using reverse_pointer=std::reverse_iterator<T*>;
namespace aligned_allocator {
template<size_t Align>void* malloc(size_t bytes){if(count_allocations){++array_allocations;array_bytes+=bytes;}return std::malloc(bytes);}
template<size_t Align>void* realloc(void* ptr,size_t,size_t bytes){if(count_allocations){++array_allocations;array_bytes+=bytes;}return std::realloc(ptr,bytes);}
inline void free(void* p){std::free(p);}
}
template <bool __is_surface=true, typename SurfaceType>
inline bool pitch_compatible(const SurfaceType* surface, u32 pitch_required, u16 height_required)
	{
		if constexpr (__is_surface)
		{
			if (height_required == 1 || surface->get_surface_height() == 1)
				return true;
		}
		else
		{
			if (height_required == 1 || surface->get_height() == 1)
				return true;
		}

		return (surface->get_rsx_pitch() == pitch_required);
	}
}



namespace rsx
{
	template <typename C, typename T>
	concept span_like =
		requires(C& c) {
			{ c.data() } -> std::convertible_to<const T*>;
			{ c.size() } -> std::integral;
	};

	template <typename T, typename U>
	concept is_trivially_comparable_v =
		requires (T t1, U t2) {
			{ t1 == t2 } -> std::same_as<bool>;
	};

	template <typename Ty, size_t Align=alignof(Ty)>
		requires std::is_trivially_destructible_v<Ty> && std::is_trivially_copyable_v<Ty>
	struct simple_array
	{
	public:
		using iterator = Ty*;
		using const_iterator = const Ty*;
		using reverse_iterator = reverse_pointer<Ty>;
		using const_reverse_iterator = reverse_pointer<const Ty>;
		using value_type = Ty;

	private:
		static constexpr u32 _local_capacity = std::max<u32>(64u / sizeof(Ty), 1u);
		alignas(Align) char _local_storage[_local_capacity * sizeof(Ty)];

		u32 _capacity = _local_capacity;
		Ty* _data = _local_capacity ? reinterpret_cast<Ty*>(_local_storage) : nullptr;
		u32 _size = 0;

		inline u32 offset(const_iterator pos)
		{
			return (_data) ? u32(pos - _data) : 0u;
		}

		bool is_local_storage() const
		{
			return _data == reinterpret_cast<const Ty*>(_local_storage);
		}

	public:
		simple_array() = default;

		simple_array(u32 initial_size)
		{
			reserve(initial_size);
			_size = initial_size;
		}

		simple_array(u32 initial_size, const Ty val)
		{
			reserve(initial_size);
			_size = initial_size;

			for (u32 n = 0; n < initial_size; ++n)
			{
				_data[n] = val;
			}
		}

		simple_array(const std::initializer_list<Ty>& args)
		{
			reserve(::size32(args));

			for (const auto& arg : args)
			{
				push_back(arg);
			}
		}

		simple_array(const simple_array& other)
		{
			resize(other._size);

			if (_size)
			{
				std::memcpy(_data, other._data, size_bytes());
			}
		}

		simple_array(simple_array&& other) noexcept
		{
			swap(other);
		}

		template <typename Container>
			requires span_like<Container, Ty>
		simple_array(const Container& container)
		{
			resize(container.size());

			if (_size)
			{
				std::memcpy(_data, container.data(), size_bytes());
			}
		}

		simple_array& operator=(const simple_array& other)
		{
			if (&other != this)
			{
				resize(other._size);

				if (_size)
				{
					std::memcpy(_data, other._data, size_bytes());
				}
			}

			return *this;
		}

		simple_array& operator=(simple_array&& other) noexcept
		{
			swap(other);
			return *this;
		}

		~simple_array()
		{
			if (_data)
			{
				if (!is_local_storage())
				{
					aligned_allocator::free(_data);
				}

				_data = nullptr;
				_size = _capacity = 0;
			}
		}

		void swap(simple_array<Ty>& that) noexcept
		{
			if (!_size && !that._size)
			{
				// NOP. Surprisingly common
				return;
			}

			const auto _this_is_local = is_local_storage();
			const auto _that_is_local = that.is_local_storage();

			if (!_this_is_local && !_that_is_local)
			{
				std::swap(_capacity, that._capacity);
				std::swap(_size, that._size);
				std::swap(_data, that._data);
				return;
			}

			if (!_size)
			{
				*this = that;
				that.clear();
				return;
			}

			if (!that._size)
			{
				that = *this;
				clear();
				return;
			}

			if (_this_is_local != _that_is_local)
			{
				// Mismatched usage of the stack storage.
				rsx::simple_array<Ty> tmp{ *this };
				*this = that;
				that = tmp;
				return;
			}

			// Use memcpy to allow compiler optimizations
			Ty _stack_alloc[_local_capacity];
			std::memcpy(_stack_alloc, that._data, that.size_bytes());
			std::memcpy(that._data, _data, size_bytes());
			std::memcpy(_data, _stack_alloc, that.size_bytes());
			std::swap(_size, that._size);
		}

		void reserve(u32 size)
		{
			if (_capacity >= size)
			{
				return;
			}

			if (is_local_storage())
			{
				// Switch to heap storage
				ensure(_data = static_cast<Ty*>(aligned_allocator::malloc<Align>(sizeof(Ty) * size)));
				std::memcpy(static_cast<void*>(_data), _local_storage, size_bytes());
			}
			else
			{
				// Extend heap storage
				ensure(_data = static_cast<Ty*>(aligned_allocator::realloc<Align>(_data, size_bytes(), sizeof(Ty) * size))); // "realloc() failed!"
			}

			_capacity = size;
		}

		template <typename T> requires UnsignedInt<T>
		void resize(T size)
		{
			const auto new_size = static_cast<u32>(size);
			reserve(new_size);
			_size = new_size;
		}

		void push_back(const Ty& val)
		{
			if (_size >= _capacity)
			{
				reserve(_capacity + 16);
			}

			_data[_size++] = val;
		}

		void push_back(Ty&& val)
		{
			if (_size >= _capacity)
			{
				reserve(_capacity + 16);
			}

			_data[_size++] = val;
		}

		template <typename... Args>
		void emplace_back(Args&&... args)
		{
			if (_size >= _capacity)
			{
				reserve(_capacity + 16);
			}

			std::construct_at(&_data[_size++], std::forward<Args&&>(args)...);
		}

		Ty pop_back()
		{
			return _data[--_size];
		}

		iterator insert(iterator pos, const Ty& val)
		{
			ensure(pos >= _data);
			const auto _loc = offset(pos);

			if (_size >= _capacity)
			{
				reserve(_capacity + 16);
				pos = _data + _loc;
			}

			if (_loc >= _size)
			{
				_data[_size++] = val;
				return pos;
			}

			AUDIT(_loc < _size);

			const auto remaining = (_size - _loc);
			std::memmove(pos + 1, pos, remaining * sizeof(Ty));

			*pos = val;
			_size++;

			return pos;
		}

		iterator insert(iterator pos, Ty&& val)
		{
			ensure(pos >= _data);
			const auto _loc = offset(pos);

			if (_size >= _capacity)
			{
				reserve(_capacity + 16);
				pos = _data + _loc;
			}

			if (_loc >= _size)
			{
				_data[_size++] = val;
				return pos;
			}

			AUDIT(_loc < _size);

			const u32 remaining = (_size - _loc);
			std::memmove(pos + 1, pos, remaining * sizeof(Ty));

			*pos = val;
			_size++;

			return pos;
		}

		iterator insert(iterator where, span_like<Ty> auto const& values)
		{
			ensure(where >= _data);
			const auto _loc = offset(where);
			const auto in_size = static_cast<u32>(values.size());
			const auto in_size_bytes = in_size * sizeof(Ty);

			reserve(_size + in_size);

			if (_loc >= _size)
			{
				where = _data + _size;
				std::memcpy(where, values.data(), in_size_bytes);
				_size += in_size;
				return where;
			}

			const u32 remaining_bytes = (_size - _loc) * sizeof(Ty);
			where = _data + _loc;
			std::memmove(where + in_size, where, remaining_bytes);
			std::memmove(where, values.data(), in_size_bytes);
			_size += in_size;
			return where;
		}

		void operator += (const rsx::simple_array<Ty>& that)
		{
			const auto old_size = _size;
			resize(_size + that._size);
			std::memcpy(data() + old_size, that.data(), that.size_bytes());
		}

		void clear()
		{
			_size = 0;
		}

		bool empty() const
		{
			return _size == 0;
		}

		u32 size() const
		{
			return _size;
		}

		u64 size_bytes() const
		{
			return _size * sizeof(Ty);
		}

		u32 size_bytes32() const
		{
			return _size * sizeof(Ty);
		}

		u32 capacity() const
		{
			return _capacity;
		}

		Ty& operator[] (u32 index)
		{
			return _data[index];
		}

		const Ty& operator[] (u32 index) const
		{
			return _data[index];
		}

		Ty* data()
		{
			return _data;
		}

		const Ty* data() const
		{
			return _data;
		}

		Ty& back()
		{
			return _data[_size - 1];
		}

		const Ty& back() const
		{
			return _data[_size - 1];
		}

		Ty& front()
		{
			return _data[0];
		}

		const Ty& front() const
		{
			return _data[0];
		}

		iterator begin()
		{
			return _data;
		}

		iterator end()
		{
			return _data ? _data + _size : nullptr;
		}

		const_iterator begin() const
		{
			return _data;
		}

		const_iterator end() const
		{
			return _data ? _data + _size : nullptr;
		}

		const_iterator cbegin() const
		{
			return _data;
		}

		const_iterator cend() const
		{
			return _data ? _data + _size : nullptr;
		}

		reverse_iterator rbegin()
		{
			return reverse_iterator(end() - 1);
		}

		reverse_iterator rend()
		{
			return reverse_iterator(begin() - 1);
		}

		const_reverse_iterator rbegin() const
		{
			return crbegin();
		}

		const_reverse_iterator rend() const
		{
			return crend();
		}

		const_reverse_iterator crbegin() const
		{
			return const_reverse_iterator(cend() - 1);
		}

		const_reverse_iterator crend() const
		{
			return const_reverse_iterator(cbegin() - 1);
		}

		bool any(std::predicate<const Ty&> auto predicate) const
		{
			for (auto it = begin(); it != end(); ++it)
			{
				if (std::invoke(predicate, *it))
				{
					return true;
				}
			}
			return false;
		}

		/**
		 * Note that find and find_if return pointers to objects and not iterators for simplified usage.
		 * It is functionally equivalent to retrieve a nullptr meaning empty object stored and nullptr meaning not found for all practical uses of this container.
		 */
		template <typename T = Ty>
			requires is_trivially_comparable_v<Ty, T>
		Ty* find(const T& value)
		{
			for (auto it = begin(); it != end(); ++it)
			{
				if (*it == value)
				{
					return &(*it);
				}
			}
			return nullptr;
		}

		// Remove when we switch to C++23
		template <typename T = Ty>
			requires is_trivially_comparable_v<Ty, T>
		const Ty* find(const T& value) const
		{
			return const_cast<simple_array<Ty, Align>*>(this)->find(value);
		}

		Ty* find_if(std::predicate<const Ty&> auto predicate)
		{
			for (auto it = begin(); it != end(); ++it)
			{
				if (std::invoke(predicate, *it))
				{
					return &(*it);
				}
			}
			return nullptr;
		}

		// Remove with C++23
		const Ty* find_if(std::predicate<const Ty&> auto predicate) const
		{
			return const_cast<simple_array<Ty, Align>*>(this)->find_if(predicate);
		}

		bool erase_if(std::predicate<const Ty&> auto predicate)
		{
			if (!_size)
			{
				return false;
			}

			bool ret = false;
			for (auto ptr = _data, last = _data + _size - 1; ptr <= last;)
			{
				if (predicate(*ptr))
				{
					ret = true;

					if (ptr == last)
					{
						// Popping the last entry from list. Just set the new size and exit
						_size--;
						break;
					}

					// Move item to the end of the list and shrink by 1
					std::memcpy(ptr, last, sizeof(Ty));
					_size--;
					last--;

					// Retest the same ptr which now has the previous tail item
					continue;
				}

				ptr++;
			}

			return ret;
		}

		simple_array<Ty> filter(std::predicate<const Ty&> auto predicate) const
		{
			simple_array<Ty> result;
			result.reserve(size());

			for (auto it = begin(); it != end(); ++it)
			{
				if (predicate(*it))
				{
					result.push_back(*it);
				}
			}
			return result;
		}

		simple_array<Ty>& sort(std::predicate<const Ty&, const Ty&> auto predicate)
		{
			if (_size < 2)
			{
				return *this;
			}

			std::sort(begin(), end(), predicate);
			return *this;
		}

		template <typename F, typename U = std::invoke_result_t<F, const Ty&>>
			requires (std::is_invocable_v<F, const Ty&> && std::is_trivially_destructible_v<U>)
		simple_array<U> map(F&& xform) const
		{
			simple_array<U> result;
			result.reserve(size());

			for (auto it = begin(); it != end(); ++it)
			{
				result.push_back(xform(*it));
			}
			return result;
		}

		template <typename F, typename U = std::invoke_result_t<F, const Ty&>>
			requires (std::is_invocable_v<F, const Ty&> && !std::is_trivially_destructible_v<U>)
		std::vector<U> map(F&& xform) const
		{
			std::vector<U> result;
			result.reserve(size());

			for (auto it = begin(); it != end(); ++it)
			{
				result.push_back(xform(*it));
			}
			return result;
		}

		template <typename F, typename U>
			requires std::is_invocable_r_v<U, F, const U&, const Ty&>
		U reduce(U initial_value, F&& reducer) const
		{
			U accumulate = initial_value;
			for (auto it = begin(); it != end(); ++it)
			{
				accumulate = reducer(accumulate, *it);
			}
			return accumulate;
		}

		template <typename F>
		void for_each(F&& func)
		{
			std::for_each(begin(), end(), func);
		}
	};
}
struct Attributes {u32 address=0,gcm_format=7;u16 width=32,height=32,depth=1,mipmaps=4;u32 pitch=128;bool swizzled=false;};
struct Options {u32 lookup_mask=7;};
struct Result {
 u32 view=0,context=0,format=0,scale=0,image=0,address=0,merge_count=0;
 address_range32 ios_validation_range;
 bool selected=false;
 Result()=default;
 Result(u32 v,u32 c,u32 f,u32 s,u32 i,u32 a):view(v),context(c),format(f),scale(s),image(i),address(a),selected(true){}
 bool operator==(const Result&)const=default;
};
using sampled_image_descriptor=Result;
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

		private:
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

	private:
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
			const auto it = std::find_if(m_address_index.begin(), m_address_index.end(),
				[&](const address_entry& entry) { return entry.section == &section; });
			if (it != m_address_index.end()) m_address_index.erase(it);
		}

		void add_address_entry(section_storage_type& section)
		{
			if (sections.size() <= address_index_threshold) return;
			// reset() can replace a valid resource-less range without first
			// destroying a GPU resource. Remove by slot, not by its new address.
			remove_address_entry(section);
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

	private:
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

		private:
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
 u32 view_id=0;
 bool pack_unpack_swap_bytes=false,swizzled=false,synchronized=false,flushed=false,speculatively_flushed=false,deferred_commit=false;
 u64 sync_timestamp=0,cache_tag=0,last_write_tag=0,last_use_frame=0;void* m_predictor_entry=nullptr;
 memory_read_flags readback_behaviour=memory_read_flags::flush_once;component_order view_flags=component_order::default_;
 texture_upload_context context=texture_upload_context::shader_read;texture_dimension_extended image_type=texture_dimension_extended::texture_dimension_2d;
 std::vector<address_range32> flush_exclusions;
 Section()=default;explicit Section(ranged_storage_block_type* b){initialize(b);}
 Section* derived(){return this;}
 void initialize(ranged_storage_block_type*);void reset(const address_range32&);void notify_range_valid();
private:

void invalidate_range();
public:
void invalidate_test_range(){invalidate_range();}

 void on_section_resources_created();void on_section_resources_destroyed();void set_dirty(bool);void update_unreleased();bool is_unreleased()const;
 bool sync_protection();bool matches(u32,u32,u32,u32,u32)const;bool matches(u32,u32,u32,u32,u32,u32)const;
 bool is_dirty()const{if(rsx::count_visits)++rsx::visits;return dirty;}
 bool exists()const{return resources||(context==texture_upload_context::dma&&locked);}
 bool is_managed()const{return true;}
 texture_upload_context get_context()const{return context;}
 bool is_swizzled()const{return swizzled;}
 u16 get_height()const{return height;}
 u32 get_rsx_pitch()const{return rsx_pitch;}
 u32 get_view(u32)const{return view_id;}
 u32 get_format_class()const{return gcm_format+17;}
 u32 get_image_type()const{return static_cast<u32>(image_type);}
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
 [[gnu::noinline]] Result query_before(const Attributes& attr,const address_range32& memory_range,const Options& options) {
const u32 scale=1,remap=0;rsx::simple_array<section_storage_type*> overlapping_locals;
			const u32 lookup_mask = rsx::texture_upload_context::shader_read | rsx::texture_upload_context::blit_engine_dst | rsx::texture_upload_context::blit_engine_src;
#ifdef RPCS3_IOS
			auto& exact_block = m_storage.block_for(attr.address);
			if (false && memory_range.valid() && memory_range.start == attr.address &&
				exact_block.size() > ranged_storage_block::address_index_threshold)
			{
				// REWINDBOX_TEXTURE_EXACT_INDEX: the caller holds the cache reader
				// lock. Only slots with this base can match; the address index keeps
				// their original order. Defer overlap collection until an exact miss.
				const u32 candidate_contexts = lookup_mask & options.lookup_mask;
				const u32 required_pitch = attr.height > 1 ? attr.pitch : 0;
				rsx::simple_array<section_storage_type*> invalidated_exact;
				bool stop_exact = false;
				for (const auto& entry : exact_block.find_address(attr.address))
				{
					auto* cached_texture = entry.section;
					if (!cached_texture->is_locked() || cached_texture->is_dirty() ||
						!(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
						(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1)))
					{
						continue;
					}
					if (!cached_texture->matches(attr.address, attr.gcm_format, attr.width, attr.height, attr.depth, 0))
					{
						continue;
					}
					if (cached_texture->sync_protection())
					{
#ifdef TEXTURE_CACHE_DEBUG
						if (!memory_range.inside(cached_texture->get_confirmed_range()))
						{
							continue;
						}
#endif
						if (attr.swizzled == cached_texture->is_swizzled())
						{
							sampled_image_descriptor exact_match
							{
								cached_texture->get_view(remap),
								cached_texture->get_context(),
								cached_texture->get_format_class(),
								scale,
								cached_texture->get_image_type(),
								cached_texture->get_section_base()
							};
							exact_match.ios_validation_range = cached_texture->get_section_range();
							return exact_match;
						}
						rsx_log.warning("A texture was found in cache for address 0x%x, but swizzle flag does not match", attr.address);
						cached_texture->unprotect();
						cached_texture->set_dirty(true);
						stop_exact = true;
					}
					// The old walk appended this slot before failed validation or
					// swizzle rejection. Preserve the swap-with-tail erase order.
					invalidated_exact.push_back(cached_texture);
					if (stop_exact) break;
				}

				// Exact candidates were already checked in slot order. Collect
				// merge inputs once, including slots invalidated by those checks.
				const bool retain_invalidated = !invalidated_exact.empty();
				usz invalidated_pos = 0;
				for (auto It = m_storage.range_begin(memory_range, full_range, !retain_invalidated); It != m_storage.range_end(); It++)
				{
					auto* cached_texture = &*It;
					const bool was_invalidated = invalidated_pos < invalidated_exact.size() &&
						invalidated_exact[invalidated_pos] == cached_texture;
					if (was_invalidated) ++invalidated_pos;
					if (!was_invalidated && ((retain_invalidated && !cached_texture->is_locked()) || cached_texture->is_dirty() ||
						!(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
						(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1))))
					{
						continue;
					}
					overlapping_locals.push_back(cached_texture);
				}
			}
			else
			{
#endif
#ifdef RPCS3_IOS
			// REWINDBOX_TEXTURE_EXACT_HIT: visit candidates in the same order as
			// find_texture_from_range, but stop at the first valid exact match.
			// Common hits need neither a heap array nor a walk of all overlaps.
			const u32 candidate_contexts = lookup_mask & options.lookup_mask;
			const u32 required_pitch = attr.height > 1 ? attr.pitch : 0;
			bool search_exact = true;
			for (auto It = m_storage.range_begin(memory_range, full_range, true); It != m_storage.range_end(); It++)
			{
				auto* cached_texture = &*It;
				if (cached_texture->is_dirty() || !(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
					(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1)))
				{
					continue;
				}
				// Retain the ordered merge candidates as we go. A miss still walks
				// the range once; a swizzle mismatch stops only the exact search.
				overlapping_locals.push_back(cached_texture);
				if (!search_exact)
				{
					continue;
				}
#else
			// Collect candidates without validating their contents yet. An exact hit
			// needs only its own validation; otherwise only blit destinations can
			// contribute to the merge below. Hashing unrelated overlaps is expensive
			// on platforms that use content hashes instead of page protection.
			overlapping_locals = find_texture_from_range<true, false>(memory_range, attr.height > 1 ? attr.pitch : 0, lookup_mask & options.lookup_mask);

			// Search for exact match if possible
			for (auto& cached_texture : overlapping_locals)
			{
#endif
				if (cached_texture->matches(attr.address, attr.gcm_format, attr.width, attr.height, attr.depth, 0) &&
					cached_texture->sync_protection())
				{
#ifdef TEXTURE_CACHE_DEBUG
					if (!memory_range.inside(cached_texture->get_confirmed_range()))
					{
						// TODO. This is easily possible for blit_dst textures if the blit is incomplete in Y
						// The possibility that a texture will be split into parts on the CPU like this is very rare
						continue;
					}
#endif
					if (attr.swizzled != cached_texture->is_swizzled())
					{
						// We can have the correct data in cached_texture but it needs decoding before it can be sampled.
						// Usually a sign of a game bug where the developer forgot to mark the texture correctly the first time we see it.
						// TODO: This section should execute under an exclusive lock, but we're not actually modifying any object references, only flags
						rsx_log.warning("A texture was found in cache for address 0x%x, but swizzle flag does not match", attr.address);
						cached_texture->unprotect();
						cached_texture->set_dirty(true);
#ifdef RPCS3_IOS
						search_exact = false;
						continue;
#else
						break;
#endif
					}

					sampled_image_descriptor exact_match
					{
						cached_texture->get_view(remap),
						cached_texture->get_context(),
						cached_texture->get_format_class(),
						scale,
						cached_texture->get_image_type(),
						cached_texture->get_section_base()
					};
#ifdef RPCS3_IOS
					exact_match.ios_validation_range = cached_texture->get_section_range();
#endif
					return exact_match;
				}
			}
#ifdef RPCS3_IOS
			}
#endif

			if (!overlapping_locals.empty())
			{
				// Validate every transfer target before it can be used by the merge.
				overlapping_locals.erase_if([](const auto& e)
				{
					return e->is_dirty() || (e->get_context() != rsx::texture_upload_context::blit_engine_dst) ||
						!e->sync_protection();
				});
			}

Result result;result.merge_count=overlapping_locals.size();if(rsx::tracing)for(const auto* section:overlapping_locals)rsx::merges.push_back(section->id);return result;
}
[[gnu::noinline]] Result query_after(const Attributes& attr,const address_range32& memory_range,const Options& options) {
const u32 scale=1,remap=0;rsx::simple_array<section_storage_type*> overlapping_locals;
			const u32 lookup_mask = rsx::texture_upload_context::shader_read | rsx::texture_upload_context::blit_engine_dst | rsx::texture_upload_context::blit_engine_src;
#ifdef RPCS3_IOS
			auto& exact_block = m_storage.block_for(attr.address);
			if (memory_range.valid() && memory_range.start == attr.address &&
				exact_block.size() > ranged_storage_block::address_index_threshold)
			{
				// REWINDBOX_TEXTURE_EXACT_INDEX: the caller holds the cache reader
				// lock. Only slots with this base can match; the address index keeps
				// their original order. Defer overlap collection until an exact miss.
				const u32 candidate_contexts = lookup_mask & options.lookup_mask;
				const u32 required_pitch = attr.height > 1 ? attr.pitch : 0;
				rsx::simple_array<section_storage_type*> invalidated_exact;
				bool stop_exact = false;
				for (const auto& entry : exact_block.find_address(attr.address))
				{
					auto* cached_texture = entry.section;
					if (!cached_texture->is_locked() || cached_texture->is_dirty() ||
						!(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
						(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1)))
					{
						continue;
					}
					if (!cached_texture->matches(attr.address, attr.gcm_format, attr.width, attr.height, attr.depth, 0))
					{
						continue;
					}
					if (cached_texture->sync_protection())
					{
#ifdef TEXTURE_CACHE_DEBUG
						if (!memory_range.inside(cached_texture->get_confirmed_range()))
						{
							continue;
						}
#endif
						if (attr.swizzled == cached_texture->is_swizzled())
						{
							sampled_image_descriptor exact_match
							{
								cached_texture->get_view(remap),
								cached_texture->get_context(),
								cached_texture->get_format_class(),
								scale,
								cached_texture->get_image_type(),
								cached_texture->get_section_base()
							};
							exact_match.ios_validation_range = cached_texture->get_section_range();
							return exact_match;
						}
						rsx_log.warning("A texture was found in cache for address 0x%x, but swizzle flag does not match", attr.address);
						cached_texture->unprotect();
						cached_texture->set_dirty(true);
						stop_exact = true;
					}
					// The old walk appended this slot before failed validation or
					// swizzle rejection. Preserve the swap-with-tail erase order.
					invalidated_exact.push_back(cached_texture);
					if (stop_exact) break;
				}

				// Exact candidates were already checked in slot order. Collect
				// merge inputs once, including slots invalidated by those checks.
				const bool retain_invalidated = !invalidated_exact.empty();
				usz invalidated_pos = 0;
				for (auto It = m_storage.range_begin(memory_range, full_range, !retain_invalidated); It != m_storage.range_end(); It++)
				{
					auto* cached_texture = &*It;
					const bool was_invalidated = invalidated_pos < invalidated_exact.size() &&
						invalidated_exact[invalidated_pos] == cached_texture;
					if (was_invalidated) ++invalidated_pos;
					if (!was_invalidated && ((retain_invalidated && !cached_texture->is_locked()) || cached_texture->is_dirty() ||
						!(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
						(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1))))
					{
						continue;
					}
					overlapping_locals.push_back(cached_texture);
				}
			}
			else
			{
#endif
#ifdef RPCS3_IOS
			// REWINDBOX_TEXTURE_EXACT_HIT: visit candidates in the same order as
			// find_texture_from_range, but stop at the first valid exact match.
			// Common hits need neither a heap array nor a walk of all overlaps.
			const u32 candidate_contexts = lookup_mask & options.lookup_mask;
			const u32 required_pitch = attr.height > 1 ? attr.pitch : 0;
			bool search_exact = true;
			for (auto It = m_storage.range_begin(memory_range, full_range, true); It != m_storage.range_end(); It++)
			{
				auto* cached_texture = &*It;
				if (cached_texture->is_dirty() || !(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
					(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1)))
				{
					continue;
				}
				// Retain the ordered merge candidates as we go. A miss still walks
				// the range once; a swizzle mismatch stops only the exact search.
				overlapping_locals.push_back(cached_texture);
				if (!search_exact)
				{
					continue;
				}
#else
			// Collect candidates without validating their contents yet. An exact hit
			// needs only its own validation; otherwise only blit destinations can
			// contribute to the merge below. Hashing unrelated overlaps is expensive
			// on platforms that use content hashes instead of page protection.
			overlapping_locals = find_texture_from_range<true, false>(memory_range, attr.height > 1 ? attr.pitch : 0, lookup_mask & options.lookup_mask);

			// Search for exact match if possible
			for (auto& cached_texture : overlapping_locals)
			{
#endif
				if (cached_texture->matches(attr.address, attr.gcm_format, attr.width, attr.height, attr.depth, 0) &&
					cached_texture->sync_protection())
				{
#ifdef TEXTURE_CACHE_DEBUG
					if (!memory_range.inside(cached_texture->get_confirmed_range()))
					{
						// TODO. This is easily possible for blit_dst textures if the blit is incomplete in Y
						// The possibility that a texture will be split into parts on the CPU like this is very rare
						continue;
					}
#endif
					if (attr.swizzled != cached_texture->is_swizzled())
					{
						// We can have the correct data in cached_texture but it needs decoding before it can be sampled.
						// Usually a sign of a game bug where the developer forgot to mark the texture correctly the first time we see it.
						// TODO: This section should execute under an exclusive lock, but we're not actually modifying any object references, only flags
						rsx_log.warning("A texture was found in cache for address 0x%x, but swizzle flag does not match", attr.address);
						cached_texture->unprotect();
						cached_texture->set_dirty(true);
#ifdef RPCS3_IOS
						search_exact = false;
						continue;
#else
						break;
#endif
					}

					sampled_image_descriptor exact_match
					{
						cached_texture->get_view(remap),
						cached_texture->get_context(),
						cached_texture->get_format_class(),
						scale,
						cached_texture->get_image_type(),
						cached_texture->get_section_base()
					};
#ifdef RPCS3_IOS
					exact_match.ios_validation_range = cached_texture->get_section_range();
#endif
					return exact_match;
				}
			}
#ifdef RPCS3_IOS
			}
#endif

			if (!overlapping_locals.empty())
			{
				// Validate every transfer target before it can be used by the merge.
				overlapping_locals.erase_if([](const auto& e)
				{
					return e->is_dirty() || (e->get_context() != rsx::texture_upload_context::blit_engine_dst) ||
						!e->sync_protection();
				});
			}

Result result;result.merge_count=overlapping_locals.size();if(rsx::tracing)for(const auto* section:overlapping_locals)rsx::merges.push_back(section->id);return result;
}
#define TEXTURE_CACHE_DEBUG
[[gnu::noinline]] Result query_before_debug(const Attributes& attr,const address_range32& memory_range,const Options& options) {
const u32 scale=1,remap=0;rsx::simple_array<section_storage_type*> overlapping_locals;
			const u32 lookup_mask = rsx::texture_upload_context::shader_read | rsx::texture_upload_context::blit_engine_dst | rsx::texture_upload_context::blit_engine_src;
#ifdef RPCS3_IOS
			auto& exact_block = m_storage.block_for(attr.address);
			if (false && memory_range.valid() && memory_range.start == attr.address &&
				exact_block.size() > ranged_storage_block::address_index_threshold)
			{
				// REWINDBOX_TEXTURE_EXACT_INDEX: the caller holds the cache reader
				// lock. Only slots with this base can match; the address index keeps
				// their original order. Defer overlap collection until an exact miss.
				const u32 candidate_contexts = lookup_mask & options.lookup_mask;
				const u32 required_pitch = attr.height > 1 ? attr.pitch : 0;
				rsx::simple_array<section_storage_type*> invalidated_exact;
				bool stop_exact = false;
				for (const auto& entry : exact_block.find_address(attr.address))
				{
					auto* cached_texture = entry.section;
					if (!cached_texture->is_locked() || cached_texture->is_dirty() ||
						!(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
						(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1)))
					{
						continue;
					}
					if (!cached_texture->matches(attr.address, attr.gcm_format, attr.width, attr.height, attr.depth, 0))
					{
						continue;
					}
					if (cached_texture->sync_protection())
					{
#ifdef TEXTURE_CACHE_DEBUG
						if (!memory_range.inside(cached_texture->get_confirmed_range()))
						{
							continue;
						}
#endif
						if (attr.swizzled == cached_texture->is_swizzled())
						{
							sampled_image_descriptor exact_match
							{
								cached_texture->get_view(remap),
								cached_texture->get_context(),
								cached_texture->get_format_class(),
								scale,
								cached_texture->get_image_type(),
								cached_texture->get_section_base()
							};
							exact_match.ios_validation_range = cached_texture->get_section_range();
							return exact_match;
						}
						rsx_log.warning("A texture was found in cache for address 0x%x, but swizzle flag does not match", attr.address);
						cached_texture->unprotect();
						cached_texture->set_dirty(true);
						stop_exact = true;
					}
					// The old walk appended this slot before failed validation or
					// swizzle rejection. Preserve the swap-with-tail erase order.
					invalidated_exact.push_back(cached_texture);
					if (stop_exact) break;
				}

				// Exact candidates were already checked in slot order. Collect
				// merge inputs once, including slots invalidated by those checks.
				const bool retain_invalidated = !invalidated_exact.empty();
				usz invalidated_pos = 0;
				for (auto It = m_storage.range_begin(memory_range, full_range, !retain_invalidated); It != m_storage.range_end(); It++)
				{
					auto* cached_texture = &*It;
					const bool was_invalidated = invalidated_pos < invalidated_exact.size() &&
						invalidated_exact[invalidated_pos] == cached_texture;
					if (was_invalidated) ++invalidated_pos;
					if (!was_invalidated && ((retain_invalidated && !cached_texture->is_locked()) || cached_texture->is_dirty() ||
						!(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
						(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1))))
					{
						continue;
					}
					overlapping_locals.push_back(cached_texture);
				}
			}
			else
			{
#endif
#ifdef RPCS3_IOS
			// REWINDBOX_TEXTURE_EXACT_HIT: visit candidates in the same order as
			// find_texture_from_range, but stop at the first valid exact match.
			// Common hits need neither a heap array nor a walk of all overlaps.
			const u32 candidate_contexts = lookup_mask & options.lookup_mask;
			const u32 required_pitch = attr.height > 1 ? attr.pitch : 0;
			bool search_exact = true;
			for (auto It = m_storage.range_begin(memory_range, full_range, true); It != m_storage.range_end(); It++)
			{
				auto* cached_texture = &*It;
				if (cached_texture->is_dirty() || !(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
					(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1)))
				{
					continue;
				}
				// Retain the ordered merge candidates as we go. A miss still walks
				// the range once; a swizzle mismatch stops only the exact search.
				overlapping_locals.push_back(cached_texture);
				if (!search_exact)
				{
					continue;
				}
#else
			// Collect candidates without validating their contents yet. An exact hit
			// needs only its own validation; otherwise only blit destinations can
			// contribute to the merge below. Hashing unrelated overlaps is expensive
			// on platforms that use content hashes instead of page protection.
			overlapping_locals = find_texture_from_range<true, false>(memory_range, attr.height > 1 ? attr.pitch : 0, lookup_mask & options.lookup_mask);

			// Search for exact match if possible
			for (auto& cached_texture : overlapping_locals)
			{
#endif
				if (cached_texture->matches(attr.address, attr.gcm_format, attr.width, attr.height, attr.depth, 0) &&
					cached_texture->sync_protection())
				{
#ifdef TEXTURE_CACHE_DEBUG
					if (!memory_range.inside(cached_texture->get_confirmed_range()))
					{
						// TODO. This is easily possible for blit_dst textures if the blit is incomplete in Y
						// The possibility that a texture will be split into parts on the CPU like this is very rare
						continue;
					}
#endif
					if (attr.swizzled != cached_texture->is_swizzled())
					{
						// We can have the correct data in cached_texture but it needs decoding before it can be sampled.
						// Usually a sign of a game bug where the developer forgot to mark the texture correctly the first time we see it.
						// TODO: This section should execute under an exclusive lock, but we're not actually modifying any object references, only flags
						rsx_log.warning("A texture was found in cache for address 0x%x, but swizzle flag does not match", attr.address);
						cached_texture->unprotect();
						cached_texture->set_dirty(true);
#ifdef RPCS3_IOS
						search_exact = false;
						continue;
#else
						break;
#endif
					}

					sampled_image_descriptor exact_match
					{
						cached_texture->get_view(remap),
						cached_texture->get_context(),
						cached_texture->get_format_class(),
						scale,
						cached_texture->get_image_type(),
						cached_texture->get_section_base()
					};
#ifdef RPCS3_IOS
					exact_match.ios_validation_range = cached_texture->get_section_range();
#endif
					return exact_match;
				}
			}
#ifdef RPCS3_IOS
			}
#endif

			if (!overlapping_locals.empty())
			{
				// Validate every transfer target before it can be used by the merge.
				overlapping_locals.erase_if([](const auto& e)
				{
					return e->is_dirty() || (e->get_context() != rsx::texture_upload_context::blit_engine_dst) ||
						!e->sync_protection();
				});
			}

Result result;result.merge_count=overlapping_locals.size();if(rsx::tracing)for(const auto* section:overlapping_locals)rsx::merges.push_back(section->id);return result;
}
[[gnu::noinline]] Result query_after_debug(const Attributes& attr,const address_range32& memory_range,const Options& options) {
const u32 scale=1,remap=0;rsx::simple_array<section_storage_type*> overlapping_locals;
			const u32 lookup_mask = rsx::texture_upload_context::shader_read | rsx::texture_upload_context::blit_engine_dst | rsx::texture_upload_context::blit_engine_src;
#ifdef RPCS3_IOS
			auto& exact_block = m_storage.block_for(attr.address);
			if (memory_range.valid() && memory_range.start == attr.address &&
				exact_block.size() > ranged_storage_block::address_index_threshold)
			{
				// REWINDBOX_TEXTURE_EXACT_INDEX: the caller holds the cache reader
				// lock. Only slots with this base can match; the address index keeps
				// their original order. Defer overlap collection until an exact miss.
				const u32 candidate_contexts = lookup_mask & options.lookup_mask;
				const u32 required_pitch = attr.height > 1 ? attr.pitch : 0;
				rsx::simple_array<section_storage_type*> invalidated_exact;
				bool stop_exact = false;
				for (const auto& entry : exact_block.find_address(attr.address))
				{
					auto* cached_texture = entry.section;
					if (!cached_texture->is_locked() || cached_texture->is_dirty() ||
						!(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
						(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1)))
					{
						continue;
					}
					if (!cached_texture->matches(attr.address, attr.gcm_format, attr.width, attr.height, attr.depth, 0))
					{
						continue;
					}
					if (cached_texture->sync_protection())
					{
#ifdef TEXTURE_CACHE_DEBUG
						if (!memory_range.inside(cached_texture->get_confirmed_range()))
						{
							continue;
						}
#endif
						if (attr.swizzled == cached_texture->is_swizzled())
						{
							sampled_image_descriptor exact_match
							{
								cached_texture->get_view(remap),
								cached_texture->get_context(),
								cached_texture->get_format_class(),
								scale,
								cached_texture->get_image_type(),
								cached_texture->get_section_base()
							};
							exact_match.ios_validation_range = cached_texture->get_section_range();
							return exact_match;
						}
						rsx_log.warning("A texture was found in cache for address 0x%x, but swizzle flag does not match", attr.address);
						cached_texture->unprotect();
						cached_texture->set_dirty(true);
						stop_exact = true;
					}
					// The old walk appended this slot before failed validation or
					// swizzle rejection. Preserve the swap-with-tail erase order.
					invalidated_exact.push_back(cached_texture);
					if (stop_exact) break;
				}

				// Exact candidates were already checked in slot order. Collect
				// merge inputs once, including slots invalidated by those checks.
				const bool retain_invalidated = !invalidated_exact.empty();
				usz invalidated_pos = 0;
				for (auto It = m_storage.range_begin(memory_range, full_range, !retain_invalidated); It != m_storage.range_end(); It++)
				{
					auto* cached_texture = &*It;
					const bool was_invalidated = invalidated_pos < invalidated_exact.size() &&
						invalidated_exact[invalidated_pos] == cached_texture;
					if (was_invalidated) ++invalidated_pos;
					if (!was_invalidated && ((retain_invalidated && !cached_texture->is_locked()) || cached_texture->is_dirty() ||
						!(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
						(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1))))
					{
						continue;
					}
					overlapping_locals.push_back(cached_texture);
				}
			}
			else
			{
#endif
#ifdef RPCS3_IOS
			// REWINDBOX_TEXTURE_EXACT_HIT: visit candidates in the same order as
			// find_texture_from_range, but stop at the first valid exact match.
			// Common hits need neither a heap array nor a walk of all overlaps.
			const u32 candidate_contexts = lookup_mask & options.lookup_mask;
			const u32 required_pitch = attr.height > 1 ? attr.pitch : 0;
			bool search_exact = true;
			for (auto It = m_storage.range_begin(memory_range, full_range, true); It != m_storage.range_end(); It++)
			{
				auto* cached_texture = &*It;
				if (cached_texture->is_dirty() || !(candidate_contexts & static_cast<u32>(cached_texture->get_context())) ||
					(required_pitch && !rsx::pitch_compatible<false>(cached_texture, required_pitch, -1)))
				{
					continue;
				}
				// Retain the ordered merge candidates as we go. A miss still walks
				// the range once; a swizzle mismatch stops only the exact search.
				overlapping_locals.push_back(cached_texture);
				if (!search_exact)
				{
					continue;
				}
#else
			// Collect candidates without validating their contents yet. An exact hit
			// needs only its own validation; otherwise only blit destinations can
			// contribute to the merge below. Hashing unrelated overlaps is expensive
			// on platforms that use content hashes instead of page protection.
			overlapping_locals = find_texture_from_range<true, false>(memory_range, attr.height > 1 ? attr.pitch : 0, lookup_mask & options.lookup_mask);

			// Search for exact match if possible
			for (auto& cached_texture : overlapping_locals)
			{
#endif
				if (cached_texture->matches(attr.address, attr.gcm_format, attr.width, attr.height, attr.depth, 0) &&
					cached_texture->sync_protection())
				{
#ifdef TEXTURE_CACHE_DEBUG
					if (!memory_range.inside(cached_texture->get_confirmed_range()))
					{
						// TODO. This is easily possible for blit_dst textures if the blit is incomplete in Y
						// The possibility that a texture will be split into parts on the CPU like this is very rare
						continue;
					}
#endif
					if (attr.swizzled != cached_texture->is_swizzled())
					{
						// We can have the correct data in cached_texture but it needs decoding before it can be sampled.
						// Usually a sign of a game bug where the developer forgot to mark the texture correctly the first time we see it.
						// TODO: This section should execute under an exclusive lock, but we're not actually modifying any object references, only flags
						rsx_log.warning("A texture was found in cache for address 0x%x, but swizzle flag does not match", attr.address);
						cached_texture->unprotect();
						cached_texture->set_dirty(true);
#ifdef RPCS3_IOS
						search_exact = false;
						continue;
#else
						break;
#endif
					}

					sampled_image_descriptor exact_match
					{
						cached_texture->get_view(remap),
						cached_texture->get_context(),
						cached_texture->get_format_class(),
						scale,
						cached_texture->get_image_type(),
						cached_texture->get_section_base()
					};
#ifdef RPCS3_IOS
					exact_match.ios_validation_range = cached_texture->get_section_range();
#endif
					return exact_match;
				}
			}
#ifdef RPCS3_IOS
			}
#endif

			if (!overlapping_locals.empty())
			{
				// Validate every transfer target before it can be used by the merge.
				overlapping_locals.erase_if([](const auto& e)
				{
					return e->is_dirty() || (e->get_context() != rsx::texture_upload_context::blit_engine_dst) ||
						!e->sync_protection();
				});
			}

Result result;result.merge_count=overlapping_locals.size();if(rsx::tracing)for(const auto* section:overlapping_locals)rsx::merges.push_back(section->id);return result;
}
#undef TEXTURE_CACHE_DEBUG

};
void Section::unprotect(){if(rsx::tracing)rsx::unprotects.push_back(id);if(locked){rsx::buffered_section::discard();m_block->on_section_unprotected(*this);if(context==texture_upload_context::shader_read)set_dirty(true);}}
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

struct Query {Attributes attr;address_range32 range;Options options;};
Query make_query(u32 address,u32 length=256){Query q;q.attr.address=address;q.range=address_range32::start_length(address,length);return q;}
void lock_section(Section& s,bool locked){if(s.locked==locked)return;s.locked=locked;if(locked){s.protection=utils::protection::ro;s.m_block->on_section_protected(s);}else{s.protection=utils::protection::rw;s.m_block->on_section_unprotected(s);}s.update_unreleased();}
void reset_section(Section& s,u32 base,u32 length,bool resources=true){
 lock_section(s,false);s.reset(address_range32::start_length(base,length));
 s.width=32;s.height=32;s.depth=1;s.mipmaps=4;s.gcm_format=7;s.rsx_pitch=128;
 s.memory_valid=true;s.swizzled=false;s.view_id=s.id;
 s.context=rsx::texture_upload_context::blit_engine_dst;
 if(resources){s.resources=true;s.on_section_resources_created();lock_section(s,true);s.set_dirty(false);}else{s.set_dirty(true);}
}
struct Rig {
 std::unique_ptr<Cache> cache=std::make_unique<Cache>();std::vector<Section*> slots;
 Section& add(u32 address,u32 length,u32 id,bool resources=true){auto& s=cache->m_storage.block_for(address).create_section();s.id=id;reset_section(s,address,length,resources);slots.push_back(&s);return s;}
 void clear(){cache->m_storage.clear();slots.clear();}
};
struct State {
 bool dirty,locked,resources,unreleased,memory_valid,swizzled;
 utils::protection protection;address_range32 confirmed,cpu;u64 last_use,validated_epoch;
 bool operator==(const State&)const=default;
};
State state(const Section& s){return {s.dirty,s.locked,s.resources,s.triggered_unreleased_callbacks,s.memory_valid,s.swizzled,s.protection,s.confirmed_range,s.cpu_range,s.last_use_frame,s.validated_epoch};}
std::vector<State> states(const Rig& r){std::vector<State> out;for(const auto* s:r.slots)out.push_back(state(*s));return out;}
void restore(Rig& r,const std::vector<State>& snapshots){
 for(usz i=0;i<r.slots.size();++i){auto& s=*r.slots[i];const auto& v=snapshots[i];assert(s.resources==v.resources&&s.cpu_range==v.cpu);lock_section(s,v.locked);s.dirty=v.dirty;s.memory_valid=v.memory_valid;s.swizzled=v.swizzled;s.protection=v.protection;s.confirmed_range=v.confirmed;s.last_use_frame=v.last_use;s.validated_epoch=v.validated_epoch;s.update_unreleased();assert(state(s)==v);}
}
void clear_trace(){rsx::validations.clear();rsx::unprotects.clear();rsx::merges.clear();warnings.clear();rsx::visits=rsx::range_visits=0;array_allocations=array_bytes=0;}
struct Trace {std::vector<u32> validations,unprotects,merges,warnings;bool operator==(const Trace&)const=default;};
Trace trace(){return {rsx::validations,rsx::unprotects,rsx::merges,warnings};}
struct Counts {u64 queries=0,debug_queries=0,mutations=0,range_before=0,range_after=0,predicates_before=0,predicates_after=0,allocations_before=0,allocations_after=0;};
Result compare(Rig& r,const Query& q,Counts& c,bool debug=false){
 const auto initial=states(r);clear_trace();count_allocations=true;
 const auto old=debug?r.cache->query_before_debug(q.attr,q.range,q.options):r.cache->query_before(q.attr,q.range,q.options);
 count_allocations=false;const auto old_trace=trace();const auto old_state=states(r);
 c.range_before+=rsx::range_visits;c.predicates_before+=rsx::visits;c.allocations_before+=array_allocations;
 restore(r,initial);clear_trace();count_allocations=true;
 const auto now=debug?r.cache->query_after_debug(q.attr,q.range,q.options):r.cache->query_after(q.attr,q.range,q.options);
 count_allocations=false;c.range_after+=rsx::range_visits;c.predicates_after+=rsx::visits;c.allocations_after+=array_allocations;
 if(!(old==now&&old_trace==trace()&&old_state==states(r))){std::cerr<<"differential failure query "<<c.queries<<" debug="<<debug<<" base="<<q.attr.address<<" before="<<old.selected<<":"<<old.view<<":"<<old.merge_count<<" after="<<now.selected<<":"<<now.view<<":"<<now.merge_count<<"\n";std::cerr<<" result="<<(old==now)<<" states="<<(old_state==states(r))<<" trace="<<(old_trace==trace())<<"\n";for(auto v:old_trace.validations)std::cerr<<"bV"<<v<<",";for(auto v:rsx::validations)std::cerr<<"aV"<<v<<",";for(auto v:old_trace.merges)std::cerr<<"bM"<<v<<",";for(auto v:rsx::merges)std::cerr<<"aM"<<v<<",";std::cerr<<"\n";std::abort();}
 ++c.queries;c.debug_queries+=debug;return now;
}
void fill(Rig& r,u32 count,u32 base=0x100000){for(u32 i=0;i<count;++i)r.add(base+i*512,256,i+1);}
Counts correctness(){
 Counts counts;
 for(u32 n:{1,8,16,17,64,256}){
  Rig r;fill(r,n);
  for(u32 i=0;i<n;++i){auto q=make_query(0x100000+i*512);auto hit=compare(r,q,counts);assert(hit.selected&&hit.view==i+1);compare(r,q,counts,true);q.attr.gcm_format=99;assert(!compare(r,q,counts).selected);q=make_query(q.attr.address+256);assert(!compare(r,q,counts).selected);}
 }
 {
  Rig r;fill(r,17);const auto base=0x110000;auto& first=r.add(base,256,101);auto& second=r.add(base,256,102);auto& third=r.add(base,256,103);
  first.gcm_format=3;second.rsx_pitch=256;auto q=make_query(base);assert(compare(r,q,counts).view==103);
  first.gcm_format=7;first.memory_valid=false;second.rsx_pitch=128;assert(compare(r,q,counts).view==102);
  assert(rsx::validations==std::vector<u32>({101,102}));assert(first.dirty&&!first.locked);
  reset_section(first,base,256);first.swizzled=true;third.swizzled=false;
  const auto result=compare(r,q,counts);assert(!result.selected&&warnings.size()==1);assert(first.dirty&&!first.locked);assert(rsx::validations.front()==101);
  reset_section(first,base,256);first.view_id=0;const auto null_view=compare(r,q,counts);assert(null_view.selected&&null_view.view==0&&null_view.merge_count==0);
  reset_section(first,base,256);first.confirmed_range=address_range32::start_length(base,128);second.confirmed_range=address_range32::start_length(base,64);third.confirmed_range=address_range32::start_length(base,256);
  assert(compare(r,q,counts,true).view==103);assert(rsx::validations==std::vector<u32>({101,102,103}));
  third.confirmed_range=address_range32::start_length(base,32);assert(!compare(r,q,counts,true).selected);assert(rsx::validations==std::vector<u32>({101,102,103,101,102,103}));
  // Height-one rules use the production pitch_compatible helper. Mip counts
  // deliberately differ: this exact path requests zero and ignores mip count.
  for(auto* s:{&first,&second,&third}){reset_section(*s,base,256);s->height=1;s->rsx_pitch=13;s->mipmaps=0;}
  q.attr.height=1;q.attr.pitch=99;assert(compare(r,q,counts).view==101);
  q.attr.height=0;assert(compare(r,q,counts).view==101);
  q.attr.height=32;for(auto* s:{&first,&second,&third})s->height=32;
  assert(!compare(r,q,counts).selected);
  q.attr.pitch=13;first.context=rsx::framebuffer_storage;second.context=rsx::blit_engine_src;q.options.lookup_mask=rsx::shader_read|rsx::blit_engine_dst;
  assert(compare(r,q,counts).view==103);
  lock_section(third,false);assert(!compare(r,q,counts).selected);
 }
 {
  Rig r;fill(r,17);const u32 base=0x120000;
  r.add(base-64,512,3100);std::vector<Section*> duplicates;
  for(u32 i=0;i<24;++i){auto& slot=r.add(base,256,3200+i);slot.memory_valid=false;duplicates.push_back(&slot);}
  r.add(base-32,512,3300);
  auto q=make_query(base);const auto miss=compare(r,q,counts);assert(!miss.selected&&miss.merge_count==2);
  // More than eight invalidated exacts exercises the retention buffer's real
  // heap growth and swap-with-tail merge order, including a later swizzle stop.
  for(u32 i=0;i<24;++i){reset_section(*duplicates[i],base,256);duplicates[i]->memory_valid=i>=15;}
  duplicates[15]->swizzled=true;const auto swizzle=compare(r,q,counts);assert(!swizzle.selected&&warnings.size()==1);
  for(u32 i=0;i<24;++i){reset_section(*duplicates[i],base,256);duplicates[i]->memory_valid=i>=20;}
  assert(compare(r,q,counts).view==3220);
 }
 {
  Rig r;
  // Earlier blocks contribute unowned overlap pointers. Same storage is used
  // for each version so their unordered_set iteration order is truly equal.
  for(u32 i=0;i<24;++i)r.add(0xff000+i*16,0x6000,1000+i);
  for(u32 i=0;i<64;++i)r.add(0x100000+i*32,0x5000,1100+i);
  auto q=make_query(0x100000+63*32);assert(compare(r,q,counts).view==1163);
  q.attr.gcm_format=99;assert(!compare(r,q,counts).selected);assert(rsx::merges.size()==88);
  // A failed earlier exact candidate remains dirty and absent from the final
  // merge, while validation order of all other blit destinations is retained.
  r.slots.back()->memory_valid=false;q.attr.gcm_format=7;compare(r,q,counts);
  q=make_query(0xff000);q.range=address_range32::start_length(0x100000,256);
  auto& probe_block=r.cache->m_storage.block_for(q.range.start);
  std::vector<Section*> probe_slots;for(auto it=probe_block.unowned_begin();it!=probe_block.unowned_end();++it)probe_slots.push_back(*it);
  assert(probe_slots.size()==24);std::sort(probe_slots.begin(),probe_slots.end(),[](const auto* a,const auto* b){return a->id<b->id;});
  for(auto* slot:probe_slots)probe_block.remove_unowned_section(*slot);
  u32 shift=std::strtoul(std::getenv("PROBE_ROTATION"),nullptr,10);
  for(u32 i=0;i<24;++i)probe_block.add_unowned_section(*probe_slots[(i+shift)%24]);
  const auto counts_before_unowned=counts;u64 probe_rank=0;
  for(auto it=probe_block.unowned_begin();it!=probe_block.unowned_end();++it){++probe_rank;if((*it)->id==1000)break;}
  const auto unowned=compare(r,q,counts);assert(unowned.selected&&unowned.view==1000);
  assert(counts.range_before-counts_before_unowned.range_before==2*probe_rank+1);
  assert(counts.range_after-counts_before_unowned.range_after==2*probe_rank+1);
  assert(counts.predicates_before-counts_before_unowned.predicates_before==probe_rank+1);
  assert(counts.predicates_after-counts_before_unowned.predicates_after==probe_rank+1);
  std::cerr<<probe_rank<<"\n";
  // Multiblock ranges, out-of-order insertion and a same-address duplicate.
  for(u32 i=0;i<24;++i)r.add(0x200000+(23-i)*512,256,1300+i);
  r.add(0x100000,0x120000,1400);q=make_query(0x100000,0x120000);q.attr.width=99;compare(r,q,counts);compare(r,q,counts,true);
 }
 {
  Rig r;fill(r,16);r.slots.push_back(&r.cache->m_storage.block_for(0x100000).create_section());
  for(u32 i=0;i<16;++i)assert(compare(r,make_query(0x100000+i*512),counts).view==i+1);
  auto& no_resource=r.add(0x120000,256,3000,false);
  reset_section(no_resource,0x121000,256,false);compare(r,make_query(0x120000),counts);
  reset_section(no_resource,0x121000,256,true);assert(compare(r,make_query(0x121000),counts).view==3000);
  r.clear();fill(r,64);compare(r,make_query(0x121000),counts);assert(compare(r,make_query(0x100000),counts).view==1);
 }
 {
  Rig r;for(u32 base:{0u,0xfff00000u})for(u32 i=0;i<24;++i)r.add(base+i*512,256,4000+i);
  compare(r,make_query(0),counts);compare(r,make_query(0xfff00000),counts);
  r.add(0xfffff000,4096,5000);assert(compare(r,make_query(0xfffff000,4096),counts).view==5000);
  auto q=make_query(0xfffff000,16);q.range=address_range32::start_length(0xfffffff0,16);compare(r,q,counts);
 }
 {
  Rig r;fill(r,256);std::mt19937 rng(0x59329);
  for(u32 i=0;i<12000;++i){
   auto& s=*r.slots[rng()%r.slots.size()];
   switch(rng()%9){
    case 0:s.memory_valid=rng()%2;break;
    case 1:s.set_dirty(true);break;
    case 2:reset_section(s,0x100000+(rng()%192)*512,256,true);++counts.mutations;break;
    case 3:reset_section(s,0x100000+(rng()%192)*512,256,false);++counts.mutations;break;
    case 4:lock_section(s,false);s.destroy();s.invalidate_test_range();s.invalidate_test_range();++counts.mutations;break;
    case 5:s.width=16+(rng()%3)*16;s.height=1+(rng()%2)*31;s.depth=1+(rng()%2);s.mipmaps=rng()%8;break;
    case 6:s.swizzled=rng()%2;s.rsx_pitch=(rng()%3)*128;break;
    case 7:s.context=rsx::texture_upload_context(1u<<(rng()%5));s.update_unreleased();break;
    case 8:if(s.valid_range()&&s.resources){lock_section(s,true);s.set_dirty(false);}break;
   }
   auto q=make_query(0x100000+(rng()%192)*512);q.attr.width=16+(rng()%3)*16;q.attr.height=(rng()%4==0)?1:32;q.attr.depth=1+(rng()%2);q.attr.pitch=(rng()%3)*128;q.attr.swizzled=rng()%2;q.options.lookup_mask=1+(rng()%15);
   if(i%17==0)q.attr.gcm_format=0;
   compare(r,q,counts,i%4==0);
  }
 }
 return counts;
}
template<class Fn>double median(Fn fn,u32 count=20000){std::array<double,7>times{};u64 checksum=0;for(auto& t:times){auto start=std::chrono::steady_clock::now();for(u32 i=0;i<count;++i){asm volatile("":::"memory");auto result=fn(i);checksum+=result.view+result.merge_count+1;}t=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/count;}assert(checksum);std::sort(times.begin(),times.end());return times[3];}
void benchmark(){
 rsx::tracing=rsx::count_visits=false;std::cout<<",\"benchmarks\":[";bool first=true;
 for(u32 n:{8,16,17,64,256,1024}){
  Rig r;fill(r,n);
  auto run=[&](bool candidate,bool miss,bool first_slot){return median([&](u32 i){auto q=make_query(0x100000+(first_slot?0:((i*131)%n))*512+(miss?256u:0u));return candidate?r.cache->query_after(q.attr,q.range,q.options):r.cache->query_before(q.attr,q.range,q.options);});};
  const double hit_before=run(false,false,false),hit_after=run(true,false,false),miss_before=run(false,true,false),miss_after=run(true,true,false),first_before=run(false,false,true),first_after=run(true,false,true);
  // Dense overlapping ranges force the baseline's small-vector overflow.
  Rig overlaps;for(u32 i=0;i<n;++i)overlaps.add(0x100000+i*32,0x10000,i+1);
  auto q=make_query(0x100000+(n-1)*32);
  auto bench_overlap=[&](bool candidate){return median([&](u32){return candidate?overlaps.cache->query_after(q.attr,q.range,q.options):overlaps.cache->query_before(q.attr,q.range,q.options);});};
  const double overlap_before=bench_overlap(false),overlap_after=bench_overlap(true);
  array_allocations=array_bytes=0;count_allocations=true;for(u32 i=0;i<1000;++i)overlaps.cache->query_before(q.attr,q.range,q.options);count_allocations=false;
  const auto before_alloc=array_allocations,before_bytes=array_bytes;
  array_allocations=array_bytes=0;count_allocations=true;for(u32 i=0;i<1000;++i)overlaps.cache->query_after(q.attr,q.range,q.options);count_allocations=false;
  const auto after_alloc=array_allocations,after_bytes=array_bytes;if(n>16)assert(after_alloc==0);if(n>8)assert(before_alloc>0);
  if(!first)std::cout<<",";
  first=false;
  std::cout<<"{\"sections\":"<<n<<",\"uniformHitBeforeNs\":"<<hit_before<<",\"uniformHitAfterNs\":"<<hit_after<<",\"missBeforeNs\":"<<miss_before<<",\"missAfterNs\":"<<miss_after<<",\"firstSlotBeforeNs\":"<<first_before<<",\"firstSlotAfterNs\":"<<first_after<<",\"overlapPrefixHitBeforeNs\":"<<overlap_before<<",\"overlapPrefixHitAfterNs\":"<<overlap_after<<",\"allocationsFor1000PrefixHitsBefore\":"<<before_alloc<<",\"allocationsFor1000PrefixHitsAfter\":"<<after_alloc<<",\"allocatedBytesBefore\":"<<before_bytes<<",\"allocatedBytesAfter\":"<<after_bytes<<"}";
 }
 std::cout<<"]";rsx::tracing=rsx::count_visits=true;
}
int main(int argc,char**){const auto c=correctness();std::cout<<"{\"queries\":"<<c.queries<<",\"debugQueries\":"<<c.debug_queries<<",\"mutations\":"<<c.mutations<<",\"rangePredicateCallsBefore\":"<<c.range_before<<",\"rangePredicateCallsAfter\":"<<c.range_after<<",\"dirtyPredicateCallsBefore\":"<<c.predicates_before<<",\"dirtyPredicateCallsAfter\":"<<c.predicates_after<<",\"arrayAllocationsBefore\":"<<c.allocations_before<<",\"arrayAllocationsAfter\":"<<c.allocations_after<<",\"sameFirstMatch\":true,\"sameValidationOrder\":true,\"sameMergeOrder\":true,\"sameMutationState\":true,\"sameInvalidViewSelection\":true,\"confirmedRangeDebugCovered\":true,\"realStorageAndPitch\":true";if(argc>1)benchmark();std::cout<<"}\n";}
