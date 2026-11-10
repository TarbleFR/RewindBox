#include <algorithm>
#include <array>
#include <cassert>
#include <chrono>
#include <concepts>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <random>
#include <string>
#include <type_traits>
#include <utility>
#include <vector>
using u8=std::uint8_t;using u16=std::uint16_t;using u32=std::uint32_t;using u64=std::uint64_t;
using usz=std::size_t;
struct max_value{template<class T>operator T()const{return static_cast<T>(~T{0});}};constexpr max_value umax{};
#define ensure(x,...) assert(x)
#define AUDIT(x) assert(x)
template<class C>u32 size32(const C& c){return static_cast<u32>(c.size());}
namespace fmt{template<class...A>std::string format(const char* f,A...v){int n=std::snprintf(nullptr,0,f,v...);std::vector<char>b(n+1);std::snprintf(b.data(),b.size(),f,v...);return std::string(b.data(),n);}}
namespace utils{constexpr u32 get_page_size(){return 4096;}u32 aligned_div(u32 a,u32 b){return (a+b-1)/b;}}


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
template<class T,class C>T read_from_ptr(const C& c,u32 offset){T value;std::memcpy(&value,reinterpret_cast<const u8*>(c.data())+offset,sizeof(T));return value;}
template<class T,class C,class V>void write_to_ptr(C& c,u32 offset,V value){T cast=value;std::memcpy(reinterpret_cast<u8*>(c.data())+offset,&cast,sizeof(T));}
template<class C>void write_to_ptr(C& c,u32 offset,u32 value){write_to_ptr<u32>(c,offset,value);}
struct Logger{template<class...A>void warning(const char*,A...){}template<class...A>void notice(const char*,A...){}}rsx_log;
namespace rsx{enum class surface_metrics{bytes,samples};using utils::address_range32;template<class T>using simple_array=std::vector<T>;}
struct Surface{
 u32 address,width,pitch,height;
 address_range32 get_memory_range()const{return address_range32::start_length(address,(height-1)*pitch+width);}
 u32 get_rsx_pitch()const{return pitch;}
 template<rsx::surface_metrics>u32 get_surface_width()const{return width;}
 template<rsx::surface_metrics>u32 get_surface_height()const{return height;}
};
struct surface_overlap_info{Surface* surface;u32 base_address;bool is_depth;};
struct Boundary{
 std::vector<std::pair<u32,bool>> invalidated;
 Boundary(){invalidated.reserve(512);}
 void invalidate_surface_address(u32 address,bool depth){invalidated.emplace_back(address,depth);}
};
struct Result{std::vector<bool> changed,covered;size_t storageBytes;};
struct before : Boundary {
void remove_duplicates_fallback_impl(rsx::simple_array<surface_overlap_info>& sections, const rsx::address_range32& range)
		{
			// Originally used to debug crashes but this function breaks often enough that I'll leave the checks in for now.
			// Safe to remove after some time if no asserts are reported.
			constexpr u32 overrun_cookie_value = 0xCAFEBABEu;

			// Generic painter's algorithm to detect obsolete sections
			ensure(range.length() < 64 * 0x100000);
			std::vector<u8> marker(range.length() + sizeof(overrun_cookie_value), 0);

			// Tag end
			write_to_ptr(marker, range.length(), overrun_cookie_value);

			u32 removed_count = 0;

			auto compare_and_tag_row = [&](u32 offset, u32 length) -> bool
			{
				u64 mask = 0;

				while (length >= 8)
				{
					const u64 value = read_from_ptr<u64>(marker, offset);
					const u64 block_mask = ~value;              // If the value is not all 1s, set valid to true
					mask |= block_mask;
					write_to_ptr<u64>(marker, offset, umax);

					offset += 8;
					length -= 8;
				}

				if (length >= 4)
				{
					const u32 value = read_from_ptr<u32>(marker, offset);
					const u32 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u32>(marker, offset, umax);

					offset += 4;
					length -= 4;
				}

				if (length >= 2)
				{
					const u16 value = read_from_ptr<u16>(marker, offset);
					const u16 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u16>(marker, offset, umax);

					offset += 2;
					length -= 2;
				}

				if (length)
				{
					const u8 value = read_from_ptr<u8>(marker, offset);
					const u8 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u8>(marker, offset, umax);
				}

				return !!mask;
			};

			for (auto it = sections.crbegin(); it != sections.crend(); ++it)
			{
				auto this_range = it->surface->get_memory_range();
				ensure(this_range.overlaps(range));

				const auto native_pitch = it->surface->template get_surface_width<rsx::surface_metrics::bytes>();
				const auto rsx_pitch = it->surface->get_rsx_pitch();
				auto num_rows = it->surface->template get_surface_height<rsx::surface_metrics::samples>();
				bool valid = false;

				if (this_range.start < range.start)
				{
					// Starts outside bounds
					const auto internal_offset = (range.start - this_range.start);
					const auto row_num = internal_offset / rsx_pitch;
					const auto row_offset = internal_offset % rsx_pitch;

					// This section is unconditionally valid
					valid = true;

					if (row_offset < native_pitch)
					{
						compare_and_tag_row(0, std::min(native_pitch - row_offset, range.length()));
					}

					// Jump to next row...
					this_range.start = this_range.start + (row_num + 1) * rsx_pitch;
				}

				if (this_range.end > range.end)
				{
					// Unconditionally valid
					valid = true;
					this_range.end = range.end;
				}

				if (valid)
				{
					if (this_range.start >= this_range.end)
					{
						continue;
					}

					num_rows = utils::aligned_div(this_range.length(), rsx_pitch);
				}

				for (u32 row = 0, offset = (this_range.start - range.start), section_len = (this_range.end - range.start + 1);
					row < num_rows;
					++row, offset += rsx_pitch)
				{
					valid |= compare_and_tag_row(offset, std::min<u32>(native_pitch, (section_len - offset)));
				}

				if (!valid)
				{
					removed_count++;
					rsx_log.warning("Stale surface at address 0x%x will be deleted", it->base_address);
					invalidate_surface_address(it->base_address, it->is_depth);
				}
			}

			// Notify
			rsx_log.notice("rsx::surface_cache::check_for_duplicates_fallback analysed %u overlapping sections and removed %u", ::size32(sections), removed_count);

			// Verify no OOB
			ensure(read_from_ptr<u32>(marker, range.length()) == overrun_cookie_value);
		}
Result rows(const address_range32& range,const std::vector<std::pair<u32,u32>>& spans){
constexpr u32 overrun_cookie_value = 0xCAFEBABEu;

			// Generic painter's algorithm to detect obsolete sections
			ensure(range.length() < 64 * 0x100000);
			std::vector<u8> marker(range.length() + sizeof(overrun_cookie_value), 0);

			// Tag end
			write_to_ptr(marker, range.length(), overrun_cookie_value);

			[[maybe_unused]] u32 removed_count = 0;

			auto compare_and_tag_row = [&](u32 offset, u32 length) -> bool
			{
				u64 mask = 0;

				while (length >= 8)
				{
					const u64 value = read_from_ptr<u64>(marker, offset);
					const u64 block_mask = ~value;              // If the value is not all 1s, set valid to true
					mask |= block_mask;
					write_to_ptr<u64>(marker, offset, umax);

					offset += 8;
					length -= 8;
				}

				if (length >= 4)
				{
					const u32 value = read_from_ptr<u32>(marker, offset);
					const u32 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u32>(marker, offset, umax);

					offset += 4;
					length -= 4;
				}

				if (length >= 2)
				{
					const u16 value = read_from_ptr<u16>(marker, offset);
					const u16 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u16>(marker, offset, umax);

					offset += 2;
					length -= 2;
				}

				if (length)
				{
					const u8 value = read_from_ptr<u8>(marker, offset);
					const u8 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u8>(marker, offset, umax);
				}

				return !!mask;
			};

			Result result;result.storageBytes=marker.size()*sizeof(marker[0]);for(auto [start,len]:spans)result.changed.push_back(compare_and_tag_row(start,len));
for(u32 i=0;i<range.length();++i){result.covered.push_back(marker[i]!=0);}
return result;}
};
#define RPCS3_IOS
struct after : Boundary {
void remove_duplicates_fallback_impl(rsx::simple_array<surface_overlap_info>& sections, const rsx::address_range32& range)
		{
			// Originally used to debug crashes but this function breaks often enough that I'll leave the checks in for now.
			// Safe to remove after some time if no asserts are reported.
			constexpr u32 overrun_cookie_value = 0xCAFEBABEu;

			// Generic painter's algorithm to detect obsolete sections
			ensure(range.length() < 64 * 0x100000);
#ifdef RPCS3_IOS
			// Coverage is boolean per guest byte. A packed bitmap avoids clearing
			// and streaming a full byte for every byte of the surface address span.
			std::vector<u64> marker((range.length() + 63u) / 64u + 1u, 0);
			marker.back() = overrun_cookie_value;
			u32 removed_count = 0;
			auto compare_and_tag_row = [&](u32 offset, u32 length) -> bool
			{
				ensure(offset <= range.length() && length <= range.length() - offset);
				if (!length) return false;

				const u32 first = offset / 64u;
				const u32 last = (offset + length - 1u) / 64u;
				const u64 first_mask = ~u64{0} << (offset & 63u);
				const u64 last_mask = ~u64{0} >> ((64u - ((offset + length) & 63u)) & 63u);
				u64 uncovered = 0;
				auto tag = [&](u32 word, u64 mask)
				{
					uncovered |= ~marker[word] & mask;
					marker[word] |= mask;
				};
				if (first == last)
				{
					tag(first, first_mask & last_mask);
				}
				else
				{
					tag(first, first_mask);
					for (u32 word = first + 1u; word < last; ++word)
					{
						tag(word, ~u64{0});
					}
					tag(last, last_mask);
				}
				return uncovered != 0;
			};
#else
			std::vector<u8> marker(range.length() + sizeof(overrun_cookie_value), 0);

			// Tag end
			write_to_ptr(marker, range.length(), overrun_cookie_value);

			u32 removed_count = 0;

			auto compare_and_tag_row = [&](u32 offset, u32 length) -> bool
			{
				u64 mask = 0;

				while (length >= 8)
				{
					const u64 value = read_from_ptr<u64>(marker, offset);
					const u64 block_mask = ~value;              // If the value is not all 1s, set valid to true
					mask |= block_mask;
					write_to_ptr<u64>(marker, offset, umax);

					offset += 8;
					length -= 8;
				}

				if (length >= 4)
				{
					const u32 value = read_from_ptr<u32>(marker, offset);
					const u32 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u32>(marker, offset, umax);

					offset += 4;
					length -= 4;
				}

				if (length >= 2)
				{
					const u16 value = read_from_ptr<u16>(marker, offset);
					const u16 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u16>(marker, offset, umax);

					offset += 2;
					length -= 2;
				}

				if (length)
				{
					const u8 value = read_from_ptr<u8>(marker, offset);
					const u8 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u8>(marker, offset, umax);
				}

				return !!mask;
			};
#endif

			for (auto it = sections.crbegin(); it != sections.crend(); ++it)
			{
				auto this_range = it->surface->get_memory_range();
				ensure(this_range.overlaps(range));

				const auto native_pitch = it->surface->template get_surface_width<rsx::surface_metrics::bytes>();
				const auto rsx_pitch = it->surface->get_rsx_pitch();
				auto num_rows = it->surface->template get_surface_height<rsx::surface_metrics::samples>();
				bool valid = false;

				if (this_range.start < range.start)
				{
					// Starts outside bounds
					const auto internal_offset = (range.start - this_range.start);
					const auto row_num = internal_offset / rsx_pitch;
					const auto row_offset = internal_offset % rsx_pitch;

					// This section is unconditionally valid
					valid = true;

					if (row_offset < native_pitch)
					{
						compare_and_tag_row(0, std::min(native_pitch - row_offset, range.length()));
					}

					// Jump to next row...
					this_range.start = this_range.start + (row_num + 1) * rsx_pitch;
				}

				if (this_range.end > range.end)
				{
					// Unconditionally valid
					valid = true;
					this_range.end = range.end;
				}

				if (valid)
				{
					if (this_range.start >= this_range.end)
					{
						continue;
					}

					num_rows = utils::aligned_div(this_range.length(), rsx_pitch);
				}

				for (u32 row = 0, offset = (this_range.start - range.start), section_len = (this_range.end - range.start + 1);
					row < num_rows;
					++row, offset += rsx_pitch)
				{
					valid |= compare_and_tag_row(offset, std::min<u32>(native_pitch, (section_len - offset)));
				}

				if (!valid)
				{
					removed_count++;
					rsx_log.warning("Stale surface at address 0x%x will be deleted", it->base_address);
					invalidate_surface_address(it->base_address, it->is_depth);
				}
			}

			// Notify
			rsx_log.notice("rsx::surface_cache::check_for_duplicates_fallback analysed %u overlapping sections and removed %u", ::size32(sections), removed_count);

			// Verify no OOB
#ifdef RPCS3_IOS
			ensure(marker.back() == overrun_cookie_value);
#else
			ensure(read_from_ptr<u32>(marker, range.length()) == overrun_cookie_value);
#endif
		}
Result rows(const address_range32& range,const std::vector<std::pair<u32,u32>>& spans){
constexpr u32 overrun_cookie_value = 0xCAFEBABEu;

			// Generic painter's algorithm to detect obsolete sections
			ensure(range.length() < 64 * 0x100000);
#ifdef RPCS3_IOS
			// Coverage is boolean per guest byte. A packed bitmap avoids clearing
			// and streaming a full byte for every byte of the surface address span.
			std::vector<u64> marker((range.length() + 63u) / 64u + 1u, 0);
			marker.back() = overrun_cookie_value;
			[[maybe_unused]] u32 removed_count = 0;
			auto compare_and_tag_row = [&](u32 offset, u32 length) -> bool
			{
				ensure(offset <= range.length() && length <= range.length() - offset);
				if (!length) return false;

				const u32 first = offset / 64u;
				const u32 last = (offset + length - 1u) / 64u;
				const u64 first_mask = ~u64{0} << (offset & 63u);
				const u64 last_mask = ~u64{0} >> ((64u - ((offset + length) & 63u)) & 63u);
				u64 uncovered = 0;
				auto tag = [&](u32 word, u64 mask)
				{
					uncovered |= ~marker[word] & mask;
					marker[word] |= mask;
				};
				if (first == last)
				{
					tag(first, first_mask & last_mask);
				}
				else
				{
					tag(first, first_mask);
					for (u32 word = first + 1u; word < last; ++word)
					{
						tag(word, ~u64{0});
					}
					tag(last, last_mask);
				}
				return uncovered != 0;
			};
#else
			std::vector<u8> marker(range.length() + sizeof(overrun_cookie_value), 0);

			// Tag end
			write_to_ptr(marker, range.length(), overrun_cookie_value);

			[[maybe_unused]] u32 removed_count = 0;

			auto compare_and_tag_row = [&](u32 offset, u32 length) -> bool
			{
				u64 mask = 0;

				while (length >= 8)
				{
					const u64 value = read_from_ptr<u64>(marker, offset);
					const u64 block_mask = ~value;              // If the value is not all 1s, set valid to true
					mask |= block_mask;
					write_to_ptr<u64>(marker, offset, umax);

					offset += 8;
					length -= 8;
				}

				if (length >= 4)
				{
					const u32 value = read_from_ptr<u32>(marker, offset);
					const u32 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u32>(marker, offset, umax);

					offset += 4;
					length -= 4;
				}

				if (length >= 2)
				{
					const u16 value = read_from_ptr<u16>(marker, offset);
					const u16 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u16>(marker, offset, umax);

					offset += 2;
					length -= 2;
				}

				if (length)
				{
					const u8 value = read_from_ptr<u8>(marker, offset);
					const u8 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u8>(marker, offset, umax);
				}

				return !!mask;
			};
#endif

			Result result;result.storageBytes=marker.size()*sizeof(marker[0]);for(auto [start,len]:spans)result.changed.push_back(compare_and_tag_row(start,len));
for(u32 i=0;i<range.length();++i){result.covered.push_back(((marker[i/64]>>(i%64))&1)!=0);}
return result;}
};
#undef RPCS3_IOS
struct desktop : Boundary {
void remove_duplicates_fallback_impl(rsx::simple_array<surface_overlap_info>& sections, const rsx::address_range32& range)
		{
			// Originally used to debug crashes but this function breaks often enough that I'll leave the checks in for now.
			// Safe to remove after some time if no asserts are reported.
			constexpr u32 overrun_cookie_value = 0xCAFEBABEu;

			// Generic painter's algorithm to detect obsolete sections
			ensure(range.length() < 64 * 0x100000);
#ifdef RPCS3_IOS
			// Coverage is boolean per guest byte. A packed bitmap avoids clearing
			// and streaming a full byte for every byte of the surface address span.
			std::vector<u64> marker((range.length() + 63u) / 64u + 1u, 0);
			marker.back() = overrun_cookie_value;
			u32 removed_count = 0;
			auto compare_and_tag_row = [&](u32 offset, u32 length) -> bool
			{
				ensure(offset <= range.length() && length <= range.length() - offset);
				if (!length) return false;

				const u32 first = offset / 64u;
				const u32 last = (offset + length - 1u) / 64u;
				const u64 first_mask = ~u64{0} << (offset & 63u);
				const u64 last_mask = ~u64{0} >> ((64u - ((offset + length) & 63u)) & 63u);
				u64 uncovered = 0;
				auto tag = [&](u32 word, u64 mask)
				{
					uncovered |= ~marker[word] & mask;
					marker[word] |= mask;
				};
				if (first == last)
				{
					tag(first, first_mask & last_mask);
				}
				else
				{
					tag(first, first_mask);
					for (u32 word = first + 1u; word < last; ++word)
					{
						tag(word, ~u64{0});
					}
					tag(last, last_mask);
				}
				return uncovered != 0;
			};
#else
			std::vector<u8> marker(range.length() + sizeof(overrun_cookie_value), 0);

			// Tag end
			write_to_ptr(marker, range.length(), overrun_cookie_value);

			u32 removed_count = 0;

			auto compare_and_tag_row = [&](u32 offset, u32 length) -> bool
			{
				u64 mask = 0;

				while (length >= 8)
				{
					const u64 value = read_from_ptr<u64>(marker, offset);
					const u64 block_mask = ~value;              // If the value is not all 1s, set valid to true
					mask |= block_mask;
					write_to_ptr<u64>(marker, offset, umax);

					offset += 8;
					length -= 8;
				}

				if (length >= 4)
				{
					const u32 value = read_from_ptr<u32>(marker, offset);
					const u32 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u32>(marker, offset, umax);

					offset += 4;
					length -= 4;
				}

				if (length >= 2)
				{
					const u16 value = read_from_ptr<u16>(marker, offset);
					const u16 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u16>(marker, offset, umax);

					offset += 2;
					length -= 2;
				}

				if (length)
				{
					const u8 value = read_from_ptr<u8>(marker, offset);
					const u8 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u8>(marker, offset, umax);
				}

				return !!mask;
			};
#endif

			for (auto it = sections.crbegin(); it != sections.crend(); ++it)
			{
				auto this_range = it->surface->get_memory_range();
				ensure(this_range.overlaps(range));

				const auto native_pitch = it->surface->template get_surface_width<rsx::surface_metrics::bytes>();
				const auto rsx_pitch = it->surface->get_rsx_pitch();
				auto num_rows = it->surface->template get_surface_height<rsx::surface_metrics::samples>();
				bool valid = false;

				if (this_range.start < range.start)
				{
					// Starts outside bounds
					const auto internal_offset = (range.start - this_range.start);
					const auto row_num = internal_offset / rsx_pitch;
					const auto row_offset = internal_offset % rsx_pitch;

					// This section is unconditionally valid
					valid = true;

					if (row_offset < native_pitch)
					{
						compare_and_tag_row(0, std::min(native_pitch - row_offset, range.length()));
					}

					// Jump to next row...
					this_range.start = this_range.start + (row_num + 1) * rsx_pitch;
				}

				if (this_range.end > range.end)
				{
					// Unconditionally valid
					valid = true;
					this_range.end = range.end;
				}

				if (valid)
				{
					if (this_range.start >= this_range.end)
					{
						continue;
					}

					num_rows = utils::aligned_div(this_range.length(), rsx_pitch);
				}

				for (u32 row = 0, offset = (this_range.start - range.start), section_len = (this_range.end - range.start + 1);
					row < num_rows;
					++row, offset += rsx_pitch)
				{
					valid |= compare_and_tag_row(offset, std::min<u32>(native_pitch, (section_len - offset)));
				}

				if (!valid)
				{
					removed_count++;
					rsx_log.warning("Stale surface at address 0x%x will be deleted", it->base_address);
					invalidate_surface_address(it->base_address, it->is_depth);
				}
			}

			// Notify
			rsx_log.notice("rsx::surface_cache::check_for_duplicates_fallback analysed %u overlapping sections and removed %u", ::size32(sections), removed_count);

			// Verify no OOB
#ifdef RPCS3_IOS
			ensure(marker.back() == overrun_cookie_value);
#else
			ensure(read_from_ptr<u32>(marker, range.length()) == overrun_cookie_value);
#endif
		}
Result rows(const address_range32& range,const std::vector<std::pair<u32,u32>>& spans){
constexpr u32 overrun_cookie_value = 0xCAFEBABEu;

			// Generic painter's algorithm to detect obsolete sections
			ensure(range.length() < 64 * 0x100000);
#ifdef RPCS3_IOS
			// Coverage is boolean per guest byte. A packed bitmap avoids clearing
			// and streaming a full byte for every byte of the surface address span.
			std::vector<u64> marker((range.length() + 63u) / 64u + 1u, 0);
			marker.back() = overrun_cookie_value;
			[[maybe_unused]] u32 removed_count = 0;
			auto compare_and_tag_row = [&](u32 offset, u32 length) -> bool
			{
				ensure(offset <= range.length() && length <= range.length() - offset);
				if (!length) return false;

				const u32 first = offset / 64u;
				const u32 last = (offset + length - 1u) / 64u;
				const u64 first_mask = ~u64{0} << (offset & 63u);
				const u64 last_mask = ~u64{0} >> ((64u - ((offset + length) & 63u)) & 63u);
				u64 uncovered = 0;
				auto tag = [&](u32 word, u64 mask)
				{
					uncovered |= ~marker[word] & mask;
					marker[word] |= mask;
				};
				if (first == last)
				{
					tag(first, first_mask & last_mask);
				}
				else
				{
					tag(first, first_mask);
					for (u32 word = first + 1u; word < last; ++word)
					{
						tag(word, ~u64{0});
					}
					tag(last, last_mask);
				}
				return uncovered != 0;
			};
#else
			std::vector<u8> marker(range.length() + sizeof(overrun_cookie_value), 0);

			// Tag end
			write_to_ptr(marker, range.length(), overrun_cookie_value);

			[[maybe_unused]] u32 removed_count = 0;

			auto compare_and_tag_row = [&](u32 offset, u32 length) -> bool
			{
				u64 mask = 0;

				while (length >= 8)
				{
					const u64 value = read_from_ptr<u64>(marker, offset);
					const u64 block_mask = ~value;              // If the value is not all 1s, set valid to true
					mask |= block_mask;
					write_to_ptr<u64>(marker, offset, umax);

					offset += 8;
					length -= 8;
				}

				if (length >= 4)
				{
					const u32 value = read_from_ptr<u32>(marker, offset);
					const u32 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u32>(marker, offset, umax);

					offset += 4;
					length -= 4;
				}

				if (length >= 2)
				{
					const u16 value = read_from_ptr<u16>(marker, offset);
					const u16 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u16>(marker, offset, umax);

					offset += 2;
					length -= 2;
				}

				if (length)
				{
					const u8 value = read_from_ptr<u8>(marker, offset);
					const u8 block_mask = ~value;
					mask |= block_mask;
					write_to_ptr<u8>(marker, offset, umax);
				}

				return !!mask;
			};
#endif

			Result result;result.storageBytes=marker.size()*sizeof(marker[0]);for(auto [start,len]:spans)result.changed.push_back(compare_and_tag_row(start,len));
for(u32 i=0;i<range.length();++i){result.covered.push_back(marker[i]!=0);}
return result;}
};

u64 rowChecks=0,geometryChecks=0,sink=0;
void rows(u32 length,const std::vector<std::pair<u32,u32>>& spans){
 auto range=address_range32::start_length(0x100000,length);before a;after b;desktop c;
 auto x=a.rows(range,spans),y=b.rows(range,spans),z=c.rows(range,spans);
 assert(x.changed==y.changed&&x.covered==y.covered&&x.changed==z.changed&&x.covered==z.covered);rowChecks+=spans.size();
}
void geometry(std::vector<Surface>& surfaces,const address_range32& range){
 std::vector<surface_overlap_info> sections;for(auto& s:surfaces){assert(s.get_memory_range().overlaps(range));sections.push_back({&s,s.address,(s.address&4)!=0});}
 before a;after b;desktop c;a.remove_duplicates_fallback_impl(sections,range);b.remove_duplicates_fallback_impl(sections,range);c.remove_duplicates_fallback_impl(sections,range);
 assert(a.invalidated==b.invalidated&&a.invalidated==c.invalidated);++geometryChecks;
}
template<class T>double bench(u32 length,u32 width,u32 pitch){
 std::vector<Surface> surfaces(12,Surface{0x100000,width,pitch,(length-width)/pitch+1});std::vector<surface_overlap_info> sections;
 for(auto& s:surfaces){sections.push_back({&s,s.address,false});}
 auto range=surfaces.front().get_memory_range();
 std::vector<double> samples;T test;constexpr int iterations=8;
 for(int round=0;round<5;++round){auto start=std::chrono::steady_clock::now();for(int i=0;i<iterations;++i){test.invalidated.clear();test.remove_duplicates_fallback_impl(sections,range);sink+=test.invalidated.size();}samples.push_back(std::chrono::duration<double,std::micro>(std::chrono::steady_clock::now()-start).count()/iterations);}
 std::sort(samples.begin(),samples.end());return samples[2];
}
int main(int argc,char**){
 for(u32 length:{1u,7u,8u,63u,64u,65u,127u,128u,129u,257u}){
  std::vector<std::pair<u32,u32>> spans;
  for(u32 start=0;start<=length;++start)for(u32 n=0;n<=length-start;++n){
   spans.emplace_back(start,n);spans.emplace_back(start,n);
   // Fresh coverage keeps every pair observable instead of saturating the
   // bitmap before testing later offsets and trailing masks.
   rows(length,{{start,n},{start,n}});
  }
  rows(length,spans);
  for(u32 start=0;start<length;++start){rows(length,{{start,1},{0,start},{start+1,length-start-1},{0,length}});}
 }
 rows(129,{{1,127},{0,1},{128,1},{0,129}});
 constexpr u32 max_span=64u*1024u*1024u-1u;
 rows(max_span,{{0,1},{63,65},{max_span-129,128},{max_span-65,64},{max_span-1,1},{max_span,0}});
 std::mt19937 random(595);
 for(int i=0;i<2000;++i){u32 length=1+random()%4096;std::vector<std::pair<u32,u32>> spans;for(int j=0;j<64;++j){u32 start=random()%(length+1);spans.emplace_back(start,random()%(length-start+1));}rows(length,spans);}
 for(int i=0;i<10000;++i){
  std::vector<Surface> surfaces;u32 low=~u32{0},high=0;auto base=(i%2)?0x100000u:0xffff0000u;
  for(u32 j=0,n=1+random()%32;j<n;++j){u32 width=1+random()%192,pitch=width+random()%65,height=1+random()%24,address=base+random()%4096;surfaces.push_back({address,width,pitch,height});low=std::min(low,address);high=std::max(high,surfaces.back().get_memory_range().end);}
  geometry(surfaces,address_range32::start_end(low,high));
 }
 // Explicit partial rows outside the tested range and multi-byte boundaries.
 for(u32 offset=0;offset<128;++offset){std::vector<Surface>s{{1000,80,128,4},{1000+offset,70,128,4},{1120,45,64,5}};geometry(s,address_range32::start_length(1128,256));}
 before a;after b;std::vector<std::pair<u32,u32>> spans{{0,4194304},{7,131}};auto range=address_range32::start_length(0x100000,4194304);auto x=a.rows(range,spans),y=b.rows(range,spans);assert(x.covered==y.covered);
 std::cout<<"{\"rowChecks\":"<<rowChecks<<",\"surfaceGeometryCases\":"<<geometryChecks<<",\"sameInvalidationsAndOrder\":true,\"baseline4MiBMarkerBytes\":"<<x.storageBytes<<",\"candidate4MiBMarkerBytes\":"<<y.storageBytes;
 if(argc>1){std::cout<<",\"benchmarks\":[";bool first=true;for(u32 length:{65536u,1048576u,8388608u})for(u32 width:{16u,256u,4096u}){if(!first)std::cout<<',';first=false;std::cout<<"{\"spanBytes\":"<<length<<",\"rowBytes\":"<<width<<",\"baselineUs\":"<<bench<before>(length,width,width*2)<<",\"candidateUs\":"<<bench<after>(length,width,width*2)<<"}";}std::cout<<']';}
 std::cout<<",\"sink\":"<<sink<<"}";
}
