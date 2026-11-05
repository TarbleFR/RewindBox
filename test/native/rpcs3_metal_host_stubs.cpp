// REWINDBOX_METAL_NATIVE (M2): host-only stand-ins for the RPCS3 runtime pieces the shader stack test links
// against but never runs (file logging, config saving, thread control). Each stand-in that is not expected to
// run stops the test loudly instead of pretending to work; log messages are printed to stderr.

#include "stdafx.h"

#include "Emu/RSX/Metal/MTLAPI.h"
#include "Emu/system_config.h"
#include "Utilities/File.h"
#include "Utilities/cheat_info.h"
#include "Utilities/Thread.h"
#include "util/logs.hpp"
#include "util/sysinfo.hpp"

#include <cstdarg>
#include <cstdio>
#include <cstdlib>

namespace
{
	[[noreturn]] void unexpected(const char* what)
	{
		std::fprintf(stderr, "FAIL: the shader stack test reached %s, which the host test does not provide\n", what);
		std::abort();
	}
}

// mtl::object without Objective-C: the host test only ever holds null objects (no Metal device on the host).
namespace mtl
{
	object::object(const object& other) noexcept
		: m_ptr(other.m_ptr)
	{
		if (m_ptr) unexpected("a Metal object copy");
	}

	object& object::operator=(const object& other) noexcept
	{
		if (other.m_ptr) unexpected("a Metal object copy");
		m_ptr = nullptr;
		return *this;
	}

	object::object(object&& other) noexcept
		: m_ptr(other.m_ptr)
	{
		other.m_ptr = nullptr;
	}

	object& object::operator=(object&& other) noexcept
	{
		if (other.m_ptr) unexpected("a Metal object move");
		m_ptr = nullptr;
		return *this;
	}

	object::~object()
	{
		if (m_ptr) unexpected("a Metal object release");
	}

	object object::adopt(void* retained) noexcept
	{
		if (retained) unexpected("a Metal object");
		return {};
	}

	object object::retain(void* unretained) noexcept
	{
		if (unretained) unexpected("a Metal object");
		return {};
	}

	void object::reset() noexcept
	{
		if (m_ptr) unexpected("a Metal object release");
	}
}

namespace logs
{
	registerer::registerer(channel&)
	{
	}

	void message::broadcast(const char* fmt, const fmt_type_info* sup, ...) const
	{
		// Format the message the RPCS3 way (fmt::raw_append) with the packed arguments.
		std::va_list args;
		va_start(args, sup);
		std::vector<u64> packed;
		if (sup)
		{
			for (const fmt_type_info* info = sup; info->fmt_string; ++info)
			{
				packed.push_back(va_arg(args, u64));
			}
		}
		va_end(args);

		static constexpr fmt_type_info empty_sup{};
		std::string text;
		fmt::raw_append(text, fmt, sup ? sup : &empty_sup, packed.data());
		std::fprintf(stderr, "[%s] %s\n", (*this)->name, text.c_str());
	}
}

namespace fs
{
	[[noreturn]] void xnull(std::source_location)
	{
		unexpected("fs::xnull");
	}

	[[noreturn]] void xfail(std::source_location)
	{
		unexpected("fs::xfail");
	}

	const std::string& get_cache_dir()
	{
		unexpected("fs::get_cache_dir (shader logging)");
	}

	file::file(const std::string&, bs_t<open_mode>)
	{
		unexpected("fs::file (shader logging)");
	}

	pending_file::~pending_file()
	{
	}

	bool pending_file::open(std::string_view)
	{
		unexpected("fs::pending_file::open (config saving)");
	}

	bool pending_file::commit(bool)
	{
		unexpected("fs::pending_file::commit (config saving)");
	}
}

[[noreturn]] void thread_ctrl::emergency_exit(std::string_view reason)
{
	std::fprintf(stderr, "FAIL: emergency exit: %.*s\n", static_cast<int>(reason.size()), reason.data());
	std::abort();
}

namespace utils
{
	u64 _get_main_tid()
	{
		return 0;
	}

	bool has_avx()
	{
		return false;
	}
}

// Enum formatters of modules the host test does not link (used only to print config values).
template <>
void fmt_class_string<CellKbMappingType>::format(std::string& out, u64 arg)
{
	out += std::to_string(static_cast<s64>(arg));
}

template <>
void fmt_class_string<CellSysutilLang>::format(std::string& out, u64 arg)
{
	out += std::to_string(static_cast<s64>(arg));
}

template <>
void fmt_class_string<CellSysutilLicenseArea>::format(std::string& out, u64 arg)
{
	out += std::to_string(static_cast<s64>(arg));
}

template <>
void fmt_class_string<cheat_type>::format(std::string& out, u64 arg)
{
	out += std::to_string(arg);
}

template <>
void fmt_class_string<logs::level>::format(std::string& out, u64 arg)
{
	out += std::to_string(arg);
}
