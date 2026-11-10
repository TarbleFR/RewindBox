// RewindBox RPCS3 candidate validation. No game content or product hook replacement.
// SPDX-License-Identifier: MIT
#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#include <MoltenVK/mvk_vulkan.h>
#include <MoltenVK/mvk_private_api.h>
#include <dispatch/dispatch.h>
#include <atomic>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

// Test executable adapters only: real dispatch queues and real Metal are used.
// The product's RPCS3IOSPlatform.mm implementations remain untouched.
extern "C" dispatch_queue_t rbx_mvk_compile_qos_queue(intptr_t priority, uintptr_t flags) {
    return dispatch_get_global_queue(priority, flags);
}
extern "C" dispatch_queue_t rbx_mvk_exec_q_create(const char* label, dispatch_queue_attr_t attributes) {
    return dispatch_queue_create(label, attributes);
}

// Authored minimal SPIR-V 1.0: Shader capability, Logical/GLSL450 model,
// GLCompute main, LocalSize(1,1,1), empty function. No application assets.
// Opcode/operand definitions: Khronos SPIRV-Headers 29981f65241605e08b0ede4cfeb999fe3b723c6a.
static const uint32_t computeSPIRV[] = {
    0x07230203, 0x00010000, 0, 6, 0,
    0x00020011, 1,
    0x0003000e, 0, 1,
    0x0005000f, 5, 4, 0x6e69616d, 0,
    0x00060010, 4, 17, 1, 1, 1,
    0x00020013, 1,
    0x00030021, 2, 1,
    0x00050036, 1, 4, 0, 2,
    0x000200f8, 5,
    0x000100fd,
    0x00010038,
};

static void require(bool condition, const char* message) {
    if (!condition) throw std::runtime_error(message);
}
static void check(VkResult result, const char* operation) {
    if (result != VK_SUCCESS) {
        throw std::runtime_error(std::string(operation) + ": VkResult " + std::to_string(result));
    }
}
static void writeReport(const char* path, NSDictionary* report) {
    NSError* error = nil;
    NSData* data = [NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingPrettyPrinted error:&error];
    if (!data || ![data writeToFile:@(path) options:NSDataWritingAtomic error:&error]) {
        throw std::runtime_error("Could not write Metal probe report");
    }
}

struct Context {
    VkInstance instance = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkShaderModule shader = VK_NULL_HANDLE;
    VkPipelineLayout layout = VK_NULL_HANDLE;
    VkQueue queue = VK_NULL_HANDLE;
    uint32_t family = 0;
    std::string deviceName;

    ~Context() {
        if (device) {
            vkDeviceWaitIdle(device);
            if (layout) vkDestroyPipelineLayout(device, layout, nullptr);
            if (shader) vkDestroyShaderModule(device, shader, nullptr);
            vkDestroyDevice(device, nullptr);
        }
        if (instance) vkDestroyInstance(instance, nullptr);
    }

    void create() {
        VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
        app.pApplicationName = "RewindBox MoltenVK cache probe";
        app.apiVersion = VK_API_VERSION_1_0;
        std::vector<const char*> extensions;
        uint32_t extensionCount = 0;
        check(vkEnumerateInstanceExtensionProperties(nullptr, &extensionCount, nullptr), "instance extension count");
        std::vector<VkExtensionProperties> extensionProperties(extensionCount);
        check(vkEnumerateInstanceExtensionProperties(nullptr, &extensionCount, extensionProperties.data()), "instance extensions");
        bool portability = false;
        for (const auto& property : extensionProperties) {
            if (std::strcmp(property.extensionName, VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME) == 0) portability = true;
        }
        if (portability) extensions.push_back(VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME);
        VkInstanceCreateInfo info{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
        info.pApplicationInfo = &app;
        info.enabledExtensionCount = static_cast<uint32_t>(extensions.size());
        info.ppEnabledExtensionNames = extensions.data();
        if (portability) info.flags = VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR;
        check(vkCreateInstance(&info, nullptr, &instance), "vkCreateInstance");
        uint32_t count = 0;
        check(vkEnumeratePhysicalDevices(instance, &count, nullptr), "physical device count");
        require(count > 0, "Vulkan exposes no real Metal physical device");
        std::vector<VkPhysicalDevice> physicalDevices(count);
        check(vkEnumeratePhysicalDevices(instance, &count, physicalDevices.data()), "physical devices");
        VkPhysicalDevice physical = physicalDevices[0];
        VkPhysicalDeviceProperties properties{};
        vkGetPhysicalDeviceProperties(physical, &properties);
        deviceName = properties.deviceName;
        uint32_t queueCount = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &queueCount, nullptr);
        std::vector<VkQueueFamilyProperties> queues(queueCount);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &queueCount, queues.data());
        bool found = false;
        for (uint32_t index = 0; index < queueCount; ++index) {
            if (queues[index].queueCount && (queues[index].queueFlags & VK_QUEUE_COMPUTE_BIT)) {
                family = index;
                found = true;
                break;
            }
        }
        require(found, "No compute queue family");
        extensions.clear();
        check(vkEnumerateDeviceExtensionProperties(physical, nullptr, &extensionCount, nullptr), "device extension count");
        extensionProperties.resize(extensionCount);
        check(vkEnumerateDeviceExtensionProperties(physical, nullptr, &extensionCount, extensionProperties.data()), "device extensions");
        for (const auto& property : extensionProperties) {
            if (std::strcmp(property.extensionName, VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME) == 0) {
                extensions.push_back(VK_KHR_PORTABILITY_SUBSET_EXTENSION_NAME);
            }
        }
        float priority = 1;
        VkDeviceQueueCreateInfo queueInfo{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
        queueInfo.queueFamilyIndex = family;
        queueInfo.queueCount = 1;
        queueInfo.pQueuePriorities = &priority;
        VkDeviceCreateInfo deviceInfo{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
        deviceInfo.queueCreateInfoCount = 1;
        deviceInfo.pQueueCreateInfos = &queueInfo;
        deviceInfo.enabledExtensionCount = static_cast<uint32_t>(extensions.size());
        deviceInfo.ppEnabledExtensionNames = extensions.data();
        check(vkCreateDevice(physical, &deviceInfo, nullptr, &device), "vkCreateDevice");
        vkGetDeviceQueue(device, family, 0, &queue);
        VkShaderModuleCreateInfo shaderInfo{VK_STRUCTURE_TYPE_SHADER_MODULE_CREATE_INFO};
        shaderInfo.codeSize = sizeof(computeSPIRV);
        shaderInfo.pCode = computeSPIRV;
        check(vkCreateShaderModule(device, &shaderInfo, nullptr, &shader), "vkCreateShaderModule");
        VkPipelineLayoutCreateInfo layoutInfo{VK_STRUCTURE_TYPE_PIPELINE_LAYOUT_CREATE_INFO};
        check(vkCreatePipelineLayout(device, &layoutInfo, nullptr, &layout), "vkCreatePipelineLayout");
    }

    MVKPerformanceStatistics stats() const {
        MVKPerformanceStatistics value{};
        size_t size = sizeof(value);
        check(vkGetPerformanceStatisticsMVK(device, &value, &size), "vkGetPerformanceStatisticsMVK");
        require(size == sizeof(value), "MoltenVK private performance API size changed");
        return value;
    }

    VkPipelineCache cache(const std::vector<uint8_t>& data = {}) const {
        VkPipelineCacheCreateInfo info{VK_STRUCTURE_TYPE_PIPELINE_CACHE_CREATE_INFO};
        info.initialDataSize = data.size();
        info.pInitialData = data.empty() ? nullptr : data.data();
        VkPipelineCache value = VK_NULL_HANDLE;
        check(vkCreatePipelineCache(device, &info, nullptr, &value), "vkCreatePipelineCache");
        return value;
    }

    VkPipeline pipeline(VkPipelineCache pipelineCache) const {
        VkComputePipelineCreateInfo info{VK_STRUCTURE_TYPE_COMPUTE_PIPELINE_CREATE_INFO};
        info.stage.sType = VK_STRUCTURE_TYPE_PIPELINE_SHADER_STAGE_CREATE_INFO;
        info.stage.stage = VK_SHADER_STAGE_COMPUTE_BIT;
        info.stage.module = shader;
        info.stage.pName = "main";
        info.layout = layout;
        VkPipeline value = VK_NULL_HANDLE;
        check(vkCreateComputePipelines(device, pipelineCache, 1, &info, nullptr, &value), "vkCreateComputePipelines");
        return value;
    }

    void dispatch(VkPipeline pipeline) const {
        VkCommandPoolCreateInfo poolInfo{VK_STRUCTURE_TYPE_COMMAND_POOL_CREATE_INFO};
        poolInfo.queueFamilyIndex = family;
        VkCommandPool pool = VK_NULL_HANDLE;
        check(vkCreateCommandPool(device, &poolInfo, nullptr, &pool), "vkCreateCommandPool");
        VkCommandBufferAllocateInfo allocation{VK_STRUCTURE_TYPE_COMMAND_BUFFER_ALLOCATE_INFO};
        allocation.commandPool = pool;
        allocation.level = VK_COMMAND_BUFFER_LEVEL_PRIMARY;
        allocation.commandBufferCount = 1;
        VkCommandBuffer commands = VK_NULL_HANDLE;
        check(vkAllocateCommandBuffers(device, &allocation, &commands), "vkAllocateCommandBuffers");
        VkCommandBufferBeginInfo begin{VK_STRUCTURE_TYPE_COMMAND_BUFFER_BEGIN_INFO};
        begin.flags = VK_COMMAND_BUFFER_USAGE_ONE_TIME_SUBMIT_BIT;
        check(vkBeginCommandBuffer(commands, &begin), "vkBeginCommandBuffer");
        vkCmdBindPipeline(commands, VK_PIPELINE_BIND_POINT_COMPUTE, pipeline);
        vkCmdDispatch(commands, 1, 1, 1);
        check(vkEndCommandBuffer(commands), "vkEndCommandBuffer");
        VkFenceCreateInfo fenceInfo{VK_STRUCTURE_TYPE_FENCE_CREATE_INFO};
        VkFence fence = VK_NULL_HANDLE;
        check(vkCreateFence(device, &fenceInfo, nullptr, &fence), "vkCreateFence");
        VkSubmitInfo submit{VK_STRUCTURE_TYPE_SUBMIT_INFO};
        submit.commandBufferCount = 1;
        submit.pCommandBuffers = &commands;
        check(vkQueueSubmit(queue, 1, &submit, fence), "vkQueueSubmit");
        check(vkWaitForFences(device, 1, &fence, VK_TRUE, 30'000'000'000ull), "vkWaitForFences");
        vkDestroyFence(device, fence, nullptr);
        vkDestroyCommandPool(device, pool, nullptr);
    }
};

int main(int argc, char** argv) {
    if (argc != 2) return 2;
    @autoreleasepool {
        NSMutableDictionary* report = [@{@"schema": @1, @"real_metal_execution": @NO,
            @"iphone_tested": @NO, @"fps_gain_claimed": @NO,
            @"queue_hooks": @"test executable adapters using real dispatch; product hooks unchanged"} mutableCopy];
        try {
            // Set before MoltenVK initialization. The producer's release code is used.
            setenv("MVK_CONFIG_PERFORMANCE_TRACKING", "1", 1);
            setenv("MVK_CONFIG_ACTIVITY_PERFORMANCE_LOGGING_STYLE", "0", 1);
            id<MTLDevice> metalDevice = MTLCreateSystemDefaultDevice();
            if (!metalDevice) {
                report[@"status"] = @"unavailable";
                report[@"reason"] = @"MTLCreateSystemDefaultDevice returned nil; no mock fallback";
                writeReport(argv[1], report);
                [report release];
                return 77;
            }
            report[@"metal_device"] = metalDevice.name;
            [metalDevice release];
            Context context;
            context.create();
            report[@"vulkan_device"] = @(context.deviceName.c_str());
            const auto initial = context.stats();
            VkPipelineCache seed = context.cache();
            VkPipeline seedPipeline = context.pipeline(seed);
            const auto seeded = context.stats();
            uint32_t seedCompiles = seeded.shaderCompilation.mslCompile.count - initial.shaderCompilation.mslCompile.count;
            report[@"seed_library_compiles"] = @(seedCompiles);
            require(seedCompiles == 1, "Seed pipeline must compile exactly one Metal library");
            context.dispatch(seedPipeline);
            report[@"real_metal_execution"] = @YES;
            size_t bytes = 0;
            check(vkGetPipelineCacheData(context.device, seed, &bytes, nullptr), "cache data size");
            std::vector<uint8_t> data(bytes);
            check(vkGetPipelineCacheData(context.device, seed, &bytes, data.data()), "cache data");
            data.resize(bytes);
            report[@"serialized_cache_bytes"] = @(bytes);
            require(bytes > 36, "Seed cache contains no serialized shader entry");
            vkDestroyPipeline(context.device, seedPipeline, nullptr);
            vkDestroyPipelineCache(context.device, seed, nullptr);

            const auto beforeImport = context.stats();
            VkPipelineCache restored = context.cache(data);
            const auto imported = context.stats();
            uint32_t importCompiles = imported.shaderCompilation.mslCompile.count - beforeImport.shaderCompilation.mslCompile.count;
            uint32_t importedEntries = imported.pipelineCache.readPipelineCache.count - beforeImport.pipelineCache.readPipelineCache.count;
            report[@"import_library_compiles"] = @(importCompiles);
            report[@"imported_shader_entries"] = @(importedEntries);
            require(importCompiles == 0, "Candidate import compiled a Metal library eagerly");
            require(importedEntries == 1, "Candidate import did not deserialize the seed shader entry");
            VkPipeline warmPipeline = context.pipeline(restored);
            const auto warmed = context.stats();
            uint32_t warmCompiles = warmed.shaderCompilation.mslCompile.count - imported.shaderCompilation.mslCompile.count;
            report[@"first_demand_library_compiles"] = @(warmCompiles);
            require(warmCompiles == 1, "First demand must compile exactly one imported Metal library");
            context.dispatch(warmPipeline);
            VkPipeline repeated = context.pipeline(restored);
            require(context.stats().shaderCompilation.mslCompile.count == warmed.shaderCompilation.mslCompile.count,
                    "Repeated demand compiled an imported Metal library twice");
            vkDestroyPipeline(context.device, repeated, nullptr);
            vkDestroyPipeline(context.device, warmPipeline, nullptr);
            vkDestroyPipelineCache(context.device, restored, nullptr);

            VkPipelineCache concurrent = context.cache(data);
            const auto beforeConcurrent = context.stats();
            constexpr size_t threadCount = 8;
            std::vector<VkPipeline> pipelines(threadCount, VK_NULL_HANDLE);
            std::atomic<unsigned> failures{0};
            std::atomic<bool> start{false};
            std::vector<std::thread> threads;
            for (size_t index = 0; index < threadCount; ++index) threads.emplace_back([&, index] {
                @autoreleasepool {
                    while (!start.load(std::memory_order_acquire)) std::this_thread::yield();
                    try { pipelines[index] = context.pipeline(concurrent); }
                    catch (...) { ++failures; }
                }
            });
            start.store(true, std::memory_order_release);
            for (auto& thread : threads) thread.join();
            const auto completed = context.stats();
            uint32_t concurrentCompiles = completed.shaderCompilation.mslCompile.count - beforeConcurrent.shaderCompilation.mslCompile.count;
            report[@"concurrent_threads"] = @(threadCount);
            report[@"concurrent_library_compiles"] = @(concurrentCompiles);
            report[@"concurrent_pipeline_failures"] = @(failures.load());
            require(failures == 0 && concurrentCompiles == 1, "Concurrent same-entry demands must compile one Metal library");
            context.dispatch(pipelines[0]);
            for (auto pipeline : pipelines) vkDestroyPipeline(context.device, pipeline, nullptr);
            vkDestroyPipelineCache(context.device, concurrent, nullptr);
            report[@"status"] = @"passed";
            report[@"limits"] = @"macOS compute cache probe only; no game, iPhone recovery, visual correctness or speedup measurement";
            writeReport(argv[1], report);
            [report release];
            return 0;
        } catch (const std::exception& error) {
            report[@"status"] = @"failed";
            report[@"error"] = @(error.what());
            writeReport(argv[1], report);
            [report release];
            return 1;
        }
    }
}
