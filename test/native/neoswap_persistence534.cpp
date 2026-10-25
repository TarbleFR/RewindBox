#include "SourceArchive.h"
#include <chrono>
#include <iostream>
#include <string>
#include <cstdlib>
using namespace neostation;
#define C(x) do { if (!(x)) { std::cerr << "FAIL " << __LINE__ << " " #x "\n"; std::abort(); } } while(0)
int main(int argc, char** argv) {
    C(argc == 2);
    C(storage::Config{}.sync_writes); // Persistent cache clients keep their policy.
    C(!source_archive::Config{}.managed.store.sync_writes);
    const std::size_t bytes = 691200;
    std::string pixels(bytes, ' '); uint64_t random = 45;
    for (auto& b : pixels) { random ^= random << 13; random ^= random >> 7; random ^= random << 17; b = static_cast<char>(random); }
    for (bool durable : {true, false}) {
        source_archive::Config c; c.domain_mask = 15;
        c.managed.store.sync_writes = durable;
        c.managed.store.free_disk_floor = 0;
        c.managed.store.max_write_bytes_per_second = 0;
        c.managed.store.compression = false;
        source_archive::Archive a(argv[1], durable ? 5341 : 5342, c);
        const auto start = std::chrono::steady_clock::now();
        for (unsigned i = 0; i < 10; ++i) {
            auto id = a.admit(3, pixels.data(), pixels.size()); C(id.code == NS_SOURCE_OK);
            while (a.maintain(1, 4)) {}
            auto cold = a.snapshot(); C(!cold.pending && !cold.staging_bytes && !cold.managed.resident_mapped_bytes);
            std::string output(bytes, '\0'); int error = 0;
            C(a.read(id.object, output.data(), output.size(), error) == NS_SOURCE_OK && error == 0 && output == pixels);
            a.discard(id.object); while (a.maintain(1, 4)) {}
        }
        const auto elapsed = std::chrono::duration_cast<std::chrono::microseconds>(std::chrono::steady_clock::now() - start).count();
        auto s = a.snapshot(); const auto& disk = s.managed.store;
        C(!s.sources && !s.staging_bytes && !s.managed.logical_bytes);
        C(s.restored_bytes == 10 * bytes);
        C(s.staging_peak <= c.staging_bytes && s.managed.resident_mapped_peak <= s.managed.resident_limit_bytes);
        C(disk.sync_calls == (durable ? 30u : 0u) && disk.sync_skipped == (durable ? 0u : 30u));
        std::cout << "{\"durable\":" << (durable ? "true" : "false") << ",\"syncCalls\":" << disk.sync_calls
            << ",\"syncSkipped\":" << disk.sync_skipped << ",\"syncUs\":" << disk.sync_us
            << ",\"roundtripUs\":" << elapsed << ",\"restoredBytes\":" << s.restored_bytes
            << ",\"stagingPeak\":" << s.staging_peak << ",\"mappedPeak\":" << s.managed.resident_mapped_peak << "}\n";
    }
}
