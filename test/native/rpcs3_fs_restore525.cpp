// SPDX-License-Identifier: MIT
// Production constructors + serialization/layout/enum headers. Host file,
// mount, FXO and log adapters deliberately perform no actual filesystem I/O.
#include <algorithm>
#include <cstdlib>
#include <exception>
#include <functional>
#include <iostream>
#include <span>
#include <string_view>
#include <thread>
#include <vector>
#include "util/types.hpp"
namespace utils { struct serial; }
template<class T> bool serialize(utils::serial&, T&) { std::fputs("Unsupported portable serialize adapter\n", stderr); std::abort(); }
#include "util/serialization.hpp"
#include "util/endian.hpp"

struct Event { std::string_view stage; u32 id, type; u64 value; };
static thread_local std::vector<Event> events;
static thread_local unsigned fs_limits = 0, fxo_events = 0, fxo_limits = 0;
struct TraceLog
{
    template<class... Args> void notice(const char* format, Args&&... args)
    {
        if constexpr (sizeof...(Args) == 8)
        {
            const auto tuple = std::forward_as_tuple(args...);
            events.push_back({std::get<0>(tuple), std::get<1>(tuple), std::get<2>(tuple), std::get<3>(tuple)});
        }
        else if constexpr (sizeof...(Args) == 7) ++fxo_events;
        else if (std::string_view(format).find("fs_trace_limit") != std::string_view::npos) ++fs_limits;
        else ++fxo_limits;
    }
} sys_log;
static u64 get_system_time() { return 1'000'000; }
namespace stx {
#include "trace.inc"
}

static unsigned lookups = 0, opens = 0;
static volatile usz observed_name_length = 0;
static utils::serial* observed_archive = nullptr;
static bool expect_invalid_vle = false;
namespace fmt {
[[noreturn]] void raw_verify_error(std::source_location loc, const char8_t*, usz) {
    if (expect_invalid_vle && !events.empty() && events.back().stage == "dir_count_begin") {
        std::fputs("REJECT invalid directory count before allocation\n", stderr); std::fflush(stderr); std::_Exit(90);
    }
    std::fprintf(stderr, "verify at %s:%u\n", loc.file_name(), loc.line()); std::abort();
}
[[noreturn]] void raw_verify_error(std::source_location loc, std::source_location, const char8_t* msg, usz value) { raw_verify_error(loc, msg, value); }
template<class... Args> [[noreturn]] void throw_exception(const char*, Args&&...)
{
    // Production uses emergency_exit. This test adapter also terminates rather
    // than inventing a recoverable exception or mutating the archive.
    if (lookups || !observed_archive || observed_archive->pos != 0x420 || events.empty() || events.back().stage != "name_unterminated") std::abort();
    std::fputs("REJECT unterminated before mount lookup; stream read=0x420\n", stderr);
    std::fflush(stderr);
    std::_Exit(88);
}
}
namespace fs {
#include "layout.inc"
struct file
{
    bool valid = false;
    s64 seek_pos = -1;
    std::vector<u8> bytes;
    explicit operator bool() const { return valid; }
    void seek(s64 value) { seek_pos = value; }
};
template<class T> file make_stream(T&& data, stat_t) { return {true, -1, std::move(data)}; }
}
#include "enum.inc"
struct lv2_fs_mount_info {};
struct lv2_fs_mount_info_map
{
    lv2_fs_mount_info mount;
    const lv2_fs_mount_info& lookup(std::string_view name) {
        // A real mount lookup consumes the name. Preserve that observation
        // so Clang cannot delete the negative control's strlen as dead code.
        observed_name_length = name.size(); ++lookups; return mount;
    }
};
struct loaded_npdrm_keys
{
    std::array<u8, 16> one_time_key{};
    struct { u32 count = 0; u32& raw() { return count; } } npdrm_fds;
};
struct FXO
{
    lv2_fs_mount_info_map mounts;
    loaded_npdrm_keys keys;
    template<class T> T& get()
    {
        if constexpr (std::is_same_v<T, loaded_npdrm_keys>) return keys;
        else return mounts;
    }
} fixed_objects;
static auto* g_fxo = &fixed_objects;
namespace idm { static u32 last_id() { return 3; } }
struct lv2_fs_object
{
    const std::array<char, 0x420> name;
    const lv2_fs_mount_info& mp;
    lv2_fs_object(utils::serial& ar, bool);
};
static constexpr s32 CELL_FS_O_ACCMODE = 3;
#undef GET_SERIALIZATION_VERSION
#define GET_SERIALIZATION_VERSION(name) 2
struct lv2_file : lv2_fs_object
{
    fs::file file;
    const s32 mode;
    const s32 flags;
    std::string real_path;
    const lv2_file_type type;
    u32 lock = 0;
    lv2_file(utils::serial& ar);
    struct open_result_t { s32 error; fs::file file; std::string real_path; };
    static open_result_t open(std::string_view, s32, s32, const void*, u64);
};
struct lv2_dir : lv2_fs_object
{
    static constexpr u32 id_type = 2;
    const std::vector<fs::dir_entry> entries;
    u64 pos;
    lv2_dir(utils::serial& ar);
};
struct Open { s32 flags, mode; u64 argument, size; std::array<u8, 16> key; } last_open{};
lv2_file::open_result_t lv2_file::open(std::string_view, s32 flags, s32 mode, const void* argument, u64 size)
{
    ++opens;
    last_open = {flags, mode, argument ? static_cast<u64>(*static_cast<const be_t<u64>*>(argument)) : 0, size, g_fxo->keys.one_time_key};
    return {0, {true, -1, {}}, "/portable/file"};
}
struct Log { template<class... Args> void error(const char*, Args&&...) {} template<class... Args> void success(const char*, Args&&...) {} } sys_fs;
static struct { struct { bool state_inspection_mode = false; } savestate; } g_cfg;
#ifdef FS_BASELINE
#include "before.inc"
#else
#include "after.inc"
#endif

static std::array<char, 0x420> saved_name(std::string_view value)
{
    std::array<char, 0x420> name;
    name.fill('p'); // Nonzero padding after NUL is valid and must survive.
    ensure(value.size() < name.size());
    std::copy(value.begin(), value.end(), name.begin());
    name[value.size()] = '\0';
    return name;
}
static void file_archive(utils::serial& ar, lv2_file_type type, s32 flags, bool memory, u64 size = 0)
{
    const auto name = saved_name("/dev_hdd0/game/TEST/file");
    const s32 mode = 0600;
    const u32 lock = 7;
    const std::string path = "/dev_hdd0/game/TEST/file";
    ar(name, mode, flags, type, lock, path);
    if (type == lv2_file_type::edata)
    {
        const std::array<u8, 16> key{1, 2, 3}; ar(key);
    }
    ar(memory);
    if (memory)
    {
        fs::stat_t stat; stat.size = size; ar(stat);
        if (size < 1024)
        {
            const std::vector<u8> bytes(size, 0x5a); ar(std::span<const u8>(bytes));
        }
    }
    const s64 seek = 9; ar(seek); ar.set_reading_state(); return;
}
static void dir_archive(utils::serial& ar, u64 count)
{
    ar(saved_name("/dev_hdd0/game/TEST")); ar.serialize_vle(count);
    if (count < 1024)
    {
        for (u64 i = 0; i < count; ++i)
        {
            const std::string name = "entry" + std::to_string(i);
            fs::stat_t stat; stat.size = i; ar(name, stat);
        }
    }
    const u64 pos = 1; ar(pos); ar.set_reading_state(); return;
}
static void allocation_terminate()
{
    // SIZE_MAX is above vector::max_size: fail without allocating a huge
    // buffer. This explicitly documents an unresolved production preflight.
    if (events.empty() || (events.back().stage != "file_memory_begin" && events.back().stage != "dir_entries_begin") || events.back().value != ~u64{0}) std::abort();
    std::fputs("EXPECTED unresolved allocation before archive payload\n", stderr); std::fflush(stderr); std::_Exit(89);
}
int main(int argc, char** argv)
{
    stx::serial_restore_trace_reset();
    if (argc > 1 && std::string_view(argv[1]) == "dir-vle-invalid")
    {
        utils::serial ar; ar(saved_name("/dev_hdd0/game/TEST"));
        const std::array<u8, 11> continuation{0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80,0x80};
        ar(continuation); ar.set_reading_state(); expect_invalid_vle = true;
        lv2_dir dir(ar); return 9;
    }
    if (argc > 1 && std::string_view(argv[1]) == "unterminated")
    {
        utils::serial ar; std::array<char, 0x420> name; name.fill('x'); ar(name); ar.set_reading_state(); observed_archive = &ar;
        // Poison the complete storage before placement construction, including
        // the not-yet-initialized reference bytes. strlen then reaches ASan's
        // heap redzone deterministically in the original production ctor.
        auto* storage = static_cast<unsigned char*>(::operator new(sizeof(lv2_fs_object)));
        std::memset(storage, 'x', sizeof(lv2_fs_object));
        auto* obj = new(storage) lv2_fs_object(ar, false);
        obj->~lv2_fs_object(); ::operator delete(storage); return 7;
    }
    if (argc > 1)
    {
        std::set_terminate(allocation_terminate);
        if (std::string_view(argv[1]) == "file-size-overflow") { utils::serial ar; file_archive(ar, lv2_file_type::regular, 0, true, ~u64{0}); lv2_file file(ar); }
        else { utils::serial ar; dir_archive(ar, ~u64{0}); lv2_dir dir(ar); }
        return 8;
    }
    unsigned cases = 0;
    for (const std::string& value : {std::string{}, std::string("/dev_hdd0/file"), std::string("CELL_FS_IOS:BUILTIN_FLSH1"), std::string(1055, 'x')})
    {
        utils::serial ar; auto name = saved_name(value); ar(name); ar.set_reading_state(); const auto saved = ar.data; const auto old_lookups = lookups;
        lv2_fs_object obj(ar, false);
        ensure(obj.name == name && ar.pos == 0x420 && ar.data == saved && lookups == old_lookups + 1); ++cases;
    }
    for (auto type : {lv2_file_type::regular, lv2_file_type::sdata, lv2_file_type::edata})
    for (s32 access : {0, 1, 2})
    for (bool memory : {false, true})
    {
        g_fxo->keys = {};
        utils::serial ar; file_archive(ar, type, access | 000100 | 001000 | 002000, memory, 37);
        const auto saved = ar.data; const auto old_opens = opens;
        lv2_file file(ar);
        ensure(ar.pos == ar.data.size() && ar.data == saved && opens == old_opens + 1);
        ensure(last_open.flags == access && last_open.mode == 0600 && file.lock == 7 && file.file.seek_pos == 9);
        ensure(last_open.size == (type == lv2_file_type::regular ? 0 : 8));
        ensure(last_open.argument == (type == lv2_file_type::sdata ? 0x18000000010 : type == lv2_file_type::edata ? 2 : 0));
        ensure(last_open.key[0] == (type == lv2_file_type::edata ? 1 : 0));
        ensure(g_fxo->keys.one_time_key == std::array<u8, 16>{});
        ensure(g_fxo->keys.npdrm_fds.count == (type == lv2_file_type::regular ? 0u : 1u));
        ensure(file.file.bytes == (memory ? std::vector<u8>(37, 0x5a) : std::vector<u8>{})); ++cases;
    }
    unsigned directory_cases = 0, directory_mismatches = 0;
    std::size_t first_dir_read = 0, first_dir_size = 0;
    for (u64 count : {0u, 1u, 9u, 127u, 128u, 257u})
    {
        utils::serial ar; dir_archive(ar, count); const auto saved = ar.data;
        lv2_dir dir(ar);
        const bool restored = ar.pos == ar.data.size() && ar.data == saved && dir.entries.size() == count && dir.pos == 1;
        if (count == 1) { first_dir_read = ar.pos; first_dir_size = ar.data.size(); }
#ifdef FS_BASELINE
        ensure(restored == (count == 0));
#else
        ensure(restored);
        for (u64 i = 0; i < count; ++i) ensure(dir.entries[i].name == "entry" + std::to_string(i) && dir.entries[i].size == i);
#endif
        directory_mismatches += !restored;
        ++directory_cases;
    }
    // Exercise the actual production trace and reset, independently of how
    // many valid constructors ran. It must not consume the FXO trace budget.
    utils::serial ar; ar.set_reading_state(); events.clear(); fs_limits = fxo_events = fxo_limits = 0; stx::serial_restore_trace_reset();
    for (unsigned i = 0; i < 600; ++i) stx::serial_restore_fs_trace(ar, "fixture", 3, 1, i);
    ensure(events.size() == 256 && fs_limits == 1 && ar.pos == 0 && ar.data.empty());
    for (unsigned i = 0; i < 600; ++i) stx::serial_restore_trace(ar, "fixture", true);
    ensure(fxo_events == 512 && fxo_limits == 1 && events.size() == 256);
    stx::serial_restore_trace_reset(); stx::serial_restore_fs_trace(ar, "next", 4, 2, 12); ensure(events.size() == 257 && events.back().id == 4);
    utils::serial writing; stx::serial_restore_fs_trace(writing, "write", 0, 0, 0); ensure(events.size() == 257);
    std::thread worker([&]{ ensure(events.empty()); stx::serial_restore_trace_reset(); stx::serial_restore_fs_trace(ar, "thread", 5, 1, 0); ensure(events.size() == 1); }); worker.join();
    ensure(events.size() == 257);
    std::cout << "{\"fileCases\":" << cases << ",\"directoryCases\":" << directory_cases
              << ",\"directoryMismatches\":" << directory_mismatches << ",\"firstDirectoryReadPosition\":" << first_dir_read
              << ",\"firstDirectoryArchiveBytes\":" << first_dir_size << ",\"boundedTracePassed\":true}\n";
}
