// Host test of the staged RPCS3 Core patch NEOSTATION_RPCS3_RETROACHIEVEMENTS_V1
// (build-utils/rpcs3/retroachievements-core.patch). test/rpcs3_retroachievements_test.py
// extracts, from that patch, the new rpcs3/ios/RPCS3IOSAchievements.h, the
// declarations added to RPCS3IOS.h (ra_declarations.inc) and the rpcs3_ios_ra_*
// definitions added to RPCS3IOS.cpp (ra_exports.inc), then compiles them here
// against minimal stand-ins of Emu, vm::try_access and g_cfg. The exported code
// itself is compiled unchanged; only RPCS3's own services are replaced.
#include <atomic>
#include <chrono>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

using u8 = std::uint8_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using usz = std::size_t;

// ---- Stand-ins for the RPCS3IOS.h types used by the additions -------------
typedef enum rpcs3_ios_status
{
    RPCS3_IOS_OK = 0,
    RPCS3_IOS_INVALID_ARGUMENT = 1,
    RPCS3_IOS_INVALID_STATE = 2,
    RPCS3_IOS_INTERNAL_ERROR = 7
} rpcs3_ios_status;

typedef enum rpcs3_ios_emulation_state
{
    RPCS3_IOS_EMULATION_STATE_UNKNOWN = 0,
    RPCS3_IOS_EMULATION_STATE_STOPPED = 1,
    RPCS3_IOS_EMULATION_STATE_RUNNING = 5,
    RPCS3_IOS_EMULATION_STATE_PAUSED = 6
} rpcs3_ios_emulation_state;

#define RPCS3_IOS_EXPORT
#define RPCS3_IOS_NOEXCEPT noexcept

extern "C" {
#include "ra_declarations.inc"
}

#include "RPCS3IOSAchievements.h"

// ---- Stand-ins for the RPCS3 services the exports call ---------------------
enum class frame_limit_type { none, _30, _50, _60, _120, display_rate, _auto, _ps3, infinite };

template <typename T>
struct fake_setting
{
    T value;
    T get() const { return value; }
};

struct fake_config
{
    struct { fake_setting<frame_limit_type> frame_limit{frame_limit_type::_auto}; fake_setting<int> vblank_rate{60}; } video;
    struct { fake_setting<int> clocks_scale{100}; } core;
} g_cfg;

struct fake_emulator
{
    bool running = false;
    bool paused = false;
    bool IsRunning() const { return running; }
    bool IsPaused() const { return paused; }
} Emu;

namespace vm
{
    std::map<u32, std::vector<u8>> pages;  // page base -> 4096 bytes
    bool throw_next = false;
    int calls = 0;

    bool try_access(u32 begin, void* ptr, u32 size, bool is_write)
    {
        ++calls;
        if (is_write || size == 0 || begin / 4096 != (begin + size - 1) / 4096)
        {
            std::fprintf(stderr, "FAIL: read must be a single-page read access (0x%x, %u, %d)\n", begin, size, is_write);
            std::exit(1);
        }
        if (throw_next)
        {
            throw_next = false;
            throw std::runtime_error("Out of range lock bits");
        }
        const auto found = pages.find(begin & ~4095u);
        if (found == pages.end())
        {
            return false;
        }
        std::memcpy(ptr, found->second.data() + (begin & 4095u), size);
        return true;
    }
}

rpcs3_ios_emulation_state current_emulation_state() noexcept
{
    return Emu.running ? RPCS3_IOS_EMULATION_STATE_RUNNING
        : Emu.paused ? RPCS3_IOS_EMULATION_STATE_PAUSED : RPCS3_IOS_EMULATION_STATE_STOPPED;
}

#include "ra_exports.inc"

// ---- Tests -------------------------------------------------------------------
static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); ++failures; } } while (0)

static_assert(sizeof(rpcs3_ios_ra_session_info) == 1120, "session info layout");
static_assert(offsetof(rpcs3_ios_ra_session_info, boot_generation) == 24, "boot_generation offset");
static_assert(offsetof(rpcs3_ios_ra_session_info, title_id) == 32, "title_id offset");
static_assert(offsetof(rpcs3_ios_ra_session_info, content_path) == 96, "content_path offset");

namespace
{
    std::atomic<int> g_calls{0};
    std::atomic<u64> g_last_frame{0};
    std::atomic<bool> g_inside{false};
    std::atomic<int> g_slow_ms{0};

    void on_frame(void* context, u64 frame)
    {
        g_inside = true;
        if (g_slow_ms.load())
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(g_slow_ms.load()));
        }
        g_last_frame = frame;
        g_calls += *static_cast<int*>(context);
        g_inside = false;
    }

    void test_frame_hook()
    {
        auto& hook = rpcs3::ios::achievements::vblank_hook();
        CHECK(&hook == &rpcs3::ios::achievements::vblank_hook());
        CHECK(!hook.armed());
        hook.notify(1);  // nothing attached: no effect
        CHECK(g_calls == 0);

        int weight = 1;
        CHECK(rpcs3_ios_ra_set_frame_callback(on_frame, &weight) == RPCS3_IOS_OK);
        CHECK(hook.armed());
        hook.notify(7);
        CHECK(g_calls == 1 && g_last_frame == 7);

        CHECK(rpcs3_ios_ra_set_frame_callback(nullptr, &weight) == RPCS3_IOS_OK);
        CHECK(!hook.armed());
        hook.notify(8);
        CHECK(g_calls == 1 && g_last_frame == 7);

        // Detaching waits for the callback in flight, and a VBlank never waits
        // for a (de)registration: it skips the frame instead.
        g_slow_ms = 60;
        CHECK(rpcs3_ios_ra_set_frame_callback(on_frame, &weight) == RPCS3_IOS_OK);
        std::thread vblank([&hook] { hook.notify(9); });
        while (!g_inside) std::this_thread::yield();
        const auto before = std::chrono::steady_clock::now();
        CHECK(rpcs3_ios_ra_set_frame_callback(nullptr, nullptr) == RPCS3_IOS_OK);
        const auto waited = std::chrono::steady_clock::now() - before;
        CHECK(!g_inside);
        CHECK(g_last_frame == 9 && g_calls == 2);
        CHECK(waited >= std::chrono::milliseconds(20));
        vblank.join();
        g_slow_ms = 0;

        CHECK(rpcs3_ios_ra_set_frame_callback(on_frame, &weight) == RPCS3_IOS_OK);
        // The callback in flight holds for 400 ms. Only the skipped notify(11) is timed (not the
        // scheduling sleep before it): a VBlank that waited for the callback would take about
        // 390 ms, a skipping one returns at once; 200 ms separates both on a loaded CI runner.
        g_slow_ms = 400;
        std::thread busy([&hook] { hook.notify(10); });
        while (!g_inside) std::this_thread::yield();
        std::thread blocked_set([] { rpcs3_ios_ra_set_frame_callback(nullptr, nullptr); });
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
        const auto skip_start = std::chrono::steady_clock::now();
        hook.notify(11);  // set() holds the lock or waits for it: this frame is skipped, without blocking
        CHECK(std::chrono::steady_clock::now() - skip_start < std::chrono::milliseconds(200));
        CHECK(g_inside);  // the in-flight frame 10 was not awaited
        busy.join();
        blocked_set.join();
        CHECK(g_last_frame == 10);
        g_slow_ms = 0;
    }

    void test_read_memory()
    {
        u8 buffer[16];
        u32 mapped = 99;
        CHECK(rpcs3_ios_ra_read_memory(0x10000, nullptr, 4, &mapped) == RPCS3_IOS_INVALID_ARGUMENT && mapped == 0);
        CHECK(rpcs3_ios_ra_read_memory(0x10000, buffer, 0, &mapped) == RPCS3_IOS_INVALID_ARGUMENT);
        CHECK(rpcs3_ios_ra_read_memory(0x10000, buffer, 65537, &mapped) == RPCS3_IOS_INVALID_ARGUMENT);
        CHECK(rpcs3_ios_ra_read_memory(0xFFFFFFFEu, buffer, 4, &mapped) == RPCS3_IOS_INVALID_ARGUMENT);
        CHECK(rpcs3_ios_ra_read_memory(0xFFFFFFFCu, buffer, 4, nullptr) != RPCS3_IOS_INVALID_ARGUMENT);

        std::vector<u8> page(4096);
        for (u32 i = 0; i < page.size(); ++i) page[i] = static_cast<u8>(i * 7 + 1);
        vm::pages[0x10000] = page;

        Emu = {};
        std::memset(buffer, 0xAA, sizeof(buffer));
        mapped = 99;
        CHECK(rpcs3_ios_ra_read_memory(0x10000, buffer, 4, &mapped) == RPCS3_IOS_INVALID_STATE);
        CHECK(mapped == 0 && buffer[0] == 0 && buffer[3] == 0 && buffer[4] == 0xAA);

        Emu.running = true;
        vm::calls = 0;
        CHECK(rpcs3_ios_ra_read_memory(0x10004, buffer, 4, &mapped) == RPCS3_IOS_OK);
        CHECK(mapped == 4 && vm::calls == 1);
        CHECK(std::memcmp(buffer, page.data() + 4, 4) == 0);  // guest (PS3) byte order, unchanged

        // Mapped head, unmapped tail: page by page, the tail is zero-filled.
        std::memset(buffer, 0xAA, sizeof(buffer));
        vm::calls = 0;
        CHECK(rpcs3_ios_ra_read_memory(0x10000 + 4092, buffer, 8, &mapped) == RPCS3_IOS_OK);
        CHECK(vm::calls == 2 && mapped == 4);
        CHECK(std::memcmp(buffer, page.data() + 4092, 4) == 0);
        CHECK(buffer[4] == 0 && buffer[7] == 0 && buffer[8] == 0xAA);

        // Unmapped head, mapped tail.
        vm::pages[0x12000] = page;
        CHECK(rpcs3_ios_ra_read_memory(0x12000 - 2, buffer, 4, &mapped) == RPCS3_IOS_OK);
        CHECK(mapped == 2 && buffer[0] == 0 && buffer[1] == 0 && buffer[2] == page[0] && buffer[3] == page[1]);

        // Fully unmapped (not allocated yet): zeros, still OK.
        CHECK(rpcs3_ios_ra_read_memory(0x40000000, buffer, 4, &mapped) == RPCS3_IOS_OK && mapped == 0);

        Emu.running = false;
        Emu.paused = true;
        CHECK(rpcs3_ios_ra_read_memory(0x10000, buffer, 2, &mapped) == RPCS3_IOS_OK && mapped == 2);

        // An exception from the VM is contained and never escapes the C ABI.
        vm::throw_next = true;
        std::memset(buffer, 0xAA, sizeof(buffer));
        CHECK(rpcs3_ios_ra_read_memory(0x10000, buffer, 4, &mapped) == RPCS3_IOS_INTERNAL_ERROR);
        CHECK(mapped == 0 && buffer[0] == 0 && buffer[3] == 0);
        Emu = {};
    }

    void test_session_info()
    {
        rpcs3_ios_ra_session_info info{};
        CHECK(rpcs3_ios_ra_get_session_info(nullptr) == RPCS3_IOS_INVALID_ARGUMENT);
        info.struct_size = sizeof(info) - 1;
        CHECK(rpcs3_ios_ra_get_session_info(&info) == RPCS3_IOS_INVALID_ARGUMENT);

        info = {};
        info.struct_size = sizeof(info);
        std::memset(info.content_path, 'x', sizeof(info.content_path));
        CHECK(rpcs3_ios_ra_get_session_info(&info) == RPCS3_IOS_OK);
        CHECK(info.struct_size == sizeof(info));
        CHECK(info.emulation_state == RPCS3_IOS_EMULATION_STATE_STOPPED);
        CHECK(info.hardcore_compatible == 1 && info.vblank_rate == 60 && info.clocks_scale == 100);
        CHECK(info.frame_limit_unbounded == 0 && info.boot_generation == 0);
        CHECK(info.title_id[0] == '\0' && info.content_path[0] == '\0');

        struct speed_case { int vblank; int clocks; frame_limit_type limit; u32 compatible; u32 unbounded; };
        const speed_case cases[] = {
            {60, 100, frame_limit_type::_30, 1, 0}, {60, 100, frame_limit_type::_ps3, 1, 0},
            {60, 100, frame_limit_type::display_rate, 1, 0}, {60, 100, frame_limit_type::_60, 1, 0},
            {60, 100, frame_limit_type::none, 0, 1}, {60, 100, frame_limit_type::infinite, 0, 1},
            {60, 100, frame_limit_type::_120, 0, 1}, {120, 100, frame_limit_type::_auto, 0, 0},
            {59, 100, frame_limit_type::_auto, 0, 0}, {60, 50, frame_limit_type::_auto, 0, 0},
            {60, 150, frame_limit_type::_auto, 0, 0},
        };
        for (const auto& item : cases)
        {
            g_cfg.video.vblank_rate.value = item.vblank;
            g_cfg.core.clocks_scale.value = item.clocks;
            g_cfg.video.frame_limit.value = item.limit;
            CHECK(rpcs3_ios_ra_get_session_info(&info) == RPCS3_IOS_OK);
            CHECK(info.hardcore_compatible == item.compatible);
            CHECK(info.frame_limit_unbounded == item.unbounded);
            CHECK(info.vblank_rate == static_cast<u32>(item.vblank) && info.clocks_scale == static_cast<u32>(item.clocks));
        }
        g_cfg = {};

        auto& record = rpcs3::ios::achievements::last_boot();
        record.set("BLUS30001", "/private/var/mobile/Data/games/BLUS30001/disc.iso");
        Emu.running = true;
        CHECK(rpcs3_ios_ra_get_session_info(&info) == RPCS3_IOS_OK);
        CHECK(info.emulation_state == RPCS3_IOS_EMULATION_STATE_RUNNING);
        CHECK(std::string(info.title_id) == "BLUS30001");
        CHECK(std::string(info.content_path) == "/private/var/mobile/Data/games/BLUS30001/disc.iso");
        CHECK(info.boot_generation == 1);

        record.clear();  // a failed or non-game boot never describes the previous title
        CHECK(rpcs3_ios_ra_get_session_info(&info) == RPCS3_IOS_OK);
        CHECK(info.title_id[0] == '\0' && info.content_path[0] == '\0' && info.boot_generation == 1);

        record.set("NPUB30002", "/Data/dev_hdd0/game/NPUB30002");
        CHECK(rpcs3_ios_ra_get_session_info(&info) == RPCS3_IOS_OK && info.boot_generation == 2);
        CHECK(std::string(info.content_path) == "/Data/dev_hdd0/game/NPUB30002");

        // A path that does not fit is refused, never truncated into another path.
        record.set("BLES00001", "/" + std::string(1100, 'a'));
        CHECK(rpcs3_ios_ra_get_session_info(&info) == RPCS3_IOS_OK);
        CHECK(info.content_path[0] == '\0' && info.title_id[0] == '\0' && info.boot_generation == 3);
        Emu = {};
    }

    void test_pure_rules()
    {
        using namespace rpcs3::ios::achievements;
        CHECK(valid_read(0, reinterpret_cast<void*>(1), 1));
        CHECK(valid_read(0xFFFFFFFFu, reinterpret_cast<void*>(1), 1));
        CHECK(!valid_read(0xFFFFFFFFu, reinterpret_cast<void*>(1), 2));
        CHECK(!valid_read(0, nullptr, 1));
        CHECK(!valid_read(0, reinterpret_cast<void*>(1), max_read_size + 1));
        CHECK(hardcore_compatible({}));
        char small[4];
        CHECK(!copy_text(small, sizeof(small), "abcd") && small[0] == '\0');
        CHECK(copy_text(small, sizeof(small), "abc") && std::string(small) == "abc");
        CHECK(!copy_text(small, sizeof(small), std::string_view("a\0b", 3)));
        CHECK(rpcs3_ios_ra_api_version() == RPCS3_IOS_RA_API_VERSION && RPCS3_IOS_RA_API_VERSION == 1u);
    }
}

int main()
{
    test_pure_rules();
    test_frame_hook();
    test_read_memory();
    test_session_info();
    if (failures)
    {
        std::fprintf(stderr, "%d check(s) failed\n", failures);
        return 1;
    }
    std::puts("PASS: RPCS3 RetroAchievements Core hooks (frame hook, guarded reads, session info)");
    return 0;
}
