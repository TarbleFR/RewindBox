// Source-bound native lifetime test. Build with the project's pinned LLVM:
// c++ -std=c++20 mcjit_ir_release_test.cpp $(llvm-config --cxxflags --ldflags --system-libs --libs core executionengine mcjit native irreader) -o mcjit_ir_release_test
// The test driver replaces PRODUCTION_RELEASE_BLOCK with the exact production block.
#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <string>
#include <vector>
#include <llvm/ExecutionEngine/ExecutionEngine.h>
#include <llvm/ExecutionEngine/MCJIT.h>
#include <llvm/ExecutionEngine/ObjectCache.h>
#include <llvm/IR/LLVMContext.h>
#include <llvm/IR/IRBuilder.h>
#include <llvm/IR/Module.h>
#include <llvm/IR/ValueHandle.h>
#include <llvm/IRReader/IRReader.h>
#include <llvm/Support/MemoryBuffer.h>
#include <llvm/Support/SourceMgr.h>
#include <llvm/Support/TargetSelect.h>
#include <llvm/Support/raw_ostream.h>

namespace {
using fn_t = std::int64_t (*)(std::int64_t);
std::int64_t host_a(std::int64_t x) { return x + 17; }
std::int64_t host_b(std::int64_t x) { return x + 31; }

struct jit_compiler {
    llvm::ExecutionEngine* m_engine;
    llvm::Module* m_module = nullptr;
    llvm::IRBuilder<> builder;
    llvm::IRBuilder<>* m_ir = &builder;
    llvm::Function* m_function = nullptr;
    llvm::Function* m_test_state = nullptr;
    llvm::Function* m_dispatch = nullptr;
    jit_compiler(llvm::ExecutionEngine* engine, llvm::LLVMContext& context) : m_engine(engine), builder(context) {}
    bool release_compiled_module(llvm::Module* module) noexcept
    {
        m_module = module;
        m_function = module->getFunction("entry");
        // PRODUCTION_RELEASE_BLOCK
        return m_module == nullptr && m_function == nullptr && m_test_state == nullptr && m_dispatch == nullptr;
    }
};

struct cache final : llvm::ObjectCache {
    std::vector<char> object;
    bool reuse = false;
    unsigned writes = 0, hits = 0;
    void notifyObjectCompiled(const llvm::Module*, llvm::MemoryBufferRef buffer) override {
        const auto bytes = buffer.getBuffer();
        object.assign(bytes.begin(), bytes.end());
        ++writes;
    }
    std::unique_ptr<llvm::MemoryBuffer> getObject(const llvm::Module*) override {
        if (!reuse || object.empty()) return {};
        ++hits;
        return llvm::MemoryBuffer::getMemBufferCopy(llvm::StringRef(object.data(), object.size()), "cached.obj");
    }
};

std::unique_ptr<llvm::Module> parse(llvm::LLVMContext& context, const std::string& text) {
    llvm::SMDiagnostic error;
    auto module = llvm::parseIR(llvm::MemoryBufferRef(text, "lifetime-test"), error, context);
    if (!module) error.print("lifetime-test", llvm::errs());
    assert(module);
    return module;
}

const char* base_ir = R"(
    @table = global [4 x i64] [i64 5, i64 7, i64 11, i64 13]
    declare i64 @host_bias(i64)
    define i64 @entry(i64 %x) {
      %i = and i64 %x, 3
      %p = getelementptr [4 x i64], ptr @table, i64 0, i64 %i
      %v = load i64, ptr %p
      %h = call i64 @host_bias(i64 %x)
      %r = add i64 %v, %h
      ret i64 %r
    }
)";

std::unique_ptr<llvm::ExecutionEngine> engine_for(std::unique_ptr<llvm::Module> module) {
    std::string error;
    auto* engine = llvm::EngineBuilder(std::move(module)).setEngineKind(llvm::EngineKind::JIT).setErrorStr(&error).create();
    if (!engine) std::cerr << error << '\n';
    assert(engine);
    return std::unique_ptr<llvm::ExecutionEngine>(engine);
}

// Mirrors the real add/fin ordering: the native object is generated, function
// bodies are deleted, relocations finalize, then pointers are retrieved. The
// test checks ownership release, not a synthetic memory/FPS claim.
fn_t finish(llvm::ExecutionEngine& engine, llvm::Module* module, const std::string& name) {
    auto* entry = module->getFunction(name);
    assert(entry);
    engine.generateCodeForModule(module);
    for (auto& fn : module->functions()) fn.deleteBody();
    engine.finalizeObject();
    auto* pointer = engine.getPointerToFunction(entry);
    assert(pointer && !engine.hasError());
    return reinterpret_cast<fn_t>(pointer);
}
}

int main() {
    llvm::InitializeNativeTarget();
    llvm::InitializeNativeTargetAsmPrinter();
    llvm::LLVMContext context;
    auto module = parse(context, base_ir);
    auto* raw = module.get();
    llvm::WeakTrackingVH global(raw->getGlobalVariable("table"));
    auto engine = engine_for(std::move(module));
    cache object_cache;
    engine->setObjectCache(&object_cache);
    engine->updateGlobalMapping(raw->getFunction("host_bias"), reinterpret_cast<void*>(&host_a));
    auto entry = finish(*engine, raw, "entry");
    assert(entry(3) == 33 && object_cache.writes == 1 && object_cache.hits == 0);
    engine->setObjectCache(nullptr);
    const auto table_address = engine->getGlobalValueAddress("table");
    assert(table_address);
    jit_compiler jit{engine.get(), context};
    assert(jit.release_compiled_module(raw));
    assert(!global && !engine->FindFunctionNamed("entry"));
    assert(entry(3) == 33);
    assert(engine->getFunctionAddress("entry") == reinterpret_cast<std::uint64_t>(entry));
    assert(engine->getGlobalValueAddress("table") == table_address);

    std::vector<fn_t> callers;
    for (unsigned i = 0; i < 64; ++i) {
        engine->clearAllGlobalMappings();
        const auto name = "caller" + std::to_string(i);
        auto caller = parse(context, "declare i64 @entry(i64)\n@table = external global [4 x i64]\ndefine i64 @" + name + R"((i64 %x) {
          %a = call i64 @entry(i64 %x)
          %p = getelementptr [4 x i64], ptr @table, i64 0, i64 1
          %b = load i64, ptr %p
          %r = add i64 %a, %b
          ret i64 %r
        })");
        auto* pointer = caller.get();
        engine->addModule(std::move(caller));
        auto fn = finish(*engine, pointer, name);
        assert(fn(3) == 40);
        assert(jit.release_compiled_module(pointer));
        assert(!engine->FindFunctionNamed(name.c_str()));
        callers.push_back(fn);
    }
    for (auto fn : callers) assert(fn(3) == 40);
    assert(entry(2) == 30);

    // Real cached-object path. The same bytes are loaded into a new engine;
    // the external host binding must relocate to this process/engine's value.
    llvm::LLVMContext cached_context;
    auto cached_module = parse(cached_context, base_ir);
    auto* cached_raw = cached_module.get();
    llvm::WeakTrackingVH cached_global(cached_raw->getGlobalVariable("table"));
    auto cached_engine = engine_for(std::move(cached_module));
    object_cache.reuse = true;
    cached_engine->setObjectCache(&object_cache);
    cached_engine->updateGlobalMapping(cached_raw->getFunction("host_bias"), reinterpret_cast<void*>(&host_b));
    auto cached_entry = finish(*cached_engine, cached_raw, "entry");
    cached_engine->setObjectCache(nullptr);
    assert(object_cache.hits == 1 && object_cache.writes == 1);
    assert(cached_entry(3) == 47);
    jit_compiler cached_jit{cached_engine.get(), cached_context};
    assert(cached_jit.release_compiled_module(cached_raw));
    assert(!cached_global && !cached_engine->FindFunctionNamed("entry"));
    assert(cached_entry(3) == 47 && entry(3) == 33);
    std::cout << "{\"passed\":true,\"modulesReleased\":66,\"crossModuleCallers\":64,\"cachedObjectHits\":1,\"nativeCodeAndDataPreserved\":true}\n";
}
