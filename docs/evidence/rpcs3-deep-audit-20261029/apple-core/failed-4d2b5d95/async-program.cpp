#include <atomic>
#include <cassert>
#include <cstdint>
#include <iostream>
#include <memory>
#include <mutex>
#include <utility>
#include <vector>
using u32=uint32_t;using u64=uint64_t;using usz=size_t;using VkBool32=bool;
template<class T>using atomic_t=std::atomic<T>;
using shared_mutex=std::mutex;
#define ensure(x) assert(x)
enum class video_renderer{vulkan,other};enum class vk_gpu_scheduler_mode{safe,fast};
struct {struct{video_renderer renderer=video_renderer::vulkan;struct{bool asynchronous_texture_streaming=true;}vk;bool strict_rendering_mode=false;}video;}g_cfg;
struct Log{template<class...T>void notice(T&&...){}template<class...T>void error(T&&...){assert(false);}}rsx_log;
struct VkDependencyInfoKHR{u32 identity=42;};
struct Counts{u32 sema=0,event=0,deadSema=0,deadEvent=0,pools=0,destroyPools=0,cb=0,destroyCb=0,reset=0,signal=0,submit=0;};
static Counts counts;
namespace boundary{
struct render_device{u32 get_transfer_queue_family()const{return 3;}u32 get_transfer_queue()const{return 11;}};
static const render_device device;
inline const render_device* get_current_renderer(){return &device;}
enum class sync_domain{gpu};
struct command_pool{void create(render_device&,u32 q){assert(q==3);++counts.pools;}void destroy(){++counts.destroyPools;}};
struct queue_submit_t{u32 queue=0;};
struct command_buffer{u32 id=0;bool open=false;void create(command_pool&){id=++counts.cb;}void destroy(){assert(!open);++counts.destroyCb;}
 void begin(){assert(!open);open=true;}void end(){assert(open);open=false;}void submit(queue_submit_t& q,VkBool32){assert(!open&&q.queue==11);++counts.submit;}};
struct event{u32 id;event(const render_device&,sync_domain):id(++counts.event){}~event(){++counts.deadEvent;}
 void reset(){++counts.reset;}void signal(const command_buffer& c,const VkDependencyInfoKHR& d){assert(c.open&&d.identity==42);++counts.signal;}};
struct semaphore{u32 id;semaphore(const render_device&):id(++counts.sema){}~semaphore(){++counts.deadSema;}};
}
namespace before { namespace vk { using namespace boundary; }


#define VK_MAX_ASYNC_COMPUTE_QUEUES 256

namespace vk
{
	class AsyncTaskScheduler
	{
		// Vulkan resources
		std::vector<command_buffer> m_async_command_queue;
		command_pool m_command_pool;

		// Running state
		command_buffer* m_last_used_cb = nullptr;
		command_buffer* m_current_cb = nullptr;
		usz m_next_cb_index = 0;
		atomic_t<u64> m_submit_count = 0;

		// Scheduler
		shared_mutex m_config_mutex;
		bool m_options_initialized = false;
		bool m_use_host_scheduler = false;

		// Sync
		event* m_sync_label = nullptr;
		atomic_t<bool> m_sync_required = false;
		VkDependencyInfoKHR m_dependency_info{};

		static constexpr u32 events_pool_size = 16384;
		std::vector<std::unique_ptr<vk::event>> m_events_pool;
		atomic_t<u64> m_next_event_id = 0;

		std::vector<std::unique_ptr<vk::semaphore>> m_semaphore_pool;
		atomic_t<u64> m_next_semaphore_id = 0;

		shared_mutex m_submit_mutex;

		void init_config_options(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency);
		void delayed_init();
		void insert_sync_event();

	public:
		AsyncTaskScheduler(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency);
		~AsyncTaskScheduler();

		command_buffer* get_current();
		event* get_primary_sync_label();
		semaphore* get_sema();

		void flush(queue_submit_t& submit_info, VkBool32 force_flush);
		void destroy();

		// Inline getters
		inline bool is_recording() const { return m_current_cb != nullptr; }
		inline bool is_host_mode() const { return m_use_host_scheduler; }
	};
}


namespace vk
{
	AsyncTaskScheduler::AsyncTaskScheduler(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency)
	{
		if (g_cfg.video.renderer != video_renderer::vulkan || !g_cfg.video.vk.asynchronous_texture_streaming)
		{
			// Invalid renderer combination, do not proceed. This should never happen.
			// NOTE: If managed by fxo, this object may be created automatically on boot.
			rsx_log.notice("Vulkan async streaming is disabled. This thread will now exit.");
			return;
		}

		init_config_options(mode, queue_dependency);
	}

	AsyncTaskScheduler::~AsyncTaskScheduler()
	{
		if (!m_async_command_queue.empty())
		{
			// Driver resources should be destroyed before driver is detached or you get crashes. RAII won't save you here.
			rsx_log.error("Async task scheduler resources were not freed correctly!");
		}
	}

	void AsyncTaskScheduler::init_config_options(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency)
	{
		std::lock_guard lock(m_config_mutex);
		if (std::exchange(m_options_initialized, true))
		{
			// Nothing to do
			return;
		}

		m_use_host_scheduler = (mode == vk_gpu_scheduler_mode::safe) || g_cfg.video.strict_rendering_mode;
		rsx_log.notice("Asynchronous task scheduler is active running in %s mode", m_use_host_scheduler? "'Safe'" : "'Fast'");

		m_dependency_info = queue_dependency;
	}

	void AsyncTaskScheduler::delayed_init()
	{
		ensure(m_options_initialized);

		auto pdev = get_current_renderer();
		m_command_pool.create(*const_cast<render_device*>(pdev), pdev->get_transfer_queue_family());

		if (m_use_host_scheduler)
		{
			for (usz i = 0; i < events_pool_size; ++i)
			{
				auto sema = std::make_unique<semaphore>(*pdev);
				m_semaphore_pool.emplace_back(std::move(sema));
			}

			return;
		}

		for (usz i = 0; i < events_pool_size; ++i)
		{
			auto ev = std::make_unique<vk::event>(*pdev, sync_domain::gpu);
			m_events_pool.emplace_back(std::move(ev));
		}
	}

	void AsyncTaskScheduler::insert_sync_event()
	{
		ensure(m_current_cb);
		auto& sync_label = m_events_pool[m_next_event_id++ % events_pool_size];

		sync_label->reset();
		sync_label->signal(*m_current_cb, m_dependency_info);
		m_sync_label = sync_label.get();
	}

	command_buffer* AsyncTaskScheduler::get_current()
	{
		std::lock_guard lock(m_submit_mutex);
		m_sync_required = true;

		// 0. Anything still active?
		if (m_current_cb)
		{
			return m_current_cb;
		}

		// 1. Check if there is a 'next' entry
		if (m_async_command_queue.empty())
		{
			delayed_init();
		}
		else if (m_next_cb_index < m_async_command_queue.size())
		{
			m_current_cb = &m_async_command_queue[m_next_cb_index];
		}

		// 2. Create entry
		if (!m_current_cb)
		{
			if (m_next_cb_index == VK_MAX_ASYNC_COMPUTE_QUEUES)
			{
				m_next_cb_index = 0;
				m_current_cb = &m_async_command_queue[m_next_cb_index];
			}
			else
			{
				m_async_command_queue.emplace_back();
				m_current_cb = &m_async_command_queue.back();
				m_current_cb->create(m_command_pool);
			}
		}

		m_next_cb_index++;
		return m_current_cb;
	}

	event* AsyncTaskScheduler::get_primary_sync_label()
	{
		ensure(!m_use_host_scheduler);

		if (m_sync_required) [[unlikely]]
		{
			std::lock_guard lock(m_submit_mutex); // For some reason this is inexplicably expensive. WTF!
			ensure(m_current_cb);
			insert_sync_event();
			m_sync_required = false;
		}

		return std::exchange(m_sync_label, nullptr);
	}

	semaphore* AsyncTaskScheduler::get_sema()
	{
		if (m_semaphore_pool.empty())
		{
			delayed_init();
			ensure(!m_semaphore_pool.empty());
		}

		const u32 sema_id = static_cast<u32>(m_next_semaphore_id++ % m_semaphore_pool.size());
		return m_semaphore_pool[sema_id].get();
	}

	void AsyncTaskScheduler::flush(queue_submit_t& submit_info, VkBool32 force_flush)
	{
		if (!m_current_cb)
		{
			return;
		}

		submit_info.queue = get_current_renderer()->get_transfer_queue();

		std::lock_guard lock(m_submit_mutex);
		if (m_sync_required && !m_use_host_scheduler)
		{
			insert_sync_event();
		}

		m_current_cb->end();
		m_current_cb->submit(submit_info, force_flush);

		m_submit_count++;

		m_last_used_cb = m_current_cb;
		m_current_cb = nullptr;
		m_sync_required = false;
	}

	void AsyncTaskScheduler::destroy()
	{
		for (auto& cb : m_async_command_queue)
		{
			cb.destroy();
		}

		m_async_command_queue.clear();
		m_next_cb_index = 0;
		m_command_pool.destroy();
		m_events_pool.clear();
		m_semaphore_pool.clear();
	}
}
}
#define RPCS3_IOS
namespace after { namespace vk { using namespace boundary; }


#define VK_MAX_ASYNC_COMPUTE_QUEUES 256

namespace vk
{
	class AsyncTaskScheduler
	{
		// Vulkan resources
		std::vector<command_buffer> m_async_command_queue;
		command_pool m_command_pool;

		// Running state
		command_buffer* m_last_used_cb = nullptr;
		command_buffer* m_current_cb = nullptr;
		usz m_next_cb_index = 0;
		atomic_t<u64> m_submit_count = 0;

		// Scheduler
		shared_mutex m_config_mutex;
		bool m_options_initialized = false;
		bool m_use_host_scheduler = false;

		// Sync
		event* m_sync_label = nullptr;
		atomic_t<bool> m_sync_required = false;
		VkDependencyInfoKHR m_dependency_info{};

		static constexpr u32 events_pool_size = 16384;
		std::vector<std::unique_ptr<vk::event>> m_events_pool;
		atomic_t<u64> m_next_event_id = 0;

		std::vector<std::unique_ptr<vk::semaphore>> m_semaphore_pool;
		atomic_t<u64> m_next_semaphore_id = 0;

		shared_mutex m_submit_mutex;

		void init_config_options(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency);
		void delayed_init();
		void insert_sync_event();

	public:
		AsyncTaskScheduler(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency);
		~AsyncTaskScheduler();

		command_buffer* get_current();
		event* get_primary_sync_label();
		semaphore* get_sema();

		void flush(queue_submit_t& submit_info, VkBool32 force_flush);
		void destroy();

		// Inline getters
		inline bool is_recording() const { return m_current_cb != nullptr; }
		inline bool is_host_mode() const { return m_use_host_scheduler; }
	};
}


namespace vk
{
	AsyncTaskScheduler::AsyncTaskScheduler(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency)
	{
		if (g_cfg.video.renderer != video_renderer::vulkan || !g_cfg.video.vk.asynchronous_texture_streaming)
		{
			// Invalid renderer combination, do not proceed. This should never happen.
			// NOTE: If managed by fxo, this object may be created automatically on boot.
			rsx_log.notice("Vulkan async streaming is disabled. This thread will now exit.");
			return;
		}

		init_config_options(mode, queue_dependency);
	}

	AsyncTaskScheduler::~AsyncTaskScheduler()
	{
		if (!m_async_command_queue.empty())
		{
			// Driver resources should be destroyed before driver is detached or you get crashes. RAII won't save you here.
			rsx_log.error("Async task scheduler resources were not freed correctly!");
		}
	}

	void AsyncTaskScheduler::init_config_options(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency)
	{
		std::lock_guard lock(m_config_mutex);
		if (std::exchange(m_options_initialized, true))
		{
			// Nothing to do
			return;
		}

		m_use_host_scheduler = (mode == vk_gpu_scheduler_mode::safe) || g_cfg.video.strict_rendering_mode;
		rsx_log.notice("Asynchronous task scheduler is active running in %s mode", m_use_host_scheduler? "'Safe'" : "'Fast'");

		m_dependency_info = queue_dependency;
	}

	void AsyncTaskScheduler::delayed_init()
	{
		ensure(m_options_initialized);

		auto pdev = get_current_renderer();
		m_command_pool.create(*const_cast<render_device*>(pdev), pdev->get_transfer_queue_family());

		if (m_use_host_scheduler)
		{
#ifdef RPCS3_IOS
			// Keep the same reuse distance without creating thousands of driver
			// objects before the first upload. Each slot is populated on first use.
			m_semaphore_pool.resize(events_pool_size);
#else
			for (usz i = 0; i < events_pool_size; ++i)
			{
				auto sema = std::make_unique<semaphore>(*pdev);
				m_semaphore_pool.emplace_back(std::move(sema));
			}
#endif

			return;
		}

#ifdef RPCS3_IOS
		m_events_pool.resize(events_pool_size);
#else
		for (usz i = 0; i < events_pool_size; ++i)
		{
			auto ev = std::make_unique<vk::event>(*pdev, sync_domain::gpu);
			m_events_pool.emplace_back(std::move(ev));
		}
#endif
	}

	void AsyncTaskScheduler::insert_sync_event()
	{
		ensure(m_current_cb);
		auto& sync_label = m_events_pool[m_next_event_id++ % events_pool_size];
#ifdef RPCS3_IOS
		if (!sync_label)
		{
			sync_label = std::make_unique<vk::event>(*get_current_renderer(), sync_domain::gpu);
		}
#endif

		sync_label->reset();
		sync_label->signal(*m_current_cb, m_dependency_info);
		m_sync_label = sync_label.get();
	}

	command_buffer* AsyncTaskScheduler::get_current()
	{
		std::lock_guard lock(m_submit_mutex);
		m_sync_required = true;

		// 0. Anything still active?
		if (m_current_cb)
		{
			return m_current_cb;
		}

		// 1. Check if there is a 'next' entry
		if (m_async_command_queue.empty())
		{
			delayed_init();
		}
		else if (m_next_cb_index < m_async_command_queue.size())
		{
			m_current_cb = &m_async_command_queue[m_next_cb_index];
		}

		// 2. Create entry
		if (!m_current_cb)
		{
			if (m_next_cb_index == VK_MAX_ASYNC_COMPUTE_QUEUES)
			{
				m_next_cb_index = 0;
				m_current_cb = &m_async_command_queue[m_next_cb_index];
			}
			else
			{
				m_async_command_queue.emplace_back();
				m_current_cb = &m_async_command_queue.back();
				m_current_cb->create(m_command_pool);
			}
		}

		m_next_cb_index++;
		return m_current_cb;
	}

	event* AsyncTaskScheduler::get_primary_sync_label()
	{
		ensure(!m_use_host_scheduler);

		if (m_sync_required) [[unlikely]]
		{
			std::lock_guard lock(m_submit_mutex); // For some reason this is inexplicably expensive. WTF!
			ensure(m_current_cb);
			insert_sync_event();
			m_sync_required = false;
		}

		return std::exchange(m_sync_label, nullptr);
	}

	semaphore* AsyncTaskScheduler::get_sema()
	{
		if (m_semaphore_pool.empty())
		{
			delayed_init();
			ensure(!m_semaphore_pool.empty());
		}

		const u32 sema_id = static_cast<u32>(m_next_semaphore_id++ % m_semaphore_pool.size());
#ifdef RPCS3_IOS
		auto& sema = m_semaphore_pool[sema_id];
		if (!sema)
		{
			sema = std::make_unique<semaphore>(*get_current_renderer());
		}
		return sema.get();
#else
		return m_semaphore_pool[sema_id].get();
#endif
	}

	void AsyncTaskScheduler::flush(queue_submit_t& submit_info, VkBool32 force_flush)
	{
		if (!m_current_cb)
		{
			return;
		}

		submit_info.queue = get_current_renderer()->get_transfer_queue();

		std::lock_guard lock(m_submit_mutex);
		if (m_sync_required && !m_use_host_scheduler)
		{
			insert_sync_event();
		}

		m_current_cb->end();
		m_current_cb->submit(submit_info, force_flush);

		m_submit_count++;

		m_last_used_cb = m_current_cb;
		m_current_cb = nullptr;
		m_sync_required = false;
	}

	void AsyncTaskScheduler::destroy()
	{
		for (auto& cb : m_async_command_queue)
		{
			cb.destroy();
		}

		m_async_command_queue.clear();
		m_next_cb_index = 0;
		m_command_pool.destroy();
		m_events_pool.clear();
		m_semaphore_pool.clear();
	}
}
}
#undef RPCS3_IOS
namespace desktop { namespace vk { using namespace boundary; }


#define VK_MAX_ASYNC_COMPUTE_QUEUES 256

namespace vk
{
	class AsyncTaskScheduler
	{
		// Vulkan resources
		std::vector<command_buffer> m_async_command_queue;
		command_pool m_command_pool;

		// Running state
		command_buffer* m_last_used_cb = nullptr;
		command_buffer* m_current_cb = nullptr;
		usz m_next_cb_index = 0;
		atomic_t<u64> m_submit_count = 0;

		// Scheduler
		shared_mutex m_config_mutex;
		bool m_options_initialized = false;
		bool m_use_host_scheduler = false;

		// Sync
		event* m_sync_label = nullptr;
		atomic_t<bool> m_sync_required = false;
		VkDependencyInfoKHR m_dependency_info{};

		static constexpr u32 events_pool_size = 16384;
		std::vector<std::unique_ptr<vk::event>> m_events_pool;
		atomic_t<u64> m_next_event_id = 0;

		std::vector<std::unique_ptr<vk::semaphore>> m_semaphore_pool;
		atomic_t<u64> m_next_semaphore_id = 0;

		shared_mutex m_submit_mutex;

		void init_config_options(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency);
		void delayed_init();
		void insert_sync_event();

	public:
		AsyncTaskScheduler(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency);
		~AsyncTaskScheduler();

		command_buffer* get_current();
		event* get_primary_sync_label();
		semaphore* get_sema();

		void flush(queue_submit_t& submit_info, VkBool32 force_flush);
		void destroy();

		// Inline getters
		inline bool is_recording() const { return m_current_cb != nullptr; }
		inline bool is_host_mode() const { return m_use_host_scheduler; }
	};
}


namespace vk
{
	AsyncTaskScheduler::AsyncTaskScheduler(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency)
	{
		if (g_cfg.video.renderer != video_renderer::vulkan || !g_cfg.video.vk.asynchronous_texture_streaming)
		{
			// Invalid renderer combination, do not proceed. This should never happen.
			// NOTE: If managed by fxo, this object may be created automatically on boot.
			rsx_log.notice("Vulkan async streaming is disabled. This thread will now exit.");
			return;
		}

		init_config_options(mode, queue_dependency);
	}

	AsyncTaskScheduler::~AsyncTaskScheduler()
	{
		if (!m_async_command_queue.empty())
		{
			// Driver resources should be destroyed before driver is detached or you get crashes. RAII won't save you here.
			rsx_log.error("Async task scheduler resources were not freed correctly!");
		}
	}

	void AsyncTaskScheduler::init_config_options(vk_gpu_scheduler_mode mode, const VkDependencyInfoKHR& queue_dependency)
	{
		std::lock_guard lock(m_config_mutex);
		if (std::exchange(m_options_initialized, true))
		{
			// Nothing to do
			return;
		}

		m_use_host_scheduler = (mode == vk_gpu_scheduler_mode::safe) || g_cfg.video.strict_rendering_mode;
		rsx_log.notice("Asynchronous task scheduler is active running in %s mode", m_use_host_scheduler? "'Safe'" : "'Fast'");

		m_dependency_info = queue_dependency;
	}

	void AsyncTaskScheduler::delayed_init()
	{
		ensure(m_options_initialized);

		auto pdev = get_current_renderer();
		m_command_pool.create(*const_cast<render_device*>(pdev), pdev->get_transfer_queue_family());

		if (m_use_host_scheduler)
		{
#ifdef RPCS3_IOS
			// Keep the same reuse distance without creating thousands of driver
			// objects before the first upload. Each slot is populated on first use.
			m_semaphore_pool.resize(events_pool_size);
#else
			for (usz i = 0; i < events_pool_size; ++i)
			{
				auto sema = std::make_unique<semaphore>(*pdev);
				m_semaphore_pool.emplace_back(std::move(sema));
			}
#endif

			return;
		}

#ifdef RPCS3_IOS
		m_events_pool.resize(events_pool_size);
#else
		for (usz i = 0; i < events_pool_size; ++i)
		{
			auto ev = std::make_unique<vk::event>(*pdev, sync_domain::gpu);
			m_events_pool.emplace_back(std::move(ev));
		}
#endif
	}

	void AsyncTaskScheduler::insert_sync_event()
	{
		ensure(m_current_cb);
		auto& sync_label = m_events_pool[m_next_event_id++ % events_pool_size];
#ifdef RPCS3_IOS
		if (!sync_label)
		{
			sync_label = std::make_unique<vk::event>(*get_current_renderer(), sync_domain::gpu);
		}
#endif

		sync_label->reset();
		sync_label->signal(*m_current_cb, m_dependency_info);
		m_sync_label = sync_label.get();
	}

	command_buffer* AsyncTaskScheduler::get_current()
	{
		std::lock_guard lock(m_submit_mutex);
		m_sync_required = true;

		// 0. Anything still active?
		if (m_current_cb)
		{
			return m_current_cb;
		}

		// 1. Check if there is a 'next' entry
		if (m_async_command_queue.empty())
		{
			delayed_init();
		}
		else if (m_next_cb_index < m_async_command_queue.size())
		{
			m_current_cb = &m_async_command_queue[m_next_cb_index];
		}

		// 2. Create entry
		if (!m_current_cb)
		{
			if (m_next_cb_index == VK_MAX_ASYNC_COMPUTE_QUEUES)
			{
				m_next_cb_index = 0;
				m_current_cb = &m_async_command_queue[m_next_cb_index];
			}
			else
			{
				m_async_command_queue.emplace_back();
				m_current_cb = &m_async_command_queue.back();
				m_current_cb->create(m_command_pool);
			}
		}

		m_next_cb_index++;
		return m_current_cb;
	}

	event* AsyncTaskScheduler::get_primary_sync_label()
	{
		ensure(!m_use_host_scheduler);

		if (m_sync_required) [[unlikely]]
		{
			std::lock_guard lock(m_submit_mutex); // For some reason this is inexplicably expensive. WTF!
			ensure(m_current_cb);
			insert_sync_event();
			m_sync_required = false;
		}

		return std::exchange(m_sync_label, nullptr);
	}

	semaphore* AsyncTaskScheduler::get_sema()
	{
		if (m_semaphore_pool.empty())
		{
			delayed_init();
			ensure(!m_semaphore_pool.empty());
		}

		const u32 sema_id = static_cast<u32>(m_next_semaphore_id++ % m_semaphore_pool.size());
#ifdef RPCS3_IOS
		auto& sema = m_semaphore_pool[sema_id];
		if (!sema)
		{
			sema = std::make_unique<semaphore>(*get_current_renderer());
		}
		return sema.get();
#else
		return m_semaphore_pool[sema_id].get();
#endif
	}

	void AsyncTaskScheduler::flush(queue_submit_t& submit_info, VkBool32 force_flush)
	{
		if (!m_current_cb)
		{
			return;
		}

		submit_info.queue = get_current_renderer()->get_transfer_queue();

		std::lock_guard lock(m_submit_mutex);
		if (m_sync_required && !m_use_host_scheduler)
		{
			insert_sync_event();
		}

		m_current_cb->end();
		m_current_cb->submit(submit_info, force_flush);

		m_submit_count++;

		m_last_used_cb = m_current_cb;
		m_current_cb = nullptr;
		m_sync_required = false;
	}

	void AsyncTaskScheduler::destroy()
	{
		for (auto& cb : m_async_command_queue)
		{
			cb.destroy();
		}

		m_async_command_queue.clear();
		m_next_cb_index = 0;
		m_command_pool.destroy();
		m_events_pool.clear();
		m_semaphore_pool.clear();
	}
}
}

struct Result{std::vector<u32> ids;Counts final;u32 startupObjects=0,firstObjects=0,eightObjects=0;};
template<class Scheduler>Result run(bool host,bool strict=false){
 counts={};g_cfg.video.strict_rendering_mode=strict;Result r;
 {Scheduler s(host?vk_gpu_scheduler_mode::safe:vk_gpu_scheduler_mode::fast,{});
  assert(s.is_host_mode()==(host||strict));host=host||strict;
  for(u32 i=0;i<33000;++i){
   auto* cb=s.get_current();assert(s.get_current()==cb);cb->begin();assert(s.is_recording());
   if(i==0)r.startupObjects=counts.sema+counts.event;
   if(host){r.ids.push_back(s.get_sema()->id);}
   else{auto* ev=s.get_primary_sync_label();assert(ev);r.ids.push_back(ev->id);assert(!s.get_primary_sync_label());}
   if(i==0)r.firstObjects=counts.sema+counts.event;
   if(i==7)r.eightObjects=counts.sema+counts.event;
   boundary::queue_submit_t info;s.flush(info,i%2);assert(!s.is_recording());
   s.flush(info,false); // Empty flush must not submit or allocate.
  }
  if(!host){ // Flush may insert the event before a caller asks for its label.
   s.get_current()->begin();boundary::queue_submit_t info;s.flush(info,false);
   auto* ev=s.get_primary_sync_label();assert(ev&&ev->id==233);assert(!s.get_primary_sync_label());
  }
  s.destroy();
 }
 r.final=counts;assert(counts.sema==counts.deadSema&&counts.event==counts.deadEvent);
 assert(counts.cb==256&&counts.destroyCb==256&&counts.pools==1&&counts.destroyPools==1);
 assert(counts.submit==33000u+!host);assert(counts.signal==(!host?33001u:0u));
 return r;
}
int main(){
 u64 comparisons=0;
 for(auto mode:{0,1,2}){
  auto a=run<before::vk::AsyncTaskScheduler>(mode==1,mode==2);
  auto b=run<after::vk::AsyncTaskScheduler>(mode==1,mode==2);
  auto c=run<desktop::vk::AsyncTaskScheduler>(mode==1,mode==2);
  assert(a.ids==b.ids&&a.ids==c.ids);comparisons+=a.ids.size();
  assert(a.startupObjects==16384&&c.startupObjects==16384&&b.startupObjects==0);
  assert(a.firstObjects==16384&&b.firstObjects==1&&b.eightObjects==8);
  assert(a.final.sema==b.final.sema&&a.final.event==b.final.event);
  for(u32 i=0;i<a.ids.size();++i)assert(a.ids[i]==i%16384+1);
 }
 std::cout<<"{\"passed\":true,\"sameSlotIdentityChecks\":"<<comparisons
 <<",\"baselineStartupDriverObjects\":16384,\"candidateStartupDriverObjects\":0,\"candidateFirstUseObjects\":1,\"candidateAfterEightObjects\":8,\"fullCycleObjectsUnchanged\":16384,\"destroyedExactlyOnce\":true,\"desktopUnchanged\":true}\n";
}
