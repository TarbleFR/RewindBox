// SPDX-License-Identifier: MIT
// Real LLVM MCJIT, production memory-manager bodies, real dual RW/RX aliases.
// The Core's ELF AArch64 Android triple is used on Apple ARM64, reserving x18.
#include "Utilities/JITPublicationQueue.h"
#include <llvm/ExecutionEngine/ExecutionEngine.h>
#include <llvm/ExecutionEngine/MCJIT.h>
#include <llvm/ExecutionEngine/RTDyldMemoryManager.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Module.h>
#include <llvm/Support/Error.h>
#include <llvm/Support/TargetSelect.h>
#include <llvm/TargetParser/Host.h>
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <functional>
#include <memory>
#include <stdexcept>
#include <string>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>
#ifdef __APPLE__
#include <libkern/OSCacheControl.h>
#include <mach/mach.h>
#include <mach/mach_vm.h>
#endif

using u8 = std::uint8_t;
using u64 = std::uint64_t;
using usz = std::size_t;
using uptr = std::uintptr_t;
using uint = unsigned;
static std::uint64_t checks = 0;
static void require(bool condition)
{
	++checks;
	if (!condition) { std::fprintf(stderr, "FAIL real LLVM check %llu\n", static_cast<unsigned long long>(checks)); std::abort(); }
}
template <typename T> T ensure(T value) { require(bool(value)); return value; }
namespace utils {
static std::uint64_t get_tsc() { return std::chrono::steady_clock::now().time_since_epoch().count(); }
}
namespace fmt {
template <typename... T> [[noreturn]] void throw_exception(const char* message, T&&...) { throw std::runtime_error(message); }
}
struct test_log {
template <typename... T> [[noreturn]] void fatal(const char* message, T&&...) { throw std::runtime_error(message); }
} jit_log;
static void maybe_log_ios_jit_arena_pressure(bool) {}
static u64 make_null_function(const std::string&) { return 0; }

struct mapping { void* target; void* local; std::size_t bytes; bool code; bool released = false; };
static std::vector<mapping> mappings;
static std::uint64_t flush_calls = 0, flush_bytes = 0, release_calls = 0;
namespace rpcs3::ios::jit {
static void* allocate(bool code, std::size_t bytes, unsigned alignment)
{
	const auto page = static_cast<std::size_t>(::sysconf(_SC_PAGESIZE));
	require(alignment <= page);
	const auto size = (std::max<std::size_t>(bytes, 1) + page - 1) / page * page;
	if (!code)
	{
		void* ptr = ::mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
		require(ptr != MAP_FAILED);
		mappings.push_back({ptr, ptr, size, false});
		return ptr;
	}
#ifdef __APPLE__
	// Anonymous source plus shared Mach alias avoids executable unsigned file
	// mappings on Apple Silicon and follows the Core's split-view design.
	void* local = ::mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	require(local != MAP_FAILED);
	mach_vm_address_t target_address = 0;
	vm_prot_t current_protection = 0, maximum_protection = 0;
	require(::mach_vm_remap(mach_task_self(), &target_address, size, 0,
		VM_FLAGS_ANYWHERE, mach_task_self(), reinterpret_cast<mach_vm_address_t>(local), false,
		&current_protection, &maximum_protection, VM_INHERIT_NONE) == KERN_SUCCESS);
	void* target = reinterpret_cast<void*>(target_address);
	require(::mprotect(target, size, PROT_READ | PROT_EXEC) == 0);
#else
	char path[] = "/tmp/rpcs3-publication527-XXXXXX";
	const int fd = ::mkstemp(path);
	require(fd >= 0);
	::unlink(path);
	require(::ftruncate(fd, size) == 0);
	void* local = ::mmap(nullptr, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0);
	void* target = ::mmap(nullptr, size, PROT_READ | PROT_EXEC, MAP_SHARED, fd, 0);
	::close(fd);
#endif
	require(local != MAP_FAILED && target != MAP_FAILED && local != target);
	mappings.push_back({target, local, size, true});
	return target;
}
static void* writable(const void* address, std::size_t size)
{
	for (auto& item : mappings)
	{
		const auto offset = reinterpret_cast<std::uintptr_t>(address) - reinterpret_cast<std::uintptr_t>(item.target);
		if (item.code && offset <= item.bytes && size <= item.bytes - offset)
			return static_cast<u8*>(item.local) + offset;
	}
	return nullptr;
}
static const char* last_error() { return "test allocation failed"; }
static void flush(const void* address, std::size_t size)
{
	void* local = ensure(writable(address, size));
	++flush_calls; flush_bytes += size;
#ifdef __APPLE__
	::sys_dcache_flush(local, size);
	::sys_icache_invalidate(const_cast<void*>(address), size);
#else
	__builtin___clear_cache(static_cast<char*>(local), static_cast<char*>(local) + size);
	__builtin___clear_cache(static_cast<char*>(const_cast<void*>(address)), static_cast<char*>(const_cast<void*>(address)) + size);
#endif
}
static void release_allocation(bool code, const void* target, std::size_t size)
{
	for (auto& item : mappings)
		if (item.target == target && item.code == code && size <= item.bytes)
		{
			require(!item.released); item.released = true; ++release_calls; return;
		}
	require(false);
}
}
namespace jit_runtime {
static u8* alloc(std::size_t size, unsigned align, bool code)
{
	return static_cast<u8*>(rpcs3::ios::jit::allocate(code, size, align));
}
}

#define RPCS3_IOS 1
#include "ReferenceMemoryManagers.inc"
#include "CurrentMemoryManagers.inc"

static void clear_mappings()
{
	for (auto& item : mappings)
	{
		if (item.local != item.target) require(::munmap(item.local, item.bytes) == 0);
		require(::munmap(item.target, item.bytes) == 0);
	}
	mappings.clear();
}
static void protect_published_aliases()
{
	// Subsequent objects may refer to old symbols, but must never relocate or
	// emit a stub into an already successfully finalized code section.
	for (const auto& item : mappings)
		if (item.code) require(::mprotect(item.local, item.bytes, PROT_READ) == 0);
}
extern "C" __attribute__((noinline)) std::uint64_t jit527_helper(std::uint64_t x) { return x * 3 + 7; }
static std::string target_triple()
{
#if defined(__aarch64__) || defined(__arm64__)
	return "aarch64-unknown-linux-android";
#else
	return "x86_64-unknown-linux-gnu";
#endif
}

static std::unique_ptr<llvm::Module> module(llvm::LLVMContext& context, const std::string& name,
	const std::string& callee, std::uint64_t increment)
{
	auto result = std::make_unique<llvm::Module>(name, context);
	result->setTargetTriple(llvm::Triple(target_triple()));
	auto* type = llvm::Type::getInt64Ty(context);
	auto* signature = llvm::FunctionType::get(type, {type}, false);
	auto* function = llvm::Function::Create(signature, llvm::GlobalValue::ExternalLinkage, name, *result);
	llvm::IRBuilder<> ir(llvm::BasicBlock::Create(context, "entry", function));
	llvm::Value* value = function->getArg(0);
	if (!callee.empty()) value = ir.CreateCall(result->getOrInsertFunction(callee, signature), {value});
	ir.CreateRet(ir.CreateAdd(value, llvm::ConstantInt::get(type, increment)));
	return result;
}

template <typename Manager>
static std::unique_ptr<llvm::ExecutionEngine> engine(llvm::LLVMContext& context, Manager** output = nullptr)
{
	auto owner = std::make_unique<Manager>([](const std::string& name) -> u64 {
		return name.find("jit527_helper") != std::string::npos ? reinterpret_cast<u64>(&jit527_helper) : 0;
	});
	if (output) *output = owner.get();
	auto initial = std::make_unique<llvm::Module>("empty", context);
	initial->setTargetTriple(llvm::Triple(target_triple()));
	std::string error;
	auto* result = llvm::EngineBuilder(std::move(initial)).setErrorStr(&error)
		.setEngineKind(llvm::EngineKind::JIT).setMCJITMemoryManager(std::move(owner))
		.setOptLevel(llvm::CodeGenOptLevel::Aggressive).setRelocationModel(llvm::Reloc::PIC_)
		.setCodeModel(llvm::CodeModel::Small).create();
	if (!result) { std::fprintf(stderr, "%s\n", error.c_str()); std::abort(); }
	return std::unique_ptr<llvm::ExecutionEngine>(result);
}

template <typename Manager> static void lifecycle(const char* label, bool owner, bool incremental)
{
	const auto before_release = release_calls;
	const auto before_flush = flush_calls;
	{
		llvm::LLVMContext context;
		auto compiler = engine<Manager>(context);
		for (unsigned index = 0; index < 40; ++index)
		{
			const std::string name = "jit527_function_" + std::to_string(index);
			compiler->addModule(module(context, name, "jit527_helper", index));
			auto address = compiler->getGlobalValueAddress(name);
			require(address && !compiler->hasError());
			auto function = reinterpret_cast<std::uint64_t(*)(std::uint64_t)>(address);
			require(function(index) == index * 3 + 7 + index);
			protect_published_aliases();
			const auto after_publish = flush_calls;
			for (unsigned retry = 0; retry < 4; ++retry)
			{
				require(compiler->getGlobalValueAddress(name) == address);
				compiler->finalizeObject();
				require(function(index + retry) == (index + retry) * 3 + 7 + index);
			}
			if (incremental) require(flush_calls == after_publish);
		}
		// Forward symbol triggers nested module emission while resolving the
		// caller's relocations. Both newly allocated code sections must flush.
		compiler->addModule(module(context, "jit527_forward_caller", "jit527_forward_target", 11));
		compiler->addModule(module(context, "jit527_forward_target", "jit527_helper", 19));
		const auto forward = compiler->getGlobalValueAddress("jit527_forward_caller");
		require(forward && !compiler->hasError());
		require(reinterpret_cast<std::uint64_t(*)(std::uint64_t)>(forward)(5) == 5 * 3 + 7 + 19 + 11);
		protect_published_aliases();
		// A newly compiled function may call an already published one. The old
		// target does not change and its code need not be flushed again.
		compiler->addModule(module(context, "jit527_old_target_caller", "jit527_function_0", 23));
		const auto old = compiler->getGlobalValueAddress("jit527_old_target_caller");
		require(old && !compiler->hasError());
		require(reinterpret_cast<std::uint64_t(*)(std::uint64_t)>(old)(5) == 5 * 3 + 7 + 23);
	}
	std::uint64_t code_allocations = 0, data_allocations = 0;
	for (const auto& item : mappings) { code_allocations += item.code; data_allocations += !item.code; }
	if (owner) require(release_calls - before_release == code_allocations + data_allocations);
	else require(release_calls == before_release);
	std::printf("LLVM lifecycle %s: code=%llu flushes=%llu\n", label,
		static_cast<unsigned long long>(code_allocations), static_cast<unsigned long long>(flush_calls - before_flush));
	clear_mappings();
}

template <typename Base> struct failing_manager : Base
{
	using Base::Base;
	bool fail_lookup = true;
	llvm::JITSymbol findSymbol(const std::string& name) override
	{
		if (name.find("jit527_late_helper") != std::string::npos)
		{
			if (fail_lookup) return llvm::make_error<llvm::StringError>("expected recoverable resolver failure", llvm::inconvertibleErrorCode());
			return {reinterpret_cast<u64>(&jit527_helper), llvm::JITSymbolFlags::Exported};
		}
		return Base::findSymbol(name);
	}
};

template <typename Base> static void resolver_failure()
{
	{
		llvm::LLVMContext context;
		failing_manager<Base>* manager = nullptr;
		auto compiler = engine(context, &manager);
		compiler->addModule(module(context, "jit527_error_caller", "jit527_late_helper", 31));
		const auto address = compiler->getGlobalValueAddress("jit527_error_caller");
		require(address && compiler->hasError());
		const auto before_retry = flush_calls;
		manager->fail_lookup = false;
		compiler->clearErrorMessage();
		compiler->finalizeObject();
		require(flush_calls > before_retry);
		require(reinterpret_cast<std::uint64_t(*)(std::uint64_t)>(address)(13) == 13 * 3 + 7 + 31);
		// RuntimeDyld retains its error flag; conservative full dirty suffix
		// remains covered instead of trusting a cleared Engine error string.
		require(compiler->hasError());
	}
	clear_mappings();
}

struct timing { std::uint64_t nanoseconds{}, flushes{}, bytes{}; };
template <typename Manager> static timing warm_lookup(unsigned modules)
{
	timing result;
	{
		llvm::LLVMContext context;
		auto compiler = engine<Manager>(context);
		for (unsigned index = 0; index < modules; ++index)
		{
			const auto name = "jit527_bench_" + std::to_string(index);
			compiler->addModule(module(context, name, {}, index));
			require(compiler->getGlobalValueAddress(name));
		}
		const auto begin_flush = flush_calls, begin_bytes = flush_bytes;
		const auto begin = std::chrono::steady_clock::now();
		for (unsigned repeat = 0; repeat < 1000; ++repeat)
			require(compiler->getGlobalValueAddress("jit527_bench_0"));
		result.nanoseconds = std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - begin).count();
		result.flushes = flush_calls - begin_flush;
		result.bytes = flush_bytes - begin_bytes;
	}
	clear_mappings();
	return result;
}

struct append_timing { std::uint64_t total_ns{}, max_ns{}, flushes{}, bytes{}; };
template <typename Manager> static append_timing append_objects(unsigned modules)
{
	append_timing result;
	{
		llvm::LLVMContext context;
		auto compiler = engine<Manager>(context);
		compiler->finalizeObject();
		const auto begin_flush = flush_calls, begin_bytes = flush_bytes;
		for (unsigned index = 0; index < modules; ++index)
		{
			const auto name = "jit527_append_" + std::to_string(index);
			auto object = module(context, name, "jit527_helper", index);
			auto* fn = object->getFunction(name);
			auto* pointer = object.get();
			compiler->addModule(std::move(object));
			compiler->generateCodeForModule(pointer);
			const auto begin = std::chrono::steady_clock::now();
			compiler->finalizeObject();
			const auto elapsed = static_cast<std::uint64_t>(std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now() - begin).count());
			result.total_ns += elapsed;
			result.max_ns = std::max(result.max_ns, elapsed);
			auto execute = reinterpret_cast<std::uint64_t(*)(std::uint64_t)>(compiler->getPointerToFunction(fn));
			require(execute && !compiler->hasError() && execute(index) == index * 3 + 7 + index);
			protect_published_aliases();
		}
		result.flushes = flush_calls - begin_flush;
		result.bytes = flush_bytes - begin_bytes;
	}
	clear_mappings();
	return result;
}

int main()
{
	llvm::InitializeNativeTarget(); llvm::InitializeNativeTargetAsmPrinter(); llvm::InitializeNativeTargetAsmParser();
	for (unsigned session = 0; session < 3; ++session)
	{
		lifecycle<ReferenceMemoryManager1>("526-MM1", true, false);
		lifecycle<MemoryManager1>("527-MM1", true, true);
		lifecycle<ReferenceMemoryManager2>("526-MM2", false, false);
		lifecycle<MemoryManager2>("527-MM2", false, true);
	}
	resolver_failure<MemoryManager1>(); resolver_failure<MemoryManager2>();
	std::string benchmark_json;
	bool comma = false;
	for (unsigned modules : {8u, 32u, 128u})
	{
		std::vector<timing> before, after;
		for (unsigned round = 0; round < 7; ++round)
		{
			if (round % 2) { after.push_back(warm_lookup<MemoryManager2>(modules)); before.push_back(warm_lookup<ReferenceMemoryManager2>(modules)); }
			else { before.push_back(warm_lookup<ReferenceMemoryManager2>(modules)); after.push_back(warm_lookup<MemoryManager2>(modules)); }
		}
		require(after.back().flushes == 0 && before.back().flushes >= modules * 1000);
		auto median = [](const std::vector<timing>& values) { std::vector<std::uint64_t> ns; for (auto item : values) ns.push_back(item.nanoseconds); std::sort(ns.begin(), ns.end()); return ns[ns.size()/2]; };
		char row[512];
		std::snprintf(row, sizeof(row), "%s{\"loaded_modules\":%u,\"warm_lookups\":1000,\"before_ns\":%llu,\"after_ns\":%llu,\"before_flushes\":%llu,\"after_flushes\":%llu}", comma ? "," : "", modules,
			static_cast<unsigned long long>(median(before)), static_cast<unsigned long long>(median(after)),
			static_cast<unsigned long long>(before.back().flushes), static_cast<unsigned long long>(after.back().flushes));
		benchmark_json += row;
		comma = true;
	}
	std::string append_json;
	for (unsigned round = 0; round < 5; ++round)
	{
		append_timing before, after;
		if (round % 2) { after = append_objects<MemoryManager2>(128); before = append_objects<ReferenceMemoryManager2>(128); }
		else { before = append_objects<ReferenceMemoryManager2>(128); after = append_objects<MemoryManager2>(128); }
		require(before.flushes == 128 * 129 / 2 && after.flushes == 128);
		char row[640];
		std::snprintf(row, sizeof(row), "%s{\"round\":%u,\"modules\":128,\"before_finalize_ns\":%llu,\"after_finalize_ns\":%llu,\"before_max_ns\":%llu,\"after_max_ns\":%llu,\"before_flushes\":%llu,\"after_flushes\":%llu}", round ? "," : "", round,
			static_cast<unsigned long long>(before.total_ns), static_cast<unsigned long long>(after.total_ns),
			static_cast<unsigned long long>(before.max_ns), static_cast<unsigned long long>(after.max_ns),
			static_cast<unsigned long long>(before.flushes), static_cast<unsigned long long>(after.flushes));
		append_json += row;
	}
	std::printf("{\"passed\":true,\"triple\":\"%s\",\"checks\":%llu,\"physical_device\":false,\"benchmarks\":[%s],\"append_benchmarks\":[%s]}\n", target_triple().c_str(), static_cast<unsigned long long>(checks), benchmark_json.c_str(), append_json.c_str());
}
