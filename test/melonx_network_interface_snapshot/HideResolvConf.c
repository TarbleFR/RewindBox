/* Gate shim of adapt_network_interface_snapshot (Linux, LD_PRELOAD): /etc/resolv.conf does not exist for this process, as
 * in the iOS sandbox. Every open and stat entry point the runtime's System.Native may call answers ENOENT for that path
 * and passes any other path to the C library; the opens refused are counted and printed at exit. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

static const char hidden[] = "/etc/resolv.conf";
static volatile long refused;

static int is_hidden(const char *path)
{
    if (path && strcmp(path, hidden) == 0) {
        __sync_fetch_and_add(&refused, 1);
        errno = ENOENT;
        return 1;
    }
    return 0;
}

#define NEXT(name) static __typeof__(name) *next; if (!next) next = (__typeof__(name) *)dlsym(RTLD_NEXT, #name)

int open(const char *path, int flags, ...)
{
    va_list args; va_start(args, flags); mode_t mode = va_arg(args, int); va_end(args);
    if (is_hidden(path)) return -1;
    NEXT(open); return next(path, flags, mode);
}

int open64(const char *path, int flags, ...)
{
    va_list args; va_start(args, flags); mode_t mode = va_arg(args, int); va_end(args);
    if (is_hidden(path)) return -1;
    NEXT(open64); return next(path, flags, mode);
}

int openat(int dir, const char *path, int flags, ...)
{
    va_list args; va_start(args, flags); mode_t mode = va_arg(args, int); va_end(args);
    if (is_hidden(path)) return -1;
    NEXT(openat); return next(dir, path, flags, mode);
}

int openat64(int dir, const char *path, int flags, ...)
{
    va_list args; va_start(args, flags); mode_t mode = va_arg(args, int); va_end(args);
    if (is_hidden(path)) return -1;
    NEXT(openat64); return next(dir, path, flags, mode);
}

int stat(const char *path, struct stat *buffer) { if (is_hidden(path)) return -1; NEXT(stat); return next(path, buffer); }
int stat64(const char *path, struct stat64 *buffer) { if (is_hidden(path)) return -1; NEXT(stat64); return next(path, buffer); }
int lstat(const char *path, struct stat *buffer) { if (is_hidden(path)) return -1; NEXT(lstat); return next(path, buffer); }
int lstat64(const char *path, struct stat64 *buffer) { if (is_hidden(path)) return -1; NEXT(lstat64); return next(path, buffer); }
int fstatat(int dir, const char *path, struct stat *buffer, int flags) { if (is_hidden(path)) return -1; NEXT(fstatat); return next(dir, path, buffer, flags); }
int fstatat64(int dir, const char *path, struct stat64 *buffer, int flags) { if (is_hidden(path)) return -1; NEXT(fstatat64); return next(dir, path, buffer, flags); }
int __xstat(int version, const char *path, struct stat *buffer) { if (is_hidden(path)) return -1; NEXT(__xstat); return next(version, path, buffer); }
int __xstat64(int version, const char *path, struct stat64 *buffer) { if (is_hidden(path)) return -1; NEXT(__xstat64); return next(version, path, buffer); }
int __lxstat(int version, const char *path, struct stat *buffer) { if (is_hidden(path)) return -1; NEXT(__lxstat); return next(version, path, buffer); }
int __lxstat64(int version, const char *path, struct stat64 *buffer) { if (is_hidden(path)) return -1; NEXT(__lxstat64); return next(version, path, buffer); }
int access(const char *path, int mode) { if (is_hidden(path)) return -1; NEXT(access); return next(path, mode); }

struct statx;
int statx(int dir, const char *path, int flags, unsigned int mask, struct statx *buffer)
{
    if (is_hidden(path)) return -1;
    NEXT(statx); return next(dir, path, flags, mask, buffer);
}

__attribute__((destructor)) static void report(void)
{
    fprintf(stderr, "{\"hiddenOpensAndStats\":%ld}\n", refused);
}
