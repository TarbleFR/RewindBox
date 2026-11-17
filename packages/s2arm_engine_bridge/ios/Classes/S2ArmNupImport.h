#import <Flutter/Flutter.h>
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

// Switch 2 NUP containers (.nup) for the import: the Files picker opens them in place (no copy of a file of tens
// of GB into the app), their content is checked (rb_s2arm_nup_inspect) and expanded into an export folder
// (rb_s2arm_nup_expand, S2ArmPrepare.xcframework, a port of S2Arm's pack/ns2_nup.py) that the Dart import then
// moves into Games like any export. See docs/s2arm-switch2-library.md, § NUP containers.
@interface S2ArmNupImport : NSObject <UIDocumentPickerDelegate, UIAdaptivePresentationControllerDelegate>

- (instancetype)initWithChannel:(FlutterMethodChannel *)channel;

// Presents the picker from presenter: result gets the picked paths (security-scoped access kept until
// releaseFiles), @[] when the player cancels, or a FlutterError.
- (void)pickFrom:(nullable UIViewController *)presenter result:(FlutterResult)result;
// Ends the access the picker gave to the picked files.
- (void)releaseFiles;
// {success:true, programId, bytes, updateVersion, dlcCount, hasBase} or {success:false, code, diagnostic}.
- (void)inspect:(NSString *)path result:(FlutterResult)result;
// Expands path into output (inside Documents), reporting "nupProgress" {done, total} on the channel; result gets
// {success:true} or {success:false, code (nupInvalid, nupIo, cancelled), diagnostic}.
- (void)expand:(NSString *)path into:(NSString *)output documents:(NSString *)documents result:(FlutterResult)result;
- (void)cancel;

@end

NS_ASSUME_NONNULL_END
