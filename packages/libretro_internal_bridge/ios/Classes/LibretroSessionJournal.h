#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Plain-text journal of one embedded libretro session, written line by
/// line with write(2) as the session goes: launch, startup confirmation,
/// stop request and every teardown step (context_destroy,
/// retro_unload_game, retro_deinit, renderer release, dlclose, dismissal),
/// then the core's log and an END line. A process that ends during a
/// session (crash, iOS termination) leaves a journal without END: the
/// kernel keeps what was written, and the next session keeps that file as
/// `unfinished-session.log`, its last line naming the step that never
/// returned.
///
/// A session finished as "launch failed ..." is also copied to
/// `failed-launch.log`, kept until another launch fails: the sessions
/// started after a failure (retries, other games) would otherwise rotate
/// it away before it can be read.
///
/// Files live in Diagnostics/<console>/Libretro. Each session has at most
/// two 2 MiB generations: session.log and session-overflow.log. Previous,
/// unfinished and failed-launch snapshots retain both matching generations.
/// The process fatal descriptor belongs to Diagnostics/System/Libretro and
/// does not change when a later session selects another console. Thread-safe.
@interface LibretroSessionJournal : NSObject

/// Starts `session.log` in `directory` (created when missing), after
/// rotating the previous file. nil when the file cannot be created.
+ (nullable instancetype)journalInDirectory:(NSString *)directory;

/// The production crash directory remains fixed across console changes. The
/// one-argument entry retains the caller's original directory for fixtures.
+ (nullable instancetype)journalInDirectory:(NSString *)directory
                           crashDirectory:(NSString *)crashDirectory;

/// The session before this one never wrote its END line.
@property(nonatomic, readonly) BOOL previousSessionUnfinished;
@property(nonatomic, copy, readonly) NSString *path;
@property(nonatomic, copy, readonly) NSString *sessionIdentifier;

/// One timestamped line (UTC time and seconds since the session started).
- (void)note:(NSString *)line;

/// Loaded app/core image UUIDs and addresses for the fatal PC breadcrumb.
- (void)noteLoadedImages;

/// A titled block of lines (the core's log), indented.
- (void)noteLines:(NSArray<NSString *> *)lines title:(NSString *)title;

/// Writes "END <outcome>" and closes the file; later notes are ignored. An
/// outcome starting with "launch failed" copies the file to
/// `failed-launch.log`.
- (void)finishWithOutcome:(NSString *)outcome;

@end

NS_ASSUME_NONNULL_END
