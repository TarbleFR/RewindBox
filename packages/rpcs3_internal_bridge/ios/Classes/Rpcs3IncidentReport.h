#pragma once

// REWINDBOX_INCIDENT_REPORT_621: the PS3 incident a tester can share.
//
// The Core reports freezes as episodes (FREEZE_EPISODE begin/update/end, one
// FREEZE_DUMP snapshot per episode, rpcs3/ios/RPCS3IOSFreezeEpisode.h) and
// fatal-level lines through the log callback. The host adds what only it
// knows: whether its in-game menu was open (the menu does not pause the PS3
// emulation: the game keeps running behind it) and whether the app was in the
// background. This header turns them into one readable incident per episode,
// keeps a minimal session record that survives a process death, and exports a
// report by streaming bounded tails of the journals (never a whole file in
// memory). Plain C++ and POSIX only: test/rpcs3_core621_test.py runs it on
// Linux; Rpcs3Diagnostics.mm drives it on its serial diagnostics queue.

#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>

#include <algorithm>
#include <cerrno>
#include <cstdint>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <map>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

namespace rpcs3_host
{
// Value of `key=` in a space-separated record, at most `limit` bytes.
inline std::string token(std::string_view line, std::string_view key, std::size_t limit = 160)
{
	for (std::size_t at = line.find(key); at != std::string_view::npos; at = line.find(key, at + 1))
	{
		const bool start = at == 0 || line[at - 1] == ' ' || line[at - 1] == '\n';
		const std::size_t value = at + key.size();
		if (start && value < line.size() && line[value] == '=')
		{
			const std::size_t end = line.find_first_of(" \n", value + 1);
			return std::string(line.substr(value + 1, std::min(limit, (end == std::string_view::npos ? line.size() : end) - value - 1)));
		}
	}
	return {};
}

// The first line of `text` that starts with `prefix`, or empty.
inline std::string line_with(std::string_view text, std::string_view prefix)
{
	for (std::size_t at = text.find(prefix); at != std::string_view::npos; at = text.find(prefix, at + 1))
	{
		if (at == 0 || text[at - 1] == '\n')
		{
			const std::size_t end = text.find('\n', at);
			return std::string(text.substr(at, end == std::string_view::npos ? std::string_view::npos : end - at));
		}
	}
	return {};
}

inline std::string bounded(std::string_view text, std::size_t limit = 600)
{
	std::string result(text.substr(0, limit));
	for (char& c : result)
		if (c == '\n' || c == '\r') c = ' ';
	return result;
}

// ---------------------------------------------------------------------------
// Last fatal error: written on the logging thread with one write(2) before the
// callback returns, so it survives report_fatal_error's abort(). Bounded file
// with one previous generation.
class fatal_slot
{
public:
	explicit fatal_slot(std::string path = {}, std::size_t limit = 64 * 1024) : m_path(std::move(path)), m_limit(limit) {}
	~fatal_slot() { close_file(); }
	fatal_slot(const fatal_slot&) = delete;
	fatal_slot& operator=(const fatal_slot&) = delete;

	void set_path(std::string path)
	{
		std::lock_guard lock(m_mutex);
		close_file();
		m_path = std::move(path);
	}

	bool write(std::string_view line, double wall_time_s)
	{
		std::lock_guard lock(m_mutex);
		if (m_path.empty()) return false;
		if (m_fd < 0 && !open_file()) return false;
		char stamp[48];
		std::snprintf(stamp, sizeof(stamp), "%.3f pid=%d ", wall_time_s, static_cast<int>(::getpid()));
		std::string record = stamp;
		record += bounded(line, 4000);
		record += '\n';
		struct ::stat info{};
		if (::fstat(m_fd, &info) == 0 && static_cast<std::size_t>(info.st_size) + record.size() > m_limit)
		{
			close_file();
			::rename(m_path.c_str(), (m_path + ".1").c_str());
			if (!open_file()) return false;
		}
		std::size_t done = 0;
		while (done < record.size())
		{
			const ssize_t written = ::write(m_fd, record.data() + done, record.size() - done);
			if (written < 0 && errno == EINTR) continue;
			if (written <= 0) return false;
			done += static_cast<std::size_t>(written);
		}
		m_last.assign(record.data(), record.size() - 1);
		return true;
	}

	std::string last() const
	{
		std::lock_guard lock(m_mutex);
		return m_last;
	}

private:
	bool open_file()
	{
		m_fd = ::open(m_path.c_str(), O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
		return m_fd >= 0;
	}

	void close_file()
	{
		if (m_fd >= 0) ::close(m_fd);
		m_fd = -1;
	}

	mutable std::mutex m_mutex;
	std::string m_path;
	std::size_t m_limit;
	int m_fd = -1;
	std::string m_last;
};

// ---------------------------------------------------------------------------
// Minimal session record: rewritten atomically (temporary file + rename) at
// boot, at each Core report window, at episode, fatal and host events, and
// marked stopped at a clean stop. Found "running" at the next launch with
// another pid, it becomes an "unexpected end" incident.
struct session_record
{
	std::string state = "running"; // running | stopped
	long long pid = 0;
	std::string build, title, core;
	double started_s = 0.0, updated_s = 0.0;
	std::string last_window;  // compact COREPROF summary
	std::string last_episode; // last FREEZE_EPISODE line
	std::string last_fatal;   // last fatal-level line
	std::string host;         // menu / background state

	std::string serialize() const
	{
		std::string out = "REWINDBOX_PS3_SESSION v1\n";
		const auto field = [&](const char* key, const std::string& value) { out += key; out += '='; out += bounded(value, 1200); out += '\n'; };
		field("state", state);
		field("pid", std::to_string(pid));
		field("build", build);
		field("title", title);
		field("core", core);
		char time[64];
		std::snprintf(time, sizeof(time), "%.3f", started_s);
		field("started", time);
		std::snprintf(time, sizeof(time), "%.3f", updated_s);
		field("updated", time);
		field("last_window", last_window);
		field("last_episode", last_episode);
		field("last_fatal", last_fatal);
		field("host", host);
		return out;
	}

	static bool parse(std::string_view text, session_record& out)
	{
		if (text.substr(0, 25) != "REWINDBOX_PS3_SESSION v1\n") return false;
		std::size_t at = 25;
		while (at < text.size())
		{
			const std::size_t end = std::min(text.find('\n', at), text.size());
			const std::string_view line = text.substr(at, end - at);
			at = end + 1;
			const std::size_t equal = line.find('=');
			if (equal == std::string_view::npos) continue;
			const std::string_view key = line.substr(0, equal);
			const std::string value(line.substr(equal + 1));
			if (key == "state") out.state = value;
			else if (key == "pid") out.pid = std::atoll(value.c_str());
			else if (key == "build") out.build = value;
			else if (key == "title") out.title = value;
			else if (key == "core") out.core = value;
			else if (key == "started") out.started_s = std::atof(value.c_str());
			else if (key == "updated") out.updated_s = std::atof(value.c_str());
			else if (key == "last_window") out.last_window = value;
			else if (key == "last_episode") out.last_episode = value;
			else if (key == "last_fatal") out.last_fatal = value;
			else if (key == "host") out.host = value;
		}
		return true;
	}
};

inline bool write_atomically(const std::string& path, std::string_view data)
{
	const std::string temporary = path + ".tmp";
	const int fd = ::open(temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
	if (fd < 0) return false;
	std::size_t done = 0;
	while (done < data.size())
	{
		const ssize_t written = ::write(fd, data.data() + done, data.size() - done);
		if (written < 0 && errno == EINTR) continue;
		if (written <= 0) { ::close(fd); ::unlink(temporary.c_str()); return false; }
		done += static_cast<std::size_t>(written);
	}
	::close(fd);
	return ::rename(temporary.c_str(), path.c_str()) == 0;
}

inline bool read_small_file(const std::string& path, std::string& out, std::size_t limit = 256 * 1024)
{
	const int fd = ::open(path.c_str(), O_RDONLY | O_CLOEXEC);
	if (fd < 0) return false;
	out.clear();
	char buffer[4096];
	for (;;)
	{
		const ssize_t got = ::read(fd, buffer, sizeof(buffer));
		if (got < 0 && errno == EINTR) continue;
		if (got <= 0) break;
		out.append(buffer, static_cast<std::size_t>(got));
		if (out.size() >= limit) break;
	}
	::close(fd);
	return true;
}

// ---------------------------------------------------------------------------
// One incident per freeze episode, plus fatal and unexpected-end incidents.
struct incident
{
	std::string kind;  // freeze | fatal | unexpected_end
	std::string session, episode;
	std::string title, build, core;
	double began_s = 0.0, updated_s = 0.0;
	std::string begin_line, last_line, end_line;  // FREEZE_EPISODE records
	std::string dump_header, dump_waits, dump_rsx; // FREEZE_DUMP snapshot lines
	std::string fatal_line;
	std::string last_window;
	std::string host_sample; // last host sample: iOS thermal state (0-3), FPS, available memory
	bool menu_open_at_begin = false, background_at_begin = false;
	unsigned menu_opened = 0, backgrounded = 0; // during the episode
	std::string previous_session;               // unexpected_end: the session record found at launch
};

// What the host knows while the Core reports.
struct host_state
{
	bool menu_open = false;
	bool background = false;
	double changed_s = 0.0;
};

inline std::string certainty(const incident& value)
{
	if (value.kind == "fatal") return "certain: the emulator reported a fatal error that stops the game";
	if (value.kind == "unexpected_end" && value.previous_session.find("app=background") != std::string::npos)
		return "low: the process ended while RewindBox was in the background (iOS may end a suspended app)";
	if (value.kind == "unexpected_end")
		return !value.fatal_line.empty()
			? "high: the process ended during the session after a fatal error line"
			: "medium: the process ended during the session without a clean stop (cause not recorded)";
	if (value.background_at_begin) return "low: the stall began while RewindBox was in the background";
	const std::string reason = token(value.begin_line, "reason");
	const std::string outcome = token(value.end_line.empty() ? value.last_line : value.end_line, "outcome");
	const double seconds = std::atof(token(value.end_line.empty() ? value.last_line : value.end_line, "episode_s").c_str());
	if (outcome == "recovered" && seconds < 10.0)
		return "low: frames came back after a short stall (a long hitch or loading, not a freeze)";
	if (reason == "emulator_frozen") return "certain: the emulator froze on a guest fault";
	if (reason == "no_frames_busy") return "high: no guest frame while a thread group kept at least half a core busy";
	if (reason == "no_frames_idle") return "medium: no guest frame and little CPU activity (a quiet freeze or a long wait)";
	return "unknown";
}

inline std::string summarize(const incident& value)
{
	std::string out;
	const auto row = [&](const char* label, const std::string& text) {
		if (text.empty()) return;
		out += label;
		out += ": ";
		out += text;
		out += '\n';
	};
	char time[64];
	out += "RewindBox PS3 incident report\n";
	out += "=============================\n";
	row("Kind", value.kind);
	row("Game", value.title.empty() ? std::string("unknown") : value.title);
	row("Build", value.build);
	row("Core", value.core);
	row("Session", value.session);
	row("Episode", value.episode);
	std::snprintf(time, sizeof(time), "%.3f (Unix time)", value.began_s);
	row("Began", value.began_s > 0.0 ? time : "");
	row("Certainty", certainty(value));
	if (value.kind == "freeze")
	{
		const std::string& latest = value.end_line.empty() ? value.last_line : value.end_line;
		row("Reason", token(value.begin_line, "reason"));
		row("Outcome", token(latest.empty() ? value.begin_line : latest, "outcome"));
		row("No frame before the episode (s of running time)", token(value.begin_line, "no_frames_s"));
		row("Episode running time (s)", token(latest.empty() ? value.begin_line : latest, "episode_s"));
		row("Last guest frame (s ago)", token(latest.empty() ? value.begin_line : latest, "last_flip_age_s"));
		row("Guest frames during the episode", token(latest.empty() ? value.begin_line : latest, "flips_during"));
		row("Last known progress (busiest threads)", token(value.begin_line, "top"));
		row("Busiest thread group (cores)", token(value.begin_line, "busiest_cores"));
		row("Paused / suspended / loading (s)", token(latest.empty() ? value.begin_line : latest, "paused_s") + " / " +
			token(latest.empty() ? value.begin_line : latest, "suspended_s") + " / " +
			token(latest.empty() ? value.begin_line : latest, "loading_s"));
		std::string rsx = "semaphore_wait=" + token(value.begin_line, "rsx_semaphore_wait") + " stalled=" +
			token(value.begin_line, "rsx_semaphore_stalled") + " addr=" + token(value.begin_line, "rsx_semaphore_addr") +
			" expected=" + token(value.begin_line, "rsx_semaphore_expected") + " observed=" + token(value.begin_line, "rsx_semaphore_observed");
		if (!value.dump_rsx.empty()) rsx += " | " + bounded(value.dump_rsx, 300);
		row("RSX wait", rsx);
		row("PPU waits (call:threads)", token(value.dump_waits, "ppu_calls", 300));
		row("SPU waits (call:threads)", token(value.dump_waits, "spu_calls", 300));
		row("SPU groups (state:groups)", token(value.dump_waits, "spu_groups", 300));
		row("Thread dump", value.dump_header.empty() ? std::string("not taken (see dump_suppressed)") : bounded(value.dump_header, 400));
		row("RewindBox menu", std::string(value.menu_open_at_begin ? "open when the stall began" : "closed when the stall began") +
			(value.menu_opened ? ", opened " + std::to_string(value.menu_opened) + " time(s) during it" : std::string()) +
			" (the menu does not pause the PS3 emulation)");
		row("App state", std::string(value.background_at_begin ? "background when the stall began" : "foreground when the stall began") +
			(value.backgrounded ? ", sent to the background " + std::to_string(value.backgrounded) + " time(s) during it" : std::string()));
	}
	row("Fatal error", bounded(value.fatal_line, 800));
	row("Last Core window", bounded(value.last_window, 400));
	row("Last host sample (iOS thermal state 0-3, FPS, available bytes)", bounded(value.host_sample, 200));
	if (!value.previous_session.empty())
	{
		out += "\nPrevious session record\n-----------------------\n";
		out += value.previous_session;
	}
	out += "\nRaw records\n-----------\n";
	for (const std::string* line : {&value.begin_line, &value.last_line, &value.end_line, &value.dump_header, &value.dump_waits, &value.dump_rsx})
	{
		if (!line->empty()) { out += bounded(*line, 2000); out += '\n'; }
	}
	return out;
}

class incident_model
{
public:
	void begin_session(std::string title, std::string build, std::string core, double now_s)
	{
		m_title = std::move(title);
		m_build = std::move(build);
		m_core = std::move(core);
		m_session_started_s = now_s;
		m_open.clear();
	}

	void host(const host_state& state, double now_s)
	{
		for (auto& [id, value] : m_open)
		{
			if (state.menu_open && !m_host.menu_open) value.menu_opened++;
			if (state.background && !m_host.background) value.backgrounded++;
			value.updated_s = now_s;
		}
		m_host = state;
		m_host.changed_s = now_s;
	}

	const host_state& current_host() const { return m_host; }

	// The host's per-second sample (performance_sample stage).
	void host_sample(std::string_view line)
	{
		m_host_sample = "thermal=" + token(line, "thermal") + " fps=" + token(line, "fps") + " available=" + token(line, "available");
	}

	// A Core line (core_log stage). Returns the incident it created or changed, or nullptr.
	incident* core_line(std::string_view line, double now_s)
	{
		if (line.find("COREPROF frames=") != std::string_view::npos)
		{
			m_last_window = "avg_fps=" + token(line, "avg_fps") + " p99_ms=" + token(line, "p99_ms") + " wall_guest_fps=" +
				token(line, "wall_guest_fps") + " last_guest_flip_age_ms=" + token(line, "last_guest_flip_age_ms") +
				" memory_mib=" + token(line, "memory_mib");
			return nullptr;
		}
		if (const std::string record = line_with(line, "FREEZE_EPISODE "); !record.empty())
		{
			const std::string event = record.substr(15, record.find(' ', 15) - 15);
			const std::string key = token(record, "session") + ":" + token(record, "episode");
			auto& value = m_open[key];
			if (value.kind.empty())
			{
				value.kind = "freeze";
				value.session = token(record, "session");
				value.episode = token(record, "episode");
				value.title = m_title;
				value.build = m_build;
				value.core = m_core;
				value.began_s = now_s;
				value.menu_open_at_begin = m_host.menu_open;
				// A stall that began within 2 s of going to the background counts as background.
				value.background_at_begin = m_host.background || (m_background_left_s > 0.0 && now_s - m_background_left_s < 2.0);
			}
			if (event == "begin") value.begin_line = record;
			else if (event == "end") value.end_line = record;
			else value.last_line = record;
			value.last_window = m_last_window;
			value.host_sample = m_host_sample;
			value.updated_s = now_s;
			m_changed = key;
			return &value;
		}
		if (line.find("FREEZE_DUMP snapshot") != std::string_view::npos)
		{
			const std::string header = line_with(line, "FREEZE_DUMP begin ");
			const std::string episode = token(header, "episode");
			for (auto& [key, value] : m_open)
			{
				if (value.episode == episode)
				{
					value.dump_header = header;
					value.dump_waits = line_with(line, "FREEZE_DUMP waits ");
					value.dump_rsx = line_with(line, "FREEZE_DUMP rsx ");
					m_changed = key;
					return &value;
				}
			}
		}
		return nullptr;
	}

	// A fatal-level line; game_stopped: the game cannot continue.
	incident* fatal(std::string_view line, bool game_stopped, double now_s)
	{
		m_last_fatal = bounded(line, 1200);
		if (!game_stopped) return nullptr;
		const std::string key = "fatal:" + std::to_string(++m_fatal_count);
		auto& value = m_open[key];
		value.kind = "fatal";
		value.title = m_title;
		value.build = m_build;
		value.core = m_core;
		value.began_s = value.updated_s = now_s;
		value.fatal_line = m_last_fatal;
		value.last_window = m_last_window;
		value.host_sample = m_host_sample;
		m_changed = key;
		return &value;
	}

	void background_left(double now_s) { m_background_left_s = now_s; }
	const std::string& last_fatal() const { return m_last_fatal; }
	const std::string& last_window() const { return m_last_window; }
	const std::map<std::string, incident>& incidents() const { return m_open; }

private:
	std::string m_title, m_build, m_core, m_last_window, m_last_fatal, m_changed, m_host_sample;
	double m_session_started_s = 0.0, m_background_left_s = 0.0;
	unsigned m_fatal_count = 0;
	host_state m_host;
	std::map<std::string, incident> m_open;
};

// The unexpected-end incident of a session record found at launch, or false
// when the previous session stopped cleanly or belongs to this process.
inline bool unexpected_end(std::string_view record_text, long long current_pid, incident& out)
{
	session_record record;
	if (!session_record::parse(record_text, record) || record.state != "running" || record.pid == current_pid) return false;
	out = {};
	out.kind = "unexpected_end";
	out.title = record.title;
	out.build = record.build;
	out.core = record.core;
	out.began_s = record.started_s;
	out.updated_s = record.updated_s;
	out.fatal_line = record.last_fatal;
	out.last_window = record.last_window;
	out.begin_line = record.last_episode;
	out.previous_session = std::string(record_text);
	return true;
}

// ---------------------------------------------------------------------------
// Report export: the summary, then a bounded tail of each journal, copied in
// 64 KiB steps. Memory stays O(buffer) whatever the journal sizes.
struct export_source
{
	std::string path;      // absolute
	std::string label;     // section title
	std::uint64_t tail = 0; // bytes kept from the end (0: whole file)
};

struct export_result
{
	bool ok = false;
	std::uint64_t bytes = 0, sources = 0, missing = 0, truncated = 0;
	std::string error;
};

inline export_result export_report(const std::string& output, std::string_view summary,
	const std::vector<export_source>& sources, std::size_t buffer_size = 64 * 1024)
{
	export_result result;
	const std::string temporary = output + ".tmp";
	const int out = ::open(temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC | O_CLOEXEC, 0644);
	if (out < 0)
	{
		result.error = std::strerror(errno);
		return result;
	}
	const auto put = [&](const char* data, std::size_t size) {
		std::size_t done = 0;
		while (done < size)
		{
			const ssize_t written = ::write(out, data + done, size - done);
			if (written < 0 && errno == EINTR) continue;
			if (written <= 0) return false;
			done += static_cast<std::size_t>(written);
		}
		result.bytes += size;
		return true;
	};
	bool ok = put(summary.data(), summary.size());
	std::vector<char> buffer(buffer_size);
	for (const auto& source : sources)
	{
		if (!ok) break;
		const int in = ::open(source.path.c_str(), O_RDONLY | O_CLOEXEC);
		std::string header = "\n\n===== " + source.label + " (" + source.path.substr(source.path.find_last_of('/') + 1) + ")";
		if (in < 0)
		{
			result.missing++;
			header += ": absent =====\n";
			ok = put(header.data(), header.size());
			continue;
		}
		struct ::stat info{};
		::fstat(in, &info);
		const std::uint64_t size = static_cast<std::uint64_t>(info.st_size);
		std::uint64_t offset = 0;
		if (source.tail && size > source.tail)
		{
			offset = size - source.tail;
			result.truncated++;
			header += ", last " + std::to_string(source.tail) + " of " + std::to_string(size) + " bytes";
		}
		header += " =====\n";
		ok = put(header.data(), header.size());
		bool skip_partial = offset != 0; // start at the first complete line of the tail
		while (ok)
		{
			const ssize_t got = ::pread(in, buffer.data(), buffer.size(), static_cast<off_t>(offset));
			if (got < 0 && errno == EINTR) continue;
			if (got <= 0) break;
			offset += static_cast<std::uint64_t>(got);
			std::size_t start = 0;
			if (skip_partial)
			{
				const void* newline = std::memchr(buffer.data(), '\n', static_cast<std::size_t>(got));
				if (!newline) continue;
				start = static_cast<std::size_t>(static_cast<const char*>(newline) - buffer.data()) + 1;
				skip_partial = false;
			}
			ok = put(buffer.data() + start, static_cast<std::size_t>(got) - start);
		}
		::close(in);
		result.sources++;
	}
	if (::close(out) != 0) ok = false;
	if (!ok || ::rename(temporary.c_str(), output.c_str()) != 0)
	{
		::unlink(temporary.c_str());
		if (result.error.empty()) result.error = "write failed";
		return result;
	}
	result.ok = true;
	return result;
}
}
