// SPDX-License-Identifier: GPL-3.0-or-later
// In-game "HD textures" page of the embedded ARMSX2 menu (Build 485).
//
// Three states are kept apart on purpose: the pack installed on disk (store),
// NeoStation's per-game switch (this game's INI, applied live by the engine) and
// what the engine reports (textures it recognized and loaded, its memory use).
// A successful import proves the files only; the engine rows are the evidence.
#import "ARMSX2TexturePage.h"
#import "ARMSX2TextureStrings.h"
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

typedef NS_ENUM(NSInteger, ARMSX2TextureSection) {
  ARMSX2TextureSectionGame,
  ARMSX2TextureSectionPack,
  ARMSX2TextureSectionSwitch,
  ARMSX2TextureSectionActions,
  ARMSX2TextureSectionCount,
};

static NSString* const kActionFolder = @"importFolder";
static NSString* const kActionArchive = @"importArchive";
static NSString* const kActionRemove = @"remove";
static NSString* const kActionHelp = @"help";

static NSInteger Int(id value, NSInteger fallback) {
  return [value isKindOfClass:NSNumber.class] ? [value integerValue] : fallback;
}
static NSString* Text(id value) { return [value isKindOfClass:NSString.class] ? value : @""; }
static NSString* Bytes(id value) {
  return [NSByteCountFormatter stringFromByteCount:(long long)[value unsignedLongLongValue]
                                         countStyle:NSByteCountFormatterCountStyleFile];
}

NSString* ARMSX2TextureErrorText(NSDictionary<NSString*, id>* result, NSString* locale) {
  static NSDictionary<NSString*, NSString*>* keys = @{
    @"format": @"errFormat", @"zstdNeedsGame": @"errZstdNeedsGame", @"unsafe": @"errUnsafe",
    @"entries": @"errEntries", @"multipleSerials": @"errMultipleSerials", @"fileTooLarge": @"errFileTooLarge",
    @"duplicate": @"errDuplicate", @"noTextures": @"errNoTextures", @"noNamedTextures": @"errNoNamedTextures",
    @"space": @"errSpace", @"encrypted": @"errEncrypted", @"split": @"errSplit", @"method": @"errMethod",
    @"invalid": @"errInvalid", @"unreadable": @"errUnreadable", @"write": @"errWrite", @"cancelled": @"errCancelled",
    @"gameUnknown": @"errGameUnknown", @"sessionActive": @"errSessionActive", @"changed": @"errChanged",
    @"missing": @"errMissing",
  };
  NSString* key = keys[Text(result[@"error"])] ?: @"errFailed";
  return ARMSX2TextureFormat(key, locale, @{
    @"detail": Text(result[@"detail"]), @"serial": Text(result[@"gameSerial"]).length ? result[@"gameSerial"] : Text(result[@"serial"]),
    @"needed": Bytes(result[@"needed"]), @"available": Bytes(result[@"available"]),
  });
}

static NSString* FormatList(NSDictionary* formats) {
  if (![formats isKindOfClass:NSDictionary.class] || !formats.count) return @"";
  NSDictionary* names = @{@"png": @"PNG", @"ddsRgba": @"DDS RGBA", @"ddsBc1": @"DDS BC1", @"ddsBc2": @"DDS BC2",
                          @"ddsBc3": @"DDS BC3", @"ddsBc7": @"DDS BC7", @"astc": @"ASTC", @"ktx": @"KTX"};
  NSMutableArray* parts = [NSMutableArray array];
  for (NSString* key in @[@"png", @"ddsRgba", @"ddsBc1", @"ddsBc2", @"ddsBc3", @"ddsBc7", @"astc", @"ktx"])
    if (Int(formats[key], 0) > 0) [parts addObject:[NSString stringWithFormat:@"%@ %ld", names[key], (long)Int(formats[key], 0)]];
  return [parts componentsJoinedByString:@" · "];
}

@interface ARMSX2TexturePage () <UIDocumentPickerDelegate>
@property(nonatomic, copy) NSDictionary* state;
@property(nonatomic, copy) NSString* message;
@property(nonatomic, assign) BOOL working;
@property(nonatomic, copy) NSString* activeToken;
@property(nonatomic, assign) BOOL pickingFolder;
@end

@implementation ARMSX2TexturePage

- (instancetype)init { return [super initWithStyle:UITableViewStyleInsetGrouped]; }

- (NSString*)t:(NSString*)key { return ARMSX2TextureText(key, self.localeIdentifier); }
- (NSString*)t:(NSString*)key with:(NSDictionary*)values { return ARMSX2TextureFormat(key, self.localeIdentifier, values); }

- (void)viewDidLoad {
  [super viewDidLoad];
  self.title = [self t:@"title"];
  self.overrideUserInterfaceStyle = UIUserInterfaceStyleDark;
  self.view.backgroundColor = UIColor.systemGroupedBackgroundColor;
  self.tableView.backgroundColor = UIColor.systemGroupedBackgroundColor;
  self.tableView.separatorColor = [UIColor.separatorColor colorWithAlphaComponent:0.35];
  self.tableView.accessibilityIdentifier = @"armsx2HDTextures";
  [self reload];
}

- (void)reload {
  __weak ARMSX2TexturePage* weakSelf = self;
  [self.host textureReadState:^(NSDictionary* state) {
    ARMSX2TexturePage* page = weakSelf;
    if (!page) return;
    page.state = state ?: @{};
    [page.tableView reloadData];
  }];
}

- (NSDictionary*)game { NSDictionary* v = self.state[@"game"]; return [v isKindOfClass:NSDictionary.class] ? v : @{}; }
- (NSDictionary*)pack { NSDictionary* v = self.state[@"pack"]; return [v isKindOfClass:NSDictionary.class] ? v : @{}; }
- (NSDictionary*)engine { NSDictionary* v = self.state[@"engine"]; return [v isKindOfClass:NSDictionary.class] ? v : nil; }
- (NSString*)serial { return Text(self.game[@"serial"]); }
- (BOOL)installed { return [self.pack[@"installed"] boolValue]; }

// NeoStation's choice, else the engine's (in a game) or the game's INI, else off.
- (BOOL)switchOn {
  NSDictionary* engine = self.engine;
  if (engine && [engine[@"available"] boolValue]) return [engine[@"effective"] boolValue];
  id choice = self.pack[@"enabled"];
  if ([choice isKindOfClass:NSNumber.class]) return [choice boolValue];
  id ini = self.pack[@"iniEnabled"];
  if ([ini isKindOfClass:NSNumber.class]) return [ini boolValue];
  return [self.pack[@"globalEnabled"] boolValue];
}

- (NSArray<NSString*>*)actions {
  NSMutableArray* actions = [@[kActionFolder, kActionArchive] mutableCopy];
  if (self.installed) [actions addObject:kActionRemove];
  [actions addObject:kActionHelp];
  return actions;
}

- (NSInteger)numberOfSectionsInTableView:(UITableView*)tableView {
  return self.state ? ARMSX2TextureSectionCount : 0;
}

- (NSInteger)tableView:(UITableView*)tableView numberOfRowsInSection:(NSInteger)section {
  switch (section) {
    case ARMSX2TextureSectionGame: return 1;
    case ARMSX2TextureSectionPack: return self.engine ? 2 : 1;
    case ARMSX2TextureSectionSwitch: return 1;
    case ARMSX2TextureSectionActions: return (NSInteger)self.actions.count;
  }
  return 0;
}

- (NSString*)tableView:(UITableView*)tableView titleForFooterInSection:(NSInteger)section {
  if (section == ARMSX2TextureSectionPack) {
    NSDictionary* formats = self.state[@"formats"];
    if (![formats isKindOfClass:NSDictionary.class]) return nil;
    NSDictionary* engine = self.engine;
    // In a game the engine's own device answers; otherwise the same Metal queries.
    const BOOL bc = engine[@"bcTextures"] ? [engine[@"bcTextures"] boolValue] : [formats[@"bcTextures"] boolValue];
    const BOOL astc = engine[@"astcTextures"] ? [engine[@"astcTextures"] boolValue] : [formats[@"astcTextures"] boolValue];
    return [self t:@"formatsDevice" with:@{@"bc": [self t:bc ? @"bcNative" : @"bcCpu"],
                                            @"astc": [self t:astc ? @"astcYes" : @"astcNo"]}];
  }
  if (section == ARMSX2TextureSectionActions) {
    NSString* hint = [self t:@"engineInGame"];
    return self.message.length ? [NSString stringWithFormat:@"%@\n\n%@", self.message, hint] : hint;
  }
  return nil;
}

- (UITableViewCell*)tableView:(UITableView*)tableView cellForRowAtIndexPath:(NSIndexPath*)indexPath {
  UITableViewCell* cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
  cell.backgroundColor = UIColor.secondarySystemGroupedBackgroundColor;
  cell.tintColor = UIColor.systemIndigoColor;
  cell.textLabel.font = [UIFont systemFontOfSize:16 weight:UIFontWeightSemibold];
  cell.textLabel.numberOfLines = 0;
  cell.detailTextLabel.numberOfLines = 0;
  cell.detailTextLabel.textColor = UIColor.secondaryLabelColor;
  cell.selectionStyle = UITableViewCellSelectionStyleNone;
  switch (indexPath.section) {
    case ARMSX2TextureSectionGame: [self fillGame:cell]; break;
    case ARMSX2TextureSectionPack:
      if (indexPath.row == 0) [self fillPack:cell];
      else [self fillEngine:cell];
      break;
    case ARMSX2TextureSectionSwitch: [self fillSwitch:cell]; break;
    case ARMSX2TextureSectionActions: [self fillAction:self.actions[indexPath.row] cell:cell]; break;
  }
  return cell;
}

- (void)fillGame:(UITableViewCell*)cell {
  NSDictionary* game = self.game;
  cell.textLabel.text = self.serial.length ? self.serial : [self t:@"unknownSerial"];
  NSMutableArray* lines = [NSMutableArray array];
  NSMutableArray* first = [NSMutableArray array];
  if (Text(game[@"title"]).length) [first addObject:game[@"title"]];
  if (Text(game[@"region"]).length) [first addObject:game[@"region"]];
  if (Text(game[@"version"]).length) [first addObject:[self t:@"gameVersion" with:@{@"version": game[@"version"]}]];
  if (first.count) [lines addObject:[first componentsJoinedByString:@" · "]];
  NSString* source = Text(game[@"source"]);
  NSString* sourceKey = [source isEqual:@"session"] ? @"serialSession" : [source isEqual:@"disc"] ? @"serialDisc" :
      [source isEqual:@"name"] ? @"serialName" : @"serialNone";
  [lines addObject:[self t:sourceKey]];
  cell.detailTextLabel.text = [lines componentsJoinedByString:@"\n"];
  cell.imageView.image = [UIImage systemImageNamed:@"opticaldisc"];
  cell.imageView.tintColor = UIColor.systemIndigoColor;
}

- (void)fillPack:(UITableViewCell*)cell {
  NSDictionary* pack = self.pack;
  cell.imageView.image = [UIImage systemImageNamed:self.installed ? @"photo.stack.fill" : @"photo.stack"];
  cell.imageView.tintColor = UIColor.systemIndigoColor;
  if (!self.installed) { cell.textLabel.text = [self t:@"packNone"]; return; }
  cell.textLabel.text = [self t:@"packInstalled"];
  NSMutableArray* lines = [NSMutableArray array];
  [lines addObject:[self t:@"packCounts" with:@{@"named": @(Int(pack[@"named"], 0)), @"size": Bytes(pack[@"bytes"])}]];
  if (Int(pack[@"mips"], 0) > 0) [lines addObject:[self t:@"packMips" with:@{@"mips": pack[@"mips"]}]];
  NSString* formats = FormatList(pack[@"formats"]);
  if (formats.length) [lines addObject:[self t:@"packFormats" with:@{@"formats": formats}]];
  if (Int(pack[@"unsupported"], 0) > 0) [lines addObject:[self t:@"packUnsupported" with:@{@"count": pack[@"unsupported"]}]];
  NSString* packSerial = Text(pack[@"packSerial"]);
  if (packSerial.length && ![packSerial isEqual:self.serial]) [lines addObject:[self t:@"packFor" with:@{@"serial": packSerial}]];
  if ([pack[@"external"] boolValue]) [lines addObject:[self t:@"packExternal"]];
  else if (Text(pack[@"source"]).length) [lines addObject:[self t:@"packSource" with:@{@"source": pack[@"source"]}]];
  if (Text(pack[@"folder"]).length) [lines addObject:[self t:@"packFolder" with:@{@"folder": pack[@"folder"]}]];
  cell.detailTextLabel.text = [lines componentsJoinedByString:@"\n"];
}

- (void)fillEngine:(UITableViewCell*)cell {
  NSDictionary* engine = self.engine;
  cell.textLabel.text = [self t:@"engineTitle"];
  cell.imageView.image = [UIImage systemImageNamed:@"cpu"];
  cell.imageView.tintColor = UIColor.systemIndigoColor;
  NSMutableArray* lines = [NSMutableArray array];
  if (![engine[@"effective"] boolValue]) [lines addObject:[self t:@"engineOff"]];
  else if (engine[@"hardware"] && ![engine[@"hardware"] boolValue]) [lines addObject:[self t:@"engineSoftware"]];
  else {
    [lines addObject:[self t:@"engineCounts" with:@{@"indexed": @(Int(engine[@"indexed"], 0)), @"loaded": @(Int(engine[@"loaded"], 0))}]];
    if (Int(engine[@"indexed"], 0) == 0 && self.installed) [lines addObject:[self t:@"engineNone"]];
    const unsigned long long budget = [engine[@"budgetBytes"] unsignedLongLongValue];
    [lines addObject:budget ? [self t:@"engineCache" with:@{@"used": Bytes(engine[@"cacheBytes"]), @"budget": Bytes(engine[@"budgetBytes"])}]
                            : [self t:@"engineCacheOpen" with:@{@"used": Bytes(engine[@"cacheBytes"])}]];
    if ([engine[@"budgetReached"] boolValue]) [lines addObject:[self t:@"engineBudget"]];
    if ([engine[@"async"] boolValue] && ![engine[@"precache"] boolValue]) [lines addObject:[self t:@"engineAsync"]];
  }
  cell.detailTextLabel.text = [lines componentsJoinedByString:@"\n"];
}

- (void)fillSwitch:(UITableViewCell*)cell {
  cell.textLabel.text = [self t:@"enable"];
  UISwitch* toggle = [UISwitch new];
  toggle.on = self.switchOn;
  toggle.onTintColor = UIColor.systemIndigoColor;
  toggle.enabled = self.serial.length > 0 && !self.working;
  toggle.accessibilityIdentifier = @"armsx2HDTexturesSwitch";
  [toggle addTarget:self action:@selector(switchChanged:) forControlEvents:UIControlEventValueChanged];
  cell.accessoryView = toggle;
  NSMutableArray* lines = [NSMutableArray arrayWithObject:[self t:self.host.textureLive ? @"enableLive" : @"enableNext"]];
  if (!self.installed) [lines addObject:[self t:@"enableNoPack"]];
  cell.detailTextLabel.text = [lines componentsJoinedByString:@"\n"];
}

- (void)fillAction:(NSString*)action cell:(UITableViewCell*)cell {
  cell.selectionStyle = UITableViewCellSelectionStyleDefault;
  cell.accessoryType = [action isEqual:kActionHelp] ? UITableViewCellAccessoryDisclosureIndicator : UITableViewCellAccessoryNone;
  NSDictionary* symbols = @{kActionFolder: @"folder", kActionArchive: @"archivebox", kActionRemove: @"trash", kActionHelp: @"questionmark.circle"};
  cell.imageView.image = [UIImage systemImageNamed:symbols[action]];
  cell.imageView.tintColor = [action isEqual:kActionRemove] ? UIColor.systemRedColor : UIColor.systemIndigoColor;
  if ([action isEqual:kActionArchive]) cell.textLabel.text = [self t:self.host.textureLive ? @"importArchiveGame" : @"importArchive"];
  else cell.textLabel.text = [self t:action];
  if ([action isEqual:kActionRemove]) cell.textLabel.textColor = UIColor.systemRedColor;
  if (([action isEqual:kActionFolder] || [action isEqual:kActionArchive]) && self.installed)
    cell.detailTextLabel.text = [self t:@"importReplaces"];
  const BOOL needsSerial = ![action isEqual:kActionHelp];
  if (self.working || (needsSerial && !self.serial.length)) {
    cell.userInteractionEnabled = NO;
    cell.textLabel.textColor = UIColor.tertiaryLabelColor;
  }
}

- (void)setWorking:(BOOL)working {
  _working = working;
  self.navigationItem.hidesBackButton = working;
  self.navigationController.interactivePopGestureRecognizer.enabled = !working;
  if (!working) {
    self.navigationItem.prompt = nil;
    self.navigationItem.rightBarButtonItem = nil;
  }
  [self.tableView reloadData];
}

- (void)showProgress:(double)fraction phase:(NSString*)phase {
  NSString* text;
  if ([phase isEqual:@"expanding"]) text = fraction < 0 ? [self t:@"expandingUnknown"] :
      [self t:@"expanding" with:@{@"percent": @((NSInteger)llround(fraction * 100))}];
  else if ([phase isEqual:@"installing"]) text = [self t:@"installing" with:@{@"percent": @((NSInteger)llround(fraction * 100))}];
  else text = [self t:@"checking"];
  self.navigationItem.prompt = text;
}

- (void)tableView:(UITableView*)tableView didSelectRowAtIndexPath:(NSIndexPath*)indexPath {
  [tableView deselectRowAtIndexPath:indexPath animated:YES];
  if (self.working || indexPath.section != ARMSX2TextureSectionActions || self.presentedViewController) return;
  NSString* action = self.actions[indexPath.row];
  if ([action isEqual:kActionHelp]) { [self showHelp]; return; }
  if ([action isEqual:kActionRemove]) { [self confirmRemove]; return; }
  NSMutableArray<UTType*>* types = [NSMutableArray array];
  self.pickingFolder = [action isEqual:kActionFolder];
  if (self.pickingFolder) [types addObject:UTTypeFolder];
  else {
    [types addObjectsFromArray:@[UTTypeZIP, UTTypeArchive]];
    for (NSString* extension in @[@"tar", @"zst", @"tzst"]) {
      UTType* type = [UTType typeWithFilenameExtension:extension];
      if (type) [types addObject:type];
    }
  }
  UIDocumentPickerViewController* picker = [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:types asCopy:NO];
  picker.delegate = self;
  picker.allowsMultipleSelection = NO;
  [self presentViewController:picker animated:YES completion:nil];
}

- (void)documentPicker:(UIDocumentPickerViewController*)controller didPickDocumentsAtURLs:(NSArray<NSURL*>*)urls {
  NSURL* url = urls.firstObject;
  if (!url || self.working) return;
  self.working = YES;
  self.message = nil;
  [self showProgress:0 phase:@"checking"];
  self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:[self t:@"cancel"]
      style:UIBarButtonItemStylePlain target:self action:@selector(cancelImport)];
  // The picker dismisses itself; a question waits for that transition (presentSettled:).
  __weak ARMSX2TexturePage* weakSelf = self;
  [self.host textureInspectURL:url progress:^(double fraction, NSString* phase) {
    [weakSelf showProgress:fraction phase:phase];
  } completion:^(NSDictionary* inspection) { [weakSelf inspected:inspection]; }];
}

- (void)presentSettled:(UIViewController*)controller {
  id<UIViewControllerTransitionCoordinator> coordinator = self.transitionCoordinator;
  if (!coordinator) { [self presentViewController:controller animated:YES completion:nil]; return; }
  __weak ARMSX2TexturePage* weakSelf = self;
  [coordinator animateAlongsideTransition:nil completion:^(id<UIViewControllerTransitionCoordinatorContext> context) {
    [weakSelf presentViewController:controller animated:YES completion:nil];
  }];
}

- (void)documentPickerWasCancelled:(UIDocumentPickerViewController*)controller {}

- (NSString*)labelFor:(NSString*)serial region:(NSString*)region {
  return region.length ? [NSString stringWithFormat:@"%@ (%@)", serial, region] : serial;
}

- (void)inspected:(NSDictionary*)inspection {
  NSString* token = Text(inspection[@"token"]);
  if (![inspection[@"success"] boolValue]) {
    if (token.length) [self.host textureDiscard:token];
    self.message = ARMSX2TextureErrorText(inspection, self.localeIdentifier);
    self.working = NO;
    return;
  }
  self.activeToken = token;
  if (![inspection[@"needsConfirmation"] boolValue] && ![inspection[@"replacing"] boolValue]) {
    [self install:token allow:NO];
    return;
  }
  NSString* serial = Text(inspection[@"gameSerial"]);
  UIAlertController* alert = [UIAlertController alertControllerWithTitle:[self t:@"confirmTitle"]
      message:[self confirmationMessage:inspection] preferredStyle:UIAlertControllerStyleAlert];
  __weak ARMSX2TexturePage* weakSelf = self;
  [alert addAction:[UIAlertAction actionWithTitle:[self t:@"cancel"] style:UIAlertActionStyleCancel handler:^(UIAlertAction* a) {
    ARMSX2TexturePage* page = weakSelf;
    [page.host textureDiscard:token];
    page.activeToken = nil;
    page.working = NO;
  }]];
  const BOOL allow = [inspection[@"needsConfirmation"] boolValue];
  [alert addAction:[UIAlertAction actionWithTitle:[self t:@"confirmInstall" with:@{@"serial": serial}]
      style:UIAlertActionStyleDefault handler:^(UIAlertAction* a) { [weakSelf install:token allow:allow]; }]];
  [self presentSettled:alert];
}

// Every reason a pack may not fit this game, before anything is written.
- (NSString*)confirmationMessage:(NSDictionary*)inspection {
  NSString* serial = Text(inspection[@"gameSerial"]);
  NSMutableArray* lines = [NSMutableArray array];
  NSString* match = Text(inspection[@"match"]);
  NSString* game = [self labelFor:serial region:Text(inspection[@"gameRegion"])];
  if ([match isEqual:@"otherSerial"])
    [lines addObject:[self t:@"confirmOther" with:@{@"pack": [self labelFor:Text(inspection[@"packSerial"]) region:Text(inspection[@"packRegion"])], @"game": game}]];
  else if ([match isEqual:@"noSerial"]) [lines addObject:[self t:@"confirmNoSerial" with:@{@"game": game}]];
  if ([inspection[@"regionConflict"] boolValue])
    [lines addObject:[self t:@"confirmRegion" with:@{@"regions": [inspection[@"regions"] componentsJoinedByString:@", "] ?: @"",
                                                      @"region": Text(inspection[@"gameRegion"])}]];
  if ([inspection[@"crcConflict"] boolValue])
    [lines addObject:[self t:@"confirmCrc" with:@{@"crcs": [inspection[@"crcs"] componentsJoinedByString:@", "] ?: @"",
                                                   @"crc": Text(inspection[@"gameCrc"])}]];
  if ([inspection[@"uncertain"] boolValue]) [lines addObject:[self t:@"confirmUncertain" with:@{@"serial": serial}]];
  if ([inspection[@"needsConfirmation"] boolValue]) [lines addObject:[self t:@"confirmMatching"]];
  if ([inspection[@"replacing"] boolValue]) [lines addObject:[self t:@"confirmReplace"]];
  return [lines componentsJoinedByString:@"\n\n"];
}

- (void)install:(NSString*)token allow:(BOOL)allow {
  self.navigationItem.rightBarButtonItem = [[UIBarButtonItem alloc] initWithTitle:[self t:@"cancel"]
      style:UIBarButtonItemStylePlain target:self action:@selector(cancelImport)];
  [self showProgress:0 phase:@"installing"];
  __weak ARMSX2TexturePage* weakSelf = self;
  [self.host textureInstall:token allowMismatch:allow progress:^(double fraction, NSString* phase) {
    [weakSelf showProgress:fraction phase:phase];
  } completion:^(NSDictionary* result) {
    ARMSX2TexturePage* page = weakSelf;
    if (!page) return;
    [page.host textureDiscard:token];
    page.activeToken = nil;
    page.message = [page installMessage:result];
    page.working = NO;
    [page reload];
  }];
}

- (void)cancelImport {
  if (self.activeToken) [self.host textureCancel:self.activeToken];
  else [self.host textureCancelInspection];
}

- (NSString*)installMessage:(NSDictionary*)result {
  if (![result[@"success"] boolValue]) return ARMSX2TextureErrorText(result, self.localeIdentifier);
  NSMutableArray* lines = [NSMutableArray arrayWithObject:
      [self t:[result[@"replaced"] boolValue] ? @"replaced" : @"installed"
         with:@{@"serial": Text(result[@"serial"]), @"named": @(Int(result[@"named"], 0)), @"size": Bytes(result[@"bytes"])}]];
  if (Int(result[@"unsupported"], 0) > 0)
    [lines addObject:[self t:@"resultUnsupported" with:@{@"count": result[@"unsupported"],
        @"files": [result[@"unsupportedSamples"] componentsJoinedByString:@", "] ?: @""}]];
  if (Int(result[@"excluded"], 0) > 0) [lines addObject:[self t:@"resultExcluded" with:@{@"count": result[@"excluded"]}]];
  if ([result[@"enabled"] boolValue] && [result[@"live"] boolValue]) [lines addObject:[self t:@"resultLive"]];
  else if (![result[@"enabled"] boolValue]) [lines addObject:[self t:@"resultOff"]];
  return [lines componentsJoinedByString:@"\n"];
}

- (void)switchChanged:(UISwitch*)toggle {
  if (self.working) return;
  const BOOL enabled = toggle.on;
  self.working = YES;
  __weak ARMSX2TexturePage* weakSelf = self;
  [self.host textureSetEnabled:enabled completion:^(NSDictionary* result) {
    ARMSX2TexturePage* page = weakSelf;
    if (!page) return;
    page.message = [result[@"success"] boolValue] ? [page t:Text(result[@"message"])]
                                                  : ARMSX2TextureErrorText(result, page.localeIdentifier);
    page.working = NO;
    [page reload];
  }];
}

- (void)confirmRemove {
  NSString* serial = self.serial;
  UIAlertController* alert = [UIAlertController alertControllerWithTitle:[self t:@"removeTitle" with:@{@"serial": serial}]
      message:[self t:@"removeMessage" with:@{@"serial": serial}] preferredStyle:UIAlertControllerStyleAlert];
  [alert addAction:[UIAlertAction actionWithTitle:[self t:@"cancel"] style:UIAlertActionStyleCancel handler:nil]];
  __weak ARMSX2TexturePage* weakSelf = self;
  [alert addAction:[UIAlertAction actionWithTitle:[self t:@"removeConfirm"] style:UIAlertActionStyleDestructive
      handler:^(UIAlertAction* a) { [weakSelf performRemove]; }]];
  [self presentViewController:alert animated:YES completion:nil];
}

- (void)performRemove {
  self.working = YES;
  __weak ARMSX2TexturePage* weakSelf = self;
  [self.host textureRemove:^(NSDictionary* result) {
    ARMSX2TexturePage* page = weakSelf;
    if (!page) return;
    page.message = [result[@"success"] boolValue] ? [page t:@"removed"] : ARMSX2TextureErrorText(result, page.localeIdentifier);
    page.working = NO;
    [page reload];
  }];
}

- (void)showHelp {
  UIViewController* help = [UIViewController new];
  help.title = [self t:@"help"];
  help.overrideUserInterfaceStyle = UIUserInterfaceStyleDark;
  UITextView* text = [UITextView new];
  text.editable = NO;
  text.backgroundColor = UIColor.systemGroupedBackgroundColor;
  text.textColor = UIColor.labelColor;
  text.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
  text.textContainerInset = UIEdgeInsetsMake(16, 16, 24, 16);
  text.text = [self t:@"helpBody"];
  text.accessibilityIdentifier = @"armsx2HDTexturesHelp";
  help.view = text;
  [self.navigationController pushViewController:help animated:YES];
}

@end
