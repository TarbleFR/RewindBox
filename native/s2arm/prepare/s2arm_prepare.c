// See s2arm_prepare.h. Built against S2Arm's runtime/rewriter/rewriter.h at the pinned commit.
#include "s2arm_prepare.h"
#include "rewriter.h"

#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>

// The modules the S2Arm runtime loads, the same list as pack/stage_rewrite.sh.
static const char *const k_modules[] = {"main",    "subsdk0", "subsdk1", "subsdk2", "subsdk3", "subsdk4",
                                        "subsdk5", "subsdk6", "subsdk7", "subsdk8", "subsdk9", "sdk"};
enum { MODULES = sizeof k_modules / sizeof *k_modules };

static int fail(char *error, size_t size, int code, const char *format, ...) {
    if (error && size) {
        va_list arguments;
        va_start(arguments, format);
        vsnprintf(error, size, format, arguments);
        va_end(arguments);
    }
    return code;
}

static int join(char *out, size_t size, const char *directory, const char *name, const char *suffix) {
    int length = snprintf(out, size, "%s/%s%s", directory, name, suffix);
    return length > 0 && (size_t)length < size;
}

// 1 = an NSO, 0 = absent, -1 = present but not an NSO, -2 = unreadable.
static int probe_module(const char *path) {
    FILE *file = fopen(path, "rb");
    if (!file) return errno == ENOENT ? 0 : -2;
    char magic[4];
    size_t got = fread(magic, 1, sizeof magic, file);
    fclose(file);
    return got == sizeof magic && !memcmp(magic, "NSO0", 4) ? 1 : -1;
}

static int copy_file(const char *from, const char *to) {
    FILE *in = fopen(from, "rb");
    if (!in) return -1;
    FILE *out = fopen(to, "wb");
    if (!out) {
        fclose(in);
        return -1;
    }
    char block[65536];
    size_t count;
    int bad = 0;
    while ((count = fread(block, 1, sizeof block, in)) > 0)
        if (fwrite(block, 1, count, out) != count) {
            bad = 1;
            break;
        }
    bad |= ferror(in);
    fclose(in);
    bad |= fclose(out) != 0;
    return bad ? -1 : 0;
}

int rb_s2arm_prepare_rewrite(const rb_s2arm_rewrite_request *request, char *error, size_t error_size) {
    if (!request || !request->exefs_dir || !request->output_dir)
        return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "incomplete request");
    char path[MODULES][2048];
    const char *present[MODULES];
    int count = 0;
    for (int i = 0; i < MODULES; i++) {
        if (!join(path[count], sizeof path[count], request->exefs_dir, k_modules[i], ""))
            return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
        int kind = probe_module(path[count]);
        if (kind == -2) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot read %s", k_modules[i]);
        if (kind == -1) return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "%s is not an NSO", k_modules[i]);
        if (kind == 1) present[count++] = k_modules[i];
        else if (i == 0) return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "exefs has no main module");
    }
    char npdm_in[2048], npdm_out[2048];
    if (!join(npdm_in, sizeof npdm_in, request->exefs_dir, "main.npdm", "") ||
        !join(npdm_out, sizeof npdm_out, request->output_dir, "main.npdm", ""))
        return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
    FILE *npdm = fopen(npdm_in, "rb");
    if (!npdm) return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "exefs has no main.npdm");
    fclose(npdm);

    for (int i = 0; i < count; i++) {
        if (request->cancelled && request->cancelled(request->context))
            return fail(error, error_size, RB_S2ARM_PREPARE_CANCELLED, "cancelled before %s", present[i]);
        if (request->progress) request->progress(request->context, present[i], i, count);
        char log_path[2048];
        if (!join(log_path, sizeof log_path, request->output_dir, present[i], ".rewrite.log"))
            return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
        FILE *log = fopen(log_path, "w");
        if (!log) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot write the log of %s", present[i]);
        // The values S2Arm's packer uses: default Apple target, spin gate on, no optional table.
        s2a_rewrite_request rewrite = {.input = path[i], .output_dir = request->output_dir, .module = present[i], .spin = 1};
        int result = s2a_rewrite_files_with_options(&rewrite, NULL, log);
        if (fclose(log)) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot finish the log of %s", present[i]);
        if (result == 3)
            return fail(error, error_size, RB_S2ARM_PREPARE_GAPS, "%s contains code the rewriter cannot rewrite", present[i]);
        if (result) return fail(error, error_size, RB_S2ARM_PREPARE_REWRITER, "the rewriter failed on %s (%d)", present[i], result);
    }
    if (copy_file(npdm_in, npdm_out)) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot copy main.npdm");
    return RB_S2ARM_PREPARE_OK;
}
