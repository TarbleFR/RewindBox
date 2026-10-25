// CELL545 scenarios. The namespaces before/after hold production bodies copied
// verbatim from the 543 baseline and the 545 tree by test/rpcs3_cell545_test.py.

static std::string json_escape(std::string_view s)
{
	std::string out;
	for (const char c : s)
	{
		if (c == '"' || c == '\\') out += '\\';
		out += c;
	}
	return out;
}

static std::atomic<usz> g_allocations{0};
static bool g_count_allocations = false;

void* operator new(std::size_t size)
{
	if (g_count_allocations) g_allocations++;
	if (void* p = std::malloc(size ? size : 1)) return p;
	std::abort();
}

void* operator new(std::size_t size, const std::nothrow_t&) noexcept
{
	if (g_count_allocations) g_allocations++;
	return std::malloc(size ? size : 1);
}

void operator delete(void* p) noexcept { std::free(p); }
void operator delete(void* p, std::size_t) noexcept { std::free(p); }
void operator delete(void* p, const std::nothrow_t&) noexcept { std::free(p); }

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

static std::string pkg_report()
{
	using pkg_after::select;
	const std::string theme = "/sandbox/dev_hdd0/theme/";
	const std::string game = "/sandbox/dev_hdd0/game/NPUB00001/";
	struct expectation { std::string install, name; bool ok; std::string path; };
	const std::vector<expectation> cases = {
		{game, "USRDIR/EBOOT.BIN", true, game + "USRDIR/EBOOT.BIN"},
		{theme, "../../dev_hdd0/home/psn_avatar/PSNA_1.edat", true, "/sandbox/dev_hdd0/home/psn_avatar/PSNA_1.edat"},
		{theme, "..", true, "/sandbox/dev_hdd0"},
		{theme, "../..", false, ""},
		{theme, "./a", true, "/sandbox/dev_hdd0/theme/a"},
		{game, "../../../../Library/Preferences/app.plist", false, ""},
		{game, "/etc/hosts", false, ""},
		{theme, "../../dev_flash/vsh/module.sprx", false, ""},
		{theme, "../../../dev_hdd0/x", false, ""},
	};
	int passed = 0;
	for (const auto& c : cases)
	{
		const auto r = select(c.install, c.name);
		const bool good = r.ok == c.ok && (!c.ok || r.path == c.path);
		if (!good) std::fprintf(stderr, "PKG case '%s' + '%s': ok=%d path='%s'\n", c.install.c_str(), c.name.c_str(), r.ok, r.path.c_str());
		CHECK(good);
		passed += good;
		if (r.ok)
		{
			// Every accepted path stays inside the emulated hard drive.
			const std::string norm = std::filesystem::path(r.path).lexically_normal().string();
			CHECK(norm.starts_with("/sandbox/dev_hdd0"));
		}
	}
	const std::vector<std::pair<std::string, bool>> dirs = {{"NPUB00001", true}, {"../x", false}, {".", false}, {"", false}, {"a/../../b", false}};
	int dirs_passed = 0;
	for (const auto& [dir, ok] : dirs)
	{
		const bool good = pkg_after::install_dir_valid(dir) == ok;
		CHECK(good);
		dirs_passed += good;
	}
	// 543 control: the same traversal name is joined and leaves dev_hdd0.
	const std::string escaped = std::filesystem::path(pkg_before::join(game, "../../../../Library/Preferences/app.plist")).lexically_normal().string();
	const bool control_escapes = !escaped.starts_with("/sandbox/dev_hdd0");
	CHECK(control_escapes);
	return "{\"cases\":" + std::to_string(cases.size()) + ",\"passed\":" + std::to_string(passed) +
		",\"installDirCases\":" + std::to_string(dirs.size()) + ",\"installDirPassed\":" + std::to_string(dirs_passed) +
		",\"controlTraversalLeavesHdd0\":" + (control_escapes ? "true" : "false") + ",\"controlPath\":\"" + json_escape(escaped) + "\"}";
}

template <typename P>
static std::deque<P> programs()
{
	std::deque<P> list;
	std::mt19937 rng(545);
	for (u32 i = 0; i < 400; i++)
	{
		P p{};
		const u32 size = 4 + rng() % 60;
		p.lower_bound = 0x1000 * (rng() % 4);
		p.entry_point = p.lower_bound + 4 * (rng() % size);
		for (u32 j = 0; j < size; j++) p.data.push_back(rng() % 7);
		list.push_back(p);
		if (i % 3 == 0) list.push_back(p); // duplicate record
		if (i % 7 == 0) { P q = p; q.lower_bound += 0x100; q.entry_point += 0x100; list.push_back(q); } // equal program elsewhere
	}
	return list;
}

static std::string spu_report()
{
	auto after = programs<spu_after::spu_program>();
	auto before = programs<spu_before::spu_program>();
	const usz input = after.size();
	spu_after::order(after);
	spu_before::order(before);
	bool unique = true, ordered = true;
	for (usz i = 0; i < after.size(); i++)
	{
		for (usz j = i + 1; j < after.size(); j++) unique &= !(after[i] == after[j]);
		if (i) ordered &= after[i - 1].data.size() >= after[i].data.size();
	}
	CHECK(unique);
	CHECK(ordered);
	// Every input program is still compiled once.
	bool covered = true;
	for (const auto& p : programs<spu_after::spu_program>())
	{
		covered &= std::any_of(after.begin(), after.end(), [&](const auto& q) { return q == p; });
	}
	CHECK(covered);
	CHECK(before.size() == input);
	return "{\"input\":" + std::to_string(input) + ",\"compiled\":" + std::to_string(after.size()) +
		",\"controlCompiled\":" + std::to_string(before.size()) + ",\"unique\":" + (unique ? "true" : "false") +
		",\"biggestFirst\":" + (ordered ? "true" : "false") + ",\"everyProgramKept\":" + (covered ? "true" : "false") + "}";
}

static std::string savedata_report()
{
	struct expectation { u32 sdk; u32 max; usz after, before; };
	const std::vector<expectation> cases = {{0x260000, 4, 4, 10}, {0x26FFFF, 4, 4, 10}, {0x300000, 4, 10, 10}, {0x300000, 0, 0, 10}, {0x260000, 20, 10, 10}};
	int passed = 0;
	for (const auto& c : cases)
	{
		const bool good = savedata_after::listed(c.sdk, c.max, 10) == c.after && savedata_before::listed(c.sdk, c.max, 10) == c.before;
		CHECK(good);
		passed += good;
	}
	return "{\"cases\":" + std::to_string(cases.size()) + ",\"passed\":" + std::to_string(passed) + "}";
}

template <typename NS>
static bool savestate_case(usz flushed, usz content, usz readable)
{
	typename NS::serial ar;
	ar.data_offset = flushed;
	ar.data.assign(16, 0xAB);
	ar.pos = ar.data.size() + ar.data_offset;
	typename NS::file_stub file;
	for (usz i = 0; i < content; i++) file.content.push_back(static_cast<u8>(i));
	file.available = readable;
	NS::save(ar, file);
	// What a load reads back: [16 earlier bytes][stat_t, size patched][size file bytes][file position].
	typename NS::stat_t stats{};
	if (ar.data.size() < 16 + sizeof(stats)) return false;
	std::memcpy(&stats, ar.data.data() + 16, sizeof(stats));
	bool good = ar.data.size() == 16 + sizeof(stats) + readable + sizeof(u64) && stats.size == readable && ar.pos == ar.data.size() + ar.data_offset;
	for (usz i = 0; good && i < readable; i++) good &= ar.data[16 + sizeof(stats) + i] == static_cast<u8>(i);
	u64 position = 0;
	if (good) std::memcpy(&position, ar.data.data() + 16 + sizeof(stats) + readable, sizeof(position));
	return good && position == NS::file_stub::position;
}

static std::string savestate_report()
{
	const bool flushed_short = savestate_case<state_after::tag>(4096, 64, 40);
	const bool flushed_full = savestate_case<state_after::tag>(4096, 64, 64);
	const bool memory_short = savestate_case<state_after::tag>(0, 64, 40);
	const bool memory_full = savestate_case<state_after::tag>(0, 64, 64);
	// 543 control without any flushed data: the file position lands inside the content.
	const bool control_unflushed = savestate_case<state_before::tag>(0, 64, 64);
	CHECK(flushed_short && flushed_full && memory_short && memory_full);
	CHECK(!control_unflushed);
	return std::string("{\"flushedShortRead\":") + (flushed_short ? "true" : "false") + ",\"flushedFullRead\":" + (flushed_full ? "true" : "false") +
		",\"unflushedShortRead\":" + (memory_short ? "true" : "false") + ",\"unflushedFullRead\":" + (memory_full ? "true" : "false") +
		",\"controlUnflushedLayoutValid\":" + (control_unflushed ? "true" : "false") + "}";
}

struct late_logger
{
	~late_logger() { logs_after::format_once(); }
};

static std::string logs_report()
{
	logs_after::format_once();
	g_allocations = 0;
	g_count_allocations = true;
	for (int i = 0; i < 1000; i++) logs_after::format_once();
	const usz after_allocations = g_allocations.exchange(0);
	for (int i = 0; i < 1000; i++) logs_before::format_once();
	const usz before_allocations = g_allocations.exchange(0);
	g_count_allocations = false;
	CHECK(after_allocations == 0);
	CHECK(before_allocations >= 1000);
	// A thread_local destroyed after the buffer still logs safely (ASan would report reuse).
	std::thread([] { thread_local late_logger late; (void)&late; logs_after::format_once(); }).join();
	return "{\"calls\":1000,\"allocations\":" + std::to_string(after_allocations) + ",\"controlAllocations\":" + std::to_string(before_allocations) +
		",\"threadExitSafe\":true}";
}

static std::string sce_report()
{
	const bool after_rejects = !sce_after::accepts(0, 2, 2) && sce_after::accepts(1, 1, 2);
	const bool control_accepts = sce_before::accepts(0, 2, 2);
	CHECK(after_rejects);
	CHECK(control_accepts);
	return std::string("{\"ivIndexEqualKeyCountRejected\":") + (after_rejects ? "true" : "false") + ",\"controlAcceptsOutOfRange\":" + (control_accepts ? "true" : "false") + "}";
}

int main(int argc, char** argv)
{
	if (argc > 1 && std::string_view(argv[1]) == "savestate-control-flushed")
	{
		// 543 body with data already flushed: indexes ar.data by an absolute position.
		std::printf("%d\n", savestate_case<state_before::tag>(4096, 64, 40));
		return 0;
	}
	const std::string pkg = pkg_report(), spu = spu_report(), savedata = savedata_report(), savestate = savestate_report(),
		logs = logs_report(), sce = sce_report();
	std::printf("{\"pkg\":%s,\"spuWarmup\":%s,\"savedata\":%s,\"savestate\":%s,\"logs\":%s,\"sceKeyIndex\":%s,\"failures\":%d}\n",
		pkg.c_str(), spu.c_str(), savedata.c_str(), savestate.c_str(), logs.c_str(), sce.c_str(), failures);
	return failures ? 1 : 0;
}
