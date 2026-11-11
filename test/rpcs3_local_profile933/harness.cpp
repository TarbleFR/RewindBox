// Host harness of REWINDBOX_LOCAL_PROFILE_933 and REWINDBOX_LEARNED_PREFETCH_933: the real headers of the materialized
// Core (ios/IOSLocalProfile933.h, ios/IOSLocalProfileStore933.h), the store over a temporary directory through a
// stand-in for Utilities/File.h with the same atomic write. Several boots of one title are played in a row: what one
// boot writes is what the next one reads.
#include "ios/IOSLocalProfileStore933.h"

#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <string>

namespace lp = rpcs3::ios::local_profile933;

static int checks = 0, failures = 0;

#define CHECK(condition) \
	do \
	{ \
		checks++; \
		if (!(condition)) \
		{ \
			failures++; \
			std::fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
		} \
	} while (0)

static lp::profile sample()
{
	lp::profile p{"BLES01234", "01.02", {}, 0};
	p.prefetch = {lp::state::on, 2, 7162, 4300, 0, 0};
	return p;
}

static void format_cases()
{
	const std::string text = lp::serialize(sample());
	CHECK(text == "rewindbox-local-profile 1\nserial BLES01234\nversion 01.02\n"
		"spu_object_prefetch on validated=2 evidence_reads=7162 evidence_ms=4300 withdrawn_planned=0 withdrawn_hits=0\n");
	CHECK(text.size() <= lp::max_bytes);

	lp::profile read;
	CHECK(lp::parse(text, "BLES01234", "01.02", read) == lp::load_status::loaded);
	CHECK(read.prefetch.value == lp::state::on && read.prefetch.validated == 2 && read.prefetch.evidence_reads == 7162 &&
		read.prefetch.evidence_ms == 4300 && read.skipped_lines == 0);

	// A profile without a decision is the header and the identity.
	lp::profile empty{"BLES01234", "01.02", {}, 0};
	CHECK(lp::serialize(empty) == "rewindbox-local-profile 1\nserial BLES01234\nversion 01.02\n");
	CHECK(lp::parse(lp::serialize(empty), "BLES01234", "01.02", read) == lp::load_status::loaded && read.prefetch.value == lp::state::none);

	// A withdrawn decision keeps what withdrew it.
	lp::profile withdrawn = sample();
	withdrawn.prefetch.value = lp::state::withdrawn;
	withdrawn.prefetch.withdrawn_planned = 5000;
	withdrawn.prefetch.withdrawn_hits = 3;
	CHECK(lp::parse(lp::serialize(withdrawn), "BLES01234", "01.02", read) == lp::load_status::loaded &&
		read.prefetch.value == lp::state::withdrawn && read.prefetch.withdrawn_planned == 5000 && read.prefetch.withdrawn_hits == 3);

	// Another game version: the decisions are not used; the profile is reset to this version.
	CHECK(lp::parse(text, "BLES01234", "01.03", read) == lp::load_status::other_version);
	CHECK(read.serial == "BLES01234" && read.version == "01.03" && read.prefetch.value == lp::state::none);

	// Not understood: never half read.
	const auto malformed = [&](const std::string& candidate)
	{
		lp::profile out;
		const lp::load_status status = lp::parse(candidate, "BLES01234", "01.02", out);
		return status == lp::load_status::malformed && out.prefetch.value == lp::state::none;
	};
	CHECK(malformed(text.substr(0, text.size() - 1)));                              // cut: no final newline
	CHECK(malformed(text.substr(0, text.find("version"))));                         // no version line
	CHECK(malformed("rewindbox-local-profile 2\n" + text.substr(text.find('\n') + 1))); // another format
	CHECK(malformed(text + "spu_object_prefetch on validated=1 evidence_reads=1 evidence_ms=1 withdrawn_planned=0 withdrawn_hits=0\n")); // twice
	CHECK(malformed(text + "serial BLES01234\n"));                                   // identity twice
	CHECK(malformed("rewindbox-local-profile 1\nserial BLES09999\nversion 01.02\n")); // another title's file
	CHECK(malformed("rewindbox-local-profile 1\nserial BLES01234\nversion 01.02\nspu_object_prefetch maybe validated=0 evidence_reads=0 evidence_ms=0 withdrawn_planned=0 withdrawn_hits=0\n"));
	CHECK(malformed("rewindbox-local-profile 1\nserial BLES01234\nversion 01.02\nspu_object_prefetch on validated=-1 evidence_reads=0 evidence_ms=0 withdrawn_planned=0 withdrawn_hits=0\n"));
	CHECK(malformed("rewindbox-local-profile 1\nserial BLES01234\nversion 01.02\nspu_object_prefetch on validated=1 evidence_reads=0 evidence_ms=0 withdrawn_planned=0\n"));
	CHECK(malformed("rewindbox-local-profile 1\nserial BLES01234\nversion 01.02\nspu_object_prefetch on validated=1 evidence_reads=0 evidence_ms=0 withdrawn_planned=0 withdrawn_hits=0 extra=1\n"));
	CHECK(malformed("rewindbox-local-profile 1\nserial BLES01234\nversion 01.02\nspu_object_prefetch on validated=99999999999999999999999 evidence_reads=0 evidence_ms=0 withdrawn_planned=0 withdrawn_hits=0\n"));
	CHECK(malformed("rewindbox-local-profile 1\nserial BLES01234\nversion 01.02\nkey=value\n"));
	CHECK(malformed(""));

	// A decision of a later Core is skipped and counted; the rest is read.
	CHECK(lp::parse(text + "texture_prehash_depth 16\n", "BLES01234", "01.02", read) == lp::load_status::loaded &&
		read.skipped_lines == 1 && read.prefetch.value == lp::state::on);

	// Bounded.
	CHECK(lp::parse(text + std::string(lp::max_bytes, '#') + "\n", "BLES01234", "01.02", read) == lp::load_status::too_large);

	// Identity rules: the serial names the file.
	CHECK(lp::valid_serial("BLES01717") && lp::valid_serial("NPUB30702") && lp::valid_serial("BCES00510"));
	CHECK(!lp::valid_serial("") && !lp::valid_serial("BLES0171") && !lp::valid_serial("BLES017170") && !lp::valid_serial("bles01717") &&
		!lp::valid_serial("../../../x") && !lp::valid_serial("BLES0171/") && !lp::valid_serial("12340BLES"));
	CHECK(lp::valid_version("01.02") && lp::valid_version("1.0") && !lp::valid_version("") && !lp::valid_version("01 02") &&
		!lp::valid_version("01.02\nserial") && !lp::valid_version("0123456789ABCDEFG"));
}

static lp::window_input play_window(std::uint64_t reads, std::uint64_t ms, std::uint64_t gameplay, std::uint64_t session = 1)
{
	lp::window_input in;
	in.cache_reads = reads;
	in.cache_read_us = ms * 1000;
	in.gameplay_compiles = gameplay;
	in.frames = 150;
	in.session = session;
	return in;
}

// The first window of a session is not used: a heavy one proves it (it would teach, validate or withdraw).
static void prime(lp::prefetch_rule& rule, lp::prefetch_record& record, std::uint64_t session = 1)
{
	lp::window_input heavy = play_window(7162, 4300, 7162, session);
	heavy.prefetch_hits = 9000;
	heavy.prefetch_planned = 9000;
	const lp::prefetch_record before = record;
	CHECK(rule.observe(heavy, record) == lp::verdict::none);
	CHECK(record.value == before.value && record.validated == before.validated);
}

static void rule_cases()
{
	// Learning.
	{
		lp::prefetch_rule rule;
		lp::prefetch_record record{};
		rule.begin(true, false);
		prime(rule, record);
		CHECK(rule.observe(play_window(199, 900, 199), record) == lp::verdict::none); // too few objects
		CHECK(rule.observe(play_window(400, 499, 400), record) == lp::verdict::none); // too little time
		CHECK(rule.observe(play_window(1810, 1852, 0), record) == lp::verdict::none); // the boot warm-up (God of War III)
		CHECK(rule.observe(play_window(1000, 900, 499), record) == lp::verdict::none); // mostly warm-up
		lp::window_input active = play_window(7162, 4300, 7162);
		active.prefetch_active = true;
		CHECK(rule.observe(active, record) == lp::verdict::none); // the prefetch already runs: nothing to learn
		CHECK(record.value == lp::state::none);
		CHECK(rule.observe(play_window(1674, 628, 1674), record) == lp::verdict::learned);
		CHECK(record.value == lp::state::on && record.evidence_reads == 1674 && record.evidence_ms == 628 && record.validated == 0);
		CHECK(rule.observe(play_window(1674, 628, 1674), record) == lp::verdict::none); // once per boot
	}
	// Not eligible (a setting, or the title list): nothing is learned or withdrawn.
	{
		lp::prefetch_rule rule;
		lp::prefetch_record record{};
		rule.begin(false, true);
		CHECK(!rule.learned_on());
		CHECK(rule.observe(play_window(7162, 4300, 7162), record) == lp::verdict::none && record.value == lp::state::none);
	}
	// A withdrawn decision is not learned again.
	{
		lp::prefetch_rule rule;
		lp::prefetch_record record{lp::state::withdrawn, 0, 1674, 628, 5000, 3};
		rule.begin(true, false);
		prime(rule, record);
		CHECK(rule.observe(play_window(7162, 4300, 7162), record) == lp::verdict::none && record.value == lp::state::withdrawn);
	}
	// Validation by hits.
	{
		lp::prefetch_rule rule;
		lp::prefetch_record record{lp::state::on, 1, 1674, 628, 0, 0};
		rule.begin(true, true);
		prime(rule, record);
		lp::window_input in = play_window(0, 0, 0);
		in.prefetch_active = true;
		in.prefetch_planned = 6000;
		in.prefetch_hits = 499;
		CHECK(rule.observe(in, record) == lp::verdict::none);
		in.prefetch_hits = 1;
		CHECK(rule.observe(in, record) == lp::verdict::validated && record.validated == 2 && record.value == lp::state::on);
		in.prefetch_hits = 5000;
		CHECK(rule.observe(in, record) == lp::verdict::none && record.validated == 2); // once per boot
	}
	// Withdrawal after two minutes of play with almost no hit; paused windows do not count.
	{
		lp::prefetch_rule rule;
		lp::prefetch_record record{lp::state::on, 0, 1674, 628, 0, 0};
		rule.begin(true, true);
		prime(rule, record);
		lp::window_input in = play_window(0, 0, 0);
		in.prefetch_active = true;
		in.prefetch_planned = 5000;
		in.prefetch_hits = 2;
		lp::window_input paused = in;
		paused.frames = 0;
		paused.prefetch_hits = 0;
		for (int i = 0; i < 200; i++)
		{
			CHECK(rule.observe(paused, record) == lp::verdict::none); // a long pause or the background
		}
		for (unsigned i = 1; i < lp::withdraw_after_windows; i++)
		{
			CHECK(rule.observe(in, record) == lp::verdict::none);
		}
		CHECK(record.value == lp::state::on);
		CHECK(rule.observe(in, record) == lp::verdict::withdrawn);
		CHECK(record.value == lp::state::withdrawn && record.withdrawn_planned == 5000 && record.withdrawn_hits == 2 * lp::withdraw_after_windows);
		CHECK(rule.observe(in, record) == lp::verdict::none);
	}
	// Few planned objects or enough hits: kept.
	{
		lp::prefetch_rule rule;
		lp::prefetch_record record{lp::state::on, 0, 1674, 628, 0, 0};
		rule.begin(true, true);
		prime(rule, record);
		lp::window_input in = play_window(0, 0, 0);
		in.prefetch_active = true;
		in.prefetch_planned = 99;
		for (unsigned i = 0; i < 3 * lp::withdraw_after_windows; i++)
		{
			CHECK(rule.observe(in, record) == lp::verdict::none);
		}
		CHECK(record.value == lp::state::on);
		rule.begin(true, true);
		prime(rule, record);
		in.prefetch_planned = 4000;
		in.prefetch_hits = 2; // 48 hits over 24 windows = 1.2 % of 4000: above the 1 % bound
		for (unsigned i = 0; i < lp::withdraw_after_windows; i++)
		{
			CHECK(rule.observe(in, record) == lp::verdict::none);
		}
		CHECK(record.value == lp::state::on);
	}
}

static void review_cases()
{
	// The end of the previous boot (a game started within 5 s of another): a window reported before the new session,
	// then the first window of the session, both heavy; neither teaches nor validates.
	{
		lp::prefetch_rule rule;
		lp::prefetch_record record{};
		rule.begin(true, false);
		CHECK(rule.observe(play_window(7162, 4300, 7162, 41), record) == lp::verdict::none); // previous boot's session
		CHECK(rule.observe(play_window(7162, 4300, 7162, 42), record) == lp::verdict::none); // first window of this one
		CHECK(record.value == lp::state::none);
		CHECK(rule.observe(play_window(1674, 628, 1674, 42), record) == lp::verdict::learned); // this boot's own window
	}
	{
		lp::prefetch_rule rule;
		lp::prefetch_record record{lp::state::on, 0, 1674, 628, 0, 0};
		rule.begin(true, true);
		lp::window_input carried = play_window(0, 0, 0, 7);
		carried.prefetch_active = true;
		carried.prefetch_planned = 5000;
		carried.prefetch_hits = 2000; // hits of the previous boot's last window
		CHECK(rule.observe(carried, record) == lp::verdict::none);
		carried.session = 8;
		CHECK(rule.observe(carried, record) == lp::verdict::none);
		CHECK(record.validated == 0);
		lp::window_input own = carried;
		own.prefetch_hits = 2;
		for (unsigned i = 1; i < lp::withdraw_after_windows; i++)
		{
			CHECK(rule.observe(own, record) == lp::verdict::none);
		}
		CHECK(rule.observe(own, record) == lp::verdict::withdrawn); // the carried hits did not hide the withdrawal
	}
	// Validated `validation_writes` times: a boot that validates again writes nothing.
	{
		lp::prefetch_rule rule;
		lp::prefetch_record record{lp::state::on, lp::validation_writes, 1674, 628, 0, 0};
		rule.begin(true, true);
		prime(rule, record);
		lp::window_input in = play_window(0, 0, 0);
		in.prefetch_active = true;
		in.prefetch_planned = 6000;
		in.prefetch_hits = 5000;
		CHECK(rule.observe(in, record) == lp::verdict::none && record.validated == lp::validation_writes);
		// ...and does not withdraw it either in the same boot.
		in.prefetch_hits = 0;
		for (unsigned i = 0; i < 2 * lp::withdraw_after_windows; i++)
		{
			CHECK(rule.observe(in, record) == lp::verdict::none);
		}
		CHECK(record.value == lp::state::on);
	}
	// A title without a version gets no profile.
	CHECK(!lp::valid_version("Unknown") && !lp::valid_version("A.B") && lp::valid_version("01.02") && lp::valid_version("1"));
	CHECK(lp::current::instance().load("BLUS30418", "Unknown") == lp::load_status::not_a_title);
}

// One boot of the title through the store, as Emulator::Load, the policy and the report thread drive it.
struct boot_result
{
	lp::load_status status;
	bool prefetch_on;
	lp::verdict outcome;
};

static std::uint64_t next_session = 100;

template <typename Play>
static boot_result boot(std::string_view serial, std::string_view version, bool automatic, bool on_title_list, Play&& play)
{
	auto& current = lp::current::instance();
	const lp::load_status status = current.load(serial, version);
	const bool learnable = automatic && !on_title_list;
	const bool learned = learnable && current.prefetch().value == lp::state::on;
	current.begin_boot(learnable, learned);
	const bool prefetch_on = (automatic ? on_title_list : false) || learned;
	const std::uint64_t session = next_session++;
	lp::verdict outcome = lp::verdict::none;
	{
		lp::window_input heavy = play_window(7162, 4300, 7162, session);
		heavy.prefetch_active = prefetch_on;
		heavy.prefetch_hits = prefetch_on ? 9000 : 0;
		heavy.prefetch_planned = prefetch_on ? 9000 : 0;
		CHECK(current.observe(heavy).outcome == lp::verdict::none); // the session's first window
	}
	play(prefetch_on, [&](lp::window_input in)
	{
		in.session = session;
		const lp::observation seen = current.observe(in);
		if (seen.outcome != lp::verdict::none)
		{
			outcome = seen.outcome;
			CHECK(seen.saved);
		}
	});
	return {status, prefetch_on, outcome};
}

static std::string read_file(const std::string& path)
{
	fs::file file{path, fs::read};
	return file ? file.to_string() : std::string{};
}

static void store_cases(const std::string& root)
{
	fs::config_root = root + "/a/";
	const std::string path = lp::path_for("BLUS30418");
	CHECK(path == root + "/a/config/local_profiles/BLUS30418.txt");

	// Boot 1: no profile; play shows the cost; the decision is written for the next boot, this boot is unchanged.
	boot_result r = boot("BLUS30418", "01.00", true, false, [](bool on, auto&& window)
	{
		CHECK(!on);
		window(play_window(50, 20, 50));
		window(play_window(1674, 628, 1674));
		window(play_window(1500, 700, 1500));
	});
	CHECK(r.status == lp::load_status::absent && !r.prefetch_on && r.outcome == lp::verdict::learned);
	CHECK(read_file(path).find("spu_object_prefetch on validated=0 evidence_reads=1674 evidence_ms=628") != std::string::npos);
	CHECK(!fs::is_file(path + ".pending"));

	// Boot 2: the prefetch runs from the start and serves the reads: validated.
	r = boot("BLUS30418", "01.00", true, false, [](bool on, auto&& window)
	{
		CHECK(on);
		lp::window_input in = play_window(1674, 30, 1674);
		in.prefetch_active = true;
		in.prefetch_planned = 6000;
		in.prefetch_hits = 1600;
		window(in);
	});
	CHECK(r.status == lp::load_status::loaded && r.prefetch_on && r.outcome == lp::verdict::validated);
	CHECK(read_file(path).find("spu_object_prefetch on validated=1 ") != std::string::npos);

	// Boot 3: the user sets the prefetch (Enabled or Disabled): the profile is read, nothing is learned or written.
	const unsigned commits_before = fs::commits;
	r = boot("BLUS30418", "01.00", false, false, [](bool on, auto&& window)
	{
		CHECK(!on); // Disabled by the user in this scenario
		window(play_window(7162, 4300, 7162));
	});
	CHECK(r.status == lp::load_status::loaded && r.outcome == lp::verdict::none && fs::commits == commits_before);

	// Boot 4: a game update (01.01): the decisions of 01.00 do not apply; this version learns on its own.
	r = boot("BLUS30418", "01.01", true, false, [](bool on, auto&& window)
	{
		CHECK(!on);
		window(play_window(10, 1, 10));
	});
	CHECK(r.status == lp::load_status::other_version && !r.prefetch_on && r.outcome == lp::verdict::none);

	// Boot 5: back on 01.00 (the file was not rewritten by boot 4): still learned.
	r = boot("BLUS30418", "01.00", true, false, [](bool on, auto&&) { CHECK(on); });
	CHECK(r.status == lp::load_status::loaded && r.prefetch_on);

	// Boot 6: two minutes of play without use: withdrawn, written; boot 7 runs without it and does not learn it again.
	r = boot("BLUS30418", "01.00", true, false, [](bool on, auto&& window)
	{
		CHECK(on);
		lp::window_input in = play_window(0, 0, 0);
		in.prefetch_active = true;
		in.prefetch_planned = 5000;
		for (unsigned i = 0; i < lp::withdraw_after_windows; i++)
		{
			window(in);
		}
	});
	CHECK(r.outcome == lp::verdict::withdrawn);
	CHECK(read_file(path).find("spu_object_prefetch withdrawn ") != std::string::npos);
	r = boot("BLUS30418", "01.00", true, false, [](bool on, auto&& window)
	{
		CHECK(!on);
		window(play_window(7162, 4300, 7162));
	});
	CHECK(r.status == lp::load_status::loaded && !r.prefetch_on && r.outcome == lp::verdict::none);

	// A title on the list (Black Ops II) is decided by the list: no file is written for it.
	r = boot("BLES01717", "01.00", true, true, [](bool on, auto&& window)
	{
		CHECK(on);
		window(play_window(7162, 4300, 7162));
	});
	CHECK(r.outcome == lp::verdict::none && !fs::is_file(lp::path_for("BLES01717")));

	// A boot without a game serial (the system menu) reads and writes nothing.
	r = boot("", "", true, false, [](bool, auto&& window) { window(play_window(7162, 4300, 7162)); });
	CHECK(r.status == lp::load_status::not_a_title && r.outcome == lp::verdict::none);
	r = boot("../../../x", "01.00", true, false, [](bool, auto&& window) { window(play_window(7162, 4300, 7162)); });
	CHECK(r.status == lp::load_status::not_a_title && r.outcome == lp::verdict::none);

	// A damaged file is ignored, the boot goes on, and the next decision replaces it whole.
	fs::config_root = root + "/b/";
	CHECK(fs::create_path(lp::directory()));
	{
		fs::file damaged{lp::path_for("NPUB30702"), fs::write};
		const std::string text = "rewindbox-local-profile 1\nserial NPUB30702\nversion 01.08\nspu_object_prefetch on validated=";
		damaged.write(text.data(), text.size());
	}
	r = boot("NPUB30702", "01.08", true, false, [](bool on, auto&& window)
	{
		CHECK(!on);
		window(play_window(1674, 628, 1674));
	});
	CHECK(r.status == lp::load_status::malformed && r.outcome == lp::verdict::learned);
	lp::profile reread;
	CHECK(lp::parse(read_file(lp::path_for("NPUB30702")), "NPUB30702", "01.08", reread) == lp::load_status::loaded &&
		reread.prefetch.value == lp::state::on);

	// An oversized file is not read.
	{
		fs::file big{lp::path_for("BLUS30127"), fs::write};
		const std::string text(lp::max_bytes + 1, 'x');
		big.write(text.data(), text.size());
	}
	CHECK(lp::current::instance().load("BLUS30127", "01.08") == lp::load_status::too_large);

	// A write that fails leaves the old file whole, and the boot goes on.
	const std::string before = read_file(lp::path_for("NPUB30702"));
	fs::fail_writes = true;
	{
		auto& current = lp::current::instance();
		CHECK(current.load("NPUB30702", "01.08") == lp::load_status::loaded);
		current.begin_boot(true, true);
		lp::window_input in = play_window(0, 0, 0);
		in.prefetch_active = true;
		in.prefetch_planned = 6000;
		in.prefetch_hits = 600;
		in.session = next_session++;
		CHECK(current.observe(in).outcome == lp::verdict::none); // the session's first window
		const lp::observation seen = current.observe(in);
		CHECK(seen.outcome == lp::verdict::validated && !seen.saved);
	}
	fs::fail_writes = false;
	CHECK(read_file(lp::path_for("NPUB30702")) == before);
}

int main(int argc, char** argv)
{
	if (argc != 2)
	{
		std::fprintf(stderr, "usage: harness <empty directory>\n");
		return 2;
	}
	format_cases();
	rule_cases();
	review_cases();
	store_cases(argv[1]);
	std::printf("{\"checks\": %d, \"failures\": %d}\n", checks, failures);
	return failures ? 1 : 0;
}
