#import "LibretroGameViewController.h"

#import <external_display/NeoExternalDisplayLabels.h>

#import "LibretroChromeLayout.h"
#import "LibretroInputState.h"
#import "LibretroRenderSurface.h"
#import "LibretroSkinRenderer.h"
#import "LibretroTouchDiagnosticsView.h"
#import "LibretroTouchOverlay.h"

@interface LibretroMetalView : UIView
@end

@implementation LibretroMetalView
+ (Class)layerClass {
  return CAMetalLayer.class;
}
@end

static const CGFloat kEditBarPadding = 10;
static const CGFloat kEditButtonHeight = 36;

/// Logical input of a skin item that opens the session menu (LibretroInputMap).
static NSString *const kMenuInput = @"menu";

/// The portable layout rectangles (LibretroGeometry) and CoreGraphics ones
/// of the render surface rule (LibretroRenderSurface).
static CGRect LibretroCGRectFromRect(LibretroRect rect) {
  return CGRectMake(rect.x, rect.y, rect.w, rect.h);
}

static LibretroRect LibretroRectFromCGRect(CGRect rect) {
  return LibretroRectMake(rect.origin.x, rect.origin.y, rect.size.width, rect.size.height);
}

@implementation LibretroGameViewController {
  LibretroInputState *_input;
  NSString *_cacheDirectory;
  LibretroMetalView *_metalView;
  UIButton *_menuButton;
  UILabel *_statusLabel;
  UIActivityIndicatorView *_spinner;
  LibretroTouchDiagnosticsView *_diagnosticsView;
  CADisplayLink *_displayLink;
  NSUInteger _statusGeneration;

  // Skin layout (main thread).
  LibretroSkinRepresentation *_representation;
  LibretroSkinLayoutResult *_layout;
  BOOL _hasMenuItem;
  BOOL _controlsHidden;
  BOOL _skinLayoutDirty;
  BOOL _inLayoutPass;
  BOOL _relayoutScheduled;
  CGSize _laidOutSize;
  UIEdgeInsets _laidOutInsets;
  NSArray<NSValue *> *_lastNormalizedMappings;
  CGSize _lastMappingSize;

  // Surface of the Metal view while it is in the external window (points at
  // the TV's scale, NeoExternalRenderHost); zero on the iPhone. The
  // placement maps the game areas of the iPhone layout into that surface
  // (identity on the phone).
  CGSize _externalSurface;
  CGFloat _externalScale;
  LibretroRenderSurfacePlacement _externalPlacement;

  // "Commandes › Modifier la disposition".
  BOOL _editing;
  NSMutableDictionary<NSString *, NSDictionary *> *_editOverrides;
  LibretroControlsOverridesProvider _editStartingOverrides;
  NSString *_editSelectedItem;
  void (^_editFinished)(void);
  void (^_editReset)(void);
  UIView *_editBar;
  UILabel *_editHint;
  UIButton *_editDoneButton;
  UIButton *_editResetButton;
}

- (instancetype)initWithInput:(LibretroInputState *)input cacheDirectory:(NSString *)cacheDirectory {
  self = [super initWithNibName:nil bundle:nil];
  if (self) {
    _input = input;
    _cacheDirectory = [cacheDirectory copy];
    _touchControlsEnabled = YES;
    _controlsOpacity = 0.75;
    // Replaced by the translated label before the view loads (LibretroSession).
    _menuAccessibilityLabel = @"";
    // Replaced by the session's language before the view appears (LibretroSession).
    _uiLocale = @"en";
    _allowedOrientations = UIInterfaceOrientationMaskAllButUpsideDown;
    _currentOrientation = LibretroSkinOrientationLandscape;
    _skinLayoutDirty = YES;
    _externalPlacement = LibretroRenderSurfacePlacementIdentity();
    self.modalPresentationStyle = UIModalPresentationFullScreen;
    self.modalTransitionStyle = UIModalTransitionStyleCrossDissolve;
  }
  return self;
}

- (void)dealloc {
  [NSNotificationCenter.defaultCenter removeObserver:self];
  [_displayLink invalidate];
}

- (CAMetalLayer *)metalLayer {
  [self loadViewIfNeeded];
  return (CAMetalLayer *)_metalView.layer;
}

#pragma mark - View

- (void)loadView {
  UIView *root = [[UIView alloc] initWithFrame:UIScreen.mainScreen.bounds];
  root.backgroundColor = UIColor.blackColor;
  self.view = root;
  UIViewAutoresizing flexible = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;

  // Stack: picture, skin, touches, menu button, edit toolbar, status, spinner.
  _metalView = [[LibretroMetalView alloc] initWithFrame:root.bounds];
  _metalView.autoresizingMask = flexible;
  _metalView.contentScaleFactor = UIScreen.mainScreen.nativeScale;
  _metalView.backgroundColor = UIColor.blackColor;
  _metalView.userInteractionEnabled = NO;
  [root addSubview:_metalView];

  _skinRenderer = [[LibretroSkinRenderer alloc] initWithCacheDirectory:_cacheDirectory ?: NSTemporaryDirectory()];
  _skinRenderer.frame = root.bounds;
  _skinRenderer.autoresizingMask = flexible;
  _skinRenderer.userInteractionEnabled = NO;
  [root addSubview:_skinRenderer];

  _overlay = [[LibretroTouchOverlay alloc] initWithInput:_input];
  _overlay.frame = root.bounds;
  _overlay.autoresizingMask = flexible;
  __weak LibretroSkinRenderer *renderer = _skinRenderer;
  _overlay.pressedItemsChanged = ^(NSSet<NSString *> *itemIdentifiers) {
    [renderer setPressedItems:itemIdentifiers];
  };
  // The knob of a held thumbstick follows the finger.
  _overlay.stickVectorsChanged = ^(NSDictionary<NSString *, NSValue *> *vectors) {
    [renderer setStickVectors:vectors];
  };
  [root addSubview:_overlay];

  _menuButton = [UIButton buttonWithType:UIButtonTypeSystem];
  [_menuButton setImage:[UIImage systemImageNamed:@"line.3.horizontal"] forState:UIControlStateNormal];
  _menuButton.tintColor = [UIColor colorWithWhite:1.0 alpha:0.85];
  _menuButton.backgroundColor = [UIColor colorWithWhite:0.0 alpha:0.35];
  _menuButton.layer.cornerRadius = 20;
  _menuButton.accessibilityIdentifier = @"libretro-game-menu";
  _menuButton.accessibilityLabel = _menuAccessibilityLabel;
  [_menuButton addTarget:self action:@selector(menuPressed) forControlEvents:UIControlEventTouchUpInside];
  [root addSubview:_menuButton];

  _statusLabel = [[UILabel alloc] initWithFrame:CGRectZero];
  _statusLabel.textColor = UIColor.whiteColor;
  _statusLabel.backgroundColor = [UIColor colorWithWhite:0.0 alpha:0.65];
  _statusLabel.textAlignment = NSTextAlignmentCenter;
  _statusLabel.numberOfLines = 2;
  _statusLabel.font = [UIFont systemFontOfSize:14 weight:UIFontWeightMedium];
  _statusLabel.layer.cornerRadius = 10;
  _statusLabel.layer.masksToBounds = YES;
  _statusLabel.alpha = 0;
  _statusLabel.userInteractionEnabled = NO;
  [root addSubview:_statusLabel];

  _spinner = [[UIActivityIndicatorView alloc] initWithActivityIndicatorStyle:UIActivityIndicatorViewStyleLarge];
  _spinner.color = UIColor.whiteColor;
  _spinner.hidesWhenStopped = YES;
  _spinner.userInteractionEnabled = NO;
  [root addSubview:_spinner];
}

- (void)viewDidLoad {
  [super viewDidLoad];
  [self applyTouchDiagnostics];
  NSNotificationCenter *center = NSNotificationCenter.defaultCenter;
  [center addObserver:self
             selector:@selector(applicationWillResignActive)
                 name:UIApplicationWillResignActiveNotification
               object:nil];
  [center addObserver:self
             selector:@selector(applicationDidBecomeActive)
                 name:UIApplicationDidBecomeActiveNotification
               object:nil];
}

- (void)setMenuAccessibilityLabel:(NSString *)menuAccessibilityLabel {
  _menuAccessibilityLabel = [menuAccessibilityLabel copy];
  _menuButton.accessibilityLabel = _menuAccessibilityLabel;
}

- (void)applicationWillResignActive {
  [_overlay releaseAllTouches];
  if (self.activeHandler != nil) self.activeHandler(NO);
}

- (void)applicationDidBecomeActive {
  if (self.activeHandler != nil) self.activeHandler(YES);
}

- (void)viewDidLayoutSubviews {
  [super viewDidLayoutSubviews];
  CGRect bounds = self.view.bounds;
  // On the TV the Metal view belongs to the external window and keeps the
  // surface the coordinator gave it; the coordinator sizes it again on its
  // return to the iPhone.
  if (![self onExternalDisplay]) _metalView.frame = bounds;
  _skinRenderer.frame = bounds;
  _overlay.frame = bounds;
  _diagnosticsView.frame = bounds;
  [self performSkinLayoutIfNeeded];
  [self layoutChrome];
}

- (void)viewSafeAreaInsetsDidChange {
  [super viewSafeAreaInsetsDidChange];
  // The display type (edgeToEdge) and the default skins depend on the safe
  // area, known only once the view is in its window.
  _skinLayoutDirty = YES;
  [self.view setNeedsLayout];
}

- (void)viewWillTransitionToSize:(CGSize)size
       withTransitionCoordinator:(id<UIViewControllerTransitionCoordinator>)coordinator {
  [super viewWillTransitionToSize:size withTransitionCoordinator:coordinator];
  [_overlay releaseAllTouches];
  _skinLayoutDirty = YES;
  __weak LibretroGameViewController *weakSelf = self;
  [coordinator animateAlongsideTransition:nil
                               completion:^(__unused id<UIViewControllerTransitionCoordinatorContext> context) {
                                 [weakSelf setNeedsSkinLayout];
                               }];
}

- (void)viewDidAppear:(BOOL)animated {
  [super viewDidAppear:animated];
  if (_displayLink == nil) {
    _displayLink = [CADisplayLink displayLinkWithTarget:self selector:@selector(tick)];
    [_displayLink addToRunLoop:NSRunLoop.mainRunLoop forMode:NSRunLoopCommonModes];
  }
  // A phone already held in portrait rotates now (LibretroOrientation).
  [self setNeedsUpdateOfSupportedInterfaceOrientations];
  UIViewController *root = self.view.window.rootViewController;
  if (root != nil && root != self) [root setNeedsUpdateOfSupportedInterfaceOrientations];
  [self setNeedsSkinLayout];
}

#pragma mark - Skin layout

- (void)setNeedsSkinLayout {
  _skinLayoutDirty = YES;
  if (!self.isViewLoaded) return;
  if (_inLayoutPass) {
    [self.view setNeedsLayout];
    return;
  }
  [self performSkinLayoutIfNeeded];
  [self layoutChrome];
}

/// Coalesces relayouts requested while the overlay handles a touch (edit
/// mode), so the overlay never receives a new layout inside its own event.
- (void)scheduleSkinLayout {
  _skinLayoutDirty = YES;
  if (_relayoutScheduled) return;
  _relayoutScheduled = YES;
  __weak LibretroGameViewController *weakSelf = self;
  dispatch_async(dispatch_get_main_queue(), ^{
    LibretroGameViewController *controller = weakSelf;
    if (controller == nil) return;
    controller->_relayoutScheduled = NO;
    [controller setNeedsSkinLayout];
  });
}

- (LibretroSize)layoutViewSize {
  CGSize size = self.view.bounds.size;
  return (LibretroSize){size.width, size.height};
}

- (LibretroInsets)layoutSafeInsets {
  UIEdgeInsets insets = self.view.safeAreaInsets;
  return (LibretroInsets){insets.top, insets.left, insets.bottom, insets.right};
}

- (CGFloat)layoutScale {
  CGFloat scale = self.view.window.screen.nativeScale;
  if (scale <= 0) scale = _metalView.contentScaleFactor;
  return scale > 0 ? scale : 1;
}

/// Runs the layout when the size, the safe area or a setting changed:
/// orientation from the bounds (iPad and resizable windows included),
/// representation from the session, LibretroSkinLayout with the user's
/// overrides, then the session (presenter screens, overlay remaps), then
/// the skin renderer. The skin and the overlay always use the iPhone
/// bounds; the drawable follows the external surface while the Metal view
/// is on the TV (LibretroRenderSurface).
- (void)performSkinLayoutIfNeeded {
  if (!self.isViewLoaded || self.view.window == nil || _inLayoutPass) return;
  CGRect bounds = self.view.bounds;
  if (bounds.size.width < 1 || bounds.size.height < 1) return;
  UIEdgeInsets insets = self.view.safeAreaInsets;
  if (!_skinLayoutDirty && CGSizeEqualToSize(bounds.size, _laidOutSize) &&
      UIEdgeInsetsEqualToEdgeInsets(insets, _laidOutInsets)) {
    return;
  }
  _skinLayoutDirty = NO;
  _laidOutSize = bounds.size;
  _laidOutInsets = insets;
  _inLayoutPass = YES;

  LibretroRenderSurface surface =
      LibretroRenderSurfaceResolve(bounds.size, [self layoutScale], _externalSurface, _externalScale);
  if (_metalView.contentScaleFactor != surface.scale) _metalView.contentScaleFactor = surface.scale;
  _currentOrientation =
      bounds.size.width > bounds.size.height ? LibretroSkinOrientationLandscape : LibretroSkinOrientationPortrait;
  BOOL iPad = UIDevice.currentDevice.userInterfaceIdiom == UIUserInterfaceIdiomPad;
  LibretroSize viewSize = [self layoutViewSize];
  LibretroInsets safeInsets = [self layoutSafeInsets];

  id<LibretroGameViewLayoutSource> source = self.layoutSource;
  LibretroSkinRepresentation *representation = nil;
  LibretroSkinLayoutResult *layout = nil;
  if (source != nil) {
    representation = [source representationForOrientation:_currentOrientation
                                                  viewSize:viewSize
                                                safeInsets:safeInsets
                                                      iPad:iPad];
    NSDictionary<NSString *, NSDictionary *> *overrides =
        _editing ? [_editOverrides copy] : [source layoutOverridesForRepresentation:representation];
    layout = [LibretroSkinLayout layoutRepresentation:representation
                                             viewSize:viewSize
                                           safeInsets:safeInsets
                                            overrides:overrides];
  }
  _representation = representation;
  _layout = layout;
  BOOL hasMenuItem = NO;
  for (LibretroSkinItem *item in representation.items) {
    if ([item.inputs containsObject:kMenuInput]) {
      hasMenuItem = YES;
      break;
    }
  }
  _hasMenuItem = hasMenuItem;

  // The picture is drawn into the surface: on the phone (the surface is the
  // view's bounds) the game areas where the skin laid them out; on the TV
  // the same areas placed in the external surface, scaled uniformly and
  // centred so the picture fills it, the black around them (the skin's and
  // the controls' room on the phone) left out. The session normalizes the
  // screens by the surface's points (LibretroGameViewLayoutSource); the
  // skin, the overlay and the chrome keep the iPhone layout.
  CGSize drawableSize = LibretroRenderSurfaceDrawableSize(surface);
  NSArray<LibretroLaidOutScreen *> *pictureScreens = layout.screens ?: @[];
  _externalPlacement = LibretroRenderSurfacePlacementIdentity();
  if (surface.external && layout != nil) {
    _externalPlacement = LibretroRenderSurfacePlacementMake([self unionOfScreens:layout.screens], surface.points);
    pictureScreens = [self screens:layout.screens placedBy:_externalPlacement];
  }
  // The touch screens are converted again with this placement (tick).
  _lastMappingSize = CGSizeZero;
  if (representation != nil && layout != nil) {
    [source gameViewDidLayout:layout
               representation:representation
                      screens:pictureScreens
                 drawableSize:drawableSize
                       points:surface.points];
  }
  if (self.layoutHandler != nil) self.layoutHandler(drawableSize);
  _inLayoutPass = NO;
  // After the session gave the overlay its layout and remaps.
  if (_diagnosticsView != nil) [_diagnosticsView showLayout:_layout deadItems:[_overlay deadItemIdentifiers]];

  _controlsHidden = [self controlsShouldHide];
  _overlay.controlsDisabled = _controlsHidden;
  [self showSkin];
  if (_editing) [_skinRenderer setEditing:YES selectedItem:_editSelectedItem];
}

- (BOOL)controlsShouldHide {
  if (_editing) return NO;
  return !self.touchControlsEnabled || _input.hasPhysicalController;
}

/// Bounding box of the game areas of the iPhone layout (CGRectZero without
/// any), in iPhone points.
- (CGRect)unionOfScreens:(NSArray<LibretroLaidOutScreen *> *)screens {
  CGRect areas = CGRectNull;
  for (LibretroLaidOutScreen *screen in screens) {
    areas = CGRectUnion(areas, LibretroCGRectFromRect(screen.container));
  }
  return CGRectIsNull(areas) ? CGRectZero : areas;
}

/// The same screens (source, role, touch screen) with their containers
/// placed in the external surface.
- (NSArray<LibretroLaidOutScreen *> *)screens:(NSArray<LibretroLaidOutScreen *> *)screens
                                     placedBy:(LibretroRenderSurfacePlacement)placement {
  NSMutableArray<LibretroLaidOutScreen *> *placed = [NSMutableArray arrayWithCapacity:screens.count];
  for (LibretroLaidOutScreen *screen in screens) {
    LibretroLaidOutScreen *entry = [LibretroLaidOutScreen new];
    entry.container =
        LibretroRectFromCGRect(LibretroRenderSurfacePlace(placement, LibretroCGRectFromRect(screen.container)));
    entry.source = screen.source;
    entry.role = screen.role;
    entry.touchScreen = screen.touchScreen;
    [placed addObject:entry];
  }
  return placed;
}

- (void)showSkin {
  [_skinRenderer showRepresentation:_representation
                             layout:_layout
                            opacity:self.controlsOpacity
                     controlsHidden:_controlsHidden];
}

/// Controller connected or disconnected, touch controls toggled: buttons
/// are hidden and ignored, the touch screen keeps working.
- (void)updateControlsVisibility {
  BOOL hidden = [self controlsShouldHide];
  if (_overlay.controlsDisabled != hidden) _overlay.controlsDisabled = hidden;
  if (hidden == _controlsHidden) return;
  _controlsHidden = hidden;
  // The layout source may choose another skin for this orientation when a
  // controller comes or goes (a skin not playable by touch stays in use
  // with a controller): lay out again, which also redraws the skin.
  if (self.isViewLoaded && self.view.window != nil && !_inLayoutPass) {
    [self setNeedsSkinLayout];
    return;
  }
  if (_representation != nil) [self showSkin];
  [self layoutChrome];
}

- (void)setTouchControlsEnabled:(BOOL)touchControlsEnabled {
  _touchControlsEnabled = touchControlsEnabled;
  if (self.isViewLoaded) [self updateControlsVisibility];
}

- (void)setControlsOpacity:(CGFloat)controlsOpacity {
  if (fabs(controlsOpacity - _controlsOpacity) < 0.001) return;
  _controlsOpacity = controlsOpacity;
  // Inside a layout pass the renderer is updated right after the session.
  if (self.isViewLoaded && !_inLayoutPass && _representation != nil) [self showSkin];
}

- (void)setAllowedOrientations:(UIInterfaceOrientationMask)allowedOrientations {
  _allowedOrientations = allowedOrientations;
  if (self.isViewLoaded) [self setNeedsUpdateOfSupportedInterfaceOrientations];
}

/// Menu button: hidden when the skin has its own "menu" item (shown
/// again when the skin's controls are hidden). Otherwise at the top centre
/// in landscape, at the top-right corner of the safe area in portrait (the
/// default skins' game area), unless that place covers a touch screen or a
/// shown control: the button sits above the touch overlay and takes every
/// touch in its frame, so LibretroChromeLayout moves it to the closest free
/// place (DS / 3DS bottom screen swapped to the top, bottom screen only...).
- (void)layoutChrome {
  if (!self.isViewLoaded) return;
  CGRect bounds = self.view.bounds;
  BOOL hidden = _editing || (_hasMenuItem && !_controlsHidden);
  _menuButton.hidden = hidden;
  if (!hidden) {
    LibretroRect frame = [LibretroChromeLayout menuButtonFrameForLayout:_layout
                                                               viewSize:[self layoutViewSize]
                                                             safeInsets:[self layoutSafeInsets]
                                                        controlsVisible:!_controlsHidden];
    _menuButton.frame = CGRectMake(frame.x, frame.y, frame.w, frame.h);
  }
  _spinner.center = CGPointMake(CGRectGetMidX(bounds), CGRectGetMidY(bounds));
  if (_editBar != nil && !_editBar.hidden) [self layoutEditBar];
}

#pragma mark - Touch diagnostics

- (void)setTouchDiagnosticsEnabled:(BOOL)touchDiagnosticsEnabled {
  _touchDiagnosticsEnabled = touchDiagnosticsEnabled;
  if (self.isViewLoaded) [self applyTouchDiagnostics];
}

- (void)applyTouchDiagnostics {
  BOOL enabled = self.touchDiagnosticsEnabled;
  _overlay.recordsContacts = enabled;
  if (!enabled) {
    [_diagnosticsView removeFromSuperview];
    _diagnosticsView = nil;
    _overlay.resolutionChanged = nil;
    _overlay.touchDelivered = nil;
    return;
  }
  if (_diagnosticsView == nil) {
    _diagnosticsView = [[LibretroTouchDiagnosticsView alloc] initWithFrame:self.view.bounds];
    _diagnosticsView.autoresizingMask = UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    [self.view insertSubview:_diagnosticsView aboveSubview:_overlay];
  }
  __weak LibretroTouchDiagnosticsView *view = _diagnosticsView;
  _overlay.resolutionChanged = ^(LibretroTouchResolution *resolution) {
    [view showResolution:resolution];
  };
  _overlay.touchDelivered = ^(__unused CGPoint point, NSTimeInterval delay) {
    [view noteDeliveryDelay:delay];
  };
  [_diagnosticsView showLayout:_layout deadItems:[_overlay deadItemIdentifiers]];
}

#pragma mark - Input polling

- (void)stopInputPolling {
  [_displayLink invalidate];
  _displayLink = nil;
  [_overlay releaseAllTouches];
}

- (void)tick {
  BOOL menuRequested = [_input pollControllers];
  if (_diagnosticsView != nil) {
    uint64_t frame = 0;
    LibretroInputSnapshot delivered = [_input lastDelivered:&frame];
    [_diagnosticsView showDelivered:delivered frame:frame];
  }
  [self updateControlsVisibility];
  NSArray<NSValue *> * (^provider)(void) = self.screenMappingsProvider;
  if (provider != nil) [self refreshTouchScreenMappings:provider()];
  if (menuRequested && !_editing && self.presentedViewController == nil) [self menuPressed];
}

/// Touch-screen mappings of the last presented frame, normalized to the
/// drawable, converted to overlay points. On the phone the drawable is the
/// whole view; on the TV it is the external surface, where the picture was
/// placed by the layout's placement: the same placement brings each touch
/// screen back to the iPhone layout, where the overlay maps the touches.
- (void)refreshTouchScreenMappings:(NSArray<NSValue *> *)normalized {
  CGSize size = _overlay.bounds.size;
  if (CGSizeEqualToSize(size, _lastMappingSize) && [normalized isEqualToArray:_lastNormalizedMappings ?: @[]]) {
    return;
  }
  _lastMappingSize = size;
  _lastNormalizedMappings = [normalized copy];
  const BOOL external = [self onExternalDisplay];
  const CGSize picture = external ? _externalSurface : size;
  NSMutableArray<NSValue *> *converted = [NSMutableArray arrayWithCapacity:normalized.count];
  for (NSValue *value in normalized) {
    LibretroScreenMapping mapping;
    [value getValue:&mapping size:sizeof(mapping)];
    CGRect output = CGRectMake(mapping.output.x * picture.width, mapping.output.y * picture.height,
                               mapping.output.w * picture.width, mapping.output.h * picture.height);
    if (external) output = LibretroRenderSurfaceUnplace(_externalPlacement, output);
    mapping.output = LibretroRectFromCGRect(output);
    [converted addObject:[NSValue valueWithBytes:&mapping objCType:@encode(LibretroScreenMapping)]];
  }
  _overlay.touchScreenMappings = converted;
}

- (void)menuPressed {
  if (self.presentedViewController != nil || _editing) return;
  [_overlay releaseAllTouches];
  if (self.menuHandler != nil) self.menuHandler();
}

#pragma mark - Controls editing

- (void)beginEditingControlsWithDoneTitle:(NSString *)doneTitle
                               resetTitle:(NSString *)resetTitle
                                     hint:(NSString *)hint
                                 finished:(void (^)(void))finished
                                    reset:(void (^)(void))reset {
  [self beginEditingControlsWithDoneTitle:doneTitle
                               resetTitle:resetTitle
                                     hint:hint
                        startingOverrides:nil
                                 finished:finished
                                    reset:reset];
}

- (void)beginEditingControlsWithDoneTitle:(NSString *)doneTitle
                               resetTitle:(NSString *)resetTitle
                                     hint:(NSString *)hint
                        startingOverrides:(LibretroControlsOverridesProvider)startingOverrides
                                 finished:(void (^)(void))finished
                                    reset:(void (^)(void))reset {
  [self loadViewIfNeeded];
  [_overlay releaseAllTouches];
  _editing = YES;
  _editFinished = [finished copy];
  _editReset = [reset copy];
  _editStartingOverrides = [startingOverrides copy];
  [self ensureEditBar];
  [_editDoneButton setTitle:doneTitle forState:UIControlStateNormal];
  [_editResetButton setTitle:resetTitle forState:UIControlStateNormal];
  _editHint.text = hint;
  _editBar.hidden = NO;

  _editOverrides = [self editingStartOverrides];
  __weak LibretroGameViewController *weakSelf = self;
  _overlay.editOverrides = _editOverrides;
  _overlay.editChanged = ^(NSString *itemIdentifier, NSDictionary<NSString *, NSNumber *> *override) {
    [weakSelf editedItem:itemIdentifier override:override];
  };
  _overlay.editSelectionChanged = ^(NSString *itemIdentifier) {
    [weakSelf selectEditedItem:itemIdentifier];
  };
  _overlay.controlsDisabled = NO;
  _overlay.editing = YES;
  _editSelectedItem = nil;
  [_skinRenderer setEditing:YES selectedItem:nil];
  // The overrides belong to one orientation: it stays fixed while editing.
  [self setNeedsUpdateOfSupportedInterfaceOrientations];
  [self setNeedsSkinLayout];
  UIAccessibilityPostNotification(UIAccessibilityScreenChangedNotification, _editBar);
}

/// What the editor starts from, and comes back to after Reset: the
/// session's overrides for the scope being edited, else those in effect for
/// the representation on screen (game, else console).
- (NSMutableDictionary<NSString *, NSDictionary *> *)editingStartOverrides {
  NSMutableDictionary<NSString *, NSDictionary *> *overrides = [NSMutableDictionary dictionary];
  LibretroControlsOverridesProvider provider = _editStartingOverrides;
  NSDictionary *stored = nil;
  if (provider != nil) {
    stored = provider();
  } else if (_representation != nil) {
    stored = [self.layoutSource layoutOverridesForRepresentation:_representation];
  }
  for (id key in stored) {
    id value = stored[key];
    if ([key isKindOfClass:NSString.class] && [value isKindOfClass:NSDictionary.class]) overrides[key] = value;
  }
  return overrides;
}

- (void)selectEditedItem:(NSString *)itemIdentifier {
  if (!_editing) return;
  _editSelectedItem = [itemIdentifier copy];
  [_skinRenderer setEditing:YES selectedItem:_editSelectedItem];
}

- (void)editedItem:(NSString *)itemIdentifier override:(NSDictionary<NSString *, NSNumber *> *)override {
  if (!_editing || itemIdentifier.length == 0 || override == nil) return;
  NSDictionary<NSString *, NSNumber *> *value = override;
  LibretroSkinItem *item = nil;
  for (LibretroSkinItem *candidate in _representation.items) {
    if ([candidate.identifier isEqualToString:itemIdentifier]) {
      item = candidate;
      break;
    }
  }
  if (item == nil || !item.movable) return;
  // Inside the view and never over the DS / 3DS touch screen; a proposal
  // that cannot be placed leaves the item at its last valid place.
  NSDictionary *previous = _editOverrides[itemIdentifier];
  BOOL fitted = NO;
  value = [LibretroSkinLayout clampOverride:value
                                   previous:[previous isKindOfClass:NSDictionary.class] ? previous : nil
                                    forItem:item
                             representation:_representation
                                   viewSize:[self layoutViewSize]
                                 safeInsets:[self layoutSafeInsets]
                                     fitted:&fitted];
  if (!fitted) {
    _overlay.editOverrides = _editOverrides;
    return;
  }
  _editOverrides[itemIdentifier] = value;
  _overlay.editOverrides = _editOverrides;
  [self scheduleSkinLayout];
}

- (void)ensureEditBar {
  if (_editBar != nil) return;
  _editBar = [[UIView alloc] initWithFrame:CGRectZero];
  _editBar.backgroundColor = [UIColor colorWithWhite:0.0 alpha:0.78];
  _editBar.layer.cornerRadius = 12;
  _editBar.accessibilityIdentifier = @"libretro-controls-editing";

  _editHint = [[UILabel alloc] initWithFrame:CGRectZero];
  _editHint.textColor = [UIColor colorWithWhite:1.0 alpha:0.9];
  _editHint.font = [UIFont systemFontOfSize:13 weight:UIFontWeightRegular];
  _editHint.textAlignment = NSTextAlignmentCenter;
  _editHint.numberOfLines = 0;
  [_editBar addSubview:_editHint];

  _editResetButton = [UIButton buttonWithType:UIButtonTypeSystem];
  _editResetButton.tintColor = [UIColor colorWithWhite:1.0 alpha:0.85];
  _editResetButton.titleLabel.font = [UIFont systemFontOfSize:15 weight:UIFontWeightRegular];
  _editResetButton.titleLabel.adjustsFontSizeToFitWidth = YES;
  _editResetButton.titleLabel.minimumScaleFactor = 0.6;
  _editResetButton.contentHorizontalAlignment = UIControlContentHorizontalAlignmentLeading;
  _editResetButton.accessibilityIdentifier = @"libretro-controls-reset";
  [_editResetButton addTarget:self action:@selector(editResetPressed) forControlEvents:UIControlEventTouchUpInside];
  [_editBar addSubview:_editResetButton];

  _editDoneButton = [UIButton buttonWithType:UIButtonTypeSystem];
  _editDoneButton.tintColor = UIColor.whiteColor;
  _editDoneButton.titleLabel.font = [UIFont systemFontOfSize:16 weight:UIFontWeightSemibold];
  _editDoneButton.titleLabel.adjustsFontSizeToFitWidth = YES;
  _editDoneButton.titleLabel.minimumScaleFactor = 0.6;
  _editDoneButton.contentHorizontalAlignment = UIControlContentHorizontalAlignmentTrailing;
  _editDoneButton.accessibilityIdentifier = @"libretro-controls-done";
  [_editDoneButton addTarget:self action:@selector(editDonePressed) forControlEvents:UIControlEventTouchUpInside];
  [_editBar addSubview:_editDoneButton];

  [self.view insertSubview:_editBar belowSubview:_statusLabel];
}

/// Toolbar at the top of the safe area, narrower in landscape so the
/// shoulder buttons in the top corners stay reachable.
- (void)layoutEditBar {
  CGRect bounds = self.view.bounds;
  UIEdgeInsets insets = self.view.safeAreaInsets;
  CGFloat available = bounds.size.width - insets.left - insets.right;
  BOOL landscape = bounds.size.width > bounds.size.height;
  CGFloat width = MIN(560, landscape ? available - 240 : available - 24);
  width = MAX(MIN(260, available - 16), width);
  CGFloat inner = width - 2 * kEditBarPadding;
  CGSize hint = [_editHint sizeThatFits:CGSizeMake(inner, CGFLOAT_MAX)];
  CGFloat height = kEditBarPadding + kEditButtonHeight + 4 + ceil(hint.height) + kEditBarPadding;
  CGFloat x = insets.left + (available - width) / 2;
  _editBar.frame = CGRectMake(x, insets.top + 6, width, height);
  CGFloat half = (inner - 8) / 2;
  _editResetButton.frame = CGRectMake(kEditBarPadding, kEditBarPadding, half, kEditButtonHeight);
  _editDoneButton.frame = CGRectMake(kEditBarPadding + half + 8, kEditBarPadding, half, kEditButtonHeight);
  _editHint.frame = CGRectMake(kEditBarPadding, kEditBarPadding + kEditButtonHeight + 4, inner, ceil(hint.height));
}

- (void)editDonePressed {
  if (!_editing) return;
  // The session reads overlay.editOverrides to save them before they are cleared.
  void (^finished)(void) = _editFinished;
  if (finished != nil) finished();
  [self endEditingControls];
}

- (void)editResetPressed {
  if (!_editing) return;
  void (^reset)(void) = _editReset;
  if (reset != nil) reset();
  // What is stored now for the scope being edited (the console's layout
  // after a game reset, nothing after a console reset).
  _editOverrides = [self editingStartOverrides];
  _overlay.editOverrides = _editOverrides;
  // No pinch may resize an item that is no longer shown as selected.
  [_overlay clearEditSelection];
  _editSelectedItem = nil;
  [_skinRenderer setEditing:YES selectedItem:nil];
  [self setNeedsSkinLayout];
}

- (void)endEditingControls {
  _editing = NO;
  _editFinished = nil;
  _editReset = nil;
  _editStartingOverrides = nil;
  [_overlay clearEditSelection];
  _overlay.editing = NO;
  _overlay.editChanged = nil;
  _overlay.editSelectionChanged = nil;
  _overlay.editOverrides = nil;
  _editOverrides = nil;
  _editSelectedItem = nil;
  [_skinRenderer setEditing:NO selectedItem:nil];
  _editBar.hidden = YES;
  [self setNeedsUpdateOfSupportedInterfaceOrientations];
  [self setNeedsSkinLayout];
}

#pragma mark - NeoExternalRenderHost (main thread, coordinator)

- (UIView *)renderView {
  [self loadViewIfNeeded];
  return _metalView;
}

- (UIView *)placeholderView {
  [self loadViewIfNeeded];
  return self.view;
}

- (BOOL)fixedDrawable {
  // The surface follows the TV: the coordinator sizes the Metal view to the
  // TV's surface and the drawable is rebuilt from it, so the core's picture
  // is rendered at the TV's resolution instead of being scaled up.
  return NO;
}

- (BOOL)onExternalDisplay {
  return LibretroRenderSurfaceUsable(_externalSurface, _externalScale);
}

- (void)externalSurfaceDidChange:(CGSize)pointSize scale:(CGFloat)scale {
  // CGSizeZero at scale 0: the view is back at index 0 of this view with its
  // iPhone frame and scale restored by the coordinator.
  _externalSurface = pointSize;
  _externalScale = scale;
  // The placement follows at the next layout; until then the touch screens
  // are converted again from the surface they are drawn in.
  _lastMappingSize = CGSizeZero;
  [self setNeedsSkinLayout];
}

- (void)externalDisplayDidChange:(BOOL)active {
  if (!active) return;
  // The picture left the iPhone: say where it went, in the session's
  // language, from the plugin's own catalog.
  [self showStatus:NeoExternalDisplayText(@"externalOnPhone", self.uiLocale)];
}

#pragma mark - Status

- (void)showStatus:(NSString *)message {
  if (message.length == 0 || !self.isViewLoaded) return;
  NSUInteger generation = ++_statusGeneration;
  _statusLabel.text = message;
  CGRect bounds = self.view.bounds;
  UIEdgeInsets insets = self.view.safeAreaInsets;
  CGFloat top = insets.top + 10;
  if (_editing && _editBar != nil) {
    top = CGRectGetMaxY(_editBar.frame) + 10;
  } else if (!_menuButton.hidden && CGRectGetMinY(_menuButton.frame) <= insets.top + 10) {
    // Below the menu button while it is in the top row (not when it moved
    // down beside a touch screen).
    top = CGRectGetMaxY(_menuButton.frame) + 10;
  }
  CGSize fit = [_statusLabel sizeThatFits:CGSizeMake(bounds.size.width * 0.7, 80)];
  CGFloat width = MIN(bounds.size.width * 0.8, fit.width + 32);
  _statusLabel.frame = CGRectMake(CGRectGetMidX(bounds) - width / 2, top, width, fit.height + 16);
  [UIView animateWithDuration:0.2
                   animations:^{
                     self->_statusLabel.alpha = 1;
                   }];
  UIAccessibilityPostNotification(UIAccessibilityAnnouncementNotification, message);
  dispatch_after(dispatch_time(DISPATCH_TIME_NOW, (int64_t)(2.5 * NSEC_PER_SEC)), dispatch_get_main_queue(), ^{
    if (generation != self->_statusGeneration) return;
    [UIView animateWithDuration:0.3
                     animations:^{
                       self->_statusLabel.alpha = 0;
                     }];
  });
}

- (void)setLoading:(BOOL)loading {
  if (loading) {
    [_spinner startAnimating];
  } else {
    [_spinner stopAnimating];
  }
}

#pragma mark - Presentation

- (BOOL)prefersStatusBarHidden {
  return YES;
}

- (BOOL)prefersHomeIndicatorAutoHidden {
  return YES;
}

- (UIRectEdge)preferredScreenEdgesDeferringSystemGestures {
  return UIRectEdgeAll;
}

- (UIInterfaceOrientationMask)supportedInterfaceOrientations {
  if (_editing) {
    return _currentOrientation == LibretroSkinOrientationLandscape ? UIInterfaceOrientationMaskLandscape
                                                                    : UIInterfaceOrientationMaskPortrait;
  }
  return self.allowedOrientations != 0 ? self.allowedOrientations : UIInterfaceOrientationMaskAllButUpsideDown;
}

@end
