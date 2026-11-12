// See s2arm_prepare.h. Built against S2Arm's runtime/rewriter/rewriter.h at the pinned commit.
#include "s2arm_prepare.h"
#include "rewriter.h"
#include "s2arm_addr_need.h"
#include "s2arm_modules.h"
#include "s2arm_nro.h"
#include "s2arm_zbic.h"

#include <dirent.h>
#include <errno.h>
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
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

// ---- progress bar (rb_s2arm_code_request.work) --------------------------------------------
// Every part of the code stage weighs: a module's rewrite its size, the address-need table 5 % of main's, the
// RomFS walks 1 % of the modules each. Inside a rewrite the rewriter's passes take fixed shares (the analysis and
// the generation dominate) and move with the rewriter's own counts. Reports only: nothing here reaches an output.
typedef struct {
    const rb_s2arm_code_request *request;
    double lo, hi;          // the share of the whole code stage this tracker covers
    double total, done;     // weights: every part, the parts finished
    double part;            // weight of the current part
    const char *part_name;
    int attempt;            // the rewriter's attempt the current part is on
    double attempt_base;    // the part's progress when that attempt began (attempt > 1)
    double within;          // last progress inside the part, in [0, 1]
    double last;            // last fraction sent
    const char *last_phase;
    uint64_t last_ns;
} work_t;

static uint64_t work_now_ns(void) {
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    return (uint64_t)now.tv_sec * 1000000000ull + (uint64_t)now.tv_nsec;
}

static void work_send(work_t *w, const char *phase, int attempt, uint64_t done, uint64_t total, double within, int force) {
    if (!w || !w->request->work) return;
    w->within = within < 0 ? 0 : within > 1 ? 1 : within;
    double share = w->total > 0 ? (w->done + w->part * w->within) / w->total : 0;
    double fraction = w->lo + (w->hi - w->lo) * (share > 1 ? 1 : share);
    if (fraction < w->last) fraction = w->last;   // never back, even when a later part adds weight
    uint64_t now = work_now_ns();
    int changed = !w->last_phase || strcmp(w->last_phase, phase);
    if (!force && !changed && now - w->last_ns < 100000000ull) return;
    w->last = fraction;
    w->last_phase = phase;
    w->last_ns = now;
    w->request->work(w->request->context, w->part_name ? w->part_name : "", phase, attempt, done, total, fraction);
}

// The previous part is finished; `name` starts with `weight`.
static void work_part(work_t *w, const char *name, double weight) {
    if (!w) return;
    w->done += w->part;
    w->part = weight;
    w->part_name = name;
    w->attempt = 0;
    w->attempt_base = 0;
    w->within = 0;
    work_send(w, "start", 0, 0, 0, 0, 1);
}

static void work_end(work_t *w) {
    if (!w) return;
    w->done += w->part;
    w->part = 0;
    work_send(w, "end", 0, 0, 0, 1, 1);
}

// Shares of a module's rewrite by pass of the rewriter (S2A_PROGRESS_LOAD .. S2A_PROGRESS_OUTPUTS).
static const double k_pass_start[] = {0, 0.00, 0.03, 0.07, 0.13, 0.20, 0.23, 0.63, 0.88, 0.90, 0.95};
static const double k_pass_width[] = {0, 0.03, 0.04, 0.06, 0.07, 0.03, 0.40, 0.25, 0.02, 0.05, 0.05};
static const char *const k_pass_name[] = {"", "load", "prepass", "boundaries", "scan", "data", "analyze", "generate", "late", "spins", "outputs"};

static void rewriter_progress(void *context, int attempt, int phase, unsigned long long done, unsigned long long total) {
    work_t *w = context;
    if (phase < S2A_PROGRESS_LOAD || phase > S2A_PROGRESS_OUTPUTS) return;
    double within = k_pass_start[phase] + k_pass_width[phase] * (total ? (double)(done > total ? total : done) / (double)total : 0);
    if (attempt != w->attempt) {
        if (attempt > 1) w->attempt_base = w->within;   // a new layout: the rest of the part, from where the bar is
        w->attempt = attempt;
    }
    if (attempt > 1) within = w->attempt_base + (1 - w->attempt_base) * within;
    work_send(w, k_pass_name[phase], attempt, done, total, within, 0);
}

// RomFS walks (NRO search, NRO exports): a count of entries, no total; the part does not move inside.
static void walk_seen(void *context, unsigned long long entries) {
    work_t *w = context;
    work_send(w, "walk", 0, entries, 0, 0, 0);
}

static int rewrite_one(const char *input, const char *module, const char *output_dir, work_t *work, char *error, size_t error_size) {
    char log_path[2048];
    if (!join(log_path, sizeof log_path, output_dir, module, ".rewrite.log"))
        return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
    FILE *log = fopen(log_path, "w");
    if (!log) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot write the log of %s", module);
    // S2Arm's packer values (default Apple target, no optional table), with the spin pass off.
    // - Mario Kart World on an iPhone (IPA 729, 12 Nov): main (42 MB of text) passed every other pass in under 3 s, then
    //   stayed in the spin pass for over 20 minutes without finishing.
    // - The pass is an optimisation, as the rewriter itself says. It puts a gate in the game's spin-wait loops so that a
    //   thread spinning for over 2 s sleeps (runtime S2A_SPIN, thread.c s2a_spin_wait). Virtual cores are off by
    //   default, so nothing else depends on it.
    // - S2Arm's own Android path rewrites with S2A_REWRITE_SPIN=0.
    // - At the pinned commit only the spin code reads the original image (g->orig), which is not copied with spin 0.
    s2a_rewrite_request rewrite = {.input = input, .output_dir = output_dir, .module = module, .spin = 0};
    if (work && work->request->work) s2a_rewrite_set_progress(rewriter_progress, work);
    int result = s2a_rewrite_files_with_options(&rewrite, NULL, log);
    s2a_rewrite_set_progress(NULL, NULL);
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
        int result = rewrite_one(path[i], present[i], request->output_dir, NULL, error, error_size);
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

// ---- ZBIC modules -------------------------------------------------------------
// S2Arm's packer never sees a ZBIC NSO: its unpack step (nx_unpack, or pack/ns2_dump.py for a
// Switch 2 export) rewrites them with uncompressed segments first. When the ExeFS given here
// still holds one, the same normalisation (s2arm_zbic.c) is applied to a copy of its top-level
// entries in <output>/nsoexe, the stage runs on that copy, and the copy is removed at the end.

// 1 = some top-level NSO has the ZBIC flag, 0 = none, -1 = the directory cannot be listed.
static int exefs_has_zbic(const char *exefs) {
    DIR *directory = opendir(exefs);
    if (!directory) return -1;
    struct dirent *entry;
    int found = 0;
    char path[2048];
    while (!found && (entry = readdir(directory))) {
        if (!join(path, sizeof path, exefs, entry->d_name, "")) continue;
        FILE *file = fopen(path, "rb");
        if (!file) continue;
        unsigned char header[16];
        size_t got = fread(header, 1, sizeof header, file);
        fclose(file);
        found = got == sizeof header && !memcmp(header, "NSO0", 4) && (header[12] & 0x80);
    }
    closedir(directory);
    return found;
}

static void remove_nsoexe(const char *directory) {
    DIR *d = opendir(directory);
    if (d) {
        struct dirent *entry;
        char path[2048];
        while ((entry = readdir(d)))
            if (strcmp(entry->d_name, ".") && strcmp(entry->d_name, "..") && join(path, sizeof path, directory, entry->d_name, "")) {
                if (remove(path)) rmdir(path);
            }
        closedir(d);
    }
    rmdir(directory);
}

// The ZBIC decoder polls the cancel callback between blocks: the progress bar uses the polls to report the
// file being decoded (bytes of the files finished, of all files), then asks the request's own callback.
typedef struct {
    const rb_s2arm_code_request *request;
    work_t *work;
    uint64_t done, total;
} zbic_watch_t;

static int zbic_poll(void *context) {
    zbic_watch_t *watch = context;
    work_send(watch->work, "zbic", 0, watch->done, watch->total, watch->total ? (double)watch->done / (double)watch->total : 0, 0);
    return watch->request->cancelled ? watch->request->cancelled(watch->request->context) : 0;
}

// Copies every top-level entry of exefs into work, NSOs through rb_s2arm_nso_normalize_file_ex
// (ZBIC ones decoded, others unchanged; unknown flag bits fail; default 1 GiB cap per module;
// the request's cancel callback polled between files and ZBIC blocks). A subdirectory becomes an
// empty directory so that the later steps see the same entries as in the original ExeFS.
static int normalise_exefs(const rb_s2arm_code_request *request, const char *work, work_t *progress, char *error, size_t error_size) {
    const char *exefs = request->exefs_dir;
    zbic_watch_t watch = {request, progress, 0, 0};
    {   // the bytes to read, for the progress bar
        DIR *listing = opendir(exefs);
        struct dirent *item;
        char path[2048];
        struct stat status;
        while (listing && (item = readdir(listing)))
            if (join(path, sizeof path, exefs, item->d_name, "") && !stat(path, &status) && S_ISREG(status.st_mode))
                watch.total += (uint64_t)status.st_size;
        if (listing) closedir(listing);
    }
    work_part(progress, "zbic", 1);
    rb_s2arm_zbic_options options = {0, zbic_poll, &watch};
    if (mkdir(work, 0700) && !exists(work)) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot create the ZBIC work directory");
    DIR *directory = opendir(exefs);
    if (!directory) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot list the exefs");
    struct dirent *entry;
    int result = RB_S2ARM_PREPARE_OK;
    char from[2048], to[2048];
    while (!result && (entry = readdir(directory))) {
        if (!strcmp(entry->d_name, ".") || !strcmp(entry->d_name, "..")) continue;
        if (request->cancelled && request->cancelled(request->context)) {
            result = fail(error, error_size, RB_S2ARM_PREPARE_CANCELLED, "cancelled while normalising ZBIC modules");
            break;
        }
        if (!join(from, sizeof from, exefs, entry->d_name, "") || !join(to, sizeof to, work, entry->d_name, "")) {
            result = fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
            break;
        }
        struct stat status;
        if (stat(from, &status)) {
            result = fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot read %s", entry->d_name);
            break;
        }
        if (S_ISDIR(status.st_mode)) {
            if (mkdir(to, 0700)) result = fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot create %s", to);
            continue;
        }
        char why[512] = "";
        int code = rb_s2arm_nso_normalize_file_ex(from, to, &options, why, sizeof why);
        if (code == RB_S2ARM_ZBIC_CANCELLED) result = fail(error, error_size, RB_S2ARM_PREPARE_CANCELLED, "cancelled while normalising ZBIC modules");
        else if (code == RB_S2ARM_ZBIC_INVALID) result = fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "%s", why);
        else if (code) result = fail(error, error_size, RB_S2ARM_PREPARE_IO, "%s", why);
        watch.done += (uint64_t)status.st_size;
    }
    closedir(directory);
    if (!result) work_end(progress);
    return result;
}

static int prepare_code(const rb_s2arm_code_request *request, work_t *work, char *error, size_t error_size);

int rb_s2arm_prepare_code(const rb_s2arm_code_request *request, char *error, size_t error_size) {
    if (!request || !request->exefs_dir || !request->output_dir)
        return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "incomplete request");
    // The ZBIC decoding, when there is one, takes the first 5 % of the bar.
    work_t bar = {.request = request, .lo = 0, .hi = 1};
    work_t *progress = request->work ? &bar : NULL;
    if (exefs_has_zbic(request->exefs_dir) != 1) return prepare_code(request, progress, error, error_size);
    char work[2048];
    if (!join(work, sizeof work, request->output_dir, "nsoexe", "")) return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
    bar.hi = 0.05;
    bar.total = 1;   // one part, "zbic", weighing everything inside this 5 %
    int result = normalise_exefs(request, work, progress, error, error_size);
    if (!result) {
        rb_s2arm_code_request normalised = *request;
        normalised.exefs_dir = work;
        work_t rest = {.request = &normalised, .lo = 0.05, .hi = 1, .last = bar.last};
        result = prepare_code(&normalised, progress ? &rest : NULL, error, error_size);
    }
    remove_nsoexe(work);
    return result;
}

static double file_size(const char *path) {
    struct stat status;
    return stat(path, &status) ? 0 : (double)status.st_size;
}

static int prepare_code(const rb_s2arm_code_request *request, work_t *work, char *error, size_t error_size) {
    const char *out = request->output_dir;
    char main_path[2048], npdm[2048], table[2048], nroexe[2048], from[2048], to[2048];
    if (!join(main_path, sizeof main_path, request->exefs_dir, "main", "") || !join(npdm, sizeof npdm, request->exefs_dir, "main.npdm", "") ||
        !join(nroexe, sizeof nroexe, out, "nroexe", ""))
        return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
    int exefs_modules = 0;
    double module_bytes = 0;
    for (int i = 0; i < MODULES; i++)
        if (join(from, sizeof from, request->exefs_dir, k_modules[i], "") && probe_module(from) == 1) {
            exefs_modules++;
            module_bytes += file_size(from);
        }
    // The number of converted NROs is only known after the conversion; the count grows then.
    struct code_steps steps = {request, 0, 2 + exefs_modules + 1};
    int result;
    // The progress bar's weights; the converted NROs are added once known.
    double walk_weight = module_bytes * 0.01, addr_weight = file_size(main_path) * 0.05;
    if (work) work->total = module_bytes + addr_weight + (request->romfs_dir ? 2 * walk_weight : 0);

    if ((result = next_step(&steps, "addr_need", error, error_size))) return result;
    work_part(work, "addr_need", addr_weight);
    if (!join(table, sizeof table, out, "addr_need.tsv", "")) return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
    if ((result = stage_code(rb_s2arm_addr_need(main_path, npdm, table, error, error_size)))) return result;

    int nro_modules = 0;
    if ((result = next_step(&steps, "nro", error, error_size))) return result;
    if (request->romfs_dir) {
        work_part(work, "nro", walk_weight);
        if (mkdir(nroexe, 0700) && !exists(nroexe)) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot create the NRO work directory");
        result = stage_code(rb_s2arm_nro_to_nso_ex(request->romfs_dir, nroexe, work ? walk_seen : NULL, work, error, error_size));
        for (;; nro_modules++) {
            char name[32];
            snprintf(name, sizeof name, "nro%d", nro_modules);
            if (!join(from, sizeof from, nroexe, name, "") || !exists(from)) break;
            if (work) work->total += file_size(from);
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
        if ((result = next_step(&steps, k_modules[i], error, error_size))) {
            remove_nroexe(nroexe, nro_modules);
            return result;
        }
        work_part(work, k_modules[i], file_size(present_path));
        if ((result = rewrite_one(present_path, k_modules[i], modules.output_dir, work, error, error_size))) {
            remove_nroexe(nroexe, nro_modules);
            return result;
        }
    }
    for (int i = 0; i < nro_modules; i++) {
        char name[32];
        snprintf(name, sizeof name, "nro%d", i);
        if (!join(from, sizeof from, nroexe, name, "")) continue;
        if ((result = next_step(&steps, name, error, error_size))) {
            remove_nroexe(nroexe, nro_modules);
            return result;
        }
        // `name` lives until the end of this iteration: the bar reads the part name only while the part runs.
        work_part(work, name, file_size(from));
        if ((result = rewrite_one(from, name, out, work, error, error_size))) {
            remove_nroexe(nroexe, nro_modules);
            return result;
        }
    }
    if (request->romfs_dir) remove_nroexe(nroexe, nro_modules);

    if ((result = next_step(&steps, "tables", error, error_size))) return result;
    work_part(work, "tables", request->romfs_dir ? walk_weight : 0);
    if (!join(to, sizeof to, out, "main.npdm", "") || copy_file(npdm, to)) return fail(error, error_size, RB_S2ARM_PREPARE_IO, "cannot copy main.npdm");
    if (request->romfs_dir) {
        if (!join(table, sizeof table, out, "nro_exports.tsv", "")) return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
        if ((result = stage_code(rb_s2arm_nro_exports_ex(request->romfs_dir, table, work ? walk_seen : NULL, work, error, error_size)))) return result;
    }
    if (!join(table, sizeof table, out, "gpu_drivers.tsv", "")) return fail(error, error_size, RB_S2ARM_PREPARE_INVALID, "path too long");
    if ((result = stage_code(rb_s2arm_gpu_drivers(request->exefs_dir, table, error, error_size)))) return result;
    work_end(work);
    return RB_S2ARM_PREPARE_OK;
}
