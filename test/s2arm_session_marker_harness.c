// Runs the session marker of engine patch 0018 (runtime/src/sesdiag.c: mark_write, s2a_sesmark_set and s2a_sesmark_rest, as
// the patch leaves them; the test extracts them into rb_sesmark.inc) on a folder given as argv[1].
// The marker is what the engine reads at a start to ask "export diagnostics from last time?": "fg" = the last session
// ended in the foreground without an orderly end. A RewindBox guest parks the session at the in-game Quit, so that
// orderly end never came: the marker stayed "fg" for a game the player had quit. mark_path and the reader below are
// the harness's own (sesdiag.c's are unchanged by the patch and need the engine's headers).
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdatomic.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

enum { S2A_SESMARK_NONE = 0, S2A_SESMARK_FG = 1, S2A_SESMARK_BG = 2 };
#define LOG(...) fprintf(stderr, __VA_ARGS__)
static int mark_path(const char *docs, char *p, size_t n) { return docs && *docs && snprintf(p, n, "%s/s2a_session.mark", docs) < (int)n; }

#include "rb_sesmark.inc"

static int g_failures, g_checks;
#define CHECK(condition, ...) do { g_checks++; if (!(condition)) { g_failures++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

// What the next start would read (s2a_sesmark_prev): no file = an orderly end, "bg" = ended in the background, anything else = "fg"
static int prev(const char *docs) {
    char p[1100], b[8] = {0};
    if (!mark_path(docs, p, sizeof p)) return S2A_SESMARK_NONE;
    int fd = open(p, O_RDONLY);
    if (fd < 0) return S2A_SESMARK_NONE;
    ssize_t r = read(fd, b, sizeof b - 1);
    close(fd);
    return r >= 2 && !memcmp(b, "bg", 2) ? S2A_SESMARK_BG : S2A_SESMARK_FG;
}

static const char *g_docs;
static _Atomic int g_stop;
static void *changes(void *unused) {   // the app going to the background and back, as fast as it can
    (void)unused;
    for (int i = 0; !atomic_load(&g_stop); i++) s2a_sesmark_set(g_docs, i & 1 ? S2A_SESMARK_FG : S2A_SESMARK_BG);
    return NULL;
}

int main(int argc, char **argv) {
    if (argc != 2) return 2;
    const char *docs = g_docs = argv[1];

    // 1. as before the patch (S2Arm's own t_sesdiag): a start writes fg, the background bg, an orderly end deletes it
    CHECK(prev(docs) == S2A_SESMARK_NONE, "no marker: the last session ended in order");
    s2a_sesmark_set(docs, S2A_SESMARK_FG); CHECK(prev(docs) == S2A_SESMARK_FG, "a start writes fg");
    s2a_sesmark_set(docs, S2A_SESMARK_BG); CHECK(prev(docs) == S2A_SESMARK_BG, "the background writes bg");
    s2a_sesmark_set(docs, S2A_SESMARK_FG); CHECK(prev(docs) == S2A_SESMARK_FG, "the foreground writes fg again");
    s2a_sesmark_set(docs, S2A_SESMARK_NONE); CHECK(prev(docs) == S2A_SESMARK_NONE, "an orderly end deletes it");
    s2a_sesmark_set(docs, S2A_SESMARK_NONE); CHECK(prev(docs) == S2A_SESMARK_NONE, "deleting what is not there is not an error");

    // 2. the in-game Quit parks the session: at rest, the marker is gone, and the host app's later changes do not bring it back
    s2a_sesmark_set(docs, S2A_SESMARK_FG);
    s2a_sesmark_rest(docs, 1); CHECK(prev(docs) == S2A_SESMARK_NONE, "parked: the marker is deleted, as at an orderly end");
    s2a_sesmark_set(docs, S2A_SESMARK_BG); CHECK(prev(docs) == S2A_SESMARK_NONE, "parked, the app goes to the background: nothing written");
    s2a_sesmark_set(docs, S2A_SESMARK_FG); CHECK(prev(docs) == S2A_SESMARK_NONE, "parked, the app comes back: nothing written (this was the fg that asked the question for a game the player had quit)");

    // 3. a resume writes the state the app is in, then changes are written again
    s2a_sesmark_rest(docs, 0); CHECK(prev(docs) == S2A_SESMARK_FG, "resumed in the foreground: fg, a crash from here on is asked about");
    s2a_sesmark_rest(docs, 1);                // parked in the foreground
    s2a_sesmark_set(docs, S2A_SESMARK_BG);    // the app goes to the background while the session is parked
    s2a_sesmark_rest(docs, 0); CHECK(prev(docs) == S2A_SESMARK_BG, "resumed after the app went to the background while parked: bg (the change was kept)");
    s2a_sesmark_rest(docs, 1);                // parked in the background
    s2a_sesmark_set(docs, S2A_SESMARK_FG);    // the app comes back while the session is parked
    s2a_sesmark_rest(docs, 0); CHECK(prev(docs) == S2A_SESMARK_FG, "resumed after the app came back while parked: fg");
    s2a_sesmark_set(docs, S2A_SESMARK_BG); CHECK(prev(docs) == S2A_SESMARK_BG, "running again: the background writes bg");
    s2a_sesmark_set(docs, S2A_SESMARK_FG);

    // 4. an orderly end of a parked session still deletes, and stays deleted
    s2a_sesmark_rest(docs, 1);
    s2a_sesmark_set(docs, S2A_SESMARK_NONE); CHECK(prev(docs) == S2A_SESMARK_NONE, "parked then ended in order: no marker");
    s2a_sesmark_rest(docs, 0);
    s2a_sesmark_set(docs, S2A_SESMARK_NONE);

    // 5. a change that arrives while the session parks is not written after the deletion (the lock): many parks against a thread of changes
    pthread_t thread;
    int lost = 0;
    if (pthread_create(&thread, NULL, changes, NULL)) { perror("pthread_create"); return 2; }
    for (int i = 0; i < 2000; i++) {
        s2a_sesmark_rest(docs, 1);
        if (prev(docs) != S2A_SESMARK_NONE) lost++;
        usleep(20);
        if (prev(docs) != S2A_SESMARK_NONE) lost++;
        s2a_sesmark_rest(docs, 0);
    }
    atomic_store(&g_stop, 1);
    pthread_join(thread, NULL);
    CHECK(lost == 0, "2000 parks under changes from another thread: the marker came back %d times while parked", lost);
    s2a_sesmark_set(docs, S2A_SESMARK_NONE);

    printf("%s %d checks, %d failed\n", g_failures ? "FAILED" : "PASSED", g_checks, g_failures);
    return g_failures ? 1 : 0;
}
