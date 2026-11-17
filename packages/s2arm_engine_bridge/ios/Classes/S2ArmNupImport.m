// Switch 2 NUP containers for the import. See S2ArmNupImport.h.
#import "S2ArmNupImport.h"
#import "S2ArmPrepareABI.h"

#import <UniformTypeIdentifiers/UniformTypeIdentifiers.h>
#import <stdatomic.h>

static NSString *const kNupProgressMethod = @"nupProgress";

@interface S2ArmNupImport ()
@property(nonatomic, weak) FlutterMethodChannel *channel;
@property(nonatomic, copy, nullable) FlutterResult pendingPick;
@property(nonatomic, strong) NSMutableArray<NSURL *> *accessed;   // security-scoped URLs this picker opened (main thread)
@property(nonatomic, strong) dispatch_queue_t queue;               // inspect and expand, one at a time
@end

@implementation S2ArmNupImport {
  atomic_int _cancel;
  _Atomic uint64_t _lastProgressNs;
}

- (instancetype)initWithChannel:(FlutterMethodChannel *)channel {
  if ((self = [super init])) {
    _channel = channel;
    _accessed = [NSMutableArray array];
    _queue = dispatch_queue_create("rewindbox.s2arm.nup", dispatch_queue_attr_make_with_qos_class(DISPATCH_QUEUE_SERIAL, QOS_CLASS_USER_INITIATED, 0));
  }
  return self;
}

// ---------------- picker ----------------

- (void)finishPick:(id)value {
  FlutterResult result = self.pendingPick;
  self.pendingPick = nil;
  if (result) result(value);
}

- (void)pickFrom:(UIViewController *)presenter result:(FlutterResult)result {
  if (self.pendingPick) [self finishPick:@[]];   // a pick whose sheet went away without an answer
  if (!presenter) {
    result([FlutterError errorWithCode:@"NO_ROOT_VC" message:@"No view controller to present the picker from" details:nil]);
    return;
  }
  self.pendingPick = result;
  // Opened in place, not copied: a NUP holds a whole game (tens of GB). Any data file can be picked; the import keeps
  // those whose first bytes are a NUP superblock (rb_s2arm_nup_inspect).
  UIDocumentPickerViewController *picker = [[UIDocumentPickerViewController alloc] initForOpeningContentTypes:@[ UTTypeData ] asCopy:NO];
  picker.delegate = self;
  picker.allowsMultipleSelection = YES;
  picker.presentationController.delegate = self;
  [presenter presentViewController:picker animated:YES completion:nil];
}

- (void)documentPicker:(UIDocumentPickerViewController *)controller didPickDocumentsAtURLs:(NSArray<NSURL *> *)urls {
  NSMutableArray<NSString *> *paths = [NSMutableArray array];
  for (NSURL *url in urls) {
    if ([url startAccessingSecurityScopedResource]) [self.accessed addObject:url];   // released by releaseFiles
    if (url.path.length) [paths addObject:url.path];
  }
  [self finishPick:paths];
}

- (void)documentPickerWasCancelled:(UIDocumentPickerViewController *)controller {
  [self finishPick:@[]];
}

- (void)presentationControllerDidDismiss:(UIPresentationController *)presentationController {
  if ([presentationController.presentedViewController isKindOfClass:UIDocumentPickerViewController.class]) [self finishPick:@[]];
}

- (void)releaseFiles {
  for (NSURL *url in self.accessed) [url stopAccessingSecurityScopedResource];
  [self.accessed removeAllObjects];
}

// ---------------- inspect / expand ----------------

static NSString *S2ArmNupCode(int rc) {
  return rc == RB_S2ARM_NUP_CANCELLED ? @"cancelled" : rc == RB_S2ARM_NUP_INVALID ? @"nupInvalid" : @"nupIo";
}

static NSDictionary *S2ArmNupInfo(const rb_s2arm_nup_info *info) {
  return @{
    @"success" : @YES,
    @"programId" : [NSString stringWithFormat:@"%016llX", (unsigned long long)info->program_id],
    @"bytes" : @(info->bytes),
    @"updateVersion" : @(info->update_version),
    @"dlcCount" : @(info->dlc_count),
    @"hasBase" : info->has_base ? @YES : @NO,
  };
}

- (void)inspect:(NSString *)path result:(FlutterResult)result {
  dispatch_async(self.queue, ^{
    rb_s2arm_nup_info info;
    char error[1024] = "";
    int rc = path.length ? rb_s2arm_nup_inspect(path.fileSystemRepresentation, &info, error, sizeof error) : RB_S2ARM_NUP_INVALID;
    NSDictionary *report = rc ? @{@"success" : @NO, @"code" : S2ArmNupCode(rc), @"diagnostic" : @(error)} : S2ArmNupInfo(&info);
    dispatch_async(dispatch_get_main_queue(), ^{ result(report); });
  });
}

static void s2arm_nup_note(void *context, const char *line) {
  (void)context;
  NSLog(@"S2Arm NUP: %s", line);
}

static int s2arm_nup_cancelled(void *context) {
  S2ArmNupImport *me = (__bridge S2ArmNupImport *)context;
  return atomic_load(&me->_cancel);
}

static void s2arm_nup_progress(void *context, uint64_t done, uint64_t total) {
  S2ArmNupImport *me = (__bridge S2ArmNupImport *)context;
  uint64_t now = clock_gettime_nsec_np(CLOCK_UPTIME_RAW), last = atomic_load(&me->_lastProgressNs);
  if (done < total && now - last < 100000000ull) return;   // ten a second at most, and the last one always
  atomic_store(&me->_lastProgressNs, now);
  dispatch_async(dispatch_get_main_queue(), ^{
    [me.channel invokeMethod:kNupProgressMethod arguments:@{@"done" : @(done), @"total" : @(total)}];
  });
}

- (void)expand:(NSString *)path into:(NSString *)output documents:(NSString *)documents result:(FlutterResult)result {
  NSString *root = documents.stringByStandardizingPath, *target = output.stringByStandardizingPath;
  if (!path.length || !output.isAbsolutePath || !root.length || ![target hasPrefix:[root stringByAppendingString:@"/"]]) {
    result(@{@"success" : @NO, @"code" : @"nupIo", @"diagnostic" : @"the output folder must be inside Documents"});
    return;
  }
  atomic_store(&_cancel, 0);
  atomic_store(&_lastProgressNs, 0);
  dispatch_async(self.queue, ^{
    rb_s2arm_nup_request request = {path.fileSystemRepresentation, target.fileSystemRepresentation, s2arm_nup_note, s2arm_nup_cancelled,
                                    s2arm_nup_progress, (__bridge void *)self};
    rb_s2arm_nup_info info;
    char error[1024] = "";
    int rc = rb_s2arm_nup_expand(&request, &info, error, sizeof error);
    NSDictionary *report = rc ? @{@"success" : @NO, @"code" : S2ArmNupCode(rc), @"diagnostic" : @(error)} : S2ArmNupInfo(&info);
    dispatch_async(dispatch_get_main_queue(), ^{ result(report); });
  });
}

- (void)cancel {
  atomic_store(&_cancel, 1);
}

@end
