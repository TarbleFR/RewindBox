// REWINDBOX_SPIRV_CAP_636: the real store (ios/IOSSpirvCache.h) on a real file, against its 256 MiB bound when
// add() runs while flush() is writing. The write of the store goes through a hook that can run add() in the middle
// of a flush, as a warmup worker does: deterministic, no timing. Cases:
// 1. The audit's sequence: 1024 bytes below the bound, an 840-byte entry flushed while another 840-byte entry is
//    added during that write, then flushed: the file never exceeds the bound (Core 634: 268436112 bytes).
// 2. An empty file: the 16-byte header counts, so entries that fill the bound without it are refused.
// 3. Six adders and repeated flushes near the bound: the file stays within it, every accepted entry reads back
//    after reopening, every refused one is absent.
#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <mutex>
#include <shared_mutex>
#include <string>
#include <string_view>
#include <thread>
#include <unordered_map>
#include <unordered_set>
#include <vector>

#include <fcntl.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>
#include <zlib.h>

#include "Crypto/sha256.h"

ssize_t rewindbox_test_write(int file, const void* data, size_t size);
#define write rewindbox_test_write
#include "ios/IOSSpirvCache.h"
#undef write

namespace sc = rpcs3::ios::spirv_cache;

void mbedtls_zeroize(void* data, std::size_t size) { std::memset(data, 0, size); }

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

static std::function<void()> g_during_write;

ssize_t rewindbox_test_write(int file, const void* data, size_t size)
{
	if (g_during_write)
	{
		auto action = std::move(g_during_write);
		g_during_write = nullptr;
		action(); // add() while this flush holds only its writer lock
	}
	return ::write(file, data, size);
}

static std::vector<std::uint32_t> words_of(std::uint32_t seed, std::size_t count)
{
	std::vector<std::uint32_t> out(count);
	for (std::size_t i = 0; i < count; i++) out[i] = seed * 2654435761u + static_cast<std::uint32_t>(i);
	return out;
}

static sc::key key_of(const std::string& text)
{
	sc::key name{};
	CHECK(sc::make_key(text, 1, name));
	return name;
}

static std::uint64_t file_size(const std::string& path)
{
	struct stat info{};
	return ::stat(path.c_str(), &info) == 0 ? static_cast<std::uint64_t>(info.st_size) : 0;
}

static constexpr std::uint64_t entry_bytes(std::size_t words) { return sizeof(sc::entry_header) + 4ull * words; }

// Fills a fresh store with large entries until `target` bytes are on disk (header included).
static void fill_to(sc::store& store, const std::string& path, std::uint64_t target)
{
	std::uint64_t size = sizeof(sc::file_header);
	for (unsigned i = 0; size < target; i++)
	{
		const std::uint64_t room = target - size;
		const std::size_t words = room >= entry_bytes(sc::max_entry_words) ? sc::max_entry_words : (room - sizeof(sc::entry_header)) / 4;
		store.add(key_of("fill" + std::to_string(i)), words_of(i, words));
		store.flush();
		size += entry_bytes(words);
		CHECK(file_size(path) == size);
	}
}

static bool readable(sc::store& store, const std::string& text, const std::vector<std::uint32_t>& expected)
{
	std::vector<std::uint32_t> words;
	return store.find(key_of(text), words) && words == expected;
}

int main(int argc, char** argv)
{
	const std::string folder = argc > 1 ? argv[1] : ".";
	int scenarios = 0;

	{ // 1. the audit's sequence, 1024 bytes below the bound
		const std::string path = folder + "/cap-interleaved.pack";
		::unlink(path.c_str());
		sc::store store;
		store.open(path);
		fill_to(store, path, sc::max_file_bytes - 1024);
		const auto first = words_of(1001, 200), second = words_of(1002, 200); // 840 bytes each
		static_assert(entry_bytes(200) == 840);
		store.add(key_of("first"), first);
		g_during_write = [&] { store.add(key_of("second"), second); };
		store.flush();
		CHECK(!g_during_write);
		store.flush();
		const std::uint64_t size = file_size(path);
		std::printf("{\"case\": \"interleaved\", \"bytes\": %llu, \"bound\": %llu}\n",
		            static_cast<unsigned long long>(size), static_cast<unsigned long long>(sc::max_file_bytes));
		CHECK(size <= sc::max_file_bytes);
		CHECK(size == sc::max_file_bytes - 1024 + 840);
		store.close();
		sc::store reopened;
		reopened.open(path);
		CHECK(readable(reopened, "first", first));
		CHECK(!readable(reopened, "second", second));
		reopened.close();
		::unlink(path.c_str());
		scenarios++;
	}

	{ // 2. an empty file: the header counts toward the bound
		const std::string path = folder + "/cap-header.pack";
		::unlink(path.c_str());
		sc::store store;
		store.open(path);
		// Entries whose sum alone is 8 bytes under the bound: with the header the file would be 8 bytes over it.
		std::uint64_t sum = 0;
		std::vector<std::size_t> sizes;
		while (sc::max_file_bytes - 8 - sum >= entry_bytes(sc::max_entry_words))
		{
			sizes.push_back(sc::max_entry_words);
			sum += entry_bytes(sc::max_entry_words);
		}
		sizes.push_back((sc::max_file_bytes - 8 - sum - sizeof(sc::entry_header)) / 4);
		for (std::size_t i = 0; i < sizes.size(); i++) store.add(key_of("h" + std::to_string(i)), words_of(2000 + static_cast<std::uint32_t>(i), sizes[i]));
		store.flush();
		const std::uint64_t size = file_size(path);
		std::printf("{\"case\": \"header\", \"bytes\": %llu, \"bound\": %llu}\n",
		            static_cast<unsigned long long>(size), static_cast<unsigned long long>(sc::max_file_bytes));
		CHECK(size <= sc::max_file_bytes);
		store.close();
		::unlink(path.c_str());
		scenarios++;
	}

	{ // 3. six adders and repeated flushes near the bound
		const std::string path = folder + "/cap-concurrent.pack";
		::unlink(path.c_str());
		sc::store store;
		store.open(path);
		fill_to(store, path, sc::max_file_bytes - 64 * 1024);
		std::atomic<bool> stop{false};
		std::vector<std::thread> workers;
		for (unsigned worker = 0; worker < 6; worker++)
		{
			workers.emplace_back([&, worker] {
				for (unsigned i = 0; i < 200; i++)
					store.add(key_of("w" + std::to_string(worker) + "-" + std::to_string(i)), words_of(worker * 1000 + i, 100 + (i % 7) * 13));
			});
		}
		std::thread flusher([&] { while (!stop) { store.flush(); std::this_thread::yield(); } });
		for (auto& worker : workers) worker.join();
		stop = true;
		flusher.join();
		store.flush();
		const std::uint64_t size = file_size(path);
		CHECK(size <= sc::max_file_bytes);
		store.close();
		sc::store reopened;
		reopened.open(path);
		std::uint64_t found = 0, bytes = sc::max_file_bytes - 64 * 1024;
		for (unsigned worker = 0; worker < 6; worker++)
			for (unsigned i = 0; i < 200; i++)
				if (readable(reopened, "w" + std::to_string(worker) + "-" + std::to_string(i), words_of(worker * 1000 + i, 100 + (i % 7) * 13)))
				{
					found++;
					bytes += entry_bytes(100 + (i % 7) * 13);
				}
		CHECK(found > 0 && bytes == size);
		std::printf("{\"case\": \"concurrent\", \"bytes\": %llu, \"entries\": %llu}\n",
		            static_cast<unsigned long long>(size), static_cast<unsigned long long>(found));
		reopened.close();
		::unlink(path.c_str());
		scenarios++;
	}

	std::printf("{\"failures\": %d, \"scenarios\": %d}\n", failures, scenarios);
	return failures != 0;
}
