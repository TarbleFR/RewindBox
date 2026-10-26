#import <Foundation/Foundation.h>
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <thread>
#include <vector>

#import "packages/rpcs3_internal_bridge/ios/Classes/Rpcs3Diagnostics.h"

// REWINDBOX_CORE_LOG_DURABLE_V1 on the actual Foundation logger.
// report_fatal_error (rpcs3/ios/RPCS3IOS.cpp) passes its message to the log
// callback, which forwards it as a "core_log" diagnostic, then calls
// std::abort() as soon as the callback returns. This program does the same:
//   <directory> fatal   -- queue 2000 asynchronous samples (the 1 Hz sampler
//                          and the other stages share the queue), log one fatal
//                          core_log line, abort.
//   <directory> burst   -- 8 threads log 100 core_log lines each while samples
//                          are queued, then abort: no wait may deadlock and
//                          every core_log line must be in the file.
// The Python runner reads RPCS3-diagnostic.log after the abort. Built against
// the 551 logger (control), the fatal line is lost.

int main(int argc, const char* argv[]) {
  @autoreleasepool {
    assert(argc == 3);
    NSString* directory = [NSString stringWithUTF8String:argv[1]];
    RPCS3DiagnosticsSetDirectoryForTesting(directory);
    if (std::strcmp(argv[2], "fatal") == 0) {
      for (unsigned i = 0; i < 2000; ++i)
        RPCS3Diagnostic(@"performance_sample", [NSString stringWithFormat:@"title=TEST sample=%u", i]);
      RPCS3Diagnostic(@"core_log", @"TID: 1: CORE_LOG_DURABLE_552_FATAL Verification failed (object: 0x0)");
      std::abort();
    }
    if (std::strcmp(argv[2], "burst") == 0) {
      std::vector<std::thread> threads;
      for (unsigned t = 0; t < 8; ++t) {
        threads.emplace_back([t] {
          @autoreleasepool {
            for (unsigned i = 0; i < 100; ++i) {
              RPCS3Diagnostic(@"performance_sample", [NSString stringWithFormat:@"title=TEST thread=%u sample=%u", t, i]);
              RPCS3Diagnostic(@"core_log", [NSString stringWithFormat:@"TID: %u: CORE_LOG_DURABLE_552_BURST thread=%u line=%u", t, t, i]);
            }
          }
        });
      }
      for (auto& thread : threads) thread.join();
      std::abort();
    }
    std::fprintf(stderr, "unknown mode %s\n", argv[2]);
    return 2;
  }
}
