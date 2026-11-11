// Stand-in for the engine's Utilities/File.h in the REWINDBOX_LOCAL_PROFILE_933 host harness: the calls the profile
// store makes, over a temporary directory, with the same atomic write (a temporary file renamed over the target on
// commit; a pending file that is not committed leaves the target as it was). A write can be made to fail.
#pragma once

#include <cstdint>
#include <cstdio>
#include <filesystem>
#include <string>
#include <string_view>

namespace fs
{
using u64 = std::uint64_t;

inline std::string config_root;   // set by the harness: a fresh temporary directory per scenario
inline bool fail_writes = false;  // the next pending files cannot be written
inline unsigned commits = 0;      // committed pending files

inline const std::string& get_config_dir(bool get_config_subdirectory = false)
{
	static std::string path;
	path = config_root + (get_config_subdirectory ? "config/" : "");
	return path;
}

inline bool create_path(const std::string& path)
{
	std::error_code error;
	std::filesystem::create_directories(path, error);
	return !error && std::filesystem::is_directory(path, error);
}

inline bool is_file(const std::string& path)
{
	std::error_code error;
	return std::filesystem::is_regular_file(path, error);
}

inline constexpr unsigned read = 1, write = 2;

class file
{
	std::FILE* m_file = nullptr;

public:
	file() = default;
	explicit file(const std::string& path, unsigned mode = read) { m_file = std::fopen(path.c_str(), mode == read ? "rb" : "wb"); }
	file(const file&) = delete;
	file& operator=(const file&) = delete;
	file(file&& other) noexcept : m_file(other.m_file) { other.m_file = nullptr; }
	file& operator=(file&& other) noexcept
	{
		close();
		m_file = other.m_file;
		other.m_file = nullptr;
		return *this;
	}
	~file() { close(); }

	void close()
	{
		if (m_file)
		{
			std::fclose(m_file);
			m_file = nullptr;
		}
	}

	explicit operator bool() const { return m_file != nullptr; }

	u64 size() const
	{
		const long position = std::ftell(m_file);
		std::fseek(m_file, 0, SEEK_END);
		const long end = std::ftell(m_file);
		std::fseek(m_file, position, SEEK_SET);
		return end < 0 ? 0 : static_cast<u64>(end);
	}

	std::string to_string() const
	{
		std::string text(static_cast<std::size_t>(size()), '\0');
		std::fseek(m_file, 0, SEEK_SET);
		const std::size_t read_bytes = text.empty() ? 0 : std::fread(text.data(), 1, text.size(), m_file);
		text.resize(read_bytes);
		return text;
	}

	u64 write(const void* buffer, u64 count) const { return std::fwrite(buffer, 1, static_cast<std::size_t>(count), m_file); }
};

struct pending_file
{
	fs::file file{};

	explicit pending_file(std::string_view path)
	{
		m_target = std::string{path};
		m_temporary = m_target + ".pending";
		if (!fail_writes)
		{
			file = fs::file{m_temporary, write};
		}
	}

	pending_file(const pending_file&) = delete;
	pending_file& operator=(const pending_file&) = delete;

	bool commit(bool = true)
	{
		if (!file)
		{
			return false;
		}
		file.close();
		std::error_code error;
		std::filesystem::rename(m_temporary, m_target, error);
		if (error)
		{
			return false;
		}
		commits++;
		return true;
	}

	~pending_file()
	{
		file.close();
		std::error_code error;
		std::filesystem::remove(m_temporary, error);
	}

private:
	std::string m_target, m_temporary;
};
} // namespace fs
