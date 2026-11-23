#import "LibretroPerformanceOverlay.h"

#include <math.h>

static const CGFloat kLibretroPerformancePaddingX = 10;
static const CGFloat kLibretroPerformancePaddingY = 7;

@implementation LibretroPerformanceOverlay {
  UILabel *_label;
}

- (instancetype)initWithFrame:(CGRect)frame {
  self = [super initWithFrame:frame];
  if (self) {
    self.userInteractionEnabled = NO;
    self.backgroundColor = [UIColor colorWithWhite:0.0 alpha:0.7];
    self.layer.cornerRadius = 6;
    self.layer.masksToBounds = YES;
    self.accessibilityElementsHidden = YES;
    _label = [[UILabel alloc] initWithFrame:CGRectZero];
    _label.numberOfLines = 0;
    _label.textColor = UIColor.whiteColor;
    // Digits of one width, so that the numbers do not jitter as they change.
    _label.font = [UIFont monospacedDigitSystemFontOfSize:12 weight:UIFontWeightSemibold];
    _label.textAlignment = NSTextAlignmentLeft;
    [self addSubview:_label];
  }
  return self;
}

- (void)showLines:(NSArray<NSString *> *)lines {
  NSString *text = [lines componentsJoinedByString:@"\n"];
  if (![text isEqualToString:_label.text ?: @""]) _label.text = text;
  CGSize fit = [_label sizeThatFits:CGSizeMake(CGFLOAT_MAX, CGFLOAT_MAX)];
  CGRect frame = self.frame;
  frame.size = CGSizeMake(ceil(fit.width) + 2 * kLibretroPerformancePaddingX,
                          ceil(fit.height) + 2 * kLibretroPerformancePaddingY);
  self.frame = frame;
  _label.frame = CGRectMake(kLibretroPerformancePaddingX, kLibretroPerformancePaddingY, ceil(fit.width), ceil(fit.height));
}

@end
