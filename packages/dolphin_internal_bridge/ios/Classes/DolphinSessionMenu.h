#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN
@interface DolphinSessionMenu : UITableViewController
@property(nonatomic, copy) NSDictionary<NSString*, NSString*>* labels;
@property(nonatomic, assign) BOOL wii;
@property(nonatomic, copy) NSString* gameTitle;
@property(nonatomic, assign) BOOL stateActionsAvailable;
@property(nonatomic, assign) NSInteger slot;
@property(nonatomic, copy) void (^readSettings)(BOOL wii, NSInteger slot, void (^completion)(NSDictionary* _Nullable));
@property(nonatomic, copy) void (^applySettings)(NSDictionary* request, void (^completion)(BOOL));
@property(nonatomic, copy) void (^readStates)(void (^completion)(NSDictionary* _Nullable));
@property(nonatomic, copy) void (^performStateOperation)(NSInteger slot, BOOL load, void (^completion)(BOOL));
@property(nonatomic, copy, nullable) void (^readCheats)(void (^completion)(NSDictionary* _Nullable));
@property(nonatomic, copy, nullable) void (^performCheatCommand)(
    NSDictionary* request,
    void (^completion)(BOOL success, NSDictionary* _Nullable result));
@property(nonatomic, copy, nullable) void (^readRecording)(void (^completion)(NSDictionary* _Nullable));
@property(nonatomic, copy, nullable) void (^toggleRecording)(void (^completion)(BOOL));
@property(nonatomic, copy, nullable) dispatch_block_t shareRecording;
@property(nonatomic, copy) dispatch_block_t resumeGame;
@property(nonatomic, copy) dispatch_block_t quitGame;
@property(nonatomic, copy) dispatch_block_t restartGame;
@property(nonatomic, copy, nullable) dispatch_block_t openDisplaySettings;
@property(nonatomic, copy, nullable) dispatch_block_t openShaderSettings;
@property(nonatomic, copy, nullable) dispatch_block_t openTextureSettings;
// Build 484: Touch controls page (editor and "hide with a controller").
// Without openTouchEditor the root page has no Touch controls row.
@property(nonatomic, copy, nullable) dispatch_block_t openTouchEditor;
@property(nonatomic, copy, nullable) BOOL (^readTouchHideWithController)(void);
@property(nonatomic, copy, nullable) void (^setTouchHideWithController)(BOOL hide);
- (void)refreshRecordingStatus;
@end
NS_ASSUME_NONNULL_END
