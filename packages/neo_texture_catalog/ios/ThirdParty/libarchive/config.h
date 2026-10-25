/* NeoStation's fixed POSIX/iOS LP64 configuration for the read-only RAR subset.
 * Upstream source is unchanged. No external program, encryption or write backend.
 */
#ifndef NEOTEX_LIBARCHIVE_CONFIG_H
#define NEOTEX_LIBARCHIVE_CONFIG_H
#define __LIBARCHIVE_CONFIG_H_INCLUDED 1
#define LIBARCHIVE_STATIC 1
#include "NeoTextureLibarchivePrefix.h"
#include "../../Classes/NeoTextureRARMemory.h"
#define malloc NeoTexRARMalloc
#define calloc NeoTexRARCalloc
#define realloc NeoTexRARRealloc
#define free NeoTexRARFree
#define strdup NeoTexRARStrdup
#define HAVE_INT16_T 1
#define HAVE_INT32_T 1
#define HAVE_INT64_T 1
#define HAVE_INTMAX_T 1
#define HAVE_UINT8_T 1
#define HAVE_UINT16_T 1
#define HAVE_UINT32_T 1
#define HAVE_UINT64_T 1
#define HAVE_UINTMAX_T 1
#define SIZEOF_SHORT 2
#define SIZEOF_INT 4
#define SIZEOF_LONG 8
#define SIZEOF_LONG_LONG 8
#define SIZEOF_WCHAR_T 4
#define HAVE_INTTYPES_H 1
#define HAVE_STDINT_H 1
#define HAVE_STDLIB_H 1
#define HAVE_STRING_H 1
#define HAVE_STRINGS_H 1
#define HAVE_LIMITS_H 1
#define HAVE_ERRNO_H 1
#define HAVE_FCNTL_H 1
#define HAVE_UNISTD_H 1
#define HAVE_SYS_TYPES_H 1
#define HAVE_SYS_STAT_H 1
#define HAVE_SYS_TIME_H 1
#define HAVE_TIME_H 1
#define HAVE_WCHAR_H 1
#define HAVE_WCTYPE_H 1
#define HAVE_LOCALE_H 1
#define HAVE_LANGINFO_H 1
#define HAVE_NL_LANGINFO 1
#define HAVE_ICONV_H 1
#define HAVE_ICONV 1
#define ICONV_CONST
#define HAVE_MBRTOWC 1
#define HAVE_WCRTOMB 1
#define HAVE_WCSLEN 1
#define HAVE_WCSCMP 1
#define HAVE_WCSCPY 1
#define HAVE_WCSCHR 1
#define HAVE_WMEMCPY 1
#define HAVE_WMEMMOVE 1
#define HAVE_DECL_SIZE_MAX 1
#define HAVE_DECL_SSIZE_MAX 1
#define HAVE_DECL_UINT32_MAX 1
#define HAVE_DECL_INT32_MAX 1
#define HAVE_DECL_INT32_MIN 1
#define HAVE_DECL_UINT64_MAX 1
#define HAVE_DECL_INT64_MAX 1
#define HAVE_DECL_INT64_MIN 1
#define HAVE_DECL_UINTMAX_MAX 1
#define HAVE_DECL_INTMAX_MAX 1
#define HAVE_DECL_INTMAX_MIN 1
#define HAVE_DECL_EFTYPE 0
#define HAVE_EILSEQ 1
#define HAVE_STRERROR 1
#define HAVE_STRDUP 1
#define HAVE_STRNLEN 1
#define HAVE_MEMMOVE 1
#define HAVE_SNPRINTF 1
#define HAVE_VSNPRINTF 1
#define HAVE_READLINK 1
#define HAVE_LSTAT 1
#define HAVE_FSTAT 1
#define HAVE_ZLIB_H 1
#define HAVE_LIBZ 1
#define HAVE_LOCALTIME_R 1
#define HAVE_ARC4RANDOM_BUF 1
#define HAVE_WORKING_EXT2_IOC_GETFLAGS 0
#define HAVE_FCHDIR 1
#define HAVE_CHOWN 1
#define HAVE_FCHOWN 1
#define HAVE_FCHMOD 1
#define HAVE_FUTIMES 1
#if defined(__APPLE__)
#define HAVE_STRUCT_STAT_ST_MTIMESPEC_TV_NSEC 1
#define HAVE_STRUCT_STAT_ST_BIRTHTIMESPEC_TV_NSEC 1
#else
#define HAVE_STRUCT_STAT_ST_MTIM_TV_NSEC 1
#define HAVE_STRUCT_STAT_ST_ATIM_TV_NSEC 1
#define HAVE_STRUCT_STAT_ST_CTIM_TV_NSEC 1
#endif
#endif
