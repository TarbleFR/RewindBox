// SPDX-License-Identifier: BSD-3-Clause
#import "XeniaSessionMenu.h"

#include <mach/mach.h>

NSArray<NSString*>* RBXeniaOverlayLevels(void) {
  return @[ @"off", @"simple", @"detailed" ];
}

const NSInteger RBXeniaResolutionCount = 17;

// XeniOS src/xenia/gpu/graphics_system.cc internal_display_resolution (0...16).
NSString* RBXeniaResolutionLabel(NSInteger index) {
  static NSArray<NSString*>* labels;
  static dispatch_once_t once;
  dispatch_once(&once, ^{
    labels = @[
      @"640×480", @"640×576", @"720×480", @"720×576", @"800×600", @"848×480", @"1024×768",
      @"1152×864", @"1280×720", @"1280×768", @"1280×960", @"1280×1024", @"1360×768",
      @"1440×900", @"1680×1050", @"1920×540", @"1920×1080"
    ];
  });
  return index >= 0 && index < (NSInteger)labels.count ? labels[(NSUInteger)index] : labels[8];
}

static NSString* RBXeniaText(NSDictionary<NSString*, NSString*>* texts, NSString* key, NSString* fallback) {
  id value = texts[key];
  return [value isKindOfClass:NSString.class] && [value length] ? value : fallback;
}

// ------------------------------------------------------------------ choices

@interface RBXeniaChoiceMenu : UITableViewController
@property(nonatomic, copy) NSArray<NSString*>* values;
@property(nonatomic, copy) NSArray<NSString*>* titles;
@property(nonatomic, copy) NSString* selected;
@property(nonatomic, copy, nullable) NSString* footer;
@property(nonatomic, copy) void (^chosen)(NSString* value);
@end

@implementation RBXeniaChoiceMenu

- (instancetype)init {
  return [super initWithStyle:UITableViewStyleInsetGrouped];
}

- (NSInteger)tableView:(UITableView*)tableView numberOfRowsInSection:(NSInteger)section {
  return (NSInteger)self.values.count;
}

- (UITableViewCell*)tableView:(UITableView*)tableView cellForRowAtIndexPath:(NSIndexPath*)indexPath {
  UITableViewCell* cell = [tableView dequeueReusableCellWithIdentifier:@"choice"];
  if (!cell) cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleDefault reuseIdentifier:@"choice"];
  const NSUInteger row = (NSUInteger)indexPath.row;
  cell.textLabel.text = self.titles[row];
  cell.accessoryType = [self.values[row] isEqualToString:self.selected] ? UITableViewCellAccessoryCheckmark
                                                                        : UITableViewCellAccessoryNone;
  return cell;
}

- (NSString*)tableView:(UITableView*)tableView titleForFooterInSection:(NSInteger)section {
  return self.footer;
}

- (void)tableView:(UITableView*)tableView didSelectRowAtIndexPath:(NSIndexPath*)indexPath {
  [tableView deselectRowAtIndexPath:indexPath animated:YES];
  NSString* value = self.values[(NSUInteger)indexPath.row];
  const BOOL changed = ![value isEqualToString:self.selected];
  self.selected = value;
  [tableView reloadData];
  if (changed && self.chosen) self.chosen(value);
  [self.navigationController popViewControllerAnimated:YES];
}

@end

// --------------------------------------------------------------------- menu

typedef NS_ENUM(NSInteger, RBXeniaMenuSection) {
  RBXeniaMenuSectionResume,
  RBXeniaMenuSectionDisplay,
  RBXeniaMenuSectionGame,
  RBXeniaMenuSectionSession,
  RBXeniaMenuSectionCount,
};

typedef NS_ENUM(NSInteger, RBXeniaGameRow) {
  RBXeniaGameRowAspect,
  RBXeniaGameRowResolution,
  RBXeniaGameRowLetterbox,
  RBXeniaGameRowCount,
};

@interface RBXeniaSessionMenu ()
@property(nonatomic, weak) id<RBXeniaSessionMenuHost> host;
@property(nonatomic, copy) NSDictionary<NSString*, NSString*>* texts;
@property(nonatomic, copy) NSString* locale;
@property(nonatomic, strong) NSMutableDictionary<NSString*, NSString*>* settings;
@property(nonatomic, copy) NSString* overlayLevel;
/// Set once an action closes the menu, so a swipe-dismiss does not also resume.
@property(nonatomic, assign) BOOL closing;
@end

@implementation RBXeniaSessionMenu

- (instancetype)initWithTitle:(NSString*)title
                        texts:(NSDictionary<NSString*, NSString*>*)texts
                       locale:(NSString*)locale
                     settings:(NSDictionary<NSString*, NSString*>*)settings
                 overlayLevel:(NSString*)overlayLevel
                         host:(id<RBXeniaSessionMenuHost>)host {
  if ((self = [super initWithStyle:UITableViewStyleInsetGrouped])) {
    self.title = title;
    _texts = [texts copy];
    _locale = [locale copy];
    _settings = [settings mutableCopy];
    _overlayLevel = [RBXeniaOverlayLevels() containsObject:overlayLevel] ? [overlayLevel copy] : @"off";
    _host = host;
  }
  return self;
}

- (NSString*)text:(NSString*)key fallback:(NSString*)fallback {
  return RBXeniaText(self.texts, key, fallback);
}

- (NSString*)setting:(NSString*)key fallback:(NSString*)fallback {
  NSString* value = self.settings[key];
  return value.length ? value : fallback;
}

- (NSArray<NSString*>*)overlayTitles {
  return @[ [self text:@"overlayOff" fallback:@"Off"], [self text:@"overlaySimple" fallback:@"Simple"],
            [self text:@"overlayDetailed" fallback:@"Detailed"] ];
}

- (NSArray<NSString*>*)resolutionValues {
  NSMutableArray<NSString*>* values = [NSMutableArray array];
  for (NSInteger index = 0; index < RBXeniaResolutionCount; index++) [values addObject:@(index).stringValue];
  return values;
}

- (NSArray<NSString*>*)resolutionTitles {
  NSMutableArray<NSString*>* titles = [NSMutableArray array];
  NSString* fallback = [self text:@"default" fallback:@"default"];
  for (NSInteger index = 0; index < RBXeniaResolutionCount; index++) {
    NSString* label = RBXeniaResolutionLabel(index);
    [titles addObject:index == 8 ? [NSString stringWithFormat:@"%@ (%@)", label, fallback] : label];
  }
  return titles;
}

- (NSString*)titleOf:(NSString*)value values:(NSArray<NSString*>*)values titles:(NSArray<NSString*>*)titles {
  const NSUInteger index = [values indexOfObject:value];
  return index == NSNotFound ? value : titles[index];
}

// key, values, titles of a row of the This game section.
- (void)gameRow:(NSInteger)row key:(NSString**)key values:(NSArray<NSString*>**)values
         titles:(NSArray<NSString*>**)titles title:(NSString**)title fallback:(NSString**)fallback {
  switch (row) {
    case RBXeniaGameRowAspect:
      *key = @"widescreen";
      *values = @[ @"true", @"false" ];
      *titles = @[ [self text:@"aspectWide" fallback:@"16:9 (widescreen)"], [self text:@"aspectStandard" fallback:@"4:3"] ];
      *title = [self text:@"aspect" fallback:@"Aspect ratio"];
      *fallback = @"true";
      break;
    case RBXeniaGameRowResolution:
      *key = @"internal_display_resolution";
      *values = [self resolutionValues];
      *titles = [self resolutionTitles];
      *title = [self text:@"resolution" fallback:@"Resolution reported to the game"];
      *fallback = @"8";
      break;
    default:
      *key = @"present_letterbox";
      *values = @[ @"true", @"false" ];
      *titles = @[ [self text:@"on" fallback:@"On"], [self text:@"off" fallback:@"Off"] ];
      *title = [self text:@"letterbox" fallback:@"Letterbox"];
      *fallback = @"true";
      break;
  }
}

- (void)viewDidLoad {
  [super viewDidLoad];
  self.tableView.cellLayoutMarginsFollowReadableWidth = YES;
}

- (NSInteger)numberOfSectionsInTableView:(UITableView*)tableView {
  return RBXeniaMenuSectionCount;
}

- (NSInteger)tableView:(UITableView*)tableView numberOfRowsInSection:(NSInteger)section {
  switch (section) {
    case RBXeniaMenuSectionResume:
    case RBXeniaMenuSectionDisplay:
      return 1;
    case RBXeniaMenuSectionGame:
      return RBXeniaGameRowCount;
    default:
      return 2;
  }
}

- (NSString*)tableView:(UITableView*)tableView titleForHeaderInSection:(NSInteger)section {
  if (section == RBXeniaMenuSectionDisplay) return [self text:@"display" fallback:@"Display"];
  if (section == RBXeniaMenuSectionGame) return [self text:@"thisGame" fallback:@"This game"];
  return nil;
}

- (NSString*)tableView:(UITableView*)tableView titleForFooterInSection:(NSInteger)section {
  if (section == RBXeniaMenuSectionDisplay)
    return [self text:@"appliesNow" fallback:@"Applies now, to all Xbox 360 games."];
  if (section == RBXeniaMenuSectionGame)
    return [self text:@"nextLaunch"
             fallback:@"Aspect ratio, resolution and letterbox apply the next time this game starts. "
                      @"They are saved for this game."];
  return nil;
}

- (UITableViewCell*)tableView:(UITableView*)tableView cellForRowAtIndexPath:(NSIndexPath*)indexPath {
  UITableViewCell* cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleValue1 reuseIdentifier:nil];
  cell.accessoryType = UITableViewCellAccessoryNone;
  switch (indexPath.section) {
    case RBXeniaMenuSectionResume:
      cell.textLabel.text = [self text:@"resume" fallback:@"Resume"];
      cell.textLabel.textColor = self.view.tintColor;
      cell.textLabel.font = [UIFont boldSystemFontOfSize:UIFont.labelFontSize];
      break;
    case RBXeniaMenuSectionDisplay:
      cell.textLabel.text = [self text:@"overlay" fallback:@"Performance overlay"];
      cell.detailTextLabel.text = [self titleOf:self.overlayLevel values:RBXeniaOverlayLevels()
                                         titles:[self overlayTitles]];
      cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
      break;
    case RBXeniaMenuSectionGame: {
      NSString* key = nil;
      NSString* title = nil;
      NSString* fallback = nil;
      NSArray<NSString*>* values = nil;
      NSArray<NSString*>* titles = nil;
      [self gameRow:indexPath.row key:&key values:&values titles:&titles title:&title fallback:&fallback];
      cell.textLabel.text = title;
      cell.detailTextLabel.text = [self titleOf:[self setting:key fallback:fallback] values:values titles:titles];
      cell.accessoryType = UITableViewCellAccessoryDisclosureIndicator;
      break;
    }
    default:
      if (indexPath.row == 0) {
        cell.textLabel.text = [self text:@"touchControls" fallback:@"Edit touch controls"];
      } else {
        cell.textLabel.text = [self text:@"quit" fallback:@"Quit game"];
        cell.textLabel.textColor = UIColor.systemRedColor;
      }
      break;
  }
  return cell;
}

- (void)pushChoiceTitled:(NSString*)title
                  values:(NSArray<NSString*>*)values
                  titles:(NSArray<NSString*>*)titles
                selected:(NSString*)selected
                  footer:(NSString*)footer
                  chosen:(void (^)(NSString* value))chosen {
  RBXeniaChoiceMenu* choice = [[RBXeniaChoiceMenu alloc] init];
  choice.title = title;
  choice.values = values;
  choice.titles = titles;
  choice.selected = selected;
  choice.footer = footer;
  choice.chosen = chosen;
  [self.navigationController pushViewController:choice animated:YES];
}

- (void)closeThen:(void (^)(id<RBXeniaSessionMenuHost> host))action {
  if (self.closing) return;
  self.closing = YES;
  id<RBXeniaSessionMenuHost> host = self.host;
  [self.navigationController dismissViewControllerAnimated:YES completion:^{
    if (host) action(host);
  }];
}

- (void)tableView:(UITableView*)tableView didSelectRowAtIndexPath:(NSIndexPath*)indexPath {
  [tableView deselectRowAtIndexPath:indexPath animated:YES];
  __weak RBXeniaSessionMenu* weakSelf = self;
  switch (indexPath.section) {
    case RBXeniaMenuSectionResume:
      [self closeThen:^(id<RBXeniaSessionMenuHost> host) { [host sessionMenuResume]; }];
      break;
    case RBXeniaMenuSectionDisplay:
      [self pushChoiceTitled:[self text:@"overlay" fallback:@"Performance overlay"]
                      values:RBXeniaOverlayLevels()
                      titles:[self overlayTitles]
                    selected:self.overlayLevel
                      footer:[self text:@"appliesNow" fallback:@"Applies now, to all Xbox 360 games."]
                      chosen:^(NSString* value) {
        RBXeniaSessionMenu* strongSelf = weakSelf;
        if (!strongSelf) return;
        strongSelf.overlayLevel = value;
        [strongSelf.tableView reloadData];
        [strongSelf.host sessionMenuSetOverlayLevel:value];
      }];
      break;
    case RBXeniaMenuSectionGame: {
      NSString* key = nil;
      NSString* title = nil;
      NSString* fallback = nil;
      NSArray<NSString*>* values = nil;
      NSArray<NSString*>* titles = nil;
      [self gameRow:indexPath.row key:&key values:&values titles:&titles title:&title fallback:&fallback];
      [self pushChoiceTitled:title
                      values:values
                      titles:titles
                    selected:[self setting:key fallback:fallback]
                      footer:[self tableView:tableView titleForFooterInSection:RBXeniaMenuSectionGame]
                      chosen:^(NSString* value) {
        RBXeniaSessionMenu* strongSelf = weakSelf;
        if (!strongSelf) return;
        strongSelf.settings[key] = value;
        [strongSelf.tableView reloadData];
        [strongSelf.host sessionMenuSetGameSetting:key value:value];
      }];
      break;
    }
    default:
      if (indexPath.row == 0) {
        [self closeThen:^(id<RBXeniaSessionMenuHost> host) { [host sessionMenuEditTouchControls]; }];
      } else {
        [self closeThen:^(id<RBXeniaSessionMenuHost> host) { [host sessionMenuQuit]; }];
      }
      break;
  }
}

// A swipe down closes the menu as Resume does.
- (void)presentationControllerDidDismiss:(UIPresentationController*)presentationController {
  if (self.closing) return;
  self.closing = YES;
  [self.host sessionMenuResume];
}

@end

// ------------------------------------------------------------------ overlay

@implementation RBXeniaPerformanceOverlay {
  NSDictionary<NSString*, NSString*>* _texts;
  NSString* _locale;
  UILabel* _label;
  NSNumberFormatter* _decimal;
  BOOL _hasSample;
  uint64_t _lastFrames;
  uint64_t _lastNanoseconds;
  BOOL _hasRate;
  double _fps;
  double _frameMilliseconds;
}

- (instancetype)initWithTexts:(NSDictionary<NSString*, NSString*>*)texts locale:(NSString*)locale {
  if ((self = [super initWithFrame:CGRectZero])) {
    _texts = [texts copy];
    _locale = [locale copy];
    _level = @"off";
    self.userInteractionEnabled = NO;
    self.hidden = YES;
    self.backgroundColor = [UIColor colorWithWhite:0 alpha:0.55];
    self.layer.cornerRadius = 8;
    self.accessibilityElementsHidden = YES;
    _label = [[UILabel alloc] init];
    _label.numberOfLines = 0;
    _label.textColor = UIColor.whiteColor;
    _label.font = [UIFont monospacedDigitSystemFontOfSize:12 weight:UIFontWeightSemibold];
    _label.translatesAutoresizingMaskIntoConstraints = NO;
    [self addSubview:_label];
    [NSLayoutConstraint activateConstraints:@[
      [_label.topAnchor constraintEqualToAnchor:self.topAnchor constant:4],
      [_label.bottomAnchor constraintEqualToAnchor:self.bottomAnchor constant:-4],
      [_label.leadingAnchor constraintEqualToAnchor:self.leadingAnchor constant:8],
      [_label.trailingAnchor constraintEqualToAnchor:self.trailingAnchor constant:-8],
    ]];
    _decimal = [[NSNumberFormatter alloc] init];
    _decimal.numberStyle = NSNumberFormatterDecimalStyle;
    _decimal.minimumFractionDigits = 1;
    _decimal.maximumFractionDigits = 1;
    _decimal.locale = [NSLocale localeWithLocaleIdentifier:_locale.length ? _locale : @"en"];
    [self render];
  }
  return self;
}

- (void)setLevel:(NSString*)level {
  _level = [RBXeniaOverlayLevels() containsObject:level] ? [level copy] : @"off";
  self.hidden = [_level isEqualToString:@"off"];
  if (self.hidden) {
    _hasSample = NO;
    _hasRate = NO;
  }
  [self render];
}

- (void)resetSamples {
  _hasSample = NO;
}

- (void)sampleGuestFrames:(uint64_t)frames atNanoseconds:(uint64_t)nanoseconds {
  if (_hasSample && frames >= _lastFrames && nanoseconds > _lastNanoseconds) {
    const double seconds = (double)(nanoseconds - _lastNanoseconds) / 1e9;
    const uint64_t presented = frames - _lastFrames;
    _fps = (double)presented / seconds;
    _frameMilliseconds = presented ? seconds * 1000.0 / (double)presented : 0;
    _hasRate = YES;
  }
  _lastFrames = frames;
  _lastNanoseconds = nanoseconds;
  _hasSample = YES;
  [self render];
}

- (NSString*)text:(NSString*)key fallback:(NSString*)fallback {
  return RBXeniaText(_texts, key, fallback);
}

- (NSString*)thermalText {
  switch (NSProcessInfo.processInfo.thermalState) {
    case NSProcessInfoThermalStateNominal: return [self text:@"thermalNominal" fallback:@"Normal"];
    case NSProcessInfoThermalStateFair: return [self text:@"thermalFair" fallback:@"Warm"];
    case NSProcessInfoThermalStateSerious: return [self text:@"thermalSerious" fallback:@"Hot"];
    case NSProcessInfoThermalStateCritical: return [self text:@"thermalCritical" fallback:@"Critical"];
  }
  return @"–";
}

// The process footprint (what iOS counts against the memory limit).
static long long RBXeniaFootprintBytes(void) {
  task_vm_info_data_t info;
  mach_msg_type_number_t count = TASK_VM_INFO_COUNT;
  if (task_info(mach_task_self(), TASK_VM_INFO, (task_info_t)&info, &count) != KERN_SUCCESS) return -1;
  return (long long)info.phys_footprint;
}

- (void)render {
  if (self.hidden) return;
  NSString* fps = _hasRate ? [NSString stringWithFormat:@"%.0f", _fps] : @"–";
  NSString* fpsLabel = [self text:@"fps" fallback:@"FPS"];
  if ([_level isEqualToString:@"simple"]) {
    _label.text = [NSString stringWithFormat:@"%@ %@", fps, fpsLabel];
  } else {
    NSString* frame = _hasRate && _frameMilliseconds > 0
                          ? [NSString stringWithFormat:@"%@ ms", [_decimal stringFromNumber:@(_frameMilliseconds)]]
                          : @"–";
    const long long footprint = RBXeniaFootprintBytes();
    NSString* memory = footprint >= 0 ? [NSByteCountFormatter stringFromByteCount:footprint
                                                                       countStyle:NSByteCountFormatterCountStyleMemory]
                                      : @"–";
    _label.text = [NSString stringWithFormat:@"%@ %@\n%@ %@\n%@ %@\n%@ %@", fpsLabel, fps,
                   [self text:@"frameTime" fallback:@"Frame time"], frame,
                   [self text:@"memory" fallback:@"Memory"], memory,
                   [self text:@"thermal" fallback:@"Temperature"], [self thermalText]];
  }
}

@end
