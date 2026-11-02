// Host stub of RPCS3's fs:: layer for the REWINDBOX_ISO_IMAGE_LIFETIME_621 test.
// Same API shape as Utilities/File.h for what Loader/ISO.cpp uses, backed by
// POSIX open/pread. As in RPCS3 (File.h xnull), any I/O on a null fs::file
// throws "Null object.", which is how a failed per-file reopen surfaced.
#pragma once

#include "stdafx.h"

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <atomic>
#include <cerrno>
#include <functional>

namespace fs
{
enum class error : u32 { ok = 0, inval, noent, exist, acces, notempty, readonly, isdir, notdir, toolong, nospace, xdev, unknown };
inline thread_local error g_tls_error = error::ok;

enum class open_mode : u32 { read, write };
inline constexpr bs_t<open_mode> read{1};
inline constexpr bs_t<open_mode> write{2};

enum seek_mode : u32 { seek_set, seek_cur, seek_end };
inline constexpr auto delim = "/";

struct stat_t
{
	bool is_directory = false, is_symlink = false, is_writable = false;
	u64 size = 0;
	s64 atime = 0, mtime = 0, ctime = 0;
};

struct dir_entry : stat_t
{
	std::string name{};
};

struct device_stat
{
	u64 block_size = 0, total_size = 0, total_free = 0, avail_free = 0;
};

struct file_base
{
	virtual ~file_base() = default;
	virtual stat_t get_stat() { throw std::runtime_error("get_stat unsupported"); }
	virtual bool trunc(u64 length) = 0;
	virtual u64 read(void* buffer, u64 size) = 0;
	virtual u64 read_at(u64 offset, void* buffer, u64 size) = 0;
	virtual u64 write(const void* buffer, u64 size) = 0;
	virtual u64 seek(s64 offset, seek_mode whence) = 0;
	virtual u64 size() = 0;
	virtual void release() {}
};

struct dir_base
{
	virtual ~dir_base() = default;
	virtual bool read(dir_entry&) = 0;
	virtual void rewind() = 0;
};

// Every POSIX descriptor this stub opened and has not closed yet (the test
// checks that unmounting releases the image).
inline std::atomic<int>& open_descriptors()
{
	static std::atomic<int> value{0};
	return value;
}

class posix_file final : public file_base
{
	int m_fd;
	u64 m_pos = 0;

public:
	explicit posix_file(int fd) : m_fd(fd) { open_descriptors()++; }
	~posix_file() override { ::close(m_fd); open_descriptors()--; }

	stat_t get_stat() override
	{
		struct ::stat info{};
		::fstat(m_fd, &info);
		stat_t result;
		result.size = static_cast<u64>(info.st_size);
		return result;
	}
	bool trunc(u64) override { g_tls_error = error::readonly; return false; }
	u64 read(void* buffer, u64 size) override
	{
		const u64 result = read_at(m_pos, buffer, size);
		m_pos += result;
		return result;
	}
	u64 read_at(u64 offset, void* buffer, u64 size) override
	{
		const ssize_t result = ::pread(m_fd, buffer, size, static_cast<off_t>(offset));
		if (result < 0) throw std::runtime_error("pread failed");
		return static_cast<u64>(result);
	}
	u64 write(const void*, u64) override { g_tls_error = error::readonly; return 0; }
	u64 seek(s64 offset, seek_mode whence) override
	{
		const s64 position = whence == seek_set ? offset : whence == seek_cur ? offset + static_cast<s64>(m_pos) : offset + static_cast<s64>(size());
		if (position < 0) { g_tls_error = error::inval; return umax; }
		m_pos = static_cast<u64>(position);
		return m_pos;
	}
	u64 size() override
	{
		struct ::stat info{};
		::fstat(m_fd, &info);
		return static_cast<u64>(info.st_size);
	}
};

class file
{
	std::unique_ptr<file_base> m_file;

	file_base& get() const
	{
		if (!m_file) throw std::runtime_error("Null object.");
		return *m_file;
	}

public:
	file() = default;
	file(const std::string& path, bs_t<open_mode> = fs::read)
	{
		const int fd = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
		if (fd < 0)
		{
			g_tls_error = errno == ENOENT ? error::noent : error::unknown;
			return;
		}
		m_file = std::make_unique<posix_file>(fd);
	}
	file(std::unique_ptr<file_base>&& base) : m_file(std::move(base)) {}

	explicit operator bool() const noexcept { return m_file != nullptr; }

	stat_t get_stat() const { return get().get_stat(); }
	u64 read(void* buffer, u64 count) const { return get().read(buffer, count); }
	u64 read_at(u64 offset, void* buffer, u64 count) const { return get().read_at(offset, buffer, count); }
	u64 seek(s64 offset, seek_mode whence = seek_set) const { return get().seek(offset, whence); }
	u64 size() const { return get().size(); }
	u64 pos() const { return get().seek(0, seek_cur); }
	void release() { if (m_file) m_file->release(); }

	template <typename T>
	T read() const
	{
		T value{};
		if (read(&value, sizeof(T)) != sizeof(T)) throw std::runtime_error("short read");
		return value;
	}

	bool read(std::string& out, u64 count) const
	{
		out.resize(count);
		return read(out.data(), count) == count;
	}
};

struct device_base
{
	std::string fs_prefix;
	virtual ~device_base() = default;
	virtual bool stat(const std::string& path, stat_t& info) = 0;
	virtual bool statfs(const std::string& path, device_stat& info) = 0;
	virtual std::unique_ptr<file_base> open(const std::string& path, bs_t<open_mode> mode) = 0;
	virtual std::unique_ptr<dir_base> open_dir(const std::string& path) = 0;
};

// The global virtual device table of RPCS3 (File.cpp set_device).
inline std::map<std::string, std::shared_ptr<device_base>>& virtual_devices()
{
	static std::map<std::string, std::shared_ptr<device_base>> value;
	return value;
}

inline void set_virtual_device(const std::string& name, std::shared_ptr<device_base> device)
{
	if (device) virtual_devices()[name] = std::move(device);
	else virtual_devices().erase(name);
}

inline bool get_optical_raw_device(const std::string&, std::string* = nullptr) { return false; }
inline bool is_optical_raw_device(const std::string&) { return false; }
inline bool is_file(const std::string& path)
{
	struct ::stat info{};
	return ::stat(path.c_str(), &info) == 0 && S_ISREG(info.st_mode);
}

struct dir
{
	explicit dir(const std::string&) {}
	const dir_entry* begin() const { return nullptr; }
	const dir_entry* end() const { return nullptr; }
};
}
