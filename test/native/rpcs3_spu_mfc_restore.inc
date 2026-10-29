using s64=std::int64_t;
struct MaxValue {template<class T>constexpr operator T()const{return std::numeric_limits<T>::max();}};constexpr MaxValue umax{};
enum cpu_flag:u32 {pending=1,wait=2,temp=4};
namespace utils {
struct serial {
 bool writing;std::vector<u8> bytes;std::size_t cursor{};
 bool is_writing()const{return writing;}
 template<class T>void one(T&& v){
  using V=std::remove_reference_t<T>;
  if constexpr(requires {v.data();v.size_bytes();}){
   for(auto& x:v)one(x);
  }else{
   static_assert(std::is_trivially_copyable_v<V>);
   if(writing){const auto* p=reinterpret_cast<const u8*>(&v);bytes.insert(bytes.end(),p,p+sizeof(V));}
   else{if constexpr(std::is_const_v<V>){assert(false);}else{assert(cursor+sizeof(V)<=bytes.size());std::memcpy(&v,bytes.data()+cursor,sizeof(V));cursor+=sizeof(V);}}
  }
 }
 template<class... T>void operator()(T&&...v){(one(v),...);}
 operator u8(){u8 v{};one(v);return v;}
};
}
// @STATE_MEMBERS@
 u32 state{},last_getllar_addr{};
 bool test_stopped(){return false;}
 void wakeup_delay(){state&=~cpu_flag::wait;}
 u64 gpr[2]{};
 spu_mfc_cmd ch_mfc_cmd{},mfc_prxy_cmd{};
 u32 mfc_prxy_mask{},ch_stall_mask{},snr_config{},run_ctrl{};
 struct {u64 all{};}mfc_prxy_write_state;
 Channel ch_stall_stat,ch_atomic_stat,ch_out_mbox,ch_out_intr_mbox,ch_snr1,ch_snr2,exit_status;
 struct {u32 status{};}status;
 struct StatusNpc {u32 status{};StatusNpc& raw(){return *this;}}status_npc;
 u64 ch_dec_start_timestamp{},ch_dec_value{};bool is_dec_frozen{};
 struct InMbox {
  u8 count{};u32 values[4]{};
  u8 try_read(u32* output){std::copy(values,values+count,output);return count;}
  void set_values(u8 n,u32 a,u32 b,u32 c,u32 d){count=n;values[0]=a;values[1]=b;values[2]=c;values[3]=d;}
 }ch_in_mbox;
// @DRIVER@
struct Counters {u32 cases{},before_stalls{},after_completed{},list_blocks{},empty{},disabled{};} counts;
template<class T>void load(T& thread,const std::vector<u8>& bytes){utils::serial reader{false,bytes};thread.restore(reader);assert(reader.cursor==bytes.size());}
void scenario(u32 shuffle,u32 size,u32 tag,bool stalled,bool steps){
 g_cfg.core.mfc_transfers_shuffling=shuffle;g_cfg.core.mfc_shuffling_in_steps=steps;
 before::spu_thread saved;
 saved.mfc_size=size;saved.mfc_barrier=0;saved.mfc_fence=size?(1u<<tag):0;
 saved.ch_tag_mask=1u<<tag;saved.ch_tag_upd=MFC_TAG_UPDATE_ALL;
 for(u32 i=0;i<size;++i){auto& q=saved.mfc_queue[i];q.cmd=stalled?MFC_GETL_CMD:MFC_PUT_CMD;q.tag=tag|(stalled?0x80:0);q.eah=i+1;q.size=16;q.eal=0x60300510+i*128;}
 utils::serial writer{true,{}};saved.serialize_common(writer);
 before::spu_thread old;after::spu_thread fresh;load(old,writer.bytes);load(fresh,writer.bytes);
 assert(old.mfc_size==fresh.mfc_size&&std::memcmp(old.mfc_queue,fresh.mfc_queue,sizeof(old.mfc_queue))==0);
 assert(fresh.state==(shuffle&&size?cpu_flag::pending:0u));
 active=&old;utils::clock_calls=0;utils::fixed=false;auto prior=old.read_tag();
 active=&fresh;utils::clock_calls=0;utils::fixed=false;auto next=fresh.read_tag();active=nullptr;
 assert(prior==-1);++counts.cases;
 if(!shuffle){assert(next==-1&&fresh.mfc_size==size&&fresh.actions.empty());++counts.disabled;return;}
 if(!size){assert(next==-1&&fresh.mfc_size==0&&fresh.actions.empty());++counts.empty;return;}
 ++counts.before_stalls;
 if(stalled){
  assert(next==-1&&fresh.mfc_size==size&&fresh.ch_tag_stat.count==0);++counts.list_blocks;
  for(u32 i=0;i<size;++i)fresh.mfc_queue[i].tag&=0x7f;
  fresh.complete_lists=true;active=&fresh;next=fresh.read_tag();active=nullptr;
 }
 assert(next==s64{1}<<tag&&fresh.mfc_size==0&&fresh.mfc_fence==0);
 assert(fresh.ch_tag_upd==MFC_TAG_UPDATE_IMMEDIATE);++counts.after_completed;
}
int main(){
 for(u32 shuffle:{0u,1u,16u})for(u32 size:{0u,1u,2u,16u})for(u32 tag:{0u,5u,31u})for(bool stalled:{false,true})for(bool steps:{false,true})scenario(shuffle,size,tag,stalled,steps);
 std::cout<<"{\"cases\":"<<counts.cases<<",\"baselineStalledWaits\":"<<counts.before_stalls<<",\"candidateCompletedWaits\":"<<counts.after_completed<<",\"stalledListsRequireAck\":"<<counts.list_blocks<<",\"emptyQueueCases\":"<<counts.empty<<",\"disabledShufflingCases\":"<<counts.disabled<<",\"queueRoundtripPreserved\":true,\"interruptsDisabled\":true,\"timeoutIndependentChannelDrain\":true}";
}
