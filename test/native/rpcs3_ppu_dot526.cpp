// SPDX-License-Identifier: MIT
// Production PPU method bodies and native LLVM builders are unchanged. The
// register file and generic expression DSL use minimal LLVM IRBuilder adapters. This runs generated code on ARM64; it is not a game/device test.
#include "rpcs3/Emu/CPU/Backends/AArch64/CellVectorLowering.h"
#include <llvm/ExecutionEngine/ExecutionEngine.h>
#include <llvm/ExecutionEngine/MCJIT.h>
#include <llvm/ExecutionEngine/SectionMemoryManager.h>
#include <llvm/IR/LegacyPassManager.h>
#include <llvm/IR/Verifier.h>
#include <llvm/MC/TargetRegistry.h>
#include <llvm/Support/TargetSelect.h>
#include <llvm/Support/CodeGen.h>
#include <llvm/Support/raw_ostream.h>
#include <llvm/Target/TargetMachine.h>
#include <llvm/TargetParser/Host.h>
#include <llvm/Transforms/Utils/Cloning.h>
#include <algorithm>
#include <array>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <memory>
#include <random>
#include <sstream>
#include <string>
#include <type_traits>
#include <tuple>
#include <vector>
#ifdef __APPLE__
#include <sys/sysctl.h>
#endif

using u8 = std::uint8_t;
using u16 = std::uint16_t;
using u32 = std::uint32_t;
using s16 = std::int16_t;
using s32 = std::int32_t;
namespace utils { bool dotprod = true; bool has_dotprod() { return dotprod; } }
namespace {
[[noreturn]] void fail(const std::string& message) {
    std::fprintf(stderr, "FAIL %s\n", message.c_str()); std::exit(1);
}
llvm::IRBuilder<>* current_ir = nullptr;
bool verified_host_dotprod = false;
struct host_feature_proof {
    bool llvm_key_present = false;
    bool llvm_value = false;
    int darwin_status = -2;
    int darwin_value = 0;
    bool darwin_size_valid = false;
};
host_feature_proof probe_host_dotprod() {
    host_feature_proof proof;
    const auto features = llvm::sys::getHostCPUFeatures();
    const auto feature = features.find("dotprod");
    proof.llvm_key_present = feature != features.end();
    proof.llvm_value = proof.llvm_key_present && feature->second;
#ifdef __APPLE__
    std::size_t size = sizeof(proof.darwin_value);
    proof.darwin_status = ::sysctlbyname("hw.optional.arm.FEAT_DotProd",
        &proof.darwin_value, &size, nullptr, 0);
    proof.darwin_size_valid = size == sizeof(proof.darwin_value);
    verified_host_dotprod = proof.darwin_status == 0 && proof.darwin_size_valid && proof.darwin_value == 1;
#else
    verified_host_dotprod = proof.llvm_value;
#endif
    std::printf("DOTPROD hardware proof: LLVM key=%d value=%d Darwin sysctl_rc=%d size_valid=%d value=%d verified=%d\n",
        proof.llvm_key_present, proof.llvm_value, proof.darwin_status, proof.darwin_size_valid, proof.darwin_value, verified_host_dotprod);
    std::fflush(stdout);
    if (!verified_host_dotprod) fail("DOTPROD hardware capability absent, false or unknown");
    return proof;
}
#if defined(__aarch64__) || defined(__arm64__)
// Called only after the platform reports DOTPROD. The explicit instruction
// proves that the host executes it, independently of MCJIT feature detection.
__attribute__((target("dotprod"), noinline))
void hardware_udot(u32* accumulator, const u8* a, const u8* b) {
    asm volatile("ldr q0, [%0]\n"
                 "ldr q1, [%1]\n"
                 "ldr q2, [%2]\n"
                 "udot v0.4s, v1.16b, v2.16b\n"
                 "str q0, [%0]\n"
                 : : "r"(accumulator), "r"(a), "r"(b) : "v0", "v1", "v2", "memory");
}
#endif
void verify_hardware_udot() {
    if (!verified_host_dotprod) fail("UDOT execution attempted without hardware proof");
#if defined(__aarch64__) || defined(__arm64__)
    for (unsigned sample = 0; sample < 5; ++sample) {
        std::array<u8, 16> a{}, b{};
        std::array<u32, 4> actual{}, expected{};
        for (unsigned i = 0; i < 16; ++i) {
            a[i] = static_cast<u8>(sample * 29 + i * 7);
            b[i] = static_cast<u8>(255 - sample * 13 - i * 5);
        }
        for (unsigned lane = 0; lane < 4; ++lane) {
            actual[lane] = expected[lane] = 0xffffff00u + sample * 19 + lane * 43;
            for (unsigned term = 0; term < 4; ++term)
                expected[lane] += u32(a[lane * 4 + term]) * b[lane * 4 + term];
        }
        hardware_udot(actual.data(), a.data(), b.data());
        if (actual != expected) fail("hardware UDOT control mismatch");
    }
    std::puts("PASS hardware UDOT: five explicit-instruction controls before MCJIT");
#else
    fail("hardware UDOT execution requires ARM64");
#endif
}
template <class T> struct value_t { llvm::Value* value; };
template <class T> llvm::Type* vector_type(llvm::LLVMContext& context) {
    return llvm::FixedVectorType::get(llvm::IntegerType::get(context, 8 * sizeof(std::remove_extent_t<T>)), std::extent_v<T>);
}
template <class T> value_t<T> operator<<(value_t<T> a, unsigned bits) {
    return {current_ir->CreateShl(a.value, bits)};
}
template <class T> value_t<T> operator>>(value_t<T> a, unsigned bits) {
    if constexpr (std::is_signed_v<std::remove_extent_t<T>>) return {current_ir->CreateAShr(a.value, bits)};
    else return {current_ir->CreateLShr(a.value, bits)};
}
template <class T> value_t<T> operator*(value_t<T> a, value_t<T> b) { return {current_ir->CreateMul(a.value, b.value)}; }
template <class T> value_t<T> operator+(value_t<T> a, value_t<T> b) { return {current_ir->CreateAdd(a.value, b.value)}; }
template <class T> value_t<T> eval(value_t<T> a) { return a; }
template <class T, class U> value_t<T> bitcast(value_t<U> a) {
    return {current_ir->CreateBitCast(a.value, vector_type<T>(current_ir->getContext()))};
}
template <class T, class U> value_t<T> noncast(value_t<U> a) { return bitcast<T>(a); }
struct ppu_opcode_t { unsigned va = 0, vb = 1, vc = 2, vd = 3; };
struct register_adapter {
    llvm::IRBuilder<>* m_ir;
    std::array<llvm::Value*, 4> registers;
    template <class T> value_t<T> get_vr(unsigned index) {
        return {m_ir->CreateBitCast(registers.at(index), vector_type<T>(m_ir->getContext()))};
    }
    template <class T> std::pair<value_t<T>, value_t<T>> get_vrs(unsigned a, unsigned b) {
        return {get_vr<T>(a), get_vr<T>(b)};
    }
    template <class T> std::tuple<value_t<T>, value_t<T>, value_t<T>> get_vrs(unsigned a, unsigned b, unsigned c) {
        return {get_vr<T>(a), get_vr<T>(b), get_vr<T>(c)};
    }
    template <class T> value_t<T> value(llvm::Value* raw) { return {raw}; }
    template <class T> void set_vr(unsigned index, value_t<T> raw) { registers.at(index) = raw.value; }
};
struct before_translator : register_adapter {
    void VMSUMUBM(ppu_opcode_t); void VMSUMMBM(ppu_opcode_t);
    void VMSUMUHM(ppu_opcode_t); void VMSUMSHM(ppu_opcode_t);
};
struct after_translator : register_adapter {
    void VMSUMUBM(ppu_opcode_t); void VMSUMMBM(ppu_opcode_t);
    void VMSUMUHM(ppu_opcode_t); void VMSUMSHM(ppu_opcode_t);
};
#define PPUTranslator before_translator
#include "rpcs3_ppu_dot526_before.inc"
#undef PPUTranslator
#define ARCH_ARM64 1
#define PPUTranslator after_translator
#include "rpcs3_ppu_dot526_after.inc"
#undef PPUTranslator
#undef ARCH_ARM64

constexpr std::array<const char*, 4> names = {"VMSUMUBM", "VMSUMMBM", "VMSUMUHM", "VMSUMSHM"};
using kernel = void(*)(u8*, const u8*, const u8*, const u8*);
using block = std::array<u8, 16>;
struct data_case { block a, b, c; };
template <class Translator> void translate(Translator& translator, unsigned operation) {
    switch (operation) {
    case 0: translator.VMSUMUBM({}); break;
    case 1: translator.VMSUMMBM({}); break;
    case 2: translator.VMSUMUHM({}); break;
    case 3: translator.VMSUMSHM({}); break;
    default: fail("operation");
    }
}
template <class Translator> std::unique_ptr<llvm::Module> build(llvm::LLVMContext& context, unsigned operation) {
    auto module = std::make_unique<llvm::Module>(names[operation], context);
    auto* pointer = llvm::PointerType::getUnqual(context);
    auto* function = llvm::Function::Create(llvm::FunctionType::get(llvm::Type::getVoidTy(context),
        {pointer, pointer, pointer, pointer}, false), llvm::GlobalValue::ExternalLinkage, "run", *module);
    auto* entry = llvm::BasicBlock::Create(context, "entry", function);
    llvm::IRBuilder<> ir(entry);
    current_ir = &ir;
    Translator translator;
    translator.m_ir = &ir;
    auto* bytes = llvm::FixedVectorType::get(llvm::Type::getInt8Ty(context), 16);
    for (unsigned i = 0; i < 3; ++i) {
        auto* load = ir.CreateLoad(bytes, function->getArg(i + 1));
        load->setAlignment(llvm::Align(1));
        translator.registers[i] = load;
    }
    translate(translator, operation);
    ir.CreateAlignedStore(ir.CreateBitCast(translator.registers[3], bytes), function->getArg(0), llvm::Align(1));
    ir.CreateRetVoid();
    current_ir = nullptr;
    if (llvm::verifyModule(*module, &llvm::errs())) fail("production method IR verification");
    return module;
}
struct assembly_record { std::string text; unsigned instructions; };
assembly_record assembly(llvm::Module& module, bool dotprod) {
    const char* triple = "aarch64-unknown-linux-android"; // Actual Core JIT triple, not the app platform.
    std::string error;
    auto* target = llvm::TargetRegistry::lookupTarget(triple, error);
    if (!target) fail(error);
    std::unique_ptr<llvm::TargetMachine> machine(target->createTargetMachine(llvm::Triple(triple),
        dotprod ? "apple-m4" : "cortex-a53", dotprod ? "+neon,+dotprod,-sve,-sve2" : "+neon,-dotprod,-sve,-sve2",
        llvm::TargetOptions(), llvm::Reloc::PIC_, llvm::CodeModel::Small, llvm::CodeGenOptLevel::Aggressive, true));
    module.setDataLayout(machine->createDataLayout());
    llvm::SmallString<4096> buffer;
    llvm::raw_svector_ostream stream(buffer);
    llvm::legacy::PassManager passes;
    if (machine->addPassesToEmitFile(passes, stream, nullptr, llvm::CodeGenFileType::AssemblyFile)) fail("assembly emitter");
    passes.run(module);
    std::string text(buffer.str());
    unsigned count = 0;
    std::istringstream lines(text);
    for (std::string line; std::getline(lines, line);) {
        if (line.empty() || (line.front() != '\t' && line.front() != ' ')) continue;
        const auto first = line.find_first_not_of("\t ");
        if (first != std::string::npos && line[first] != '.' && line[first] != '/' && line[first] != ';') ++count;
    }
    return {std::move(text), count};
}
struct compiled {
    std::unique_ptr<llvm::ExecutionEngine> engine;
    kernel function;
};
compiled compile(std::unique_ptr<llvm::Module> module) {
    if (!verified_host_dotprod) fail("MCJIT DOTPROD target attempted without hardware proof");
    module->setTargetTriple(llvm::Triple(llvm::sys::getDefaultTargetTriple()));
    std::string error;
    std::unique_ptr<llvm::ExecutionEngine> engine(llvm::EngineBuilder(std::move(module))
        .setErrorStr(&error).setEngineKind(llvm::EngineKind::JIT)
        .setMCJITMemoryManager(std::make_unique<llvm::SectionMemoryManager>())
        .setOptLevel(llvm::CodeGenOptLevel::Aggressive).setMCPU(llvm::sys::getHostCPUName().str())
        .setMAttrs(std::vector<std::string>{"+neon", "+dotprod", "-sve", "-sve2"}).create());
    if (!engine) fail(error);
    engine->finalizeObject();
    auto function = reinterpret_cast<kernel>(engine->getFunctionAddress("run"));
    if (!function) fail("missing entry");
    return {std::move(engine), function};
}
u16 little16(const u8* p) { return u16(p[0]) | (u16(p[1]) << 8); }
u32 little32(const u8* p) { return u32(p[0]) | (u32(p[1]) << 8) | (u32(p[2]) << 16) | (u32(p[3]) << 24); }
void store32(u8* p, u32 value) { for (unsigned i = 0; i < 4; ++i) p[i] = static_cast<u8>(value >> (8 * i)); }
block reference(const data_case& input, unsigned operation) {
    block result{};
    for (unsigned lane = 0; lane < 4; ++lane) {
        std::int64_t sum = little32(input.c.data() + lane * 4);
        const unsigned terms = operation < 2 ? 4 : 2;
        for (unsigned term = 0; term < terms; ++term) {
            const unsigned offset = lane * 4 + term * (operation < 2 ? 1 : 2);
            if (operation == 0) sum += unsigned(input.a[offset]) * unsigned(input.b[offset]);
            if (operation == 1) sum += std::int64_t(static_cast<std::int8_t>(input.a[offset])) * unsigned(input.b[offset]);
            if (operation == 2) sum += std::int64_t(little16(input.a.data() + offset)) * little16(input.b.data() + offset);
            if (operation == 3) sum += std::int64_t(static_cast<s16>(little16(input.a.data() + offset))) * static_cast<s16>(little16(input.b.data() + offset));
        }
        store32(result.data() + lane * 4, static_cast<u32>(sum));
    }
    return result;
}
// Independent guest-big-endian model; reversing a register to/from the host
// representation must preserve all byte/halfword grouping and accumulator bits.
block guest_reference(data_case input, unsigned operation) {
    auto be16 = [](const u8* p) { return u16((u16(p[0]) << 8) | p[1]); };
    block result{};
    for (unsigned lane = 0; lane < 4; ++lane) {
        const unsigned start = lane * 4;
        std::int64_t sum = (u32(input.c[start]) << 24) | (u32(input.c[start+1]) << 16) | (u32(input.c[start+2]) << 8) | input.c[start+3];
        for (unsigned term = 0; term < (operation < 2 ? 4u : 2u); ++term) {
            const unsigned offset = start + term * (operation < 2 ? 1 : 2);
            if (operation == 0) sum += unsigned(input.a[offset]) * unsigned(input.b[offset]);
            if (operation == 1) sum += std::int64_t(static_cast<std::int8_t>(input.a[offset])) * unsigned(input.b[offset]);
            if (operation == 2) sum += std::int64_t(be16(input.a.data() + offset)) * be16(input.b.data() + offset);
            if (operation == 3) sum += std::int64_t(static_cast<s16>(be16(input.a.data() + offset))) * static_cast<s16>(be16(input.b.data() + offset));
        }
        const u32 value = static_cast<u32>(sum);
        for (unsigned i = 0; i < 4; ++i) result[start + i] = static_cast<u8>(value >> (24 - 8*i));
    }
    return result;
}
double time_kernel(kernel function, const std::vector<data_case>& corpus) {
    block out{};
    const auto started = std::chrono::steady_clock::now();
    for (unsigned loop = 0; loop < 256; ++loop)
        for (unsigned i = 0; i < 4096; ++i) {
            const auto& input = corpus[i];
            function(out.data(), input.a.data(), input.b.data(), input.c.data());
        }
    const auto stopped = std::chrono::steady_clock::now();
    static volatile u32 sink = 0;
    sink = little32(out.data());
    (void)sink;
    return std::chrono::duration<double, std::milli>(stopped - started).count();
}
double median(std::vector<double> values) {
    std::sort(values.begin(), values.end()); return (values[values.size()/2] + values[(values.size()-1)/2]) / 2.;
}
}
int main(int argc, char** argv) {
    if (argc != 3) fail("expected result.json and assembly directory");
    llvm::InitializeAllTargetInfos(); llvm::InitializeAllTargets(); llvm::InitializeAllTargetMCs();
    llvm::InitializeAllAsmPrinters(); llvm::InitializeNativeTargetAsmParser(); LLVMLinkInMCJIT();
#if !defined(__aarch64__) && !defined(__arm64__)
    fail("generated NEON execution requires an ARM64 host; no emulated success");
#endif
    const auto host_proof = probe_host_dotprod();
    verify_hardware_udot();
    llvm::LLVMContext context;
    std::vector<data_case> corpus;
    for (unsigned a = 0; a < 256; ++a)
        for (unsigned b = 0; b < 256; ++b) {
            data_case input{};
            for (unsigned i = 0; i < 16; ++i) { input.a[i] = a; input.b[i] = b; input.c[i] = static_cast<u8>(i * 29 + a + b); }
            corpus.push_back(input);
        }
    const std::array<u16, 9> edges = {0, 1, 127, 255, 0x7fff, 0x8000, 0x8001, 0xfffe, 0xffff};
    for (auto a : edges) for (auto b : edges) for (u32 c : {0u, 1u, 0x7fffffffu, 0x80000000u, 0xffffffffu}) {
        data_case input{};
        for (unsigned i = 0; i < 16; i += 2) { input.a[i] = static_cast<u8>(a); input.a[i+1] = static_cast<u8>(a >> 8); input.b[i] = static_cast<u8>(b); input.b[i+1] = static_cast<u8>(b >> 8); }
        for (unsigned i = 0; i < 16; i += 4) store32(input.c.data() + i, c);
        corpus.push_back(input);
    }
    std::mt19937_64 random(0x526);
    for (unsigned n = 0; n < 10000; ++n) {
        data_case input{};
        for (auto* bytes : {&input.a, &input.b, &input.c}) for (auto& b : *bytes) b = static_cast<u8>(random());
        corpus.push_back(input);
    }
    std::ofstream json(argv[1]);
    json << "{\n  \"schema\":1,\n  \"host_cpu\":\"" << llvm::sys::getHostCPUName().str()
         << "\",\n  \"host_triple\":\"" << llvm::sys::getDefaultTargetTriple()
         << "\",\n  \"dotprod_hardware_proof\":{\"llvm_key_present\":" << (host_proof.llvm_key_present ? "true" : "false")
         << ",\"llvm_value\":" << (host_proof.llvm_value ? "true" : "false")
         << ",\"darwin_sysctl_status\":" << host_proof.darwin_status
         << ",\"darwin_sysctl_size_valid\":" << (host_proof.darwin_size_valid ? "true" : "false")
         << ",\"darwin_sysctl_value\":" << host_proof.darwin_value
         << ",\"hardware_verified\":true,\"explicit_udot_controls\":5,\"jit_attributes\":\"+neon,+dotprod,-sve,-sve2\"}"
         << ",\n  \"game_or_device_tested\":false,\n  \"cases_per_operation\":" << corpus.size() << ",\n  \"operations\":[\n";
    for (unsigned operation = 0; operation < 4; ++operation) {
        utils::dotprod = true;
        auto before = build<before_translator>(context, operation);
        auto after = build<after_translator>(context, operation);
        utils::dotprod = false;
        auto fallback = build<after_translator>(context, operation);
        auto before_assembly_module = llvm::CloneModule(*before);
        auto after_assembly_module = llvm::CloneModule(*after);
        auto fallback_assembly_module = llvm::CloneModule(*fallback);
        const auto old_assembly = assembly(*before_assembly_module, true);
        const auto new_assembly = assembly(*after_assembly_module, true);
        const auto fallback_assembly = assembly(*fallback_assembly_module, false);
        std::ofstream(std::string(argv[2]) + "/" + names[operation] + "-before.s") << old_assembly.text;
        std::ofstream(std::string(argv[2]) + "/" + names[operation] + "-after.s") << new_assembly.text;
        std::ofstream(std::string(argv[2]) + "/" + names[operation] + "-fallback.s") << fallback_assembly.text;
        if (operation < 2 && new_assembly.text.find("udot") == std::string::npos) fail("DOTPROD missing");
        if (fallback_assembly.text.find("udot") != std::string::npos) fail("DOTPROD reached generic ARM fallback");
        if (operation >= 2 && new_assembly.text.find(operation == 2 ? "umull" : "smull") == std::string::npos) fail("widening multiply missing");
        if (new_assembly.text.find("\tbl\t") != std::string::npos) fail("unexpected runtime helper call");
        auto original = compile(std::move(before));
        auto candidate = compile(std::move(after));
        auto legacy_fallback = compile(std::move(fallback));
        for (const auto& input : corpus) {
            const auto expected = reference(input, operation);
            for (auto function : {original.function, candidate.function, legacy_fallback.function}) {
                block result{};
                function(result.data(), input.a.data(), input.b.data(), input.c.data());
                if (result != expected) fail(std::string(names[operation]) + " differential or edge-case mismatch");
            }
            auto reversed = input;
            for (auto* bytes : {&reversed.a, &reversed.b, &reversed.c}) std::reverse(bytes->begin(), bytes->end());
            block result{};
            candidate.function(result.data(), reversed.a.data(), reversed.b.data(), reversed.c.data());
            std::reverse(result.begin(), result.end());
            if (result != guest_reference(input, operation)) fail(std::string(names[operation]) + " endian mismatch");
        }
        std::vector<double> old_times, new_times;
        for (unsigned round = 0; round < 12; ++round) {
            double old_ms, new_ms;
            if (round % 2 == 0) { old_ms = time_kernel(original.function, corpus); new_ms = time_kernel(candidate.function, corpus); }
            else { new_ms = time_kernel(candidate.function, corpus); old_ms = time_kernel(original.function, corpus); }
            if (round >= 2) { old_times.push_back(old_ms); new_times.push_back(new_ms); }
        }
        if (operation) json << ",\n";
        json << "    {\"name\":\"" << names[operation] << "\",\"before_instructions\":" << old_assembly.instructions
             << ",\"after_instructions\":" << new_assembly.instructions << ",\"fallback_instructions\":" << fallback_assembly.instructions
             << ",\"host_median_before_ms\":" << median(old_times) << ",\"host_median_after_ms\":" << median(new_times)
             << ",\"calls_per_round\":1048576,\"rounds\":12,\"discarded_rounds\":2,\"bit_exact\":true,\"big_endian_exact\":true}";
        std::printf("PASS %s: %zu corpus x before/after/fallback + guest big-endian, AArch64 instructions %u -> %u (fallback %u), host median %.6f -> %.6f ms\n",
            names[operation], corpus.size(), old_assembly.instructions, new_assembly.instructions, fallback_assembly.instructions, median(old_times), median(new_times));
    }
    json << "\n  ]\n}\n";
}
