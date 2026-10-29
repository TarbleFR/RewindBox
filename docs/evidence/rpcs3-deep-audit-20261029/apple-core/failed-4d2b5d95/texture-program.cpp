#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <concepts>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <iterator>
#include <list>
#include <memory>
#include <new>
#include <string>
#include <type_traits>
#include <unordered_map>
#include <unordered_set>
#include <utility>
#include <vector>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;using usz=std::size_t;
#define ensure(x,...) assert(x)
#define AUDIT(x) assert(x)
template<class C>u32 size32(const C& c){return static_cast<u32>(c.size());}
template<class T>concept UnsignedInt=std::is_unsigned_v<T>;
namespace fmt {template<class...T>[[noreturn]]void throw_exception(const char*,T...){std::abort();}}
inline bool count_allocations=false;inline u64 allocation_calls=0;
[[gnu::noinline]] void* operator new(std::size_t n){if(count_allocations)++allocation_calls;if(void* p=std::malloc(n?n:1))return p;throw std::bad_alloc();}
[[gnu::noinline]] void operator delete(void* p) noexcept {std::free(p);}
[[gnu::noinline]] void operator delete(void* p,std::size_t) noexcept {std::free(p);}
constexpr u32 CELL_GCM_TEXTURE_REMAP_ZERO=0,CELL_GCM_TEXTURE_REMAP_ONE=1,CELL_GCM_TEXTURE_REMAP_REMAP=2,RSX_TEXTURE_REMAP_IDENTITY=0xAAE4;
enum CellGcmTexture : u32
	{
		// Color Flag
		CELL_GCM_TEXTURE_B8 = 0x81,
		CELL_GCM_TEXTURE_A1R5G5B5 = 0x82,
		CELL_GCM_TEXTURE_A4R4G4B4 = 0x83,
		CELL_GCM_TEXTURE_R5G6B5 = 0x84,
		CELL_GCM_TEXTURE_A8R8G8B8 = 0x85,
		CELL_GCM_TEXTURE_COMPRESSED_DXT1 = 0x86,
		CELL_GCM_TEXTURE_COMPRESSED_DXT23 = 0x87,
		CELL_GCM_TEXTURE_COMPRESSED_DXT45 = 0x88,
		CELL_GCM_TEXTURE_G8B8 = 0x8B,
		CELL_GCM_TEXTURE_COMPRESSED_B8R8_G8R8 = 0x8D, // NOTE: 0xAD in firmware
		CELL_GCM_TEXTURE_COMPRESSED_R8B8_R8G8 = 0x8E, // NOTE: 0xAE in firmware
		CELL_GCM_TEXTURE_R6G5B5 = 0x8F,
		CELL_GCM_TEXTURE_DEPTH24_D8 = 0x90,
		CELL_GCM_TEXTURE_DEPTH24_D8_FLOAT = 0x91,
		CELL_GCM_TEXTURE_DEPTH16 = 0x92,
		CELL_GCM_TEXTURE_DEPTH16_FLOAT = 0x93,
		CELL_GCM_TEXTURE_X16 = 0x94,
		CELL_GCM_TEXTURE_Y16_X16 = 0x95,
		CELL_GCM_TEXTURE_R5G5B5A1 = 0x97,
		CELL_GCM_TEXTURE_COMPRESSED_HILO8 = 0x98,
		CELL_GCM_TEXTURE_COMPRESSED_HILO_S8 = 0x99,
		CELL_GCM_TEXTURE_W16_Z16_Y16_X16_FLOAT = 0x9A,
		CELL_GCM_TEXTURE_W32_Z32_Y32_X32_FLOAT = 0x9B,
		CELL_GCM_TEXTURE_X32_FLOAT = 0x9C,
		CELL_GCM_TEXTURE_D1R5G5B5 = 0x9D,
		CELL_GCM_TEXTURE_D8R8G8B8 = 0x9E,
		CELL_GCM_TEXTURE_Y16_X16_FLOAT = 0x9F,

		// Swizzle Flag
		CELL_GCM_TEXTURE_SZ = 0x00,
		CELL_GCM_TEXTURE_LN = 0x20,

		// Normalization Flag
		CELL_GCM_TEXTURE_NR = 0x00,
		CELL_GCM_TEXTURE_UN = 0x40,
	};
enum : u32 {
		CELL_GCM_SURFACE_Z16 = 1,
		CELL_GCM_SURFACE_Z24S8 = 2,
};
namespace rsx {
template<class T>using reverse_pointer=std::reverse_iterator<T*>;
namespace aligned_allocator {
template<size_t>void* malloc(size_t n){if(count_allocations)++allocation_calls;return std::malloc(n);}
template<size_t>void* realloc(void* p,size_t,size_t n){if(count_allocations)++allocation_calls;return std::realloc(p,n);}
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
namespace rsx {
enum class surface_depth_format : u8
	{
		z16 = CELL_GCM_SURFACE_Z16,     // typeless 16 bits depth
		z24s8 = CELL_GCM_SURFACE_Z24S8, // typeless 24 bits depth + 8 bits stencil
	};
enum class surface_depth_format2 : u8
	{
		z16_uint = CELL_GCM_SURFACE_Z16,      // unsigned 16 bits depth
		z24s8_uint = CELL_GCM_SURFACE_Z24S8,  // unsigned 24 bits depth + 8 bits stencil
		z16_float,   // floating point 16 bits depth
		z24s8_float, // floating point 24 bits depth + 8 bits stencil
	};
constexpr bool operator ==(surface_depth_format2 rhs, surface_depth_format lhs)
	{
		switch (lhs)
		{
		case surface_depth_format::z16:
			return (rhs == surface_depth_format2::z16_uint || rhs == surface_depth_format2::z16_float);
		case surface_depth_format::z24s8:
			return (rhs == surface_depth_format2::z24s8_uint || rhs == surface_depth_format2::z24s8_float);
		[[unlikely]] default:
			return false;
		}
	}
enum format_class : u8
		{
			RSX_FORMAT_CLASS_UNDEFINED = 0,
			RSX_FORMAT_CLASS_COLOR = 1,
			RSX_FORMAT_CLASS_DEPTH16_UNORM = 2,
			RSX_FORMAT_CLASS_DEPTH16_FLOAT = 4,
			RSX_FORMAT_CLASS_DEPTH24_UNORM_X8_PACK32 = 8,
			RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32 = 16,

			RSX_FORMAT_CLASS_DEPTH_FLOAT_MASK = (RSX_FORMAT_CLASS_DEPTH16_FLOAT | RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32),
			RSX_FORMAT_CLASS_DONT_CARE = RSX_FORMAT_CLASS_UNDEFINED,
		};
enum class component_order
	{
		default_ = 0,
		native = 1,
		swapped_native = 2,
	};
struct texture_channel_remap_t
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

inline auto default_remap_vector=decode_remap_encoding(RSX_TEXTURE_REMAP_IDENTITY);
rsx::format_class classify_format(u32 gcm_format)
	{
		switch (gcm_format)
		{
		case CELL_GCM_TEXTURE_DEPTH16:
			return RSX_FORMAT_CLASS_DEPTH16_UNORM;
		case CELL_GCM_TEXTURE_DEPTH16_FLOAT:
			return RSX_FORMAT_CLASS_DEPTH16_FLOAT;
		case CELL_GCM_TEXTURE_DEPTH24_D8:
			return RSX_FORMAT_CLASS_DEPTH24_UNORM_X8_PACK32;
		case CELL_GCM_TEXTURE_DEPTH24_D8_FLOAT:
			return RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32;
		default:
			return RSX_FORMAT_CLASS_COLOR;
		}
	}
std::pair<u32, bool> get_compatible_gcm_format(rsx::surface_depth_format2 format)
	{
		switch (format)
		{
		case rsx::surface_depth_format2::z16_uint:
			return{ CELL_GCM_TEXTURE_DEPTH16, true };
		case rsx::surface_depth_format2::z24s8_uint:
			return{ CELL_GCM_TEXTURE_DEPTH24_D8, true };
		case rsx::surface_depth_format2::z16_float:
			return{ CELL_GCM_TEXTURE_DEPTH16_FLOAT, true };
		case rsx::surface_depth_format2::z24s8_float:
			return{ CELL_GCM_TEXTURE_DEPTH24_D8_FLOAT, true };
		default:
			fmt::throw_exception("Unreachable");
		}
	}
}
using namespace rsx;
using VkDevice=int;using VkImage=u64;using VkFormat=u32;using VkComponentSwizzle=u32;using VkImageAspectFlags=u32;using VkImageViewType=u32;using VkImageType=u32;using VkImageCreateFlags=u32;using VkImageUsageFlags=u32;using VkSharingMode=u32;using VkFlags=u32;
constexpr u32 VK_COMPONENT_SWIZZLE_IDENTITY=0,VK_COMPONENT_SWIZZLE_ZERO=1,VK_COMPONENT_SWIZZLE_ONE=2,VK_COMPONENT_SWIZZLE_R=3,VK_COMPONENT_SWIZZLE_G=4,VK_COMPONENT_SWIZZLE_B=5,VK_COMPONENT_SWIZZLE_A=6;
constexpr u32 VK_IMAGE_ASPECT_COLOR_BIT=1,VK_IMAGE_ASPECT_DEPTH_BIT=2,VK_IMAGE_VIEW_TYPE_MAX_ENUM=~0u,VK_IMAGE_LAYOUT_GENERAL=1,VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL=2,VK_IMAGE_TYPE_2D=1,VK_IMAGE_TYPE_3D=2;
constexpr u32 VK_IMAGE_USAGE_TRANSFER_SRC_BIT=1,VK_IMAGE_USAGE_TRANSFER_DST_BIT=2,VK_IMAGE_USAGE_SAMPLED_BIT=4,VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT=1,VK_SAMPLE_COUNT_1_BIT=1,VK_IMAGE_LAYOUT_UNDEFINED=0,VK_IMAGE_TILING_OPTIMAL=0,VMM_ALLOCATION_POOL_TEXTURE_CACHE=0,VK_IMAGE_CREATE_ALLOW_NULL_RPCS3=0x80000000,VK_SHARING_MODE_EXCLUSIVE=0;
struct VkComponentMapping{u32 r,g,b,a;bool operator==(const VkComponentMapping&)const=default;};
struct VkImageSubresourceRange{u32 aspectMask,baseMipLevel,levelCount,baseArrayLayer,layerCount;bool operator==(const VkImageSubresourceRange&)const=default;};
inline u64 constructed_views=0,destroyed_views=0;
namespace vk {
constexpr u32 VK_REMAP_IDENTITY=0xCAFEBABE;
struct command_buffer{u64 pushes=0,pops=0,copies=0,push_digest=0,copy_digest=0;};
struct memory_block {u64 size()const{return 4096;}};
struct image {
 u64 value=1;
 struct {u32 format=37,mipLevels=1,arrayLayers=1,width=512,height=512,depth=1,imageType=2,flags=0,sharingMode=0,usage=3;} info;
 VkComponentMapping native_component_map{VK_COMPONENT_SWIZZLE_R,VK_COMPONENT_SWIZZLE_G,VK_COMPONENT_SWIZZLE_B,VK_COMPONENT_SWIZZLE_A};
 u32 aspect_mask=VK_IMAGE_ASPECT_COLOR_BIT;
 u32 aspect()const{return aspect_mask;}u32 format()const{return info.format;}
 u32 width()const{return info.width;}u32 height()const{return info.height;}
 u32 depth()const{return info.depth;}u32 mipmaps()const{return info.mipLevels;}
 u32 type()const{return info.imageType;}u32 layers()const{return info.arrayLayers;}
 rsx::format_class image_class=RSX_FORMAT_CLASS_COLOR;
 rsx::format_class format_class()const{return image_class;}
 std::unique_ptr<memory_block>memory=std::make_unique<memory_block>();
 u32 identity=0,current_layout=3,saved_layout=0,push_count=0,pop_count=0,copy_count=0;
 void push_layout(command_buffer& cmd,u32 layout){assert(!saved_layout);saved_layout=current_layout;current_layout=layout;++push_count;++cmd.pushes;cmd.push_digest=cmd.push_digest*31+identity;}
 void pop_layout(command_buffer& cmd){assert(saved_layout);current_layout=saved_layout;saved_layout=0;++pop_count;++cmd.pops;}
 void copy(command_buffer& cmd){assert(saved_layout&&current_layout==(saved_layout==VK_IMAGE_LAYOUT_GENERAL?VK_IMAGE_LAYOUT_GENERAL:VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL));++copy_count;++cmd.copies;cmd.copy_digest=cmd.copy_digest*31+identity;}
};
struct image_view {
 struct {VkImage image;VkFormat format;VkImageViewType viewType;VkComponentMapping components;VkImageSubresourceRange subresourceRange;} info;
 VkDevice m_device;vk::image* m_resource=nullptr;image_view* m_root_view=nullptr;
 std::unordered_map<VkFormat,std::unique_ptr<image_view>>m_subviews;
 image_view(VkDevice dev,vk::image* resource,VkFormat format,VkImageViewType type,VkComponentMapping mapping,VkImageSubresourceRange range):info{resource->value,format,type,mapping,range},m_device(dev),m_resource(resource){++constructed_views;}
 image_view(VkDevice dev,VkImage image,VkImageViewType type,VkFormat format,VkComponentMapping mapping,VkImageSubresourceRange range):info{image,format,type,mapping,range},m_device(dev){++constructed_views;}
 ~image_view(){++destroyed_views;}
 vk::image* image()const{return m_resource;}VkFormat format()const{return info.format;}
 image_view* as(VkFormat format);
};
struct viewable_image:image {
 viewable_image()=default;
 viewable_image(int,int,u32,u32 type,u32 format,u32 w,u32 h,u32 d,u32 m,u32 layers,u32,u32,u32,u32 usage,u32 flags,u32,rsx::format_class c){info.imageType=type;info.format=format;info.width=w;info.height=h;info.depth=d;info.mipLevels=m;info.arrayLayers=layers;info.usage=usage;info.flags=flags&~VK_IMAGE_CREATE_ALLOW_NULL_RPCS3;image_class=c;}
 std::unordered_map<u64,std::unique_ptr<image_view>> views;
 u64 m_last_view_key=0;image_view* m_last_view=nullptr;
 image_view* get_view(const texture_channel_remap_t&,VkImageAspectFlags=VK_IMAGE_ASPECT_COLOR_BIT|VK_IMAGE_ASPECT_DEPTH_BIT);
 void set_native_component_layout(VkComponentMapping);
};
inline int device=1;inline int* g_render_device=&device;
inline int* get_current_renderer(){return g_render_device;}
struct GC {std::vector<std::unique_ptr<image_view>>retired;void dispose(std::unique_ptr<image_view>& p){retired.push_back(std::move(p));}};
inline GC* get_resource_manager(){static GC gc;return &gc;}
std::array<VkComponentSwizzle, 4> get_component_mapping(u32 format)
	{
		//Component map in ARGB format
		std::array<VkComponentSwizzle, 4> mapping = {};

		switch (format)
		{
		case CELL_GCM_TEXTURE_A1R5G5B5:
		case CELL_GCM_TEXTURE_R5G5B5A1:
		case CELL_GCM_TEXTURE_R6G5B5:
		case CELL_GCM_TEXTURE_R5G6B5:
		case CELL_GCM_TEXTURE_COMPRESSED_DXT1:
		case CELL_GCM_TEXTURE_COMPRESSED_DXT23:
		case CELL_GCM_TEXTURE_COMPRESSED_DXT45:
			mapping = { VK_COMPONENT_SWIZZLE_A, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_B }; break;

		case CELL_GCM_TEXTURE_DEPTH24_D8:
		case CELL_GCM_TEXTURE_DEPTH24_D8_FLOAT:
		case CELL_GCM_TEXTURE_DEPTH16:
		case CELL_GCM_TEXTURE_DEPTH16_FLOAT:
			mapping = { VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R }; break;

		case CELL_GCM_TEXTURE_A4R4G4B4:
			mapping = { VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_B, VK_COMPONENT_SWIZZLE_A }; break;

		case CELL_GCM_TEXTURE_G8B8:
			mapping = { VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_R }; break;

		case CELL_GCM_TEXTURE_B8:
			mapping = { VK_COMPONENT_SWIZZLE_ONE, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R }; break;

		case CELL_GCM_TEXTURE_X16:
			mapping = { VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_ONE, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_ONE }; break;

		case CELL_GCM_TEXTURE_X32_FLOAT:
			mapping = { VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R }; break;

		case CELL_GCM_TEXTURE_Y16_X16:
			mapping = { VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_R }; break;

		case CELL_GCM_TEXTURE_Y16_X16_FLOAT:
			mapping = { VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G }; break;

		case CELL_GCM_TEXTURE_W16_Z16_Y16_X16_FLOAT:
		case CELL_GCM_TEXTURE_W32_Z32_Y32_X32_FLOAT:
			mapping = { VK_COMPONENT_SWIZZLE_A, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_B }; break;

		case CELL_GCM_TEXTURE_D8R8G8B8:
			mapping = { VK_COMPONENT_SWIZZLE_ONE, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_B }; break;

		case CELL_GCM_TEXTURE_D1R5G5B5:
			mapping = { VK_COMPONENT_SWIZZLE_ONE, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_B }; break;

		case CELL_GCM_TEXTURE_COMPRESSED_HILO8:
		case CELL_GCM_TEXTURE_COMPRESSED_HILO_S8:
			mapping = { VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G }; break;

		case CELL_GCM_TEXTURE_COMPRESSED_B8R8_G8R8:
		case CELL_GCM_TEXTURE_COMPRESSED_R8B8_R8G8:
			mapping = { VK_COMPONENT_SWIZZLE_A, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_B }; break;

		case CELL_GCM_TEXTURE_A8R8G8B8:
			mapping = { VK_COMPONENT_SWIZZLE_A, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_B }; break;

		default:
			fmt::throw_exception("Invalid or unsupported component mapping for texture format (0x%x)", format);
		}

		return mapping;
	}
VkComponentMapping apply_swizzle_remap(const std::array<VkComponentSwizzle, 4>& base_remap, const rsx::texture_channel_remap_t& remap_vector)
	{
		const auto final_mapping = remap_vector.remap(base_remap, VK_COMPONENT_SWIZZLE_ZERO, VK_COMPONENT_SWIZZLE_ONE);
		return { final_mapping[1], final_mapping[2], final_mapping[3], final_mapping[0] };
	}
VkComponentMapping apply_component_mapping_flags(u32 gcm_format, rsx::component_order flags, const rsx::texture_channel_remap_t& remap_vector)
	{
		switch (gcm_format)
		{
		case CELL_GCM_TEXTURE_DEPTH24_D8:
		case CELL_GCM_TEXTURE_DEPTH24_D8_FLOAT:
		case CELL_GCM_TEXTURE_DEPTH16:
		case CELL_GCM_TEXTURE_DEPTH16_FLOAT:
			// Dont bother letting this propagate
			return{ VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_R };
		default:
			break;
		}

		VkComponentMapping mapping = {};
		switch (flags)
		{
		case rsx::component_order::default_:
		{
			mapping = vk::apply_swizzle_remap(vk::get_component_mapping(gcm_format), remap_vector);
			break;
		}
		case rsx::component_order::native:
		{
			mapping = { VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_B, VK_COMPONENT_SWIZZLE_A };
			break;
		}
		case rsx::component_order::swapped_native:
		{
			mapping = { VK_COMPONENT_SWIZZLE_A, VK_COMPONENT_SWIZZLE_R, VK_COMPONENT_SWIZZLE_G, VK_COMPONENT_SWIZZLE_B };
			break;
		}
		default:
			break;
		}

		return mapping;
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
u64 hash_image_properties(VkFormat format, u16 w, u16 h, u16 d, u16 mipmaps, VkImageType type, VkImageCreateFlags create_flags, VkSharingMode sharing_mode)
	{
		/**
		* Key layout:
		* 00-08: Format  (Max 255)
		* 08-24: Width   (Max 64K)
		* 24-40: Height  (Max 64K)
		* 40-48: Depth   (Max 255)
		* 48-54: Mipmaps (Max 63)   <- We have some room here, it is not possible to have more than 12 mip levels on PS3 and 16 on PC is pushing it.
		* 54-56: Type    (Max 3)
		* 56-57: Sharing (Max 1)    <- Boolean. Exclusive = 0, shared = 1
		* 57-64: Flags   (Max 127)  <- We have some room here, we only care about a small subset of create flags.
		*/
		ensure(static_cast<u32>(format) < 0xFF);
		return (static_cast<u64>(format) & 0xFF) |
			(static_cast<u64>(w) << 8) |
			(static_cast<u64>(h) << 24) |
			(static_cast<u64>(d) << 40) |
			(static_cast<u64>(mipmaps) << 48) |
			(static_cast<u64>(type) << 54) |
			(static_cast<u64>(sharing_mode) << 56) |
			(static_cast<u64>(create_flags) << 57);
	}
void initialize_before(viewable_image* image,u32 gcm_format,rsx::component_order swizzle_flags){image->native_component_map = apply_component_mapping_flags(gcm_format, swizzle_flags, rsx::default_remap_vector);}
void initialize_after(viewable_image* image,u32 gcm_format,rsx::component_order swizzle_flags){image->set_native_component_layout(apply_component_mapping_flags(gcm_format, swizzle_flags, rsx::default_remap_vector));}
struct render_target {
 bool depth_surface;rsx::surface_depth_format2 format;
 bool is_depth_surface()const{return depth_surface;}
 rsx::surface_depth_format2 get_surface_depth_format()const{return format;}
 u32 get_surface_color_format()const{return CELL_GCM_TEXTURE_A8R8G8B8;}
};
std::pair<u32,bool>get_compatible_gcm_format(u32 format){return{format,false};}
struct section_boundary {
 u32 captured_format=0;bool captured_swap=false;image*captured_image=nullptr;std::array<u32,6> dimensions{};
 void create(u16 w,u16 h,u16 d,u16 m,image* im,u32 pitch,bool managed,u32 format,bool swap){captured_format=format;captured_swap=swap;captured_image=im;dimensions={w,h,d,m,pitch,managed};}
};
struct before_section:section_boundary {using section_boundary::create;void create(u16 w, u16 h, u16 depth, u16 mipmaps, vk::image* image, u32 rsx_pitch, bool managed, const vk::render_target* surface)
		{
			u32 gcm_format;
			bool swap_bytes;

			if (surface->is_depth_surface())
			{
				gcm_format = (surface->get_surface_depth_format() != rsx::surface_depth_format::z16) ? CELL_GCM_TEXTURE_DEPTH16 : CELL_GCM_TEXTURE_DEPTH24_D8;
				swap_bytes = true;
			}
			else
			{
				auto info = get_compatible_gcm_format(surface->get_surface_color_format());
				gcm_format = info.first;
				swap_bytes = info.second;
			}

			create(w, h, depth, mipmaps, image, rsx_pitch, managed, gcm_format, swap_bytes);
		}};
struct after_section:section_boundary {using section_boundary::create;void create(u16 w, u16 h, u16 depth, u16 mipmaps, vk::image* image, u32 rsx_pitch, bool managed, const vk::render_target* surface)
		{
			u32 gcm_format;
			bool swap_bytes;

			if (surface->is_depth_surface())
			{
				const auto info = get_compatible_gcm_format(surface->get_surface_depth_format());
				gcm_format = info.first;
				swap_bytes = info.second;
			}
			else
			{
				auto info = get_compatible_gcm_format(surface->get_surface_color_format());
				gcm_format = info.first;
				swap_bytes = info.second;
			}

			create(w, h, depth, mipmaps, image, rsx_pitch, managed, gcm_format, swap_bytes);
		}};
// The pool's synchronization boundary checks one upgrade, balanced destruction
// and no removal under a reader lock. Actual driver retirement is unchanged.
struct reader_lock {int& state;explicit reader_lock(int& s):state(s){assert(!s);s=1;}void upgrade(){assert(state==1);state=2;}~reader_lock(){state=0;}};
struct entry {u64 key;std::unique_ptr<viewable_image>data;};
struct pool_boundary {
 int m_cached_pool_lock=0;std::list<entry>m_cached_images;u64 m_cached_memory_size=0;
 void put(u32 d,u32 m,rsx::format_class c){auto im=std::make_unique<viewable_image>();im->info.depth=d;im->info.mipLevels=m;im->image_class=c;const u64 key=hash_image_properties(im->format(),im->width(),im->height(),im->depth(),im->mipmaps(),im->info.imageType,im->info.flags,im->info.sharingMode);m_cached_images.push_back({key,std::move(im)});m_cached_memory_size+=4096;}
};
struct before_pool:pool_boundary {std::unique_ptr<vk::viewable_image> find_cached_image(VkFormat format, u16 w, u16 h, u16 d, u16 mipmaps, VkImageType type, VkImageCreateFlags create_flags, VkImageUsageFlags usage, VkSharingMode sharing);};
struct after_pool:pool_boundary {std::unique_ptr<vk::viewable_image> find_cached_image(VkFormat format, u16 w, u16 h, u16 d, u16 mipmaps, VkImageType type, VkImageCreateFlags create_flags, VkImageUsageFlags usage, VkSharingMode sharing, rsx::format_class format_class);};
std::unique_ptr<vk::viewable_image> before_pool::find_cached_image(VkFormat format, u16 w, u16 h, u16 d, u16 mipmaps, VkImageType type, VkImageCreateFlags create_flags, VkImageUsageFlags usage, VkSharingMode sharing)
	{
		reader_lock lock(m_cached_pool_lock);

		if (!m_cached_images.empty())
		{
			const u64 desired_key = hash_image_properties(format, w, h, d, mipmaps, type, create_flags, sharing);
			lock.upgrade();

			for (auto it = m_cached_images.begin(); it != m_cached_images.end(); ++it)
			{
				if (it->key == desired_key && (it->data->info.usage & usage) == usage)
				{
					auto ret = std::move(it->data);
					m_cached_images.erase(it);
					m_cached_memory_size -= ret->memory->size();
					return ret;
				}
			}
		}

		return {};
	}
std::unique_ptr<vk::viewable_image> after_pool::find_cached_image(VkFormat format, u16 w, u16 h, u16 d, u16 mipmaps, VkImageType type, VkImageCreateFlags create_flags, VkImageUsageFlags usage, VkSharingMode sharing, rsx::format_class format_class)
	{
		reader_lock lock(m_cached_pool_lock);

		if (!m_cached_images.empty())
		{
			const u64 desired_key = hash_image_properties(format, w, h, d, mipmaps, type, create_flags, sharing);
			lock.upgrade();

			for (auto it = m_cached_images.begin(); it != m_cached_images.end(); ++it)
			{
				if (it->key == desired_key && (it->data->info.usage & usage) == usage &&
					it->data->depth() == d && it->data->mipmaps() == mipmaps &&
					it->data->format_class() == format_class)
				{
					auto ret = std::move(it->data);
					m_cached_images.erase(it);
					m_cached_memory_size -= ret->memory->size();
					return ret;
				}
			}
		}

		return {};
	}
struct before_storage:before_pool {struct{int device_local=0;}m_memory_types;std::unique_ptr<vk::viewable_image> create_temporary_subresource_storage(
		rsx::format_class format_class, VkFormat format,
		u16 width, u16 height, u16 depth, u16 layers, u8 mips,
		VkImageType image_type, VkFlags image_flags, VkFlags usage_flags)
	{
		auto image = find_cached_image(format, width, height, depth, mips, image_type, image_flags, usage_flags, VK_SHARING_MODE_EXCLUSIVE);

		if (!image)
		{
			image = std::make_unique<vk::viewable_image>(*vk::get_current_renderer(), m_memory_types.device_local, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT,
				image_type,
				format,
				width, height, depth, mips, layers, VK_SAMPLE_COUNT_1_BIT, VK_IMAGE_LAYOUT_UNDEFINED,
				VK_IMAGE_TILING_OPTIMAL, VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT, image_flags | VK_IMAGE_CREATE_ALLOW_NULL_RPCS3,
				VMM_ALLOCATION_POOL_TEXTURE_CACHE, format_class);

			if (!image->value)
			{
				// OOM, bail
				return nullptr;
			}
		}

		return image;
	}};
struct after_storage:after_pool {struct{int device_local=0;}m_memory_types;std::unique_ptr<vk::viewable_image> create_temporary_subresource_storage(
		rsx::format_class format_class, VkFormat format,
		u16 width, u16 height, u16 depth, u16 layers, u8 mips,
		VkImageType image_type, VkFlags image_flags, VkFlags usage_flags)
	{
		usage_flags |= VK_IMAGE_USAGE_TRANSFER_DST_BIT | VK_IMAGE_USAGE_SAMPLED_BIT;
		auto image = find_cached_image(format, width, height, depth, mips, image_type, image_flags, usage_flags, VK_SHARING_MODE_EXCLUSIVE, format_class);

		if (!image)
		{
			image = std::make_unique<vk::viewable_image>(*vk::get_current_renderer(), m_memory_types.device_local, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT,
				image_type,
				format,
				width, height, depth, mips, layers, VK_SAMPLE_COUNT_1_BIT, VK_IMAGE_LAYOUT_UNDEFINED,
				VK_IMAGE_TILING_OPTIMAL, usage_flags, image_flags | VK_IMAGE_CREATE_ALLOW_NULL_RPCS3,
				VMM_ALLOCATION_POOL_TEXTURE_CACHE, format_class);

			if (!image->value)
			{
				// OOM, bail
				return nullptr;
			}
		}

		return image;
	}};
struct copy_region_descriptor{image* src;u32 level=0,src_w=1,src_h=1,dst_x=0,dst_y=0,dst_z=0,dst_w=1,dst_h=1;};
[[gnu::noinline]] void before_copy(command_buffer& cmd, const std::vector<copy_region_descriptor>& sections_to_transfer) {


		std::unordered_set<decltype(sections_to_transfer.front().src)> processed_input_images;

 for (const auto& section : sections_to_transfer) {if (!section.src) continue;
if (!processed_input_images.contains(section.src))
			{
				// Avoid inserting unnecessary barrier GENERAL->TRANSFER_SRC->GENERAL in active render targets
				const auto preferred_layout = (section.src->current_layout != VK_IMAGE_LAYOUT_GENERAL) ?
					VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL : VK_IMAGE_LAYOUT_GENERAL;

				section.src->push_layout(cmd, preferred_layout);
				processed_input_images.insert(section.src);
			}
section.src->copy(cmd);
}
// Pop unique image layouts here
		for (auto& image : processed_input_images)
		{
			image->pop_layout(cmd);
		}
}

[[gnu::noinline]] void after_copy(command_buffer& cmd, const std::vector<copy_region_descriptor>& sections_to_transfer) {


		using source_image_type = decltype(sections_to_transfer.front().src);

const auto transfer_regions = [&]<bool use_inline_inputs>() {

			using source_set = std::conditional_t<use_inline_inputs,
				rsx::simple_array<source_image_type>, std::unordered_set<source_image_type>>;
			source_set processed_input_images;
			const auto first_use = [&](source_image_type source)
			{
				if constexpr (use_inline_inputs)
				{
					if (std::find(processed_input_images.begin(), processed_input_images.end(), source) != processed_input_images.end())
						return false;

					processed_input_images.push_back(source);
				}
				else
				{
					if (processed_input_images.contains(source))
						return false;

					processed_input_images.insert(source);
				}
				return true;
			};

			
 for (const auto& section : sections_to_transfer) {if (!section.src) continue;
if (first_use(section.src))
				{
					// Avoid inserting unnecessary barrier GENERAL->TRANSFER_SRC->GENERAL in active render targets
					const auto preferred_layout = (section.src->current_layout != VK_IMAGE_LAYOUT_GENERAL) ?
						VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL : VK_IMAGE_LAYOUT_GENERAL;

					section.src->push_layout(cmd, preferred_layout);
				}
section.src->copy(cmd);
}
// Pop unique image layouts here
			for (auto& image : processed_input_images)
			{
				image->pop_layout(cmd);
			}
		
};
if (sections_to_transfer.size() <= 8)
			transfer_regions.template operator()<true>();
		else
			transfer_regions.template operator()<false>();
	
}

bool copy_transfer_regions_fully_cover_image(vk::image* dst, const rsx::simple_array<copy_region_descriptor>& sections)
	{
		const u32 mipmaps = dst->mipmaps();
		if (dst->aspect() != VK_IMAGE_ASPECT_COLOR_BIT || !mipmaps || mipmaps > 16)
			return false;

		// One bit per complete layer/depth slice. This also catches duplicate
		// copies that leave another slice undefined on a recycled image.
		std::array<u32, 17> mip_offsets{};
		for (u32 level = 0; level < mipmaps; ++level)
		{
			const u32 slices = dst->type() == VK_IMAGE_TYPE_3D ? std::max(1u, dst->depth() >> level) : dst->layers();
			mip_offsets[level + 1] = mip_offsets[level] + slices;
		}

		std::array<u64, 32> covered{};
		u32 remaining = mip_offsets[mipmaps];
		if (!remaining || remaining > covered.size() * 64 || sections.size() < remaining)
			return false;

		for (const auto& section : sections)
		{
			if (!section.src || section.src->aspect() != VK_IMAGE_ASPECT_COLOR_BIT ||
				!section.src_w || !section.src_h || section.level >= mipmaps ||
				section.dst_x || section.dst_y ||
				section.dst_w != std::max(1u, dst->width() >> section.level) ||
				section.dst_h != std::max(1u, dst->height() >> section.level) ||
				section.dst_z >= mip_offsets[section.level + 1] - mip_offsets[section.level])
			{
				return false;
			}

			const u32 slice = mip_offsets[section.level] + section.dst_z;
			const u64 bit = u64{1} << (slice % 64);
			if (!(covered[slice / 64] & bit))
			{
				covered[slice / 64] |= bit;
				--remaining;
			}
		}

		return remaining == 0;
	}
}
VkComponentMapping oracle(const texture_channel_remap_t& r,VkComponentMapping native){
 std::array<u32,4>input{native.a,native.r,native.g,native.b},output{};
 for(u32 i=0;i<4;++i)output[i]=r.control_map[i]==0?VK_COMPONENT_SWIZZLE_ZERO:r.control_map[i]==1?VK_COMPONENT_SWIZZLE_ONE:input[r.channel_map[i]];
 return {output[1],output[2],output[3],output[0]};
}
u64 native_checks=0,native_wrong=0,pool_checks=0,pool_wrong=0,depth_checks=0,depth_wrong=0,copy_checks=0,coverage_checks=0,clear_eliminated=0,storage_checks=0,storage_wrong=0;
void test_views(){
 for(u32 controls=0;controls<81;++controls)for(u32 channels=0;channels<256;++channels){
  u32 packed=0,t=controls;for(u32 n=0;n<4;++n){packed|=(t%3)<<(8+n*2);t/=3;}
  auto remap=rsx::decode_remap_encoding(packed|channels);
  vk::viewable_image old,now;old.info.mipLevels=now.info.mipLevels=5;old.info.arrayLayers=now.info.arrayLayers=6;
  vk::initialize_before(&old,CELL_GCM_TEXTURE_A8R8G8B8,component_order::default_);vk::initialize_after(&now,CELL_GCM_TEXTURE_A8R8G8B8,component_order::default_);
  auto* original=now.get_view(remap);auto* original_sub=original->as(72);old.get_view(remap);
  auto original_mapping=original->info.components;
  vk::initialize_before(&old,CELL_GCM_TEXTURE_D8R8G8B8,component_order::default_);vk::initialize_after(&now,CELL_GCM_TEXTURE_D8R8G8B8,component_order::default_);
  auto* view=now.get_view(remap);auto expected=oracle(remap,{VK_COMPONENT_SWIZZLE_R,VK_COMPONENT_SWIZZLE_G,VK_COMPONENT_SWIZZLE_B,VK_COMPONENT_SWIZZLE_ONE});
  native_wrong+=old.get_view(remap)->info.components!=expected;
  assert(view->info.components==expected&&view->image()==&now&&view->info.subresourceRange.levelCount==5&&view->info.subresourceRange.layerCount==6);
  assert(view->as(72)->info.components==expected);
  // Old descriptors stay alive until the resource manager retires their scope.
  assert(original->info.components==original_mapping&&original_sub->format()==72);
  auto total=constructed_views;vk::initialize_after(&now,CELL_GCM_TEXTURE_D8R8G8B8,component_order::default_);
  assert(now.get_view(remap)==view&&constructed_views==total);
  vk::initialize_after(&now,CELL_GCM_TEXTURE_A8R8G8B8,component_order::default_);
  assert(now.get_view(remap)->info.components==original_mapping);
  vk::get_resource_manager()->retired.clear();++native_checks;
 }
 // Explicit order changes and depth native mapping use the same production path.
 vk::viewable_image now;
 for(auto order:{component_order::native,component_order::swapped_native,component_order::default_}){
  vk::initialize_after(&now,CELL_GCM_TEXTURE_A8R8G8B8,order);auto* v=now.get_view(rsx::default_remap_vector);
  auto expected=order==component_order::swapped_native?VkComponentMapping{6,3,4,5}:VkComponentMapping{3,4,5,6};
  assert(v->info.components==expected);++native_checks;
 }
 vk::get_resource_manager()->retired.clear();
}
void test_pool(){
 const std::array<rsx::format_class,5> classes{RSX_FORMAT_CLASS_COLOR,RSX_FORMAT_CLASS_DEPTH16_UNORM,RSX_FORMAT_CLASS_DEPTH16_FLOAT,RSX_FORMAT_CLASS_DEPTH24_UNORM_X8_PACK32,RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32};
 for(u32 depth:{1,2,16,128,256,512})for(u32 wanted_d:{1,2,16,128,256,512})for(u32 stored_m=1;stored_m<=10;++stored_m)for(u32 wanted_m=1;wanted_m<=10;++wanted_m)for(auto stored:classes)for(auto wanted:classes){
  vk::before_pool old;vk::after_pool now;old.put(depth,stored_m,stored);now.put(depth,stored_m,stored);
  auto a=old.find_cached_image(37,512,512,wanted_d,wanted_m,2,0,3,0);
  auto b=now.find_cached_image(37,512,512,wanted_d,wanted_m,2,0,3,0,wanted);
  const bool expected=depth==wanted_d&&stored_m==wanted_m&&stored==wanted;
  pool_wrong+=bool(a)!=expected;assert(bool(b)==expected);
  assert(now.m_cached_memory_size==(expected?0:4096)&&now.m_cached_images.size()==(expected?0:1));assert(!now.m_cached_pool_lock);
  if(b)assert(b->depth()==depth&&b->mipmaps()==wanted_m&&b->format_class()==wanted);
  ++pool_checks;
 }
 // Missing entries and unsupported usages cannot change pool accounting.
 vk::after_pool pool;assert(!pool.find_cached_image(37,512,512,1,1,2,0,1,0,RSX_FORMAT_CLASS_COLOR));
 pool.put(1,1,RSX_FORMAT_CLASS_COLOR);
 assert(!pool.find_cached_image(37,512,512,1,1,2,0,4,0,RSX_FORMAT_CLASS_COLOR)&&pool.m_cached_memory_size==4096);
 assert(!pool.find_cached_image(37,512,512,1,1,2,0,1,1,RSX_FORMAT_CLASS_COLOR)&&pool.m_cached_memory_size==4096);
 // Two images with the same VkFormat but different PS3 depth interpretation.
 assert(rsx::classify_format(CELL_GCM_TEXTURE_DEPTH24_D8)!=rsx::classify_format(CELL_GCM_TEXTURE_DEPTH24_D8_FLOAT));
 vk::after_pool mixed;mixed.put(1,1,RSX_FORMAT_CLASS_DEPTH24_UNORM_X8_PACK32);mixed.put(1,1,RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32);
 auto f=mixed.find_cached_image(37,512,512,1,1,2,0,1,0,RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32);assert(f&&f->format_class()==RSX_FORMAT_CLASS_DEPTH24_FLOAT_X8_PACK32&&mixed.m_cached_memory_size==4096);
 auto n=mixed.find_cached_image(37,512,512,1,1,2,0,1,0,RSX_FORMAT_CLASS_DEPTH24_UNORM_X8_PACK32);assert(n&&n->format_class()==RSX_FORMAT_CLASS_DEPTH24_UNORM_X8_PACK32&&!mixed.m_cached_memory_size);
 pool_checks+=5;
}
// Independent payload model: paint individual destination texels over stale
// pooled bytes. A skipped clear must give the same bytes as clearing first.
void check_coverage(vk::image& dst,const rsx::simple_array<vk::copy_region_descriptor>& sections){
 const bool skip=vk::copy_transfer_regions_fully_cover_image(&dst,sections);
 if(skip){
  for(u32 level=0;level<dst.mipmaps();++level){
   const u32 w=std::max(1u,dst.width()>>level),h=std::max(1u,dst.height()>>level);
   const u32 slices=dst.type()==VK_IMAGE_TYPE_3D?std::max(1u,dst.depth()>>level):dst.layers();
   std::vector<u32>old(w*h*slices,0),now(w*h*slices,0xfeed);
   u32 value=0;
   for(const auto& s:sections){++value;if(!s.src||s.level!=level)continue;
    for(u32 y=s.dst_y;y<s.dst_y+s.dst_h;++y)for(u32 x=s.dst_x;x<s.dst_x+s.dst_w;++x){assert(x<w&&y<h&&s.dst_z<slices);old[(s.dst_z*h+y)*w+x]=now[(s.dst_z*h+y)*w+x]=value;}
   }
   assert(old==now);
  }
  ++clear_eliminated;
 }
 ++coverage_checks;
}
void test_coverage(){
 vk::image src,depth_src;depth_src.aspect_mask=VK_IMAGE_ASPECT_DEPTH_BIT;
 for(u32 type:{VK_IMAGE_TYPE_2D,VK_IMAGE_TYPE_3D})for(u32 width:{1,3,8,17})for(u32 height:{1,4,9})for(u32 depth:{1,2,7})for(u32 mips:{1,2,4}){
  vk::image dst;dst.info.width=width;dst.info.height=height;dst.info.depth=depth;dst.info.imageType=type;dst.info.arrayLayers=type==VK_IMAGE_TYPE_2D?6:1;dst.info.mipLevels=mips;
  rsx::simple_array<vk::copy_region_descriptor>full;
  for(u32 level=0;level<mips;++level)for(u32 z=0;z<(type==VK_IMAGE_TYPE_3D?std::max(1u,depth>>level):6);++z){
   vk::copy_region_descriptor s{&src};s.level=level;s.dst_z=z;s.src_w=s.dst_w=std::max(1u,width>>level);s.src_h=s.dst_h=std::max(1u,height>>level);full.push_back(s);
  }
  assert(vk::copy_transfer_regions_fully_cover_image(&dst,full));check_coverage(dst,full);
  auto reversed=full;std::reverse(reversed.begin(),reversed.end());check_coverage(dst,reversed);
  for(u32 mutation=0;mutation<13;++mutation){
   auto partial=full;
   switch(mutation){
   case 0:partial.resize(partial.size()-1);break;
   case 1:if(partial.size()>1)partial.back()=partial.front();else partial.clear();break;
   case 2:partial.front().src=nullptr;break;
   case 3:partial.front().src=&depth_src;break;
   case 4:partial.front().src_w=0;break;
   case 5:partial.front().src_h=0;break;
   case 6:partial.front().level=mips;break;
   case 7:partial.front().dst_x=1;break;
   case 8:partial.front().dst_y=1;break;
   case 9:++partial.front().dst_w;break;
   case 10:++partial.front().dst_h;break;
   case 11:partial.front().dst_z=2048;break;
   case 12:partial.front().dst_w=0;break;
   }
   assert(!vk::copy_transfer_regions_fully_cover_image(&dst,partial));check_coverage(dst,partial);
  }
  full.push_back(full.front());assert(vk::copy_transfer_regions_fully_cover_image(&dst,full));check_coverage(dst,full);
  dst.aspect_mask=VK_IMAGE_ASPECT_DEPTH_BIT;assert(!vk::copy_transfer_regions_fully_cover_image(&dst,full));++coverage_checks;
 }
 // The coverage bitmap's bound is conservative, including 512-deep images
 // with long mipchains and boundaries at 64, 1024 and 2048 slices.
 for(u32 depth:{64,512,1024,2048,2049})for(u32 mips:{1,10,16,17}){
  vk::image dst;dst.info.width=dst.info.height=1;dst.info.depth=depth;dst.info.mipLevels=mips;dst.info.imageType=VK_IMAGE_TYPE_3D;
  rsx::simple_array<vk::copy_region_descriptor>sections;u32 total=0;
  for(u32 level=0;level<mips;++level)for(u32 z=0;z<std::max(1u,depth>>level);++z){vk::copy_region_descriptor s{&src};s.level=level;s.dst_z=z;sections.push_back(s);++total;}
  assert(vk::copy_transfer_regions_fully_cover_image(&dst,sections)==(mips<=16&&total<=2048));check_coverage(dst,sections);
 }
}
void test_depth(){
 vk::image image;
 for(bool is_depth:{false,true})for(auto format:{surface_depth_format2::z16_uint,surface_depth_format2::z24s8_uint,surface_depth_format2::z16_float,surface_depth_format2::z24s8_float}){
  vk::render_target surface{is_depth,format};vk::before_section old;vk::after_section now;
  old.create(17,23,1,3,&image,256,true,&surface);now.create(17,23,1,3,&image,256,true,&surface);
  const std::array<u32,4>expected_formats{CELL_GCM_TEXTURE_DEPTH16,CELL_GCM_TEXTURE_DEPTH24_D8,CELL_GCM_TEXTURE_DEPTH16_FLOAT,CELL_GCM_TEXTURE_DEPTH24_D8_FLOAT};
  auto expected=is_depth?expected_formats[static_cast<u32>(format)-1]:CELL_GCM_TEXTURE_A8R8G8B8;
  depth_wrong+=old.captured_format!=expected;assert(now.captured_format==expected&&now.captured_swap==is_depth&&now.captured_image==&image&&now.dimensions==old.dimensions);++depth_checks;
 }
}
void test_storage(){
 for(u32 usage=0;usage<8;++usage){
  vk::before_storage old;vk::after_storage now;
  auto a=old.create_temporary_subresource_storage(RSX_FORMAT_CLASS_COLOR,37,512,512,1,1,1,VK_IMAGE_TYPE_2D,0,usage);
  auto b=now.create_temporary_subresource_storage(RSX_FORMAT_CLASS_COLOR,37,512,512,1,1,1,VK_IMAGE_TYPE_2D,0,usage);
  auto expected=usage|VK_IMAGE_USAGE_TRANSFER_DST_BIT|VK_IMAGE_USAGE_SAMPLED_BIT;
  storage_wrong+=a->info.usage!=expected;assert(b->info.usage==expected&&b->info.flags==0&&b->mipmaps()==1&&b->layers()==1);++storage_checks;
 }
 // A pool entry satisfying caller usage but missing intrinsic DST must stay in
 // the pool; a complete superset is accepted without another image allocation.
 vk::after_storage cache;cache.put(1,1,RSX_FORMAT_CLASS_COLOR);cache.m_cached_images.back().data->info.imageType=VK_IMAGE_TYPE_2D;cache.m_cached_images.back().key=vk::hash_image_properties(37,512,512,1,1,VK_IMAGE_TYPE_2D,0,0);cache.m_cached_images.back().data->info.usage=VK_IMAGE_USAGE_TRANSFER_SRC_BIT|VK_IMAGE_USAGE_SAMPLED_BIT;
 auto rejected=cache.create_temporary_subresource_storage(RSX_FORMAT_CLASS_COLOR,37,512,512,1,1,1,VK_IMAGE_TYPE_2D,0,VK_IMAGE_USAGE_TRANSFER_SRC_BIT|VK_IMAGE_USAGE_SAMPLED_BIT);
 assert(cache.m_cached_memory_size==4096&&rejected->info.usage==7);++storage_checks;
 auto* identity=cache.m_cached_images.back().data.get();identity->info.usage=7;
 auto reused=cache.create_temporary_subresource_storage(RSX_FORMAT_CLASS_COLOR,37,512,512,1,1,1,VK_IMAGE_TYPE_2D,0,VK_IMAGE_USAGE_SAMPLED_BIT);
 assert(reused.get()==identity&&!cache.m_cached_memory_size);++storage_checks;
}
using Copy=void(*)(vk::command_buffer&,const std::vector<vk::copy_region_descriptor>&);
void reset_images(std::array<vk::image,16>& images){for(u32 i=0;i<images.size();++i){auto& image=images[i];image.identity=i+1;image.current_layout=i%2?VK_IMAGE_LAYOUT_GENERAL:3;image.saved_layout=image.push_count=image.pop_count=image.copy_count=0;}}
void test_copies(){
 std::array<vk::image,16>old,now;u32 random=1;
 for(u32 count=0;count<=64;++count)for(u32 pattern=0;pattern<200;++pattern){
  reset_images(old);reset_images(now);std::vector<vk::copy_region_descriptor>a,b;
  for(u32 n=0;n<count;++n){random=random*1664525+1013904223;u32 id=(random>>24)%18;a.push_back({id<16?&old[id]:nullptr});b.push_back({id<16?&now[id]:nullptr});}
  vk::command_buffer ca,cb;vk::before_copy(ca,a);vk::after_copy(cb,b);
  assert(ca.pushes==cb.pushes&&ca.pops==cb.pops&&ca.copies==cb.copies&&ca.push_digest==cb.push_digest&&ca.copy_digest==cb.copy_digest);
  for(u32 n=0;n<16;++n){assert(old[n].push_count==now[n].push_count&&old[n].pop_count==now[n].pop_count&&old[n].copy_count==now[n].copy_count&&old[n].current_layout==now[n].current_layout);assert(now[n].push_count<=1&&now[n].push_count==now[n].pop_count&&!now[n].saved_layout);}
  ++copy_checks;
 }
}
struct timing{double ns;u64 allocations,digest;};
timing measure(Copy fn,const std::vector<vk::copy_region_descriptor>& sections,u32 iterations){
 vk::command_buffer cmd;allocation_calls=0;count_allocations=true;
 auto start=std::chrono::steady_clock::now();for(u32 i=0;i<iterations;++i)fn(cmd,sections);auto end=std::chrono::steady_clock::now();
 count_allocations=false;return{std::chrono::duration<double,std::nano>(end-start).count()/iterations,allocation_calls,cmd.copy_digest};
}
void benchmark(){
 std::array<vk::image,16>images;reset_images(images);bool first=true;
 std::cout<<"[";
 for(u32 count:{1,2,4,8,9,32,256})for(bool repeated:{false,true}){
  std::vector<vk::copy_region_descriptor>sections;for(u32 n=0;n<count;++n)sections.push_back({&images[repeated?0:n%16]});
  const u32 iterations=30000/(1+count/16);
  std::array<double,7>old_trials{},new_trials{};timing old{},now{};
  for(u32 trial=0;trial<7;++trial){
   if(trial%2){now=measure(vk::after_copy,sections,iterations);old=measure(vk::before_copy,sections,iterations);}
   else{old=measure(vk::before_copy,sections,iterations);now=measure(vk::after_copy,sections,iterations);}
   old_trials[trial]=old.ns;new_trials[trial]=now.ns;
  }
  auto old_sorted=old_trials,new_sorted=new_trials;std::sort(old_sorted.begin(),old_sorted.end());std::sort(new_sorted.begin(),new_sorted.end());old.ns=old_sorted[3];now.ns=new_sorted[3];
  assert(old.digest==now.digest);if(count<=8)assert(now.allocations==0&&old.allocations>0);else assert(now.allocations==old.allocations);
  if(!first)std::cout<<",";
  first=false;
  std::cout<<"{\"sections\":"<<count<<",\"repeated\":"<<(repeated?"true":"false")<<",\"iterationsPerTrial\":"<<iterations<<",\"beforeMedianNs\":"<<old.ns<<",\"afterMedianNs\":"<<now.ns<<",\"beforeAllocationsPerTrial\":"<<old.allocations<<",\"afterAllocationsPerTrial\":"<<now.allocations<<",\"beforeTrialsNs\":[";
  for(u32 i=0;i<7;++i){if(i)std::cout<<",";std::cout<<old_trials[i];}std::cout<<"],\"afterTrialsNs\":[";
  for(u32 i=0;i<7;++i){if(i)std::cout<<",";std::cout<<new_trials[i];}std::cout<<"]}";
 }
 std::cout<<"]";
}
int main(){
 test_views();test_pool();test_depth();test_copies();test_coverage();test_storage();
 assert(native_wrong>0&&pool_wrong>0&&depth_wrong==4&&storage_wrong==4&&constructed_views==destroyed_views);
 std::cout<<"{\"nativeChecks\":"<<native_checks<<",\"baselineWrongNativeMappings\":"<<native_wrong<<",\"candidateWrongNativeMappings\":0,\"poolChecks\":"<<pool_checks<<",\"baselineWrongPoolSelections\":"<<pool_wrong<<",\"candidateWrongPoolSelections\":0,\"depthChecks\":"<<depth_checks<<",\"baselineWrongDepthFormats\":"<<depth_wrong<<",\"candidateWrongDepthFormats\":0,\"copyChecks\":"<<copy_checks<<",\"sameCopiesAndPerImageBarriers\":true,\"coverageChecks\":"<<coverage_checks<<",\"colorClearEliminationsInCases\":"<<clear_eliminated<<",\"sameModeledDestinationTexels\":true,\"viewsConstructed\":"<<constructed_views<<",\"viewsDestroyed\":"<<destroyed_views<<",\"copyBenchmarks\":";
 benchmark();std::cout<<",\"storageChecks\":"<<storage_checks<<",\"baselineWrongUsageFlags\":"<<storage_wrong<<",\"candidateWrongUsageFlags\":0}";
}
