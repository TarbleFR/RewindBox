// SPDX-License-Identifier: GPL-2.0-only
// Core 928 host model of the renderer's settle function (REWINDBOX_GPU_BACKGROUND_GATE_927,
// REWINDBOX_GPU_DEACTIVATION_GATE_928).
//
// The text of vk::ios_settle_queues and vk::ios_release_settle_fences is copied from the Core source by the test
// (rpcs3/Emu/RSX/VK/VKCommandStream.cpp -> settle928_text.inc) and compiled here unchanged, against a model of the six
// Vulkan calls it makes and of the submit lock. The model counts what is given to the queues: the point of the
// "resume" argument is that the background notification gives them nothing new when the settle of the deactivation
// already did. No iPhone or GPU result is inferred.
#include <array>
#include <atomic>
#include <chrono>
#include <cstdint>
#include <cstdio>
#include <mutex>
#include <thread>
#include <vector>

using u32 = std::uint32_t;
using u64 = std::uint64_t;

template <typename T>
static u32 size32(const T& container)
{
	return static_cast<u32>(container.size());
}

static int g_failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #condition); g_failures++; } } while (0)

// ---- Model of Vulkan --------------------------------------------------------------------------------------------
struct fence_model
{
	std::atomic<bool> signalled{false};
};

struct queue_model
{
	int index = 0;
};

struct device_model
{
};

using VkFence = fence_model*;
using VkQueue = queue_model*;
using VkDevice = device_model*;
using VkResult = int;
using VkBool32 = u32;
struct VkSubmitInfo;
struct VkAllocationCallbacks;
struct VkFenceCreateInfo
{
	int sType = 0;
};

#define VK_NULL_HANDLE nullptr
constexpr VkResult VK_SUCCESS = 0, VK_NOT_READY = 1, VK_TIMEOUT = 2;
constexpr VkBool32 VK_TRUE = 1;
constexpr int VK_STRUCTURE_TYPE_FENCE_CREATE_INFO = 8;

struct gpu_model
{
	std::mutex mutex;
	std::vector<VkFence> pending; // submitted, not completed
	bool completes = true;        // a submission completes at once
	std::atomic<u64> created{0}, destroyed{0}, submits{0}, waits{0};

	void complete_all()
	{
		std::lock_guard lock(mutex);
		for (VkFence fence : pending)
		{
			fence->signalled.store(true);
		}

		pending.clear();
	}
};

static gpu_model g_gpu;

static VkResult vkCreateFence(VkDevice, const VkFenceCreateInfo* info, const VkAllocationCallbacks*, VkFence* fence)
{
	CHECK(info->sType == VK_STRUCTURE_TYPE_FENCE_CREATE_INFO);
	*fence = new fence_model;
	g_gpu.created.fetch_add(1);
	return VK_SUCCESS;
}

static void vkDestroyFence(VkDevice, VkFence fence, const VkAllocationCallbacks*)
{
	// A fence is destroyed only once its submission has completed (Vulkan requires it).
	CHECK(fence->signalled.load());
	delete fence;
	g_gpu.destroyed.fetch_add(1);
}

static VkResult vkGetFenceStatus(VkDevice, VkFence fence)
{
	return fence->signalled.load() ? VK_SUCCESS : VK_NOT_READY;
}

static VkResult vkQueueSubmit(VkQueue queue, u32 count, const VkSubmitInfo* submits, VkFence fence)
{
	CHECK(queue && count == 0 && !submits && fence); // an empty submission with a fence
	g_gpu.submits.fetch_add(1);
	std::lock_guard lock(g_gpu.mutex);
	if (g_gpu.completes)
	{
		fence->signalled.store(true);
	}
	else
	{
		g_gpu.pending.push_back(fence);
	}

	return VK_SUCCESS;
}

static VkResult vkWaitForFences(VkDevice, u32 count, const VkFence* fences, VkBool32 all, u64 timeout_ns)
{
	CHECK(all == VK_TRUE && count > 0);
	g_gpu.waits.fetch_add(1);
	const auto end = std::chrono::steady_clock::now() + std::chrono::nanoseconds(timeout_ns);
	for (;;)
	{
		bool done = true;
		for (u32 i = 0; i < count; i++)
		{
			done = done && fences[i]->signalled.load();
		}

		if (done)
		{
			return VK_SUCCESS;
		}

		if (std::chrono::steady_clock::now() >= end)
		{
			return VK_TIMEOUT;
		}

		std::this_thread::sleep_for(std::chrono::milliseconds(1));
	}
}

// The submit lock of the renderer: held is a submitter that entered before the gate closed.
struct submit_lock_model
{
	std::atomic<bool> held{false};
	std::atomic<u64> locked{0}, unlocked{0};

	bool try_lock()
	{
		if (held.load())
		{
			return false;
		}

		locked.fetch_add(1);
		return true;
	}

	void unlock()
	{
		unlocked.fetch_add(1);
	}
};

namespace vk
{
	struct render_device
	{
		device_model device;
		queue_model graphics{0}, transfer{1};

		operator VkDevice() const { return const_cast<device_model*>(&device); }
		// MoltenVK on the iPhone: the presenting queue is the graphics queue, the transfer queue is another one.
		VkQueue get_graphics_queue() const { return const_cast<queue_model*>(&graphics); }
		VkQueue get_present_queue() const { return const_cast<queue_model*>(&graphics); }
		VkQueue get_transfer_queue() const { return const_cast<queue_model*>(&transfer); }
	};

	static const render_device* g_render_device = nullptr;
	static submit_lock_model g_submit_mutex;

	namespace
	{
		std::mutex s_ios_settle_fences_mutex;
		std::vector<VkFence> s_ios_unsettled_fences;
		bool s_ios_settle_reached_queues = false;
	}

#include "settle928_text.inc"
}

using namespace std::chrono_literals;

int main()
{
	static const vk::render_device device;

	// No renderer: nothing to settle.
	CHECK(vk::ios_settle_queues(50ms, false) && vk::ios_settle_queues(50ms, true) && g_gpu.submits.load() == 0);
	vk::g_render_device = &device;

	// 1. The queues complete: one empty submission with a fence on each distinct queue, waited for, destroyed.
	CHECK(vk::ios_settle_queues(1000ms, false));
	CHECK(g_gpu.submits.load() == 2 && g_gpu.created.load() == 2 && g_gpu.destroyed.load() == 2 && g_gpu.waits.load() == 1);
	CHECK(vk::g_submit_mutex.locked.load() == 1 && vk::g_submit_mutex.unlocked.load() == 1);
	CHECK(vk::s_ios_unsettled_fences.empty() && vk::s_ios_settle_reached_queues);
	// Resumed after a settle that left nothing: true, and nothing is given to the queues.
	CHECK(vk::ios_settle_queues(1000ms, true) && g_gpu.submits.load() == 2 && g_gpu.waits.load() == 1);

	// 2. The GPU has not finished within the limit: false, the fences are kept (their submissions still own them).
	g_gpu.completes = false;
	auto begin = std::chrono::steady_clock::now();
	CHECK(!vk::ios_settle_queues(30ms, false));
	CHECK(std::chrono::steady_clock::now() - begin >= 25ms);
	CHECK(g_gpu.submits.load() == 4 && g_gpu.created.load() == 4 && g_gpu.destroyed.load() == 2);
	CHECK(vk::s_ios_unsettled_fences.size() == 2 && vk::s_ios_settle_reached_queues);
	// The background notification resumes it: it waits for those fences and gives the queues nothing new.
	CHECK(!vk::ios_settle_queues(30ms, true));
	CHECK(g_gpu.submits.load() == 4 && g_gpu.created.load() == 4 && vk::s_ios_unsettled_fences.size() == 2);
	CHECK(vk::g_submit_mutex.locked.load() == 2); // the submit lock is not taken by a resumed wait
	g_gpu.complete_all();
	CHECK(vk::ios_settle_queues(30ms, true));
	CHECK(g_gpu.submits.load() == 4 && g_gpu.destroyed.load() == 4 && vk::s_ios_unsettled_fences.empty());

	// 3. A submitter holds the submit lock for longer than the limit: false, and the queues were not reached.
	g_gpu.completes = true;
	vk::g_submit_mutex.held.store(true);
	begin = std::chrono::steady_clock::now();
	CHECK(!vk::ios_settle_queues(30ms, false));
	CHECK(std::chrono::steady_clock::now() - begin >= 25ms);
	CHECK(g_gpu.submits.load() == 4 && !vk::s_ios_settle_reached_queues);
	// Resumed: nothing was left to wait for because nothing was submitted, so the whole settle is done now.
	vk::g_submit_mutex.held.store(false);
	CHECK(vk::ios_settle_queues(1000ms, true));
	CHECK(g_gpu.submits.load() == 6 && g_gpu.created.load() == 6 && g_gpu.destroyed.load() == 6 && vk::s_ios_settle_reached_queues);

	// 4. A later closing after a settle that timed out: the kept fences that have signalled since are released, and
	// the new settle is a whole one.
	g_gpu.completes = false;
	CHECK(!vk::ios_settle_queues(20ms, false));
	CHECK(vk::s_ios_unsettled_fences.size() == 2 && g_gpu.submits.load() == 8);
	g_gpu.complete_all();
	g_gpu.completes = true;
	CHECK(vk::ios_settle_queues(1000ms, false));
	CHECK(g_gpu.submits.load() == 10 && g_gpu.created.load() == 10 && g_gpu.destroyed.load() == 10 && vk::s_ios_unsettled_fences.empty());

	// 5. The renderer goes away with fences still kept: they are destroyed once its device is idle.
	g_gpu.completes = false;
	CHECK(!vk::ios_settle_queues(20ms, false) && vk::s_ios_unsettled_fences.size() == 2);
	g_gpu.complete_all(); // vkDeviceWaitIdle of the destructor
	vk::ios_release_settle_fences();
	CHECK(vk::s_ios_unsettled_fences.empty() && g_gpu.created.load() == 12 && g_gpu.destroyed.load() == 12);
	CHECK(vk::g_submit_mutex.locked.load() == vk::g_submit_mutex.unlocked.load()); // the submit lock was always given back

	std::printf("{\"failures\": %d, \"submits\": %llu, \"fencesCreated\": %llu, \"fencesDestroyed\": %llu}\n", g_failures,
		static_cast<unsigned long long>(g_gpu.submits.load()), static_cast<unsigned long long>(g_gpu.created.load()),
		static_cast<unsigned long long>(g_gpu.destroyed.load()));
	return g_failures ? 1 : 0;
}
