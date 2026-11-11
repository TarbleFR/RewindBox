// RewindBox diagnostic: can S2Arm-rewritten code run from JIT memory?
// See S2ArmProbe.h and docs/s2arm-prototype-2026-11-10.md.
//
// Every step writes "begin" to the journal before it acts, because a step may
// end the process; the last "begin" without a result names the step that did.
#include "S2ArmProbe.h"

#if defined(__APPLE__) && defined(__arm64__)
#include "S2ArmSynthModule.h"
#include <errno.h>
#include <libkern/OSCacheControl.h>
#include <mach/mach.h>
#include <pthread.h>
#include <setjmp.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/ucontext.h>

#define PAGE 0x4000ull
#define UP(x) (((uint64_t)(x) + PAGE - 1) & ~(PAGE - 1))
#define GIB (1ull << 30)
#define TOP39 (1ull << 39)
#define SLOT_ALIGN (2ull << 20)

// Module layout from the slot start (base = slot + LOAD_BIAS), as S2Arm's loader maps it.
#define LB RB_S2ARM_SYNTH_LOAD_BIAS
#define TEXT_LEN UP(RB_S2ARM_SYNTH_TEXT_END + LB)
#define PATCH_AT (((uint64_t)RB_S2ARM_SYNTH_PATCH_OFF + LB) & ~(PAGE - 1))
#define SPAN UP(LB + UP(RB_S2ARM_SYNTH_FILE_SIZE))
#define PATCH_LEN (SPAN - PATCH_AT)
#define CODE_LEN (TEXT_LEN + PATCH_LEN)
#define STUB_BACK 0x100 // the test stub sits this far before the end of a code area

extern void rb_s2arm_probe_gate(void);

static struct {
    rb_s2arm_log_fn log;
    int modes;
    uint8_t *window;
    uint64_t window_size;
    uint8_t *slot;     // fixed mode: slot start inside the window
    uint8_t *code;     // helper region: text then patch, contiguous
    uint8_t *code_rw;  // writable alias of it
    uint8_t *arena;    // arena mode: one helper region of SPAN bytes
    uint8_t *arena_rw; // writable alias of it
    uint8_t *mapped;         // mapped mode: slot whose code pages the process mapped itself
    uint8_t *mapped_text_rw; // writable aliases of its text and patch pages
    uint8_t *mapped_patch_rw;
} g;

static void say(const char *step, const char *status, const char *format, ...) {
    char detail[768];
    va_list arguments;
    va_start(arguments, format);
    vsnprintf(detail, sizeof detail, format, arguments);
    va_end(arguments);
    if (g.log) g.log(step, status, detail);
}

// ---- faults caught around a risky access -------------------------------------
static sigjmp_buf g_jump;
static volatile sig_atomic_t g_guarding;
static const int k_fault_signals[] = {SIGSEGV, SIGBUS, SIGILL};
static struct sigaction g_old_fault[3];

static void chain(const struct sigaction *old, int signal_number, siginfo_t *info, void *context) {
    if ((old->sa_flags & SA_SIGINFO) && old->sa_sigaction) old->sa_sigaction(signal_number, info, context);
    else if (old->sa_handler != SIG_DFL && old->sa_handler != SIG_IGN) old->sa_handler(signal_number);
    else sigaction(signal_number, old, NULL); // default: the instruction faults again
}

static void on_fault(int signal_number, siginfo_t *info, void *context) {
    if (g_guarding) siglongjmp(g_jump, signal_number);
    for (int i = 0; i < 3; i++)
        if (k_fault_signals[i] == signal_number) chain(&g_old_fault[i], signal_number, info, context);
}

// Runs fn(argument); returns 0, or the signal that interrupted it.
static int guarded(void (*fn)(void *), void *argument) {
    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_sigaction = on_fault;
    action.sa_flags = SA_SIGINFO;
    for (int i = 0; i < 3; i++) sigaction(k_fault_signals[i], &action, &g_old_fault[i]);
    int caught = sigsetjmp(g_jump, 1);
    if (!caught) {
        g_guarding = 1;
        fn(argument);
    }
    g_guarding = 0;
    for (int i = 0; i < 3; i++) sigaction(k_fault_signals[i], &g_old_fault[i], NULL);
    return caught;
}

// ---- small helpers -----------------------------------------------------------
static double footprint_mib(void) {
    task_vm_info_data_t info;
    mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
    if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) != KERN_SUCCESS) return -1;
    return (double)info.phys_footprint / (1024.0 * 1024.0);
}

static kern_return_t remap(uint8_t *source, uint64_t length, uint8_t **target, int flags, vm_prot_t *current, vm_prot_t *maximum) {
    vm_address_t address = (vm_address_t)*target;
    kern_return_t result = vm_remap(mach_task_self(), &address, (vm_size_t)length, 0, flags, mach_task_self(),
                                    (vm_address_t)source, FALSE, current, maximum, VM_INHERIT_NONE);
    *target = (uint8_t *)address;
    return result;
}

// A writable alias anywhere, like the MeloNX arena's.
static uint8_t *writable_alias(const char *step, uint8_t *source, uint64_t length) {
    uint8_t *alias = NULL;
    vm_prot_t current = 0, maximum = 0;
    say(step, "begin", "vm_remap of %p, %#llx bytes, then read-write", (void *)source, (unsigned long long)length);
    kern_return_t result = remap(source, length, &alias, VM_FLAGS_ANYWHERE, &current, &maximum);
    if (result != KERN_SUCCESS) {
        say(step, "failed", "vm_remap kr=%d", result);
        return NULL;
    }
    kern_return_t protect = vm_protect(mach_task_self(), (vm_address_t)alias, (vm_size_t)length, FALSE, VM_PROT_READ | VM_PROT_WRITE);
    if (protect != KERN_SUCCESS) {
        say(step, "failed", "alias %p cur=%d max=%d, vm_protect RW kr=%d", (void *)alias, current, maximum, protect);
        return NULL;
    }
    say(step, "passed", "alias %p (remapped cur=%d max=%d)", (void *)alias, current, maximum);
    return alias;
}

struct stub_call { uint8_t *write_at, *run_at; uint32_t value; };
static void stub_body(void *argument) {
    struct stub_call *call = argument;
    const uint32_t code[] = {0x5289A980u, 0xD65F03C0u}; // mov w0, #0x4d4c; ret
    if (call->write_at) memcpy(call->write_at, code, sizeof code);
    sys_icache_invalidate(call->run_at, sizeof code);
    call->value = ((uint32_t (*)(void))call->run_at)();
}
// Writes the stub through write_at (NULL = already there) and runs it at run_at.
static int run_stub(const char *step, uint8_t *write_at, uint8_t *run_at) {
    struct stub_call call = {write_at, run_at, 0};
    say(step, "begin", "write %p, execute %p", (void *)write_at, (void *)run_at);
    int caught = guarded(stub_body, &call);
    int ok = !caught && call.value == 0x4D4C;
    say(step, ok ? "passed" : "failed", "signal=%d value=%#x", caught, call.value);
    return ok;
}

struct poke { uint8_t *at; uint8_t seen; };
static void poke_body(void *argument) {
    struct poke *poke = argument;
    volatile uint8_t *cell = poke->at;
    *cell = 0xA5;
    poke->seen = *cell;
}

// The helper script returns a debugserver error code as if it were an address
// (for instance 0xE08), so only a plausible, page-aligned address is accepted.
static uint8_t *helper_region(const char *step, rb_s2arm_prepare_fn prepare, uint64_t length) {
    say(step, "begin", "command 1, address 0, %#llx bytes", (unsigned long long)length);
    uint64_t address = prepare(0, length);
    if (address < 0x10000 || (address & (PAGE - 1))) {
        say(step, "failed", "the helper returned %#llx, not a region", (unsigned long long)address);
        return NULL;
    }
    say(step, "passed", "%#llx%s", (unsigned long long)address, address + length <= TOP39 ? " (below 2^39)" : " (above 2^39)");
    return (uint8_t *)address;
}

// ---- phase 1: helper attached --------------------------------------------------
static void scan_holes(uint64_t *best_at, uint64_t *best, uint64_t *total, unsigned *regions, uint64_t *above) {
    vm_address_t cursor = 0x100000000ull;
    *best_at = *best = *total = *above = 0;
    *regions = 0;
    for (;;) {
        vm_address_t address = cursor;
        vm_size_t size = 0;
        vm_region_basic_info_data_64_t info;
        mach_msg_type_number_t count = VM_REGION_BASIC_INFO_COUNT_64;
        mach_port_t object = MACH_PORT_NULL;
        kern_return_t result = vm_region_64(mach_task_self(), &address, &size, VM_REGION_BASIC_INFO_64, (vm_region_info_t)&info, &count, &object);
        uint64_t start = result != KERN_SUCCESS || address >= TOP39 ? TOP39 : address;
        if (result == KERN_SUCCESS && address >= TOP39 && !*above) *above = address;
        if (start > cursor) {
            uint64_t hole = start - cursor;
            *total += hole;
            if (hole > *best) { *best = hole; *best_at = cursor; }
        }
        if (start == TOP39) return;
        (*regions)++;
        cursor = address + size;
        if (cursor >= TOP39) return;
    }
}

static int reserve_window(void) {
    uint64_t best_at, best, total, above;
    unsigned regions;
    say("holes", "begin", "scanning 0x100000000..2^39");
    scan_holes(&best_at, &best, &total, &regions, &above);
    say("holes", "passed", "largest=%.2f GiB at %#llx, free=%.2f GiB, regions=%u, firstRegionAbove2^39=%#llx",
        (double)best / GIB, (unsigned long long)best_at, (double)total / GIB, regions, (unsigned long long)above);
    static const unsigned sizes[] = {64, 32, 16, 8, 4, 2, 1};
    char tried[160] = "";
    for (unsigned i = 0; i < sizeof sizes / sizeof *sizes; i++) {
        uint64_t size = sizes[i] * GIB, hint = (best_at + GIB - 1) & ~(GIB - 1);
        if (hint + size > best_at + best) hint = best_at;
        say("window", "begin", "reserve %u GiB near %#llx", sizes[i], (unsigned long long)hint);
        void *address = mmap((void *)hint, size, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
        int error = address == MAP_FAILED ? errno : 0;
        if (address != MAP_FAILED && (uint64_t)address + size <= TOP39) {
            g.window = address;
            g.window_size = size;
            say("window", "passed", "%u GiB at %p (below 2^39)%s", sizes[i], address, tried);
            return 1;
        }
        size_t used = strlen(tried);
        snprintf(tried + used, sizeof tried - used, "; %uGiB:%s", sizes[i], address == MAP_FAILED ? strerror(error) : "above 2^39");
        if (address != MAP_FAILED) munmap(address, size);
    }
    say("window", "failed", "no window below 2^39%s", tried);
    return 0;
}

static void probe_fixed(rb_s2arm_prepare_fn prepare) {
    say("fixedData", "begin", "read-write pages at %p, %#llx bytes", (void *)g.slot, (unsigned long long)SPAN);
    if (mmap(g.slot, SPAN, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0) != g.slot) {
        say("fixedData", "failed", "%s", strerror(errno));
        return;
    }
    say("fixedData", "passed", "slot %p", (void *)g.slot);

    g.code = helper_region("helperRegion", prepare, CODE_LEN);
    if (!g.code) return;
    g.code_rw = writable_alias("helperAlias", g.code, CODE_LEN);
    if (!g.code_rw) return;
    if (!run_stub("helperExecute", g.code_rw + TEXT_LEN - STUB_BACK, g.code + TEXT_LEN - STUB_BACK)) return;

    // The decisive step: the same pages, mapped again at the chosen address.
    struct { const char *name; uint64_t from, to, length; } parts[] = {
        {"text", 0, 0, TEXT_LEN}, {"patch", TEXT_LEN, PATCH_AT, PATCH_LEN}};
    for (int i = 0; i < 2; i++) {
        uint8_t *target = g.slot + parts[i].to;
        vm_prot_t current = 0, maximum = 0;
        say("fixedAlias", "begin", "%s: vm_remap %p onto %p, %#llx bytes", parts[i].name, (void *)(g.code + parts[i].from),
            (void *)target, (unsigned long long)parts[i].length);
        kern_return_t result = remap(g.code + parts[i].from, parts[i].length, &target, VM_FLAGS_FIXED | VM_FLAGS_OVERWRITE, &current, &maximum);
        if (result != KERN_SUCCESS || target != g.slot + parts[i].to) {
            say("fixedAlias", "failed", "%s: kr=%d at %p", parts[i].name, result, (void *)target);
            return;
        }
        kern_return_t protect = KERN_SUCCESS;
        if (!(current & VM_PROT_EXECUTE))
            protect = vm_protect(mach_task_self(), (vm_address_t)target, (vm_size_t)parts[i].length, FALSE, VM_PROT_READ | VM_PROT_EXECUTE);
        say("fixedAlias", protect == KERN_SUCCESS ? "passed" : "failed", "%s: cur=%d max=%d, vm_protect RX kr=%d", parts[i].name, current, maximum, protect);
        if (protect != KERN_SUCCESS) return;
    }
    if (!run_stub("fixedExecuteText", NULL, g.slot + TEXT_LEN - STUB_BACK)) return;
    if (!run_stub("fixedExecutePatch", g.code_rw + CODE_LEN - STUB_BACK, g.slot + SPAN - STUB_BACK)) return;
    g.modes |= RB_S2ARM_MODE_FIXED;
}

static void probe_arena(rb_s2arm_prepare_fn prepare) {
    g.arena = helper_region("arenaRegion", prepare, SPAN);
    if (!g.arena) return;
    g.arena_rw = writable_alias("arenaAlias", g.arena, SPAN);
    if (!g.arena_rw) return;
    if (!run_stub("arenaExecute", g.arena_rw + TEXT_LEN - STUB_BACK, g.arena + TEXT_LEN - STUB_BACK)) return;

    // Data pages in the middle of the executable region: change protection, else replace the pages.
    uint8_t *data = g.arena + TEXT_LEN;
    uint64_t length = PATCH_AT - TEXT_LEN;
    struct poke poke = {data + PAGE, 0};
    say("arenaDataProtect", "begin", "vm_protect read-write on %p, %#llx bytes", (void *)data, (unsigned long long)length);
    kern_return_t protect = vm_protect(mach_task_self(), (vm_address_t)data, (vm_size_t)length, FALSE, VM_PROT_READ | VM_PROT_WRITE);
    int caught = protect == KERN_SUCCESS ? guarded(poke_body, &poke) : 0;
    int writable = protect == KERN_SUCCESS && !caught && poke.seen == 0xA5;
    say("arenaDataProtect", writable ? "passed" : "failed", "kr=%d signal=%d read=%#x", protect, caught, poke.seen);
    if (!writable) {
        say("arenaDataOverlay", "begin", "mmap MAP_FIXED read-write over %p", (void *)data);
        void *mapped = mmap(data, length, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0);
        int error = mapped == MAP_FAILED ? errno : 0;
        poke.seen = 0;
        caught = mapped == data ? guarded(poke_body, &poke) : 0;
        writable = mapped == data && !caught && poke.seen == 0xA5;
        say("arenaDataOverlay", writable ? "passed" : "failed", "errno=%d signal=%d read=%#x", error, caught, poke.seen);
        if (!writable) return;
    }
    // The code on both sides of the data must still run.
    if (!run_stub("arenaExecuteText", NULL, g.arena + TEXT_LEN - STUB_BACK)) return;
    if (!run_stub("arenaExecutePatch", g.arena_rw + SPAN - STUB_BACK, g.arena + SPAN - STUB_BACK)) return;
    g.modes |= RB_S2ARM_MODE_ARENA;
}

// The process maps read-execute pages itself at the chosen address, then hands each range to
// the helper (command 1 with that address). This is what the RPCS3 Core of this app does for
// its JIT arena, reported as observed on the maintainer's iPhone under iOS 27 beta; it runs
// first because it is the one path with device evidence.
static void probe_mapped(rb_s2arm_prepare_fn prepare) {
    uint8_t *slot = g.slot + 2 * SLOT_ALIGN;
    say("mappedData", "begin", "read-write pages at %p, %#llx bytes", (void *)slot, (unsigned long long)SPAN);
    if (mmap(slot, SPAN, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0) != slot) {
        say("mappedData", "failed", "%s", strerror(errno));
        return;
    }
    say("mappedData", "passed", "slot %p", (void *)slot);
    struct { const char *name; uint64_t at, length; uint8_t **alias; } parts[] = {
        {"text", 0, TEXT_LEN, &g.mapped_text_rw}, {"patch", PATCH_AT, PATCH_LEN, &g.mapped_patch_rw}};
    for (int i = 0; i < 2; i++) {
        uint8_t *at = slot + parts[i].at;
        say("mappedCode", "begin", "%s: mmap read-execute at %p, %#llx bytes", parts[i].name, (void *)at, (unsigned long long)parts[i].length);
        if (mmap(at, parts[i].length, PROT_READ | PROT_EXEC, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0) != at) {
            say("mappedCode", "failed", "%s: mmap: %s", parts[i].name, strerror(errno));
            return;
        }
        say("mappedCode", "begin", "%s: command 1 on %p", parts[i].name, (void *)at);
        uint64_t prepared = prepare((uint64_t)at, parts[i].length);
        if (prepared != (uint64_t)at) {
            say("mappedCode", "failed", "%s: the helper returned %#llx", parts[i].name, (unsigned long long)prepared);
            return;
        }
        say("mappedCode", "passed", "%s: prepared at %p", parts[i].name, (void *)at);
        *parts[i].alias = writable_alias("mappedAlias", at, parts[i].length);
        if (!*parts[i].alias) return;
    }
    if (!run_stub("mappedExecuteText", g.mapped_text_rw + TEXT_LEN - STUB_BACK, slot + TEXT_LEN - STUB_BACK)) return;
    if (!run_stub("mappedExecutePatch", g.mapped_patch_rw + PATCH_LEN - STUB_BACK, slot + SPAN - STUB_BACK)) return;
    g.mapped = slot;
    g.modes |= RB_S2ARM_MODE_MAPPED;
}

int rb_s2arm_probe_attached(rb_s2arm_prepare_fn prepare, rb_s2arm_log_fn log, uint32_t flags) {
    if (!prepare || !log || g.log) return -1;
    g.log = log;
    say("phase1", "begin", "module sha256=%s span=%#llx text=%#llx patchAt=%#llx flags=%#x footprint=%.1f MiB", RB_S2ARM_SYNTH_SHA256,
        (unsigned long long)SPAN, (unsigned long long)TEXT_LEN, (unsigned long long)PATCH_AT, flags, footprint_mib());
    // Order: the path with device evidence first, the never-exercised remap last.
    int window = reserve_window();
    if (window) {
        g.slot = (uint8_t *)(((uint64_t)g.window + SLOT_ALIGN + SLOT_ALIGN - 1) & ~(SLOT_ALIGN - 1));
        probe_mapped(prepare);
    }
    probe_arena(prepare);
    if (window) probe_fixed(prepare);
    say("phase1", g.modes ? "passed" : "failed", "modes mapped=%d fixed=%d arena=%d footprint=%.1f MiB", !!(g.modes & RB_S2ARM_MODE_MAPPED),
        !!(g.modes & RB_S2ARM_MODE_FIXED), !!(g.modes & RB_S2ARM_MODE_ARENA), footprint_mib());
    return g.modes;
}

// ---- phase 2: helper detached ---------------------------------------------------
enum { K18, KTLS, KTLR, KGATE, KEYS };
static pthread_key_t g_keys[KEYS];
static uint8_t *g_base;
static int g_svc_hits, g_cntpct_hits, g_unknown_gate;
static uint64_t g_svc_x0;
static volatile sig_atomic_t g_brk_hits;
static struct sigaction g_old_trap;

void rb_s2arm_probe_gate_dispatch(uint64_t ret, uint64_t *regs) {
    for (unsigned i = 0; i < sizeof rb_s2arm_synth_gates / sizeof *rb_s2arm_synth_gates; i++) {
        if ((uint64_t)g_base + rb_s2arm_synth_gates[i].ret != ret) continue;
        if (rb_s2arm_synth_gates[i].kind == 0) {
            g_svc_hits++;
            g_svc_x0 = regs[0];
            regs[0] = 0xD15C000000000000ull | ((uint64_t)rb_s2arm_synth_gates[i].arg << 16) | (regs[0] & 0xFFFF);
        } else {
            g_cntpct_hits++;
            regs[rb_s2arm_synth_gates[i].arg] = 0xC0FFEE00C0FFEE00ull;
        }
        return;
    }
    g_unknown_gate++;
}

// Handles only the module's own brk; anything else goes to the previous handler unchanged.
static void on_trap(int signal_number, siginfo_t *info, void *context) {
    ucontext_t *uc = context;
    uint64_t pc = uc->uc_mcontext->__ss.__pc;
    if (g_base && pc == (uint64_t)g_base + RB_S2ARM_SYNTH_BRK_OFF) {
        g_brk_hits++;
        uc->uc_mcontext->__ss.__pc = pc + 4;
        return;
    }
    chain(&g_old_trap, signal_number, info, context);
}

struct load { uint8_t *start, *text_rw, *patch_rw; const uint8_t *image; };
static void load_body(void *argument) {
    struct load *load = argument;
    memcpy(load->text_rw, load->image, TEXT_LEN);
    memcpy(load->start + TEXT_LEN, load->image + TEXT_LEN, PATCH_AT - TEXT_LEN);
    memcpy(load->patch_rw, load->image + PATCH_AT, PATCH_LEN);
    sys_icache_invalidate(load->start, TEXT_LEN);
    sys_icache_invalidate(load->start + PATCH_AT, PATCH_LEN);
}

struct run { uint8_t *entry; uint64_t out[8]; };
static void run_body(void *argument) {
    struct run *run = argument;
    ((void (*)(uint64_t *))run->entry)(run->out);
}

static int run_module(const char *mode, uint8_t *start, uint8_t *text_rw, uint8_t *patch_rw) {
    char step[48];
    static uint8_t image[SPAN];
    memset(image, 0, sizeof image);
    for (unsigned i = 0; i < sizeof rb_s2arm_synth_ranges / sizeof *rb_s2arm_synth_ranges; i++)
        memcpy(image + LB + rb_s2arm_synth_ranges[i].offset, rb_s2arm_synth_ranges[i].bytes, rb_s2arm_synth_ranges[i].length);
    uint64_t *page = (uint64_t *)(image + LB + RB_S2ARM_SYNTH_KEY_PAGE_OFF);
    const unsigned index[KEYS] = {RB_S2ARM_SYNTH_K18_IDX, RB_S2ARM_SYNTH_KTLS_IDX, RB_S2ARM_SYNTH_KTLR_IDX, RB_S2ARM_SYNTH_KGATE_IDX};
    for (int k = 0; k < KEYS; k++) page[index[k]] = (uint64_t)g_keys[k] * 8;

    snprintf(step, sizeof step, "%sWrite", mode);
    struct load load = {start, text_rw, patch_rw, image};
    say(step, "begin", "code through the writable alias after detach, slot %p", (void *)start);
    int caught = guarded(load_body, &load);
    say(step, caught ? "failed" : "passed", "signal=%d", caught);
    if (caught) return 0;

    g_base = start + LB;
    g_svc_hits = g_cntpct_hits = g_unknown_gate = 0;
    g_svc_x0 = 0;
    g_brk_hits = 0;
    const uint64_t tls_in = 0xAAAA000000000001ull, tlr_in = 0xBBBB000000000002ull;
    pthread_setspecific(g_keys[KTLS], (void *)tls_in);
    pthread_setspecific(g_keys[KTLR], (void *)tlr_in);
    pthread_setspecific(g_keys[K18], NULL);
    pthread_setspecific(g_keys[KGATE], (void *)&rb_s2arm_probe_gate);
    uint64_t slot_base, x18_before, x18_after;
    __asm__ volatile("mrs %0, tpidrro_el0" : "=r"(slot_base));
    snprintf(step, sizeof step, "%sSlots", mode);
    // Rewritten blocks add the key offset to tpidrro_el0 without masking it.
    int slots_ok = !(slot_base & 7) && *(uint64_t *)(slot_base + (uint64_t)g_keys[KTLS] * 8) == tls_in;
    say(step, slots_ok ? "passed" : "failed", "tpidrro_el0=%#llx lowBits=%llu keys=%lu,%lu,%lu,%lu", (unsigned long long)slot_base,
        (unsigned long long)(slot_base & 7), (unsigned long)g_keys[K18], (unsigned long)g_keys[KTLS], (unsigned long)g_keys[KTLR],
        (unsigned long)g_keys[KGATE]);
    if (!slots_ok) return 0;

    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_sigaction = on_trap;
    action.sa_flags = SA_SIGINFO;
    sigaction(SIGTRAP, &action, &g_old_trap);
    struct run run = {g_base + RB_S2ARM_SYNTH_ENTRY, {0}};
    snprintf(step, sizeof step, "%sRun", mode);
    say(step, "begin", "entry %p; contains one brk, one svc gate, one counter gate", (void *)run.entry);
    __asm__ volatile("mov %0, x18" : "=r"(x18_before));
    caught = guarded(run_body, &run);
    __asm__ volatile("mov %0, x18" : "=r"(x18_after));
    sigaction(SIGTRAP, &g_old_trap, NULL);

    struct { const char *name; uint64_t got, want; } checks[] = {
        {"tpidrRead", run.out[0], tls_in},
        {"tpidrroRead", run.out[1], tlr_in},
        {"x18Use", run.out[2], 0x123C},
        {"cntpctGate", run.out[3], 0xC0FFEE00C0FFEE00ull},
        {"ctrConstant", run.out[4], 0x8444C004},
        {"svcGate", run.out[5], 0xD15C000000260077ull},
        {"tpidrReadBack", run.out[6], 0x1234},
        {"slotK18", (uint64_t)pthread_getspecific(g_keys[K18]), 0x1234},
        {"slotKTLS", (uint64_t)pthread_getspecific(g_keys[KTLS]), 0x1234},
        {"slotKTLR", (uint64_t)pthread_getspecific(g_keys[KTLR]), tlr_in},
        {"svcArgument", g_svc_x0, 0x77},
        {"svcHits", (uint64_t)g_svc_hits, 1},
        {"cntpctHits", (uint64_t)g_cntpct_hits, 1},
        {"unknownGate", (uint64_t)g_unknown_gate, 0},
        {"brkHandled", (uint64_t)g_brk_hits, 1},
        {"hostX18Kept", x18_after, x18_before},
    };
    char failed[512] = "";
    unsigned total = sizeof checks / sizeof *checks, good = 0;
    for (unsigned i = 0; i < total; i++) {
        if (checks[i].got == checks[i].want) { good++; continue; }
        size_t used = strlen(failed);
        snprintf(failed + used, sizeof failed - used, " %s=%#llx(want %#llx)", checks[i].name, (unsigned long long)checks[i].got,
                 (unsigned long long)checks[i].want);
    }
    int ok = !caught && good == total;
    say(step, ok ? "passed" : "failed", "signal=%d checks=%u/%u brk=%d svc=%d cntpct=%d%s", caught, good, total, (int)g_brk_hits, g_svc_hits,
        g_cntpct_hits, failed);
    g_base = NULL;
    return ok;
}

// The window is address space only, but the engine started next reserves its own.
static void release_window(void) {
    if (!g.window) return;
    say("windowRelease", "begin", "munmap %p, %.0f GiB", (void *)g.window, (double)g.window_size / GIB);
    int result = munmap(g.window, g.window_size);
    say("windowRelease", result ? "failed" : "passed", "errno=%d", result ? errno : 0);
    g.window = NULL;
    g.slot = NULL;
    g.mapped = NULL;
    g.modes &= ~(RB_S2ARM_MODE_FIXED | RB_S2ARM_MODE_MAPPED);
}

int rb_s2arm_probe_detached(rb_s2arm_log_fn log) {
    if (!log || !g.log) return -1;
    g.log = log;
    say("phase2", "begin", "modes mapped=%d fixed=%d arena=%d footprint=%.1f MiB", !!(g.modes & RB_S2ARM_MODE_MAPPED),
        !!(g.modes & RB_S2ARM_MODE_FIXED), !!(g.modes & RB_S2ARM_MODE_ARENA), footprint_mib());
    if (!g.modes) {
        say("phase2", "failed", "phase 1 found no way to place executable code");
        release_window();
        return -1;
    }
    for (int k = 0; k < KEYS; k++)
        if (!g_keys[k] && (pthread_key_create(&g_keys[k], NULL) || !g_keys[k])) {
            say("phase2", "failed", "pthread_key_create");
            return 1;
        }
    int mapped = -1, fixed = -1, arena = -1;
    if (g.modes & RB_S2ARM_MODE_MAPPED) mapped = run_module("mapped", g.mapped, g.mapped_text_rw, g.mapped_patch_rw);
    if (g.modes & RB_S2ARM_MODE_FIXED) fixed = run_module("fixed", g.slot, g.code_rw, g.code_rw + TEXT_LEN);
    if (g.modes & RB_S2ARM_MODE_ARENA) arena = run_module("arena", g.arena, g.arena_rw, g.arena_rw + PATCH_AT);

    // A new writable alias created after the detach (MeloNX never does this).
    uint8_t *source = g.mapped ? g.mapped : g.code ? g.code : g.arena;
    uint8_t *late = writable_alias("lateAlias", source, PAGE);
    if (late) run_stub("lateAliasExecute", late + PAGE - 2 * STUB_BACK, source + PAGE - 2 * STUB_BACK);

    release_window();
    // Passed = the module ran at a chosen address, or, when no such placement exists, in the arena.
    int ok = mapped == 1 || fixed == 1 || (mapped == -1 && fixed == -1 && arena == 1);
    say("phase2", ok ? "passed" : "failed", "mapped=%d fixed=%d arena=%d (1 passed, 0 failed, -1 not available) footprint=%.1f MiB", mapped,
        fixed, arena, footprint_mib());
    return ok ? 0 : 1;
}

#else

int rb_s2arm_probe_attached(rb_s2arm_prepare_fn prepare, rb_s2arm_log_fn log, uint32_t flags) {
    (void)prepare; (void)log; (void)flags;
    return -1;
}
// The window is address space only, but the engine started next reserves its own.
static void release_window(void) {
    if (!g.window) return;
    say("windowRelease", "begin", "munmap %p, %.0f GiB", (void *)g.window, (double)g.window_size / GIB);
    int result = munmap(g.window, g.window_size);
    say("windowRelease", result ? "failed" : "passed", "errno=%d", result ? errno : 0);
    g.window = NULL;
    g.slot = NULL;
    g.mapped = NULL;
    g.modes &= ~(RB_S2ARM_MODE_FIXED | RB_S2ARM_MODE_MAPPED);
}

int rb_s2arm_probe_detached(rb_s2arm_log_fn log) {
    (void)log;
    return -1;
}

#endif
