// SPDX-License-Identifier: GPL-3.0-or-later
#import <UIKit/UIKit.h>
#import "NeoTouchLayoutModel.h"

NS_ASSUME_NONNULL_BEGIN

/// Places the engines' control views from a layout.
///
/// Every control keeps the centre and bounds its engine gave it (the stock
/// placement); the layout adds a single transform (scale about the centre,
/// then translation to the stored position). UIKit draws and hit-tests a view
/// through its transform, so the visible control and its touch area stay the
/// same rectangle after any move or resize. A control never leaves the canvas.
@interface NeoTouchLayoutApplier : NSObject
/// Canvas bounds inset by its safe area (the reference of stored positions).
+ (CGRect)safeRectOfCanvas:(UIView*)canvas;
/// Visible frame of a control in canvas coordinates under `layout`.
+ (CGRect)frameOfElement:(NeoTouchElement*)element layout:(nullable NeoTouchLayout*)layout canvas:(UIView*)canvas;
+ (CGPoint)centerOfElement:(NeoTouchElement*)element layout:(nullable NeoTouchLayout*)layout canvas:(UIView*)canvas;
/// Stored position of a control whose centre is `center` (canvas coordinates).
+ (CGPoint)normalizedPositionForCenter:(CGPoint)center canvas:(UIView*)canvas;
/// Applies `layout` (nil: stock controls). While editing, hidden controls are
/// drawn faintly instead of being removed, so they can be shown again.
+ (void)applyLayout:(nullable NeoTouchLayout*)layout
           elements:(NSArray<NeoTouchElement*>*)elements
             canvas:(UIView*)canvas
            editing:(BOOL)editing;
/// Removes every layout transform and restores the stock alpha/visibility.
+ (void)resetElements:(NSArray<NeoTouchElement*>*)elements;
@end

NS_ASSUME_NONNULL_END
