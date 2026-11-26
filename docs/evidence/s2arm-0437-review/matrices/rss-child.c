// Launch from a small native parent so the interpreter's RSS doesn't set the
// child's minimum observed high-water mark before exec on Linux.
#include <stdio.h>
#include <sys/resource.h>
#include <sys/wait.h>
#include <unistd.h>

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    pid_t pid = fork();
    if (pid < 0) return 1;
    if (pid == 0) {
        execv(argv[1], argv + 1);
        _exit(127);
    }
    struct rusage usage;
    int status;
    if (wait4(pid, &status, 0, &usage) < 0 || !WIFEXITED(status) || WEXITSTATUS(status)) return 1;
#ifdef __APPLE__
    const long bytes_per_unit = 1;
#else
    const long bytes_per_unit = 1024;
#endif
    printf("peak_rss_bytes,%lld\n", (long long)usage.ru_maxrss * bytes_per_unit);
    return 0;
}
