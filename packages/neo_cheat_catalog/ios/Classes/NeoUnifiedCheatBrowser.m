// SPDX-License-Identifier: GPL-3.0-or-later
#import "NeoUnifiedCheatBrowser.h"
#import "Public/NeoUnifiedCheatCatalog.h"
#include <limits.h>

static unsigned long long NUCBSize(id value) {
    return [value isKindOfClass:NSNumber.class] && [value doubleValue] >= 0 ? [value unsignedLongLongValue] : 0;
}
static unsigned long long NUCBAddSize(unsigned long long left, unsigned long long right) {
    return ULLONG_MAX - left < right ? ULLONG_MAX : left + right;
}

static NSString *NUCBString(id value) {
    return [value isKindOfClass:NSString.class] ? value : @"";
}
static NSArray *NUCBArray(id value) {
    return [value isKindOfClass:NSArray.class] ? value : @[];
}
static NSString *NUCBLocale(NSString *locale) {
    NSString *normal = [[NUCBString(locale) stringByReplacingOccurrencesOfString:@"-" withString:@"_"] lowercaseString];
    if ([normal hasPrefix:@"zh_hant"] || [normal hasPrefix:@"zh_tw"] ||
        [normal hasPrefix:@"zh_hk"] || [normal hasPrefix:@"zh_mo"]) return @"zh_Hant";
    NSString *base = [normal componentsSeparatedByString:@"_"].firstObject;
    return [@[@"en", @"es", @"ru", @"zh", @"pt", @"fr", @"de", @"it", @"id", @"ja", @"ko"] containsObject:base] ? base : @"en";
}

/// Kept outside view state so locale tests can exercise the actual resource.
NSDictionary *NeoUnifiedCheatBrowserLabels(NSString *locale) {
    static NSDictionary *all;
    static dispatch_once_t once;
    dispatch_once(&once, ^{
        NSBundle *owner = [NSBundle bundleForClass:NeoUnifiedCheatBrowser.class];
        NSURL *bundleURL = [owner URLForResource:@"NeoCheatCatalog" withExtension:@"bundle"];
        if (!bundleURL) bundleURL = [NSBundle.mainBundle URLForResource:@"NeoCheatCatalog" withExtension:@"bundle"];
        NSBundle *resources = bundleURL ? [NSBundle bundleWithURL:bundleURL] : owner;
        NSURL *url = [resources URLForResource:@"labels" withExtension:@"json"];
        NSData *data = url ? [NSData dataWithContentsOfURL:url] : nil;
        id parsed = data ? [NSJSONSerialization JSONObjectWithData:data options:0 error:nil] : nil;
        all = [parsed isKindOfClass:NSDictionary.class] ? parsed : @{};
    });
    id result = all[NUCBLocale(locale)];
    return [result isKindOfClass:NSDictionary.class] ? result : @{};
}

typedef NS_ENUM(NSInteger, NUCBPage) { NUCBGames, NUCBPrograms, NUCBProgram };

@interface NUCBTextCell : UITableViewCell
@property(nonatomic, strong) UILabel *headline;
@property(nonatomic, strong) UILabel *subtitle;
@end
@implementation NUCBTextCell
- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)identifier {
    if ((self = [super initWithStyle:UITableViewCellStyleDefault reuseIdentifier:identifier])) {
        _headline = [[UILabel alloc] init];
        _subtitle = [[UILabel alloc] init];
        for (UILabel *label in @[_headline, _subtitle]) {
            label.numberOfLines = 0;
            label.lineBreakMode = NSLineBreakByWordWrapping;
            label.adjustsFontForContentSizeCategory = YES;
        }
        _headline.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
        _subtitle.font = [UIFont preferredFontForTextStyle:UIFontTextStyleSubheadline];
        UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:@[_headline, _subtitle]];
        stack.axis = UILayoutConstraintAxisVertical;
        stack.spacing = 8;
        stack.translatesAutoresizingMaskIntoConstraints = NO;
        [self.contentView addSubview:stack];
        UILayoutGuide *guide = self.contentView.layoutMarginsGuide;
        [NSLayoutConstraint activateConstraints:@[
            [stack.leadingAnchor constraintEqualToAnchor:guide.leadingAnchor],
            [stack.trailingAnchor constraintEqualToAnchor:guide.trailingAnchor],
            [stack.topAnchor constraintEqualToAnchor:guide.topAnchor],
            [stack.bottomAnchor constraintEqualToAnchor:guide.bottomAnchor]
        ]];
    }
    return self;
}
@end

@interface NUCBCodeCell : UITableViewCell
@property(nonatomic, strong) UITextView *codeView;
@end
@implementation NUCBCodeCell
- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)identifier {
    if ((self = [super initWithStyle:style reuseIdentifier:identifier])) {
        self.selectionStyle = UITableViewCellSelectionStyleNone;
        _codeView = [[UITextView alloc] initWithFrame:CGRectZero];
        _codeView.translatesAutoresizingMaskIntoConstraints = NO;
        _codeView.editable = NO;
        _codeView.selectable = YES;
        _codeView.backgroundColor = UIColor.clearColor;
        _codeView.adjustsFontForContentSizeCategory = YES;
        _codeView.font = [UIFontMetrics.defaultMetrics scaledFontForFont:[UIFont monospacedSystemFontOfSize:14 weight:UIFontWeightRegular]];
        [self.contentView addSubview:_codeView];
        UILayoutGuide *guide = self.contentView.layoutMarginsGuide;
        [NSLayoutConstraint activateConstraints:@[
            [_codeView.leadingAnchor constraintEqualToAnchor:guide.leadingAnchor],
            [_codeView.trailingAnchor constraintEqualToAnchor:guide.trailingAnchor],
            [_codeView.topAnchor constraintEqualToAnchor:guide.topAnchor],
            [_codeView.bottomAnchor constraintEqualToAnchor:guide.bottomAnchor],
            [_codeView.heightAnchor constraintEqualToConstant:240]
        ]];
    }
    return self;
}
@end

@interface NUCBProgressCell : UITableViewCell
@property(nonatomic, strong) UILabel *progressLabel;
@property(nonatomic, strong) UIProgressView *progressView;
@end
@implementation NUCBProgressCell
- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString *)identifier {
    if ((self = [super initWithStyle:style reuseIdentifier:identifier])) {
        self.selectionStyle = UITableViewCellSelectionStyleNone;
        _progressLabel = [[UILabel alloc] init];
        _progressLabel.numberOfLines = 0;
        _progressLabel.adjustsFontForContentSizeCategory = YES;
        _progressLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleSubheadline];
        _progressView = [[UIProgressView alloc] initWithProgressViewStyle:UIProgressViewStyleDefault];
        UIStackView *stack = [[UIStackView alloc] initWithArrangedSubviews:@[_progressLabel, _progressView]];
        stack.axis = UILayoutConstraintAxisVertical;
        stack.spacing = 12;
        stack.translatesAutoresizingMaskIntoConstraints = NO;
        [self.contentView addSubview:stack];
        UILayoutGuide *guide = self.contentView.layoutMarginsGuide;
        [NSLayoutConstraint activateConstraints:@[
            [stack.leadingAnchor constraintEqualToAnchor:guide.leadingAnchor],
            [stack.trailingAnchor constraintEqualToAnchor:guide.trailingAnchor],
            [stack.topAnchor constraintEqualToAnchor:guide.topAnchor],
            [stack.bottomAnchor constraintEqualToAnchor:guide.bottomAnchor]
        ]];
    }
    return self;
}
@end

@interface NeoUnifiedCheatBrowser () <UISearchResultsUpdating, UIAdaptivePresentationControllerDelegate>
@property(nonatomic, strong) NeoUnifiedCheatCatalog *catalog;
@property(nonatomic, copy) NSDictionary *identity;
@property(nonatomic, copy) NSString *engine;
@property(nonatomic, copy) NSString *locale;
@property(nonatomic, copy) NSDictionary *labels;
@property(nonatomic, copy) BOOL (^accepts)(NSDictionary *);
@property(nonatomic, copy) void (^importHandler)(NSDictionary *, NSArray *, void (^)(NSError *));
@property(nonatomic) NUCBPage page;
@property(nonatomic, copy) NSDictionary *game;
@property(nonatomic, copy) NSDictionary *program;
@property(nonatomic, copy) NSArray<NSDictionary *> *games;
@property(nonatomic, copy) NSArray<NSDictionary *> *programs;
@property(nonatomic, copy) NSDictionary<NSString *, NSDictionary *> *programsByID;
@property(nonatomic, copy) NSDictionary *summary;
@property(nonatomic, copy) NSDictionary *progress;
@property(nonatomic, strong) NSError *lastError;
@property(nonatomic, copy) NSString *statusKey;
@property(nonatomic, copy) NSString *query;
@property(nonatomic, strong) UISearchController *search;
@property(nonatomic) BOOL loading;
@property(nonatomic) BOOL installing;
@property(nonatomic) BOOL importing;
@property(nonatomic) BOOL retryAvailable;
@property(nonatomic) BOOL closed;
@property(nonatomic) NSUInteger failedPacks;
@property(nonatomic) NSUInteger generation;
@property(nonatomic) unsigned long long downloadEstimate;
@property(nonatomic) unsigned long long offlineEstimate;
@property(nonatomic) BOOL downloadEstimateKnown;
@property(nonatomic) BOOL offlineEstimateKnown;
@end

@implementation NeoUnifiedCheatBrowser

+ (NSString *)localizedText:(NSString *)key locale:(NSString *)locale {
    NSString *value = NUCBString(NeoUnifiedCheatBrowserLabels(locale)[key]);
    return value.length ? value : key;
}

+ (void)presentFrom:(UIViewController *)presenter identity:(NSDictionary *)identity
             engine:(NSString *)engine locale:(NSString *)locale
            accepts:(BOOL (^)(NSDictionary *))accepts
      importHandler:(void (^)(NSDictionary *, NSArray *, void (^)(NSError *)))importHandler {
    if (!presenter || !accepts || !importHandler) return;
    if (!NSThread.isMainThread) {
        dispatch_async(dispatch_get_main_queue(), ^{
            [self presentFrom:presenter identity:identity engine:engine locale:locale accepts:accepts importHandler:importHandler];
        });
        return;
    }
    if (presenter.isBeingDismissed || presenter.presentedViewController) return;
    NeoUnifiedCheatBrowser *browser = [[self alloc] initWithIdentity:identity engine:engine locale:locale accepts:accepts importHandler:importHandler];
    UINavigationController *navigation = [[UINavigationController alloc] initWithRootViewController:browser];
    navigation.modalPresentationStyle = UIModalPresentationPageSheet;
    navigation.presentationController.delegate = browser;
    [presenter presentViewController:navigation animated:YES completion:nil];
}

- (instancetype)initWithIdentity:(NSDictionary *)identity engine:(NSString *)engine locale:(NSString *)locale
                        accepts:(BOOL (^)(NSDictionary *))accepts
                  importHandler:(void (^)(NSDictionary *, NSArray *, void (^)(NSError *)))importHandler {
    if ((self = [super initWithStyle:UITableViewStyleInsetGrouped])) {
        _catalog = NeoUnifiedCheatCatalog.sharedCatalog;
        _identity = [identity isKindOfClass:NSDictionary.class] ? [identity copy] : @{};
        _engine = [NUCBString(engine) copy];
        _locale = NUCBLocale(locale);
        _labels = NeoUnifiedCheatBrowserLabels(_locale);
        _accepts = [accepts copy];
        _importHandler = [importHandler copy];
        _games = @[];
        _programs = @[];
        _programsByID = @{};
        _summary = @{};
        _progress = @{};
        _query = @"";
        _statusKey = @"loading";
    }
    return self;
}

- (NSString *)text:(NSString *)key {
    // Missing official translations fail the resource gate before packaging.
    // Do not expose an English NSError as a translated product explanation.
    NSString *value = NUCBString(self.labels[key]);
    return value.length ? value : key;
}
- (NSString *)text:(NSString *)key values:(NSDictionary *)values {
    NSString *result = [self text:key];
    for (NSString *parameter in values) {
        NSString *marker = [NSString stringWithFormat:@"{%@}", parameter];
        result = [result stringByReplacingOccurrencesOfString:marker withString:[values[parameter] description]];
    }
    return result;
}
- (NSDictionary *)catalogueSizesForManifest:(NSDictionary *)manifest {
    unsigned long long download = 0, extracted = 0;
    for (id pack in NUCBArray(manifest[@"packs"])) {
        if ([pack isKindOfClass:NSDictionary.class]) download = NUCBAddSize(download, NUCBSize(pack[@"size"]));
    }
    for (id game in NUCBArray(manifest[@"games"])) {
        if ([game isKindOfClass:NSDictionary.class]) extracted = NUCBAddSize(extracted, NUCBSize(game[@"size"]));
    }
    return @{@"download_bytes": @(download), @"offline_bytes": @(NUCBAddSize(download, extracted))};
}
- (void)updateSizeEstimates:(NSDictionary *)manifest {
    if ([manifest[@"packs"] isKindOfClass:NSArray.class] && [manifest[@"games"] isKindOfClass:NSArray.class]) {
        NSDictionary *sizes = [self catalogueSizesForManifest:manifest];
        self.downloadEstimate = [sizes[@"download_bytes"] unsignedLongLongValue];
        self.offlineEstimate = [sizes[@"offline_bytes"] unsignedLongLongValue];
        self.downloadEstimateKnown = YES;
        self.offlineEstimateKnown = YES;
    } else if ([manifest[@"total_bytes"] isKindOfClass:NSNumber.class]) {
        self.downloadEstimate = NUCBSize(manifest[@"total_bytes"]);
        self.downloadEstimateKnown = YES;
    }
}
- (NSString *)sizeExplanation {
    NSString *download = self.downloadEstimateKnown ? [NSByteCountFormatter stringFromByteCount:(long long)MIN(self.downloadEstimate, (unsigned long long)LLONG_MAX) countStyle:NSByteCountFormatterCountStyleFile] : [self text:@"unknown"];
    NSString *offline = self.offlineEstimateKnown ? [NSByteCountFormatter stringFromByteCount:(long long)MIN(self.offlineEstimate, (unsigned long long)LLONG_MAX) countStyle:NSByteCountFormatterCountStyleFile] : [self text:@"unknown"];
    return [NSString stringWithFormat:@"%@\n%@", [self text:@"downloadSize" values:@{@"size": download}], [self text:@"storageSize" values:@{@"size": offline}]];
}
- (NSString *)joinedStrings:(id)values {
    NSMutableArray *clean = [NSMutableArray array];
    for (id value in NUCBArray(values)) if (NUCBString(value).length) [clean addObject:value];
    return clean.count ? [clean componentsJoinedByString:@", "] : [self text:@"unknown"];
}
- (NSString *)editionText:(NSDictionary *)game {
    NSString *text = [NSString stringWithFormat:@"%@\n%@: %@\n%@: %@\n%@: %@",
        NUCBString(game[@"title"]), [self text:@"regions"], [self joinedStrings:game[@"regions"]],
        [self text:@"languages"], [self joinedStrings:game[@"languages"]],
        [self text:@"revision"], NUCBString(game[@"revision"]).length ? game[@"revision"] : [self text:@"unknown"]];
    if ([game[@"parts"] isKindOfClass:NSNumber.class] && [game[@"parts"] unsignedIntegerValue] > 1) {
        NSNumber *part = [game[@"part"] isKindOfClass:NSNumber.class] ? game[@"part"] : @1;
        text = [text stringByAppendingFormat:@"\n%@", [self text:@"cataloguePart" values:@{@"part": part, @"parts": game[@"parts"]}]];
    }
    return text;
}
- (NSString *)provenanceText:(NSDictionary *)program {
    NSMutableOrderedSet *items = [NSMutableOrderedSet orderedSet];
    for (id source in NUCBArray(program[@"provenance"])) {
        if ([source isKindOfClass:NSString.class] && [source length]) [items addObject:source];
        if (![source isKindOfClass:NSDictionary.class]) continue;
        NSMutableArray *parts = [NSMutableArray array];
        for (NSString *key in @[@"source_name", @"source_id", @"source", @"name", @"author", @"url", @"license"]) {
            NSString *part = NUCBString(source[key]);
            if (part.length && ![parts containsObject:part]) [parts addObject:part];
        }
        for (id author in NUCBArray(source[@"authors"])) if (NUCBString(author).length && ![parts containsObject:author]) [parts addObject:author];
        if (parts.count) [items addObject:[parts componentsJoinedByString:@" · "]];
    }
    return items.count ? [items.array componentsJoinedByString:@"\n\n"] : [self text:@"unknown"];
}
- (NSString *)provenanceSummary:(NSDictionary *)program {
    NSMutableOrderedSet *names = [NSMutableOrderedSet orderedSet];
    for (id source in NUCBArray(program[@"provenance"])) {
        if ([source isKindOfClass:NSDictionary.class]) {
            for (NSString *key in @[@"source_name", @"source_id", @"source", @"name"]) {
                NSString *name = NUCBString(source[key]);
                if (name.length) { [names addObject:name]; break; }
            }
        }
    }
    return [NSString stringWithFormat:@"%@: %@", [self text:@"provenance"],
        names.count ? [names.array componentsJoinedByString:@", "] : [self text:@"unknown"]];
}
- (NSArray *)programInfoRows {
    NSMutableArray *rows = [NSMutableArray arrayWithArray:@[
        @{ @"title": NUCBString(self.program[@"name"]), @"detail": [self text:[self reasonForProgram:self.program] ?: @"compatible"] },
        @{ @"title": [self text:@"provenance"], @"detail": [self provenanceText:self.program] },
        @{ @"title": [self text:@"edition"], @"detail": [self editionText:self.game] }
    ]];
    NSMutableOrderedSet *notes = [NSMutableOrderedSet orderedSet];
    for (NSString *key in @[@"description", @"notes"]) {
        id value = self.program[key];
        if (NUCBString(value).length) [notes addObject:value];
        for (id line in NUCBArray(value)) if (NUCBString(line).length) [notes addObject:line];
    }
    if (notes.count) [rows addObject:@{ @"title": [self text:@"notes"], @"detail": [notes.array componentsJoinedByString:@"\n\n"] }];
    for (NSString *key in @[@"group", @"exclusive_group"]) {
        if (NUCBString(self.program[key]).length) [rows addObject:@{ @"title": [self text:[key isEqualToString:@"group"] ? @"group" : @"exclusiveGroup"], @"detail": self.program[key] }];
    }
    return rows;
}

- (void)viewDidLoad {
    [super viewDidLoad];
    self.view.backgroundColor = UIColor.systemGroupedBackgroundColor;
    self.tableView.rowHeight = UITableViewAutomaticDimension;
    self.tableView.estimatedRowHeight = 76;
    [self.tableView registerClass:NUCBCodeCell.class forCellReuseIdentifier:@"code"];
    [self.tableView registerClass:NUCBProgressCell.class forCellReuseIdentifier:@"progress"];
    self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:[self text:@"close"] style:UIBarButtonItemStyleDone target:self action:@selector(closeBrowser)];
    self.navigationItem.rightBarButtonItem.accessibilityIdentifier = @"unifiedCheats.close";
    self.title = self.page == NUCBGames ? [self text:@"title"] : self.page == NUCBPrograms ? NUCBString(self.game[@"title"]) : NUCBString(self.program[@"name"]);
    if (self.page == NUCBGames) {
        self.search = [[UISearchController alloc] initWithSearchResultsController:nil];
        self.search.searchResultsUpdater = self;
        self.search.obscuresBackgroundDuringPresentation = NO;
        self.search.searchBar.placeholder = [self text:@"searchPlaceholder"];
        self.search.searchBar.accessibilityIdentifier = @"unifiedCheats.search";
        self.navigationItem.searchController = self.search;
        self.navigationItem.hidesSearchBarWhenScrolling = NO;
        self.definesPresentationContext = YES;
        [self loadCatalogue];
    }
}
- (void)viewDidDisappear:(BOOL)animated {
    [super viewDidDisappear:animated];
    if (self.isMovingFromParentViewController || self.isBeingDismissed || self.navigationController.isBeingDismissed) {
        self.closed = YES;
        self.generation += 1;
    }
}
- (void)markNavigationClosed {
    for (UIViewController *controller in self.navigationController.viewControllers) {
        if ([controller isKindOfClass:NeoUnifiedCheatBrowser.class]) {
            NeoUnifiedCheatBrowser *browser = (NeoUnifiedCheatBrowser *)controller;
            browser.closed = YES;
            browser.generation += 1;
        }
    }
}
- (void)closeBrowser {
    [self markNavigationClosed];
    [self.navigationController dismissViewControllerAnimated:YES completion:nil];
}
- (void)presentationControllerDidDismiss:(UIPresentationController *)presentationController {
    [self markNavigationClosed];
}
- (BOOL)canPresent {
    return !self.closed && self.isViewLoaded && self.view.window &&
           self.navigationController.topViewController == self && !self.presentedViewController;
}
- (void)showError:(NSError *)error explanation:(NSString *)key {
    if (![self canPresent]) return;
    NSString *details = [NSString stringWithFormat:@"%@ (%ld)\n%@", error.domain, (long)error.code, error.localizedDescription ?: @""];
    UIAlertController *alert = [UIAlertController alertControllerWithTitle:[self text:key]
        message:[NSString stringWithFormat:@"%@\n\n%@", [self text:@"technicalDetails"], details]
        preferredStyle:UIAlertControllerStyleAlert];
    [alert addAction:[UIAlertAction actionWithTitle:[self text:@"close"] style:UIAlertActionStyleCancel handler:nil]];
    [self presentViewController:alert animated:YES completion:nil];
}

- (void)loadCatalogue {
    if (self.closed) return;
    self.loading = YES;
    self.statusKey = @"loading";
    [self.tableView reloadData];
    __weak typeof(self) weakSelf = self;
    [self.catalog loadWithCompletion:^(NSDictionary *summary, NSError *error) {
        typeof(self) self = weakSelf;
        if (!self || self.closed) return;
        self.loading = NO;
        self.summary = summary ?: @{};
        [self updateSizeEstimates:self.summary];
        self.lastError = error;
        self.statusKey = error ? @"loadFailed" : @"searchHelp";
        [self.tableView reloadData];
        if (summary) [self refreshGames];
    }];
}
- (void)downloadAll {
    if (self.closed || self.installing) return;
    self.installing = YES;
    self.failedPacks = 0;
    self.retryAvailable = NO;
    self.progress = @{};
    self.lastError = nil;
    [self.tableView reloadData];
    __weak typeof(self) weakSelf = self;
    [self.catalog installAllWithProgress:^(NSDictionary *progress) {
        typeof(self) self = weakSelf;
        if (!self || self.closed) return;
        self.progress = progress ?: @{};
        [self.tableView reloadSections:[NSIndexSet indexSetWithIndex:0] withRowAnimation:UITableViewRowAnimationNone];
    } completion:^(NSDictionary *result, NSError *error) {
        typeof(self) self = weakSelf;
        if (!self || self.closed) return;
        self.installing = NO;
        self.summary = result ?: self.summary;
        [self updateSizeEstimates:self.summary];
        self.progress = result ?: self.progress;
        self.failedPacks = NUCBArray(result[@"failed_packs"]).count;
        self.retryAvailable = error != nil || self.failedPacks > 0;
        self.lastError = error;
        self.statusKey = error ? @"downloadFailed" : @"installedReady";
        [self.tableView reloadData];
        [self refreshGames];
        if (error) [self showError:error explanation:@"downloadFailed"];
    }];
}
- (void)updateSearchResultsForSearchController:(UISearchController *)searchController {
    self.query = [NUCBString(searchController.searchBar.text) stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceAndNewlineCharacterSet];
    NSUInteger ticket = ++self.generation;
    __weak typeof(self) weakSelf = self;
    dispatch_after(dispatch_time(DISPATCH_TIME_NOW, 250 * NSEC_PER_MSEC), dispatch_get_main_queue(), ^{
        typeof(self) self = weakSelf;
        if (!self || self.closed || ticket != self.generation) return;
        [self refreshGames];
    });
}
- (void)refreshGames {
    if (self.closed) return;
    NSUInteger ticket = ++self.generation;
    self.loading = YES;
    self.statusKey = @"searching";
    [self.tableView reloadData];
    __weak typeof(self) weakSelf = self;
    void (^completion)(NSArray *, NSError *) = ^(NSArray *games, NSError *error) {
        typeof(self) self = weakSelf;
        if (!self || self.closed || ticket != self.generation) return;
        self.loading = NO;
        self.games = games ?: @[];
        self.statusKey = error ? @"lookupFailed" : self.games.count ? @"searchHelp" : @"noMatches";
        self.lastError = error;
        [self.tableView reloadData];
    };
    if (self.query.length) [self.catalog searchGames:self.query system:NUCBString(self.identity[@"system"]) completion:completion];
    else [self.catalog gamesForIdentity:self.identity completion:completion];
}

- (void)setProgramsForDisplay:(NSArray *)programs {
    NSMutableArray *rows = [NSMutableArray array];
    NSMutableDictionary *byID = [NSMutableDictionary dictionary];
    NSMutableSet *duplicateIDs = [NSMutableSet set];
    for (id program in programs) {
        if (![program isKindOfClass:NSDictionary.class]) continue;
        [rows addObject:program];
        NSString *identifier = NUCBString(program[@"id"]);
        if (identifier.length && byID[identifier]) [duplicateIDs addObject:identifier];
        if (identifier.length) byID[identifier] = program;
    }
    // Duplicate IDs are never usable as an unambiguous dependency target.
    for (NSString *identifier in duplicateIDs) [byID removeObjectForKey:identifier];
    self.programs = rows;
    self.programsByID = byID;
}
- (NSString *)localReasonForProgram:(NSDictionary *)program {
    if (self.game && [NeoUnifiedCheatCatalog gameHasConflict:self.game identity:self.identity]) return @"editionMismatch";
    NSString *status = NUCBString(program[@"status"]);
    if (![status isEqualToString:@"available"]) {
        if ([status isEqualToString:@"invalid"]) return @"invalid";
        if ([status isEqualToString:@"unresolved"]) return @"unresolved";
        if ([status isEqualToString:@"requires_engine"]) return @"requiresEngine";
        return @"unavailable";
    }
    if ((program[@"dependencies"] && ![program[@"dependencies"] isKindOfClass:NSArray.class]) ||
        (program[@"parameters"] && ![program[@"parameters"] isKindOfClass:NSArray.class])) return @"invalid";
    if (NUCBArray(program[@"parameters"]).count) return @"parametersRequired";
    if (!NUCBString(program[@"id"]).length || !NUCBString(program[@"code"]).length) return @"invalid";
    if (!self.programsByID[program[@"id"]]) return @"invalid";
    if (!self.accepts || !self.accepts(program)) return @"unsupported";
    return nil;
}
- (BOOL)collectProgram:(NSDictionary *)program visiting:(NSMutableSet *)visiting
              visited:(NSMutableSet *)visited ordered:(NSMutableArray *)ordered reason:(NSString **)reason {
    NSString *local = [self localReasonForProgram:program];
    if (local) { if (reason) *reason = local; return NO; }
    NSString *identifier = NUCBString(program[@"id"]);
    if ([visiting containsObject:identifier]) { if (reason) *reason = @"dependenciesCycle"; return NO; }
    if ([visited containsObject:identifier]) return YES;
    if (visited.count + visiting.count >= 1024) { if (reason) *reason = @"dependenciesMissing"; return NO; }
    [visiting addObject:identifier];
    for (id reference in NUCBArray(program[@"dependencies"])) {
        if (![reference isKindOfClass:NSString.class]) { if (reason) *reason = @"dependenciesMissing"; return NO; }
        NSDictionary *dependency = self.programsByID[reference];
        if (!dependency) { if (reason) *reason = @"dependenciesMissing"; return NO; }
        if (![self collectProgram:dependency visiting:visiting visited:visited ordered:ordered reason:reason]) return NO;
    }
    [visiting removeObject:identifier];
    [visited addObject:identifier];
    NSMutableDictionary *disabled = [program mutableCopy];
    disabled[@"enabled"] = @NO;
    [ordered addObject:[disabled copy]];
    return YES;
}
- (NSArray *)importClosureForProgram:(NSDictionary *)program reason:(NSString **)reason {
    NSMutableArray *ordered = [NSMutableArray array];
    if (![self collectProgram:program visiting:[NSMutableSet set] visited:[NSMutableSet set] ordered:ordered reason:reason]) return nil;
    NSMutableSet *exclusive = [NSMutableSet set];
    for (NSDictionary *part in ordered) {
        NSString *group = NUCBString(part[@"exclusive_group"]);
        if (group.length && [exclusive containsObject:group]) {
            if (reason) *reason = @"dependenciesExclusive";
            return nil;
        }
        if (group.length) [exclusive addObject:group];
    }
    return [ordered copy];
}
- (NSString *)reasonForProgram:(NSDictionary *)program {
    NSString *reason = nil;
    [self importClosureForProgram:program reason:&reason];
    return reason;
}
- (NSUInteger)compatibleCount {
    NSUInteger count = 0;
    for (NSDictionary *program in self.programs) if (![self reasonForProgram:program]) count++;
    return count;
}
- (NeoUnifiedCheatBrowser *)childBrowser {
    NeoUnifiedCheatBrowser *child = [[NeoUnifiedCheatBrowser alloc] initWithIdentity:self.identity engine:self.engine locale:self.locale accepts:self.accepts importHandler:self.importHandler];
    child.catalog = self.catalog;
    return child;
}
- (void)openGame:(NSDictionary *)game {
    if (self.closed || self.loading) return;
    self.loading = YES;
    [self.tableView reloadData];
    NSUInteger ticket = ++self.generation;
    __weak typeof(self) weakSelf = self;
    [self.catalog cheatsForGame:game completion:^(NSArray *programs, NSError *error) {
        typeof(self) self = weakSelf;
        if (!self || self.closed || ticket != self.generation) return;
        self.loading = NO;
        [self.tableView reloadData];
        if (error) { [self showError:error explanation:@"lookupFailed"]; return; }
        if (![self canPresent]) return;
        self.search.active = NO;
        NeoUnifiedCheatBrowser *child = [self childBrowser];
        child.page = NUCBPrograms;
        child.game = game;
        [child setProgramsForDisplay:programs];
        [self.navigationController pushViewController:child animated:YES];
    }];
}
- (void)chooseGame:(NSDictionary *)game {
    // Re-evaluate against the current identity. Search result titles alone
    // cannot promote a candidate to an exact edition.
    if ([NeoUnifiedCheatCatalog gameHasConflict:game identity:self.identity]) {
        NSMutableDictionary *readOnly = [game mutableCopy];
        readOnly[@"match"] = @"conflict";
        readOnly[@"edition_confirmed"] = @NO;
        [self openGame:readOnly];
        return;
    }
    NSString *match = [NeoUnifiedCheatCatalog matchGame:game identity:self.identity];
    if ([match isEqualToString:@"exact"]) {
        NSMutableDictionary *exact = [game mutableCopy];
        exact[@"match"] = @"exact";
        [self openGame:exact];
        return;
    }
    if (![self canPresent]) return;
    UIAlertController *confirmation = [UIAlertController alertControllerWithTitle:[self text:@"editionConfirmTitle"]
        message:[self text:@"editionConfirmMessage" values:@{@"edition": [self editionText:game]}]
        preferredStyle:UIAlertControllerStyleAlert];
    [confirmation addAction:[UIAlertAction actionWithTitle:[self text:@"cancel"] style:UIAlertActionStyleCancel handler:nil]];
    __weak typeof(self) weakSelf = self;
    [confirmation addAction:[UIAlertAction actionWithTitle:[self text:@"chooseEdition"] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
        NSMutableDictionary *confirmed = [game mutableCopy];
        confirmed[@"match"] = @"candidate";
        confirmed[@"edition_confirmed"] = @YES;
        [weakSelf openGame:confirmed];
    }]];
    [self presentViewController:confirmation animated:YES completion:nil];
}
- (void)importSelectedProgram {
    if (self.closed || self.importing || !self.importHandler) return;
    NSString *reason = nil;
    NSArray *complete = [self importClosureForProgram:self.program reason:&reason];
    if (!complete.count || reason) return;
    self.importing = YES;
    [self.tableView reloadData];
    __weak typeof(self) weakSelf = self;
    __block BOOL completed = NO;
    self.importHandler(self.game, complete, ^(NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            if (completed) return;
            completed = YES;
            typeof(self) self = weakSelf;
            if (!self || self.closed) return;
            self.importing = NO;
            [self.tableView reloadData];
            if (error) { [self showError:error explanation:@"importFailed"]; return; }
            if (![self canPresent]) return;
            UIAlertController *alert = [UIAlertController alertControllerWithTitle:[self text:@"importDoneTitle"]
                message:[self text:@"importDoneMessage"] preferredStyle:UIAlertControllerStyleAlert];
            [alert addAction:[UIAlertAction actionWithTitle:[self text:@"backToEngine"] style:UIAlertActionStyleDefault handler:^(UIAlertAction *action) {
                [weakSelf closeBrowser];
            }]];
            [self presentViewController:alert animated:YES completion:nil];
        });
    });
}

- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView {
    return self.page == NUCBProgram ? 5 : 2;
}
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section {
    if (self.page == NUCBGames) return section == 0 ? 3 + (self.retryAvailable ? 1 : 0) : (NSInteger)self.games.count + 1;
    if (self.page == NUCBPrograms) return section == 0 ? 2 : MAX((NSInteger)self.programs.count, 1);
    if (section == 0) return (NSInteger)[self programInfoRows].count;
    if (section == 2) return MAX((NSInteger)NUCBArray(self.program[@"dependencies"]).count, 1);
    return 1;
}
- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section {
    if (self.page == NUCBGames) return section == 1 ? [self text:@"edition"] : nil;
    if (self.page == NUCBPrograms) return section == 1 ? [self text:@"programs"] : [self text:@"edition"];
    return @[[self text:@"programs"], [self text:@"code"], [self text:@"dependencies"], [self text:@"importDisabled"], [self text:@"technicalDetails"]][section];
}
- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section {
    if (self.page == NUCBGames && section == 0) return [self text:@"downloadExplanation"];
    if (self.page == NUCBPrograms && section == 1 && [self compatibleCount] == 0)
        return [self text:[NeoUnifiedCheatCatalog gameHasConflict:self.game identity:self.identity] ? @"editionMismatch" : @"noCompatible"];
    if (self.page == NUCBProgram && section == 3) return [self text:@"noAutoEnable"];
    return nil;
}
- (UITableViewCell *)cellWithTitle:(NSString *)title detail:(NSString *)detail identifier:(NSString *)identifier {
    NUCBTextCell *cell = [self.tableView dequeueReusableCellWithIdentifier:identifier];
    if (!cell) cell = [[NUCBTextCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:identifier];
    cell.headline.text = title;
    cell.headline.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    cell.headline.textColor = UIColor.labelColor;
    cell.subtitle.text = detail.length ? detail : nil;
    cell.subtitle.hidden = !detail.length;
    cell.subtitle.font = [UIFont preferredFontForTextStyle:UIFontTextStyleSubheadline];
    cell.subtitle.textColor = UIColor.secondaryLabelColor;
    cell.accessoryType = UITableViewCellAccessoryNone;
    cell.selectionStyle = UITableViewCellSelectionStyleNone;
    cell.accessibilityTraits = UIAccessibilityTraitStaticText;
    cell.isAccessibilityElement = YES;
    cell.accessibilityLabel = title;
    cell.accessibilityValue = detail;
    cell.accessibilityIdentifier = nil;
    return cell;
}
- (void)makeActionCell:(UITableViewCell *)cell enabled:(BOOL)enabled identifier:(NSString *)identifier {
    ((NUCBTextCell *)cell).headline.textColor = enabled ? self.view.tintColor : UIColor.tertiaryLabelColor;
    cell.selectionStyle = enabled ? UITableViewCellSelectionStyleDefault : UITableViewCellSelectionStyleNone;
    cell.accessibilityTraits = UIAccessibilityTraitButton | (enabled ? UIAccessibilityTraitNone : UIAccessibilityTraitNotEnabled);
    cell.accessibilityIdentifier = identifier;
}
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)indexPath {
    NSInteger section = indexPath.section, row = indexPath.row;
    if (self.page == NUCBGames && section == 0) {
        if (row == 0) {
            BOOL installed = [self.summary[@"installed_games"] unsignedIntegerValue] > 0;
            UITableViewCell *cell = [self cellWithTitle:[self text:self.installing ? @"downloading" : installed ? @"updateAll" : @"downloadAll"] detail:[self sizeExplanation] identifier:@"action"];
            [self makeActionCell:cell enabled:!self.installing identifier:@"unifiedCheats.downloadAll"];
            return cell;
        }
        if (row == 1) {
            NUCBProgressCell *cell = [tableView dequeueReusableCellWithIdentifier:@"progress" forIndexPath:indexPath];
            NSDictionary *info = self.installing ? self.progress : self.summary;
            unsigned long long total = [info[@"total_bytes"] unsignedLongLongValue];
            unsigned long long done = [info[self.installing ? @"completed_bytes" : @"installed_bytes"] unsignedLongLongValue];
            if (!self.installing && !done) done = [info[@"completed_bytes"] unsignedLongLongValue];
            NSString *bytes = [self text:@"progressBytes" values:@{@"done": [NSByteCountFormatter stringFromByteCount:(long long)done countStyle:NSByteCountFormatterCountStyleFile], @"total": [NSByteCountFormatter stringFromByteCount:(long long)total countStyle:NSByteCountFormatterCountStyleFile]}];
            NSNumber *completed = info[self.installing ? @"completed_packs" : @"installed_packs"];
            if (!self.installing && !completed) completed = @([info[@"completed_packs"] unsignedIntegerValue] - MIN([info[@"completed_packs"] unsignedIntegerValue], self.failedPacks));
            NSString *counts = [self text:@"progressPacks" values:@{@"done": completed ?: @0, @"total": info[@"total_packs"] ?: @0}];
            cell.progressLabel.text = [NSString stringWithFormat:@"%@\n%@", counts, bytes];
            cell.progressView.progress = total ? MIN(1.0, (double)done / (double)total) : 0;
            cell.progressView.accessibilityLabel = [self text:@"downloading"];
            cell.progressView.accessibilityValue = cell.progressLabel.text;
            cell.accessibilityIdentifier = @"unifiedCheats.progress";
            return cell;
        }
        if (row == 3) {
            UITableViewCell *cell = [self cellWithTitle:[self text:@"retryDownloads"] detail:nil identifier:@"retry"];
            [self makeActionCell:cell enabled:!self.installing identifier:@"unifiedCheats.retry"];
            return cell;
        }
        NSString *title = [self text:@"readyCount" values:@{@"games": self.summary[@"installed_games"] ?: @0}];
        NSString *detail = self.failedPacks ? [self text:@"partialFailure" values:@{@"count": @(self.failedPacks)}] : [self text:@"downloadExplanation"];
        return [self cellWithTitle:title detail:detail identifier:@"summary"];
    }
    if (self.page == NUCBGames) {
        if (row == 0) {
            UITableViewCell *cell = [self cellWithTitle:[self text:self.statusKey ?: @"searchHelp"] detail:self.lastError ? [self text:@"technicalDetails"] : nil identifier:@"status"];
            if (self.lastError) [self makeActionCell:cell enabled:YES identifier:@"unifiedCheats.errorDetails"];
            return cell;
        }
        NSDictionary *game = self.games[row - 1];
        NSString *match = [NeoUnifiedCheatCatalog matchGame:game identity:self.identity];
        NSString *status = [self text:[NeoUnifiedCheatCatalog gameHasConflict:game identity:self.identity] ? @"editionMismatch" : [match isEqualToString:@"exact"] ? @"exactMatch" : @"candidateMatch"];
        NSString *detail = [NSString stringWithFormat:@"%@\n%@", [self editionText:game], status];
        UITableViewCell *cell = [self cellWithTitle:NUCBString(game[@"title"]) detail:detail identifier:@"game"];
        cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
        cell.selectionStyle = self.loading ? UITableViewCellSelectionStyleNone : UITableViewCellSelectionStyleDefault;
        cell.accessibilityTraits = UIAccessibilityTraitButton;
        cell.accessibilityIdentifier = @"unifiedCheats.game";
        return cell;
    }
    if (self.page == NUCBPrograms) {
        if (section == 0 && row == 0) return [self cellWithTitle:[self editionText:self.game] detail:nil identifier:@"edition"];
        if (section == 0) return [self cellWithTitle:[self text:@"availableCount" values:@{@"count": @([self compatibleCount])}] detail:[self text:[NeoUnifiedCheatCatalog gameHasConflict:self.game identity:self.identity] ? @"editionMismatch" : @"noAutoEnable"] identifier:@"count"];
        if (!self.programs.count) return [self cellWithTitle:[self text:@"noCompatible"] detail:nil identifier:@"empty"];
        NSDictionary *program = self.programs[row];
        NSString *reason = [self reasonForProgram:program];
        NSMutableArray *details = [NSMutableArray arrayWithObject:[self text:reason ?: @"compatible"]];
        if (NUCBString(program[@"group"]).length) [details addObject:program[@"group"]];
        [details addObject:[self provenanceSummary:program]];
        UITableViewCell *cell = [self cellWithTitle:NUCBString(program[@"name"]) detail:[details componentsJoinedByString:@"\n"] identifier:@"program"];
        cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
        cell.selectionStyle = UITableViewCellSelectionStyleDefault;
        cell.accessibilityTraits = UIAccessibilityTraitButton;
        cell.accessibilityIdentifier = @"unifiedCheats.program";
        return cell;
    }
    if (section == 0) {
        NSDictionary *info = [self programInfoRows][row];
        return [self cellWithTitle:info[@"title"] detail:info[@"detail"] identifier:@"programInfo"];
    }
    if (section == 1) {
        NUCBCodeCell *cell = [tableView dequeueReusableCellWithIdentifier:@"code" forIndexPath:indexPath];
        cell.codeView.text = NUCBString(self.program[@"code"]);
        cell.codeView.accessibilityLabel = [self text:@"code"];
        cell.codeView.accessibilityIdentifier = @"unifiedCheats.completeProgram";
        return cell;
    }
    if (section == 2) {
        NSArray *dependencies = NUCBArray(self.program[@"dependencies"]);
        if (!dependencies.count) return [self cellWithTitle:[self text:@"noDependencies"] detail:nil identifier:@"dependency"];
        id reference = dependencies[row];
        NSDictionary *dependency = [reference isKindOfClass:NSString.class] ? self.programsByID[reference] : nil;
        return [self cellWithTitle:dependency ? NUCBString(dependency[@"name"]) : [self text:@"dependenciesMissing"] detail:dependency ? [self text:[self reasonForProgram:dependency] ?: @"compatible"] : nil identifier:@"dependency"];
    }
    if (section == 3) {
        NSString *reason = [self reasonForProgram:self.program];
        UITableViewCell *cell = [self cellWithTitle:[self text:self.importing ? @"importing" : @"importDisabled"] detail:reason ? [self text:reason] : [self text:@"noAutoEnable"] identifier:@"import"];
        [self makeActionCell:cell enabled:!self.importing && !reason identifier:@"unifiedCheats.importDisabled"];
        return cell;
    }
    NSMutableDictionary *metadata = [self.program mutableCopy];
    [metadata removeObjectForKey:@"code"];
    [metadata removeObjectForKey:@"lines"];
    NSData *json = [NSJSONSerialization isValidJSONObject:metadata] ? [NSJSONSerialization dataWithJSONObject:metadata options:NSJSONWritingPrettyPrinted | NSJSONWritingSortedKeys error:nil] : nil;
    NUCBCodeCell *cell = [tableView dequeueReusableCellWithIdentifier:@"code" forIndexPath:indexPath];
    cell.codeView.text = json ? [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding] : @"";
    cell.codeView.accessibilityLabel = [self text:@"technicalDetails"];
    cell.codeView.accessibilityIdentifier = @"unifiedCheats.metadata";
    return cell;
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)indexPath {
    [tableView deselectRowAtIndexPath:indexPath animated:YES];
    if (self.closed) return;
    if (self.page == NUCBGames) {
        if (indexPath.section == 0 && (indexPath.row == 0 || indexPath.row == 3)) [self downloadAll];
        else if (indexPath.section == 1 && indexPath.row == 0 && self.lastError) [self showError:self.lastError explanation:self.statusKey ?: @"lookupFailed"];
        else if (indexPath.section == 1 && indexPath.row > 0 && !self.loading) [self chooseGame:self.games[indexPath.row - 1]];
    } else if (self.page == NUCBPrograms && indexPath.section == 1 && self.programs.count) {
        NeoUnifiedCheatBrowser *child = [self childBrowser];
        child.page = NUCBProgram;
        child.game = self.game;
        child.program = self.programs[indexPath.row];
        [child setProgramsForDisplay:self.programs];
        [self.navigationController pushViewController:child animated:YES];
    } else if (self.page == NUCBProgram && indexPath.section == 3) [self importSelectedProgram];
}
@end
