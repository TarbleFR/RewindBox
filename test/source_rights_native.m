#import <Foundation/Foundation.h>
#import <CommonCrypto/CommonDigest.h>
#import "NeoUnifiedCheatCatalog.h"
@interface NeoUnifiedCheatCatalog (RightsTest)
- (NSArray *)validatedCheats:(NSData *)data game:(NSDictionary *)game error:(NSError **)error;
@end
static void Require(BOOL value) { if(!value)abort(); }
int main(void) { @autoreleasepool {
  NSDictionary *game=@{@"id":@"rights",@"system":@"gb"};
  NSMutableArray *programs=[NSMutableArray array];
  for(NSString *kind in @[@"source_id",@"import_source_id",@"other"]) {
    [programs addObject:@{@"id":kind,@"name":kind,@"code":@"01000000",@"handler":@0,
      @"status":@"available",@"provenance":@[@{kind:@"pokemonfrance"}],@"enabled":@YES}];
  }
  NSData *bytes=[NSJSONSerialization dataWithJSONObject:@{@"schema_version":@1,@"game":game,@"cheats":programs} options:0 error:nil];
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];CC_SHA256(bytes.bytes,(CC_LONG)bytes.length,digest);
  NSMutableString *hash=[NSMutableString string];for(int i=0;i<CC_SHA256_DIGEST_LENGTH;i++)[hash appendFormat:@"%02x",digest[i]];
  NSDictionary *meta=@{@"id":@"rights",@"system":@"gb",@"sha256":hash};
  NeoUnifiedCheatCatalog *catalog=[NeoUnifiedCheatCatalog new];
  for(int i=0;i<2;i++) {
    NSError *error=nil;NSArray *result=[catalog validatedCheats:bytes game:meta error:&error];
    Require(!error && result.count==1);Require([result[0][@"id"] isEqualToString:@"other"]);
    Require(![result[0][@"enabled"] boolValue]);Require([result[0][@"provenance"] count]==1);
  }
  puts("Source rights: old downloaded programs withheld, unrelated provenance retained, cache and default-off checks passed.");
}return 0;}
