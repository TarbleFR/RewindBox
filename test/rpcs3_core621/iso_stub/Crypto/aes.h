// Host stub (REWINDBOX_ISO_IMAGE_LIFETIME_621 test): the generated images are not encrypted.
#pragma once
#include "stdafx.h"
struct aes_context { u32 unused = 0; };
inline int aes_setkey_dec(aes_context*, const unsigned char*, unsigned int) { return 1; }
inline int aes_setkey_enc(aes_context*, const unsigned char*, unsigned int) { return 1; }
inline int aes_crypt_cbc(aes_context*, int, std::size_t, unsigned char*, const unsigned char*, unsigned char*) { return 1; }
#define AES_DECRYPT 0
#define AES_ENCRYPT 1
