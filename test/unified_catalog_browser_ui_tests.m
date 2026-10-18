// Targeted UIKit tests. No emulator core, ROM, BIOS, network or IPA is used.
#import <XCTest/XCTest.h>
#import <UIKit/UIKit.h>
#import <objc/runtime.h>
#import "NeoUnifiedCheatBrowser.h"
#import "Public/NeoUnifiedCheatCatalog.h"
#import "LibretroCheatMenu.h"
#import "LibretroCheats.h"
#import "LibretroSessionMenu.h"

static NeoUnifiedCheatCatalog *NUCBInjectedShared;
@interface NeoUnifiedCheatCatalog (UITestSingleton)
+ (instancetype)nucbTestSharedCatalog;
@end
@implementation NeoUnifiedCheatCatalog (UITestSingleton)
+ (instancetype)nucbTestSharedCatalog { return NUCBInjectedShared; }
@end
static void NUCBExchangeSingleton(void) {
    method_exchangeImplementations(class_getClassMethod(NeoUnifiedCheatCatalog.class, @selector(sharedCatalog)),
        class_getClassMethod(NeoUnifiedCheatCatalog.class, @selector(nucbTestSharedCatalog)));
}

@interface LibretroCheatMenu (UnifiedBrowserTests)
- (BOOL)acceptsUnifiedProgram:(NSDictionary *)program;
- (BOOL)appendUnifiedProgram:(NSDictionary *)program index:(NSDictionary *)index visited:(NSMutableSet *)visited
    visiting:(NSMutableSet *)visiting result:(NSMutableArray *)result depth:(NSUInteger)depth;
- (NSDictionary *)unifiedRecordForGame:(NSDictionary *)game programs:(NSArray *)programs;
- (void)presentUnifiedFrom:(UIViewController *)page;
- (BOOL)verified:(NSDictionary *)record;
- (void)merge:(NSArray *)records;
@end

@interface NeoUnifiedCheatBrowser (BrowserTests)
- (instancetype)initWithIdentity:(NSDictionary *)identity engine:(NSString *)engine locale:(NSString *)locale
    accepts:(BOOL (^)(NSDictionary *))accepts importHandler:(void (^)(NSDictionary *, NSArray *, void (^)(NSError *)))handler;
- (void)setProgramsForDisplay:(NSArray *)programs;
- (NSArray *)importClosureForProgram:(NSDictionary *)program reason:(NSString **)reason;
- (NSString *)reasonForProgram:(NSDictionary *)program;
- (NSDictionary *)catalogueSizesForManifest:(NSDictionary *)manifest;
- (void)chooseGame:(NSDictionary *)game;
- (void)openGame:(NSDictionary *)game;
- (void)closeBrowser;
@end

@interface NUCBFakeCatalog : NeoUnifiedCheatCatalog
@property(nonatomic, copy) NSArray *rows;
@property(nonatomic, copy) NSArray *codes;
@property(nonatomic, copy) NSDictionary *summaryFixture;
@property(nonatomic, copy) NSDictionary *chosenGame;
@property(nonatomic, copy) void (^installProgress)(NSDictionary *);
@property(nonatomic, copy) void (^installCompletion)(NSDictionary *, NSError *);
@property(nonatomic, copy) void (^cheatsCompletion)(NSArray *, NSError *);
@property(nonatomic, copy) void (^lateImportCompletion)(NSError *);
@property(nonatomic) BOOL holdCheats;
@property(nonatomic) NSUInteger installs;
@property(nonatomic) NSUInteger lookups;
@end
@implementation NUCBFakeCatalog
- (void)loadWithCompletion:(void (^)(NSDictionary *, NSError *))completion {
    completion(self.summaryFixture ?: @{@"installed_games": @0, @"installed_packs": @0, @"total_packs": @2, @"total_bytes": @1000}, nil);
}
- (void)gamesForIdentity:(NSDictionary *)identity completion:(void (^)(NSArray *, NSError *))completion { completion(self.rows ?: @[], nil); }
- (void)searchGames:(NSString *)query system:(NSString *)system completion:(void (^)(NSArray *, NSError *))completion { completion(self.rows ?: @[], nil); }
- (void)installAllWithProgress:(void (^)(NSDictionary *))progress completion:(void (^)(NSDictionary *, NSError *))completion {
    self.installs++;
    self.installProgress = progress;
    self.installCompletion = completion;
}
- (void)cheatsForGame:(NSDictionary *)game completion:(void (^)(NSArray *, NSError *))completion {
    self.lookups++;
    self.chosenGame = game;
    if (self.holdCheats) self.cheatsCompletion = completion;
    else completion(self.codes ?: @[], nil);
}
@end

@interface UnifiedCatalogueBrowserTests : XCTestCase
@property(nonatomic, strong) UIWindow *window;
@property(nonatomic, strong) NUCBFakeCatalog *catalog;
@property(nonatomic, strong) NeoUnifiedCheatBrowser *browser;
@property(nonatomic, strong) UINavigationController *navigation;
@property(nonatomic, strong) NSMutableArray<NSString *> *temporaryFolders;
@end
@implementation UnifiedCatalogueBrowserTests
- (void)setUp {
    [super setUp];
    [UIView setAnimationsEnabled:NO];
    self.window = [[UIWindow alloc] initWithFrame:UIScreen.mainScreen.bounds];
    self.catalog = [NUCBFakeCatalog new];
    NUCBInjectedShared = self.catalog;
    NUCBExchangeSingleton();
    self.temporaryFolders = [NSMutableArray array];
}
- (void)tearDown {
    [self.browser closeBrowser];
    self.window.hidden = YES;
    self.window.rootViewController = nil;
    self.navigation = nil;
    self.browser = nil;
    self.catalog = nil;
    NUCBExchangeSingleton();
    NUCBInjectedShared = nil;
    for (NSString *folder in self.temporaryFolders) [NSFileManager.defaultManager removeItemAtPath:folder error:nil];
    self.window = nil;
    [UIView setAnimationsEnabled:YES];
    [super tearDown];
}
- (NSDictionary *)identity { return @{@"system": @"gb", @"title": @"Probe", @"regions": @[@"France"], @"languages": @[@"Fr"]}; }
- (NSDictionary *)game { return @{@"id": @"probe-fr", @"system": @"gb", @"title": @"Probe (France)", @"regions": @[@"France"], @"languages": @[@"Fr"], @"revision": @"", @"identities": @[]}; }
- (NSDictionary *)program:(NSString *)identifier dependencies:(NSArray *)dependencies {
    return @{@"id": identifier, @"name": identifier, @"status": @"available", @"code": @"010100C0\n010200C1", @"lines": @[@"010100C0", @"010200C1"], @"dialect": @"gb-gameshark", @"handler": @0, @"dependencies": dependencies, @"parameters": @[], @"enabled": @YES, @"provenance": @[@{@"source_id": @"author-source", @"author": @"Original author", @"url": @"https://example.invalid/source"}]};
}
- (NeoUnifiedCheatBrowser *)makeBrowser:(NSInteger)page programs:(NSArray *)programs
    handler:(void (^)(NSDictionary *, NSArray *, void (^)(NSError *)))handler {
    NeoUnifiedCheatBrowser *browser = [[NeoUnifiedCheatBrowser alloc] initWithIdentity:[self identity] engine:@"test" locale:@"fr"
        accepts:^BOOL(NSDictionary *program) { return [program[@"dialect"] isEqual:@"gb-gameshark"]; }
        importHandler:handler ?: ^(NSDictionary *game, NSArray *codes, void (^done)(NSError *)) { done(nil); }];
    [browser setValue:self.catalog forKey:@"catalog"];
    [browser setValue:@(page) forKey:@"page"];
    [browser setValue:[self game] forKey:@"game"];
    [browser setProgramsForDisplay:programs ?: @[]];
    if (programs.count) [browser setValue:programs.lastObject forKey:@"program"];
    return browser;
}
- (void)host:(NeoUnifiedCheatBrowser *)browser {
    self.browser = browser;
    self.navigation = [[UINavigationController alloc] initWithRootViewController:browser];
    self.window.rootViewController = self.navigation;
    [self.window makeKeyAndVisible];
    [self.navigation loadViewIfNeeded];
    [browser loadViewIfNeeded];
    [self.window layoutIfNeeded];
}
- (void)waitFor:(BOOL (^)(void))condition {
    XCTNSPredicateExpectation *expected = [[XCTNSPredicateExpectation alloc] initWithPredicate:[NSPredicate predicateWithBlock:^BOOL(id object, NSDictionary *bindings) { return condition(); }] object:nil];
    [self waitForExpectations:@[expected] timeout:5];
}
- (void)selectSection:(NSInteger)section row:(NSInteger)row {
    [self.browser tableView:self.browser.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:row inSection:section]];
}
- (void)dismissAlert:(UIAlertController *)alert action:(UIAlertAction *)action {
    void (^handler)(UIAlertAction *) = [action valueForKey:@"handler"];
    [alert dismissViewControllerAnimated:NO completion:^{ if (handler) handler(action); }];
}

- (void)testTwelveRealTranslationsAndTraditionalChineseSelection {
    for (NSString *locale in @[@"en", @"fr", @"es", @"de", @"it", @"pt", @"ru", @"id", @"zh", @"zh_Hant", @"ja", @"ko"]) {
        for (NSString *key in @[@"unifiedCatalogue", @"downloadAll", @"editionConfirmTitle", @"dependenciesExclusive", @"importDoneMessage", @"cataloguePart", @"technicalDetails"]) {
            XCTAssertNotEqualObjects([NeoUnifiedCheatBrowser localizedText:key locale:locale], key);
        }
    }
    XCTAssertEqualObjects([NeoUnifiedCheatBrowser localizedText:@"downloadAll" locale:@"zh-TW"], [NeoUnifiedCheatBrowser localizedText:@"downloadAll" locale:@"zh_Hant"]);
    XCTAssertEqualObjects([NeoUnifiedCheatBrowser localizedText:@"downloadAll" locale:@"zh-Hant-HK"], [NeoUnifiedCheatBrowser localizedText:@"downloadAll" locale:@"zh_Hant"]);
    XCTAssertNotEqualObjects([NeoUnifiedCheatBrowser localizedText:@"downloadAll" locale:@"zh-Hant"], [NeoUnifiedCheatBrowser localizedText:@"downloadAll" locale:@"zh-Hans"]);
}
- (void)testDependencyClosurePreservesEveryLineAndDisablesWholePrograms {
    NSDictionary *master = [self program:@"master" dependencies:@[]];
    NSDictionary *body = [self program:@"body" dependencies:@[@"master"]];
    self.browser = [self makeBrowser:2 programs:@[master, body] handler:nil];
    NSString *reason = nil;
    NSArray *closure = [self.browser importClosureForProgram:body reason:&reason];
    XCTAssertNil(reason); XCTAssertEqual(closure.count, 2U);
    XCTAssertEqualObjects(closure[0][@"id"], @"master"); XCTAssertEqualObjects(closure.lastObject[@"id"], @"body");
    for (NSDictionary *program in closure) {
        XCTAssertEqualObjects(program[@"enabled"], @NO);
        XCTAssertEqualObjects(program[@"code"], body[@"code"]);
        XCTAssertEqualObjects(program[@"lines"], body[@"lines"]);
    }
    XCTAssertEqualObjects(master[@"enabled"], @YES); XCTAssertEqualObjects(body[@"enabled"], @YES);
}
- (void)testInvalidUnresolvedUnsupportedAndIncompleteDependenciesCannotImport {
    for (NSString *status in @[@"invalid", @"unresolved", @"requires_engine", @"other"]) {
        NSMutableDictionary *program = [[self program:@"body" dependencies:@[]] mutableCopy]; program[@"status"] = status;
        self.browser = [self makeBrowser:2 programs:@[program] handler:nil];
        XCTAssertNotNil([self.browser reasonForProgram:program]);
    }
    NSMutableDictionary *program = [[self program:@"body" dependencies:@[]] mutableCopy];
    program[@"parameters"] = @[@{@"name": @"XXXX"}];
    self.browser = [self makeBrowser:2 programs:@[program] handler:nil];
    XCTAssertEqualObjects([self.browser reasonForProgram:program], @"parametersRequired");
    program[@"parameters"] = @[]; program[@"dialect"] = @"unknown";
    [self.browser setProgramsForDisplay:@[program]]; XCTAssertEqualObjects([self.browser reasonForProgram:program], @"unsupported");
    NSDictionary *missing = [self program:@"body" dependencies:@[@"missing"]];
    [self.browser setProgramsForDisplay:@[missing]]; XCTAssertEqualObjects([self.browser reasonForProgram:missing], @"dependenciesMissing");
    NSDictionary *a = [self program:@"a" dependencies:@[@"b"]], *b = [self program:@"b" dependencies:@[@"a"]];
    [self.browser setProgramsForDisplay:@[a, b]]; XCTAssertEqualObjects([self.browser reasonForProgram:a], @"dependenciesCycle");
    NSMutableDictionary *x = [[self program:@"x" dependencies:@[]] mutableCopy], *y = [[self program:@"y" dependencies:@[@"x"]] mutableCopy];
    x[@"exclusive_group"] = @"one-choice"; y[@"exclusive_group"] = @"one-choice";
    [self.browser setProgramsForDisplay:@[x, y]]; XCTAssertEqualObjects([self.browser reasonForProgram:y], @"dependenciesExclusive");
    [self.browser setProgramsForDisplay:@[x, x]]; XCTAssertEqualObjects([self.browser reasonForProgram:x], @"invalid");
}
- (void)testCandidateCannotDownloadProgramsBeforeExplicitEditionConfirmation {
    self.catalog.rows = @[[self game]]; self.catalog.codes = @[[self program:@"body" dependencies:@[]]];
    [self host:[self makeBrowser:0 programs:nil handler:nil]];
    [self selectSection:1 row:1];
    UIAlertController *alert = (id)self.browser.presentedViewController;
    XCTAssertTrue([alert isKindOfClass:UIAlertController.class]); XCTAssertEqual(self.catalog.lookups, 0U);
    XCTAssertTrue([alert.message containsString:@"France"]);
    [self dismissAlert:alert action:alert.actions.firstObject];
    XCTAssertEqual(self.catalog.lookups, 0U);
    [self selectSection:1 row:1]; alert = (id)self.browser.presentedViewController;
    [self dismissAlert:alert action:alert.actions.lastObject];
    [self waitFor:^BOOL { return self.navigation.viewControllers.count == 2; }];
    XCTAssertEqual(self.catalog.lookups, 1U);
    XCTAssertEqualObjects(self.catalog.chosenGame[@"match"], @"candidate");
    XCTAssertEqualObjects(self.catalog.chosenGame[@"edition_confirmed"], @YES);
}
- (void)testExactTypedROMIdentityOpensCodesWithoutEditionConfirmation {
    NSArray *identities = @[@{@"type": @"md5", @"value": @"0123456789abcdef0123456789abcdef", @"scheme": @"rom-full"}];
    NSMutableDictionary *identity = [[self identity] mutableCopy], *game = [[self game] mutableCopy];
    identity[@"identities"] = identities; game[@"identities"] = identities;
    self.catalog.rows = @[game]; self.catalog.codes = @[[self program:@"body" dependencies:@[]]];
    NeoUnifiedCheatBrowser *browser = [self makeBrowser:0 programs:nil handler:nil];
    [browser setValue:identity forKey:@"identity"];
    [self host:browser]; [self selectSection:1 row:1];
    XCTAssertEqual(self.catalog.lookups, 1U); XCTAssertNil(browser.presentedViewController);
    XCTAssertEqual(self.navigation.viewControllers.count, 2U);
    XCTAssertEqualObjects(self.catalog.chosenGame[@"match"], @"exact");
    XCTAssertNil(self.catalog.chosenGame[@"edition_confirmed"]);
}
- (void)testKnownTypedHashConflictIsReadOnlyAndCannotBeConfirmedOrImported {
    NSMutableDictionary *identity = [[self identity] mutableCopy], *game = [[self game] mutableCopy];
    identity[@"identities"] = @[@{@"type": @"md5", @"value": @"0123456789abcdef0123456789abcdef", @"scheme": @"rom-full"}];
    game[@"identities"] = @[@{@"type": @"md5", @"value": @"fedcba9876543210fedcba9876543210", @"scheme": @"rom-full"}];
    XCTAssertTrue([NeoUnifiedCheatCatalog gameHasConflict:game identity:identity]);
    XCTAssertFalse([NeoUnifiedCheatCatalog gameHasConflict:[self game] identity:[self identity]]);
    self.catalog.rows = @[game]; self.catalog.codes = @[[self program:@"body" dependencies:@[]]];
    __block NSUInteger imports = 0;
    NeoUnifiedCheatBrowser *browser = [self makeBrowser:0 programs:nil handler:^(NSDictionary *chosen, NSArray *programs, void (^done)(NSError *)) { imports++; done(nil); }];
    [browser setValue:identity forKey:@"identity"];
    [self host:browser]; [self selectSection:1 row:1];
    XCTAssertNil(browser.presentedViewController);
    XCTAssertEqual(self.navigation.viewControllers.count, 2U);
    XCTAssertEqualObjects(self.catalog.chosenGame[@"match"], @"conflict");
    XCTAssertEqualObjects(self.catalog.chosenGame[@"edition_confirmed"], @NO);
    NeoUnifiedCheatBrowser *codes = (id)self.navigation.topViewController;
    XCTAssertEqualObjects([codes reasonForProgram:self.catalog.codes.firstObject], @"editionMismatch");
    [codes tableView:codes.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:1]];
    self.browser = (id)self.navigation.topViewController;
    UITableViewCell *import = [self.browser tableView:self.browser.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:3]];
    XCTAssertTrue((import.accessibilityTraits & UIAccessibilityTraitNotEnabled) != 0);
    XCTAssertEqualObjects(import.accessibilityValue, [NeoUnifiedCheatBrowser localizedText:@"editionMismatch" locale:@"fr"]);
    [self selectSection:3 row:0];
    XCTAssertEqual(imports, 0U); XCTAssertNil(self.browser.presentedViewController);
}
- (void)testAllPartsRemainVisibleWithExplicitPartNumbers {
    NSMutableDictionary *one = [[self game] mutableCopy], *two = [[self game] mutableCopy];
    one[@"part"] = @1; one[@"parts"] = @2; one[@"identity_group"] = @"probe";
    two[@"id"] = @"probe-fr-part2"; two[@"part"] = @2; two[@"parts"] = @2; two[@"identity_group"] = @"probe";
    self.catalog.rows = @[one, two];
    [self host:[self makeBrowser:0 programs:nil handler:nil]];
    XCTAssertEqual([self.browser tableView:self.browser.tableView numberOfRowsInSection:1], 3);
    UITableViewCell *cell = [self.browser tableView:self.browser.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:2 inSection:1]];
    XCTAssertTrue([cell.accessibilityValue containsString:@"2 / 2"]);
}
- (void)testSingleDownloadActionShowsGlobalProgressAndRetriesPartialFailure {
    [self host:[self makeBrowser:0 programs:nil handler:nil]];
    [self selectSection:0 row:0]; [self selectSection:0 row:0]; XCTAssertEqual(self.catalog.installs, 1U);
    self.catalog.installProgress(@{@"total_packs": @2, @"completed_packs": @1, @"failed_packs": @0, @"total_bytes": @1000, @"completed_bytes": @250});
    UITableViewCell *progress = [self.browser tableView:self.browser.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:1 inSection:0]];
    XCTAssertEqualWithAccuracy([[progress valueForKey:@"progressView"] progress], 0.25, 0.001);
    XCTAssertTrue([[[progress valueForKey:@"progressLabel"] text] containsString:@"1 / 2"]);
    NSError *failure = [NSError errorWithDomain:@"ProbeDownload" code:17 userInfo:@{NSLocalizedDescriptionKey:@"raw technical failure"}];
    self.catalog.installCompletion(@{@"installed_games": @3, @"total_packs": @2, @"completed_packs": @2, @"failed_packs": @[@"failed"], @"total_bytes": @1000, @"completed_bytes": @500}, failure);
    XCTAssertEqual([self.browser tableView:self.browser.tableView numberOfRowsInSection:0], 4);
    XCTAssertEqual([[[self.browser valueForKey:@"summary"] objectForKey:@"installed_games"] unsignedIntegerValue], 3U);
    UIAlertController *alert = (id)self.browser.presentedViewController;
    XCTAssertEqualObjects(alert.title, [NeoUnifiedCheatBrowser localizedText:@"downloadFailed" locale:@"fr"]);
    XCTAssertTrue([alert.message containsString:@"raw technical failure"]);
    [alert dismissViewControllerAnimated:NO completion:nil];
    [self selectSection:0 row:3]; XCTAssertEqual(self.catalog.installs, 2U);
    self.catalog.installCompletion(@{@"installed_games": @6, @"total_packs": @2, @"completed_packs": @2, @"failed_packs": @[], @"total_bytes": @1000, @"completed_bytes": @1000}, nil);
    XCTAssertEqual([self.browser tableView:self.browser.tableView numberOfRowsInSection:0], 3);
}
- (void)testDownloadActionAnnouncesCompressedDownloadAndExtractedPlusCachedStorage {
    self.catalog.summaryFixture = @{@"installed_games": @0, @"total_packs": @2, @"total_bytes": @9999,
        @"packs": @[@{@"size": @128000}, @{@"size": @256000}],
        @"games": @[@{@"size": @1048576}, @{@"size": @2097152}]};
    [self host:[self makeBrowser:0 programs:nil handler:nil]];
    NSDictionary *totals = [self.browser catalogueSizesForManifest:self.catalog.summaryFixture];
    XCTAssertEqualObjects(totals[@"download_bytes"], @384000);
    XCTAssertEqualObjects(totals[@"offline_bytes"], @3529728);
    UITableViewCell *action = [self.browser tableView:self.browser.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
    NSString *download = [NSByteCountFormatter stringFromByteCount:384000 countStyle:NSByteCountFormatterCountStyleFile];
    NSString *storage = [NSByteCountFormatter stringFromByteCount:3529728 countStyle:NSByteCountFormatterCountStyleFile];
    XCTAssertTrue([action.accessibilityValue containsString:download]);
    XCTAssertTrue([action.accessibilityValue containsString:storage]);
    XCTAssertTrue([action.accessibilityValue containsString:@"Stockage hors ligne"]);
    XCTAssertFalse([action.accessibilityValue containsString:@"{size}"]);
    XCTAssertEqual(self.catalog.installs, 0U);
    [self selectSection:0 row:0]; XCTAssertEqual(self.catalog.installs, 1U);
    XCTAssertNil(self.browser.presentedViewController);
    NSDictionary *bad = [self.browser catalogueSizesForManifest:@{@"packs": @[@{@"size": NSNull.null}, @{@"size": @(-1)}], @"games": @[@{@"size": @7}]}];
    XCTAssertEqualObjects(bad[@"download_bytes"], @0); XCTAssertEqualObjects(bad[@"offline_bytes"], @7);
}
- (void)testActualImportActionSendsOneWholeDependencyGroupOnlyOnce {
    NSDictionary *master = [self program:@"master" dependencies:@[]], *body = [self program:@"body" dependencies:@[@"master"]];
    __block NSArray *captured = nil; __block void (^finish)(NSError *) = nil; __block NSUInteger calls = 0;
    [self host:[self makeBrowser:2 programs:@[master, body] handler:^(NSDictionary *game, NSArray *programs, void (^completion)(NSError *)) { calls++; captured = programs; finish = [completion copy]; }]];
    [self selectSection:3 row:0]; [self selectSection:3 row:0];
    XCTAssertEqual(calls, 1U); XCTAssertEqual(captured.count, 2U);
    XCTAssertEqualObjects(captured.firstObject[@"id"], @"master"); XCTAssertEqualObjects(captured.lastObject[@"id"], @"body");
    for (NSDictionary *part in captured) XCTAssertEqualObjects(part[@"enabled"], @NO);
    finish(nil);
    [self waitFor:^BOOL { return self.browser.presentedViewController != nil; }];
    UIAlertController *alert = (id)self.browser.presentedViewController;
    XCTAssertEqualObjects(alert.message, [NeoUnifiedCheatBrowser localizedText:@"importDoneMessage" locale:@"fr"]);
    finish([NSError errorWithDomain:@"duplicate-completion" code:1 userInfo:nil]);
    XCTAssertEqual(calls, 1U);
}
- (void)testDismissedBrowserIgnoresLateLookupDownloadAndImportCallbacks {
    self.catalog.rows = @[[self game]]; self.catalog.holdCheats = YES;
    [self host:[self makeBrowser:0 programs:nil handler:nil]];
    [self selectSection:0 row:0];
    [self.browser openGame:[self game]];
    XCTAssertEqual(self.catalog.lookups, 1U);
    [self.browser closeBrowser];
    self.catalog.cheatsCompletion(@[[self program:@"body" dependencies:@[]]], nil);
    self.catalog.installProgress(@{@"completed_bytes": @1});
    self.catalog.installCompletion(nil, [NSError errorWithDomain:@"late" code:1 userInfo:nil]);
    XCTAssertNil(self.browser.presentedViewController);
    XCTAssertTrue([[self.browser valueForKey:@"closed"] boolValue]);
    NeoUnifiedCheatBrowser *detail = [self makeBrowser:2 programs:@[[self program:@"body" dependencies:@[]]] handler:^(NSDictionary *game, NSArray *programs, void (^completion)(NSError *)) { self.catalog.lateImportCompletion = [completion copy]; }];
    [self host:detail]; [self selectSection:3 row:0];
    void (^completion)(NSError *) = self.catalog.lateImportCompletion;
    [detail closeBrowser]; completion([NSError errorWithDomain:@"late-import" code:2 userInfo:nil]);
    XCTestExpectation *drained = [self expectationWithDescription:@"main callback drained"];
    dispatch_async(dispatch_get_main_queue(), ^{ [drained fulfill]; });
    [self waitForExpectations:@[drained] timeout:5]; XCTAssertNil(detail.presentedViewController);
}
- (void)testLongRowsActuallyFitNarrowUIKitCellsAtAccessibilitySize {
    NSMutableDictionary *longProgram = [[self program:@"body" dependencies:@[]] mutableCopy];
    longProgram[@"name"] = [@"Long programme name and precise edition " stringByPaddingToLength:360 withString:@" game title " startingAtIndex:0];
    longProgram[@"group"] = [@"Long author category " stringByPaddingToLength:200 withString:@" nested group " startingAtIndex:0];
    self.browser = [self makeBrowser:1 programs:@[longProgram] handler:nil];
    UIViewController *container = [UIViewController new];
    self.window.rootViewController = container;
    [self.window makeKeyAndVisible];
    [container addChildViewController:self.browser]; [container.view addSubview:self.browser.view]; [self.browser didMoveToParentViewController:container];
    [container setOverrideTraitCollection:[UITraitCollection traitCollectionWithPreferredContentSizeCategory:UIContentSizeCategoryAccessibilityExtraExtraExtraLarge] forChildViewController:self.browser];
    container.view.frame = CGRectMake(0, 0, 320, 568); self.browser.view.frame = container.view.bounds;
    [self.browser.tableView reloadData]; [self.browser.tableView layoutIfNeeded];
    NSIndexPath *path = [NSIndexPath indexPathForRow:0 inSection:1];
    [self.browser.tableView scrollToRowAtIndexPath:path atScrollPosition:UITableViewScrollPositionTop animated:NO]; [self.browser.tableView layoutIfNeeded];
    UITableViewCell *cell = [self.browser.tableView cellForRowAtIndexPath:path];
    XCTAssertNotNil(cell);
    UILabel *headline = [cell valueForKey:@"headline"], *subtitle = [cell valueForKey:@"subtitle"];
    CGRect a = [headline convertRect:headline.bounds toView:cell], b = [subtitle convertRect:subtitle.bounds toView:cell];
    XCTAssertFalse(CGRectIntersectsRect(a, b));
    XCTAssertTrue(CGRectContainsRect(CGRectInset(cell.bounds, -1, -1), a));
    XCTAssertTrue(CGRectContainsRect(CGRectInset(cell.bounds, -1, -1), b));
    XCTAssertGreaterThanOrEqual(headline.bounds.size.height + 1, [headline sizeThatFits:CGSizeMake(headline.bounds.size.width, CGFLOAT_MAX)].height);
    XCTAssertGreaterThanOrEqual(subtitle.bounds.size.height + 1, [subtitle sizeThatFits:CGSizeMake(subtitle.bounds.size.width, CGFLOAT_MAX)].height);
    XCTAssertFalse([cell.accessibilityValue containsString:longProgram[@"code"]]);
    XCTAssertFalse([cell.accessibilityValue containsString:@"https://"]);
}

- (LibretroCheatMenu *)realLibretroMenu:(void (^)(NSArray *))apply {
    NSString *directory = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    [self.temporaryFolders addObject:directory];
    [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *content = [directory stringByAppendingPathComponent:@"Probe.gb"];
    [[NSMutableData dataWithLength:32768] writeToFile:content atomically:YES];
    LibretroCheatMenu *menu = [[LibretroCheatMenu alloc] initWithDirectory:directory console:@"gb" core:@"gambatte"
        contentPath:content gameTitle:@"Probe" legacy:@[] text:^NSString *(NSString *key) { return key; }
        apply:apply ?: ^(NSArray *codes) {}];
    __weak LibretroCheatMenu *weakMenu = menu;
    [self waitFor:^BOOL { LibretroCheatMenu *current = weakMenu; return [[current valueForKey:@"ready"] boolValue] &&
        [[current valueForKey:@"pendingSources"] unsignedIntegerValue] == 0 && ![[current valueForKey:@"discovering"] boolValue]; }];
    return menu;
}
- (void)testRealLibretroCombinesMasterAndChildIntoOneDisabledToggle {
    LibretroCheatMenu *menu = [self realLibretroMenu:nil];
    NSDictionary *master = [self program:@"master" dependencies:@[]];
    NSMutableDictionary *body = [[self program:@"child" dependencies:@[@"master"]] mutableCopy];
    body[@"code"] = @"010300C2"; body[@"lines"] = @[@"010300C2"];
    XCTAssertTrue([menu acceptsUnifiedProgram:master]);
    NSMutableArray *ordered = [NSMutableArray array];
    XCTAssertTrue([menu appendUnifiedProgram:body index:@{@"master": master, @"child": body}
        visited:[NSMutableSet set] visiting:[NSMutableSet set] result:ordered depth:0]);
    XCTAssertEqualObjects(ordered, (@[master, body]));
    NSDictionary *record = [menu unifiedRecordForGame:[self game] programs:ordered];
    XCTAssertNotNil(record); XCTAssertEqualObjects(record[@"name"], @"child");
    XCTAssertEqualObjects(record[@"enabled"], @NO); XCTAssertEqualObjects(record[@"selected"], @NO);
    XCTAssertEqualObjects(record[@"code"], @"010100C0\n010200C1+010300C2");
    XCTAssertEqualObjects(record[@"programs"], ordered);
    [menu merge:@[record]];
    XCTAssertEqual([[menu valueForKey:@"records"] count], 1U);
    XCTAssertEqual(menu.enabledCount, 0U);
    NSMutableArray *incomplete = [NSMutableArray array];
    XCTAssertFalse([menu appendUnifiedProgram:body index:@{@"child": body} visited:[NSMutableSet set]
        visiting:[NSMutableSet set] result:incomplete depth:0]);
}
- (void)testRealLibretroKeepsRegionalConfirmationByGameIDAndMergesAllAttribution {
    LibretroCheatMenu *menu = [self realLibretroMenu:nil];
    NSDictionary *program = [self program:@"child" dependencies:@[]];
    NSDictionary *record = [menu unifiedRecordForGame:[self game] programs:@[program]];
    XCTAssertNotNil(record); XCTAssertTrue([record[@"uncertain"] boolValue]); XCTAssertFalse([menu verified:record]);
    [[menu valueForKey:@"confirmedGames"] addObject:@"another-release-with-the-same-title"];
    XCTAssertFalse([menu verified:record]);
    [[menu valueForKey:@"confirmedGames"] addObject:[self game][@"id"]];
    XCTAssertTrue([menu verified:record]);
    [menu merge:@[record]];
    NSMutableDictionary *other = [record mutableCopy]; other[@"provenance"] = @[@{@"source_id": @"second-source", @"author": @"Second author"}];
    [menu merge:@[other]];
    NSArray *records = [menu valueForKey:@"records"];
    XCTAssertEqual(records.count, 1U); XCTAssertEqual([records[0][@"provenance"] count], 2U);
    XCTAssertEqualObjects(records[0][@"enabled"], @NO);
}
- (void)testRealLibretroSameTitleAndCodeKeepDistinctUncertainEditionScopes {
    LibretroCheatMenu *menu = [self realLibretroMenu:nil];
    NSDictionary *program = [self program:@"child" dependencies:@[]];
    NSMutableDictionary *otherEdition = [[self game] mutableCopy]; otherEdition[@"id"] = @"probe-fr-revision-two";
    NSDictionary *first = [menu unifiedRecordForGame:[self game] programs:@[program]];
    NSDictionary *second = [menu unifiedRecordForGame:otherEdition programs:@[program]];
    [menu merge:@[first, second]];
    NSArray *records = [menu valueForKey:@"records"];
    XCTAssertEqual(records.count, 2U);
    XCTAssertNotEqualObjects(records[0][@"dedup"], records[1][@"dedup"]);
    [[menu valueForKey:@"confirmedGames"] addObject:[self game][@"id"]];
    XCTAssertTrue([menu verified:records[0]]); XCTAssertFalse([menu verified:records[1]]);
}
- (void)testRealLibretroAutoloadRejectsExclusiveDependenciesAndWrongParameterTypes {
    LibretroCheatMenu *menu = [self realLibretroMenu:nil];
    NSMutableDictionary *master = [[self program:@"master" dependencies:@[]] mutableCopy];
    NSMutableDictionary *body = [[self program:@"body" dependencies:@[@"master"]] mutableCopy];
    master[@"exclusive_group"] = @"choose-one"; body[@"exclusive_group"] = @"choose-one";
    NSMutableDictionary *wrongParameters = [[self program:@"wrong-parameters" dependencies:@[]] mutableCopy];
    wrongParameters[@"parameters"] = @{};
    NSMutableDictionary *wrongDependencies = [[self program:@"wrong-dependencies" dependencies:@[]] mutableCopy];
    wrongDependencies[@"dependencies"] = @{};
    XCTAssertFalse([menu acceptsUnifiedProgram:wrongParameters]); XCTAssertFalse([menu acceptsUnifiedProgram:wrongDependencies]);
    NSMutableDictionary *installed = [[self game] mutableCopy]; installed[@"installed"] = @YES; installed[@"sha256"] = [@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0];
    self.catalog.rows = @[installed]; self.catalog.codes = @[master, body, wrongParameters, wrongDependencies];
    XCTAssertNoThrow([NSNotificationCenter.defaultCenter postNotificationName:NeoUnifiedCheatCatalogDidInstallNotification object:self.catalog]);
    NSArray *records = [menu valueForKey:@"records"];
    XCTAssertEqual(records.count, 1U); XCTAssertEqualObjects(records[0][@"id"], @"master");
    XCTAssertEqualObjects(records[0][@"enabled"], @NO);
}
- (void)testRealLibretroFullRecordLimitReportsImportFailureInSharedUI {
    LibretroCheatMenu *menu = [self realLibretroMenu:nil];
    NSMutableArray *full = [NSMutableArray arrayWithCapacity:4096];
    for (NSUInteger index = 0; index < 4096; index++) [full addObject:[@{@"id": @(index), @"enabled": @NO} mutableCopy]];
    [menu setValue:full forKey:@"records"];
    UIViewController *presenter = [UIViewController new];
    self.window.rootViewController = presenter; [self.window makeKeyAndVisible];
    [menu presentUnifiedFrom:presenter];
    UINavigationController *navigation = (id)presenter.presentedViewController;
    XCTAssertTrue([navigation isKindOfClass:UINavigationController.class]);
    NeoUnifiedCheatBrowser *root = (id)navigation.topViewController;
    XCTAssertTrue([root isKindOfClass:NeoUnifiedCheatBrowser.class]);
    void (^handler)(NSDictionary *, NSArray *, void (^)(NSError *)) = [root valueForKey:@"importHandler"];
    XCTAssertNotNil(handler);
    [navigation dismissViewControllerAnimated:NO completion:nil];
    [self host:[self makeBrowser:2 programs:@[[self program:@"new-code" dependencies:@[]]] handler:handler]];
    [self selectSection:3 row:0];
    [self waitFor:^BOOL { return self.browser.presentedViewController != nil; }];
    UIAlertController *alert = (id)self.browser.presentedViewController;
    XCTAssertEqualObjects(alert.title, [NeoUnifiedCheatBrowser localizedText:@"importFailed" locale:@"fr"]);
    XCTAssertTrue([alert.message containsString:NeoUnifiedCheatCatalogErrorDomain]);
    XCTAssertEqual([[menu valueForKey:@"records"] count], 4096U);
}
- (void)testRealLibretroNotificationLoadsInstalledCodesWithoutActivationOrNetwork {
    __block NSUInteger activations = 0;
    LibretroCheatMenu *menu = [self realLibretroMenu:^(NSArray *codes) { activations++; }];
    XCTAssertEqual([[menu valueForKey:@"records"] count], 0U);
    NSMutableDictionary *installed = [[self game] mutableCopy]; installed[@"installed"] = @YES; installed[@"sha256"] = [@"a" stringByPaddingToLength:64 withString:@"a" startingAtIndex:0];
    self.catalog.rows = @[installed]; self.catalog.codes = @[[self program:@"offline-program" dependencies:@[]]];
    [NSNotificationCenter.defaultCenter postNotificationName:NeoUnifiedCheatCatalogDidInstallNotification object:self.catalog];
    [self waitFor:^BOOL { return [[menu valueForKey:@"records"] count] == 1; }];
    XCTAssertEqual(self.catalog.lookups, 1U); XCTAssertEqual(activations, 0U); XCTAssertEqual(menu.enabledCount, 0U);
    [NSNotificationCenter.defaultCenter postNotificationName:NeoUnifiedCheatCatalogDidInstallNotification object:self.catalog];
    XCTAssertEqual(self.catalog.lookups, 1U); XCTAssertEqual([[menu valueForKey:@"records"] count], 1U);
}
- (void)testRealLibretroOwnerIsReleasedAfterPageDismissalAndNotificationObserverRemoval {
    __weak LibretroCheatMenu *owner = nil;
    LibretroMenuPage *page = nil;
    @autoreleasepool {
        LibretroCheatMenu *menu = [self realLibretroMenu:nil]; owner = menu; page = [menu rootPage];
        [page loadViewIfNeeded];
        XCTAssertNotNil(owner);
        page = nil;
        menu = nil;
    }
    [self waitFor:^BOOL { return owner == nil; }];
    XCTAssertNil(owner);
    // A subsequent catalogue notification cannot resurrect the dismissed owner.
    [NSNotificationCenter.defaultCenter postNotificationName:NeoUnifiedCheatCatalogDidInstallNotification object:self.catalog];
    XCTAssertNil(owner);
}
@end
