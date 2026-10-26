#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <memory>
#include <vector>

using Hash = std::uint64_t (*)(const void*, std::size_t, const void*, std::size_t, std::uint64_t) noexcept;
#define DECLARE(N) namespace N { std::uint64_t texture_hash_hybrid(const void*, std::size_t, const void*, std::size_t, std::uint64_t) noexcept; }
DECLARE(baseline6) DECLARE(neon8) DECLARE(pair8) DECLARE(group4) DECLARE(neon4) DECLARE(hybrid4) DECLARE(twins6) DECLARE(twins8)
const Hash functions[] = {baseline6::texture_hash_hybrid, neon8::texture_hash_hybrid, pair8::texture_hash_hybrid, group4::texture_hash_hybrid, neon4::texture_hash_hybrid, hybrid4::texture_hash_hybrid, twins6::texture_hash_hybrid, twins8::texture_hash_hybrid};
const char* names[] = {"baseline6", "neon8", "pair8", "group4", "neon4", "hybrid4", "twins6", "twins8"};
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
    std::vector<std::uint8_t> data((benchmark ? 64 : 8) * 1024 * 1024 + 128);
    alignas(64) std::array<std::uint8_t, 256> secret{};
    for (auto& byte : data) byte = static_cast<std::uint8_t>(random_word());
    for (auto& byte : secret) byte = static_cast<std::uint8_t>(random_word());
    std::uint64_t cases = 0;
    auto check_buffer = [&](const std::uint8_t* buffer, std::size_t size, std::size_t offset, std::size_t secret_size, std::uint64_t seed)
    {
        const auto expected = functions[0](buffer + offset, size, secret.data(), secret_size, seed);
        for (unsigned variant = 1; variant < variant_count; ++variant)
        {
            const auto actual = functions[variant](buffer + offset, size, secret.data(), secret_size, seed);
            if (actual != expected)
            {
                std::fprintf(stderr, "hash mismatch variant=%s size=%zu offset=%zu secret=%zu seed=%llu\n", names[variant], size, offset, secret_size, static_cast<unsigned long long>(seed));
                std::exit(1);
            }
        }
        ++cases;
    };
    auto check = [&](std::size_t size, std::size_t offset, std::size_t secret_size, std::uint64_t seed)
    {
        check_buffer(data.data(), size, offset, secret_size, seed);
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
        // Exact allocations put the final byte immediately before an ASan
        // redzone. The large reusable corpus above alone cannot detect reads
        // beyond a short logical input when they remain inside its allocation.
        for (const auto boundary : {0u, 64u, 240u, 1024u, 4096u, 16384u, 65536u})
            for (const int delta : {-1, 0, 1})
                for (const auto offset : {0u, 1u, 7u, 15u, 63u})
                {
                    if (boundary == 0 && delta < 0) continue;
                    const std::size_t size = boundary + delta;
                    auto bounded = std::make_unique<std::uint8_t[]>(size + offset);
                    for (std::size_t i = 0; i < size + offset; ++i)
                        bounded[i] = static_cast<std::uint8_t>(random_word());
                    check_buffer(bounded.get(), size, offset, 192, 0);
                }
        std::printf("{\"passed\":true,\"comparisons\":%llu,\"variants\":%u,\"reference\":\"unaltered six-lane production hash\"}\n", static_cast<unsigned long long>(cases * (variant_count - 1)), variant_count);
        return 0;
    }
    // Six timed variants keep the twelve-round Williams design balanced.
    // The rejected simple eight-lane and two-stripe controls remain included
    // in correctness checks and in the first two measurement artifacts.
    constexpr std::array<unsigned, 6> timed = {0, 4, 3, 5, 6, 7};
    constexpr std::array<unsigned, 6> williams = {0, 1, 5, 2, 4, 3};
    constexpr unsigned repeats = 12;
    constexpr std::uint64_t bytes_per_trial = 4ull * 1024 * 1024 * 1024;
    auto quantile = [](std::vector<double> values, double fraction)
    {
        std::sort(values.begin(), values.end());
        const double index = (values.size() - 1) * fraction;
        const auto lower = static_cast<std::size_t>(index);
        const auto upper = std::min(lower + 1, values.size() - 1);
        return values[lower] + (values[upper] - values[lower]) * (index - lower);
    };
    auto print_values = [](const std::vector<double>& values, double scale)
    {
        for (unsigned i = 0; i < values.size(); ++i)
            std::printf("%s%.6f", i ? "," : "", values[i] * scale);
    };
    std::printf("{\"passed\":true,\"benchmark\":true,\"repeats\":12,\"bytes_per_trial\":4294967296,\"order\":\"balanced Williams six treatments, reverse second cycle\",\"paired_ratio\":\"candidate_time / baseline_time in the same round; below1 is faster\",\"rows\":[");
    bool comma = false;
    for (unsigned mode = 0; mode < 2; ++mode)
    for (const auto size : {4096u, 65536u, 1048576u, 8388608u})
    {
        std::array<std::vector<double>, timed.size()> samples;
        const auto iterations = bytes_per_trial / size;
        const std::size_t working_set = mode == 0 ? size : 64u * 1024 * 1024;
        for (unsigned repeat = 0; repeat < repeats; ++repeat)
        {
            // Every treatment occupies each position twice. Predecessor order
            // is also balanced; samples are paired by round, never just ratios
            // of unrelated aggregate medians from different machines/runs.
            for (unsigned position = 0; position < timed.size(); ++position)
            {
                const auto order_position = repeat < 6 ? position : 5 - position;
                const auto treatment = (williams[order_position] + repeat) % timed.size();
                const auto fn = functions[timed[treatment]];
                std::uint64_t output = 0;
                for (std::size_t offset = 0; offset < working_set; offset += size)
                    output ^= fn(data.data() + offset, size, secret.data(), 192, 0);
                const auto start = std::chrono::steady_clock::now();
                for (std::uint64_t iteration = 0; iteration < iterations; ++iteration)
                {
                    const auto offset = ((iteration * size) & (working_set - 1)) + (iteration % 16);
                    output ^= fn(data.data() + offset, size, secret.data(), 192, 0);
                }
                const double seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
                sink = output;
                samples[treatment].push_back(seconds);
            }
        }
        for (unsigned treatment = 0; treatment < timed.size(); ++treatment)
        {
            const auto& values = samples[treatment];
            std::vector<double> ratios;
            for (unsigned round = 0; round < repeats; ++round)
                ratios.push_back(values[round] / samples[0][round]);
            if (comma) std::printf(",");
            comma = true;
            std::printf("{\"variant\":\"%s\",\"mode\":\"%s\",\"working_set_bytes\":%zu,\"size\":%u,\"iterations\":%llu,\"median_ms\":%.6f,\"p10_ms\":%.6f,\"p90_ms\":%.6f,\"minimum_ms\":%.6f,\"maximum_ms\":%.6f,\"paired_ratio_median\":%.6f,\"paired_ratio_p10\":%.6f,\"paired_ratio_p90\":%.6f,\"samples_ms\":[", names[timed[treatment]], mode == 0 ? "cache_hot" : "streaming", working_set, size, static_cast<unsigned long long>(iterations), quantile(values,.5)*1000, quantile(values,.1)*1000, quantile(values,.9)*1000, *std::min_element(values.begin(),values.end())*1000, *std::max_element(values.begin(),values.end())*1000, quantile(ratios,.5), quantile(ratios,.1), quantile(ratios,.9));
            print_values(values,1000);
            std::printf("],\"paired_ratios\":[");
            print_values(ratios,1);
            std::printf("]}");
        }
    }
    std::printf("]}\n");
}
