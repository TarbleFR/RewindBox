// Lot 7: one "session" of the MoltenVK Metal binary archive prototype, through the Vulkan API only.
//
// Creates the same set of pipelines every time from the synthetic shaders of shaders.spvz (generate_shaders.py):
// 62 graphics pipelines (12 fragment shaders x 2 colour formats x blending on/off with a vertex-index vertex shader, the
// 12 again with a vertex-buffer vertex shader, and fragment shader 0 with two specialization values) and 6 compute
// pipelines. Each pipeline is created by its own call, timed. Every RGBA8 graphics pipeline then draws into a 64x64
// target that is read back, and every compute pipeline fills a buffer: the hashes must be the same in every session,
// whether a pipeline was compiled or came from a Metal binary archive. "--absent" also creates one variant no archive
// holds unless a session collected it (fragment shader 0 on a BGRA8 target).
//
// The prototype itself is driven by the environment (RBX_MVK_BINARY_ARCHIVE_*); this program only reports what Vulkan
// returned, how long each creation took, MoltenVK's own shader statistics, and the hashes. The salt replaces one float
// constant in every shader, so a new salt gives Metal sources it never compiled.
//
// Usage: mvk_archive_test <shaders.spvz> <salt> <output.json> [--absent] [--threads N] [--cache-reads N] [--no-draw]
// Builds against any Vulkan loader or MoltenVK directly; on other drivers (lavapipe) it only checks the program itself.
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

static VkResult createGraphics(const Context& c, const GraphicsVariant& v, VkPipeline* pipeline) {
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
    return vkCreateGraphicsPipelines(c.device, c.cache, 1, &info, nullptr, pipeline);
}

static VkResult createCompute(const Context& c, int index, VkPipeline* pipeline) {
    VkComputePipelineCreateInfo info{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
    info.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    info.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
    info.stage.module = c.computes[index];
    info.stage.pName = "main";
    info.layout = c.computeLayout;
    *pipeline = VK_NULL_HANDLE;
    return vkCreateComputePipelines(c.device, c.cache, 1, &info, nullptr, pipeline);
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

int main(int argc, char** argv) {
    if (argc < 4) fail("usage: mvk_archive_test <shaders.spvz> <salt> <output.json> [--absent] [--threads N] [--cache-reads N] [--no-draw]");
    uint32_t salt = (uint32_t)strtoul(argv[2], nullptr, 10);
    std::string output = argv[3];
    bool absent = false, draw = true;
    int threads = 1, cacheReads = 0;
    for (int i = 4; i < argc; i++) {
        if (!strcmp(argv[i], "--absent")) absent = true;
        else if (!strcmp(argv[i], "--no-draw")) draw = false;
        else if (!strcmp(argv[i], "--threads") && i + 1 < argc) threads = atoi(argv[++i]);
        else if (!strcmp(argv[i], "--cache-reads") && i + 1 < argc) cacheReads = atoi(argv[++i]);
    }
    std::vector<Shader> shaders = loadShaders(argv[1], salt);
    double start = nowMs();
    Context c;

    // Instance and device.
    uint32_t count = 0;
    vkEnumerateInstanceExtensionProperties(nullptr, &count, nullptr);
    std::vector<VkExtensionProperties> available(count);
    vkEnumerateInstanceExtensionProperties(nullptr, &count, available.data());
    std::vector<const char*> instanceExtensions;
    VkInstanceCreateInfo instanceInfo{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    for (auto& e : available) {
        if (!strcmp(e.extensionName, "VK_KHR_portability_enumeration")) {
            instanceExtensions.push_back("VK_KHR_portability_enumeration");
            instanceInfo.flags |= 0x00000001; // VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR
        }
    }
    VkApplicationInfo application{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    application.pApplicationName = "mvk_archive_test";
    application.apiVersion = VK_API_VERSION_1_1;
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
    float priority = 1.0f;
    VkDeviceQueueCreateInfo queueInfo{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    queueInfo.queueFamilyIndex = c.family;
    queueInfo.queueCount = 1;
    queueInfo.pQueuePriorities = &priority;
    VkDeviceCreateInfo deviceInfo{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    deviceInfo.queueCreateInfoCount = 1;
    deviceInfo.pQueueCreateInfos = &queueInfo;
    deviceInfo.enabledExtensionCount = (uint32_t)deviceExtensions.size();
    deviceInfo.ppEnabledExtensionNames = deviceExtensions.data();
    check(vkCreateDevice(c.physical, &deviceInfo, nullptr, &c.device), "vkCreateDevice");
    vkGetDeviceQueue(c.device, c.family, 0, &c.queue);
    double deviceMs = nowMs() - start;

    VkCommandPoolCreateInfo poolInfo{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    poolInfo.queueFamilyIndex = c.family;
    check(vkCreateCommandPool(c.device, &poolInfo, nullptr, &c.pool), "vkCreateCommandPool");
    VkPipelineCacheCreateInfo cacheInfo{VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO};
    check(vkCreatePipelineCache(c.device, &cacheInfo, nullptr, &c.cache), "vkCreatePipelineCache");

    // Render passes (one colour attachment each), layouts, shader modules.
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
    VkDescriptorSetLayoutBinding setBinding{0, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1, VK_SHADER_STAGE_COMPUTE_BIT, nullptr};
    VkDescriptorSetLayoutCreateInfo setInfo{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
    setInfo.bindingCount = 1;
    setInfo.pBindings = &setBinding;
    check(vkCreateDescriptorSetLayout(c.device, &setInfo, nullptr, &c.setLayout), "vkCreateDescriptorSetLayout");
    VkPipelineLayoutCreateInfo computeLayoutInfo{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    computeLayoutInfo.setLayoutCount = 1;
    computeLayoutInfo.pSetLayouts = &c.setLayout;
    check(vkCreatePipelineLayout(c.device, &computeLayoutInfo, nullptr, &c.computeLayout), "vkCreatePipelineLayout");
    Timing moduleTime;
    for (auto& shader : shaders) {
        VkShaderModuleCreateInfo moduleInfo{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
        moduleInfo.codeSize = shader.words.size() * 4;
        moduleInfo.pCode = shader.words.data();
        VkShaderModule module;
        double t = nowMs();
        check(vkCreateShaderModule(c.device, &moduleInfo, nullptr, &module), "vkCreateShaderModule");
        moduleTime.add(nowMs() - t);
        c.modules.push_back(module);
        if (shader.name == "vertexIndex") c.vertexIndex = module;
        else if (shader.name == "vertexBuffer") c.vertexBuffer = module;
        else if (shader.name.compare(0, 8, "fragment") == 0) c.fragments.push_back(module);
        else c.computes.push_back(module);
    }

    // The set of pipelines.
    std::vector<GraphicsVariant> variants;
    for (int f = 0; f < (int)c.fragments.size(); f++)
        for (int format = 0; format < 2; format++)
            for (int blend = 0; blend < 2; blend++) variants.push_back({f, kFormats[format], blend != 0, false, 0});
    for (int f = 0; f < (int)c.fragments.size(); f++) variants.push_back({f, kFormats[0], false, true, 0});
    variants.push_back({0, kFormats[0], false, false, 1});
    variants.push_back({0, kFormats[0], false, false, 2});
    std::vector<VkPipeline> graphics(variants.size(), VK_NULL_HANDLE), computes(c.computes.size(), VK_NULL_HANDLE);
    std::vector<VkResult> graphicsResults(variants.size(), VK_SUCCESS), computeResults(c.computes.size(), VK_SUCCESS);
    std::vector<double> graphicsMs(variants.size(), 0), computeMs(c.computes.size(), 0);

    // Another thread reads the pipeline cache data while pipelines are created (the application's own persistence).
    std::atomic<bool> stopReads{false};
    std::atomic<int> readsDone{0};
    std::thread reader;
    if (cacheReads > 0) {
        reader = std::thread([&] {
            while (!stopReads && readsDone < cacheReads) {
                size_t size = 0;
                if (vkGetPipelineCacheData(c.device, c.cache, &size, nullptr) == VK_SUCCESS && size) {
                    std::vector<uint8_t> data(size);
                    vkGetPipelineCacheData(c.device, c.cache, &size, data.data());
                }
                readsDone++;
                std::this_thread::sleep_for(std::chrono::milliseconds(20));
            }
        });
    }
    double createStart = nowMs();
    std::vector<std::thread> workers;
    for (int t = 0; t < threads; t++) {
        workers.emplace_back([&, t] {
            for (size_t i = t; i < variants.size(); i += threads) {
                double begin = nowMs();
                graphicsResults[i] = createGraphics(c, variants[i], &graphics[i]);
                graphicsMs[i] = nowMs() - begin;
            }
            for (size_t i = t; i < computes.size(); i += threads) {
                double begin = nowMs();
                computeResults[i] = createCompute(c, (int)i, &computes[i]);
                computeMs[i] = nowMs() - begin;
            }
        });
    }
    for (auto& worker : workers) worker.join();
    double createWallMs = nowMs() - createStart;
    stopReads = true;
    if (reader.joinable()) reader.join();
    if (cacheReads > 0) {
        // One last read after every pipeline exists.
        size_t size = 0;
        if (vkGetPipelineCacheData(c.device, c.cache, &size, nullptr) == VK_SUCCESS && size) {
            std::vector<uint8_t> data(size);
            vkGetPipelineCacheData(c.device, c.cache, &size, data.data());
        }
    }
    Timing graphicsTime, computeTime;
    int graphicsCreated = 0, computeCreated = 0;
    std::string graphicsFailures, computeFailures;
    for (size_t i = 0; i < variants.size(); i++) {
        graphicsTime.add(graphicsMs[i]);
        if (graphicsResults[i] == VK_SUCCESS && graphics[i]) graphicsCreated++;
        else graphicsFailures += (graphicsFailures.empty() ? "" : ", ") + std::to_string(i) + ":" + std::to_string((int)graphicsResults[i]);
    }
    for (size_t i = 0; i < computes.size(); i++) {
        computeTime.add(computeMs[i]);
        if (computeResults[i] == VK_SUCCESS && computes[i]) computeCreated++;
        else computeFailures += (computeFailures.empty() ? "" : ", ") + std::to_string(i) + ":" + std::to_string((int)computeResults[i]);
    }

    // The variant no archive holds unless a session collected it.
    VkPipeline absentPipeline = VK_NULL_HANDLE;
    VkResult absentResult = VK_SUCCESS;
    double absentMs = 0;
    if (absent) {
        double begin = nowMs();
        absentResult = createGraphics(c, {0, kFormats[2], false, false, 0}, &absentPipeline);
        absentMs = nowMs() - begin;
    }

    // Draws and dispatches with what was created.
    uint64_t drawHash = 1469598103934665603ull, computeHash = 1469598103934665603ull;
    int draws = 0, dispatches = 0, nonBlack = 0;
    if (draw) {
        VkImageCreateInfo imageInfo{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
        imageInfo.imageType = VK_IMAGE_TYPE_2D;
        imageInfo.format = kFormats[0];
        imageInfo.extent = {64, 64, 1};
        imageInfo.mipLevels = imageInfo.arrayLayers = 1;
        imageInfo.samples = VK_SAMPLE_COUNT_1_BIT;
        imageInfo.usage = VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT;
        VkImage image;
        check(vkCreateImage(c.device, &imageInfo, nullptr, &image), "vkCreateImage");
        VkMemoryRequirements requirements;
        vkGetImageMemoryRequirements(c.device, image, &requirements);
        VkMemoryAllocateInfo allocate{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
        allocate.allocationSize = requirements.size;
        allocate.memoryTypeIndex = memoryType(c, requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        VkDeviceMemory imageMemory;
        check(vkAllocateMemory(c.device, &allocate, nullptr, &imageMemory), "vkAllocateMemory");
        check(vkBindImageMemory(c.device, image, imageMemory, 0), "vkBindImageMemory");
        VkImageViewCreateInfo viewInfo{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
        viewInfo.image = image;
        viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
        viewInfo.format = kFormats[0];
        viewInfo.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        VkImageView view;
        check(vkCreateImageView(c.device, &viewInfo, nullptr, &view), "vkCreateImageView");
        VkFramebufferCreateInfo framebufferInfo{VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO};
        framebufferInfo.renderPass = c.passes[0];
        framebufferInfo.attachmentCount = 1;
        framebufferInfo.pAttachments = &view;
        framebufferInfo.width = framebufferInfo.height = 64;
        framebufferInfo.layers = 1;
        VkFramebuffer framebuffer;
        check(vkCreateFramebuffer(c.device, &framebufferInfo, nullptr, &framebuffer), "vkCreateFramebuffer");
        Buffer pixels = makeBuffer(c, 64 * 64 * 4, VK_BUFFER_USAGE_TRANSFER_DST_BIT);
        Buffer vertices = makeBuffer(c, 6 * sizeof(float), VK_BUFFER_USAGE_VERTEX_BUFFER_BIT);
        const float triangle[6] = {0, 0, 2, 0, 0, 2};
        memcpy(vertices.mapped, triangle, sizeof(triangle));
        const float params[8] = {0.25f, 0.5f, 0.75f, 1.0f, 0.125f, 0.375f, 0.625f, 0.875f};
        for (size_t i = 0; i < variants.size(); i++) {
            if (!graphics[i] || variants[i].format != kFormats[0]) continue;
            memset(pixels.mapped, 0, (size_t)pixels.size);
            VkCommandBuffer commands = begin(c);
            VkClearValue clear{};
            VkRenderPassBeginInfo passBegin{VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO};
            passBegin.renderPass = c.passes[0];
            passBegin.framebuffer = framebuffer;
            passBegin.renderArea = {{0, 0}, {64, 64}};
            passBegin.clearValueCount = 1;
            passBegin.pClearValues = &clear;
            vkCmdBeginRenderPass(commands, &passBegin, VK_SUBPASS_CONTENTS_INLINE);
            vkCmdBindPipeline(commands, VK_PIPELINE_BIND_POINT_GRAPHICS, graphics[i]);
            VkViewport viewport{0, 0, 64, 64, 0, 1};
            VkRect2D scissor{{0, 0}, {64, 64}};
            vkCmdSetViewport(commands, 0, 1, &viewport);
            vkCmdSetScissor(commands, 0, 1, &scissor);
            vkCmdPushConstants(commands, c.graphicsLayout, VK_SHADER_STAGE_FRAGMENT_BIT, 0, 32, params);
            if (variants[i].vertexBuffer) {
                VkDeviceSize offset = 0;
                vkCmdBindVertexBuffers(commands, 0, 1, &vertices.buffer, &offset);
            }
            vkCmdDraw(commands, 3, 1, 0, 0);
            vkCmdEndRenderPass(commands);
            VkBufferImageCopy region{};
            region.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
            region.imageExtent = {64, 64, 1};
            vkCmdCopyImageToBuffer(commands, image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, pixels.buffer, 1, &region);
            submit(c, commands);
            vkFreeCommandBuffers(c.device, c.pool, 1, &commands);
            drawHash = fnv(drawHash, pixels.mapped, (size_t)pixels.size);
            const uint8_t* p = (const uint8_t*)pixels.mapped;
            for (int k = 0; k < 64 * 64 * 4; k += 4) if (p[k] | p[k + 1] | p[k + 2]) nonBlack++;
            draws++;
        }
        Buffer output = makeBuffer(c, 1024 * sizeof(float), VK_BUFFER_USAGE_STORAGE_BUFFER_BIT);
        VkDescriptorPoolSize poolSize{VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 1};
        VkDescriptorPoolCreateInfo descriptorPoolInfo{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
        descriptorPoolInfo.maxSets = 1;
        descriptorPoolInfo.poolSizeCount = 1;
        descriptorPoolInfo.pPoolSizes = &poolSize;
        VkDescriptorPool descriptorPool;
        check(vkCreateDescriptorPool(c.device, &descriptorPoolInfo, nullptr, &descriptorPool), "vkCreateDescriptorPool");
        VkDescriptorSetAllocateInfo setAllocate{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
        setAllocate.descriptorPool = descriptorPool;
        setAllocate.descriptorSetCount = 1;
        setAllocate.pSetLayouts = &c.setLayout;
        VkDescriptorSet set;
        check(vkAllocateDescriptorSets(c.device, &setAllocate, &set), "vkAllocateDescriptorSets");
        VkDescriptorBufferInfo bufferInfo{output.buffer, 0, VK_WHOLE_SIZE};
        VkWriteDescriptorSet write{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
        write.dstSet = set;
        write.descriptorCount = 1;
        write.descriptorType = VK_DESCRIPTOR_TYPE_STORAGE_BUFFER;
        write.pBufferInfo = &bufferInfo;
        vkUpdateDescriptorSets(c.device, 1, &write, 0, nullptr);
        for (size_t i = 0; i < computes.size(); i++) {
            if (!computes[i]) continue;
            memset(output.mapped, 0, (size_t)output.size);
            VkCommandBuffer commands = begin(c);
            vkCmdBindPipeline(commands, VK_PIPELINE_BIND_POINT_COMPUTE, computes[i]);
            vkCmdBindDescriptorSets(commands, VK_PIPELINE_BIND_POINT_COMPUTE, c.computeLayout, 0, 1, &set, 0, nullptr);
            vkCmdDispatch(commands, 16, 1, 1);
            submit(c, commands);
            vkFreeCommandBuffers(c.device, c.pool, 1, &commands);
            computeHash = fnv(computeHash, output.mapped, (size_t)output.size);
            dispatches++;
        }
        vkDestroyDescriptorPool(c.device, descriptorPool, nullptr);
        freeBuffer(c, output);
        freeBuffer(c, vertices);
        freeBuffer(c, pixels);
        vkDestroyFramebuffer(c.device, framebuffer, nullptr);
        vkDestroyImageView(c.device, view, nullptr);
        vkDestroyImage(c.device, image, nullptr);
        vkFreeMemory(c.device, imageMemory, nullptr);
    }

    std::ostringstream json;
    json.precision(6);
    json << std::fixed;
    json << "{\"device\": \"" << properties.deviceName << "\", \"salt\": " << salt << ", \"threads\": " << threads
         << ", \"deviceMs\": " << deviceMs << ", \"shaderModules\": " << moduleTime.json()
         << ", \"graphics\": {\"requested\": " << variants.size() << ", \"created\": " << graphicsCreated << ", \"failures\": \"" << graphicsFailures << "\", \"time\": " << graphicsTime.json() << "}"
         << ", \"compute\": {\"requested\": " << computes.size() << ", \"created\": " << computeCreated << ", \"failures\": \"" << computeFailures << "\", \"time\": " << computeTime.json() << "}"
         << ", \"createWallMs\": " << createWallMs << ", \"cacheReads\": " << readsDone.load();
    if (absent) json << ", \"absent\": {\"result\": " << (int)absentResult << ", \"created\": " << (absentPipeline ? "true" : "false") << ", \"ms\": " << absentMs << "}";
    char hash[32];
    snprintf(hash, sizeof(hash), "%016llx", (unsigned long long)drawHash);
    json << ", \"draws\": " << draws << ", \"drawHash\": \"" << hash << "\", \"nonBlackPixels\": " << nonBlack;
    snprintf(hash, sizeof(hash), "%016llx", (unsigned long long)computeHash);
    json << ", \"dispatches\": " << dispatches << ", \"computeHash\": \"" << hash << "\"";
#ifdef __APPLE__
    // MoltenVK's own shader statistics for this device (needs MVK_CONFIG_PERFORMANCE_TRACKING=1).
    MVKPerformanceStatistics statistics{};
    size_t statisticsSize = sizeof(statistics);
    if (vkGetPerformanceStatisticsMVK(c.device, &statistics, &statisticsSize) == VK_SUCCESS) {
        auto tracker = [&](const char* name, const MVKPerformanceTracker& t) {
            json << ", \"" << name << "\": {\"count\": " << t.count << ", \"totalMs\": " << t.average * t.count << ", \"maxMs\": " << t.maximum << "}";
        };
        tracker("mvkSpirvToMsl", statistics.shaderCompilation.spirvToMSL);
        tracker("mvkMslCompile", statistics.shaderCompilation.mslCompile);
        tracker("mvkMslLoad", statistics.shaderCompilation.mslLoad);
        tracker("mvkFunctionRetrieval", statistics.shaderCompilation.functionRetrieval);
        tracker("mvkFunctionSpecialization", statistics.shaderCompilation.functionSpecialization);
        tracker("mvkPipelineCompile", statistics.shaderCompilation.pipelineCompile);
    }
#endif

    if (absentPipeline) vkDestroyPipeline(c.device, absentPipeline, nullptr);
    for (VkPipeline pipeline : graphics) if (pipeline) vkDestroyPipeline(c.device, pipeline, nullptr);
    for (VkPipeline pipeline : computes) if (pipeline) vkDestroyPipeline(c.device, pipeline, nullptr);
    for (VkShaderModule module : c.modules) vkDestroyShaderModule(c.device, module, nullptr);
    for (VkRenderPass pass : c.passes) vkDestroyRenderPass(c.device, pass, nullptr);
    vkDestroyPipelineLayout(c.device, c.graphicsLayout, nullptr);
    vkDestroyPipelineLayout(c.device, c.computeLayout, nullptr);
    vkDestroyDescriptorSetLayout(c.device, c.setLayout, nullptr);
    vkDestroyPipelineCache(c.device, c.cache, nullptr);
    vkDestroyCommandPool(c.device, c.pool, nullptr);
    double destroyStart = nowMs();
    vkDestroyDevice(c.device, nullptr);
    json << ", \"destroyDeviceMs\": " << nowMs() - destroyStart << "}";
    vkDestroyInstance(c.instance, nullptr);

    std::ofstream out(output);
    out << json.str() << "\n";
    printf("%s\n", json.str().c_str());
    return 0;
}
