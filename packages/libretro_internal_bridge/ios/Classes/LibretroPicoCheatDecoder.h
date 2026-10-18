// Mathematical MD Game Genie/RAW encoding. Differential-tested against the
// delivered PicoDrive revision's original decoder; no memory access occurs.
#pragma once
#include <stdint.h>
#include <string.h>

typedef struct NeoPicoDecoded { uint32_t address; uint16_t value; } NeoPicoDecoded;
static int NeoPicoHex(char c) {
  const char* alphabet="0123456789ABCDEF";
  const char* at=strchr(alphabet,c);
  return at ? (int)(at-alphabet) : -1;
}
static int NeoPicoDecodeMD(const char* code,NeoPicoDecoded* result) {
  if (!code || !result) return 0;
  uint32_t address=0;uint16_t value=0;
  const size_t length=strlen(code);
  if (length==11 && code[6]==':') {
    for (size_t i=0;i<11;i++) {
      if (i==6) continue;
      int n=NeoPicoHex(code[i]);if(n<0)return 0;
      if(i<6)address=(address<<4)|(uint32_t)n;else value=(uint16_t)((value<<4)|n);
    }
  } else if (length==9 && code[4]=='-') {
    const char* alphabet="ABCDEFGHJKLMNPRSTVWXYZ0123456789";
    for (size_t i=0;i<9;i++) {
      if(i==4)continue;
      const char* at=strchr(alphabet,code[i]);if(!at)return 0;
      uint32_t n=(uint32_t)(at-alphabet);
      switch(i) {
        case 0:value|=(uint16_t)(n<<3);break;
        case 1:value|=(uint16_t)(n>>2);address|=(n&3)<<14;break;
        case 2:address|=n<<9;break;
        case 3:address|=((n&15)<<20)|((n>>4)<<8);break;
        case 5:value|=(uint16_t)((n&1)<<12);address|=(n>>1)<<16;break;
        case 6:value|=(uint16_t)(((n&1)<<15)|((n>>1)<<8));break;
        case 7:value|=(uint16_t)((n>>3)<<13);address|=(n&7)<<5;break;
        case 8:address|=n;break;
      }
    }
  } else return 0;
  result->address=address;result->value=value;return 1;
}
static int NeoPicoMDTokenAllowed(const char* code,int allowROM) {
  NeoPicoDecoded decoded;
  return NeoPicoDecodeMD(code,&decoded) && !(decoded.address&1) && decoded.value!=0xFFFF &&
      ((allowROM && decoded.address<0x400000) ||
       (decoded.address>=0xFF0000 && decoded.address<=0xFFFFFE));
}
