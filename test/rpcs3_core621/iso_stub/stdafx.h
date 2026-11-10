// Host stub of RPCS3's precompiled header for the REWINDBOX_ISO_IMAGE_LIFETIME_621
// test: only what rpcs3/Loader/ISO.cpp uses, backed by POSIX files.
#pragma once

#include <algorithm>
#include <array>
#include <bit>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <memory>
#include <optional>
#include <stdexcept>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

using namespace std::literals;

using u8 = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s8 = std::int8_t;
using s16 = std::int16_t;
using s32 = std::int32_t;
using s64 = std::int64_t;
using usz = std::size_t;

struct umax_t
{
	template <typename T>
	constexpr operator T() const noexcept { return static_cast<T>(~T{}); }
	template <typename T>
	friend constexpr bool operator==(const T& value, umax_t) noexcept { return value == static_cast<T>(~T{}); }
};
inline constexpr umax_t umax{};

template <typename T>
T ensure(T&& value, const char* = nullptr)
{
	if (!value) throw std::runtime_error("ensure() failed");
	return std::forward<T>(value);
}

template <typename C>
auto& at32(C& container, std::size_t index)
{
	if (index >= container.size()) throw std::out_of_range("at32");
	return container[index];
}

template <typename T>
struct be_t
{
	u8 raw[sizeof(T)];
	operator T() const noexcept
	{
		T value{};
		for (std::size_t i = 0; i < sizeof(T); ++i) value = static_cast<T>((value << 8) | raw[i]);
		return value;
	}
};

template <typename T, typename C>
T read_from_ptr(const C& data, std::size_t offset = 0)
{
	T value;
	std::memcpy(&value, data.data() + offset, sizeof(T));
	return value;
}

namespace utils
{
template <typename T, typename U>
T* bless(U* pointer) noexcept { return reinterpret_cast<T*>(pointer); }
}

template <typename T>
struct bs_t
{
	u32 bits = 0;
	constexpr bs_t() = default;
	constexpr explicit bs_t(u32 value) : bits(value) {}
	constexpr bs_t operator+(bs_t other) const noexcept { return bs_t(bits | other.bits); }
	constexpr bool operator&(bs_t other) const noexcept { return (bits & other.bits) != 0; }
};

// Log channels: the test reads the last error instead of a log file.
struct log_channel
{
	const char* name;
	template <typename... Args> void error(const char* format, const Args&...) const { last_error() = format; }
	template <typename... Args> void warning(const char*, const Args&...) const {}
	template <typename... Args> void notice(const char*, const Args&...) const {}
	template <typename... Args> void success(const char*, const Args&...) const {}
	template <typename... Args> void todo(const char*, const Args&...) const {}
	static std::string& last_error() { static thread_local std::string value; return value; }
};
#define LOG_CHANNEL(name, ...) static const log_channel name{#name}

namespace stx
{
template <typename T> using shared_ptr = std::shared_ptr<T>;
template <typename T, typename... Args> std::shared_ptr<T> make_shared(Args&&... args) { return std::make_shared<T>(std::forward<Args>(args)...); }
}

inline void hex_to_bytes(u8*, std::string_view, std::size_t, std::string* error) { if (error) *error = "unsupported in the host test"; }

// Joliet names (UCS-2): ASCII-only conversion is enough for the generated images.
inline std::string utf16_to_utf8(std::u16string_view text)
{
	std::string result;
	for (const char16_t c : text) result += c < 0x80 ? static_cast<char>(c) : '?';
	return result;
}
