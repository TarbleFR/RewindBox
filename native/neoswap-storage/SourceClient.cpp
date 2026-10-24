// SPDX-License-Identifier: MIT
#include "SourceClient.h"
#include "FrameClient.h"
#include <algorithm>
#include <chrono>
#if !defined(__cpp_exceptions)
#error "NeoSwap SourceClient.cpp requires exceptions in this dedicated unit"
#endif
namespace neostation::source_client {
bool ColdSource::offload(std::string& source,uint32_t domain) noexcept {
    if(reference_ || source.empty())return false;
    const auto* api=installed.load();if(!api)return false;
    const auto session=api->session();if(!session)return false;
    try {
        auto ref=std::make_shared<Reference>(); // Before host ownership transfer.
        ref->api=api;ref->session=session;ref->bytes=source.size();
        uint64_t object=0;
        if(api->admit(session,domain,source.data(),source.size(),&object)!=NS_SOURCE_OK || !object)
            return false;
        ref->object=object;reference_=std::move(ref);
        const auto capacity=source.capacity();std::string().swap(source);
        api->released(session,capacity);
        return true;
    }catch(...){return false;}
}
int ColdSource::restore(std::string& output,int& os_error) const noexcept {
    os_error=0;output.clear();if(!reference_)return NS_SOURCE_MISSING;
    const auto& ref=*reference_;
    try {
        output.resize(static_cast<size_t>(ref.bytes));
        const auto result=ref.api->read(ref.session,ref.object,output.data(),ref.bytes,&os_error);
        if(result!=NS_SOURCE_OK)output.clear();
        return result;
    }catch(...){output.clear();return NS_SOURCE_BUSY;}
}
bool ColdFrame::offload(const char* pixels, size_t bytes) noexcept {
    if(reference_ || !pixels || bytes < 4096 || bytes > frame_max_bytes)return false;
    const auto* api=installed.load();if(!api)return false;
    const auto epoch=api->session();if(!epoch)return false;
    try {
        auto candidate=std::make_shared<FrameReference>();
        candidate->bytes=bytes;
        candidate->count=static_cast<uint32_t>((bytes+NEOSWAP_SOURCE_MAX_BYTES-1)/NEOSWAP_SOURCE_MAX_BYTES);
        const auto chunk=(bytes+candidate->count-1)/candidate->count;
        size_t offset=0;
        for(uint32_t index=0;index<candidate->count;++index){
            auto& ref=candidate->chunks[index];
            ref.api=api;ref.session=epoch;ref.bytes=std::min(chunk,bytes-offset);
            if(api->admit(epoch,frame_domain,pixels+offset,ref.bytes,&ref.object)!=NS_SOURCE_OK || !ref.object)
                return false; // candidate retires ALL accepted chunks exactly once
            offset+=static_cast<size_t>(ref.bytes);
        }
        // A concurrent stop/relaunch must never strand the original frame in
        // a retired epoch. Old hosts reject domain 3 and keep the RAM fallback.
        if(api->session()!=epoch)return false;
        reference_=std::move(candidate);return true;
    }catch(...){return false;}
}
bool ColdFrame::offload_copy(size_t bytes,PixelCopy copy,void* context) noexcept {
    const auto* api=installed.load();
    if(reference_ || !copy || bytes<4096 || bytes>frame_max_bytes || !api || !api->session())return false;
    try {
        std::string packed(bytes,'\0');
        if(copy(packed.data(),bytes,context)!=static_cast<int>(bytes))return false;
        return offload(packed.data(),packed.size());
    }catch(...){return false;}
}
namespace {
void frame_peak(std::atomic<uint64_t>& field,uint64_t value) noexcept {
    auto old=field.load(std::memory_order_relaxed);
    while(old<value&&!field.compare_exchange_weak(old,value,std::memory_order_relaxed)){}
}
bool reserve_frame_payload(uint64_t bytes) noexcept {
    auto used=frame_prefetch_payload_bytes.load(std::memory_order_relaxed);
    do {
        if(bytes>frame_prefetch_payload_limit || used>frame_prefetch_payload_limit-bytes)return false;
    }while(!frame_prefetch_payload_bytes.compare_exchange_weak(used,used+bytes,std::memory_order_relaxed));
    const auto count=frame_prefetch_count.fetch_add(1,std::memory_order_relaxed);
    if(count>=frame_prefetch_count_limit){
        frame_prefetch_count.fetch_sub(1,std::memory_order_relaxed);
        frame_prefetch_payload_bytes.fetch_sub(bytes,std::memory_order_relaxed);return false;
    }
    frame_peak(frame_prefetch_peak_bytes,used+bytes);return true;
}
void release_frame_payload(uint64_t bytes) noexcept {
    frame_prefetch_payload_bytes.fetch_sub(bytes,std::memory_order_relaxed);
    frame_prefetch_count.fetch_sub(1,std::memory_order_relaxed);
}
int read_frame_payload(const FrameReference& frame,std::string& output,int& os_error) noexcept {
    try {
        output.resize(static_cast<size_t>(frame.bytes));size_t offset=0;
        for(uint32_t index=0;index<frame.count;++index){
            const auto& ref=frame.chunks[index];
            const int code=ref.api->read(ref.session,ref.object,output.data()+offset,ref.bytes,&os_error);
            if(code!=NS_SOURCE_OK){output.clear();return code;}
            offset+=static_cast<size_t>(ref.bytes);
        }
        return NS_SOURCE_OK;
    }catch(...){output.clear();return NS_SOURCE_BUSY;}
}
}
FrameReference::~FrameReference(){
    if(warm_charge){std::string().swap(warm_pixels);release_frame_payload(bytes);}
}
bool ColdFrame::prefetch() const noexcept {
    if(!reference_)return false;
    auto frame=reference_; // pins objects and epoch during the existing producer's read
    // A zero/stale session also covers paused or pressure-closed admission.
    // Demand restores remain permitted; speculative RAM is not grown there.
    if(!frame->chunks[0].api || frame->chunks[0].api->session()!=frame->chunks[0].session){
        frame_prefetch_refusals.fetch_add(1);return false;
    }
    try {
        {
            std::unique_lock lock(frame->warm_mutex,std::try_to_lock);
            if(!lock.owns_lock() || frame->warm_state.load()!=FrameWarmState::cold)return false;
            if(!reserve_frame_payload(frame->bytes)){frame_prefetch_refusals.fetch_add(1);return false;}
            frame->warm_charge=true;
            frame->warm_state.store(FrameWarmState::loading);
        }
        frame_prefetch_requests.fetch_add(1);
        std::string pixels;int error=0;
        const int result=read_frame_payload(*frame,pixels,error);
        {
            std::lock_guard lock(frame->warm_mutex);
            if(result==NS_SOURCE_OK){
                frame->warm_pixels.swap(pixels);
                frame->warm_state.store(FrameWarmState::ready);
            }else{
                std::string().swap(pixels);
                release_frame_payload(frame->bytes);frame->warm_charge=false;
                frame->warm_state.store(FrameWarmState::failed);
                frame_prefetch_failures.fetch_add(1);
            }
        }
        frame->warm_changed.notify_all();return result==NS_SOURCE_OK;
    }catch(...){
        // No I/O occurs under this metadata lock. Always release waiters, and
        // keep the archived original available to the normal retry path.
        std::lock_guard lock(frame->warm_mutex);
        if(frame->warm_charge){release_frame_payload(frame->bytes);frame->warm_charge=false;}
        frame->warm_state.store(FrameWarmState::failed);frame->warm_changed.notify_all();
        frame_prefetch_failures.fetch_add(1);return false;
    }
}
int ColdFrame::restore(std::string& output,int& os_error,bool* prefetched) const noexcept {
    os_error=0;output.clear();if(prefetched)*prefetched=false;
    if(!reference_)return NS_SOURCE_MISSING;
    auto frame=reference_;
    try {
        std::string retired_output;
        std::unique_lock lock(frame->warm_mutex);
        const auto start=std::chrono::steady_clock::now();
        frame->warm_changed.wait(lock,[&]{return frame->warm_state.load()!=FrameWarmState::loading;});
        frame_peak(frame_prefetch_wait_max_us,std::chrono::duration_cast<std::chrono::microseconds>(
            std::chrono::steady_clock::now()-start).count());
        if(frame->warm_state.load()==FrameWarmState::ready){
            output.swap(frame->warm_pixels);retired_output.swap(frame->warm_pixels);
            release_frame_payload(frame->bytes);frame->warm_charge=false;
            frame->warm_state.store(FrameWarmState::consumed);
            if(prefetched)*prefetched=true;
            frame_prefetch_hits.fetch_add(1);return NS_SOURCE_OK;
        }
        frame->warm_state.store(FrameWarmState::consumed);
        lock.unlock();frame_demand_reads.fetch_add(1);
        return read_frame_payload(*frame,output,os_error);
    }catch(...){output.clear();return NS_SOURCE_BUSY;}
}
}
