
u64 recovered{},stop_cases{},again_cases{},wait_cases{},interrupt_cases{},baseline_halts{},successful_retries{};
Thread full_fixture(u32 tag) {
    Thread thread;
    thread.mfc_size=16;thread.mfc_barrier=thread.mfc_fence=0;
    for(u32 i=0;i<16;++i){thread.mfc_queue[i]={MFC_PUT_CMD,static_cast<u8>((tag+i)%32),16,i*16,0x10000+i*16,i};thread.mfc_fence|=1u<<thread.mfc_queue[i].tag;}
    return thread;
}
void full_cases() {
    for(MFC command:{MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD})for(u32 tag=0;tag<32;++tag) {
        // A legitimate pending queue can drain; no list acknowledgement needed.
        Thread old=full_fixture(tag),fresh=old;
        Emitter original(old,command,tag),fixed(fresh,command,tag);
        bool halted=false;try{original.before();}catch(const GuardedAccess&){halted=true;}
        assert(halted&&old.mfc_size==16&&old.actions.empty());++baseline_halts;
        utils::fixed=true;utils::sample=0xffff;g_cfg.core.mfc_transfers_shuffling=16;
        active=&fresh;fixed.after();active=nullptr;
        assert(fresh.mfc_size==0&&fixed.helper_calls==1&&fixed.storage.queue_writes==0);
        assert(fresh.actions.size()==17&&std::get<0>(fresh.actions.back())==Action::barrier);
        assert(fixed.storage.reachable.contains(1));++recovered;

        // Stop before any DMA: the command must remain current for a retry at
        // the same WRCH PC, and nothing may be appended to the full queue.
        Thread stopped=full_fixture(tag);stopped.stopped=true;
        Emitter stop(stopped,command,tag);bool escaped=false;
        try{stop.after();}catch(const Escaped&){escaped=true;}
        assert(escaped&&stopped.pc==0x1240&&stopped.mfc_size==16&&stopped.ch_mfc_cmd.cmd==command);
        assert(stopped.actions.size()==1&&std::get<0>(stopped.actions[0])==Action::escape);
        assert(!stop.storage.reachable.contains(1)&&stop.storage.queue_writes==0);++stop_cases;
        stopped.stopped=false;stopped.actions.clear();Emitter retry(stopped,command,tag);retry.after();
        assert(stopped.mfc_size==0&&retry.helper_calls==1&&stopped.actions.size()==17);++successful_retries;

        // The generic WRCH helper's preexisting ::again contract is retained.
        Thread again=full_fixture(tag);again.state.bits=1u<<u32(cpu_flag::again);
        Emitter repeat(again,command,tag);escaped=false;
        try{repeat.after();}catch(const Escaped&){escaped=true;}
        assert(escaped&&again.pc==0x1240&&again.mfc_size==0&&!repeat.storage.reachable.contains(1));++again_cases;

        // A stalled list must stay queued until a wait delivers its ack.
        Thread blocked=full_fixture(tag);blocked.mfc_queue[0].cmd=MFC_GETL_CMD;blocked.mfc_queue[0].tag|=0x80;
        blocked.mfc_queue[1].cmd=MFC_BARRIER_CMD;
        const auto waits_before=wait_calls;bool observed=false;
        wait_action=[&]{assert(blocked.mfc_size==16&&blocked.actions.empty());observed=true;
            blocked.mfc_queue[0].tag&=0x7f;blocked.complete_lists=true;};
        Emitter waiting(blocked,command,tag);waiting.after();wait_action={};
        assert(observed&&wait_calls==waits_before+1&&blocked.mfc_size==0&&waiting.helper_calls==1);++wait_cases;

        // Interruption during the drain is compared with the unchanged generic
        // helper contract; no claim about the complete guest interrupt scheduler.
        Thread interrupt=full_fixture(tag);interrupt.interrupts_enabled=true;interrupt.ch_events.value.count=true;
        Emitter interrupted(interrupt,command,tag);escaped=false;
        try{interrupted.after();}catch(const Escaped&){escaped=true;}
        assert(escaped&&!interrupted.storage.reachable.contains(1)&&interrupt.mfc_size==0);
        assert(interrupt.ch_mfc_cmd.cmd==command&&interrupt.srr0==0x1244);++interrupt_cases;
    }
}
int main(){
    std::cout<<"{\"tagRegression\":";tag_cases();full_cases();
    std::cout<<",\"fullQueue\":{\"baselineHalts\":"<<baseline_halts<<",\"recovered\":"<<recovered
        <<",\"stopBeforeDrain\":"<<stop_cases<<",\"successfulRetries\":"<<successful_retries
        <<",\"againEscapes\":"<<again_cases<<",\"stalledListWaits\":"<<wait_cases
        <<",\"interruptDrainEscapes\":"<<interrupt_cases<<",\"noDoubleEnqueue\":true,\"currentPCPreservedOnStop\":true}}";
}
