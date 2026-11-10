// REWINDBOX_SPURS_RELAXED_STORE_916, executed: the real rpcs3/ios/IOSSpursRelaxedStore.h.
// Driver: test/rpcs3_spurs_relaxed_store916_test.py. Two negative controls, each of which must fail:
// -DCONTROL_OLD_STORE replaces the store by what the relaxed path did before (copy of the whole line once the
// reservation time is unchanged); -DCONTROL_BYTE_MERGE by the first form of this correction, which kept a guest store
// that reached a changed lane beside the SPU's bytes, byte by byte (independent review, 10 November: a store wider
// than one byte could end split).
#include "ios/IOSSpursRelaxedStore.h"

#include <atomic>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <functional>
#include <thread>
#include <vector>

namespace store916 = rpcs3::ios::spurs_relaxed_store;

namespace
{
int g_failures = 0;
int g_checks = 0;

void check(bool condition, const char* what)
{
	g_checks++;

	if (!condition)
	{
		g_failures++;
		std::printf("FAILED: %s\n", what);
	}
}

alignas(128) unsigned char g_line[128];

bool exchange16(unsigned char* lane, store916::lane_t& expected, const store916::lane_t& desired)
{
	unsigned __int128 comp, exch;
	std::memcpy(&comp, expected.bytes, 16);
	std::memcpy(&exch, desired.bytes, 16);
	// Inlined by GCC and Clang (lock cmpxchg16b with -mcx16, an exclusive pair or CASP on ARM64): no libatomic.
	const unsigned __int128 found = __sync_val_compare_and_swap(reinterpret_cast<unsigned __int128*>(lane), comp, exch);
	std::memcpy(expected.bytes, &found, 16);
	return found == comp;
}

// What a PUTLLC on a SPURS header does once the reservation time is unchanged and the unique lock is taken.
template <typename Exchange>
store916::result putllc_store(unsigned char* memory, const unsigned char* getllar, const unsigned char* to_write, Exchange&& exchange)
{
#if defined(CONTROL_OLD_STORE)
	static_cast<void>(getllar);
	static_cast<void>(exchange);
	std::memcpy(memory, to_write, 128);
	return store916::result::stored;
#elif defined(CONTROL_BYTE_MERGE)
	if (std::memcmp(memory, getllar, 128) != 0)
	{
		return store916::result::refused_changed;
	}

	bool written = false;

	for (unsigned at = 0; at < 128; at += 16)
	{
		if (std::memcmp(to_write + at, getllar + at, 16) == 0)
		{
			continue;
		}

		store916::lane_t expected, desired;
		std::memcpy(expected.bytes, getllar + at, 16);
		std::memcpy(desired.bytes, to_write + at, 16);

		if (exchange(memory + at, expected, desired))
		{
			written = true;
			continue;
		}

		if (!written)
		{
			return store916::result::refused_changed;
		}

		for (;;)
		{
			store916::lane_t next;

			for (unsigned i = 0; i < 16; i++)
			{
				next.bytes[i] = expected.bytes[i] != getllar[at + i] ? expected.bytes[i] : to_write[at + i];
			}

			if (exchange(memory + at, expected, next))
			{
				break;
			}
		}
	}

	return store916::result::stored;
#else
	return store916::store(memory, getllar, to_write, exchange);
#endif
}

// The first SPURS header line as the build 718 dump shows it (Assassin's Creed, 0x102ec580), before the wake-up.
void spurs_line(unsigned char* line)
{
	std::memset(line, 0, 128);
	const unsigned char minimum[16] = {1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 8, 0, 0, 0, 0, 0};
	const unsigned char maximum[16] = {6, 6, 6, 6, 6, 6, 6, 6, 6, 6, 3, 0, 0, 0, 0, 0};
	std::memcpy(line + 0x40, minimum, 16);
	std::memcpy(line + 0x50, maximum, 16);
	std::memset(line + 0x6c, 0xff, 4);
	line[0x72] = 0xe0; // sysSrvMessage: the five kernels took their bit of the previous message
	line[0x73] = 0x1e; // spuIdling: kernel 0 is about to go idle
	line[0x76] = 5;    // nSpus
	line[0x77] = 0xff;
}

constexpr unsigned message = 0x72, idling = 0x73;

void deterministic()
{
	unsigned char getllar[128], to_write[128], expected[128];
	std::function<void(unsigned char*, unsigned)> hook; // called before each exchange with the lane and its index in the call order
	unsigned calls = 0;
	const auto exchange = [&](unsigned char* lane, store916::lane_t& want, const store916::lane_t& desired)
	{
		if (hook)
		{
			hook(lane, calls);
		}

		calls++;
		return exchange16(lane, want, desired);
	};
	const auto begin = [&]()
	{
		spurs_line(g_line);
		std::memcpy(getllar, g_line, 128);
		std::memcpy(to_write, getllar, 128);
		to_write[idling] = 0x1f; // lane 0x70: this kernel goes idle
		to_write[0x10] = 1;      // lane 0x10: its idle count
		hook = nullptr;
		calls = 0;
	};

	// 1. Nothing else writes: the line becomes the SPU's copy.
	begin();
	check(putllc_store(g_line, getllar, to_write, exchange) == store916::result::stored && std::memcmp(g_line, to_write, 128) == 0,
		"an undisturbed PUTLLC stores the line");

	// 2. The build 718 sequence: GETLLAR, the PPU stores sysSrvMessage = 0xff, PUTLLC. The store must survive and the
	//    PUTLLC must fail (the kernel then reads the message).
	begin();
	g_line[message] = 0xff;
	std::memcpy(expected, g_line, 128);
	{
		const store916::result r = putllc_store(g_line, getllar, to_write, exchange);
		check(g_line[message] == 0xff, "the PPU's sysSrvMessage store made between GETLLAR and PUTLLC is still in memory");
		check(r == store916::result::refused_changed, "a PUTLLC on a line stored into since GETLLAR fails");
		check(std::memcmp(g_line, expected, 128) == 0, "a refused PUTLLC writes nothing");
	}

	// 3. A guest store before the PUTLLC into a lane the SPU does not change (wklFlag, lane 0x60).
	begin();
	g_line[0x6f] = 0x00;
	std::memcpy(expected, g_line, 128);
	check(putllc_store(g_line, getllar, to_write, exchange) == store916::result::refused_changed && std::memcmp(g_line, expected, 128) == 0,
		"a store into an untouched lane before the PUTLLC fails it and stays");

	// 4. A guest store that arrives while the PUTLLC is being stored, into a lane the SPU does not change.
	begin();
	hook = [&](unsigned char*, unsigned call) { if (call == 0) g_line[0x6f] = 0x12; };
	std::memcpy(expected, to_write, 128);
	expected[0x6f] = 0x12;
	check(putllc_store(g_line, getllar, to_write, exchange) == store916::result::stored && std::memcmp(g_line, expected, 128) == 0,
		"a concurrent store into an untouched lane is never overwritten");

	// 5. A guest store that reaches the first changed lane before anything was written: the PUTLLC fails, untouched line.
	begin();
	hook = [&](unsigned char*, unsigned call) { if (call == 0) g_line[0x11] = 0x77; };
	std::memcpy(expected, getllar, 128);
	expected[0x11] = 0x77;
	check(putllc_store(g_line, getllar, to_write, exchange) == store916::result::refused_changed && std::memcmp(g_line, expected, 128) == 0,
		"a concurrent store into the first changed lane fails the PUTLLC with the line untouched");

	// 6. A guest store that reaches a later changed lane after an earlier one was stored: the PUTLLC fails and the
	//    lane it had stored is given back. The line is what GETLLAR read plus the guest's store.
	begin();
	hook = [&](unsigned char*, unsigned call) { if (call == 1) g_line[message] = 0xff; };
	std::memcpy(expected, getllar, 128);
	expected[message] = 0xff;
	check(putllc_store(g_line, getllar, to_write, exchange) == store916::result::refused_undone && std::memcmp(g_line, expected, 128) == 0,
		"a concurrent store into a later changed lane fails the PUTLLC, which takes back what it had stored");

	// 7. As 6, and a second guest store reaches the lane already stored before it is given back: both stores stay.
	begin();
	hook = [&](unsigned char*, unsigned call)
	{
		if (call == 1) g_line[message] = 0xff;
		if (call == 2) g_line[0x11] = 0x77;
	};
	std::memcpy(expected, getllar, 128);
	expected[message] = 0xff;
	expected[0x11] = 0x77;
	check(putllc_store(g_line, getllar, to_write, exchange) == store916::result::refused_undone && std::memcmp(g_line, expected, 128) == 0,
		"a second store, into the lane being given back, is kept too");

	// 8. A guest store of the byte the SPU changes, while the PUTLLC is stored: the guest's value stays, the PUTLLC fails.
	begin();
	hook = [&](unsigned char*, unsigned call) { if (call == 1) g_line[idling] = 0x00; };
	std::memcpy(expected, getllar, 128);
	expected[idling] = 0x00;
	check(putllc_store(g_line, getllar, to_write, exchange) == store916::result::refused_undone && std::memcmp(g_line, expected, 128) == 0,
		"a concurrent store of a byte the SPU also changes fails the PUTLLC and stays");

	// 9. The counterexample of the review: a two-byte guest store reaches a later changed lane; one of its bytes has
	//    the value GETLLAR read, and the SPU changes both bytes. No order of the two gives a mix of both: the line
	//    must hold the guest's two bytes.
	begin();
	to_write[0x7a] = 1;
	to_write[0x7b] = 1;
	hook = [&](unsigned char*, unsigned call)
	{
		if (call == 1)
		{
			g_line[0x7a] = 0; // the value it had
			g_line[0x7b] = 5;
		}
	};
	std::memcpy(expected, getllar, 128);
	expected[0x7b] = 5;
	{
		const store916::result r = putllc_store(g_line, getllar, to_write, exchange);
		check(g_line[0x7a] == 0 && g_line[0x7b] == 5, "a two-byte guest store is never split between the guest's and the SPU's bytes");
		check(r == store916::result::refused_undone && std::memcmp(g_line, expected, 128) == 0, "the line is what GETLLAR read plus that store");
	}

	// 10. Three changed lanes, the guest store reaches the last one: both stored lanes are given back.
	begin();
	to_write[0x20] = 9;
	hook = [&](unsigned char*, unsigned call) { if (call == 2) g_line[message] = 0xff; };
	std::memcpy(expected, getllar, 128);
	expected[message] = 0xff;
	check(putllc_store(g_line, getllar, to_write, exchange) == store916::result::refused_undone && std::memcmp(g_line, expected, 128) == 0,
		"every lane already stored is given back");
}

// Two plain-store writers (PPU threads: one writes sysSrvMessage, the other a byte of the other lane the SPU threads
// change) beside SPU threads that each count their own byte of both lanes with GETLLAR / PUTLLC. The reservation word
// is the engine's: time in the upper bits, 64 = unique lock; as in do_putllc the time advances for a store and for a
// store that was taken back, and stays for a refusal that wrote nothing.
void concurrent(unsigned spus, unsigned rounds)
{
	spurs_line(g_line);
	std::atomic<std::uint64_t> res{128};
	std::atomic<bool> stop{false};
	std::atomic<std::uint64_t> lost{0}, guest_stores{0};
	std::vector<std::uint64_t> successes(spus, 0), undone(spus, 0);
	const auto byte = [](unsigned at) { return reinterpret_cast<std::atomic<unsigned char>*>(g_line + at); };
	const auto plain_writer = [&](unsigned at, unsigned char first)
	{
		unsigned char value = first;

		while (!stop.load(std::memory_order_relaxed))
		{
			value++;
			byte(at)->store(value, std::memory_order_relaxed);
			guest_stores.fetch_add(1, std::memory_order_relaxed);

			for (int i = 0; i < 64; i++)
			{
				if (byte(at)->load(std::memory_order_relaxed) != value)
				{
					lost.fetch_add(1, std::memory_order_relaxed);
					break;
				}
			}
		}
	};

	std::thread ppu([&]() { plain_writer(message, 0xe0); });
	std::thread ppu2([&]() { plain_writer(0x1f, 0x00); }); // lane 0x10, a byte no SPU thread changes

	std::vector<std::thread> threads;

	for (unsigned index = 0; index < spus; index++)
	{
		threads.emplace_back([&, index]()
		{
			unsigned char getllar[128], to_write[128];

			for (unsigned round = 0; round < rounds;)
			{
				// GETLLAR
				const std::uint64_t rtime = res.load();

				if (rtime & 127)
				{
					continue;
				}

				std::memcpy(getllar, g_line, 128);

				if (res.load() != rtime)
				{
					continue;
				}

				std::memcpy(to_write, getllar, 128);
				to_write[0x78 + index]++; // lane 0x70, beside sysSrvMessage
				to_write[0x10 + index]++; // lane 0x10

				// PUTLLC
				std::uint64_t r = rtime;

				if (!res.compare_exchange_strong(r, rtime + 64))
				{
					continue;
				}

				const store916::result result = putllc_store(g_line, getllar, to_write, exchange16);
				res.fetch_add(result == store916::result::refused_changed ? std::uint64_t{0} - 64 : 64);
				undone[index] += result == store916::result::refused_undone;

				if (result == store916::result::stored)
				{
					successes[index]++;
					round++;
				}
			}
		});
	}

	for (auto& thread : threads)
	{
		thread.join();
	}

	stop = true;
	ppu.join();
	ppu2.join();

	std::uint64_t taken_back = 0;

	for (unsigned index = 0; index < spus; index++)
	{
		taken_back += undone[index];
		// A PUTLLC that failed after it had stored a lane must have given it back: the counts are the successes only.
		check(g_line[0x78 + index] == static_cast<unsigned char>(successes[index]) && g_line[0x10 + index] == static_cast<unsigned char>(successes[index]),
			"the successful PUTLLC of an SPU, and only they, are in memory, in both lanes");
	}

	check(lost.load() == 0, "no plain guest store is overwritten by a PUTLLC");
	std::printf("concurrent: spus=%u rounds=%u guest_stores=%llu lost_guest_stores=%llu undone=%llu\n", spus, rounds,
		static_cast<unsigned long long>(guest_stores.load()), static_cast<unsigned long long>(lost.load()), static_cast<unsigned long long>(taken_back));
}
} // namespace

int main(int argc, char** argv)
{
	deterministic();

	if (argc > 1 && std::strcmp(argv[1], "--deterministic") == 0)
	{
		std::printf("{\"checks\": %d, \"failures\": %d}\n", g_checks, g_failures);
		return g_failures != 0;
	}

	concurrent(5, 200000);
	std::printf("{\"checks\": %d, \"failures\": %d}\n", g_checks, g_failures);
	return g_failures != 0;
}
