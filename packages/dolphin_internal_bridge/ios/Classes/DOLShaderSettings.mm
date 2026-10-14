// SPDX-License-Identifier: GPL-3.0-or-later
#import "DOLShaderSettings.h"

#import <CommonCrypto/CommonDigest.h>
#import <Metal/Metal.h>
#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>

#if __has_include(<neo_shader_kit/NeoDolphinShader.h>)
#import <neo_shader_kit/NeoDolphinShader.h>
#import <neo_shader_kit/NeoShaderCatalog.h>
#else
#import "NeoDolphinShader.h"
#import "NeoShaderCatalog.h"
#endif

#include "DOLShaderLabels.h"
#include "DOLShaderStore.h"

/// Files imported in one go.
static const NSUInteger DOLShaderImportLimit = 32;

static NSString* DOLShaderSHA256(NSData* data) {
  unsigned char digest[CC_SHA256_DIGEST_LENGTH];
  CC_SHA256(data.bytes, (CC_LONG)data.length, digest);
  NSMutableString* hex = [NSMutableString stringWithCapacity:64];
  for (int index = 0; index < CC_SHA256_DIGEST_LENGTH; index++) [hex appendFormat:@"%02x", digest[index]];
  return hex;
}

static NSString* DOLShaderTypeName(NeoDolphinOptionType type) {
  switch (type) {
    case NeoDolphinOptionTypeBool: return @"bool";
    case NeoDolphinOptionTypeInteger: return @"integer";
    case NeoDolphinOptionTypeFloat: break;
  }
  return @"float";
}

typedef NS_ENUM(NSInteger, DOLShaderRowKind) { DOLShaderRowAction, DOLShaderRowSwitch, DOLShaderRowSlider };

@interface DOLShaderRow : NSObject
@property(nonatomic, assign) DOLShaderRowKind kind;
@property(nonatomic, copy) NSString* title;
@property(nonatomic, copy, nullable) NSString* detail;
@property(nonatomic, copy, nullable) NSString* identifier;
@property(nonatomic, assign) BOOL checked;
@property(nonatomic, assign) BOOL enabled;
@property(nonatomic, assign) BOOL disclosure;
/// An imported shader: the row can be removed.
@property(nonatomic, copy, nullable) NSString* removableName;
@property(nonatomic, copy, nullable) void (^action)(UIView* cell);
@property(nonatomic, assign) BOOL on;
@property(nonatomic, copy, nullable) void (^toggled)(BOOL on);
@property(nonatomic, assign) float value;
@property(nonatomic, assign) float minimum;
@property(nonatomic, assign) float maximum;
@property(nonatomic, assign) float step;
@property(nonatomic, assign) BOOL integer;
@property(nonatomic, copy, nullable) void (^changed)(float value, BOOL finished);
@end

@implementation DOLShaderRow
- (instancetype)init {
  if ((self = [super init])) {
    _enabled = YES;
    _title = @"";
  }
  return self;
}
@end

@interface DOLShaderSection : NSObject
@property(nonatomic, copy, nullable) NSString* title;
@property(nonatomic, copy, nullable) NSString* footer;
@property(nonatomic, copy) NSArray<DOLShaderRow*>* rows;
@end

@implementation DOLShaderSection
@end

/// A slider below its title and value, snapped to the option's step.
@interface DOLShaderSliderCell : UITableViewCell
@property(nonatomic, strong) UILabel* nameLabel;
@property(nonatomic, strong) UILabel* valueLabel;
@property(nonatomic, strong) UISlider* slider;
@property(nonatomic, strong, nullable) DOLShaderRow* row;
@end

@implementation DOLShaderSliderCell
- (instancetype)initWithStyle:(UITableViewCellStyle)style reuseIdentifier:(NSString*)identifier {
  if ((self = [super initWithStyle:style reuseIdentifier:identifier])) {
    self.selectionStyle = UITableViewCellSelectionStyleNone;
    _nameLabel = [UILabel new];
    _nameLabel.numberOfLines = 0;
    _nameLabel.font = [UIFont preferredFontForTextStyle:UIFontTextStyleBody];
    _nameLabel.adjustsFontForContentSizeCategory = YES;
    _valueLabel = [UILabel new];
    _valueLabel.font = [UIFont monospacedDigitSystemFontOfSize:[UIFont preferredFontForTextStyle:UIFontTextStyleBody].pointSize
                                                        weight:UIFontWeightRegular];
    _valueLabel.textColor = UIColor.secondaryLabelColor;
    [_valueLabel setContentHuggingPriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    [_valueLabel setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
    _slider = [UISlider new];
    [_slider addTarget:self action:@selector(moved) forControlEvents:UIControlEventValueChanged];
    [_slider addTarget:self
                action:@selector(released)
      forControlEvents:UIControlEventTouchUpInside | UIControlEventTouchUpOutside | UIControlEventTouchCancel];
    UIStackView* header = [[UIStackView alloc] initWithArrangedSubviews:@[ _nameLabel, _valueLabel ]];
    header.spacing = 8;
    UIStackView* stack = [[UIStackView alloc] initWithArrangedSubviews:@[ header, _slider ]];
    stack.axis = UILayoutConstraintAxisVertical;
    stack.spacing = 6;
    stack.translatesAutoresizingMaskIntoConstraints = NO;
    [self.contentView addSubview:stack];
    UILayoutGuide* margins = self.contentView.layoutMarginsGuide;
    [NSLayoutConstraint activateConstraints:@[
      [stack.leadingAnchor constraintEqualToAnchor:margins.leadingAnchor],
      [stack.trailingAnchor constraintEqualToAnchor:margins.trailingAnchor],
      [stack.topAnchor constraintEqualToAnchor:margins.topAnchor],
      [stack.bottomAnchor constraintEqualToAnchor:margins.bottomAnchor],
    ]];
  }
  return self;
}

- (float)snapped:(float)value {
  DOLShaderRow* row = self.row;
  if (row == nil) return value;
  float result = value;
  if (row.step > 0) result = row.minimum + roundf((value - row.minimum) / row.step) * row.step;
  if (row.integer) result = roundf(result);
  return fminf(fmaxf(result, row.minimum), row.maximum);
}

- (NSString*)format:(float)value {
  if (self.row.integer) return [NSString stringWithFormat:@"%ld", (long)lroundf(value)];
  NSNumberFormatter* formatter = [NSNumberFormatter new];
  formatter.numberStyle = NSNumberFormatterDecimalStyle;
  formatter.minimumFractionDigits = 0;
  formatter.maximumFractionDigits = 3;
  return [formatter stringFromNumber:@(value)] ?: @"";
}

- (void)configureWithRow:(DOLShaderRow*)row {
  self.row = row;
  self.nameLabel.text = row.title;
  self.slider.minimumValue = row.minimum;
  self.slider.maximumValue = row.maximum;
  self.slider.value = row.value;
  self.slider.enabled = row.enabled;
  self.valueLabel.text = [self format:row.value];
  self.accessibilityIdentifier = row.identifier;
  self.slider.accessibilityLabel = row.title;
  self.slider.accessibilityValue = self.valueLabel.text;
}

- (void)moved {
  const float value = [self snapped:self.slider.value];
  self.valueLabel.text = [self format:value];
  self.slider.accessibilityValue = self.valueLabel.text;
  if (self.row.changed) self.row.changed(value, NO);
}

- (void)released {
  const float value = [self snapped:self.slider.value];
  self.slider.value = value;
  self.row.value = value;
  if (self.row.changed) self.row.changed(value, YES);
}
@end

@interface DOLShaderSettings () <UIDocumentPickerDelegate>
@end

@implementation DOLShaderSettings {
  NSArray<DOLShaderSection*>* _sections;
  NSMutableDictionary* _selection;
  /// Every top-level shader of Sys/Shaders (an import may not take a name).
  NSArray<NSString*>* _systemNames;
  /// Official shaders offered: shipped, not hidden by an import of the
  /// same name, not left out of the catalog for a failure.
  NSArray<NSString*>* _official;
  NSArray<NSString*>* _imported;
  /// Official shaders whose shipped file is the one the catalog records as
  /// rendered by the CI.
  NSSet<NSString*>* _verified;
  /// Shader(s) being compiled; the page is read-only meanwhile.
  NSString* _checking;
  BOOL _gameScope;
}

- (NSString*)text:(NSString*)key {
  return DOLShaderText(key, self.locale.length ? self.locale : @"en");
}

- (NSString*)text:(NSString*)key values:(NSDictionary<NSString*, NSString*>*)values {
  NSString* text = [self text:key];
  for (NSString* placeholder in values) {
    text = [text stringByReplacingOccurrencesOfString:[NSString stringWithFormat:@"{%@}", placeholder]
                                           withString:values[placeholder] ?: @""];
  }
  return text;
}

- (BOOL)hasGame {
  return DOLShaderValidGame(self.gameId);
}

- (void)viewDidLoad {
  [super viewDidLoad];
  self.overrideUserInterfaceStyle = UIUserInterfaceStyleDark;
  self.view.backgroundColor = UIColor.systemGroupedBackgroundColor;
  self.title = [self text:@"title"];
  self.tableView.rowHeight = UITableViewAutomaticDimension;
  self.tableView.estimatedRowHeight = 64;
  self.navigationItem.largeTitleDisplayMode = UINavigationItemLargeTitleDisplayModeNever;
  [self.tableView registerClass:DOLShaderSliderCell.class forCellReuseIdentifier:@"slider"];
  _selection = DOLShaderReadSelection(self.userDirectory);
  _gameScope = self.hasGame && [_selection[@"games"][self.gameId] isKindOfClass:NSString.class];
  [self scanFiles];
  [self rebuild];
}

- (void)scanFiles {
  NSString* system = DOLShaderFolder(self.systemDirectory);
  _systemNames = DOLShaderNames(system);
  _imported = DOLShaderNames(DOLShaderFolder(self.userDirectory));
  NeoShaderCatalogManager* manager = NeoShaderCatalogManager.sharedManager;
  NSMutableSet<NSString*>* excluded = [NSMutableSet set];
  for (NSDictionary<NSString*, NSString*>* item in [manager diagnosticsForEngine:@"dolphin"]) {
    NSString* file = item[@"identifier"];
    if ([file.pathExtension isEqualToString:@"glsl"] && ![file containsString:@"/"]) {
      [excluded addObject:file.stringByDeletingPathExtension];
    }
  }
  NeoShaderCatalog* catalog = [manager catalogForEngine:@"dolphin"];
  NSMutableArray<NSString*>* official = [NSMutableArray array];
  NSMutableSet<NSString*>* verified = [NSMutableSet set];
  for (NSString* name in _systemNames) {
    // An imported file of that name is what Dolphin loads: listed as imported.
    if ([_imported containsObject:name] || [excluded containsObject:name]) continue;
    [official addObject:name];
    NeoShaderCatalogEntry* entry = [catalog entryWithIdentifier:[@"sys/" stringByAppendingString:name]];
    NeoShaderCatalogFile* pinned = entry.files.firstObject;
    if (![entry.validation isEqualToString:@"rendered"] || pinned == nil) continue;
    NSData* data = [NSData dataWithContentsOfFile:[system stringByAppendingPathComponent:[name stringByAppendingPathExtension:@"glsl"]]];
    if (data.length == pinned.size && [DOLShaderSHA256(data) isEqualToString:pinned.sha256]) [verified addObject:name];
  }
  _official = official;
  _verified = verified;
}

/// The file Dolphin will load for `name` compiled here or is the CI's.
- (BOOL)trusted:(NSString*)name {
  BOOL imported = NO;
  NSString* file = DOLShaderFile(self.userDirectory, self.systemDirectory, name, &imported);
  if (file == nil) return NO;
  if (!imported && [_verified containsObject:name]) return YES;
  NSData* data = [NSData dataWithContentsOfFile:file];
  NSString* checked = _selection[@"checked"][name];
  return data != nil && [checked isKindOfClass:NSString.class] && [checked isEqualToString:DOLShaderSHA256(data)];
}

- (NSString*)statusOf:(NSString*)name {
  if ([_checking isEqualToString:name]) return [self text:@"checking" values:@{@"name" : name}];
  BOOL imported = NO;
  DOLShaderFile(self.userDirectory, self.systemDirectory, name, &imported);
  if (!imported && [_verified containsObject:name]) return [self text:@"verified"];
  return [self text:[self trusted:name] ? @"deviceChecked" : @"unverified"];
}

#pragma mark Model

- (DOLShaderRow*)rowWithTitle:(NSString*)title action:(void (^)(UIView* cell))action {
  DOLShaderRow* row = [DOLShaderRow new];
  row.title = title;
  row.action = action;
  return row;
}

- (void)rebuild {
  _selection = DOLShaderReadSelection(self.userDirectory);
  __weak DOLShaderSettings* weakSelf = self;
  const BOOL idle = _checking == nil;
  NSString* global = [_selection[@"global"] isKindOfClass:NSString.class] ? _selection[@"global"] : @"";
  NSString* own = self.hasGame && [_selection[@"games"][self.gameId] isKindOfClass:NSString.class]
                      ? _selection[@"games"][self.gameId]
                      : nil;
  NSString* chosen = _gameScope ? own : global;
  NSString* shown = DOLShaderEffective(_selection, _gameScope ? self.gameId : nil);
  NSMutableArray<DOLShaderSection*>* sections = [NSMutableArray array];

  if (self.hasGame) {
    DOLShaderRow* all = [self rowWithTitle:[self text:@"scopeAll"]
                                    action:^(UIView* cell) {
                                      [weakSelf setGameScope:NO];
                                    }];
    all.checked = !_gameScope;
    all.enabled = idle;
    all.identifier = @"dolphinShaderScopeAll";
    DOLShaderRow* game = [self rowWithTitle:[self text:@"scopeGame" values:@{@"game" : self.gameId}]
                                     action:^(UIView* cell) {
                                       [weakSelf setGameScope:YES];
                                     }];
    game.checked = _gameScope;
    game.enabled = idle;
    game.identifier = @"dolphinShaderScopeGame";
    DOLShaderSection* scope = [DOLShaderSection new];
    scope.title = [self text:@"scopeSection"];
    scope.rows = @[ all, game ];
    scope.footer = [self text:@"nextLaunch"];
    [sections addObject:scope];
  }

  NSMutableArray<DOLShaderRow*>* effect = [NSMutableArray array];
  if (_gameScope) {
    NSString* followed = global.length ? global : [self text:@"off"];
    DOLShaderRow* follow = [self rowWithTitle:[self text:@"followAll" values:@{@"effect" : followed}]
                                       action:^(UIView* cell) {
                                         [weakSelf choose:nil];
                                       }];
    follow.checked = own == nil;
    follow.enabled = idle;
    follow.identifier = @"dolphinShaderFollowAll";
    [effect addObject:follow];
  }
  DOLShaderRow* off = [self rowWithTitle:[self text:@"off"]
                                  action:^(UIView* cell) {
                                    [weakSelf choose:@""];
                                  }];
  off.checked = [chosen isEqualToString:@""];
  off.enabled = idle;
  off.identifier = @"dolphinShaderOff";
  [effect addObject:off];
  DOLShaderSection* effectSection = [DOLShaderSection new];
  effectSection.rows = effect;
  effectSection.footer = self.hasGame ? nil : [self text:@"nextLaunch"];
  [sections addObject:effectSection];

  NSMutableArray<DOLShaderRow*>* official = [NSMutableArray array];
  for (NSString* name in _official) {
    DOLShaderRow* row = [self rowWithTitle:name
                                    action:^(UIView* cell) {
                                      [weakSelf choose:name];
                                    }];
    row.detail = [self statusOf:name];
    row.checked = [chosen isEqualToString:name];
    row.enabled = idle;
    row.identifier = [@"dolphinShaderOfficial." stringByAppendingString:name];
    [official addObject:row];
  }
  if (official.count > 0) {
    DOLShaderSection* section = [DOLShaderSection new];
    section.title = [self text:@"official"];
    section.rows = official;
    section.footer = [self text:@"officialFooter"];
    [sections addObject:section];
  }

  NSMutableArray<DOLShaderRow*>* imported = [NSMutableArray array];
  for (NSString* name in _imported) {
    DOLShaderRow* row = [self rowWithTitle:name
                                    action:^(UIView* cell) {
                                      [weakSelf choose:name];
                                    }];
    row.detail = [self statusOf:name];
    row.checked = [chosen isEqualToString:name];
    row.enabled = idle;
    row.removableName = name;
    row.identifier = [@"dolphinShaderImported." stringByAppendingString:name];
    [imported addObject:row];
  }
  if (imported.count == 0) {
    DOLShaderRow* none = [self rowWithTitle:[self text:@"importedNone"] action:nil];
    none.enabled = NO;
    [imported addObject:none];
  }
  DOLShaderRow* importRow = [self rowWithTitle:[self text:@"importAction"]
                                        action:^(UIView* cell) {
                                          [weakSelf pickFiles:cell];
                                        }];
  importRow.enabled = idle;
  importRow.disclosure = YES;
  importRow.identifier = @"dolphinShaderImport";
  [imported addObject:importRow];
  DOLShaderSection* importedSection = [DOLShaderSection new];
  importedSection.title = [self text:@"imported"];
  importedSection.rows = imported;
  importedSection.footer = [self text:@"importedFooter"];
  [sections addObject:importedSection];

  DOLShaderSection* options = shown.length ? [self optionsSectionOf:shown idle:idle] : nil;
  if (options != nil) [sections addObject:options];
  _sections = sections;
  [self.tableView reloadData];
}

/// Values in effect for an option: NeoStation's when of the same type and
/// size, else the shader's defaults.
- (NSArray<NSNumber*>*)valuesOf:(NeoDolphinShaderOption*)option stored:(NSDictionary*)stored {
  NSDictionary* record = stored[option.name];
  NSArray* values = record[@"values"];
  if ([record[@"type"] isEqual:DOLShaderTypeName(option.type)] && values.count == option.defaultValues.count) return values;
  return option.defaultValues;
}

- (DOLShaderSection*)optionsSectionOf:(NSString*)name idle:(BOOL)idle {
  NSString* file = DOLShaderFile(self.userDirectory, self.systemDirectory, name, NULL);
  NSDictionary* attributes = file ? [NSFileManager.defaultManager attributesOfItemAtPath:file error:nil] : nil;
  if (attributes == nil || [attributes[NSFileSize] unsignedLongLongValue] > DOLShaderMaxBytes) return nil;
  NSString* code = [NSString stringWithContentsOfFile:file encoding:NSUTF8StringEncoding error:nil];
  if (code == nil) return nil;
  NSArray<NeoDolphinShaderOption*>* options = [NeoDolphinShader optionsOfCode:code];
  NSArray<NSString*>* credits = [NeoDolphinShader creditLinesOfCode:code];
  if (options.count == 0 && credits.count == 0) return nil;
  NSDictionary* stored = _selection[@"options"][name];
  __weak DOLShaderSettings* weakSelf = self;
  NSMutableArray<DOLShaderRow*>* rows = [NSMutableArray array];
  for (NeoDolphinShaderOption* option in options) {
    NSArray<NSNumber*>* values = [self valuesOf:option stored:stored];
    NSString* label = option.guiName.length ? option.guiName : option.name;
    if (option.type == NeoDolphinOptionTypeBool) {
      DOLShaderRow* row = [self rowWithTitle:label action:nil];
      row.kind = DOLShaderRowSwitch;
      row.on = values.firstObject.boolValue;
      row.enabled = idle;
      row.identifier = [@"dolphinShaderOption." stringByAppendingString:option.name];
      row.toggled = ^(BOOL on) {
        [weakSelf storeOption:option component:0 value:on ? 1.0 : 0.0 shader:name options:options];
      };
      [rows addObject:row];
      continue;
    }
    for (NSUInteger index = 0; index < values.count; index++) {
      NSString* title = values.count > 1
                            ? [self text:@"component" values:@{@"option" : label, @"index" : [@(index + 1) stringValue]}]
                            : label;
      DOLShaderRow* row = [self rowWithTitle:title action:nil];
      row.kind = DOLShaderRowSlider;
      row.integer = option.type == NeoDolphinOptionTypeInteger;
      row.minimum = index < option.minimums.count ? option.minimums[index].floatValue : 0;
      row.maximum = index < option.maximums.count ? option.maximums[index].floatValue : 1;
      if (!(row.minimum < row.maximum)) continue;
      row.step = index < option.steps.count ? option.steps[index].floatValue : 0;
      row.value = fminf(fmaxf(values[index].floatValue, row.minimum), row.maximum);
      row.enabled = idle;
      row.identifier = [NSString stringWithFormat:@"dolphinShaderOption.%@.%lu", option.name, (unsigned long)index];
      row.changed = ^(float value, BOOL finished) {
        if (finished) [weakSelf storeOption:option component:index value:value shader:name options:options];
      };
      [rows addObject:row];
    }
  }
  if (options.count > 0) {
    DOLShaderRow* reset = [self rowWithTitle:[self text:@"resetOptions"]
                                      action:^(UIView* cell) {
                                        [weakSelf resetOptionsOf:name];
                                      }];
    reset.enabled = idle && stored.count > 0;
    reset.identifier = @"dolphinShaderResetOptions";
    [rows addObject:reset];
  }
  DOLShaderSection* section = [DOLShaderSection new];
  section.title = [self text:@"options" values:@{@"name" : name}];
  section.rows = rows;
  NSString* footer = options.count > 0 ? [self text:@"optionsFooter"] : nil;
  if (credits.count > 0) {
    // Quoted as the file gives them, untranslated.
    NSString* line = [self text:@"credits" values:@{@"credits" : [credits componentsJoinedByString:@" · "]}];
    footer = footer.length ? [NSString stringWithFormat:@"%@\n\n%@", footer, line] : line;
  }
  section.footer = footer;
  return rows.count > 0 || footer.length ? section : nil;
}

#pragma mark Actions

- (void)setGameScope:(BOOL)gameScope {
  // check: captures the destination scope before leaving the main thread.
  // Keep it fixed until that check saves or refuses its result.
  if (_checking != nil) return;
  _gameScope = gameScope && self.hasGame;
  self.navigationItem.prompt = nil;
  [self rebuild];
}

- (void)saved:(BOOL)saved {
  self.navigationItem.prompt = [self text:saved ? @"saved" : @"saveFailed"];
}

/// nil: this game follows every game's choice; "": no effect.
- (void)choose:(NSString*)name {
  if (_checking != nil) return;
  if (name.length > 0 && ![self trusted:name]) {
    [self check:name];
    return;
  }
  [self saved:DOLShaderSetChoice(self.userDirectory, _gameScope ? self.gameId : nil, name)];
  [self rebuild];
}

- (void)showMessage:(NSString*)message {
  UIAlertController* alert = [UIAlertController alertControllerWithTitle:[self text:@"title"]
                                                                 message:message
                                                          preferredStyle:UIAlertControllerStyleAlert];
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"ok"] style:UIAlertActionStyleCancel handler:nil]];
  [self presentViewController:alert animated:YES completion:nil];
}

/// Compiles the file Dolphin would load (translation as the core does, then
/// the device's Metal compiler) before saving the choice.
- (void)check:(NSString*)name {
  NSString* file = DOLShaderFile(self.userDirectory, self.systemDirectory, name, NULL);
  if (file == nil) {
    [self rebuild];
    return;
  }
  _checking = name;
  self.navigationItem.prompt = [self text:@"checking" values:@{@"name" : name}];
  [self rebuild];
  NSString* user = self.userDirectory;
  const BOOL gameScope = _gameScope;
  NSString* gameId = self.gameId;
  __weak DOLShaderSettings* weakSelf = self;
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    NSData* data = [NSData dataWithContentsOfFile:file];
    NSString* code = data.length > 0 && data.length <= DOLShaderMaxBytes
                         ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]
                         : nil;
    NSError* error = nil;
    NeoDolphinShader* shader = code != nil ? [NeoDolphinShader shaderWithCode:code error:&error] : nil;
    const BOOL compiled = shader != nil && [shader compileWithDevice:MTLCreateSystemDefaultDevice() error:&error];
    NSString* reason = compiled ? nil : (error.userInfo[NeoDolphinShaderErrorCodeKey] ?: @"DOLPHIN_NOT_TEXT");
    if (!compiled) {
      NSLog(@"[Dolphin] post-processing shader %@ refused: %@ %@", name, reason,
            error.userInfo[NSDebugDescriptionErrorKey] ?: @"");
    }
    dispatch_async(dispatch_get_main_queue(), ^{
      DOLShaderSettings* page = weakSelf;
      BOOL saved = NO;
      if (compiled) {
        saved = DOLShaderSetChecked(user, name, DOLShaderSHA256(data)) &&
                DOLShaderSetChoice(user, gameScope ? gameId : nil, name);
      }
      if (page == nil) return;
      page->_checking = nil;
      if (compiled) {
        [page saved:saved];
      } else {
        page.navigationItem.prompt = nil;
        [page showMessage:[page text:@"incompatible" values:@{@"name" : name, @"code" : reason}]];
      }
      [page rebuild];
    });
  });
}

- (void)storeOption:(NeoDolphinShaderOption*)changed
          component:(NSUInteger)component
              value:(double)value
             shader:(NSString*)name
            options:(NSArray<NeoDolphinShaderOption*>*)options {
  NSDictionary* stored = DOLShaderReadSelection(self.userDirectory)[@"options"][name];
  NSMutableDictionary* records = [NSMutableDictionary dictionary];
  for (NeoDolphinShaderOption* option in options) {
    NSMutableArray<NSNumber*>* values = [[self valuesOf:option stored:stored] mutableCopy];
    if (option == changed && component < values.count) values[component] = @(value);
    records[option.name] = @{@"type" : DOLShaderTypeName(option.type), @"values" : values};
  }
  [self saved:DOLShaderSetOptionValues(self.userDirectory, name, records)];
  _selection = DOLShaderReadSelection(self.userDirectory);
  // The reset row follows; sliders keep their touch (no reload needed for them).
  dispatch_async(dispatch_get_main_queue(), ^{
    [self rebuild];
  });
}

- (void)resetOptionsOf:(NSString*)name {
  [self saved:DOLShaderSetOptionValues(self.userDirectory, name, nil)];
  [self rebuild];
}

- (void)pickFiles:(UIView*)cell {
  if (_checking != nil || self.presentedViewController != nil) return;
  NSMutableArray<UTType*>* types = [NSMutableArray array];
  UTType* glsl = [UTType typeWithFilenameExtension:@"glsl"];
  if (glsl != nil) [types addObject:glsl];
  [types addObject:UTTypePlainText];
  [types addObject:UTTypeSourceCode];
  UIDocumentPickerViewController* picker = [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:types
                                                                                                       asCopy:YES];
  picker.allowsMultipleSelection = YES;
  picker.delegate = self;
  [self presentViewController:picker animated:YES completion:nil];
}

- (void)documentPicker:(UIDocumentPickerViewController*)controller didPickDocumentsAtURLs:(NSArray<NSURL*>*)urls {
  NSMutableArray<NSString*>* problems = [NSMutableArray array];
  NSMutableArray<NSArray*>* candidates = [NSMutableArray array];
  for (NSURL* url in [urls subarrayWithRange:NSMakeRange(0, MIN(urls.count, DOLShaderImportLimit))]) {
    NSString* name = url.lastPathComponent.stringByDeletingPathExtension ?: @"";
    NSString* shown = name.length ? name : url.lastPathComponent;
    if (![url.pathExtension.lowercaseString isEqualToString:@"glsl"]) {
      [problems addObject:[self text:@"importFailedText" values:@{@"name" : shown}]];
      continue;
    }
    if (!DOLShaderValidName(name)) {
      [problems addObject:[self text:@"importFailedName" values:@{@"name" : shown}]];
      continue;
    }
    if ([_systemNames containsObject:name]) {
      [problems addObject:[self text:@"importFailedOfficial" values:@{@"name" : name}]];
      continue;
    }
    NSNumber* size = nil;
    [url getResourceValue:&size forKey:NSURLFileSizeKey error:nil];
    if (size.unsignedLongLongValue > DOLShaderMaxBytes) {
      [problems addObject:[self text:@"importFailedSize" values:@{@"name" : name}]];
      continue;
    }
    NSData* data = [NSData dataWithContentsOfURL:url];
    NSString* code = data.length > 0 && data.length <= DOLShaderMaxBytes
                         ? [[NSString alloc] initWithData:data encoding:NSUTF8StringEncoding]
                         : nil;
    if (code == nil) {
      [problems addObject:[self text:data.length > DOLShaderMaxBytes ? @"importFailedSize" : @"importFailedText"
                              values:@{@"name" : name}]];
      continue;
    }
    [candidates addObject:@[ name, data, code ]];
  }
  if (candidates.count == 0) {
    if (problems.count > 0) [self showMessage:[problems componentsJoinedByString:@"\n\n"]];
    return;
  }
  NSMutableArray<NSString*>* names = [NSMutableArray array];
  for (NSArray* candidate in candidates) [names addObject:candidate[0]];
  _checking = @"";
  self.navigationItem.prompt = [self text:@"checking" values:@{@"name" : [names componentsJoinedByString:@", "]}];
  [self rebuild];
  NSString* user = self.userDirectory;
  __weak DOLShaderSettings* weakSelf = self;
  dispatch_async(dispatch_get_global_queue(QOS_CLASS_USER_INITIATED, 0), ^{
    id<MTLDevice> device = MTLCreateSystemDefaultDevice();
    NSMutableArray<NSString*>* failures = [NSMutableArray array];
    NSMutableArray<NSArray*>* accepted = [NSMutableArray array];
    for (NSArray* candidate in candidates) {
      NSError* error = nil;
      NeoDolphinShader* shader = [NeoDolphinShader shaderWithCode:candidate[2] error:&error];
      if (shader != nil && [shader compileWithDevice:device error:&error]) {
        [accepted addObject:candidate];
      } else {
        NSString* code = error.userInfo[NeoDolphinShaderErrorCodeKey] ?: @"DOLPHIN_NOT_TEXT";
        NSLog(@"[Dolphin] imported shader %@ refused: %@ %@", candidate[0], code,
              error.userInfo[NSDebugDescriptionErrorKey] ?: @"");
        [failures addObject:candidate[0]];
        [failures addObject:code];
      }
    }
    dispatch_async(dispatch_get_main_queue(), ^{
      // Validated files are kept even when the page closed meanwhile.
      NSMutableArray<NSString*>* imported = [NSMutableArray array];
      NSMutableArray<NSString*>* unsaved = [NSMutableArray array];
      for (NSArray* candidate in accepted) {
        NSString* name = candidate[0];
        BOOL replaced = NO;
        if (!DOLShaderStoreImport(user, name, candidate[1], &replaced)) {
          [unsaved addObject:name];
          continue;
        }
        // A new version keeps none of the old one's settings.
        if (replaced) DOLShaderSetOptionValues(user, name, nil);
        DOLShaderSetChecked(user, name, DOLShaderSHA256(candidate[1]));
        [imported addObject:name];
      }
      DOLShaderSettings* page = weakSelf;
      if (page == nil) return;
      page->_checking = nil;
      page.navigationItem.prompt = nil;
      NSMutableArray<NSString*>* messages = [NSMutableArray array];
      if (imported.count > 0) {
        [messages addObject:[page text:@"importDone" values:@{@"names" : [imported componentsJoinedByString:@", "]}]];
      }
      for (NSString* name in unsaved) [messages addObject:[page text:@"importFailedSave" values:@{@"name" : name}]];
      for (NSUInteger index = 0; index + 1 < failures.count; index += 2) {
        [messages addObject:[page text:@"importFailedCompile" values:@{@"name" : failures[index], @"code" : failures[index + 1]}]];
      }
      [messages addObjectsFromArray:problems];
      [page scanFiles];
      [page rebuild];
      [page showMessage:[messages componentsJoinedByString:@"\n\n"]];
    });
  });
}

- (void)confirmRemoval:(NSString*)name {
  UIAlertController* alert = [UIAlertController alertControllerWithTitle:[self text:@"remove"]
                                                                 message:[self text:@"removeConfirm" values:@{@"name" : name}]
                                                          preferredStyle:UIAlertControllerStyleAlert];
  __weak DOLShaderSettings* weakSelf = self;
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"cancel"] style:UIAlertActionStyleCancel handler:nil]];
  [alert addAction:[UIAlertAction actionWithTitle:[self text:@"remove"]
                                            style:UIAlertActionStyleDestructive
                                          handler:^(UIAlertAction* action) {
                                            DOLShaderSettings* page = weakSelf;
                                            if (page == nil) return;
                                            [page saved:DOLShaderRemoveImport(page.userDirectory, name)];
                                            [page scanFiles];
                                            [page rebuild];
                                          }]];
  [self presentViewController:alert animated:YES completion:nil];
}

#pragma mark Table

- (DOLShaderRow*)rowAt:(NSIndexPath*)path {
  if (path.section >= (NSInteger)_sections.count) return nil;
  NSArray<DOLShaderRow*>* rows = _sections[path.section].rows;
  return path.row < (NSInteger)rows.count ? rows[path.row] : nil;
}

- (NSInteger)numberOfSectionsInTableView:(UITableView*)table {
  return _sections.count;
}

- (NSInteger)tableView:(UITableView*)table numberOfRowsInSection:(NSInteger)section {
  return section < (NSInteger)_sections.count ? _sections[section].rows.count : 0;
}

- (NSString*)tableView:(UITableView*)table titleForHeaderInSection:(NSInteger)section {
  return section < (NSInteger)_sections.count ? _sections[section].title : nil;
}

- (NSString*)tableView:(UITableView*)table titleForFooterInSection:(NSInteger)section {
  return section < (NSInteger)_sections.count ? _sections[section].footer : nil;
}

- (void)tableView:(UITableView*)table willDisplayFooterView:(UIView*)view forSection:(NSInteger)section {
  if ([view isKindOfClass:UITableViewHeaderFooterView.class]) {
    UITableViewHeaderFooterView* footer = (UITableViewHeaderFooterView*)view;
    footer.textLabel.textColor = UIColor.secondaryLabelColor;
    footer.textLabel.numberOfLines = 0;
  }
}

- (UITableViewCell*)tableView:(UITableView*)table cellForRowAtIndexPath:(NSIndexPath*)path {
  DOLShaderRow* row = [self rowAt:path];
  if (row.kind == DOLShaderRowSlider) {
    DOLShaderSliderCell* cell = [table dequeueReusableCellWithIdentifier:@"slider" forIndexPath:path];
    cell.backgroundColor = UIColor.secondarySystemGroupedBackgroundColor;
    [cell configureWithRow:row];
    return cell;
  }
  UITableViewCell* cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
  cell.backgroundColor = UIColor.secondarySystemGroupedBackgroundColor;
  cell.textLabel.text = row.title;
  cell.textLabel.numberOfLines = 0;
  cell.textLabel.adjustsFontForContentSizeCategory = YES;
  cell.textLabel.textColor = row.enabled ? UIColor.labelColor : UIColor.secondaryLabelColor;
  cell.detailTextLabel.text = row.detail;
  cell.detailTextLabel.numberOfLines = 0;
  cell.detailTextLabel.textColor = UIColor.secondaryLabelColor;
  cell.accessibilityIdentifier = row.identifier;
  if (row.kind == DOLShaderRowSwitch) {
    UISwitch* toggle = [UISwitch new];
    toggle.on = row.on;
    toggle.enabled = row.enabled;
    [toggle addTarget:self action:@selector(switchChanged:) forControlEvents:UIControlEventValueChanged];
    cell.accessoryView = toggle;
    cell.selectionStyle = UITableViewCellSelectionStyleNone;
    return cell;
  }
  if (row.checked) {
    cell.accessoryType = UITableViewCellAccessoryCheckmark;
    cell.accessibilityTraits |= UIAccessibilityTraitSelected;
  } else if (row.disclosure) {
    cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
  }
  if (row.action == nil || !row.enabled) cell.selectionStyle = UITableViewCellSelectionStyleNone;
  return cell;
}

- (void)switchChanged:(UISwitch*)toggle {
  CGPoint point = [toggle convertPoint:CGPointZero toView:self.tableView];
  DOLShaderRow* row = [self rowAt:[self.tableView indexPathForRowAtPoint:point]];
  if (row.toggled != nil) row.toggled(toggle.on);
}

- (void)tableView:(UITableView*)table didSelectRowAtIndexPath:(NSIndexPath*)path {
  [table deselectRowAtIndexPath:path animated:YES];
  DOLShaderRow* row = [self rowAt:path];
  if (row == nil || !row.enabled || row.action == nil || self.presentedViewController != nil) return;
  row.action([table cellForRowAtIndexPath:path]);
}

- (UISwipeActionsConfiguration*)tableView:(UITableView*)table
    trailingSwipeActionsConfigurationForRowAtIndexPath:(NSIndexPath*)path {
  DOLShaderRow* row = [self rowAt:path];
  NSString* name = row.removableName;
  if (name == nil || _checking != nil) return nil;
  __weak DOLShaderSettings* weakSelf = self;
  UIContextualAction* remove = [UIContextualAction contextualActionWithStyle:UIContextualActionStyleDestructive
                                                                       title:[self text:@"remove"]
                                                                     handler:^(UIContextualAction* action, UIView* view,
                                                                               void (^done)(BOOL)) {
                                                                       [weakSelf confirmRemoval:name];
                                                                       done(YES);
                                                                     }];
  return [UISwipeActionsConfiguration configurationWithActions:@[ remove ]];
}

@end
