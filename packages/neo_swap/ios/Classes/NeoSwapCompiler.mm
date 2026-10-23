// SPDX-License-Identifier: GPL-2.0-or-later
#include "NeoSwapCompilerAPI.h"
#include "NeoSwapCompilerBudget.h"

extern "C" void NeoSwapCompilerBudgetChanged();
namespace {
neostation::compiler::budget& controller() {
    static neostation::compiler::budget value;
    return value;
}
uint64_t acquire(uint64_t estimate, uint64_t headroom) { const auto ticket = controller().acquire(estimate, headroom); if (ticket) NeoSwapCompilerBudgetChanged(); return ticket; }
void release(uint64_t ticket) { controller().release(ticket); NeoSwapCompilerBudgetChanged(); }
const NeoSwapCompilerAPI api{sizeof(api), NEOSWAP_COMPILER_ABI, acquire, release};
}
extern "C" const NeoSwapCompilerAPI* NeoSwap_GetCompilerAPI(uint32_t abi) {
    return abi == NEOSWAP_COMPILER_ABI ? &api : nullptr;
}
extern "C" void NeoSwapCompiler_Update(bool foreground, bool constrained, uint64_t reserve) {
    controller().update(foreground, constrained, reserve);
}
extern "C" uint64_t NeoSwapCompiler_Reserved() { return controller().reserved(); }
