#pragma once

#include "Rpcs3EarlyAddressSpaceEscrowPolicy.h"

#include <mach/mach.h>
#include <mach/vm_map.h>
#include <mach/vm_statistics.h>
#include <unistd.h>

#include <algorithm>
#include <cstddef>
#include <sstream>
#include <string>
#include <vector>

namespace neostation::rpcs3::early_escrow {

struct DarwinBackend {
  int protection_error = 0;
  int cleanup_error = 0;

  bool cleanup_failed() const { return cleanup_error != 0; }

  int reserve(uint64_t address, uint64_t bytes) {
    vm_address_t actual = static_cast<vm_address_t>(address);
    int error = ::vm_allocate(
        mach_task_self(), &actual, static_cast<vm_size_t>(bytes),
        VM_FLAGS_FIXED | VM_MAKE_TAG(VM_MEMORY_APPLICATION_SPECIFIC_1));
    if (error) return error;
    if (actual != address) {
      cleanup_error = release(actual, bytes);
      return KERN_INVALID_ADDRESS;
    }
    error = ::vm_protect(mach_task_self(), actual,
                         static_cast<vm_size_t>(bytes), false, VM_PROT_NONE);
    if (error) {
      protection_error = error;
      cleanup_error = release(actual, bytes);
    }
    return error;
  }

  int release(uint64_t address, uint64_t bytes) {
    const int error = ::vm_deallocate(mach_task_self(),
                                      static_cast<vm_address_t>(address),
                                      static_cast<vm_size_t>(bytes));
    if (error) cleanup_error = error;
    return error;
  }
};

struct MapSnapshot {
  std::vector<Range> gaps;
  uint64_t largest_gap = 0;
  uint64_t total_free = 0;
  size_t regions = 0;
  int kernel = 0;
};

inline MapSnapshot snapshot() {
  MapSnapshot map;
  uint64_t cursor = low;
  while (cursor < high && map.regions < 32768) {
    vm_address_t address = static_cast<vm_address_t>(cursor);
    vm_size_t size = 0;
    vm_region_basic_info_data_64_t info = {};
    mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
    mach_port_t object = MACH_PORT_NULL;
    const int error = ::vm_region_64(
        mach_task_self(), &address, &size, VM_REGION_BASIC_INFO_64,
        reinterpret_cast<vm_region_info_t>(&info), &count, &object);
    if (object != MACH_PORT_NULL) {
      ::mach_port_deallocate(mach_task_self(), object);
    }
    if (error != KERN_SUCCESS && error != KERN_INVALID_ADDRESS) {
      map.kernel = error;
      break;
    }

    const uint64_t gap_end =
        error == KERN_INVALID_ADDRESS
            ? high
            : std::min(high, static_cast<uint64_t>(address));
    if (gap_end > cursor) {
      map.gaps.push_back({cursor, gap_end});
      map.largest_gap = std::max(map.largest_gap, gap_end - cursor);
      map.total_free += gap_end - cursor;
    }
    if (error == KERN_INVALID_ADDRESS ||
        static_cast<uint64_t>(address) >= high) {
      break;
    }
    if (!size || static_cast<uint64_t>(address) + size <= cursor) {
      map.kernel = KERN_INVALID_ADDRESS;
      break;
    }
    cursor = static_cast<uint64_t>(address) + size;
    ++map.regions;
  }
  if (map.regions == 32768) map.kernel = KERN_RESOURCE_SHORTAGE;
  return map;
}

// NEOSTATION_VA_CENSUS_V1: one compact line describing who owns the address
// space when the escrow is taken (diagnostic only; no reservation decision
// reads it). The low window [low, high) holds the JIT arena; the task's
// maximum address and the gaps above `high` show whether a wider window is
// available. Tags are VM_MEMORY_* numbers (user_tag of each mapping).
inline std::string census() {
  uint64_t max_address = 0;
  uint64_t min_address = 0;
  {
    task_vm_info_data_t vm = {};
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (::task_info(mach_task_self(), TASK_VM_INFO,
                    reinterpret_cast<task_info_t>(&vm), &count) == KERN_SUCCESS &&
        count * sizeof(natural_t) >=
            offsetof(task_vm_info_data_t, max_address) + sizeof(vm.max_address)) {
      min_address = vm.min_address;
      max_address = vm.max_address;
    }
  }
  struct Tag {
    unsigned tag = 0;
    uint64_t bytes = 0;
    uint64_t regions = 0;
  };
  struct Region {
    uint64_t address = 0;
    uint64_t bytes = 0;
    unsigned tag = 0;
    int protection = 0;
  };
  std::vector<Tag> tags;
  std::vector<Region> top;
  std::vector<Range> gaps_above;
  uint64_t free_above = 0;
  uint64_t used_above = 0;
  uint64_t cursor = low;
  size_t regions = 0;
  int kernel = 0;
  while (regions < 32768) {
    vm_address_t address = static_cast<vm_address_t>(cursor);
    vm_size_t size = 0;
    vm_region_extended_info_data_t info = {};
    mach_msg_type_number_t count = VM_REGION_EXTENDED_INFO_COUNT;
    mach_port_t object = MACH_PORT_NULL;
    const int error = ::vm_region_64(
        mach_task_self(), &address, &size, VM_REGION_EXTENDED_INFO,
        reinterpret_cast<vm_region_info_t>(&info), &count, &object);
    if (object != MACH_PORT_NULL) {
      ::mach_port_deallocate(mach_task_self(), object);
    }
    const uint64_t begin = static_cast<uint64_t>(address);
    const uint64_t gap_end =
        error == KERN_SUCCESS ? begin
                              : (max_address > cursor ? max_address : cursor);
    const uint64_t above_begin = std::max(cursor, high);
    if (gap_end > above_begin) {
      gaps_above.push_back({above_begin, gap_end});
      free_above += gap_end - above_begin;
    }
    if (error != KERN_SUCCESS) {
      if (error != KERN_INVALID_ADDRESS) kernel = error;
      break;
    }
    if (!size || begin + size <= cursor) {
      kernel = KERN_INVALID_ADDRESS;
      break;
    }
    if (begin < high) {
      const uint64_t bytes = std::min<uint64_t>(begin + size, high) - begin;
      auto it = std::find_if(tags.begin(), tags.end(), [&](const Tag& t) {
        return t.tag == info.user_tag;
      });
      if (it == tags.end()) {
        tags.push_back({info.user_tag, 0, 0});
        it = tags.end() - 1;
      }
      it->bytes += bytes;
      ++it->regions;
      top.push_back({begin, bytes, info.user_tag, info.protection});
      std::sort(top.begin(), top.end(), [](const Region& a, const Region& b) {
        return a.bytes > b.bytes;
      });
      if (top.size() > 8) top.pop_back();
    }
    if (begin + size > high) {
      used_above += begin + size - std::max(begin, high);
    }
    cursor = begin + size;
    ++regions;
  }
  std::sort(tags.begin(), tags.end(),
            [](const Tag& a, const Tag& b) { return a.bytes > b.bytes; });
  std::sort(gaps_above.begin(), gaps_above.end(),
            [](const Range& a, const Range& b) {
              return a.end - a.begin > b.end - b.begin;
            });
  std::ostringstream out;
  out << "NEOSTATION_VA_CENSUS_V1 minAddress=0x" << std::hex << min_address
      << " maxAddress=0x" << max_address << std::dec << " kernel=" << kernel
      << " regions=" << regions << " windowTags=";
  for (size_t i = 0; i < tags.size() && i < 12; ++i) {
    out << (i ? "," : "") << tags[i].tag << ":" << tags[i].bytes / mib << "MiB/"
        << tags[i].regions;
  }
  out << " windowTop=";
  for (size_t i = 0; i < top.size(); ++i) {
    out << (i ? "," : "") << "0x" << std::hex << top[i].address << std::dec
        << ":" << top[i].bytes / mib << "MiB:t" << top[i].tag << ":p"
        << top[i].protection;
  }
  out << " aboveUsedMiB=" << used_above / mib
      << " aboveFreeMiB=" << free_above / mib << " aboveGaps=";
  for (size_t i = 0; i < gaps_above.size() && i < 6; ++i) {
    out << (i ? "," : "") << "0x" << std::hex << gaps_above[i].begin << std::dec
        << ":" << (gaps_above[i].end - gaps_above[i].begin) / mib << "MiB";
  }
  return out.str();
}

enum class EscrowState {
  empty,
  held,
  handed_off,
  failed,
  poisoned,
};

class EarlyAddressSpaceEscrow {
 public:
  EarlyAddressSpaceEscrow() = default;
  EarlyAddressSpaceEscrow(const EarlyAddressSpaceEscrow&) = delete;
  EarlyAddressSpaceEscrow& operator=(const EarlyAddressSpaceEscrow&) = delete;

  ~EarlyAddressSpaceEscrow() {
    if (state_ == EscrowState::held) {
      DarwinBackend backend;
      (void)early_escrow::release(layout_, backend);
    }
  }

  bool acquire() {
    if (state_ == EscrowState::held) return true;
    if (state_ != EscrowState::empty) return false;

    const MapSnapshot map = snapshot();
    DarwinBackend backend;
    ReservationResult result;
    if (!map.kernel) {
      result = early_escrow::reserve(
          map.gaps, static_cast<uint64_t>(::getpagesize()), backend);
    }
    layout_ = result.layout;
    if (layout_ && result.cleanup_ok && !backend.cleanup_error) {
      state_ = EscrowState::held;
    } else if (!result.cleanup_ok || backend.cleanup_error) {
      state_ = EscrowState::poisoned;
    } else {
      state_ = EscrowState::failed;
    }

    std::ostringstream out;
    out << marker << " status=" << status()
        << " codeBytes=" << layout_.code_bytes
        << " dataBytes=" << data_bytes << " codeAddress=0x" << std::hex
        << layout_.code << " dataAddress=0x" << layout_.data << std::dec
        << " contiguous=" << (layout_.contiguous ? 1 : 0)
        << " mapKernel=" << map.kernel
        << " reserveKernel=" << result.kernel
        << " protectKernel=" << backend.protection_error
        << " cleanupKernel=" << backend.cleanup_error
        << " attempts=" << result.attempts
        << " attemptedAddress=0x" << std::hex
        << result.attempted_address << std::dec
        << " attemptedBytes=" << result.attempted_bytes
        << " largestGapBytes=" << map.largest_gap
        << " totalFreeBytes=" << map.total_free
        << " regions=" << map.regions;
    // Diagnostic only, after the reservation decision: who owns the window.
    out << " " << census();
    detail_ = out.str();
    return state_ == EscrowState::held;
  }

  bool active() const { return state_ == EscrowState::held; }
  const char* status() const {
    switch (state_) {
      case EscrowState::empty:
        return "empty";
      case EscrowState::held:
        return "held";
      case EscrowState::handed_off:
        return "handed_off";
      case EscrowState::failed:
        return "failed";
      case EscrowState::poisoned:
        return "poisoned";
    }
    return "unknown";
  }
  const std::string& detail() const { return detail_; }

  // On success, this function performs no allocation after vm_deallocate.
  // The caller must enter rpcs3_ios_initialize as its very next operation.
  bool release_for_core() {
    if (state_ != EscrowState::held || !verify_owned()) return false;
    DarwinBackend backend;
    const int error = early_escrow::release(layout_, backend);
    if (error || backend.cleanup_error) {
      state_ = EscrowState::poisoned;
      return false;
    }
    state_ = EscrowState::handed_off;
    return true;
  }

 private:
  bool verify_owned() {
    const std::array<Range, 2> ranges = {
        Range{layout_.code, layout_.code + layout_.code_bytes},
        Range{layout_.data, layout_.data + data_bytes},
    };
    for (const Range range : ranges) {
      uint64_t cursor = range.begin;
      while (cursor < range.end) {
        vm_address_t address = static_cast<vm_address_t>(cursor);
        vm_size_t size = 0;
        vm_region_basic_info_data_64_t info = {};
        mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
        mach_port_t object = MACH_PORT_NULL;
        const int error = ::vm_region_64(
            mach_task_self(), &address, &size, VM_REGION_BASIC_INFO_64,
            reinterpret_cast<vm_region_info_t>(&info), &count, &object);
        if (object != MACH_PORT_NULL) {
          ::mach_port_deallocate(mach_task_self(), object);
        }
        if (error || address > cursor || !size ||
            static_cast<uint64_t>(address) + size <= cursor ||
            info.protection != VM_PROT_NONE) {
          state_ = EscrowState::poisoned;
          return false;
        }
        cursor = static_cast<uint64_t>(address) + size;
      }
    }
    return true;
  }

  Layout layout_;
  EscrowState state_ = EscrowState::empty;
  std::string detail_;
};

}  // namespace neostation::rpcs3::early_escrow
