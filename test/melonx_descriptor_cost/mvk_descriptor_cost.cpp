// Lot 9 (render thread): what writing a texture descriptor set costs in MoltenVK, against binding a set already
// written (macOS runner, real Metal, the same MoltenVK build as the device's recipe).
//
// IPA 718, Hogwarts Legacy in play (pid 44597): the render thread spends 9.6 ms per frame in draw descriptors and
// 3.1 ms in compute descriptors; its counters give 5.39 M descriptors written per 5 s, 63 517 texture sets, about 74
// descriptors per texture set. MeloNX writes a set with vkUpdateDescriptorSetWithTemplate (one template per program and
// set) and binds it with vkCmdBindDescriptorSets; MoltenVK on the device uses Metal3 argument buffers ("Descriptor sets
// binding resources using Metal3 argument buffers") and, on iOS 18 / macOS 15, a residency set.
//
// Measured, per size (8, 32, 74 combined image samplers): template writes alternating between two contents (each write
// changes every descriptor), writes repeating the same content, plain vkUpdateDescriptorSets writes, and binds of an
// already written set recorded into a command buffer. Prints one JSON line.
// Usage: mvk_descriptor_cost <output.json>
#include <vulkan/vulkan.h>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

static void fail(const std::string& message) { fprintf(stderr, "%s\n", message.c_str()); exit(2); }
static void check(VkResult result, const char* what) { if (result != VK_SUCCESS) fail(std::string(what) + " failed: " + std::to_string(result)); }
static double nowMs() {
    return std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now().time_since_epoch()).count();
}

int main(int argc, char** argv) {
    if (argc < 2) fail("usage: mvk_descriptor_cost <output.json>");
    std::string output = argv[1];

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
    application.pApplicationName = "mvk_descriptor_cost";
    application.apiVersion = VK_API_VERSION_1_3;
    instanceInfo.pApplicationInfo = &application;
    instanceInfo.enabledExtensionCount = (uint32_t)instanceExtensions.size();
    instanceInfo.ppEnabledExtensionNames = instanceExtensions.data();
    VkInstance instance;
    check(vkCreateInstance(&instanceInfo, nullptr, &instance), "vkCreateInstance");
    VkPhysicalDevice physical;
    count = 1;
    VkResult enumerated = vkEnumeratePhysicalDevices(instance, &count, &physical);
    if ((enumerated != VK_SUCCESS && enumerated != VK_INCOMPLETE) || count == 0) fail("no physical device");
    VkPhysicalDeviceProperties properties;
    vkGetPhysicalDeviceProperties(physical, &properties);
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, nullptr);
    std::vector<VkQueueFamilyProperties> families(count);
    vkGetPhysicalDeviceQueueFamilyProperties(physical, &count, families.data());
    uint32_t family = 0;
    for (uint32_t i = 0; i < count; i++) if (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) { family = i; break; }
    vkEnumerateDeviceExtensionProperties(physical, nullptr, &count, nullptr);
    std::vector<VkExtensionProperties> deviceAvailable(count);
    vkEnumerateDeviceExtensionProperties(physical, nullptr, &count, deviceAvailable.data());
    std::vector<const char*> deviceExtensions;
    for (auto& e : deviceAvailable) if (!strcmp(e.extensionName, "VK_KHR_portability_subset")) deviceExtensions.push_back("VK_KHR_portability_subset");
    float priority = 1.0f;
    VkDeviceQueueCreateInfo queueInfo{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
    queueInfo.queueFamilyIndex = family;
    queueInfo.queueCount = 1;
    queueInfo.pQueuePriorities = &priority;
    VkDeviceCreateInfo deviceInfo{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
    deviceInfo.queueCreateInfoCount = 1;
    deviceInfo.pQueueCreateInfos = &queueInfo;
    deviceInfo.enabledExtensionCount = (uint32_t)deviceExtensions.size();
    deviceInfo.ppEnabledExtensionNames = deviceExtensions.data();
    VkDevice device;
    check(vkCreateDevice(physical, &deviceInfo, nullptr, &device), "vkCreateDevice");

    // 160 small textures (two contents of up to 74 descriptors, plus spares) and two samplers.
    const int kTextures = 160;
    VkMemoryRequirements requirements{};
    VkPhysicalDeviceMemoryProperties memoryProperties;
    vkGetPhysicalDeviceMemoryProperties(physical, &memoryProperties);
    std::vector<VkImage> images(kTextures);
    std::vector<VkImageView> views(kTextures);
    std::vector<VkDeviceMemory> memories(kTextures);
    for (int i = 0; i < kTextures; i++) {
        VkImageCreateInfo imageInfo{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
        imageInfo.imageType = VK_IMAGE_TYPE_2D;
        imageInfo.format = VK_FORMAT_R8G8B8A8_UNORM;
        imageInfo.extent = {16, 16, 1};
        imageInfo.mipLevels = 1;
        imageInfo.arrayLayers = 1;
        imageInfo.samples = VK_SAMPLE_COUNT_1_BIT;
        imageInfo.tiling = VK_IMAGE_TILING_OPTIMAL;
        imageInfo.usage = VK_IMAGE_USAGE_SAMPLED_BIT;
        check(vkCreateImage(device, &imageInfo, nullptr, &images[i]), "vkCreateImage");
        vkGetImageMemoryRequirements(device, images[i], &requirements);
        uint32_t type = 0;
        for (uint32_t t = 0; t < memoryProperties.memoryTypeCount; t++)
            if ((requirements.memoryTypeBits & (1u << t)) && (memoryProperties.memoryTypes[t].propertyFlags & VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT)) { type = t; break; }
        VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = type;
        check(vkAllocateMemory(device, &allocation, nullptr, &memories[i]), "vkAllocateMemory");
        check(vkBindImageMemory(device, images[i], memories[i], 0), "vkBindImageMemory");
        VkImageViewCreateInfo viewInfo{VK_STRUCTURE_TYPE_IMAGE_VIEW_CREATE_INFO};
        viewInfo.image = images[i];
        viewInfo.viewType = VK_IMAGE_VIEW_TYPE_2D;
        viewInfo.format = VK_FORMAT_R8G8B8A8_UNORM;
        viewInfo.subresourceRange = {VK_IMAGE_ASPECT_COLOR_BIT, 0, 1, 0, 1};
        check(vkCreateImageView(device, &viewInfo, nullptr, &views[i]), "vkCreateImageView");
    }
    VkSampler samplers[2];
    for (int i = 0; i < 2; i++) {
        VkSamplerCreateInfo samplerInfo{VK_STRUCTURE_TYPE_SAMPLER_CREATE_INFO};
        samplerInfo.magFilter = samplerInfo.minFilter = i ? VK_FILTER_NEAREST : VK_FILTER_LINEAR;
        check(vkCreateSampler(device, &samplerInfo, nullptr, &samplers[i]), "vkCreateSampler");
    }
    VkCommandPool commandPool;
    VkCommandPoolCreateInfo poolInfo{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    poolInfo.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    poolInfo.queueFamilyIndex = family;
    check(vkCreateCommandPool(device, &poolInfo, nullptr, &commandPool), "vkCreateCommandPool");
    VkCommandBuffer command;
    VkCommandBufferAllocateInfo commandInfo{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    commandInfo.commandPool = commandPool;
    commandInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    commandInfo.commandBufferCount = 1;
    check(vkAllocateCommandBuffers(device, &commandInfo, &command), "vkAllocateCommandBuffers");

    const char* rounds = getenv("MVK_BENCH_ROUNDS");
    int iterations = rounds ? atoi(rounds) : 20000;
    std::ostringstream json;
    json << "{\"device\": \"" << properties.deviceName << "\", \"iterations\": " << iterations << ", \"sizes\": [";
    const int sizes[3] = {8, 32, 74};
    for (int s = 0; s < 3; s++) {
        int n = sizes[s];
        VkDescriptorSetLayoutBinding binding{};
        binding.binding = 0;
        binding.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        binding.descriptorCount = (uint32_t)n;
        binding.stageFlags = VK_SHADER_STAGE_FRAGMENT_BIT | VK_SHADER_STAGE_VERTEX_BIT;
        VkDescriptorSetLayoutCreateInfo layoutInfo{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_LAYOUT_CREATE_INFO};
        layoutInfo.bindingCount = 1;
        layoutInfo.pBindings = &binding;
        VkDescriptorSetLayout setLayout;
        check(vkCreateDescriptorSetLayout(device, &layoutInfo, nullptr, &setLayout), "vkCreateDescriptorSetLayout");
        VkPipelineLayoutCreateInfo pipelineLayoutInfo{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
        pipelineLayoutInfo.setLayoutCount = 1;
        pipelineLayoutInfo.pSetLayouts = &setLayout;
        VkPipelineLayout pipelineLayout;
        check(vkCreatePipelineLayout(device, &pipelineLayoutInfo, nullptr, &pipelineLayout), "vkCreatePipelineLayout");
        VkDescriptorPoolSize poolSize{VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER, (uint32_t)(n * 4)};
        VkDescriptorPoolCreateInfo descriptorPoolInfo{VK_STRUCTURE_TYPE_DESCRIPTOR_POOL_CREATE_INFO};
        descriptorPoolInfo.maxSets = 4;
        descriptorPoolInfo.poolSizeCount = 1;
        descriptorPoolInfo.pPoolSizes = &poolSize;
        VkDescriptorPool descriptorPool;
        check(vkCreateDescriptorPool(device, &descriptorPoolInfo, nullptr, &descriptorPool), "vkCreateDescriptorPool");
        VkDescriptorSet sets[2];
        VkDescriptorSetLayout layouts[2] = {setLayout, setLayout};
        VkDescriptorSetAllocateInfo setInfo{VK_STRUCTURE_TYPE_DESCRIPTOR_SET_ALLOCATE_INFO};
        setInfo.descriptorPool = descriptorPool;
        setInfo.descriptorSetCount = 2;
        setInfo.pSetLayouts = layouts;
        check(vkAllocateDescriptorSets(device, &setInfo, sets), "vkAllocateDescriptorSets");
        VkDescriptorUpdateTemplateEntry entry{};
        entry.dstBinding = 0;
        entry.descriptorCount = (uint32_t)n;
        entry.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        entry.stride = sizeof(VkDescriptorImageInfo);
        VkDescriptorUpdateTemplateCreateInfo templateInfo{VK_STRUCTURE_TYPE_DESCRIPTOR_UPDATE_TEMPLATE_CREATE_INFO};
        templateInfo.descriptorUpdateEntryCount = 1;
        templateInfo.pDescriptorUpdateEntries = &entry;
        templateInfo.templateType = VK_DESCRIPTOR_UPDATE_TEMPLATE_TYPE_DESCRIPTOR_SET;
        templateInfo.descriptorSetLayout = setLayout;
        VkDescriptorUpdateTemplate updateTemplate;
        check(vkCreateDescriptorUpdateTemplate(device, &templateInfo, nullptr, &updateTemplate), "vkCreateDescriptorUpdateTemplate");
        std::vector<VkDescriptorImageInfo> contents[2];
        for (int k = 0; k < 2; k++) {
            contents[k].resize(n);
            for (int i = 0; i < n; i++) contents[k][i] = {samplers[k], views[k * 80 + i], VK_IMAGE_LAYOUT_GENERAL};
        }
        // Warm-up, then template writes alternating between the two contents (every descriptor changes each time).
        for (int i = 0; i < 200; i++) vkUpdateDescriptorSetWithTemplate(device, sets[0], updateTemplate, contents[i & 1].data());
        double start = nowMs();
        for (int i = 0; i < iterations; i++) vkUpdateDescriptorSetWithTemplate(device, sets[0], updateTemplate, contents[i & 1].data());
        double alternating = (nowMs() - start) * 1000.0 / iterations;
        start = nowMs();
        for (int i = 0; i < iterations; i++) vkUpdateDescriptorSetWithTemplate(device, sets[1], updateTemplate, contents[0].data());
        double same = (nowMs() - start) * 1000.0 / iterations;
        VkWriteDescriptorSet write{VK_STRUCTURE_TYPE_WRITE_DESCRIPTOR_SET};
        write.dstSet = sets[0];
        write.dstBinding = 0;
        write.descriptorCount = (uint32_t)n;
        write.descriptorType = VK_DESCRIPTOR_TYPE_COMBINED_IMAGE_SAMPLER;
        start = nowMs();
        for (int i = 0; i < iterations; i++) {
            write.pImageInfo = contents[i & 1].data();
            vkUpdateDescriptorSets(device, 1, &write, 0, nullptr);
        }
        double plain = (nowMs() - start) * 1000.0 / iterations;
        // Binds of the two written sets, alternating, recorded into one command buffer (reset every 1 000 binds).
        VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
        double bindTotal = 0;
        for (int i = 0; i < iterations; i += 1000) {
            check(vkResetCommandBuffer(command, 0), "vkResetCommandBuffer");
            check(vkBeginCommandBuffer(command, &begin), "vkBeginCommandBuffer");
            double bindStart = nowMs();
            for (int j = 0; j < 1000; j++) vkCmdBindDescriptorSets(command, VK_PIPELINE_BIND_POINT_GRAPHICS, pipelineLayout, 0, 1, &sets[j & 1], 0, nullptr);
            bindTotal += nowMs() - bindStart;
            check(vkEndCommandBuffer(command), "vkEndCommandBuffer");
        }
        double bind = bindTotal * 1000.0 / iterations;
        json << (s ? ", " : "") << "{\"descriptors\": " << n << ", \"templateWriteAlternatingUs\": " << alternating
             << ", \"templateWriteSameUs\": " << same << ", \"plainWriteUs\": " << plain << ", \"bindRecordUs\": " << bind
             << ", \"templateWritePerDescriptorUs\": " << alternating / n << "}";
        vkDestroyDescriptorUpdateTemplate(device, updateTemplate, nullptr);
        vkDestroyDescriptorPool(device, descriptorPool, nullptr);
        vkDestroyPipelineLayout(device, pipelineLayout, nullptr);
        vkDestroyDescriptorSetLayout(device, setLayout, nullptr);
    }
    json << "]}";
    std::ofstream(output) << json.str() << "\n";
    printf("%s\n", json.str().c_str());
    vkDestroyDevice(device, nullptr);
    vkDestroyInstance(instance, nullptr);
    return 0;
}
