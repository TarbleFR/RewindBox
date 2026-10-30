// Compiled after the actual IOSTextureHash.cpp translation unit. Timer is a
// host adapter; XXH3, counters, cancellation and all hash functions are real.
#include <array>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <vector>
#include <sys/mman.h>
#include <unistd.h>

namespace rpcs3::ios {
std::uint64_t texture_hash_hybrid_baseline(const void*, std::size_t,
    const void*, std::size_t, std::uint64_t) noexcept;
}

int main(int argc, char**)
{
    using namespace rpcs3::ios;
    constexpr std::uint64_t sentinel = 0x123456789abcdef0ull;
    std::vector<unsigned char> data((32u << 20) + 64);
    std::uint64_t random = 71;
    for (auto& value : data) {
        random ^= random << 13; random ^= random >> 7; random ^= random << 17;
        value = static_cast<unsigned char>(random);
    }
    std::atomic<std::uint64_t> epoch{12};
    std::atomic<std::size_t> position{3};
    std::atomic<bool> enabled{true};
    texture_hash_cancellation guard{epoch, position, enabled, 12, 3};
    std::size_t cases = 0, aborts = 0, guarded = 0;
    alignas(64) std::array<unsigned char, 256> secret{};
    const std::size_t lengths[] = {0,1,3,4,7,8,15,16,17,31,32,63,64,65,127,128,129,
        239,240,241,255,256,511,512,1023,1024,1025,4095,4096,4097,
        65535,65536,65537,131071,131072,131073,1048575,1048576,1048577};
    for (std::uint64_t seed : {0ull, 1ull, 14695981039346656037ull, 0xffffffffffffffffull})
    for (std::size_t secret_size : {136u, 192u, 256u}) {
        if (secret_size == 192) XXH3_generateSecret_fromSeed(secret.data(), seed);
        else assert(XXH3_generateSecret(secret.data(), secret_size, &seed, sizeof(seed)) == XXH_OK);
        for (auto length : lengths) for (std::size_t offset : {0u,1u,7u,15u,31u}) {
            auto hash = sentinel;
            std::size_t processed = ~std::size_t{0};
            const auto expected = texture_hash_hybrid_baseline(data.data() + offset,
                length, secret.data(), secret_size, seed);
            assert(texture_hash_hybrid_cancellable(data.data() + offset, length,
                secret.data(), secret_size, seed, guard, hash, processed));
            assert(hash == expected && processed == length);
            assert(texture_hash_hybrid(data.data() + offset, length,
                secret.data(), secret_size, seed) == expected);
            ++cases;
        }
    }
    XXH3_generateSecret_fromSeed(secret.data(), 14695981039346656037ull);
    // Reject work that is already obsolete without touching the output.
    for (unsigned reason = 0; reason < 3; ++reason) {
        if (reason == 0) epoch = 13;
        if (reason == 1) position = 4;
        if (reason == 2) enabled = false;
        auto hash = sentinel;
        std::size_t processed = 999;
        assert(!texture_hash_hybrid_cancellable(data.data(), 1048576,
            secret.data(), 192, 14695981039346656037ull, guard, hash, processed));
        assert(hash == sentinel && processed == 0);
        ++aborts;
        epoch = 12; position = 3; enabled = true;
    }
    // Deterministic cancellation at each group boundary uses the actual
    // template/kernel; the injected predicate is a host scheduling stimulus.
    for (std::size_t length : {4096u,65536u,65537u,131073u,1048576u,1048577u}) {
        const auto blocks = (length - 1) / 1024;
        const auto groups = (blocks + 63) / 64;
        for (std::size_t fail_at = 0; fail_at <= groups + 1; ++fail_at) {
            auto hash = sentinel;
            std::size_t processed = 0, calls = 0;
            const bool complete = hash_long_cancellable<XXH3_accumulate, XXH3_scrambleAcc>(data.data() + 1, length,
                secret.data(),
                [&] { return calls++ != fail_at; }, hash, processed);
            assert(!complete && hash == sentinel);
            const std::size_t expected = fail_at <= groups
                ? std::min(fail_at * 64, blocks) * 1024 : length;
            assert(processed == expected && processed <= length);
            ++aborts;
        }
    }
    // Place input exactly against an inaccessible page to catch final-stripe
    // and group-tail overreads independently of vector allocation padding.
    const auto page = static_cast<std::size_t>(sysconf(_SC_PAGESIZE));
    const std::size_t arena = (2u << 20) + 2 * page;
    auto* mapping = static_cast<unsigned char*>(mmap(nullptr, arena, PROT_NONE,
        MAP_PRIVATE | MAP_ANONYMOUS, -1, 0));
    assert(mapping != MAP_FAILED);
    assert(mprotect(mapping + page, arena - 2 * page, PROT_READ | PROT_WRITE) == 0);
    for (std::size_t length : {4096u,4097u,65535u,65536u,65537u,1048575u,1048576u,1048577u}) {
        auto* input = mapping + arena - page - length;
        std::memcpy(input, data.data(), length);
        auto hash = sentinel;
        std::size_t processed = 0;
        assert(texture_hash_hybrid_cancellable(input, length, secret.data(), 192,
            14695981039346656037ull, guard, hash, processed));
        assert(hash == texture_hash_hybrid_baseline(input, length, secret.data(), 192,
            14695981039346656037ull));
        assert(processed == length);
        ++guarded;
    }
    assert(munmap(mapping, arena) == 0);
    std::cout << "{\"passed\":true,\"hashEquivalenceCases\":" << cases
        << ",\"cancelledCases\":" << aborts << ",\"guardPageCases\":" << guarded
        << ",\"maximumGroupBytes\":65536,\"benchmark\":[";
    if (argc > 1) {
        bool first = true;
        std::uint64_t checksum = 0;
        for (std::size_t length : {65536u,1048576u,16777216u}) {
            const std::size_t iterations = (256u << 20) / length;
            std::array<double, 7> before{}, after{};
            auto measure = [&](bool candidate) {
                const auto start = std::chrono::steady_clock::now();
                for (std::size_t i = 0; i < iterations; ++i) {
                    if (candidate) {
                        std::uint64_t hash = 0; std::size_t processed = 0;
                        const bool ok = texture_hash_hybrid_cancellable(data.data() + (i & 31),
                            length, secret.data(), 192, 14695981039346656037ull,
                            guard, hash, processed);
                        assert(ok && processed == length); checksum ^= hash;
                    } else checksum ^= texture_hash_hybrid_baseline(data.data() + (i & 31),
                        length, secret.data(), 192, 14695981039346656037ull);
                }
                return std::chrono::duration<double, std::milli>(
                    std::chrono::steady_clock::now() - start).count();
            };
            measure(false); measure(true);
            for (unsigned i = 0; i < 7; ++i) {
                if (i & 1) { after[i] = measure(true); before[i] = measure(false); }
                else { before[i] = measure(false); after[i] = measure(true); }
            }
            if (!first) std::cout << ',';
            first = false;
            std::cout << "{\"bytesPerHash\":" << length << ",\"iterations\":" << iterations
                << ",\"baselineMs\":[";
            for (unsigned i = 0; i < 7; ++i) { if(i) std::cout << ','; std::cout << before[i]; }
            std::cout << "],\"candidateMs\":[";
            for (unsigned i = 0; i < 7; ++i) { if(i) std::cout << ','; std::cout << after[i]; }
            std::cout << "]}";
        }
        std::fprintf(stderr, "checksum=%llu\n", static_cast<unsigned long long>(checksum));
    }
    std::cout << "]}\n";
}
