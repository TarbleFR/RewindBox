// SPDX-License-Identifier: MIT
#pragma once
#include <array>
#include <atomic>
#include <cstdint>
namespace rpcs3::ios::diagnostics {
class WriterCounters final {
public:
 static constexpr uint32_t sources=5, shard_count=64;
 struct Total {uint64_t count=0,acquire=0,hold=0,maximum=0;};
 void record(uint32_t source,uint64_t acquire,uint64_t hold) noexcept {
  auto& entry=shards_[thread_slot()].source[source<sources?source:0];
  entry.count.fetch_add(1,std::memory_order_relaxed);
  entry.acquire.fetch_add(acquire,std::memory_order_relaxed);
  entry.hold.fetch_add(hold,std::memory_order_relaxed);
  auto maximum=entry.maximum.load(std::memory_order_relaxed);
  while(maximum<hold&&!entry.maximum.compare_exchange_weak(maximum,hold,std::memory_order_relaxed)){}
 }
 std::array<Total,sources> drain() noexcept {
  std::array<Total,sources> result{};
  for(auto& shard:shards_)for(uint32_t i=0;i<sources;++i){
   auto& entry=shard.source[i];auto& total=result[i];
   total.count+=entry.count.exchange(0,std::memory_order_relaxed);
   total.acquire+=entry.acquire.exchange(0,std::memory_order_relaxed);
   total.hold+=entry.hold.exchange(0,std::memory_order_relaxed);
   const auto maximum=entry.maximum.exchange(0,std::memory_order_relaxed);
   if(maximum>total.maximum)total.maximum=maximum;
  }
  return result;
 }
private:
 struct Entry {std::atomic<uint64_t> count{0},acquire{0},hold{0},maximum{0};};
 struct alignas(128) Shard {std::array<Entry,sources> source{};};
 static uint32_t thread_slot() noexcept {
  static std::atomic<uint32_t> next{0};
  // Only the first event on a thread registers. Slots contain no thread
  // pointers and need no retirement; collisions retain exact atomic counters.
  static thread_local const uint32_t slot=next.fetch_add(1,std::memory_order_relaxed)%shard_count;
  return slot;
 }
 std::array<Shard,shard_count> shards_{};
};
}
