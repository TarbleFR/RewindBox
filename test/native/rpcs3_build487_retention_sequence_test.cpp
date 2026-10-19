// Linux simulation of the Build 487 boot-time sequence of spu_runtime::spu_runtime()
// (rpcs3/Emu/Cell/SPUCommonRecompiler.cpp, L5): candidate collection, retention
// plan, current-directory eviction (unchanged Build 481 call), shared eviction of
// the other retained directories, and removal of a directory left empty.
// Uses the two pure headers exactly as the Core does; the file system is a map.
#include "rpcs3/Emu/Cell/SPUObjectCachePolicy.h"
#include "rpcs3/ios/RPCS3IOSLeverHelpers.h"

#include <cstdio>
#include <cstdlib>
#include <map>
#include <string>
#include <vector>

namespace levers = rpcs3::ios::levers;
namespace object_cache = rpcs3::spu::object_cache;

static int g_checks = 0;
#define CHECK(expr) do { ++g_checks; if (!(expr)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #expr); std::exit(1); } } while (0)

struct fake_file { std::uint64_t size; std::int64_t mtime; };
struct fake_dir { std::int64_t mtime; std::map<std::string, fake_file> files; std::string marker; };
using fake_fs = std::map<std::string, fake_dir>;

// File-system clock of the simulated boots. The Core sets the current
// directory's time to the marker's own after rewriting it (fs::utime), so a
// key booted without writing any object still counts as recently used.
static std::int64_t g_now = 0;

struct outcome
{
	std::vector<std::string> removed_directories;
	std::vector<std::string> removed_files; // "<dir>/<file>"
	std::size_t current_kept_files = 0;
	std::size_t shared_kept_files = 0;
	unsigned retained_directories = 0;
};

// Mirrors the production sequence with the same helper calls and the same
// bounds arguments (small bounds are passed to exercise eviction).
static outcome boot(fake_fs& fs, const std::string& current, const std::string& marker, unsigned retained_keys,
	std::size_t max_files = object_cache::max_files, std::uint64_t max_bytes = object_cache::max_bytes)
{
	outcome result;
	std::vector<levers::cache_directory_candidate> candidates;
	for (const auto& [name, dir] : fs)
	{
		if (name.starts_with("spuobj-") && name != current)
		{
			candidates.push_back({name, dir.mtime, levers::build_marker_matches(dir.marker, marker)});
		}
	}
	const levers::retention_plan retention = levers::plan_directory_retention(std::move(candidates), current, retained_keys, object_cache::format_version);
	for (const std::string& name : retention.remove)
	{
		fs.erase(name);
		result.removed_directories.push_back(name);
	}
	fake_dir& current_dir = fs[current]; // create_path
	current_dir.marker = marker + "\n";   // marker rewritten at every boot
	current_dir.mtime = g_now;            // directory time set to the marker's
	std::vector<object_cache::entry> entries;
	for (const auto& [name, file] : current_dir.files)
	{
		if (name != levers::build_marker_name)
		{
			entries.push_back({name, file.size, file.mtime});
		}
	}
	const object_cache::eviction_plan plan = object_cache::plan_eviction(std::move(entries), max_files, max_bytes);
	for (const std::string& name : plan.remove)
	{
		current_dir.files.erase(name);
		result.removed_files.push_back(current + "/" + name);
	}
	result.current_kept_files = plan.kept_files;
	if (!retention.retain.empty())
	{
		std::vector<object_cache::entry> shared_entries;
		std::vector<std::string> shared_names;
		for (const std::string& directory : retention.retain)
		{
			for (const auto& [name, file] : fs[directory].files)
			{
				if (name != levers::build_marker_name)
				{
					shared_entries.push_back({directory + "/" + name, file.size, file.mtime});
					shared_names.push_back(shared_entries.back().name);
				}
			}
		}
		const auto [files_left, bytes_left] = levers::remaining_budget(plan.kept_files, plan.kept_bytes, max_files, max_bytes);
		const object_cache::eviction_plan shared = object_cache::plan_eviction(std::move(shared_entries), files_left, bytes_left);
		for (const std::string& name : shared.remove)
		{
			const auto slash = name.find('/');
			fs[name.substr(0, slash)].files.erase(name.substr(slash + 1));
			result.removed_files.push_back(name);
		}
		result.shared_kept_files = shared.kept_files;
		for (const std::string& directory : retention.retain)
		{
			if (levers::entries_left_in(directory, shared_names, shared.remove))
			{
				result.retained_directories++;
				continue;
			}
			fs.erase(directory);
			result.removed_directories.push_back(directory);
		}
	}
	return result;
}

static bool has(const std::vector<std::string>& list, const std::string& value)
{
	return std::find(list.begin(), list.end(), value) != list.end();
}

int main()
{
	// Real commit/revision of every NeoStation Core build ("1-22f11527"); the
	// other Core build differs only by its SPU codegen identity.
	const std::string marker = levers::build_marker_content("1", "22f11527", "Cg487AbCdEfG", "apple-a18", 7, 24'000'000);
	const std::string other_marker = levers::build_marker_content("1", "22f11527", "Cg488HiJkLmN", "apple-a18", 7, 24'000'000);

	// --- Scenario 1: first boot after Build 487 over a Build 483 cache. The
	// 483 directory of another key has no marker: removed, as before.
	{
		fake_fs fs;
		fs["spuobj-v6-build483key"] = {100, {{"a.gz", {10, 50}}}, ""};
		auto r = boot(fs, "spuobj-v6-new", marker, 2);
		CHECK(has(r.removed_directories, "spuobj-v6-build483key"));
		CHECK(fs.count("spuobj-v6-new") == 1 && fs["spuobj-v6-new"].marker == marker + "\n");
		CHECK(r.retained_directories == 0);
	}

	// --- Scenario 2: A/B of a key setting with retained_keys = 2 (default).
	// Boot with key A, then key B, then A again: A's objects survive the flip.
	{
		fake_fs fs;
		g_now = 100;
		auto r = boot(fs, "spuobj-v6-A", marker, 2);
		fs["spuobj-v6-A"].files["a1.gz"] = {10, 110};
		fs["spuobj-v6-A"].mtime = 110; // object written during the session
		g_now = 200;
		r = boot(fs, "spuobj-v6-B", marker, 2);
		CHECK(r.removed_directories.empty() && r.retained_directories == 1);
		CHECK(fs.count("spuobj-v6-A") == 1 && fs["spuobj-v6-A"].files.count("a1.gz") == 1);
		fs["spuobj-v6-B"].files["b1.gz"] = {10, 210};
		fs["spuobj-v6-B"].mtime = 210;
		// Third boot, key A again: a cache-hit session writes no object, yet the
		// marker refresh makes A the most recently used directory.
		g_now = 300;
		r = boot(fs, "spuobj-v6-A", marker, 2);
		CHECK(r.removed_directories.empty() && r.retained_directories == 1);
		CHECK(fs["spuobj-v6-A"].files.count("a1.gz") == 1 && fs["spuobj-v6-B"].files.count("b1.gz") == 1);
		CHECK(fs["spuobj-v6-A"].mtime == 300);
		// A third key C with retained_keys = 2: the least recently used of A/B
		// goes (B, last used at 210); A, booted last, stays.
		g_now = 400;
		r = boot(fs, "spuobj-v6-C", marker, 2);
		CHECK(r.removed_directories.size() == 1 && r.removed_directories[0] == "spuobj-v6-B");
		CHECK(fs.count("spuobj-v6-A") == 1 && fs["spuobj-v6-A"].files.count("a1.gz") == 1 && r.retained_directories == 1);
	}

	// --- Scenario 3: retained_keys = 1 reproduces the Build 483 policy
	// (every other key removed, marker or not).
	{
		fake_fs fs;
		fs["spuobj-v6-A"] = {100, {{"a.gz", {10, 50}}}, marker + "\n"};
		fs["spuobj-v6-B"] = {200, {{"b.gz", {10, 50}}}, ""};
		auto r = boot(fs, "spuobj-v6-C", marker, 1);
		CHECK(has(r.removed_directories, "spuobj-v6-A") && has(r.removed_directories, "spuobj-v6-B"));
		CHECK(fs.size() == 1 && fs.count("spuobj-v6-C") == 1);
	}

	// --- Scenario 4: another Core build (same commit/revision, other SPU
	// codegen identity) / format version: still removed even with
	// retained_keys = 4.
	{
		fake_fs fs;
		fs["spuobj-v6-otherbuild"] = {900, {{"x.gz", {10, 50}}}, other_marker + "\n"};
		fs["spuobj-v5-oldformat"] = {900, {{"x.gz", {10, 50}}}, marker + "\n"};
		fs["spuobj-v6-same"] = {800, {{"x.gz", {10, 50}}}, marker + "\n"};
		auto r = boot(fs, "spuobj-v6-current", marker, 4);
		CHECK(has(r.removed_directories, "spuobj-v6-otherbuild") && has(r.removed_directories, "spuobj-v5-oldformat"));
		CHECK(!has(r.removed_directories, "spuobj-v6-same") && r.retained_directories == 1);
	}

	// --- Scenario 5: shared bounds. Current directory within bounds keeps
	// everything (unchanged 481 call); the other retained directory gets the
	// remaining budget, oldest objects first, and never the marker.
	{
		fake_fs fs;
		fs["spuobj-v6-other"] = {100, {{"old.gz", {10, 1}}, {"mid.gz", {10, 2}}, {"new.gz", {10, 3}}}, marker + "\n"};
		fs["spuobj-v6-cur"] = {200, {{"c1.gz", {10, 5}}, {"c2.gz", {10, 6}}}, marker + "\n"};
		// Bounds: 4 files total. Current keeps 2 -> 2 left; the other has 3 -> evict to 90 % of 2 = 1 kept.
		auto r = boot(fs, "spuobj-v6-cur", marker, 2, 4, 1 << 20);
		CHECK(r.current_kept_files == 2);
		CHECK(has(r.removed_files, "spuobj-v6-other/old.gz") && has(r.removed_files, "spuobj-v6-other/mid.gz"));
		CHECK(!has(r.removed_files, "spuobj-v6-other/new.gz"));
		CHECK(fs["spuobj-v6-other"].marker == marker + "\n" && r.retained_directories == 1);
		CHECK(r.shared_kept_files == 1);
	}

	// --- Scenario 6: the current directory alone fills the bounds: the other
	// retained directory is emptied and removed, so it frees its slot.
	{
		fake_fs fs;
		fs["spuobj-v6-other"] = {100, {{"o.gz", {10, 1}}}, marker + "\n"};
		fs["spuobj-v6-cur"] = {200, {{"c1.gz", {10, 5}}, {"c2.gz", {10, 6}}}, marker + "\n"};
		auto r = boot(fs, "spuobj-v6-cur", marker, 2, 2, 1 << 20);
		CHECK(r.current_kept_files == 2);
		CHECK(has(r.removed_files, "spuobj-v6-other/o.gz"));
		CHECK(has(r.removed_directories, "spuobj-v6-other") && fs.count("spuobj-v6-other") == 0);
		CHECK(r.retained_directories == 0);
	}

	// --- Scenario 7: the current directory over its own bounds evicts its
	// oldest objects exactly as Build 481 did (same plan_eviction call).
	{
		fake_fs fs;
		fs["spuobj-v6-cur"] = {200, {{"c1.gz", {10, 1}}, {"c2.gz", {10, 2}}, {"c3.gz", {10, 3}}}, marker + "\n"};
		auto r = boot(fs, "spuobj-v6-cur", marker, 2, 2, 1 << 20);
		CHECK(has(r.removed_files, "spuobj-v6-cur/c1.gz") && has(r.removed_files, "spuobj-v6-cur/c2.gz"));
		CHECK(r.current_kept_files == 1);
	}

	std::printf("PASS: %d checks of the Build 487 retention sequence\n", g_checks);
	return 0;
}
