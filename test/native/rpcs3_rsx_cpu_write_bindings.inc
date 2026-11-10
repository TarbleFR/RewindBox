
// Production sampler guards, descriptor expiry, range registration and scoped
// invalidation are inserted verbatim. The cache adapter below models resource
// upload by retaining the exact payload hash; it runs the real section sync.
#include <memory>
#include <shared_mutex>

namespace rsx
{
    enum class texture_upload_context { shader_read, framebuffer_storage, blit_engine_src, blit_engine_dst };
    enum class surface_access { gpu_reference };
    namespace limits { constexpr u32 fragment_textures_count = 16, vertex_textures_count = 4; }
    inline renderer* current_model_renderer = nullptr;
    inline renderer* get_current_renderer() { return current_model_renderer; }
}

namespace binding_test
{
    using address_range32 = rsx::address_range32;
    using reader_lock = std::shared_lock<std::shared_mutex>;
    enum class deferred_request_command { nop, copy_image_dynamic, copy_image_static };
    struct image { virtual ~image() = default; };
    struct surface : image
    {
        u64 last_use_tag = 0;
        image* get_surface(rsx::surface_access) { return this; }
    };
    struct view { binding_test::image* value = nullptr; binding_test::image* image() { return value; } };
    struct surface_cache
    {
        using surface_type = surface*;
        u64 cache_tag = 0;
        surface* get_surface_at(u32) { return nullptr; }
        bool address_is_bound(u32) { return false; }
    };
    struct descriptor
    {
        rsx::texture_upload_context upload_context = rsx::texture_upload_context::shader_read;
        view* image_handle = nullptr;
        struct { image* external_handle = nullptr; bool do_not_cache = false; deferred_request_command op = deferred_request_command::nop; address_range32 cache_range; } external_subresource_desc;
        bool is_cyclic_reference = false;
        u32 ref_address = 0;
        u64 surface_cache_tag = 0, payload_hash = 0;
        tv::sampler_stamp ios_validation_stamp;
        address_range32 ios_validation_range;
        bool ios_direct_framebuffer = false;
        bool validate() const { return image_handle || external_subresource_desc.op != deferred_request_command::nop; }
        template <typename surface_store_type, typename surface_type = typename surface_store_type::surface_type>
        @IS_EXPIRED@
    };
    struct texture
    {
        u32 address = 0;
        u64 length = texture_size;
        bool active = false;
        u32 offset() const { return address; }
        u32 location() const { return address >= rsx::constants::local_mem_base ? CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER : CELL_GCM_LOCATION_MAIN; }
        bool enabled() const { return active; }
    };
    inline u64 get_texture_size(const texture& tex) { return tex.length; }
    struct entry
    {
        rsx::after::buffered_section section;
        u64 gpu_hash;
        explicit entry(u32 address) : section(address,texture_size)
        {
            section.protect(utils::protection::ro);
            gpu_hash = section.mem_hash;
        }
        void reset_validation() { section.reset_validation(); }
    };
    struct storage
    {
        std::vector<std::unique_ptr<entry>> entries;
        struct iterator
        {
            storage* owner;
            usz index;
            address_range32 range;
            void skip()
            {
                while (index < owner->entries.size())
                {
                    const auto& r = owner->entries[index]->section.cpu_range;
                    if (range.start <= r.end && r.start <= range.end) break;
                    index++;
                }
            }
            entry* operator->() const { return owner->entries[index].get(); }
            iterator& operator++() { index++; skip(); return *this; }
            bool operator!=(const iterator& other) const { return index != other.index; }
        };
        iterator range_begin(address_range32 range, int, bool) { iterator it{this,0,range}; it.skip(); return it; }
        iterator range_end() { return {this,entries.size(),{}}; }
    };
    struct cache
    {
        using sampled_image_descriptor = descriptor;
        std::shared_mutex m_cache_mutex;
        tv::sampler_bindings<rsx::limits::fragment_textures_count + rsx::limits::vertex_textures_count> m_sampler_validation;
        storage m_storage;
        static constexpr int full_range = 0;
        u64 lookups = 0, hashes = 0, uploads = 0;
        image dummy_image;
        view dummy_view{&dummy_image};

        @REQUIRES@
        @PREPARE@
        template <typename surface_store_type>
        @FINISH@
        @SCOPED@
        @BEFORE_SCOPED@

        descriptor upload_texture(u32&, const texture& tex, surface_cache&)
        {
            reader_lock lock(m_cache_mutex);
            lookups++;
            entry* item = nullptr;
            for (auto& e : m_storage.entries) if (e->section.cpu_range.start == tex.address) item = e.get();
            ensure(item);
            const u64 skip0 = tv::epoch_skips, hits0 = tp::hits;
            const bool unchanged = item->section.sync();
            hashes += 1 - (tv::epoch_skips - skip0) - (tp::hits - hits0);
            if (!unchanged)
            {
                uploads++;
                item->section.discard();
                item->section.protect(utils::protection::ro);
                item->gpu_hash = item->section.mem_hash;
            }
            descriptor result;
            result.image_handle = &dummy_view;
            result.ref_address = tex.address;
            result.payload_hash = item->gpu_hash;
            result.ios_validation_range = item->section.cpu_range;
            return result;
        }
        void write_scoped(u32 address, u32 seed, bool candidate)
        {
            std::unique_lock lock(m_cache_mutex);
            const auto range = address_range32::start_length(address,texture_size);
            if (candidate) revalidate_overlapping(range); else before_revalidate_overlapping(range);
            fill(address,texture_size,seed);
        }
    };
    struct renderer
    {
        cache m_texture_cache;
        surface_cache m_rtts;
        u32 command = 0;
        u32* m_current_command_buffer = &command;
        bool m_samplers_dirty = true;
        std::array<bool,16> m_textures_dirty{};
        std::array<bool,4> m_vertex_textures_dirty{};
        std::array<descriptor,20> samplers;
        std::array<texture,20> textures;
        std::array<bool,20> referenced{};
        u64 descriptor_revisits = 0;
        explicit renderer(u32 address)
        {
            for (u32 n = 0; n < 3; n++)
            {
                fill(address + n * texture_size,texture_size,37 + n);
                m_texture_cache.m_storage.entries.push_back(std::make_unique<entry>(address + n * texture_size));
            }
        }
        void draw(bool candidate)
        {
            auto check_surface_cache_sampler_valid = [&](descriptor* d, const texture&) { return !d->is_expired(m_rtts).first; };
            for (u32 i = 0; i < 16; i++)
            {
                auto& tex = textures[i];
                if (!tex.enabled() && !referenced[i]) continue;
                auto* sampler_state = &samplers[i];
                if (candidate)
                {
                    @AFTER_FS_GUARD@
                }
                else
                {
                    @BEFORE_FS_GUARD@
                }
                descriptor_revisits++;
                m_textures_dirty[i] = false;
                if (!tex.enabled()) { *sampler_state = {}; continue; }
                if (candidate)
                {
                    @FS_LOOKUP@
                }
                else
                {
                    *sampler_state = m_texture_cache.upload_texture(*m_current_command_buffer,tex,m_rtts);
                }
            }
            for (u32 i = 0; i < 4; i++)
            {
                auto& tex = textures[16+i];
                if (!tex.enabled() && !referenced[16+i]) continue;
                auto* sampler_state = &samplers[16+i];
                if (candidate)
                {
                    @AFTER_VS_GUARD@
                }
                else
                {
                    @BEFORE_VS_GUARD@
                }
                descriptor_revisits++;
                m_vertex_textures_dirty[i] = false;
                if (!tex.enabled()) { *sampler_state = {}; continue; }
                if (candidate)
                {
                    @VS_LOOKUP@
                }
                else
                {
                    *sampler_state = m_texture_cache.upload_texture(*m_current_command_buffer,tex,m_rtts);
                }
            }
            m_samplers_dirty = false;
        }
    };
}

int main()
{
    ensure(cpu_write_main() == 0);
    namespace bt = binding_test;
    constexpr u32 address = rsx::constants::local_mem_base;
    constexpr u64 reservation = u64{address} + (2u << 20);
    void* memory = mmap(nullptr,reservation,PROT_NONE,MAP_PRIVATE | MAP_ANONYMOUS | MAP_NORESERVE,-1,0);
    ensure(memory != MAP_FAILED);
    vm::g_sudo_addr = static_cast<u8*>(memory);
    ensure(mprotect(vm::g_sudo_addr + address,2u << 20,PROT_READ | PROT_WRITE) == 0);
    ensure(mprotect(vm::g_sudo_addr + vm::main_base,vm::main_size,PROT_READ | PROT_WRITE) == 0);
    rsx::context context;
    rsx::current_model_renderer = &context.engine;
    tv::epoch_listener = nullptr;
    u64 scenarios = 0, stale_before = 0, stale_after = 0, unchanged_fastpaths = 0, scoped_unaffected = 0, scoped_zero_hashes = 0;
    for (bool candidate : {false,true})
    for (bool vertex : {false,true})
    for (bool composite : {false,true})
    for (bool enabled : {false,true})
    for (bool prehashed : {false,true})
    for (int event = 0; event < 3; event++)
    {
        tv::epoch_enabled = enabled;
        tp::enabled = prehashed;
        bt::renderer model(address);
        const u32 slot = vertex ? 16 : 0;
        model.textures[slot] = {address,texture_size,true};
        model.textures[slot+1] = {address+texture_size,texture_size,true};
        model.draw(candidate);
        if (composite)
        {
            auto& descriptor = model.samplers[slot];
            descriptor.upload_context = rsx::texture_upload_context::framebuffer_storage;
            descriptor.image_handle = nullptr;
            descriptor.external_subresource_desc.op = bt::deferred_request_command::copy_image_static;
            descriptor.external_subresource_desc.cache_range = descriptor.ios_validation_range;
            model.m_texture_cache.finish_sampler_validation(slot,descriptor,descriptor.ios_validation_stamp,model.m_rtts);
        }
        const u64 before = model.m_texture_cache.lookups;
        for (int n = 0; n < 100; n++) model.draw(candidate);
        ensure(model.m_texture_cache.lookups == before);
        unchanged_fastpaths += 200;
        const u64 old_epoch = tv::current_epoch();
        const u64 old_hash = model.samplers[slot].payload_hash;
        tp::publish(address,texture_size,old_epoch,old_hash);
        if (event == 0)
        {
            context.registers.dst = address;
            context.registers.dma = CELL_GCM_CONTEXT_DMA_MEMORY_FRAME_BUFFER;
            context.ctrl.put = context.fifo.address + context.fifo.count * 4;
            fill(context.fifo.address,context.fifo.count * 4,193);
            rsx::nv308a_after::color::impl(&context,NV308A_COLOR,0);
        }
        if (event == 1)
        {
            fill(address,texture_size,193);
            tv::advance_epoch(); // Production FIFO read_put() calls this after observing a new guest PUT.
        }
        if (event == 2) model.m_texture_cache.write_scoped(address,193,candidate);
        // A worker may finish an old-epoch hash after the notification. The real
        // lookup still rejects its old tag, or the scoped section bypasses it.
        tp::publish(address,texture_size,old_epoch,old_hash);
        const u64 expected = tp::range_hash(vm::_ptr<u8>(address),texture_size);
        const u64 hashes0 = model.m_texture_cache.hashes;
        model.draw(candidate);
        const bool stale = model.samplers[slot].payload_hash != expected;
        ensure(stale == !candidate);
        if (candidate) stale_after += stale; else stale_before += stale;
        if (candidate)
        {
            ensure(model.m_texture_cache.uploads == 1);
            ensure(model.m_texture_cache.lookups - before == (event == 2 ? 1u : 2u));
            if (event == 2)
            {
                ensure(model.m_texture_cache.hashes - hashes0 == 1);
                scoped_unaffected++;
            }
        }
        scenarios++;
    }
    // Frequent surface commits elsewhere must not make all active samplers do
    // cache lookups. Two bindings, 1,000 disjoint scoped writes, zero lookups,
    // zero hashes and zero resource uploads between the existing draws.
    for (bool enabled : {false,true})
    {
        tv::epoch_enabled = enabled;
        tp::enabled = false;
        bt::renderer model(address);
        model.textures[0] = {address,texture_size,true};
        model.textures[16] = {address+texture_size,texture_size,true};
        model.draw(true);
        const u64 lookups0 = model.m_texture_cache.lookups, hashes0 = model.m_texture_cache.hashes, uploads0 = model.m_texture_cache.uploads;
        for (u32 n = 0; n < 1000; n++)
        {
            model.m_texture_cache.write_scoped(address+2*texture_size,193+n,true);
            model.draw(true);
        }
        ensure(model.m_texture_cache.lookups == lookups0 && model.m_texture_cache.hashes == hashes0 && model.m_texture_cache.uploads == uploads0);
        scoped_zero_hashes += 2000;
    }
    // Unknown, tiled and wrapping spans conservatively participate in every
    // scoped write. Known mip-tail/pitch bytes participate in the exact span.
    u64 range_cases = 0;
    {
        bt::cache cache;
        for (const auto& [start,length] : {std::pair<u32,u64>{address,0}, {0xfffffff0u,32}, {0,1ull<<32}, {address,texture_size}})
        {
            context.engine.tiled = length == texture_size;
            bt::descriptor d;
            d.image_handle = &cache.dummy_view;
            d.ios_validation_range = {start,static_cast<u32>(start+length-1)};
            auto stamp = cache.prepare_sampler_validation(0);
            cache.finish_sampler_validation(0,d,stamp,bt::surface_cache{});
            ensure(!cache.sampler_requires_validation(0,d));
            { std::unique_lock lock(cache.m_cache_mutex); cache.m_sampler_validation.invalidate(0x1234,4); }
            ensure(cache.sampler_requires_validation(0,d));
            range_cases++;
        }
        context.engine.tiled = false;
        bt::descriptor d;
        d.image_handle = &cache.dummy_view;
        d.ios_validation_range = bt::address_range32::start_length(address,texture_size);
        auto stamp = cache.prepare_sampler_validation(0);
        cache.finish_sampler_validation(0,d,stamp,bt::surface_cache{});
        { std::unique_lock lock(cache.m_cache_mutex); cache.m_sampler_validation.invalidate(address+texture_size,4); }
        ensure(!cache.sampler_requires_validation(0,d));
        { std::unique_lock lock(cache.m_cache_mutex); cache.m_sampler_validation.invalidate(address+texture_size-1,1); }
        ensure(cache.sampler_requires_validation(0,d));
        range_cases += 2;
        // Empty/uninitialized stamps never count as validated, including when
        // epochs are disabled, and framebuffer expiry keeps its original path.
        tv::epoch_enabled = false;
        ensure(!cache.sampler_requires_validation(1,bt::descriptor{})); // legacy invalid-descriptor fastpath
        bt::descriptor valid_without_stamp;
        valid_without_stamp.image_handle = &cache.dummy_view;
        ensure(cache.sampler_requires_validation(1,valid_without_stamp));
        d.upload_context = rsx::texture_upload_context::framebuffer_storage;
        bt::surface real_rtt;
        bt::view rtt_view{&real_rtt};
        d.image_handle = &rtt_view;
        cache.finish_sampler_validation(0,d,stamp,bt::surface_cache{});
        ensure(!cache.sampler_requires_validation(0,d));
        range_cases += 2;
        // A clipped local view may be labelled FBO but must not inherit the
        // direct-RTT exemption merely from that label and a non-null handle.
        d.image_handle = &cache.dummy_view;
        stamp = cache.prepare_sampler_validation(0);
        cache.finish_sampler_validation(0,d,stamp,bt::surface_cache{});
        ensure(!d.ios_direct_framebuffer && !cache.sampler_requires_validation(0,d));
        { std::unique_lock lock(cache.m_cache_mutex); cache.m_sampler_validation.invalidate(address,4); }
        ensure(cache.sampler_requires_validation(0,d));
        range_cases++;
    }
    // Switching the hashing lever cannot make the cached binding stamp 0 or
    // suppress a later synchronization notification.
    for (bool start_enabled : {false,true})
    {
        tv::epoch_enabled = start_enabled;
        tp::enabled = false;
        bt::renderer model(address);
        model.textures[0] = {address,texture_size,true};
        model.draw(true);
        tv::epoch_enabled = !start_enabled;
        fill(address,texture_size,193);
        tv::advance_epoch();
        model.draw(true);
        ensure(model.samplers[0].payload_hash == tp::range_hash(vm::_ptr<u8>(address),texture_size));
        ensure(model.m_texture_cache.uploads == 1);
        range_cases++;
    }
    for (bool vertex : {false,true})
    {
        bt::renderer model(address);
        const u32 slot = vertex ? 16 : 0;
        model.textures[slot] = {address,texture_size,true};
        model.referenced[slot] = true;
        model.draw(true);
        model.textures[slot].active = false;
        (vertex ? model.m_vertex_textures_dirty[0] : model.m_textures_dirty[0]) = true;
        model.draw(true);
        ensure(!model.samplers[slot].validate());
        const u64 revisit0 = model.descriptor_revisits;
        for (int n = 0; n < 100; n++) model.draw(true);
        ensure(model.descriptor_revisits == revisit0);
        model.textures[slot].active = true;
        (vertex ? model.m_vertex_textures_dirty[0] : model.m_textures_dirty[0]) = true;
        fill(address,texture_size,77);
        tv::advance_epoch();
        model.draw(true);
        ensure(model.samplers[slot].payload_hash == tp::range_hash(vm::_ptr<u8>(address),texture_size));
        range_cases++;
    }
    // Both sides of registration vs scoped-write ordering under the actual
    // reader/exclusive-lock contract. No pointer to an old entry is retained.
    u64 race_cases = 0;
    for (int n = 0; n < 100; n++)
    {
        bt::renderer model(address);
        auto& cache = model.m_texture_cache;
        bt::texture old_tex{address,texture_size,true}, new_tex{address+texture_size,texture_size,true};
        auto old_stamp = cache.prepare_sampler_validation(0);
        bt::descriptor old_descriptor;
        old_descriptor.image_handle = &cache.dummy_view;
        old_descriptor.ios_validation_range = bt::address_range32::start_length(old_tex.address,texture_size);
        cache.finish_sampler_validation(0,old_descriptor,old_stamp,model.m_rtts);
        bt::descriptor fresh;
        std::unique_lock writer(cache.m_cache_mutex);
        std::thread reader([&]
        {
            const auto stamp = cache.prepare_sampler_validation(0);
            fresh = cache.upload_texture(model.command,new_tex,model.m_rtts);
            cache.finish_sampler_validation(0,fresh,stamp,model.m_rtts);
        });
        cache.revalidate_overlapping(bt::address_range32::start_length(new_tex.address,texture_size));
        fill(new_tex.address,texture_size,193+n);
        writer.unlock();
        reader.join();
        ensure(fresh.payload_hash == tp::range_hash(vm::_ptr<u8>(new_tex.address),texture_size));
        ensure(!cache.sampler_requires_validation(0,fresh));
        race_cases++;

        const auto stamp = cache.prepare_sampler_validation(0);
        std::thread after_register([&] { cache.write_scoped(old_tex.address,71+n,true); });
        after_register.join();
        fresh = cache.upload_texture(model.command,old_tex,model.m_rtts);
        cache.finish_sampler_validation(0,fresh,stamp,model.m_rtts);
        ensure(fresh.payload_hash == tp::range_hash(vm::_ptr<u8>(old_tex.address),texture_size));
        ensure(cache.sampler_requires_validation(0,fresh)); // conservative retry, not a falsely fresh stamp
        race_cases++;
    }
    tp::stop();
    ensure(stale_before == 48 && stale_after == 0);
    std::printf("{\"passed\":true,\"boundDrawScenarios\":%llu,\"baselineStaleGpuPayloads\":%llu,\"candidateStaleGpuPayloads\":%llu,"
                "\"unchangedBindingFastpaths\":%llu,\"scopedUntouchedBindingChecks\":%llu,\"disjointScopedDrawsWithoutLookupHashOrUpload\":%llu,"
                "\"rangeAndDisabledCases\":%llu,\"registrationWriteRaceCases\":%llu,\"rangeStorageHasNoSectionPointers\":true,\"physicalGpuModelled\":true}\n",
                static_cast<unsigned long long>(scenarios),static_cast<unsigned long long>(stale_before),static_cast<unsigned long long>(stale_after),
                static_cast<unsigned long long>(unchanged_fastpaths),static_cast<unsigned long long>(scoped_unaffected),static_cast<unsigned long long>(scoped_zero_hashes),
                static_cast<unsigned long long>(range_cases),static_cast<unsigned long long>(race_cases));
    munmap(memory,reservation);
}
