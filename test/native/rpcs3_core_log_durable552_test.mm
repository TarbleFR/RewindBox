#import <Foundation/Foundation.h>
#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>

#import "packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.h"

// REWINDBOX_CORE_LOG_DURABLE_V1, carried by REWINDBOX_CORE_LOG_BOUNDED_621, on
// the actual Foundation logger. report_fatal_error (rpcs3/ios/RPCS3IOS.cpp)
// passes its message to the log callback, then calls std::abort() as soon as
// the callback returns. Since 621 the callback (RPCS3ForwardCoreLog) writes a
// fatal line at once to RPCS3-last-fatal.log, queues it for the journal and
// waits at most 500 ms for the queue; ordinary lines never wait. This program
// takes the same calls:
//   <directory> fatal   -- queue 2000 asynchronous samples, take the fatal
//                          path, abort: the line must be in RPCS3-last-fatal.log.
//   <directory> burst   -- 8 threads log 100 core_log lines each while samples
//                          are queued, then a fatal line with a long drain,
//                          then abort: no deadlock, every line in the journal,
//                          and no caller waited for the disk (slowest call
//                          printed on stderr as SLOWEST_US=<n>).

static void fatal_path(const char* message, uint32_t drain_ms) {
  RPCS3RecordFatalLine(message, NO);
  RPCS3CoreLogLine([NSString stringWithUTF8String:message], strlen(message));
  RPCS3DiagnosticsDrain(drain_ms);
}

int main(int argc, const char* argv[]) {
  @autoreleasepool {
    assert(argc == 3);
    NSString* directory = [NSString stringWithUTF8String:argv[1]];
    RPCS3DiagnosticsSetDirectoryForTesting(directory);
    if (std::strcmp(argv[2], "fatal") == 0) {
      for (unsigned i = 0; i < 2000; ++i)
        RPCS3Diagnostic(@"performance_sample", [NSString stringWithFormat:@"title=TEST sample=%u", i]);
      fatal_path("TID: 1: CORE_LOG_DURABLE_552_FATAL Verification failed (object: 0x0)", 500);
      std::abort();
    }
    if (std::strcmp(argv[2], "burst") == 0) {
      std::atomic<long long> slowest{0};
      std::vector<std::thread> threads;
      for (unsigned t = 0; t < 8; ++t) {
        threads.emplace_back([t, &slowest] {
          @autoreleasepool {
            for (unsigned i = 0; i < 100; ++i) {
              RPCS3Diagnostic(@"performance_sample", [NSString stringWithFormat:@"title=TEST thread=%u sample=%u", t, i]);
              NSString* line = [NSString stringWithFormat:@"TID: %u: CORE_LOG_DURABLE_552_BURST thread=%u line=%u", t, t, i];
              const auto begin = std::chrono::steady_clock::now();
              RPCS3CoreLogLine(line, [line lengthOfBytesUsingEncoding:NSUTF8StringEncoding]);
              const long long us = std::chrono::duration_cast<std::chrono::microseconds>(
                  std::chrono::steady_clock::now() - begin).count();
              long long seen = slowest.load();
              while (us > seen && !slowest.compare_exchange_weak(seen, us)) {}
            }
          }
        });
      }
      for (auto& thread : threads) thread.join();
      std::fprintf(stderr, "SLOWEST_US=%lld\n", slowest.load());
      fatal_path("TID: 1: CORE_LOG_DURABLE_552_BURST_END fatal after the burst", 10000);
      std::abort();
    }
    std::fprintf(stderr, "unknown mode %s\n", argv[2]);
    return 2;
  }
}
