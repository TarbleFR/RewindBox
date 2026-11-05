// Fatal-signal and exit journal of the in-process MeloNX engine (see MeloNXCrashJournal.h).
//
// IPA 662 (MeloNX Core 661) sessions ended with no line in any journal: the Core's journal is written by managed code,
// the stderr capture is drained by a thread of the dying process, and this device writes no crash report. The handlers
// are installed when this framework loads (a constructor), before any engine, so the journal is the last handler of
// each fatal signal: the NativeAOT runtime and Ryujinx's memory-tracking handler are installed after it and pass on
// only the faults they do not handle. Until the journal file is opened (MeloNXCrashJournalInstall), a fatal signal
// writes nothing and takes its usual course. The handler uses write(2), read(2), fcntl(2) and sigaction(2), plus
// dladdr(3) and the thread name, which are not async-signal-safe but run once, when the process is already ending.
#import "MeloNXCrashJournal.h"

#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <signal.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/ucontext.h>
#include <time.h>
#include <unistd.h>
#if __has_include(<ptrauth.h>)
#include <ptrauth.h>
#endif

// Swift reaches these functions through dlsym (MeloNXCrashJournalLink): kept and exported from the pod's framework.
#define MELONX_CRASH_JOURNAL_EXPORT __attribute__((visibility("default"), used))

static int g_fd = -1;
static atomic_int g_installed = 0;
static atomic_int g_handlersInstalled = 0;
static atomic_int g_inHandler = 0;
static atomic_int g_stderrSource = -1;
static const int kSignals[] = { SIGSEGV, SIGBUS, SIGILL, SIGTRAP, SIGABRT, SIGFPE, SIGSYS };
static struct sigaction g_previous[NSIG];

// The journal stays small: a file over this size is started again when the journal is armed.
static const off_t kMaximumBytes = 2 * 1024 * 1024;
// At most this much of the stderr pipe is copied on a fatal signal.
static const size_t kMaximumStderrBytes = 256 * 1024;

static void put_bytes(const char *text, size_t length) {
    if (g_fd < 0 || text == NULL) return;
    while (length > 0) {
        ssize_t written = write(g_fd, text, length);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) return;
        text += written;
        length -= (size_t)written;
    }
}

static void put(const char *text) {
    if (text != NULL) put_bytes(text, strlen(text));
}

static void put_hex(uintptr_t value) {
    char digits[18] = { '0', 'x' };
    for (int i = 0; i < 16; i++) {
        unsigned nibble = (unsigned)((value >> ((15 - i) * 4)) & 0xf);
        digits[2 + i] = (char)(nibble < 10 ? '0' + nibble : 'a' + nibble - 10);
    }
    put_bytes(digits, sizeof digits);
}

static void put_decimal(long long value) {
    char digits[24];
    int index = (int)sizeof digits;
    unsigned long long magnitude = value < 0 ? (unsigned long long)(-(value + 1)) + 1 : (unsigned long long)value;
    do {
        digits[--index] = (char)('0' + magnitude % 10);
        magnitude /= 10;
    } while (magnitude != 0 && index > 1);
    if (value < 0) digits[--index] = '-';
    put_bytes(digits + index, sizeof digits - (size_t)index);
}

static uintptr_t strip_pointer(uintptr_t value) {
#if __has_feature(ptrauth_calls)
    return (uintptr_t)ptrauth_strip((void *)value, ptrauth_key_return_address);
#else
    // An arm64 process still runs arm64e system code: drop pointer-authentication bits above the 47-bit address space.
    return value & 0x00007fffffffffffULL;
#endif
}

// "  #N 0xADDRESS image+0xOFFSET symbol": the image offset is what a symbol map of that image resolves.
static void put_frame(int index, uintptr_t address) {
    put("  #");
    put_decimal(index);
    put(" ");
    put_hex(address);
    Dl_info info;
    if (address != 0 && dladdr((const void *)address, &info) != 0 && info.dli_fname != NULL) {
        const char *name = strrchr(info.dli_fname, '/');
        put(" ");
        put(name != NULL ? name + 1 : info.dli_fname);
        put("+");
        put_hex(address - (uintptr_t)info.dli_fbase);
        if (info.dli_sname != NULL) {
            put(" ");
            put(info.dli_sname);
        }
    }
    put("\n");
}

static void put_thread(void) {
    char name[64] = { 0 };
    pthread_getname_np(pthread_self(), name, sizeof name);
    uint64_t identifier = 0;
    pthread_threadid_np(NULL, &identifier);
    put(" thread ");
    put(name[0] != '\0' ? name : "(unnamed)");
    put(" tid ");
    put_decimal((long long)identifier);
}

static void put_header(const char *what) {
    struct timeval now;
    gettimeofday(&now, NULL);
    put("[MeloNX:crash] ");
    put(what);
    put(" pid ");
    put_decimal(getpid());
    put_thread();
    put(" unix ");
    put_decimal((long long)now.tv_sec);
    put(".");
    put_decimal((long long)(now.tv_usec / 1000));
}

// Frame-pointer walk of the current thread's stack: the raw return addresses are written first (no lock taken), then
// each one is symbolised (dladdr takes dyld's lock, which a fault during a dlopen could hold).
static uintptr_t g_frames[96];

static void put_frames(int first, uintptr_t frame) {
    pthread_t self = pthread_self();
    uintptr_t high = (uintptr_t)pthread_get_stackaddr_np(self);
    uintptr_t low = high - (uintptr_t)pthread_get_stacksize_np(self);
    int count = 0;
    while (count < (int)(sizeof g_frames / sizeof g_frames[0])) {
        if (frame < low || frame + 2 * sizeof(uintptr_t) > high || (frame & (sizeof(uintptr_t) - 1)) != 0) break;
        const uintptr_t *record = (const uintptr_t *)frame;
        uintptr_t next = record[0];
        uintptr_t ret = strip_pointer(record[1]);
        if (ret == 0) break;
        g_frames[count++] = ret;
        if (next <= frame) break;
        frame = next;
    }
    put("[MeloNX:crash] frames");
    for (int i = 0; i < count; i++) {
        put(" ");
        put_hex(g_frames[i]);
    }
    put("\n");
    for (int i = 0; i < count; i++) put_frame(first + i, g_frames[i]);
}

static void drain_stderr(void) {
    int source = atomic_load(&g_stderrSource);
    if (source < 0) return;
    int flags = fcntl(source, F_GETFL);
    if (flags < 0) return;
    // Non-blocking while the dying process copies what is left (the capture thread may read concurrently).
    fcntl(source, F_SETFL, flags | O_NONBLOCK);
    char buffer[4096];
    size_t total = 0;
    int announced = 0;
    for (;;) {
        ssize_t count = read(source, buffer, sizeof buffer);
        if (count < 0 && errno == EINTR) continue;
        if (count <= 0) break;
        if (!announced) {
            put("[MeloNX:crash] stderr still in the pipe:\n");
            announced = 1;
        }
        put_bytes(buffer, (size_t)count);
        total += (size_t)count;
        if (total >= kMaximumStderrBytes) break;
    }
    if (announced) put("\n[MeloNX:crash] end of stderr\n");
    fcntl(source, F_SETFL, flags);
}

static void on_fatal_signal(int signal_number, siginfo_t *info, void *context) {
    (void)context;
    if (g_fd >= 0 && atomic_exchange(&g_inHandler, 1) == 0) {
        put_header("fatal signal");
        put(" signal ");
        put_decimal(signal_number);
        put(" code ");
        put_decimal(info != NULL ? info->si_code : 0);
        put(" address ");
        put_hex(info != NULL ? (uintptr_t)info->si_addr : 0);
        put("\n");
#if defined(__arm64__)
        ucontext_t *ucontext = (ucontext_t *)context;
        if (ucontext != NULL && ucontext->uc_mcontext != NULL) {
#if defined(__darwin_arm_thread_state64_get_pc)
            uintptr_t pc = strip_pointer((uintptr_t)__darwin_arm_thread_state64_get_pc(ucontext->uc_mcontext->__ss));
            uintptr_t lr = strip_pointer((uintptr_t)__darwin_arm_thread_state64_get_lr(ucontext->uc_mcontext->__ss));
            uintptr_t fp = (uintptr_t)__darwin_arm_thread_state64_get_fp(ucontext->uc_mcontext->__ss);
            uintptr_t sp = (uintptr_t)__darwin_arm_thread_state64_get_sp(ucontext->uc_mcontext->__ss);
#else
            uintptr_t pc = strip_pointer((uintptr_t)ucontext->uc_mcontext->__ss.__pc);
            uintptr_t lr = strip_pointer((uintptr_t)ucontext->uc_mcontext->__ss.__lr);
            uintptr_t fp = (uintptr_t)ucontext->uc_mcontext->__ss.__fp;
            uintptr_t sp = (uintptr_t)ucontext->uc_mcontext->__ss.__sp;
#endif
            put("[MeloNX:crash] pc ");
            put_hex(pc);
            put(" lr ");
            put_hex(lr);
            put(" fp ");
            put_hex(fp);
            put(" sp ");
            put_hex(sp);
            put("\n");
            // Raw return addresses first, then symbols (pc and lr last: dladdr may wait on dyld's lock).
            put_frames(2, fp);
            put_frame(0, pc);
            put_frame(1, lr);
        }
#endif
        // The stderr capture thread keeps running: give it time to write what it already read (the runtime's fatal
        // message is written to fd 2 just before abort), then copy what is still in the pipe.
        struct timespec pause = { 0, 300 * 1000 * 1000 };
        nanosleep(&pause, NULL);
        drain_stderr();
        put("[MeloNX:crash] end\n");
    }
    // The previous action (normally the default) takes over: a fault re-executes and ends the process as before; a
    // signal raised on purpose is raised again.
    if (signal_number > 0 && signal_number < NSIG) sigaction(signal_number, &g_previous[signal_number], NULL);
    int hardware = (signal_number == SIGSEGV || signal_number == SIGBUS || signal_number == SIGILL ||
                    signal_number == SIGFPE || signal_number == SIGTRAP) &&
                   info != NULL && info->si_code > 0 && info->si_code != SI_USER && info->si_code != SI_QUEUE;
    if (!hardware) raise(signal_number);
}

static void on_exit_call(void) {
    if (g_fd < 0 || atomic_exchange(&g_inHandler, 1) != 0) return;
    put_header("exit() called");
    put("\n");
    put_frames(0, (uintptr_t)__builtin_frame_address(0));
    put("[MeloNX:crash] end\n");
    atomic_store(&g_inHandler, 0);
}

// Installed when the framework loads, before any engine and its own handlers; the previous actions are restored on
// the fatal path.
__attribute__((constructor)) static void install_handlers(void) {
    if (atomic_exchange(&g_handlersInstalled, 1) != 0) return;
    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_sigaction = on_fatal_signal;
    action.sa_flags = SA_SIGINFO;
    sigemptyset(&action.sa_mask);
    for (size_t i = 0; i < sizeof kSignals / sizeof kSignals[0]; i++) {
        sigaction(kSignals[i], &action, &g_previous[kSignals[i]]);
    }
    atexit(on_exit_call);
}

MELONX_CRASH_JOURNAL_EXPORT void MeloNXCrashJournalInstall(const char *path) {
    if (path == NULL || atomic_exchange(&g_installed, 1) != 0) return;
    int descriptor = open(path, O_WRONLY | O_CREAT | O_APPEND | O_CLOEXEC, 0644);
    if (descriptor < 0) {
        atomic_store(&g_installed, 0);
        return;
    }
    struct stat status;
    if (fstat(descriptor, &status) == 0 && status.st_size > kMaximumBytes) ftruncate(descriptor, 0);
    g_fd = descriptor;
    put_header("journal armed");
    put(atomic_load(&g_handlersInstalled) ? " handlers since load\n" : " handlers missing\n");
}

MELONX_CRASH_JOURNAL_EXPORT void MeloNXCrashJournalSetStderrSource(int fd) {
    atomic_store(&g_stderrSource, fd);
}

MELONX_CRASH_JOURNAL_EXPORT void MeloNXCrashJournalNote(const char *text) {
    if (text == NULL || g_fd < 0) return;
    put_header("note");
    put(" ");
    put(text);
    put("\n");
}
