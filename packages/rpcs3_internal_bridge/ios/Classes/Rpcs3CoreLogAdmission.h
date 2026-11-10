#pragma once

// REWINDBOX_CORE_LOG_BOUNDED_621: what the RPCS3 log callback (RPCS3Log in
// Rpcs3InternalBridgePlugin.mm) may hand to the diagnostics writer, decided on
// the emulator thread that logs, without any file access there.
//
// Before 621 every admitted Core line was written by dispatch_sync on the
// diagnostics queue (REWINDBOX_CORE_LOG_DURABLE_V1): a PPU, SPU or RSX thread
// that logged waited for its own JSON line and the cause/performance appends,
// and for every asynchronous record queued before it, so a slow disk stalled
// emulation. Now:
//  - ordinary lines (always, error and warning levels): at most per_second per
//    second, a run of the identical message collapsed into one LOG_REPEAT line,
//    and at most backlog_lines / backlog_bytes waiting for the writer; refused
//    lines are counted and reported (LOG_BUDGET, or LOG_BACKLOG when
//    per_second is 0: the application's RPCS3Log keeps its Build 283 budget of
//    128 lines per second, with its own LOG_BUDGET line, before this admission);
//  - profiler and diagnostic lines (COREPROF, FREEZE_*, ...): not budgeted, but
//    bounded by the backlog plus a reserve of their own;
//  - fatal-level lines (logs::level::fatal = 1): never dropped; the caller also writes them at once to
//    RPCS3-last-fatal.log (write(2) before returning, kept through abort()),
//    so the last fatal error survives the process.
// Every line is then written asynchronously. Thread-safe; header-only C++ so
// test/rpcs3_core621_test.py runs it on Linux.

#include <cstdint>
#include <cstring>
#include <mutex>
#include <string>
#include <string_view>

namespace rpcs3_host
{
struct core_log_limits
{
	std::uint32_t per_second = 128;         // ordinary lines per second (0: the caller budgets them)
	std::uint32_t backlog_lines = 2048;     // lines admitted but not yet written
	std::uint64_t backlog_bytes = 2u << 20; // their bytes
	std::uint32_t reserve_lines = 512;      // extra backlog for profiler and fatal lines
	double repeat_window_s = 2.0;           // identical consecutive lines collapse within it
};

enum class core_log_kind : std::uint32_t
{
	ordinary = 0,
	profiler = 1,
	fatal = 2,
};

struct core_log_decision
{
	bool write = false;        // hand the line to the asynchronous writer
	bool fatal = false;        // also write it synchronously to the last-fatal file
	bool game_stopped = false; // the game cannot continue (thread terminated, guest fault)
	std::string before;        // LOG_REPEAT / LOG_BUDGET line(s) to write first, if any
};

struct core_log_counters
{
	std::uint64_t admitted = 0, budget_dropped = 0, backlog_dropped = 0, repeats = 0;
	std::uint64_t fatal = 0, backlog_peak_lines = 0, backlog_peak_bytes = 0;
	std::uint64_t pending_lines = 0, pending_bytes = 0;
};

// Lines whose text says the game itself cannot continue while the process
// lives (Utilities/Thread.cpp: a named thread's fatal error ends that thread;
// a guest access violation freezes the emulator).
inline bool core_log_game_stopped(int level, std::string_view message) noexcept
{
	if (level != 1) return false;
	return message.find("Thread terminated due to fatal error") != std::string_view::npos ||
		message.find("Access violation ") != std::string_view::npos;
}

class core_log_admission
{
public:
	explicit core_log_admission(core_log_limits limits = {}) : m_limits(limits) {}

	// Emulator thread. `now_s` is a monotonic time in seconds. The caller writes
	// decision.before (if any) then the message (if decision.write), and reports
	// each written line with written().
	core_log_decision admit(int level, std::string_view message, bool profiler, double now_s)
	{
		std::lock_guard lock(m_mutex);
		core_log_decision decision = decide(level, message, profiler, now_s);
		if (!decision.before.empty()) reserve(decision.before.size(), lines(decision.before));
		if (decision.write) reserve(message.size(), 1);
		return decision;
	}

	// Writer: one line (or `lines`) of `bytes` bytes left the backlog.
	void written(std::uint64_t bytes, std::uint64_t lines = 1) noexcept
	{
		std::lock_guard lock(m_mutex);
		m_counters.pending_lines = m_counters.pending_lines > lines ? m_counters.pending_lines - lines : 0;
		m_counters.pending_bytes = m_counters.pending_bytes > bytes ? m_counters.pending_bytes - bytes : 0;
	}

	// The LOG_REPEAT / LOG_BUDGET line of a run still open (session end,
	// report export); counted as pending, to be reported with written().
	std::string flush()
	{
		std::lock_guard lock(m_mutex);
		std::string line;
		flush_repeat(line);
		report_drops(line);
		if (!line.empty()) reserve(line.size(), lines(line));
		return line;
	}

	core_log_counters counters() const
	{
		std::lock_guard lock(m_mutex);
		return m_counters;
	}

	// Lines in a `before` / flush() text (joined by '\n').
	static std::uint64_t lines(std::string_view text) noexcept
	{
		std::uint64_t count = text.empty() ? 0 : 1;
		for (const char c : text) count += c == '\n';
		return count;
	}

private:
	core_log_decision decide(int level, std::string_view message, bool profiler, double now_s)
	{
		core_log_decision decision;
		// logs::level::fatal is 1; always (0), error (2) and the profiler-exempt
		// higher levels keep the Build 283 rules: only profiler lines skip the budget.
		const bool fatal = level == 1;
		decision.fatal = fatal;
		decision.game_stopped = core_log_game_stopped(level, message);
		const core_log_kind kind = fatal ? core_log_kind::fatal
			: profiler ? core_log_kind::profiler : core_log_kind::ordinary;

		// Once per second: the drops and the count of a run still going on are
		// reported, so an endless loop of one message is counted every window.
		if (m_window_s == 0.0 || now_s - m_window_s >= 1.0)
		{
			flush_repeat(decision.before);
			report_drops(decision.before);
			m_window_s = now_s;
			m_window_count = 0;
		}

		if (kind == core_log_kind::ordinary)
		{
			// A run of the same message: count it, write it once.
			if (m_last_valid && now_s - m_last_time_s <= m_limits.repeat_window_s &&
				message.size() == m_last_size && hash(message) == m_last_hash)
			{
				m_repeat_count++;
				m_counters.repeats++;
				m_last_time_s = now_s;
				return decision;
			}
			flush_repeat(decision.before);
			m_last_valid = true;
			m_last_hash = hash(message);
			m_last_size = message.size();
			m_last_time_s = now_s;
			m_last_text.assign(utf8_prefix(message, 200));
		}

		if (kind == core_log_kind::ordinary && m_limits.per_second && m_window_count >= m_limits.per_second)
		{
			m_counters.budget_dropped++;
			m_window_budget_dropped++;
			return decision;
		}

		const bool reserved = kind != core_log_kind::ordinary;
		const std::uint64_t line_limit = m_limits.backlog_lines + (reserved ? m_limits.reserve_lines : 0);
		const std::uint64_t byte_limit = m_limits.backlog_bytes + (reserved ? m_limits.backlog_bytes / 4 : 0);
		if (kind != core_log_kind::fatal &&
			(m_counters.pending_lines >= line_limit || m_counters.pending_bytes + message.size() > byte_limit))
		{
			m_counters.backlog_dropped++;
			m_window_backlog_dropped++;
			return decision;
		}

		if (kind == core_log_kind::ordinary) m_window_count++;
		if (fatal) m_counters.fatal++;
		m_counters.admitted++;
		decision.write = true;
		return decision;
	}

	void reserve(std::uint64_t bytes, std::uint64_t lines) noexcept
	{
		m_counters.pending_lines += lines;
		m_counters.pending_bytes += bytes;
		if (m_counters.pending_lines > m_counters.backlog_peak_lines) m_counters.backlog_peak_lines = m_counters.pending_lines;
		if (m_counters.pending_bytes > m_counters.backlog_peak_bytes) m_counters.backlog_peak_bytes = m_counters.pending_bytes;
	}

	// At most `limit` bytes, never ending inside a UTF-8 sequence.
	static std::string_view utf8_prefix(std::string_view text, std::size_t limit) noexcept
	{
		if (text.size() <= limit) return text;
		std::size_t end = limit;
		while (end > 0 && (static_cast<unsigned char>(text[end]) & 0xC0) == 0x80) end--;
		return text.substr(0, end);
	}

	static std::uint64_t hash(std::string_view text) noexcept
	{
		std::uint64_t value = 1469598103934665603ull;
		for (const unsigned char c : text)
		{
			value ^= c;
			value *= 1099511628211ull;
		}
		return value;
	}

	void flush_repeat(std::string& out)
	{
		if (!m_repeat_count) return;
		append(out, "LOG_REPEAT count=" + std::to_string(m_repeat_count) + " message=" + m_last_text);
		m_repeat_count = 0;
	}

	void report_drops(std::string& out)
	{
		if (!m_window_budget_dropped && !m_window_backlog_dropped) return;
		if (!m_limits.per_second)
		{
			// The caller's budget reports its own drops (Build 283 LOG_BUDGET line).
			append(out, "LOG_BACKLOG dropped=" + std::to_string(m_window_backlog_dropped) + " backlog_lines=" +
				std::to_string(m_limits.backlog_lines) + " repeats_total=" + std::to_string(m_counters.repeats) +
				" backlog_peak_lines=" + std::to_string(m_counters.backlog_peak_lines) + " scope=core_log_admission_621");
			m_window_backlog_dropped = 0;
			return;
		}
		// The first two fields keep the Build 546 LOG_BUDGET line readable by older tools.
		append(out, "LOG_BUDGET dropped=" + std::to_string(m_window_budget_dropped) + " limit_per_s=" +
			std::to_string(m_limits.per_second) + " backlog_dropped=" + std::to_string(m_window_backlog_dropped) +
			" repeats_total=" + std::to_string(m_counters.repeats) + " backlog_peak_lines=" +
			std::to_string(m_counters.backlog_peak_lines) + " scope=core_log_admission_621");
		m_window_budget_dropped = 0;
		m_window_backlog_dropped = 0;
	}

	static void append(std::string& out, const std::string& line)
	{
		if (!out.empty()) out += '\n';
		out += line;
	}

	core_log_limits m_limits;
	mutable std::mutex m_mutex;
	core_log_counters m_counters;
	bool m_last_valid = false;
	std::uint64_t m_last_hash = 0;
	std::size_t m_last_size = 0;
	double m_last_time_s = 0.0;
	std::string m_last_text;
	std::uint64_t m_repeat_count = 0;
	double m_window_s = 0.0;
	std::uint32_t m_window_count = 0;
	std::uint64_t m_window_budget_dropped = 0, m_window_backlog_dropped = 0;
};
}
