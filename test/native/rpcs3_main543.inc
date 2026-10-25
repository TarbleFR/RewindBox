template<class M> std::string lookup_json(const M& m) {
    char out[1024];
    std::snprintf(out,sizeof(out),"{\"concurrentRequests\":%u,\"concurrentBuilds\":%u,\"concurrentNullReturns\":%u,\"concurrentDistinct\":%u,"
        "\"preloadBuilds\":%u,\"preloadNullReturns\":%u,\"failureBuilds\":%u,\"failureExceptions\":%u,\"failureNullReturns\":%u,"
        "\"failureStickyNull\":%u,\"nullResultRetryNull\":%u,\"asyncRequests\":%u,\"asyncJobs\":%u,\"missFlagMismatches\":%u,"
        "\"dsRequests\":[%u,%u,%u,%u,%u],\"dsBuilds\":[%u,%u,%u,%u,%u],\"hashPairs\":%u,\"hashDistinct\":%u}",
        m.concurrent_requests,m.concurrent_builds,m.concurrent_null_returns,m.concurrent_distinct,m.preload_builds,m.preload_null_returns,
        m.failure_builds,m.failure_exceptions,m.failure_null_returns,m.failure_sticky_null,m.null_result_retry_null,m.async_requests,
        m.async_jobs,m.miss_flag_mismatches,m.ds_requests[0],m.ds_requests[1],m.ds_requests[2],m.ds_requests[3],m.ds_requests[4],
        m.ds_builds[0],m.ds_builds[1],m.ds_builds[2],m.ds_builds[3],m.ds_builds[4],m.hash_pairs,m.hash_distinct);
    return out;
}
template<class M> std::string store_json(const M& m) {
    char out[512];
    std::snprintf(out,sizeof(out),"{\"records\":%u,\"producers\":%u,\"filesVerified\":%u,\"tempFilesLeft\":%u,\"callerP50Us\":%.1f,"
        "\"callerMaxUs\":%.1f,\"callerTotalMs\":%.3f,\"fsyncs\":%u}",
        m.records,m.producers,m.files_verified,m.temp_files_left,m.caller_p50_us,m.caller_max_us,m.caller_total_ms,m.fsyncs);
    return out;
}
int main() {
    const auto before_lookup=before::lookup_test();
    const auto after_lookup=after::lookup_test();
    const auto ds_cases=after::ds_reference_test();
    const auto builds542=regression542::test(true);
    const auto blend_cases=regression542::semantic_test();
    const auto host_before=store_before::store_test(48,1,0);
    const auto host_after=store_after::store_test(48,1,0);
    const auto slow_before=store_before::store_test(24,1,10000);
    const auto slow_after=store_after::store_test(24,1,10000);
    const auto concurrent=store_after::store_test(400,8,0);
    assert(store_after::thread_ctrl::lowered>0 && store_after::thread_ctrl::lowered_by!=std::this_thread::get_id());
    rpcs3::ios::shader_timing::publication.take();
    const auto bounded=store_after::store_test(300,1,2000);
    const auto pub=rpcs3::ios::shader_timing::publication.take();
    if (!(pub.deferred+pub.inline_writes==300 && pub.inline_writes>0 && pub.depth_peak<=257 && !pub.failures))
        std::fprintf(stderr,"bounded: deferred=%llu inline=%llu peak=%llu failures=%llu\n",(unsigned long long)pub.deferred,
            (unsigned long long)pub.inline_writes,(unsigned long long)pub.depth_peak,(unsigned long long)pub.failures);
    // Queue capacity 256 plus the one record the writer holds.
    assert(pub.deferred+pub.inline_writes==300 && pub.inline_writes>0 && pub.depth_peak<=257 && !pub.failures);
    assert(pub.write.count==300 && pub.caller.count==300);
    // The RSX-side cost no longer includes three fsync+rename operations.
    assert(slow_after.caller_p50_us*20<slow_before.caller_p50_us);
    const auto deferred=deferred_test();
    const auto feedback=feedback_test();
    timing_test();
    std::printf("{\"lookupBefore\":%s,\"lookupAfter\":%s,\"depthStencilReferenceCases\":%u,"
        "\"regression542Builds\":[%u,%u,%u,%u],\"regression542BlendCases\":%u,"
        "\"storeHostFsyncBefore\":%s,\"storeHostFsyncAfter\":%s,\"storeInjected10msBefore\":%s,\"storeInjected10msAfter\":%s,"
        "\"storeConcurrentAfter\":%s,\"storeBoundedAfter\":%s,\"boundedDeferred\":%llu,\"boundedInline\":%llu,\"boundedDepthPeak\":%llu,"
        "\"deferredOrdered\":%u,\"deferredConcurrent\":%u,\"deferredInline\":%u,\"feedbackBitCases\":%u,\"saveCases\":%u,\"fingerprintCases\":%u}\n",
        lookup_json(before_lookup).c_str(),lookup_json(after_lookup).c_str(),ds_cases,builds542[0],builds542[1],builds542[2],builds542[3],
        blend_cases,store_json(host_before).c_str(),store_json(host_after).c_str(),store_json(slow_before).c_str(),store_json(slow_after).c_str(),
        store_json(concurrent).c_str(),store_json(bounded).c_str(),(unsigned long long)pub.deferred,(unsigned long long)pub.inline_writes,
        (unsigned long long)pub.depth_peak,deferred.ordered,deferred.concurrent,deferred.inline_writes,feedback.bit_cases,feedback.save_cases,
        feedback.fingerprint_cases);
}
