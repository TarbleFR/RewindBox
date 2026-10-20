// SPDX-License-Identifier: GPL-3.0-or-later
// Per-reader allocation budget for the vendored RAR decoder only.
#pragma once
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#ifdef __cplusplus
extern "C" {
#endif
typedef struct NeoTexRARBudget {
  size_t limit, used, peak;
  int failed;
} NeoTexRARBudget;
NeoTexRARBudget *NeoTexRARUseBudget(NeoTexRARBudget *budget);
void *NeoTexRARMalloc(size_t size);
void *NeoTexRARCalloc(size_t count, size_t size);
void *NeoTexRARRealloc(void *pointer, size_t size);
void NeoTexRARFree(void *pointer);
char *NeoTexRARStrdup(const char *text);
#ifdef __cplusplus
}
#endif
