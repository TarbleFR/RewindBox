#import <CoreGraphics/CoreGraphics.h>

/// Non-destructive extraction of a painted control. Requires an opaque,
/// uniform or gently graded two-pixel perimeter and visible artwork inside it. Returns an
/// owned crop and an owned background image, or NULL when isolation is uncertain.
/// Never called from a touch handler; the renderer prepares it with images.
CGImageRef LibretroSkinCreateButtonCrop(CGImageRef image, CGRect pixels, CGImageRef *background) CF_RETURNS_RETAINED;
