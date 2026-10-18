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
  for(NSString *unreviewed in @[@"azahar",@"unreviewed_core"])CHECK((![[LibretroCheats supportedCoreIDs] containsObject:unreviewed]),"identity support does not claim unverified native activation");
  CHECK((([LibretroCheats codesForCheat:@{@"code":@"_L 0x200F0024 0x0000007F\n_L 0x200F0028 0x00000022",@"handler":@0} core:@"ppsspp" console:@"psp"].count==1)),"PSP CWCheat normalized as one ordered program");
  CHECK((([LibretroCheats codesForCheat:@{@"code":@"_M 0x200F0024 0x0000007F",@"handler":@0} core:@"ppsspp" console:@"psp"]==nil)),"PSP alternate dialect is not silently rewritten");
  NSMutableArray *n64Lines=[NSMutableArray array];for(NSUInteger i=0;i<128;i++)[n64Lines addObject:@"800F0024 007F"];program=[n64Lines componentsJoinedByString:@"+"];
  native=[LibretroCheats codesForCheat:@{@"code":program,@"handler":@0} core:@"mupen64plus_next" console:@"n64"];CHECK((native.count==1&&[native[0] isEqual:program]&&program.length==1791),"N64 complete128pairs fit upstream256tokens");
  [n64Lines addObject:@"800F0024 007F"];CHECK(([LibretroCheats codesForCheat:@{@"code":[n64Lines componentsJoinedByString:@"+"],@"handler":@0} core:@"mupen64plus_next" console:@"n64"]==nil),"N64 never overruns upstream token slots");
  CHECK((([LibretroCheats codesForCheat:@{@"code":@"D00F0024 0001+800F0028 007F",@"handler":@0} core:@"mupen64plus_next" console:@"n64"].count==1)),"N64 condition and write stay grouped");
  CHECK((([LibretroCheats codesForCheat:@{@"code":@"D00F0024 0001",@"handler":@0} core:@"mupen64plus_next" console:@"n64"]==nil)),"dangling N64 condition rejected");
  CHECK((([LibretroCheats codesForCheat:@{@"code":@"880F0024 007F",@"handler":@0} core:@"mupen64plus_next" console:@"n64"]==nil)),"N64 physical GameShark button code not falsely advertised");
  [NSFileManager.defaultManager removeItemAtPath:folder error:nil];
} printf("Unified identity: %u checks, %u failures\n",checks,failures);return failures?1:0; }
