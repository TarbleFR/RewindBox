// CELL559 SPU cache-hit work. The PASS_SETUP marker receives the analysis-manager, PassBuilder
// and function-pass-pipeline construction copied verbatim from compile() in
// SPULLVMRecompiler.cpp; 559 runs it only for a cache miss. This measures, with
// the host's LLVM, the per-hit construction the 555 Core performed and discarded.
// It is a host CPU measurement, not an iPhone SPU stall or frame-time result.
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <vector>
#include <llvm/Analysis/CGSCCPassManager.h>
#include <llvm/Analysis/LoopAnalysisManager.h>
#include <llvm/IR/PassManager.h>
#include <llvm/Passes/PassBuilder.h>
#include <llvm/Transforms/Scalar/ADCE.h>
#include <llvm/Transforms/Scalar/DeadStoreElimination.h>
#include <llvm/Transforms/Scalar/EarlyCSE.h>
#include <llvm/Transforms/Scalar/LICM.h>
#include <llvm/Transforms/Scalar/LoopPassManager.h>
#include <llvm/Transforms/Scalar/SimplifyCFG.h>
#include <llvm/Transforms/InstCombine/InstCombine.h>
#include <llvm/Config/llvm-config.h>

using namespace llvm;
enum class spu_llvm_pipeline_type { reference, upstream };
struct { struct { spu_llvm_pipeline_type spu_llvm_pipeline = spu_llvm_pipeline_type::upstream; } core; } g_cfg;

static unsigned setup_once()
{
	@PASS_SETUP@
	return fpm.isEmpty() ? 0u : 1u;
}

int main()
{
	unsigned sink = 0;
	for (int i = 0; i < 200; ++i) sink += setup_once();
	std::vector<double> us;
	constexpr int rounds = 31, iterations = 400;
	for (int r = 0; r < rounds; ++r)
	{
		const auto t0 = std::chrono::steady_clock::now();
		for (int i = 0; i < iterations; ++i) sink += setup_once();
		const auto t1 = std::chrono::steady_clock::now();
		us.push_back(std::chrono::duration<double, std::micro>(t1 - t0).count() / iterations);
	}
	std::sort(us.begin(), us.end());
	std::printf("{\"passed\":%s,\"llvmVersion\":\"%s\",\"pipeline\":\"upstream\",\"medianMicrosecondsPerCacheHit\":%.3f,"
		"\"p10Microseconds\":%.3f,\"p90Microseconds\":%.3f,\"rounds\":%d,\"iterationsPerRound\":%d}\n",
		sink == 200u + rounds * iterations ? "true" : "false", LLVM_VERSION_STRING,
		us[rounds / 2], us[rounds / 10], us[rounds - 1 - rounds / 10], rounds, iterations);
	return sink == 200u + rounds * iterations ? 0 : 1;
}
