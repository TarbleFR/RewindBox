#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

typedef void (^Rpcs3SessionCommand)(
    NSString* command,
    id _Nullable value,
    void (^completion)(BOOL success, NSString* message));

typedef void (^Rpcs3SessionReadStates)(
    void (^completion)(NSDictionary<NSString*, id>* _Nullable state));

typedef void (^Rpcs3SessionStateCommand)(
    NSInteger slot,
    BOOL load,
    NSString* _Nullable identifier,
    void (^completion)(BOOL success, NSString* message));

// REWINDBOX_GRAPHICS_TESTS_612: the key=value tokens of the current title's
// last "CONFIG_LAYERS part=rsx" Core line, or nil before its first boot report.
typedef NSDictionary<NSString*, NSString*>* _Nullable (^Rpcs3SessionReadAccuracy)(void);

@interface Rpcs3SessionMenu : UITableViewController
@property(nonatomic, copy) NSString* localeIdentifier;
@property(nonatomic, copy) NSString* gameTitle;
@property(nonatomic, assign) BOOL performanceVisible;
@property(nonatomic, assign) BOOL touchControlsVisible;
// Build 484: "Hide touch controls when a controller is connected" (PS3).
@property(nonatomic, assign) BOOL touchHideWithController;
@property(nonatomic, copy) NSArray<NSDictionary<NSString*, NSString*>*>* languageChoices;
@property(nonatomic, copy) Rpcs3SessionCommand performCommand;
@property(nonatomic, copy) Rpcs3SessionReadStates readStates;
@property(nonatomic, copy) Rpcs3SessionReadStates readCheats;
@property(nonatomic, copy) void (^importCheats)(NSDictionary*,NSArray*,void (^)(BOOL));
@property(nonatomic, copy) void (^setCheat)(NSString*,BOOL,void (^)(BOOL));
@property(nonatomic, copy) Rpcs3SessionStateCommand performStateOperation;
@property(nonatomic, copy) dispatch_block_t resumeGame;
@property(nonatomic, copy) dispatch_block_t quitGame;
@property(nonatomic, copy, nullable) Rpcs3SessionReadAccuracy readAccuracy;
// REWINDBOX_INCIDENT_REPORT_621: called when the menu itself is dismissed (from
// the visible page; idempotent), and the "Report a problem" row (shown when set).
@property(nonatomic, copy, nullable) dispatch_block_t menuDismissed;
@property(nonatomic, copy, nullable) void (^shareReport)(UIViewController* presenter);
@end

NS_ASSUME_NONNULL_END
