// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTextureHDPage.h"
#import "Public/NeoTextureCatalog.h"
#import "Public/NeoTexturePackStore.h"
#import "Public/NeoTextureIdentityReader.h"
#import "NeoTextureSupport.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <Metal/Metal.h>

#pragma mark - Labels

static NSDictionary *Labels(void) {
  static NSDictionary *labels;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    for (NSBundle *bundle in @[[NSBundle bundleForClass:NeoTextureHDPage.class], NSBundle.mainBundle]) {
      NSURL *url = [bundle URLForResource:@"NeoTextureCatalog" withExtension:@"bundle"];
      NSBundle *resources = url ? [NSBundle bundleWithURL:url] : bundle;
      NSURL *file = [resources URLForResource:@"labels" withExtension:@"json"];
      NSDictionary *json = file ? NeoTexJSONDictionary([NSData dataWithContentsOfURL:file]) : nil;
      if (json.count) { labels = json; break; }
    }
    if (!labels) labels = @{};
  });
  return labels;
}

static NSString *LanguageKey(NSString *locale) {
  NSString *value = [locale ?: NSLocale.preferredLanguages.firstObject ?: @"en" stringByReplacingOccurrencesOfString:@"-" withString:@"_"];
  if ([value hasPrefix:@"zh_Hant"] || [value hasPrefix:@"zh_TW"] || [value hasPrefix:@"zh_HK"] || [value hasPrefix:@"zh_MO"]) return @"zh_Hant";
  return [value componentsSeparatedByString:@"_"].firstObject.lowercaseString ?: @"en";
}

static NSString *Text(NSString *key, NSString *locale) {
  NSDictionary *labels = Labels();
  NSString *value = labels[LanguageKey(locale)][key] ?: labels[@"en"][key];
  return value ?: key;
}

static NSString *Fill(NSString *text, NSDictionary *values) {
  for (NSString *name in values) {
    id value = values[name];
    text = [text stringByReplacingOccurrencesOfString:[NSString stringWithFormat:@"{%@}", name]
                                           withString:[value isKindOfClass:NSString.class] ? value : [value description]];
  }
  return text;
}

#pragma mark - Rows

@interface NTRow : NSObject
@property(nonatomic, copy) NSString *title;
@property(nonatomic, copy) NSString *detail;
@property(nonatomic, copy) NSString *identifier;
@property(nonatomic, assign) BOOL disclosure, disabled, destructive, checked, action;
@property(nonatomic, strong) NSNumber *toggle;  // non-nil: a switch with this value
@property(nonatomic, copy) void (^run)(void);
@property(nonatomic, copy) void (^switched)(BOOL on);
@end
@implementation NTRow
+ (instancetype)title:(NSString *)title detail:(NSString *)detail {
  NTRow *row = [self new];
  row.title = title ?: @"";
  row.detail = detail;
  return row;
}
@end

@interface NTSection : NSObject
@property(nonatomic, copy) NSString *header, *footer;
@property(nonatomic, strong) NSMutableArray<NTRow *> *rows;
@end
@implementation NTSection
+ (instancetype)header:(NSString *)header {
  NTSection *section = [self new];
  section.header = header;
  section.rows = [NSMutableArray array];
  return section;
}
@end

@interface NeoTextureTablePage ()
@property(nonatomic, strong) NSArray<NTSection *> *sections;
- (NSString *)t:(NSString *)key;
- (NSString *)t:(NSString *)key with:(NSDictionary *)values;
- (void)alert:(NSString *)title message:(NSString *)message;
- (void)confirm:(NSString *)title message:(NSString *)message action:(NSString *)action destructive:(BOOL)destructive
           then:(void (^)(void))then;
@end
@implementation NeoTextureTablePage
- (NSString *)t:(NSString *)key { return Text(key, self.locale); }
- (NSString *)t:(NSString *)key with:(NSDictionary *)values { return Fill(Text(key, self.locale), values); }
- (NSInteger)numberOfSectionsInTableView:(UITableView *)tableView { return (NSInteger)self.sections.count; }
- (NSInteger)tableView:(UITableView *)tableView numberOfRowsInSection:(NSInteger)section { return (NSInteger)self.sections[(NSUInteger)section].rows.count; }
- (NSString *)tableView:(UITableView *)tableView titleForHeaderInSection:(NSInteger)section { return self.sections[(NSUInteger)section].header; }
- (NSString *)tableView:(UITableView *)tableView titleForFooterInSection:(NSInteger)section { return self.sections[(NSUInteger)section].footer; }
- (UITableViewCell *)tableView:(UITableView *)tableView cellForRowAtIndexPath:(NSIndexPath *)path {
  NTRow *row = self.sections[(NSUInteger)path.section].rows[(NSUInteger)path.row];
  UITableViewCell *cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
  cell.textLabel.text = row.title;
  cell.textLabel.numberOfLines = 0;
  cell.detailTextLabel.text = row.detail;
  cell.detailTextLabel.numberOfLines = 0;
  cell.detailTextLabel.textColor = UIColor.secondaryLabelColor;
  cell.accessibilityIdentifier = row.identifier;
  if (row.action) cell.textLabel.textColor = row.destructive ? UIColor.systemRedColor : self.view.tintColor;
  if (row.disabled) { cell.textLabel.textColor = UIColor.tertiaryLabelColor; cell.selectionStyle = UITableViewCellSelectionStyleNone; }
  if (row.toggle) {
    UISwitch *control = [UISwitch new];
    control.on = row.toggle.boolValue;
    control.enabled = !row.disabled;
    control.accessibilityIdentifier = row.identifier;
    [control addTarget:self action:@selector(switchChanged:) forControlEvents:UIControlEventValueChanged];
    control.tag = path.section * 1000 + path.row;
    cell.accessoryView = control;
    cell.selectionStyle = UITableViewCellSelectionStyleNone;
  } else if (row.disclosure) {
    cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
  } else if (row.checked) {
    cell.accessoryType = UITableViewCellAccessoryCheckmark;
  }
  if (!row.run && !row.toggle && !row.disclosure) cell.selectionStyle = UITableViewCellSelectionStyleNone;
  return cell;
}
- (void)switchChanged:(UISwitch *)control {
  const NSUInteger section = (NSUInteger)(control.tag / 1000), index = (NSUInteger)(control.tag % 1000);
  if (section >= self.sections.count || index >= self.sections[section].rows.count) return;
  NTRow *row = self.sections[section].rows[index];
  if (row.switched && !row.disabled) row.switched(control.on);
}
- (void)tableView:(UITableView *)tableView didSelectRowAtIndexPath:(NSIndexPath *)path {
  [tableView deselectRowAtIndexPath:path animated:YES];
  NTRow *row = self.sections[(NSUInteger)path.section].rows[(NSUInteger)path.row];
  if (row.run && !row.disabled && !self.presentedViewController) row.run();
}
- (void)alert:(NSString *)title message:(NSString *)message {
  if (!self.view.window || self.presentedViewController) return;
  UIAlertController *alert = [UIAlertController alertControllerWithTitle:title message:message preferredStyle:UIAlertControllerStyleAlert];
  [alert addAction:[UIAlertAction actionWithTitle:[self t:@"ok"] style:UIAlertActionStyleCancel handler:nil]];
  [self presentViewController:alert animated:YES completion:nil];
}
- (void)confirm:(NSString *)title message:(NSString *)message action:(NSString *)action destructive:(BOOL)destructive
           then:(void (^)(void))then {
  if (!self.view.window || self.presentedViewController) return;
  UIAlertController *alert = [UIAlertController alertControllerWithTitle:title message:message preferredStyle:UIAlertControllerStyleAlert];
  [alert addAction:[UIAlertAction actionWithTitle:[self t:@"cancel"] style:UIAlertActionStyleCancel handler:nil]];
  [alert addAction:[UIAlertAction actionWithTitle:action style:destructive ? UIAlertActionStyleDestructive : UIAlertActionStyleDefault
                                          handler:^(UIAlertAction *a) { then(); }]];
  [self presentViewController:alert animated:YES completion:nil];
}
@end

#pragma mark - Shared formatting

static NSString *Bytes(id value) { return NeoTexFormatBytes([value unsignedLongLongValue]); }

static NSString *Region(NSString *region, NSString *locale) {
  NSString *key = [@"region" stringByAppendingString:region.capitalizedString ?: @""];
  NSString *text = Text(key, locale);
  return [text isEqualToString:key] ? region : text;
}

static NSString *GameIDs(NSDictionary *identity) {
  NSMutableArray *ids = [NSMutableArray array];
  for (NSDictionary *entry in [identity[@"identities"] isKindOfClass:NSArray.class] ? identity[@"identities"] : @[]) {
    NSString *value = NeoTexString(entry[@"value"]);
    // An N64 ROM name is matched in hexadecimal and shown as the name itself.
    if ([NeoTexString(entry[@"scheme"]) isEqualToString:@"n64-rom-name-hex"]) value = NeoTexN64RomName(value) ?: value;
    if (value.length) [ids addObject:value];
  }
  return [ids componentsJoinedByString:@", "];
}

static NSString *ErrorText(NSError *error, NSString *locale) {
  NSString *key = error.userInfo[@"key"] ?: @"failed";
  NSString *text = Text([@"error." stringByAppendingString:key], locale);
  if ([text hasPrefix:@"error."]) text = Text(@"error.failed", locale);
  NSMutableDictionary *values = [NSMutableDictionary dictionary];
  if (error.userInfo[@"required"]) values[@"required"] = Bytes(error.userInfo[@"required"]);
  if (error.userInfo[@"free"]) values[@"free"] = Bytes(error.userInfo[@"free"]);
  values[@"detail"] = NeoTexString(error.userInfo[@"detail"]);
  if ([error.userInfo[@"sourceIDs"] isKindOfClass:NSArray.class]) values[@"source"] = [error.userInfo[@"sourceIDs"] componentsJoinedByString:@", "];
  return Fill(text, values);
}

static NSString *JobText(NSDictionary *job, NSString *locale) {
  NSString *state = job[@"state"];
  const double total = [job[@"total"] doubleValue], received = [job[@"received"] doubleValue];
  NSString *percent = [NSString stringWithFormat:@"%d", total > 0 ? (int)MIN(100.0, received * 100.0 / total) : 0];
  if ([state isEqualToString:@"downloading"]) return Fill(Text(@"stateDownloading", locale), @{@"percent": percent, @"received": Bytes(job[@"received"]), @"total": Bytes(job[@"total"])});
  if ([state isEqualToString:@"installing"] || [state isEqualToString:@"verifying"]) return Fill(Text(@"stateInstalling", locale), @{@"percent": percent});
  if ([state isEqualToString:@"paused"]) return Text(@"statePaused", locale);
  if ([state isEqualToString:@"downloaded"]) return Text(@"stateDownloaded", locale);
  if ([state isEqualToString:@"failed"] && [job[@"error"] isKindOfClass:NSString.class])
    return Fill(Text(@"stateFailed", locale), @{@"reason": ErrorText([NSError errorWithDomain:@"" code:0 userInfo:@{@"key": job[@"error"]}], locale)});
  return nil;
}

static BOOL JobActive(NSDictionary *job) {
  return [@[@"downloading", @"installing", @"verifying"] containsObject:NeoTexString(job[@"state"])];
}

static BOOL DeviceReadsBC(void) {
  static BOOL reads;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    if (@available(iOS 16.4, *)) reads = [device respondsToSelector:@selector(supportsBCTextureCompression)] && device.supportsBCTextureCompression;
  });
  return reads;
}

// What the engine's own installer found doubtful about a pack, as one sentence.
static NSString *EngineReasons(NSDictionary *verdict, NSString *locale) {
  NSMutableArray *reasons = [NSMutableArray array];
  NSString *match = NeoTexString(verdict[@"match"]);
  if ([match isEqualToString:@"otherSerial"]) [reasons addObject:Text(@"reason.otherSerial", locale)];
  if ([match isEqualToString:@"noSerial"]) [reasons addObject:Text(@"reason.noSerial", locale)];
  if ([verdict[@"regionConflict"] boolValue]) [reasons addObject:Text(@"reason.region", locale)];
  if ([verdict[@"crcConflict"] boolValue]) [reasons addObject:Text(@"reason.crc", locale)];
  if ([verdict[@"uncertain"] boolValue]) [reasons addObject:Text(@"reason.uncertain", locale)];
  return [reasons componentsJoinedByString:@" · "];
}

// A console page without a game installs a pack for the game its author names.
static NSDictionary *DeclaredIdentity(NSDictionary *pack) {
  NSDictionary *game = [pack[@"games"] firstObject];
  NSDictionary *first = [game[@"identities"] firstObject];
  if (!NeoTexString(first[@"value"]).length) return nil;
  NSMutableDictionary *identity = [@{@"system": NeoTexString(pack[@"system"]), @"title": NeoTexString(game[@"title"]),
                                     @"identities": @[first], @"declared": @YES} mutableCopy];
  if ([game[@"regions"] count] == 1) identity[@"regions"] = game[@"regions"];
  return identity;
}

#pragma mark - Pack page

// The file host a verified manual pack is published on, as its product name.
static NSString *HostName(NSString *host) {
  NSDictionary *names = @{@"mega": @"MEGA", @"gdrive": @"Google Drive", @"mediafire": @"MediaFire", @"dropbox": @"Dropbox",
                          @"gamebanana": @"GameBanana", @"direct": @"—"};
  return names[host] ?: @"—";
}

@interface NeoTexturePackPage : NeoTextureTablePage <UIDocumentPickerDelegate>
@property(nonatomic, strong) NSDictionary *pack;
@property(nonatomic, strong) id<NeoTextureEngine> engine;
@property(nonatomic, copy) NSDictionary *identity;
@property(nonatomic, strong) NSDictionary *installed;
/// The pending import of a verified file: replace an existing folder, candidate confirmed.
@property(nonatomic) BOOL replaceOnImport, confirmedOnImport;
@end

@implementation NeoTexturePackPage

- (void)viewDidLoad {
  [super viewDidLoad];
  self.title = self.pack[@"title"];
  self.tableView.accessibilityIdentifier = @"neoTexturePack";
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(changed:) name:NeoTextureCatalogDidChangeNotification object:nil];
  [self reload];
}
- (void)dealloc { [[NSNotificationCenter defaultCenter] removeObserver:self]; }
- (void)changed:(NSNotification *)notification {
  NSString *pack = notification.userInfo[@"pack"];
  if (!pack || [pack isEqual:self.pack[@"id"]] || [pack isEqual:self.installed[@"folder"]]) [self reload];
}

// Installed folders are read off the main thread (an engine store may block).
- (void)reload {
  NSDictionary *pack = self.pack, *identity = self.identity;
  id<NeoTextureEngine> engine = self.engine;
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NSArray *rows = identity ? [NeoTexturePackStore.sharedStore installedForIdentity:identity engine:engine]
                             : [NeoTexturePackStore.sharedStore installedForEngine:engine];
    NSDictionary *found = nil;
    for (NSDictionary *row in rows) if ([row[@"pack_id"] isEqual:pack[@"id"]]) { found = row; break; }
    dispatch_async(dispatch_get_main_queue(), ^{
      self.installed = found;
      [self rebuild];
    });
  });
}

- (void)rebuild {
  NSDictionary *pack = self.pack;
  NSDictionary *job = [NeoTexturePackStore.sharedStore jobForPack:pack[@"id"]];
  NSMutableArray *sections = [NSMutableArray array];

  NTSection *about = [NTSection header:nil];
  NSMutableArray *games = [NSMutableArray array];
  for (NSDictionary *game in pack[@"games"]) {
    NSMutableArray *regions = [NSMutableArray array];
    for (NSString *region in game[@"regions"]) [regions addObject:Region(region, self.locale)];
    NSString *ids = GameIDs(game);
    [games addObject:[NSString stringWithFormat:@"%@ (%@%@%@)", game[@"title"], ids, regions.count ? @" · " : @"", [regions componentsJoinedByString:@", "]]];
  }
  [about.rows addObject:[NTRow title:[self t:@"detailGames"] detail:[games componentsJoinedByString:@"\n"]]];
  [about.rows addObject:[NTRow title:[self t:@"detailAuthor"] detail:[pack[@"authors"] componentsJoinedByString:@", "]]];
  [about.rows addObject:[NTRow title:[self t:@"detailVersion"] detail:NeoTexString(pack[@"version"])]];
  // A manual pack whose author's file was verified on CI: installed from that exact file.
  NSDictionary *verifiedFile = [pack[@"availability"] isEqual:@"manual"] && pack[@"install"] ? NeoTexVerifiedFile(pack) : nil;
  unsigned long long downloadSize = [pack[@"download"][@"size"] unsignedLongLongValue];
  if (!downloadSize) for (NSDictionary *part in pack[@"download"][@"parts"]) downloadSize += [part[@"size"] unsignedLongLongValue];
  NSString *download = [pack[@"download"][@"automatable"] boolValue] ? Bytes(@(downloadSize))
                       : verifiedFile ? [NSString stringWithFormat:@"%@ · %@", Bytes(verifiedFile[@"size"]), [self t:@"stateManual"]]
                                      : [self t:@"stateManual"];
  [about.rows addObject:[NTRow title:[self t:@"detailSize"] detail:[self t:@"detailSizeValue" with:@{@"download": download, @"install": pack[@"install"][@"bytes"] ? Bytes(pack[@"install"][@"bytes"]) : @"—"}]]];
  NSArray *formats = pack[@"install"][@"formats"] ?: @[];
  NSString *formatText = [[formats valueForKey:@"uppercaseString"] componentsJoinedByString:@", "];
  NSString *archive = NeoTexString(pack[@"download"][@"format"] ?: verifiedFile[@"format"]).uppercaseString;
  [about.rows addObject:[NTRow title:[self t:@"detailFormats"] detail:archive.length ? [NSString stringWithFormat:@"%@ · %@", archive, formatText] : formatText]];
  NSString *match = pack[@"match"];
  if (match && !self.identity[@"declared"]) [about.rows addObject:[NTRow title:[self t:@"detailCompatibility"] detail:[self t:[match isEqual:@"exact"] ? @"matchExact" : @"matchCandidate"]]];
  // Dolphin decodes DDS block formats only where the GPU samples them (iOS 16.4+, Apple GPUs that report BC).
  if ([formats containsObject:@"dds"] && [self.engine.engineID isEqualToString:@"dolphin"] && !DeviceReadsBC())
    about.footer = [self t:@"gpuNoBC"];
  [sections addObject:about];

  NTSection *terms = [NTSection header:[self t:@"detailLicence"]];
  NSDictionary *licence = pack[@"licence"];
  [terms.rows addObject:[NTRow title:NeoTexString(licence[@"summary"]) detail:NeoTexString(licence[@"redistribution"])]];
  if (NeoTexString(pack[@"credits"]).length) [terms.rows addObject:[NTRow title:[self t:@"detailCredits"] detail:pack[@"credits"]]];
  [terms.rows addObject:[NTRow title:[self t:@"detailSource"] detail:[NSString stringWithFormat:@"%@\n%@", NeoTexString(pack[@"source_id"]), NeoTexString(pack[@"page_url"])]]];
  [terms.rows addObject:[NTRow title:[self t:@"detailVerified"] detail:NeoTexString(pack[@"verified_at"])]];
  if (NeoTexString(pack[@"requirements"]).length) [terms.rows addObject:[NTRow title:[self t:@"detailRequirements"] detail:pack[@"requirements"]]];
  if (NeoTexString(pack[@"notes"]).length) [terms.rows addObject:[NTRow title:[self t:@"detailNotes"] detail:pack[@"notes"]]];
  NTRow *page = [NTRow title:[self t:@"actionOpenPage"] detail:nil];
  page.action = YES;
  page.identifier = @"neoTextureOpenPage";
  page.run = ^{
    NSURL *url = [NSURL URLWithString:NeoTexString(pack[@"page_url"])];
    if (url) [UIApplication.sharedApplication openURL:url options:@{} completionHandler:nil];
  };
  [terms.rows addObject:page];
  [sections addObject:terms];

  NTSection *actions = [NTSection header:nil];
  NSString *state = JobText(job, self.locale);
  if (self.installed) {
    NSString *installedVersion = NeoTexString(self.installed[@"version"]);
    NSString *installedDigest = NeoTexString(self.installed[@"sha256"]);
    NSString *packDigest = NeoTexString(pack[@"download"][@"sha256"] ?: [pack[@"download"][@"parts"] firstObject][@"sha256"] ?: verifiedFile[@"sha256"]);
    const BOOL update = (installedVersion.length && ![installedVersion isEqualToString:NeoTexString(pack[@"version"])]) ||
                        (installedDigest.length && packDigest.length && ![installedDigest isEqualToString:packDigest]);
    [actions.rows addObject:[NTRow title:[self t:update ? @"stateUpdate" : @"stateInstalled"]
                                  detail:[self t:@"installedSummary" with:@{@"files": self.installed[@"files"] ?: @"?", @"size": self.installed[@"bytes"] ? Bytes(self.installed[@"bytes"]) : @"?",
                                                                            @"folder": NeoTexString(self.installed[@"folder"])}]]];
    if (update && !JobActive(job) && !verifiedFile) [actions.rows addObject:[self installRow:@"actionUpdate" replace:YES]];
    if (update && !JobActive(job) && verifiedFile) [actions.rows addObject:[self importVerifiedRow:YES]];
  }
  if (state) [actions.rows addObject:[NTRow title:state detail:nil]];
  if (verifiedFile) {
    if (JobActive(job)) {
      NTRow *cancel = [NTRow title:[self t:@"actionCancel"] detail:nil];
      cancel.action = YES;
      cancel.destructive = YES;
      cancel.identifier = @"neoTextureCancel";
      cancel.run = ^{ [NeoTexturePackStore.sharedStore cancelPack:pack[@"id"]]; };
      [actions.rows addObject:cancel];
    } else if ([job[@"state"] isEqual:@"downloaded"]) {
      // The imported file is kept after a confirmation or a failed install: no need to pick it again.
      [actions.rows addObject:[self installRow:@"actionInstallDownloaded" replace:self.installed != nil]];
      NTRow *discard = [NTRow title:[self t:@"actionCancel"] detail:nil];
      discard.action = YES;
      discard.destructive = YES;
      discard.identifier = @"neoTextureDiscard";
      discard.run = ^{ [NeoTexturePackStore.sharedStore cancelPack:pack[@"id"]]; };
      [actions.rows addObject:discard];
    } else if (!self.installed) {
      [actions.rows addObject:[self importVerifiedRow:NO]];
    }
    actions.footer = [self t:@"manualVerifiedHelp" with:@{@"host": HostName(NeoTexString(verifiedFile[@"host"])), @"file": NeoTexString(verifiedFile[@"file_name"]),
                                                          @"size": Bytes(verifiedFile[@"size"])}];
  } else if (![pack[@"download"][@"automatable"] boolValue] || ![pack[@"availability"] isEqual:@"available"]) {
    actions.footer = [self t:[pack[@"availability"] isEqual:@"unavailable"] ? @"unavailableHelp" : @"manualHelp"];
  } else if (JobActive(job)) {
    NTRow *pause = [NTRow title:[self t:@"actionPause"] detail:nil];
    pause.action = YES;
    pause.identifier = @"neoTexturePause";
    pause.run = ^{ [NeoTexturePackStore.sharedStore pausePack:pack[@"id"]]; };
    if ([job[@"state"] isEqual:@"downloading"]) [actions.rows addObject:pause];
    NTRow *cancel = [NTRow title:[self t:@"actionCancel"] detail:nil];
    cancel.action = YES;
    cancel.destructive = YES;
    cancel.identifier = @"neoTextureCancel";
    cancel.run = ^{ [NeoTexturePackStore.sharedStore cancelPack:pack[@"id"]]; };
    [actions.rows addObject:cancel];
  } else if (!self.installed) {
    NSString *key = [job[@"state"] isEqual:@"paused"] ? @"actionResume" : [job[@"state"] isEqual:@"downloaded"] ? @"actionInstallDownloaded" : @"actionInstall";
    [actions.rows addObject:[self installRow:key replace:NO]];
    if ([job[@"state"] isEqual:@"paused"] || [job[@"state"] isEqual:@"downloaded"]) {
      NTRow *discard = [NTRow title:[self t:@"actionCancel"] detail:nil];
      discard.action = YES;
      discard.destructive = YES;
      discard.identifier = @"neoTextureDiscard";
      discard.run = ^{ [NeoTexturePackStore.sharedStore cancelPack:pack[@"id"]]; };
      [actions.rows addObject:discard];
    }
    actions.footer = [self t:@"installFooter" with:@{@"required": Bytes(@([NeoTexturePackStore requiredBytesForPack:pack downloaded:NO]))}];
  }
  if (self.installed && !JobActive(job)) {
    NTRow *remove = [NTRow title:[self t:@"actionRemove"] detail:nil];
    remove.action = YES;
    remove.destructive = YES;
    remove.identifier = @"neoTextureRemove";
    NSDictionary *installed = self.installed;
    __weak typeof(self) weakSelf = self;
    remove.run = ^{
      [weakSelf confirm:[weakSelf t:@"confirmRemoveTitle"] message:[weakSelf t:@"confirmRemoveMessage" with:@{@"folder": NeoTexString(installed[@"folder"])}]
                 action:[weakSelf t:@"remove"] destructive:YES then:^{
        [NeoTexturePackStore.sharedStore removeInstalled:installed engine:weakSelf.engine completion:^(NSError *error) {
          if (error) [weakSelf alert:[weakSelf t:@"title"] message:ErrorText(error, weakSelf.locale)];
          [weakSelf reload];
        }];
      }];
    };
    [actions.rows addObject:remove];
  }
  if (actions.rows.count || actions.footer) [sections addObject:actions];
  self.sections = sections;
  [self.tableView reloadData];
}

- (NTRow *)installRow:(NSString *)key replace:(BOOL)replace {
  NTRow *row = [NTRow title:[self t:key] detail:nil];
  row.action = YES;
  row.identifier = @"neoTextureInstall";
  __weak typeof(self) weakSelf = self;
  row.run = ^{
    NeoTexturePackPage *page = weakSelf;
    if (!page) return;
    if ([page.pack[@"match"] isEqual:@"candidate"] && page.identity) {
      NSString *source = GameIDs([page.pack[@"games"] firstObject]);
      [page confirm:[page t:@"confirmCandidateTitle"]
            message:[page t:@"confirmCandidateMessage" with:@{@"source": source, @"game": GameIDs(page.identity)}]
             action:[page t:@"confirm"] destructive:NO then:^{ [page install:replace confirmed:YES]; }];
    } else {
      [page install:replace confirmed:NO];
    }
  };
  return row;
}

- (NTRow *)importVerifiedRow:(BOOL)replace {
  NTRow *row = [NTRow title:[self t:@"actionImportVerified"] detail:nil];
  row.action = YES;
  row.disabled = NeoTexturePackStore.sharedStore.isBusy;
  row.identifier = @"neoTextureImportVerified";
  __weak typeof(self) weakSelf = self;
  row.run = ^{
    NeoTexturePackPage *page = weakSelf;
    if (!page) return;
    void (^pick)(void) = ^{
      NSMutableArray<UTType *> *types = [NSMutableArray arrayWithObject:UTTypeZIP];
      UTType *sevenZip = [UTType typeWithFilenameExtension:@"7z"];
      if (sevenZip) [types addObject:sevenZip];
      UIDocumentPickerViewController *picker = [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:types asCopy:NO];
      picker.delegate = page;
      picker.allowsMultipleSelection = NO;
      page.replaceOnImport = replace;
      [page presentViewController:picker animated:YES completion:nil];
    };
    if ([page.pack[@"match"] isEqual:@"candidate"] && page.identity) {
      NSString *source = GameIDs([page.pack[@"games"] firstObject]);
      [page confirm:[page t:@"confirmCandidateTitle"]
            message:[page t:@"confirmCandidateMessage" with:@{@"source": source, @"game": GameIDs(page.identity)}]
             action:[page t:@"confirm"] destructive:NO then:^{ page.confirmedOnImport = YES; pick(); }];
    } else {
      page.confirmedOnImport = NO;
      pick();
    }
  };
  return row;
}

- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
  NSURL *url = urls.firstObject;
  if (!url) return;
  [controller dismissViewControllerAnimated:YES completion:^{
    [self installFile:url replace:self.replaceOnImport confirmed:self.confirmedOnImport];
  }];
}

- (void)installFile:(NSURL *)url replace:(BOOL)replace confirmed:(BOOL)confirmed {
  __weak typeof(self) weakSelf = self;
  [NeoTexturePackStore.sharedStore installPack:self.pack fromFile:url engine:self.engine identity:self.identity replace:replace confirmed:confirmed
                                    completion:^(NSDictionary *result, NSError *error) {
    NeoTexturePackPage *page = weakSelf;
    if (!page) return;
    if (error.code == NeoTexturePackErrorConflict) {
      // Asked before the file is read: picked again by the same URL once confirmed.
      [page confirm:[page t:@"confirmReplaceTitle"]
            message:[page t:@"confirmReplaceMessage" with:@{@"folder": NeoTexString(error.userInfo[@"folder"]),
                                                             @"title": [error.userInfo[@"manual"] boolValue] ? [page t:@"installedManual"] : NeoTexString(error.userInfo[@"title"])}]
             action:[page t:@"actionReplace"] destructive:NO then:^{ [page installFile:url replace:YES confirmed:confirmed]; }];
      return;
    }
    [page finishInstall:result error:error replace:replace confirmed:confirmed];
  }];
}

- (void)install:(BOOL)replace confirmed:(BOOL)confirmed {
  __weak typeof(self) weakSelf = self;
  [NeoTexturePackStore.sharedStore installPack:self.pack engine:self.engine identity:self.identity replace:replace confirmed:confirmed
                                    completion:^(NSDictionary *result, NSError *error) {
    NeoTexturePackPage *page = weakSelf;
    if (!page) return;
    if (error.code == NeoTexturePackErrorConflict) {
      [page confirm:[page t:@"confirmReplaceTitle"]
            message:[page t:@"confirmReplaceMessage" with:@{@"folder": NeoTexString(error.userInfo[@"folder"]),
                                                             @"title": [error.userInfo[@"manual"] boolValue] ? [page t:@"installedManual"] : NeoTexString(error.userInfo[@"title"])}]
             action:[page t:@"actionReplace"] destructive:NO then:^{ [page install:YES confirmed:confirmed]; }];
      return;
    }
    [page finishInstall:result error:error replace:replace confirmed:confirmed];
  }];
}

// After an install, a download or an imported verified file: confirmations, errors, result.
- (void)finishInstall:(NSDictionary *)result error:(NSError *)error replace:(BOOL)replace confirmed:(BOOL)confirmed {
  NeoTexturePackPage *page = self;
  {
    if (error.code == NeoTexturePackErrorRegion) {
      // The engine's own installer doubts the pack: its reasons, then the user's choice
      // (the verified download or imported file is kept for it).
      NSDictionary *verdict = error.userInfo[@"engine"];
      [page confirm:[page t:@"confirmEngineTitle"]
            message:[page t:@"confirmEngineMessage" with:@{@"reasons": EngineReasons(verdict, page.locale),
                                                            @"source": [error.userInfo[@"sourceIDs"] componentsJoinedByString:@", "] ?: @"—",
                                                            @"game": GameIDs(page.identity)}]
             action:[page t:@"confirm"] destructive:NO then:^{ [page install:replace confirmed:YES]; }];
      [page reload];
      return;
    }
    [page reload];
    if (error) {
      if (error.code != NeoTexturePackErrorCancelled) [page alert:[page t:@"title"] message:ErrorText(error, page.locale)];
      return;
    }
    NSString *message = [result[@"live"] boolValue] && [result[@"activated"] boolValue] ? [page t:@"doneLive"]
                        : [result[@"activated"] boolValue] ? [page t:@"doneActivated"] : [page t:@"doneInstalled"];
    [page alert:[page t:@"title"] message:message];
  }
}
@end

#pragma mark - Main page

@interface NeoTextureHDPage () <UIDocumentPickerDelegate, UISearchResultsUpdating>
@property(nonatomic, strong) id<NeoTextureEngine> engine;
@property(nonatomic, copy) NSString *system, *gameTitle;
@property(nonatomic, copy) NSDictionary *identity;
@property(nonatomic, strong) NSDictionary *snapshot, *activation;
@property(nonatomic, strong) NSArray *packs, *installed;
@property(nonatomic, copy) NSString *search;
@property(nonatomic, assign) BOOL loaded, refreshing, importing, reloadQueued, pickingFolder;
// A game opened by path (library) or by what the running engine reported.
@property(nonatomic, copy) NSString *gamePath, *gameKey;
/// The libretro core the game starts with (Mesen's switch depends on it).
@property(nonatomic, copy) NSString *libretroCore;
@property(nonatomic, copy) NSDictionary *pendingIdentity;
@property(nonatomic, assign) BOOL resolving;
// Console page: the console's games in the library, identified in the background.
@property(nonatomic, copy) NSArray<NSDictionary *> *libraryGames;
@property(nonatomic, strong) NSArray<NSDictionary *> *libraryIdentities;
@property(nonatomic, strong) NSArray<NSDictionary *> *libraryPacks;  // {identity, pack}
@property(nonatomic, assign) NSUInteger scanned;
@property(nonatomic, assign) BOOL scanning;
@property(nonatomic, strong) UIViewController *engineDetails;
@end

@implementation NeoTextureHDPage

+ (NSString *)text:(NSString *)key locale:(NSString *)locale { return Text(key, locale); }

- (instancetype)initWithEngine:(id<NeoTextureEngine>)engine system:(NSString *)system identity:(NSDictionary *)identity
                     gameTitle:(NSString *)gameTitle locale:(NSString *)locale {
  if (!(self = [super initWithStyle:UITableViewStyleInsetGrouped])) return nil;
  _engine = engine;
  _system = NeoTexCanonicalSystem(system);
  _identity = [GameIDs(identity) length] ? identity : nil;
  _gameTitle = gameTitle;
  self.locale = locale ?: NSLocale.preferredLanguages.firstObject ?: @"en";
  return self;
}

static NSString *AbsolutePath(id value) {
  NSString *path = NeoTexString(value).stringByStandardizingPath;
  return [path hasPrefix:@"/"] && path.length > 1 ? path : nil;
}

+ (id<NeoTextureEngine>)engineWithOptions:(NSDictionary *)options system:(NSString *)system {
  NSString *engineID = NeoTexString(options[@"engine"]).length ? options[@"engine"] : NeoTexEngineForSystem(system);
  if ([engineID isEqualToString:@"dolphin"]) {
    NSString *user = AbsolutePath(options[@"dolphinUser"]);
    return user ? [NeoTextureEngines dolphinWithUserDirectory:user] : nil;
  }
  if ([engineID isEqualToString:@"armsx2"]) {
    NSString *data = AbsolutePath(options[@"armsx2Data"]);
    return data ? [NeoTextureEngines armsx2WithDataDirectory:data gamePath:AbsolutePath(options[@"gamePath"]) host:options[@"armsx2Host"]] : nil;
  }
  NSString *saves = AbsolutePath(options[@"libretroSaves"]), *config = AbsolutePath(options[@"libretroConfig"]);
  id<NeoTextureEngine> engine = nil;
  // Mupen64Plus-Next reads its high-resolution textures below the libretro system directory.
  if ([engineID isEqualToString:@"mupen64plus"]) {
    NSString *system = AbsolutePath(options[@"libretroSystem"]);
    if (system && config) engine = [NeoTextureEngines mupen64plusWithSystemDirectory:system configDirectory:config];
    if (engine && (options[@"sessionReader"] || options[@"sessionWriter"]))
      [NeoTextureEngines setLibretroSessionReader:options[@"sessionReader"] writer:options[@"sessionWriter"] forEngine:engine];
    return engine;
  }
  // Mesen reads its HD packs below the libretro system directory too.
  if ([engineID isEqualToString:@"mesen"]) {
    NSString *system = AbsolutePath(options[@"libretroSystem"]);
    id selector = options[@"coreSelector"];
    if (system && config) engine = [NeoTextureEngines mesenWithSystemDirectory:system configDirectory:config coreSelector:selector];
    if (engine && (options[@"sessionReader"] || options[@"sessionWriter"]))
      [NeoTextureEngines setLibretroSessionReader:options[@"sessionReader"] writer:options[@"sessionWriter"] forEngine:engine];
    return engine;
  }
  if (!saves || !config) return nil;
  // The libretro session gives each core <Saves>/<library name> as its save
  // directory: PPSSPP's memory stick, and Azahar's user folder below it.
  if ([engineID isEqualToString:@"ppsspp"]) engine = [NeoTextureEngines ppssppWithSaveDirectory:[saves stringByAppendingPathComponent:@"PPSSPP"] configDirectory:config];
  else if ([engineID isEqualToString:@"azahar"]) engine = [NeoTextureEngines azaharWithUserDirectory:[saves stringByAppendingPathComponent:@"Azahar/Azahar"] configDirectory:config];
  // Beetle reads its packs from its own save directory (HD Texture Folder "save").
  else if ([engineID isEqualToString:@"beetle"]) engine = [NeoTextureEngines beetleWithSaveDirectory:[saves stringByAppendingPathComponent:@"Beetle PSX HW"] configDirectory:config];
  if (engine && (options[@"sessionReader"] || options[@"sessionWriter"]))
    [NeoTextureEngines setLibretroSessionReader:options[@"sessionReader"] writer:options[@"sessionWriter"] forEngine:engine];
  return engine;
}

+ (UIViewController *)textureViewControllerWithOptions:(NSDictionary *)options {
  if (![options isKindOfClass:NSDictionary.class]) return nil;
  NSString *system = NeoTexCanonicalSystem(options[@"system"]);
  id<NeoTextureEngine> engine = [self engineWithOptions:options system:system];
  if (!engine || ![engine supportsSystem:system]) return nil;
  NSString *title = NeoTexString(options[@"title"]);
  NeoTextureHDPage *page = [[NeoTextureHDPage alloc] initWithEngine:engine system:system identity:nil gameTitle:title.length ? title : nil
                                                             locale:NeoTexString(options[@"locale"]).length ? options[@"locale"] : nil];
  page.inGame = [options[@"inGame"] boolValue];
  if (options[@"engineStatus"]) page.engineStatus = options[@"engineStatus"];
  page.gamePath = AbsolutePath(options[@"gamePath"]);
  page.gameKey = NeoTexString(options[@"gameKey"]).length ? options[@"gameKey"] : nil;
  page.libretroCore = NeoTexString(options[@"libretroCore"]).length ? options[@"libretroCore"] : nil;
  page.pendingIdentity = [options[@"identity"] isKindOfClass:NSDictionary.class] ? options[@"identity"] : nil;
  // What a running engine reports, in its own terms: game ID (or serial, disc
  // ID, program ID), revision and executable CRC.
  if (!page.pendingIdentity && NeoTexString(options[@"gameID"]).length)
    page.pendingIdentity = [NeoTextureIdentityReader identityWithSystem:system value:options[@"gameID"]
                                                               revision:NeoTexString(options[@"revision"]).length ? options[@"revision"] : nil
                                                                    crc:NeoTexString(options[@"crc"]).length ? options[@"crc"] : nil
                                                                  title:title.length ? title : nil];
  page.resolving = page.gamePath || page.pendingIdentity;
  if ([options[@"games"] isKindOfClass:NSArray.class] && !page.resolving) page.libraryGames = options[@"games"];
  if ([options[@"presentation"] isEqual:@"modal"]) return [page navigationControllerForPresentation];
  return page;
}

- (UINavigationController *)navigationControllerForPresentation {
  UINavigationController *navigation = [[UINavigationController alloc] initWithRootViewController:self];
  self.navigationItem.leftBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:[self t:@"close"] style:UIBarButtonItemStyleDone
                                                                          target:self action:@selector(close)];
  self.navigationItem.leftBarButtonItem.accessibilityIdentifier = @"neoTextureClose";
  navigation.modalPresentationStyle = UIModalPresentationFormSheet;
  return navigation;
}

- (void)close { [self.navigationController dismissViewControllerAnimated:YES completion:nil]; }

- (BOOL)gameMode { return self.identity || self.resolving || self.identityProblem; }

- (void)viewDidLoad {
  [super viewDidLoad];
  self.title = [self t:@"title"];
  self.tableView.accessibilityIdentifier = @"neoTextureHD";
  if (![self gameMode]) {
    UISearchController *search = [[UISearchController alloc] initWithSearchResultsController:nil];
    search.searchResultsUpdater = self;
    search.obscuresBackgroundDuringPresentation = NO;
    search.searchBar.placeholder = [self t:@"searchPlaceholder"];
    self.navigationItem.searchController = search;
    self.navigationItem.hidesSearchBarWhenScrolling = NO;
  }
  [[NSNotificationCenter defaultCenter] addObserver:self selector:@selector(changed:) name:NeoTextureCatalogDidChangeNotification object:nil];
  [self rebuild];
  [NeoTextureCatalog.sharedCatalog loadWithCompletion:^(NSDictionary *snapshot, NSError *error) {
    self.loaded = YES;
    if (self.resolving) [self resolveGame];
    else [self reload];
    if (self.libraryGames.count) [self scanLibrary];
  }];
}

- (void)dealloc { [[NSNotificationCenter defaultCenter] removeObserver:self]; }

- (void)changed:(NSNotification *)notification {
  if (self.reloadQueued) return;
  self.reloadQueued = YES;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(0.3 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    self.reloadQueued = NO;
    [self reload];
  });
}

- (void)updateSearchResultsForSearchController:(UISearchController *)controller {
  self.search = controller.searchBar.text;
  [self rebuild];
}

// The game's identifiers: what the running engine reported, else what the
// engine recorded at an earlier boot, else the file itself.
- (void)resolveGame {
  NSDictionary *pending = self.pendingIdentity;
  NSString *path = self.gamePath, *system = self.system, *title = self.gameTitle, *gameKey = self.gameKey, *core = self.libretroCore;
  id<NeoTextureEngine> engine = self.engine;
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NSString *problem = nil;
    NSMutableDictionary *identity = nil;
    if ([GameIDs(pending) length]) identity = [pending mutableCopy];
    if (!identity && path && [engine respondsToSelector:@selector(recordedIdentityForGamePath:)]) {
      NSDictionary *recorded = [engine recordedIdentityForGamePath:path];
      if ([recorded[@"identity_source"] isEqual:@"session"]) identity = [recorded mutableCopy];
    }
    if (!identity && path) identity = [[NeoTextureIdentityReader identityForPath:path system:system title:title problem:&problem] mutableCopy];
    if (!identity && path && [engine respondsToSelector:@selector(recordedIdentityForGamePath:)]) {
      // A serial read from the file name: usable, to be confirmed for any pack.
      NSDictionary *recorded = [engine recordedIdentityForGamePath:path];
      if (recorded) { identity = [recorded mutableCopy]; identity[@"uncertain"] = @([recorded[@"identity_source"] isEqual:@"name"]); problem = nil; }
    }
    if (identity) {
      if (path) identity[@"path"] = path;
      if (gameKey) identity[@"gameKey"] = gameKey;
      if (core) identity[@"libretroCore"] = core;
      if (title.length && !NeoTexString(identity[@"title"]).length) identity[@"title"] = title;
      if (!identity[@"system"]) identity[@"system"] = system;
    }
    dispatch_async(dispatch_get_main_queue(), ^{
      self.resolving = NO;
      self.identity = [GameIDs(identity) length] ? identity : nil;
      if (!self.identity) self.identityProblem = problem ?: @"unknown";
      [self reload];
    });
  });
}

// The console's games, one identity read each (cached), a batch at a time.
- (void)scanLibrary {
  if (self.scanning) return;
  self.scanning = YES;
  NSArray *games = self.libraryGames.count > 3000 ? [self.libraryGames subarrayWithRange:NSMakeRange(0, 3000)] : self.libraryGames;
  NSString *system = self.system;
  id<NeoTextureEngine> engine = self.engine;
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_UTILITY, 0), ^{
    NSMutableArray *found = [NSMutableArray array];
    NSUInteger done = 0;
    for (NSDictionary *game in games) {
      @autoreleasepool {
        NSString *path = AbsolutePath(game[@"path"]);
        NSString *title = NeoTexString(game[@"title"]);
        NSMutableDictionary *identity = nil;
        if (path && [engine respondsToSelector:@selector(recordedIdentityForGamePath:)]) {
          NSDictionary *recorded = [engine recordedIdentityForGamePath:path];
          if ([recorded[@"identity_source"] isEqual:@"session"]) identity = [recorded mutableCopy];
        }
        if (!identity && path) identity = [[NeoTextureIdentityReader quickIdentityForPath:path system:system title:title problem:nil] mutableCopy];
        if (identity) {
          identity[@"path"] = path;
          identity[@"title"] = title.length ? title : NeoTexString(identity[@"title"]);
          if (NeoTexString(game[@"gameKey"]).length) identity[@"gameKey"] = game[@"gameKey"];
          if (NeoTexString(game[@"libretroCore"]).length) identity[@"libretroCore"] = game[@"libretroCore"];
          [found addObject:identity];
        }
      }
      if (++done % 25 == 0 || done == games.count) {
        NSArray *snapshot = [found copy];
        const NSUInteger count = done;
        dispatch_async(dispatch_get_main_queue(), ^{
          self.libraryIdentities = snapshot;
          self.scanned = count;
          if (count == games.count) self.scanning = NO;
          [self reload];
        });
      }
    }
    if (!games.count) dispatch_async(dispatch_get_main_queue(), ^{ self.scanning = NO; [self rebuild]; });
  });
}

// Disk reads (catalogue, installed folders, engine settings) stay off main.
- (void)reload {
  if (self.resolving) { [self rebuild]; return; }
  id<NeoTextureEngine> engine = self.engine;
  NSDictionary *identity = self.identity;
  NSString *system = self.system;
  NSArray *library = self.libraryIdentities;
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NeoTextureCatalog *catalog = NeoTextureCatalog.sharedCatalog;
    NSDictionary *snapshot = [catalog snapshot];
    // Rows of a game carry their match ("uncertain" identities only candidates).
    NSArray *packs = identity ? [catalog packsForIdentity:identity engine:engine.engineID]
                              : [catalog packsForSystem:system engine:engine.engineID];
    NSMutableArray *libraryPacks = [NSMutableArray array];
    for (NSDictionary *game in identity ? @[] : library)
      for (NSDictionary *pack in [catalog packsForIdentity:game engine:engine.engineID]) [libraryPacks addObject:@{@"identity": game, @"pack": pack}];
    NSArray *installed = identity ? [NeoTexturePackStore.sharedStore installedForIdentity:identity engine:engine]
                                  : [NeoTexturePackStore.sharedStore installedForEngine:engine];
    NSDictionary *activation = identity ? [engine activationForIdentity:identity] : nil;
    dispatch_async(dispatch_get_main_queue(), ^{
      self.snapshot = snapshot;
      self.packs = packs;
      self.libraryPacks = libraryPacks;
      self.installed = installed;
      self.activation = activation;
      if (identity && !self.engineDetails && [engine respondsToSelector:@selector(detailsViewControllerWithLocale:)]) {
        id details = [engine detailsViewControllerWithLocale:self.locale];
        if ([details isKindOfClass:UIViewController.class]) self.engineDetails = details;
      }
      [self rebuild];
    });
  });
}

- (NSString *)dateText:(id)seconds {
  if (![seconds isKindOfClass:NSNumber.class]) return @"";
  NSDateFormatter *formatter = [NSDateFormatter new];
  formatter.locale = [NSLocale localeWithLocaleIdentifier:self.locale];
  formatter.dateStyle = NSDateFormatterMediumStyle;
  formatter.timeStyle = NSDateFormatterShortStyle;
  return [formatter stringFromDate:[NSDate dateWithTimeIntervalSince1970:[seconds doubleValue]]];
}

- (NTSection *)catalogueSection {
  NTSection *section = [NTSection header:[self t:@"catalogueSection"]];
  NSDictionary *snapshot = self.snapshot;
  NSString *state = snapshot[@"state"];
  NSString *count = [NSString stringWithFormat:@"%@", snapshot[@"available"][self.system] ?: @0];
  NSString *status;
  if (!self.loaded && !snapshot) status = [self t:@"catalogueLoading"];
  else if ([state isEqualToString:@"downloaded"]) status = [self t:@"catalogueDownloaded" with:@{@"count": count, @"date": [self dateText:snapshot[@"refreshed_at"]]}];
  else if ([state isEqualToString:@"bundled"]) status = [self t:@"catalogueBundled" with:@{@"count": count, @"date": NeoTexString(snapshot[@"generated_at"])}];
  else status = [self t:@"catalogueMissing"];
  NTRow *summary = [NTRow title:status detail:nil];
  summary.identifier = @"neoTextureCatalogueState";
  if (snapshot[@"refresh_error"])
    summary.detail = [self t:@"catalogueRefreshFailed" with:@{@"date": [self dateText:snapshot[@"failed_at"]]}];
  [section.rows addObject:summary];
  NTRow *refresh = [NTRow title:[self t:self.refreshing || [snapshot[@"refreshing"] boolValue] ? @"catalogueRefreshing" : @"refresh"] detail:nil];
  refresh.action = YES;
  refresh.identifier = @"neoTextureRefresh";
  refresh.disabled = self.refreshing || [snapshot[@"refreshing"] boolValue];
  __weak typeof(self) weakSelf = self;
  refresh.run = ^{ [weakSelf refreshCatalogue]; };
  [section.rows addObject:refresh];
  section.footer = [self t:@"catalogueFooter"];
  return section;
}

- (void)refreshCatalogue {
  self.refreshing = YES;
  [self rebuild];
  [NeoTextureCatalog.sharedCatalog refreshWithCompletion:^(NSDictionary *snapshot, NSError *error) {
    self.refreshing = NO;
    self.snapshot = snapshot;
    [self reload];
    if (error) [self alert:[self t:@"catalogueSection"] message:[self t:@"error.catalogueUnavailable"]];
  }];
}

- (NTSection *)gameSection {
  NTSection *section = [NTSection header:self.gameTitle.length ? self.gameTitle : [self t:@"gameSection"]];
  if (self.resolving) {
    NTRow *row = [NTRow title:[self t:@"gameReading"] detail:nil];
    row.identifier = @"neoTextureGameReading";
    [section.rows addObject:row];
    return section;
  }
  if (!self.identity) {
    NTRow *row = [NTRow title:[self t:@"gameUnknown"] detail:[self t:[@"identity." stringByAppendingString:self.identityProblem ?: @"unknown"]]];
    if ([row.detail hasPrefix:@"identity."]) row.detail = [self t:@"identity.unknown"];
    row.identifier = @"neoTextureGameUnknown";
    [section.rows addObject:row];
    return section;
  }
  NSMutableArray *parts = [NSMutableArray arrayWithObject:GameIDs(self.identity)];
  NSString *region = [self.identity[@"regions"] firstObject];
  if (region.length) [parts addObject:Region(region, self.locale)];
  if (NeoTexString(self.identity[@"revision"]).length) [parts addObject:[self t:@"revision" with:@{@"revision": self.identity[@"revision"]}]];
  if (NeoTexString(self.identity[@"crc"]).length) [parts addObject:[NSString stringWithFormat:@"CRC %@", self.identity[@"crc"]]];
  NTRow *identity = [NTRow title:[parts componentsJoinedByString:@" · "] detail:[self.identity[@"uncertain"] boolValue] ? [self t:@"reason.uncertain"] : nil];
  identity.identifier = @"neoTextureGameID";
  [section.rows addObject:identity];
  NSDictionary *activation = self.activation;
  NTRow *toggle = [NTRow title:[self t:@"enableRow"] detail:nil];
  toggle.identifier = @"neoTextureEnable";
  toggle.toggle = @([activation[@"enabled"] boolValue]);
  toggle.disabled = !activation || ![activation[@"known"] boolValue] || self.importing;
  // Why the switch is unavailable, or what turning it on also does (Mesen: selects that engine).
  if (activation && (![activation[@"known"] boolValue] || NeoTexString(activation[@"reason"]).length))
    toggle.detail = [self t:[@"activation." stringByAppendingString:NeoTexString(activation[@"reason"]) ?: @""]];
  __weak typeof(self) weakSelf = self;
  toggle.switched = ^(BOOL on) { [weakSelf switchTextures:on]; };
  [section.rows addObject:toggle];
  NTRow *status = [self engineStatusRow];
  if (status) [section.rows addObject:status];
  if (self.engineDetails) {
    NTRow *details = [NTRow title:[self t:@"engineDetails"] detail:[self t:@"engineDetailsDetail"]];
    details.disclosure = YES;
    details.identifier = @"neoTextureEngineDetails";
    details.run = ^{
      NeoTextureHDPage *page = weakSelf;
      if (page.engineDetails && !page.engineDetails.parentViewController) [page.navigationController pushViewController:page.engineDetails animated:YES];
    };
    [section.rows addObject:details];
  }
  NSString *notice = [activation[@"appliesAt"] isEqual:@"live"] ? @"liveNotice" : self.inGame ? @"restartNotice" : @"nextLaunchNotice";
  section.footer = [NSString stringWithFormat:@"%@\n\n%@", [self t:notice with:@{@"setting": NeoTexString(activation[@"setting"])}], [self t:@"loadedNotice"]];
  // GLideNHQ reads a whole new pack before the game's first frame (then reuses its cache).
  if ([self.engine.engineID isEqualToString:@"mupen64plus"])
    section.footer = [NSString stringWithFormat:@"%@\n\n%@", section.footer, [self t:@"firstLaunchNotice.mupen64plus"]];
  // Mesen decodes the whole pack when the game starts; Nestopia reads none.
  if ([self.engine.engineID isEqualToString:@"mesen"])
    section.footer = [NSString stringWithFormat:@"%@\n\n%@\n\n%@", section.footer, [self t:@"firstLaunchNotice.mesen"], [self t:@"engineNotice.mesen"]];
  return section;
}

// What the running engine reports about this game (in-game only): its
// renderer and whether it replaces textures, never inferred from the pack.
- (NTRow *)engineStatusRow {
  NSDictionary *(^provider)(void) = self.engineStatus;
  NSDictionary *status = provider ? provider() : nil;
  if (![status isKindOfClass:NSDictionary.class]) return nil;
  NSString *renderer = NeoTexString(status[@"renderer"]);
  NSString *title = [renderer isEqualToString:@"vulkan"] ? [self t:@"status.vulkan"]
                    : [renderer isEqualToString:@"gles"] ? [self t:@"status.opengl"] : [self t:@"status.software"];
  NSString *folder = NeoTexString(status[@"folder"]);
  NSString *detail;
  if (![renderer isEqualToString:@"vulkan"] && ![renderer isEqualToString:@"gles"]) detail = [self t:@"status.softwareDetail"];
  else if (![status[@"replace"] boolValue]) detail = [self t:@"status.replaceOff"];
  else if (!status[@"recognized"]) detail = [self t:@"status.waiting"];
  else if ([status[@"recognized"] integerValue] <= 0) detail = [self t:@"status.noFiles" with:@{@"folder": folder}];
  else detail = [self t:@"status.active" with:@{@"count": [status[@"recognized"] description], @"folder": folder,
                                                @"applied": [status[@"applied"] ?: @0 description]}];
  NTRow *row = [NTRow title:title detail:detail];
  row.identifier = @"neoTextureEngineStatus";
  return row;
}

// The engine's own switch for this game (not the `activation` property's setter).
- (void)switchTextures:(BOOL)on {
  id<NeoTextureEngine> engine = self.engine;
  NSDictionary *identity = self.identity;
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NSError *error = nil;
    const BOOL ok = [engine setActivation:on identity:identity error:&error];
    dispatch_async(dispatch_get_main_queue(), ^{
      if (!ok) [self alert:[self t:@"title"] message:ErrorText(error, self.locale)];
      [self reload];
    });
  });
}

- (NTRow *)installedRow:(NSDictionary *)installed {
  NSString *title = [installed[@"manual"] boolValue] ? [self t:@"installedManual"]
                    : [installed[@"imported"] boolValue] ? [self t:@"installedImported"] : NeoTexString(installed[@"title"]);
  NSMutableArray *lines = [NSMutableArray array];
  if (NeoTexString(installed[@"version"]).length) [lines addObject:[self t:@"installedVersion" with:@{@"version": installed[@"version"]}]];
  [lines addObject:[self t:@"installedSummary" with:@{@"files": installed[@"files"] ?: @"?",
                                                      @"size": installed[@"bytes"] ? Bytes(installed[@"bytes"]) : @"?",
                                                      @"folder": NeoTexString(installed[@"folder"])}]];
  NTRow *row = [NTRow title:title detail:[lines componentsJoinedByString:@"\n"]];
  row.identifier = @"neoTextureInstalled";
  row.disclosure = YES;
  __weak typeof(self) weakSelf = self;
  row.run = ^{ [weakSelf openInstalled:installed]; };
  return row;
}

- (void)openInstalled:(NSDictionary *)installed {
  NSDictionary *pack = installed[@"pack_id"] ? [NeoTextureCatalog.sharedCatalog packWithID:installed[@"pack_id"]] : nil;
  if (pack) { [self openPack:pack identity:self.identity]; return; }
  __weak typeof(self) weakSelf = self;
  [self confirm:[self t:@"confirmRemoveTitle"] message:[self t:@"confirmRemoveMessage" with:@{@"folder": NeoTexString(installed[@"folder"])}]
         action:[self t:@"remove"] destructive:YES then:^{
    [NeoTexturePackStore.sharedStore removeInstalled:installed engine:weakSelf.engine completion:^(NSError *error) {
      if (error) [weakSelf alert:[weakSelf t:@"title"] message:ErrorText(error, weakSelf.locale)];
      [weakSelf reload];
    }];
  }];
}

- (void)openPack:(NSDictionary *)pack identity:(NSDictionary *)identity {
  NeoTexturePackPage *page = [[NeoTexturePackPage alloc] initWithStyle:UITableViewStyleInsetGrouped];
  // A pack reopened from its installed row has no match yet: the game's own.
  page.pack = identity ? [NeoTextureCatalog pack:pack matchedTo:identity] : pack;
  page.engine = self.engine;
  page.identity = identity ?: DeclaredIdentity(pack);
  page.locale = self.locale;
  [self.navigationController pushViewController:page animated:YES];
}

- (NTRow *)packRow:(NSDictionary *)pack identity:(NSDictionary *)identity title:(NSString *)title installedIDs:(NSDictionary *)installedVersions {
  NSDictionary *game = [pack[@"games"] firstObject];
  NSMutableArray *details = [NSMutableArray array];
  [details addObject:[NSString stringWithFormat:@"%@ · %@", [pack[@"authors"] componentsJoinedByString:@", "], NeoTexString(pack[@"version"])]];
  if (pack[@"match"]) [details addObject:[self t:[pack[@"match"] isEqual:@"exact"] ? @"matchExact" : @"matchCandidate"]];
  if (!self.identity) [details addObject:GameIDs(identity ?: game)];
  if ([pack[@"download"][@"automatable"] boolValue] && [pack[@"availability"] isEqual:@"available"]) {
    unsigned long long size = [pack[@"download"][@"size"] unsignedLongLongValue];
    if (!size) for (NSDictionary *part in pack[@"download"][@"parts"]) size += [part[@"size"] unsignedLongLongValue];
    [details addObject:Bytes(@(size))];
  } else if ([pack[@"availability"] isEqual:@"manual"] && pack[@"install"] && NeoTexVerifiedFile(pack)) {
    [details addObject:Bytes(NeoTexVerifiedFile(pack)[@"size"])];
    [details addObject:[self t:@"stateManualVerified"]];
  } else {
    [details addObject:[self t:[pack[@"availability"] isEqual:@"unavailable"] ? @"stateUnavailable" : @"stateManual"]];
  }
  NSString *installed = installedVersions[pack[@"id"]];
  if (installed) [details addObject:[self t:[installed isEqualToString:NeoTexString(pack[@"version"])] ? @"stateInstalled" : @"stateUpdate"]];
  NSString *job = JobText([NeoTexturePackStore.sharedStore jobForPack:pack[@"id"]], self.locale);
  if (job) [details addObject:job];
  NTRow *row = [NTRow title:title detail:[details componentsJoinedByString:@" · "]];
  row.identifier = [@"neoTexturePack." stringByAppendingString:pack[@"id"]];
  row.disclosure = YES;
  __weak typeof(self) weakSelf = self;
  row.run = ^{ [weakSelf openPack:pack identity:identity]; };
  return row;
}

- (BOOL)matchesSearch:(NSDictionary *)pack game:(NSDictionary *)identity {
  if (!self.search.length) return YES;
  NSDictionary *game = [pack[@"games"] firstObject];
  NSString *haystack = NeoTexFoldTitle([NSString stringWithFormat:@"%@ %@ %@ %@", game[@"title"], pack[@"title"], GameIDs(game),
                                                                   NeoTexString(identity[@"title"])]);
  return [haystack containsString:NeoTexFoldTitle(self.search)];
}

- (void)rebuild {
  NSMutableArray *sections = [NSMutableArray arrayWithObject:[self catalogueSection]];
  const BOOL game = [self gameMode];
  if (game) [sections addObject:[self gameSection]];
  NSMutableDictionary *installedVersions = [NSMutableDictionary dictionary];
  for (NSDictionary *installed in self.installed) if (installed[@"pack_id"]) installedVersions[installed[@"pack_id"]] = NeoTexString(installed[@"version"]);
  NSString *state = self.snapshot[@"state"];
  const BOOL noCatalogue = [state isEqualToString:@"missing"] || !state;

  NTSection *installed = [NTSection header:[self t:game ? @"installedSection" : @"installedConsoleSection"]];
  for (NSDictionary *row in self.installed) [installed.rows addObject:[self installedRow:row]];
  if (!installed.rows.count) [installed.rows addObject:[NTRow title:[self t:@"installedNone"] detail:nil]];

  if (!game && (self.libraryGames.count || self.libraryPacks.count)) {
    // Packs for the games this console has in the library, with each game's own identifiers.
    NTSection *owned = [NTSection header:[self t:@"libraryGamesSection"]];
    for (NSDictionary *entry in self.libraryPacks) {
      NSDictionary *identity = entry[@"identity"], *pack = entry[@"pack"];
      if (![self matchesSearch:pack game:identity]) continue;
      NSString *title = [NSString stringWithFormat:@"%@ — %@", NeoTexString(identity[@"title"]).length ? identity[@"title"] : GameIDs(identity), pack[@"title"]];
      [owned.rows addObject:[self packRow:pack identity:identity title:title installedIDs:installedVersions]];
    }
    if (!owned.rows.count) {
      NSString *key = !self.loaded || self.scanning ? @"libraryScanning" : noCatalogue ? @"availableNoCatalogue" : @"libraryNone";
      NTRow *empty = [NTRow title:[self t:key with:@{@"done": @(self.scanned), @"total": @(self.libraryGames.count)}] detail:nil];
      empty.identifier = @"neoTextureLibraryEmpty";
      [owned.rows addObject:empty];
    } else if (self.scanning) {
      owned.footer = [self t:@"libraryScanning" with:@{@"done": @(self.scanned), @"total": @(self.libraryGames.count)}];
    }
    [sections addObject:owned];
  }

  NTSection *available = [NTSection header:[self t:game ? @"availableSection" : @"availableConsoleSection"]];
  if (!self.resolving) {
    for (NSDictionary *pack in self.packs) {
      if (![self matchesSearch:pack game:nil]) continue;
      NSDictionary *first = [pack[@"games"] firstObject];
      NSString *title = game ? pack[@"title"] : [NSString stringWithFormat:@"%@ — %@", first[@"title"], pack[@"title"]];
      [available.rows addObject:[self packRow:pack identity:game ? self.identity : nil title:title installedIDs:installedVersions]];
    }
  }
  if (!available.rows.count) {
    // Never present a missing or failed catalogue as "no pack for this game".
    NSString *key = !self.loaded || self.resolving ? @"catalogueLoading" : noCatalogue ? @"availableNoCatalogue" :
        game ? (self.identity ? @"availableNone" : @"availableNoIdentity") : @"availableNoneConsole";
    NTRow *empty = [NTRow title:[self t:key] detail:nil];
    empty.identifier = @"neoTextureAvailableEmpty";
    [available.rows addObject:empty];
    if (self.snapshot[@"refresh_error"] && ([key isEqualToString:@"availableNone"] || [key isEqualToString:@"availableNoneConsole"]))
      available.footer = [self t:@"availableAfterFailure"];
  }
  [sections addObject:available];
  [sections addObject:installed];

  NTSection *import = [NTSection header:[self t:@"importSection"]];
  if (self.identity) {
    for (NSString *kind in @[@"folder", @"archive"]) {
      NTRow *row = [NTRow title:[self t:[kind isEqualToString:@"folder"] ? @"actionImportFolder" : @"actionImportArchive"] detail:nil];
      row.action = YES;
      row.disabled = self.importing || NeoTexturePackStore.sharedStore.isBusy;
      row.identifier = [@"neoTextureImport." stringByAppendingString:kind];
      __weak typeof(self) weakSelf = self;
      row.run = ^{ [weakSelf pick:[kind isEqualToString:@"folder"]]; };
      [import.rows addObject:row];
    }
    NSString *folder = [self.engine folderForIdentity:self.identity] ?: @"";
    import.footer = [self t:[@"importHelp." stringByAppendingString:self.engine.engineID] with:@{@"folder": folder, @"id": GameIDs(self.identity)}];
    if (self.importing) import.footer = [NSString stringWithFormat:@"%@\n\n%@", [self t:@"importing"], import.footer];
  } else {
    [import.rows addObject:[NTRow title:[self t:@"importFromGame"] detail:nil]];
  }
  [sections addObject:import];

  NTSection *sources = [NTSection header:[self t:@"sourcesSection"]];
  for (NSDictionary *source in self.snapshot[@"sources"]) {
    if (![source[@"systems"] isKindOfClass:NSArray.class] || [source[@"systems"] containsObject:self.system]) {
      NTRow *row = [NTRow title:NeoTexString(source[@"name"]) detail:[NSString stringWithFormat:@"%@\n%@", NeoTexString(source[@"licence"]), NeoTexString(source[@"url"])]];
      NSURL *url = [NSURL URLWithString:NeoTexString(source[@"url"])];
      if (url) {
        row.disclosure = YES;
        row.run = ^{ [UIApplication.sharedApplication openURL:url options:@{} completionHandler:nil]; };
      }
      [sources.rows addObject:row];
    }
  }
  if (sources.rows.count) [sections addObject:sources];
  self.sections = sections;
  [self.tableView reloadData];
}

#pragma mark - Import

- (void)pick:(BOOL)folder {
  NSMutableArray<UTType *> *types = [NSMutableArray arrayWithObject:folder ? UTTypeFolder : UTTypeZIP];
  if (!folder) {
    for (NSString *extension in [self.engine.engineID isEqualToString:@"armsx2"] ? @[@"tar", @"zst", @"tzst"] : @[@"7z"]) {
      UTType *type = [UTType typeWithFilenameExtension:extension];
      if (type) [types addObject:type];
    }
  }
  UIDocumentPickerViewController *picker = [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:types asCopy:NO];
  picker.delegate = self;
  picker.allowsMultipleSelection = NO;
  self.pickingFolder = folder;
  [self presentViewController:picker animated:YES completion:nil];
}

- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
  NSURL *url = urls.firstObject;
  if (!url) return;
  // Present a follow-up question only once Files has gone.
  [controller dismissViewControllerAnimated:YES completion:^{ [self import:url allowOtherRegion:NO replace:NO]; }];
}

- (void)import:(NSURL *)url allowOtherRegion:(BOOL)allowOtherRegion replace:(BOOL)replace {
  self.importing = YES;
  [self rebuild];
  __weak typeof(self) weakSelf = self;
  [NeoTexturePackStore.sharedStore importURL:url engine:self.engine identity:self.identity allowOtherRegion:allowOtherRegion replace:replace
                                  completion:^(NSDictionary *result, NSError *error) {
    NeoTextureHDPage *page = weakSelf;
    if (!page) return;
    page.importing = NO;
    [page reload];
    if (error.code == NeoTexturePackErrorRegion) {
      NSDictionary *verdict = error.userInfo[@"engine"];
      NSString *source = [error.userInfo[@"sourceIDs"] componentsJoinedByString:@", "] ?: @"";
      if (verdict)
        [page confirm:[page t:@"confirmEngineTitle"]
              message:[page t:@"confirmEngineMessage" with:@{@"reasons": EngineReasons(verdict, page.locale), @"source": source.length ? source : @"—",
                                                              @"game": GameIDs(page.identity)}]
               action:[page t:@"confirm"] destructive:NO then:^{ [page import:url allowOtherRegion:YES replace:replace]; }];
      else
        [page confirm:[page t:@"confirmCandidateTitle"]
              message:[page t:@"confirmCandidateMessage" with:@{@"source": source, @"game": GameIDs(page.identity)}]
               action:[page t:@"confirm"] destructive:NO then:^{ [page import:url allowOtherRegion:YES replace:replace]; }];
      return;
    }
    if (error.code == NeoTexturePackErrorConflict) {
      [page confirm:[page t:@"confirmReplaceTitle"]
            message:[page t:@"confirmReplaceMessage" with:@{@"folder": NeoTexString(error.userInfo[@"folder"]),
                                                             @"title": [error.userInfo[@"manual"] boolValue] ? [page t:@"installedManual"] : NeoTexString(error.userInfo[@"title"])}]
             action:[page t:@"actionReplace"] destructive:NO then:^{ [page import:url allowOtherRegion:allowOtherRegion replace:YES]; }];
      return;
    }
    if (error) { [page alert:[page t:@"title"] message:ErrorText(error, page.locale)]; return; }
    [page alert:[page t:@"title"] message:[result[@"activated"] boolValue] ? [page t:@"doneActivated"] : [page t:@"doneInstalled"]];
  }];
}

@end
