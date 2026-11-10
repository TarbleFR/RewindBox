// CELL546 scenarios. The namespaces before/after hold production bodies copied
// verbatim from the 545 baseline and the 546 tree by test/rpcs3_cell546_test.py.

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

struct zip_result
{
	int level = -100;
	usz bytes = 0;
	double best_ms = 0;
	bool round_trip = false;
};

// Read back with the production object reader, as ObjectCache::load does.
static bool read_back(const std::string& gz, const std::string& expected)
{
	const auto read_at = [&](std::uint64_t offset, void* data, std::size_t count) -> std::size_t
	{
		if (offset >= gz.size()) return 0;
		const usz n = std::min<usz>(count, gz.size() - offset);
		std::memcpy(data, gz.data() + offset, n);
		return n;
	};
	const usz size = jit_object_buffer::gzip_size(gz.size(), read_at);
	if (size != expected.size()) return false;
	std::string out(size, '\0');
	return jit_object_buffer::inflate(gz.size(), read_at, out.data(), out.size()) && out == expected;
}

template <typename File, typename Zip>
static zip_result run_zip(const std::string& sample, Zip&& zip, int rounds)
{
	zip_result r;
	std::string first;
	for (int i = 0; i < rounds; i++)
	{
		File out;
		g_deflate_level = -100;
		const auto t0 = std::chrono::steady_clock::now();
		const bool ok = zip(sample.data(), sample.size(), out);
		const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
		CHECK(ok);
		if (!i || ms < r.best_ms) r.best_ms = ms;
		if (!i)
		{
			r.level = g_deflate_level;
			r.bytes = out.bytes.size();
			first = out.bytes;
		}
		else
		{
			// Deterministic output for the same input and level.
			CHECK(out.bytes == first);
		}
	}
	r.round_trip = read_back(first, sample);
	return r;
}

template <typename Serial, typename Reset, typename Trace, typename FsTrace>
static usz trace_lines_without_restore(std::vector<std::string>& lines, Trace&& trace, FsTrace&& fs_trace, Reset&&)
{
	// A fresh boot's in-memory archive (sys_process containers): 4 bytes, no file handler.
	const usz start = lines.size();
	std::thread([&]
	{
		Serial ar;
		ar.data.resize(4);
		trace(ar, "id_manager::id_map<lv2_memory_container>", true);
		ar.pos = 4;
		trace(ar, "id_manager::id_map<lv2_memory_container>", false);
		fs_trace(ar, "name_ready", 1, 0, 4);
	}).join();
	return lines.size() - start;
}

template <typename Serial, typename Reset, typename Trace, typename FsTrace>
static void trace_restore(std::vector<std::string>& lines, Reset&& reset, Trace&& trace, FsTrace&& fs_trace, usz& fxo, usz& fs, bool& limits, u64& max_elapsed)
{
	const usz start = lines.size();
	std::thread([&]
	{
		g_now = 540'000'000'000ull; // Device uptime in microseconds, as in build 541.
		reset();
		Serial ar;
		ar.data.resize(16);
		for (int i = 0; i < 300; i++)
		{
			g_now += 170;
			trace(ar, "id_manager::id_map<vdec_context>", true);
			trace(ar, "id_manager::id_map<vdec_context>", false);
			fs_trace(ar, "file_open_end", static_cast<u32>(i), 1, 1);
		}
		// The archive being written is never traced.
		Serial writer;
		writer.writing = true;
		trace(writer, "writer", true);
		fs_trace(writer, "writer", 0, 0, 0);
	}).join();
	fxo = fs = 0; limits = false; max_elapsed = 0;
	usz fxo_limit = 0, fs_limit = 0;
	for (usz i = start; i < lines.size(); i++)
	{
		const std::string& l = lines[i];
		fxo += l.find("phase=fxo_type_") != std::string::npos;
		fs += l.find("phase=fs_stage") != std::string::npos;
		fxo_limit += l.find("phase=fxo_trace_limit events=512") != std::string::npos;
		fs_limit += l.find("phase=fs_trace_limit events=256") != std::string::npos;
		CHECK(l.find("type=writer") == std::string::npos && l.find("stage=writer") == std::string::npos);
		if (const auto at = l.find("elapsed_us="); at != std::string::npos)
			max_elapsed = std::max<u64>(max_elapsed, std::strtoull(l.c_str() + at + 11, nullptr, 10));
	}
	limits = fxo_limit == 1 && fs_limit == 1;
}

int main(int argc, char** argv)
{
	if (argc != 3) return 2;
	const std::string_view platform = argv[1];
	std::ifstream in(argv[2], std::ios::binary);
	const std::string sample((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
	CHECK(sample.size() >= (1u << 20));

	const auto after = run_zip<zip_after::fs::file>(sample, [](const void* p, usz n, zip_after::fs::file& out) { return zip_after::zip(p, n, out); }, 3);
	const auto before = run_zip<zip_before::fs::file>(sample, [](const void* p, usz n, zip_before::fs::file& out) { return zip_before::zip(p, n, out); }, 3);
	// Callers that request the threaded path for a large buffer (upstream log viewer, not built on iOS).
	const auto threaded_after = run_zip<zip_after::fs::file>(sample, [](const void* p, usz n, zip_after::fs::file& out) { return zip_after::zip(p, n, out, true); }, 1);
	const auto threaded_before = run_zip<zip_before::fs::file>(sample, [](const void* p, usz n, zip_before::fs::file& out) { return zip_before::zip(p, n, out, true); }, 1);
	CHECK(after.round_trip && before.round_trip && threaded_after.round_trip && threaded_before.round_trip);
	CHECK(before.level == 9);
	const bool large = sample.size() >= 0x40'0000;
	CHECK(threaded_before.level == (large ? 8 : 9));
	if (platform == "ios")
	{
		CHECK(after.level == Z_BEST_SPEED && threaded_after.level == Z_BEST_SPEED);
		CHECK(after.best_ms < before.best_ms);
		CHECK(after.bytes <= before.bytes * 115 / 100);
	}
	else
	{
		// Other platforms keep the upstream levels byte for byte.
		CHECK(after.level == before.level && threaded_after.level == threaded_before.level);
	}

	using trace_serial_after = trace_after::utils::serial;
	using trace_serial_before = trace_before::utils::serial;
	auto& la = trace_after::sys_log.lines;
	auto& lb = trace_before::sys_log.lines;
	g_now = 540'567'673'530ull;
	const usz spurious_after = trace_lines_without_restore<trace_serial_after>(la,
		[](trace_serial_after& ar, std::string_view n, bool b) { trace_after::serial_restore_trace(ar, n, b); },
		[](trace_serial_after& ar, std::string_view s, u32 id, u32 t, u64 v) { trace_after::serial_restore_fs_trace(ar, s, id, t, v); },
		[] { trace_after::serial_restore_trace_reset(); });
	const usz spurious_before = trace_lines_without_restore<trace_serial_before>(lb,
		[](trace_serial_before& ar, std::string_view n, bool b) { trace_before::serial_restore_trace(ar, n, b); },
		[](trace_serial_before& ar, std::string_view s, u32 id, u32 t, u64 v) { trace_before::serial_restore_fs_trace(ar, s, id, t, v); },
		[] { trace_before::serial_restore_trace_reset(); });
	// 545 control: the build 541 line, elapsed_us equal to the device uptime.
	const bool control_uptime = spurious_before == 3 && lb.front().find("elapsed_us=540567673530") != std::string::npos;
	CHECK(spurious_after == 0);
	CHECK(control_uptime);

	usz fxo_a, fs_a, fxo_b, fs_b; bool limits_a, limits_b; u64 elapsed_a, elapsed_b;
	trace_restore<trace_serial_after>(la, [] { trace_after::serial_restore_trace_reset(); },
		[](trace_serial_after& ar, std::string_view n, bool b) { trace_after::serial_restore_trace(ar, n, b); },
		[](trace_serial_after& ar, std::string_view s, u32 id, u32 t, u64 v) { trace_after::serial_restore_fs_trace(ar, s, id, t, v); },
		fxo_a, fs_a, limits_a, elapsed_a);
	trace_restore<trace_serial_before>(lb, [] { trace_before::serial_restore_trace_reset(); },
		[](trace_serial_before& ar, std::string_view n, bool b) { trace_before::serial_restore_trace(ar, n, b); },
		[](trace_serial_before& ar, std::string_view s, u32 id, u32 t, u64 v) { trace_before::serial_restore_fs_trace(ar, s, id, t, v); },
		fxo_b, fs_b, limits_b, elapsed_b);
	// A real restore is traced exactly as in 545: same budgets, elapsed relative to its start.
	CHECK(fxo_a == 512 && fs_a == 256 && limits_a);
	CHECK(fxo_a == fxo_b && fs_a == fs_b && limits_b && elapsed_a == elapsed_b);
	// Both budgets are reached after 256 iterations of 170 us.
	CHECK(elapsed_a == 256u * 170u);
	// A thread that never began a restore stays silent after another thread restored.
	const usz later_after = trace_lines_without_restore<trace_serial_after>(la,
		[](trace_serial_after& ar, std::string_view n, bool b) { trace_after::serial_restore_trace(ar, n, b); },
		[](trace_serial_after& ar, std::string_view s, u32 id, u32 t, u64 v) { trace_after::serial_restore_fs_trace(ar, s, id, t, v); },
		[] {});
	CHECK(later_after == 0);

	std::printf("{\"failures\": %d, \"platform\": \"%s\", \"sampleBytes\": %zu,\n", failures, std::string(platform).c_str(), sample.size());
	std::printf(" \"jitObject\": {\"after\": {\"level\": %d, \"bytes\": %zu, \"bestMs\": %.3f, \"productionReaderRoundTrip\": %s},\n",
		after.level, after.bytes, after.best_ms, after.round_trip ? "true" : "false");
	std::printf("  \"before\": {\"level\": %d, \"bytes\": %zu, \"bestMs\": %.3f, \"productionReaderRoundTrip\": %s},\n",
		before.level, before.bytes, before.best_ms, before.round_trip ? "true" : "false");
	std::printf("  \"speedup\": %.3f, \"sizeRatio\": %.4f},\n", before.best_ms / after.best_ms, static_cast<double>(after.bytes) / static_cast<double>(before.bytes));
	std::printf(" \"threadedLargeBuffer\": {\"afterLevel\": %d, \"beforeLevel\": %d},\n", threaded_after.level, threaded_before.level);
	std::printf(" \"restoreTrace\": {\"withoutRestoreAfter\": %zu, \"withoutRestoreBefore\": %zu, \"beforeElapsedWasUptime\": %s,\n",
		spurious_after, spurious_before, control_uptime ? "true" : "false");
	std::printf("  \"restoreFxoLines\": %zu, \"restoreFsLines\": %zu, \"limitsLogged\": %s, \"maxElapsedUs\": %llu, \"sameAsBefore\": %s,\n",
		fxo_a, fs_a, limits_a ? "true" : "false", static_cast<unsigned long long>(elapsed_a), fxo_a == fxo_b && fs_a == fs_b && elapsed_a == elapsed_b ? "true" : "false");
	std::printf("  \"otherThreadAfterRestore\": %zu}}\n", later_after);
	return failures ? 1 : 0;
}
