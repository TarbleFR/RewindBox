// REWINDBOX_GRAPHICS_TESTS_612: CONFIG_LAYERS part=rsx formatter, executed on the
// host with the real header of the candidate Core (rpcs3/ios/RPCS3IOSBootDiagnostics.h).
// Driven by test/rpcs3_graphics_tests612_test.py; no emulator, Metal or iPhone.
#include "rpcs3/ios/RPCS3IOSBootDiagnostics.h"

#include <cstdio>
#include <cstdlib>
#include <string>
#include <string_view>
#include <vector>

namespace bd = rpcs3::ios::boot_diagnostics;

static int failures = 0;

static void check(bool condition, const char* what)
{
	if (!condition)
	{
		std::fprintf(stderr, "FAIL: %s\n", what);
		++failures;
	}
}

static bool has_token(const std::string& line, const std::string& token)
{
	const std::string padded = " " + token;
	for (std::size_t at = line.find(padded); at != std::string::npos; at = line.find(padded, at + 1))
	{
		const std::size_t end = at + padded.size();
		if (end == line.size() || line[end] == ' ')
		{
			return true;
		}
	}
	return false;
}

int main()
{
	// Assassin's Creed profile values (Relaxed ZCULL, invariance and asynchronous submits on).
	bd::config_rsx ac{};
	ac.title = "BLES00158";
	ac.relaxed_zcull = "true";
	ac.precise_zpass = "false";
	ac.zcull_queries_off = "false";
	ac.depth_compare = "false";
	ac.shader_precision = "High";
	ac.msl_fast_math_off = "false";
	ac.vertex_cache_off = "false";
	ac.strict = "false";
	ac.rcb = "false";
	ac.rdb = "false";
	ac.msaa = "Auto";
	ac.hp_z = "false";
	ac.fb_bias = "Auto";
	ac.vsync = "Off";
	ac.host_labels = "false";
	ac.strict_flush = "false";
	ac.invariance = true;
	ac.invariance_policy = true;
	ac.mvk_async = true;
	ac.overrides = "gpu.resolution_scale,gpu.zcull_accuracy";
	const std::string line = bd::format_config_rsx_line(ac);
	std::printf("%s\n", line.c_str());

	check(line.rfind("CONFIG_LAYERS part=rsx title=BLES00158 ", 0) == 0, "prefix, part and title first");
	for (const char* token : {
		"relaxed_zcull=true", "precise_zpass=false", "zcull_queries_off=false", "depth_compare=false",
		"shader_precision=High", "msl_fast_math_off=false", "vertex_cache_off=false", "strict=false",
		"rcb=false", "rdb=false", "msaa=Auto", "hp_z=false", "fb_bias=Auto", "vsync=Off",
		"host_labels=false", "strict_flush=false", "invariance=1", "invariance_policy=1", "mvk_async=1",
		"legacy_custom=0", "overrides=gpu.zcull_accuracy", "overrides_truncated=0"})
	{
		check(has_token(line, token), token);
	}
	check(line.find('\n') == std::string::npos, "single line");

	// No override file: empty values print '-' and never split a token.
	bd::config_rsx empty{};
	empty.title = "BLES01717";
	const std::string bare = bd::format_config_rsx_line(empty);
	check(has_token(bare, "overrides=-") && has_token(bare, "invariance=0") && has_token(bare, "mvk_async=0") &&
		has_token(bare, "invariance_policy=0") && has_token(bare, "legacy_custom=0"),
		"empty values print '-' and booleans 0");

	// Shader Precision Low keeps the policy but removes the invariant position.
	bd::config_rsx low = ac;
	low.shader_precision = "Low";
	low.invariance = false;
	low.legacy_custom = true;
	const std::string low_line = bd::format_config_rsx_line(low);
	check(has_token(low_line, "invariance=0") && has_token(low_line, "invariance_policy=1") &&
		has_token(low_line, "legacy_custom=1"), "effective invariance and policy are separate fields");

	// Many unrelated per-game keys before the tested one: only reported keys are kept, none is lost.
	std::string many;
	for (int i = 0; i < 40; ++i)
	{
		many += "gpu.unrelated_setting_number_" + std::to_string(i) + ",";
	}
	many += "debug.emulate_depth_compare,gpu.zcull_accuracy,debug.emulate_depth_compare";
	bd::config_rsx crowded = ac;
	crowded.overrides = many;
	const std::string crowded_line = bd::format_config_rsx_line(crowded);
	check(has_token(crowded_line, "overrides=debug.emulate_depth_compare,gpu.zcull_accuracy") &&
		has_token(crowded_line, "overrides_truncated=0") && crowded_line.find("unrelated") == std::string::npos,
		"unrelated override keys are dropped, the tested keys kept once in order");
	check(has_token(bare, "relaxed_zcull=-"), "unset text value prints '-'");

	// Heavy values: the eight test keys plus spaces in a value stay one bounded line.
	bd::config_rsx heavy = ac;
	heavy.title = "BLES01717-WITH-A-VERY-LONG-TITLE-IDENTIFIER-THAT-IS-NOT-REAL-0123456789";
	heavy.msaa = "Auto with spaces %";
	std::string every;
	for (const std::string_view key : bd::rsx_override_keys)
	{
		every += std::string{key} + ",";
	}
	heavy.overrides = every;
	const std::string long_line = bd::format_config_rsx_line(heavy);
	std::printf("heavy bytes=%zu budget=%zu\n", long_line.size(), bd::line_budget);
	check(long_line.size() < bd::line_budget, "heavy line stays under the host budget");
	check(has_token(long_line, "msaa=Auto%20with%20spaces%20%25"), "spaces and '%' are percent-encoded");
	check(long_line.find("experimental.moltenvk_async_submits") != std::string::npos &&
		has_token(long_line, "overrides_truncated=0"), "every reported key fits without truncation");
	check(long_line.find("title=" + std::string(heavy.title.substr(0, 64)) + " ") != std::string::npos &&
		heavy.title.size() > 64, "title cut at 64 bytes");

	// The main CONFIG_LAYERS line is unchanged by the rsx part (it has no part= token).
	bd::config_layers layers{};
	layers.title = "BLES00158";
	const std::string main_line = bd::format_config_layers_line(layers);
	check(main_line.rfind("CONFIG_LAYERS title=BLES00158 ", 0) == 0 && main_line.find("part=") == std::string::npos,
		"main line keeps its prefix and has no part token");

	if (failures)
	{
		std::fprintf(stderr, "%d failure(s)\n", failures);
		return 1;
	}
	std::printf("PASS: CONFIG_LAYERS part=rsx formatter\n");
	return 0;
}
