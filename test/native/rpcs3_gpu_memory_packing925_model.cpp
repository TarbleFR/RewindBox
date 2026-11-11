// SPDX-License-Identifier: GPL-2.0-only
// REWINDBOX_GPU_MEMORY_PACKING_925 host model. The Vulkan Memory Allocator is the revision RPCS3 pins (3.3.0), behind a
// mock Vulkan device: one device-local heap of 7,989,460,992 bytes (the heap MoltenVK reported on the iPhone), 64 MiB
// preferred blocks (vkutils/VRAMBudgetPolicy.h). The placement rule is the production header ios/IOSGpuMemoryPacking.h.
// Load shaped on Black Ops II, build 724: 338 MiB of system buffers and 183 MiB of surfaces that stay, then textures of
// 16 KiB to 4 MiB allocated and released at random, their live total rising to 290 MiB and staying there.
// "before": the fastest strategy for everything (the only one iOS ever used). "after": the lever on.
// Device bytes are what the mock device has handed out (blocks and dedicated memory): on the iPhone each is a Metal
// heap. This model says nothing of the time Metal takes to create a heap, nor of the device's own load.
#define VMA_VULKAN_VERSION 1000000
#define VMA_STATIC_VULKAN_FUNCTIONS 0
#define VMA_DYNAMIC_VULKAN_FUNCTIONS 0
#define VMA_DEDICATED_ALLOCATION 0
#define VMA_BIND_MEMORY2 0
#define VMA_MEMORY_BUDGET 0
#define VMA_IMPLEMENTATION
#include <vulkan/vulkan_core.h>
#include "vk_mem_alloc.h"
#include "ios/IOSGpuMemoryPacking.h"
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <vector>

static uint64_t g_device_bytes = 0;

static VKAPI_ATTR void VKAPI_CALL props(VkPhysicalDevice, VkPhysicalDeviceProperties* p)
{
	*p = {};
	p->limits.bufferImageGranularity = 1;
	p->limits.nonCoherentAtomSize = 1;
	p->limits.maxMemoryAllocationCount = 1u << 20;
}

static VKAPI_ATTR void VKAPI_CALL memprops(VkPhysicalDevice, VkPhysicalDeviceMemoryProperties* p)
{
	*p = {};
	p->memoryHeapCount = 1;
	p->memoryHeaps[0] = {7989460992ull, VK_MEMORY_HEAP_DEVICE_LOCAL_BIT};
	p->memoryTypeCount = 1;
	p->memoryTypes[0] = {VK_MEMORY_PROPERTY_DEVICE_LOCAL_BIT, 0};
}

struct mem
{
	uint64_t size;
};

static VKAPI_ATTR VkResult VKAPI_CALL alloc_memory(VkDevice, const VkMemoryAllocateInfo* i, const VkAllocationCallbacks*, VkDeviceMemory* m)
{
	g_device_bytes += i->allocationSize;
	*m = reinterpret_cast<VkDeviceMemory>(new mem{i->allocationSize});
	return VK_SUCCESS;
}

static VKAPI_ATTR void VKAPI_CALL free_memory(VkDevice, VkDeviceMemory m, const VkAllocationCallbacks*)
{
	auto p = reinterpret_cast<mem*>(m);
	g_device_bytes -= p->size;
	delete p;
}

static VKAPI_ATTR VkResult VKAPI_CALL map_memory(VkDevice, VkDeviceMemory, VkDeviceSize, VkDeviceSize, VkMemoryMapFlags, void**) { return VK_ERROR_MEMORY_MAP_FAILED; }
static VKAPI_ATTR void VKAPI_CALL unmap_memory(VkDevice, VkDeviceMemory) {}
static VKAPI_ATTR VkResult VKAPI_CALL flush_ranges(VkDevice, uint32_t, const VkMappedMemoryRange*) { return VK_SUCCESS; }
static VKAPI_ATTR VkResult VKAPI_CALL bind_buffer(VkDevice, VkBuffer, VkDeviceMemory, VkDeviceSize) { return VK_SUCCESS; }
static VKAPI_ATTR VkResult VKAPI_CALL bind_image(VkDevice, VkImage, VkDeviceMemory, VkDeviceSize) { return VK_SUCCESS; }
static VKAPI_ATTR void VKAPI_CALL req_buffer(VkDevice, VkBuffer, VkMemoryRequirements* r) { *r = {}; }
static VKAPI_ATTR void VKAPI_CALL req_image(VkDevice, VkImage, VkMemoryRequirements* r) { *r = {}; }
static VKAPI_ATTR VkResult VKAPI_CALL create_buffer(VkDevice, const VkBufferCreateInfo*, const VkAllocationCallbacks*, VkBuffer*) { return VK_ERROR_UNKNOWN; }
static VKAPI_ATTR void VKAPI_CALL destroy_buffer(VkDevice, VkBuffer, const VkAllocationCallbacks*) {}
static VKAPI_ATTR VkResult VKAPI_CALL create_image(VkDevice, const VkImageCreateInfo*, const VkAllocationCallbacks*, VkImage*) { return VK_ERROR_UNKNOWN; }
static VKAPI_ATTR void VKAPI_CALL destroy_image(VkDevice, VkImage, const VkAllocationCallbacks*) {}
static VKAPI_ATTR void VKAPI_CALL copy_buffer(VkCommandBuffer, VkBuffer, VkBuffer, uint32_t, const VkBufferCopy*) {}

struct result
{
	double blocks_mib, live_mib, peak_blocks_mib;
};

static result run(bool lever, unsigned seed, double small_bias)
{
	g_device_bytes = 0;
	VmaVulkanFunctions f = {};
	f.vkGetPhysicalDeviceProperties = props;
	f.vkGetPhysicalDeviceMemoryProperties = memprops;
	f.vkAllocateMemory = alloc_memory;
	f.vkFreeMemory = free_memory;
	f.vkMapMemory = map_memory;
	f.vkUnmapMemory = unmap_memory;
	f.vkFlushMappedMemoryRanges = flush_ranges;
	f.vkInvalidateMappedMemoryRanges = flush_ranges;
	f.vkBindBufferMemory = bind_buffer;
	f.vkBindImageMemory = bind_image;
	f.vkGetBufferMemoryRequirements = req_buffer;
	f.vkGetImageMemoryRequirements = req_image;
	f.vkCreateBuffer = create_buffer;
	f.vkDestroyBuffer = destroy_buffer;
	f.vkCreateImage = create_image;
	f.vkDestroyImage = destroy_image;
	f.vkCmdCopyBuffer = copy_buffer;

	static int handle;
	VmaAllocatorCreateInfo info = {};
	info.physicalDevice = reinterpret_cast<VkPhysicalDevice>(&handle);
	info.device = reinterpret_cast<VkDevice>(&handle);
	info.instance = reinterpret_cast<VkInstance>(&handle);
	info.vulkanApiVersion = VK_API_VERSION_1_0;
	info.pVulkanFunctions = &f;
	info.preferredLargeHeapBlockSize = 64ull << 20;

	VmaAllocator a;
	if (vmaCreateAllocator(&info, &a) != VK_SUCCESS)
	{
		std::puts("create failed");
		std::exit(2);
	}

	std::mt19937_64 rng(seed);
	std::vector<std::pair<VmaAllocation, uint64_t>> live;
	uint64_t live_bytes = 0;
	double peak = 0;

	std::vector<VmaAllocation> pinned;
	// Static part: 338 MiB of system buffers (8..64 MiB each) and 183 MiB of surfaces (1..8 MiB each), never freed.
	auto add = [&](uint64_t bytes, bool keep)
	{
		VkMemoryRequirements r = {};
		r.size = (bytes + 4095) & ~4095ull;
		r.alignment = 4096;
		r.memoryTypeBits = 1;
		VmaAllocationCreateInfo c = {};
		// vkutils/memory.cpp: set_fastest_allocation_flags() and do_vma_alloc().
		c.flags = (lever ? VMA_ALLOCATION_CREATE_STRATEGY_MIN_MEMORY_BIT : VMA_ALLOCATION_CREATE_STRATEGY_MIN_TIME_BIT) |
			(rpcs3::ios::gpu_memory_packing::wants_dedicated(lever, r.size) ? VMA_ALLOCATION_CREATE_DEDICATED_MEMORY_BIT : 0);
		c.memoryTypeBits = 1;
		VmaAllocation h;
		if (vmaAllocateMemory(a, &r, &c, &h, nullptr) != VK_SUCCESS)
		{
			std::puts("alloc failed");
			std::exit(3);
		}
		if (keep)
		{
			live.push_back({h, r.size});
			live_bytes += r.size;
		}
		else
		{
			pinned.push_back(h);
		}
		return r.size;
	};
	uint64_t fixed = 0;
	while (fixed < (338ull << 20)) fixed += add(std::uniform_int_distribution<uint64_t>(8ull << 20, 48ull << 20)(rng), false);
	while (fixed < (521ull << 20)) fixed += add(std::uniform_int_distribution<uint64_t>(1ull << 20, 8ull << 20)(rng), false);

	// Textures: log-uniform 16 KiB .. 4 MiB biased small (mean about 270 KiB with bias 2), live total 0 -> 290 MiB then a plateau.
	auto size = [&]()
	{
		const double u = std::pow(std::uniform_real_distribution<double>(0, 1)(rng), small_bias);
		return static_cast<uint64_t>(16384.0 * std::pow(256.0, u));
	};
	const int steps = 120000;
	for (int step = 0; step < steps; step++)
	{
		const double target = 290.0 * std::min(1.0, step / (steps * 0.4)) * 1048576.0;
		for (int k = 0; k < 2; k++)
		{
			add(size(), true);
		}
		while (live_bytes > target && !live.empty())
		{
			const size_t i = std::uniform_int_distribution<size_t>(0, live.size() - 1)(rng);
			vmaFreeMemory(a, live[i].first);
			live_bytes -= live[i].second;
			live[i] = live.back();
			live.pop_back();
		}
		peak = std::max(peak, g_device_bytes / 1048576.0);
	}
	live_bytes += fixed;

	const result out{g_device_bytes / 1048576.0, live_bytes / 1048576.0, peak};
	for (auto& l : live)
	{
		vmaFreeMemory(a, l.first);
	}
	for (auto h : pinned)
	{
		vmaFreeMemory(a, h);
	}
	vmaDestroyAllocator(a);
	return out;
}

int main()
{
	namespace packing = rpcs3::ios::gpu_memory_packing;
	int failures = 0;
	// The rule: off places nothing alone; on, from dedicated_from up.
	if (packing::wants_dedicated(false, 64ull << 20) || packing::wants_dedicated(true, packing::dedicated_from - 1) ||
		!packing::wants_dedicated(true, packing::dedicated_from) || packing::dedicated_from != (1ull << 20))
	{
		std::fprintf(stderr, "rule check failed\n");
		failures++;
	}

	std::printf("{\"vma\": \"3.3.0\", \"blockMib\": 64, \"dedicatedFrom\": %llu, \"runs\": [", static_cast<unsigned long long>(packing::dedicated_from));
	bool first = true;
	for (double bias : {2.0, 3.0})
	{
		double before_device = 0, before_unused = 0, after_device = 0, after_unused = 0, live = 0;
		const int seeds = 3;
		for (unsigned seed = 1; seed <= seeds; seed++)
		{
			const auto b = run(false, seed, bias);
			const auto a = run(true, seed, bias);
			before_device += b.blocks_mib;
			before_unused += b.blocks_mib - b.live_mib;
			after_device += a.blocks_mib;
			after_unused += a.blocks_mib - a.live_mib;
			live += b.live_mib;
			// Same load, same live bytes; the lever must not hand out more device memory than the fastest strategy.
			if (std::fabs(a.live_mib - b.live_mib) > 0.5 || a.blocks_mib > b.blocks_mib)
			{
				std::fprintf(stderr, "seed %u bias %.0f: after %.0f MiB, before %.0f MiB\n", seed, bias, a.blocks_mib, b.blocks_mib);
				failures++;
			}
		}
		if (after_unused * 2 > before_unused)
		{
			std::fprintf(stderr, "bias %.0f: unused not halved (%.0f -> %.0f MiB)\n", bias, before_unused / seeds, after_unused / seeds);
			failures++;
		}
		std::printf("%s{\"sizeBias\": %.0f, \"liveMib\": %.0f, \"before\": {\"deviceMib\": %.0f, \"unusedMib\": %.0f}, \"after\": {\"deviceMib\": %.0f, \"unusedMib\": %.0f}}",
			first ? "" : ", ", bias, live / seeds, before_device / seeds, before_unused / seeds, after_device / seeds, after_unused / seeds);
		first = false;
	}
	std::printf("], \"passed\": %s}\n", failures ? "false" : "true");
	return failures ? 1 : 0;
}
