#include <algorithm>
#include <array>
#include <cassert>
#include <concepts>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <iterator>
#include <memory>
#include <mutex>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <utility>
#include <vector>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using usz=std::size_t;
constexpr u32 umax=~u32{0};
template<class C>u32 size32(const C& c){return static_cast<u32>(c.size());}
template<class T>concept UnsignedInt=std::is_unsigned_v<T>;
#define ensure(x,...) assert(x)
#define AUDIT(x) assert(x)
namespace fmt {
template<class...T>std::string format(const char* f,T...v){int n=std::snprintf(nullptr,0,f,v...);std::vector<char>b(n+1);std::snprintf(b.data(),b.size(),f,v...);return std::string(b.data(),n);}
template<class...T>[[noreturn]]void throw_exception(const char*,T...){std::abort();}
}
namespace utils{constexpr u32 get_page_size(){return 4096;}}


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
using utils::address_range32;
namespace rsx {
template<class T>using reverse_pointer=std::reverse_iterator<T*>;
namespace aligned_allocator {
template<size_t>void* malloc(size_t n){return std::malloc(n);}
template<size_t>void* realloc(void* p,size_t,size_t n){return std::realloc(p,n);}
inline void free(void* p){std::free(p);}
}
}
#define RPCS3_IOS



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

#ifdef RPCS3_IOS
			if (_this_is_local != _that_is_local)
			{
				// Transfer the heap allocation instead of copying it into the
				// inline array (including moves into an empty destination).
				// Only the bounded inline payload needs to change address.
				auto& local = _this_is_local ? *this : that;
				auto& heap = _this_is_local ? that : *this;
				auto* heap_data = heap._data;
				const u32 heap_capacity = heap._capacity;
				const u32 heap_size = heap._size;
				if (local._size)
				{
					std::memcpy(heap._local_storage, local._data, local.size_bytes());
				}
				heap._data = reinterpret_cast<Ty*>(heap._local_storage);
				heap._capacity = _local_capacity;
				heap._size = local._size;
				local._data = heap_data;
				local._capacity = heap_capacity;
				local._size = heap_size;
				return;
			}
#endif

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
#undef RPCS3_IOS
struct image_section_attributes_t
	{
		u32 address;
		u32 gcm_format;
		u32 pitch;
		u16 width;
		u16 height;
		u16 depth;
		u16 mipmaps;
		u16 slice_h;
		u8  bpp;
		bool swizzled;
		bool edge_clamped;
	};
constexpr u32 CELL_GCM_TEXTURE_REMAP_ZERO=0,CELL_GCM_TEXTURE_REMAP_ONE=1,CELL_GCM_TEXTURE_REMAP_REMAP=2,RSX_TEXTURE_REMAP_IDENTITY=0xAAE4;
namespace rsx {struct texture_channel_remap_t
	{
		u32 encoded = 0xDEAD;
		std::array<u8, 4> control_map;
		std::array<u8, 4> channel_map;

 template<typename T>
std::array<T, 4> remap(const std::array<T, 4>& components, T select_zero, T select_one) const
		{
			ensure(encoded != 0xDEAD, "Channel remap was not initialized");

			std::array<T, 4> remapped{};
			for (u8 channel = 0; channel < 4; ++channel)
			{
				switch (control_map[channel])
				{
				default:
					[[fallthrough]];
				case CELL_GCM_TEXTURE_REMAP_REMAP:
					remapped[channel] = components[channel_map[channel]];
					break;
				case CELL_GCM_TEXTURE_REMAP_ZERO:
					remapped[channel] = select_zero;
					break;
				case CELL_GCM_TEXTURE_REMAP_ONE:
					remapped[channel] = select_one;
					break;
				}
			}
			return remapped;
		}
};

#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wmissing-field-initializers"
static inline texture_channel_remap_t decode_remap_encoding(u32 remap_ctl)
	{
		// Remapping tables; format is A-R-G-B
		// Remap input table. Contains channel index to read color from
		texture_channel_remap_t result =
		{
			.encoded = remap_ctl
		};

		result.channel_map =
		{
			static_cast<u8>(remap_ctl & 0x3),
			static_cast<u8>((remap_ctl >> 2) & 0x3),
			static_cast<u8>((remap_ctl >> 4) & 0x3),
			static_cast<u8>((remap_ctl >> 6) & 0x3),
		};

		// Remap control table. Controls whether the remap value is used, or force either 0 or 1
		result.control_map =
		{
			static_cast<u8>((remap_ctl >> 8) & 0x3),
			static_cast<u8>((remap_ctl >> 10) & 0x3),
			static_cast<u8>((remap_ctl >> 12) & 0x3),
			static_cast<u8>((remap_ctl >> 14) & 0x3),
		};

		return result;
	}
#pragma GCC diagnostic pop
}
using rsx::texture_channel_remap_t;
using VkDevice=int;using VkImage=u64;using VkFormat=u32;using VkComponentSwizzle=u32;using VkImageAspectFlags=u32;using VkImageViewType=u32;
constexpr u32 VK_COMPONENT_SWIZZLE_IDENTITY=0,VK_COMPONENT_SWIZZLE_ZERO=1,VK_COMPONENT_SWIZZLE_ONE=2,VK_COMPONENT_SWIZZLE_R=3,VK_COMPONENT_SWIZZLE_G=4,VK_COMPONENT_SWIZZLE_B=5,VK_COMPONENT_SWIZZLE_A=6;
constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT=1,VK_IMAGE_ASPECT_DEPTH_BIT=2,VK_IMAGE_VIEW_TYPE_MAX_ENUM=~0u;
struct VkComponentMapping{u32 r,g,b,a;bool operator==(const VkComponentMapping&)const=default;};
struct VkImageSubresourceRange{u32 aspectMask,baseMipLevel,levelCount,baseArrayLayer,layerCount;bool operator==(const VkImageSubresourceRange&)const=default;};
inline u64 constructed_views=0,destroyed_views=0;
namespace vk {
constexpr u32 VK_REMAP_IDENTITY=0xCAFEBABE;
struct command_buffer{};
struct image {
 u64 value=1;
 struct {u32 format=37,mipLevels=1,arrayLayers=1;} info;
 VkComponentMapping native_component_map{VK_COMPONENT_SWIZZLE_R,VK_COMPONENT_SWIZZLE_G,VK_COMPONENT_SWIZZLE_B,VK_COMPONENT_SWIZZLE_A};
 u32 aspect_mask=VK_IMAGE_ASPECT_COLOR_BIT;
 u32 aspect()const{return aspect_mask;}
 u32 format()const{return info.format;}
};
struct image_view {
 struct {VkImage image;VkFormat format;VkImageViewType viewType;VkComponentMapping components;VkImageSubresourceRange subresourceRange;} info;
 VkDevice m_device;vk::image* m_resource=nullptr;image_view* m_root_view=nullptr;
 std::unordered_map<VkFormat,std::unique_ptr<image_view>>m_subviews;
 image_view(VkDevice dev,vk::image* resource,VkFormat format,VkImageViewType type,VkComponentMapping mapping,VkImageSubresourceRange range):info{resource->value,format,type,mapping,range},m_device(dev),m_resource(resource){++constructed_views;}
 image_view(VkDevice dev,VkImage image,VkImageViewType type,VkFormat format,VkComponentMapping mapping,VkImageSubresourceRange range):info{image,format,type,mapping,range},m_device(dev){++constructed_views;}
 ~image_view(){++destroyed_views;}
 vk::image* image()const{return m_resource;}
 VkFormat format()const{return info.format;}
 image_view* as(VkFormat format);
};
struct viewable_image:image {
 std::unordered_map<u64,std::unique_ptr<image_view>> views;
 u64 m_last_view_key=0;image_view* m_last_view=nullptr;
 image_view* get_view(const texture_channel_remap_t&,VkImageAspectFlags=VK_IMAGE_ASPECT_COLOR_BIT|VK_IMAGE_ASPECT_DEPTH_BIT);
 void set_native_component_layout(VkComponentMapping);
};
inline int device=1;inline int* g_render_device=&device;
struct GC {template<class T>void dispose(std::unique_ptr<T>& p){p.reset();}};
inline GC* get_resource_manager(){static GC gc;return &gc;}
VkComponentMapping apply_swizzle_remap(const std::array<VkComponentSwizzle, 4>& base_remap, const rsx::texture_channel_remap_t& remap_vector)
	{
		const auto final_mapping = remap_vector.remap(base_remap, VK_COMPONENT_SWIZZLE_ZERO, VK_COMPONENT_SWIZZLE_ONE);
		return { final_mapping[1], final_mapping[2], final_mapping[3], final_mapping[0] };
	}
image_view* viewable_image::get_view(const rsx::texture_channel_remap_t& remap, VkImageAspectFlags mask)
	{
		u32 remap_encoding = remap.encoded;
		if (remap_encoding == VK_REMAP_IDENTITY)
		{
			if (native_component_map.a == VK_COMPONENT_SWIZZLE_A &&
				native_component_map.r == VK_COMPONENT_SWIZZLE_R &&
				native_component_map.g == VK_COMPONENT_SWIZZLE_G &&
				native_component_map.b == VK_COMPONENT_SWIZZLE_B)
			{
				remap_encoding = RSX_TEXTURE_REMAP_IDENTITY;
			}
		}

		const u64 storage_key = remap_encoding | (static_cast<u64>(mask) << 32);
		if (m_last_view && m_last_view_key == storage_key)
		{
			return m_last_view;
		}
		auto found = views.find(storage_key);
		if (found != views.end())
		{
			ensure(found->second->info.subresourceRange.aspectMask & mask);
			m_last_view_key = storage_key;
			return m_last_view = found->second.get();
		}

		VkComponentMapping real_mapping;
		switch (remap_encoding)
		{
		case VK_REMAP_IDENTITY:
			real_mapping = { VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_IDENTITY, VK_COMPONENT_SWIZZLE_IDENTITY };
			break;
		case RSX_TEXTURE_REMAP_IDENTITY:
			real_mapping = native_component_map;
			break;
		default:
			real_mapping = vk::apply_swizzle_remap
			(
				{ native_component_map.a, native_component_map.r, native_component_map.g, native_component_map.b },
				remap
			);
			break;
		}

		const VkImageSubresourceRange range = { aspect() & mask, 0, info.mipLevels, 0, info.arrayLayers };
		ensure(range.aspectMask);

		auto view = std::make_unique<vk::image_view>(*g_render_device, this, format(), VK_IMAGE_VIEW_TYPE_MAX_ENUM, real_mapping, range);
		auto result = view.get();
		views.emplace(storage_key, std::move(view));
		m_last_view_key = storage_key;
		return m_last_view = result;
	}
image_view* image_view::as(VkFormat format)
	{
		if (this->format() == format)
		{
			return this;
		}

		auto self = this->m_root_view
			? this->m_root_view
			: this;

		if (auto found = self->m_subviews.find(format);
			found != self->m_subviews.end())
		{
			return found->second.get();
		}

		// Create a derived
		auto view = std::make_unique<image_view>(m_device, info.image, info.viewType, format, info.components, info.subresourceRange);
		view->m_resource = self->m_resource;
		view->m_root_view = self;

		auto ret = view.get();
		self->m_subviews.emplace(format, std::move(view));
		return ret;
	}
void viewable_image::set_native_component_layout(VkComponentMapping new_layout)
	{
		if (new_layout.r != native_component_map.r ||
			new_layout.g != native_component_map.g ||
			new_layout.b != native_component_map.b ||
			new_layout.a != native_component_map.a)
		{
			native_component_map = new_layout;
			m_last_view = nullptr;

			// Safely discard existing views
			auto gc = vk::get_resource_manager();
			for (auto& p : views)
			{
				gc->dispose(p.second);
			}
			views.clear();
		}
	}
}
enum class deferred_request_command:u32{nop,copy_image_static,copy_image_dynamic,cubemap_gather,cubemap_unwrap,atlas_gather,_3d_gather,_3d_unwrap,mipmap_gather,blit_image_static};
struct copy_region_descriptor{void*src;u32 xform,base_addr;u8 level;u16 src_x,src_y,dst_x,dst_y,dst_z,src_w,src_h,dst_w,dst_h;};
using image_resource_type=vk::image*;using image_view_type=vk::image_view*;using commandbuffer_type=vk::command_buffer;
struct deferred_subresource : image_section_attributes_t
		{
			image_resource_type external_handle = 0;
			rsx::simple_array<copy_region_descriptor> sections_to_copy;
			texture_channel_remap_t remap;
			deferred_request_command op = deferred_request_command::nop;
			u32 external_ref_addr = 0;

			utils::address_range32 cache_range;
			bool do_not_cache = false;
			bool force_bg_load = false;

			using section_array_type = rsx::simple_array<copy_region_descriptor>;

u64 encoded_properties() const
			{
				return (static_cast<u64>(width)) |
					(static_cast<u64>(height) << 16) |
					((static_cast<u64>(depth) & 0x7ff) << 32) |
					((static_cast<u64>(mipmaps) & 0x1f) << 43) |
					((static_cast<u64>(gcm_format) & 0xff) << 48) |
					((static_cast<u64>(op) & 0x1f) << 56);
			}
};
struct Boundary {
 std::mutex m_cache_mutex;
 std::vector<image_view_type>m_uncached_subresources;
 std::unordered_map<vk::image*,std::unique_ptr<vk::viewable_image>>owned;
 std::vector<std::unique_ptr<vk::viewable_image>>pool;
 u64 allocations=0,releases=0,updates=0,copies=0;bool fail=false;u32 aspects=VK_IMAGE_ASPECT_COLOR_BIT;
 VkComponentMapping native{VK_COMPONENT_SWIZZLE_R,VK_COMPONENT_SWIZZLE_G,VK_COMPONENT_SWIZZLE_B,VK_COMPONENT_SWIZZLE_A};
 image_view_type create(commandbuffer_type&,const deferred_subresource& desc){
  if(fail)return nullptr;
  auto image=pool.empty()?std::make_unique<vk::viewable_image>():std::move(pool.back());if(!pool.empty())pool.pop_back();
  image->aspect_mask=aspects;image->info.mipLevels=desc.mipmaps;image->info.arrayLayers=desc.depth;image->set_native_component_layout(native);
  auto* result=image->get_view(desc.remap);auto* key=image.get();owned.emplace(key,std::move(image));++allocations;++copies;return result;
 }
 void update_image_contents(commandbuffer_type&,image_view_type view,const deferred_subresource&){assert(owned.contains(view->image()));++updates;++copies;}
 void release_temporary_subresource(image_view_type view){auto it=owned.find(view->image());assert(it!=owned.end());pool.push_back(std::move(it->second));owned.erase(it);++releases;}
 image_view_type generate_cubemap_from_images(commandbuffer_type& c,const deferred_subresource& d){return create(c,d);}
 image_view_type generate_3d_from_2d_images(commandbuffer_type& c,const deferred_subresource& d){return create(c,d);}
 image_view_type generate_atlas_from_images(commandbuffer_type& c,const deferred_subresource& d){return create(c,d);}
 image_view_type create_temporary_subresource_view(commandbuffer_type& c,const deferred_subresource& d){return create(c,d);}
 image_view_type generate_2d_mipmaps_from_images(commandbuffer_type& c,const deferred_subresource& d){return create(c,d);}
 void expand_cube_unwrap_sections(rsx::simple_array<copy_region_descriptor>& out,const deferred_subresource& d){out=d.sections_to_copy;}
 void expand_3d_unwrap_sections(rsx::simple_array<copy_region_descriptor>& out,const deferred_subresource& d,int){out=d.sections_to_copy;}
};
struct CommonCache:Boundary {
 struct temporary_subresource_key
		{
			u64 properties;
			address_range32 cache_range;

			temporary_subresource_key(const deferred_subresource& desc)
				: properties(desc.encoded_properties()), cache_range(desc.cache_range) {}

			u64 encoded_properties() const { return properties; }
		};
 std::unordered_multimap<u32,std::pair<temporary_subresource_key,image_view_type>>m_temporary_subresource_cache;
 image_view_type create_temporary_subresource(commandbuffer_type &cmd, deferred_subresource& desc)
		{
			if (!desc.do_not_cache) [[likely]]
			{
				const auto desc_key = desc.encoded_properties();
				const auto found = m_temporary_subresource_cache.equal_range(desc.address);
				for (auto It = found.first; It != found.second; ++It)
				{
					if (It->second.first.encoded_properties() != desc_key)
						continue;

					if (desc.op == deferred_request_command::copy_image_dynamic)
						update_image_contents(cmd, It->second.second, desc);

					return It->second.second;
				}
			}

			std::lock_guard lock(m_cache_mutex);
			image_view_type result = 0;

			switch (desc.op)
			{
			case deferred_request_command::cubemap_gather:
			{
				result = generate_cubemap_from_images(cmd, desc);
				break;
			}
			case deferred_request_command::cubemap_unwrap:
			{
				rsx::simple_array<copy_region_descriptor> sections;
				expand_cube_unwrap_sections(sections, desc);

				auto unwrap_desc = desc;
				unwrap_desc.op = deferred_request_command::cubemap_gather;
				unwrap_desc.sections_to_copy = std::move(sections);

				result = generate_cubemap_from_images(cmd, unwrap_desc);
				break;
			}
			case deferred_request_command::_3d_gather:
			{
				result = generate_3d_from_2d_images(cmd, desc);
				break;
			}
			case deferred_request_command::_3d_unwrap:
			{
				rsx::simple_array<copy_region_descriptor> sections;
				expand_3d_unwrap_sections(sections, desc, 0);

				auto unwrap_desc = desc;
				unwrap_desc.op = deferred_request_command::_3d_gather;
				unwrap_desc.sections_to_copy = std::move(sections);

				result = generate_3d_from_2d_images(cmd, unwrap_desc);
				break;
			}
			case deferred_request_command::atlas_gather:
			case deferred_request_command::blit_image_static:
			{
				result = generate_atlas_from_images(cmd, desc);
				break;
			}
			case deferred_request_command::copy_image_static:
			case deferred_request_command::copy_image_dynamic:
			{
				result = create_temporary_subresource_view(cmd, desc);
				break;
			}
			case deferred_request_command::mipmap_gather:
			{
				result = generate_2d_mipmaps_from_images(cmd, desc);
				break;
			}
			default:
			{
				//Throw
				fmt::throw_exception("Invalid deferred command op 0x%X", static_cast<u32>(desc.op));
			}
			}

			if (result) [[likely]]
			{
				if (!desc.do_not_cache) [[likely]]
				{
					m_temporary_subresource_cache.insert({ desc.address,{ desc, result } });
				}
				else
				{
					m_uncached_subresources.push_back(result);
				}
			}

			return result;
		}
 void notify_surface_changed(const utils::address_range32& range)
		{
			for (auto It = m_temporary_subresource_cache.begin(); It != m_temporary_subresource_cache.end();)
			{
				const auto& desc = It->second.first;
				if (range.overlaps(desc.cache_range))
				{
					release_temporary_subresource(It->second.second);
					It = m_temporary_subresource_cache.erase(It);
				}
				else
				{
					++It;
				}
			}
		}
 void release_uncached_temporary_subresources()
		{
			for (auto& view : m_uncached_subresources)
			{
				release_temporary_subresource(view);
			}

			m_uncached_subresources.clear();
		}
 void clear() {for (auto& entry : m_temporary_subresource_cache)
			{
				release_temporary_subresource(entry.second.second);
			}

			m_temporary_subresource_cache.clear();
			
 release_uncached_temporary_subresources(); }
 ~CommonCache(){clear();assert(owned.empty());assert(allocations==releases);}
};
namespace vk {
class texture_cache:public CommonCache {
 using baseclass=CommonCache;
public:
 image_view* create_temporary_subresource(command_buffer&,deferred_subresource&);
};
vk::image_view* texture_cache::create_temporary_subresource(vk::command_buffer& cmd, deferred_subresource& desc)
	{
		auto cached = baseclass::create_temporary_subresource(cmd, desc);
		if (!cached)
		{
			return nullptr;
		}

		// The common cache keys image contents, not sampler channel remapping.
		// Reuse that image but select the current request's view on every hit.
		// get_view has a last-view fast path; as returns directly for its format.
		return static_cast<vk::viewable_image*>(cached->image())->get_view(desc.remap)->as(cached->format());
	}
}
VkComponentMapping expected(const texture_channel_remap_t& r,VkComponentMapping native){
 // Independent scalar oracle in ARGB order; never calls production remap().
 std::array<u32,4>input{native.a,native.r,native.g,native.b},output{};
 for(u32 i=0;i<4;++i)output[i]=r.control_map[i]==0?VK_COMPONENT_SWIZZLE_ZERO:r.control_map[i]==1?VK_COMPONENT_SWIZZLE_ONE:input[r.channel_map[i]];
 return {output[1],output[2],output[3],output[0]};
}
u64 checks=0,baseline_wrong=0,remaps=0;
int main(){
 commandbuffer_type cmd;
 for(u32 aspect:{VK_IMAGE_ASPECT_COLOR_BIT,VK_IMAGE_ASPECT_DEPTH_BIT})for(u32 op=1;op<=9;++op){
  CommonCache old;vk::texture_cache now;old.aspects=now.aspects=aspect;
  deferred_subresource d{};d.address=0x100000;d.cache_range=address_range32::start_length(d.address,4096);d.width=32;d.height=32;d.depth=op==3?6:1;d.mipmaps=3;d.gcm_format=0x85;d.op=static_cast<deferred_request_command>(op);d.remap=rsx::decode_remap_encoding(RSX_TEXTURE_REMAP_IDENTITY);
  auto* a=old.create_temporary_subresource(cmd,d);auto* b=now.create_temporary_subresource(cmd,d);auto* owner=b->image();
  for(u32 controls=0;controls<81;++controls)for(u32 channels=0;channels<256;++channels){
   u32 packed=0,t=controls;for(u32 n=0;n<4;++n){packed|=(t%3)<<(8+n*2);t/=3;}
   d.remap=rsx::decode_remap_encoding(packed|channels);
   a=old.create_temporary_subresource(cmd,d);b=now.create_temporary_subresource(cmd,d);
   auto oracle=expected(d.remap,b->image()->native_component_map);
   baseline_wrong+=a->info.components!=oracle;
   assert(b->info.components==oracle&&b->image()==owner);assert(b->info.subresourceRange.aspectMask==aspect&&b->info.subresourceRange.levelCount==3&&b->info.subresourceRange.layerCount==d.depth);
   auto views=constructed_views;assert(now.create_temporary_subresource(cmd,d)==b&&constructed_views==views);old.create_temporary_subresource(cmd,d);
   assert(old.allocations==1&&now.allocations==1&&old.copies==now.copies);++checks;++remaps;
  }
  assert(now.updates==(op==2?20736u*2:0));
  old.notify_surface_changed(address_range32::start_length(d.address+128,32));now.notify_surface_changed(address_range32::start_length(d.address+128,32));
  assert(old.owned.empty()&&now.owned.empty()&&old.releases==1&&now.releases==1);++checks;
 }
 {
  vk::texture_cache cache;deferred_subresource d{};d.address=0x800000;d.width=4;d.height=4;d.depth=1;d.mipmaps=1;d.gcm_format=0x85;d.op=deferred_request_command::copy_image_dynamic;d.remap=rsx::decode_remap_encoding(RSX_TEXTURE_REMAP_IDENTITY);d.cache_range=address_range32::start_length(d.address,128);
  auto* first=cache.create_temporary_subresource(cmd,d);auto* owner=first->image();
  // An existing format subview must retain that format while its new component
  // view is selected; one owned image and the existing as() subview cache suffice.
  cache.m_temporary_subresource_cache.begin()->second.second=first->as(72);
  for(u32 bits:{0xAAE4u,0xAA1Bu,0u,0x5555u,0xAAE4u}){
   d.remap=rsx::decode_remap_encoding(bits);auto* view=cache.create_temporary_subresource(cmd,d);assert(view->format()==72&&view->image()==owner&&view->info.components==expected(d.remap,owner->native_component_map));
   auto views=constructed_views;assert(cache.create_temporary_subresource(cmd,d)==view&&constructed_views==views);++checks;
  }
  assert(cache.allocations==1&&cache.updates==10&&cache.copies==11);
  cache.clear();assert(cache.releases==1&&cache.owned.empty());
  cache.native={VK_COMPONENT_SWIZZLE_A,VK_COMPONENT_SWIZZLE_B,VK_COMPONENT_SWIZZLE_G,VK_COMPONENT_SWIZZLE_R};
  auto* recycled=cache.create_temporary_subresource(cmd,d);assert(recycled->image()==owner&&recycled->info.components==expected(d.remap,cache.native));++checks;
  cache.clear();assert(cache.releases==2&&cache.owned.empty());
  d.do_not_cache=true;
  for(u32 bits:{0xAAE4u,0xAA1Bu,0u,0x5555u}){d.remap=rsx::decode_remap_encoding(bits);auto* view=cache.create_temporary_subresource(cmd,d);assert(view&&view->info.components==expected(d.remap,view->image()->native_component_map));++checks;}
  assert(cache.m_temporary_subresource_cache.empty()&&cache.m_uncached_subresources.size()==4);
  cache.clear();assert(cache.allocations==cache.releases);
  cache.fail=true;assert(!cache.create_temporary_subresource(cmd,d));++checks;
 }
 assert(constructed_views==destroyed_views&&baseline_wrong>0);
 std::cout<<"{\"checks\":"<<checks<<",\"remapRequests\":"<<remaps<<",\"baselineWrongMappings\":"<<baseline_wrong<<",\"candidateWrongMappings\":0,\"sameImageAllocationsAndPayloadCopies\":true,\"repeatViewAllocations\":0,\"formatAndSubresourcesPreserved\":true,\"poolNativeMappingRefresh\":true,\"viewsConstructed\":"<<constructed_views<<",\"viewsDestroyed\":"<<destroyed_views<<",\"invalidationAndFrameReleaseOnce\":true}";
}
