// REWINDBOX_GUEST_ACCESS_FP_LR_636: the real instruction handling of Utilities/Thread.cpp (a64_block.inc,
// extracted by test/rpcs3_core636_test.py: decode_a64_mem_inst, put_a64_reg_value, ios_prepare_guest_access,
// ios_complete_guest_access) on the Darwin register layout. Darwin's thread state holds X0-X28 in __x[29];
// X29 (FP) and X30 (LR) are separate fields. On Apple ARM64 the real context structures are used; elsewhere a
// structure of the same layout, so a build with -fsanitize=bounds reports GPR(context, 29/30) as an index past
// __x (the Core 630 fixture's 32-slot register file hid it). Every access that names X29 or X30 as base, index or
// data register, scalar or pair, must keep the retry (t_access.size == 0) without reading or writing those
// registers through __x; the controls on X9 must still be completed.
#include "ios/IOSGuestAccessEmulation.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <initializer_list>
#include <type_traits>

#if defined(__APPLE__) && defined(__aarch64__)
#define RPCS3_TEST_DARWIN 1
#include <sys/ucontext.h>
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

#ifndef RPCS3_TEST_DARWIN
// The layout of Darwin's __darwin_arm_thread_state64 (non-opaque) inside __darwin_mcontext64.
struct fake_thread_state
{
	u64 __x[29];
	u64 __fp;
	u64 __lr;
	u64 __sp;
	u64 __pc;
	u32 __cpsr;
	u32 __pad;
};
struct fake_exception_state
{
	u64 __far;
	u32 __esr;
	u32 __exception;
};
struct fake_mcontext
{
	fake_exception_state __es;
	fake_thread_state __ss;
};
struct fake_ucontext
{
	fake_mcontext* uc_mcontext;
};
#define ucontext_t fake_ucontext
#endif

#define RIP(context) ((context)->uc_mcontext->__ss.__pc)
#define GPR(context, index) ((context)->uc_mcontext->__ss.__x[(index)])

#include "a64_block.inc"

namespace ga = rpcs3::ios::guest_access;

struct test_context
{
#ifdef RPCS3_TEST_DARWIN
	__darwin_mcontext64 machine{};
#else
	fake_mcontext machine{};
#endif
	ucontext_t value{};
	test_context() { value.uc_mcontext = &machine; }
	ucontext_t* get() { return &value; }
};

// Every register by its own field, never through GPR() past X28.
static void set_register(ucontext_t* context, u32 reg, u64 value)
{
	auto& state = context->uc_mcontext->__ss;
	if (reg < 29) state.__x[reg] = value;
	else if (reg == 29) state.__fp = value;
	else if (reg == 30) state.__lr = value;
	else state.__sp = value;
}

static u64 get_register(ucontext_t* context, u32 reg)
{
	const auto& state = context->uc_mcontext->__ss;
	return reg < 29 ? state.__x[reg] : reg == 29 ? state.__fp : reg == 30 ? state.__lr : state.__sp;
}

struct fp_lr_case { u32 inst; bool is_writing; const char* text; };

// Encodings from the LLVM assembler (llvm-mc -triple=aarch64-linux-gnu -show-encoding).
static const fp_lr_case refused[] =
{
	{0xf94003a8, false, "ldr x8, [x29]"}, {0xf94003c8, false, "ldr x8, [x30]"}, {0xb94003a8, false, "ldr w8, [x29]"},
	{0xf940013d, false, "ldr x29, [x9]"}, {0xf940013e, false, "ldr x30, [x9]"},
	{0xf900013d, true, "str x29, [x9]"}, {0xf900013e, true, "str x30, [x9]"},
	{0xf87d6928, false, "ldr x8, [x9, x29]"}, {0xf87e6928, false, "ldr x8, [x9, x30]"},
	{0xa940793d, false, "ldp x29, x30, [x9]"}, {0xa9407528, false, "ldp x8, x29, [x9]"}, {0xa94027a8, false, "ldp x8, x9, [x29]"},
	{0xa900793d, true, "stp x29, x30, [x9]"}, {0xa90027c8, true, "stp x8, x9, [x30]"},
};

static const fp_lr_case accepted[] =
{
	{0xf9400128, false, "ldr x8, [x9]"}, {0xa9402d28, false, "ldp x8, x11, [x9]"},
};

int main()
{
	alignas(16) static u8 guest[0x100];
	alignas(16) static u8 sudo[0x100];
	vm::g_base_addr = guest;
	vm::g_sudo_addr = sudo;
	const u32 addr = 0x40;
	const u64 fault = reinterpret_cast<u64>(vm::base(addr));
	int refusals = 0, completions = 0;

	for (const auto& test : refused)
	{
		u32 code[2] = {test.inst, 0};
		test_context holder;
		const auto context = holder.get();
		RIP(context) = reinterpret_cast<u64>(code);
		// Every candidate base or index register would address the fault: only the register check refuses.
		for (u32 reg : {8u, 9u, 29u, 30u}) set_register(context, reg, fault);
		const u64 fp = get_register(context, 29), lr = get_register(context, 30);
		ios_prepare_guest_access(addr, test.is_writing, context);
		CHECK(ga::t_access.size == 0);
		if (ga::t_access.size) std::printf("  accepted: %s\n", test.text);
		else refusals++;
		CHECK(get_register(context, 29) == fp && get_register(context, 30) == lr);
	}

	for (const auto& test : accepted)
	{
		u32 code[2] = {test.inst, 0};
		test_context holder;
		const auto context = holder.get();
		RIP(context) = reinterpret_cast<u64>(code);
		set_register(context, 9, fault);
		set_register(context, 29, 0x2929292929292929ull);
		set_register(context, 30, 0x3030303030303030ull);
		for (u32 i = 0; i < 16; i++) sudo[addr + i] = static_cast<u8>(0x41 + i);
		ios_prepare_guest_access(addr, test.is_writing, context);
		CHECK(ga::t_access.size == (test.inst == 0xa9402d28 ? 16u : 8u));
		if (ga::t_access.size)
		{
			ios_complete_guest_access(addr, context);
			u64 expected = 0;
			std::memcpy(&expected, sudo + addr, 8);
			CHECK(get_register(context, 8) == expected);
			CHECK(get_register(context, 29) == 0x2929292929292929ull && get_register(context, 30) == 0x3030303030303030ull);
			CHECK(RIP(context) == reinterpret_cast<u64>(code) + 4);
			completions++;
		}
	}

	std::printf("{\"failures\": %d, \"refused\": %d, \"completed\": %d}\n", failures, refusals, completions);
	return failures != 0;
}
