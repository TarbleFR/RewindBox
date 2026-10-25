#include <array>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <string>
#include <string_view>
#include <vector>
using u64 = std::uint64_t;
using BOOL = bool;
constexpr BOOL YES = true, NO = false;
using CFTimeInterval = double;
using os_unfair_lock = int;
#define OS_UNFAIR_LOCK_INIT 0
static double test_now = 1.0;
static unsigned locks = 0, unlocks = 0, lock_depth = 0;
double CACurrentMediaTime() { return test_now; }
void os_unfair_lock_lock(os_unfair_lock*) { ++locks; assert(lock_depth++ == 0); }
void os_unfair_lock_unlock(os_unfair_lock*) { ++unlocks; assert(lock_depth-- == 1); }
#include "host_milestones.inc"
bool permit_log(int32_t level, const char* message)
{
#include "host_admission.inc"
    return true;
}
namespace logs
{
#include "core_log_level.inc"
// Only message storage / abstract listener layout are adapted. The production
// listener body, severity cast, enum and emit_log forwarding remain unchanged.
struct message { level severity; operator level() const { return severity; } };
struct listener
{
    virtual ~listener() = default;
    virtual void log(u64, const message&, std::string_view, std::string_view) = 0;
};
}
namespace fmt
{
void append(std::string& destination, const char* format, std::string_view prefix)
{
    assert(std::strcmp(format, "%s: ") == 0);
    destination.append(prefix); destination.append(": ");
}
}
struct Config { void* user_context = nullptr; void (*log_callback)(void*, int32_t, const char*) = nullptr; };
static Config g_config;
#include "core_listener.inc"
#include "core_metric_formats.inc"
static std::vector<std::string> journal;
static int32_t last_level = -1;
void host_sink(void*, int32_t level, const char* message)
{
    last_level = level;
    if (permit_log(level, message)) journal.emplace_back(message);
}
int main()
{
    static_assert(static_cast<unsigned>(logs::level::notice) == 6);
    callback_log_listener listener;
    const logs::message notice{logs::level::notice};
    g_config.log_callback = host_sink;
    const auto check_delivered = [&](const std::string& line, std::string_view prefix)
    {
        const auto before = journal.size();
        listener.log(0, notice, prefix, line);
        assert(last_level == 6 && journal.size() == before + 1);
        assert(journal.back().find(line) != std::string::npos);
        assert(RPCS3Build487MilestoneStage(journal.back().c_str()) == nullptr);
    };
    // Compile the four actual notice formats, not independently invented tags.
    for (const auto line : core_metric_formats)
    {
        assert(line.starts_with("COREPROF "));
        const auto old = std::string(line.substr(std::strlen("COREPROF ")));
        const auto before = journal.size();
        listener.log(0, notice, "TID: 1234 iOS Core Profiler", old);
        assert(last_level == 6 && journal.size() == before); // old wiring loses notices
        check_delivered(std::string(line), "");
        check_delivered(std::string(line), "TID: 1234 iOS Core Profiler");
        check_delivered(std::string(line), "PPU[0x1000000] arbitrary_channel");
    }
    assert(locks == 0 && unlocks == 0); // profiling did not consume ordinary budget
    assert(!permit_log(6, "FRAMEPROF527 ordinary notice"));
    assert(!permit_log(6, "COREPROFILING FRAMEPROF527 lookalike"));
    for (unsigned i = 0; i < 128; ++i)
        assert(permit_log(i % 3, "ordinary fatal/error/always line"));
    assert(!permit_log(0, "ordinary always line after budget"));
    assert(!permit_log(1, "ordinary fatal line after budget"));
    assert(!permit_log(2, "FRAMEPROF527 error line after budget"));
    assert(!permit_log(6, "NEOSWAP_VDEC budget remains bounded"));
    const auto saturated_locks = locks;
    for (const auto line : core_metric_formats)
    {
        check_delivered(std::string(line), "TID: 4567 final_channel");
        assert(locks == saturated_locks);
    }
    assert(RPCS3Build487MilestoneStage("ordinary FRAMEPROF527 error") == nullptr);
    // Existing durable-loop bound remains intact: routing does not manufacture
    // a new milestone or bypass the old mutex retry cap.
    for (unsigned i = 0; i < 64; ++i)
        assert(RPCS3Build487AdmitBoundedLine("MUTEX_DESTROY_BUSY id=1"));
    assert(!RPCS3Build487AdmitBoundedLine("MUTEX_DESTROY_BUSY id=1"));
    test_now = 2.0;
    assert(permit_log(2, "ordinary error after one-second renewal"));
    assert(lock_depth == 0 && locks == unlocks);
    const auto count = journal.size();
    g_config.log_callback = nullptr;
    listener.log(0, notice, "TID: no callback", core_metric_formats[0]);
    assert(journal.size() == count);
    std::printf("PASS four production notices: listener preserves notice=6, host admits after budget saturation, old formats rejected, prefixes retained, no milestone/error-budget loophole\n");
}
