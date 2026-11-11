// Test driver for s2arm_prepare (CI only): s2arm_prepare_cli rewrite <exefs> <output> [cancel-after]
#include "s2arm_prepare.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int g_seen, g_cancel_after = -1;
static void progress(void *context, const char *module, int index, int count) {
    (void)context;
    g_seen++;
    printf("module %d/%d %s\n", index + 1, count, module);
}
static int cancelled(void *context) {
    (void)context;
    return g_cancel_after >= 0 && g_seen >= g_cancel_after;
}

int main(int argc, char **argv) {
    if (argc < 4 || strcmp(argv[1], "rewrite")) {
        fprintf(stderr, "usage: %s rewrite <exefs> <output> [cancel-after]\n", argv[0]);
        return 64;
    }
    if (argc > 4) g_cancel_after = atoi(argv[4]);
    char error[256] = "";
    rb_s2arm_rewrite_request request = {argv[2], argv[3], progress, cancelled, NULL};
    int result = rb_s2arm_prepare_rewrite(&request, error, sizeof error);
    printf("result=%d %s\n", result, error);
    return result;
}
