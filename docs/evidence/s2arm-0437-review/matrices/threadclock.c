#include <stdint.h>
#include <stdlib.h>
#include <time.h>

uint64_t thread_nanoseconds(void) {
    struct timespec time;
    if (clock_gettime(CLOCK_THREAD_CPUTIME_ID, &time) != 0) abort();
    return (uint64_t)time.tv_sec * UINT64_C(1000000000) + (uint64_t)time.tv_nsec;
}
