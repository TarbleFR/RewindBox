struct list_item {u8 sb,pad;be_t<u16> ts;be_t<u32> ea;};
int main(){
    constexpr u32 label=0x3000;u64 session=2000;u32 cases=0,commits=0,zeroes=0;
    for(bool enabled:{false,true})for(u32 size:{0u,1u,2u,4u,8u,16u,32u,64u,128u,512u,1024u})for(bool get:{false,true})for(bool overlaps:{false,true}){
        auto old=std::make_unique<spu_old>();auto fresh=std::make_unique<spu_new>();const u32 address=overlaps?label:label+0x1000;
        std::array<u8,1024> expected{};expected.fill(0x35);
        const list_item item{0,0,u16(size),address};
        for(bool candidate:{false,true}){
            auto& thread=candidate?static_cast<spu_common&>(*fresh):static_cast<spu_common&>(*old);
            thread.local.fill(0x35);guest_memory.fill(0x35);std::memcpy(thread.ls+0x100,&item,sizeof(item));
            trace::reset(++session,candidate&&enabled);trace::begin_acquire(label,9,0x35353535,1);
            spu_mfc_cmd args{get?MFC_GETL_CMD:MFC_PUTL_CMD,1,8,0x10000,0x100,0};
            assert(candidate?fresh->do_list_transfer(args):old->do_list_transfer(args));
            assert(std::memcmp(expected.data(),get?thread.ls+0x10000:guest_memory.data()+address,size)==0);
            auto snapshot=trace::snapshot();u32 seen=0;
            for(std::size_t i=0;i<snapshot.event_count;++i)if(snapshot.events[i].kind==trace::event_kind::spu_list_commit){++seen;const auto event=snapshot.events[i];assert(event.producer_id==thread.id&&event.pc==thread.pc&&event.write_address==address&&event.write_size==size&&!event.value_is_written_argument&&!event.value_valid&&event.value==0);}
            assert(seen==u32(candidate&&enabled&&!get&&overlaps&&size));commits+=seen;
        }
        ++cases;zeroes+=!size;
    }
    std::cout<<"{\"completeListFunctionExtracted\":true,\"beforeAfterCopyCases\":"<<cases<<",\"observedCommitRecords\":"<<commits<<",\"zeroElementsNoCommitCases\":"<<zeroes<<",\"getAndUnwatchedPathsNoCommit\":true}";
}
