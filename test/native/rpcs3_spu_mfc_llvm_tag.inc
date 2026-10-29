#include <memory>
#include <stdexcept>
#include <type_traits>

// Evaluates only the integer/pointer/load/store IR operations emitted by the
// extracted fallback. Every memory operation checks the selected allocation.
// LLVM optimization, machine-code emission and native ordering are not modeled.
struct Value {
    u64 bits{}; unsigned width{};
    u64 getZExtValue() const { return bits; }
};
struct Memory {
    u8* base{}; std::size_t length{}, offset{};
};
struct GuardedAccess : std::runtime_error { GuardedAccess():std::runtime_error("guarded invalid MFC slot"){} };
Memory _ptr(Memory base, Value* offset) { base.offset += offset->bits; return base; }
Memory _ptr(Memory base, u64 offset) { base.offset += offset; return base; }
template<class C,class T> Memory _ptr(Memory base,T C::*member) {
    C layout{};
    base.offset += reinterpret_cast<const u8*>(&(layout.*member))-reinterpret_cast<const u8*>(&layout);
    return base;
}
template<class T> constexpr unsigned get_type() { return sizeof(T); }
struct Builder {
    std::vector<std::unique_ptr<Value>> values;
    u32 writes{}, queue_writes{};
    Value* value(u64 bits,unsigned width) {
        if(width<8) bits &= (u64{1}<<(8*width))-1;
        values.push_back(std::make_unique<Value>(Value{bits,width})); return values.back().get();
    }
    Value* getInt32(u32 bits) { return value(bits,4); }
    static u8* checked(Memory memory,unsigned bytes) {
        if(!memory.base || memory.offset>memory.length || bytes>memory.length-memory.offset) throw GuardedAccess{};
        return memory.base+memory.offset;
    }
    Value* CreateLoad(unsigned width,Memory memory) {
        u64 bits{}; std::memcpy(&bits,checked(memory,width),width); return value(bits,width);
    }
    void CreateStore(Value* input,Memory memory) {
        std::memcpy(checked(memory,input->width),&input->bits,input->width); ++writes;
        if(memory.offset<sizeof(State::mfc_queue))++queue_writes;
    }
    Value* CreateAdd(Value* a,Value* b) { return value(a->bits+b->bits,a->width); }
    Value* CreateMul(Value* a,Value* b) { return value(a->bits*b->bits,a->width); }
    Value* CreateOr(Value* a,Value* b) { return value(a->bits|b->bits,a->width); }
    Value* CreateZExt(Value* a,unsigned width) { return value(a->bits,width); }
    Value* CreateICmpULT(Value* a,Value* b) { return value(a->bits<b->bits,1); }
    Memory CreateSelect(Value* condition,Memory yes,Memory no) { return condition->bits?yes:no; }
    void SetInsertPoint(int) {}
    void CreateBr(int) {}
    [[noreturn]] void CreateUnreachable() { throw std::logic_error("unexpected IR unreachable"); }
};
template<class C,class T> u32 offset32(T C::*member) {
    C layout{};
    return static_cast<u32>(reinterpret_cast<const u8*>(&(layout.*member))-reinterpret_cast<const u8*>(&layout));
}
struct Scalar { Value* value{}; };
struct Emitter {
    using spu_thread=State;
    Builder storage;
    Builder* m_ir=&storage;
    Memory m_thread,m_memptr{};
    Scalar tag,size,lsa,eal;
    Value* mask{}; Value* ci{};
    Memory pf,pb;
    int fail{},next{};
    Emitter(State& state,MFC cmd,u8 desired_tag):m_thread{reinterpret_cast<u8*>(&state),sizeof(state),0} {
        tag.value=storage.value(desired_tag,1); size.value=storage.value(16,2);
        lsa.value=storage.value(0x40,4); eal.value=storage.value(0x60300510,4);
        mask=storage.getInt32(1u<<desired_tag); ci=storage.value(cmd,1);
        pf=spu_ptr(&State::mfc_fence); pb=spu_ptr(&State::mfc_barrier);
    }
    template<class T> Memory spu_ptr(T State::*member) { return _ptr(m_thread,member); }
    void before() {
        @BEFORE_ENQUEUE@
    }
    void after() {
        @AFTER_ENQUEUE@
    }
};

u64 scenarios{},premature_before{},premature_after{},matched_after{},stale_slot_cases{},full_queue_guards{},unchanged_dma{};
using Thread=production::spu_thread;
Thread fixture(u32 desired,u32 stale,MFC command,u32 prior_count) {
    Thread thread;
    thread.mfc_fence=thread.mfc_barrier=0;
    for(u32 i=0;i<prior_count;++i) {
        const u8 list_tag=static_cast<u8>((desired+13)%32);
        thread.mfc_queue[i]={MFC_GETL_CMD,static_cast<u8>(list_tag|0x80),16,0,0,1};
        thread.mfc_fence|=1u<<list_tag;
    }
    thread.mfc_size=prior_count;
    thread.mfc_queue[prior_count]={MFC_PUT_CMD,static_cast<u8>(stale),4096,0xaaaaaaaa,0xbbbbbbbb,0xcccccccc};
    thread.ch_tag_mask=1u<<desired;
    thread.ch_tag_upd=MFC_TAG_UPDATE_IMMEDIATE;
    // Reference C++ enqueue copies the complete current command.
    (void)command;
    return thread;
}
void sweep(Thread& thread) {
    active=&thread; g_cfg.core.mfc_transfers_shuffling=0;
    assert(!thread.do_mfc(false,true)); active=nullptr;
}
void tag_query(Thread& thread) {
    active=&thread; assert(thread.request_tag_update(MFC_TAG_UPDATE_ALL)); active=nullptr;
}
void resume(Thread& thread) {
    thread.complete_lists=true;
    for(u32 i=0;i<thread.mfc_size;++i)thread.mfc_queue[i].tag&=0x7f;
    sweep(thread);
    assert(thread.mfc_size==0 && thread.mfc_barrier==0 && thread.mfc_fence==0);
    assert(thread.get_mfc_completed()==thread.ch_tag_mask);
}
int main() {
    // All legal current tags, all stale byte values (including stalled-list
    // tags) and all three barrier opcodes; exercise first and last valid slots.
    for(MFC command:{MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD})
    for(u32 desired=0;desired<32;++desired)for(u32 stale=0;stale<256;++stale)
    for(u32 prior_count:{1u,15u}) {
        Thread old=fixture(desired,stale,command,prior_count),fresh=old,reference=old;
        Emitter old_ir(old,command,desired),new_ir(fresh,command,desired);
        old_ir.before();new_ir.after();
        reference.ch_mfc_cmd={command,static_cast<u8>(desired),16,0x40,0x60300510,0};
        active=&reference;assert(reference.reference_enqueue());active=nullptr;
        assert(fresh.mfc_queue[prior_count].tag==desired);
        assert(old.mfc_queue[prior_count].tag==stale);
        assert(new_ir.storage.writes==old_ir.storage.writes+1);
        // Tag is the only additional write; irrelevant payload remains untouched.
        assert(fresh.mfc_queue[prior_count].size==4096 && fresh.mfc_queue[prior_count].lsa==0xaaaaaaaa);
        sweep(old);sweep(fresh);sweep(reference);
        assert(fresh.mfc_size==prior_count+1 && reference.mfc_size==fresh.mfc_size);
        assert(fresh.mfc_barrier==reference.mfc_barrier && fresh.mfc_fence==reference.mfc_fence);
        assert(fresh.actions.empty() && reference.actions.empty());
        tag_query(old);tag_query(fresh);tag_query(reference);
        if(old.ch_tag_stat.count)++premature_before;
        if(fresh.ch_tag_stat.count)++premature_after;
        assert(!fresh.ch_tag_stat.count && fresh.ch_tag_upd==MFC_TAG_UPDATE_ALL);
        assert(fresh.get_mfc_completed()==0);
        assert(fresh.ch_tag_upd==reference.ch_tag_upd);
        resume(fresh);resume(reference);
        assert(fresh.actions==reference.actions && fresh.ch_tag_stat.value==reference.ch_tag_stat.value);
        ++scenarios;++matched_after;if(stale!=desired)++stale_slot_cases;
    }
    // Unchanged queue encodings for ordinary fenced/unfenced DMA commands.
    for(MFC command:{MFC_PUT_CMD,MFC_PUTB_CMD,MFC_PUTF_CMD,MFC_GET_CMD,MFC_GETB_CMD,MFC_GETF_CMD})
    for(u32 tag=0;tag<32;++tag) {
        Thread old=fixture(tag,255,command,1),fresh=old;
        Emitter a(old,command,tag),b(fresh,command,tag);a.before();b.after();
        assert(std::memcmp(old.mfc_queue,fresh.mfc_queue,sizeof(old.mfc_queue))==0);
        assert(old.mfc_fence==fresh.mfc_fence && old.mfc_barrier==fresh.mfc_barrier);
        assert(a.storage.writes==b.storage.writes);++unchanged_dma;
    }
    // The existing invalid-slot selection still guards a full queue before a
    // write can occur; the patch adds no bypass or out-of-bounds publication.
    for(MFC command:{MFC_BARRIER_CMD,MFC_EIEIO_CMD,MFC_SYNC_CMD})for(bool candidate:{false,true}) {
        Thread thread;thread.mfc_size=16;Emitter emitter(thread,command,31);
        bool caught=false;try{if(candidate)emitter.after();else emitter.before();}catch(const GuardedAccess&){caught=true;}
        assert(caught && emitter.storage.writes==0 && thread.mfc_size==16);++full_queue_guards;
    }
    assert(premature_before==3u*32u*248u*2u && premature_after==0);
    std::cout<<"{\"passed\":true,\"scenarios\":"<<scenarios<<",\"baselinePrematureCompletions\":"<<premature_before
        <<",\"candidatePrematureCompletions\":"<<premature_after<<",\"candidateMatchesReference\":"<<matched_after
        <<",\"staleSlotCases\":"<<stale_slot_cases<<",\"fullQueueGuards\":"<<full_queue_guards
        <<",\"unchangedDMAEncodings\":"<<unchanged_dma<<",\"barriersPreservedUntilListAck\":true,\"publicationOrderPreserved\":true}";
}
