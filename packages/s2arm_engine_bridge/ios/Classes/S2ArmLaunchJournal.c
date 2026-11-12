// See S2ArmLaunchJournal.h. Plain C (POSIX only), so that the host test compiles and runs it on any system.
#include "S2ArmLaunchJournal.h"

#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

static pthread_mutex_t gMutex = PTHREAD_MUTEX_INITIALIZER;
static char gPath[1024];
static unsigned long gSeq;

static int make_parents(char *path) {
    for (char *p = path + 1; *p; p++) {
        if (*p != '/') continue;
        *p = 0;
        int bad = mkdir(path, 0700) != 0 && errno != EEXIST;
        *p = '/';
        if (bad) return -1;
    }
    return 0;
}

int s2arm_journal_open(const char *path) {
    if (!path || path[0] != '/' || strlen(path) >= sizeof gPath) return -1;
    pthread_mutex_lock(&gMutex);
    snprintf(gPath, sizeof gPath, "%s", path);
    gSeq = 0;
    int result = make_parents(gPath);
    if (result) gPath[0] = 0;
    pthread_mutex_unlock(&gMutex);
    return result;
}

unsigned long s2arm_journal_lines(void) {
    pthread_mutex_lock(&gMutex);
    unsigned long value = gSeq;
    pthread_mutex_unlock(&gMutex);
    return value;
}

static size_t escape(char *out, size_t room, const char *text) {
    size_t used = 0;
    for (const unsigned char *p = (const unsigned char *)(text ? text : ""); *p && used + 7 < room; p++) {
        if (*p == '"' || *p == '\\') {
            out[used++] = '\\';
            out[used++] = (char)*p;
        } else if (*p < 0x20) {
            used += (size_t)snprintf(out + used, room - used, "\\u%04x", *p);
        } else {
            out[used++] = (char)*p;
        }
    }
    out[used] = 0;
    return used;
}

void s2arm_journal(const char *step, const char *status, const char *fields, ...) {
    char members[1536] = "", stepText[128], statusText[128], stamp[40], line[2048];
    if (fields && *fields) {
        va_list arguments;
        va_start(arguments, fields);
        vsnprintf(members, sizeof members, fields, arguments);
        va_end(arguments);
    }
    escape(stepText, sizeof stepText, step);
    escape(statusText, sizeof statusText, status);
    struct timeval now;
    gettimeofday(&now, NULL);
    struct tm utc;
    time_t seconds = now.tv_sec;
    gmtime_r(&seconds, &utc);
    size_t n = strftime(stamp, sizeof stamp, "%Y-%m-%dT%H:%M:%S", &utc);
    snprintf(stamp + n, sizeof stamp - n, ".%03dZ", (int)(now.tv_usec / 1000));

    pthread_mutex_lock(&gMutex);
    if (!gPath[0]) {
        pthread_mutex_unlock(&gMutex);
        return;
    }
    int length = snprintf(line, sizeof line, "{\"t\":\"%s\",\"pid\":%d,\"seq\":%lu,\"step\":\"%s\",\"status\":\"%s\"%s%s}\n", stamp,
                          (int)getpid(), gSeq + 1, stepText, statusText, members[0] ? "," : "", members);
    if (length <= 0) {
        pthread_mutex_unlock(&gMutex);
        return;
    }
    if ((size_t)length >= sizeof line) {   // keep one valid object per line: drop the members rather than cut them
        length = snprintf(line, sizeof line, "{\"t\":\"%s\",\"pid\":%d,\"seq\":%lu,\"step\":\"%s\",\"status\":\"%s\",\"truncated\":true}\n",
                          stamp, (int)getpid(), gSeq + 1, stepText, statusText);
    }
    int fd = open(gPath, O_WRONLY | O_APPEND | O_CREAT | O_CLOEXEC, 0600);
    if (fd >= 0) {
        ssize_t offset = 0;
        while (offset < length) {
            ssize_t count = write(fd, line + offset, (size_t)(length - offset));
            if (count < 0 && errno == EINTR) continue;
            if (count <= 0) break;
            offset += count;
        }
        fsync(fd);
        close(fd);
        gSeq++;
    }
    pthread_mutex_unlock(&gMutex);
}
