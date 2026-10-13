// Run in the iOS Simulator by test/libretro_channel_codec_test.py (Build 454).
//
// The real LibretroInternalBridgePlugin answers isSessionActive in each
// state of a launch, and the real FlutterStandardMethodCodec of the pinned
// Flutter.framework encodes each answer into the success envelope the engine
// sends to Dart. The states are those of -[LibretroInternalBridgePlugin
// launchWithArguments:result:] and of LibretroSession: the plugin's
// `session` and `launching` properties, and the session's emulation thread
// (`_thread`, read by its real `active` getter), set through key-value
// coding. No core is loaded and no view is presented.
//
// Prints one line, CODEC-RESULT <json>, and exits 0 once every state was
// encoded; the Python test compares the bytes.
#import <Flutter/Flutter.h>

#import "LibretroInternalBridgePlugin.h"
#import "LibretroSession.h"

static NSString *Hex(NSData *data) {
  NSMutableString *hex = [NSMutableString stringWithCapacity:data.length * 2];
  const uint8_t *bytes = data.bytes;
  for (NSUInteger index = 0; index < data.length; index++) [hex appendFormat:@"%02x", bytes[index]];
  return hex;
}

/// isSessionActive answered by the plugin, then encoded as the engine
/// encodes a reply.
static NSDictionary<NSString *, id> *Answer(LibretroInternalBridgePlugin *plugin, LibretroSession *session) {
  __block id reply = nil;
  __block NSInteger calls = 0;
  FlutterMethodCall *call = [FlutterMethodCall methodCallWithMethodName:@"isSessionActive" arguments:nil];
  [plugin handleMethodCall:call
                    result:^(id value) {
                      reply = value;
                      calls++;
                    }];
  NSData *envelope = [[FlutterStandardMethodCodec sharedInstance] encodeSuccessEnvelope:reply];
  BOOL number = [reply isKindOfClass:NSNumber.class];
  BOOL boolean = reply != nil && CFGetTypeID((__bridge CFTypeRef)reply) == CFBooleanGetTypeID();
  return @{
    @"envelope" : Hex(envelope),
    @"replies" : [NSNumber numberWithInteger:calls],
    @"class" : reply != nil ? NSStringFromClass([reply class]) : @"nil",
    @"objCType" : number ? [NSString stringWithUTF8String:[reply objCType]] : @"",
    @"cfBoolean" : boolean ? @YES : @NO,
    // The state really set: the plugin's properties and the session's own
    // `active` getter.
    @"launching" : [[plugin valueForKey:@"launching"] boolValue] ? @YES : @NO,
    @"hasSession" : [plugin valueForKey:@"session"] != nil ? @YES : @NO,
    @"sessionActive" : session.active ? @YES : @NO,
  };
}

int main(int argc, char *argv[]) {
  @autoreleasepool {
    LibretroInternalBridgePlugin *plugin = [LibretroInternalBridgePlugin new];
    LibretroSession *session =
        [[LibretroSession alloc] initWithConfiguration:[LibretroSessionConfiguration new]];
    NSMutableDictionary<NSString *, id> *states = [NSMutableDictionary dictionary];

    // No session yet.
    states[@"idle"] = Answer(plugin, nil);

    // launchWithArguments: sets the session and `launching`, then presents
    // the view; the emulation thread starts once it is presented.
    [plugin setValue:session forKey:@"session"];
    [plugin setValue:@YES forKey:@"launching"];
    states[@"launching"] = Answer(plugin, session);

    // The thread runs and the launch answered: `launching` is cleared.
    [session setValue:[NSThread new] forKey:@"thread"];
    [plugin setValue:@NO forKey:@"launching"];
    states[@"running"] = Answer(plugin, session);

    // finishStop: the thread is gone; the plugin keeps the session until
    // its ended handler runs, after the view is dismissed.
    [session setValue:nil forKey:@"thread"];
    states[@"stopped"] = Answer(plugin, session);

    NSDictionary *report = @{
      @"states" : states,
      @"flutterCodec" : NSStringFromClass([FlutterStandardMethodCodec class]),
      @"flutterBundle" : [NSBundle bundleForClass:[FlutterStandardMethodCodec class]].bundlePath ?: @"",
    };
    NSError *error = nil;
    NSData *json = [NSJSONSerialization dataWithJSONObject:report options:NSJSONWritingSortedKeys error:&error];
    if (json == nil) {
      fprintf(stderr, "CODEC-ERROR %s\n", error.localizedDescription.UTF8String);
      return 2;
    }
    printf("CODEC-RESULT %s\n", [[NSString alloc] initWithData:json encoding:NSUTF8StringEncoding].UTF8String);
    fflush(stdout);
  }
  return 0;
}
