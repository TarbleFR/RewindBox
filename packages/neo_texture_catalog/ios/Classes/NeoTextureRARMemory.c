// SPDX-License-Identifier: GPL-3.0-or-later
#include "NeoTextureRARMemory.h"
#include <stdalign.h>

typedef union Header {
  max_align_t alignment;
  struct { size_t size; NeoTexRARBudget *budget; } allocation;
} Header;
static _Thread_local NeoTexRARBudget *currentBudget;

NeoTexRARBudget *NeoTexRARUseBudget(NeoTexRARBudget *budget) {
  NeoTexRARBudget *previous = currentBudget;
  currentBudget = budget;
  return previous;
}

void *NeoTexRARMalloc(size_t size) {
  NeoTexRARBudget *budget = currentBudget;
  if (!budget) return NULL; // Every decoder operation must enter its reader's budget.
  if (!size) size = 1;
  if (size > SIZE_MAX - sizeof(Header)) { budget->failed = 1; return NULL; }
  const size_t charge = sizeof(Header) + size;
  if (charge > budget->limit || budget->used > budget->limit - charge) {
    budget->failed = 1;
    return NULL;
  }
  Header *header = malloc(sizeof(Header) + size);
  if (!header) { budget->failed = 1; return NULL; }
  header->allocation.size = size;
  header->allocation.budget = budget;
  budget->used += charge;
  if (budget->used > budget->peak) budget->peak = budget->used;
  return header + 1;
}

void NeoTexRARFree(void *pointer) {
  if (!pointer) return;
  Header *header = (Header *)pointer - 1;
  header->allocation.budget->used -= sizeof(Header) + header->allocation.size;
  free(header);
}

void *NeoTexRARCalloc(size_t count, size_t size) {
  if (size && count > SIZE_MAX / size) { if (currentBudget) currentBudget->failed = 1; return NULL; }
  size_t total = count * size;
  void *pointer = NeoTexRARMalloc(total);
  if (pointer) memset(pointer, 0, total);
  return pointer;
}

void *NeoTexRARRealloc(void *pointer, size_t size) {
  if (!pointer) return NeoTexRARMalloc(size);
  if (!size) { NeoTexRARFree(pointer); return NULL; }
  Header *old = (Header *)pointer - 1;
  const size_t oldSize = old->allocation.size;
  // Account for both buffers during growth; libc realloc may transiently
  // retain the old allocation while copying into a new one.
  NeoTexRARBudget *previous = NeoTexRARUseBudget(old->allocation.budget);
  void *replacement = NeoTexRARMalloc(size);
  NeoTexRARUseBudget(previous);
  if (!replacement) return NULL;
  memcpy(replacement, pointer, oldSize < size ? oldSize : size);
  NeoTexRARFree(pointer);
  return replacement;
}

char *NeoTexRARStrdup(const char *text) {
  size_t size = strlen(text) + 1;
  char *copy = NeoTexRARMalloc(size);
  if (copy) memcpy(copy, text, size);
  return copy;
}
