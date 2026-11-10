// Lot 8: Metal library sharing between MeloNX's pipeline caches, on MoltenVK v1.4.2 (unpatched) through Vulkan.
//
// MoltenVK keeps the Metal libraries it compiles per VkPipelineCache (MVKPipelineCache::_shaderCache, per shader module
// code hash, each library for one SPIR-V to MSL configuration). MeloNX creates pipelines in a main cache (render thread)
// and in one cache per background worker; a worker first looks the pipeline up in the main cache with
// VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED_BIT (adapt_worker_main_cache_lookup), else compiles in its own.
// This program replays that scheme with two workers (A, B) and the synthetic shaders of shaders.spvz: for each of the 12
// fragment shaders, five variants (two colour formats, blending on/off, the vertex-buffer vertex shader) alternate
// between A and B. Strategies (argv[4]): none (as delivered: a worker cache reaches main only at the close), merge (the
// worker merges its cache into main after each pipeline it compiled), reset (merge, then the worker cache is replaced by
// an empty one), every8 (merge after every 8 own compilations), concurrent (A and B create the first variant of each
// fragment at the same moment, then merge), one (every variant on worker A: the fewest libraries, the lower bound). Printed: MoltenVK's own counts of SPIR-V conversions, MSL library compiles
// and pipeline compiles, main lookups served, merges (count, total and longest time, worker libraries merged), cache
// data sizes and the process footprint.
//
// Usage: mvk_library_share_test <shaders.spvz> <salt> <output.json> <strategy>
#include <vulkan/vulkan.h>
#ifdef __APPLE__
#include <MoltenVK/mvk_private_api.h>
#endif
#include <zlib.h>

#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <thread>
#include <vector>
#include <algorithm>
#include <mutex>
#include <condition_variable>
#ifdef __APPLE__
#include <mach/mach.h>
#endif

static double nowMs() {
    using namespace std::chrono;
    return duration<double, std::milli>(steady_clock::now().time_since_epoch()).count();
}

[[noreturn]] static void fail(const std::string& message) {
    fprintf(stderr, "mvk_archive_test: %s\n", message.c_str());
    exit(3);
}

static void check(VkResult result, const char* what) {
    if (result != VK_SUCCESS) fail(std::string(what) + " returned " + std::to_string((int)result));
}

static uint64_t fnv(uint64_t hash, const void* data, size_t length) {
    const uint8_t* bytes = (const uint8_t*)data;
    for (size_t i = 0; i < length; i++) { hash ^= bytes[i]; hash *= 1099511628211ull; }
    return hash;
}

struct Shader { std::string name; std::vector<uint32_t> words; };

static std::vector<Shader> loadShaders(const char* path, uint32_t salt) {
    std::ifstream file(path, std::ios::binary);
    std::string packed((std::istreambuf_iterator<char>(file)), std::istreambuf_iterator<char>());
    if (packed.size() < 8 || packed.compare(0, 4, "RBXS") != 0) fail("shaders.spvz is not readable");
    uint32_t size;
    memcpy(&size, packed.data() + 4, 4);
    std::vector<uint8_t> blob(size);
    uLongf length = size;
    if (uncompress(blob.data(), &length, (const Bytef*)packed.data() + 8, (uLong)packed.size() - 8) != Z_OK || length != size) fail("shaders.spvz does not inflate");
    size_t at = 0;
    auto u32 = [&]() { uint32_t v; memcpy(&v, blob.data() + at, 4); at += 4; return v; };
    uint32_t saltBits = u32(), count = u32();
    // The replacement constant: a float in [0.5, 1) derived from the salt.
    float replacement = 0.5f + (float)(salt % 4096u) / 8192.0f + (float)((salt >> 12) % 61u) / 1000000.0f;
    uint32_t replacementBits;
    memcpy(&replacementBits, &replacement, 4);
    std::vector<Shader> shaders(count);
    for (auto& shader : shaders) {
        uint32_t nameLength = u32();
        shader.name.assign((const char*)blob.data() + at, nameLength);
        at += nameLength;
        uint32_t words = u32();
        shader.words.resize(words);
        memcpy(shader.words.data(), blob.data() + at, words * 4ull);
        at += words * 4ull;
        // OpConstant (opcode 43, 4 words) holding the salt literal.
        for (size_t i = 5; i + 3 < shader.words.size();) {
            uint32_t wordCount = shader.words[i] >> 16, opcode = shader.words[i] & 0xFFFFu;
            if (wordCount == 0) break;
            if (opcode == 43 && wordCount == 4 && shader.words[i + 3] == saltBits) shader.words[i + 3] = replacementBits;
            i += wordCount;
        }
    }
    return shaders;
}

struct Timing {
    double total = 0, max = 0;
    int count = 0;
    void add(double ms) { total += ms; if (ms > max) max = ms; count++; }
    std::string json() const {
        std::ostringstream s;
        s << "{\"count\": " << count << ", \"totalMs\": " << total << ", \"maxMs\": " << max << "}";
        return s.str();
    }
};

struct GraphicsVariant {
    int fragment;
    VkFormat format;
    bool blend;
    bool vertexBuffer;
    int mode;   // specialization value of fragment 0 (0: none given)
};

struct Context {
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    uint32_t family = 0;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkPipelineLayout graphicsLayout = VK_NULL_HANDLE, computeLayout = VK_NULL_HANDLE;
    VkDescriptorSetLayout setLayout = VK_NULL_HANDLE;
    VkPipelineCache cache = VK_NULL_HANDLE;
    VkRenderPass passes[3] = {};
    std::vector<VkShaderModule> modules;
    VkShaderModule vertexIndex = VK_NULL_HANDLE, vertexBuffer = VK_NULL_HANDLE;
    std::vector<VkShaderModule> fragments, computes;
};

static const VkFormat kFormats[3] = {VK_FORMAT_R8G8B8A8_UNORM, VK_FORMAT_R16G16B16A16_SFLOAT, VK_FORMAT_B8G8R8A8_UNORM};

static VkRenderPass passFor(const Context& c, VkFormat format) {
    for (int i = 0; i < 3; i++) if (kFormats[i] == format) return c.passes[i];
    return VK_NULL_HANDLE;
}

static uint32_t memoryType(const Context& c, uint32_t bits, VkMemoryPropertyFlags flags) {
    VkPhysicalDeviceMemoryProperties properties;
    vkGetPhysicalDeviceMemoryProperties(c.physical, &properties);
    for (uint32_t i = 0; i < properties.memoryTypeCount; i++)
        if ((bits & (1u << i)) && (properties.memoryTypes[i].propertyFlags & flags) == flags) return i;
    fail("no memory type");
}

static VkResult createGraphics(const Context& c, VkPipelineCache cache, VkPipelineCreateFlags flags, const GraphicsVariant& v, VkPipeline* pipeline) {
    VkSpecializationMapEntry entry{0, 0, sizeof(int32_t)};
    int32_t mode = v.mode;
    VkSpecializationInfo specialization{1, &entry, sizeof(mode), &mode};
    VkPipelineShaderStageCreateInfo stages[2] = {};
    stages[0].sType = stages[1].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    stages[0].stage = VK_SHADER_STAGE_VERTEX_BIT;
    stages[0].module = v.vertexBuffer ? c.vertexBuffer : c.vertexIndex;
    stages[0].pName = "main";
    stages[1].stage = VK_SHADER_STAGE_FRAGMENT_BIT;
    stages[1].module = c.fragments[v.fragment];
    stages[1].pName = "main";
    if (v.mode) stages[1].pSpecializationInfo = &specialization;
    VkVertexInputBindingDescription binding{0, 2 * sizeof(float), VK_VERTEX_INPUT_RATE_VERTEX};
    VkVertexInputAttributeDescription attribute{0, 0, VK_FORMAT_R32G32_SFLOAT, 0};
    VkPipelineVertexInputStateCreateInfo vertexInput{VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
    if (v.vertexBuffer) {
        vertexInput.vertexBindingDescriptionCount = 1;
        vertexInput.pVertexBindingDescriptions = &binding;
        vertexInput.vertexAttributeDescriptionCount = 1;
        vertexInput.pVertexAttributeDescriptions = &attribute;
    }
    VkPipelineInputAssemblyStateCreateInfo assembly{VK_STRUCTURE_TYPE_PIPELINE_INPUT_ASSEMBLY_STATE_CREATE_INFO};
    assembly.topology = VK_PRIMITIVE_TOPOLOGY_TRIANGLE_LIST;
    VkPipelineViewportStateCreateInfo viewport{VK_STRUCTURE_TYPE_PIPELINE_VIEWPORT_STATE_CREATE_INFO};
    viewport.viewportCount = viewport.scissorCount = 1;
    VkPipelineRasterizationStateCreateInfo raster{VK_STRUCTURE_TYPE_PIPELINE_RASTERIZATION_STATE_CREATE_INFO};
    raster.polygonMode = VK_POLYGON_MODE_FILL;
    raster.cullMode = VK_CULL_MODE_NONE;
    raster.lineWidth = 1.0f;
    VkPipelineMultisampleStateCreateInfo multisample{VK_STRUCTURE_TYPE_PIPELINE_MULTISAMPLE_STATE_CREATE_INFO};
    multisample.rasterizationSamples = VK_SAMPLE_COUNT_1_BIT;
    VkPipelineColorBlendAttachmentState attachment{};
    attachment.colorWriteMask = 0xF;
    attachment.blendEnable = v.blend;
    attachment.srcColorBlendFactor = VK_BLEND_FACTOR_SRC_ALPHA;
    attachment.dstColorBlendFactor = VK_BLEND_FACTOR_ONE_MINUS_SRC_ALPHA;
    attachment.colorBlendOp = VK_BLEND_OP_ADD;
    attachment.srcAlphaBlendFactor = VK_BLEND_FACTOR_ONE;
    attachment.dstAlphaBlendFactor = VK_BLEND_FACTOR_ZERO;
    attachment.alphaBlendOp = VK_BLEND_OP_ADD;
    VkPipelineColorBlendStateCreateInfo blend{VK_STRUCTURE_TYPE_PIPELINE_COLOR_BLEND_STATE_CREATE_INFO};
    blend.attachmentCount = 1;
    blend.pAttachments = &attachment;
    VkDynamicState dynamics[2] = {VK_DYNAMIC_STATE_VIEWPORT, VK_DYNAMIC_STATE_SCISSOR};
    VkPipelineDynamicStateCreateInfo dynamic{VK_STRUCTURE_TYPE_PIPELINE_DYNAMIC_STATE_CREATE_INFO};
    dynamic.dynamicStateCount = 2;
    dynamic.pDynamicStates = dynamics;
    VkGraphicsPipelineCreateInfo info{VK_STRUCTURE_TYPE_GRAPHICS_PIPELINE_CREATE_INFO};
    info.flags = flags;
    info.stageCount = 2;
    info.pStages = stages;
    info.pVertexInputState = &vertexInput;
    info.pInputAssemblyState = &assembly;
    info.pViewportState = &viewport;
    info.pRasterizationState = &raster;
    info.pMultisampleState = &multisample;
    info.pColorBlendState = &blend;
    info.pDynamicState = &dynamic;
    info.layout = c.graphicsLayout;
    info.renderPass = passFor(c, v.format);
    *pipeline = VK_NULL_HANDLE;
    return vkCreateGraphicsPipelines(c.device, cache, 1, &info, nullptr, pipeline);
}

static VkResult createCompute(const Context& c, VkPipelineCache cache, VkPipelineCreateFlags flags, int index, VkPipeline* pipeline) {
    VkComputePipelineCreateInfo info{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
    info.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    info.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    info.stage.module = c.computes[index];
    info.stage.pName = "main";
    info.flags = flags;
    info.layout = c.computeLayout;
    *pipeline = VK_NULL_HANDLE;
    return vkCreateComputePipelines(c.device, cache, 1, &info, nullptr, pipeline);
}

struct Buffer { VkBuffer buffer = VK_NULL_HANDLE; VkDeviceMemory memory = VK_NULL_HANDLE; void* mapped = nullptr; VkDeviceSize size = 0; };

static Buffer makeBuffer(const Context& c, VkDeviceSize size, VkBufferUsageFlags usage) {
    Buffer b;
    b.size = size;
    VkBufferCreateInfo info{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    info.size = size;
    info.usage = usage;
    check(vkCreateBuffer(c.device, &info, nullptr, &b.buffer), "vkCreateBuffer");
    VkMemoryRequirements requirements;
    vkGetBufferMemoryRequirements(c.device, b.buffer, &requirements);
    VkMemoryAllocateInfo allocate{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    allocate.allocationSize = requirements.size;
    allocate.memoryTypeIndex = memoryType(c, requirements.memoryTypeBits, VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    check(vkAllocateMemory(c.device, &allocate, nullptr, &b.memory), "vkAllocateMemory");
    check(vkBindBufferMemory(c.device, b.buffer, b.memory, 0), "vkBindBufferMemory");
    check(vkMapMemory(c.device, b.memory, 0, VK_WHOLE_SIZE, 0, &b.mapped), "vkMapMemory");
    return b;
}

static void freeBuffer(const Context& c, Buffer& b) {
    vkDestroyBuffer(c.device, b.buffer, nullptr);
    vkFreeMemory(c.device, b.memory, nullptr);
}

static void submit(const Context& c, VkCommandBuffer commands) {
    check(vkEndCommandBuffer(commands), "vkEndCommandBuffer");
    VkSubmitInfo info{VK_STRUCTURE_TYPE_SUBMIT_INFO};
    info.commandBufferCount = 1;
    info.pCommandBuffers = &commands;
    check(vkQueueSubmit(c.queue, 1, &info, VK_NULL_HANDLE), "vkQueueSubmit");
    check(vkQueueWaitIdle(c.queue), "vkQueueWaitIdle");
}

static VkCommandBuffer begin(const Context& c) {
    VkCommandBufferAllocateInfo allocate{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    allocate.commandPool = c.pool;
    allocate.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    allocate.commandBufferCount = 1;
    VkCommandBuffer commands;
    check(vkAllocateCommandBuffers(c.device, &allocate, &commands), "vkAllocateCommandBuffers");
    VkCommandBufferBeginInfo info{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    info.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    check(vkBeginCommandBuffer(commands, &info), "vkBeginCommandBuffer");
    return commands;
}


static double footprintMiB() {
#ifdef __APPLE__
    task_vm_info_data_t info;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) == KERN_SUCCESS) return info.phys_footprint / 1048576.0;
#endif
    return -1;
}

static size_t cacheSize(VkDevice device, VkPipelineCache cache) {
    size_t size = 0;
    vkGetPipelineCacheData(device, cache, &size, nullptr);
    return size;
}

// Statistics of one worker, written only by the thread making that worker's requests (aggregated after every join).
struct Worker {
    VkPipelineCache cache = VK_NULL_HANDLE;
    int ownCompiles = 0, mainHits = 0, sinceMerge = 0, mainRefusals = 0;
    Timing ownTime, mainTime;
    std::vector<std::pair<double, double>> ownIntervals;   // [start, end] of each own-cache creation, ms from the run start
};

// Two threads meet here before their own-cache creations (concurrent strategy): both lookups in main have failed, so both
// compile at once; neither can find the other's libraries.
struct Rendezvous {
    std::mutex lock;
    std::condition_variable wake;
    int arrived = 0, generation = 0;
    void meet() {
        std::unique_lock<std::mutex> guard(lock);
        int mine = generation;
        if (++arrived == 2) { arrived = 0; generation++; wake.notify_all(); return; }
        wake.wait(guard, [&] { return generation != mine; });
    }
};

int main(int argc, char** argv) {
    if (argc < 5) fail("usage: mvk_library_share_test <shaders.spvz> <salt> <output.json> <none|one|merge|reset|every8|concurrent>");
    uint32_t salt = (uint32_t)strtoul(argv[2], nullptr, 10);
    std::string output = argv[3], strategy = argv[4];
    bool merge = strategy != "none" && strategy != "one", reset = strategy == "reset", concurrent = strategy == "concurrent";
    int mergeEvery = strategy == "every8" ? 8 : 1;
    std::vector<Shader> shaders = loadShaders(argv[1], salt);
    Context c;
    uint32_t count = 0;
    vkEnumerateInstanceExtensionProperties(nullptr, &count, nullptr);
    std::vector<VkExtensionProperties> available(count);
    vkEnumerateInstanceExtensionProperties(nullptr, &count, available.data());
    std::vector<const char*> instanceExtensions;
    VkInstanceCreateInfo instanceInfo{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    for (auto& e : available) {
        if (!strcmp(e.extensionName, "VK_KHR_portability_enumeration")) {
            instanceExtensions.push_back("VK_KHR_portability_enumeration");
            instanceInfo.flags |= 0x00000001;
        }
    }
    VkApplicationInfo application{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    application.pApplicationName = "mvk_library_share_test";
    application.apiVersion = VK_API_VERSION_1_3;
    instanceInfo.pApplicationInfo = &application;
    instanceInfo.enabledExtensionCount = (uint32_t)instanceExtensions.size();
    instanceInfo.ppEnabledExtensionNames = instanceExtensions.data();
    check(vkCreateInstance(&instanceInfo, nullptr, &c.instance), "vkCreateInstance");
    count = 1;
    VkResult enumerated = vkEnumeratePhysicalDevices(c.instance, &count, &c.physical);
    if ((enumerated != VK_SUCCESS && enumerated != VK_INCOMPLETE) || count == 0) fail("no physical device");
    VkPhysicalDeviceProperties properties;
    vkGetPhysicalDeviceProperties(c.physical, &properties);
    vkGetPhysicalDeviceQueueFamilyProperties(c.physical, &count, nullptr);
    std::vector<VkQueueFamilyProperties> families(count);
    vkGetPhysicalDeviceQueueFamilyProperties(c.physical, &count, families.data());
    for (uint32_t i = 0; i < count; i++)
        if ((families[i].queueFlags & (VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT)) == (VK_QUEUE_GRAPHICS_BIT | VK_QUEUE_COMPUTE_BIT)) { c.family = i; break; }
    vkEnumerateDeviceExtensionProperties(c.physical, nullptr, &count, nullptr);
    std::vector<VkExtensionProperties> deviceAvailable(count);
    vkEnumerateDeviceExtensionProperties(c.physical, nullptr, &count, deviceAvailable.data());
    std::vector<const char*> deviceExtensions;
    for (auto& e : deviceAvailable) if (!strcmp(e.extensionName, "VK_KHR_portability_subset")) deviceExtensions.push_back("VK_KHR_portability_subset");
    // MeloNX enables pipelineCreationCacheControl (SupportsPipelineCreationCacheControl) for its non-blocking lookups.
    VkPhysicalDevicePipelineCreationCacheControlFeatures cacheControl{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PIPELINE_CREATION_CACHE_CONTROL_FEATURES};
    VkPhysicalDeviceFeatures2 features{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2};
    features.pNext = &cacheControl;
    vkGetPhysicalDeviceFeatures2(c.physical, &features);
    if (!cacheControl.pipelineCreationCacheControl) fail("pipelineCreationCacheControl not supported");
    float priority = 1.0f;
    VkDeviceQueueCreateInfo queueInfo{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    queueInfo.queueFamilyIndex = c.family;
    queueInfo.queueCount = 1;
    queueInfo.pQueuePriorities = &priority;
    VkDeviceCreateInfo deviceInfo{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    deviceInfo.pNext = &cacheControl;
    deviceInfo.queueCreateInfoCount = 1;
    deviceInfo.pQueueCreateInfos = &queueInfo;
    deviceInfo.enabledExtensionCount = (uint32_t)deviceExtensions.size();
    deviceInfo.ppEnabledExtensionNames = deviceExtensions.data();
    check(vkCreateDevice(c.physical, &deviceInfo, nullptr, &c.device), "vkCreateDevice");
    vkGetDeviceQueue(c.device, c.family, 0, &c.queue);

    // MeloNX's cache flags (PipelineCacheManager: ExternallySynchronized with pipeline creation cache control).
    VkPipelineCacheCreateInfo cacheInfo{VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO};
    cacheInfo.flags = VK_PIPELINE_CACHE_CREATE_EXTERNALLY_SYNCHRONIZED_BIT;
    VkPipelineCache mainCache;
    check(vkCreatePipelineCache(c.device, &cacheInfo, nullptr, &mainCache), "vkCreatePipelineCache main");
    Worker workers[2];
    for (auto& w : workers) check(vkCreatePipelineCache(c.device, &cacheInfo, nullptr, &w.cache), "vkCreatePipelineCache worker");

    for (int i = 0; i < 3; i++) {
        VkAttachmentDescription attachment{};
        attachment.format = kFormats[i];
        attachment.samples = VK_SAMPLE_COUNT_1_BIT;
        attachment.loadOp = VK_ATTACHMENT_LOAD_OP_CLEAR;
        attachment.storeOp = VK_ATTACHMENT_STORE_OP_STORE;
        attachment.stencilLoadOp = VK_ATTACHMENT_LOAD_OP_DONT_CARE;
        attachment.stencilStoreOp = VK_ATTACHMENT_STORE_OP_DONT_CARE;
        attachment.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        attachment.finalLayout = VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL;
        VkAttachmentReference reference{0, VK_IMAGE_LAYOUT_COLOR_ATTACHMENT_OPTIMAL};
        VkSubpassDescription subpass{};
        subpass.pipelineBindPoint = VK_PIPELINE_BIND_POINT_GRAPHICS;
        subpass.colorAttachmentCount = 1;
        subpass.pColorAttachments = &reference;
        VkRenderPassCreateInfo passInfo{VK_STRUCTURE_TYPE_RENDER_PASS_CREATE_INFO};
        passInfo.attachmentCount = 1;
        passInfo.pAttachments = &attachment;
        passInfo.subpassCount = 1;
        passInfo.pSubpasses = &subpass;
        check(vkCreateRenderPass(c.device, &passInfo, nullptr, &c.passes[i]), "vkCreateRenderPass");
    }
    VkPushConstantRange range{VK_SHADER_STAGE_FRAGMENT_BIT, 0, 32};
    VkPipelineLayoutCreateInfo layoutInfo{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    layoutInfo.pushConstantRangeCount = 1;
    layoutInfo.pPushConstantRanges = &range;
    check(vkCreatePipelineLayout(c.device, &layoutInfo, nullptr, &c.graphicsLayout), "vkCreatePipelineLayout");
    for (auto& shader : shaders) {
        VkShaderModuleCreateInfo moduleInfo{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
        moduleInfo.codeSize = shader.words.size() * 4;
        moduleInfo.pCode = shader.words.data();
        VkShaderModule module;
        check(vkCreateShaderModule(c.device, &moduleInfo, nullptr, &module), "vkCreateShaderModule");
        c.modules.push_back(module);
        if (shader.name == "vertexIndex") c.vertexIndex = module;
        else if (shader.name == "vertexBuffer") c.vertexBuffer = module;
        else if (shader.name.compare(0, 8, "fragment") == 0) c.fragments.push_back(module);
        else c.computes.push_back(module);
    }
    double footprintStart = footprintMiB();

    std::mutex mainLock;   // MeloNX's PipelineCreationLock: main cache creations and merges hold it
    std::vector<VkPipeline> created;
    std::mutex createdLock;
    Timing mergeTime;   // written under mainLock
    long librariesMerged = 0;
    double runStart = nowMs();
    Rendezvous rendezvous;

    auto publish = [&](Worker& w) {
        if (!merge || ++w.sinceMerge < mergeEvery) return;
        w.sinceMerge = 0;
        std::lock_guard<std::mutex> lock(mainLock);
        double t = nowMs();
        check(vkMergePipelineCaches(c.device, mainCache, 1, &w.cache), "vkMergePipelineCaches");
        mergeTime.add(nowMs() - t);
        librariesMerged += w.ownCompiles;
        if (reset) {
            vkDestroyPipelineCache(c.device, w.cache, nullptr);
            check(vkCreatePipelineCache(c.device, &cacheInfo, nullptr, &w.cache), "vkCreatePipelineCache reset");
        }
    };
    // A worker creation as MeloNX makes it: the main cache first (never compiling there), else its own cache.
    auto request = [&](Worker& w, const GraphicsVariant& v, bool meet) {
        VkPipeline pipeline = VK_NULL_HANDLE;
        VkResult result;
        {
            std::lock_guard<std::mutex> lock(mainLock);
            double t = nowMs();
            result = createGraphics(c, mainCache, VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED_BIT, v, &pipeline);
            w.mainTime.add(nowMs() - t);
        }
        if (result == VK_SUCCESS) {
            w.mainHits++;
        } else {
            if (result != VK_PIPELINE_COMPILE_REQUIRED) w.mainRefusals++;
            if (meet) rendezvous.meet();
            double t = nowMs();
            check(createGraphics(c, w.cache, 0, v, &pipeline), "vkCreateGraphicsPipelines worker");
            double end = nowMs();
            w.ownTime.add(end - t);
            w.ownIntervals.push_back({t - runStart, end - runStart});
            w.ownCompiles++;
            publish(w);
        }
        std::lock_guard<std::mutex> lock(createdLock);
        created.push_back(pipeline);
    };

    double start = nowMs();
    int requests = 0;
    for (int f = 0; f < (int)c.fragments.size(); f++) {
        GraphicsVariant variants[5] = {{f, kFormats[0], false, false, 0}, {f, kFormats[1], false, false, 0},
                                       {f, kFormats[0], true, false, 0}, {f, kFormats[1], true, false, 0},
                                       {f, kFormats[0], false, true, 0}};
        int owner[5] = {0, 1, 0, 1, 1};
        if (strategy == "one") for (int& o : owner) o = 0;   // one worker cache: the fewest libraries
        int first = 0;
        if (concurrent) {
            // A and B start the first two variants of this program together: neither can find the other's library.
            std::thread a([&] { request(workers[0], variants[0], true); });
            std::thread b([&] { request(workers[1], variants[1], true); });
            a.join();
            b.join();
            first = 2;
            requests += 2;
        }
        for (int i = first; i < 5; i++) { request(workers[owner[i]], variants[i], false); requests++; }
    }
    double wallMs = nowMs() - start;
    double footprintEnd = footprintMiB();

    // Aggregated after every thread joined. Overlap: the time both workers spent in own-cache creations at once.
    Timing ownTime, mainTime;
    int mainRefusals = 0;
    for (auto& w : workers) {
        ownTime.total += w.ownTime.total; ownTime.count += w.ownTime.count; ownTime.max = std::max(ownTime.max, w.ownTime.max);
        mainTime.total += w.mainTime.total; mainTime.count += w.mainTime.count; mainTime.max = std::max(mainTime.max, w.mainTime.max);
        mainRefusals += w.mainRefusals;
    }
    double overlapMs = 0;
    int overlapping = 0;
    for (auto& a : workers[0].ownIntervals)
        for (auto& b : workers[1].ownIntervals) {
            double both = std::min(a.second, b.second) - std::max(a.first, b.first);
            if (both > 0) { overlapMs += both; overlapping++; }
        }
    std::ostringstream json;
    json << "{\"strategy\": \"" << strategy << "\", \"device\": \"" << properties.deviceName << "\", \"requests\": " << requests
         << ", \"wallMs\": " << wallMs << ", \"mainHits\": " << workers[0].mainHits + workers[1].mainHits
         << ", \"ownCompiles\": " << workers[0].ownCompiles + workers[1].ownCompiles << ", \"mainRefusals\": " << mainRefusals
         << ", \"mainLookup\": " << mainTime.json() << ", \"ownCreate\": " << ownTime.json() << ", \"merges\": " << mergeTime.json()
         << ", \"pipelinesMerged\": " << librariesMerged << ", \"ownOverlapMs\": " << overlapMs << ", \"overlappingOwnPairs\": " << overlapping
         << ", \"mainCacheBytes\": " << cacheSize(c.device, mainCache) << ", \"workerCacheBytes\": [" << cacheSize(c.device, workers[0].cache)
         << ", " << cacheSize(c.device, workers[1].cache) << "], \"footprintStartMiB\": " << footprintStart << ", \"footprintEndMiB\": " << footprintEnd;
#ifdef __APPLE__
    MVKPerformanceStatistics statistics{};
    size_t statisticsSize = sizeof(statistics);
    if (vkGetPerformanceStatisticsMVK(c.device, &statistics, &statisticsSize) == VK_SUCCESS) {
        auto tracker = [&](const char* name, const MVKPerformanceTracker& t) {
            json << ", \"" << name << "\": {\"count\": " << t.count << ", \"totalMs\": " << t.average * t.count << ", \"maxMs\": " << t.maximum << "}";
        };
        tracker("mvkSpirvToMsl", statistics.shaderCompilation.spirvToMSL);
        tracker("mvkMslCompile", statistics.shaderCompilation.mslCompile);
        tracker("mvkPipelineCompile", statistics.shaderCompilation.pipelineCompile);
        tracker("mvkLibraryFromCache", statistics.shaderCompilation.shaderLibraryFromCache);
    }
#endif
    json << "}";
    for (VkPipeline pipeline : created) if (pipeline) vkDestroyPipeline(c.device, pipeline, nullptr);
    for (VkShaderModule module : c.modules) vkDestroyShaderModule(c.device, module, nullptr);
    for (VkRenderPass pass : c.passes) vkDestroyRenderPass(c.device, pass, nullptr);
    vkDestroyPipelineLayout(c.device, c.graphicsLayout, nullptr);
    vkDestroyPipelineCache(c.device, mainCache, nullptr);
    for (auto& w : workers) vkDestroyPipelineCache(c.device, w.cache, nullptr);
    vkDestroyDevice(c.device, nullptr);
    vkDestroyInstance(c.instance, nullptr);
    std::ofstream(output) << json.str() << "\n";
    printf("%s\n", json.str().c_str());
    return 0;
}
