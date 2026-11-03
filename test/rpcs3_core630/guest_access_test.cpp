// REWINDBOX_ZCULL_ASYNC_READS_630: the real instruction handling of Utilities/Thread.cpp
// (a64_block.inc, extracted by test/rpcs3_core630_test.py: decode_a64_mem_inst, put_a64_reg_value,
// ios_prepare_guest_access, ios_complete_guest_access) on real AArch64 encodings. Everywhere, on a
// fake register file. On Apple ARM64, also in a real signal handler: a page without access, a
// second view of it, loads and stores that fault, the same context fields as on the iPhone.
#include "ios/IOSGuestAccessEmulation.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <type_traits>

#if defined(__APPLE__) && defined(__aarch64__)
#define RPCS3_TEST_REAL_FAULTS 1
#include <fcntl.h>
#include <signal.h>
#include <sys/mman.h>
#include <sys/ucontext.h>
#include <ucontext.h>
#include <unistd.h>
#endif

using u8 = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using u64 = std::uint64_t;
using s32 = std::int32_t;
using s64 = std::int64_t;

static int failures = 0;
#define CHECK(x) do { if (!(x)) { std::printf("check failed line %d: %s\n", __LINE__, #x); failures++; } } while (0)
#define ensure(x) do { if (!(x)) { std::printf("ensure failed line %d: %s\n", __LINE__, #x); std::abort(); } } while (0)

static constexpr u64 umax = ~u64{0};

template <typename T, typename P>
static T read_from_ptr_unsafe(P* pointer)
{
	T value;
	std::memcpy(&value, pointer, sizeof(T));
	return value;
}

namespace vm
{
	static u8* g_base_addr = nullptr;
	static u8* g_sudo_addr = nullptr;
	static void* base(u32 address) { return g_base_addr + address; }
}

#ifdef RPCS3_TEST_REAL_FAULTS
#define RIP(context) ((context)->uc_mcontext->__ss.__pc)
#define GPR(context, index) ((context)->uc_mcontext->__ss.__x[(index)])
#else
struct fake_context
{
	u64 x[32];
	u64 pc;
};
#define ucontext_t fake_context
#define RIP(context) ((context)->pc)
#define GPR(context, index) ((context)->x[(index)])
#endif

#include "a64_block.inc"

namespace ga = rpcs3::ios::guest_access;

struct refused_case { u32 inst; bool is_writing; const char* text; };

// Encodings from the LLVM assembler (clang --target=aarch64-linux-gnu -march=armv8.2-a+lse).
static const refused_case refused[] =
{
	{0x3dc00120, false, "ldr q0, [x9]"}, {0xfd400120, false, "ldr d0, [x9]"}, {0xbd400120, false, "ldr s0, [x9]"},
	{0xb8404528, false, "ldr w8, [x9], #4"}, {0xb8404d28, false, "ldr w8, [x9, #4]!"},
	{0x28c12d48, false, "ldp w8, w11, [x10], #8"}, {0x29c12d48, false, "ldp w8, w11, [x10, #8]!"},
	{0x88dffd28, false, "ldar w8, [x9]"}, {0x885f7d28, false, "ldxr w8, [x9]"}, {0xc85ffd28, false, "ldaxr x8, [x9]"},
	{0x880a7d28, true, "stxr w10, w8, [x9]"}, {0x889ffd28, true, "stlr w8, [x9]"}, {0x88e87d2a, true, "casa w8, w10, [x9]"},
	{0xf9800120, false, "prfm pldl1keep, [x9]"}, {0x4c407120, false, "ld1 {v0.16b}, [x9]"},
	{0xad400520, false, "ldp q0, q1, [x9]"}, {0x6d400520, false, "ldp d0, d1, [x9]"}, {0xad000520, true, "stp q0, q1, [x9]"},
	{0x91000528, false, "add x8, x9, #1"},
};

struct load_case { u32 inst; u32 size; u32 reg; u64 expected; const char* text; };

static void fake_run()
{
#ifndef RPCS3_TEST_REAL_FAULTS
	alignas(64) static u8 memory[0x8000];
	vm::g_sudo_addr = memory;
	vm::g_base_addr = reinterpret_cast<u8*>(std::uintptr_t{0x7000'0000'0000});
	const u32 addr = 0x4010;
	for (u32 i = 0; i < 32; i++) memory[addr + i] = static_cast<u8>(0x81 + i * 3); // top bit set: sign extension shows

	static const u8* bytes = memory + addr;
	const auto word = [](u32 offset) { u32 v; std::memcpy(&v, bytes + offset, 4); return v; };
	const auto dword = [](u32 offset) { u64 v; std::memcpy(&v, bytes + offset, 8); return v; };
	const auto half = [](u32 offset) { u16 v; std::memcpy(&v, bytes + offset, 2); return v; };

	// Every form at the fault address: the decoder takes the address from the fault, not from the operands.
	const load_case loads[] =
	{
		{0xb9400128, 4, 8, word(0), "ldr w8, [x9]"},
		{0xf9400528, 8, 8, dword(0), "ldr x8, [x9, #8]"},
		{0x39400d28, 1, 8, bytes[0], "ldrb w8, [x9, #3]"},
		{0x79400528, 2, 8, half(0), "ldrh w8, [x9, #2]"},
		{0xb9800528, 4, 8, static_cast<u64>(static_cast<s64>(static_cast<s32>(word(0)))), "ldrsw x8, [x9, #4]"},
		{0x39c00128, 1, 8, static_cast<u32>(static_cast<s32>(static_cast<std::int8_t>(bytes[0]))), "ldrsb w8, [x9]"},
		{0x39800128, 1, 8, static_cast<u64>(static_cast<s64>(static_cast<std::int8_t>(bytes[0]))), "ldrsb x8, [x9]"},
		{0x79c00128, 2, 8, static_cast<u32>(static_cast<s32>(static_cast<std::int16_t>(half(0)))), "ldrsh w8, [x9]"},
		{0x79800128, 2, 8, static_cast<u64>(static_cast<s64>(static_cast<std::int16_t>(half(0)))), "ldrsh x8, [x9]"},
		{0xb86a6928, 4, 8, word(0), "ldr w8, [x9, x10]"},
		{0xb86a4928, 4, 8, word(0), "ldr w8, [x9, w10, uxtw]"},
		{0xf86a7928, 8, 8, dword(0), "ldr x8, [x9, x10, lsl #3]"},
		{0x386a6928, 1, 8, bytes[0], "ldrb w8, [x9, x10]"},
		{0xb85fc128, 4, 8, word(0), "ldur w8, [x9, #-4]"},
		{0xf8401128, 8, 8, dword(0), "ldur x8, [x9, #1]"},
		{0xb89fc128, 4, 8, static_cast<u64>(static_cast<s64>(static_cast<s32>(word(0)))), "ldursw x8, [x9, #-4]"},
	};

	for (const auto& test : loads)
	{
		u32 code[2] = {test.inst, 0};
		fake_context context{};
		context.pc = reinterpret_cast<u64>(code);
		context.x[test.reg] = 0xdeadbeefdeadbeefull;
		ga::t_access = {};
		ga::t_access.emulate = true; // prepare starts from a clean record
		ios_prepare_guest_access(addr, false, &context);
		CHECK(ga::t_access.size == test.size && !ga::t_access.emulate);
		if (ga::t_access.size != test.size) std::printf("  %s\n", test.text);
		ios_complete_guest_access(addr, &context);
		CHECK(context.x[test.reg] == test.expected && context.pc == reinterpret_cast<u64>(code + 1));
		if (context.x[test.reg] != test.expected) std::printf("  %s %llx %llx\n", test.text, (unsigned long long)context.x[test.reg], (unsigned long long)test.expected);
	}

	{ // a load into the zero register reads nothing visible and steps over
		u32 code[2] = {0xb940013f, 0}; // ldr wzr, [x9]
		fake_context context{};
		context.pc = reinterpret_cast<u64>(code);
		ios_prepare_guest_access(addr, false, &context);
		CHECK(ga::t_access.size == 4);
		ios_complete_guest_access(addr, &context);
		CHECK(context.pc == reinterpret_cast<u64>(code + 1));
	}

	const auto run_store = [&](u32 inst, u32 size, u64 value, u32 reg, u64 expected)
	{
		std::memset(memory + addr, 0xee, 32);
		u32 code[2] = {inst, 0};
		fake_context context{};
		context.pc = reinterpret_cast<u64>(code);
		context.x[reg] = value;
		ios_prepare_guest_access(addr, true, &context);
		CHECK(ga::t_access.size == size);
		ios_complete_guest_access(addr, &context);
		u64 stored = 0;
		std::memcpy(&stored, memory + addr, size);
		CHECK(stored == expected && memory[addr + size] == 0xee && context.pc == reinterpret_cast<u64>(code + 1));
	};
	run_store(0xb9000128, 4, 0x1122334455667788ull, 8, 0x55667788u);        // str w8, [x9]
	run_store(0xf9000528, 8, 0x1122334455667788ull, 8, 0x1122334455667788ull); // str x8, [x9, #8]
	run_store(0x3900013f, 1, 0, 31, 0);                                      // strb wzr, [x9]
	run_store(0x79000528, 2, 0xabcd, 8, 0xabcd);                             // strh w8, [x9, #2]
	run_store(0xb81fc128, 4, 0x01020304, 8, 0x01020304);                     // stur w8, [x9, #-4]
	run_store(0xb82a693f, 4, 0, 31, 0);                                      // str wzr, [x9, x10]

	for (u32 i = 0; i < 32; i++) memory[addr + i] = static_cast<u8>(0x81 + i * 3);

	const auto pair = [&](u32 inst, bool is_writing, u32 rn, s64 offset, fake_context& context, u32* code)
	{
		code[0] = inst;
		context.pc = reinterpret_cast<u64>(code);
		context.x[rn] = reinterpret_cast<u64>(vm::base(addr)) - offset;
		ios_prepare_guest_access(addr, is_writing, &context);
	};

	{ // ldp w8, w11, [x10, #8]: two neighbouring guest words
		u32 code[2]; fake_context context{};
		pair(0x29412d48, false, 10, 8, context, code);
		CHECK(ga::t_access.size == 8);
		ios_complete_guest_access(addr, &context);
		CHECK(context.x[8] == word(0) && context.x[11] == word(4) && context.pc == reinterpret_cast<u64>(code + 1));
	}
	{ // ldp x8, x11, [x10, #16]
		u32 code[2]; fake_context context{};
		pair(0xa9412d48, false, 10, 16, context, code);
		CHECK(ga::t_access.size == 16);
		ios_complete_guest_access(addr, &context);
		CHECK(context.x[8] == dword(0) && context.x[11] == dword(8));
	}
	{ // ldpsw x8, x11, [x10]
		u32 code[2]; fake_context context{};
		pair(0x69402d48, false, 10, 0, context, code);
		CHECK(ga::t_access.size == 8);
		ios_complete_guest_access(addr, &context);
		CHECK(context.x[8] == static_cast<u64>(static_cast<s64>(static_cast<s32>(word(0)))) &&
		      context.x[11] == static_cast<u64>(static_cast<s64>(static_cast<s32>(word(4)))));
	}
	{ // ldp w8, wzr, [x10]
		u32 code[2]; fake_context context{};
		pair(0x29407d48, false, 10, 0, context, code);
		CHECK(ga::t_access.size == 8);
		ios_complete_guest_access(addr, &context);
		CHECK(context.x[8] == word(0) && context.x[31] == 0);
	}
	{ // stp w8, w11, [x10, #-8]
		u32 code[2]; fake_context context{};
		context.x[8] = 0x11111111; context.x[11] = 0x22222222;
		pair(0x293f2d48, true, 10, -8, context, code);
		CHECK(ga::t_access.size == 8);
		ios_complete_guest_access(addr, &context);
		CHECK(word(0) == 0x11111111 && word(4) == 0x22222222);
	}
	{ // stp x8, x11, [x10, #16]
		u32 code[2]; fake_context context{};
		context.x[8] = 0x3333333344444444ull; context.x[11] = 0x5555555566666666ull;
		pair(0xa9012d48, true, 10, 16, context, code);
		CHECK(ga::t_access.size == 16);
		ios_complete_guest_access(addr, &context);
		CHECK(dword(0) == 0x3333333344444444ull && dword(8) == 0x5555555566666666ull);
	}
	{ // stp xzr, xzr, [x10]
		u32 code[2]; fake_context context{};
		pair(0xa9007d5f, true, 10, 0, context, code);
		CHECK(ga::t_access.size == 16);
		ios_complete_guest_access(addr, &context);
		CHECK(dword(0) == 0 && dword(8) == 0);
	}
	{ // the fault is on the second register of a pair: no address match, it stays a retry
		u32 code[2]; fake_context context{};
		pair(0x29412d48, false, 10, 4, context, code); // the pair starts 4 bytes below the fault
		CHECK(ga::t_access.size == 0);
	}
	{ // a pair that would cross the page stays a retry
		u32 code[2] = {0xa9412d48, 0}; fake_context context{};
		const u32 last = 0x7ff8;
		context.pc = reinterpret_cast<u64>(code);
		context.x[10] = reinterpret_cast<u64>(vm::base(last)) - 16;
		ios_prepare_guest_access(last, false, &context);
		CHECK(ga::t_access.size == 0);
	}
	{ // the wrong direction and an unaligned access stay a retry
		u32 code[2] = {0xb9400128, 0}; fake_context context{};
		context.pc = reinterpret_cast<u64>(code);
		ios_prepare_guest_access(addr, true, &context);  // a load reported as a write
		CHECK(ga::t_access.size == 0);
		ios_prepare_guest_access(addr + 2, false, &context);
		CHECK(ga::t_access.size == 0);
		code[0] = 0xb9000128;
		ios_prepare_guest_access(addr, false, &context); // a store reported as a read
		CHECK(ga::t_access.size == 0);
	}
	for (const auto& test : refused)
	{
		u32 code[2] = {test.inst, 0};
		fake_context context{};
		context.pc = reinterpret_cast<u64>(code);
		ios_prepare_guest_access(addr, test.is_writing, &context);
		CHECK(ga::t_access.size == 0);
		if (ga::t_access.size) std::printf("  accepted: %s\n", test.text);
	}
#endif
}

#ifdef RPCS3_TEST_REAL_FAULTS
static volatile sig_atomic_t g_completed = 0, g_retried = 0;
static u8* g_locked = nullptr;
static constexpr std::size_t g_page = 0x4000;

static void on_fault(int, siginfo_t* info, void* uct)
{
	auto* context = static_cast<ucontext_t*>(uct);
	const auto at = reinterpret_cast<u8*>(info->si_addr);

	if (at < g_locked || at >= g_locked + g_page)
	{
		std::_Exit(3);
	}

	const u32 addr = static_cast<u32>(at - vm::g_base_addr);
	const bool is_writing = ((context->uc_mcontext->__es.__esr >> 6) & 1) != 0; // ISS.WnR
	ios_prepare_guest_access(addr, is_writing, context);

	if (ga::t_access.size)
	{
		ios_complete_guest_access(addr, context);
		g_completed = g_completed + 1;
	}
	else
	{
		mprotect(g_locked, g_page, PROT_READ | PROT_WRITE); // the instruction runs again
		g_retried = g_retried + 1;
	}
}

static void real_run()
{
	char name[] = "/tmp/core630XXXXXX";
	const int file = mkstemp(name);
	CHECK(file >= 0 && ftruncate(file, 2 * g_page) == 0);
	unlink(name);
	auto* locked = static_cast<u8*>(mmap(nullptr, 2 * g_page, PROT_READ | PROT_WRITE, MAP_SHARED, file, 0));
	auto* open = static_cast<u8*>(mmap(nullptr, 2 * g_page, PROT_READ | PROT_WRITE, MAP_SHARED, file, 0));
	CHECK(locked != MAP_FAILED && open != MAP_FAILED);
	vm::g_base_addr = locked;
	vm::g_sudo_addr = open;
	g_locked = locked;

	struct sigaction action{};
	action.sa_sigaction = on_fault;
	action.sa_flags = SA_SIGINFO;
	sigemptyset(&action.sa_mask);
	CHECK(sigaction(SIGBUS, &action, nullptr) == 0 && sigaction(SIGSEGV, &action, nullptr) == 0);

	const u32 addr = 0x10;
	for (u32 i = 0; i < 32; i++) open[addr + i] = static_cast<u8>(0x81 + i * 3);
	u8* const target = locked + addr;
	u32 w = 0; u64 x = 0, y = 0; s64 sx = 0;
	u32 expected32; u64 expected64;
	std::memcpy(&expected32, open + addr, 4);
	std::memcpy(&expected64, open + addr, 8);

	CHECK(mprotect(locked, g_page, PROT_NONE) == 0);

	__asm__ volatile("ldr %w0, [%1]" : "=&r"(w) : "r"(target) : "memory");
	CHECK(w == expected32 && g_completed == 1);
	__asm__ volatile("ldr %0, [%1]" : "=&r"(x) : "r"(target) : "memory");
	CHECK(x == expected64 && g_completed == 2);
	__asm__ volatile("ldrb %w0, [%1, #4]" : "=&r"(w) : "r"(target) : "memory");
	CHECK(w == open[addr + 4] && g_completed == 3);
	__asm__ volatile("ldrsw %0, [%1]" : "=&r"(sx) : "r"(target) : "memory");
	CHECK(sx == static_cast<s32>(expected32) && g_completed == 4);
	__asm__ volatile("ldur %w0, [%1, #-16]" : "=&r"(w) : "r"(target + 16) : "memory");
	CHECK(w == expected32 && g_completed == 5);
	__asm__ volatile("ldp %0, %1, [%2]" : "=&r"(x), "=&r"(y) : "r"(target) : "memory");
	CHECK(x == expected64 && g_completed == 6);
	std::memcpy(&expected64, open + addr + 8, 8);
	CHECK(y == expected64);

	const u32 value = 0x12345678;
	__asm__ volatile("str %w0, [%1]" : : "r"(value), "r"(target + 4) : "memory");
	CHECK(std::memcmp(open + addr + 4, &value, 4) == 0 && g_completed == 7);
	const u64 first = 0x0102030405060708ull, second = 0x1112131415161718ull;
	__asm__ volatile("stp %0, %1, [%2]" : : "r"(first), "r"(second), "r"(target) : "memory");
	CHECK(std::memcmp(open + addr, &first, 8) == 0 && std::memcmp(open + addr + 8, &second, 8) == 0 && g_completed == 8);

	// An instruction the handler leaves alone: the page opens and it runs again.
	CHECK(g_retried == 0);
	__asm__ volatile("ldar %w0, [%1]" : "=&r"(w) : "r"(target) : "memory");
	CHECK(g_retried == 1 && g_completed == 8);
	std::printf("{\"real_faults\": %d, \"real_retries\": %d}\n", static_cast<int>(g_completed), static_cast<int>(g_retried));
}
#endif

int main()
{
	fake_run();
#ifdef RPCS3_TEST_REAL_FAULTS
	real_run();
#endif
	CHECK(ga::decode_pair(0x29412d48).offset == 8 && ga::decode_pair(0x293f2d48).offset == -8 && ga::decode_pair(0xa9412d48).offset == 16);
	CHECK(ga::decode_pair(0x29400908).valid == true);   // ldp w8, w2, [x8]: the base may be a destination
	CHECK(ga::decode_pair(0x29402108).valid == false);  // ldp w8, w8, [x8]: unpredictable
	std::printf("{\"failures\": %d}\n", failures);
	return failures != 0;
}
