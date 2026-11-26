#pragma once
#include <assert.h>
#include <inttypes.h>
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "nvn_deswizzle.h"
typedef struct { nvn_texdesc d; nvn_texlayout L; uint8_t *mem; } tex_t;
typedef struct { int set_levels,base_level,set_layers,min_layer; } view_t;
typedef struct { int xoffset,yoffset,zoffset,width,height,depth; } NVNcopyRegion;
typedef struct { size_t calls,bytes,prepares,notifies; } stats;
typedef stats (*writer)(const tex_t*,const view_t*,const NVNcopyRegion*,const uint8_t*,size_t,size_t);
#define DECL_WRITER(id) stats id(const tex_t*,const view_t*,const NVNcopyRegion*,const uint8_t*,size_t,size_t)
DECL_WRITER(control); DECL_WRITER(suffix); DECL_WRITER(base); DECL_WRITER(fixed); DECL_WRITER(naive); DECL_WRITER(staged); DECL_WRITER(safe);
int eligible(const tex_t*, const NVNcopyRegion*,const uint8_t*,size_t);
void fail_next(void);
