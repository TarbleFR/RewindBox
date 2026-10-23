#import <Flutter/Flutter.h>
@interface PresentationRegistrar : NSObject<FlutterPluginRegistrar, FlutterBinaryMessenger>
@property(nonatomic,strong,nullable) UIViewController *viewController;
@property(nonatomic,strong,nullable) NSObject<FlutterPlugin> *plugin;
@end
