// SPDX-License-Identifier: GPL-3.0-or-later
#import "Public/NeoTouchLayoutApplier.h"
#import "Public/NeoTouchLayoutGeometry.h"

static NeoTouchRect NeoTouchRectFromCG(CGRect rect) {
  NeoTouchRect result = {rect.origin.x, rect.origin.y, rect.size.width, rect.size.height};
  return result;
}

// Alpha of a hidden control while the editor shows it.
static const CGFloat kNeoTouchHiddenEditingAlpha = 0.3;

@implementation NeoTouchLayoutApplier

+ (CGRect)safeRectOfCanvas:(UIView*)canvas {
  CGRect safe = UIEdgeInsetsInsetRect(canvas.bounds, canvas.safeAreaInsets);
  if (safe.size.width < 1.0 || safe.size.height < 1.0) safe = canvas.bounds;
  return safe;
}

+ (CGPoint)centerOfElement:(NeoTouchElement*)element layout:(NeoTouchLayout*)layout canvas:(UIView*)canvas {
  NeoTouchControlState* state = [layout stateForIdentifier:element.identifier] ?: [NeoTouchControlState new];
  const double scale = NeoTouchClampScale(state.scale);
  NeoTouchPoint center = {element.defaultCenter.x, element.defaultCenter.y};
  if (state.hasPosition) {
    NeoTouchPoint normalized = {state.x, state.y};
    center = NeoTouchResolve(normalized, NeoTouchRectFromCG([self safeRectOfCanvas:canvas]));
  }
  center = NeoTouchClampCenter(center, element.defaultSize.width * scale, element.defaultSize.height * scale,
                               NeoTouchRectFromCG(canvas.bounds));
  return CGPointMake(center.x, center.y);
}

+ (CGRect)frameOfElement:(NeoTouchElement*)element layout:(NeoTouchLayout*)layout canvas:(UIView*)canvas {
  NeoTouchControlState* state = [layout stateForIdentifier:element.identifier] ?: [NeoTouchControlState new];
  const CGFloat scale = (CGFloat)NeoTouchClampScale(state.scale);
  const CGPoint center = [self centerOfElement:element layout:layout canvas:canvas];
  const CGSize size = CGSizeMake(element.defaultSize.width * scale, element.defaultSize.height * scale);
  return CGRectMake(center.x - size.width * 0.5, center.y - size.height * 0.5, size.width, size.height);
}

+ (CGPoint)normalizedPositionForCenter:(CGPoint)center canvas:(UIView*)canvas {
  NeoTouchPoint point = {center.x, center.y};
  NeoTouchPoint normalized = NeoTouchNormalize(point, NeoTouchRectFromCG([self safeRectOfCanvas:canvas]));
  return CGPointMake(normalized.x, normalized.y);
}

+ (void)applyLayout:(NeoTouchLayout*)layout elements:(NSArray<NeoTouchElement*>*)elements canvas:(UIView*)canvas
            editing:(BOOL)editing {
  for (NeoTouchElement* element in elements) {
    UIView* view = element.view;
    if (!view) continue;
    NeoTouchControlState* state = [layout stateForIdentifier:element.identifier] ?: [NeoTouchControlState new];
    const CGFloat scale = (CGFloat)NeoTouchClampScale(state.scale);
    const CGPoint center = [self centerOfElement:element layout:layout canvas:canvas];
    // The translation is expressed where the view's center lives.
    UIView* parent = view.superview ?: canvas;
    const CGPoint target = parent == canvas ? center : [canvas convertPoint:center toView:parent];
    const CGFloat dx = target.x - view.center.x;
    const CGFloat dy = target.y - view.center.y;
    view.transform = CGAffineTransformConcat(CGAffineTransformMakeScale(scale, scale),
                                             CGAffineTransformMakeTranslation(dx, dy));
    const CGFloat opacity = (CGFloat)NeoTouchClampOpacity(state.opacity);
    if (state.hidden) {
      view.hidden = !editing;
      view.alpha = element.defaultAlpha * (editing ? kNeoTouchHiddenEditingAlpha : opacity);
    } else {
      view.hidden = NO;
      view.alpha = element.defaultAlpha * opacity;
    }
  }
}

+ (void)resetElements:(NSArray<NeoTouchElement*>*)elements {
  for (NeoTouchElement* element in elements) {
    UIView* view = element.view;
    if (!view) continue;
    view.transform = CGAffineTransformIdentity;
    view.alpha = element.defaultAlpha;
    view.hidden = NO;
  }
}

@end
