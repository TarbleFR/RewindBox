// Lot 10: the configuration a cached MoltenVK shader library is kept under (SPIRVToMSLConversionConfiguration::cacheKey,
// fifth part of build-utils/melonx/moltenvk/rewindbox-moltenvk.patch) against the whole configuration (as shipped), on
// MoltenVK's own matches() and alignWith() compiled from the patched tree. No Metal: any host.
//
// A pipeline cache lookup is cached.matches(candidate), then candidate.alignWith(cached); the candidate's used flags are
// what MoltenVK binds resources by afterwards. For configurations built the way MVKPipelineLayout builds them for MeloNX's
// layouts (every binding for each of the five stages) and for adversarial ones (matching duplicates with different flags
// in every order, immutable samplers, other-stage flags), the program requires:
//   P1  cached.matches(candidate) == cached.cacheKey().matches(candidate)
//   P2  the used flags of every input, output and resource binding of the candidate after alignWith(cached) and after
//       alignWith(cached.cacheKey()) are the same
//   P3  cacheKey() of a key is that key (the same bindings in the same order)
//   P4  a key keeps the options, inputs, outputs, discrete sets and dynamic buffer descriptors
//   P5  between two keys (a merge compares a cached configuration with another cache's): never a match the whole
//       configurations do not have; and the same answer when both are of one shader (its used bindings are then the same
//       function of stage, set and binding)
// and that a prune without the order rule (every unused binding dropped) is caught by P2 on the adversarial cases: the
// properties can fail. Prints the counts and the kept share of a MeloNX-shaped layout as one JSON line.
//
// Usage: cache_key_property_test <seed> <rounds>
#include "SPIRVToMSLConverter.h"

#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <vector>

using namespace mvk;
namespace spvc = SPIRV_CROSS_NAMESPACE;

static uint64_t state = 0x9E3779B97F4A7C15ull;
static uint64_t next() {
    state ^= state << 13; state ^= state >> 7; state ^= state << 17;
    return state;
}
static uint32_t below(uint32_t n) { return n ? (uint32_t)(next() % n) : 0; }
static bool chance(uint32_t percent) { return below(100) < percent; }

[[noreturn]] static void fail(const char* property, uint64_t round, const char* detail) {
    fprintf(stderr, "FAILED %s at round %llu: %s\n", property, (unsigned long long)round, detail);
    exit(1);
}

static const spv::ExecutionModel kStages[5] = {spv::ExecutionModelVertex, spv::ExecutionModelTessellationControl,
                                               spv::ExecutionModelTessellationEvaluation, spv::ExecutionModelFragment,
                                               spv::ExecutionModelGLCompute};

static MSLResourceBinding binding(int stage, spvc::SPIRType::BaseType type, uint32_t set, uint32_t number, uint32_t index) {
    MSLResourceBinding rb;
    rb.resourceBinding.stage = kStages[stage];
    rb.resourceBinding.basetype = type;
    rb.resourceBinding.desc_set = set;
    rb.resourceBinding.binding = number;
    rb.resourceBinding.count = 1;
    rb.resourceBinding.msl_buffer = index;
    rb.resourceBinding.msl_texture = index;
    rb.resourceBinding.msl_sampler = index;
    return rb;
}

// MeloNX's sets as MVKPipelineLayout::populateShaderConversionConfig lists them with argument buffers: for the vertex and
// the fragment stage of a program, 18 uniform buffers (set 0), 16 storage buffers (set 1), 32 textures and 32 buffer
// textures (set 2), 16 images and 16 buffer images (set 3); each binding once per Metal stage. shift moves the Metal
// indices (another layout).
static void meloNXLayout(SPIRVToMSLConversionConfiguration& config, uint32_t shift, bool allStages) {
    static const int programStages[2] = {0, 4};   // GpuAccessorBase stage indices: vertex 0, fragment 4
    struct Kind { uint32_t set, perStage, first, stride; spvc::SPIRType::BaseType type; };
    const Kind kinds[] = {
        {0, 18, 1, 18, spvc::SPIRType::Void}, {1, 16, 0, 16, spvc::SPIRType::Void},
        {2, 32, 0, 64, spvc::SPIRType::SampledImage}, {2, 32, 32, 64, spvc::SPIRType::Image},
        {3, 16, 0, 32, spvc::SPIRType::Image}, {3, 16, 16, 32, spvc::SPIRType::Image},
    };
    uint32_t index = shift;
    for (int stage = 0; stage < 5; stage++)
        config.resourceBindings.push_back(binding(stage, spvc::SPIRType::Void, 0, 0, index));   // the support buffer
    index++;
    for (const Kind& kind : kinds) {
        for (int program : programStages) {
            for (uint32_t i = 0; i < kind.perStage; i++) {
                uint32_t number = kind.first + program * kind.stride + i;
                for (int stage = 0; stage < 5; stage++) {
                    bool applies = (program == 0 && stage == 0) || (program == 4 && stage == 3);
                    if (allStages || applies) config.resourceBindings.push_back(binding(stage, kind.type, kind.set, number, index));
                }
                index++;
            }
        }
    }
}

static void interface(std::vector<MSLShaderInterfaceVariable>& variables, uint32_t count) {
    for (uint32_t i = 0; i < count; i++) {
        MSLShaderInterfaceVariable variable;
        variable.shaderVar.location = i;
        variable.shaderVar.component = 0;
        variable.shaderVar.vecsize = 1 + below(4);
        variable.binding = below(3);
        variable.outIsUsedByShader = chance(50);
        variables.push_back(variable);
    }
}

// Whether the shader of this round uses a binding: a function of stage, set and binding only, as SPIRV-Cross reports it.
static uint64_t usageSalt = 0;
static bool shaderUses(const MSLResourceBinding& rb) {
    uint64_t h = usageSalt ^ ((uint64_t)rb.resourceBinding.stage * 0x100000001B3ull) ^ ((uint64_t)rb.resourceBinding.desc_set << 40) ^
                 ((uint64_t)rb.resourceBinding.binding << 8);
    h ^= h >> 29; h *= 0xBF58476D1CE4E5B9ull; h ^= h >> 32;
    return (h % 100) < 8;
}

static SPIRVToMSLConversionConfiguration cachedConfiguration(int entryStage, bool adversarial, uint32_t shift, bool allStages) {
    SPIRVToMSLConversionConfiguration config;
    config.options.entryPointStage = kStages[entryStage];
    config.options.entryPointName = "main0";
    meloNXLayout(config, shift, allStages);
    interface(config.shaderInputs, 4 + below(12));
    interface(config.shaderOutputs, 1 + below(8));
    for (auto& rb : config.resourceBindings) {
        // The entry stage's flags come from the conversion; the others are what earlier stages left (anything).
        rb.outIsUsedByShader = rb.resourceBinding.stage == kStages[entryStage] ? shaderUses(rb) : chance(adversarial ? 30 : 3);
        if (chance(2)) {   // an immutable sampler
            rb.requiresConstExprSampler = true;
            rb.constExprSampler.max_anisotropy = (int)below(3);
        }
    }
    if (adversarial) {
        // Matching duplicates with any flags, anywhere: the last match decides alignWith().
        uint32_t extra = 1 + below(24);
        for (uint32_t i = 0; i < extra; i++) {
            MSLResourceBinding copy = config.resourceBindings[below((uint32_t)config.resourceBindings.size())];
            copy.outIsUsedByShader = chance(50);
            config.resourceBindings.insert(config.resourceBindings.begin() + below((uint32_t)config.resourceBindings.size() + 1), copy);
        }
    }
    if (chance(20)) config.discreteDescriptorSets.push_back(below(4));
    if (chance(20)) {
        DescriptorBinding db;
        db.stage = kStages[chance(70) ? entryStage : (int)below(5)];
        db.descriptorSet = below(4);
        db.binding = below(64);
        db.index = below(8);
        config.dynamicBufferDescriptors.push_back(db);
    }
    return config;
}

static SPIRVToMSLConversionConfiguration candidateFrom(const SPIRVToMSLConversionConfiguration& cached) {
    SPIRVToMSLConversionConfiguration candidate = cached;
    for (auto& rb : candidate.resourceBindings) rb.outIsUsedByShader = chance(50);   // whatever the previous stage left
    for (auto& si : candidate.shaderInputs) si.outIsUsedByShader = chance(50);
    for (auto& so : candidate.shaderOutputs) so.outIsUsedByShader = chance(50);
    uint32_t mutations = below(4);   // 0: the same layout (a cache hit)
    for (uint32_t m = 0; m < mutations && !candidate.resourceBindings.empty(); m++) {
        uint32_t at = below((uint32_t)candidate.resourceBindings.size());
        switch (below(9)) {
            case 0: candidate.resourceBindings[at].resourceBinding.msl_buffer += 1; break;
            case 1: candidate.resourceBindings[at].resourceBinding.binding += 1000; break;
            case 2: candidate.resourceBindings.erase(candidate.resourceBindings.begin() + at); break;
            case 3: candidate.resourceBindings.push_back(candidate.resourceBindings[at]); break;
            case 4: candidate.resourceBindings[at].requiresConstExprSampler = !candidate.resourceBindings[at].requiresConstExprSampler; break;
            case 5: candidate.resourceBindings[at].constExprSampler.max_anisotropy += 1; break;
            case 6: if (!candidate.shaderInputs.empty()) candidate.shaderInputs[below((uint32_t)candidate.shaderInputs.size())].binding += 7; break;
            case 7: candidate.options.mslOptions.msl_version += 1; break;
            case 8: if (!candidate.dynamicBufferDescriptors.empty()) candidate.dynamicBufferDescriptors.clear(); else candidate.discreteDescriptorSets.clear(); break;
        }
    }
    return candidate;
}

static bool sameBinding(const MSLResourceBinding& a, const MSLResourceBinding& b) {
    return memcmp(&a.resourceBinding, &b.resourceBinding, sizeof(a.resourceBinding)) == 0 &&
           memcmp(&a.constExprSampler, &b.constExprSampler, sizeof(a.constExprSampler)) == 0 &&
           a.requiresConstExprSampler == b.requiresConstExprSampler && a.outIsUsedByShader == b.outIsUsedByShader;
}

static bool sameFlags(const SPIRVToMSLConversionConfiguration& a, const SPIRVToMSLConversionConfiguration& b) {
    if (a.resourceBindings.size() != b.resourceBindings.size() || a.shaderInputs.size() != b.shaderInputs.size() ||
        a.shaderOutputs.size() != b.shaderOutputs.size()) return false;
    for (size_t i = 0; i < a.resourceBindings.size(); i++) if (a.resourceBindings[i].outIsUsedByShader != b.resourceBindings[i].outIsUsedByShader) return false;
    for (size_t i = 0; i < a.shaderInputs.size(); i++) if (a.shaderInputs[i].outIsUsedByShader != b.shaderInputs[i].outIsUsedByShader) return false;
    for (size_t i = 0; i < a.shaderOutputs.size(); i++) if (a.shaderOutputs[i].outIsUsedByShader != b.shaderOutputs[i].outIsUsedByShader) return false;
    return true;
}

// The prune this change must not be: every unused binding dropped, whatever stands before it.
static SPIRVToMSLConversionConfiguration naiveKey(const SPIRVToMSLConversionConfiguration& config) {
    SPIRVToMSLConversionConfiguration key = config;
    key.resourceBindings.clear();
    for (const auto& rb : config.resourceBindings) if (rb.outIsUsedByShader) key.resourceBindings.push_back(rb);
    return key;
}

int main(int argc, char** argv) {
    if (argc < 3) { fprintf(stderr, "usage: cache_key_property_test <seed> <rounds>\n"); return 2; }
    state ^= strtoull(argv[1], nullptr, 10) * 0x2545F4914F6CDD1Dull;
    uint64_t rounds = strtoull(argv[2], nullptr, 10);
    uint64_t matches = 0, mismatches = 0, alignChecks = 0, mergePairs = 0, mergeMatches = 0, naiveCaught = 0, keptOrderRule = 0;
    uint64_t wholeBindings = 0, keyBindings = 0;

    // The MeloNX-shaped layout, as counted in the patch: the bindings of one cached library, whole and as a key.
    usageSalt = 12345;
    SPIRVToMSLConversionConfiguration shape = cachedConfiguration(3, false, 0, true);
    for (auto& rb : shape.resourceBindings) if (rb.resourceBinding.stage != kStages[3]) rb.outIsUsedByShader = false;
    size_t shapeWhole = shape.resourceBindings.size(), shapeKey = shape.cacheKey().resourceBindings.size();

    for (uint64_t round = 0; round < rounds; round++) {
        usageSalt = next();
        bool adversarial = round % 2 == 1;
        int entryStage = (int)below(5);
        bool allStages = chance(80);
        SPIRVToMSLConversionConfiguration cached = cachedConfiguration(entryStage, adversarial, below(3), allStages);
        SPIRVToMSLConversionConfiguration key = cached.cacheKey();
        wholeBindings += cached.resourceBindings.size();
        keyBindings += key.resourceBindings.size();
        for (const auto& rb : key.resourceBindings) if (!rb.outIsUsedByShader) keptOrderRule++;

        // P3, P4.
        SPIRVToMSLConversionConfiguration again = key.cacheKey();
        if (again.resourceBindings.size() != key.resourceBindings.size()) fail("P3", round, "the key of a key has another size");
        for (size_t i = 0; i < key.resourceBindings.size(); i++)
            if (!sameBinding(again.resourceBindings[i], key.resourceBindings[i])) fail("P3", round, "the key of a key differs");
        if (!key.options.matches(cached.options) || !cached.options.matches(key.options) ||
            key.options.entryPointName != cached.options.entryPointName) fail("P4", round, "options");
        if (key.shaderInputs.size() != cached.shaderInputs.size() || key.shaderOutputs.size() != cached.shaderOutputs.size() ||
            key.discreteDescriptorSets != cached.discreteDescriptorSets ||
            key.dynamicBufferDescriptors.size() != cached.dynamicBufferDescriptors.size()) fail("P4", round, "another member's size");
        for (size_t i = 0; i < key.shaderInputs.size(); i++)
            if (!key.shaderInputs[i].matches(cached.shaderInputs[i]) || key.shaderInputs[i].outIsUsedByShader != cached.shaderInputs[i].outIsUsedByShader) fail("P4", round, "inputs");
        for (size_t i = 0; i < key.shaderOutputs.size(); i++)
            if (!key.shaderOutputs[i].matches(cached.shaderOutputs[i]) || key.shaderOutputs[i].outIsUsedByShader != cached.shaderOutputs[i].outIsUsedByShader) fail("P4", round, "outputs");
        for (size_t i = 0; i < key.dynamicBufferDescriptors.size(); i++)
            if (!key.dynamicBufferDescriptors[i].matches(cached.dynamicBufferDescriptors[i])) fail("P4", round, "dynamic buffer descriptors");
        // Every kept binding is one of the configuration's, in its order.
        size_t at = 0;
        for (const auto& rb : key.resourceBindings) {
            while (at < cached.resourceBindings.size() && !sameBinding(cached.resourceBindings[at], rb)) at++;
            if (at == cached.resourceBindings.size()) fail("P4", round, "a kept binding is not the configuration's, or out of order");
            at++;
        }

        for (int c = 0; c < 6; c++) {
            SPIRVToMSLConversionConfiguration candidate = candidateFrom(cached);
            // P1.
            bool whole = cached.matches(candidate), pruned = key.matches(candidate);
            if (whole != pruned) fail("P1", round, whole ? "the key misses a configuration the whole matches" : "the key matches one the whole does not");
            (whole ? matches : mismatches)++;
            // P2 (alignWith is only called after a match, but it must agree whatever the answer).
            SPIRVToMSLConversionConfiguration a = candidate, b = candidate, n = candidate;
            a.alignWith(cached);
            b.alignWith(key);
            if (!sameFlags(a, b)) fail("P2", round, "the candidate's used flags differ after alignWith");
            alignChecks++;
            n.alignWith(naiveKey(cached));
            if (!sameFlags(a, n)) naiveCaught++;
        }

        // P5: another cache's entry of the same shader (the same usage function), on the same or another layout.
        for (int c = 0; c < 2; c++) {
            uint64_t salt = usageSalt;
            SPIRVToMSLConversionConfiguration other = cachedConfiguration(entryStage, adversarial, c == 0 ? 0 : below(3), allStages);
            usageSalt = salt;
            other.options = cached.options;
            other.shaderInputs = cached.shaderInputs;
            other.shaderOutputs = cached.shaderOutputs;
            other.discreteDescriptorSets = cached.discreteDescriptorSets;
            other.dynamicBufferDescriptors = cached.dynamicBufferDescriptors;
            bool whole = cached.matches(other), pruned = key.matches(other.cacheKey());
            if (pruned && !whole) fail("P5", round, "two keys match where the whole configurations do not");
            if (!adversarial && whole != pruned) fail("P5", round, "two keys of one shader do not answer as the whole configurations");
            mergePairs++;
            if (whole) mergeMatches++;
        }
        // P5, any two configurations: a key pair is never looser.
        {
            SPIRVToMSLConversionConfiguration other = cachedConfiguration((int)below(5), true, below(3), chance(50));
            if (key.matches(other.cacheKey()) && !cached.matches(other)) fail("P5", round, "two unrelated keys match where the whole configurations do not");
        }
    }
    if (rounds >= 200 && naiveCaught == 0) fail("control", rounds, "the prune without the order rule was never caught: the properties cannot fail");
    if (rounds >= 200 && (matches == 0 || mismatches == 0)) fail("control", rounds, "the candidates never matched, or always did");
    if (rounds >= 200 && keptOrderRule == 0) fail("control", rounds, "the order rule never kept an unused binding");
    printf("{\"result\": \"passed\", \"rounds\": %llu, \"lookupsMatching\": %llu, \"lookupsNotMatching\": %llu, \"alignChecks\": %llu, "
           "\"mergePairs\": %llu, \"mergePairsMatching\": %llu, \"naivePruneCaught\": %llu, \"unusedKeptByOrderRule\": %llu, "
           "\"bindingsWhole\": %llu, \"bindingsKept\": %llu, \"meloNXShape\": {\"bindingsWhole\": %zu, \"bindingsKept\": %zu, "
           "\"bytesPerBindingInMemory\": %zu}}\n",
           (unsigned long long)rounds, (unsigned long long)matches, (unsigned long long)mismatches, (unsigned long long)alignChecks,
           (unsigned long long)mergePairs, (unsigned long long)mergeMatches, (unsigned long long)naiveCaught,
           (unsigned long long)keptOrderRule, (unsigned long long)wholeBindings, (unsigned long long)keyBindings, shapeWhole, shapeKey,
           sizeof(MSLResourceBinding));
    return 0;
}
