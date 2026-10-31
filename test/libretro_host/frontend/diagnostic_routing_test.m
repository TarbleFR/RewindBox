#import <Foundation/Foundation.h>
#import "LibretroSessionJournal.h"
#include <sys/stat.h>
#include <fcntl.h>
#include <unistd.h>
#include <stdio.h>
#include <stdlib.h>

static unsigned Checks;
static void Require(BOOL condition, NSString *message) {
  Checks++;
  if (!condition) { fprintf(stderr, "FAIL %s\n", message.UTF8String); exit(1); }
}
static NSString *Join(NSString *root, NSString *child) { return [root stringByAppendingPathComponent:child]; }
static NSData *Bytes(NSString *path) { return [NSData dataWithContentsOfFile:path]; }
static NSString *Text(NSString *path) {
  return [[NSString alloc] initWithData:Bytes(path) encoding:NSUTF8StringEncoding];
}
static void Bounded(NSString *path) {
  NSData *bytes = Bytes(path);
  Require(bytes.length > 0 && bytes.length <= 2 * 1024 * 1024, [@"bound " stringByAppendingString:path.lastPathComponent]);
  Require(Text(path) != nil, [@"valid UTF-8 " stringByAppendingString:path.lastPathComponent]);
}
static unsigned OpenDescriptorsFor(NSString *path, ino_t *inode) {
  struct stat expected;
  Require(stat(path.fileSystemRepresentation, &expected) == 0, @"stat shared fatal file");
  *inode = expected.st_ino;
  unsigned count = 0;
  for (int fd = 0; fd < 4096; fd++) {
    struct stat actual;
    if (fstat(fd, &actual) == 0 && actual.st_dev == expected.st_dev && actual.st_ino == expected.st_ino) count++;
  }
  return count;
}

int main(int argc, const char **argv) {
  @autoreleasepool {
    Require(argc == 2, @"one isolated fixture directory");
    NSString *root = @(argv[1]);
    NSFileManager *files = NSFileManager.defaultManager;
    NSString *legacy = Join(root, @"Libretro/Logs/session.log");
    [files createDirectoryAtPath:legacy.stringByDeletingLastPathComponent withIntermediateDirectories:YES attributes:nil error:nil];
    NSData *sentinel = [@"historical player diagnostic sentinel\n" dataUsingEncoding:NSUTF8StringEncoding];
    Require([sentinel writeToFile:legacy atomically:YES], @"seed legacy");
    NSString *shared = Join(root, @"Diagnostics/System/Libretro");
    [files createDirectoryAtPath:shared withIntermediateDirectories:YES attributes:nil error:nil];
    NSString *fatal = Join(shared, @"native-termination.log");
    NSData *priorFatal = [@"previous process\nfatal signal=sentinel\n" dataUsingEncoding:NSUTF8StringEncoding];
    Require([priorFatal writeToFile:fatal atomically:YES], @"seed prior fatal");
    NSString *ps1 = Join(root, @"Diagnostics/PS1/Libretro");
    NSString *psp = Join(root, @"Diagnostics/PSP/Libretro");
    LibretroSessionJournal *first = [LibretroSessionJournal journalInDirectory:ps1 crashDirectory:shared];
    Require(first != nil && !first.previousSessionUnfinished, @"first console starts");
    Require([Bytes(Join(shared, @"previous-native-termination.log")) isEqual:priorFatal], @"prior fatal preserved byte-for-byte");
    [first note:@"first console"];
    [first finishWithOutcome:@"completed"];
    ino_t inode1 = 0, inode2 = 0;
    Require(OpenDescriptorsFor(fatal, &inode1) == 1, @"one process-owned fatal descriptor");
    LibretroSessionJournal *second = [LibretroSessionJournal journalInDirectory:psp crashDirectory:shared];
    Require(second != nil && !second.previousSessionUnfinished, @"second console starts independently");
    Require(OpenDescriptorsFor(fatal, &inode2) == 1 && inode1 == inode2, @"switching consoles retains fatal descriptor identity");
    Require(![files fileExistsAtPath:Join(ps1, @"native-termination.log")] &&
            ![files fileExistsAtPath:Join(psp, @"native-termination.log")], @"no console-local process fatal files");
    Require([Text(fatal) containsString:second.sessionIdentifier], @"shared breadcrumb names current session");
    [second note:@"second console"];
    [second finishWithOutcome:@"completed"];
    NSData *pspBytes = Bytes(Join(psp, @"session.log"));

    NSMutableString *large = [NSMutableString stringWithCapacity:4 * 1024 * 1024];
    for (unsigned i = 0; i < 420000; i++) [large appendString:@"☃é🙂"];
    LibretroSessionJournal *rotated = [LibretroSessionJournal journalInDirectory:ps1 crashDirectory:shared];
    Require(!rotated.previousSessionUnfinished, @"finished prior session recognized");
    [rotated noteLines:@[large] title:@"large UTF-8 production block"];
    [rotated note:@"FINAL-TECHNICAL-ERROR-KEPT"];
    [rotated finishWithOutcome:@"completed"];
    NSString *current = Join(ps1, @"session.log"), *overflow = Join(ps1, @"session-overflow.log");
    Bounded(current); Bounded(overflow);
    Require([Text(current) containsString:@"FINAL-TECHNICAL-ERROR-KEPT"] && [Text(current) containsString:@"\nEND completed\n"], @"tail error and END survive rotation");
    Require([Text(current) containsString:rotated.sessionIdentifier], @"rotated generation retains provenance");
    NSData *rotatedBytes = Bytes(current), *overflowBytes = Bytes(overflow);
    [rotated note:@"ignored after END"];
    Require([Bytes(current) isEqual:rotatedBytes], @"closed journal ignores late writes");

    LibretroSessionJournal *unfinished = [LibretroSessionJournal journalInDirectory:ps1 crashDirectory:shared];
    Require(!unfinished.previousSessionUnfinished, @"END remains detectable after rotation");
    Require([Bytes(Join(ps1, @"previous-session.log")) isEqual:rotatedBytes] &&
            [Bytes(Join(ps1, @"previous-session-overflow.log")) isEqual:overflowBytes], @"previous matching generations preserved");
    [unfinished noteLines:@[large] title:@"interrupted UTF-8 block"];
    [unfinished note:@"INTERRUPTED-LAST-STEP"];
    NSData *unfinishedBytes = Bytes(current), *unfinishedOverflow = Bytes(overflow);
    unfinished = nil; // Simulate a session that left without END, not a signal.
    LibretroSessionJournal *failed = [LibretroSessionJournal journalInDirectory:ps1 crashDirectory:shared];
    Require(failed.previousSessionUnfinished, @"interrupted current detected");
    Require([Bytes(Join(ps1, @"unfinished-session.log")) isEqual:unfinishedBytes] &&
            [Bytes(Join(ps1, @"unfinished-session-overflow.log")) isEqual:unfinishedOverflow], @"unfinished matching generations retained");
    [failed noteLines:@[large] title:@"failed startup"];
    [failed finishWithOutcome:@"launch failed synthetic technical reason"];
    Bounded(current); Bounded(overflow);
    NSData *failedBytes = Bytes(Join(ps1, @"failed-launch.log"));
    NSData *failedOverflow = Bytes(Join(ps1, @"failed-launch-overflow.log"));
    Require([failedBytes isEqual:Bytes(current)] && [failedOverflow isEqual:Bytes(overflow)], @"failure retains both matching generations");
    LibretroSessionJournal *recovered = [LibretroSessionJournal journalInDirectory:ps1 crashDirectory:shared];
    [recovered finishWithOutcome:@"completed"];
    Require([Bytes(Join(ps1, @"failed-launch.log")) isEqual:failedBytes] &&
            [Bytes(Join(ps1, @"failed-launch-overflow.log")) isEqual:failedOverflow], @"later success preserves failed diagnostic");
    Require([Bytes(Join(psp, @"session.log")) isEqual:pspBytes], @"other console logs unchanged");
    Require([Bytes(legacy) isEqual:sentinel], @"historical player log untouched");
    Require(OpenDescriptorsFor(fatal, &inode2) == 1 && inode1 == inode2, @"one fatal descriptor remains after all teardowns");
    printf("PASS %u native journal routing checks; actual Foundation and production journal; no guest/Core execution\n", Checks);
  }
  return 0;
}
