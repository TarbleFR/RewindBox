// Test driver for s2arm_prepare (CI only):
//   s2arm_prepare_cli rewrite <exefs> <output> [cancel-after]
//   s2arm_prepare_cli addr-need <main_nso> <npdm> <output>
//   s2arm_prepare_cli gpu-drivers <exefs> <output>
//   s2arm_prepare_cli nro-exports <romfs> <output>
//   s2arm_prepare_cli nro-to-nso <romfs> <output dir>
//   s2arm_prepare_cli nso-normalize <in> <out> [--max-bytes N] [--cancel-after-polls N]
//                                     (nx_unpack --nso-normalize: exit 0, or 1 with a line on stderr; the options test the
//                                      host cap and the cancel callback)
//   s2arm_prepare_cli ns2-dump <export dir> <out dir> [--name N] [--reference] [--max-module-bytes N]
//                                     (exit 0, or 1 with a line on stderr)
//   s2arm_prepare_cli ns2-detect <dir>                  (prints "<PROGRAM ID>\t<folder>", exit 0; 1 when not an export)
//   s2arm_prepare_cli image-pack <root> <output.dylib> [module...]
//   s2arm_prepare_cli caps <root> <s2a_caps.tsv> [<s2a_caps.all.tsv>]
//   s2arm_prepare_cli module-dir <root> <dir> [--images <path>] [--save-identity <id> <name> <version> <content>]
//                                     [--launch-ctx [--ctx-images V] [--ctx-module-dir V] [--ctx-game-data V] [--ctx-docs V]]
//   s2arm_prepare_cli direct-skeleton <root> <chain> <tag> <reason file>
//   s2arm_prepare_cli resource-pack <root> <dir> [--systemdata <dir>] [--link-systemdata] [--applied]
//                                     (all: exit 0, or 1 with "result=<code> <message>" on stderr)
//   s2arm_prepare_cli zbic-batch <manifest>             (one "frame|nso<TAB>input<TAB>expected<TAB>output" per line;
//                                                        writes output on success, prints "<line> ok|err <message>")
#include "s2arm_addr_need.h"
#include "s2arm_caps.h"
#include "s2arm_pack.h"
#include "s2arm_modules.h"
#include "s2arm_ns2_dump.h"
#include "s2arm_nro.h"
#include "s2arm_prepare.h"
#include "s2arm_zbic.h"
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

static long g_polls, g_cancel_after_polls = -1;
static int cancel_after_polls(void *context) {   // stops once the callback has been polled N times
    (void)context;
    return g_cancel_after_polls >= 0 && g_polls++ >= g_cancel_after_polls;
}

static void ns2_note(void *context, const char *line) {
    (void)context;
    printf("%s\n", line);
}

static int zbic_batch(const char *manifest) {
    FILE *list = fopen(manifest, "r");
    if (!list) {
        fprintf(stderr, "cannot read %s\n", manifest);
        return 2;
    }
    char line[8192];
    int number = 0;
    while (fgets(line, sizeof line, list)) {
        number++;
        line[strcspn(line, "\r\n")] = 0;
        char *mode = strtok(line, "\t"), *input = strtok(NULL, "\t"), *expected = strtok(NULL, "\t"), *output = strtok(NULL, "\t");
        if (!mode || !input || !expected || !output) {
            printf("%d err bad manifest line\n", number);
            continue;
        }
        char error[512] = "";
        int result;
        if (!strcmp(mode, "nso")) result = rb_s2arm_nso_normalize_file(input, output, error, sizeof error);
        else {
            FILE *f = fopen(input, "rb");
            uint8_t *data = NULL, *plain = NULL;
            size_t len = 0, want = (size_t)strtoull(expected, NULL, 10);
            result = 2;
            if (f && fseek(f, 0, SEEK_END) == 0) {
                long size = ftell(f);
                rewind(f);
                data = malloc(size > 0 ? (size_t)size : 1);
                plain = malloc(want ? want : 1);
                if (size >= 0 && data && plain && fread(data, 1, (size_t)size, f) == (size_t)size) {
                    len = (size_t)size;
                    result = rb_s2arm_zbic_decompress(data, len, plain, want, error, sizeof error);
                    if (result == 0) {
                        FILE *o = fopen(output, "wb");
                        if (!o || (want && fwrite(plain, 1, want, o) != want)) result = 2;
                        if (o && fclose(o)) result = 2;
                    }
                }
            }
            if (f) fclose(f);
            free(data);
            free(plain);
        }
        printf("%d %s %s\n", number, result ? "err" : "ok", error);
    }
    fclose(list);
    return 0;
}

int main(int argc, char **argv) {
    if (argc >= 2 && !strcmp(argv[1], "nso-normalize")) {
        rb_s2arm_zbic_options options = {0, cancel_after_polls, NULL};
        int bad_usage = argc < 4;
        for (int i = 4; !bad_usage && i < argc; i++) {
            if (!strcmp(argv[i], "--max-bytes") && i + 1 < argc) options.max_output = (size_t)strtoull(argv[++i], NULL, 0);
            else if (!strcmp(argv[i], "--cancel-after-polls") && i + 1 < argc) g_cancel_after_polls = strtol(argv[++i], NULL, 0);
            else bad_usage = 1;
        }
        if (bad_usage) {
            fprintf(stderr, "usage: %s nso-normalize <in> <out> [--max-bytes N] [--cancel-after-polls N]\n", argv[0]);
            return 64;
        }
        char error[512] = "";
        int result = rb_s2arm_nso_normalize_file_ex(argv[2], argv[3], &options, error, sizeof error);
        if (result) fprintf(stderr, "result=%d %s\n", result, error);
        return result ? 1 : 0;
    }
    if (argc == 3 && !strcmp(argv[1], "zbic-batch")) return zbic_batch(argv[2]);
    if (argc >= 4 && !strcmp(argv[1], "image-pack")) {
        char error[1024] = "";
        int result = rb_s2arm_image_pack(argv[2], (const char *const *)(argv + 4), (size_t)(argc - 4), argv[3], error, sizeof error);
        if (result) fprintf(stderr, "result=%d %s\n", result, error);
        return result ? 1 : 0;
    }
    if ((argc == 4 || argc == 5) && !strcmp(argv[1], "caps")) {
        char error[1024] = "";
        int engine = 0;
        int result = rb_s2arm_caps(argv[2], argv[3], argc == 5 ? argv[4] : NULL, &engine, error, sizeof error);
        if (result) fprintf(stderr, "result=%d %s\n", result, error);
        else printf("engine_l1=%d\n", engine);
        return result ? 1 : 0;
    }
    if (argc >= 4 && !strcmp(argv[1], "module-dir")) {
        rb_s2arm_module_request request = {argv[2], argv[3], NULL, NULL, 0, NULL, NULL, NULL, NULL};
        rb_s2arm_save_identity identity = {NULL, NULL, 0, NULL};
        for (int i = 4; i < argc; i++) {
            if (!strcmp(argv[i], "--images") && i + 1 < argc) request.images_path = argv[++i];
            else if (!strcmp(argv[i], "--save-identity") && i + 4 < argc) {
                identity.id = argv[i + 1];
                identity.name = argv[i + 2];
                identity.version = strtoll(argv[i + 3], NULL, 10);
                identity.content_identity = argv[i + 4];
                request.save_identity = &identity;
                i += 4;
            } else if (!strcmp(argv[i], "--launch-ctx")) request.write_launch_ctx = 1;
            else if (!strcmp(argv[i], "--ctx-images") && i + 1 < argc) request.ctx_images = argv[++i];
            else if (!strcmp(argv[i], "--ctx-module-dir") && i + 1 < argc) request.ctx_module_dir = argv[++i];
            else if (!strcmp(argv[i], "--ctx-game-data") && i + 1 < argc) request.ctx_game_data = argv[++i];
            else if (!strcmp(argv[i], "--ctx-docs") && i + 1 < argc) request.ctx_docs = argv[++i];
            else {
                fprintf(stderr, "usage: %s module-dir <root> <dir> [--images P] [--save-identity ID NAME VERSION CONTENT] [--launch-ctx ...]\n", argv[0]);
                return 64;
            }
        }
        char error[1024] = "";
        int result = rb_s2arm_module_dir(&request, error, sizeof error);
        if (result) fprintf(stderr, "result=%d %s\n", result, error);
        return result ? 1 : 0;
    }
    if (argc == 6 && !strcmp(argv[1], "direct-skeleton")) {
        FILE *f = fopen(argv[5], "rb");
        char reason[65536];
        size_t n = f ? fread(reason, 1, sizeof reason - 1, f) : 0;
        if (f) fclose(f);
        reason[n] = 0;
        if (!f) {
            fprintf(stderr, "cannot read %s\n", argv[5]);
            return 1;
        }
        char error[1024] = "";
        int result = rb_s2arm_direct_skeleton(argv[2], argv[3], argv[4], reason, error, sizeof error);
        if (result) fprintf(stderr, "result=%d %s\n", result, error);
        return result ? 1 : 0;
    }
    if (argc >= 4 && !strcmp(argv[1], "resource-pack")) {
        rb_s2arm_resource_request request = {argv[2], argv[3], NULL, 0, 0, NULL, NULL, NULL};
        for (int i = 4; i < argc; i++) {
            if (!strcmp(argv[i], "--systemdata") && i + 1 < argc) request.systemdata_dir = argv[++i];
            else if (!strcmp(argv[i], "--link-systemdata")) request.systemdata_link = 1;
            else if (!strcmp(argv[i], "--applied")) request.write_applied = 1;
            else {
                fprintf(stderr, "usage: %s resource-pack <root> <dir> [--systemdata D] [--link-systemdata] [--applied]\n", argv[0]);
                return 64;
            }
        }
        char error[1024] = "";
        int result = rb_s2arm_resource_pack(&request, error, sizeof error);
        if (result) fprintf(stderr, "result=%d %s\n", result, error);
        return result ? 1 : 0;
    }
    if (argc == 3 && !strcmp(argv[1], "ns2-detect")) {
        char dump[4096], error[512] = "";
        uint64_t program = 0;
        if (rb_s2arm_ns2_detect(argv[2], dump, sizeof dump, &program, error, sizeof error)) return 1;
        printf("%016llX\t%s\n", (unsigned long long)program, dump);
        return 0;
    }
    if (argc >= 4 && !strcmp(argv[1], "ns2-dump")) {
        rb_s2arm_ns2_dump_request request = {argv[2], argv[3], NULL, 0, ns2_note, NULL, NULL, 0};
        for (int i = 4; i < argc; i++) {
            if (!strcmp(argv[i], "--name") && i + 1 < argc) request.name = argv[++i];
            else if (!strcmp(argv[i], "--reference")) request.reference_data = 1;
            else if (!strcmp(argv[i], "--max-module-bytes") && i + 1 < argc) request.max_module_bytes = (size_t)strtoull(argv[++i], NULL, 0);
            else {
                fprintf(stderr, "usage: %s ns2-dump <export dir> <out dir> [--name N] [--reference] [--max-module-bytes N]\n", argv[0]);
                return 64;
            }
        }
        char error[1024] = "";
        int result = rb_s2arm_ns2_dump(&request, error, sizeof error);
        if (result) fprintf(stderr, "result=%d %s\n", result, error);
        return result ? 1 : 0;
    }
    if (argc >= 2 && !strcmp(argv[1], "addr-need")) {
        if (argc != 5) {
            fprintf(stderr, "usage: %s addr-need <main_nso> <npdm> <output>\n", argv[0]);
            return 64;
        }
        char error[256] = "";
        int result = rb_s2arm_addr_need(argv[2], argv[3], argv[4], error, sizeof error);
        printf("result=%d %s\n", result, error);
        return result;
    }
    if (argc >= 2 && !strcmp(argv[1], "gpu-drivers")) {
        if (argc != 4) {
            fprintf(stderr, "usage: %s gpu-drivers <exefs> <output>\n", argv[0]);
            return 64;
        }
        char error[256] = "";
        int result = rb_s2arm_gpu_drivers(argv[2], argv[3], error, sizeof error);
        printf("result=%d %s\n", result, error);
        return result;
    }
    if (argc >= 2 && !strcmp(argv[1], "nro-exports")) {
        if (argc != 4) {
            fprintf(stderr, "usage: %s nro-exports <romfs> <output>\n", argv[0]);
            return 64;
        }
        char error[256] = "";
        int result = rb_s2arm_nro_exports(argv[2], argv[3], error, sizeof error);
        printf("result=%d %s\n", result, error);
        return result;
    }
    if (argc >= 2 && !strcmp(argv[1], "nro-to-nso")) {
        if (argc != 4) {
            fprintf(stderr, "usage: %s nro-to-nso <romfs> <output dir>\n", argv[0]);
            return 64;
        }
        char error[256] = "";
        int result = rb_s2arm_nro_to_nso(argv[2], argv[3], error, sizeof error);
        printf("result=%d %s\n", result, error);
        return result;
    }
    if (argc == 5 && !strcmp(argv[1], "code")) { // code <exefs> <romfs or -> <output>
        char error[256] = "";
        rb_s2arm_code_request request = {argv[2], strcmp(argv[3], "-") ? argv[3] : NULL, argv[4], progress, NULL, NULL};
        int result = rb_s2arm_prepare_code(&request, error, sizeof error);
        printf("result=%d %s\n", result, error);
        return result;
    }
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
