// CELL551 scenarios. test/rpcs3_cell551_test.py prepends the production
// headers (RPCS3IOSConfigInheritance.h, IOSSpuWaitProfile.h,
// IOSRsxSyncProfile.h), yaml_load copied verbatim from rpcs3/util/yaml.cpp and
// the God of War III database document rebuilt from the Dart profile.

#include <cstdio>
#include <map>
#include <string>
#include <thread>
#include <vector>

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

// cfg::node::from_string applies every key the document holds over the
// current values; a deep merge of maps models that.
static void merge(YAML::Node& base, const YAML::Node& overlay)
{
	for (const auto& entry : overlay)
	{
		const std::string key = entry.first.Scalar();
		if (entry.second.IsMap() && base[key].IsMap())
		{
			YAML::Node child = base[key];
			merge(child, entry.second);
		}
		else
		{
			base[key] = YAML::Clone(entry.second);
		}
	}
}

static std::string value_at(const YAML::Node& root, std::initializer_list<const char*> path)
{
	YAML::Node node = YAML::Clone(root);
	for (const char* key : path)
	{
		if (!node.IsMap() || !node[key].IsDefined()) return "<missing>";
		node = node[key];
	}
	return node.IsScalar() ? node.Scalar() : YAML::Dump(node);
}

// Boot order on iOS: global, then the full file, then the database settings
// the file left at the global value.
static YAML::Node boot(const std::string& global, const std::string& file, const rpcs3::ios::config_inheritance::result& r)
{
	YAML::Node effective = YAML::Load(global);
	merge(effective, YAML::Load(file));
	if (!r.yaml.empty()) merge(effective, YAML::Load(r.yaml));
	return effective;
}

static std::string replace(std::string text, const std::string& from, const std::string& to)
{
	const auto at = text.find(from);
	if (at != std::string::npos) text.replace(at, from.size(), to);
	return text;
}

struct counts { unsigned inherited, kept; };

int main()
{
	using namespace rpcs3::ios;
	std::string json = "{";

	// 1. The observed God of War III boots: a full snapshot equal to the global
	// config for every key (CONFIG_LAYERS legacy_custom=1 database=0, builds 412-547).
	{
		const auto r = config_inheritance::inherit_database(kGow3Database, kLegacySnapshot, kGlobal);
		CHECK(r.ok && r.kept == 0 && r.inherited == kGow3DatabaseLeaves);
		const YAML::Node eff = boot(kGlobal, kLegacySnapshot, r);
		CHECK(value_at(eff, {"Core", "Accurate SPU Reservations"}) == "false");
		CHECK(value_at(eff, {"Core", "SPU Block Size"}) == "Mega");
		CHECK(value_at(eff, {"Video", "Resolution Scale"}) == "75");
		CHECK(value_at(eff, {"Video", "Frame limit"}) == "30");
		CHECK(value_at(eff, {"Video", "Multithreaded RSX"}) == "true");
		CHECK(value_at(eff, {"Video", "Write Color Buffers"}) == "true");
		// Build 552: the profile overrides the GameDB's asynchronous texture
		// streaming (never run on the iPhone) and keeps synchronous submits.
		CHECK(value_at(eff, {"Video", "Vulkan", "Asynchronous Texture Streaming"}) == "false");
		CHECK(value_at(eff, {"iOS Experimental", "MoltenVK Asynchronous Submits"}) == "Disabled");
		CHECK(value_at(eff, {"iOS Experimental", "God of War III MLAA Bypass"}) == "Enabled");
		// The profile forces no shader mode: the snapshot's Legacy mode stays.
		CHECK(value_at(eff, {"Video", "Shader Mode"}) == "Legacy Recompiler (single-threaded)");
		// Untouched settings keep the file's (= global) values.
		CHECK(value_at(eff, {"Core", "Max SPURS Threads"}) == "6");
		json += "\"observedSnapshot\": {\"inherited\": " + std::to_string(r.inherited) + ", \"kept\": " + std::to_string(r.kept) + "}";
	}

	// 2. A setting the file changed relative to the global config stays.
	{
		const std::string file = replace(kLegacySnapshot, "  Resolution Scale: 100\n", "  Resolution Scale: 150\n");
		const auto r = config_inheritance::inherit_database(kGow3Database, file, kGlobal);
		CHECK(r.ok && r.kept == 1 && r.inherited == kGow3DatabaseLeaves - 1);
		const YAML::Node eff = boot(kGlobal, file, r);
		CHECK(value_at(eff, {"Video", "Resolution Scale"}) == "150");
		CHECK(value_at(eff, {"Core", "Accurate SPU Reservations"}) == "false");
		json += ", \"userChange\": {\"inherited\": " + std::to_string(r.inherited) + ", \"kept\": " + std::to_string(r.kept) + "}";
	}

	// 3. A global value changed after the snapshot was taken: the file's value
	// differs from the new global, so it is kept (conservative).
	{
		const std::string global = replace(kGlobal, "  SPU Block Size: Safe\n", "  SPU Block Size: Giga\n");
		const auto r = config_inheritance::inherit_database(kGow3Database, kLegacySnapshot, global);
		CHECK(r.ok && r.kept == 1);
		CHECK(value_at(boot(global, kLegacySnapshot, r), {"Core", "SPU Block Size"}) == "Safe");
	}

	// 4. An older snapshot without the iOS Experimental section inherits it.
	{
		const std::string file = kLegacySnapshot.substr(0, kLegacySnapshot.find("iOS Experimental:"));
		const auto r = config_inheritance::inherit_database(kGow3Database, file, kGlobal);
		CHECK(r.ok && r.kept == 0 && r.inherited == kGow3DatabaseLeaves);
		CHECK(value_at(boot(kGlobal, file, r), {"iOS Experimental", "GETLLAR Mobile Backoff"}) == "Enabled");
	}

	// 5. Sequence leaves compare as emitted text.
	{
		const std::string db = "Core:\n  Libraries Control:\n    - libvdec.sprx:lle\n";
		const std::string global = "Core:\n  Libraries Control:\n    []\n";
		auto r = config_inheritance::inherit_database(db, global, global);
		CHECK(r.ok && r.inherited == 1 && r.kept == 0);
		r = config_inheritance::inherit_database(db, "Core:\n  Libraries Control:\n    - libsail.sprx:hle\n", global);
		CHECK(r.ok && r.inherited == 0 && r.kept == 1 && r.yaml.empty());
	}

	// 6. Unparsable or non-map inputs apply nothing.
	{
		CHECK(!config_inheritance::inherit_database("Core: [unterminated", kLegacySnapshot, kGlobal).ok);
		CHECK(!config_inheritance::inherit_database(kGow3Database, "Core: {", kGlobal).ok);
		CHECK(!config_inheritance::inherit_database("just a scalar", kLegacySnapshot, kGlobal).ok);
		const auto r = config_inheritance::inherit_database("", kLegacySnapshot, kGlobal);
		CHECK(!r.ok && r.yaml.empty());
	}

	// 7. SPU wait counters: owner-only slots, released at thread exit, exact
	// totals with more threads than slots (overflow slot uses fetch_add).
	{
		const auto before = spu_wait::totals();
		constexpr int rounds = 3, threads = 40, adds = 20000;
		for (int round = 0; round < rounds; round++)
		{
			std::vector<std::thread> pool;
			for (int t = 0; t < threads; t++)
			{
				pool.emplace_back([]
				{
					for (int i = 0; i < adds; i++)
					{
						spu_wait::add(spu_wait::putllc_ok);
						spu_wait::add(spu_wait::event_wait_ticks, 3);
					}
				});
			}
			for (auto& t : pool) t.join();
		}
		const auto after = spu_wait::totals();
		CHECK(after[spu_wait::putllc_ok] - before[spu_wait::putllc_ok] == u64{rounds} * threads * adds);
		CHECK(after[spu_wait::event_wait_ticks] - before[spu_wait::event_wait_ticks] == u64{rounds} * threads * adds * 3);
		unsigned owned = 0;
		for (std::size_t i = 0; i < spu_wait::slot_count; i++) owned += spu_wait::g_slots[i].owned.load();
		CHECK(owned == 0);
		json += ", \"spuWait\": {\"threads\": " + std::to_string(rounds * threads) + ", \"slots\": " + std::to_string(spu_wait::slot_count) + "}";
	}

	// 8. Poll episodes: gaps within poll_gap count as polling time, longer gaps
	// start a new episode.
	{
		std::thread([]
		{
			const auto before = spu_wait::totals();
			spu_wait::poll(1000, 100);
			spu_wait::poll(1040, 100);
			spu_wait::poll(1100, 100);
			spu_wait::poll(5000, 100);
			spu_wait::poll(5030, 100);
			const auto after = spu_wait::totals();
			CHECK(after[spu_wait::getllar_polls] - before[spu_wait::getllar_polls] == 5);
			CHECK(after[spu_wait::getllar_poll_ticks] - before[spu_wait::getllar_poll_ticks] == 40 + 60 + 30);
		}).join();
	}

	// 9. RSX wait attribution: the outermost reason wins unless overridden.
	{
		using namespace rsx_sync;
		for (auto& cost : fence_wait_ticks) static_cast<void>(cost.take());
		record_fence_wait(5);
		{
			SiteScope frame(frame_cleanup);
			record_fence_wait(7);
			{
				SiteScope reuse(cb_reuse);
				record_fence_wait(11);
			}
		}
		{
			SiteScope hard(hard_sync, true);
			SiteScope reuse(cb_reuse);
			SiteScope frame(frame_cleanup);
			record_fence_wait(13);
			SiteScope tex(texture, true);
			record_fence_wait(17);
		}
		CHECK(t_site == other);
		const auto o = fence_wait_ticks[other].take(), f = fence_wait_ticks[frame_cleanup].take(),
			h = fence_wait_ticks[hard_sync].take(), t = fence_wait_ticks[texture].take(), c = fence_wait_ticks[cb_reuse].take();
		CHECK(o.count == 1 && o.total == 5);
		CHECK(f.count == 2 && f.total == 18 && f.maximum == 11);
		CHECK(h.count == 1 && h.total == 13);
		CHECK(t.count == 1 && t.total == 17);
		CHECK(c.count == 0);
		CHECK(std::string(site_name(frame_cleanup)) == "frame_cleanup" && std::string(site_name(site_count)) == "other");
	}

	// 10. RSX frame window: sampled period and drain semantics.
	{
		auto& w = rsx_sync::rsx_frames;
		CHECK(rsx_sync::rsx_frame_sample_period == 8);
		w.frames.fetch_add(3);
		w.setup_us.fetch_add(1200);
		CHECK(w.frames.exchange(0) == 3 && w.setup_us.exchange(0) == 1200 && w.frames.load() == 0);
		rsx_sync::frame_latency_ticks.record(90);
		const auto latency = rsx_sync::frame_latency_ticks.take();
		CHECK(latency.count == 1 && latency.total == 90);
	}

	json += ", \"failures\": " + std::to_string(failures) + "}";
	std::printf("%s\n", json.c_str());
	return failures ? 1 : 0;
}
