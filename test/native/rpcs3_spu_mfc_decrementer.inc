// Controlled timer callbacks use the extracted production publication body.
// Handler acknowledgements and the clock are explicit test boundaries.
template<class T>void full_fixture(T& t,MFC command=MFC_SYNC_CMD,u32 tag=31){
    rpcs3::ios::signal_trace::reset(100,true);
    typename T::ch_events_t events{};events.mask=SPU_EVENT_TM;t.ch_events.release(events);
    t.mfc_size=16;for(u32 i=0;i<16;++i)t.mfc_queue[i]={MFC_PUT_CMD,u8(i),16,16*i,0x10000+16*i,0};
    t.mfc_queue[0].cmd=MFC_GETL_CMD;t.mfc_queue[0].tag|=0x80;t.mfc_queue[1].cmd=MFC_BARRIER_CMD;
    t.ch_mfc_cmd={command,u8(tag),0,0,0x60300510,0};
    t.ch_dec_value=10;t.ch_dec_start_timestamp=1;t.dec_intr_armed.release(1);t.dec_intr_deadline=12;
    clock_now=1;thread_ctrl::g_tls_this_thread=&t.host_thread();
}
struct Outcome{bool blocked{},escaped{};u32 queue{},accepted{},return_pc{};bool waiting{},count{};};
template<class T>Outcome enter(T& t){
    Outcome out;
    try{t.process_prefix();}catch(const Escaped&){out.escaped=true;}catch(const WouldBlock&){out.blocked=true;}
    before_state_wait={};before_list_wait={};
    out.queue=t.mfc_size;out.accepted=t.accepted;out.return_pc=t.srr0;
    out.waiting=t.ch_events.load().waiting;out.count=t.ch_events.load().count;
    return out;
}
template<class T,class Publish>Outcome deadline(u32 location,Publish publish){
    named_thread<T> t;full_fixture(t);auto send=[&]{clock_now=12;publish(t,1);};
    if(location==0)send();else if(location==1)before_state_wait=send;else before_list_wait=send;
    return enter(t);
}
int main(){
    static_cast<void>(&before::exec_list_unstall);
    u32 reproduced=0,delivered=0,accepted_once=0,snr_preserved=0,masked=0,concurrent=0;
    for(u32 location:{0u,1u,2u}){
        auto old=deadline<before::spu_thread>(location,before::publish_timer);
        auto now=deadline<after::spu_thread>(location,after::publish_timer);
        assert(old.blocked&&!old.escaped&&!old.count&&old.queue==16&&old.accepted==0);++reproduced;
        const bool expected_interrupt=now.escaped&&!now.blocked&&now.count&&!now.waiting&&now.return_pc==0x1240&&now.queue==16&&now.accepted==0;
        assert(expected_interrupt);++delivered;
    }
    // Event collection and notification latching are both required. Mutation
    // runs omit one production change and must fail expected_interrupt above.
    for(bool enabled:{false,true})for(bool mask:{false,true})if(!enabled||!mask){
        named_thread<after::spu_thread> t;full_fixture(t);t.interrupts_enabled=enabled;
        if(!mask)t.ch_events.atomic_op([](auto& e){e.mask=0;});
        clock_now=12;after::publish_timer(t,1);auto out=enter(t);
        assert(out.blocked&&!out.escaped&&!out.count&&t.accepted==0);++masked;
    }
    for(bool frozen:{false,true}){
        named_thread<after::spu_thread> t;full_fixture(t);t.is_dec_frozen=frozen;
        // WRDEC or cancellation leaves an old timer token invalid. The owner
        // must not receive an event merely because that old deadline fires.
        t.dec_intr_armed.release(2);clock_now=5;after::publish_timer(t,1);
        assert(t.state.load()==0&&t.dec_intr_armed.load()==2);
        auto out=enter(t);assert(out.blocked&&!out.escaped&&!out.count);++masked;
    }
    // Frozen DEC with a valid stale scheduling request still cannot generate TM.
    {
        named_thread<after::spu_thread> t;full_fixture(t);t.is_dec_frozen=true;clock_now=20;
        after::publish_timer(t,1);auto out=enter(t);
        assert(out.blocked&&!out.escaped&&!out.count);++masked;
    }
    // Stop before draining, and stop after event registration but before sleep.
    for(bool late:{false,true}){
        named_thread<after::spu_thread> t;full_fixture(t);
        auto stop=[&]{t.state+=cpu_flag::stop;clock_now=12;after::publish_timer(t,1);};
        if(late)before_state_wait=stop;else stop();
        auto out=enter(t);assert(!out.blocked&&!out.escaped&&!out.waiting&&out.accepted==0);++masked;
    }
    // Keep the existing late-SNR path, including arrival before wait registration.
    for(u32 location:{1u,2u})for(u32 number:{0u,1u}){
        named_thread<after::spu_thread> t;full_fixture(t);
        t.ch_events.atomic_op([&](auto& e){e.mask=SPU_EVENT_S1>>number;});
        auto send=[&]{t.push_snr(number,0xfeed);};
        if(location==1)before_state_wait=send;else before_list_wait=send;
        auto out=enter(t);assert(out.escaped&&!out.blocked&&!out.waiting&&out.return_pc==0x1240&&out.accepted==0);++snr_preserved;
    }
    // The interrupted WRCH remains unaccepted. The actual unstall helper drains
    // the queue; actual IRET restores this PC; the real barrier branch accepts
    // the retried command exactly once after the handler acknowledges TM.
    for(MFC command:{MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD})for(u32 tag=0;tag<32;++tag){
        named_thread<after::spu_thread> t;full_fixture(t,command,tag);clock_now=12;after::publish_timer(t,1);
        auto out=enter(t);const bool expected_interrupt=out.escaped&&out.return_pc==0x1240&&out.accepted==0;
        assert(expected_interrupt);assert(t.ch_mfc_cmd.cmd==command&&t.ch_mfc_cmd.tag==tag);
        t.ch_events.atomic_op([](auto& e){e.events&=~SPU_EVENT_TM;e.count=false;});
        t.complete_lists=true;after::exec_list_unstall(&t,0);assert(t.mfc_size==0&&t.accepted==0);
        assert(!after::IRET(t,{}));assert(t.pc==0x1240);
        assert(t.process_prefix()&&t.accepted==1&&t.mfc_size==0);++accepted_once;
    }
    // Real producer and owner threads. The native wait-list backend is modeled
    // by the adapter's CV with a two-second test watchdog, never a guest timeout.
    concurrent_wait=true;
    for(u32 iteration=0;iteration<64;++iteration){
        named_thread<after::spu_thread> t;full_fixture(t);list_entered=false;
        std::thread producer([&]{
            {std::unique_lock lock(wait_mutex);assert(wait_cv.wait_for(lock,std::chrono::seconds(2),[]{return list_entered.load(std::memory_order_acquire);}));}
            clock_now=12;after::publish_timer(t,1);
        });
        auto out=enter(t);producer.join();
        const bool expected_interrupt=out.escaped&&!out.blocked&&out.return_pc==0x1240&&out.accepted==0&&!out.waiting;
        assert(expected_interrupt);++concurrent;
    }
    std::cout<<"{\"baselineBlockedDueSchedules\":"<<reproduced<<",\"candidateDeadlineInterrupts\":"<<delivered
      <<",\"commandsAcceptedExactlyOnce\":"<<accepted_once<<",\"lateSnrPreserved\":"<<snr_preserved
      <<",\"maskedDisabledFrozenOrStale\":"<<masked<<",\"concurrentDeadlineInterrupts\":"<<concurrent
      <<",\"currentPcPreserved\":true,\"unacceptedCommandPreserved\":true,\"guestTimeoutAdded\":false}";
}
