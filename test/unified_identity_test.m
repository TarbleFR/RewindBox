#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#import <zlib.h>
#import "LibretroCheats.h"
#include <stdint.h>
#include <string.h>
static unsigned checks, failures;
#define CHECK(c,m) do { checks++; if (!(c)) { failures++; fprintf(stderr,"FAIL %d %s\n",__LINE__,m); } } while(0)
static NSString *HexBytes(const uint8_t *p, NSUInteger n) { NSMutableString *s=[NSMutableString string];for(NSUInteger i=0;i<n;i++)[s appendFormat:@"%02x",p[i]];return s; }
static NSString *SHA1(NSData *d) { uint8_t out[20];CC_SHA1(d.bytes,(CC_LONG)d.length,out);return HexBytes(out,20); }
static NSString *SHA256(NSData *d) { uint8_t out[32];CC_SHA256(d.bytes,(CC_LONG)d.length,out);return HexBytes(out,32); }
static NSDictionary *ID(NSString *type, NSString *value, NSString *scheme) { return @{@"type":type,@"value":value,@"scheme":scheme}; }
static NSString *Value(NSDictionary *identity,NSString *type,NSString *scheme) { for(NSDictionary *d in identity[@"identities"])if([d[@"type"] isEqual:type]&&[d[@"scheme"] isEqual:scheme])return d[@"value"];return nil; }
static void Put32(NSMutableData *d,NSUInteger at,uint32_t v) { uint8_t *p=d.mutableBytes;for(unsigned i=0;i<4;i++)p[at+i]=(uint8_t)(v>>(i*8)); }
static NSDictionary *Read(NSString *folder,NSString *name,NSData *data,NSString *system) { NSString *path=[folder stringByAppendingPathComponent:name];[data writeToFile:path atomically:YES];return [LibretroCheats identityAtPath:path console:system core:@"test"]; }
static NSMutableData *SFO(void) {
  const char keyBytes[]="DISC_ID\0DISC_VERSION\0"; NSData *keys=[NSData dataWithBytes:keyBytes length:sizeof(keyBytes)-1];
  NSMutableData *d=[NSMutableData dataWithLength:52+keys.length+16];uint8_t *p=d.mutableBytes;memcpy(p,"\0PSF",4);Put32(d,4,0x101);Put32(d,8,52);Put32(d,12,(uint32_t)(52+keys.length));Put32(d,16,2);
  p[22]=4;p[23]=2;Put32(d,24,10);Put32(d,28,10);p[36]=8;p[38]=4;p[39]=2;Put32(d,40,5);Put32(d,44,6);Put32(d,48,10);
  memcpy(p+52,keys.bytes,keys.length);memcpy(p+52+keys.length,"ULES01234",10);memcpy(p+62+keys.length,"1.01",5);return d;
}
int main(void) { @autoreleasepool {
  NSString *folder=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];[NSFileManager.defaultManager createDirectoryAtPath:folder withIntermediateDirectories:YES attributes:nil error:nil];
  NSData *abc=[@"abc" dataUsingEncoding:NSASCIIStringEncoding];NSDictionary *simple=Read(folder,@"renamed.gb",abc,@"gb");
  CHECK(([simple[@"md5"] isEqual:@"900150983cd24fb0d6963f7d28e17f72"]),"legacy full MD5 retained");
  CHECK(([Value(simple,@"sha1",@"rom-full") isEqual:SHA1(abc)]),"typed full SHA1 retained");
  NSMutableData *nes=[NSMutableData dataWithLength:16+512+16384+8192+7];uint8_t *p=nes.mutableBytes;memcpy(p,"NES\x1a",4);p[4]=1;p[5]=1;p[6]=4;
  for(NSUInteger i=16+512;i<nes.length;i++)p[i]=(uint8_t)(i*13);
  NSDictionary *n=Read(folder,@"random.nes",nes,@"nes");NSData *prg=[nes subdataWithRange:NSMakeRange(528,16384)];NSData *prgchr=[nes subdataWithRange:NSMakeRange(528,24576)];
  CHECK(([Value(n,@"sha1",@"nes-prg") isEqual:SHA1(prg)]),"Mesen NES SHA1 is PRG only");
  CHECK(([Value(n,@"sha1",@"ines-prg-chr") isEqual:SHA1(prgchr)]),"PRG+CHR excludes trainer and appended data");
  CHECK((![Value(n,@"sha1",@"nes-prg") isEqual:Value(n,@"sha1",@"rom-full")]),"Mesen and ROM scopes stay distinct");
  NSDictionary *mesen=@{@"system":@"nes",@"title":@"Other name (USA)",@"identities":@[ID(@"sha1",SHA1(prg),@"nes-prg")]};
  CHECK(([[LibretroCheats matchGame:mesen identity:n] isEqual:@"hash"]),"Mesen hash recognizes renamed content");
  NSDictionary *wrongScope=@{@"console":@"nes",@"title":@"random",@"identities":@[ID(@"sha1",SHA1(prg),@"rom-full")]};
  CHECK(([[LibretroCheats matchGame:wrongScope identity:n] isEqual:@"mismatch"]),"same digest in wrong namespace cannot match");
  p[4]=255;NSDictionary *bad=Read(folder,@"truncated.nes",nes,@"nes");CHECK((!Value(bad,@"sha1",@"nes-prg")),"truncated header does not invent PRG identity");
  p=nes.mutableBytes;p[4]=0x38;p[5]=0x34;p[7]=8;p[9]=0xff;NSDictionary *nes2=Read(folder,@"nes2.nes",nes,@"nes");CHECK(([Value(nes2,@"sha1",@"nes-prg") isEqual:SHA1(prg)]),"NES2 exponent sizes hash the same exact PRG bytes");
  NSMutableData *snes=[NSMutableData dataWithLength:32768+512];memset(snes.mutableBytes,0xa5,512);NSDictionary *sfc=Read(folder,@"headered.smc",snes,@"snes");CHECK(([Value(sfc,@"sha256",@"bsnes-cartridge") isEqual:SHA256([snes subdataWithRange:NSMakeRange(512,32768)])]),"bsnes cartridge identity removes exactly its512byte copier header");
  [snes setLength:1536];sfc=Read(folder,@"odd-sized.smc",snes,@"snes");CHECK(([Value(sfc,@"sha256",@"bsnes-cartridge") isEqual:SHA256(snes)]),"bsnes namespace does not strip bytes outside its exact32768size test");
  NSMutableData *nds=[NSMutableData dataWithLength:1024];p=nds.mutableBytes;memcpy(p+12,"CPUF",4);p[0x1e]=5;for(NSUInteger i=512;i<nds.length;i++)p[i]=(uint8_t)i;
  NSDictionary *ds=Read(folder,@"renamed.nds",nds,@"nds");NSString *r4=@"10192E29";
  CHECK(([ds[@"ndsGameCode"] isEqual:@"CPUF"]&&[ds[@"ndsR4CRC32"] isEqual:r4]),"R4 uses inverted header CRC plus game code");
  NSDictionary *dsGame=@{@"system":@"nds",@"title":@"Platine",@"identities":@[ID(@"ds_game_code",@"CPUF",@"nds-header-gamecode"),ID(@"ds_crc",r4,@"r4-header512-crc32-inverted")]};
  CHECK(([[LibretroCheats matchGame:dsGame identity:ds] isEqual:@"hash"]),"both R4 constraints establish exact source key");
  NSMutableDictionary *partial=[ds mutableCopy];partial[@"identities"]=@[ID(@"ds_game_code",@"CPUF",@"nds-header-gamecode")];
  CHECK((![[LibretroCheats matchGame:dsGame identity:partial] isEqual:@"hash"]),"DS game code alone cannot assert matching R4 revision");
  p[12]='A';NSDictionary *differentDS=Read(folder,@"Platine.nds",nds,@"nds");CHECK(([[LibretroCheats matchGame:dsGame identity:differentDS] isEqual:@"mismatch"]),"R4 checksum does not override different game code");
  NSMutableData *n64=[NSMutableData dataWithLength:4096];p=n64.mutableBytes;memcpy(p,"\x80\x37\x12\x40",4);memcpy(p+16,"\x12\x34\x56\x78\x9a\xbc\xde\xf0",8);p[0x3e]='F';p[0x3f]=1;
  NSDictionary *z=Read(folder,@"cart.z64",n64,@"n64");CHECK(([Value(z,@"n64_header",@"n64-crc1-crc2-country") isEqual:@"12345678-9ABCDEF0-C:46"]),"N64 code includes country");
  for(NSUInteger swap=2;swap<=4;swap+=2) { NSMutableData *swapped=[n64 mutableCopy];p=swapped.mutableBytes;for(NSUInteger i=0;i<swapped.length;i+=swap)for(NSUInteger j=0;j<swap/2;j++){uint8_t t=p[i+j];p[i+j]=p[i+swap-1-j];p[i+swap-1-j]=t;}
    NSDictionary *other=Read(folder,[NSString stringWithFormat:@"swapped%lu.n64",(unsigned long)swap],swapped,@"n64");CHECK(([Value(z,@"sha1",@"n64-big-endian") isEqual:Value(other,@"sha1",@"n64-big-endian")]),"both N64 byte orders have same canonical hash");CHECK((![z[@"sha1"] isEqual:other[@"sha1"]]),"original N64 bytes still key preferences"); }
  NSMutableData *pbp=[NSMutableData dataWithLength:40];p=pbp.mutableBytes;memcpy(p,"\0PBP",4);NSMutableData *sfo=SFO();Put32(pbp,8,40);for(NSUInteger i=12;i<40;i+=4)Put32(pbp,i,(uint32_t)(40+sfo.length));[pbp appendData:sfo];
  NSDictionary *psp=Read(folder,@"arbitrary.pbp",pbp,@"psp");CHECK(([psp[@"pspGameID"] isEqual:@"ULES01234"]&&[psp[@"pspDiscVersion"] isEqual:@"1.01"]),"PSP identity reads PARAM.SFO not filename");CHECK((!Value(psp,@"sha1",@"rom-full")&&Value(psp,@"sha1",@"container-file")),"PBP wrapper hash cannot match ROM digest");
  NSMutableData *invalidPBP=[pbp mutableCopy];Put32(invalidPBP,8,0xfffffff0);NSDictionary *invalidPSP=Read(folder,@"invalid.pbp",invalidPBP,@"psp");CHECK((!invalidPSP[@"pspGameID"]),"out-of-bounds SFO offset cannot identify a PSP game");
  NSDictionary *pspGame=@{@"system":@"psp",@"title":@"PSP game",@"identities":@[ID(@"game_id",@"ULES01234",@"psp-param-sfo-disc-id")]};CHECK(([[LibretroCheats matchGame:pspGame identity:psp] isEqual:@"candidate"]),"PSP serial is not a proved executable revision");
  NSMutableData *ncch=[NSMutableData dataWithLength:512];p=ncch.mutableBytes;memcpy(p+0x100,"NCCH",4);Put32(ncch,0x118,0x00055d00);Put32(ncch,0x11c,0x00040000);
  NSDictionary *ctr=Read(folder,@"unknown.cxi",ncch,@"3ds");CHECK(([ctr[@"titleID"] isEqual:@"0004000000055D00"]),"NCCH title ID is read little endian");CHECK((!ctr[@"titleVersion"]),"NCCH title ID does not invent installed update version");
  NSMutableData *ncsd=[NSMutableData dataWithLength:1536];p=ncsd.mutableBytes;memcpy(p+0x100,"NCSD",4);Put32(ncsd,0x120,2);memcpy(p+1024,ncch.bytes,ncch.length);NSDictionary *cart3DS=Read(folder,@"renamed.3ds",ncsd,@"3ds");CHECK(([cart3DS[@"titleID"] isEqual:ctr[@"titleID"]]),"NCSD first-partition offset resolves actual NCCH title ID");
  NSDictionary *metadata=[LibretroCheats metadataForTitle:@"Pokémon (Europe) (En,Fr,De) (Rev. 2)"];CHECK(([metadata[@"regions"] containsObject:@"europe"]&&[metadata[@"languages"] containsObject:@"fr"]&&[metadata[@"gameRevision"] isEqual:@"2"]),"region language revision stay separate");
  CHECK((([[LibretroCheats matchGame:@{@"console":@"gb",@"title":@"Pokémon (Europe) (De)"} identity:@{@"console":@"gb",@"title":@"Pokémon (Europe) (Fr)"}] isEqual:@"none"])),"different explicit languages excluded");
  NSMutableArray *dsLines=[NSMutableArray array];for(NSUInteger i=0;i<56;i++)[dsLines addObject:@"22000024 0000007F"];NSString *program=[dsLines componentsJoinedByString:@"+"];
  NSArray *native=[LibretroCheats codesForCheat:@{@"code":program,@"handler":@0} core:@"desmume" console:@"nds"];CHECK((native.count==1&&[native[0] isEqual:program]&&program.length>255),"complete DS program above255 preserved under1024");
  for(NSUInteger i=0;i<2;i++)[dsLines addObject:@"22000024 0000007F"];CHECK(([LibretroCheats codesForCheat:@{@"code":[dsLines componentsJoinedByString:@"+"],@"handler":@0} core:@"desmume" console:@"nds"]==nil),"DS program exceeding upstream stack buffer rejected intact");
  NSMutableArray *psxLines=[NSMutableArray array];for(NSUInteger i=0;i<60;i++)[psxLines addObject:[NSString stringWithFormat:@"8001%04lX %04lX",(unsigned long)i,(unsigned long)i]];program=[psxLines componentsJoinedByString:@"+"];
  native=[LibretroCheats codesForCheat:@{@"code":program,@"handler":@0} core:@"mednafen_psx_hw" console:@"psx"];CHECK((native.count>1&&[[native componentsJoinedByString:@"+"] isEqual:program]),"long PSX independent writes split without loss or reordering");for(NSString *batch in native)CHECK((batch.length<=255),"every PSX call remains bounded");
  for (NSString *valid in @[@"D0010024 0011+80010028 007F",@"E3010024 0011+30010028 007F",@"50000302 0001+80010028 007F",@"D0010024 0011+50000302 0001+80010028 007F"]) {
    native=[LibretroCheats codesForCheat:@{@"code":valid} core:@"mednafen_psx_hw" console:@"psx"];
    CHECK((native.count==1&&[native[0] isEqual:[valid stringByReplacingOccurrencesOfString:@" " withString:@""]]),"PSX condition/repeater stays in one native call");
  }
  for (NSString *invalid in @[@"D0010024 0011",@"50000302 0001",@"D0010024 0011+E0010028 0011+8001002C 007F",@"50000302 0001+D0010024 0011+80010028 007F",@"50000302 0001+50000302 0001+80010028 007F",@"E0010024 0100+30010028 007F",@"50000302 0100+80010028 007F",@"50010302 0001+80010028 007F",@"50000002 0001+80010028 007F",@"C2010024 0011+80010028 007F"]) {
    CHECK(([LibretroCheats codesForCheat:@{@"code":invalid} core:@"mednafen_psx_hw" console:@"psx"]==nil),"PSX unsupported or incomplete control group rejected atomically");
  }
  NSMutableArray *atomic=[NSMutableArray arrayWithObjects:@"D00100240011",nil];for(NSUInteger i=0;i<18;i++)[atomic addObject:@"80010028007F"];
  CHECK(([LibretroCheats codesForCheat:@{@"code":[atomic componentsJoinedByString:@"+"]} core:@"mednafen_psx_hw" console:@"psx"].count==1),"PSX19compactinstructions fit one255byte call");
  [atomic addObject:@"80010028007F"];CHECK(([LibretroCheats codesForCheat:@{@"code":[atomic componentsJoinedByString:@"+"]} core:@"mednafen_psx_hw" console:@"psx"]==nil),"PSX conditional program over255 is never fragmented");
  for(NSString *unreviewed in @[@"azahar",@"unreviewed_core"])CHECK((![[LibretroCheats supportedCoreIDs] containsObject:unreviewed]),"identity support does not claim unverified native activation");
  CHECK((([LibretroCheats codesForCheat:@{@"code":@"_L 0x200F0024 0x0000007F\n_L 0x200F0028 0x00000022",@"handler":@0} core:@"ppsspp" console:@"psp"].count==1)),"PSP CWCheat normalized as one ordered program");
  CHECK((([LibretroCheats codesForCheat:@{@"code":@"_M 0x200F0024 0x0000007F",@"handler":@0} core:@"ppsspp" console:@"psp"]==nil)),"PSP alternate dialect is not silently rewritten");
  native=[LibretroCheats codesForCheat:@{@"code":@"08000100:12345678+08000104:ABCDEF01",@"dialect":@"gba-vba-raw"} core:@"mgba" console:@"gba"];
  CHECK((native.count==1&&[native[0] isEqual:@"08000100:12345678+08000104:ABCDEF01"]),"VBA ROM patch colon and source byte order preserved");
  native=[LibretroCheats codesForCheat:@{@"code":@"0200E924:96+03000000:0096+02000004:00000096+03007FFF:7F",@"dialect":@"gba-vba-raw"} core:@"mgba" console:@"gba"];
  CHECK((native.count==1&&[native[0] isEqual:@"0200E924:96  +03000000:0096+02000004:00000096+03007FFF:7F  "]),"VBA RAM write widths and required byte padding survive every separator and final record");
  for(NSString *invalid in @[@"02040000:12",@"03008000:12",@"02000001:1234",@"03007FFE:12345678",@"04000000:1234",@"08000100:1234",@"08000100 12345678",@"08000100:12345678+ZZ000104:ABCDEF01"])
    CHECK(([LibretroCheats codesForCheat:@{@"code":invalid,@"dialect":@"gba-vba-raw"} core:@"mgba" console:@"gba"]==nil),"VBA ROM profile rejects other address spaces or dialects");
  NSMutableArray *n64Lines=[NSMutableArray array];for(NSUInteger i=0;i<128;i++)[n64Lines addObject:@"800F0024 007F"];program=[n64Lines componentsJoinedByString:@"+"];
  native=[LibretroCheats codesForCheat:@{@"code":program,@"handler":@0} core:@"mupen64plus_next" console:@"n64"];CHECK((native.count==1&&[native[0] isEqual:program]&&program.length==1791),"N64 complete128pairs fit upstream256tokens");
  [n64Lines addObject:@"800F0024 007F"];CHECK(([LibretroCheats codesForCheat:@{@"code":[n64Lines componentsJoinedByString:@"+"],@"handler":@0} core:@"mupen64plus_next" console:@"n64"]==nil),"N64 never overruns upstream token slots");
  CHECK((([LibretroCheats codesForCheat:@{@"code":@"D00F0024 0001+800F0028 007F",@"handler":@0} core:@"mupen64plus_next" console:@"n64"].count==1)),"N64 condition and write stay grouped");
  CHECK((([LibretroCheats codesForCheat:@{@"code":@"D00F0024 0001",@"handler":@0} core:@"mupen64plus_next" console:@"n64"]==nil)),"dangling N64 condition rejected");
  CHECK((([LibretroCheats codesForCheat:@{@"code":@"880F0024 007F",@"handler":@0} core:@"mupen64plus_next" console:@"n64"]==nil)),"N64 physical GameShark button code not falsely advertised");
  CHECK(([LibretroCheats codesForCheat:@{@"code":@"1F0024:7F+F82024:11"} core:@"mednafen_pce_fast" console:@"pce"].count==1),"PCE native main RAM and attested alias accepted together");
  CHECK(([LibretroCheats codesForCheat:@{@"code":@"0D0000:7F+10FFFF:11"} core:@"mednafen_pce_fast" console:@"pccd"].count==1),"PCE CD RAM admitted only on CD console binding");
  CHECK(([LibretroCheats codesForCheat:@{@"code":@"0D0000:7F"} core:@"mednafen_pce_fast" console:@"pce"]==nil),"PCE cartridge profile cannot address unconfirmed CD memory");
  CHECK(([LibretroCheats codesForCheat:@{@"code":@"80C024:7F"} core:@"mednafen_pce_fast" console:@"pce"]==nil),"PCE guessed address alias remains unavailable");
  NSMutableArray *pceLines=[NSMutableArray array];for(NSUInteger i=0;i<26;i++)[pceLines addObject:@"1F0024:7F"];
  native=[LibretroCheats codesForCheat:@{@"code":[pceLines componentsJoinedByString:@"+"]} core:@"mednafen_pce_fast" console:@"pce"];
  CHECK((native.count==2&&[[native componentsJoinedByString:@"+"] isEqual:[pceLines componentsJoinedByString:@"+"]]),"PCE append-only calls preserve all26writes and their order under255bytes");
  [pceLines addObject:@"FFFFFF:01"];CHECK(([LibretroCheats codesForCheat:@{@"code":[pceLines componentsJoinedByString:@"+"]} core:@"mednafen_pce_fast" console:@"pce"]==nil),"PCE validates the tail before emitting any batches");
  native=[LibretroCheats codesForCheat:@{@"code":@"001E24:09+0000FFFF:7F"} core:@"mednafen_wswan" console:@"wsc"];
  CHECK((native.count==1&&[native[0] isEqual:@"1E24:09+FFFF:7F"]),"WonderSwan canonicalizes only numerically identical main RAM addresses");
  for(NSString *invalid in @[@"10000:01",@"00010000:01",@"0123456",@"1E24:0100"])
    CHECK(([LibretroCheats codesForCheat:@{@"code":invalid} core:@"mednafen_wswan" console:@"ws"]==nil),"WonderSwan raw profile refuses ROM Game Genie and unknown SRAM");
  NSMutableArray *wsLines=[NSMutableArray array];for(NSUInteger i=0;i<128;i++)[wsLines addObject:@"1E24:09"];
  native=[LibretroCheats codesForCheat:@{@"code":[wsLines componentsJoinedByString:@"+"]} core:@"mednafen_wswan" console:@"ws"];
  CHECK((native.count==1&&[native[0] length]==1023),"128WonderSwan writes stay in one streaming parser call");
  native=[LibretroCheats codesForCheat:@{@"code":@"AMEA-AA9Y+FF03B4:0060"} core:@"picodrive" console:@"32x"];
  CHECK((native.count==1&&[native[0] isEqual:@"AMEA-AA9Y+FF03B4:0060"]),"PicoDrive attested MD Genie and raw words preserve one programme");
  for(NSString *invalid in @[@"FF0001:0001",@"400000:1234",@"FF0000:FFFF",@"FF0000:12345"])
    CHECK(([LibretroCheats codesForCheat:@{@"code":invalid} core:@"picodrive" console:@"32x"]==nil),"PicoDrive rejects odd SH2 sentinel and oversized words");
  CHECK(([LibretroCheats codesForCheat:@{@"code":@"AMEA-AA9Y"} core:@"picodrive" console:@"mcd"]==nil),"PicoDrive CD profile never projects cartridge ROM addresses");
  CHECK(([LibretroCheats codesForCheat:@{@"code":@"FF03B4:0060"} core:@"picodrive" console:@"sms"]==nil),"PicoDrive SMS RAM no-op is not offered as an executable profile");
  NSMutableArray *picoLines=[NSMutableArray array];for(NSUInteger i=0;i<50;i++)[picoLines addObject:@"FF03B4:0060"];
  native=[LibretroCheats codesForCheat:@{@"code":[picoLines componentsJoinedByString:@"+"]} core:@"picodrive" console:@"32x"];
  CHECK((native.count==3&&[[native componentsJoinedByString:@"+"] isEqual:[picoLines componentsJoinedByString:@"+"]]),"PicoDrive append batches retain the complete50write programme");
  [picoLines addObject:@"FF0001:0001"];CHECK(([LibretroCheats codesForCheat:@{@"code":[picoLines componentsJoinedByString:@"+"]} core:@"picodrive" console:@"32x"]==nil),"PicoDrive rejects an invalid last write before returning any batches");
  [NSFileManager.defaultManager removeItemAtPath:folder error:nil];
} printf("Unified identity: %u checks, %u failures\n",checks,failures);return failures?1:0; }
