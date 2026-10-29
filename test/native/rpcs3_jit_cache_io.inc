// SPDX-License-Identifier: GPL-2.0-or-later
// Production ObjectCache read bodies are inserted by rpcs3_jit_cache_io_test.py.
// LLVM buffer allocation/validation are adapters; POSIX file I/O and zlib are real.
#include "Utilities/JITObjectBuffer.h"
#include <cassert>
#include <chrono>
#include <cerrno>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <memory>
#include <random>
#include <string>
#include <string_view>
#include <vector>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#ifdef NDEBUG
#error "The JIT cache I/O regression requires active assertions"
#endif

using u64 = std::uint64_t;
struct counters
{
    u64 opens{}, stats{}, seeks{}, reads{}, positional_reads{}, removes{};
};
static counters io;
static std::size_t read_limit = SIZE_MAX;
namespace fs
{
inline constexpr int read = O_RDONLY;
inline int g_tls_error;
struct stat_t { bool is_directory; u64 size; };
bool is_file(const std::string& path)
{
    ++io.stats;
    struct stat s{};
    return ::stat(path.c_str(), &s) == 0 && S_ISREG(s.st_mode);
}
bool remove_file(const std::string& path)
{
    ++io.removes;
    return ::unlink(path.c_str()) == 0;
}
class file
{
    int fd;
public:
    file(const std::string& path, int mode) : fd((++io.opens, ::open(path.c_str(), mode))) {}
    ~file() { if (fd >= 0) ::close(fd); }
    explicit operator bool() const { return fd >= 0; }
    u64 size() const
    {
        ++io.stats;
        struct stat s{};
        assert(::fstat(fd, &s) == 0);
        return s.st_size;
    }
    stat_t get_stat() const
    {
        ++io.stats;
        struct stat s{};
        assert(::fstat(fd, &s) == 0);
        return {S_ISDIR(s.st_mode), static_cast<u64>(s.st_size)};
    }
    u64 seek(u64 offset) { ++io.seeks; return ::lseek(fd, offset, SEEK_SET); }
    u64 read(void* out, std::size_t count)
    {
        ++io.reads;
        const auto n = ::read(fd, out, std::min(count, read_limit));
        assert(n >= 0 || errno != EISDIR);
        return n < 0 ? 0 : n;
    }
    u64 read_at(u64 offset, void* out, std::size_t count)
    {
        ++io.positional_reads;
        const auto n = ::pread(fd, out, std::min(count, read_limit), offset);
        assert(n >= 0 || errno != EISDIR);
        return n < 0 ? 0 : n;
    }
};
}
namespace llvm
{
class MemoryBuffer
{
    std::vector<char> bytes;
public:
    explicit MemoryBuffer(std::size_t size) : bytes(size) {}
    char* getBufferStart() { return bytes.data(); }
    const char* getBufferStart() const { return bytes.data(); }
    std::size_t getBufferSize() const { return bytes.size(); }
};
class WritableMemoryBuffer
{
public:
    static std::unique_ptr<MemoryBuffer> getNewUninitMemBuffer(std::size_t size)
    {
        return std::make_unique<MemoryBuffer>(size);
    }
};
}
namespace utils { u64 get_tsc() { return 0; } }
namespace jit_phase
{
enum phase { ppu_cache_read, spu_cache_read };
struct scope
{
    u64 bytes{};
    scope(phase, u64 (*)()) {}
};
}
struct log_adapter
{
    template<class... Args> void error(const char*, const Args&...) const {}
} jit_log;
struct jit_cached_object
{
    std::unique_ptr<llvm::MemoryBuffer> buffer;
    u64 bytes{};
    bool removed_invalid{};
};

// @PRODUCTION_BODIES@

static std::vector<unsigned char> compressed(const std::vector<unsigned char>& data)
{
    z_stream z{};
    assert(deflateInit2(&z, 1, Z_DEFLATED, 31, 8, Z_DEFAULT_STRATEGY) == Z_OK);
    std::vector<unsigned char> result(deflateBound(&z, data.size()));
    z.next_in = const_cast<unsigned char*>(data.data());
    z.avail_in = data.size();
    z.next_out = result.data();
    z.avail_out = result.size();
    assert(deflate(&z, Z_FINISH) == Z_STREAM_END);
    result.resize(z.total_out);
    assert(deflateEnd(&z) == Z_OK);
    return result;
}
static void write(const std::filesystem::path& path, const std::vector<unsigned char>& data)
{
    std::ofstream out(path, std::ios::binary);
    out.write(reinterpret_cast<const char*>(data.data()), data.size());
    assert(out.good());
}
struct observed
{
    std::vector<char> bytes;
    bool invalid;
    bool raw_remains;
    bool gzip_remains;
    counters calls;
};
template<class Loader>
static observed run(const std::filesystem::path& path, Loader loader)
{
    io = {};
    auto object = loader(path.string(), "entry");
    observed result{{}, object.removed_invalid, false, false, io};
    if (object.buffer)
    {
        assert(object.bytes == object.buffer->getBufferSize());
        result.bytes.assign(object.buffer->getBufferStart(),
            object.buffer->getBufferStart() + object.bytes);
    }
    result.raw_remains = std::filesystem::is_regular_file(path);
    result.gzip_remains = std::filesystem::is_regular_file(path.string() + ".gz");
    return result;
}
static void equal(const observed& a, const observed& b)
{
    assert(a.bytes == b.bytes && a.invalid == b.invalid);
    assert(a.raw_remains == b.raw_remains && a.gzip_remains == b.gzip_remains);
}

int main(int argc, char** argv)
{
    assert(argc == 2);
    const std::filesystem::path root{argv[1]};
    std::filesystem::create_directories(root);
    const auto a = root / "before object.obj";
    const auto b = root / "after object.obj";
    std::mt19937 random(593);
    unsigned cases = 0;
    counters small_before{}, small_after{}, large_before{}, large_after{};
    for (std::size_t size : {1u, 32u, 1024u, 3000u, 4072u, 4096u, 4097u, 65535u, 65536u, 65537u, 1048576u})
    {
        std::vector<unsigned char> expected(size);
        for (auto& byte : expected) byte = random();
        expected.front() = 0x7f; // The unchanged LLVM validator is adapted identically.
        const auto gz = compressed(expected);
        for (bool short_reads : {false, true})
        {
            read_limit = short_reads ? 73 : SIZE_MAX;
            write(a.string() + ".gz", gz);
            write(b.string() + ".gz", gz);
            auto old = run(a, before::load_cached_object);
            auto now = run(b, after::load_cached_object);
            equal(old, now);
            assert(now.bytes.size() == expected.size());
            assert(std::memcmp(now.bytes.data(), expected.data(), expected.size()) == 0);
            if (!short_reads && gz.size() <= 4096)
            {
                assert(now.calls.seeks == 0 && now.calls.reads == 0);
                assert(now.calls.positional_reads == 1 && now.calls.stats == 1);
                assert(old.calls.seeks == 2 && old.calls.reads == 2 && old.calls.stats == 2);
                small_before = old.calls; small_after = now.calls;
            }
            if (!short_reads && gz.size() > 4096)
            {
                assert(now.calls.seeks == 0 && now.calls.positional_reads == old.calls.reads);
                assert(now.calls.stats + 1 == old.calls.stats);
                large_before = old.calls; large_after = now.calls;
            }
            ++cases;
        }
        read_limit = SIZE_MAX;
        for (unsigned defect = 0; defect < 5; ++defect)
        {
            auto bad = gz;
            if (defect == 0) bad[bad.size() - 8] ^= 1; // CRC
            if (defect == 1) bad.pop_back(); // truncated trailer
            if (defect == 2) bad.push_back(0); // trailing bytes
            if (defect == 3) bad[0] ^= 1; // gzip header
            if (defect == 4) bad.back() = 127; // unbounded ISIZE
            write(a.string() + ".gz", bad);
            write(b.string() + ".gz", bad);
            auto old = run(a, before::load_cached_object);
            auto now = run(b, after::load_cached_object);
            equal(old, now);
            assert(now.bytes.empty() && now.invalid && !now.gzip_remains);
            ++cases;
        }
        write(a, expected); write(b, expected);
        equal(run(a, before::load_cached_object), run(b, after::load_cached_object)); ++cases;
        std::filesystem::remove(a); std::filesystem::remove(b);
    }
    equal(run(a, before::load_cached_object), run(b, after::load_cached_object)); ++cases;
    // Removing a path-level hit probe must not make directories readable objects.
    for (bool gzip_dir : {false, true})
    {
        const auto old_dir = gzip_dir ? a.string() + ".gz" : a.string();
        const auto new_dir = gzip_dir ? b.string() + ".gz" : b.string();
        std::filesystem::create_directory(old_dir);
        std::filesystem::create_directory(new_dir);
        equal(run(a, before::load_cached_object), run(b, after::load_cached_object));
        assert(io.reads == 0 && io.positional_reads == 0);
        std::filesystem::remove(old_dir); std::filesystem::remove(new_dir);
        ++cases;
    }
    // A directory at the compressed name must not destroy a valid raw object.
    std::filesystem::create_directory(b.string() + ".gz");
    write(b, {0x7f, 1, 2, 3});
    auto raw_fallback = run(b, after::load_cached_object);
    assert(raw_fallback.bytes.size() == 4 && !raw_fallback.invalid && raw_fallback.raw_remains);
    std::filesystem::remove(b); std::filesystem::remove(b.string() + ".gz"); ++cases;
    std::vector<unsigned char> foreign(128, 42);
    write(a, foreign); write(b, foreign);
    auto old = run(a, before::load_cached_object);
    auto now = run(b, after::load_cached_object);
    equal(old, now); assert(now.invalid && now.bytes.empty()); ++cases;
    // Dishonest ISIZE must not let even highly compressed input exceed its owner.
    auto bomb = compressed(std::vector<unsigned char>(1048576, 0x7f));
    bomb[bomb.size() - 4] = 16;
    bomb[bomb.size() - 3] = bomb[bomb.size() - 2] = bomb.back() = 0;
    write(a.string() + ".gz", bomb); write(b.string() + ".gz", bomb);
    old = run(a, before::load_cached_object); now = run(b, after::load_cached_object);
    equal(old, now); assert(now.invalid && now.bytes.empty()); ++cases;
    // Both paths keep the compressed file's priority over an uncompressed copy.
    foreign.front() = 0x7f;
    write(a, foreign); write(b, foreign);
    write(a.string() + ".gz", {1, 2, 3}); write(b.string() + ".gz", {1, 2, 3});
    old = run(a, before::load_cached_object); now = run(b, after::load_cached_object);
    equal(old, now); assert(now.invalid && !now.raw_remains); ++cases;

    std::vector<unsigned char> data(3000);
    for (auto& byte : data) byte = random();
    data.front() = 0x7f;
    const auto bytes = compressed(data);
    assert(bytes.size() <= 4096);
    write(a.string() + ".gz", bytes); write(b.string() + ".gz", bytes);
    auto bench = [&](auto loader, const std::filesystem::path& path)
    {
        const auto start = std::chrono::steady_clock::now();
        for (unsigned i = 0; i < 10000; ++i)
        {
            auto item = loader(path.string(), "entry");
            assert(item.bytes == data.size());
        }
        return std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - start).count() / 10000;
    };
    std::array<double, 5> old_us{}, now_us{};
    for (unsigned i = 0; i < old_us.size(); ++i)
    {
        if (i % 2) { now_us[i] = bench(after::load_cached_object, b); old_us[i] = bench(before::load_cached_object, a); }
        else { old_us[i] = bench(before::load_cached_object, a); now_us[i] = bench(after::load_cached_object, b); }
    }
    std::sort(old_us.begin(), old_us.end()); std::sort(now_us.begin(), now_us.end());
    std::cout << "{\"passed\":true,\"cases\":" << cases
        << ",\"small_hit\":{\"before_stat_seek_read\":[" << small_before.stats << ',' << small_before.seeks << ',' << small_before.reads
        << "],\"after_stat_seek_pread\":[" << small_after.stats << ',' << small_after.seeks << ',' << small_after.positional_reads
        << "]},\"large_hit\":{\"before_seek\":" << large_before.seeks << ",\"after_seek\":" << large_after.seeks
        << "},\"host_warm_3k_object_median_us\":{\"before\":" << old_us[2] << ",\"after\":" << now_us[2]
        << "},\"benchmark_scope\":\"host filesystem, zlib, adapted LLVM buffers; not iPhone or gameplay\"}\n";
}
