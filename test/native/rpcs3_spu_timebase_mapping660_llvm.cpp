// REWINDBOX_SPU_TIMEBASE_MAPPING_660 host proof (LLVM MCJIT, x86_64, without LLVM headers): a name mapping
// registered once is gone for modules linked after clearAllGlobalMappings(), and is back when re-registered.
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstddef>
extern "C" {
typedef struct LLVMOpaqueContext* LLVMContextRef; typedef struct LLVMOpaqueModule* LLVMModuleRef;
typedef struct LLVMOpaqueExecutionEngine* LLVMExecutionEngineRef; typedef struct LLVMOpaqueMemoryBuffer* LLVMMemoryBufferRef;
struct LLVMMCJITCompilerOptions { unsigned OptLevel; int CodeModel; int NoFramePointerElim; int EnableFastISel; void* MCJMM; };
LLVMContextRef LLVMContextCreate(); void LLVMLinkInMCJIT();
void LLVMInitializeX86TargetInfo(); void LLVMInitializeX86Target(); void LLVMInitializeX86TargetMC(); void LLVMInitializeX86AsmPrinter();
LLVMMemoryBufferRef LLVMCreateMemoryBufferWithMemoryRangeCopy(const char*, size_t, const char*);
int LLVMParseIRInContext(LLVMContextRef, LLVMMemoryBufferRef, LLVMModuleRef*, char**);
void LLVMInitializeMCJITCompilerOptions(LLVMMCJITCompilerOptions*, size_t);
int LLVMCreateMCJITCompilerForModule(LLVMExecutionEngineRef*, LLVMModuleRef, LLVMMCJITCompilerOptions*, size_t, char**);
void LLVMAddModule(LLVMExecutionEngineRef, LLVMModuleRef); uint64_t LLVMGetFunctionAddress(LLVMExecutionEngineRef, const char*);
// Decoy exported from this executable (-rdynamic): what a dlsym-style fallback finds.
uint64_t spu_timebase_offs = 0xDEC0DEull;
}
namespace llvm { struct StringRef { const char* d; size_t n; };
class ExecutionEngine { public: uint64_t updateGlobalMapping(StringRef, uint64_t); void clearAllGlobalMappings(); }; }
static uint64_t g_cell = 0x1234ull; // stands for g_timebase_offs
static LLVMModuleRef parse(LLVMContextRef c, const char* fn) {
  char ir[512]; snprintf(ir, sizeof ir, "@spu_timebase_offs = external global i64\ndefine i64 @%s() {\n %%v = load i64, ptr @spu_timebase_offs\n ret i64 %%v\n}\n", fn);
  LLVMModuleRef m{}; char* err{}; if (LLVMParseIRInContext(c, LLVMCreateMemoryBufferWithMemoryRangeCopy(ir, strlen(ir), fn), &m, &err)) { printf("parse %s\n", err); return nullptr; } return m; }
static uint64_t run(LLVMExecutionEngineRef ee, const char* fn) { return reinterpret_cast<uint64_t(*)()>(LLVMGetFunctionAddress(ee, fn))(); }
int main() {
  LLVMLinkInMCJIT(); LLVMInitializeX86TargetInfo(); LLVMInitializeX86Target(); LLVMInitializeX86TargetMC(); LLVMInitializeX86AsmPrinter();
  LLVMContextRef c = LLVMContextCreate();
  LLVMMCJITCompilerOptions o; LLVMInitializeMCJITCompilerOptions(&o, sizeof o);
  LLVMExecutionEngineRef ee{}; char* err{};
  if (LLVMCreateMCJITCompilerForModule(&ee, parse(c, "rd0"), &o, sizeof o, &err)) { printf("ee %s\n", err); return 2; }
  auto* e = reinterpret_cast<llvm::ExecutionEngine*>(ee);
  const llvm::StringRef name{"spu_timebase_offs", 17};
  e->updateGlobalMapping(name, reinterpret_cast<uint64_t>(&g_cell));          // init(), once
  const uint64_t a = run(ee, "rd0");                                            // mapped, no clear
  e->clearAllGlobalMappings(); LLVMAddModule(ee, parse(c, "rd1"));              // compile(): clear, build, link
  const uint64_t b = run(ee, "rd1");
  e->clearAllGlobalMappings(); e->updateGlobalMapping(name, reinterpret_cast<uint64_t>(&g_cell)); // fix: re-map after clear
  LLVMAddModule(ee, parse(c, "rd2")); const uint64_t d = run(ee, "rd2");
  printf("{\"mapped_no_clear\":\"0x%llx\",\"after_clear\":\"0x%llx\",\"after_clear_remap\":\"0x%llx\",\"cell\":\"0x%llx\",\"decoy\":\"0x%llx\"}\n",
    (unsigned long long)a, (unsigned long long)b, (unsigned long long)d, (unsigned long long)g_cell, (unsigned long long)spu_timebase_offs);
  return (a == g_cell && b == spu_timebase_offs && d == g_cell) ? 0 : 1;
}
