// NEOSTATION_RA_DISC_READER_V1 — see RBDiscHashReader.h.
//
// Sector addressing follows rcheevos' default reader (cdreader.c): `sector`
// is an absolute disc sector, track 1 index 01 being sector 0;
// first_track_sector() returns the sector of the track's index 01; a read
// returns the user data of consecutive sectors (2048 bytes for data tracks).

#include "RBDiscHashReader.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <zlib.h>

#include "libchdr/chd.h"

#define RB_CD_FRAME_BYTES 2448u      /* 2352 bytes of sector + 96 of subcode */
#define RB_CD_SECTOR_BYTES 2352u
#define RB_CD_TRACK_PADDING 4u       /* chdman pads each track to 4 frames */
#define RB_DVD_SECTOR_BYTES 2048u
#define RB_GDROM_HD_AREA 45000u      /* GD-ROM high-density area (track 3) */
#define RB_MAX_TRACKS 99
#define RB_CSO_MAX_BLOCKS (1u << 22) /* 8 GiB of 2 KiB blocks */

enum { RB_TRACK_DEFAULT = 1, RB_TRACK_CHD = 2, RB_TRACK_CSO = 3 };

typedef struct rb_disc_track {
  int kind;

  /* rcheevos' default reader (.cue/.bin, .gdi, .iso, anything else) */
  void *inner;
  rc_hash_cdreader_t fallback;

  /* CHD */
  chd_file *chd;
  uint8_t *hunk;
  uint32_t hunk_bytes;
  uint32_t total_hunks;
  uint32_t cached_hunk;
  uint32_t unit_bytes;      /* 2448 (CD frame) or 2048 (DVD sector) */
  uint32_t units_per_hunk;
  uint32_t unit_start;      /* first stored unit of the track in the CHD */
  uint32_t units;           /* stored units of the track */
  uint32_t lba_start;       /* absolute sector of the first stored unit */
  uint32_t pregap_stored;   /* stored pregap units before index 01 */
  uint32_t cooked_header;   /* user data offset when a sector has no sync */
  int audio;

  /* CSO (CISO v0/v1, zlib) */
  FILE *file;
  uint32_t *index;
  uint32_t block_count;
  uint32_t block_size;
  uint32_t align;
  uint8_t *block;
  uint8_t *packed;
  uint32_t packed_capacity;
  uint32_t cached_block;
  uint32_t cached_length;
} rb_disc_track_t;

static int rb_has_extension(const char *path, const char *extension) {
  size_t length, extension_length;
  const char *suffix;
  if (!path) return 0;
  length = strlen(path);
  extension_length = strlen(extension);
  if (length <= extension_length + 1 || path[length - extension_length - 1] != '.') return 0;
  suffix = path + length - extension_length;
  while (*extension) {
    char a = *suffix++, b = *extension++;
    if (a >= 'A' && a <= 'Z') a = (char)(a - 'A' + 'a');
    if (a != b) return 0;
  }
  return 1;
}

static int rb_is_special_or_first_track(uint32_t track) {
  return track == 1 || track == RC_HASH_CDTRACK_FIRST_DATA || track == RC_HASH_CDTRACK_LAST ||
         track == RC_HASH_CDTRACK_LARGEST;
}

static void rb_close(rb_disc_track_t *track) {
  if (!track) return;
  if (track->kind == RB_TRACK_DEFAULT && track->inner && track->fallback.close_track)
    track->fallback.close_track(track->inner);
  if (track->chd) chd_close(track->chd);
  if (track->file) fclose(track->file);
  free(track->hunk);
  free(track->index);
  free(track->block);
  free(track->packed);
  free(track);
}

/* ------------------------------------------------------------------ CHD */

typedef struct rb_chd_track_info {
  int number;
  char type[32];
  uint32_t frames;
  uint32_t pregap;
  uint32_t postgap;
  int pregap_stored;
} rb_chd_track_info_t;

static int rb_chd_metadata(chd_file *chd, uint32_t tag, uint32_t index, char *text, size_t capacity) {
  uint32_t length = 0;
  if (chd_get_metadata(chd, tag, index, text, (uint32_t)(capacity - 1), &length, NULL, NULL) != CHDERR_NONE)
    return 0;
  text[length < capacity - 1 ? length : capacity - 1] = '\0';
  return 1;
}

/* Reads the index-th CD/GD-ROM track description. */
static int rb_chd_track_info(chd_file *chd, uint32_t index, rb_chd_track_info_t *info, int *gdrom) {
  char text[512], subtype[32], pgtype[32] = "", pgsub[32];
  unsigned frames = 0, pregap = 0, postgap = 0, pad = 0;
  memset(info, 0, sizeof(*info));
  if (rb_chd_metadata(chd, CDROM_TRACK_METADATA2_TAG, index, text, sizeof(text))) {
    if (sscanf(text, "TRACK:%d TYPE:%31s SUBTYPE:%31s FRAMES:%u PREGAP:%u PGTYPE:%31s PGSUB:%31s POSTGAP:%u",
               &info->number, info->type, subtype, &frames, &pregap, pgtype, pgsub, &postgap) != 8)
      return 0;
  } else if (rb_chd_metadata(chd, CDROM_TRACK_METADATA_TAG, index, text, sizeof(text))) {
    if (sscanf(text, "TRACK:%d TYPE:%31s SUBTYPE:%31s FRAMES:%u",
               &info->number, info->type, subtype, &frames) != 4)
      return 0;
  } else if (rb_chd_metadata(chd, GDROM_TRACK_METADATA_TAG, index, text, sizeof(text))) {
    if (sscanf(text, "TRACK:%d TYPE:%31s SUBTYPE:%31s FRAMES:%u PAD:%u PREGAP:%u PGTYPE:%31s PGSUB:%31s POSTGAP:%u",
               &info->number, info->type, subtype, &frames, &pad, &pregap, pgtype, pgsub, &postgap) != 9)
      return 0;
    *gdrom = 1;
  } else {
    return 0;
  }
  info->frames = frames;
  info->pregap = pregap;
  info->postgap = postgap;
  /* "V..." pregap types mean the pregap sectors are stored in the image. */
  info->pregap_stored = pgtype[0] == 'V' && pregap > 0;
  if (info->pregap_stored && info->pregap > info->frames) info->pregap = info->frames;
  return info->number > 0 && frames > 0;
}

static uint32_t rb_cooked_header(const char *type) {
  /* MODE2 / MODE2_FORM_MIX (2336 bytes): an 8-byte subheader precedes the data. */
  if (strcmp(type, "MODE2") == 0 || strcmp(type, "MODE2/2336") == 0 || strcmp(type, "MODE2_FORM_MIX") == 0)
    return 8;
  return 0;
}

static const uint8_t *rb_chd_unit(rb_disc_track_t *track, uint32_t unit) {
  const uint32_t hunk = unit / track->units_per_hunk;
  if (hunk >= track->total_hunks) return NULL;
  if (hunk != track->cached_hunk) {
    if (chd_read(track->chd, hunk, track->hunk) != CHDERR_NONE) {
      track->cached_hunk = UINT32_MAX;
      return NULL;
    }
    track->cached_hunk = hunk;
  }
  return track->hunk + (size_t)(unit % track->units_per_hunk) * track->unit_bytes;
}

static rb_disc_track_t *rb_chd_open_track(const char *path, uint32_t track_number) {
  rb_chd_track_info_t *tracks = NULL;
  rb_disc_track_t *track = NULL;
  chd_file *chd = NULL;
  const chd_header *header;
  int count = 0, gdrom = 0, selected = -1, i;

  if (chd_open(path, CHD_OPEN_READ, NULL, &chd) != CHDERR_NONE || !chd) return NULL;
  header = chd_get_header(chd);
  if (!header || header->hunkbytes == 0 || header->totalhunks == 0) goto fail;

  track = (rb_disc_track_t *)calloc(1, sizeof(*track));
  if (!track) goto fail;
  track->kind = RB_TRACK_CHD;
  track->chd = chd;
  track->hunk_bytes = header->hunkbytes;
  track->total_hunks = header->totalhunks;
  track->cached_hunk = UINT32_MAX;
  track->hunk = (uint8_t *)malloc(header->hunkbytes);
  if (!track->hunk) goto fail;

  tracks = (rb_chd_track_info_t *)calloc(RB_MAX_TRACKS, sizeof(*tracks));
  if (!tracks) goto fail;
  while (count < RB_MAX_TRACKS && rb_chd_track_info(chd, (uint32_t)count, &tracks[count], &gdrom)) ++count;

  if (count == 0) {
    /* DVD image (PS2, PSP UMD): a single track of 2048-byte sectors. */
    if (header->hunkbytes % RB_DVD_SECTOR_BYTES != 0 ||
        (header->unitbytes != 0 && header->unitbytes != RB_DVD_SECTOR_BYTES))
      goto fail;
    if (!rb_is_special_or_first_track(track_number)) goto fail;
    track->unit_bytes = RB_DVD_SECTOR_BYTES;
    track->units_per_hunk = header->hunkbytes / RB_DVD_SECTOR_BYTES;
    track->units = (uint32_t)(header->logicalbytes / RB_DVD_SECTOR_BYTES);
    free(tracks);
    return track;
  }

  if (header->hunkbytes % RB_CD_FRAME_BYTES != 0) goto fail;
  track->unit_bytes = RB_CD_FRAME_BYTES;
  track->units_per_hunk = header->hunkbytes / RB_CD_FRAME_BYTES;

  if (track_number == RC_HASH_CDTRACK_FIRST_DATA) {
    for (i = 0; i < count && selected < 0; ++i)
      if (strcmp(tracks[i].type, "AUDIO") != 0) selected = i;
  } else if (track_number == RC_HASH_CDTRACK_LAST) {
    selected = count - 1;
  } else if (track_number == RC_HASH_CDTRACK_LARGEST) {
    selected = 0;
    for (i = 1; i < count; ++i)
      if (tracks[i].frames > tracks[selected].frames) selected = i;
  } else if (track_number == RC_HASH_CDTRACK_FIRST_OF_SECOND_SESSION) {
    selected = -1; /* CHD track metadata carries no session layout */
  } else {
    for (i = 0; i < count && selected < 0; ++i)
      if ((uint32_t)tracks[i].number == track_number) selected = i;
  }
  if (selected < 0) goto fail;

  {
    /* Same layout rules as MAME's cdrom_file: the stored data of every track
     * is padded to 4 frames; a pregap that is not stored still occupies disc
     * time (except before track 1, which is the lead-in); a postgap counts
     * against the next track. */
    uint32_t logical = 0, stored = 0;
    for (i = 0; i <= selected; ++i) {
      const rb_chd_track_info_t *info = &tracks[i];
      if (gdrom && info->number == 3 && logical < RB_GDROM_HD_AREA) logical = RB_GDROM_HD_AREA;
      if (!info->pregap_stored && i > 0) logical += info->pregap;
      if (i == selected) {
        track->lba_start = logical;
        track->unit_start = stored;
        track->units = info->frames;
        track->pregap_stored = info->pregap_stored ? info->pregap : 0;
        /* The high-density area's index 01 is sector 45000 whatever pregap
         * chdman stored before it. */
        if (gdrom && info->number == 3 && track->lba_start + track->pregap_stored != RB_GDROM_HD_AREA &&
            track->pregap_stored <= RB_GDROM_HD_AREA)
          track->lba_start = RB_GDROM_HD_AREA - track->pregap_stored;
        track->audio = strcmp(info->type, "AUDIO") == 0;
        track->cooked_header = rb_cooked_header(info->type);
        break;
      }
      logical += info->frames + info->postgap;
      stored += info->frames + (RB_CD_TRACK_PADDING - info->frames % RB_CD_TRACK_PADDING) % RB_CD_TRACK_PADDING;
    }
  }
  free(tracks);
  return track;

fail:
  free(tracks);
  if (track) {
    rb_close(track);
  } else if (chd) {
    chd_close(chd);
  }
  return NULL;
}

static size_t rb_chd_read(rb_disc_track_t *track, uint32_t sector, uint8_t *out, size_t requested) {
  static const uint8_t sync[12] = {0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0x00};
  size_t total = 0;
  uint32_t relative;
  if (sector < track->lba_start) return 0;
  relative = sector - track->lba_start;
  while (requested > 0 && relative < track->units) {
    const uint8_t *unit = rb_chd_unit(track, track->unit_start + relative);
    size_t offset = 0, available, chunk, k;
    if (!unit) break;
    if (track->unit_bytes == RB_DVD_SECTOR_BYTES) {
      available = RB_DVD_SECTOR_BYTES;
    } else if (track->audio) {
      available = RB_CD_SECTOR_BYTES;
    } else {
      /* Raw sectors carry a sync pattern and a mode byte; cooked sectors
       * start with the user data (MODE2 cooked: after an 8-byte subheader). */
      offset = memcmp(unit, sync, sizeof(sync)) == 0 ? (unit[15] == 2 ? 24 : 16) : track->cooked_header;
      available = 2048;
    }
    chunk = requested < available ? requested : available;
    if (track->audio) {
      /* CHD stores CD audio big-endian; .bin files are little-endian. */
      for (k = 0; k + 1 < chunk; k += 2) {
        out[k] = unit[offset + k + 1];
        out[k + 1] = unit[offset + k];
      }
      if (k < chunk) out[k] = unit[offset + k + 1];
    } else {
      memcpy(out, unit + offset, chunk);
    }
    out += chunk;
    total += chunk;
    requested -= chunk;
    ++relative;
  }
  return total;
}

/* ------------------------------------------------------------------ CSO */

static uint32_t rb_le32(const uint8_t *bytes) {
  return (uint32_t)bytes[0] | ((uint32_t)bytes[1] << 8) | ((uint32_t)bytes[2] << 16) | ((uint32_t)bytes[3] << 24);
}

static rb_disc_track_t *rb_cso_open_track(const char *path, uint32_t track_number) {
  uint8_t header[24];
  rb_disc_track_t *track;
  uint64_t total_bytes;
  uint32_t i;
  if (!rb_is_special_or_first_track(track_number)) return NULL;
  track = (rb_disc_track_t *)calloc(1, sizeof(*track));
  if (!track) return NULL;
  track->kind = RB_TRACK_CSO;
  track->cached_block = UINT32_MAX;
  track->file = fopen(path, "rb");
  if (!track->file || fread(header, 1, sizeof(header), track->file) != sizeof(header) ||
      memcmp(header, "CISO", 4) != 0)
    goto fail;
  total_bytes = (uint64_t)rb_le32(header + 8) | ((uint64_t)rb_le32(header + 12) << 32);
  track->block_size = rb_le32(header + 16);
  track->align = header[21];
  /* Version 2 blocks may be LZ4; only the zlib formats (0 and 1) are read. */
  if (header[20] > 1 || track->align > 31 || total_bytes == 0 || track->block_size < 2048 ||
      track->block_size > 0x100000 || track->block_size % 2048 != 0)
    goto fail;
  if ((total_bytes + track->block_size - 1) / track->block_size > RB_CSO_MAX_BLOCKS) goto fail;
  track->block_count = (uint32_t)((total_bytes + track->block_size - 1) / track->block_size);
  track->units = (uint32_t)(total_bytes / 2048);
  track->index = (uint32_t *)malloc(((size_t)track->block_count + 1) * sizeof(uint32_t));
  track->block = (uint8_t *)malloc(track->block_size);
  if (!track->index || !track->block) goto fail;
  if (fseek(track->file, 24, SEEK_SET) != 0) goto fail;
  for (i = 0; i <= track->block_count; ++i) {
    uint8_t entry[4];
    if (fread(entry, 1, 4, track->file) != 4) goto fail;
    track->index[i] = rb_le32(entry);
  }
  {
    /* A truncated download must not hash as a different game: the end of the
     * last block has to be inside the file. */
    off_t size;
    if (fseeko(track->file, 0, SEEK_END) != 0 || (size = ftello(track->file)) < 0) goto fail;
    if (((uint64_t)(track->index[track->block_count] & 0x7FFFFFFFu) << track->align) > (uint64_t)size) goto fail;
  }
  return track;

fail:
  rb_close(track);
  return NULL;
}

static int rb_cso_load_block(rb_disc_track_t *track, uint32_t block) {
  const uint32_t entry = track->index[block], next = track->index[block + 1];
  const uint64_t start = (uint64_t)(entry & 0x7FFFFFFFu) << track->align;
  const uint64_t end = (uint64_t)(next & 0x7FFFFFFFu) << track->align;
  uint32_t length;
  if (block == track->cached_block) return 1;
  track->cached_block = UINT32_MAX;
  if (end < start || end - start > (uint64_t)track->block_size * 2 + ((uint64_t)1 << track->align)) return 0;
  length = (uint32_t)(end - start);
  if (fseeko(track->file, (off_t)start, SEEK_SET) != 0) return 0;
  if (entry & 0x80000000u) {
    /* Stored block: the next index may include alignment padding. */
    const size_t wanted = length < track->block_size ? length : track->block_size;
    const size_t got = fread(track->block, 1, track->block_size, track->file);
    if (got < wanted) return 0;
    track->cached_length = (uint32_t)(got < track->block_size ? got : track->block_size);
  } else {
    z_stream stream;
    int status;
    if (length > track->packed_capacity) {
      uint8_t *packed = (uint8_t *)realloc(track->packed, length);
      if (!packed) return 0;
      track->packed = packed;
      track->packed_capacity = length;
    }
    if (fread(track->packed, 1, length, track->file) != length) return 0;
    memset(&stream, 0, sizeof(stream));
    if (inflateInit2(&stream, -15) != Z_OK) return 0;
    stream.next_in = track->packed;
    stream.avail_in = length;
    stream.next_out = track->block;
    stream.avail_out = track->block_size;
    status = inflate(&stream, Z_FINISH);
    track->cached_length = track->block_size - stream.avail_out;
    inflateEnd(&stream);
    if (status != Z_STREAM_END && status != Z_OK && status != Z_BUF_ERROR) return 0;
    if (track->cached_length == 0) return 0;
  }
  track->cached_block = block;
  return 1;
}

static size_t rb_cso_read(rb_disc_track_t *track, uint32_t sector, uint8_t *out, size_t requested) {
  size_t total = 0;
  uint64_t position = (uint64_t)sector * 2048;
  /* Same as an .iso through the default reader: 2048 bytes per sector. */
  while (requested > 0 && sector < track->units) {
    const uint32_t block = (uint32_t)(position / track->block_size);
    const uint32_t within = (uint32_t)(position % track->block_size);
    size_t chunk = requested < 2048 ? requested : 2048;
    if (block >= track->block_count || !rb_cso_load_block(track, block) || within >= track->cached_length) break;
    if (chunk > track->cached_length - within) chunk = track->cached_length - within;
    memcpy(out, track->block + within, chunk);
    out += chunk;
    total += chunk;
    requested -= chunk;
    position += 2048;
    ++sector;
    if (chunk < 2048 && requested > 0) break;
  }
  return total;
}

/* ------------------------------------------------------------ callbacks */

static void *rb_open_track_iterator(const char *path, uint32_t track, const rc_hash_iterator_t *iterator) {
  rb_disc_track_t *wrapper;
  void *inner;
  rc_hash_cdreader_t fallback;
  /* backwards compatibility in rcheevos: 0 means the largest track */
  if (track == 0) track = RC_HASH_CDTRACK_LARGEST;
  if (rb_has_extension(path, "chd")) return rb_chd_open_track(path, track);
  if (rb_has_extension(path, "cso")) return rb_cso_open_track(path, track);
  if (!iterator) return NULL;
  rc_hash_get_default_cdreader(&fallback);
  if (!fallback.open_track_iterator) return NULL;
  inner = fallback.open_track_iterator(path, track, iterator);
  if (!inner) return NULL;
  wrapper = (rb_disc_track_t *)calloc(1, sizeof(*wrapper));
  if (!wrapper) {
    if (fallback.close_track) fallback.close_track(inner);
    return NULL;
  }
  wrapper->kind = RB_TRACK_DEFAULT;
  wrapper->inner = inner;
  wrapper->fallback = fallback;
  return wrapper;
}

/* Only used by callers without an iterator; rcheevos prefers the iterator form. */
static void *rb_open_track(const char *path, uint32_t track) {
  return rb_open_track_iterator(path, track, NULL);
}

static size_t rb_read_sector(void *handle, uint32_t sector, void *buffer, size_t requested_bytes) {
  rb_disc_track_t *track = (rb_disc_track_t *)handle;
  if (!track || !buffer) return 0;
  switch (track->kind) {
    case RB_TRACK_DEFAULT:
      return track->fallback.read_sector ? track->fallback.read_sector(track->inner, sector, buffer, requested_bytes) : 0;
    case RB_TRACK_CHD:
      return rb_chd_read(track, sector, (uint8_t *)buffer, requested_bytes);
    case RB_TRACK_CSO:
      return rb_cso_read(track, sector, (uint8_t *)buffer, requested_bytes);
    default:
      return 0;
  }
}

static void rb_close_track(void *handle) {
  rb_close((rb_disc_track_t *)handle);
}

static uint32_t rb_first_track_sector(void *handle) {
  rb_disc_track_t *track = (rb_disc_track_t *)handle;
  if (!track) return 0;
  if (track->kind == RB_TRACK_DEFAULT)
    return track->fallback.first_track_sector ? track->fallback.first_track_sector(track->inner) : 0;
  if (track->kind == RB_TRACK_CHD) return track->lba_start + track->pregap_stored;
  return 0;
}

void rb_hash_install_disc_reader(rc_hash_callbacks_t *callbacks) {
  if (!callbacks) return;
  /* open_track must be set too: rcheevos only merges a cdreader that has it. */
  callbacks->cdreader.open_track = rb_open_track;
  callbacks->cdreader.read_sector = rb_read_sector;
  callbacks->cdreader.close_track = rb_close_track;
  callbacks->cdreader.first_track_sector = rb_first_track_sector;
  callbacks->cdreader.open_track_iterator = rb_open_track_iterator;
}

int rb_hash_generate_for_file(char hash[33], uint32_t console_id, const char *path) {
  rc_hash_iterator_t iterator;
  int result;
  if (!hash) return 0;
  hash[0] = '\0';
  if (!path || !*path) return 0;
  rc_hash_initialize_iterator(&iterator, path, NULL, 0);
  rb_hash_install_disc_reader(&iterator.callbacks);
  result = console_id ? rc_hash_generate(hash, console_id, &iterator) : rc_hash_iterate(hash, &iterator);
  rc_hash_destroy_iterator(&iterator);
  if (!result) hash[0] = '\0';
  return result;
}
