#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>

using Hash = std::uint64_t (*)(const void*, std::size_t, const void*, std::size_t, std::uint64_t) noexcept;
#define DECLARE(N) namespace N { std::uint64_t texture_hash_hybrid(const void*, std::size_t, const void*, std::size_t, std::uint64_t) noexcept; }
DECLARE(baseline6) DECLARE(neon8) DECLARE(pair8) DECLARE(group4) DECLARE(neon4) DECLARE(hybrid4)
const Hash functions[] = {baseline6::texture_hash_hybrid, neon8::texture_hash_hybrid, pair8::texture_hash_hybrid, group4::texture_hash_hybrid, neon4::texture_hash_hybrid, hybrid4::texture_hash_hybrid};
const char* names[] = {"baseline6", "neon8", "pair8", "group4", "neon4", "hybrid4"};
constexpr unsigned variant_count = sizeof(functions) / sizeof(functions[0]);
static std::uint64_t state = 0x24691358bdfeca71ull;
static std::uint64_t random_word()
{
    state ^= state << 13; state ^= state >> 7; state ^= state << 17;
    return state;
}
static volatile std::uint64_t sink = 0;

int main(int argc, char** argv)
{
    const bool benchmark = argc > 1 && std::strcmp(argv[1], "--bench") == 0;
    std::vector<std::uint8_t> data(8 * 1024 * 1024 + 128);
    alignas(64) std::array<std::uint8_t, 256> secret{};
    for (auto& byte : data) byte = static_cast<std::uint8_t>(random_word());
    for (auto& byte : secret) byte = static_cast<std::uint8_t>(random_word());
    std::uint64_t cases = 0;
    auto check = [&](std::size_t size, std::size_t offset, std::size_t secret_size, std::uint64_t seed)
    {
        const auto expected = functions[0](data.data() + offset, size, secret.data(), secret_size, seed);
        for (unsigned variant = 1; variant < variant_count; ++variant)
        {
            const auto actual = functions[variant](data.data() + offset, size, secret.data(), secret_size, seed);
            if (actual != expected)
            {
                std::fprintf(stderr, "hash mismatch variant=%s size=%zu offset=%zu secret=%zu seed=%llu\n", names[variant], size, offset, secret_size, static_cast<unsigned long long>(seed));
                std::exit(1);
            }
        }
        ++cases;
    };
    if (!benchmark)
    {
        for (const auto secret_size : {136u, 191u, 192u, 193u, 256u})
        {
            for (const auto seed : {0ull, 1ull, 0x9e3779b185ebca87ull})
            {
                for (std::size_t length = 0; length <= 512; ++length)
                    check(length, length % 64, secret_size, seed);
                for (std::size_t length = 4032; length <= 4160; ++length)
                    for (std::size_t offset = 0; offset < 64; offset += 7)
                        check(length, offset, secret_size, seed);
                for (const auto boundary : {64u, 1024u, 16384u, 65536u, 1048576u})
                    for (const int delta : {-1, 0, 1})
                        for (const auto offset : {0u, 1u, 7u, 15u, 31u, 63u})
                            check(boundary + delta, offset, secret_size, seed);
                for (unsigned i = 0; i < 32; ++i)
                    check(random_word() % (2 * 1024 * 1024), random_word() % 64, secret_size, seed);
            }
        }
        std::printf("{\"passed\":true,\"comparisons\":%llu,\"variants\":%u,\"reference\":\"unaltered six-lane production hash\"}\n", static_cast<unsigned long long>(cases * (variant_count - 1)), variant_count);
        return 0;
    }
    std::printf("{\"passed\":true,\"benchmark\":true,\"repeats\":9,\"rows\":[");
    bool comma = false;
    for (const auto size : {4096u, 65536u, 1048576u, 8388608u})
    {
        std::array<std::vector<double>, variant_count> samples;
        const auto iterations = (256ull * 1024 * 1024) / size;
        for (unsigned repeat = 0; repeat < 9; ++repeat)
        {
            // Rotate the execution order. No candidate always inherits the
            // warmed cache from the same predecessor.
            for (unsigned position = 0; position < variant_count; ++position)
            {
                const auto variant = (position + repeat) % variant_count;
                const auto fn = functions[variant];
                std::uint64_t output = 0;
                for (unsigned warm = 0; warm < 4; ++warm)
                    output ^= fn(data.data(), size, secret.data(), 192, 0);
                const auto start = std::chrono::steady_clock::now();
                for (std::uint64_t iteration = 0; iteration < iterations; ++iteration)
                    output ^= fn(data.data() + (iteration % 16), size, secret.data(), 192, 0);
                const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
                sink = output;
                samples[variant].push_back(seconds);
            }
        }
        for (unsigned variant = 0; variant < variant_count; ++variant)
        {
            auto ordered = samples[variant];
            std::sort(ordered.begin(), ordered.end());
            if (comma) std::printf(",");
            comma = true;
            std::printf("{\"variant\":\"%s\",\"size\":%u,\"iterations\":%llu,\"median_ms\":%.6f,\"minimum_ms\":%.6f,\"maximum_ms\":%.6f,\"samples_ms\":[", names[variant], size, static_cast<unsigned long long>(iterations), ordered[4] * 1000, ordered.front() * 1000, ordered.back() * 1000);
            for (unsigned i = 0; i < samples[variant].size(); ++i)
                std::printf("%s%.6f", i ? "," : "", samples[variant][i] * 1000);
            std::printf("]}");
        }
    }
    std::printf("]}\n");
}
