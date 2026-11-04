// Stand-in for TCManagerInterface in the skin overlay harness: records every
// button and axis call DOLSkinOverlay makes, in order. No Core runs here.
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN
FOUNDATION_EXPORT void SkinRecorderReset(void);
/// "b<id>+" / "b<id>-" for buttons, "a<axis>=<value>" (3 decimals) for axes.
FOUNDATION_EXPORT NSArray<NSString*>* SkinRecorderEvents(void);
/// Last value sent to each axis / last state of each button.
FOUNDATION_EXPORT NSDictionary<NSNumber*, NSNumber*>* SkinRecorderAxes(void);
FOUNDATION_EXPORT NSSet<NSNumber*>* SkinRecorderHeldButtons(void);
NS_ASSUME_NONNULL_END
