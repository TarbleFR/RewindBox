// Linux host test of rpcs3/ios/RPCS3IOSBootDiagnostics.h (NEOSTATION_BUILD487_DIAGNOSTICS_V1):
// counters, restart hand-off, exact line text of the four formatters, untouched
// exchange() semantics of JITPhaseProfile.h and the 1 KiB bound.
#include "rpcs3/ios/RPCS3IOSBootDiagnostics.h"

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

static int g_checks = 0;

static void expect(bool condition, const char* what, const std::string& actual = {})
{
	++g_checks;
	if (!condition)
	{
		std::printf("FAIL: %s\n  actual: %s\n", what, actual.c_str());
		std::exit(1);
	}
}

static void expect_eq(const std::string& actual, const std::string& wanted, const char* what)
{
	++g_checks;
	if (actual != wanted)
	{
		std::printf("FAIL: %s\n  actual: %s\n  wanted: %s\n", what, actual.c_str(), wanted.c_str());
		std::exit(1);
	}
}

int main()
{
	using namespace rpcs3::ios::boot_diagnostics;

	// --- encode_value
	expect_eq(encode_value({}), "-", "empty value prints as '-'");
	expect_eq(encode_value("a b%c\tx\n"), "a%20b%25c%09x%0A", "whitespace, '%' and control bytes are percent-encoded");
	expect_eq(encode_value("abcdef", 3), "abc", "limit cuts the input");
	expect_eq(encode_value("/Library/Application Support/x.yml"), "/Library/Application%20Support/x.yml", "path spaces encoded");
	expect_eq(encode_value("caf\xC3\xA9"), "caf\xC3\xA9", "UTF-8 bytes pass through");

	// --- NEOSTATION_RESTART formatter and hand-off
	expect_eq(format_restart_line(restart_reason::savestate_create, {}, "BLES01807", "home_menu"),
		"NEOSTATION_RESTART reason=savestate_create title=BLES01807 detail=home_menu", "savestate_create line");
	expect_eq(format_restart_line(restart_reason::game_setting, "gpu.resolution", "BLES01807", "1280x720"),
		"NEOSTATION_RESTART reason=game_setting:gpu.resolution title=BLES01807 detail=1280x720", "game_setting:<key> line");
	expect_eq(format_restart_line(restart_reason::sys_game, {}, {}, {}),
		"NEOSTATION_RESTART reason=sys_game title=- detail=-", "empty title/detail print as '-'");
	expect_eq(format_restart_line(restart_reason::savestate_load, {}, "BCES00510", "home_menu_reload_slot:2"),
		"NEOSTATION_RESTART reason=savestate_load title=BCES00510 detail=home_menu_reload_slot:2", "savestate_load line");
	expect_eq(format_restart_line(restart_reason::home_menu, {}, "X", "restart"),
		"NEOSTATION_RESTART reason=home_menu title=X detail=restart", "home_menu line");

	expect_eq(consume_restart_line("BLES00738"), "NEOSTATION_RESTART reason=other title=BLES00738 detail=unannounced",
		"unannounced restart is 'other'");
	announce_restart(restart_reason::savestate_create, {}, "neostation_slot:3");
	expect_eq(consume_restart_line("BLES00738"), "NEOSTATION_RESTART reason=savestate_create title=BLES00738 detail=neostation_slot:3",
		"announced reason consumed once");
	expect_eq(consume_restart_line("BLES00738"), "NEOSTATION_RESTART reason=other title=BLES00738 detail=unannounced",
		"second consume is unannounced again");
	announce_restart(restart_reason::home_menu, {}, "restart");
	cancel_restart_announcement();
	expect_eq(consume_restart_line("BLES00738"), "NEOSTATION_RESTART reason=other title=BLES00738 detail=unannounced",
		"cancelled announcement never labels a later restart");
	announce_restart(restart_reason::game_setting, std::string(200, 'k'), std::string(500, 'd'));
	{
		const std::string line = consume_restart_line("T");
		expect(line.size() < 1024, "oversized key/detail are bounded", line);
		expect(line.rfind("NEOSTATION_RESTART reason=game_setting:" + std::string(63, 'k') + " title=T detail=" + std::string(191, 'd'), 0) == 0,
			"key bounded to 63 bytes, detail to 191 bytes", line);
	}

	// --- CONFIG_LAYERS
	{
		config_layers layers{};
		layers.title = "BLES01807";
		layers.name = "database_config";
		layers.database = true;
		layers.legacy_custom = false;
		layers.legacy_path = "/ignored/when/not/legacy.yml";
		layers.sparse_overrides = true;
		layers.shader_mode = "Legacy Recompiler (single-threaded)";
		layers.frame_limit = "Auto";
		layers.wcb = "false";
		layers.wdb = "false";
		layers.rsx_res = "100";
		layers.spu_block = "Safe";
		layers.spu_decoder = "Recompiler (LLVM)";
		layers.ppu_decoder = "Recompiler (LLVM)";
		layers.async_tex = "false";
		layers.max_spurs = "6";
		layers.getllar_pct = "100";
		expect_eq(format_config_layers_line(layers),
			"CONFIG_LAYERS title=BLES01807 name=database_config database=1 legacy_custom=0 legacy_path=- sparse_overrides=1 "
			"shader_mode=Legacy%20Recompiler%20(single-threaded) frame_limit=Auto wcb=false wdb=false rsx_res=100 spu_block=Safe "
			"spu_decoder=Recompiler%20(LLVM) ppu_decoder=Recompiler%20(LLVM) async_tex=false max_spurs=6 getllar_pct=100",
			"CONFIG_LAYERS database boot");

		layers.name = "/Documents/RPCS3/config/custom_configs/config_BLES01807.yml";
		layers.database = false;
		layers.legacy_custom = true;
		layers.legacy_path = "/Documents/RPCS3/config/custom_configs/config_BLES01807.yml";
		layers.sparse_overrides = false;
		const std::string line = format_config_layers_line(layers);
		expect(line.find(" database=0 legacy_custom=1 legacy_path=/Documents/RPCS3/config/custom_configs/config_BLES01807.yml sparse_overrides=0 ") != std::string::npos,
			"legacy custom config is visible with its path", line);
		expect(line.rfind("CONFIG_LAYERS title=BLES01807 name=/Documents/RPCS3/config/custom_configs/config_BLES01807.yml ", 0) == 0, "name is g_cfg.name", line);

		// Realistic worst case on iOS: an absolute container path with a space,
		// the longest shader mode spelling.
		const std::string ios_path = "/private/var/mobile/Containers/Data/Application/0A1B2C3D-4E5F-6A7B-8C9D-0E1F2A3B4C5D"
			"/Library/Application Support/RPCS3/config/custom_configs/config_BLES01807.yml";
		layers.name = ios_path;
		layers.legacy_path = ios_path;
		layers.sparse_overrides = true;
		layers.shader_mode = "Async Recompiler with Shader Interpreter";
		layers.spu_block = "Mega";
		const std::string long_line = format_config_layers_line(layers);
		expect(long_line.size() + 96 < 1024 && long_line.size() <= line_budget, "CONFIG_LAYERS with an iOS container path fits the milestone cut", long_line);
	}

	// --- Counters and JITPROF_BOOT / SAVESTATE_BOOT
	{
		const snapshot before = take();
		g_counters.boots.fetch_add(1);
		g_counters.fragments.fetch_add(7);
		g_counters.modules_total.fetch_add(5);
		g_counters.modules_compiled.fetch_add(2);
		g_counters.modules_cached.fetch_add(3);
		g_counters.modules_existing.fetch_add(0);
		g_counters.note_cache_lookup(true);
		g_counters.note_cache_lookup(true);
		g_counters.note_cache_lookup(true);
		g_counters.note_cache_lookup(false);
		g_counters.note_cache_lookup(false);
		g_counters.objects_loaded.fetch_add(5);
		g_counters.link_ticks.fetch_add(12'500);
		const snapshot boot = delta(before, take());
		expect(boot.fragments == 7 && boot.modules_total == 5 && boot.modules_compiled == 2 && boot.modules_cached == 3 &&
			boot.modules_existing == 0 && boot.cache_hits == 3 && boot.cache_misses == 2 && boot.objects_loaded == 5 && boot.link_ticks == 12'500,
			"delta reports the boot-scoped counters");
		expect(delta(take(), before).fragments == 0, "delta saturates at zero");

		// Phase totals: the reporter's exchange() keeps its Build 444 semantics while totals persist.
		jit_phase::g_counters.begin_window();
		const jit_phase::snapshot phases_begin = jit_phase::g_counters.totals();
		jit_phase::g_counters.add(jit_phase::ppu_codegen, 4'000, 1'000);
		jit_phase::g_counters.add(jit_phase::ppu_codegen, 6'000, 2'000);
		jit_phase::g_counters.add(jit_phase::ppu_cache_read, 500, 4'096);
		jit_phase::g_counters.note_headroom(900 * 0x100000ull);
		jit_phase::g_counters.note_headroom(300 * 0x100000ull);
		const jit_phase::snapshot window = jit_phase::g_counters.exchange(); // the 5 s reporter fires mid-boot
		expect(window.events[jit_phase::ppu_codegen] == 2 && window.ticks[jit_phase::ppu_codegen] == 10'000 &&
			window.max_ticks[jit_phase::ppu_codegen] == 6'000 && window.bytes[jit_phase::ppu_codegen] == 3'000 &&
			window.headroom_samples == 2 && window.headroom_min_bytes == 300 * 0x100000ull, "exchange() semantics unchanged");
		const jit_phase::snapshot drained = jit_phase::g_counters.exchange();
		expect(drained.events[jit_phase::ppu_codegen] == 0 && drained.headroom_samples == 0 && drained.headroom_min_bytes == 0,
			"exchange() still resets the window");
		jit_phase::g_counters.add(jit_phase::ppu_codegen, 1'000, 500); // after the reporter's exchange, still inside the boot
		const jit_phase::snapshot phases = jit_phase::registry::window_delta(phases_begin, jit_phase::g_counters.totals());
		expect(phases.events[jit_phase::ppu_codegen] == 3 && phases.ticks[jit_phase::ppu_codegen] == 11'000 &&
			phases.max_ticks[jit_phase::ppu_codegen] == 6'000 && phases.bytes[jit_phase::ppu_codegen] == 3'500 &&
			phases.events[jit_phase::ppu_cache_read] == 1 && phases.bytes[jit_phase::ppu_cache_read] == 4'096 &&
			phases.headroom_samples == 2 && phases.headroom_min_bytes == 300 * 0x100000ull,
			"boot delta spans the reporter's exchange");

		jit_boot_summary summary{};
		summary.session = 1;
		summary.savestate = true;
		summary.modules = boot;
		summary.wall_ticks = 2'500'000;
		summary.tsc_frequency = 1'000'000; // 1000 ticks per ms
		summary.ppu_pipeline = 0;
		summary.ppu_ir_passes = 0;
		summary.spu_pipeline = 0;
		const std::string jitprof = format_jitprof_boot_line(summary, phases);
		expect_eq(jitprof,
			"JITPROF_BOOT session=1 boot_kind=savestate modules_total=5 modules_compiled=2 modules_cached=3 modules_existing=0 "
			"ppu_cache_hits=3 ppu_cache_misses=2 wall_ms=2500.000 "
			"ppu_translate=0:0.000:0.000:0 ppu_opt=0:0.000:0.000:0 ppu_verify=0:0.000:0.000:0 ppu_codegen=3:11.000:6.000:3500 "
			"ppu_cache_write=0:0.000:0.000:0 ppu_cache_read=1:0.500:0.500:4096 ppu_object_load=0:0.000:0.000:0 "
			"ppu_finalize=0:0.000:0.000:0 ppu_symbols=0:0.000:0.000:0 "
			"headroom_samples=2 headroom_min_mib=300.000 ppu_pipeline=0 ppu_ir_passes=0 spu_pipeline=0",
			"JITPROF_BOOT first line exact text (summary, PPU phases, tail)");
		expect_eq(format_jitprof_boot_spu_line(summary, phases),
			"JITPROF_BOOT session=1 boot_kind=savestate part=spu spu_build=0:0.000:0.000:0 spu_passes=0:0.000:0.000:0 "
			"spu_codegen=0:0.000:0.000:0 spu_cache_read=0:0.000:0.000:0 spu_object_load=0:0.000:0.000:0 spu_cache_write=0:0.000:0.000:0",
			"JITPROF_BOOT second line exact text (SPU phases)");
		expect(jitprof.size() <= line_budget, "JITPROF_BOOT first line within the line budget", jitprof);

		// Every one of the fifteen JITPROF phases appears exactly once over the two lines.
		{
			const std::string both = jitprof + "\n" + format_jitprof_boot_spu_line(summary, phases);
			for (unsigned phase = 0; phase < jit_phase::count; ++phase)
			{
				const std::string field = std::string(" ") + jit_phase::names[phase] + "=";
				const std::size_t first = both.find(field);
				expect(first != std::string::npos && both.find(field, first + 1) == std::string::npos,
					"each phase printed exactly once over the two JITPROF_BOOT lines", jit_phase::names[phase]);
			}
		}

		// 1 KiB bound with large realistic values (a long cold boot with LLVM
		// precompilation, every phase active): the host cuts a milestone at 1024
		// bytes including the listener's "<thread>: " prefix (<= 96 bytes here).
		{
			jit_boot_summary heavy{};
			heavy.session = 9'999;
			heavy.savestate = true;
			heavy.modules.modules_total = 999'999;
			heavy.modules.modules_compiled = 999'999;
			heavy.modules.modules_cached = 999'999;
			heavy.modules.modules_existing = 999'999;
			heavy.modules.cache_hits = 999'999;
			heavy.modules.cache_misses = 999'999;
			heavy.tsc_frequency = 24'000'000;                       // iPhone counter
			heavy.wall_ticks = 9'999'999ull * 24'000;               // 9 999 999 ms (2.8 h)
			heavy.ppu_pipeline = 2;
			heavy.ppu_ir_passes = 1;
			heavy.spu_pipeline = 1;
			jit_phase::snapshot large{};
			for (unsigned phase = 0; phase < jit_phase::count; ++phase)
			{
				large.events[phase] = 9'999'999;                    // seven digits per phase
				large.ticks[phase] = 9'999'999ull * 24'000;         // 9 999 999 ms of CPU across workers
				large.max_ticks[phase] = 999'999ull * 24'000;       // 999 999 ms for one event
				large.bytes[phase] = 99'999'999'999ull;             // 100 GB
			}
			large.headroom_samples = 9'999'999;
			large.headroom_min_bytes = 99'999ull * 0x100000;
			const std::string first = format_jitprof_boot_line(heavy, large);
			const std::string second = format_jitprof_boot_spu_line(heavy, large);
			expect(first.size() + 96 < 1024 && first.size() <= line_budget, "heavy JITPROF_BOOT first line fits the milestone cut", first);
			expect(second.size() + 96 < 1024 && second.size() <= line_budget, "heavy JITPROF_BOOT second line fits the milestone cut", second);
			expect(first.find(" spu_pipeline=1") != std::string::npos && first.compare(first.size() - 15, 15, " spu_pipeline=1") == 0,
				"the pipeline tail ends the first line", first);
			expect(second.compare(second.size() - std::strlen(" spu_cache_write=9999999:9999999.000:999999.000:99999999999"),
				std::string::npos, " spu_cache_write=9999999:9999999.000:999999.000:99999999999") == 0,
				"the last SPU phase ends the second line", second);
		}

		summary.savestate = false;
		summary.tsc_frequency = 0;
		expect(format_jitprof_boot_line(summary, phases).find(" boot_kind=fresh ") != std::string::npos, "fresh boot kind");
		expect(format_jitprof_boot_line(summary, phases).find(" wall_ms=0.000 ") != std::string::npos, "unknown TSC frequency prints 0 ms");
		expect(format_jitprof_boot_spu_line(summary, phases).rfind("JITPROF_BOOT session=1 boot_kind=fresh part=spu ", 0) == 0,
			"second line carries the session and boot kind of the first");

		// begin_window() resets only the window maxima / headroom minimum, never the totals.
		const jit_phase::snapshot totals_before = jit_phase::g_counters.totals();
		jit_phase::g_counters.begin_window();
		const jit_phase::snapshot totals_after = jit_phase::g_counters.totals();
		expect(totals_after.events[jit_phase::ppu_codegen] == totals_before.events[jit_phase::ppu_codegen] &&
			totals_after.ticks[jit_phase::ppu_codegen] == totals_before.ticks[jit_phase::ppu_codegen] &&
			totals_after.max_ticks[jit_phase::ppu_codegen] == 0 &&
			jit_phase::registry::window_delta(totals_after, totals_after).headroom_min_bytes == 0,
			"begin_window keeps totals and clears window maxima");

		expect_eq(format_savestate_analysis_line("BLES01807", 0, 0, 1'234, 7),
			"SAVESTATE_BOOT title=BLES01807 applied_patches=0 seg0_code_end=0x0 funcs=1234 fragments=7", "SAVESTATE_BOOT analysis line (zeroed seg0)");
		expect_eq(format_savestate_analysis_line("BCES00510", 3, 0x52c000, 9'876, 12),
			"SAVESTATE_BOOT title=BCES00510 applied_patches=3 seg0_code_end=0x52c000 funcs=9876 fragments=12", "SAVESTATE_BOOT analysis line");
		expect_eq(format_savestate_link_line("BLES01807", boot, 1'000'000),
			"SAVESTATE_BOOT title=BLES01807 ppu_cache_hits=3 ppu_cache_misses=2 objects_loaded=5 link_ms=12.500 fragments_total=5",
			"SAVESTATE_BOOT link line");
	}

	std::printf("PASS Build 487 boot diagnostics helpers: %d checks\n", g_checks);
	return 0;
}
