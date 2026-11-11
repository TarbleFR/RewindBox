// See MeloNXHeapSampler.h. Plain C: nothing here may allocate, log or touch thread-local storage, since every line
// below the hook runs inside malloc and free.
#import "MeloNXHeapSampler.h"
#import <os/lock.h>
#import <pthread.h>
#import <stdatomic.h>
#import <stdlib.h>
#import <string.h>

typedef void(malloc_logger_t)(uint32_t type, uintptr_t arg1, uintptr_t arg2, uintptr_t arg3, uintptr_t result, uint32_t skip);
extern malloc_logger_t *malloc_logger;

// stack_logging.h
#define LOG_ALLOCATE 2u
#define LOG_DEALLOCATE 4u
#define LOG_HAS_ZONE 8u

#define INTERVAL ((uint64_t)256 << 10)
#define SLOTS (1u << 16)
#define PROBES 16u
#define STACKS 4096u
#define STRIPES 64u
#define TOMBSTONE ((uintptr_t)1)

typedef struct {
    _Atomic(uintptr_t) pointer;   // 0 empty, TOMBSTONE removed
    uint32_t weightKiB;
    uint32_t stack;
} Slot;

typedef struct {
    _Atomic(int64_t) remaining;
    _Atomic(uint64_t) seed;
    char pad[48];
} Stripe;

static Slot gSlots[SLOTS];
static MeloNXHeapSamplerStack gStacks[STACKS];
static uint64_t gStackHash[STACKS];   // 0 empty
static Stripe gStripes[STRIPES];
static os_unfair_lock gLock = OS_UNFAIR_LOCK_INIT;
static MeloNXHeapSamplerTotals gTotals;
static _Atomic(int) gActive;

static inline uint64_t mix(uint64_t value) {
    value ^= value >> 33; value *= 0xff51afd7ed558ccdULL; value ^= value >> 33; value *= 0xc4ceb9fe1a85ec53ULL; value ^= value >> 33;
    return value;
}

// The call's return addresses, from the frame records inside the calling thread's own stack only.
__attribute__((noinline)) static uint32_t walk(uint64_t *frames) {
    pthread_t self = pthread_self();
    uintptr_t high = (uintptr_t)pthread_get_stackaddr_np(self);
    uintptr_t low = high - pthread_get_stacksize_np(self);
    uintptr_t *frame = (uintptr_t *)__builtin_frame_address(0);
    uint32_t count = 0;
    while (count < MeloNXHeapSamplerFrames) {
        uintptr_t address = (uintptr_t)frame;
        if (address < low || address + 16 > high || (address & 7) != 0) break;
        uintptr_t next = frame[0], link = frame[1];
        if (link == 0) break;
        frames[count++] = (uint64_t)link;
        if (next <= address) break;
        frame = (uintptr_t *)next;
    }
    return count;
}

// With gLock held: the live sample in `slot` leaves the counts (the slot's pointer is the caller's to change).
static void forget(Slot *slot) {
    uint64_t weight = (uint64_t)slot->weightKiB << 10;
    MeloNXHeapSamplerStack *stack = &gStacks[slot->stack];
    stack->liveBytes -= weight < stack->liveBytes ? weight : stack->liveBytes;
    if (stack->liveSamples) stack->liveSamples--;
    gTotals.liveBytes -= weight < gTotals.liveBytes ? weight : gTotals.liveBytes;
    if (gTotals.liveSamples) gTotals.liveSamples--;
}

static void sampled(uintptr_t pointer, uint64_t size) {
    uint64_t frames[MeloNXHeapSamplerFrames];
    uint32_t count = walk(frames);
    uint64_t hash = 0x9e3779b97f4a7c15ULL;
    for (uint32_t index = 0; index < count; index++) hash = mix(hash ^ frames[index]);
    if (hash == 0) hash = 1;
    uint64_t weight = size > INTERVAL ? size : INTERVAL;
    os_unfair_lock_lock(&gLock);
    if (count == 0) gTotals.unwalkedSamples++;
    uint32_t stack = UINT32_MAX;
    for (uint32_t probe = 0; probe < PROBES; probe++) {
        uint32_t index = (uint32_t)((hash + probe) & (STACKS - 1));
        if (gStackHash[index] == hash) { stack = index; break; }
        if (gStackHash[index] == 0) {
            gStackHash[index] = hash;
            gStacks[index].frameCount = count;
            memcpy(gStacks[index].frames, frames, count * sizeof(uint64_t));
            gTotals.stacks++;
            stack = index;
            break;
        }
    }
    int placed = 0;
    if (stack != UINT32_MAX) {
        uint64_t home = mix((uint64_t)pointer);
        Slot *target = NULL;
        for (uint32_t probe = 0; probe < PROBES; probe++) {
            Slot *slot = &gSlots[(home + probe) & (SLOTS - 1)];
            uintptr_t held = atomic_load_explicit(&slot->pointer, memory_order_relaxed);
            if (held == pointer) {
                // A block whose free the hook did not see (a zone destroyed, a batch free): its record is replaced.
                forget(slot);
                target = slot;
                break;
            }
            if (target == NULL && (held == 0 || held == TOMBSTONE)) target = slot;
            if (held == 0) break;
        }
        if (target != NULL) {
            atomic_store_explicit(&target->pointer, TOMBSTONE, memory_order_release);
            target->weightKiB = (uint32_t)(weight >> 10 > UINT32_MAX ? UINT32_MAX : weight >> 10);
            target->stack = stack;
            atomic_store_explicit(&target->pointer, pointer, memory_order_release);
            placed = 1;
        }
    }
    if (placed) {
        gStacks[stack].liveBytes += weight; gStacks[stack].liveSamples++;
        gStacks[stack].totalBytes += weight; gStacks[stack].totalSamples++;
        gTotals.liveBytes += weight; gTotals.liveSamples++;
        gTotals.totalBytes += weight; gTotals.totalSamples++;
    } else {
        gTotals.droppedSamples++;
    }
    os_unfair_lock_unlock(&gLock);
}

static inline void allocated(uintptr_t pointer, uint64_t size) {
    if (pointer == 0 || size == 0) return;
    // A block of the interval or more is always recorded, at its own size. A smaller one is recorded when it brings
    // its thread's stripe to the end of its countdown, and then stands for one interval.
    if (size < INTERVAL) {
        Stripe *stripe = &gStripes[mix((uint64_t)(uintptr_t)pthread_self()) & (STRIPES - 1)];
        int64_t left = atomic_fetch_sub_explicit(&stripe->remaining, (int64_t)size, memory_order_relaxed) - (int64_t)size;
        if (left > 0) return;
        // The next countdown: between half the interval and one and a half (two threads here only move a sample).
        uint64_t seed = atomic_load_explicit(&stripe->seed, memory_order_relaxed) * 6364136223846793005ULL + 1442695040888963407ULL;
        atomic_store_explicit(&stripe->seed, seed, memory_order_relaxed);
        atomic_store_explicit(&stripe->remaining, (int64_t)(INTERVAL / 2 + (seed >> 33) % INTERVAL), memory_order_relaxed);
    }
    sampled(pointer, size);
}

static inline void released(uintptr_t pointer) {
    if (pointer == 0) return;
    uint64_t home = mix((uint64_t)pointer);
    for (uint32_t probe = 0; probe < PROBES; probe++) {
        Slot *slot = &gSlots[(home + probe) & (SLOTS - 1)];
        uintptr_t held = atomic_load_explicit(&slot->pointer, memory_order_acquire);
        if (held == 0) return;
        if (held != pointer) continue;
        os_unfair_lock_lock(&gLock);
        if (atomic_load_explicit(&slot->pointer, memory_order_relaxed) == pointer) {
            forget(slot);
            atomic_store_explicit(&slot->pointer, TOMBSTONE, memory_order_release);
        }
        os_unfair_lock_unlock(&gLock);
        return;
    }
}

static void hook(uint32_t type, uintptr_t arg1, uintptr_t arg2, uintptr_t arg3, uintptr_t result, uint32_t skip) {
    (void)skip;
    if (!(type & LOG_HAS_ZONE)) { arg3 = arg2; arg2 = arg1; }
    if ((type & LOG_ALLOCATE) && (type & LOG_DEALLOCATE)) {   // a block moved: arg2 the old pointer, arg3 the new size
        if (result == 0) return;
        released(arg2);
        allocated(result, arg3);
    } else if (type & LOG_DEALLOCATE) {
        released(arg2);
    } else if (type & LOG_ALLOCATE) {
        allocated(result, arg2);
    }
}

int MeloNXHeapSamplerStart(void) {
    if (atomic_exchange(&gActive, 1)) return 0;
    if (malloc_logger != NULL) { atomic_store(&gActive, 0); return -1; }
    os_unfair_lock_lock(&gLock);
    for (uint32_t index = 0; index < SLOTS; index++) atomic_store_explicit(&gSlots[index].pointer, 0, memory_order_relaxed);
    memset(gStacks, 0, sizeof(gStacks));
    memset(gStackHash, 0, sizeof(gStackHash));
    memset(&gTotals, 0, sizeof(gTotals));
    gTotals.intervalBytes = INTERVAL;
    os_unfair_lock_unlock(&gLock);
    for (uint32_t index = 0; index < STRIPES; index++) {
        uint64_t seed = mix(index + 1);
        atomic_store(&gStripes[index].seed, seed);
        atomic_store(&gStripes[index].remaining, (int64_t)(INTERVAL / 2 + (seed >> 33) % INTERVAL));
    }
    malloc_logger = hook;
    return 1;
}

int MeloNXHeapSamplerStop(void) {
    if (malloc_logger != hook) return 0;
    malloc_logger = NULL;
    atomic_store(&gActive, 0);
    return 1;
}

static int byLiveBytes(const void *left, const void *right) {
    const MeloNXHeapSamplerStack *a = left, *b = right;
    if (a->liveBytes != b->liveBytes) return a->liveBytes > b->liveBytes ? -1 : 1;
    return a->totalBytes > b->totalBytes ? -1 : a->totalBytes < b->totalBytes ? 1 : 0;
}

int MeloNXHeapSamplerReport(MeloNXHeapSamplerTotals *totals, MeloNXHeapSamplerStack *stacks, int capacity) {
    // Not from the hook: this may allocate.
    MeloNXHeapSamplerStack *copy = malloc(sizeof(gStacks));
    if (copy == NULL) return 0;
    os_unfair_lock_lock(&gLock);
    if (totals != NULL) *totals = gTotals;
    int count = 0;
    for (uint32_t index = 0; index < STACKS; index++) if (gStackHash[index] != 0) copy[count++] = gStacks[index];
    os_unfair_lock_unlock(&gLock);
    qsort(copy, (size_t)count, sizeof(MeloNXHeapSamplerStack), byLiveBytes);
    int written = count < capacity ? count : capacity;
    if (stacks != NULL && written > 0) memcpy(stacks, copy, (size_t)written * sizeof(MeloNXHeapSamplerStack));
    free(copy);
    return written < 0 ? 0 : written;
}
