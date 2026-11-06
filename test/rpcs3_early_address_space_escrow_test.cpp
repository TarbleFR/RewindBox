#include "Rpcs3EarlyAddressSpaceEscrowPolicy.h"

#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <vector>

namespace escrow = neostation::rpcs3::early_escrow;

struct MockBackend {
  std::vector<escrow::Range> mappings;
  uint64_t rejected_address = 0;
  uint64_t failed_release_address = 0;
  bool cleanup_error = false;
  size_t release_count = 0;

  bool cleanup_failed() const { return cleanup_error; }

  int reserve(uint64_t address, uint64_t bytes) {
    if (address == rejected_address) return 17;
    const escrow::Range wanted{address, address + bytes};
    for (const escrow::Range mapping : mappings) {
      if (!(wanted.end <= mapping.begin || mapping.end <= wanted.begin)) {
        return 18;
      }
    }
    mappings.push_back(wanted);
    return 0;
  }

  int release(uint64_t address, uint64_t bytes) {
    ++release_count;
    if (address == failed_release_address) return 19;
    const escrow::Range wanted{address, address + bytes};
    const auto found = std::find_if(
        mappings.begin(), mappings.end(), [&](const escrow::Range mapping) {
          return mapping.begin == wanted.begin && mapping.end == wanted.end;
        });
    if (found == mappings.end()) return 20;
    mappings.erase(found);
    return 0;
  }
};

int main() {
  constexpr uint64_t page = 16 * 1024;
  constexpr uint64_t clean_gap = 715 * escrow::mib;

  // The exact post-startup gap observed on device is enough to protect the
  // Core's preferred 448 + 256 MiB layout before Dusklight can fragment it.
  MockBackend clean;
  auto held = escrow::reserve(
      {{escrow::low, escrow::low + clean_gap}}, page, clean);
  assert(held.layout);
  assert(held.layout.contiguous);
  assert(held.layout.code_bytes == 448 * escrow::mib);
  assert(clean.mappings.size() == 1);
  assert(clean.mappings.front().end - clean.mappings.front().begin ==
         704 * escrow::mib);

  // A later in-process runtime cannot claim any byte of the placeholder.
  assert(clean.reserve(held.layout.code + 64 * escrow::mib,
                       16 * escrow::mib) != 0);

  // Handoff restores the same exact hole for the Core's own allocator.
  const uint64_t original = held.layout.code;
  assert(escrow::release(held.layout, clean) == 0);
  assert(!held.layout);
  assert(clean.mappings.empty());
  assert(clean.reserve(original, 704 * escrow::mib) == 0);

  // Capacity falls back using the same 64 MiB steps as the embedded Core.
  for (const auto& [gap_size, expected_code] :
       std::vector<std::pair<uint64_t, uint64_t>>{
           {640 * escrow::mib, 384 * escrow::mib},
           {576 * escrow::mib, 320 * escrow::mib},
           {512 * escrow::mib, 256 * escrow::mib},
       }) {
    MockBackend backend;
    const auto result = escrow::reserve(
        {{escrow::low, escrow::low + gap_size}}, page, backend);
    assert(result.layout);
    assert(result.layout.code_bytes == expected_code);
  }

  // Split layouts are allowed only inside the Core's 4 GiB relative reach.
  MockBackend split;
  auto split_result = escrow::reserve(
      {{escrow::low, escrow::low + 448 * escrow::mib},
       {escrow::low + 768 * escrow::mib,
        escrow::low + 1024 * escrow::mib}},
      page, split);
  assert(split_result.layout);
  assert(!split_result.layout.contiguous);
  assert(escrow::valid(split_result.layout, page));
  assert(split.mappings.size() == 2);

  // If the second exact mapping loses a race, the first is always rolled back.
  MockBackend raced;
  raced.rejected_address = escrow::low + 768 * escrow::mib;
  auto rolled_back = escrow::reserve(
      {{escrow::low, escrow::low + 448 * escrow::mib},
       {escrow::low + 768 * escrow::mib,
        escrow::low + 1024 * escrow::mib}},
      page, raced);
  assert(!rolled_back.layout);
  assert(raced.mappings.empty());
  assert(raced.release_count > 0);

  // A failed handoff preserves the remaining ownership instead of pretending
  // that the Core received a complete address-space pair.
  MockBackend release_failure;
  auto not_released = escrow::reserve(
      {{escrow::low, escrow::low + 704 * escrow::mib}}, page,
      release_failure);
  assert(not_released.layout);
  release_failure.failed_release_address = not_released.layout.code;
  assert(escrow::release(not_released.layout, release_failure) != 0);
  assert(not_released.layout);

  // NEOSTATION_JIT_HIGH_WINDOW_904: the IPA 674 layout on iOS 27 beta. The low window holds 538 MiB in pieces
  // (largest 260 MiB, the rest below the 256 MiB minimum), and a 64 GiB gap is free at 448 GiB, below the task
  // maximum of 512 GiB.
  constexpr uint64_t high_gap = 0x7000000000ull;
  constexpr uint64_t task_max = 0x8000000000ull;
  const std::vector<escrow::Range> ios27 = {
      {escrow::low + 64 * escrow::mib, escrow::low + 324 * escrow::mib},
      {escrow::low + 1024 * escrow::mib, escrow::low + 1224 * escrow::mib},
      {escrow::low + 1536 * escrow::mib, escrow::low + 1614 * escrow::mib},
      {high_gap, task_max}};
  // Limited to the preferred 64 GiB window, nothing fits (the escrow failure of IPA 674).
  MockBackend low_only;
  assert(!escrow::reserve(ios27, page, low_only).layout);
  assert(low_only.mappings.empty());
  // With the task-wide limit, the full 448 + 256 MiB layout is held in the high gap.
  MockBackend wide;
  const auto high_layout = escrow::reserve(ios27, page, wide, task_max);
  assert(high_layout.layout);
  assert(high_layout.layout.contiguous);
  assert(high_layout.layout.code == high_gap);
  assert(high_layout.layout.code_bytes == 448 * escrow::mib);
  assert(escrow::valid(high_layout.layout, page, task_max));
  assert(!escrow::valid(high_layout.layout, page));
  // A low gap that fits is still preferred over the high window for the same capacity.
  MockBackend prefer_low;
  const auto low_layout = escrow::reserve(
      {{escrow::low, escrow::low + clean_gap}, {high_gap, task_max}}, page, prefer_low, task_max);
  assert(low_layout.layout && low_layout.layout.code == escrow::low);
  // A limit below the preferred window is refused.
  MockBackend bad_limit;
  assert(!escrow::reserve(ios27, page, bad_limit, escrow::high - 1).layout);

  std::cout << "PASS: early RPCS3 address-space escrow policy\n";
}
