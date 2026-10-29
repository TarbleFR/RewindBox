#include <algorithm>
#include <array>
#include <cassert>
#include <concepts>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <iostream>
#include <iterator>
#include <random>
#include <type_traits>
#include <unordered_set>
#include <utility>
#include <vector>
using u8=std::uint8_t;using u32=std::uint32_t;using u64=std::uint64_t;
template<class C>u32 size32(const C& c){return static_cast<u32>(c.size());}
template<class T>concept UnsignedInt=std::is_unsigned_v<T>;
#define ensure(x,...) assert(x)
#define AUDIT(x) assert(x)
namespace adapters {
inline u64 allocations=0,bytes=0;
inline std::unordered_set<void*> live;
template<size_t Align>void* malloc(size_t n){
 ++allocations;bytes+=n;constexpr size_t align=std::max(Align,alignof(void*));
 auto* p=std::aligned_alloc(align,(n+align-1)/align*align);assert(p);assert(live.insert(p).second);return p;
}
inline void free(void* p){assert(live.erase(p)==1);std::free(p);}
template<size_t Align>void* realloc(void* p,size_t old,size_t n){auto* out=malloc<Align>(n);std::memcpy(out,p,old);free(p);return out;}
}
namespace before { template<class T>using reverse_pointer=std::reverse_iterator<T*>;namespace aligned_allocator=adapters;}



namespace before
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
				before::simple_array<Ty> tmp{ *this };
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

		void operator += (const before::simple_array<Ty>& that)
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
#define RPCS3_IOS
namespace after { template<class T>using reverse_pointer=std::reverse_iterator<T*>;namespace aligned_allocator=adapters;}



namespace after
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
				after::simple_array<Ty> tmp{ *this };
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

		void operator += (const after::simple_array<Ty>& that)
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
namespace desktop { template<class T>using reverse_pointer=std::reverse_iterator<T*>;namespace aligned_allocator=adapters;}



namespace desktop
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
				desktop::simple_array<Ty> tmp{ *this };
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

		void operator += (const desktop::simple_array<Ty>& that)
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

template<size_t Size,size_t Align>struct alignas(Align) Value{
 std::array<u8,Size> bytes{};
 bool operator==(const Value&)const=default;
};
u64 checks=0;
template<class A>auto values(const A& a){return std::vector<typename A::value_type>(a.begin(),a.end());}
template<class A>void fill(A& a,u32 n,u32 salt){
 a.resize(n);for(u32 i=0;i<n;++i)for(size_t j=0;j<a[i].bytes.size();++j)a[i].bytes[j]=static_cast<u8>(i*31+j+salt);
}
template<class A,class B,class C>void same(const A& a,const B& b,const C& c){
 assert(values(a)==values(b));assert(values(a)==values(c));
 assert(a.capacity()>=a.size()&&b.capacity()>=b.size()&&c.capacity()>=c.size());
 assert(reinterpret_cast<uintptr_t>(b.data())%alignof(typename B::value_type)==0);++checks;
}
template<class T>void exercise(){
 using A=before::simple_array<T>;using B=after::simple_array<T>;using C=desktop::simple_array<T>;
 static_assert(sizeof(A)==sizeof(B)&&alignof(A)==alignof(B));
 constexpr u32 local=std::max<u32>(64/sizeof(T),1);
 for(u32 x:{0u,1u,local,local+1,local+17,257u})for(u32 y:{0u,1u,local,local+1,local+17,257u})
 for(u32 reserve=0;reserve<4;++reserve){
  A a,a2;B b,b2;C c,c2;
  if(reserve&1){a.reserve(300);b.reserve(300);c.reserve(300);}
  if(reserve&2){a2.reserve(300);b2.reserve(300);c2.reserve(300);}
  fill(a,x,17);fill(b,x,17);fill(c,x,17);fill(a2,y,29);fill(b2,y,29);fill(c2,y,29);
  for(int repeat=0;repeat<3;++repeat){
   auto prior=adapters::allocations;b.swap(b2);assert(adapters::allocations==prior);
   a.swap(a2);c.swap(c2);same(a,b,c);same(a2,b2,c2);
  }
  auto prior=adapters::allocations;B moved(std::move(b));assert(adapters::allocations==prior);
  A oldmove(std::move(a));C desktopmove(std::move(c));same(oldmove,moved,desktopmove);same(a,b,c);
  prior=adapters::allocations;b2=std::move(moved);assert(adapters::allocations==prior);
  a2=std::move(oldmove);c2=std::move(desktopmove);same(a2,b2,c2);same(oldmove,moved,desktopmove);
  fill(a,local+19,7);fill(b,local+19,7);fill(c,local+19,7);same(a,b,c);
 }
 // Interleaved allocation, copy, clear and move operations expose stale owners
 // and moved-from reuse; the reference and desktop execute the same sequence.
 std::array<A,9> old;std::array<B,9> now;std::array<C,9> desktop;std::mt19937 random(595);
 for(int i=0;i<20000;++i){
  auto a=random()%9,b=random()%9;auto n=random()%130;
  switch(random()%6){
   case 0:fill(old[a],n,i);fill(now[a],n,i);fill(desktop[a],n,i);break;
   case 1:old[a].clear();now[a].clear();desktop[a].clear();break;
   case 2:old[a]=old[b];now[a]=now[b];desktop[a]=desktop[b];break;
   case 3:{auto prior=adapters::allocations;now[a].swap(now[b]);assert(adapters::allocations==prior);old[a].swap(old[b]);desktop[a].swap(desktop[b]);break;}
   case 4:{auto prior=adapters::allocations;now[a]=std::move(now[b]);assert(adapters::allocations==prior);old[a]=std::move(old[b]);desktop[a]=std::move(desktop[b]);break;}
   case 5:old[a].reserve(n);now[a].reserve(n);desktop[a].reserve(n);break;
  }
  for(size_t j=0;j<9;++j)same(old[j],now[j],desktop[j]);
 }
}
int main(){
 exercise<Value<1,1>>();exercise<Value<4,4>>();exercise<Value<40,8>>();exercise<Value<128,64>>();
 assert(adapters::live.empty());
 u64 old_alloc,old_bytes,new_alloc,new_bytes;
 {
  before::simple_array<Value<40,8>> a;after::simple_array<Value<40,8>> b;
  fill(a,4096,1);fill(b,4096,1);auto* original=b.data();
  auto n=adapters::allocations,z=adapters::bytes;before::simple_array<Value<40,8>> oldmove(std::move(a));
  old_alloc=adapters::allocations-n;old_bytes=adapters::bytes-z;
  n=adapters::allocations;z=adapters::bytes;after::simple_array<Value<40,8>> newmove(std::move(b));
  new_alloc=adapters::allocations-n;new_bytes=adapters::bytes-z;
  assert(values(oldmove)==values(newmove)&&newmove.data()==original&&new_alloc==0);
 }
 assert(adapters::live.empty());
 std::cout<<"{\"contentAndAlignmentChecks\":"<<checks<<",\"doubleFreeOrLeak\":false,\"candidateSwapOrMoveAllocations\":0,\"baseline4096RegionMoveAllocations\":"<<old_alloc<<",\"baseline4096RegionMoveBytes\":"<<old_bytes<<",\"candidate4096RegionMoveAllocations\":"<<new_alloc<<",\"candidate4096RegionMoveBytes\":"<<new_bytes<<",\"heapOwnershipTransferred\":true}";
}
