// Host test of REWINDBOX_CORE_LOG_BOUNDED_621 and REWINDBOX_INCIDENT_REPORT_621
// (packages/rpcs3_internal_bridge/ios/Classes/Rpcs3CoreLogAdmission.h and
// Rpcs3IncidentReport.h). Linux/POSIX: a slow-disk writer and message bursts
// against the admission, a fatal line written right before abort(), the
// session record of a process that died, incidents, and the peak memory of
// the streaming export on a large journal (measured in child processes).
// Usage: host_logging_test <workdir> [big_log_mib]
#include "Rpcs3CoreLogAdmission.h"
#include "Rpcs3IncidentReport.h"

#include <sys/resource.h>
#include <sys/wait.h>

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <deque>
#include <fstream>
#include <functional>
#include <sstream>
#include <thread>

using namespace rpcs3_host;

static int g_failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #cond); ++g_failures; } } while (0)

namespace
{
double now_s()
{
	return std::chrono::duration<double>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

// The asynchronous writer: one thread, `delay` per line (a slow disk).
struct slow_writer
{
	core_log_admission& admission;
	std::chrono::microseconds delay;
	std::mutex mutex;
	std::condition_variable cv;
	std::deque<std::string> queue;
	std::vector<std::string> written;
	bool stop = false;
	std::thread thread;

	slow_writer(core_log_admission& a, std::chrono::microseconds d) : admission(a), delay(d)
	{
		thread = std::thread([this] {
			for (;;)
			{
				std::string line;
				{
					std::unique_lock lock(mutex);
					cv.wait(lock, [this] { return stop || !queue.empty(); });
					if (queue.empty()) return;
					line = std::move(queue.front());
					queue.pop_front();
				}
				std::this_thread::sleep_for(delay);
				admission.written(line.size());
				std::lock_guard lock(mutex);
				written.push_back(std::move(line));
			}
		});
	}

	~slow_writer() { finish(); }

	void finish()
	{
		{
			std::lock_guard lock(mutex);
			stop = true;
		}
		cv.notify_all();
		if (thread.joinable()) thread.join();
	}

	// What RPCS3Log does with a decision: before-lines first, then the message.
	void log(int level, const std::string& message, bool profiler, double time)
	{
		const auto decision = admission.admit(level, message, profiler, time);
		std::lock_guard lock(mutex);
		std::size_t at = 0;
		while (!decision.before.empty() && at <= decision.before.size())
		{
			const std::size_t end = std::min(decision.before.find('\n', at), decision.before.size());
			queue.push_back(decision.before.substr(at, end - at));
			at = end + 1;
		}
		if (decision.write) queue.push_back(message);
		cv.notify_one();
	}

	std::size_t count(std::string_view prefix)
	{
		std::lock_guard lock(mutex);
		std::size_t result = 0;
		for (const auto& line : written) result += line.rfind(prefix, 0) == 0;
		return result;
	}
};

void repeated_burst()
{
	// 4 threads x 50,000 copies of one error within ~0.2 s: one line plus a LOG_REPEAT.
	core_log_admission admission;
	slow_writer writer(admission, std::chrono::microseconds(0));
	std::atomic<std::uint64_t> slowest_ns{0};
	const double start = now_s();
	std::vector<std::thread> threads;
	for (int t = 0; t < 4; ++t)
	{
		threads.emplace_back([&] {
			for (int i = 0; i < 50'000; ++i)
			{
				const auto before = std::chrono::steady_clock::now();
				writer.log(2, "sys_fs: sys_fs_open(path=\"/dev_hdd0/game/X\") failed: CELL_ENOENT", false, start + i * 1e-6);
				const auto ns = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - before).count());
				std::uint64_t seen = slowest_ns.load();
				while (ns > seen && !slowest_ns.compare_exchange_weak(seen, ns)) {}
			}
		});
	}
	for (auto& thread : threads) thread.join();
	writer.log(2, "a different message", false, start + 1.0);
	writer.finish();
	const auto counters = admission.counters();
	CHECK(counters.repeats == 199'999);
	CHECK(writer.count("sys_fs:") == 1);
	CHECK(writer.count("LOG_REPEAT count=199999 ") == 1);
	CHECK(counters.pending_lines == 0);
	std::printf("repeated burst: 200000 calls -> %zu lines, slowest call %.1f us\n",
		writer.written.size(), slowest_ns.load() / 1000.0);
}

void distinct_burst_budget()
{
	core_log_admission admission;
	slow_writer writer(admission, std::chrono::microseconds(0));
	const double start = 100.0;
	for (int i = 0; i < 1000; ++i) writer.log(2, "distinct error " + std::to_string(i), false, start + i * 0.0001);
	// Next second: the drops are reported first.
	writer.log(2, "next window", false, start + 1.5);
	for (int i = 0; i < 50; ++i) writer.log(3, "COREPROF frames=" + std::to_string(i), true, start + 0.05);
	writer.finish();
	const auto counters = admission.counters();
	CHECK(counters.budget_dropped == 1000 - 128);
	CHECK(writer.count("distinct error ") == 128);
	CHECK(writer.count("LOG_BUDGET dropped=872 limit_per_s=128 ") == 1);
	CHECK(writer.count("COREPROF frames=") == 50); // profiler lines are not budgeted
}

void slow_disk()
{
	// A disk that takes 2 ms per line; producers send far more than it can take.
	core_log_limits limits;
	limits.per_second = 0; // as in the application: RPCS3Log budgets ordinary lines before (Build 283)
	limits.backlog_lines = 200;
	limits.reserve_lines = 50;
	core_log_admission admission(limits);
	slow_writer writer(admission, std::chrono::microseconds(2000));
	std::uint64_t slowest_ns = 0;
	std::uint64_t peak_pending = 0;
	for (int i = 0; i < 5000; ++i)
	{
		const auto before = std::chrono::steady_clock::now();
		writer.log(2, "slow disk line " + std::to_string(i), false, 200.0 + i * 1e-5);
		if (i % 10 == 0) writer.log(3, "COREPROF window " + std::to_string(i), true, 200.0 + i * 1e-5);
		if (i == 4000) writer.log(1, "Thread terminated due to fatal error: Null object.", false, 200.0 + i * 1e-5);
		slowest_ns = std::max<std::uint64_t>(slowest_ns, static_cast<std::uint64_t>(
			std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - before).count()));
		peak_pending = std::max(peak_pending, admission.counters().pending_lines);
	}
	// The next window reports this one's refusals (LOG_BACKLOG: no budget here).
	writer.log(3, "COREPROF window next", true, 201.5);
	const auto counters = admission.counters();
	CHECK(counters.backlog_dropped > 4000);           // refused, counted, not waited for
	CHECK(peak_pending <= limits.backlog_lines + limits.reserve_lines + 2);
	CHECK(counters.fatal == 1);
	writer.finish();
	CHECK(writer.count("Thread terminated due to fatal error") == 1); // the fatal line is never dropped
	CHECK(writer.count("COREPROF window ") > 40);                       // the reserve keeps profiler lines flowing
	CHECK(writer.count("LOG_BACKLOG dropped=") >= 1 && writer.count("LOG_BUDGET ") == 0); // its own report line
	std::printf("slow disk (2 ms/line): 5000 lines -> written %zu, backlog_dropped %llu, peak backlog %llu lines, "
		"slowest producer call %.1f us (the writer never blocks the caller)\n", writer.written.size(),
		static_cast<unsigned long long>(counters.backlog_dropped), static_cast<unsigned long long>(peak_pending), slowest_ns / 1000.0);
	CHECK(slowest_ns < 50'000'000); // far below one 2 ms write per queued line
	CHECK(core_log_game_stopped(1, "Thread terminated due to fatal error: x"));
	CHECK(core_log_game_stopped(1, "VM: Access violation reading location 0x0 (unmapped memory)"));
	CHECK(!core_log_game_stopped(2, "Thread terminated due to fatal error: x"));
	CHECK(!core_log_game_stopped(1, "jit_initialize_failed stage=x"));
}

void fatal_before_abort(const std::string& work)
{
	// The process writes its fatal line and aborts right away (report_fatal_error).
	const std::string path = work + "/RPCS3-last-fatal.log";
	::unlink(path.c_str());
	const pid_t child = ::fork();
	if (child == 0)
	{
		fatal_slot slot(path);
		slot.write("F RSX: Fatal error: VK_ERROR_DEVICE_LOST", 1'700'000'000.0);
		std::abort();
	}
	int status = 0;
	::waitpid(child, &status, 0);
	CHECK(WIFSIGNALED(status) && WTERMSIG(status) == SIGABRT);
	std::string text;
	CHECK(read_small_file(path, text));
	CHECK(text.find("VK_ERROR_DEVICE_LOST") != std::string::npos);
	// Bounded: 2000 more fatal lines keep the file under its limit plus one generation.
	fatal_slot slot(path, 16 * 1024);
	for (int i = 0; i < 2000; ++i) slot.write("F repeated fatal " + std::to_string(i), 1.0);
	struct stat info{};
	CHECK(::stat(path.c_str(), &info) == 0 && info.st_size <= 16 * 1024);
	CHECK(slot.last().find("repeated fatal 1999") != std::string::npos);
}

void session_and_incidents(const std::string& work)
{
	// The previous process (another pid) died while running.
	session_record record;
	record.pid = 424242;
	record.build = "621";
	record.title = "BLES01717";
	record.core = "core621";
	record.started_s = 1'700'000'000.5;
	record.updated_s = 1'700'000'100.0;
	record.last_window = "avg_fps=12.000 p99_ms=210.000";
	record.last_fatal = "F SIG: Thread terminated due to fatal error: Null object.";
	const std::string path = work + "/RPCS3-session.txt";
	CHECK(write_atomically(path, record.serialize()));
	std::string text;
	CHECK(read_small_file(path, text));
	incident crash;
	CHECK(unexpected_end(text, ::getpid(), crash));
	CHECK(crash.kind == "unexpected_end" && crash.title == "BLES01717");
	const std::string crash_summary = summarize(crash);
	CHECK(crash_summary.find("Certainty: high") != std::string::npos);
	CHECK(crash_summary.find("Thread terminated due to fatal error") != std::string::npos);
	// Same pid (this process) or a clean stop: nothing.
	record.pid = ::getpid();
	CHECK(!unexpected_end(record.serialize(), ::getpid(), crash));
	record.pid = 1;
	record.state = "stopped";
	CHECK(!unexpected_end(record.serialize(), ::getpid(), crash));

	// A freeze episode, the menu opened twice during it, then recovered.
	incident_model model;
	model.begin_session("BLES01717", "621", "core621", 10.0);
	model.core_line("COREPROF frames=0 avg_fps=0.000 low1_fps=0 frametime_ms=0 p95_ms=0 p99_ms=0 wall_guest_fps=0.000 "
		"last_guest_flip_age_ms=4200.000 memory_mib=2100", 14.0);
	incident* freeze = model.core_line("FREEZE_EPISODE begin episode=1 session=3 reason=no_frames_busy outcome=open "
		"no_frames_s=3.000 episode_s=0.000 last_flip_age_s=3.000 flips_during=0 paused_s=0.000 pauses=0 suspended_s=0.000 "
		"suspensions=0 loading_s=0.000 busiest_cores=1.150 begin_busiest_cores=1.150 top=SPU[0x2000004]:0.98,PPU[0x1000000]:0.10 "
		"rsx_semaphore_wait=1 rsx_semaphore_stalled=1 rsx_semaphore_addr=0x40300010 rsx_semaphore_expected=0x2 "
		"rsx_semaphore_observed=0x1 dump=1 dump_suppressed=0 state=0 guest_flips=1234", 15.0);
	CHECK(freeze && freeze->kind == "freeze" && freeze->episode == "1");
	model.core_line("FREEZE_DUMP snapshot\nFREEZE_DUMP begin dump=1 reason=no_frames_busy no_frames_s=3.000 busiest_cores=1.150 "
		"state=0 ppu=6 spu=6 groups=1 raw_spu=0 lines=16 truncated=0 suppressed=0 busy_groups=0 episode=1\n"
		"FREEZE_DUMP waits dump=1 episode=1 ppu=6 ppu_calls=sys_cond_wait:4,guest_code:2 spu=6 spu_calls=guest_code:6 "
		"spu_groups=running:1 busy_groups=0\nFREEZE_DUMP rsx present=1 state=wait fifo_state=2 get=0x100 put=0x180 in_begin_end=0 ext_lock=0\n"
		"FREEZE_DUMP end dump=1 lines=4 truncated=0", 15.1);
	for (int i = 0; i < 2; ++i)
	{
		model.host({true, false, 0.0}, 16.0 + i);
		model.host({false, false, 0.0}, 16.5 + i);
	}
	model.core_line("FREEZE_EPISODE end episode=1 session=3 reason=no_frames_busy outcome=recovered no_frames_s=3.000 "
		"episode_s=25.500 last_flip_age_s=0.000 flips_during=40 paused_s=0.000 pauses=0 suspended_s=0.000 suspensions=0 "
		"loading_s=0.000 busiest_cores=0.600 begin_busiest_cores=1.150 top=none", 40.0);
	const auto& incidents = model.incidents();
	CHECK(incidents.size() == 1);
	const std::string summary = summarize(incidents.begin()->second);
	for (const char* expected : {"Game: BLES01717", "Build: 621", "Reason: no_frames_busy", "Outcome: recovered",
			"Certainty: high", "PPU waits (call:threads): sys_cond_wait:4,guest_code:2", "SPU waits (call:threads): guest_code:6",
			"opened 2 time(s) during it", "the menu does not pause the PS3 emulation", "addr=0x40300010",
			"Last guest frame (s ago): 0.000", "Last Core window: avg_fps=0.000"})
	{
		if (summary.find(expected) == std::string::npos) std::fprintf(stderr, "missing in summary: %s\n%s\n", expected, summary.c_str());
		CHECK(summary.find(expected) != std::string::npos);
	}

	// A stall that begins while the app is in the background is graded low.
	incident_model background;
	background.begin_session("BLUS30089", "621", "core621", 0.0);
	background.host({false, true, 0.0}, 1.0);
	incident* bg = background.core_line("FREEZE_EPISODE begin episode=1 session=4 reason=no_frames_idle outcome=open", 4.0);
	CHECK(bg && bg->background_at_begin);
	CHECK(certainty(*bg).rfind("low", 0) == 0);
	// A fatal guest fault while the UI lives.
	incident* fatal = background.fatal("F VM: Access violation reading location 0x0 (unmapped memory)", true, 5.0);
	CHECK(fatal && fatal->kind == "fatal" && certainty(*fatal).rfind("certain", 0) == 0);
	CHECK(background.fatal("F jit_initialize_failed", false, 6.0) == nullptr);
	CHECK(background.last_fatal().find("jit_initialize_failed") != std::string::npos);
}

long child_peak_kib(const std::function<void()>& body)
{
	const pid_t child = ::fork();
	if (child == 0)
	{
		body();
		std::_Exit(0);
	}
	int status = 0;
	struct rusage usage{};
	::wait4(child, &status, 0, &usage);
#if defined(__APPLE__)
	const long peak = static_cast<long>(usage.ru_maxrss / 1024); // bytes on Darwin
#else
	const long peak = static_cast<long>(usage.ru_maxrss); // KiB on Linux
#endif
	return WIFEXITED(status) && WEXITSTATUS(status) == 0 ? peak : -1;
}

void streaming_export(const std::string& work, std::uint64_t big_mib)
{
	// A large journal (big_mib MiB of JSON-like lines) and smaller ones.
	const std::string big = work + "/RPCS3-diagnostic.log";
	{
		std::ofstream out(big, std::ios::binary | std::ios::trunc);
		std::string line;
		std::uint64_t written = 0, index = 0;
		while (written < big_mib * 1024 * 1024)
		{
			line = "{\"stage\":\"core_log\",\"message\":\"E sys_fs: repeated line " + std::to_string(index++) + " ";
			line.append(120, 'x');
			line += "\"}\n";
			out << line;
			written += line.size();
		}
		out << "{\"stage\":\"core_log\",\"message\":\"LAST LINE MARKER\"}\n";
	}
	std::ofstream(work + "/RPCS3-milestones.log") << "{\"stage\":\"freeze_snapshot\"}\n";
	const std::vector<export_source> sources = {
		{work + "/RPCS3-milestones.log", "Milestones", 0},
		{big, "Diagnostic journal", 3u << 20},
		{work + "/RPCS3-causes.log", "Causes", 4u << 20},
	};
	const std::string output = work + "/report.txt";
	export_result result;
	const long baseline = child_peak_kib([] {});
	const long streaming = child_peak_kib([&] {
		const auto r = export_report(output, "RewindBox PS3 incident report\n", sources);
		std::_Exit(r.ok ? 0 : 1);
	});
	// The naive approach a share sheet invites: the whole journal in memory.
	const long naive = child_peak_kib([&] {
		std::ifstream in(big, std::ios::binary);
		std::stringstream whole;
		whole << in.rdbuf();
		std::_Exit(whole.str().size() > 0 ? 0 : 1);
	});
	result = export_report(output, "RewindBox PS3 incident report\n", sources);
	CHECK(result.ok && result.sources == 2 && result.missing == 1 && result.truncated == 1);
	std::string report;
	CHECK(read_small_file(output, report, 8u << 20));
	CHECK(report.rfind("RewindBox PS3 incident report", 0) == 0);
	CHECK(report.find("LAST LINE MARKER") != std::string::npos);              // the tail is the end of the journal
	CHECK(report.find("Causes (RPCS3-causes.log): absent") != std::string::npos);
	CHECK(result.bytes < (3u << 20) + 64 * 1024);
	// The first copied line of a cut tail is complete.
	const std::size_t section = report.find("Diagnostic journal");
	const std::size_t first = report.find('\n', section) + 1;
	CHECK(report.compare(first, 2, "{\"") == 0);
	std::printf("export: journal %llu MiB -> report %.2f MiB; peak RSS baseline %ld KiB, streaming %ld KiB (+%ld), "
		"whole-file read %ld KiB (+%ld)\n", static_cast<unsigned long long>(big_mib), result.bytes / 1048576.0,
		baseline, streaming, streaming - baseline, naive, naive - baseline);
	std::printf("EXPORT_JSON {\"journal_mib\": %llu, \"report_bytes\": %llu, \"baseline_kib\": %ld, \"streaming_kib\": %ld, \"whole_file_kib\": %ld}\n",
		static_cast<unsigned long long>(big_mib), static_cast<unsigned long long>(result.bytes), baseline, streaming, naive);
	CHECK(streaming > 0 && baseline > 0 && streaming - baseline < 2048);
	CHECK(naive - baseline > static_cast<long>(big_mib * 1024 / 2));
	::unlink(big.c_str());
}
}

int main(int argc, char** argv)
{
	if (argc < 2) return 2;
	const std::string work = argv[1];
	const std::uint64_t big_mib = argc > 2 ? std::strtoull(argv[2], nullptr, 10) : 256;
	repeated_burst();
	distinct_burst_budget();
	slow_disk();
	fatal_before_abort(work);
	session_and_incidents(work);
	streaming_export(work, big_mib);
	if (g_failures)
	{
		std::fprintf(stderr, "%d failure(s)\n", g_failures);
		return 1;
	}
	std::printf("host logging: all checks passed\n");
	return 0;
}
