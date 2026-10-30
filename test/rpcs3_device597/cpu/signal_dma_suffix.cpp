int main(){
    auto owner=std::make_unique<spu_thread>();current_cpu=owner.get();new_mode=true;
    constexpr u32 label=0x10080;u32 cases=0,commits=0;u64 session=100;
    for(bool enabled:{false,true})for(bool accurate:{false,true})for(bool atomic:{false,true})
    for(bool get:{false,true})for(u32 size:{1u,2u,4u,8u,16u,64u,128u,256u,2048u})for(u32 which:{0u,1u,2u}){
        const u32 address=which==0?label:which==1?label+16:label-128;
        if(which==2&&size<256)continue;
        spu_mfc_cmd args{u8(get?MFC_GET_CMD:MFC_PUT_CMD),0,u16(size),0x800,address,0};
        g_cfg.core.spu_accurate_dma=accurate;g_cfg.core.accurate_cache_line_stores=atomic;
        std::array<u8,2048> expected{};
        for(bool candidate:{false,true}){
            for(u32 i=0;i<owner->storage.size();++i)owner->ls[i]=u8(i*7+11);
            ordinary_ram.fill(0xa5);for(auto& r:vm::reservations)r.v=0;vm::reservation_storage.fill(0);owner->slot.v=0;
            if(!get)std::memcpy(expected.data(),owner->ls+args.lsa,size);else expected.fill(0xa5);
            trace::reset(++session,candidate&&enabled);trace::begin_acquire(label,0x1a24,0xa5a5a5a5,1);
            (candidate?new_dma_transfer:old_dma_transfer)(owner.get(),args,owner->ls);
            assert(std::memcmp(expected.data(),get?owner->ls+args.lsa:ordinary_ram.data()+address,size)==0);
            auto snapshot=trace::snapshot();u32 observed=0;
            for(std::size_t i=0;i<snapshot.event_count;++i){auto event=snapshot.events[i];if(event.kind==trace::event_kind::spu_dma_commit){++observed;assert(event.producer_id==owner->id&&event.pc==owner->pc&&event.write_address==address&&event.write_size==size&&!event.value_is_written_argument&&!event.value_valid&&event.value==0);}}
            const bool overlap=u64(address)<u64(label)+4&&u64(address)+size>label;
            assert(observed==u32(candidate&&enabled&&!get&&overlap));commits+=observed;
        }
        ++cases;
    }
    // Failure before memory mutation must not manufacture a completed DMA.
    trace::reset(++session,true);trace::begin_acquire(label,7,0,1);g_cfg.core.spu_accurate_dma=false;fail_ranges=true;
    spu_mfc_cmd args{MFC_PUT_CMD,0,16,0x800,label,0};bool caught=false;try{new_dma_transfer(owner.get(),args,owner->ls);}catch(const access_fault&){caught=true;}fail_ranges=false;
    assert(caught&&trace::snapshot().event_count==1);
    // A copy begun in an old session cannot claim the next session's label.
    trace::reset(++session,true);trace::begin_acquire(label,7,0,1);reset_on_copy=true;args.size=2048;
    new_dma_transfer(owner.get(),args,owner->ls);reset_on_copy=false;assert(trace::snapshot().event_count==0&&trace::summary().totals.stale_session_dropped>0);
    std::cout<<"{\"completeDmaFunctionExtracted\":true,\"beforeAfterCopyCases\":"<<cases<<",\"observedCommitRecords\":"<<commits<<",\"failedCopyNoCommit\":true,\"inFlightSessionResetDropsOldCommit\":true,\"getAndUnwatchedPathsNoCommit\":true,\"noAdditionalGuestRead\":true,\"dmaValueExplicitlyUnknown\":true}";
}
