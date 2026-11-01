#import <XCTest/XCTest.h>
#import "RBRALegacyMigration.h"

@interface RBRALegacyMigrationTests : XCTestCase
@property(nonatomic, copy) NSString *directory;
@end

@implementation RBRALegacyMigrationTests
- (void)setUp {
  [super setUp];
  self.directory = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
  NSError *error = nil;
  XCTAssertTrue([NSFileManager.defaultManager createDirectoryAtPath:self.directory
    withIntermediateDirectories:YES attributes:nil error:&error]);
  XCTAssertNil(error);
}
- (void)tearDown {
  NSError *error = nil;
  XCTAssertTrue([NSFileManager.defaultManager removeItemAtPath:self.directory error:&error]);
  XCTAssertNil(error);
  [super tearDown];
}
- (NSString *)file:(NSString *)contents {
  NSString *path = [self.directory stringByAppendingPathComponent:@"legacy.ini"];
  NSError *error = nil;
  XCTAssertTrue([contents writeToFile:path atomically:YES encoding:NSUTF8StringEncoding error:&error]);
  XCTAssertNil(error);
  return path;
}
- (void)testINIUnicodeBOMCommentsQuotesEqualsAndCaseInsensitiveSection {
  NSString *path = [self file:@"\uFEFF[Unrelated]\nUsername=ignore\n"
    "[ aChIeVeMeNtS ] ; section comment\n"
    "; Username=ignore\n# Token=ignore\n"
    " USERNAME = \"Élise 日本\"\n Token = \"abc==#;value\"\n eNaBlEd = On\n"];
  NSData *before = [NSData dataWithContentsOfFile:path];
  NSError *error = nil;
  NSDictionary *values = [RBRALegacyMigration achievementValuesAtPath:path error:&error];
  XCTAssertNil(error);
  XCTAssertEqualObjects(values[@"username"], @"Élise 日本");
  XCTAssertEqualObjects(values[@"token"], @"abc==#;value");
  XCTAssertEqualObjects(values[@"enabled"], @"On");
  XCTAssertEqualObjects([NSData dataWithContentsOfFile:path], before);
  XCTAssertThrowsSpecificNamed([(NSMutableDictionary *)values setObject:@"x" forKey:@"token"], NSException, NSInvalidArgumentException);
}
- (void)testUnknownAndMalformedHeadersCloseTheAchievementSection {
  NSString *path = [self file:@"[Achievements]\nUsername=correct\nToken=correct-token\n"
    "[Other] ; trailing comment\nUsername=wrong\nToken=wrong-token\n"
    "[Achievements] # supported\nEnabled=true\n"
    "[Malformed\nToken=must-not-leak\n"
    "[Achievements] invalid suffix\nUsername=also-wrong\n"];
  NSError *error = nil;
  NSDictionary *values = [RBRALegacyMigration achievementValuesAtPath:path error:&error];
  XCTAssertNil(error);
  XCTAssertEqualObjects(values, (@{@"username": @"correct", @"token": @"correct-token", @"enabled": @"true"}));
}
- (void)testMissingFileIsEmptyButDirectoryInvalidEncodingAndOversizeAreErrors {
  NSError *error = nil;
  NSString *missing = [self.directory stringByAppendingPathComponent:@"missing.ini"];
  XCTAssertEqualObjects([RBRALegacyMigration achievementValuesAtPath:missing error:&error], @{});
  XCTAssertNil(error);
  XCTAssertNil([RBRALegacyMigration achievementValuesAtPath:self.directory error:&error]);
  XCTAssertNotNil(error);
  NSString *path = [self.directory stringByAppendingPathComponent:@"invalid.ini"];
  const unsigned char invalid[] = {0xff, 0xfe, 0xff};
  XCTAssertTrue([[NSData dataWithBytes:invalid length:sizeof(invalid)] writeToFile:path atomically:YES]);
  error = nil; XCTAssertNil([RBRALegacyMigration achievementValuesAtPath:path error:&error]); XCTAssertNotNil(error);
  XCTAssertTrue([[NSMutableData dataWithLength:4 * 1024 * 1024 + 1] writeToFile:path atomically:YES]);
  error = nil; XCTAssertNil([RBRALegacyMigration achievementValuesAtPath:path error:&error]); XCTAssertNotNil(error);
}
- (void)testUnreadableExistingFileIsNotTreatedAsAbsent {
  NSString *path = [self file:@"[Achievements]\nUsername=player\nToken=fixture\n"];
  NSError *error = nil;
  XCTAssertTrue([NSFileManager.defaultManager setAttributes:@{NSFilePosixPermissions: @0} ofItemAtPath:path error:&error]);
  XCTAssertNil(error);
  NSDictionary *values = [RBRALegacyMigration achievementValuesAtPath:path error:&error];
  XCTAssertNil(values); XCTAssertNotNil(error);
  XCTAssertTrue([NSFileManager.defaultManager setAttributes:@{NSFilePosixPermissions: @384} ofItemAtPath:path error:nil]);
}
- (void)testCaseInsensitiveIdentityAndEqualPoliciesMergeTheirSources {
  NSArray *candidates = [RBRALegacyMigration candidatesWithLibretro:@{@"username": @" Player ", @"token": @"libretro-token"}
    libretroEnabled:@YES dolphin:@{@"username": @"player", @"token": @"dolphin-token"}
    dolphinValues:@{@"enabled": @"true", @"hardcoreenabled": @"false"}
    armsx2Values:@{@"username": @"PLAYER", @"enabled": @"yes", @"challengemode": @"off"}
    armsx2Secrets:@{@"token": @"armsx2-token"}];
  XCTAssertEqual(candidates.count, 1u);
  XCTAssertEqualObjects(candidates.firstObject[@"username"], @"Player");
  XCTAssertEqualObjects(candidates.firstObject[@"sources"], (@[@"libretro", @"Dolphin", @"ARMSX2"]));
  XCTAssertEqualObjects(candidates.firstObject[@"enabled"], @YES);
  XCTAssertEqualObjects(candidates.firstObject[@"hardcore"], @NO);
}
- (void)testDifferentHardcoreOrEnabledPolicyRequiresAnExplicitChoice {
  NSArray *hardcore = [RBRALegacyMigration candidatesWithLibretro:@{@"username": @"player", @"token": @"one"}
    libretroEnabled:@YES dolphin:@{@"username": @"PLAYER", @"token": @"two"}
    dolphinValues:@{@"enabled": @"true", @"hardcoreenabled": @"true"}
    armsx2Values:@{} armsx2Secrets:@{}];
  XCTAssertEqual(hardcore.count, 2u);
  XCTAssertEqualObjects(hardcore[0][@"hardcore"], @NO); XCTAssertEqualObjects(hardcore[1][@"hardcore"], @YES);
  NSArray *enabled = [RBRALegacyMigration candidatesWithLibretro:@{@"username": @"player", @"token": @"one"}
    libretroEnabled:@NO dolphin:@{@"username": @"PLAYER", @"token": @"two"}
    dolphinValues:@{@"enabled": @"true", @"hardcoreenabled": @"false"}
    armsx2Values:@{} armsx2Secrets:@{}];
  XCTAssertEqual(enabled.count, 2u);
}
- (void)testDolphinKeychainWinsForSameIdentityButDifferentINIIdentityIsAChoice {
  NSDictionary *keychain = @{@"username": @"player", @"token": @"keychain-token"};
  NSArray *same = [RBRALegacyMigration candidatesWithLibretro:nil libretroEnabled:nil dolphin:keychain
    dolphinValues:@{@"username": @"PLAYER", @"apitoken": @"old-ini-token", @"enabled": @"true"}
    armsx2Values:@{} armsx2Secrets:@{}];
  XCTAssertEqual(same.count, 1u); XCTAssertEqualObjects(same.firstObject[@"token"], @"keychain-token");
  NSArray *different = [RBRALegacyMigration candidatesWithLibretro:nil libretroEnabled:nil dolphin:keychain
    dolphinValues:@{@"username": @"other-player", @"apitoken": @"other-token", @"enabled": @"true"}
    armsx2Values:@{} armsx2Secrets:@{}];
  XCTAssertEqual(different.count, 2u);
  NSSet *usernames = [NSSet setWithArray:[different valueForKey:@"username"]];
  XCTAssertEqualObjects(usernames, ([NSSet setWithArray:@[@"player", @"other-player"]]));
}
- (void)testARMSX2SecretsTakePriorityWithLegacyBaseTokenFallback {
  NSDictionary *values = @{@"username": @"player", @"token": @"old-base-token", @"enabled": @"1", @"challengemode": @"true"};
  NSArray *preferred = [RBRALegacyMigration candidatesWithLibretro:nil libretroEnabled:nil dolphin:nil
    dolphinValues:@{} armsx2Values:values armsx2Secrets:@{@"token": @"secrets-token"}];
  XCTAssertEqual(preferred.count, 1u); XCTAssertEqualObjects(preferred.firstObject[@"token"], @"secrets-token");
  NSArray *fallback = [RBRALegacyMigration candidatesWithLibretro:nil libretroEnabled:nil dolphin:nil
    dolphinValues:@{} armsx2Values:values armsx2Secrets:@{}];
  XCTAssertEqual(fallback.count, 1u); XCTAssertEqualObjects(fallback.firstObject[@"token"], @"old-base-token");
  XCTAssertEqualObjects(fallback.firstObject[@"hardcore"], @YES);
}
- (void)testAbsentLegacyDefaultIsOffAndIncompleteAccountsAreNotCandidates {
  NSArray *missingDefault = [RBRALegacyMigration candidatesWithLibretro:@{@"username": @"player", @"token": @"fixture"}
    libretroEnabled:nil dolphin:nil dolphinValues:@{} armsx2Values:@{} armsx2Secrets:@{}];
  XCTAssertEqual(missingDefault.count, 1u); XCTAssertEqualObjects(missingDefault.firstObject[@"enabled"], @NO);
  NSArray *incomplete = [RBRALegacyMigration candidatesWithLibretro:@{@"username": @"player"}
    libretroEnabled:@YES dolphin:@{@"token": @"fixture"} dolphinValues:@{}
    armsx2Values:@{@"username": @" "} armsx2Secrets:@{@"token": @"fixture"}];
  XCTAssertEqual(incomplete.count, 0u);
}
@end
