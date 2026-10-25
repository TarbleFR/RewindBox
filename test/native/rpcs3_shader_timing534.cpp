#include "ios/IOSShaderTiming.h"
#include <cassert>
#include <thread>
#include <vector>
#include <stdexcept>
#include <iostream>
using namespace rpcs3::ios::shader_timing;
int main() {
    static_assert(sizeof(costs) == 5 * 3 * sizeof(std::uint64_t));
    (void)take();
    std::vector<std::thread> workers;
    for (int i = 0; i < 4; ++i) workers.emplace_back([] {
        for (int j = 0; j < 10000; ++j) { Scope sample(Stage::source); }
    });
    for (auto& worker : workers) worker.join();
    try { Scope sample(Stage::module); throw std::runtime_error("injected"); } catch (const std::runtime_error&) {}
    { Scope sample(Stage::graphics); }
    { Scope sample(Stage::compute); }
    { Scope sample(Stage::debug_source); }
    auto samples = take(); assert(samples[0].count == 40000);
    for (std::size_t i = 1; i < samples.size(); ++i) assert(samples[i].count == 1);
    for (const auto& sample : samples) assert(sample.total >= sample.maximum);
    for (const auto& sample : take()) assert(!sample.count && !sample.total && !sample.maximum);
    std::cout << "PASS actual bounded shader counters: 40000 concurrent events, failure unwinding, all stages, drain\n";
}
