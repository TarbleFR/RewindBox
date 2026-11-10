// Extra arithmetic/order cases for the extracted production timer worker.
template<class Timer> Result edge_run(const std::vector<u64>& deadlines,u64 now,u32 scale) {
    env={}; registry.clear(); g_cfg.core.clocks_scale=scale;
    Timer timer; env.timer=&timer; env.ticks={now};
    env.inspect_pending=[&]{env.pending.push_back(snapshot(timer));};
    for(u32 i=0;i<deadlines.size();++i) timer.arm(deadlines[i],i,100+i);
    timer();
    u64 expected=umax;
    for(const auto due:deadlines) if(due>now)
        expected=std::min(expected,(due-now)*100/(80*std::max<u64>(scale,1))+1);
    assert(env.waits.size()==2 && env.waits[1]==expected);
    Result result{env.waits,env.notified,env.pending,snapshot(timer),env.erases,env.shifts,
        env.due_allocations,env.rejected_tokens,env.clock_reads,env.timer_notifications,false,false};
    env={}; registry.clear(); return result;
}
u64 arithmetic_edges() {
    u64 cases=0,random=0x94d049bb133111ebull;
    for(u32 scale:{0u,1u,25u,100u,200u,1000u,0xffffffffu})
    for(u64 now:{0ull,1ull,1000ull,0xffffffffffffffffull}) {
        std::vector<u64> due{0,1,999,1000,1001,umax/100,umax/100+1,umax/2,umax-1,umax};
        for(unsigned i=0;i<64;++i) {
            random^=random<<13; random^=random>>7; random^=random<<17;
            due.push_back(random);
            auto old=edge_run<before::spu_dec_intr_timer>(due,now,scale);
            auto fresh=edge_run<after::spu_dec_intr_timer>(due,now,scale);
            assert(old.waits==fresh.waits && old.pending==fresh.pending && old.remaining==fresh.remaining);
            assert(old.notified==fresh.notified && old.erases==fresh.erases && old.allocations==fresh.allocations);
            ++cases;
        }
    }
    return cases;
}
