// SPDX-License-Identifier: Apache-2.0
#include "rb_long_cadence.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

enum { CAP=200000 };
static uint64_t events[CAP], values[CAP];
static rb30_data live;
static unsigned n, checks;
static int cmp(const void *a,const void *b) {
    uint64_t x=*(const uint64_t *)a, y=*(const uint64_t *)b;
    return (x>y)-(x<y);
}
static void feed(uint64_t stamp) {
    assert(n<CAP); events[n++]=stamp; rb30_observe(&live,stamp);
}
// Independent oracle retains raw times, sorts unquantized intervals and clips
// silent spans at the two boundaries. Group intervals by the later endpoint.
static void check(const rb30_bucket *summary, uint64_t start, uint64_t end) {
    unsigned k=0, count=0, overflow=0; uint64_t max=0, previous=start, silence=0;
    for (unsigned i=0;i<n;++i) {
        uint64_t t=events[i]; if (t<start || t>=end) continue;
        ++count;
        uint64_t gap=t-previous; if (gap>silence) silence=gap; previous=t;
        if (!i) continue;
        uint64_t delta=t-events[i-1]; values[k++]=delta;
        if (delta>max) max=delta;
        if (delta>RB30_REGULAR*RB30_BIN_NS) ++overflow;
    }
    if (end-previous>silence) silence=end-previous;
    assert(summary->count==count && summary->intervals==k && summary->max_interval==max);
    assert(summary->hist[RB30_REGULAR]==overflow && rb30_silence(summary,start,end)==silence);
    qsort(values,k,sizeof *values,cmp);
    for (unsigned p=50;p<=99;p+=p==50?45:4) {
        uint64_t rank=((uint64_t)k*p+99)/100;
        uint64_t raw=rank ? values[rank-1] : 0;
        uint64_t expected=raw ? (1+(raw-1)/RB30_BIN_NS)*RB30_BIN_NS : 0;
        if (expected>RB30_REGULAR*RB30_BIN_NS) expected=0;
        assert(rb30_quantile(summary,p)==expected); ++checks;
    }
}
static void verify(unsigned minutes) {
    rb30_bucket total={0};
    for (unsigned m=0;m<minutes;++m) {
        uint64_t start=live.start+m*RB30_MINUTE_NS, end=start+RB30_MINUTE_NS;
        check(&live.minute[m],start,end);
        rb30_merge(&total,&live.minute[m]);
        check(&total,live.start,end);
    }
}
int main(void) {
    verify(30);
    feed(0); feed(RB30_BIN_NS); feed(RB30_BIN_NS*513); feed(RB30_BIN_NS*1025+1);
    feed(RB30_MINUTE_NS); feed(20*RB30_MINUTE_NS+1); verify(30);
    rb30_observe(&live,events[n-1]); rb30_observe(&live,events[n-1]-1);
    rb30_observe(&live,30*RB30_MINUTE_NS); assert(live.clock_errors==2);
    assert(live.minute[1].count==1 && live.minute[20].count==1);
    memset(&live,0,sizeof live); live.start=UINT64_C(882010203991); n=0;
    rb30_observe(&live,live.start-1); assert(live.clock_errors==1);
    uint32_t r=713713; uint64_t t=live.start;
    while (t<live.start+30*RB30_MINUTE_NS) {
        feed(t); r=r*1664525u+1013904223u;
        uint64_t delta=UINT64_C(15000000)+r%4000000u;
        if (!(r%573)) delta=UINT64_C(700000000);
        if (!(r%11623)) delta=2*RB30_MINUTE_NS+42;
        t+=delta;
    }
    verify(30);
    printf("raw_time_oracle=pass quantile_comparisons=%u frames=%u persistent_bytes=%zu checkpoint_copy_bytes=%zu\n",checks,n,sizeof live,sizeof live);
}
