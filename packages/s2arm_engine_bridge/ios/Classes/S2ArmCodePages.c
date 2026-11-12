// See S2ArmCodePages.h.
#include "S2ArmCodePages.h"
#include "S2ArmLaunchJournal.h"

#include <errno.h>
#include <pthread.h>
#include <string.h>
#include <time.h>

#if defined(__APPLE__)
#include <mach/mach.h>
#include <mach/vm_map.h>
#include <sys/mman.h>
#endif

static pthread_mutex_t gLock = PTHREAD_MUTEX_INITIALIZER;
static s2arm_code_stats gStats;
static uint8_t *gPool;   // spare pool (universal): R|X pages prepared while attached, handed out in order after the detach

uint64_t s2arm_code_now_ns(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint64_t)now.tv_sec * 1000000000ull + (uint64_t)now.tv_nsec;
}

#if defined(__APPLE__) && defined(__arm64__)
// The universal script's commands (s2arm-universal.js): brk #0xf00d with the command in x16, x0/x1 the arguments, x0 the answer.
__attribute__((naked, noinline)) static uint64_t s2arm_trap_prepare(uint64_t address, uint64_t length) {
    __asm__("mov x16, #1\n" "brk #0xf00d\n" "ret");
}
__attribute__((naked, noinline)) static uint64_t s2arm_trap_probe(uint64_t nonce) {
    __asm__("mov x16, #3\n" "brk #0xf00d\n" "ret");
}
__attribute__((naked, noinline)) static void s2arm_trap_detach(void) {
    __asm__("mov x16, #0\n" "brk #0xf00d\n" "ret");
}
#define S2ARM_HAVE_TRAPS 1
#else
#define S2ARM_HAVE_TRAPS 0
#endif

void s2arm_code_begin(int universal) {
    pthread_mutex_lock(&gLock);
    memset(&gStats, 0, sizeof gStats);
    gStats.mode = universal ? S2ARM_CODE_ATTACHED : S2ARM_CODE_CLASSIC;
    gPool = NULL;
    pthread_mutex_unlock(&gLock);
    s2arm_journal("codePages", "begin", "\"mode\":\"%s\"", universal ? "universal" : "classic");
}

#if defined(__APPLE__)
// Command 1 over [at, at + length) in chunks; each chunk must come back with its own address (the script answers 0 on a
// refusal; MeloNXS2ArmCheckedRegion's rule). Caller holds gLock.
static int issue_prepare(uint8_t *at, uint64_t length) {
#if S2ARM_HAVE_TRAPS
    for (uint64_t done = 0; done < length;) {
        uint64_t chunk = length - done < S2ARM_CODE_COMMAND_CHUNK ? length - done : S2ARM_CODE_COMMAND_CHUNK;
        uint64_t want = (uint64_t)(uintptr_t)(at + done);
        uint64_t got = s2arm_trap_prepare(want, chunk);
        gStats.commands++;
        if (got != want) {
            s2arm_journal("command1", "refused", "\"at\":\"%#llx\",\"length\":%llu,\"answer\":\"%#llx\"", (unsigned long long)want,
                          (unsigned long long)chunk, (unsigned long long)got);
            return -1;
        }
        done += chunk;
    }
    return 0;
#else
    (void)at;
    (void)length;
    return -1;
#endif
}

// A read-write alias anywhere of [source, source + length), as the device probe's writable_alias (802: works after detach).
static void *writable_alias(uint8_t *source, uint64_t length) {
    vm_address_t alias = 0;
    vm_prot_t current = VM_PROT_NONE, maximum = VM_PROT_NONE;
    kern_return_t kr = vm_remap(mach_task_self(), &alias, (vm_size_t)length, 0, VM_FLAGS_ANYWHERE, mach_task_self(), (vm_address_t)source,
                                FALSE, &current, &maximum, VM_INHERIT_NONE);
    if (kr != KERN_SUCCESS) {
        s2arm_journal("alias", "failed", "\"source\":\"%p\",\"length\":%llu,\"kr\":%d", (void *)source, (unsigned long long)length, kr);
        return NULL;
    }
    kr = vm_protect(mach_task_self(), alias, (vm_size_t)length, FALSE, VM_PROT_READ | VM_PROT_WRITE);
    if (kr != KERN_SUCCESS) {
        s2arm_journal("alias", "failed", "\"source\":\"%p\",\"length\":%llu,\"protectKr\":%d,\"cur\":%d,\"max\":%d", (void *)source,
                      (unsigned long long)length, kr, current, maximum);
        vm_deallocate(mach_task_self(), alias, (vm_size_t)length);
        return NULL;
    }
    return (void *)alias;
}

static int map_rx_fixed(uint8_t *at, uint64_t length) {
    void *mapped = mmap(at, (size_t)length, PROT_READ | PROT_EXEC, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
    if (mapped != at) {
        s2arm_journal("mapRX", "failed", "\"at\":\"%p\",\"length\":%llu,\"errno\":%d", (void *)at, (unsigned long long)length, errno);
        return -1;
    }
    return 0;
}

// After the detach: pool pages onto the engine's address (the same physical pages, copy = FALSE), then an alias of them.
static void *from_pool(uint8_t *at, uint64_t length) {
    if (!gPool || gStats.pool_used + length > gStats.pool_bytes) {
        s2arm_journal("pool", "exhausted", "\"at\":\"%p\",\"length\":%llu,\"used\":%llu,\"size\":%llu", (void *)at, (unsigned long long)length,
                      (unsigned long long)gStats.pool_used, (unsigned long long)gStats.pool_bytes);
        return NULL;
    }
    uint8_t *source = gPool + gStats.pool_used;
    vm_address_t target = (vm_address_t)at;
    vm_prot_t current = VM_PROT_NONE, maximum = VM_PROT_NONE;
    kern_return_t kr = vm_remap(mach_task_self(), &target, (vm_size_t)length, 0, VM_FLAGS_FIXED | VM_FLAGS_OVERWRITE, mach_task_self(),
                                (vm_address_t)source, FALSE, &current, &maximum, VM_INHERIT_NONE);
    if (kr != KERN_SUCCESS || target != (vm_address_t)at) {
        s2arm_journal("poolPlace", "failed", "\"at\":\"%p\",\"length\":%llu,\"kr\":%d", (void *)at, (unsigned long long)length, kr);
        return NULL;
    }
    if (!(current & VM_PROT_EXECUTE)) {
        kr = vm_protect(mach_task_self(), target, (vm_size_t)length, FALSE, VM_PROT_READ | VM_PROT_EXECUTE);
        if (kr != KERN_SUCCESS) {
            s2arm_journal("poolPlace", "failed", "\"at\":\"%p\",\"length\":%llu,\"protectKr\":%d,\"cur\":%d,\"max\":%d", (void *)at,
                          (unsigned long long)length, kr, current, maximum);
            return NULL;
        }
    }
    void *alias = writable_alias(source, length);
    if (alias) gStats.pool_used += length;
    return alias;
}
#endif

int s2arm_code_prepare_pool(uint64_t bytes) {
#if defined(__APPLE__)
    bytes = (bytes + S2ARM_CODE_PAGE - 1) & ~(S2ARM_CODE_PAGE - 1);
    if (!bytes) return 0;
    pthread_mutex_lock(&gLock);
    int result = -1;
    if (gStats.mode == S2ARM_CODE_ATTACHED && !gPool) {
        uint64_t started = s2arm_code_now_ns();
        void *pool = mmap(NULL, (size_t)bytes, PROT_READ | PROT_EXEC, MAP_PRIVATE | MAP_ANON, -1, 0);
        if (pool == MAP_FAILED) {
            s2arm_journal("pool", "failed", "\"bytes\":%llu,\"errno\":%d", (unsigned long long)bytes, errno);
        } else if (issue_prepare(pool, bytes)) {
            munmap(pool, (size_t)bytes);
            s2arm_journal("pool", "failed", "\"bytes\":%llu,\"reason\":\"command1\"", (unsigned long long)bytes);
        } else {
            gPool = pool;
            gStats.pool_bytes = bytes;
            result = 0;
            s2arm_journal("pool", "passed", "\"at\":\"%p\",\"bytes\":%llu,\"ms\":%llu", pool, (unsigned long long)bytes,
                          (unsigned long long)((s2arm_code_now_ns() - started) / 1000000ull));
        }
    }
    pthread_mutex_unlock(&gLock);
    return result;
#else
    (void)bytes;
    return -1;
#endif
}

uint64_t s2arm_code_probe(uint64_t nonce) {
#if S2ARM_HAVE_TRAPS
    pthread_mutex_lock(&gLock);
    uint64_t answer = gStats.mode == S2ARM_CODE_ATTACHED ? s2arm_trap_probe(nonce) : 0;
    pthread_mutex_unlock(&gLock);
    return answer;
#else
    (void)nonce;
    return 0;
#endif
}

int s2arm_code_detach(void) {
    int issued = 0;
    pthread_mutex_lock(&gLock);
    if (gStats.mode == S2ARM_CODE_ATTACHED && !gStats.detached) {
#if S2ARM_HAVE_TRAPS
        s2arm_trap_detach();
#endif
        gStats.detached = 1;
        gStats.mode = S2ARM_CODE_DETACHED;
        issued = 1;
    }
    pthread_mutex_unlock(&gLock);
    return issued;
}

void s2arm_code_stats_get(s2arm_code_stats *out) {
    if (!out) return;
    pthread_mutex_lock(&gLock);
    *out = gStats;
    pthread_mutex_unlock(&gLock);
}

void *s2arm_code_prepare(void *address, size_t length, void *context) {
    (void)context;
    uint8_t *at = address;
    uint64_t started = s2arm_code_now_ns();
    if (!at || !length || (((uint64_t)(uintptr_t)at | (uint64_t)length) & (S2ARM_CODE_PAGE - 1))) {
        s2arm_journal("prepareCode", "refused", "\"at\":\"%p\",\"length\":%llu,\"reason\":\"alignment\"", address, (unsigned long long)length);
        return NULL;
    }
    pthread_mutex_lock(&gLock);
    gStats.in_progress++;
    int mode = gStats.mode;
    unsigned call = gStats.served_blocks + gStats.failed_blocks + 1;
    if (call <= 8 || mode == S2ARM_CODE_DETACHED)   // the first calls and every pool call get a line before the risky part
        s2arm_journal("prepareCode", "begin", "\"call\":%u,\"at\":\"%p\",\"length\":%llu,\"mode\":%d", call, address, (unsigned long long)length, mode);
    void *alias = NULL;
#if defined(__APPLE__)
    if (mode == S2ARM_CODE_ATTACHED) {
        if (!map_rx_fixed(at, length) && !issue_prepare(at, length)) alias = writable_alias(at, length);
    } else if (mode == S2ARM_CODE_CLASSIC) {
        if (!map_rx_fixed(at, length)) alias = writable_alias(at, length);
    } else if (mode == S2ARM_CODE_DETACHED) {
        alias = from_pool(at, length);
        if (alias) gStats.after_detach_blocks++;
    }
#endif
    if (alias) {
        gStats.served_blocks++;
        gStats.served_bytes += length;
    } else {
        gStats.failed_blocks++;
    }
    gStats.in_progress--;
    gStats.last_activity_ns = s2arm_code_now_ns();
    unsigned long long ms = (unsigned long long)((gStats.last_activity_ns - started) / 1000000ull);
    pthread_mutex_unlock(&gLock);
    s2arm_journal("prepareCode", alias ? "passed" : "failed", "\"call\":%u,\"at\":\"%p\",\"length\":%llu,\"mode\":%d,\"ms\":%llu", call, address,
                  (unsigned long long)length, mode, ms);
    return alias;
}
