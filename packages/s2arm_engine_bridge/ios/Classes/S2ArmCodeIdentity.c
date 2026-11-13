// See S2ArmCodeIdentity.h.
#include "S2ArmCodeIdentity.h"

#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

// <mach-o/loader.h>, the three things read here: the 64-bit header, a load command's head and LC_UUID.
static const uint32_t kMachMagic64 = 0xfeedfacfu;
enum { kLoadUuid = 0x1b, kHeaderBytes = 32, kCommandHead = 8, kUuidCommandBytes = 24, kMaxCommandBytes = 1 << 20 };

static uint32_t word(const uint8_t *bytes) {   // little-endian, as every Apple platform this runs on
  return (uint32_t)bytes[0] | (uint32_t)bytes[1] << 8 | (uint32_t)bytes[2] << 16 | (uint32_t)bytes[3] << 24;
}

int s2arm_macho_uuid(const void *image, size_t size, char out[S2ARM_UUID_TEXT]) {
  const uint8_t *bytes = image;
  out[0] = 0;
  if (!bytes || size < kHeaderBytes || word(bytes) != kMachMagic64) return 0;
  uint32_t count = word(bytes + 16), commandBytes = word(bytes + 20);
  if (commandBytes > kMaxCommandBytes || (size_t)commandBytes > size - kHeaderBytes) return 0;
  const uint8_t *command = bytes + kHeaderBytes, *end = command + commandBytes;
  for (uint32_t index = 0; index < count; index++) {
    if ((size_t)(end - command) < kCommandHead) return 0;
    uint32_t kind = word(command), length = word(command + 4);
    if (length < kCommandHead || length > (size_t)(end - command)) return 0;   // a command never runs past the commands
    if (kind == kLoadUuid) {
      if (length < kUuidCommandBytes) return 0;
      const uint8_t *u = command + kCommandHead;
      snprintf(out, S2ARM_UUID_TEXT, "%02X%02X%02X%02X-%02X%02X-%02X%02X-%02X%02X-%02X%02X%02X%02X%02X%02X", u[0], u[1], u[2], u[3], u[4], u[5], u[6],
               u[7], u[8], u[9], u[10], u[11], u[12], u[13], u[14], u[15]);
      return 1;
    }
    command += length;
  }
  return 0;
}

int s2arm_macho_uuid_loaded(const void *header, char out[S2ARM_UUID_TEXT]) {
  const uint8_t *bytes = header;
  out[0] = 0;
  if (!bytes || word(bytes) != kMachMagic64) return 0;
  uint32_t commandBytes = word(bytes + 20);
  if (commandBytes > kMaxCommandBytes) return 0;
  return s2arm_macho_uuid(bytes, (size_t)kHeaderBytes + commandBytes, out);   // a loaded image's commands follow its header in memory
}

int s2arm_macho_uuid_file(const char *path, char out[S2ARM_UUID_TEXT]) {
  out[0] = 0;
  if (!path) return 0;
  int file = open(path, O_RDONLY);
  if (file < 0) return 0;
  uint8_t head[kHeaderBytes];
  int found = 0;
  if (read(file, head, sizeof head) == (ssize_t)sizeof head && word(head) == kMachMagic64 && word(head + 20) <= kMaxCommandBytes) {
    size_t size = (size_t)kHeaderBytes + word(head + 20);
    uint8_t *image = malloc(size);
    if (image) {
      memcpy(image, head, sizeof head);
      size_t have = sizeof head;
      while (have < size) {
        ssize_t got = read(file, image + have, size - have);
        if (got <= 0) break;
        have += (size_t)got;
      }
      if (have == size) found = s2arm_macho_uuid(image, size, out);
      free(image);
    }
  }
  close(file);
  return found;
}
