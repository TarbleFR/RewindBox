// NEOSTATION_BUILD483_LLVM_PIPELINES_V1 host harness, executed on the macOS arm64
// runner with the Homebrew LLVM 22 that also compiles the Core.
//
// Two jobs, both labelled "measured on host": they prove pipeline mechanics and
// count instructions on synthetic kernels shaped like translator output; they
// do not run the real PPU/SPU translators (those need the whole emulator) and
// they measure nothing on an iPhone.
//
//   cc-hazard            An internal function with preserve_mostcc (the SPU
//                        m_test_state helper) called once with the plain C
//                        convention and once with its own: InstCombine erases the
//                        mismatched call (a store to poison, LLVM's non-terminator
//                        unreachable, takes its place and later passes may drop
//                        even that) and keeps the matched one. This is the
//                        defect ARMSX3 ab53473f7 / upstream
//                        eda7621f fixed before enabling InstCombine, and why the
//                        Core sets the callee convention on both m_test_state
//                        calls.
//   kernels <out.json>   Runs the exact pipelines of the Core (PPU: none,
//                        EarlyCSE, Extended; SPU: Reference 481, Upstream
//                        InstCombine) on kernels written like the translators
//                        emit them (SPU select/compare masks, byte-swap idioms,
//                        PPU condition-register bits and register flushes,
//                        rotate-and-mask, float sign masks), verifies every
//                        module, counts IR and AArch64 instructions (apple-m4,
//                        the A18 Pro model name LLVM resolves), times the
//                        passes, and executes every variant with MCJIT on the
//                        host against the unoptimized reference on fixed inputs
//                        (bit-exact results required).
#include <llvm/ADT/SmallString.h>
#include <llvm/Analysis/CGSCCPassManager.h>
#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/ExecutionEngine/ExecutionEngine.h>
#include <llvm/ExecutionEngine/MCJIT.h>
#include <llvm/ExecutionEngine/SectionMemoryManager.h>
#include <llvm/IR/Constants.h>
#include <llvm/IR/Instructions.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/LegacyPassManager.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/PassManager.h>
#include <llvm/IR/Verifier.h>
#include <llvm/IRReader/IRReader.h>
#include <llvm/MC/TargetRegistry.h>
#include <llvm/Passes/PassBuilder.h>
#include <llvm/Support/CodeGen.h>
#include <llvm/Support/MemoryBuffer.h>
#include <llvm/Support/SourceMgr.h>
#include <llvm/Support/TargetSelect.h>
#include <llvm/Support/raw_ostream.h>
#include <llvm/Target/TargetMachine.h>
#include <llvm/Target/TargetOptions.h>
#include <llvm/TargetParser/Host.h>
#include <llvm/TargetParser/Triple.h>
#include <llvm/Transforms/InstCombine/InstCombine.h>
#include <llvm/Transforms/Scalar/ADCE.h>
#include <llvm/Transforms/Scalar/DeadStoreElimination.h>
#include <llvm/Transforms/Scalar/EarlyCSE.h>
#include <llvm/Transforms/Scalar/LICM.h>
#include <llvm/Transforms/Scalar/LoopPassManager.h>
#include <llvm/Transforms/Scalar/SimplifyCFG.h>
#include <llvm/Transforms/Utils/Cloning.h>

#include <chrono>
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
	constexpr const char* k_triple = "aarch64-unknown-linux-android"; // jit_compiler::triple1/2 on Apple ARM64
	constexpr const char* k_device_cpu = "apple-m4";                   // what LLVM's Host.cpp resolves for the A18 Pro

	// ---------------------------------------------------------------- pipelines
	enum class pipeline
	{
		none,          // PPU Upstream ARM64: no IR pass
		ppu_early_cse, // PPU EarlyCSE: fpm.addPass(EarlyCSEPass())
		ppu_extended,  // PPU Extended: EarlyCSE(memssa), SimplifyCFG, InstCombine, DSE, LICM, ADCE
		spu_reference, // SPU Reference 481: EarlyCSE(memssa), SimplifyCFG, DSE, LICM, ADCE
		spu_upstream,  // SPU Upstream InstCombine: EarlyCSE(memssa), SimplifyCFG, InstCombine, DSE, LICM, ADCE
		instcombine_only, // cc-hazard stage 1 only: InstCombine alone, to show its mechanism
	};

	const char* pipeline_name(pipeline p)
	{
		switch (p)
		{
		case pipeline::none: return "none";
		case pipeline::ppu_early_cse: return "ppu_early_cse";
		case pipeline::ppu_extended: return "ppu_extended";
		case pipeline::spu_reference: return "spu_reference";
		case pipeline::spu_upstream: return "spu_upstream";
		case pipeline::instcombine_only: return "instcombine_only";
		}
		return "?";
	}

	struct pass_setup
	{
		llvm::LoopAnalysisManager lam;
		llvm::FunctionAnalysisManager fam;
		llvm::CGSCCAnalysisManager cgam;
		llvm::ModuleAnalysisManager mam;
		llvm::PassBuilder pb;
		llvm::FunctionPassManager fpm;

		explicit pass_setup(pipeline p)
		{
			pb.registerModuleAnalyses(mam);
			pb.registerCGSCCAnalyses(cgam);
			pb.registerFunctionAnalyses(fam);
			pb.registerLoopAnalyses(lam);
			pb.crossRegisterProxies(lam, fam, cgam, mam);

			switch (p)
			{
			case pipeline::none:
				break;
			case pipeline::ppu_early_cse:
				fpm.addPass(llvm::EarlyCSEPass());
				break;
			case pipeline::ppu_extended:
			case pipeline::spu_upstream:
				fpm.addPass(llvm::EarlyCSEPass(true));
				fpm.addPass(llvm::SimplifyCFGPass());
				fpm.addPass(llvm::InstCombinePass());
				fpm.addPass(llvm::DSEPass());
				fpm.addPass(llvm::createFunctionToLoopPassAdaptor(llvm::LICMPass(llvm::LICMOptions()), true));
				fpm.addPass(llvm::ADCEPass());
				break;
			case pipeline::instcombine_only:
				fpm.addPass(llvm::InstCombinePass());
				break;
			case pipeline::spu_reference:
				fpm.addPass(llvm::EarlyCSEPass(true));
				fpm.addPass(llvm::SimplifyCFGPass());
				fpm.addPass(llvm::DSEPass());
				fpm.addPass(llvm::createFunctionToLoopPassAdaptor(llvm::LICMPass(llvm::LICMOptions()), true));
				fpm.addPass(llvm::ADCEPass());
				break;
			}
		}

		void run(llvm::Module& m)
		{
			for (llvm::Function& f : m)
			{
				if (!f.isDeclaration())
				{
					fpm.run(f, fam);
				}
			}
		}
	};

	// ---------------------------------------------------------------- helpers
	std::unique_ptr<llvm::Module> parse(llvm::LLVMContext& context, const char* text, const char* name)
	{
		llvm::SMDiagnostic diagnostic;
		std::unique_ptr<llvm::Module> m = llvm::parseIR(llvm::MemoryBufferRef(text, name), diagnostic, context);

		if (!m)
		{
			std::string message;
			llvm::raw_string_ostream stream(message);
			diagnostic.print(name, stream);
			std::fprintf(stderr, "FAIL: IR parse: %s\n", message.c_str());
			std::exit(2);
		}

		m->setTargetTriple(llvm::Triple(k_triple));
		return m;
	}

	void verify(llvm::Module& m, const char* what)
	{
		std::string error;
		llvm::raw_string_ostream stream(error);

		if (llvm::verifyModule(m, &stream))
		{
			std::fprintf(stderr, "FAIL: verification of %s: %s\n", what, error.c_str());
			std::exit(3);
		}
	}

	std::size_t ir_instructions(const llvm::Module& m)
	{
		std::size_t count = 0;

		for (const llvm::Function& f : m)
		{
			for (const llvm::BasicBlock& b : f)
			{
				count += b.size();
			}
		}

		return count;
	}

	std::unique_ptr<llvm::TargetMachine> device_target_machine()
	{
		std::string error;
		const llvm::Target* target = llvm::TargetRegistry::lookupTarget(k_triple, error);

		if (!target)
		{
			std::fprintf(stderr, "FAIL: AArch64 target: %s\n", error.c_str());
			std::exit(4);
		}

		// The Core advertises +sha3 +dotprod +i8mm (A18 Pro has them) and never SVE.
		return std::unique_ptr<llvm::TargetMachine>(target->createTargetMachine(
			llvm::Triple(k_triple), k_device_cpu, "+sha3,+dotprod,+i8mm,-sve,-sve2", llvm::TargetOptions(),
			llvm::Reloc::PIC_, llvm::CodeModel::Small, llvm::CodeGenOptLevel::Aggressive, true));
	}

	// Assembly of the module for the device CPU and the number of instructions in it.
	std::pair<std::string, std::size_t> emit_assembly(llvm::Module& m, llvm::TargetMachine& tm)
	{
		m.setDataLayout(tm.createDataLayout());
		llvm::SmallString<65536> buffer;
		llvm::raw_svector_ostream stream(buffer);
		llvm::legacy::PassManager pm;

		if (tm.addPassesToEmitFile(pm, stream, nullptr, llvm::CodeGenFileType::AssemblyFile))
		{
			std::fprintf(stderr, "FAIL: cannot emit assembly\n");
			std::exit(5);
		}

		pm.run(m);
		std::string text = std::string(buffer.str());
		std::size_t instructions = 0;
		std::size_t position = 0;

		while (position < text.size())
		{
			const std::size_t end = text.find('\n', position);
			const std::string line = text.substr(position, end == std::string::npos ? std::string::npos : end - position);
			position = end == std::string::npos ? text.size() : end + 1;

			// Instructions are indented; labels, directives and comments are not instructions.
			if (line.size() > 1 && (line[0] == '\t' || line[0] == ' '))
			{
				std::size_t first = line.find_first_not_of(" \t");

				if (first != std::string::npos && line[first] != '.' && line[first] != '/' && line[first] != ';')
				{
					instructions++;
				}
			}
		}

		return {text, instructions};
	}

	struct engine
	{
		std::unique_ptr<llvm::ExecutionEngine> ee;
	};

	engine jit(std::unique_ptr<llvm::Module> m)
	{
		std::string cpu = llvm::sys::getHostCPUName().str();

		if (cpu.empty() || cpu == "generic")
		{
			cpu = "cortex-a78";
		}

		std::string error;
		engine result;
		result.ee.reset(llvm::EngineBuilder(std::move(m))
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
			std::exit(6);
		}

		result.ee->finalizeObject();
		return result;
	}

	// ---------------------------------------------------------------- kernels
	// Every kernel reads 16 i32 from %in (and treats them as four <4 x i32> or
	// scalars) and writes 16 i32 to %out, so one driver executes them all.
	struct kernel
	{
		const char* name;
		const char* family; // "spu" or "ppu"
		const char* what;
		const char* ir;
	};

	const kernel k_kernels[] = {
		{"spu_selb_mask", "spu", "SELB as (a & ~m) | (b & m) with redundant mask and xor, as the translator emits before folding",
R"IR(
define void @kernel(ptr %in, ptr %out) {
entry:
  %pa = getelementptr i32, ptr %in, i64 0
  %pb = getelementptr i32, ptr %in, i64 4
  %pm = getelementptr i32, ptr %in, i64 8
  %a = load <4 x i32>, ptr %pa, align 16
  %b = load <4 x i32>, ptr %pb, align 16
  %m = load <4 x i32>, ptr %pm, align 16
  %nm = xor <4 x i32> %m, <i32 -1, i32 -1, i32 -1, i32 -1>
  %t1 = and <4 x i32> %a, %nm
  %t2 = and <4 x i32> %b, %m
  %r = or <4 x i32> %t1, %t2
  %r2 = and <4 x i32> %r, <i32 -1, i32 -1, i32 -1, i32 -1>
  %r3 = xor <4 x i32> %r2, zeroinitializer
  store <4 x i32> %r3, ptr %out, align 16
  %po = getelementptr i32, ptr %out, i64 4
  store <4 x i32> %t1, ptr %po, align 16
  %po2 = getelementptr i32, ptr %out, i64 8
  store <4 x i32> %t2, ptr %po2, align 16
  %po3 = getelementptr i32, ptr %out, i64 12
  store <4 x i32> %nm, ptr %po3, align 16
  ret void
}
)IR"},
		{"spu_cmp_sext_chain", "spu", "CGT/CEQ masks combined, inverted and re-tested: compare, sign-extend, or, xor, compare again",
R"IR(
define void @kernel(ptr %in, ptr %out) {
entry:
  %pa = getelementptr i32, ptr %in, i64 0
  %pb = getelementptr i32, ptr %in, i64 4
  %pm = getelementptr i32, ptr %in, i64 8
  %a = load <4 x i32>, ptr %pa, align 16
  %b = load <4 x i32>, ptr %pb, align 16
  %m = load <4 x i32>, ptr %pm, align 16
  %c1 = icmp sgt <4 x i32> %a, %b
  %s1 = sext <4 x i1> %c1 to <4 x i32>
  %c2 = icmp eq <4 x i32> %a, %m
  %s2 = sext <4 x i1> %c2 to <4 x i32>
  %o = or <4 x i32> %s1, %s2
  %n = xor <4 x i32> %o, <i32 -1, i32 -1, i32 -1, i32 -1>
  %z = icmp ne <4 x i32> %n, zeroinitializer
  %r = sext <4 x i1> %z to <4 x i32>
  %sel = select <4 x i1> %c1, <4 x i32> %a, <4 x i32> %b
  store <4 x i32> %r, ptr %out, align 16
  %po = getelementptr i32, ptr %out, i64 4
  store <4 x i32> %sel, ptr %po, align 16
  %po2 = getelementptr i32, ptr %out, i64 8
  store <4 x i32> %s1, ptr %po2, align 16
  %po3 = getelementptr i32, ptr %out, i64 12
  store <4 x i32> %s2, ptr %po3, align 16
  ret void
}
)IR"},
		{"bswap_idiom", "spu", "big-endian loads: manual byte-swap by shifts and masks, and bswap(bswap(x)) round trips",
R"IR(
declare i32 @llvm.bswap.i32(i32)
define void @kernel(ptr %in, ptr %out) {
entry:
  %x = load i32, ptr %in, align 4
  %s1 = shl i32 %x, 24
  %m1 = and i32 %x, 65280
  %s2 = shl i32 %m1, 8
  %m2 = and i32 %x, 16711680
  %s3 = lshr i32 %m2, 8
  %s4 = lshr i32 %x, 24
  %o1 = or i32 %s1, %s2
  %o2 = or i32 %s3, %s4
  %sw = or i32 %o1, %o2
  %p1 = getelementptr i32, ptr %in, i64 1
  %y = load i32, ptr %p1, align 4
  %b1 = call i32 @llvm.bswap.i32(i32 %y)
  %b2 = call i32 @llvm.bswap.i32(i32 %b1)
  %sum = add i32 %sw, %b2
  store i32 %sw, ptr %out, align 4
  %q1 = getelementptr i32, ptr %out, i64 1
  store i32 %b2, ptr %q1, align 4
  %q2 = getelementptr i32, ptr %out, i64 2
  store i32 %sum, ptr %q2, align 4
  %q3 = getelementptr i32, ptr %out, i64 3
  store i32 %b1, ptr %q3, align 4
  ret void
}
)IR"},
		{"ppu_cr_bits", "ppu", "cmpd then bc: lt/gt/eq bits stored to the thread, reloaded and combined for the branch",
R"IR(
define void @kernel(ptr %in, ptr %out) {
entry:
  %pa = getelementptr i32, ptr %in, i64 0
  %pb = getelementptr i32, ptr %in, i64 2
  %ra = load i64, ptr %pa, align 8
  %rb = load i64, ptr %pb, align 8
  %lt = icmp slt i64 %ra, %rb
  %gt = icmp sgt i64 %ra, %rb
  %eq = icmp eq i64 %ra, %rb
  %ltb = zext i1 %lt to i8
  %gtb = zext i1 %gt to i8
  %eqb = zext i1 %eq to i8
  %c0 = getelementptr i8, ptr %out, i64 0
  %c1 = getelementptr i8, ptr %out, i64 1
  %c2 = getelementptr i8, ptr %out, i64 2
  store i8 %ltb, ptr %c0, align 1
  store i8 %gtb, ptr %c1, align 1
  store i8 %eqb, ptr %c2, align 1
  %l = load i8, ptr %c0, align 1
  %e = load i8, ptr %c2, align 1
  %o = or i8 %l, %e
  %t = icmp ne i8 %o, 0
  br i1 %t, label %taken, label %fall
taken:
  %d = sub i64 %ra, %rb
  %dp = getelementptr i32, ptr %out, i64 2
  store i64 %d, ptr %dp, align 8
  br label %done
fall:
  %s = add i64 %ra, %rb
  %sp = getelementptr i32, ptr %out, i64 2
  store i64 %s, ptr %sp, align 8
  br label %done
done:
  %flag = phi i32 [1, %taken], [0, %fall]
  %fp = getelementptr i32, ptr %out, i64 4
  store i32 %flag, ptr %fp, align 4
  ret void
}
)IR"},
		{"ppu_register_flush", "ppu", "successive flushes of the same guest registers to the thread between instructions (dead stores)",
R"IR(
define void @kernel(ptr %in, ptr %out) {
entry:
  %r3p = getelementptr i32, ptr %in, i64 0
  %r4p = getelementptr i32, ptr %in, i64 2
  %r3 = load i64, ptr %r3p, align 8
  %r4 = load i64, ptr %r4p, align 8
  %g3 = getelementptr i32, ptr %out, i64 0
  %g4 = getelementptr i32, ptr %out, i64 2
  store i64 %r3, ptr %g3, align 8
  store i64 %r4, ptr %g4, align 8
  %a1 = add i64 %r3, 16
  store i64 %a1, ptr %g3, align 8
  %a2 = shl i64 %r4, 2
  store i64 %a2, ptr %g4, align 8
  %a3 = add i64 %a1, %a2
  store i64 %a3, ptr %g3, align 8
  %a4 = xor i64 %a2, %a3
  store i64 %a4, ptr %g4, align 8
  %g5 = getelementptr i32, ptr %out, i64 4
  store i64 %a3, ptr %g5, align 8
  ret void
}
)IR"},
		{"ppu_rlwinm_rotate", "ppu", "rlwinm/rlwimi sequences: rotate by shifts and or, then mask and merge",
R"IR(
define void @kernel(ptr %in, ptr %out) {
entry:
  %x = load i32, ptr %in, align 4
  %p1 = getelementptr i32, ptr %in, i64 1
  %y = load i32, ptr %p1, align 4
  %sl = shl i32 %x, 8
  %sr = lshr i32 %x, 24
  %rot = or i32 %sl, %sr
  %msk = and i32 %rot, 65535
  %sl2 = shl i32 %y, 16
  %sr2 = lshr i32 %y, 16
  %rot2 = or i32 %sl2, %sr2
  %msk2 = and i32 %rot2, -65536
  %merged = or i32 %msk, %msk2
  %again = and i32 %merged, -1
  store i32 %again, ptr %out, align 4
  %q1 = getelementptr i32, ptr %out, i64 1
  store i32 %rot, ptr %q1, align 4
  %q2 = getelementptr i32, ptr %out, i64 2
  store i32 %rot2, ptr %q2, align 4
  ret void
}
)IR"},
		{"float_sign_masks", "spu", "fabs/fneg by integer masks on <4 x float>, then fma, as XFloat Approximate lowers them",
R"IR(
declare <4 x float> @llvm.fma.v4f32(<4 x float>, <4 x float>, <4 x float>)
define void @kernel(ptr %in, ptr %out) {
entry:
  %pa = getelementptr i32, ptr %in, i64 0
  %pb = getelementptr i32, ptr %in, i64 4
  %pc = getelementptr i32, ptr %in, i64 8
  %ai = load <4 x i32>, ptr %pa, align 16
  %bi = load <4 x i32>, ptr %pb, align 16
  %ci = load <4 x i32>, ptr %pc, align 16
  %absi = and <4 x i32> %ai, <i32 2147483647, i32 2147483647, i32 2147483647, i32 2147483647>
  %negi = xor <4 x i32> %bi, <i32 -2147483648, i32 -2147483648, i32 -2147483648, i32 -2147483648>
  %a = bitcast <4 x i32> %absi to <4 x float>
  %b = bitcast <4 x i32> %negi to <4 x float>
  %c = bitcast <4 x i32> %ci to <4 x float>
  %f = call <4 x float> @llvm.fma.v4f32(<4 x float> %a, <4 x float> %b, <4 x float> %c)
  %fi = bitcast <4 x float> %f to <4 x i32>
  %fabs2 = and <4 x i32> %fi, <i32 2147483647, i32 2147483647, i32 2147483647, i32 2147483647>
  store <4 x i32> %fi, ptr %out, align 16
  %po = getelementptr i32, ptr %out, i64 4
  store <4 x i32> %fabs2, ptr %po, align 16
  %po2 = getelementptr i32, ptr %out, i64 8
  store <4 x i32> %absi, ptr %po2, align 16
  %po3 = getelementptr i32, ptr %out, i64 12
  store <4 x i32> %negi, ptr %po3, align 16
  ret void
}
)IR"},
	};

	using kernel_fn = void (*)(const std::int32_t*, std::int32_t*);

	struct run_result
	{
		std::int32_t out[16];
	};

	void execute(kernel_fn fn, const std::int32_t (&input)[16], run_result& result)
	{
		std::memset(result.out, 0, sizeof(result.out));
		fn(input, result.out);
	}

	// ---------------------------------------------------------------- cc hazard
	int cc_hazard()
	{
		llvm::LLVMContext context;
		std::unique_ptr<llvm::Module> m = parse(context, R"IR(
define internal preserve_mostcc void @spu_test_state(ptr %t) {
entry:
  store i8 1, ptr %t, align 1
  ret void
}
define void @caller_mismatched(ptr %t) {
entry:
  call void @spu_test_state(ptr %t)
  ret void
}
define void @caller_matched(ptr %t) {
entry:
  call preserve_mostcc void @spu_test_state(ptr %t)
  ret void
}
)IR", "cc-hazard");
		verify(*m, "cc-hazard input");

		// Stage 1: InstCombine alone shows the mechanism (LLVM 22.1.8: the call
		// is erased and a non-terminator unreachable, `store i1 true, ptr poison`,
		// takes its place). Stage 2: the Core's Upstream SPU pipeline shows what
		// reaches the backend (DSE/ADCE may remove even that store, or SimplifyCFG
		// may turn it into `unreachable`): in every form the state check is gone.
		std::unique_ptr<llvm::Module> after_instcombine = llvm::CloneModule(*m);
		{
			pass_setup setup(pipeline::instcombine_only);
			setup.run(*after_instcombine);
		}
		verify(*after_instcombine, "cc-hazard after InstCombine");
		{
			pass_setup setup(pipeline::spu_upstream);
			setup.run(*m);
		}
		verify(*m, "cc-hazard after the Upstream SPU pipeline");

		struct shape
		{
			bool call = false;
			bool matched_cc = false;
			bool unreachable = false;
			bool poison_store = false;
		};

		const auto inspect = [](llvm::Module& module, const char* name)
		{
			shape s;
			llvm::Function* f = module.getFunction(name);

			if (!f)
			{
				std::fprintf(stderr, "FAIL: %s missing after passes\n", name);
				std::exit(7);
			}

			for (llvm::BasicBlock& b : *f)
			{
				for (llvm::Instruction& i : b)
				{
					if (auto* call = llvm::dyn_cast<llvm::CallInst>(&i))
					{
						llvm::Function* callee = call->getCalledFunction();

						if (callee && callee->getName() == "spu_test_state")
						{
							s.call = true;
							s.matched_cc = call->getCallingConv() == callee->getCallingConv();
						}
					}
					else if (llvm::isa<llvm::UnreachableInst>(&i))
					{
						s.unreachable = true;
					}
					else if (auto* store = llvm::dyn_cast<llvm::StoreInst>(&i))
					{
						// PoisonValue derives from UndefValue.
						if (llvm::isa<llvm::UndefValue>(store->getPointerOperand()))
						{
							s.poison_store = true;
						}
					}
				}
			}

			return s;
		};

		const auto describe = [](const shape& s)
		{
			if (s.call)
			{
				return s.matched_cc ? "call kept with the callee's convention" : "call kept with a mismatched convention";
			}

			if (s.poison_store)
			{
				return "call erased, store to poison left (non-terminator unreachable)";
			}

			return s.unreachable ? "call erased, unreachable left" : "call erased, nothing left";
		};

		const shape ic_mismatched = inspect(*after_instcombine, "caller_mismatched");
		const shape ic_matched = inspect(*after_instcombine, "caller_matched");
		const shape up_mismatched = inspect(*m, "caller_mismatched");
		const shape up_matched = inspect(*m, "caller_matched");
		std::printf("cc-hazard after InstCombine alone: mismatched -> %s; matched -> %s\n", describe(ic_mismatched), describe(ic_matched));
		std::printf("cc-hazard after the Upstream SPU pipeline: mismatched -> %s; matched -> %s\n", describe(up_mismatched), describe(up_matched));

		const bool mechanism = !ic_mismatched.call && (ic_mismatched.poison_store || ic_mismatched.unreachable);
		const bool erased = !up_mismatched.call;
		const bool matched_kept = ic_matched.call && ic_matched.matched_cc && up_matched.call && up_matched.matched_cc;

		if (!mechanism || !erased || !matched_kept)
		{
			std::fprintf(stderr, "FAIL: InstCombine calling-convention behaviour differs from the documented hazard\n");
			return 8;
		}

		std::printf("PASS: InstCombine erases a direct call with a mismatched convention (non-terminator unreachable) and the Upstream SPU pipeline leaves no call; the matched call survives; the Core's m_test_state calls carry their callee's convention\n");
		return 0;
	}

	// ---------------------------------------------------------------- kernels
	int kernels(const char* output_path)
	{
		LLVMLinkInMCJIT();
		std::unique_ptr<llvm::TargetMachine> device_tm = device_target_machine();
		std::int32_t input[16];

		for (int i = 0; i < 16; i++)
		{
			// Deterministic, with sign bits, zeros and all-ones mixed in.
			input[i] = static_cast<std::int32_t>((0x9E3779B9u * static_cast<std::uint32_t>(i + 1)) ^ (i % 3 == 0 ? 0xFFFFFFFFu : 0u));
		}

		input[8] = 0;
		input[9] = -1;
		input[10] = 0x00FF00FF;
		input[11] = static_cast<std::int32_t>(0x80000000u);

		std::ofstream json(output_path, std::ios::trunc);
		json << "{\n  \"host_cpu\": \"" << llvm::sys::getHostCPUName().str() << "\",\n  \"device_cpu\": \"" << k_device_cpu << "\",\n  \"kernels\": [\n";
		bool first_kernel = true;
		bool all_equal = true;
		int failures = 0;

		for (const kernel& k : k_kernels)
		{
			llvm::LLVMContext context;
			std::unique_ptr<llvm::Module> base = parse(context, k.ir, k.name);
			verify(*base, k.name);
			run_result reference{};
			bool have_reference = false;

			if (!first_kernel)
			{
				json << ",\n";
			}

			first_kernel = false;
			json << "    {\"name\": \"" << k.name << "\", \"family\": \"" << k.family << "\", \"what\": \"" << k.what << "\", \"variants\": [";
			bool first_variant = true;

			for (const pipeline p : {pipeline::none, pipeline::ppu_early_cse, pipeline::ppu_extended, pipeline::spu_reference, pipeline::spu_upstream})
			{
				std::unique_ptr<llvm::Module> m = llvm::CloneModule(*base);
				const auto started = std::chrono::steady_clock::now();
				{
					pass_setup setup(p);
					setup.run(*m);
				}
				const double pass_ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - started).count();
				verify(*m, k.name);
				const std::size_t ir_count = ir_instructions(*m);

				std::unique_ptr<llvm::Module> for_asm = llvm::CloneModule(*m);
				const auto [assembly, asm_count] = emit_assembly(*for_asm, *device_tm);

				// Execute on the host and compare with the unoptimized module.
				std::unique_ptr<llvm::Module> for_jit = llvm::CloneModule(*m);
				for_jit->setTargetTriple(llvm::Triple(k_triple));
				engine e = jit(std::move(for_jit));
				const kernel_fn fn = reinterpret_cast<kernel_fn>(e.ee->getFunctionAddress("kernel"));

				if (!fn)
				{
					std::fprintf(stderr, "FAIL: %s/%s has no kernel entry\n", k.name, pipeline_name(p));
					return 9;
				}

				run_result result{};
				execute(fn, input, result);
				bool equal = true;

				if (!have_reference)
				{
					reference = result;
					have_reference = true;
				}
				else
				{
					equal = std::memcmp(reference.out, result.out, sizeof(result.out)) == 0;
				}

				if (!equal)
				{
					all_equal = false;
					failures++;
					std::fprintf(stderr, "FAIL: %s differs between none and %s\n", k.name, pipeline_name(p));
				}

				std::printf("%-20s %-14s ir=%3zu asm=%3zu pass_ms=%.3f equal=%d\n", k.name, pipeline_name(p), ir_count, asm_count, pass_ms, equal);

				if (p == pipeline::spu_upstream || (p == pipeline::ppu_extended && std::strcmp(k.family, "ppu") == 0))
				{
					std::printf("---- %s / %s AArch64 (%s) ----\n%s\n", k.name, pipeline_name(p), k_device_cpu, assembly.c_str());
				}

				if (!first_variant)
				{
					json << ", ";
				}

				first_variant = false;
				json << "{\"pipeline\": \"" << pipeline_name(p) << "\", \"ir_instructions\": " << ir_count << ", \"aarch64_instructions\": " << asm_count
					 << ", \"pass_ms\": " << pass_ms << ", \"equal_to_unoptimized\": " << (equal ? "true" : "false") << "}";
			}

			json << "]}";
		}

		json << "\n  ],\n  \"all_variants_bit_exact\": " << (all_equal ? "true" : "false") << ",\n  \"measured_on\": \"macOS arm64 host, not an iPhone; synthetic kernels, not translator output\"\n}\n";

		if (failures)
		{
			std::fprintf(stderr, "FAIL: %d variant(s) changed results\n", failures);
			return 10;
		}

		std::printf("PASS: %zu kernels x 5 pipelines verified, assembled for %s and executed bit-exactly against the unoptimized module\n",
			std::size(k_kernels), k_device_cpu);
		return 0;
	}
}

int main(int argc, char** argv)
{
	if (argc < 2)
	{
		std::fprintf(stderr, "usage: %s cc-hazard | kernels <out.json>\n", argv[0]);
		return 2;
	}

	LLVMInitializeAArch64TargetInfo();
	LLVMInitializeAArch64Target();
	LLVMInitializeAArch64TargetMC();
	LLVMInitializeAArch64AsmPrinter();
	LLVMInitializeAArch64AsmParser();

	const std::string mode = argv[1];

	if (mode == "cc-hazard")
	{
		return cc_hazard();
	}

	if (mode == "kernels" && argc == 3)
	{
		return kernels(argv[2]);
	}

	std::fprintf(stderr, "unknown mode\n");
	return 2;
}
