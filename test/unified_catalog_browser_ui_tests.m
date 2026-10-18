#import "Public/NeoUnifiedCheatList.h"
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
- (NSDictionary *)unifiedIdentity;
- (void)save;
- (BOOL)restoreSelectedOnPage:(LibretroMenuPage*)page;
- (BOOL)isPureMGBAVBARecord:(NSDictionary *)record;
- (NSArray *)enabledCodes;
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
    // Disabling animations does not make UIKit appearance transitions
    // synchronous. Wait for presentation and dismissal before the next tap.
    [self waitFor:^BOOL { return alert.viewIfLoaded.window && !alert.isBeingPresented && !alert.transitionCoordinator; }];
    void (^handler)(UIAlertAction *) = [action valueForKey:@"handler"];
    __block BOOL dismissed = NO;
    [alert dismissViewControllerAnimated:NO completion:^{ dismissed = YES; if (handler) handler(action); }];
    [self waitFor:^BOOL { return dismissed; }];
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
    [self waitFor:^BOOL { return codes.viewIfLoaded.window && !self.navigation.transitionCoordinator; }];
    XCTAssertEqualObjects([codes reasonForProgram:self.catalog.codes.firstObject], @"editionMismatch");
    [codes tableView:codes.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:1]];
    [self waitFor:^BOOL { return self.navigation.viewControllers.count == 3 && !self.navigation.transitionCoordinator; }];
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
    UIProgressView *progressView = [progress valueForKey:@"progressView"];
    UILabel *progressLabel = [progress valueForKey:@"progressLabel"];
    XCTAssertEqualWithAccuracy(progressView.progress, 0.25, 0.001);
    XCTAssertTrue([progressLabel.text containsString:@"1 / 2"]);
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
    XCTAssertTrue(([menu appendUnifiedProgram:body index:@{@"master": master, @"child": body}
        visited:[NSMutableSet set] visiting:[NSMutableSet set] result:ordered depth:0]));
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
- (void)testGBAVBARawDialectRequiresMGBAAndKeepsWholeAddressValueProgram {
    LibretroCheatMenu *menu = [self realLibretroMenu:nil];
    [menu setValue:@"gba" forKey:@"console"]; [menu setValue:@"mgba" forKey:@"core"];
    NSDictionary *program = @{@"id": @"gba-vba-raw", @"name": @"Raw ROM patch", @"status": @"available",
        @"dialect": @"gba-vba-raw", @"handler": @0, @"parameters": @[], @"dependencies": @[],
        @"code": @"08020000:12345678+08020004:00000000"};
    XCTAssertTrue([menu acceptsUnifiedProgram:program]);
    XCTAssertEqualObjects([LibretroCheats codesForCheat:program core:@"mgba" console:@"gba"], (@[@"08020000:12345678+08020004:00000000"]));
    [menu setValue:@"gambatte" forKey:@"core"]; XCTAssertFalse([menu acceptsUnifiedProgram:program]);
    [menu setValue:@"mgba" forKey:@"core"]; [menu setValue:@"gb" forKey:@"console"];
    XCTAssertFalse([menu acceptsUnifiedProgram:program]);
}
- (void)testPCEWonderSwanAndPicoProfilesUseNativeBindingsAndCanonicalCatalogueAliases {
    LibretroCheatMenu *menu = [self realLibretroMenu:nil];
    NSArray *fixtures = @[
        @[@"pce", @"mednafen_pce_fast", @"pce-raw", @"1F0000:01", @"pce"],
        @[@"tg16", @"mednafen_pce_fast_libretro", @"pce-raw", @"1F0000:01", @"pce"],
        @[@"pccd", @"mednafen_pce_fast", @"pce-raw", @"0D0000:01", @"pccd"],
        @[@"tgcd", @"mednafen_pce_fast_libretro", @"pce-raw", @"0D0000:01", @"pccd"],
        @[@"ws", @"mednafen_wswan", @"wswan-raw", @"1234:01", @"ws"],
        @[@"wsc", @"mednafen_wswan_libretro", @"wswan-raw", @"1234:01", @"wsc"],
        @[@"md", @"picodrive", @"md-raw", @"FF0000:0001", @"md"],
        @[@"mcd", @"picodrive", @"md-raw", @"FF0000:0001", @"mcd"],
        @[@"32x", @"picodrive_libretro", @"md-raw", @"FF0000:0001", @"32x"],
        @[@"pico", @"picodrive", @"md-raw", @"FF0000:0001", @"pico"]];
    for (NSArray *fixture in fixtures) {
        [menu setValue:fixture[0] forKey:@"console"]; [menu setValue:fixture[1] forKey:@"core"];
        NSDictionary *program = @{@"id": @"profile-probe", @"name": @"Probe", @"status": @"available",
            @"dialect": fixture[2], @"code": fixture[3], @"handler": @0, @"parameters": @[], @"dependencies": @[]};
        XCTAssertTrue([menu acceptsUnifiedProgram:program]);
        XCTAssertEqualObjects([menu unifiedIdentity][@"system"], fixture[4]);
        XCTAssertEqualObjects([menu valueForKey:@"console"], fixture[0]);
    }
    [menu setValue:@"md" forKey:@"console"]; [menu setValue:@"picodrive_libretro" forKey:@"core"];
    NSDictionary *restricted = @{@"id": @"pico-master", @"name": @"Probe", @"status": @"available",
        @"dialect": @"md-raw", @"code": @"FF0000:0001", @"handler": @0, @"parameters": @[], @"dependencies": @[],
        @"activation_profiles": @[@"picodrive"]};
    NSMutableDictionary *body = [restricted mutableCopy]; [body removeObjectForKey:@"activation_profiles"];
    body[@"id"] = @"pico-body"; body[@"code"] = @"FF0002:0002";
    NSDictionary *game = @{@"id": @"md-probe", @"title": @"Probe", @"system": @"md", @"identities": @[]};
    NSDictionary *record = [menu unifiedRecordForGame:game programs:@[restricted, body]];
    XCTAssertNotNil(record); XCTAssertEqualObjects(record[@"activation_profiles"], (@[@"picodrive"]));
    [menu merge:@[record]];
    NSMutableDictionary *stored = [[menu valueForKey:@"records"] firstObject]; stored[@"enabled"] = @YES;
    XCTAssertNotNil([menu enabledCodes]);
    [menu setValue:@"genesis_plus_gx" forKey:@"core"];
    XCTAssertFalse([menu acceptsUnifiedProgram:restricted]); XCTAssertNil([menu enabledCodes]);
}
- (LibretroCheatMenu *)realMGBAAtDirectory:(NSString *)existing apply:(void (^)(NSArray *))apply {
    NSString *directory = existing ?: [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    if (!existing) [self.temporaryFolders addObject:directory];
    [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *content = [directory stringByAppendingPathComponent:@"Probe.gba"];
    if (![NSFileManager.defaultManager fileExistsAtPath:content]) [[NSMutableData dataWithLength:32768] writeToFile:content atomically:YES];
    LibretroCheatMenu *menu = [[LibretroCheatMenu alloc] initWithDirectory:directory console:@"gba" core:@"mgba"
        contentPath:content gameTitle:@"Probe" legacy:@[] text:^NSString *(NSString *key) { return key; }
        apply:apply ?: ^(NSArray *codes) {}];
    __weak LibretroCheatMenu *weakMenu = menu;
    [self waitFor:^BOOL { LibretroCheatMenu *current = weakMenu; return [[current valueForKey:@"ready"] boolValue] &&
        [[current valueForKey:@"pendingSources"] unsignedIntegerValue] == 0 && ![[current valueForKey:@"discovering"] boolValue]; }];
    menu.uiLocale = @"fr"; [menu setValue:@YES forKey:@"warned"];
    return menu;
}
- (NSDictionary *)gbaRecord:(NSString *)identifier code:(NSString *)code dialect:(NSString *)dialect isolated:(BOOL)isolated {
    return @{@"id": identifier, @"name": identifier, @"code": code, @"dialect": dialect, @"status": @"available",
        @"handler": @0, @"parameters": @[], @"dependencies": @[], @"mgba_auto_isolated": isolated ? @YES : @NO};
}
- (void)hostMenuPage:(LibretroMenuPage *)page {
    self.navigation = [[UINavigationController alloc] initWithRootViewController:page];
    self.window.rootViewController = self.navigation; [self.window makeKeyAndVisible];
    [page loadViewIfNeeded]; [page rebuild]; [self.window layoutIfNeeded];
}
- (void)setActualMenuSwitch:(LibretroMenuPage *)page row:(NSUInteger)row enabled:(BOOL)enabled {
    [page rebuild];
    UITableViewCell *cell = [page tableView:page.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:(NSInteger)row inSection:1]];
    UISwitch *control = (id)cell.accessoryView;
    XCTAssertTrue([control isKindOfClass:UISwitch.class]); XCTAssertTrue(control.enabled);
    [control setOn:enabled animated:NO]; [control sendActionsForControlEvents:UIControlEventValueChanged];
}

- (void)testMGBARawAUTOActivationIsIsolatedButCompleteVBACanCoexist {
    __block NSUInteger applies = 0;
    LibretroCheatMenu *menu = [self realMGBAAtDirectory:nil apply:^(NSArray *codes) { applies++; }];
    NSDictionary *autoCode = [self gbaRecord:@"isolated-auto" code:@"02000000 00000001" dialect:@"gba-auto" isolated:YES];
    NSDictionary *other = [self gbaRecord:@"other-gba" code:@"02000004 00000002" dialect:@"gba-gameshark-v3" isolated:NO];
    NSDictionary *vba = [self gbaRecord:@"complete-vba" code:@"08020000:12345678" dialect:@"gba-vba-raw" isolated:NO];
    [menu merge:@[autoCode, other, vba]];
    LibretroMenuPage *page = [menu rootPage]; [self hostMenuPage:page];
    [self setActualMenuSwitch:page row:0 enabled:YES]; XCTAssertEqual(applies, 1U);
    [self setActualMenuSwitch:page row:1 enabled:YES]; XCTAssertEqual(applies, 1U);
    NSArray *records = [menu valueForKey:@"records"];
    XCTAssertEqualObjects(records[0][@"enabled"], @YES); XCTAssertEqualObjects(records[1][@"enabled"], @NO);
    XCTAssertEqualObjects(records[1][@"selected"], @NO);
    XCTAssertEqualObjects(((LibretroMenuSection *)page.builder()[1]).title, [NeoUnifiedCheatBrowser localizedText:@"mgbaIsolationConflict" locale:@"fr"]);
    [self setActualMenuSwitch:page row:2 enabled:YES]; XCTAssertEqual(applies, 2U);
    XCTAssertEqual(menu.enabledCount, 2U);
    [self setActualMenuSwitch:page row:0 enabled:NO];
    [self setActualMenuSwitch:page row:1 enabled:YES]; XCTAssertEqual(applies, 4U);
    [self setActualMenuSwitch:page row:0 enabled:YES]; XCTAssertEqual(applies, 4U);
    XCTAssertEqualObjects(records[0][@"enabled"], @NO); XCTAssertEqualObjects(records[0][@"selected"], @NO);
    XCTAssertEqualObjects(records[1][@"enabled"], @YES); XCTAssertEqualObjects(records[2][@"enabled"], @YES);
    NSMutableDictionary *mixed = [vba mutableCopy]; mixed[@"code"] = @"02000000 00000001+08020000:12345678";
    mixed[@"mgba_auto_isolated"] = @YES;
    XCTAssertFalse([menu isPureMGBAVBARecord:mixed]);
    XCTAssertEqualObjects(records[0][@"code"], autoCode[@"code"]);
}
- (void)testMGBARestoreRefusesAUTOCombinationWithoutChangingAnyPriorState {
    __block NSUInteger applies = 0;
    LibretroCheatMenu *menu = [self realMGBAAtDirectory:nil apply:^(NSArray *codes) { applies++; }];
    NSMutableDictionary *autoCode = [[self gbaRecord:@"auto" code:@"02000000 00000001" dialect:@"gba-auto" isolated:YES] mutableCopy];
    NSMutableDictionary *other = [[self gbaRecord:@"other" code:@"02000004 00000002" dialect:@"gba-gameshark-v3" isolated:NO] mutableCopy];
    NSDictionary *vba = [self gbaRecord:@"vba" code:@"08020000:12345678" dialect:@"gba-vba-raw" isolated:NO];
    autoCode[@"selected"] = @YES; other[@"selected"] = @YES;
    [menu merge:@[autoCode, other, vba]];
    LibretroMenuPage *page = [menu rootPage]; [self hostMenuPage:page];
    [self setActualMenuSwitch:page row:2 enabled:YES]; XCTAssertEqual(applies, 1U);
    NSArray *before = [[NSArray alloc] initWithArray:[menu valueForKey:@"records"] copyItems:YES];
    [menu restoreSelectedOnPage:page]; XCTAssertEqual(applies, 1U);
    XCTAssertEqualObjects([menu valueForKey:@"records"], before);
    XCTAssertEqual(menu.enabledCount, 1U);
    XCTAssertEqualObjects(((LibretroMenuSection *)page.builder()[1]).title, [NeoUnifiedCheatBrowser localizedText:@"mgbaIsolationConflict" locale:@"fr"]);
}
- (void)testExclusiveGroupsAcrossTogglesIncludeLegacyAndRestoreIsAtomic {
    __block NSUInteger applies = 0;
    LibretroCheatMenu *menu = [self realLibretroMenu:^(NSArray *codes) { applies++; }];
    menu.uiLocale = @"fr"; [menu setValue:@YES forKey:@"warned"];
    NSMutableDictionary *a = [[self program:@"a" dependencies:@[]] mutableCopy], *b = [[self program:@"b" dependencies:@[]] mutableCopy];
    a[@"code"] = @"010100C0"; b[@"code"] = @"010200C1";
    a[@"exclusive_groups"] = @[@"slot-1"]; b[@"exclusive_group"] = @"slot-1";
    a[@"selected"] = @YES; b[@"selected"] = @YES;
    [menu merge:@[a, b]];
    LibretroMenuPage *page = [menu rootPage]; [self hostMenuPage:page];
    [self setActualMenuSwitch:page row:0 enabled:YES]; XCTAssertEqual(applies, 1U);
    NSArray *before = [[NSArray alloc] initWithArray:[menu valueForKey:@"records"] copyItems:YES];
    [self setActualMenuSwitch:page row:1 enabled:YES]; XCTAssertEqual(applies, 1U);
    XCTAssertEqualObjects([menu valueForKey:@"records"], before);
    [menu restoreSelectedOnPage:page]; XCTAssertEqual(applies, 1U);
    XCTAssertEqualObjects([menu valueForKey:@"records"], before);
    XCTAssertEqualObjects(((LibretroMenuSection *)page.builder()[1]).title, [NeoUnifiedCheatBrowser localizedText:@"exclusiveConflict" locale:@"fr"]);
}
- (void)testClosureAUTOAndExclusiveMetadataSurviveMergeSaveAndActualReload {
    LibretroCheatMenu *menu = [self realMGBAAtDirectory:nil apply:nil];
    NSMutableDictionary *master = [[self gbaRecord:@"master" code:@"02000000 00000001" dialect:@"gba-auto" isolated:YES] mutableCopy];
    NSMutableDictionary *body = [[self gbaRecord:@"body" code:@"02000004 00000002" dialect:@"gba-auto" isolated:NO] mutableCopy];
    master[@"exclusive_group"] = @"master-choice"; body[@"exclusive_groups"] = @[@"body-choice"];
    NSDictionary *game = @{@"id": @"gba-probe", @"title": @"Probe", @"system": @"gba", @"identities": @[]};
    NSDictionary *record = [menu unifiedRecordForGame:game programs:@[master, body]];
    XCTAssertNotNil(record); XCTAssertEqualObjects(record[@"mgba_auto_isolated"], @YES);
    XCTAssertEqualObjects(record[@"exclusive_groups"], (@[@"master-choice", @"body-choice"]));
    [menu merge:@[record]];
    NSMutableDictionary *duplicate = [record mutableCopy]; duplicate[@"mgba_auto_isolated"] = @NO;
    duplicate[@"exclusive_groups"] = @[@"second-source-choice"];
    [menu merge:@[duplicate]]; [menu save];
    NSString *file = [menu valueForKey:@"preferencesPath"];
    [self waitFor:^BOOL { return [NSFileManager.defaultManager fileExistsAtPath:file]; }];
    NSDictionary *saved = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:file] options:0 error:nil];
    NSDictionary *savedRecord = [saved[@"cheats"] firstObject];
    XCTAssertEqualObjects(savedRecord[@"mgba_auto_isolated"], @YES);
    XCTAssertTrue([savedRecord[@"exclusive_groups"] containsObject:@"master-choice"]);
    XCTAssertTrue([savedRecord[@"exclusive_groups"] containsObject:@"body-choice"]);
    XCTAssertTrue([savedRecord[@"exclusive_groups"] containsObject:@"second-source-choice"]);
    XCTAssertEqualObjects(savedRecord[@"programIDs"], (@[@"master", @"body"])); XCTAssertNil(savedRecord[@"programs"]);
    LibretroCheatMenu *reloaded = [self realMGBAAtDirectory:[menu valueForKey:@"directory"] apply:nil];
    NSArray *records = [reloaded valueForKey:@"records"];
    XCTAssertEqual(records.count, 1U); XCTAssertEqualObjects(records[0][@"mgba_auto_isolated"], @YES);
    XCTAssertEqualObjects(records[0][@"exclusive_groups"], savedRecord[@"exclusive_groups"]);
    XCTAssertEqualObjects(records[0][@"enabled"], @NO);
    NSMutableDictionary *nullFlags = [[self gbaRecord:@"null-flags" code:@"02000008 00000003" dialect:@"gba-auto" isolated:NO] mutableCopy];
    nullFlags[@"mgba_auto_isolated"] = NSNull.null; nullFlags[@"exclusive_group"] = NSNull.null;
    nullFlags[@"exclusive_groups"] = NSNull.null;
    NSMutableDictionary *stringFlags = [[self gbaRecord:@"string-flags" code:@"0200000C 00000004" dialect:@"gba-auto" isolated:NO] mutableCopy];
    stringFlags[@"mgba_auto_isolated"] = @"YES"; stringFlags[@"exclusive_groups"] = @[NSNull.null, @7, @"valid-choice", @""];
    [reloaded merge:@[nullFlags, stringFlags]]; [reloaded save];
    [self waitFor:^BOOL {
        NSDictionary *latest = [NSJSONSerialization JSONObjectWithData:[NSData dataWithContentsOfFile:file] options:0 error:nil];
        return [latest[@"cheats"] count] == 3;
    }];
    LibretroCheatMenu *malformedReload = [self realMGBAAtDirectory:[menu valueForKey:@"directory"] apply:nil];
    NSArray *sanitized = [malformedReload valueForKey:@"records"];
    XCTAssertEqual(sanitized.count, 3U);
    XCTAssertEqualObjects(sanitized[1][@"mgba_auto_isolated"], @NO); XCTAssertEqualObjects(sanitized[1][@"exclusive_groups"], @[]);
    XCTAssertEqualObjects(sanitized[2][@"mgba_auto_isolated"], @NO);
    XCTAssertEqualObjects(sanitized[2][@"exclusive_groups"], (@[@"valid-choice"]));
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

- (NSDictionary *)fbneoGame {
    return @{@"id": @"arcade-probe", @"title": @"Probe", @"system": @"arcade", @"identities": @[
        @{@"type": @"romset", @"value": @"probe", @"scheme": @"fbneo-driver-name"}]};
}
- (NSDictionary *)fbneoProgram {
    return @{@"id": @"native-block", @"name": @"Infinite Credits", @"dialect": @"fbneo-ini", @"status": @"available",
        @"code": @"cheat \"Infinite Credits\"\ndefault 1\n0 \"Disabled\"\n1 \"Enabled\", 0, 0xE018, 0x01, 0, 0xE010, 0x08",
        @"parameters": @[], @"dependencies": @[], @"enabled": @NO};
}
- (LibretroCheatMenu *)realFBNeoMenu:(void (^)(NSArray *))apply {
    NSString *directory = [NSTemporaryDirectory() stringByAppendingPathComponent:NSUUID.UUID.UUIDString];
    [self.temporaryFolders addObject:directory];
    [NSFileManager.defaultManager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *content = [directory stringByAppendingPathComponent:@"probe.zip"];
    [[NSMutableData dataWithLength:256] writeToFile:content atomically:YES];
    LibretroCheatMenu *menu = [[LibretroCheatMenu alloc] initWithDirectory:directory console:@"arcade" core:@"fbneo"
        contentPath:content gameTitle:@"Probe" legacy:@[] text:^NSString *(NSString *key) { return key; }
        apply:apply ?: ^(NSArray *codes) {}];
    __weak LibretroCheatMenu *weakMenu = menu;
    [self waitFor:^BOOL { LibretroCheatMenu *current = weakMenu; return [[current valueForKey:@"ready"] boolValue] &&
        [[current valueForKey:@"pendingSources"] unsignedIntegerValue] == 0; }];
    menu.uiLocale = @"fr";
    return menu;
}
- (NSDictionary *)fbneoOption:(NSString *)value {
    return @{@"key": @"fbneo-cheat-0-probe-Infinite Credits", @"name": @"Infinite Credits", @"value": value,
        @"values": @[@"0 - Disabled", @"1 - Enabled"], @"labels": @[@"Disabled", @"Enabled"], @"off_value": @"0 - Disabled",
        @"available": @YES, @"reason_code": @""};
}
- (void)testFBNeoFirstLaunchOffersOneBulkDownloadWithoutImportOrActivation {
    __block NSUInteger mutations=0;
    LibretroCheatMenu *menu=[self realFBNeoMenu:nil];
    menu.fbneoCommand=^(NSDictionary *request,void (^completion)(NSDictionary*,NSError*)) {
        if(![request[@"action"] isEqual:@"snapshot"])mutations++;
        completion(@{@"driver":@"probe",@"options":@[],@"restart_required":@NO},nil);
    };
    LibretroMenuPage *page=[menu rootPage];[self waitFor:^BOOL{return ![[menu valueForKey:@"fbneoLoading"] boolValue];}];
    NSArray *sections=page.builder();NSArray *actions=((LibretroMenuSection*)sections[0]).rows;
    XCTAssertEqual(actions.count,2U);XCTAssertEqualObjects(((LibretroMenuRow*)actions[0]).title,[NeoUnifiedCheatBrowser localizedText:@"downloadAll" locale:@"fr"]);
    ((LibretroMenuRow*)actions[0]).action(page);XCTAssertEqual(self.catalog.installs,1U);XCTAssertEqual(mutations,0U);
    self.catalog.installCompletion(@{},nil);XCTAssertEqual(mutations,0U);
}

- (void)testFBNeoUnavailableNativeOptionsStayVisibleAndCannotSendActivation {
    LibretroCheatMenu *menu = [self realFBNeoMenu:nil];
    NSMutableArray *requests = [NSMutableArray array];
    NSMutableDictionary *unsafe = [[self fbneoOption:@"0 - Disabled"] mutableCopy];
    unsafe[@"available"] = @NO; unsafe[@"reason_code"] = @"nonzero_native_default";
    NSMutableDictionary *unmanaged = [unsafe mutableCopy]; unmanaged[@"key"] = @"fbneo-cheat-1-probe-unmanaged";
    unmanaged[@"available"] = NSNull.null; unmanaged[@"reason_code"] = @"unmanaged_native_file";
    menu.fbneoCommand = ^(NSDictionary *request, void (^completion)(NSDictionary *, NSError *)) {
        [requests addObject:request];
        completion(@{@"driver": @"probe", @"options": @[unsafe, unmanaged], @"restart_required": @NO}, nil);
    };
    LibretroMenuPage *page = [menu rootPage];
    [self waitFor:^BOOL { return ![[menu valueForKey:@"fbneoLoading"] boolValue]; }];
    NSArray *rows = ((LibretroMenuSection *)page.builder()[1]).rows;
    XCTAssertEqual(rows.count, 2U);
    LibretroMenuRow *first = rows[0], *second = rows[1];
    XCTAssertFalse(first.enabled); XCTAssertFalse(second.enabled);
    XCTAssertEqualObjects(first.detail, [NeoUnifiedCheatBrowser localizedText:@"fbneoUnsafeDefault" locale:@"fr"]);
    XCTAssertEqualObjects(second.detail, [NeoUnifiedCheatBrowser localizedText:@"fbneoUnmanagedOption" locale:@"fr"]);
    first.toggle(page, YES); second.toggle(page, YES);
    for (NSDictionary *request in requests) XCTAssertEqualObjects(request[@"action"], @"snapshot");
    XCTAssertEqual(menu.enabledCount, 0U);
}
- (void)testFBNeoMenuLoadsNativeOptionsWithoutActivatingOrUsingRetroCheatSet {
    __block NSUInteger genericApply = 0;
    LibretroCheatMenu *menu = [self realFBNeoMenu:^(NSArray *codes) { genericApply++; }];
    NSMutableArray *requests = [NSMutableArray array];
    menu.fbneoCommand = ^(NSDictionary *request, void (^completion)(NSDictionary *, NSError *)) {
        [requests addObject:request];
        completion(@{@"driver": @"probe", @"options": @[[self fbneoOption:@"0 - Disabled"]], @"restart_required": @NO}, nil);
    };
    LibretroMenuPage *page = [menu rootPage];
    [self waitFor:^BOOL { return ![[menu valueForKey:@"fbneoLoading"] boolValue]; }];
    NSArray *sections = page.builder();
    XCTAssertEqual(sections.count, 2U);
    NSArray *rows = ((LibretroMenuSection *)sections[1]).rows;
    XCTAssertEqual(rows.count, 1U); XCTAssertTrue(((LibretroMenuRow *)rows[0]).isToggle);
    XCTAssertFalse(((LibretroMenuRow *)rows[0]).toggleOn);
    XCTAssertEqual(menu.enabledCount, 0U); XCTAssertEqual(genericApply, 0U);
    for (NSDictionary *request in requests) XCTAssertEqualObjects(request[@"action"], @"snapshot");
    XCTAssertEqual(self.catalog.lookups, 0U);
    XCTAssertFalse([LibretroCheats.supportedCoreIDs containsObject:@"fbneo"]);
    XCTAssertTrue([menu acceptsUnifiedProgram:[self fbneoProgram]]);
    NSMutableDictionary *dependent = [[self fbneoProgram] mutableCopy]; dependent[@"dependencies"] = @[@"unconverted-master"];
    XCTAssertFalse([menu acceptsUnifiedProgram:dependent]);
    NSMutableDictionary *invalid = [[self fbneoProgram] mutableCopy]; invalid[@"parameters"] = NSNull.null;
    XCTAssertFalse([menu acceptsUnifiedProgram:invalid]);
}
- (void)testFBNeoExplicitToggleAndDisableAllUseSessionNativeOptionsOnly {
    __block NSUInteger genericApply = 0; __block NSString *current = @"0 - Disabled";
    LibretroCheatMenu *menu = [self realFBNeoMenu:^(NSArray *codes) { genericApply++; }];
    NSMutableArray *requests = [NSMutableArray array];
    menu.fbneoCommand = ^(NSDictionary *request, void (^completion)(NSDictionary *, NSError *)) {
        [requests addObject:request];
        if ([request[@"action"] isEqual:@"set"]) current = request[@"value"];
        if ([request[@"action"] isEqual:@"disableAll"]) current = @"0 - Disabled";
        completion(@{@"driver": @"probe", @"options": @[[self fbneoOption:current]], @"restart_required": @NO}, nil);
    };
    LibretroMenuPage *page = [menu rootPage];
    [self waitFor:^BOOL { return ![[menu valueForKey:@"fbneoLoading"] boolValue]; }];
    [menu setValue:@YES forKey:@"warned"];
    LibretroMenuRow *toggle = ((LibretroMenuSection *)page.builder()[1]).rows.firstObject;
    toggle.toggle(page, YES);
    [self waitFor:^BOOL { return menu.enabledCount == 1; }];
    XCTAssertEqualObjects(requests.lastObject[@"action"], @"set");
    XCTAssertEqualObjects(requests.lastObject[@"key"], @"fbneo-cheat-0-probe-Infinite Credits");
    XCTAssertEqualObjects(requests.lastObject[@"value"], @"1 - Enabled");
    LibretroMenuRow *disable = ((LibretroMenuSection *)page.builder()[1]).rows.firstObject;
    disable.toggle(page, NO);
    [self waitFor:^BOOL { return menu.enabledCount == 0; }];
    XCTAssertEqualObjects(requests.lastObject[@"action"], @"set");
    XCTAssertEqualObjects(requests.lastObject[@"value"], @"0 - Disabled");
    XCTAssertEqual(genericApply, 0U);
    XCTAssertEqual([[menu valueForKey:@"records"] count], 0U);
}
- (void)testFBNeoCompleteNativeImportStaysDisabledAndExplainsGameRelaunch {
    __block NSDictionary *imported = nil; __block NSUInteger genericApply = 0; __block BOOL restartRequired = NO;
    LibretroCheatMenu *menu = [self realFBNeoMenu:^(NSArray *codes) { genericApply++; }];
    menu.fbneoCommand = ^(NSDictionary *request, void (^completion)(NSDictionary *, NSError *)) {
        if ([request[@"action"] isEqual:@"import"]) { imported = request; restartRequired = YES; }
        completion(@{@"driver": @"probe", @"options": @[[self fbneoOption:@"0 - Disabled"]], @"restart_required": restartRequired ? @YES : @NO}, nil);
    };
    [self waitFor:^BOOL { return ![[menu valueForKey:@"fbneoLoading"] boolValue]; }];
    UIViewController *presenter = [UIViewController new]; self.window.rootViewController = presenter; [self.window makeKeyAndVisible];
    [menu presentUnifiedFrom:presenter];
    UINavigationController *navigation = (id)presenter.presentedViewController;
    NeoUnifiedCheatBrowser *root = (id)navigation.topViewController;
    XCTAssertEqualObjects([root valueForKey:@"engine"], @"fbneo");
    void (^handler)(NSDictionary *, NSArray *, void (^)(NSError *)) = [root valueForKey:@"importHandler"];
    [navigation dismissViewControllerAnimated:NO completion:nil];
    NeoUnifiedCheatBrowser *detail = [[NeoUnifiedCheatBrowser alloc] initWithIdentity:[self fbneoGame] engine:@"fbneo" locale:@"fr"
        accepts:^BOOL(NSDictionary *program) { return [menu acceptsUnifiedProgram:program]; } importHandler:handler];
    [detail setValue:@2 forKey:@"page"]; [detail setValue:[self fbneoGame] forKey:@"game"];
    [detail setValue:[self fbneoProgram] forKey:@"program"]; [detail setProgramsForDisplay:@[[self fbneoProgram]]];
    [self host:detail]; [self selectSection:3 row:0];
    [self waitFor:^BOOL { return self.browser.presentedViewController != nil; }];
    XCTAssertEqualObjects(imported[@"action"], @"import"); XCTAssertEqual([imported[@"programs"] count], 1U);
    XCTAssertEqualObjects(imported[@"programs"][0][@"code"], [self fbneoProgram][@"code"]);
    XCTAssertEqualObjects(imported[@"programs"][0][@"enabled"], @NO);
    XCTAssertEqual(menu.enabledCount, 0U); XCTAssertEqual(genericApply, 0U);
    UIAlertController *alert = (id)self.browser.presentedViewController;
    XCTAssertEqualObjects(alert.message, [NeoUnifiedCheatBrowser localizedText:@"fbneoImportDoneMessage" locale:@"fr"]);
    LibretroMenuPage *nativeRoot = [menu rootPage];
    [self waitFor:^BOOL { return ![[menu valueForKey:@"fbneoLoading"] boolValue]; }];
    NSArray *sections = nativeRoot.builder();
    XCTAssertEqual(sections.count, 3U);
    XCTAssertFalse(((LibretroMenuRow *)((LibretroMenuSection *)sections[1]).rows.firstObject).enabled);
    LibretroMenuRow *restart = ((LibretroMenuSection *)sections[2]).rows.firstObject;
    XCTAssertEqualObjects(restart.title, [NeoUnifiedCheatBrowser localizedText:@"fbneoRestartRequired" locale:@"fr"]);
}

- (NeoUnifiedCheatList*)directListWithItems:(NSArray*)items {
    NeoUnifiedCheatList* list=[NeoUnifiedCheatList new];list.locale=@"fr";list.engine=NSUUID.UUID.UUIDString;
    list.accepts=^BOOL(NSDictionary* program){return YES;};
    list.readState=^(void (^done)(NSDictionary*)){done(@{@"identity":[self identity],@"available":@YES,@"items":items});};
    self.catalog.rows=@[({NSMutableDictionary* game=[[self game] mutableCopy];game[@"installed"]=@YES;game[@"match"]=@"exact";game;})];
    self.catalog.codes=@[[self program:@"body" dependencies:@[]]];
    UIViewController* root=[UIViewController new];self.navigation=[[UINavigationController alloc] initWithRootViewController:root];
    self.window.rootViewController=self.navigation;[self.window makeKeyAndVisible];
    [self.navigation pushViewController:list animated:NO];[list loadViewIfNeeded];
    [self waitFor:^BOOL{return [list tableView:list.tableView numberOfRowsInSection:1]==1;}];
    return list;
}
- (void)testDirectListDependencyClosureStartsDisabledAndRejectsPartialPrograms {
    NSDictionary* game=[self game];NSDictionary* a=[self program:@"a" dependencies:@[]],*b=[self program:@"b" dependencies:@[@"a"]];
    NSArray* selections=[NeoUnifiedCheatList selectionsForGame:game programs:@[a,b] accepts:^BOOL(NSDictionary* p){return YES;}];
    XCTAssertEqual(selections.count,2U);NSArray* closure=selections.lastObject[@"programs"];
    XCTAssertEqual(closure.count,2U);XCTAssertEqualObjects(closure[0][@"id"],@"a");XCTAssertEqualObjects(closure[1][@"id"],@"b");
    XCTAssertEqualObjects(closure[0][@"enabled"],@NO);XCTAssertEqualObjects(closure[1][@"enabled"],@NO);
    XCTAssertEqualObjects(a[@"enabled"],@YES);
    NSArray* missing=[NeoUnifiedCheatList selectionsForGame:game programs:@[b] accepts:^BOOL(NSDictionary* p){return YES;}];XCTAssertEqual(missing.count,0U);
    NSArray* unsupported=[NeoUnifiedCheatList selectionsForGame:game programs:@[a,b] accepts:^BOOL(NSDictionary* p){return ![p[@"id"] isEqual:@"a"];}];XCTAssertEqual(unsupported.count,0U);
}
- (void)testDirectListDisplaysInstalledCodesWithoutImportingAndOneSwitchActivates {
    NeoUnifiedCheatList* list=[self directListWithItems:@[]];__block NSUInteger imports=0,sets=0;
    list.install=^(NSDictionary* g,NSArray* p,void (^done)(NSDictionary*,NSError*)){imports++;XCTAssertEqual(p.count,1U);XCTAssertEqualObjects(p[0][@"enabled"],@NO);done(@{@"key":@"native-one",@"name":@"body"},nil);};
    list.setEnabled=^(NSDictionary* item,BOOL enabled,void (^done)(BOOL)){sets++;XCTAssertTrue(enabled);XCTAssertEqualObjects(item[@"key"],@"native-one");done(YES);};
    UITableViewCell* cell=[list tableView:list.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:1]];
    XCTAssertEqualObjects(cell.textLabel.text,@"body");UISwitch* toggle=(id)cell.accessoryView;XCTAssertFalse(toggle.on);
    XCTAssertEqual(imports,0U);XCTAssertEqual(sets,0U);toggle.on=YES;[toggle sendActionsForControlEvents:UIControlEventValueChanged];
    [self waitFor:^BOOL{return sets==1;}];XCTAssertEqual(imports,1U);
}
- (void)testDirectListLateImportAfterPopCannotEnableACode {
    NeoUnifiedCheatList* list=[self directListWithItems:@[]];__block void (^late)(NSDictionary*,NSError*);__block NSUInteger sets=0;
    list.install=^(NSDictionary* g,NSArray* p,void (^done)(NSDictionary*,NSError*)){late=done;};
    list.setEnabled=^(NSDictionary* item,BOOL enabled,void (^done)(BOOL)){sets++;done(YES);};
    UITableViewCell* cell=[list tableView:list.tableView cellForRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:1]];
    UISwitch* toggle=(id)cell.accessoryView;toggle.on=YES;[toggle sendActionsForControlEvents:UIControlEventValueChanged];XCTAssertNotNil(late);
    [self.navigation popViewControllerAnimated:NO];late(@{@"key":@"native-one"},nil);XCTAssertEqual(sets,0U);
}
- (void)testDirectListDownloadButtonInstallsAllWithoutImportOrActivation {
    NeoUnifiedCheatList* list=[self directListWithItems:@[]];__block NSUInteger mutations=0;
    list.install=^(NSDictionary* g,NSArray* p,void (^done)(NSDictionary*,NSError*)){mutations++;};
    list.setEnabled=^(NSDictionary* item,BOOL enabled,void (^done)(BOOL)){mutations++;};
    [list tableView:list.tableView didSelectRowAtIndexPath:[NSIndexPath indexPathForRow:0 inSection:0]];
    XCTAssertEqual(self.catalog.installs,1U);XCTAssertEqual(mutations,0U);
    self.catalog.installCompletion(@{},nil);[self waitFor:^BOOL{return ![[list valueForKey:@"busy"] boolValue];}];XCTAssertEqual(mutations,0U);
}
@end
