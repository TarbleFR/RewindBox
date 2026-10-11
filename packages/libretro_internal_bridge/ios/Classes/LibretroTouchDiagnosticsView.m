#import "LibretroTouchDiagnosticsView.h"

#include <string.h>

static CGRect DiagnosticsRect(LibretroRect rect) { return CGRectMake(rect.x, rect.y, rect.w, rect.h); }

/// Deliveries kept for the "slowest of the last" figure.
static const NSUInteger kDelayWindow = 20;

@implementation LibretroTouchDiagnosticsView {
  LibretroSkinLayoutResult *_layout;
  NSSet<NSString *> *_deadItems;
  LibretroTouchResolution *_resolution;
  LibretroInputSnapshot _delivered;
  uint64_t _deliveredFrame;
  NSMutableArray<NSNumber *> *_delays;
  UILabel *_panel;
}

- (instancetype)initWithFrame:(CGRect)frame {
  self = [super initWithFrame:frame];
  if (self) {
    self.userInteractionEnabled = NO;
    self.backgroundColor = UIColor.clearColor;
    self.opaque = NO;
    self.contentMode = UIViewContentModeRedraw;
    _deadItems = [NSSet set];
    _delays = [NSMutableArray array];
    memset(&_delivered, 0, sizeof(_delivered));
    _panel = [[UILabel alloc] initWithFrame:CGRectZero];
    _panel.numberOfLines = 0;
    _panel.font = [UIFont monospacedSystemFontOfSize:11 weight:UIFontWeightMedium];
    _panel.textColor = UIColor.whiteColor;
    _panel.backgroundColor = [UIColor colorWithWhite:0 alpha:0.7];
    _panel.layer.cornerRadius = 6;
    _panel.layer.masksToBounds = YES;
    _panel.accessibilityIdentifier = @"libretro-touch-diagnostics";
    [self addSubview:_panel];
  }
  return self;
}

- (void)showLayout:(LibretroSkinLayoutResult *)layout deadItems:(NSSet<NSString *> *)deadItems {
  _layout = layout;
  _deadItems = [deadItems copy] ?: [NSSet set];
  [self setNeedsDisplay];
}

- (void)showResolution:(LibretroTouchResolution *)resolution {
  _resolution = resolution;
  [self setNeedsDisplay];
  [self updatePanel];
}

- (void)showDelivered:(LibretroInputSnapshot)snapshot frame:(uint64_t)frame {
  if (frame == _deliveredFrame && memcmp(&snapshot, &_delivered, sizeof(snapshot)) == 0) return;
  _delivered = snapshot;
  _deliveredFrame = frame;
  [self updatePanel];
}

- (void)noteDeliveryDelay:(NSTimeInterval)delay {
  [_delays addObject:@(delay)];
  while (_delays.count > kDelayWindow) [_delays removeObjectAtIndex:0];
  [self updatePanel];
}

- (void)updatePanel {
  NSMutableArray<NSString *> *lines = [NSMutableArray array];
  LibretroCoreInput touch = _resolution.coreInput;
  [lines addObject:[NSString stringWithFormat:@"touch  RetroPad %@", LibretroRetroPadDescription(touch.buttons)]];
  [lines addObject:[NSString stringWithFormat:@"core   frame %llu  RetroPad %@", (unsigned long long)_deliveredFrame,
                                              LibretroRetroPadDescription(_delivered.buttons[0])]];
  [lines addObject:[NSString stringWithFormat:@"core   L(%d,%d) R(%d,%d)  pointer %@ (%d,%d)", _delivered.analog[0][0][0],
                                              _delivered.analog[0][0][1], _delivered.analog[0][1][0],
                                              _delivered.analog[0][1][1], _delivered.pointerPressed ? @"down" : @"up",
                                              _delivered.pointerX, _delivered.pointerY]];
  if (_delays.count > 0) {
    double last = _delays.lastObject.doubleValue, slowest = 0;
    for (NSNumber *delay in _delays) slowest = MAX(slowest, delay.doubleValue);
    [lines addObject:[NSString stringWithFormat:@"iOS delivery  last %.0f ms  slowest %.0f ms", last * 1000,
                                                slowest * 1000]];
  }
  for (LibretroTouchContact *contact in _resolution.contacts) {
    NSString *items = contact.itemIdentifiers.count > 0 ? [contact.itemIdentifiers componentsJoinedByString:@","] : @"-";
    NSString *sent = contact.sentInputs.count > 0 ? [contact.sentInputs componentsJoinedByString:@"+"] : @"-";
    NSMutableString *line = [NSMutableString stringWithFormat:@"finger %lu  %@ -> %@", (unsigned long)contact.serial,
                                                              items, sent];
    if (contact.inertInputs.count > 0) {
      [line appendFormat:@"  inert %@", [contact.inertInputs componentsJoinedByString:@"+"]];
    }
    [lines addObject:line];
  }
  _panel.text = [lines componentsJoinedByString:@"\n"];
  CGRect bounds = self.bounds;
  UIEdgeInsets safe = self.safeAreaInsets;
  CGFloat width = MIN(bounds.size.width - safe.left - safe.right - 16, 420);
  CGSize fit = [_panel sizeThatFits:CGSizeMake(width, CGFLOAT_MAX)];
  _panel.frame = CGRectMake(safe.left + 8, safe.top + 52, MIN(width, fit.width + 12), fit.height + 8);
}

- (void)layoutSubviews {
  [super layoutSubviews];
  [self updatePanel];
}

- (void)drawRect:(CGRect)rect {
  UIColor *alive = [UIColor colorWithRed:0.2 green:0.9 blue:0.4 alpha:0.9];
  UIColor *dead = [UIColor colorWithRed:1.0 green:0.25 blue:0.2 alpha:0.9];
  UIColor *touch = [UIColor colorWithRed:0.3 green:0.6 blue:1.0 alpha:0.9];
  NSSet<NSString *> *pressed = _resolution.pressedItems ?: [NSSet set];
  for (LibretroLaidOutItem *laidOut in _layout.items) {
    LibretroSkinItem *item = laidOut.item;
    UIColor *color = item.kind == LibretroSkinItemKindTouchScreen ? touch
                     : [_deadItems containsObject:item.identifier] ? dead
                                                                   : alive;
    UIBezierPath *hit = [UIBezierPath bezierPathWithRect:DiagnosticsRect(laidOut.hitFrame)];
    const CGFloat dashes[2] = {4, 3};
    [hit setLineDash:dashes count:2 phase:0];
    hit.lineWidth = 1;
    [[color colorWithAlphaComponent:0.5] setStroke];
    [hit stroke];
    UIBezierPath *frame = [UIBezierPath bezierPathWithRect:DiagnosticsRect(laidOut.frame)];
    frame.lineWidth = [pressed containsObject:item.identifier] ? 3 : 1.5;
    [color setStroke];
    [frame stroke];
    if ([pressed containsObject:item.identifier]) {
      [[color colorWithAlphaComponent:0.25] setFill];
      [frame fill];
    }
  }
  for (LibretroTouchContact *contact in _resolution.contacts) {
    CGRect dot = CGRectMake(contact.x - 14, contact.y - 14, 28, 28);
    UIBezierPath *circle = [UIBezierPath bezierPathWithOvalInRect:dot];
    circle.lineWidth = 2;
    [(contact.sentInputs.count > 0 ? alive : dead) setStroke];
    [circle stroke];
  }
}

@end
