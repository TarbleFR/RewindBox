// Isolate the report's time bases using deterministic synthetic timestamps.
#include <assert.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
static time_t epoch_s;
static int sensor_clock(clockid_t clock, struct timespec *t) {
    assert(clock==CLOCK_MONOTONIC); t->tv_sec=epoch_s; t->tv_nsec=0; return 0;
}
static char row[1200];
static void report(const char *fmt,...) {
    va_list ap;va_start(ap,fmt);vsnprintf(row,sizeof row,fmt,ap);va_end(ap);
}
#define clock_gettime sensor_clock
#define MLOG report
#include "rb_fi_present_stats.h"
#undef clock_gettime

int main(void) {
    setenv("S2A_RB_FI_PRESENT_STATS","1",1);
    epoch_s=100; rb_fi_stats_begin_session();
    uint64_t first=rb_fi_stats_reserve(),last=rb_fi_stats_reserve();
    rb_fi_stats_update(first,RB_FI_GPU_READY,RB_FI_METALFX,0);
    rb_fi_stats_update(last,RB_FI_DISPLAY_READY,RB_FI_GPU_ERROR,9.5);
    rb_fi_stats_update(last,RB_FI_GPU_READY,RB_FI_CUT,0);
    rb_fi_stats_update(first,RB_FI_DISPLAY_READY,RB_FI_GPU_ERROR,9.25);
    epoch_s=110; rb_fi_stats_report(0);
    assert(strstr(row,"wall_ns=10000000000 classification_complete=1"));
    assert(strstr(row,"first_midpoint_presented_s=9.250000000 last_midpoint_presented_s=9.500000000 confirmed_midpoint_span_s=0.250000000"));
    puts(row);
    uint64_t pending=rb_fi_stats_reserve();
    rb_fi_stats_update(pending,RB_FI_DISPLAY_READY,RB_FI_GPU_ERROR,9.75);
    epoch_s=111; rb_fi_stats_report(1);
    assert(strstr(row,"wall_ns=11000000000 classification_complete=0 registered=3 pending=1"));
    puts(row);
    rb_fi_stats_update(pending,RB_FI_GPU_READY,RB_FI_METALFX,0);
    epoch_s=130; rb_fi_stats_begin_session();
    rb_fi_stats_update(pending,RB_FI_GPU_READY,RB_FI_METALFX,0);
    epoch_s=135; rb_fi_stats_report(1);
    assert(strstr(row,"session=2 final=1 wall_ns=5000000000 classification_complete=1 registered=0"));
    assert(strstr(row,"confirmed_midpoint_span_s=0.000000000"));
    puts(row);
}
