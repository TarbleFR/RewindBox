#include <pthread.h>
#include <stdint.h>
#include <stdatomic.h>
#include <stdlib.h>
#include <assert.h>
#include <stdio.h>
#define PQ 8
static pthread_mutex_t g_pq_mu=PTHREAD_MUTEX_INITIALIZER, step_mu=PTHREAD_MUTEX_INITIALIZER;
static pthread_cond_t g_pq_cv=PTHREAD_COND_INITIALIZER, steps=PTHREAD_COND_INITIALIZER;
static uint64_t g_pq_done,g_pq_in;
static atomic_int g_present_discard;
static int waits, first_gap, resume, complete, high_water;
static _Thread_local int first_producer;
static void wait_for_room(void) {
    pthread_mutex_lock(&step_mu); waits++; pthread_cond_broadcast(&steps); pthread_mutex_unlock(&step_mu);
    pthread_cond_wait(&g_pq_cv,&g_pq_mu);
}
static void end_block(void) {
    if (!first_producer) return;
    pthread_mutex_lock(&step_mu);
    if (!first_gap) { first_gap=1;pthread_cond_broadcast(&steps);while(!resume)pthread_cond_wait(&steps,&step_mu); }
    pthread_mutex_unlock(&step_mu);
}
#define DM_BLOCK_BEGIN() (void)0
#define DM_BLOCK_END() end_block()
#define RB_WAKE_CALL(a,b,c) wait_for_room()
static uint64_t enqueue(void) {
#include "admission.inc"
    uint64_t ticket=++g_pq_in;
    unsigned depth=ticket-g_pq_done;
    if(depth>high_water)high_water=depth;
    pthread_mutex_unlock(&g_pq_mu);
    return ticket;
}
static void *producer(void *data) {
    first_producer=1; enqueue();
    pthread_mutex_lock(&step_mu); complete=1;pthread_cond_broadcast(&steps);pthread_mutex_unlock(&step_mu);
    return NULL;
}
static void retire(void) {
    pthread_mutex_lock(&g_pq_mu);g_pq_done++;pthread_cond_broadcast(&g_pq_cv);pthread_mutex_unlock(&g_pq_mu);
}
int main(void) {
    high_water=g_pq_in=PQ;
    pthread_t a;pthread_create(&a,NULL,producer,NULL);
    pthread_mutex_lock(&step_mu);while(waits<1)pthread_cond_wait(&steps,&step_mu);pthread_mutex_unlock(&step_mu);
    retire();
    pthread_mutex_lock(&step_mu);while(!first_gap)pthread_cond_wait(&steps,&step_mu);pthread_mutex_unlock(&step_mu);
    enqueue();
    pthread_mutex_lock(&step_mu);resume=1;pthread_cond_broadcast(&steps);
    while(waits<2&&!complete)pthread_cond_wait(&steps,&step_mu);
    pthread_mutex_unlock(&step_mu);
    retire();
    pthread_join(a,NULL);
    printf("capacity=%d peak=%d producer_waits=%d tickets=%llu\n",PQ,high_water,waits,(unsigned long long)g_pq_in);
    return high_water!=PQ;
}
