// Lot 10: what a MoltenVK pipeline cache holds for pipelines built with MeloNX's descriptor set layouts, and what the
// fifth part of build-utils/melonx/moltenvk/rewindbox-moltenvk.patch changes (cache keys), on a real Metal device.
//
// MeloNX declares, for each stage of a program, 18 uniform buffers (set 0), 16 storage buffers (set 1), 32 textures and 32
// buffer textures (set 2), 16 images and 16 buffer images (set 3): ShaderInfoBuilder.AddStageInfo, Constants.cs. With
// Metal argument buffers MoltenVK lists every binding once per Metal stage in each shader's conversion configuration,
// and keeps that configuration with each cached library: about 1 300 entries of 136 bytes per library, in memory and in
// the pipeline cache data. This program builds that layout, creates pipelines whose shaders read resources at MeloNX's
// binding numbers (test/melonx_cache_keys/shaders.spvz), and:
//   save  creates MVK_BENCH_ROUNDS rounds of distinct shaders (13 libraries and 36 pipelines a round) in an empty cache
//         and writes its data;
//   load  the way RewindBox loads its main cache: maps the file read-only, creates a staging cache from the mapping with
//         RewindBox's private pNext structure, merges it into an empty main cache, destroys it; then creates every
//         pipeline again in main with FAIL_ON_PIPELINE_COMPILE_REQUIRED, one more of each pipeline of the last round, and
//         writes main's data.
// Both draw with the 12 pipelines of round 0 (two sets of resource contents each) into a 4x4 target and read a pixel
// back: the colour says whether every resource reached the shader, from a compiled pipeline and from a cache hit.
// MVK_CONFIG_REWINDBOX_FULL_CACHE_KEYS in the environment makes the patched MoltenVK keep whole configurations (the
// control: the shipped behaviour). Printed and written as JSON: counts, data size, the footprint at each step, times,
// MoltenVK's own counters and the pixels.
//
// Usage: mvk_cache_keys_test <shaders.spvz> <salt> <output.json> save <data file>
//        mvk_cache_keys_test <shaders.spvz> <salt> <output.json> load <data file> <written data file>
#include <vulkan/vulkan.h>
#ifdef __APPLE__
#include <MoltenVK/mvk_private_api.h>
#include <mach/mach.h>
#endif
#include <zlib.h>

#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>
#include <fcntl.h>
#include <sys/mman.h>
#include <unistd.h>

static double nowMs() {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

[[noreturn]] static void fail(const std::string& message) {
    fprintf(stderr, "FAILED: %s\n", message.c_str());
    exit(1);
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

// The pack's shaders with the salt literal replaced by a float in [0.5, 1) derived from the salt and the round.
static std::vector<Shader> loadShaders(const char* path, uint32_t salt, uint32_t round) {
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
    uint32_t pair[2] = {salt, round};
    uint32_t replacementBits = 0x3F000000u | (uint32_t)(fnv(1469598103934665603ull, pair, sizeof(pair)) & 0x007FFFFFu);
    std::vector<Shader> shaders(count);
    for (auto& shader : shaders) {
        uint32_t nameLength = u32();
        shader.name.assign((const char*)blob.data() + at, nameLength);
        at += nameLength;
        uint32_t words = u32();
        shader.words.resize(words);
        memcpy(shader.words.data(), blob.data() + at, words * 4ull);
        at += words * 4ull;
        bool replaced = false;
        for (size_t i = 5; i + 3 < shader.words.size();) {   // OpConstant (opcode 43, 4 words) holding the salt literal
            uint32_t wordCount = shader.words[i] >> 16, opcode = shader.words[i] & 0xFFFFu;
            if (wordCount == 0) break;
            if (opcode == 43 && wordCount == 4 && shader.words[i + 3] == saltBits) { shader.words[i + 3] = replacementBits; replaced = true; }
            i += wordCount;
        }
        if (!replaced) fail("no salt literal in " + shader.name);
    }
    return shaders;
}

struct Context {
    VkInstance instance = VK_NULL_HANDLE;
    VkPhysicalDevice physical = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    uint32_t family = 0;
    VkCommandPool pool = VK_NULL_HANDLE;
    VkDescriptorSetLayout setLayouts[4] = {};
    VkPipelineLayout layout = VK_NULL_HANDLE;
    VkRenderPass passes[2] = {};
    uint32_t layoutBindings = 0;
};

static const VkFormat kFormats[2] = {VK_FORMAT_R8G8B8A8_UNORM, VK_FORMAT_B8G8R8A8_UNORM};
struct Variant { int format; bool blend; };
static const Variant kVariants[3] = {{0, false}, {0, true}, {1, false}};

static uint32_t memoryType(const Context& c, uint32_t bits, VkMemoryPropertyFlags flags) {
    VkPhysicalDeviceMemoryProperties properties;
    vkGetPhysicalDeviceMemoryProperties(c.physical, &properties);
    for (uint32_t i = 0; i < properties.memoryTypeCount; i++)
        if ((bits & (1u << i)) && (properties.memoryTypes[i].propertyFlags & flags) == flags) return i;
    fail("no memory type");
}

// MeloNX's descriptor set layouts for a vertex + fragment program (ShaderInfoBuilder: the support buffer, then per stage
// the whole range of each kind; stage index 0 for the vertex stage and 4 for the fragment stage; one descriptor each;
// PipelineLayoutFactory on iOS 17 and later: each binding for its own stage, no push descriptor set on MoltenVK).
static void createMeloNXLayout(Context& c) {
    std::vector<VkDescriptorSetLayoutBinding> sets[4];
    auto add = [&](int set, uint32_t first, uint32_t count, VkDescriptorType type, VkShaderStageFlags stages) {
        for (uint32_t i = 0; i < count; i++) sets[set].push_back({first + i, type, 1, stages, nullptr});
    };
    add(0, 0, 1, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, VK_SHADER_STAGE_VERTEX_BIT | VK_SHADER_STAGE_FRAGMENT_BIT | VK_SHADER_STAGE_COMPUTE_BIT);
    const uint32_t stageIndex[2] = {0, 4};
    const VkShaderStageFlags stageFlags[2] = {VK_SHADER_STAGE_VERTEX_BIT, VK_SHADER_STAGE_FRAGMENT_BIT};
    for (int s = 0; s < 2; s++) add(0, 1 + stageIndex[s] * 18, 18, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, stageFlags[s]);
    for (int s = 0; s < 2; s++) add(1, stageIndex[s] * 16, 16, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, stageFlags[s]);
    for (int s = 0; s < 2; s++) {
        add(2, stageIndex[s] * 64, 32, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, stageFlags[s]);
        add(2, stageIndex[s] * 64 + 32, 32, VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER, stageFlags[s]);
    }
    for (int s = 0; s < 2; s++) {
        add(3, stageIndex[s] * 32, 16, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, stageFlags[s]);
        add(3, stageIndex[s] * 32 + 16, 16, VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER, stageFlags[s]);
    }
    for (int set = 0; set < 4; set++) {
        VkDescriptorSetLayoutCreateInfo info{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
        info.bindingCount = (uint32_t)sets[set].size();
        info.pBindings = sets[set].data();
        check(vkCreateDescriptorSetLayout(c.device, &info, nullptr, &c.setLayouts[set]), "vkCreateDescriptorSetLayout");
        c.layoutBindings += info.bindingCount;
    }
    VkPipelineLayoutCreateInfo layoutInfo{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
    layoutInfo.setLayoutCount = 4;
    layoutInfo.pSetLayouts = c.setLayouts;
    check(vkCreatePipelineLayout(c.device, &layoutInfo, nullptr, &c.layout), "vkCreatePipelineLayout");
}

static VkResult createPipeline(const Context& c, VkPipelineCache cache, VkPipelineCreateFlags flags, VkShaderModule vertex,
                               VkShaderModule fragment, const Variant& v, VkPipeline* pipeline) {
    VkPipelineShaderStageCreateInfo stages[2] = {};
    stages[0].sType = stages[1].sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
    stages[0].stage = VK_SHADER_STAGE_VERTEX_BIT;
    stages[0].module = vertex;
    stages[0].pName = "main";
    stages[1].stage = VK_SHADER_STAGE_FRAGMENT_BIT;
    stages[1].module = fragment;
    stages[1].pName = "main";
    VkPipelineVertexInputStateCreateInfo vertexInput{VK_STRUCTURE_TYPE_PIPELINE_VERTEX_INPUT_STATE_CREATE_INFO};
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
    info.layout = c.layout;
    info.renderPass = c.passes[v.format];
    *pipeline = VK_NULL_HANDLE;
    return vkCreateGraphicsPipelines(c.device, cache, 1, &info, nullptr, pipeline);
}

struct Buffer { VkBuffer buffer = VK_NULL_HANDLE; VkDeviceMemory memory = VK_NULL_HANDLE; void* mapped = nullptr; };

static Buffer makeBuffer(const Context& c, VkDeviceSize size, VkBufferUsageFlags usage) {
    Buffer b;
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

struct Image { VkImage image = VK_NULL_HANDLE; VkDeviceMemory memory = VK_NULL_HANDLE; VkImageView view = VK_NULL_HANDLE; };

static Image makeImage(const Context& c, uint32_t side, VkImageUsageFlags usage) {
    Image image;
    VkImageCreateInfo info{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
    info.imageType = VK_IMAGE_TYPE_2D;
    info.format = VK_FORMAT_R8G8B8A8_UNORM;
    info.extent = {side, side, 1};
    info.mipLevels = info.arrayLayers = 1;
    info.samples = VK_SAMPLE_COUNT_1_BIT;
    info.tiling = VK_IMAGE_TILING_OPTIMAL;
    info.usage = usage;
    info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
    check(vkCreateImage(c.device, &info, nullptr, &image.image), "vkCreateImage");
    VkMemoryRequirements requirements;
    vkGetImageMemoryRequirements(c.device, image.image, &requirements);
    VkMemoryAllocateInfo allocate{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    allocate.allocationSize = requirements.size;
    allocate.memoryTypeIndex = memoryType(c, requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
    check(vkAllocateMemory(c.device, &allocate, nullptr, &image.memory), "vkAllocateMemory image");
    check(vkBindImageMemory(c.device, image.image, image.memory, 0), "vkBindImageMemory");
    VkImageViewCreateInfo view{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
    view.image = image.image;
    view.viewType = VK_IMAGE_VIEW_TYPE_2D;
    view.format = VK_FORMAT_R8G8B8A8_UNORM;
    view.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    check(vkCreateImageView(c.device, &view, nullptr, &image.view), "vkCreateImageView");
    return image;
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

static void submit(const Context& c, VkCommandBuffer commands) {
    check(vkEndCommandBuffer(commands), "vkEndCommandBuffer");
    VkSubmitInfo info{VK_STRUCTURE_TYPE_SUBMIT_INFO};
    info.commandBufferCount = 1;
    info.pCommandBuffers = &commands;
    check(vkQueueSubmit(c.queue, 1, &info, VK_NULL_HANDLE), "vkQueueSubmit");
    check(vkQueueWaitIdle(c.queue), "vkQueueWaitIdle");
    vkFreeCommandBuffers(c.device, c.pool, 1, &commands);
}

static void transition(VkCommandBuffer commands, VkImage image, VkImageLayout from, VkImageLayout to) {
    VkImageMemoryBarrier barrier{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
    barrier.srcAccessMask = barrier.dstAccessMask = VK_ACCESS_MEMORY_READ_BIT | VK_ACCESS_MEMORY_WRITE_BIT;
    barrier.oldLayout = from;
    barrier.newLayout = to;
    barrier.srcQueueFamilyIndex = barrier.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    barrier.image = image;
    barrier.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    vkCmdPipelineBarrier(commands, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 0, nullptr, 0, nullptr, 1, &barrier);
}

static double footprintMiB() {
#ifdef __APPLE__
    task_vm_info_data_t info;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) == KERN_SUCCESS) return info.phys_footprint / 1048576.0;
#endif
    return -1;
}

// The resources the shaders read, at MeloNX's binding numbers, in one descriptor set per set layout.
struct Scene {
    Buffer support, vertexParams, fragmentParams, values, texels, readback;
    VkBufferView texelView = VK_NULL_HANDLE;
    Image tex0, tex1, picture, target;
    VkSampler sampler = VK_NULL_HANDLE;
    VkFramebuffer framebuffer = VK_NULL_HANDLE;
    VkDescriptorPool pool = VK_NULL_HANDLE;
    VkDescriptorSet sets[4] = {};
    bool filled = false;
};

struct Contents { float tint[3], tex0Red, tex1Green, values[3], texels[3], picture[3]; };
// Exactly representable in 8 bits where a texture holds them (0, 51/255 steps are not needed: 0.2 = 51/255 and so on).
static const Contents kContents[2] = {
    {{0.8f, 0.4f, 0.2f}, 1.0f, 0.6f, {0.4f, 0.8f, 0.2f}, {0.2f, 0.4f, 0.6f}, {0.4f, 0.6f, 0.2f}},
    {{0.2f, 0.6f, 1.0f}, 0.4f, 1.0f, {0.6f, 0.2f, 0.4f}, {0.6f, 0.2f, 0.4f}, {0.2f, 0.8f, 0.6f}},
};

// The colour a fragment of the pack gives for those contents, without its chain (at most 2 of 255): bound * 0.25.
static void expected(const Contents& k, int fragment, float out[3]) {
    for (int i = 0; i < 3; i++) {
        float bound = k.tint[i] * k.tex0Red + k.tex1Green * k.values[i];
        if (fragment % 3 == 1) bound += k.texels[i];
        if (fragment % 3 == 2) bound += k.picture[i];
        out[i] = bound * 0.25f;
    }
}

static Scene createScene(const Context& c) {
    Scene s;
    s.support = makeBuffer(c, 16, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT);
    s.vertexParams = makeBuffer(c, 16, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT);
    s.fragmentParams = makeBuffer(c, 48, VK_BUFFER_USAGE_UNIFORM_BUFFER_BIT);
    s.values = makeBuffer(c, 16, VK_BUFFER_USAGE_STORAGE_BUFFER_BIT);
    s.texels = makeBuffer(c, 16, VK_BUFFER_USAGE_UNIFORM_TEXEL_BUFFER_BIT);
    s.readback = makeBuffer(c, 64, VK_BUFFER_USAGE_TRANSFER_DST_BIT);
    VkBufferViewCreateInfo viewInfo{VK_STRUCTURE_TYPE_BUFFER_VIEW_CREATE_INFO};
    viewInfo.buffer = s.texels.buffer;
    viewInfo.format = VK_FORMAT_R32G32B32A32_SFLOAT;
    viewInfo.range = 16;
    check(vkCreateBufferView(c.device, &viewInfo, nullptr, &s.texelView), "vkCreateBufferView");
    s.tex0 = makeImage(c, 1, VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT);
    s.tex1 = makeImage(c, 1, VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT);
    s.picture = makeImage(c, 1, VK_IMAGE_USAGE_STORAGE_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT);
    s.target = makeImage(c, 4, VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT);
    VkSamplerCreateInfo samplerInfo{VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
    samplerInfo.magFilter = samplerInfo.minFilter = VK_FILTER_NEAREST;
    samplerInfo.mipmapMode = VK_SAMPLER_MIPMAP_MODE_NEAREST;
    samplerInfo.addressModeU = samplerInfo.addressModeV = samplerInfo.addressModeW = VK_SAMPLER_ADDRESS_MODE_CLAMP_TO_EDGE;
    check(vkCreateSampler(c.device, &samplerInfo, nullptr, &s.sampler), "vkCreateSampler");
    VkFramebufferCreateInfo framebufferInfo{VK_STRUCTURE_TYPE_FRAMEBUFFER_CREATE_INFO};
    framebufferInfo.renderPass = c.passes[0];
    framebufferInfo.attachmentCount = 1;
    framebufferInfo.pAttachments = &s.target.view;
    framebufferInfo.width = framebufferInfo.height = 4;
    framebufferInfo.layers = 1;
    check(vkCreateFramebuffer(c.device, &framebufferInfo, nullptr, &s.framebuffer), "vkCreateFramebuffer");

    VkDescriptorPoolSize sizes[6] = {{VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER, 37}, {VK_DESCRIPTOR_TYPE_STORAGE_BUFFER, 32},
                                     {VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, 64}, {VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER, 64},
                                     {VK_DESCRIPTOR_TYPE_STORAGE_IMAGE, 32}, {VK_DESCRIPTOR_TYPE_STORAGE_TEXEL_BUFFER, 32}};
    VkDescriptorPoolCreateInfo poolInfo{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
    poolInfo.maxSets = 4;
    poolInfo.poolSizeCount = 6;
    poolInfo.pPoolSizes = sizes;
    check(vkCreateDescriptorPool(c.device, &poolInfo, nullptr, &s.pool), "vkCreateDescriptorPool");
    VkDescriptorSetAllocateInfo allocate{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
    allocate.descriptorPool = s.pool;
    allocate.descriptorSetCount = 4;
    allocate.pSetLayouts = c.setLayouts;
    check(vkAllocateDescriptorSets(c.device, &allocate, s.sets), "vkAllocateDescriptorSets");

    VkDescriptorBufferInfo supportInfo{s.support.buffer, 0, 16}, vertexInfo{s.vertexParams.buffer, 0, 16};
    VkDescriptorBufferInfo fragmentInfo{s.fragmentParams.buffer, 0, 48}, valuesInfo{s.values.buffer, 0, 16};
    VkDescriptorImageInfo tex0Info{s.sampler, s.tex0.view, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
    VkDescriptorImageInfo tex1Info{s.sampler, s.tex1.view, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
    VkDescriptorImageInfo pictureInfo{VK_NULL_HANDLE, s.picture.view, VK_IMAGE_LAYOUT_GENERAL};
    VkWriteDescriptorSet writes[8] = {};
    auto write = [&](int at, int set, uint32_t binding, VkDescriptorType type) -> VkWriteDescriptorSet& {
        writes[at].sType = VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET;
        writes[at].dstSet = s.sets[set];
        writes[at].dstBinding = binding;
        writes[at].descriptorCount = 1;
        writes[at].descriptorType = type;
        return writes[at];
    };
    write(0, 0, 0, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER).pBufferInfo = &supportInfo;
    write(1, 0, 1, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER).pBufferInfo = &vertexInfo;
    write(2, 0, 73, VK_DESCRIPTOR_TYPE_UNIFORM_BUFFER).pBufferInfo = &fragmentInfo;
    write(3, 1, 64, VK_DESCRIPTOR_TYPE_STORAGE_BUFFER).pBufferInfo = &valuesInfo;
    write(4, 2, 256, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER).pImageInfo = &tex0Info;
    write(5, 2, 257, VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER).pImageInfo = &tex1Info;
    write(6, 2, 288, VK_DESCRIPTOR_TYPE_UNIFORM_TEXEL_BUFFER).pTexelBufferView = &s.texelView;
    write(7, 3, 128, VK_DESCRIPTOR_TYPE_STORAGE_IMAGE).pImageInfo = &pictureInfo;
    vkUpdateDescriptorSets(c.device, 8, writes, 0, nullptr);
    return s;
}

static void fillScene(const Context& c, Scene& s, const Contents& k) {
    float support[4] = {1.0f, 0, 0, 0}, vertexParams[4] = {0, 0, 0, 0};
    float fragmentParams[12] = {k.tint[0], k.tint[1], k.tint[2], 1.0f, 0.25f, 0.5f, 0, 0, 0.125f, 0.375f, 0.625f, 0};
    float values[4] = {k.values[0], k.values[1], k.values[2], 0}, texels[4] = {k.texels[0], k.texels[1], k.texels[2], 0};
    memcpy(s.support.mapped, support, sizeof(support));
    memcpy(s.vertexParams.mapped, vertexParams, sizeof(vertexParams));
    memcpy(s.fragmentParams.mapped, fragmentParams, sizeof(fragmentParams));
    memcpy(s.values.mapped, values, sizeof(values));
    memcpy(s.texels.mapped, texels, sizeof(texels));
    VkCommandBuffer commands = begin(c);
    VkImageSubresourceRange range{VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
    VkClearColorValue tex0{{k.tex0Red, 0, 0, 1}}, tex1{{0, k.tex1Green, 0, 1}}, picture{{k.picture[0], k.picture[1], k.picture[2], 1}};
    struct { Image* image; VkClearColorValue* colour; VkImageLayout layout; } images[3] = {
        {&s.tex0, &tex0, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL}, {&s.tex1, &tex1, VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL},
        {&s.picture, &picture, VK_IMAGE_LAYOUT_GENERAL}};
    for (auto& entry : images) {
        transition(commands, entry.image->image, s.filled ? entry.layout : VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL);
        vkCmdClearColorImage(commands, entry.image->image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, entry.colour, 1, &range);
        transition(commands, entry.image->image, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, entry.layout);
    }
    submit(c, commands);
    s.filled = true;
}

// One draw of the pipeline over the 4x4 target; the pixel at (1, 1), RGBA.
static void drawPixel(const Context& c, Scene& s, VkPipeline pipeline, uint8_t pixel[4]) {
    VkCommandBuffer commands = begin(c);
    VkClearValue clear{};
    VkRenderPassBeginInfo pass{VK_STRUCTURE_TYPE_RENDER_PASS_BEGIN_INFO};
    pass.renderPass = c.passes[0];
    pass.framebuffer = s.framebuffer;
    pass.renderArea = {{0, 0}, {4, 4}};
    pass.clearValueCount = 1;
    pass.pClearValues = &clear;
    vkCmdBeginRenderPass(commands, &pass, VK_SUBPASS_CONTENTS_INLINE);
    VkViewport viewport{0, 0, 4, 4, 0, 1};
    VkRect2D scissor{{0, 0}, {4, 4}};
    vkCmdSetViewport(commands, 0, 1, &viewport);
    vkCmdSetScissor(commands, 0, 1, &scissor);
    vkCmdBindPipeline(commands, VK_PIPELINE_BIND_POINT_GRAPHICS, pipeline);
    vkCmdBindDescriptorSets(commands, VK_PIPELINE_BIND_POINT_GRAPHICS, c.layout, 0, 4, s.sets, 0, nullptr);
    vkCmdDraw(commands, 3, 1, 0, 0);
    vkCmdEndRenderPass(commands);
    VkBufferImageCopy region{};
    region.imageSubresource = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
    region.imageExtent = {4, 4, 1};
    vkCmdCopyImageToBuffer(commands, s.target.image, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, s.readback.buffer, 1, &region);
    submit(c, commands);
    memcpy(pixel, (const uint8_t*)s.readback.mapped + (1 * 4 + 1) * 4, 4);
}

int main(int argc, char** argv) {
    if (argc < 6) fail("usage: mvk_cache_keys_test <shaders.spvz> <salt> <output.json> <save|load> <data file> [<written data file>]");
    uint32_t salt = (uint32_t)strtoul(argv[2], nullptr, 10);
    std::string output = argv[3], mode = argv[4], dataPath = argv[5], writtenPath = argc > 6 ? argv[6] : "";
    bool save = mode == "save";
    if (!save && mode != "load") fail("mode is save or load");
    const char* roundsText = getenv("MVK_BENCH_ROUNDS");
    uint32_t rounds = roundsText ? (uint32_t)strtoul(roundsText, nullptr, 10) : 8u;
    // A driver without MoltenVK's cache (a local check on a software driver) may compile at a lookup.
    bool allowCompile = getenv("MVK_BENCH_ALLOW_COMPILE") != nullptr;

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
    application.pApplicationName = "mvk_cache_keys_test";
    application.apiVersion = VK_API_VERSION_1_3;
    instanceInfo.pApplicationInfo = &application;
    instanceInfo.enabledExtensionCount = (uint32_t)instanceExtensions.size();
    instanceInfo.ppEnabledExtensionNames = instanceExtensions.data();
    check(vkCreateInstance(&instanceInfo, nullptr, &c.instance), "vkCreateInstance");
    count = 1;
    VkResult enumerated = vkEnumeratePhysicalDevices(c.instance, &count, &c.physical);
    if ((enumerated != VK_SUCCESS && enumerated != VK_INCOMPLETE) || count == 0) fail("no physical device");
    vkGetPhysicalDeviceQueueFamilyProperties(c.physical, &count, nullptr);
    std::vector<VkQueueFamilyProperties> families(count);
    vkGetPhysicalDeviceQueueFamilyProperties(c.physical, &count, families.data());
    for (uint32_t i = 0; i < count; i++)
        if (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) { c.family = i; break; }
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
    VkCommandPoolCreateInfo poolInfo{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    poolInfo.queueFamilyIndex = c.family;
    check(vkCreateCommandPool(c.device, &poolInfo, nullptr, &c.pool), "vkCreateCommandPool");

    for (int i = 0; i < 2; i++) {
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
    createMeloNXLayout(c);

    // MeloNX's cache flags (PipelineCacheManager: ExternallySynchronized with pipeline creation cache control).
    VkPipelineCacheCreateInfo cacheInfo{VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO};
    cacheInfo.flags = VK_PIPELINE_CACHE_CREATE_EXTERNALLY_SYNCHRONIZED_BIT;
    VkPipelineCache cache = VK_NULL_HANDLE;
    void* mapped = nullptr;
    size_t mappedSize = 0;
    double footprintStart = footprintMiB(), afterStaging = 0, afterMerge = 0, afterDestroy = 0, loadMs = 0;
    uint32_t compiledAtLoad = 0;
    if (save) {
        check(vkCreatePipelineCache(c.device, &cacheInfo, nullptr, &cache), "vkCreatePipelineCache");
    } else {
        int fd = open(dataPath.c_str(), O_RDONLY);
        if (fd < 0) fail("cannot open " + dataPath);
        mappedSize = (size_t)lseek(fd, 0, SEEK_END);
        mapped = mmap(nullptr, mappedSize, PROT_READ, MAP_PRIVATE, fd, 0);
        close(fd);
        if (mapped == MAP_FAILED) fail("mmap failed");
        struct { VkStructureType sType; const void* pNext; } referenceInfo{(VkStructureType)0x52425831, nullptr};
        VkPipelineCacheCreateInfo loadInfo = cacheInfo;
        loadInfo.pNext = &referenceInfo;
        loadInfo.initialDataSize = mappedSize;
        loadInfo.pInitialData = mapped;
        footprintStart = footprintMiB();
        double t = nowMs();
        VkPipelineCache staging = VK_NULL_HANDLE;
        check(vkCreatePipelineCache(c.device, &cacheInfo, nullptr, &cache), "vkCreatePipelineCache main");
        check(vkCreatePipelineCache(c.device, &loadInfo, nullptr, &staging), "vkCreatePipelineCache staging");
        afterStaging = footprintMiB();
        check(vkMergePipelineCaches(c.device, cache, 1, &staging), "vkMergePipelineCaches staging into main");
        afterMerge = footprintMiB();
        vkDestroyPipelineCache(c.device, staging, nullptr);
        loadMs = nowMs() - t;
        afterDestroy = footprintMiB();
#ifdef __APPLE__
        MVKPerformanceStatistics atLoad{};
        size_t atLoadSize = sizeof(atLoad);
        if (vkGetPerformanceStatisticsMVK(c.device, &atLoad, &atLoadSize) == VK_SUCCESS) compiledAtLoad = atLoad.shaderCompilation.mslCompile.count;
#endif
    }

    // Every round's modules stay alive, as a session's programs do.
    VkPipelineCreateFlags flags = save || allowCompile ? 0 : VK_PIPELINE_CREATE_FAIL_ON_PIPELINE_COMPILE_REQUIRED_BIT;
    std::vector<VkShaderModule> modules;
    std::vector<VkPipeline> made, firstRound;
    VkShaderModule lastVertex = VK_NULL_HANDLE;
    std::vector<VkShaderModule> lastFragments;
    int pipelines = 0, missing = 0, libraries = 0;
    double createMs = 0;
    for (uint32_t round = 0; round < rounds; round++) {
        std::vector<Shader> shaders = loadShaders(argv[1], salt, round);
        VkShaderModule vertex = VK_NULL_HANDLE;
        std::vector<VkShaderModule> fragments;
        for (auto& shader : shaders) {
            VkShaderModuleCreateInfo moduleInfo{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
            moduleInfo.codeSize = shader.words.size() * 4;
            moduleInfo.pCode = shader.words.data();
            VkShaderModule module;
            check(vkCreateShaderModule(c.device, &moduleInfo, nullptr, &module), "vkCreateShaderModule");
            modules.push_back(module);
            libraries++;
            if (shader.name == "vertex") vertex = module; else fragments.push_back(module);
        }
        for (int f = 0; f < (int)fragments.size(); f++) {
            for (int v = 0; v < 3; v++) {
                VkPipeline pipeline = VK_NULL_HANDLE;
                double t = nowMs();
                VkResult result = createPipeline(c, cache, flags, vertex, fragments[f], kVariants[v], &pipeline);
                createMs += nowMs() - t;
                if (result == VK_SUCCESS) { made.push_back(pipeline); if (round == 0 && v == 0) firstRound.push_back(pipeline); } else missing++;
                pipelines++;
            }
        }
        lastVertex = vertex;
        lastFragments = fragments;
    }
    double afterPipelines = footprintMiB();
    // One more pipeline of each program of the last round (new objects; its libraries and Metal states exist): what a
    // lookup of cached libraries costs by itself.
    double againMs = 0;
    int again = 0, againMissing = 0;
    if (!save) {
        for (int repeat = 0; repeat < 4; repeat++) {
            for (VkShaderModule fragment : lastFragments) {
                VkPipeline pipeline = VK_NULL_HANDLE;
                double t = nowMs();
                VkResult result = createPipeline(c, cache, flags, lastVertex, fragment, kVariants[0], &pipeline);
                againMs += nowMs() - t;
                if (result == VK_SUCCESS) made.push_back(pipeline); else againMissing++;
                again++;
            }
        }
    }

    size_t size = 0;
    double sizeMs = nowMs();
    vkGetPipelineCacheData(c.device, cache, &size, nullptr);
    sizeMs = nowMs() - sizeMs;
    std::vector<uint8_t> data(size);
    size_t written = size;
    double writeMs = nowMs();
    VkResult wrote = vkGetPipelineCacheData(c.device, cache, &written, data.data());
    writeMs = nowMs() - writeMs;
    std::string target = save ? dataPath : writtenPath;
    if (!target.empty()) std::ofstream(target, std::ios::binary).write((const char*)data.data(), (std::streamsize)written);
    uint64_t dataHash = fnv(1469598103934665603ull, data.data(), written);
    data = std::vector<uint8_t>();
    double afterWrite = footprintMiB();

    // The draws: every pipeline of round 0 (first variant), two sets of contents.
    std::ostringstream pixels;
    int drawn = 0, wrongPixels = 0, unchangedPixels = 0;
    if (firstRound.size() == 12) {
        Scene scene = createScene(c);
        std::vector<std::vector<uint8_t>> results(2);
        for (int k = 0; k < 2; k++) {
            fillScene(c, scene, kContents[k]);
            for (int f = 0; f < 12; f++) {
                uint8_t pixel[4];
                drawPixel(c, scene, firstRound[f], pixel);
                float want[3];
                expected(kContents[k], f, want);
                for (int channel = 0; channel < 3; channel++) {
                    // The chain adds at most 2 of 255; 3 more for rounding and the device's arithmetic.
                    double difference = (double)pixel[channel] - want[channel] * 255.0;
                    if (difference < -3.0 || difference > 5.0) wrongPixels++;
                }
                results[k].insert(results[k].end(), pixel, pixel + 4);
                pixels << (drawn ? ", " : "") << "[" << (int)pixel[0] << ", " << (int)pixel[1] << ", " << (int)pixel[2] << ", " << (int)pixel[3] << "]";
                drawn++;
            }
        }
        for (int f = 0; f < 12; f++)
            if (memcmp(results[0].data() + f * 4, results[1].data() + f * 4, 3) == 0) unchangedPixels++;
    }

    std::ostringstream json;
    json << "{\"mode\": \"" << mode << "\", \"rounds\": " << rounds << ", \"layoutBindings\": " << c.layoutBindings
         << ", \"shaderModules\": " << libraries << ", \"pipelines\": " << pipelines << ", \"missing\": " << missing
         << ", \"bytes\": " << written << ", \"writeResult\": " << (int)wrote << ", \"fileBytes\": " << mappedSize
         << ", \"footprintStartMiB\": " << footprintStart << ", \"footprintAfterStagingMiB\": " << afterStaging
         << ", \"footprintAfterMergeMiB\": " << afterMerge << ", \"footprintAfterDestroyMiB\": " << afterDestroy
         << ", \"footprintAfterPipelinesMiB\": " << afterPipelines << ", \"footprintAfterWriteMiB\": " << afterWrite
         << ", \"loadMs\": " << loadMs << ", \"createMs\": " << createMs << ", \"again\": " << again << ", \"againMissing\": " << againMissing
         << ", \"againMs\": " << againMs << ", \"sizeQueryMs\": " << sizeMs << ", \"writeMs\": " << writeMs
         << ", \"mvkMslCompileAtLoad\": " << compiledAtLoad << ", \"draws\": " << drawn << ", \"wrongPixels\": " << wrongPixels
         << ", \"pixelsUnchangedByContents\": " << unchangedPixels << ", \"pixels\": [" << pixels.str() << "]"
         << ", \"dataHash\": \"" << std::hex << dataHash << std::dec << "\"";
#ifdef __APPLE__
    MVKPerformanceStatistics statistics{};
    size_t statisticsSize = sizeof(statistics);
    if (vkGetPerformanceStatisticsMVK(c.device, &statistics, &statisticsSize) == VK_SUCCESS) {
        auto tracker = [&](const char* name, const MVKPerformanceTracker& t) {
            json << ", \"" << name << "\": {\"count\": " << t.count << ", \"totalMs\": " << t.average * t.count << ", \"maxMs\": " << t.maximum << "}";
        };
        tracker("mvkMslCompile", statistics.shaderCompilation.mslCompile);
        tracker("mvkSpirvToMsl", statistics.shaderCompilation.spirvToMSL);
        tracker("mvkPipelineCompile", statistics.shaderCompilation.pipelineCompile);
        tracker("mvkReadPipelineCache", statistics.pipelineCache.readPipelineCache);
        tracker("mvkWritePipelineCache", statistics.pipelineCache.writePipelineCache);
        tracker("mvkSizePipelineCache", statistics.pipelineCache.sizePipelineCache);
    }
#endif
    json << "}";
    std::ofstream(output) << json.str() << "\n";
    printf("%s\n", json.str().c_str());
    // The process ends here: the cache, its mapping and the pipelines go with it (the measures are taken).
    return 0;
}
