// REWINDBOX_SPIRV_DISK_CACHE_634: the real store on a real file. A miss, a hit after reopening, the
// words back unchanged, a torn tail, a damaged entry, another revision, the size bound, and readers
// against writers (the 6 warmup workers against the flush at the end of the warmup).
#include "ios/IOSSpirvCache.h"

#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <thread>
#include <vector>

namespace sc = rpcs3::ios::spirv_cache;

void mbedtls_zeroize(void* data, std::size_t size) { std::memset(data, 0, size); }

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)

static std::vector<std::uint32_t> words_of(std::uint32_t seed, std::size_t count)
{
	std::vector<std::uint32_t> out(count);
	for (std::size_t i = 0; i < count; i++) out[i] = seed * 2654435761u + static_cast<std::uint32_t>(i);
	return out;
}

static sc::key key_of(const std::string& text, std::uint32_t stage = 1)
{
	sc::key name{};
	CHECK(sc::make_key(text, stage, name));
	return name;
}

static std::uint64_t file_size(const std::string& path)
{
	struct stat info{};
	return ::stat(path.c_str(), &info) == 0 ? static_cast<std::uint64_t>(info.st_size) : 0;
}

int main(int argc, char** argv)
{
	const std::string path = std::string(argc > 1 ? argv[1] : ".") + "/spirv.pack";
	::unlink(path.c_str());

	CHECK(key_of("void main() {}") == key_of("void main() {}"));
	CHECK(key_of("void main() {}") != key_of("void main() { }"));
	CHECK(key_of("void main() {}", 1) != key_of("void main() {}", 2));
	{ // the key names the stage, the compiler environment and the text
		const std::uint32_t prefix[2] = {3, sc::environment_revision};
		std::string message(reinterpret_cast<const char*>(prefix), sizeof(prefix));
		message += "void main() {}";
		sc::key expected{};
		mbedtls_sha256_context context;
		mbedtls_sha256_init(&context);
		mbedtls_sha256_starts_ret(&context, 0);
		mbedtls_sha256_update_ret(&context, reinterpret_cast<const unsigned char*>(message.data()), message.size());
		mbedtls_sha256_finish_ret(&context, expected.data());
		mbedtls_sha256_free(&context);
		CHECK(key_of("void main() {}", 3) == expected);
	}

	sc::store store;
	std::vector<std::uint32_t> out;
	CHECK(!store.active() && !store.find(key_of("a"), out));
	store.add(key_of("a"), words_of(1, 10)); // closed: nothing kept
	store.flush();
	CHECK(file_size(path) == 0);

	store.open(path);
	CHECK(store.active() && !store.find(key_of("a"), out));
	const auto first = words_of(1, 1000), second = words_of(2, 77), third = words_of(3, 1);
	store.add(key_of("a"), first);
	store.add(key_of("b"), second);
	CHECK(store.find(key_of("a"), out) && out == first); // before the flush too
	store.flush();
	CHECK(file_size(path) == sizeof(sc::file_header) + 2 * sizeof(sc::entry_header) + (1000 + 77) * 4);
	store.add(key_of("a"), first); // written in this session: not added twice
	store.flush();
	CHECK(file_size(path) == sizeof(sc::file_header) + 2 * sizeof(sc::entry_header) + (1000 + 77) * 4);
	store.close();
	CHECK(!store.active());

	store.open(path);
	CHECK(store.find(key_of("a"), out) && out == first);
	CHECK(store.find(key_of("b"), out) && out == second);
	CHECK(!store.find(key_of("c"), out));
	store.add(key_of("c"), third);
	store.close();

	store.open(path);
	CHECK(store.find(key_of("a"), out) && out == first && store.find(key_of("c"), out) && out == third);
	store.close();

	{ // a torn tail: the valid prefix stays, the next flush cuts the tail and appends after it
		const auto whole = file_size(path);
		CHECK(::truncate(path.c_str(), static_cast<off_t>(whole - 2)) == 0);
		store.open(path);
		CHECK(store.find(key_of("b"), out) && !store.find(key_of("c"), out));
		store.add(key_of("d"), words_of(4, 9));
		store.close();
		store.open(path);
		CHECK(store.find(key_of("a"), out) && out == first);
		CHECK(store.find(key_of("d"), out) && out == words_of(4, 9));
		CHECK(!store.find(key_of("c"), out));
		store.close();
	}
	{ // an entry cut right after its header: its words are not in the file, it is never read
		store.open(path);
		const auto words = words_of(9, 1 << 20);
		store.add(key_of("big"), words);
		store.close();
		const auto whole = file_size(path);
		const auto before = whole - words.size() * 4 - sizeof(sc::entry_header);
		CHECK(::truncate(path.c_str(), static_cast<off_t>(before + sizeof(sc::entry_header))) == 0);
		store.open(path);
		CHECK(!store.find(key_of("big"), out));
		store.add(key_of("f"), words_of(6, 5));
		store.close();
		CHECK(file_size(path) == before + sizeof(sc::entry_header) + 5 * 4);
		store.open(path);
		CHECK(store.find(key_of("f"), out) && out == words_of(6, 5) && store.find(key_of("a"), out) && out == first);
		store.close();
	}
	{ // a damaged entry: a miss at use; the recompiled copy is appended and wins at the next boot
		std::fstream file(path, std::ios::in | std::ios::out | std::ios::binary);
		file.seekp(static_cast<std::streamoff>(sizeof(sc::file_header) + sizeof(sc::entry_header)) + 100);
		const char damaged = 0x5a;
		file.write(&damaged, 1);
		file.close();
		store.open(path);
		const bool first_is_a = store.find(key_of("a"), out);
		const bool second_is_b = store.find(key_of("b"), out);
		CHECK(first_is_a != second_is_b); // the map keeps one order: exactly one of the two was damaged
		const auto name = first_is_a ? key_of("b") : key_of("a");
		const auto words = first_is_a ? second : first;
		store.add(name, words);
		store.close();
		store.open(path);
		CHECK(store.find(name, out) && out == words);
		store.close();
	}
	{ // another compiler environment: nothing is read, the file is rewritten
		std::fstream file(path, std::ios::in | std::ios::out | std::ios::binary);
		file.seekp(8);
		const std::uint32_t other = sc::environment_revision + 1;
		file.write(reinterpret_cast<const char*>(&other), 4);
		file.close();
		store.open(path);
		CHECK(!store.find(key_of("a"), out) && !store.find(key_of("d"), out));
		store.add(key_of("e"), words_of(5, 3));
		store.close();
		CHECK(file_size(path) == sizeof(sc::file_header) + sizeof(sc::entry_header) + 3 * 4);
		store.open(path);
		CHECK(store.find(key_of("e"), out) && !store.find(key_of("a"), out));
		store.close();
	}
	{ // not a pack at all, an empty file, a directory in the way: compiling, as before
		{ std::ofstream file(path, std::ios::trunc | std::ios::binary); file << "not a pack"; }
		store.open(path);
		CHECK(!store.find(key_of("e"), out));
		store.close();
		::unlink(path.c_str());
		::mkdir(path.c_str(), 0755);
		store.open(path);
		CHECK(!store.find(key_of("e"), out));
		store.add(key_of("e"), words_of(5, 3));
		store.close();
		::rmdir(path.c_str());
	}
	{ // the size bound: a full file stops growing, what it holds keeps working
		store.open(path);
		const auto big = words_of(9, sc::max_entry_words);
		unsigned kept = 0;
		for (unsigned i = 0; i < 40; i++)
		{
			store.add(key_of("big" + std::to_string(i)), big);
			store.flush();
			kept += file_size(path) <= sc::max_file_bytes;
		}
		CHECK(kept == 40 && file_size(path) <= sc::max_file_bytes);
		CHECK(file_size(path) >= sc::max_file_bytes - sc::max_entry_words * 4 - sizeof(sc::entry_header));
		store.add(key_of("too large"), std::vector<std::uint32_t>(sc::max_entry_words + 1));
		store.close();
		store.open(path);
		CHECK(store.find(key_of("big0"), out) && out == big && !store.find(key_of("too large"), out));
		store.close();
		::unlink(path.c_str());
	}
	{ // six readers and writers, a flush in the middle, as at the end of a warmup
		store.open(path);
		std::atomic<unsigned> hits{0};
		std::vector<std::thread> workers;
		for (unsigned worker = 0; worker < 6; worker++)
		{
			workers.emplace_back([&, worker]()
			{
				std::vector<std::uint32_t> local;
				for (unsigned i = 0; i < 300; i++)
				{
					const auto name = key_of("shader" + std::to_string((i + worker * 7) % 200));
					if (store.find(name, local)) hits++;
					else store.add(name, words_of((i + worker * 7) % 200, 50 + (i + worker * 7) % 200));
				}
			});
		}
		for (unsigned i = 0; i < 20; i++) store.flush();
		for (auto& worker : workers) worker.join();
		store.close();
		store.open(path);
		unsigned found = 0;
		for (unsigned i = 0; i < 200; i++)
		{
			found += store.find(key_of("shader" + std::to_string(i)), out) && out == words_of(i, 50 + i);
		}
		CHECK(found == 200);
		store.close();
		::unlink(path.c_str());
	}

	std::printf("{\"failures\": %d}\n", failures);
	return failures != 0;
}
