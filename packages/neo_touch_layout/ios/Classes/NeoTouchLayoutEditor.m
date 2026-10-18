// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTouchLayoutEditor.h"
#import "Public/NeoTouchControllerMonitor.h"
#import "Public/NeoTouchLayoutApplier.h"
#import "Public/NeoTouchLayoutGeometry.h"
#import "Public/NeoTouchLayoutStrings.h"

typedef NS_ENUM(NSInteger, NeoTouchGestureMode) {
  NeoTouchGestureNone = 0,
  NeoTouchGestureDrag,
  NeoTouchGestureResize,
  NeoTouchGesturePinch,
};

static NSString* NeoTouchDraftKey(NeoTouchLayoutScope scope, NSString* orientation) {
  return [NSString stringWithFormat:@"%@|%@", scope == NeoTouchLayoutScopeGame ? @"game" : @"general", orientation];
}

static const CGFloat kNeoTouchHandleRadius = 26.0;
static const CGFloat kNeoTouchHitSlop = 6.0;
static const NSUInteger kNeoTouchUndoLimit = 64;

#pragma mark - Undo entries and outlines

@interface NeoTouchUndoEntry : NSObject
@property(nonatomic, copy) NSString* draftKey;
@property(nonatomic, copy) NeoTouchLayout* layout;
@property(nonatomic) BOOL followGeneral;
@property(nonatomic) BOOL dirty;
@end

@implementation NeoTouchUndoEntry
@end

@interface NeoTouchOutlineView : UIView
@property(nonatomic) BOOL selectedOutline;
@property(nonatomic) BOOL hiddenControl;
@property(nonatomic, strong) CAShapeLayer* border;
@property(nonatomic, strong) NSArray<UIView*>* handles;
@property(nonatomic, strong) UILabel* badge;
@end

@implementation NeoTouchOutlineView

- (instancetype)initWithFrame:(CGRect)frame {
  self = [super initWithFrame:frame];
  if (self) {
    self.userInteractionEnabled = NO;
    self.backgroundColor = UIColor.clearColor;
    _border = [CAShapeLayer layer];
    _border.fillColor = UIColor.clearColor.CGColor;
    [self.layer addSublayer:_border];
    NSMutableArray* handles = [NSMutableArray array];
    for (NSUInteger index = 0; index < 4; index++) {
      UIView* handle = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 12, 12)];
      handle.backgroundColor = UIColor.systemYellowColor;
      handle.layer.cornerRadius = 6;
      handle.layer.borderWidth = 1.5;
      handle.layer.borderColor = UIColor.blackColor.CGColor;
      handle.hidden = YES;
      [self addSubview:handle];
      [handles addObject:handle];
    }
    _handles = handles;
    _badge = [UILabel new];
    _badge.font = [UIFont systemFontOfSize:10 weight:UIFontWeightBold];
    _badge.textColor = UIColor.blackColor;
    _badge.backgroundColor = [UIColor.systemYellowColor colorWithAlphaComponent:0.9];
    _badge.textAlignment = NSTextAlignmentCenter;
    _badge.layer.cornerRadius = 4;
    _badge.clipsToBounds = YES;
    _badge.hidden = YES;
    [self addSubview:_badge];
  }
  return self;
}

- (void)layoutSubviews {
  [super layoutSubviews];
  CGRect box = CGRectInset(self.bounds, 1.5, 1.5);
  self.border.frame = self.bounds;
  self.border.path = [UIBezierPath bezierPathWithRoundedRect:box cornerRadius:8].CGPath;
  self.border.lineWidth = self.selectedOutline ? 2.5 : 1.0;
  self.border.strokeColor = (self.selectedOutline ? UIColor.systemYellowColor
                                                  : [UIColor colorWithWhite:1 alpha:0.75]).CGColor;
  self.border.lineDashPattern = self.selectedOutline ? nil : @[@5, @4];
  const CGPoint corners[4] = {
    CGPointMake(CGRectGetMinX(box), CGRectGetMinY(box)), CGPointMake(CGRectGetMaxX(box), CGRectGetMinY(box)),
    CGPointMake(CGRectGetMinX(box), CGRectGetMaxY(box)), CGPointMake(CGRectGetMaxX(box), CGRectGetMaxY(box)),
  };
  for (NSUInteger index = 0; index < self.handles.count; index++) {
    self.handles[index].center = corners[index];
    self.handles[index].hidden = !self.selectedOutline;
  }
  [self.badge sizeToFit];
  CGRect badge = self.badge.frame;
  badge.size.width += 8;
  badge.size.height += 2;
  badge.origin = CGPointMake(CGRectGetMidX(self.bounds) - badge.size.width * 0.5, CGRectGetMinY(self.bounds) - badge.size.height - 2);
  self.badge.frame = badge;
  self.badge.hidden = !self.hiddenControl;
}

@end

#pragma mark - Editor

@interface NeoTouchLayoutEditor () <UITableViewDataSource, UITableViewDelegate>
@end

@implementation NeoTouchLayoutEditor {
  __weak id<NeoTouchLayoutEditorHost> _host;
  NeoTouchLayoutStore* _store;
  NSString* _locale;
  NSString* _title;
  NSMutableDictionary<NSString*, NeoTouchLayout*>* _drafts;
  NSMutableSet<NSString*>* _dirty;
  NSMutableSet<NSString*>* _following;
  NSMutableArray<NeoTouchUndoEntry*>* _undo;
  NSArray<NeoTouchElement*>* _elements;
  NSMutableDictionary<NSString*, NeoTouchOutlineView*>* _outlines;
  UIView* _outlineContainer;
  CAShapeLayer* _safeAreaLayer;
  // Gesture state.
  NSMutableArray<UITouch*>* _touches;
  NeoTouchGestureMode _mode;
  CGPoint _startPoint;
  CGPoint _startCenter;
  double _startScale;
  double _startDistance;
  BOOL _changeOpen;
  // Chrome.
  UIVisualEffectView* _toolbar;
  UIStackView* _toolbarColumn;
  UILabel* _caption;
  UIButton* _cancelButton;
  UIButton* _undoButton;
  UIButton* _resetButton;
  UIButton* _elementsButton;
  UIButton* _previewButton;
  UIButton* _moveButton;
  UIButton* _useGeneralButton;
  UIButton* _saveButton;
  UISegmentedControl* _scopeControl;
  UIVisualEffectView* _inspector;
  UILabel* _nameLabel;
  UISlider* _sizeSlider;
  UILabel* _sizeValue;
  UISlider* _opacitySlider;
  UILabel* _opacityValue;
  UISwitch* _visibleSwitch;
  UILabel* _visibleLabel;
  UIButton* _resetControlButton;
  UIVisualEffectView* _elementsPanel;
  UITableView* _elementsTable;
  UILabel* _hintLabel;
  UIButton* _endPreviewButton;
  BOOL _toolbarAtBottom;
  BOOL _finishedCalled;
  BOOL _presented;
  NSString* _errorText;
  NSNumberFormatter* _percent;
}

- (instancetype)initWithHost:(id<NeoTouchLayoutEditorHost>)host
                   layoutKey:(NSString*)layoutKey
                     gameKey:(NSString*)gameKey
                       title:(NSString*)title
                      locale:(NSString*)locale
                       store:(NeoTouchLayoutStore*)store {
  self = [super initWithFrame:CGRectZero];
  if (self) {
    _host = host;
    _layoutKey = [layoutKey copy];
    _gameKey = [NeoTouchLayoutGameKey(gameKey) copy];
    _title = [title copy];
    _locale = NeoTouchLayoutCanonicalLocale(locale);
    _store = store;
    _drafts = [NSMutableDictionary dictionary];
    _dirty = [NSMutableSet set];
    _following = [NSMutableSet set];
    _undo = [NSMutableArray array];
    _outlines = [NSMutableDictionary dictionary];
    _touches = [NSMutableArray array];
    _elements = @[];
    UIView* canvas = [host touchLayoutCanvas];
    _orientation = NeoTouchLayoutOrientationForSize(canvas.bounds.size);
    _scope = (_gameKey && [store hasGameLayoutForKey:layoutKey game:_gameKey]) ? NeoTouchLayoutScopeGame
                                                                                 : NeoTouchLayoutScopeGeneral;
    _percent = [NSNumberFormatter new];
    _percent.numberStyle = NSNumberFormatterPercentStyle;
    _percent.maximumFractionDigits = 0;
    _percent.locale = [NSLocale localeWithLocaleIdentifier:[_locale stringByReplacingOccurrencesOfString:@"_" withString:@"-"]];
    self.multipleTouchEnabled = YES;
    self.backgroundColor = UIColor.clearColor;
    self.accessibilityIdentifier = @"neo.touchLayout.editor";
    [self buildChrome];
  }
  return self;
}

- (NSString*)text:(NSString*)key {
  return NeoTouchLayoutText(key, _locale);
}

#pragma mark Chrome

- (UIButton*)toolbarButton:(NSString*)symbol textKey:(NSString*)key action:(SEL)action showsTitle:(BOOL)showsTitle {
  UIButtonConfiguration* configuration = [UIButtonConfiguration plainButtonConfiguration];
  if (symbol) configuration.image = [UIImage systemImageNamed:symbol];
  if (showsTitle) configuration.title = [self text:key];
  configuration.baseForegroundColor = UIColor.whiteColor;
  configuration.contentInsets = NSDirectionalEdgeInsetsMake(6, 8, 6, 8);
  configuration.imagePadding = 4;
  UIButton* button = [UIButton buttonWithConfiguration:configuration primaryAction:nil];
  button.accessibilityLabel = [self text:key];
  button.titleLabel.adjustsFontSizeToFitWidth = YES;
  [button addTarget:self action:action forControlEvents:UIControlEventTouchUpInside];
  [button setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
  return button;
}

- (UIVisualEffectView*)panel {
  UIVisualEffectView* panel = [[UIVisualEffectView alloc]
      initWithEffect:[UIBlurEffect effectWithStyle:UIBlurEffectStyleSystemThickMaterialDark]];
  panel.layer.cornerRadius = 14;
  panel.clipsToBounds = YES;
  panel.overrideUserInterfaceStyle = UIUserInterfaceStyleDark;
  return panel;
}

- (UILabel*)label:(UIFont*)font {
  UILabel* label = [UILabel new];
  label.font = font;
  label.textColor = UIColor.whiteColor;
  label.adjustsFontSizeToFitWidth = YES;
  label.minimumScaleFactor = 0.7;
  return label;
}

- (void)buildChrome {
  _outlineContainer = [[UIView alloc] initWithFrame:self.bounds];
  _outlineContainer.userInteractionEnabled = NO;
  _outlineContainer.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  [self addSubview:_outlineContainer];
  _safeAreaLayer = [CAShapeLayer layer];
  _safeAreaLayer.fillColor = UIColor.clearColor.CGColor;
  _safeAreaLayer.strokeColor = [UIColor colorWithWhite:1 alpha:0.18].CGColor;
  _safeAreaLayer.lineDashPattern = @[@3, @6];
  _safeAreaLayer.lineWidth = 1;
  [_outlineContainer.layer addSublayer:_safeAreaLayer];

  // Toolbar: actions on the first row, layout/scope/state on the second.
  _toolbar = [self panel];
  _toolbar.accessibilityIdentifier = @"neo.touchLayout.toolbar";
  _cancelButton = [self toolbarButton:@"xmark" textKey:@"cancel" action:@selector(cancelPressed) showsTitle:YES];
  _undoButton = [self toolbarButton:@"arrow.uturn.backward" textKey:@"undo" action:@selector(undo) showsTitle:NO];
  _resetButton = [self toolbarButton:@"arrow.counterclockwise" textKey:@"resetLayout"
                              action:@selector(restoreDefaultLayout) showsTitle:NO];
  _elementsButton = [self toolbarButton:@"list.bullet" textKey:@"elements" action:@selector(toggleElementsPanel)
                             showsTitle:NO];
  _previewButton = [self toolbarButton:@"eye" textKey:@"preview" action:@selector(previewPressed) showsTitle:NO];
  _moveButton = [self toolbarButton:@"arrow.up.and.down" textKey:@"moveToolbar" action:@selector(toggleToolbarPosition)
                         showsTitle:NO];
  _useGeneralButton = [self toolbarButton:@"rectangle.stack" textKey:@"useGeneralLayout"
                                   action:@selector(useGeneralLayout) showsTitle:NO];
  UIButtonConfiguration* saveConfiguration = [UIButtonConfiguration filledButtonConfiguration];
  saveConfiguration.title = [self text:@"save"];
  saveConfiguration.image = [UIImage systemImageNamed:@"checkmark"];
  saveConfiguration.imagePadding = 4;
  saveConfiguration.baseBackgroundColor = UIColor.systemYellowColor;
  saveConfiguration.baseForegroundColor = UIColor.blackColor;
  saveConfiguration.contentInsets = NSDirectionalEdgeInsetsMake(6, 10, 6, 10);
  _saveButton = [UIButton buttonWithConfiguration:saveConfiguration primaryAction:nil];
  _saveButton.accessibilityLabel = [self text:@"save"];
  [_saveButton addTarget:self action:@selector(savePressed) forControlEvents:UIControlEventTouchUpInside];
  [_saveButton setContentCompressionResistancePriority:UILayoutPriorityRequired forAxis:UILayoutConstraintAxisHorizontal];
  _scopeControl = [[UISegmentedControl alloc] initWithItems:@[[self text:@"scopeAllGames"], [self text:@"scopeThisGame"]]];
  _scopeControl.accessibilityIdentifier = @"neo.touchLayout.scope";
  [_scopeControl addTarget:self action:@selector(scopeChanged:) forControlEvents:UIControlEventValueChanged];
  _scopeControl.hidden = _gameKey == nil;

  UIStackView* row = [[UIStackView alloc] initWithArrangedSubviews:@[
    _cancelButton, _undoButton, _resetButton, _elementsButton, _previewButton, _moveButton, _scopeControl,
    _useGeneralButton, _saveButton,
  ]];
  row.axis = UILayoutConstraintAxisHorizontal;
  row.alignment = UIStackViewAlignmentCenter;
  row.spacing = 2;
  _caption = [self label:[UIFont systemFontOfSize:12 weight:UIFontWeightMedium]];
  _caption.textColor = [UIColor colorWithWhite:1 alpha:0.8];
  _caption.textAlignment = NSTextAlignmentCenter;
  _caption.numberOfLines = 2;
  _toolbarColumn = [[UIStackView alloc] initWithArrangedSubviews:@[row, _caption]];
  _toolbarColumn.axis = UILayoutConstraintAxisVertical;
  _toolbarColumn.alignment = UIStackViewAlignmentCenter;
  _toolbarColumn.spacing = 2;
  _toolbarColumn.layoutMargins = UIEdgeInsetsMake(6, 8, 6, 8);
  _toolbarColumn.layoutMarginsRelativeArrangement = YES;
  [_toolbar.contentView addSubview:_toolbarColumn];
  [self addSubview:_toolbar];

  // Inspector of the selected control.
  _inspector = [self panel];
  _inspector.accessibilityIdentifier = @"neo.touchLayout.inspector";
  _nameLabel = [self label:[UIFont systemFontOfSize:15 weight:UIFontWeightSemibold]];
  _sizeSlider = [UISlider new];
  _sizeSlider.minimumValue = NEO_TOUCH_MIN_SCALE * 100.0;
  _sizeSlider.maximumValue = NEO_TOUCH_MAX_SCALE * 100.0;
  _sizeSlider.accessibilityLabel = [self text:@"size"];
  _opacitySlider = [UISlider new];
  _opacitySlider.minimumValue = NEO_TOUCH_MIN_OPACITY * 100.0;
  _opacitySlider.maximumValue = NEO_TOUCH_MAX_OPACITY * 100.0;
  _opacitySlider.accessibilityLabel = [self text:@"opacity"];
  for (UISlider* slider in @[_sizeSlider, _opacitySlider]) {
    slider.minimumTrackTintColor = UIColor.systemYellowColor;
    [slider addTarget:self action:@selector(sliderBegan:) forControlEvents:UIControlEventTouchDown];
    [slider addTarget:self action:@selector(sliderChanged:) forControlEvents:UIControlEventValueChanged];
    [slider addTarget:self action:@selector(sliderEnded:)
          forControlEvents:UIControlEventTouchUpInside | UIControlEventTouchUpOutside | UIControlEventTouchCancel];
  }
  _sizeValue = [self label:[UIFont monospacedDigitSystemFontOfSize:13 weight:UIFontWeightMedium]];
  _opacityValue = [self label:[UIFont monospacedDigitSystemFontOfSize:13 weight:UIFontWeightMedium]];
  _visibleSwitch = [UISwitch new];
  _visibleSwitch.onTintColor = UIColor.systemYellowColor;
  _visibleSwitch.accessibilityLabel = [self text:@"visible"];
  [_visibleSwitch addTarget:self action:@selector(visibleChanged:) forControlEvents:UIControlEventValueChanged];
  _visibleLabel = [self label:[UIFont systemFontOfSize:13]];
  _visibleLabel.text = [self text:@"visible"];
  _resetControlButton = [self toolbarButton:@"arrow.counterclockwise" textKey:@"resetControl"
                                     action:@selector(resetSelectedPressed) showsTitle:YES];
  UILabel* sizeTitle = [self label:[UIFont systemFontOfSize:13]];
  sizeTitle.text = [self text:@"size"];
  UILabel* opacityTitle = [self label:[UIFont systemFontOfSize:13]];
  opacityTitle.text = [self text:@"opacity"];
  for (UILabel* label in @[sizeTitle, opacityTitle]) [label.widthAnchor constraintEqualToConstant:84].active = YES;
  for (UILabel* label in @[_sizeValue, _opacityValue]) {
    label.textAlignment = NSTextAlignmentRight;
    [label.widthAnchor constraintEqualToConstant:52].active = YES;
  }
  UIStackView* sizeRow = [[UIStackView alloc] initWithArrangedSubviews:@[sizeTitle, _sizeSlider, _sizeValue]];
  UIStackView* opacityRow = [[UIStackView alloc] initWithArrangedSubviews:@[opacityTitle, _opacitySlider, _opacityValue]];
  UIView* spacer = [UIView new];
  UIStackView* visibleRow = [[UIStackView alloc] initWithArrangedSubviews:@[_visibleLabel, _visibleSwitch, spacer,
                                                                             _resetControlButton]];
  for (UIStackView* line in @[sizeRow, opacityRow, visibleRow]) {
    line.axis = UILayoutConstraintAxisHorizontal;
    line.alignment = UIStackViewAlignmentCenter;
    line.spacing = 8;
  }
  UIStackView* inspectorColumn = [[UIStackView alloc] initWithArrangedSubviews:@[_nameLabel, sizeRow, opacityRow,
                                                                                  visibleRow]];
  inspectorColumn.axis = UILayoutConstraintAxisVertical;
  inspectorColumn.spacing = 4;
  inspectorColumn.layoutMargins = UIEdgeInsetsMake(8, 12, 8, 12);
  inspectorColumn.layoutMarginsRelativeArrangement = YES;
  inspectorColumn.translatesAutoresizingMaskIntoConstraints = NO;
  [_inspector.contentView addSubview:inspectorColumn];
  [NSLayoutConstraint activateConstraints:@[
    [inspectorColumn.leadingAnchor constraintEqualToAnchor:_inspector.contentView.leadingAnchor],
    [inspectorColumn.trailingAnchor constraintEqualToAnchor:_inspector.contentView.trailingAnchor],
    [inspectorColumn.topAnchor constraintEqualToAnchor:_inspector.contentView.topAnchor],
    [inspectorColumn.bottomAnchor constraintEqualToAnchor:_inspector.contentView.bottomAnchor],
  ]];
  _inspector.hidden = YES;
  [self addSubview:_inspector];

  // List of every control, with its visibility.
  _elementsPanel = [self panel];
  _elementsPanel.accessibilityIdentifier = @"neo.touchLayout.elements";
  UILabel* elementsTitle = [self label:[UIFont systemFontOfSize:15 weight:UIFontWeightSemibold]];
  elementsTitle.text = [self text:@"elements"];
  UILabel* elementsHelp = [self label:[UIFont systemFontOfSize:12]];
  elementsHelp.text = [self text:@"elementsHelp"];
  elementsHelp.numberOfLines = 2;
  elementsHelp.textColor = [UIColor colorWithWhite:1 alpha:0.75];
  UIButton* closeElements = [self toolbarButton:@"xmark.circle.fill" textKey:@"cancel"
                                         action:@selector(toggleElementsPanel) showsTitle:NO];
  UIStackView* header = [[UIStackView alloc] initWithArrangedSubviews:@[elementsTitle, closeElements]];
  header.axis = UILayoutConstraintAxisHorizontal;
  header.alignment = UIStackViewAlignmentCenter;
  _elementsTable = [[UITableView alloc] initWithFrame:CGRectZero style:UITableViewStylePlain];
  _elementsTable.backgroundColor = UIColor.clearColor;
  _elementsTable.dataSource = self;
  _elementsTable.delegate = self;
  _elementsTable.rowHeight = 44;
  UIStackView* elementsColumn = [[UIStackView alloc] initWithArrangedSubviews:@[header, elementsHelp, _elementsTable]];
  elementsColumn.axis = UILayoutConstraintAxisVertical;
  elementsColumn.spacing = 4;
  elementsColumn.layoutMargins = UIEdgeInsetsMake(8, 12, 8, 8);
  elementsColumn.layoutMarginsRelativeArrangement = YES;
  elementsColumn.translatesAutoresizingMaskIntoConstraints = NO;
  [_elementsPanel.contentView addSubview:elementsColumn];
  [NSLayoutConstraint activateConstraints:@[
    [elementsColumn.leadingAnchor constraintEqualToAnchor:_elementsPanel.contentView.leadingAnchor],
    [elementsColumn.trailingAnchor constraintEqualToAnchor:_elementsPanel.contentView.trailingAnchor],
    [elementsColumn.topAnchor constraintEqualToAnchor:_elementsPanel.contentView.topAnchor],
    [elementsColumn.bottomAnchor constraintEqualToAnchor:_elementsPanel.contentView.bottomAnchor],
  ]];
  _elementsPanel.hidden = YES;
  [self addSubview:_elementsPanel];

  _hintLabel = [self label:[UIFont systemFontOfSize:14 weight:UIFontWeightMedium]];
  _hintLabel.text = [self text:@"hint"];
  _hintLabel.numberOfLines = 0;
  _hintLabel.textAlignment = NSTextAlignmentCenter;
  _hintLabel.backgroundColor = [UIColor colorWithWhite:0 alpha:0.72];
  _hintLabel.layer.cornerRadius = 12;
  _hintLabel.clipsToBounds = YES;
  _hintLabel.userInteractionEnabled = NO;
  [self addSubview:_hintLabel];

  UIButtonConfiguration* endPreview = [UIButtonConfiguration filledButtonConfiguration];
  endPreview.title = [self text:@"endPreview"];
  endPreview.image = [UIImage systemImageNamed:@"pencil"];
  endPreview.imagePadding = 4;
  endPreview.baseBackgroundColor = [UIColor colorWithWhite:0 alpha:0.7];
  endPreview.baseForegroundColor = UIColor.whiteColor;
  _endPreviewButton = [UIButton buttonWithConfiguration:endPreview primaryAction:nil];
  [_endPreviewButton addTarget:self action:@selector(endPreviewPressed) forControlEvents:UIControlEventTouchUpInside];
  _endPreviewButton.hidden = YES;
  [self addSubview:_endPreviewButton];
}

#pragma mark Presentation

- (void)presentOverCanvas {
  id<NeoTouchLayoutEditorHost> host = _host;
  UIView* canvas = [host touchLayoutCanvas];
  if (!canvas || _presented) return;
  _presented = YES;
  UIView* parent = canvas.superview ?: canvas;
  self.frame = parent == canvas ? canvas.bounds : [parent convertRect:canvas.bounds fromView:canvas];
  self.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  [parent addSubview:self];
  [canvas layoutIfNeeded];
  _orientation = NeoTouchLayoutOrientationForSize(canvas.bounds.size);
  [self applyDraft];
  __weak NeoTouchLayoutEditor* weakSelf = self;
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(6 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    [weakSelf dismissHint];
  });
}

- (void)dismissHint {
  if (_hintLabel.hidden) return;
  [UIView animateWithDuration:0.2 animations:^{ self->_hintLabel.alpha = 0; } completion:^(__unused BOOL done) {
    self->_hintLabel.hidden = YES;
  }];
}

- (void)setControllerConnected:(BOOL)controllerConnected {
  _controllerConnected = controllerConnected;
  [self refreshToolbar];
}

#pragma mark Drafts

- (NSString*)currentKey {
  return NeoTouchDraftKey(_scope, _orientation);
}

- (NeoTouchLayout*)storedDraftForScope:(NeoTouchLayoutScope)scope orientation:(NSString*)orientation {
  NSString* key = NeoTouchDraftKey(scope, orientation);
  NeoTouchLayout* draft = _drafts[key];
  if (draft) return draft;
  if (scope == NeoTouchLayoutScopeGeneral || !_gameKey) {
    draft = [_store layoutForKey:_layoutKey orientation:orientation game:nil] ?: [NeoTouchLayout new];
  } else {
    draft = [_store layoutForKey:_layoutKey orientation:orientation game:_gameKey];
    if (!draft) {
      draft = [NeoTouchLayout new];
      [_following addObject:key];
    }
  }
  _drafts[key] = draft;
  return draft;
}

/// The layout shown for a scope: a game that follows the general layout
/// shows the general draft.
- (NeoTouchLayout*)visibleDraftForScope:(NeoTouchLayoutScope)scope orientation:(NSString*)orientation {
  NeoTouchLayout* draft = [self storedDraftForScope:scope orientation:orientation];
  if (scope == NeoTouchLayoutScopeGame && [_following containsObject:NeoTouchDraftKey(scope, orientation)])
    return [self storedDraftForScope:NeoTouchLayoutScopeGeneral orientation:orientation];
  return draft;
}

- (NeoTouchLayout*)draftLayout {
  return [[self visibleDraftForScope:_scope orientation:_orientation] copy];
}

/// The draft about to change: a game following the general layout gets its
/// own copy first.
- (NeoTouchLayout*)mutableDraft {
  NSString* key = [self currentKey];
  if (_scope == NeoTouchLayoutScopeGame && [_following containsObject:key]) {
    _drafts[key] = [[self storedDraftForScope:NeoTouchLayoutScopeGeneral orientation:_orientation] copy];
    [_following removeObject:key];
  }
  [_dirty addObject:key];
  return [self storedDraftForScope:_scope orientation:_orientation];
}

- (void)pushUndo {
  NSString* key = [self currentKey];
  NeoTouchUndoEntry* entry = [NeoTouchUndoEntry new];
  entry.draftKey = key;
  entry.layout = [self storedDraftForScope:_scope orientation:_orientation];
  entry.followGeneral = [_following containsObject:key];
  entry.dirty = [_dirty containsObject:key];
  [_undo addObject:entry];
  if (_undo.count > kNeoTouchUndoLimit) [_undo removeObjectAtIndex:0];
}

- (void)beginChange {
  if (_changeOpen) return;
  _changeOpen = YES;
  [self pushUndo];
}

- (void)endChange {
  if (!_changeOpen) return;
  _changeOpen = NO;
  NeoTouchUndoEntry* top = _undo.lastObject;
  NSString* key = [self currentKey];
  if (top && [top.draftKey isEqualToString:key] && top.followGeneral == [_following containsObject:key] &&
      [top.layout isEqualToLayout:[self storedDraftForScope:_scope orientation:_orientation]]) {
    [_undo removeLastObject];
    if (!top.dirty) [_dirty removeObject:key];
  }
  [self refreshChrome];
}

- (void)performChange:(void (^)(void))change {
  const BOOL nested = _changeOpen;
  if (!nested) [self beginChange];
  change();
  [self applyDraft];
  if (!nested) [self endChange];
}

- (BOOL)hasChanges {
  for (NSString* key in _dirty) {
    NSArray* parts = [key componentsSeparatedByString:@"|"];
    const BOOL game = [parts.firstObject isEqualToString:@"game"];
    NSString* orientation = parts.lastObject;
    NeoTouchLayout* stored = [_store layoutForKey:_layoutKey orientation:orientation game:game ? _gameKey : nil];
    if (game && [_following containsObject:key]) {
      if (stored) return YES;
      continue;
    }
    NeoTouchLayout* draft = _drafts[key];
    if (game ? ![draft isEqualToLayout:stored] || !stored : ![draft isEqualToLayout:stored]) return YES;
  }
  return NO;
}

#pragma mark Elements

- (NeoTouchElement*)elementWithIdentifier:(NSString*)identifier {
  for (NeoTouchElement* element in _elements)
    if ([element.identifier isEqualToString:identifier]) return element;
  return nil;
}

- (UIView*)canvas {
  return [_host touchLayoutCanvas];
}

- (CGRect)frameOfElement:(NSString*)identifier {
  NeoTouchElement* element = [self elementWithIdentifier:identifier];
  UIView* canvas = [self canvas];
  if (!element || !canvas) return CGRectNull;
  CGRect frame = [NeoTouchLayoutApplier frameOfElement:element layout:[self draftLayout] canvas:canvas];
  return [self convertRect:frame fromView:canvas];
}

- (NSString*)elementAtPoint:(CGPoint)point {
  for (NeoTouchElement* element in _elements.reverseObjectEnumerator) {
    if (CGRectContainsPoint(CGRectInset([self frameOfElement:element.identifier], -kNeoTouchHitSlop, -kNeoTouchHitSlop), point))
      return element.identifier;
  }
  return nil;
}

- (void)applyDraft {
  id<NeoTouchLayoutEditorHost> host = _host;
  [host touchLayoutApplyLayout:[self draftLayout] editing:YES];
  _elements = [host touchLayoutElements] ?: @[];
  if (_selectedIdentifier && ![self elementWithIdentifier:_selectedIdentifier]) _selectedIdentifier = nil;
  [self refreshChrome];
}

#pragma mark Actions

- (void)selectScope:(NeoTouchLayoutScope)scope {
  if (scope == NeoTouchLayoutScopeGame && !_gameKey) return;
  [self endChange];
  _scope = scope;
  [self applyDraft];
}

- (void)selectElement:(NSString*)identifier {
  _selectedIdentifier = identifier && [self elementWithIdentifier:identifier] ? [identifier copy] : nil;
  [self refreshChrome];
}

- (void)applyCenter:(CGPoint)center toElement:(NeoTouchElement*)element {
  UIView* canvas = [self canvas];
  if (!canvas) return;
  NeoTouchLayout* draft = [self mutableDraft];
  NeoTouchControlState* state = [draft stateForIdentifier:element.identifier];
  const double scale = NeoTouchClampScale(state.scale);
  NeoTouchPoint target = {center.x, center.y};
  NeoTouchRect bounds = {canvas.bounds.origin.x, canvas.bounds.origin.y, canvas.bounds.size.width, canvas.bounds.size.height};
  target = NeoTouchClampCenter(target, element.defaultSize.width * scale, element.defaultSize.height * scale, bounds);
  const CGPoint normalized = [NeoTouchLayoutApplier normalizedPositionForCenter:CGPointMake(target.x, target.y)
                                                                         canvas:canvas];
  state.hasPosition = YES;
  state.x = normalized.x;
  state.y = normalized.y;
  [draft setState:state forIdentifier:element.identifier];
}

- (void)moveElement:(NSString*)identifier toCenter:(CGPoint)center {
  NeoTouchElement* element = [self elementWithIdentifier:identifier];
  if (!element) return;
  [self performChange:^{ [self applyCenter:center toElement:element]; }];
}

- (void)applyScale:(double)scale toIdentifier:(NSString*)identifier {
  NeoTouchLayout* draft = [self mutableDraft];
  NeoTouchControlState* state = [draft stateForIdentifier:identifier];
  state.scale = NeoTouchClampScale(scale);
  [draft setState:state forIdentifier:identifier];
}

- (void)setScale:(CGFloat)scale forElement:(NSString*)identifier {
  if (![self elementWithIdentifier:identifier]) return;
  [self performChange:^{ [self applyScale:scale toIdentifier:identifier]; }];
}

- (void)applyOpacity:(double)opacity toIdentifier:(NSString*)identifier {
  NeoTouchLayout* draft = [self mutableDraft];
  NeoTouchControlState* state = [draft stateForIdentifier:identifier];
  state.opacity = NeoTouchClampOpacity(opacity);
  [draft setState:state forIdentifier:identifier];
}

- (void)setOpacity:(CGFloat)opacity forElement:(NSString*)identifier {
  if (![self elementWithIdentifier:identifier]) return;
  [self performChange:^{ [self applyOpacity:opacity toIdentifier:identifier]; }];
}

- (void)setHidden:(BOOL)hidden forElement:(NSString*)identifier {
  if (![self elementWithIdentifier:identifier]) return;
  [self performChange:^{
    NeoTouchLayout* draft = [self mutableDraft];
    NeoTouchControlState* state = [draft stateForIdentifier:identifier];
    state.hidden = hidden;
    [draft setState:state forIdentifier:identifier];
  }];
}

- (void)resetElement:(NSString*)identifier {
  if (![self elementWithIdentifier:identifier]) return;
  [self performChange:^{ [[self mutableDraft] setState:nil forIdentifier:identifier]; }];
}

- (void)undo {
  [self endChange];
  NeoTouchUndoEntry* entry = _undo.lastObject;
  if (!entry) return;
  [_undo removeLastObject];
  NSArray* parts = [entry.draftKey componentsSeparatedByString:@"|"];
  _scope = [parts.firstObject isEqualToString:@"game"] ? NeoTouchLayoutScopeGame : NeoTouchLayoutScopeGeneral;
  _drafts[entry.draftKey] = [entry.layout copy];
  if (entry.followGeneral) [_following addObject:entry.draftKey];
  else [_following removeObject:entry.draftKey];
  if (entry.dirty) [_dirty addObject:entry.draftKey];
  else [_dirty removeObject:entry.draftKey];
  // An entry of the other orientation applies when the surface turns back.
  [self applyDraft];
}

- (void)restoreDefaultLayout {
  [self performChange:^{
    NSString* key = [self currentKey];
    [self->_following removeObject:key];
    self->_drafts[key] = [NeoTouchLayout new];
    [self->_dirty addObject:key];
  }];
}

- (void)useGeneralLayout {
  if (_scope != NeoTouchLayoutScopeGame) return;
  [self performChange:^{
    NSString* key = [self currentKey];
    [self->_following addObject:key];
    [self->_dirty addObject:key];
  }];
}

- (void)toggleToolbarPosition {
  _toolbarAtBottom = !_toolbarAtBottom;
  [self setNeedsLayout];
  [self layoutIfNeeded];
}

- (void)setPreviewing:(BOOL)previewing {
  if (_previewing == previewing) return;
  [self endChange];
  _previewing = previewing;
  if (previewing) {
    _elementsPanel.hidden = YES;
    [self dismissHint];
  }
  id<NeoTouchLayoutEditorHost> host = _host;
  // The preview shows exactly what the game will show: hidden controls gone.
  [host touchLayoutApplyLayout:[self draftLayout] editing:!previewing];
  [self refreshChrome];
}

- (BOOL)save {
  [self endChange];
  NSError* failure = nil;
  BOOL ok = YES;
  NSMutableSet* keys = [_dirty mutableCopy];
  for (NSString* key in keys) {
    NSArray* parts = [key componentsSeparatedByString:@"|"];
    const BOOL game = [parts.firstObject isEqualToString:@"game"];
    NSString* orientation = parts.lastObject;
    if (game && [_following containsObject:key]) {
      ok = [_store removeLayoutForKey:_layoutKey orientation:orientation game:_gameKey error:&failure] && ok;
    } else {
      NeoTouchLayout* draft = _drafts[key] ?: [NeoTouchLayout new];
      ok = [_store saveLayout:draft forKey:_layoutKey orientation:orientation game:game ? _gameKey : nil
                        error:&failure] && ok;
    }
    if (ok) [_dirty removeObject:key];
  }
  if (!ok) {
    _errorText = [self text:@"saveFailed"];
    NSLog(@"[NeoTouchLayout] Save failed for %@: %@", _layoutKey, failure.localizedDescription);
    [self refreshChrome];
    return NO;
  }
  [self finish:YES];
  return YES;
}

- (void)cancel {
  [self endChange];
  [self finish:NO];
}

- (void)finish:(BOOL)saved {
  if (_finishedCalled) return;
  _finishedCalled = YES;
  [_touches removeAllObjects];
  [self removeFromSuperview];
  void (^finished)(BOOL) = self.finished;
  self.finished = nil;
  if (finished) finished(saved);
}

- (void)cancelPressed { [self cancel]; }
- (void)savePressed { [self save]; }
- (void)previewPressed { [self setPreviewing:YES]; }
- (void)endPreviewPressed { [self setPreviewing:NO]; }

- (void)scopeChanged:(UISegmentedControl*)control {
  [self selectScope:control.selectedSegmentIndex == 1 ? NeoTouchLayoutScopeGame : NeoTouchLayoutScopeGeneral];
}

- (void)toggleElementsPanel {
  _elementsPanel.hidden = !_elementsPanel.hidden;
  if (!_elementsPanel.hidden) [_elementsTable reloadData];
  [self setNeedsLayout];
}

- (void)resetSelectedPressed {
  if (_selectedIdentifier) [self resetElement:_selectedIdentifier];
}

- (void)sliderBegan:(UISlider*)slider {
  if (_selectedIdentifier) [self beginChange];
}

- (void)sliderChanged:(UISlider*)slider {
  NSString* identifier = _selectedIdentifier;
  if (!identifier) return;
  const BOOL nested = _changeOpen;
  if (!nested) [self beginChange];
  if (slider == _sizeSlider) [self applyScale:slider.value / 100.0 toIdentifier:identifier];
  else [self applyOpacity:slider.value / 100.0 toIdentifier:identifier];
  [self applyDraft];
  if (!nested) [self endChange];
}

- (void)sliderEnded:(UISlider*)slider {
  [self endChange];
}

- (void)visibleChanged:(UISwitch*)control {
  if (_selectedIdentifier) [self setHidden:!control.isOn forElement:_selectedIdentifier];
}

#pragma mark Touches

- (CGPoint)canvasPoint:(CGPoint)point {
  UIView* canvas = [self canvas];
  return canvas ? [self convertPoint:point toView:canvas] : point;
}

- (void)touchesBegan:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  [self dismissHint];
  if (_previewing) {
    [self setPreviewing:NO];
    return;
  }
  const NSUInteger before = _touches.count;
  for (UITouch* touch in touches) {
    // Touches that land on the toolbar or a panel and travel up the responder
    // chain are not edits.
    if (touch.view && touch.view != self) continue;
    if (![_touches containsObject:touch]) [_touches addObject:touch];
  }
  if (_touches.count == before) return;
  if (_touches.count == 1) [self beginSingleTouch:_touches.firstObject];
  else if (_touches.count == 2) [self beginPinch];
}

- (void)beginSingleTouch:(UITouch*)touch {
  const CGPoint point = [touch locationInView:self];
  _startPoint = point;
  _mode = NeoTouchGestureNone;
  if (_selectedIdentifier) {
    const CGRect frame = [self frameOfElement:_selectedIdentifier];
    const CGPoint corners[4] = {
      CGPointMake(CGRectGetMinX(frame), CGRectGetMinY(frame)), CGPointMake(CGRectGetMaxX(frame), CGRectGetMinY(frame)),
      CGPointMake(CGRectGetMinX(frame), CGRectGetMaxY(frame)), CGPointMake(CGRectGetMaxX(frame), CGRectGetMaxY(frame)),
    };
    for (NSUInteger index = 0; index < 4 && !CGRectIsNull(frame); index++) {
      if (hypot(point.x - corners[index].x, point.y - corners[index].y) <= kNeoTouchHandleRadius) {
        _mode = NeoTouchGestureResize;
        _startCenter = CGPointMake(CGRectGetMidX(frame), CGRectGetMidY(frame));
        _startScale = [[self draftLayout] stateForIdentifier:_selectedIdentifier].scale;
        [self beginChange];
        return;
      }
    }
  }
  NSString* hit = [self elementAtPoint:point];
  [self selectElement:hit];
  if (!hit) return;
  const CGRect frame = [self frameOfElement:hit];
  _startCenter = CGPointMake(CGRectGetMidX(frame), CGRectGetMidY(frame));
  _mode = NeoTouchGestureDrag;
  [self beginChange];
}

- (void)beginPinch {
  UITouch* first = _touches[0];
  UITouch* second = _touches[1];
  const CGPoint a = [first locationInView:self];
  const CGPoint b = [second locationInView:self];
  if (!_selectedIdentifier) [self selectElement:[self elementAtPoint:CGPointMake((a.x + b.x) * 0.5, (a.y + b.y) * 0.5)]];
  if (!_selectedIdentifier) {
    _mode = NeoTouchGestureNone;
    return;
  }
  _startDistance = hypot(a.x - b.x, a.y - b.y);
  _startScale = [[self draftLayout] stateForIdentifier:_selectedIdentifier].scale;
  _mode = _startDistance > 8 ? NeoTouchGesturePinch : NeoTouchGestureNone;
  if (_mode == NeoTouchGesturePinch) [self beginChange];
}

- (void)touchesMoved:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  NSString* identifier = _selectedIdentifier;
  NeoTouchElement* element = identifier ? [self elementWithIdentifier:identifier] : nil;
  if (!element || _touches.count == 0) return;
  if (_mode == NeoTouchGestureDrag && _touches.count == 1) {
    const CGPoint point = [_touches.firstObject locationInView:self];
    const CGPoint center = CGPointMake(_startCenter.x + point.x - _startPoint.x, _startCenter.y + point.y - _startPoint.y);
    [self applyCenter:[self canvasPoint:center] toElement:element];
    [self applyDraft];
  } else if (_mode == NeoTouchGestureResize && _touches.count == 1) {
    const CGPoint point = [_touches.firstObject locationInView:self];
    NeoTouchPoint center = {_startCenter.x, _startCenter.y};
    NeoTouchPoint start = {_startPoint.x, _startPoint.y};
    NeoTouchPoint current = {point.x, point.y};
    [self applyScale:NeoTouchScaleFromDrag(_startScale, center, start, current) toIdentifier:identifier];
    [self applyDraft];
  } else if (_mode == NeoTouchGesturePinch && _touches.count >= 2) {
    const CGPoint a = [_touches[0] locationInView:self];
    const CGPoint b = [_touches[1] locationInView:self];
    const double distance = hypot(a.x - b.x, a.y - b.y);
    [self applyScale:_startScale * distance / _startDistance toIdentifier:identifier];
    [self applyDraft];
  }
}

- (void)finishTouches:(NSSet<UITouch*>*)touches {
  for (UITouch* touch in touches) [_touches removeObject:touch];
  // Lifting one finger of a pinch must not turn it into a jump.
  if (_touches.count > 0) {
    _mode = NeoTouchGestureNone;
    return;
  }
  _mode = NeoTouchGestureNone;
  [self endChange];
}

- (void)touchesEnded:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  [self finishTouches:touches];
}

- (void)touchesCancelled:(NSSet<UITouch*>*)touches withEvent:(UIEvent*)event {
  [self finishTouches:touches];
}

#pragma mark Layout and refresh

- (void)layoutSubviews {
  [super layoutSubviews];
  UIView* canvas = [self canvas];
  NSString* orientation = canvas ? NeoTouchLayoutOrientationForSize(canvas.bounds.size) : _orientation;
  if (_presented && ![orientation isEqualToString:_orientation]) {
    // The surface turned: release the gesture and edit that orientation's layout.
    [self endChange];
    [_touches removeAllObjects];
    _mode = NeoTouchGestureNone;
    _orientation = orientation;
    [self applyDraft];
  } else if (_presented) {
    _elements = [_host touchLayoutElements] ?: @[];
    [self refreshOutlines];
  }
  [self layoutChrome];
}

- (void)layoutChrome {
  const CGRect bounds = self.bounds;
  const UIEdgeInsets safe = self.safeAreaInsets;
  const CGFloat width = bounds.size.width;
  const CGFloat maximumWidth = MAX(120, width - safe.left - safe.right - 16);
  CGSize toolbarSize = [_toolbarColumn systemLayoutSizeFittingSize:UILayoutFittingCompressedSize];
  toolbarSize.width = MIN(maximumWidth, toolbarSize.width);
  const CGFloat top = MAX(safe.top, 4) + 4;
  const CGFloat bottom = bounds.size.height - MAX(safe.bottom, 4) - 4;
  const CGFloat toolbarY = _toolbarAtBottom ? bottom - toolbarSize.height : top;
  _toolbar.frame = CGRectMake(floor((width - toolbarSize.width) * 0.5), toolbarY, toolbarSize.width, toolbarSize.height);
  _toolbarColumn.frame = _toolbar.contentView.bounds;

  const CGFloat inspectorWidth = MIN(380, maximumWidth);
  CGSize inspectorSize = [_inspector.contentView systemLayoutSizeFittingSize:CGSizeMake(inspectorWidth, 0)
                                               withHorizontalFittingPriority:UILayoutPriorityRequired
                                                     verticalFittingPriority:UILayoutPriorityFittingSizeLevel];
  const CGFloat inspectorY = _toolbarAtBottom ? CGRectGetMinY(_toolbar.frame) - 6 - inspectorSize.height
                                              : CGRectGetMaxY(_toolbar.frame) + 6;
  _inspector.frame = CGRectMake(floor((width - inspectorWidth) * 0.5), inspectorY, inspectorWidth, inspectorSize.height);

  const CGFloat panelWidth = MIN(420, maximumWidth);
  const CGFloat panelHeight = MIN(340, bounds.size.height - top - MAX(safe.bottom, 4) - 16);
  _elementsPanel.frame = CGRectMake(floor((width - panelWidth) * 0.5), floor((bounds.size.height - panelHeight) * 0.5),
                                    panelWidth, panelHeight);

  const CGFloat hintWidth = MIN(440, maximumWidth);
  CGSize hint = [_hintLabel sizeThatFits:CGSizeMake(hintWidth - 24, CGFLOAT_MAX)];
  _hintLabel.frame = CGRectMake(floor((width - hintWidth) * 0.5), floor(bounds.size.height * 0.5 - hint.height * 0.5 - 10),
                                hintWidth, hint.height + 20);
  CGSize endPreview = [_endPreviewButton sizeThatFits:CGSizeMake(maximumWidth, 44)];
  _endPreviewButton.frame = CGRectMake(floor((width - endPreview.width) * 0.5), top, endPreview.width, endPreview.height);
  UIView* canvas = [self canvas];
  if (canvas) {
    CGRect safeRect = [self convertRect:[NeoTouchLayoutApplier safeRectOfCanvas:canvas] fromView:canvas];
    _safeAreaLayer.frame = _outlineContainer.bounds;
    _safeAreaLayer.path = [UIBezierPath bezierPathWithRect:CGRectInset(safeRect, 0.5, 0.5)].CGPath;
  }
}

- (void)refreshChrome {
  [self refreshOutlines];
  [self refreshToolbar];
  [self refreshInspector];
  if (!_elementsPanel.hidden) [_elementsTable reloadData];
  [self setNeedsLayout];
}

- (void)refreshOutlines {
  NSMutableSet* seen = [NSMutableSet set];
  NeoTouchLayout* draft = [self draftLayout];
  for (NeoTouchElement* element in _elements) {
    [seen addObject:element.identifier];
    NeoTouchOutlineView* outline = _outlines[element.identifier];
    if (!outline) {
      outline = [[NeoTouchOutlineView alloc] initWithFrame:CGRectZero];
      outline.badge.text = [self text:@"hidden"];
      _outlines[element.identifier] = outline;
      [_outlineContainer addSubview:outline];
    }
    const CGRect frame = [self frameOfElement:element.identifier];
    outline.frame = CGRectIsNull(frame) ? CGRectZero : CGRectInset(frame, -3, -3);
    outline.selectedOutline = [element.identifier isEqualToString:_selectedIdentifier];
    outline.hiddenControl = [draft stateForIdentifier:element.identifier].hidden;
    outline.hidden = _previewing;
    [outline setNeedsLayout];
  }
  for (NSString* identifier in _outlines.allKeys) {
    if ([seen containsObject:identifier]) continue;
    [_outlines[identifier] removeFromSuperview];
    [_outlines removeObjectForKey:identifier];
  }
  _safeAreaLayer.hidden = _previewing;
}

- (NSString*)layoutName {
  NSDictionary* names = @{
    NeoTouchLayoutKeyGameCube: @"layoutGameCube", NeoTouchLayoutKeyWii: @"layoutWii",
    NeoTouchLayoutKeyWiiClassic: @"layoutWiiClassic", NeoTouchLayoutKeyPlayStation2: @"layoutPS2",
    NeoTouchLayoutKeyPlayStation3: @"layoutPS3",
  };
  NSString* key = names[_layoutKey];
  return key ? [self text:key] : _layoutKey;
}

- (void)refreshToolbar {
  const BOOL game = _scope == NeoTouchLayoutScopeGame;
  _scopeControl.hidden = _gameKey == nil;
  _scopeControl.selectedSegmentIndex = game ? 1 : 0;
  _useGeneralButton.hidden = !game;
  _useGeneralButton.enabled = game && ![_following containsObject:[self currentKey]];
  _undoButton.enabled = _undo.count > 0;
  NSMutableArray* parts = [NSMutableArray arrayWithObject:[self layoutName]];
  [parts addObject:[self text:[_orientation isEqualToString:NeoTouchLayoutOrientationPortrait] ? @"portrait" : @"landscape"]];
  if (game) {
    NSString* status = [_following containsObject:[self currentKey]] ? [self text:@"generalLayout"] : [self text:@"gameLayout"];
    [parts addObject:_title.length ? [NSString stringWithFormat:@"%@ (%@)", status, _title] : status];
  } else {
    [parts addObject:[self text:@"generalLayout"]];
  }
  NSString* caption = [parts componentsJoinedByString:@" · "];
  if (_controllerConnected) caption = [caption stringByAppendingFormat:@"\n%@", [self text:@"controllerNote"]];
  if (_errorText.length) caption = [caption stringByAppendingFormat:@"\n%@", _errorText];
  _caption.text = caption;
  _caption.textColor = _errorText.length ? UIColor.systemRedColor : [UIColor colorWithWhite:1 alpha:0.8];
  _toolbar.hidden = _previewing;
  _endPreviewButton.hidden = !_previewing;
}

- (NSString*)percentText:(double)value {
  return [_percent stringFromNumber:@(value)] ?: [NSString stringWithFormat:@"%.0f%%", value * 100.0];
}

- (void)refreshInspector {
  NSString* identifier = _selectedIdentifier;
  NeoTouchElement* element = identifier ? [self elementWithIdentifier:identifier] : nil;
  _inspector.hidden = element == nil || _previewing;
  if (!element) return;
  NeoTouchControlState* state = [[self draftLayout] stateForIdentifier:identifier];
  _nameLabel.text = element.name;
  _sizeSlider.value = (float)(NeoTouchClampScale(state.scale) * 100.0);
  _opacitySlider.value = (float)(NeoTouchClampOpacity(state.opacity) * 100.0);
  _sizeValue.text = [self percentText:NeoTouchClampScale(state.scale)];
  _opacityValue.text = [self percentText:NeoTouchClampOpacity(state.opacity)];
  _visibleSwitch.on = !state.hidden;
  _resetControlButton.enabled = !state.isDefault;
}

#pragma mark Elements list

- (NSInteger)tableView:(UITableView*)tableView numberOfRowsInSection:(NSInteger)section {
  return (NSInteger)_elements.count;
}

- (UITableViewCell*)tableView:(UITableView*)tableView cellForRowAtIndexPath:(NSIndexPath*)indexPath {
  UITableViewCell* cell = [[UITableViewCell alloc] initWithStyle:UITableViewCellStyleSubtitle reuseIdentifier:nil];
  cell.backgroundColor = UIColor.clearColor;
  NeoTouchElement* element = _elements[(NSUInteger)indexPath.row];
  NeoTouchControlState* state = [[self draftLayout] stateForIdentifier:element.identifier];
  cell.textLabel.text = element.name;
  cell.textLabel.textColor = UIColor.whiteColor;
  cell.detailTextLabel.text = state.hidden ? [self text:@"hidden"] : (state.isDefault ? nil : [self text:@"customized"]);
  cell.detailTextLabel.textColor = [UIColor colorWithWhite:1 alpha:0.65];
  UISwitch* toggle = [UISwitch new];
  toggle.on = !state.hidden;
  toggle.tag = indexPath.row;
  toggle.onTintColor = UIColor.systemYellowColor;
  toggle.accessibilityLabel = [NSString stringWithFormat:@"%@, %@", element.name, [self text:@"visible"]];
  [toggle addTarget:self action:@selector(elementToggleChanged:) forControlEvents:UIControlEventValueChanged];
  cell.accessoryView = toggle;
  return cell;
}

- (void)elementToggleChanged:(UISwitch*)toggle {
  if (toggle.tag < 0 || toggle.tag >= (NSInteger)_elements.count) return;
  [self setHidden:!toggle.isOn forElement:_elements[(NSUInteger)toggle.tag].identifier];
}

- (void)tableView:(UITableView*)tableView didSelectRowAtIndexPath:(NSIndexPath*)indexPath {
  [tableView deselectRowAtIndexPath:indexPath animated:YES];
  if (indexPath.row < 0 || indexPath.row >= (NSInteger)_elements.count) return;
  _elementsPanel.hidden = YES;
  [self selectElement:_elements[(NSUInteger)indexPath.row].identifier];
}

@end

#pragma mark - Registry

@implementation NeoTouchLayoutRegistry

+ (NSMutableDictionary<NSString*, NeoTouchLayoutPreviewFactory>*)factories {
  static NSMutableDictionary* factories;
  static dispatch_once_t once;
  dispatch_once(&once, ^{ factories = [NSMutableDictionary dictionary]; });
  return factories;
}

+ (void)registerPreviewFactory:(NeoTouchLayoutPreviewFactory)factory forLayoutKeys:(NSArray<NSString*>*)keys {
  if (!factory) return;
  @synchronized(self) {
    for (NSString* key in keys)
      if (NeoTouchLayoutKeyIsValid(key)) [self factories][key] = [factory copy];
  }
}

+ (NeoTouchLayoutPreviewFactory)previewFactoryForLayoutKey:(NSString*)key {
  @synchronized(self) {
    return key ? [self factories][key] : nil;
  }
}

@end

#pragma mark - Editor outside a game

@implementation NeoTouchLayoutEditorController {
  NSString* _locale;
  NeoTouchLayoutPreviewFactory _factory;
  UIView<NeoTouchLayoutEditorHost>* _preview;
  UILabel* _backdropTitle;
}

- (instancetype)initWithLayoutKey:(NSString*)layoutKey locale:(NSString*)locale {
  NeoTouchLayoutPreviewFactory factory = [NeoTouchLayoutRegistry previewFactoryForLayoutKey:layoutKey];
  if (!factory) return nil;
  self = [super initWithNibName:nil bundle:nil];
  if (self) {
    _layoutKey = [layoutKey copy];
    _locale = NeoTouchLayoutCanonicalLocale(locale);
    _factory = factory;
    self.modalPresentationStyle = UIModalPresentationFullScreen;
    self.modalTransitionStyle = UIModalTransitionStyleCrossDissolve;
  }
  return self;
}

- (void)loadView {
  UIView* root = [[UIView alloc] initWithFrame:UIScreen.mainScreen.bounds];
  root.backgroundColor = [UIColor colorWithRed:0.05 green:0.06 blue:0.08 alpha:1];
  root.accessibilityIdentifier = @"neo.touchLayout.previewRoot";
  self.view = root;
  _backdropTitle = [UILabel new];
  _backdropTitle.textColor = [UIColor colorWithWhite:1 alpha:0.12];
  _backdropTitle.font = [UIFont systemFontOfSize:34 weight:UIFontWeightHeavy];
  _backdropTitle.textAlignment = NSTextAlignmentCenter;
  _backdropTitle.frame = root.bounds;
  _backdropTitle.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
  NSDictionary* names = @{
    NeoTouchLayoutKeyGameCube: @"layoutGameCube", NeoTouchLayoutKeyWii: @"layoutWii",
    NeoTouchLayoutKeyWiiClassic: @"layoutWiiClassic", NeoTouchLayoutKeyPlayStation2: @"layoutPS2",
    NeoTouchLayoutKeyPlayStation3: @"layoutPS3",
  };
  _backdropTitle.text = names[_layoutKey] ? NeoTouchLayoutText(names[_layoutKey], _locale) : _layoutKey;
  [root addSubview:_backdropTitle];
  _preview = _factory(_layoutKey, _locale);
  if (_preview) {
    _preview.frame = root.bounds;
    _preview.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    // The engine's preview disables its own controls; the editor, added next
    // to the canvas, receives every touch.
    [root addSubview:_preview];
  }
}

- (void)viewDidLayoutSubviews {
  [super viewDidLayoutSubviews];
  if (_editor || !_preview || !self.view.window) return;
  NeoTouchLayoutEditor* editor = [[NeoTouchLayoutEditor alloc] initWithHost:_preview layoutKey:_layoutKey gameKey:nil
                                                                      title:nil locale:_locale
                                                                      store:NeoTouchLayoutStore.sharedStore];
  editor.controllerConnected = [NeoTouchControllerMonitor compatibleControllerConnected];
  __weak NeoTouchLayoutEditorController* weakSelf = self;
  editor.finished = ^(BOOL saved) {
    NeoTouchLayoutEditorController* controller = weakSelf;
    if (!controller) return;
    void (^finished)(BOOL) = controller.finished;
    controller.finished = nil;
    [controller.presentingViewController dismissViewControllerAnimated:YES completion:^{
      if (finished) finished(saved);
    }];
  };
  _editor = editor;
  [editor presentOverCanvas];
}

- (BOOL)prefersStatusBarHidden { return YES; }
- (BOOL)prefersHomeIndicatorAutoHidden { return YES; }

- (UIInterfaceOrientationMask)supportedInterfaceOrientations {
  [self loadViewIfNeeded];
  if ([_preview respondsToSelector:@selector(touchLayoutSupportedInterfaceOrientations)])
    return [_preview touchLayoutSupportedInterfaceOrientations];
  return UIInterfaceOrientationMaskAllButUpsideDown;
}

@end
