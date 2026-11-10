#include <cassert>
#include <chrono>
#include <functional>
#include <iostream>
#include <utility>
#include <vector>
std::function<void()> before_payload;
// SPDX-License-Identifier: GPL-2.0-only


#include <array>
#include <atomic>
#include <cstddef>
#include <cstdint>

// CELL581_TEXTURE_PREHASH: on iOS the texture cache confirms CPU textures by
// content hash, not page protection. Under "Texture Validation Per FIFO Batch"
// (CELL559_TEXTURE_EPOCH) a texture is hashed again on its first use after
// each synchronization point (guest PUT, semaphore acquire, frame end), on the
// RSX thread. God of War III spends 2.8-10.4 ms of every frame there on build
// 575 (7-10 GB per 5 s window, 13-17 % of the frame) and its RSX thread limits
// the frame rate. A frame validates nearly the same textures in nearly the same
// order as the frame before it. As soon as an epoch starts, a worker thread
// therefore hashes the ranges the previous frame validated next, ahead of the
// RSX thread, with the same function (identical results).
//
// A result is used only in the epoch it was computed in; the worker reads the
// epoch before the bytes. Everything the commands of an epoch may read was
// written before the epoch began, so a hash taken after its start confirms the
// same data as the RSX thread's own hash would. A section revalidated by an RSX
// write inside the epoch (CELL573_SCOPED_RSX_WRITES) is hashed by the RSX
// thread itself. The worker reads RSX local memory, which is never unmapped
// while the RSX thread runs, and main memory only under a vm range lock (an
// unmap waits for it; a memory map change in progress makes it skip the range).
// Whatever the worker has not hashed is hashed by the RSX thread as before.
//
// CELL583_PREHASH_PACING (build 581 iPhone logs, God of War III: 56 % of the
// validations served, 48 % of the worker's bytes never used; Black Ops II, whose
// SPU threads use 3.4-4.1 cores while its RSX thread uses 0.1-0.5, served 20-28 %):
// the worker leaves out the ranges the RSX thread has already passed, the RSX thread
// wakes it halfway through its ranges instead of a 4 ms timeout, and Automatic is
// God of War III only.
namespace rpcs3::ios::texture_prehash
{
inline std::atomic<bool> enabled{false};

// Shorter ranges are left to the RSX thread.
constexpr std::uint32_t min_bytes = 64u << 10;
// Validations recorded per frame; the previous frame's list predicts the next.
constexpr std::size_t max_sequence = 2048;
// Recorded validations the worker hashes ahead of the RSX thread.
constexpr std::size_t lookahead = 64;
// Results kept (direct mapped, power of two).
constexpr std::size_t table_size = 4096;

struct result_slot
{
	// Even: stable; odd: being written. The worker and synchronous validators
	// share completed hashes; a contended publication is simply abandoned.
	std::atomic<std::uint64_t> seq{0};
	std::atomic<std::uint64_t> key{0};
	std::atomic<std::uint64_t> epoch{0};
	std::atomic<std::uint64_t> hash{0};
};

inline std::array<result_slot, table_size> table{};

// OPT581 profile counters (process window).
inline std::atomic<std::uint64_t> hits{0}, misses{0}, hit_bytes{0};
inline std::atomic<std::uint64_t> worker_hashes{0}, worker_bytes{0}, worker_ticks{0}, worker_skips{0};
// OPT583 profile counters (process window): ranges the RSX thread passed before the
// worker reached them (left unhashed), and wakes by the RSX thread's progress.
inline std::atomic<std::uint64_t> worker_passed{0}, worker_refills{0};

constexpr std::uint64_t make_key(std::uint32_t start, std::uint32_t length) noexcept
{
	return start | (std::uint64_t{length} << 32);
}

constexpr std::size_t slot_of(std::uint64_t key) noexcept
{
	return static_cast<std::size_t>((key * 0x9E3779B97F4A7C15ull) >> 52) & (table_size - 1);
}

// Any thread: a completed hash of [start, start + length) taken in `epoch`.
inline bool lookup(std::uint32_t start, std::uint32_t length, std::uint64_t epoch, std::uint64_t& out) noexcept
{
	const std::uint64_t key = make_key(start, length);
	const auto& slot = table[slot_of(key)];
	const std::uint64_t seq = slot.seq.load(std::memory_order_acquire);

	if (seq & 1)
	{
		return false;
	}

	// Acquire loads: a field the next writer stored brings its odd sequence with it.
	const std::uint64_t stored_key = slot.key.load(std::memory_order_acquire);
	const std::uint64_t stored_epoch = slot.epoch.load(std::memory_order_acquire);
	if (before_payload) { auto fn=std::move(before_payload); before_payload={}; fn(); }
	const std::uint64_t stored_hash = slot.hash.load(std::memory_order_acquire);

	if (slot.seq.load(std::memory_order_relaxed) != seq || stored_key != key || stored_epoch != epoch)
	{
		return false;
	}

	out = stored_hash;
	return true;
}

// Any producer. Try once: validation must never wait for speculative work.
inline void publish(std::uint32_t start, std::uint32_t length, std::uint64_t epoch, std::uint64_t hash) noexcept
{
	const std::uint64_t key = make_key(start, length);
	auto& slot = table[slot_of(key)];
	std::uint64_t seq = slot.seq.load(std::memory_order_relaxed);
	if ((seq & 1) || !slot.seq.compare_exchange_strong(seq, seq + 1,
		std::memory_order_acquire, std::memory_order_relaxed))
	{
		return;
	}
	// Release stores: whoever reads one of them also sees the odd sequence before it.
	slot.key.store(key, std::memory_order_release);
	slot.epoch.store(epoch, std::memory_order_release);
	slot.hash.store(hash, std::memory_order_release);
	slot.seq.store(seq + 2, std::memory_order_release);
}

// The texture cache's validation hash of guest memory at `src` (Emu/RSX/Common/texture_cache.cpp).
std::uint64_t range_hash(const void* src, std::uint32_t length) noexcept;

// A validation that hashed or looked up [start, start + length) (any thread).
// Keep ineligible validations in the sequence so its positions/epoch ordinals
// remain aligned, but do not predict worker work for a validation that had to
// bypass worker results after an RSX write. This only schedules speculation;
// it never changes whether a result may validate the current texture.
void record(std::uint32_t start, std::uint32_t length, bool eligible = true) noexcept;
// The texture cache's frame end, after the frame's epoch advance.
void end_frame() noexcept;
// Any thread that advanced the validation epoch.
void on_epoch_advance() noexcept;
// RSX thread exit: stops and joins the worker and turns the lever off until the next
// boot resolves it; the next boot's first record() starts a worker again.
void stop() noexcept;
}

namespace tp=rpcs3::ios::texture_prehash;
int main(int argc,char** argv) {
    constexpr std::uint32_t addr=0x10000,len=0x10000;
    std::uint64_t out=0;
    tp::publish(addr,len,10,111);
    assert(tp::lookup(addr,len,10,out) && out==111);
    before_payload=[&]{tp::publish(addr,len,11,222);};
    assert(!tp::lookup(addr,len,10,out));
    assert(tp::lookup(addr,len,11,out) && out==222);
    assert(!tp::lookup(addr,len+1,11,out));
    tp::table[tp::slot_of(tp::make_key(addr,len))].seq.fetch_add(1);
    assert(!tp::lookup(addr,len,11,out));
    tp::table[tp::slot_of(tp::make_key(addr,len))].seq.fetch_add(1);
    std::cout<<"{\"passed\":true,\"interleavedEpochRejected\":true,\"samples\":[";
    if(argc==2 && std::string_view(argv[1])=="--benchmark") {
        std::uint64_t sink=0;
        for(unsigned mode=0;mode<3;++mode) for(unsigned sample=0;sample<7;++sample) {
            auto start=std::chrono::steady_clock::now();
            for(unsigned i=0;i<2000000;++i) {
                auto epoch=std::uint64_t{mode==1?12u:11u};
                auto address=std::uint32_t{mode==2?addr+1:addr};
                asm volatile("" : "+r"(epoch),"+r"(address) : : "memory");
                sink+=tp::lookup(address,len,epoch,out)?out:1;
            }
            auto elapsed=std::chrono::duration<double,std::nano>(std::chrono::steady_clock::now()-start).count()/2000000;
            if(mode || sample) std::cout<<',';
            std::cout<<"{\"mode\":"<<mode<<",\"nanoseconds\":"<<elapsed<<'}';
        }
        std::cout<<"],\"sink\":"<<sink;
    } else std::cout<<']';
    std::cout<<"}\n";
}
