#import "Registrar.h"
@implementation PresentationRegistrar
- (NSObject<FlutterBinaryMessenger>*)messenger { return self; }
- (NSObject<FlutterTextureRegistry>*)textures { return nil; }
- (void)registerViewFactory:(NSObject<FlutterPlatformViewFactory>*)factory withId:(NSString*)identifier {}
- (void)registerViewFactory:(NSObject<FlutterPlatformViewFactory>*)factory withId:(NSString*)identifier gestureRecognizersBlockingPolicy:(FlutterPlatformViewGestureRecognizersBlockingPolicy)policy {}
- (void)publish:(NSObject*)value {}
- (void)addMethodCallDelegate:(NSObject<FlutterPlugin>*)delegate channel:(FlutterMethodChannel*)channel { self.plugin=delegate; }
- (void)addApplicationDelegate:(NSObject<FlutterPlugin>*)delegate {}
- (void)addSceneDelegate:(NSObject<FlutterSceneLifeCycleDelegate>*)delegate {}
- (NSString*)lookupKeyForAsset:(NSString*)asset { return asset; }
- (NSString*)lookupKeyForAsset:(NSString*)asset fromPackage:(NSString*)package { return asset; }
- (NSObject*)valuePublishedByPlugin:(NSString*)key { return nil; }
- (void)sendOnChannel:(NSString*)channel message:(NSData*)message {}
- (void)sendOnChannel:(NSString*)channel message:(NSData*)message binaryReply:(FlutterBinaryReply)reply { if(reply) reply(nil); }
- (FlutterBinaryMessengerConnection)setMessageHandlerOnChannel:(NSString*)channel binaryMessageHandler:(FlutterBinaryMessageHandler)handler { return 1; }
- (void)cleanUpConnection:(FlutterBinaryMessengerConnection)connection {}
@end
