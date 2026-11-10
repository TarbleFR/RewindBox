
u64 historical_irq_skips{},irq_retries{},stalled_irq_acks{},multi_pass_drains{},accepted_once{};
u64 barriers(const Thread& thread) {
    return std::count_if(thread.actions.begin(),thread.actions.end(),[](const auto& action){return std::get<0>(action)==Action::barrier;});
}
void irq_cases() {
    for(MFC command:{MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD})for(u32 tag=0;tag<32;++tag) {
        g_cfg.core.mfc_transfers_shuffling=16;
        g_cfg.core.mfc_shuffling_in_steps=false;
        // An event is already pending before draining, and the non-stepping
        // clock sequence requires more than one mask to empty this queue.
        Thread historical=full_fixture(tag);
        historical.pc=0x1240;historical.interrupts_enabled=true;historical.ch_events.value.count=true;
        historical.ch_mfc_cmd={command,static_cast<u8>(tag),16,0x40,0x60300510,0};
        utils::fixed=false;utils::sample=0;utils::clock_calls=0;active=&historical;
        bool escaped=false;
        try{historical.process_mfc_cmd_before_irq();}catch(const Escaped&){escaped=true;}
        assert(escaped&&historical.srr0==0x1244&&historical.accepted_commands==0&&barriers(historical)==0);
        assert(utils::clock_calls==1);
        historical.ch_events.value.count=false;
        assert(!IRET(historical,{}));
        assert(historical.pc==0x1244&&historical.ch_mfc_cmd.cmd==command);++historical_irq_skips;

        Thread current=full_fixture(tag);
        current.interrupts_enabled=true;current.ch_events.value.count=true;
        utils::fixed=false;utils::sample=0;utils::clock_calls=0;
        Emitter interrupt(current,command,tag);escaped=false;
        try{interrupt.after();}catch(const Escaped&){escaped=true;}
        assert(escaped&&current.srr0==0x1240&&current.mfc_size==0&&current.accepted_commands==0);
        assert(current.ch_mfc_cmd.cmd==command&&barriers(current)==0&&!interrupt.storage.reachable.contains(1));
        assert(utils::clock_calls>1);++multi_pass_drains;
        current.ch_events.value.count=false;
        assert(!IRET(current,{}));assert(current.pc==0x1240);
        active=&current;exec_wrch(&current,MFC_Cmd,command);
        assert(current.accepted_commands==1&&current.mfc_size==0&&barriers(current)==1);
        ++irq_retries;++accepted_once;

        // The full queue cannot drain until its list is acknowledged. An IRQ
        // must remain deliverable before acceptance, even though no slot frees.
        Thread blocked=full_fixture(tag);
        blocked.mfc_queue[0].cmd=MFC_GETL_CMD;blocked.mfc_queue[0].tag|=0x80;
        blocked.mfc_queue[1].cmd=MFC_BARRIER_CMD;
        blocked.interrupts_enabled=true;blocked.ch_events.value.count=true;
        utils::fixed=true;utils::sample=0xffff;utils::clock_calls=0;
        const auto waits=wait_calls;
        Emitter stalled(blocked,command,tag);escaped=false;
        try{stalled.after();}catch(const Escaped&){escaped=true;}
        assert(escaped&&blocked.srr0==0x1240&&blocked.mfc_size==16&&blocked.accepted_commands==0);
        assert(blocked.mfc_queue[0].tag&0x80);
        assert(wait_calls==waits&&blocked.actions.size()==2);
        assert(std::get<0>(blocked.actions[0])==Action::cancel&&std::get<0>(blocked.actions[1])==Action::escape);
        // The interrupt handler's explicit ack uses the real unstall helper.
        blocked.ch_events.value.count=false;blocked.complete_lists=true;active=&blocked;
        exec_list_unstall(&blocked,tag);
        assert(blocked.mfc_size==0&&blocked.accepted_commands==0);
        const auto prior_barriers=barriers(blocked);
        assert(!IRET(blocked,{}));assert(blocked.pc==0x1240);
        exec_wrch(&blocked,MFC_Cmd,command);
        assert(blocked.accepted_commands==1&&blocked.mfc_size==0&&barriers(blocked)==prior_barriers+1);
        ++stalled_irq_acks;++accepted_once;
        active=nullptr;
    }
}
int main(){
    std::cout<<"{\"tagRegression\":";tag_cases();full_cases();irq_cases();
    std::cout<<",\"fullQueue\":{\"baselineHalts\":"<<baseline_halts<<",\"recovered\":"<<recovered
        <<",\"stopBeforeDrain\":"<<stop_cases<<",\"successfulRetries\":"<<successful_retries
        <<",\"againEscapes\":"<<again_cases<<",\"stalledListWaits\":"<<wait_cases
        <<",\"interruptDrainEscapes\":"<<interrupt_cases<<",\"noDoubleEnqueue\":true,\"currentPCPreservedOnStop\":true}"
        <<",\"preAcceptanceInterrupt\":{\"historicalSkippedWRCH\":"<<historical_irq_skips
        <<",\"currentPCRetries\":"<<irq_retries<<",\"stalledListIRQAcks\":"<<stalled_irq_acks
        <<",\"multipleMaskPasses\":"<<multi_pass_drains<<",\"commandsAcceptedExactlyOnce\":"<<accepted_once
        <<",\"stepsDisabled\":true,\"eventPendingBeforeDrain\":true}}";
}
