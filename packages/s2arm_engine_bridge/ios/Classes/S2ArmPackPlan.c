// See S2ArmPackPlan.h.
#include "S2ArmPackPlan.h"

#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define PLAN_PAGE 0x4000ull
#define PLAN_MAX_MODULES 512u            // rb_s2arm_image_pack refuses more
#define PLAN_MAX_COMMANDS (1u << 20)     // sizeofcmds bound when reading the load commands

static int plan_fail(char *error, size_t size, const char *format, ...) __attribute__((format(printf, 3, 4)));
static int plan_fail(char *error, size_t size, const char *format, ...) {
    if (error && size) {
        va_list arguments;
        va_start(arguments, format);
        vsnprintf(error, size, format, arguments);
        va_end(arguments);
    }
    return -1;
}

static uint32_t le32(const uint8_t *p) { return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24; }
static uint64_t le64(const uint8_t *p) { return (uint64_t)le32(p) | (uint64_t)le32(p + 4) << 32; }

static int read_at(int fd, void *buffer, size_t length, uint64_t offset) {
    uint8_t *p = buffer;
    while (length) {
        ssize_t n = pread(fd, p, length, (off_t)offset);
        if (n < 0 && errno == EINTR) continue;
        if (n <= 0) return -1;
        p += n;
        length -= (size_t)n;
        offset += (uint64_t)n;
    }
    return 0;
}

int s2arm_pack_plan_is_boot_module(const char *name) {
    if (!name) return 0;
    if (!strcmp(name, "main") || !strcmp(name, "sdk")) return 1;
    if (strncmp(name, "subsdk", 6) || !name[6]) return 0;
    for (const char *p = name + 6; *p; p++)
        if (*p < '0' || *p > '9') return 0;
    return 1;
}

int s2arm_pack_plan_boot_served(const s2arm_pack_plan *plan, unsigned served_blocks, uint64_t served_bytes) {
    if (!plan || !plan->boot_code_blocks || !plan->boot_code_bytes) return 0;
    return served_blocks >= plan->boot_code_blocks && served_bytes >= plan->boot_code_bytes;
}

int s2arm_pack_plan_read(const char *path, s2arm_pack_plan *plan, char *error, size_t error_size) {
    if (error && error_size) error[0] = 0;
    if (!path || !plan) return plan_fail(error, error_size, "incomplete request");
    memset(plan, 0, sizeof *plan);
    int fd = open(path, O_RDONLY | O_CLOEXEC);
    if (fd < 0) return plan_fail(error, error_size, "image pack not readable (errno %d)", errno);
    struct stat info;
    uint8_t header[32];
    int result = -1;
    uint8_t *commands = NULL, *index = NULL;
    if (fstat(fd, &info) || read_at(fd, header, sizeof header, 0)) {
        plan_fail(error, error_size, "image pack header not readable");
        goto done;
    }
    uint64_t file_size = (uint64_t)info.st_size;
    if (le32(header) != 0xfeedfacfu) {
        plan_fail(error, error_size, "image pack is not a 64-bit Mach-O");
        goto done;
    }
    uint32_t ncmds = le32(header + 16), sizeofcmds = le32(header + 20);
    if (!ncmds || sizeofcmds > PLAN_MAX_COMMANDS || 32ull + sizeofcmds > file_size) {
        plan_fail(error, error_size, "image pack load commands out of range");
        goto done;
    }
    commands = malloc(sizeofcmds);
    if (!commands || read_at(fd, commands, sizeofcmds, 32)) {
        plan_fail(error, error_size, "image pack load commands not readable");
        goto done;
    }
    uint64_t index_offset = 0, index_size = 0;
    int found = 0;
    for (uint32_t i = 0, at = 0; i < ncmds; i++) {
        if (at + 8ull > sizeofcmds) break;
        uint32_t cmd = le32(commands + at), cmdsize = le32(commands + at + 4);
        if (cmdsize < 8 || at + (uint64_t)cmdsize > sizeofcmds) break;
        if (cmd == 0x19 && cmdsize >= 72 && !strncmp((const char *)commands + at + 8, "__TEXT", 16)) {   // LC_SEGMENT_64
            uint32_t nsects = le32(commands + at + 64);
            for (uint32_t s = 0; s < nsects; s++) {
                uint64_t sect = (uint64_t)at + 72 + (uint64_t)s * 80;
                if (sect + 80 > (uint64_t)at + cmdsize) break;
                if (!strncmp((const char *)commands + sect, "__swidx", 16)) {
                    index_size = le64(commands + sect + 40);
                    index_offset = le32(commands + sect + 48);
                    found = 1;
                }
            }
        }
        at += cmdsize;
    }
    if (!found) {
        plan_fail(error, error_size, "image pack has no __TEXT,__swidx section");
        goto done;
    }
    if (index_size < 16 || index_offset + index_size > file_size || index_size > 16ull + PLAN_MAX_MODULES * 88ull) {
        plan_fail(error, error_size, "image pack index out of range (%llu bytes)", (unsigned long long)index_size);
        goto done;
    }
    index = malloc((size_t)index_size);
    if (!index || read_at(fd, index, (size_t)index_size, index_offset)) {
        plan_fail(error, error_size, "image pack index not readable");
        goto done;
    }
    uint32_t count = le32(index + 8), entry = le32(index + 12);
    if (memcmp(index, "S2AEMB01", 8) || entry != 88 || !count || count > PLAN_MAX_MODULES || 16ull + (uint64_t)count * 88 > index_size) {
        plan_fail(error, error_size, "image pack index is not S2AEMB01 with 88-byte entries");
        goto done;
    }
    for (uint32_t k = 0; k < count; k++) {
        const uint8_t *e = index + 16 + (size_t)k * 88;
        char name[25];
        memcpy(name, e, 24);
        name[24] = 0;
        int boot = s2arm_pack_plan_is_boot_module(name);
        plan->modules++;
        if (boot) plan->boot_modules++;
        static const int code_kinds[3] = {0, 2, 3};   // x0, x1, x2
        for (int c = 0; c < 3; c++) {
            uint64_t length = le64(e + 24 + (size_t)code_kinds[c] * 16 + 8);
            if (!length) continue;
            if (length % PLAN_PAGE || length > file_size) {
                plan_fail(error, error_size, "image pack entry %u has a code block of 0x%llx bytes", k, (unsigned long long)length);
                goto done;
            }
            if (boot) {
                plan->boot_code_blocks++;
                plan->boot_code_bytes += length;
            } else {
                plan->later_code_blocks++;
                plan->later_code_bytes += length;
            }
            if (length > plan->largest_code_block) plan->largest_code_block = length;
        }
    }
    result = 0;
done:
    free(commands);
    free(index);
    close(fd);
    return result;
}
