// What a blocking collection run by a low-class thread costs on Apple's scheduler, and which way of raising the
// thread for its duration works. Built and run on macOS arm64 by the melonx-collection-class workflow (same kernel
// scheduler and QoS interfaces as iOS). Prints one JSON line.
//
// A thread of the utility (or default) class does a fixed amount of CPU work (the stand-in for a collection) while
// more user-interactive threads than cores are busy (the stand-in for the guest's threads, which keep running native
// code during a collection). Measured: the wall time of that work as is, with a QoS override started on the thread
// (by itself, and by another thread), and with the thread's own class raised and restored.
#include <mach/mach.h>
#include <pthread.h>
#include <pthread/qos.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/sysctl.h>
#include <time.h>
#include <unistd.h>

static atomic_int stop_load;

static uint64_t now_ns(clockid_t clock) { return clock_gettime_nsec_np(clock); }

static void priorities(int *base, int *current)
{
    thread_extended_info_data_t info;
    mach_msg_type_number_t count = THREAD_EXTENDED_INFO_COUNT;
    mach_port_t self = mach_thread_self();
    memset(&info, 0, sizeof info);
    thread_info(self, THREAD_EXTENDED_INFO, (thread_info_t)&info, &count);
    mach_port_deallocate(mach_task_self(), self);
    *base = info.pth_priority;
    *current = info.pth_curpri;
}

static void *load(void *unused)
{
    pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
    volatile uint64_t x = 1;
    while (!atomic_load(&stop_load)) x = x * 6364136223846793005ULL + 1442695040888963407ULL;
    return NULL;
}

// Spins until this thread has used cpu_ms of CPU time; returns the wall time it took, in milliseconds.
static double work(double cpu_ms)
{
    uint64_t wall = now_ns(CLOCK_UPTIME_RAW), cpu = now_ns(CLOCK_THREAD_CPUTIME_ID), target = (uint64_t)(cpu_ms * 1e6);
    volatile uint64_t x = 1;
    while (now_ns(CLOCK_THREAD_CPUTIME_ID) - cpu < target)
        for (int i = 0; i < 2000; i++) x = x * 6364136223846793005ULL + 1442695040888963407ULL;
    return (now_ns(CLOCK_UPTIME_RAW) - wall) / 1e6;
}

typedef struct { qos_class_t qos; const char *name; char out[1024]; } subject;
typedef struct { pthread_t target; pthread_override_t token; } helper;

static void *start_override(void *argument)
{
    helper *h = argument;
    h->token = pthread_override_qos_class_start_np(h->target, QOS_CLASS_USER_INTERACTIVE, 0);
    return NULL;
}

static void *end_override(void *argument)
{
    helper *h = argument;
    pthread_override_qos_class_end_np(h->token);
    return NULL;
}

static void *subject_thread(void *argument)
{
    subject *s = argument;
    const double cpu_ms = 20.0;
    int base[6], current[6];
    double wall[5];
    pthread_set_qos_class_self_np(s->qos, 0);
    usleep(20000);

    priorities(&base[0], &current[0]);
    wall[0] = work(cpu_ms); // as is

    pthread_override_t token = pthread_override_qos_class_start_np(pthread_self(), QOS_CLASS_USER_INTERACTIVE, 0);
    priorities(&base[1], &current[1]);
    wall[1] = work(cpu_ms); // override started by the thread itself
    pthread_override_qos_class_end_np(token);
    priorities(&base[2], &current[2]);

    helper h = { pthread_self(), NULL };
    pthread_t other;
    pthread_create(&other, NULL, start_override, &h);
    pthread_join(other, NULL);
    priorities(&base[3], &current[3]);
    wall[2] = work(cpu_ms); // override started by another thread
    pthread_create(&other, NULL, end_override, &h); // and ended by another thread
    pthread_join(other, NULL);

    qos_class_t own = qos_class_self();
    int raised = pthread_set_qos_class_self_np(QOS_CLASS_USER_INTERACTIVE, 0);
    priorities(&base[4], &current[4]);
    wall[3] = work(cpu_ms); // the thread's own class raised
    int restored = pthread_set_qos_class_self_np(own, 0);
    priorities(&base[5], &current[5]);
    wall[4] = work(cpu_ms); // as is again, after the restore

    snprintf(s->out, sizeof s->out,
             "{\"class\":\"%s\",\"cpuMs\":%.1f,"
             "\"asIs\":{\"base\":%d,\"current\":%d,\"wallMs\":%.1f},"
             "\"overrideBySelf\":{\"base\":%d,\"current\":%d,\"wallMs\":%.1f,\"token\":%d,\"currentAfterEnd\":%d},"
             "\"overrideByOther\":{\"base\":%d,\"current\":%d,\"wallMs\":%.1f,\"token\":%d},"
             "\"ownClassRaised\":{\"status\":%d,\"base\":%d,\"current\":%d,\"wallMs\":%.1f},"
             "\"restored\":{\"status\":%d,\"sameClass\":%d,\"base\":%d,\"current\":%d,\"wallMs\":%.1f}}",
             s->name, cpu_ms, base[0], current[0], wall[0], base[1], current[1], wall[1], token != NULL, current[2],
             base[3], current[3], wall[2], h.token != NULL, raised, base[4], current[4], wall[3],
             restored, qos_class_self() == own, base[5], current[5], wall[4]);
    return NULL;
}

int main(void)
{
    int cores = 0;
    size_t size = sizeof cores;
    sysctlbyname("hw.ncpu", &cores, &size, NULL, 0);
    int loads = cores + 2;
    pthread_t *threads = calloc((size_t)loads, sizeof *threads);
    for (int i = 0; i < loads; i++) pthread_create(&threads[i], NULL, load, NULL);
    usleep(200000);

    subject subjects[] = { { QOS_CLASS_UTILITY, "utility", "" }, { QOS_CLASS_DEFAULT, "default", "" },
                           { QOS_CLASS_BACKGROUND, "background", "" }, { QOS_CLASS_USER_INTERACTIVE, "userInteractive", "" } };
    int count = (int)(sizeof subjects / sizeof subjects[0]);
    printf("{\"cores\":%d,\"busyUserInteractiveThreads\":%d,\"subjects\":[", cores, loads);
    for (int i = 0; i < count; i++)
    {
        pthread_t thread;
        pthread_create(&thread, NULL, subject_thread, &subjects[i]);
        pthread_join(thread, NULL);
        printf("%s%s", i ? "," : "", subjects[i].out);
    }
    printf("]}\n");
    atomic_store(&stop_load, 1);
    for (int i = 0; i < loads; i++) pthread_join(threads[i], NULL);
    return 0;
}
