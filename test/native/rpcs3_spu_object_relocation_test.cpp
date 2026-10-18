// NEOSTATION_BUILD481_SPU_OBJECT_CACHE_V1 mechanism proof, executed on the macOS
// arm64 runner with the Homebrew LLVM 22 that also compiles the Core.
//
// The persistent SPU object cache relies on one property: every host reference
// of a compiled SPU module is a symbol (external global or function) that MCJIT
// resolves through the engine's global mapping when the object is linked, in
// whatever process links it. This program builds, with the SPU triple of the
// Core (aarch64-unknown-linux-android, PIC, small code model), a module shaped
// like an SPU block: an external data symbol read through the GOT (the timebase
// offset), an external helper called by symbol (spu_escape/spu_dispatch style),
// a private rodata table (frest/frsqest LUTs) and an internal function table of
// absolute pointers (m_function_table). It is used in separate processes:
//
//   save <dir>     compiles the module, writes the object, records the host
//                  addresses it linked against and the results it computed;
//   load <dir>     maps the symbols to DIFFERENT host addresses (a different
//                  static slot plus the ASLR slide of a new process), forbids
//                  code generation, links the cached object and checks the
//                  results against the new addresses;
//   corrupt <dir>  truncates the object, then checks that the same validation
//                  the Core performs (parse + required defined symbol) rejects
//                  it and that a normal compilation replaces it.
//
// It proves the loader mechanism, not iPhone behaviour: the Core's own memory
// manager, W^X handling and JIT arena are exercised only on the device.
#include <llvm/ExecutionEngine/ExecutionEngine.h>
#include <llvm/ExecutionEngine/MCJIT.h>
#include <llvm/ExecutionEngine/ObjectCache.h>
#include <llvm/ExecutionEngine/SectionMemoryManager.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/DerivedTypes.h>
#include <llvm/IR/Function.h>
#include <llvm/IR/GlobalVariable.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/Verifier.h>
#include <llvm/Object/ObjectFile.h>
#include <llvm/Support/Error.h>
#include <llvm/Support/MemoryBuffer.h>
#include <llvm/Support/TargetSelect.h>
#include <llvm/Support/raw_ostream.h>
#include <llvm/TargetParser/Host.h>
#include <llvm/TargetParser/Triple.h>

#include <cinttypes>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <memory>
#include <string>
#include <vector>

namespace
{
	constexpr const char* k_triple = "aarch64-unknown-linux-android"; // jit_compiler::triple2() on Apple ARM64
	constexpr const char* k_module = "__spu-0x00abc-reloctest.obj";
	constexpr const char* k_entry = "__spu-0x00abc-reloctest";
	constexpr const char* k_data_symbol = "spu_timebase_offs";
	constexpr const char* k_helper_symbol = "reloc_helper";

	std::uint64_t g_helper_calls = 0;

	extern "C" std::uint64_t reloc_helper(std::uint64_t value)
	{
		g_helper_calls++;
		return value * 3 + 7;
	}

	// The timebase stand-in. save and load use different slots, so the data
	// address differs even without an ASLR slide; with ASLR it differs twice.
	std::uint64_t g_cells[64]{};

	std::uint64_t expected(std::uint64_t x, std::uint64_t cell)
	{
		return cell + (x * 3 + 7) + (1000 + (x & 31)) + (x + 11);
	}

	// Mirrors jit_compiler::load_cached_object + ObjectCache::validate: the file
	// is parsed and the entry symbol must be defined before MCJIT sees it.
	bool validate(const llvm::MemoryBuffer& buffer, const char* required)
	{
		llvm::Expected<std::unique_ptr<llvm::object::ObjectFile>> object = llvm::object::ObjectFile::createObjectFile(buffer.getMemBufferRef());

		if (!object)
		{
			llvm::consumeError(object.takeError());
			return false;
		}

		for (const llvm::object::SymbolRef& symbol : (*object)->symbols())
		{
			llvm::Expected<llvm::StringRef> name = symbol.getName();

			if (!name)
			{
				llvm::consumeError(name.takeError());
				continue;
			}

			if (*name != llvm::StringRef(required))
			{
				continue;
			}

			llvm::Expected<std::uint32_t> flags = symbol.getFlags();

			if (!flags)
			{
				llvm::consumeError(flags.takeError());
				return false;
			}

			return !(*flags & llvm::object::SymbolRef::SF_Undefined);
		}

		return false;
	}

	struct file_cache final : llvm::ObjectCache
	{
		std::string dir;
		bool allow_compile;
		// Entry symbol of the module being compiled, like m_hash in the Core:
		// a cached file under this name must define it or it is a foreign object.
		const char* entry = k_entry;
		bool compiled = false;
		bool loaded = false;
		bool rejected = false;
		std::size_t bytes = 0;

		file_cache(std::string directory, bool allow)
			: dir(std::move(directory))
			, allow_compile(allow)
		{
		}

		std::string path(const llvm::Module* m) const
		{
			return dir + "/" + m->getName().str();
		}

		void notifyObjectCompiled(const llvm::Module* m, llvm::MemoryBufferRef obj) override
		{
			if (!allow_compile)
			{
				std::fprintf(stderr, "FAIL: code was generated although the cached object had to be linked\n");
				std::exit(3);
			}

			std::ofstream out(path(m), std::ios::binary | std::ios::trunc);
			out.write(obj.getBufferStart(), static_cast<std::streamsize>(obj.getBufferSize()));
			compiled = true;
			bytes = obj.getBufferSize();
		}

		std::unique_ptr<llvm::MemoryBuffer> getObject(const llvm::Module* m) override
		{
			llvm::ErrorOr<std::unique_ptr<llvm::MemoryBuffer>> buffer = llvm::MemoryBuffer::getFile(path(m));

			if (!buffer)
			{
				return nullptr;
			}

			if (!validate(**buffer, entry))
			{
				rejected = true;
				std::printf("validation rejected the cached object (%zu bytes); compiling instead\n", (*buffer)->getBufferSize());
				return nullptr;
			}

			loaded = true;
			bytes = (*buffer)->getBufferSize();
			return std::move(*buffer);
		}
	};

	std::unique_ptr<llvm::Module> build(llvm::LLVMContext& context, const char* entry_name)
	{
		auto m = std::make_unique<llvm::Module>(k_module, context);
		m->setTargetTriple(llvm::Triple(k_triple));

		llvm::IRBuilder<> ir(context);
		llvm::Type* i64 = ir.getInt64Ty();

		// External data symbol, read through the GOT: the timebase offset.
		llvm::Constant* cell = m->getOrInsertGlobal(k_data_symbol, i64);

		// External helper, called by symbol.
		llvm::FunctionType* helper_type = llvm::FunctionType::get(i64, {i64}, false);
		llvm::FunctionCallee helper = m->getOrInsertFunction(k_helper_symbol, helper_type);

		// Private rodata table, PC-relative.
		std::vector<llvm::Constant*> lut;
		for (int i = 0; i < 32; i++)
			lut.push_back(ir.getInt64(1000 + i));
		llvm::ArrayType* lut_type = llvm::ArrayType::get(i64, 32);
		auto* lut_global = new llvm::GlobalVariable(*m, lut_type, true, llvm::GlobalValue::PrivateLinkage, llvm::ConstantArray::get(lut_type, lut), "lut");

		// Internal chunk and a table of absolute pointers to it (m_function_table).
		llvm::FunctionType* fn_type = llvm::FunctionType::get(i64, {i64}, false);
		llvm::Function* chunk = llvm::Function::Create(fn_type, llvm::GlobalValue::InternalLinkage, "chunk", m.get());
		{
			llvm::BasicBlock* bb = llvm::BasicBlock::Create(context, "entry", chunk);
			ir.SetInsertPoint(bb);
			ir.CreateRet(ir.CreateAdd(chunk->getArg(0), ir.getInt64(11)));
		}
		llvm::ArrayType* table_type = llvm::ArrayType::get(ir.getPtrTy(), 2);
		auto* table = new llvm::GlobalVariable(*m, table_type, true, llvm::GlobalValue::PrivateLinkage, llvm::ConstantArray::get(table_type, {chunk, chunk}), "ftable");

		llvm::Function* entry = llvm::Function::Create(fn_type, llvm::GlobalValue::ExternalLinkage, entry_name, m.get());
		llvm::BasicBlock* bb = llvm::BasicBlock::Create(context, "entry", entry);
		ir.SetInsertPoint(bb);
		llvm::Value* x = entry->getArg(0);
		llvm::Value* timebase = ir.CreateLoad(i64, cell);
		llvm::Value* h = ir.CreateCall(helper, {x});
		llvm::Value* index = ir.CreateAnd(x, ir.getInt64(31));
		llvm::Value* lut_ptr = ir.CreateInBoundsGEP(lut_type, lut_global, {ir.getInt64(0), index});
		llvm::Value* lut_value = ir.CreateLoad(i64, lut_ptr);
		llvm::Value* slot = ir.CreateInBoundsGEP(table_type, table, {ir.getInt64(0), ir.CreateAnd(x, ir.getInt64(1))});
		llvm::Value* fp = ir.CreateLoad(ir.getPtrTy(), slot);
		llvm::Value* chunk_value = ir.CreateCall(fn_type, fp, {x});
		ir.CreateRet(ir.CreateAdd(ir.CreateAdd(ir.CreateAdd(timebase, h), lut_value), chunk_value));

		std::string error;
		llvm::raw_string_ostream stream(error);

		if (llvm::verifyModule(*m, &stream))
		{
			std::fprintf(stderr, "FAIL: module verification: %s\n", error.c_str());
			std::exit(4);
		}

		return m;
	}

	struct engine
	{
		std::unique_ptr<llvm::ExecutionEngine> ee;
		llvm::Module* module = nullptr;
	};

	engine create(std::unique_ptr<llvm::Module> module)
	{
		engine result;
		result.module = module.get();
		std::string error;
		std::string cpu = llvm::sys::getHostCPUName().str();

		if (cpu.empty() || cpu == "generic")
		{
			cpu = "cortex-a78";
		}

		result.ee.reset(llvm::EngineBuilder(std::move(module))
			.setErrorStr(&error)
			.setEngineKind(llvm::EngineKind::JIT)
			.setMCJITMemoryManager(std::make_unique<llvm::SectionMemoryManager>())
			.setOptLevel(llvm::CodeGenOptLevel::Aggressive)
			.setCodeModel(llvm::CodeModel::Small)
			.setRelocationModel(llvm::Reloc::PIC_)
			.setMCPU(cpu)
			.create());

		if (!result.ee)
		{
			std::fprintf(stderr, "FAIL: ExecutionEngine: %s\n", error.c_str());
			std::exit(5);
		}

		return result;
	}

	using entry_fn = std::uint64_t (*)(std::uint64_t);

	struct run_result
	{
		std::uint64_t cell_address;
		std::uint64_t helper_address;
		std::uint64_t code_address;
		std::uint64_t values[3];
	};

	run_result run(file_cache& cache, std::uint64_t* cell, std::uint64_t cell_value, const char* entry_name)
	{
		llvm::LLVMContext context;
		engine e = create(build(context, entry_name));
		cache.entry = entry_name;
		*cell = cell_value;
		e.ee->updateGlobalMapping(k_data_symbol, reinterpret_cast<std::uint64_t>(cell));
		e.ee->updateGlobalMapping(k_helper_symbol, reinterpret_cast<std::uint64_t>(&reloc_helper));
		e.ee->setObjectCache(&cache);
		e.ee->generateCodeForModule(e.module);
		e.ee->setObjectCache(nullptr);
		e.ee->finalizeObject();

		const entry_fn fn = reinterpret_cast<entry_fn>(e.ee->getFunctionAddress(entry_name));

		if (!fn)
		{
			std::fprintf(stderr, "FAIL: entry point not found after link\n");
			std::exit(6);
		}

		run_result result{};
		result.cell_address = reinterpret_cast<std::uint64_t>(cell);
		result.helper_address = reinterpret_cast<std::uint64_t>(&reloc_helper);
		result.code_address = reinterpret_cast<std::uint64_t>(fn);
		const std::uint64_t inputs[3] = {5, 40, 0x7777};
		g_helper_calls = 0;

		for (int i = 0; i < 3; i++)
		{
			result.values[i] = fn(inputs[i]);
			const std::uint64_t want = expected(inputs[i], cell_value);

			if (result.values[i] != want)
			{
				std::fprintf(stderr, "FAIL: fn(%" PRIu64 ") = %" PRIu64 ", expected %" PRIu64 " (cell at %#" PRIx64 ")\n", inputs[i], result.values[i], want, result.cell_address);
				std::exit(7);
			}
		}

		if (g_helper_calls != 3)
		{
			std::fprintf(stderr, "FAIL: helper called %" PRIu64 " times\n", g_helper_calls);
			std::exit(8);
		}

		return result;
	}

	std::string record_path(const std::string& dir)
	{
		return dir + "/save-record.txt";
	}
}

int main(int argc, char** argv)
{
	if (argc != 3)
	{
		std::fprintf(stderr, "usage: %s save|load|corrupt <dir>\n", argv[0]);
		return 2;
	}

	const std::string mode = argv[1];
	const std::string dir = argv[2];

	LLVMInitializeAArch64TargetInfo();
	LLVMInitializeAArch64Target();
	LLVMInitializeAArch64TargetMC();
	LLVMInitializeAArch64AsmPrinter();
	LLVMInitializeAArch64AsmParser();
	LLVMLinkInMCJIT();

	if (mode == "save")
	{
		file_cache cache(dir, true);
		const run_result result = run(cache, &g_cells[3], 0x1111222233334444ull, k_entry);

		if (!cache.compiled || cache.loaded)
		{
			std::fprintf(stderr, "FAIL: save must generate code (compiled=%d loaded=%d)\n", cache.compiled, cache.loaded);
			return 9;
		}

		std::ofstream record(record_path(dir));
		record << result.cell_address << ' ' << result.helper_address << ' ' << result.code_address << ' ' << cache.bytes << '\n';
		std::printf("saved %zu-byte object; cell=%#" PRIx64 " helper=%#" PRIx64 " code=%#" PRIx64 "\n", cache.bytes, result.cell_address, result.helper_address, result.code_address);
		return 0;
	}

	if (mode == "load")
	{
		std::uint64_t saved_cell = 0, saved_helper = 0, saved_code = 0;
		std::size_t saved_bytes = 0;
		std::ifstream record(record_path(dir));

		if (!(record >> saved_cell >> saved_helper >> saved_code >> saved_bytes))
		{
			std::fprintf(stderr, "FAIL: no save record in %s\n", dir.c_str());
			return 10;
		}

		file_cache cache(dir, false);
		const run_result result = run(cache, &g_cells[47], 0x5555666677778888ull, k_entry);

		if (!cache.loaded || cache.compiled)
		{
			std::fprintf(stderr, "FAIL: load must link the cached object (loaded=%d compiled=%d)\n", cache.loaded, cache.compiled);
			return 11;
		}

		if (cache.bytes != saved_bytes)
		{
			std::fprintf(stderr, "FAIL: object size changed (%zu vs %zu)\n", cache.bytes, saved_bytes);
			return 12;
		}

		if (result.cell_address == saved_cell)
		{
			std::fprintf(stderr, "FAIL: the data symbol was mapped to the same address in both processes\n");
			return 13;
		}

		if (result.code_address == saved_code)
		{
			std::fprintf(stderr, "FAIL: the object was loaded at the same address in both processes\n");
			return 14;
		}

		std::printf("linked the %zu-byte cached object without code generation; cell %#" PRIx64 " -> %#" PRIx64 ", helper %#" PRIx64 " -> %#" PRIx64 " (%s), code %#" PRIx64 " -> %#" PRIx64 "\n",
			cache.bytes, saved_cell, result.cell_address, saved_helper, result.helper_address,
			saved_helper == result.helper_address ? "same image slide" : "different image slide", saved_code, result.code_address);
		std::printf("PASS: relocated external data, external call, rodata and pointer table across processes\n");
		return 0;
	}

	if (mode == "corrupt")
	{
		const std::string object = dir + "/" + k_module;
		std::ifstream in(object, std::ios::binary);
		std::vector<char> bytes((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
		in.close();

		if (bytes.size() < 64)
		{
			std::fprintf(stderr, "FAIL: no object to corrupt\n");
			return 15;
		}

		// A truncated file must be rejected by validation, never linked.
		{
			std::ofstream out(object, std::ios::binary | std::ios::trunc);
			out.write(bytes.data(), static_cast<std::streamsize>(bytes.size() / 2));
		}

		file_cache cache(dir, true);
		static_cast<void>(run(cache, &g_cells[9], 0x0102030405060708ull, k_entry));

		if (!cache.rejected || !cache.compiled || cache.loaded)
		{
			std::fprintf(stderr, "FAIL: truncated object handling (rejected=%d compiled=%d loaded=%d)\n", cache.rejected, cache.compiled, cache.loaded);
			return 16;
		}

		// A valid object whose entry symbol differs (a foreign module under this
		// name) must be rejected by the symbol requirement as well.
		{
			file_cache foreign(dir, true);
			static_cast<void>(run(foreign, &g_cells[10], 0x1020304050607080ull, "__spu-0x00abc-foreign"));

			if (!foreign.compiled)
			{
				std::fprintf(stderr, "FAIL: foreign module did not compile\n");
				return 17;
			}
		}

		file_cache again(dir, true);
		static_cast<void>(run(again, &g_cells[11], 0x2030405060708090ull, k_entry));

		if (!again.rejected || !again.compiled || again.loaded)
		{
			std::fprintf(stderr, "FAIL: foreign object handling (rejected=%d compiled=%d loaded=%d)\n", again.rejected, again.compiled, again.loaded);
			return 18;
		}

		std::printf("PASS: truncated and foreign objects are rejected before MCJIT and replaced by a normal compilation\n");
		return 0;
	}

	std::fprintf(stderr, "unknown mode %s\n", mode.c_str());
	return 2;
}
