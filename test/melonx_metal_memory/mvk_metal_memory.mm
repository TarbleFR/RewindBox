// What a Vulkan image costs in Metal memory under MoltenVK, by kind (macOS runner, real Metal, the device's recipe).
//
// IPA 773, Hogwarts Legacy courtyard (pid 37647): MoltenVK's "GPU memory allocated" (MTLDevice currentAllocatedSize)
// went from 718 MB (17:00:08) to 1 356 MB (17:00:35) and stayed there, while the engine's Vulkan device memory stayed
// at 679-766 MiB (13 500-15 800 blocks). MeloNX gives every image its own VkDeviceMemory without a dedicated-allocation
// structure, so MoltenVK v1.4.2 makes a placement MTLHeap of that size at vkAllocateMemory; an image's texture is then
// placed in that heap, except a depth or stencil image's ("Metal support for depth/stencil from heaps is flaky",
// MVKImagePlane::getMTLTexture), which gets a texture of its own from the device next to the heap.
//
// Measured for each case, over kImages images of 1024 x 1024 created as Ryujinx's TextureStorage creates them (optimal
// tiling, mutable format and extended usage, a memory of the requirement's size bound at offset 0): the change of
// currentAllocatedSize and of the process's physical footprint after the allocations and binds, after a first use (a
// clear of every image, submitted and waited for), and after every image and memory is destroyed. Cases: a depth and
// stencil format, a depth-only format, a color format; the depth and stencil format again with a dedicated allocation
// (VkMemoryDedicatedAllocateInfo, which makes MoltenVK create no heap); each image's content is read back after its clear
// (depth, stencil and color values). Prints one JSON line and writes it to the output file.
// Usage: mvk_metal_memory <output.json>
#import <Metal/Metal.h>
#define VK_USE_PLATFORM_METAL_EXT 1
#include <vulkan/vulkan.h>
#include <mach/mach.h>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

static void fail(const std::string& message) { fprintf(stderr, "%s\n", message.c_str()); exit(2); }
static void check(VkResult result, const char* what) { if (result != VK_SUCCESS) fail(std::string(what) + " failed: " + std::to_string(result)); }

static const int kImages = 16;
static const uint32_t kSize = 1024;

struct Context {
    VkInstance instance;
    VkPhysicalDevice physical;
    VkDevice device;
    VkQueue queue;
    uint32_t family;
    VkCommandPool pool;
    VkPhysicalDeviceMemoryProperties memoryProperties;
    id<MTLDevice> mtlDevice;
};

static int64_t footprint() {
    task_vm_info_data_t info;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) != KERN_SUCCESS) return -1;
    return (int64_t)info.phys_footprint;
}

static int64_t allocated(Context& c) { return (int64_t)[c.mtlDevice currentAllocatedSize]; }

static uint32_t memoryType(Context& c, uint32_t bits, VkMemoryPropertyFlags wanted) {
    for (uint32_t t = 0; t < c.memoryProperties.memoryTypeCount; t++)
        if ((bits & (1u << t)) && (c.memoryProperties.memoryTypes[t].propertyFlags & wanted) == wanted) return t;
    fail("no memory type");
    return 0;
}

static bool isDepth(VkFormat format) {
    return format == VK_FORMAT_D32_SFLOAT_S8_UINT || format == VK_FORMAT_D32_SFLOAT || format == VK_FORMAT_D16_UNORM ||
           format == VK_FORMAT_D24_UNORM_S8_UINT;
}

static bool hasStencil(VkFormat format) { return format == VK_FORMAT_D32_SFLOAT_S8_UINT || format == VK_FORMAT_D24_UNORM_S8_UINT; }

// A buffer the host reads, for the read back of a clear.
struct HostBuffer { VkBuffer buffer; VkDeviceMemory memory; void* data; };

static HostBuffer hostBuffer(Context& c, VkDeviceSize size) {
    HostBuffer b{};
    VkBufferCreateInfo info{VK_STRUCTURE_TYPE_BUFFER_CREATE_INFO};
    info.size = size;
    info.usage = VK_BUFFER_USAGE_TRANSFER_DST_BIT;
    check(vkCreateBuffer(c.device, &info, nullptr, &b.buffer), "vkCreateBuffer");
    VkMemoryRequirements requirements;
    vkGetBufferMemoryRequirements(c.device, b.buffer, &requirements);
    VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
    allocation.allocationSize = requirements.size;
    allocation.memoryTypeIndex = memoryType(c, requirements.memoryTypeBits,
                                            VK_MEMORY_PROPERTY_HOST_VISIBLE_BIT | VK_MEMORY_PROPERTY_HOST_COHERENT_BIT);
    check(vkAllocateMemory(c.device, &allocation, nullptr, &b.memory), "vkAllocateMemory (host)");
    check(vkBindBufferMemory(c.device, b.buffer, b.memory, 0), "vkBindBufferMemory");
    check(vkMapMemory(c.device, b.memory, 0, VK_WHOLE_SIZE, 0, &b.data), "vkMapMemory");
    return b;
}

static void freeHostBuffer(Context& c, HostBuffer& b) {
    vkUnmapMemory(c.device, b.memory);
    vkDestroyBuffer(c.device, b.buffer, nullptr);
    vkFreeMemory(c.device, b.memory, nullptr);
}

static void barrier(VkCommandBuffer cb, VkImage image, VkImageAspectFlags aspect, VkImageLayout from, VkImageLayout to,
                    VkAccessFlags srcAccess, VkAccessFlags dstAccess) {
    VkImageMemoryBarrier b{VK_STRUCTURE_TYPE_IMAGE_MEMORY_BARRIER};
    b.oldLayout = from;
    b.newLayout = to;
    b.srcAccessMask = srcAccess;
    b.dstAccessMask = dstAccess;
    b.srcQueueFamilyIndex = b.dstQueueFamilyIndex = VK_QUEUE_FAMILY_IGNORED;
    b.image = image;
    b.subresourceRange = {aspect, 0, 1, 0, 1};
    vkCmdPipelineBarrier(cb, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, VK_PIPELINE_STAGE_ALL_COMMANDS_BIT, 0, 0, nullptr, 0, nullptr, 1, &b);
}

struct CaseResult {
    std::string name;
    std::string format;
    bool dedicated = false;
    bool supported = true;
    int64_t requirementBytes = 0;   // per image
    double allocatedAfterBindMiB = 0, allocatedAfterUseMiB = 0, allocatedAfterFreeMiB = 0;
    double footprintAfterBindMiB = 0, footprintAfterUseMiB = 0, footprintAfterFreeMiB = 0;
    double allocatedPerImageOverRequirement = 0;
    bool contentMatches = false;
};

static double mib(int64_t bytes) { return std::round(bytes / 1048576.0 * 100.0) / 100.0; }

static CaseResult runCase(Context& c, const char* name, VkFormat format, const char* formatName, bool dedicated) {
    CaseResult r;
    r.name = name;
    r.format = formatName;
    r.dedicated = dedicated;
    const bool depth = isDepth(format);
    const VkImageAspectFlags aspect = depth ? (VK_IMAGE_ASPECT_DEPTH_BIT | (hasStencil(format) ? VK_IMAGE_ASPECT_STENCIL_BIT : 0))
                                            : VK_IMAGE_ASPECT_COLOR_BIT;
    VkImageUsageFlags usage = VK_IMAGE_USAGE_SAMPLED_BIT | VK_IMAGE_USAGE_TRANSFER_SRC_BIT | VK_IMAGE_USAGE_TRANSFER_DST_BIT |
                              (depth ? VK_IMAGE_USAGE_DEPTH_STENCIL_ATTACHMENT_BIT : VK_IMAGE_USAGE_COLOR_ATTACHMENT_BIT);
    VkImageCreateFlags flags = VK_IMAGE_CREATE_MUTABLE_FORMAT_BIT | VK_IMAGE_CREATE_EXTENDED_USAGE_BIT;
    VkImageFormatProperties formatProperties;
    if (vkGetPhysicalDeviceImageFormatProperties(c.physical, format, VK_IMAGE_TYPE_2D, VK_IMAGE_TILING_OPTIMAL, usage, flags,
                                                 &formatProperties) != VK_SUCCESS) {
        r.supported = false;
        return r;
    }

    check(vkDeviceWaitIdle(c.device), "vkDeviceWaitIdle");
    const int64_t allocated0 = allocated(c), footprint0 = footprint();
    std::vector<VkImage> images(kImages);
    std::vector<VkDeviceMemory> memories(kImages);
    for (int i = 0; i < kImages; i++) {
        VkImageCreateInfo info{VK_STRUCTURE_TYPE_IMAGE_CREATE_INFO};
        info.flags = flags;
        info.imageType = VK_IMAGE_TYPE_2D;
        info.format = format;
        info.extent = {kSize, kSize, 1};
        info.mipLevels = 1;
        info.arrayLayers = 1;
        info.samples = VK_SAMPLE_COUNT_1_BIT;
        info.tiling = VK_IMAGE_TILING_OPTIMAL;
        info.usage = usage;
        info.sharingMode = VK_SHARING_MODE_EXCLUSIVE;
        info.initialLayout = VK_IMAGE_LAYOUT_UNDEFINED;
        check(vkCreateImage(c.device, &info, nullptr, &images[i]), "vkCreateImage");
        VkMemoryRequirements requirements;
        vkGetImageMemoryRequirements(c.device, images[i], &requirements);
        r.requirementBytes = (int64_t)requirements.size;
        VkMemoryDedicatedAllocateInfo dedicatedInfo{VK_STRUCTURE_TYPE_MEMORY_DEDICATED_ALLOCATE_INFO};
        dedicatedInfo.image = images[i];
        VkMemoryAllocateInfo allocation{VK_STRUCTURE_TYPE_MEMORY_ALLOCATE_INFO};
        allocation.pNext = dedicated ? &dedicatedInfo : nullptr;
        allocation.allocationSize = requirements.size;
        allocation.memoryTypeIndex = memoryType(c, requirements.memoryTypeBits, VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT);
        check(vkAllocateMemory(c.device, &allocation, nullptr, &memories[i]), "vkAllocateMemory");
        check(vkBindImageMemory(c.device, images[i], memories[i], 0), "vkBindImageMemory");
    }
    const int64_t allocated1 = allocated(c), footprint1 = footprint();

    // First use: clear every image (depth 0.25 and stencil 0x5A, or a color), then copy each one to a host buffer.
    const VkDeviceSize texel = 4;
    std::vector<HostBuffer> readBacks;
    VkCommandBufferAllocateInfo cbInfo{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
    cbInfo.commandPool = c.pool;
    cbInfo.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
    cbInfo.commandBufferCount = 1;
    VkCommandBuffer cb;
    check(vkAllocateCommandBuffers(c.device, &cbInfo, &cb), "vkAllocateCommandBuffers");
    VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
    begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
    check(vkBeginCommandBuffer(cb, &begin), "vkBeginCommandBuffer");
    for (int i = 0; i < kImages; i++) {
        barrier(cb, images[i], aspect, VK_IMAGE_LAYOUT_UNDEFINED, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, 0, VK_ACCESS_TRANSFER_WRITE_BIT);
        VkImageSubresourceRange range{aspect, 0, 1, 0, 1};
        if (depth) {
            VkClearDepthStencilValue value{0.25f, 0x5A};
            vkCmdClearDepthStencilImage(cb, images[i], VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &value, 1, &range);
        } else {
            VkClearColorValue value{};
            value.float32[0] = 1.0f; value.float32[1] = 0.5f; value.float32[2] = 0.0f; value.float32[3] = 1.0f;
            vkCmdClearColorImage(cb, images[i], VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, &value, 1, &range);
        }
        barrier(cb, images[i], aspect, VK_IMAGE_LAYOUT_TRANSFER_DST_OPTIMAL, VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL,
                VK_ACCESS_TRANSFER_WRITE_BIT, VK_ACCESS_TRANSFER_READ_BIT);
    }
    // Read back two images (the first and the last): a 64 x 64 corner of the depth (and stencil) or color aspect.
    const uint32_t corner = 64;
    for (int i : {0, kImages - 1}) {
        HostBuffer depthOrColor = hostBuffer(c, corner * corner * texel);
        VkBufferImageCopy copy{};
        copy.imageSubresource = {depth ? (VkImageAspectFlags)VK_IMAGE_ASPECT_DEPTH_BIT : (VkImageAspectFlags)VK_IMAGE_ASPECT_COLOR_BIT, 0, 0, 1};
        copy.imageExtent = {corner, corner, 1};
        vkCmdCopyImageToBuffer(cb, images[i], VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, depthOrColor.buffer, 1, &copy);
        readBacks.push_back(depthOrColor);
        if (hasStencil(format)) {
            HostBuffer stencil = hostBuffer(c, corner * corner);
            copy.imageSubresource.aspectMask = VK_IMAGE_ASPECT_STENCIL_BIT;
            vkCmdCopyImageToBuffer(cb, images[i], VK_IMAGE_LAYOUT_TRANSFER_SRC_OPTIMAL, stencil.buffer, 1, &copy);
            readBacks.push_back(stencil);
        }
    }
    check(vkEndCommandBuffer(cb), "vkEndCommandBuffer");
    VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
    submit.commandBufferCount = 1;
    submit.pCommandBuffers = &cb;
    check(vkQueueSubmit(c.queue, 1, &submit, VK_NULL_HANDLE), "vkQueueSubmit");
    check(vkQueueWaitIdle(c.queue), "vkQueueWaitIdle");

    bool matches = true;
    for (size_t b = 0; b < readBacks.size(); b++) {
        const bool stencilBuffer = hasStencil(format) && (b % 2 == 1);
        for (uint32_t t = 0; t < corner * corner && matches; t++) {
            if (stencilBuffer) {
                matches = ((const uint8_t*)readBacks[b].data)[t] == 0x5A;
            } else if (depth && format == VK_FORMAT_D16_UNORM) {
                matches = std::fabs(((const uint16_t*)readBacks[b].data)[t] / 65535.0 - 0.25) < 1e-3;
            } else if (depth) {
                matches = std::fabs(((const float*)readBacks[b].data)[t] - 0.25f) < 1e-6f;
            } else {
                const uint8_t* p = (const uint8_t*)readBacks[b].data + 4 * t;
                matches = p[0] == 255 && (p[1] == 127 || p[1] == 128) && p[2] == 0 && p[3] == 255;
            }
        }
    }
    r.contentMatches = matches;
    for (auto& b : readBacks) freeHostBuffer(c, b);
    vkFreeCommandBuffers(c.device, c.pool, 1, &cb);
    const int64_t allocated2 = allocated(c), footprint2 = footprint();

    for (int i = 0; i < kImages; i++) {
        vkDestroyImage(c.device, images[i], nullptr);
        vkFreeMemory(c.device, memories[i], nullptr);
    }
    check(vkDeviceWaitIdle(c.device), "vkDeviceWaitIdle");
    const int64_t allocated3 = allocated(c), footprint3 = footprint();

    r.allocatedAfterBindMiB = mib(allocated1 - allocated0);
    r.allocatedAfterUseMiB = mib(allocated2 - allocated0);
    r.allocatedAfterFreeMiB = mib(allocated3 - allocated0);
    r.footprintAfterBindMiB = mib(footprint1 - footprint0);
    r.footprintAfterUseMiB = mib(footprint2 - footprint0);
    r.footprintAfterFreeMiB = mib(footprint3 - footprint0);
    r.allocatedPerImageOverRequirement =
        std::round((double)(allocated2 - allocated0) / kImages / (double)r.requirementBytes * 1000.0) / 1000.0;
    return r;
}

int main(int argc, char** argv) {
    if (argc < 2) fail("usage: mvk_metal_memory <output.json>");
    std::string output = argv[1];
    Context c{};

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
    application.pApplicationName = "mvk_metal_memory";
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
    vkGetPhysicalDeviceMemoryProperties(c.physical, &c.memoryProperties);
    vkGetPhysicalDeviceQueueFamilyProperties(c.physical, &count, nullptr);
    std::vector<VkQueueFamilyProperties> families(count);
    vkGetPhysicalDeviceQueueFamilyProperties(c.physical, &count, families.data());
    for (uint32_t i = 0; i < count; i++) if (families[i].queueFlags & VK_QUEUE_GRAPHICS_BIT) { c.family = i; break; }
    vkEnumerateDeviceExtensionProperties(c.physical, nullptr, &count, nullptr);
    std::vector<VkExtensionProperties> deviceAvailable(count);
    vkEnumerateDeviceExtensionProperties(c.physical, nullptr, &count, deviceAvailable.data());
    std::vector<const char*> deviceExtensions;
    bool metalObjects = false;
    for (auto& e : deviceAvailable) {
        if (!strcmp(e.extensionName, "VK_KHR_portability_subset")) deviceExtensions.push_back("VK_KHR_portability_subset");
        if (!strcmp(e.extensionName, VK_EXT_METAL_OBJECTS_EXTENSION_NAME)) { deviceExtensions.push_back(VK_EXT_METAL_OBJECTS_EXTENSION_NAME); metalObjects = true; }
    }
    if (!metalObjects) fail("VK_EXT_metal_objects is required to read the Metal device");
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
    VkCommandPoolCreateInfo poolInfo{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
    poolInfo.queueFamilyIndex = c.family;
    poolInfo.flags = VK_COMMAND_POOL_CREATE_RESET_COMMAND_BUFFER_BIT;
    check(vkCreateCommandPool(c.device, &poolInfo, nullptr, &c.pool), "vkCreateCommandPool");

    auto exportObjects = (PFN_vkExportMetalObjectsEXT)vkGetDeviceProcAddr(c.device, "vkExportMetalObjectsEXT");
    if (!exportObjects) fail("vkExportMetalObjectsEXT");
    VkExportMetalDeviceInfoEXT deviceExport{VK_STRUCTURE_TYPE_EXPORT_METAL_DEVICE_INFO_EXT};
    VkExportMetalObjectsInfoEXT objects{VK_STRUCTURE_TYPE_EXPORT_METAL_OBJECTS_INFO_EXT};
    objects.pNext = &deviceExport;
    exportObjects(c.device, &objects);
    c.mtlDevice = deviceExport.mtlDevice;
    if (!c.mtlDevice) fail("no Metal device exported");

    std::vector<CaseResult> results;
    // A warm-up case first (the device's first allocations), not reported.
    runCase(c, "warm-up", VK_FORMAT_R8G8B8A8_UNORM, "R8G8B8A8_UNORM", false);
    results.push_back(runCase(c, "depthStencil", VK_FORMAT_D32_SFLOAT_S8_UINT, "D32_SFLOAT_S8_UINT", false));
    results.push_back(runCase(c, "depthStencilDedicated", VK_FORMAT_D32_SFLOAT_S8_UINT, "D32_SFLOAT_S8_UINT", true));
    results.push_back(runCase(c, "depth", VK_FORMAT_D32_SFLOAT, "D32_SFLOAT", false));
    results.push_back(runCase(c, "depth16", VK_FORMAT_D16_UNORM, "D16_UNORM", false));
    results.push_back(runCase(c, "color", VK_FORMAT_R8G8B8A8_UNORM, "R8G8B8A8_UNORM", false));
    results.push_back(runCase(c, "colorDedicated", VK_FORMAT_R8G8B8A8_UNORM, "R8G8B8A8_UNORM", true));

    std::ostringstream json;
    json << "{\"device\":\"" << properties.deviceName << "\",\"images\":" << kImages << ",\"size\":" << kSize
         << ",\"placementHeaps\":" << ([c.mtlDevice supportsFamily:MTLGPUFamilyApple2] || [c.mtlDevice supportsFamily:MTLGPUFamilyMac2] ? "true" : "false")
         << ",\"cases\":[";
    for (size_t i = 0; i < results.size(); i++) {
        const CaseResult& r = results[i];
        json << (i ? "," : "") << "{\"name\":\"" << r.name << "\",\"format\":\"" << r.format << "\",\"dedicated\":"
             << (r.dedicated ? "true" : "false") << ",\"supported\":" << (r.supported ? "true" : "false")
             << ",\"requirementMiB\":" << mib(r.requirementBytes) << ",\"allocatedAfterBindMiB\":" << r.allocatedAfterBindMiB
             << ",\"allocatedAfterUseMiB\":" << r.allocatedAfterUseMiB << ",\"allocatedAfterFreeMiB\":" << r.allocatedAfterFreeMiB
             << ",\"footprintAfterBindMiB\":" << r.footprintAfterBindMiB << ",\"footprintAfterUseMiB\":" << r.footprintAfterUseMiB
             << ",\"footprintAfterFreeMiB\":" << r.footprintAfterFreeMiB
             << ",\"allocatedPerImageOverRequirement\":" << r.allocatedPerImageOverRequirement
             << ",\"contentMatches\":" << (r.contentMatches ? "true" : "false") << "}";
    }
    json << "]}";
    printf("%s\n", json.str().c_str());
    std::ofstream(output) << json.str() << "\n";

    vkDestroyCommandPool(c.device, c.pool, nullptr);
    vkDestroyDevice(c.device, nullptr);
    vkDestroyInstance(c.instance, nullptr);
    return 0;
}
