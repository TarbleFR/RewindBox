// Actual lookup, publication, abandonment and clear bodies. Fake pipelines
// replace GPU objects; real map/mutex/atomics protect the production hints.
namespace rpcs3::ios::shader_timing {
inline struct { std::atomic<u64> abandoned{0}; } pipeline_profile;
}
struct RecentCache {
    struct Pipeline { u32 id; };
    using pipeline_properties=vk::pipeline_props;
    using pipeline_type=Pipeline;
    using pipeline_storage_type=std::unique_ptr<Pipeline>;
    using reader_lock=std::shared_lock<std::shared_mutex>;
    // KEY_TYPES
    std::shared_mutex m_pipeline_mutex,m_vertex_mutex,m_fragment_mutex,m_decompiler_mutex;
    std::unordered_map<pipeline_key,pipeline_storage_type,pipeline_key_hash,pipeline_key_compare> m_storage;
    using stored_pipeline=decltype(m_storage)::value_type;
    std::array<std::atomic<const stored_pipeline*>,64> m_recent_pipelines{};
    std::unordered_set<pipeline_key,pipeline_key_hash,pipeline_key_compare> m_inline_builds;
    std::unordered_map<int,int> m_vertex_shader_cache,m_fragment_shader_cache;
    std::function<void()> notify_pipeline_compiled;
    void wake_pipeline_waiters() {}
    // FIND
    // PUBLISH
    // ABANDON
    // CLEAR
    static pipeline_key key(u32 v,u32 f,const vk::pipeline_props& p) { return {v,f,p}; }
    Pipeline* insert(pipeline_key k,u32 id) {
        k.hash=pipeline_key_hash::compute(k);
        auto p=std::make_unique<Pipeline>(Pipeline{id});return publish_pipeline(k,p);
    }
    void add_pending(pipeline_key k) {
        k.hash=pipeline_key_hash::compute(k);std::lock_guard lock(m_pipeline_mutex);
        m_storage.try_emplace(k,nullptr);
    }
    void erase_pending(pipeline_key k) { k.hash=pipeline_key_hash::compute(k);abandon_pipeline_build(k); }
};
void recent_pipeline_test() {
    RecentCache cache;
    const auto p=pipeline_base();
    auto key=RecentCache::key(4,1,p);
    const auto* first=cache.insert(key,1);
    assert(cache.find_cached_pipeline(key)==first && key.hash);
    for(unsigned i=0;i<10000;++i) {
        key.hash=0;
        assert(cache.find_cached_pipeline(key)==first && key.hash==0);
    }
    // Same bucket and properties, different shader IDs: no false hit.
    auto collision=RecentCache::key(68,1,p);
    const auto* second=cache.insert(collision,2);
    assert(cache.find_cached_pipeline(collision)==second && collision.hash);
    key.hash=0;assert(cache.find_cached_pipeline(key)==first && key.hash);
    // Same IDs, different static state: no false hit.
    auto different=key;different.hash=0;different.properties.state.rs.cullMode=VK_CULL_MODE_BACK_BIT;
    const auto* third=cache.insert(different,3);
    assert(cache.find_cached_pipeline(different)==third && different.hash);
    key.hash=0;assert(cache.find_cached_pipeline(key)==first && key.hash);
    // A map rehash keeps node hints valid. Populate another hint bucket.
    for(u32 i=0;i<4096;++i) cache.insert(RecentCache::key(i*64+1,1,p),i+10);
    key.hash=0;assert(cache.find_cached_pipeline(key)==first && key.hash==0);
    // Null placeholders are never remembered; their removal cannot leave a
    // dangling hint. Publication afterwards becomes visible through the map.
    auto pending=RecentCache::key(900000,3,p);
    cache.add_pending(pending);assert(!cache.find_cached_pipeline(pending));
    cache.erase_pending(pending);assert(!cache.find_cached_pipeline(pending));
    const auto* completed=cache.insert(pending,5000);
    assert(cache.find_cached_pipeline(pending)==completed);
    pending.hash=0;assert(cache.find_cached_pipeline(pending)==completed && !pending.hash);
    // Even a null replacement of a previously completed node must fall back
    // with a computed key and erase its hint before the node is destroyed.
    pending.hash=RecentCache::pipeline_key_hash::compute(pending);
    RecentCache::pipeline_storage_type empty;
    cache.publish_pipeline(pending,empty);
    pending.hash=0;assert(!cache.find_cached_pipeline(pending) && pending.hash);
    cache.erase_pending(pending);assert(!cache.find_cached_pipeline(pending));
    // Multiple readers remember colliding hints while a writer grows the map.
    std::atomic<bool> start=false;
    std::array<std::thread,4> readers;
    for(u32 r=0;r<readers.size();++r) readers[r]=std::thread([&,r] {
        while(!start.load(std::memory_order_acquire)) std::this_thread::yield();
        for(u32 n=0;n<20000;++n) {
            const u32 i=(n*37+r*71)%4096;
            auto k=RecentCache::key(i*64+1,1,p);
            const auto* pipeline=cache.find_cached_pipeline(k);
            assert(pipeline && pipeline->id==i+10);
        }
    });
    start.store(true,std::memory_order_release);
    for(u32 i=0;i<4096;++i) cache.insert(RecentCache::key(i*64+2,1,p),i+6000);
    for(auto& reader:readers) reader.join();
    // Renderer teardown occurs after users stop, as for the existing cache.
    cache.clear();key.hash=0;assert(!cache.find_cached_pipeline(key));
    const auto* replacement=cache.insert(key,42);
    assert(cache.find_cached_pipeline(key)==replacement && replacement->id==42);
}
