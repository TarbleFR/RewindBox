// Host proof of the S2Arm feasibility prototype (macOS arm64 only).
//
// Loads the synthetic module rewritten by S2Arm's rewriter from plain data
// files, the way S2Arm's own macOS loader does (runtime/src/loader.c, near
// layout): anonymous memory at a fixed address inside a reserved window, the
// key page, read-execute sealing, the gate table. It then runs the module to
// its gates through S2Arm's unmodified gate entry (runtime/src/entry.S), with a
// SIGTRAP handler for the module's brk.
//
// Usage: host_loader <dir with main.patched.bin/fixups.tsv/gates.tsv> <mode>
//   pass       everything installed; exit 0 only if every observed value matches
//   nogate     thread slot KGATE left empty        (must not exit 0)
//   wrongtls   key page: KTLS reads the KTLR slot  (must not exit 0)
//   nokeypage  key page left zeroed                (must not exit 0)
//   nobrk      SIGTRAP handler not installed       (must not exit 0)
// Exit 3 = ran to the end with a value mismatch; 2 = setup error.
#include <errno.h>
#include <inttypes.h>
#include <mach/mach.h>
#include <pthread.h>
#include <signal.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/stat.h>
#include <sys/ucontext.h>
#include <unistd.h>

#define PAGE 0x4000ull
#define UP(x) (((x) + PAGE - 1) & ~(PAGE - 1))
#define WINDOW (1ull << 30)
#define SLOT (2ull << 20)
#define BRK_WORD 0xD4202460u // brk #0x123, see make_synth_nso.py

// Symbols S2Arm's entry.S refers to. Offset 0 = no stack switch (xstack.c absent).
void *g_xs_fn[8192];
uint64_t g_xs_off;
int g_lazy_core;
void s2a_guest_return(void) {}
void sw_thread_returned(void) { abort(); }
void s2a_touch_body(uint64_t address) { (void)address; abort(); }
extern void sw_gate(void);

enum { K18, KTLS, KTLR, KGATE, KEYS };
static const char *const key_name[KEYS] = {"K18", "KTLS", "KTLR", "KGATE"};
struct gate { uint64_t ret, orig; char kind[16]; int arg; };
static struct gate gates[32];
static int gate_count, svc_hits, cntpct_hits, unknown_gate;
static volatile sig_atomic_t brk_hits;
static uint8_t *base;
static uint64_t text_end, svc_x0_in;

static void fail(const char *format, ...) {
    va_list arguments;
    va_start(arguments, format);
    fprintf(stderr, "setup: ");
    vfprintf(stderr, format, arguments);
    fprintf(stderr, "\n");
    va_end(arguments);
    exit(2);
}

// Called by sw_gate with the gate block's return address and the saved x0..x30.
void gate_dispatch(uint64_t ret, uint64_t *regs) {
    for (int i = 0; i < gate_count; i++) {
        if (gates[i].ret != ret) continue;
        if (!strcmp(gates[i].kind, "svc")) {
            svc_hits++;
            svc_x0_in = regs[0];
            regs[0] = 0xD15C000000000000ull | ((uint64_t)gates[i].arg << 16) | (regs[0] & 0xFFFF);
        } else if (!strcmp(gates[i].kind, "cntpct")) {
            cntpct_hits++;
            regs[gates[i].arg] = 0xC0FFEE00C0FFEE00ull;
        } else unknown_gate++;
        return;
    }
    unknown_gate++;
}

static void on_trap(int signal_number, siginfo_t *info, void *context) {
    (void)signal_number; (void)info;
    ucontext_t *uc = context;
    uint64_t pc = uc->uc_mcontext->__ss.__pc;
    if (pc < (uint64_t)base || pc >= (uint64_t)base + text_end || *(const uint32_t *)pc != BRK_WORD) _exit(70);
    brk_hits++;
    uc->uc_mcontext->__ss.__pc = pc + 4;
}

static uint8_t *slurp(const char *directory, const char *name, size_t *size) {
    char path[1024];
    snprintf(path, sizeof path, "%s/%s", directory, name);
    FILE *file = fopen(path, "rb");
    struct stat status;
    if (!file || fstat(fileno(file), &status)) fail("cannot open %s", path);
    uint8_t *bytes = malloc((size_t)status.st_size + 1);
    if (!bytes || fread(bytes, 1, (size_t)status.st_size, file) != (size_t)status.st_size) fail("cannot read %s", path);
    fclose(file);
    bytes[status.st_size] = 0;
    *size = (size_t)status.st_size;
    return bytes;
}

static void seal(void *address, uint64_t length, const char *what) {
    if (mprotect(address, length, PROT_READ | PROT_EXEC)) fail("mprotect %s: %s", what, strerror(errno));
    if (vm_protect(mach_task_self(), (vm_address_t)address, length, TRUE, VM_PROT_READ | VM_PROT_EXECUTE) != KERN_SUCCESS)
        fail("cannot lower the maximum protection of %s", what);
}

int main(int argc, char **argv) {
    if (argc != 3) fail("usage: host_loader <directory> <mode>");
    const char *mode = argv[2];
    int no_gate = !strcmp(mode, "nogate"), wrong_tls = !strcmp(mode, "wrongtls"),
        no_key_page = !strcmp(mode, "nokeypage"), no_brk = !strcmp(mode, "nobrk");
    if (strcmp(mode, "pass") && !no_gate && !wrong_tls && !no_key_page && !no_brk) fail("unknown mode %s", mode);

    // 1. Layout header of fixups.tsv.
    size_t size;
    char *fixups = (char *)slurp(argv[1], "main.fixups.tsv", &size);
    long long patch_off = 0, patch2_off = 0;
    uint64_t load_bias = 0, key_page_off = 0, key_page_size = 0, key_index[KEYS] = {0};
    unsigned seen = 0;
    for (char *line = strtok(fixups, "\n"); line; line = strtok(NULL, "\n")) {
        char key[32];
        unsigned long value;
        if (!strncmp(line, "# BUILD_ID\t", 11)) continue;
        if (!strncmp(line, "# TARGET\t", 9)) fail("not an Apple-target output: %s", line);
        if (sscanf(line, "# %31s %lx", key, &value) != 2) continue;
        const char *text = line + 2 + strlen(key);
        if (!strcmp(key, "PATCH_OFF")) patch_off = strtoll(text, NULL, 16);
        else if (!strcmp(key, "PATCH2_OFF")) patch2_off = strtoll(text, NULL, 16);
        else if (!strcmp(key, "LOAD_BIAS")) load_bias = value;
        else if (!strcmp(key, "KEY_PAGE_OFF")) key_page_off = value;
        else if (!strcmp(key, "KEY_PAGE_SIZE")) key_page_size = value;
        else if (!strcmp(key, "TEXT_END")) text_end = value;
        else if (!strcmp(key, "TRAP_SITES") || !strcmp(key, "FAR_JUMPS")) {
            if (strtoul(text, NULL, 10)) fail("%s is not expected for this module", key);
        } else for (int k = 0; k < KEYS; k++) {
            char want[32];
            snprintf(want, sizeof want, "KEY_%s_IDX", key_name[k]);
            if (!strcmp(key, want)) { key_index[k] = strtoul(strrchr(line, '\t') + 1, NULL, 10); seen |= 1u << k; }
        }
    }
    if (patch_off <= 0 || patch2_off) fail("only the near single-island layout is handled here (PATCH_OFF %lld, PATCH2_OFF %lld)", patch_off, patch2_off);
    if (seen != (1u << KEYS) - 1 || key_page_size != PAGE || (key_page_off + load_bias) % PAGE || load_bias % 0x1000 || load_bias >= PAGE || !text_end)
        fail("incomplete layout header");

    // 2. Reserve a window and map the image at a fixed slot inside it.
    uint8_t *raw = slurp(argv[1], "main.patched.bin", &size);
    uint64_t image = UP(size), span = load_bias + image;
    uint8_t *window = mmap(NULL, WINDOW, PROT_NONE, MAP_PRIVATE | MAP_ANON, -1, 0);
    if (window == MAP_FAILED) fail("cannot reserve the window");
    uint8_t *at = (uint8_t *)(((uint64_t)window + SLOT + SLOT - 1) & ~(SLOT - 1));
    if (mmap(at, span, PROT_READ | PROT_WRITE, MAP_PRIVATE | MAP_ANON | MAP_FIXED, -1, 0) != at) fail("cannot map the module slot");
    base = at + load_bias;
    memcpy(base, raw, size);
    if (key_page_off + key_page_size > image) fail("key page outside the image");

    // 3. Thread-slot keys; the slot of a key is tpidrro_el0 + key * 8 on Apple.
    pthread_key_t keys[KEYS];
    for (int k = 0; k < KEYS; k++) if (pthread_key_create(&keys[k], NULL) || !keys[k]) fail("pthread_key_create");
    uint64_t slot_base;
    __asm__ volatile("mrs %0, tpidrro_el0" : "=r"(slot_base));
    const uint64_t tls_in = 0xAAAA000000000001ull, tlr_in = 0xBBBB000000000002ull;
    pthread_setspecific(keys[KTLS], (void *)tls_in);
    pthread_setspecific(keys[KTLR], (void *)tlr_in);
    pthread_setspecific(keys[K18], NULL);
    pthread_setspecific(keys[KGATE], no_gate ? NULL : (void *)&sw_gate);
    if (*(uint64_t *)(slot_base + (uint64_t)keys[KTLS] * 8) != tls_in) fail("thread-slot layout differs (tpidrro_el0 %#" PRIx64 ")", slot_base);

    // 4. Key page: the four slot offsets, then read-only.
    uint64_t *page = (uint64_t *)(base + key_page_off);
    memset(page, 0, key_page_size);
    if (!no_key_page)
        for (int k = 0; k < KEYS; k++) page[key_index[k]] = (uint64_t)keys[wrong_tls && k == KTLS ? KTLR : k] * 8;
    if (mprotect(page, key_page_size, PROT_READ)) fail("mprotect key page");

    // 5. Seal text and the patch area read-execute.
    seal(at, UP(text_end + load_bias), "text");
    uint64_t patch = (((uint64_t)patch_off + load_bias) & ~(PAGE - 1)) - load_bias;
    if (patch >= image) fail("patch area outside the image");
    seal(base + patch, image - patch, "patch");

    // 6. Gate table.
    char *table = (char *)slurp(argv[1], "main.gates.tsv", &size);
    for (char *line = strtok(table, "\n"); line; line = strtok(NULL, "\n")) {
        unsigned long ret, orig;
        struct gate g;
        if (sscanf(line, "%lx %15s %d %lx", &ret, g.kind, &g.arg, &orig) != 4) continue;
        if (gate_count == 32) fail("too many gates");
        if (ret < patch || ret >= image) fail("gate return %#lx outside the patch area", ret);
        g.ret = (uint64_t)base + ret; g.orig = (uint64_t)base + orig;
        gates[gate_count++] = g;
    }

    // 7. SIGTRAP handler, then run the module function at text offset 0x100.
    if (!no_brk) {
        struct sigaction action;
        memset(&action, 0, sizeof action);
        action.sa_sigaction = on_trap;
        action.sa_flags = SA_SIGINFO;
        if (sigaction(SIGTRAP, &action, NULL)) fail("sigaction");
    }
    uint64_t out[8] = {0};
    printf("mode=%s base=%p load_bias=%#" PRIx64 " text_end=%#" PRIx64 " patch=%#" PRIx64 " image=%#" PRIx64 " gates=%d\n",
           mode, (void *)base, load_bias, text_end, patch, image, gate_count);
    fflush(stdout);
    ((void (*)(uint64_t *))(base + 0x100))(out);

    // 8. Compare what the module observed with what the redirections must give.
    uint64_t k18 = (uint64_t)pthread_getspecific(keys[K18]), tls = (uint64_t)pthread_getspecific(keys[KTLS]),
             tlr = (uint64_t)pthread_getspecific(keys[KTLR]);
    struct { const char *name; uint64_t got, want; } checks[] = {
        {"out0 mrs tpidr_el0 = slot KTLS", out[0], tls_in},
        {"out1 mrs tpidrro_el0 = slot KTLR", out[1], tlr_in},
        {"out2 x18 + 8", out[2], 0x123C},
        {"out3 cntpct from gate", out[3], 0xC0FFEE00C0FFEE00ull},
        {"out4 ctr_el0 constant", out[4], 0x8444C004},
        {"out5 svc result from gate", out[5], 0xD15C000000260077ull},
        {"out6 tpidr_el0 read back", out[6], 0x1234},
        {"slot K18 after", k18, 0x1234},
        {"slot KTLS after", tls, 0x1234},
        {"slot KTLR after", tlr, tlr_in},
        {"svc x0 seen by gate", svc_x0_in, 0x77},
        {"svc gate hits", (uint64_t)svc_hits, 1},
        {"cntpct gate hits", (uint64_t)cntpct_hits, 1},
        {"unknown gate calls", (uint64_t)unknown_gate, 0},
        {"brk handled", (uint64_t)brk_hits, 1},
    };
    int bad = 0;
    for (size_t i = 0; i < sizeof checks / sizeof *checks; i++) {
        int ok = checks[i].got == checks[i].want;
        bad += !ok;
        printf("%s %-34s got=%#" PRIx64 " want=%#" PRIx64 "\n", ok ? "ok  " : "FAIL", checks[i].name, checks[i].got, checks[i].want);
    }
    printf("result=%s\n", bad ? "mismatch" : "pass");
    return bad ? 3 : 0;
}
