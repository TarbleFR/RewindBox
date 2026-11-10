// Uses the existing deterministic scheduler/IDM/atomic adapters and complete
// production class bodies. Only this additional driver and assertions are new.
template<class Timer> Result repeated_run(const std::vector<u32>& batches,int fail_round=-1) {
    env={};registry.clear();g_cfg.core.clocks_scale=100;
    Timer timer;env.timer=&timer;
    for(u32 i=0;i<batches.size();++i)env.ticks.push_back(1000+1000*i);
    env.inspect_pending=[&]{env.pending.push_back(snapshot(timer));};
    env.on_wait=[&](std::size_t round){
        if(round>=batches.size())return;
        for(u32 id=0;id<batches[round];++id){
            const u64 token=1+id+u64{round}*10000;
            add_thread(id,token);timer.arm(env.ticks[round],id,token);
        }
        if(static_cast<int>(round)==fail_round)env.fail_allocation=env.allocation_attempts+1;
    };
    bool threw=false;
    try{timer();}catch(const std::bad_alloc&){threw=true;}
    assert(env.lock_depth==0);
    Result result{env.waits,env.notified,env.pending,snapshot(timer),env.erases,env.shifts,
                  env.due_allocations,env.rejected_tokens,env.clock_reads,env.timer_notifications,
                  threw,env.timing_retain_checked};
    env={};registry.clear();return result;
}
int main(){
    for(u32 count:{0u,1u,2u,6u,16u,64u,256u})for(u32 pattern=0;pattern<6;++pattern)
    for(u32 scale:{0u,1u,25u,100u,200u}){
        const auto old=run<before::spu_dec_intr_timer>(count,pattern,scale);
        const auto fresh=run<after::spu_dec_intr_timer>(count,pattern,scale);
        compare(old,fresh);assert(fresh.remaining.empty());++counts.cases;
    }
    for(u32 pattern:{1u,4u}){
        const auto old=run<before::spu_dec_intr_timer>(6,pattern,100,true);
        const auto fresh=run<after::spu_dec_intr_timer>(6,pattern,100,true);
        compare(old,fresh);assert(fresh.threw&&fresh.notified.empty()&&fresh.remaining==fresh.pending.front());++counts.failures;
    }
    const auto old_reentrant=run<before::spu_dec_intr_timer>(6,1,100,false,true);
    const auto fresh_reentrant=run<after::spu_dec_intr_timer>(6,1,100,false,true);
    compare(old_reentrant,fresh_reentrant);assert(fresh_reentrant.retained&&fresh_reentrant.notified.size()==7);++counts.reentrant;
    const auto old_shutdown=run<before::spu_dec_intr_timer>(6,1,100,false,false,true);
    const auto fresh_shutdown=run<after::spu_dec_intr_timer>(6,1,100,false,false,true);
    compare(old_shutdown,fresh_shutdown);
    assert(fresh_shutdown.clock_reads==0&&fresh_shutdown.allocations==0&&fresh_shutdown.notified.empty());++counts.shutdown;

    const std::vector<u32> stable(128,6);
    const auto repeated_old=repeated_run<before::spu_dec_intr_timer>(stable);
    const auto repeated_new=repeated_run<after::spu_dec_intr_timer>(stable);
    compare(repeated_old,repeated_new);
    assert(repeated_old.allocations==128&&repeated_new.allocations==1);
    assert(repeated_new.notified.size()==768&&repeated_new.remaining.empty());
    std::vector<u32> varied;
    for(u32 round=0;round<128;++round)for(u32 size:{0u,1u,6u,64u,6u,257u,0u,16u})varied.push_back(size);
    const auto varied_old=repeated_run<before::spu_dec_intr_timer>(varied);
    const auto varied_new=repeated_run<after::spu_dec_intr_timer>(varied);
    compare(varied_old,varied_new);
    assert(varied_old.allocations==768&&varied_new.allocations==4);
    // A later growth failure must leave the pending queue untouched just like
    // the first allocation failure. The failure is injected at the same wake.
    const auto fail_old=repeated_run<before::spu_dec_intr_timer>({6,6,64},2);
    const auto fail_new=repeated_run<after::spu_dec_intr_timer>({6,6,64},2);
    compare(fail_old,fail_new);
    assert(fail_new.threw&&fail_new.remaining.size()==64&&fail_new.notified.size()==12);
    std::cout<<"{\"passed\":true,\"assertionsActive\":true,\"matrixCases\":"<<counts.cases
        <<",\"reentrantCases\":"<<counts.reentrant<<",\"shutdownCases\":"<<counts.shutdown
        <<",\"firstAllocationFailureCases\":"<<counts.failures<<",\"laterGrowthFailureCases\":1"
        <<",\"stableWakes\":128,\"baselineStableAllocations\":"<<repeated_old.allocations
        <<",\"candidateStableAllocations\":"<<repeated_new.allocations
        <<",\"variableWakes\":1024,\"baselineVariableAllocations\":"<<varied_old.allocations
        <<",\"candidateVariableAllocations\":"<<varied_new.allocations
        <<",\"obsoleteTokensRejected\":"<<counts.rejected<<",\"notifications\":"<<counts.notifications
        <<",\"pendingOrderComparisons\":"<<counts.orders<<",\"waitDeadlineComparisons\":"<<counts.deadlines
        <<",\"callbacksWhileLocked\":0,\"samePublicationAndWaitOrder\":true,\"reentrantRetainedUntilCallbackReturned\":true}\n";
}
