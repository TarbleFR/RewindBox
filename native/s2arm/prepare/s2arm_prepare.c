// See s2arm_prepare.h. Built against S2Arm's runtime/rewriter/rewriter.h at the pinned commit.
#include "s2arm_prepare.h"
#include "rewriter.h"
#include "s2arm_addr_need.h"
#include "s2arm_modules.h"
#include "s2arm_nro.h"

#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

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

static int rewrite_one(const char *input, const char *module, const char *output_dir, char *error, size_t error_size) {
    char log_path[2048];
    if (!join(log_path, sizeof log_path, output_dir, module, ".rewrite.log"))
        return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
    FILE *log = fopen(log_path, "w");
    if (!log) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot write the log of %s", module);
    // The values S2Arm's packer uses: default Apple target, spin gate on, no optional table.
    s2a_rewrite_request rewrite = {.input = input, .output_dir = output_dir, .module = module, .spin = 1};
    int result = s2a_rewrite_files_with_options(&rewrite, NULL, log);
    if (fclose(log)) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot finish the log of %s", module);
    if (result == 3) return fail(error, error_size, RB_S2ARM_PREPARE_GAPS, "%s contains code the rewriter cannot rewrite", module);
    if (result) return fail(error, error_size, RB_S2ARM_PREPARE_REWRITER, "the rewriter failed on %s (%d)", module, result);
    return RB_S2ARM_PREPARE_OK;
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
        int result = rewrite_one(path[i], present[i], request->output_dir, error, error_size);
        if (result) return result;
    }
    if (copy_file(npdm_in, npdm_out)) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot copy main.npdm");
    return RB_S2ARM_PREPARE_OK;
}

// ---- the whole code stage ------------------------------------------------------
// The sub-stages share the meaning of codes 1 (invalid) and 2 (I/O); their 3 means unsupported.
static int stage_code(int code) {
    return code == 0 ? RB_S2ARM_PREPARE_OK : code == 1 ? RB_S2ARM_PREPARE_INVALID : code == 2 ? RB_S2ARM_PREPARE_IO : RB_S2ARM_PREPARE_UNSUPPORTED;
}

struct code_steps {
    const rb_s2arm_code_request *request;
    int index, count;
};
static int next_step(struct code_steps *steps, const char *name, char *error, size_t error_size) {
    const rb_s2arm_code_request *request = steps->request;
    if (request->cancelled && request->cancelled(request->context))
        return fail(error, error_size, RB_S2ARM_PREPARE_CANCELLED, "cancelled before %s", name);
    if (request->progress) request->progress(request->context, name, steps->index, steps->count);
    steps->index++;
    return RB_S2ARM_PREPARE_OK;
}

static int exists(const char *path) {
    struct stat status;
    return stat(path, &status) == 0;
}

static void remove_nroexe(const char *directory, int modules) {
    char path[2048], name[32];
    for (int i = 0; i < modules; i++) {
        snprintf(name, sizeof name, "nro%d", i);
        if (join(path, sizeof path, directory, name, "")) remove(path);
    }
    if (join(path, sizeof path, directory, "nro_modules.tsv", "")) remove(path);
    rmdir(directory);
}

int rb_s2arm_prepare_code(const rb_s2arm_code_request *request, char *error, size_t error_size) {
    if (!request || !request->exefs_dir || !request->output_dir)
        return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "incomplete request");
    const char *out = request->output_dir;
    char main_path[2048], npdm[2048], table[2048], nroexe[2048], from[2048], to[2048];
    if (!join(main_path, sizeof main_path, request->exefs_dir, "main", "") || !join(npdm, sizeof npdm, request->exefs_dir, "main.npdm", "") ||
        !join(nroexe, sizeof nroexe, out, "nroexe", ""))
        return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
    int exefs_modules = 0;
    for (int i = 0; i < MODULES; i++)
        if (join(from, sizeof from, request->exefs_dir, k_modules[i], "") && probe_module(from) == 1) exefs_modules++;
    // The number of converted NROs is only known after the conversion; the count grows then.
    struct code_steps steps = {request, 0, 2 + exefs_modules + 1};
    int result;

    if ((result = next_step(&steps, "addr_need", error, error_size))) return result;
    if (!join(table, sizeof table, out, "addr_need.tsv", "")) return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
    if ((result = stage_code(rb_s2arm_addr_need(main_path, npdm, table, error, error_size)))) return result;

    int nro_modules = 0;
    if ((result = next_step(&steps, "nro", error, error_size))) return result;
    if (request->romfs_dir) {
        if (mkdir(nroexe, 0700) && !exists(nroexe)) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot create the NRO work directory");
        result = stage_code(rb_s2arm_nro_to_nso(request->romfs_dir, nroexe, error, error_size));
        for (;; nro_modules++) {
            char name[32];
            snprintf(name, sizeof name, "nro%d", nro_modules);
            if (!join(from, sizeof from, nroexe, name, "") || !exists(from)) break;
        }
        if (result) {
            remove_nroexe(nroexe, nro_modules);
            return result;
        }
        if (join(from, sizeof from, nroexe, "nro_modules.tsv", "") && exists(from)) {
            if (!join(to, sizeof to, out, "nro_modules.tsv", "") || rename(from, to)) {
                remove_nroexe(nroexe, nro_modules);
                return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot place nro_modules.tsv");
            }
        }
        steps.count += nro_modules;
    }

    // ExeFS modules first, then the converted NROs, each under its own module name.
    rb_s2arm_rewrite_request modules = {request->exefs_dir, out, NULL, NULL, NULL};
    char present_path[2048];
    for (int i = 0; i < MODULES; i++) {
        if (!join(present_path, sizeof present_path, request->exefs_dir, k_modules[i], "")) continue;
        int kind = probe_module(present_path);
        if (kind == 0 && i != 0) continue;
        if (kind != 1) {
            remove_nroexe(nroexe, nro_modules);
            return fail(error, error_size, kind == -2 ? RB_S2ARM_PREPARE_IO : RB_S2ARM_PREPARE_INVALID,
                        kind == 0 ? "exefs has no main module" : "%s is not a readable NSO", k_modules[i]);
        }
        if ((result = next_step(&steps, k_modules[i], error, error_size)) ||
            (result = rewrite_one(present_path, k_modules[i], modules.output_dir, error, error_size))) {
            remove_nroexe(nroexe, nro_modules);
            return result;
        }
    }
    for (int i = 0; i < nro_modules; i++) {
        char name[32];
        snprintf(name, sizeof name, "nro%d", i);
        if (!join(from, sizeof from, nroexe, name, "")) continue;
        if ((result = next_step(&steps, name, error, error_size)) || (result = rewrite_one(from, name, out, error, error_size))) {
            remove_nroexe(nroexe, nro_modules);
            return result;
        }
    }
    if (request->romfs_dir) remove_nroexe(nroexe, nro_modules);

    if ((result = next_step(&steps, "tables", error, error_size))) return result;
    if (!join(to, sizeof to, out, "main.npdm", "") || copy_file(npdm, to)) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot copy main.npdm");
    if (request->romfs_dir) {
        if (!join(table, sizeof table, out, "nro_exports.tsv", "")) return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
        if ((result = stage_code(rb_s2arm_nro_exports(request->romfs_dir, table, error, error_size)))) return result;
    }
    if (!join(table, sizeof table, out, "gpu_drivers.tsv", "")) return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
    return stage_code(rb_s2arm_gpu_drivers(request->exefs_dir, table, error, error_size));
}
