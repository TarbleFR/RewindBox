// Exact service behaviour and a full-size on-disk metadata benchmark.
#define main PreviousCatalogueMain
#import "unified_catalog_runtime_native.m"
#undef main
#import <fcntl.h>
#import <unistd.h>
@interface NeoUnifiedCheatCatalog (Probe479)
- (BOOL)hasChunk:(NSDictionary *)game verify:(BOOL)verify;
@end
@interface Catalogue479Probe : NeoUnifiedCheatCatalog
@property(nonatomic) NSUInteger fileChecks;
@end
@implementation Catalogue479Probe
- (BOOL)hasChunk:(NSDictionary *)game verify:(BOOL)verify {self.fileChecks++;return [super hasChunk:game verify:verify];}
@end
static NSArray *Matches479(NeoUnifiedCheatCatalog *catalog,NSDictionary *identity) {
  __block BOOL done=NO;__block NSArray *rows=nil;
  [catalog gamesForIdentity:identity completion:^(NSArray *games,NSError *error){CHECK(!error,"discovery succeeds");rows=games;done=YES;}];Spin(^BOOL{return done;});return rows;
}
static void Editions479(NSString *root,BOOL baseline) {
  NSMutableArray *games=[NSMutableArray array],*packs=[NSMutableArray array];NSMutableDictionary *responses=[NSMutableDictionary dictionary];
  NSArray *specs=@[@[@"EUR",@"SLES51839",@"AABBCCDD",@"Europe",@"01.01"],@[@"EUR2",@"SLES51839",@"AABBCCDD",@"Europe",@"01.01"],
    @[@"USA",@"SLUS20851",@"11223344",@"USA",@"01.01"],@[@"World",@"",@"",@"World",@""],@[@"TitleUSA",@"",@"",@"USA",@""],
    @[@"Old",@"SLES51839",@"AABBCCDD",@"Europe",@"01.00"],@[@"BadCRC",@"SLES51839",@"87654321",@"Europe",@"01.01"]];
  for(NSArray *s in specs) {
    NSMutableArray *ids=[NSMutableArray array];if([s[1] length])[ids addObject:ID(@"serial",s[1],@"ps2-disc-serial")];if([s[2] length])[ids addObject:ID(@"ps2_crc",s[2],@"pcsx2-executable-crc")];
    NSString *gid=s[0],*pid=[@"pack-" stringByAppendingString:gid];
    NSMutableDictionary *g=[@{@"id":gid,@"system":@"ps2",@"title":@"Edition fixture",@"identities":ids,@"regions":@[s[3]],@"revision":s[4],@"pack_id":pid,@"path":[NSString stringWithFormat:@"games/%@.json",gid]} mutableCopy];
    NSDictionary *program=@{@"id":@"code",@"name":@"Money",@"code":@"patch=1,EE,20100000,extended,00000001",@"dialect":@"pnach",@"handler":@0,@"status":@"available",@"enabled":@NO};
    NSData *data=Bytes(@{@"schema_version":@1,@"game":g,@"cheats":@[program]});g[@"sha256"]=Hash(data);g[@"size"]=@(data.length);
    NSData *expanded=Bytes(@{@"schema_version":@1,@"files":@[@{@"game_id":gid,@"data":[data base64EncodedStringWithOptions:0]}]});NSData *packed=Gzip(expanded);
    NSString *path=[NSString stringWithFormat:@"packs/%@.json.gz",pid];[games addObject:g];[packs addObject:@{@"id":pid,@"path":path,@"game_ids":@[gid],@"size":@(packed.length),@"uncompressed_size":@(expanded.length),@"sha256":Hash(packed)}];responses[path]=packed;
  }
  NSDictionary *manifest=@{@"schema_version":@1,@"catalogue_id":@"479-editions",@"revision":@"1",@"games":games,@"packs":packs,@"sources":@[]};
  NeoUnifiedCheatCatalog *catalog=[NeoUnifiedCheatCatalog new];catalog.storageDirectory=root;catalog.bundledDirectory=[root stringByAppendingPathComponent:@"bundle"];
  [NSFileManager.defaultManager createDirectoryAtPath:catalog.bundledDirectory withIntermediateDirectories:YES attributes:nil error:nil];[Bytes(manifest) writeToFile:[catalog.bundledDirectory stringByAppendingPathComponent:@"manifest.json"] atomically:YES];
  catalog.manifestURL=[NSURL URLWithString:@"https://fixture.example/index.json"];__block NSUInteger fetches=0;
  catalog.fetch=^(NSURL *url,NSUInteger limit,void(^done)(NSData*,NSError*)){fetches++;done(responses[[url.path substringFromIndex:1]],nil);};
  NSDictionary *identity=@{@"system":@"ps2",@"title":@"Edition fixture",@"revision":@"01.01",@"identities":@[ID(@"serial",@"SLES-51839",@"ps2-disc-serial"),ID(@"ps2_crc",@"AABBCCDD",@"pcsx2-executable-crc")]};
  NSArray *found=Matches479(catalog,identity);
  if(baseline){CHECK(found.count>2,"delivered 478 reproduces title-only regional candidates");printf("CONFIRMED delivered 478 adds title-only regional/World candidates after typed identification\n");return;}
  CHECK(found.count==2,"only both compatible European source parts remain");
  for(NSDictionary *g in found)CHECK([g[@"id"] hasPrefix:@"EUR"],"USA, World, old version and conflicting CRC stay excluded");
  NSMutableDictionary *missing=[identity mutableCopy];missing[@"identities"]=@[ID(@"serial",@"SLES99999",@"ps2-disc-serial")];CHECK(!Matches479(catalog,missing).count,"unknown detected serial never falls back to same-title other editions");
  NSMutableDictionary *manual=[identity mutableCopy];manual[@"identities"]=@[];CHECK(Matches479(catalog,manual).count>2,"unidentified explicit candidates remain available without an invented identity");
  NSArray *first=Codes(catalog,found[0],YES);NSUInteger count=fetches;NSArray *again=Codes(catalog,found[0],YES);
  CHECK(first==again && fetches==count,"repeat reads reuse decoded programs and fetch nothing");
  NSString *path=[root stringByAppendingPathComponent:[NSString stringWithFormat:@"files/%@.json",found[0][@"sha256"]]];
  NSMutableData *corrupt=[[NSData dataWithContentsOfFile:path] mutableCopy];((char *)corrupt.mutableBytes)[corrupt.length-2]^=1;[corrupt writeToFile:path atomically:YES];
  CHECK(Codes(catalog,found[0],YES).count==1,"corrupted bytes cannot bypass SHA verification through a warm decode cache");
  CHECK([[NSData dataWithContentsOfFile:path] length]==[found[0][@"size"] unsignedIntegerValue],"repair restores the exact source chunk");
}
static NSDictionary *Large479(NSString *repo,NSString *root,BOOL baseline) {
  NSString *index=[repo stringByAppendingPathComponent:@"packages/neo_cheat_catalog/ios/Resources/manifest.json.gz"];
  Catalogue479Probe *catalog=[Catalogue479Probe new];catalog.storageDirectory=root;catalog.bundledDirectory=index.stringByDeletingLastPathComponent;
  NSDictionary *manifest=[catalog validatedManifest:[NSData dataWithContentsOfFile:index] error:nil];CHECK([manifest[@"games"] count]==51652,"benchmark uses the exact delivered 478 publication");
  NSString *files=[root stringByAppendingPathComponent:@"files"];[NSFileManager.defaultManager createDirectoryAtPath:files withIntermediateDirectories:YES attributes:nil error:nil];
  // Sparse metadata fixture for the other editions. Only the two actual game
  // chunks below contain programs; this is not a claim of a full gameplay test.
  for(NSDictionary *game in manifest[@"games"]) {@autoreleasepool{
    NSString *p=[files stringByAppendingPathComponent:[game[@"sha256"] stringByAppendingString:@".json"]];
    int fd=open(p.fileSystemRepresentation,O_CREAT|O_RDWR,0600);CHECK(fd>=0,"create metadata fixture");CHECK(ftruncate(fd,[game[@"size"] longLongValue])==0,"set real published metadata length");close(fd);
  }}
  NSMutableArray *identities=[NSMutableArray array];
  for(NSString *name in @[@"bladestorm-bles00113.json",@"gow2-scus97481.json"]) {
    NSData *data=[NSData dataWithContentsOfFile:[repo stringByAppendingPathComponent:[@"test/fixtures/cheats477/" stringByAppendingString:name]]];NSDictionary *chunk=[NSJSONSerialization JSONObjectWithData:data options:0 error:nil];
    NSDictionary *game=chunk[@"game"];CHECK(game && data.length,"actual published target chunk exists");
    [data writeToFile:[files stringByAppendingPathComponent:[Hash(data) stringByAppendingString:@".json"]] atomically:YES];[identities addObject:game];
  }
  catalog.fetch=^(NSURL *url,NSUInteger limit,void(^done)(NSData*,NSError*)){CHECK(NO,"installed lookup stays offline");};
  NSTimeInterval start=NSDate.timeIntervalSinceReferenceDate;NSDictionary *state=Load(catalog);NSTimeInterval cold=NSDate.timeIntervalSinceReferenceDate-start;
  CHECK([state[@"installation_state"] isEqual:@"complete"],"all published metadata recovers as one common installation");
  NSUInteger initialChecks=catalog.fileChecks;
  if(!baseline)CHECK(initialChecks<32,"opening a full catalogue does not stat every game separately");
  else CHECK(initialChecks>=51652,"baseline benchmark measures the real full-directory stat pass");
  start=NSDate.timeIntervalSinceReferenceDate;NSUInteger rows=0;
  for(NSUInteger i=0;i<12;i++) {@autoreleasepool{rows+=Matches479(catalog,identities[i%2]).count;}}
  NSTimeInterval warm=NSDate.timeIntervalSinceReferenceDate-start;
  for(NSDictionary *identity in identities) {
    NSArray *matches=Matches479(catalog,identity);BOOL target=NO;
    for(NSDictionary *g in matches)if([g[@"id"] isEqual:identity[@"id"]]){CHECK(Codes(catalog,g,YES).count>0,"exact published target remains readable");target=YES;}
    CHECK(target,"both actual PS2 and PS3 targets remain discoverable");
    if([identity[@"system"] isEqual:@"ps3"]){NSMutableDictionary *newVersion=[identity mutableCopy];newVersion[@"revision"]=@"01.01";
      CHECK(!Matches479(catalog,newVersion).count,"real BLES00113 01.00 programs are never relabeled as 01.01");}
  }
  return @{@"baseline":@(baseline),@"manifestRows":@51652,@"coldLoadSeconds":@(cold),@"warm12QueriesSeconds":@(warm),
    @"initialPerFileChecks":@(initialChecks),@"totalPerFileChecks":@(catalog.fileChecks),@"matchedRowsAcross12Queries":@(rows)};
}
int main(int argc,const char *argv[]) {@autoreleasepool{
  CHECK(argc>=2,"repository argument");BOOL baseline=argc>2;
  NSString *repo=@(argv[1]),*root=[NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  Editions479([root stringByAppendingPathComponent:@"editions"],baseline);
  NSDictionary *metrics=Large479(repo,[root stringByAppendingPathComponent:@"large"],baseline);
  NSData *json=Bytes(metrics);printf("METRICS479 %s\n",[[[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding] UTF8String]);
  [NSFileManager.defaultManager removeItemAtPath:root error:nil];
  printf("PASS 479 compatible edition selection, bounded installed lookup, verified cache; baseline=%d\n",baseline);
  return 0;
}}

