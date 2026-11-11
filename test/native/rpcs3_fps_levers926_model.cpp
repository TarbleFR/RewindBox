// SPDX-License-Identifier: GPL-2.0-only
// Core 926 host model: the production title levers and MoltenVK canary rule (-I<source>/rpcs3).
#include <cstdio>
#include <string>
#include <vector>

#include "ios/IOSMoltenVKAsyncCanary.h"
#include "ios/IOSTitleLevers.h"

namespace levers = rpcs3::ios::title_levers;
namespace canary = rpcs3::ios::mvk_async_canary;

static int failures = 0;
#define CHECK(cond) do { if (!(cond)) { std::fprintf(stderr, "CHECK failed line %d: %s\n", __LINE__, #cond); failures++; } } while (0)

int main()
{
	// Texture lookup memo, Automatic: Black Ops II and Assassin's Creed served, nothing only verified.
	for (const char* bo2 : {"BLES01717"}) // the serial the title levers know (IOSTitleLevers.h)
	{
		CHECK(levers::is_black_ops_ii_title(bo2));
		CHECK(levers::serves_texture_lookup_memo(bo2));
		CHECK(!levers::verifies_texture_lookup_memo(bo2));
	}
	CHECK(levers::serves_texture_lookup_memo("BLES00158"));
	CHECK(!levers::serves_texture_lookup_memo("BCES00510"));
	CHECK(!levers::verifies_texture_lookup_memo("BCES00510"));

	// Canary: the 627 record (Black Ops II and God of War III failed) is another file; the 926 cell starts empty.
	CHECK(canary::file_name == "rewindbox-mvk-async-926.txt");
	auto old_records = canary::parse("BLES01717 failed\nBCES00510 failed\nBLES00158 ok\n");
	CHECK(canary::on_boot(old_records, "BLES01717", true) == canary::verdict::failed_before);

	std::vector<canary::record> records = canary::parse("");
	// First 926 boot of Black Ops II: armed.
	CHECK(canary::on_boot(records, "BLES01717", true) == canary::verdict::run);
	CHECK(canary::find(records, "BLES01717")->value == canary::state::armed);
	// It ends while armed (crash or forced exit): the next boot finds it armed, marks it failed and stays synchronous.
	auto after_crash = canary::parse(canary::serialize(records));
	CHECK(canary::on_boot(after_crash, "BLES01717", true) == canary::verdict::previous_boot_failed);
	CHECK(canary::find(after_crash, "BLES01717")->value == canary::state::failed);
	CHECK(canary::on_boot(after_crash, "BLES01717", true) == canary::verdict::failed_before);
	// Confirmed instead (900 presents or a clean shutdown): ok, and the next boot runs again.
	CHECK(canary::on_confirm(records, "BLES01717"));
	auto after_ok = canary::parse(canary::serialize(records));
	CHECK(canary::on_boot(after_ok, "BLES01717", true) == canary::verdict::run);
	// Not requested (the per-game setting Disabled): nothing recorded.
	std::vector<canary::record> none;
	CHECK(canary::on_boot(none, "BCES00510", false) == canary::verdict::off && none.empty());

	std::printf("{\"passed\": %s, \"checks\": \"title levers and canary rule\"}\n", failures ? "false" : "true");
	return failures ? 1 : 0;
}
