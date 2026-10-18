// Declarations only for the standalone Apple SDK compile gate.
// Production imports the actual Flutter.framework through CocoaPods.
#include_next <Flutter/Flutter.h>

typedef void (^FlutterEventSink)(id event);
@protocol FlutterStreamHandler <NSObject>
- (FlutterError *)onListenWithArguments:(id)arguments eventSink:(FlutterEventSink)events;
- (FlutterError *)onCancelWithArguments:(id)arguments;
@end
@interface FlutterEventChannel : NSObject
+ (instancetype)eventChannelWithName:(NSString *)name binaryMessenger:(NSObject<FlutterBinaryMessenger> *)messenger;
- (void)setStreamHandler:(NSObject<FlutterStreamHandler> *)handler;
@end
