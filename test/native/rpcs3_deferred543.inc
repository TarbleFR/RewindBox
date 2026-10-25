// Generic cases for the production rsx::deferred_publisher header.
struct DeferredMetrics { unsigned ordered=0, concurrent=0, inline_writes=0, drained=0, failures=0; bool worker_thread=false; };

DeferredMetrics deferred_test() {
    using rsx::deferred_publisher;
    DeferredMetrics m;
    // Single producer: submission order is write order; destruction drains.
    {
        std::vector<int> written; std::thread::id worker;
        {
            deferred_publisher<int> pub(1024,[&](int& v) { std::this_thread::sleep_for(std::chrono::microseconds(50)); written.push_back(v); },
                [&] { worker=std::this_thread::get_id(); });
            for (int i=0;i<500;++i) assert(pub.submit(int(i)));
        }
        assert(written.size()==500);
        for (int i=0;i<500;++i) assert(written[i]==i);
        m.ordered=500; m.worker_thread=worker!=std::thread::id{} && worker!=std::this_thread::get_id();
        assert(m.worker_thread);
    }
    // Many producers: every record exactly once, whether queued or inline.
    {
        std::mutex lock; std::multiset<int> written;
        {
            deferred_publisher<int> pub(16,[&](int& v) { std::lock_guard g(lock); written.insert(v); });
            std::vector<std::thread> pool;
            for (int t=0;t<8;++t) pool.emplace_back([&,t] { for (int i=0;i<1000;++i) pub.submit(t*1000+i); });
            for (auto& p:pool) p.join();
        }
        assert(written.size()==8000);
        for (int v=0;v<8000;++v) assert(written.count(v)==1);
        m.concurrent=8000;
    }
    // Bounded queue: a blocked writer forces inline writes; nothing is dropped.
    {
        std::mutex gate; gate.lock();
        std::atomic<int> first_started{0}, written{0};
        std::vector<std::thread::id> who;
        std::mutex who_lock;
        deferred_publisher<int> pub(4,[&](int&) {
            if (!first_started.exchange(1)) { std::lock_guard g(gate); }
            std::lock_guard g(who_lock); who.push_back(std::this_thread::get_id()); ++written;
        });
        assert(pub.submit(0));
        while (!first_started.load()) std::this_thread::yield();
        unsigned queued=0, inline_count=0;
        for (int i=1;i<=10;++i) (pub.submit(int(i))?queued:inline_count)++;
        assert(queued==4 && inline_count==6);
        assert(pub.stats().inline_writes==6 && pub.stats().peak_depth==4);
        gate.unlock();
        pub.drain();
        assert(written==11 && pub.depth()==0 && pub.stats().written==5);
        m.inline_writes=inline_count; m.drained=unsigned(written.load());
    }
    // A throwing sink is counted; later records still reach the sink.
    {
        std::atomic<int> seen{0};
        deferred_publisher<int> pub(8,[&](int& v) { ++seen; if (v==1) throw std::runtime_error("disk"); });
        for (int i=0;i<4;++i) assert(pub.submit(int(i)));
        pub.drain();
        assert(seen==4 && pub.stats().sink_failures==1 && pub.stats().written==4);
        m.failures=1;
    }
    // Destruction with a slow sink still writes everything accepted.
    {
        std::atomic<int> written{0};
        {
            deferred_publisher<int> pub(64,[&](int&) { std::this_thread::sleep_for(std::chrono::milliseconds(2)); ++written; });
            for (int i=0;i<40;++i) pub.submit(int(i));
        }
        assert(written==40);
    }
    return m;
}
