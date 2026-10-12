// Behaviour of LibretroTouchTracker, the interactive layer of every skin:
// scripted fingers go through the real hit test, the console's input map
// and the user's remaps, and the test reads the RetroPad / analog / pointer
// state the core would receive. The visual layer (halo) is checked against
// that state: an item is reported pressed only when it really sends an
// input. Covers every default skin on several iPhone sizes in both
// orientations, imported Delta skins (adapted names included), multitouch,
// long presses, slides, D-pad diagonals, sticks, triggers, rotation with a
// finger down, cancellation and the DS touch screen.
#import <Foundation/Foundation.h>

#import "LibretroDefaultSkins.h"
#import "LibretroInputMap.h"
#import "LibretroSkin.h"
#import "LibretroSkinLayout.h"
#import "LibretroTouchTracker.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include "libretro.h"

static int failures = 0;
static int checks = 0;
static NSString *workDirectory = nil;

static void Report(BOOL passed, NSString *message, int line) {
  checks++;
  if (passed) {
    printf("PASS %s\n", message.UTF8String);
  } else {
    printf("FAIL %s (%s:%d)\n", message.UTF8String, __FILE__, line);
    failures++;
  }
}

/// Only failures are printed for the large sweeps.
static void Quiet(BOOL passed, NSString *message, int line) {
  checks++;
  if (passed) return;
  printf("FAIL %s (%s:%d)\n", message.UTF8String, __FILE__, line);
  failures++;
}

#define CHECK(condition, ...) Report((condition) ? YES : NO, [NSString stringWithFormat:__VA_ARGS__], __LINE__)
#define QUIET(condition, ...) Quiet((condition) ? YES : NO, [NSString stringWithFormat:__VA_ARGS__], __LINE__)
#define BIT(joypad) ((uint16_t)(1u << RETRO_DEVICE_ID_JOYPAD_##joypad))

typedef struct {
  const char *name;
  LibretroSize size;
  LibretroInsets portrait;   // top, left, bottom, right
  LibretroInsets landscape;
  BOOL iPad;
} Device;

static const Device kDevices[] = {
    {"iPhone SE", {375, 667}, {20, 0, 0, 0}, {0, 0, 0, 0}, NO},
    {"iPhone 15", {393, 852}, {59, 0, 34, 0}, {0, 59, 21, 59}, NO},
    {"iPhone 16 Pro Max", {440, 956}, {62, 0, 34, 0}, {0, 62, 21, 62}, NO},
    {"iPad Air", {820, 1180}, {24, 0, 20, 0}, {24, 0, 20, 0}, YES},
};

static NSDictionary<NSString *, NSArray<NSNumber *> *> *Regions(NSString *console) {
  if ([console isEqualToString:@"3ds"]) return @{@"top" : @[ @0, @0, @1, @0.5 ], @"bottom" : @[ @0.1, @0.5, @0.8, @0.5 ]};
  if ([console isEqualToString:@"nds"]) return @{@"top" : @[ @0, @0, @1, @0.5 ], @"bottom" : @[ @0, @0.5, @1, @0.5 ]};
  return nil;
}

static LibretroSkinLayoutResult *DefaultLayout(NSString *console, LibretroSkinOrientation orientation, Device device) {
  LibretroSize size = orientation == LibretroSkinOrientationLandscape ? (LibretroSize){device.size.h, device.size.w}
                                                                       : device.size;
  LibretroInsets insets = orientation == LibretroSkinOrientationLandscape ? device.landscape : device.portrait;
  LibretroSkinRepresentation *representation = [LibretroDefaultSkins representationForConsole:console
                                                                                   orientation:orientation
                                                                                      viewSize:size
                                                                                    safeInsets:insets
                                                                                          iPad:device.iPad
                                                                                   arrangement:nil
                                                                                       swapped:NO
                                                                                       regions:Regions(console)];
  return [LibretroSkinLayout layoutRepresentation:representation viewSize:size safeInsets:insets overrides:nil];
}

static LibretroTouchTracker *Tracker(LibretroSkinLayoutResult *layout, NSString *console,
                                     NSDictionary<NSString *, NSArray<NSString *> *> *remap) {
  LibretroTouchTracker *tracker = [LibretroTouchTracker new];
  tracker.recordsContacts = YES;
  [tracker applyLayout:layout inputMap:[LibretroInputMap mapForConsole:console] touchRemap:remap];
  return tracker;
}

static LibretroLaidOutItem *LaidOut(LibretroSkinLayoutResult *layout, NSString *identifier) {
  for (LibretroLaidOutItem *laidOut in layout.items) {
    if ([laidOut.item.identifier isEqualToString:identifier]) return laidOut;
  }
  return nil;
}

static double MidX(LibretroRect rect) { return rect.x + rect.w / 2; }
static double MidY(LibretroRect rect) { return rect.y + rect.h / 2; }

/// The state `inputs` give at full deflection, computed with the input
/// map alone (independently of the tracker), and the actions they hold.
static LibretroCoreInput Expected(LibretroInputMap *map, NSArray<NSString *> *inputs, NSMutableSet<NSNumber *> *actions) {
  LibretroCoreInput state;
  memset(&state, 0, sizeof(state));
  for (NSString *input in inputs) {
    LibretroInputTarget target = [map targetForInput:input];
    if (target.kind == LibretroInputTargetAction) [actions addObject:@(target.action)];
    [map applyInput:input magnitude:1.0 toState:&state];
  }
  return state;
}

static BOOL SameInput(LibretroCoreInput a, LibretroCoreInput b) {
  return a.buttons == b.buttons && memcmp(a.analog, b.analog, sizeof(a.analog)) == 0;
}

static BOOL Released(LibretroTouchResolution *resolution) {
  LibretroCoreInput none;
  memset(&none, 0, sizeof(none));
  return SameInput(resolution.coreInput, none) && resolution.pressedItems.count == 0 &&
         resolution.actions.count == 0 && !resolution.pointerPressed;
}

static NSString *Describe(LibretroTouchResolution *resolution) {
  return [NSString stringWithFormat:@"buttons 0x%04x analog [%d %d %d %d] pressed {%@} inert {%@} actions %lu pointer %d",
                                    resolution.coreInput.buttons, resolution.coreInput.analog[0][0],
                                    resolution.coreInput.analog[0][1], resolution.coreInput.analog[1][0],
                                    resolution.coreInput.analog[1][1],
                                    [resolution.pressedItems.allObjects componentsJoinedByString:@","],
                                    [resolution.inertItems.allObjects componentsJoinedByString:@","],
                                    (unsigned long)resolution.actions.count, resolution.pointerPressed];
}

#pragma mark - Every default skin

/// Every control of every default skin, on every device and orientation:
/// a finger on the centre of a button sends exactly that button's inputs
/// and lights only it; the D-pad sends the direction under the finger; a
/// stick deflects its axis; the touch screen presses the pointer; lifting
/// the finger releases everything.
static void TestDefaultSkinsSweep(void) {
  NSUInteger buttons = 0, dpads = 0, sticks = 0, screens = 0;
  for (NSString *console in [LibretroDefaultSkins consoles]) {
    LibretroInputMap *map = [LibretroInputMap mapForConsole:console];
    for (size_t index = 0; index < sizeof(kDevices) / sizeof(kDevices[0]); index++) {
      Device device = kDevices[index];
      for (LibretroSkinOrientation orientation = LibretroSkinOrientationPortrait;
           orientation <= LibretroSkinOrientationLandscape; orientation++) {
        NSString *where = [NSString stringWithFormat:@"%@ %s %@", console, device.name, LibretroSkinOrientationName(orientation)];
        LibretroSkinLayoutResult *layout = DefaultLayout(console, orientation, device);
        LibretroTouchTracker *tracker = Tracker(layout, console, nil);
        for (LibretroLaidOutItem *laidOut in layout.items) {
          LibretroSkinItem *item = laidOut.item;
          LibretroRect frame = laidOut.frame;
          double x = MidX(frame), y = MidY(frame);
          NSString *what = [NSString stringWithFormat:@"%@ %@", where, item.identifier];
          switch (item.kind) {
            case LibretroSkinItemKindButton: {
              buttons++;
              NSMutableSet<NSNumber *> *actions = [NSMutableSet set];
              LibretroCoreInput expected = Expected(map, item.inputs, actions);
              [tracker beginTouch:@1 x:x y:y];
              LibretroTouchResolution *resolution = [tracker resolve];
              QUIET([resolution.pressedItems isEqualToSet:[NSSet setWithObject:item.identifier]] &&
                        SameInput(resolution.coreInput, expected) && [resolution.actions isEqualToSet:actions],
                    @"%@: the centre sends %@ and lights only this button (%@)", what,
                    [item.inputs componentsJoinedByString:@"+"], Describe(resolution));
              [tracker endTouch:@1];
              QUIET(Released([tracker resolve]), @"%@: lifting the finger releases it", what);
              break;
            }
            case LibretroSkinItemKindDPad: {
              dpads++;
              NSArray<NSString *> *inputs = item.inputs;
              // Up, down, left, right, then the up-right diagonal.
              double points[5][2] = {{x, frame.y + frame.h * 0.1}, {x, frame.y + frame.h * 0.9},
                                     {frame.x + frame.w * 0.1, y}, {frame.x + frame.w * 0.9, y},
                                     {x + frame.w * 0.32, y - frame.h * 0.32}};
              NSArray *expectedInputs = @[
                @[ inputs[0] ], @[ inputs[1] ], @[ inputs[2] ], @[ inputs[3] ], @[ inputs[0], inputs[3] ]
              ];
              for (int point = 0; point < 5; point++) {
                [tracker beginTouch:@2 x:points[point][0] y:points[point][1]];
                LibretroTouchResolution *resolution = [tracker resolve];
                LibretroCoreInput expected = Expected(map, expectedInputs[point], [NSMutableSet set]);
                QUIET(SameInput(resolution.coreInput, expected) &&
                          [resolution.pressedItems isEqualToSet:[NSSet setWithObject:item.identifier]],
                      @"%@: D-pad point %d sends %@ (%@)", what, point,
                      [expectedInputs[point] componentsJoinedByString:@"+"], Describe(resolution));
                [tracker endTouch:@2];
              }
              [tracker beginTouch:@2 x:x y:y];
              LibretroTouchResolution *centre = [tracker resolve];
              QUIET(centre.coreInput.buttons == 0 && centre.pressedItems.count == 0,
                    @"%@: the D-pad centre is a dead zone (%@)", what, Describe(centre));
              [tracker endTouch:@2];
              break;
            }
            case LibretroSkinItemKindThumbstick: {
              sticks++;
              [tracker beginTouch:@3 x:x y:y];
              LibretroTouchResolution *held = [tracker resolve];
              QUIET([held.pressedItems containsObject:item.identifier] && held.stickVectors[item.identifier] != nil &&
                        SameInput(held.coreInput, Expected(map, @[], nil)),
                    @"%@: a finger on the stick centre holds it without deflection (%@)", what, Describe(held));
              [tracker moveTouch:@3 x:frame.x + frame.w y:y];
              LibretroTouchResolution *right = [tracker resolve];
              QUIET(SameInput(right.coreInput, Expected(map, @[ item.inputs[3] ], [NSMutableSet set])),
                    @"%@: full right deflection sends %@ (%@)", what, item.inputs[3], Describe(right));
              [tracker moveTouch:@3 x:x y:frame.y - frame.h];
              LibretroTouchResolution *up = [tracker resolve];
              QUIET(SameInput(up.coreInput, Expected(map, @[ item.inputs[0] ], [NSMutableSet set])),
                    @"%@: a finger past the top edge stays bound and sends %@ (%@)", what, item.inputs[0], Describe(up));
              [tracker endTouch:@3];
              QUIET(Released([tracker resolve]), @"%@: the stick recentres on release", what);
              break;
            }
            case LibretroSkinItemKindTouchScreen: {
              screens++;
              [tracker beginTouch:@4 x:x y:y];
              LibretroTouchResolution *touch = [tracker resolve];
              QUIET(touch.pointerPressed && touch.coreInput.buttons == 0 && touch.pressedItems.count == 0,
                    @"%@: the touch screen presses the pointer only (%@)", what, Describe(touch));
              [tracker endTouch:@4];
              QUIET(![tracker resolve].pointerPressed, @"%@: lifting the stylus releases the pointer", what);
              break;
            }
          }
        }
      }
    }
  }
  CHECK(buttons > 400 && dpads >= 100 && sticks >= 30 && screens >= 16,
        @"default skins sweep: %lu buttons, %lu D-pads, %lu sticks, %lu touch screens checked", (unsigned long)buttons,
        (unsigned long)dpads, (unsigned long)sticks, (unsigned long)screens);
}

#pragma mark - Gestures

static void TestGestures(void) {
  Device phone = kDevices[1];
  LibretroSkinLayoutResult *gba = DefaultLayout(@"gba", LibretroSkinOrientationLandscape, phone);
  LibretroTouchTracker *tracker = Tracker(gba, @"gba", nil);
  LibretroRect a = LaidOut(gba, @"a").frame, b = LaidOut(gba, @"b").frame;
  LibretroRect l = LaidOut(gba, @"l").frame, r = LaidOut(gba, @"r").frame;
  LibretroRect start = LaidOut(gba, @"start").frame;

  // Multitouch A + B, then each released on its own.
  [tracker beginTouch:@"a" x:MidX(a) y:MidY(a)];
  [tracker beginTouch:@"b" x:MidX(b) y:MidY(b)];
  LibretroTouchResolution *both = [tracker resolve];
  CHECK(both.coreInput.buttons == (BIT(A) | BIT(B)) &&
            [both.pressedItems isEqualToSet:([NSSet setWithObjects:@"a", @"b", nil])],
        @"A + B with two fingers: both reach the core (%@)", Describe(both));
  [tracker endTouch:@"a"];
  CHECK([tracker resolve].coreInput.buttons == BIT(B), @"A released, B still held");
  [tracker endTouch:@"b"];

  // A long press stays pressed for as long as the finger stays.
  [tracker beginTouch:@"hold" x:MidX(a) y:MidY(a)];
  BOOL held = YES;
  for (int step = 0; step < 600; step++) {
    [tracker moveTouch:@"hold" x:MidX(a) + (step % 3) - 1 y:MidY(a)];
    if ([tracker resolve].coreInput.buttons != BIT(A)) held = NO;
  }
  CHECK(held, @"a long press with small finger jitter keeps A pressed");
  // Sliding from A to B (Delta): A is released, B pressed.
  [tracker moveTouch:@"hold" x:MidX(b) y:MidY(b)];
  LibretroTouchResolution *slid = [tracker resolve];
  CHECK(slid.coreInput.buttons == BIT(B) && [slid.pressedItems isEqualToSet:[NSSet setWithObject:@"b"]],
        @"sliding from A onto B moves the press (%@)", Describe(slid));
  [tracker endTouch:@"hold"];

  // Shoulders and start together.
  [tracker beginTouch:@1 x:MidX(l) y:MidY(l)];
  [tracker beginTouch:@2 x:MidX(r) y:MidY(r)];
  [tracker beginTouch:@3 x:MidX(start) y:MidY(start)];
  CHECK([tracker resolve].coreInput.buttons == (BIT(L) | BIT(R) | BIT(START)), @"L + R + START together");
  // Cancellation (incoming call, Control Center): nothing stays stuck.
  [tracker endAllTouches];
  CHECK(Released([tracker resolve]), @"cancelling every touch releases every button");

  // D-pad: a finger that starts on the D-pad stays bound to it, past its
  // edge, and follows the diagonals.
  LibretroRect dpad = LaidOut(gba, @"dpad").frame;
  [tracker beginTouch:@"d" x:MidX(dpad) y:dpad.y + dpad.h * 0.1];
  CHECK([tracker resolve].coreInput.buttons == BIT(UP), @"D-pad up");
  [tracker moveTouch:@"d" x:dpad.x + dpad.w * 1.5 y:dpad.y - dpad.h * 0.5];
  CHECK([tracker resolve].coreInput.buttons == (BIT(UP) | BIT(RIGHT)), @"past the edge, up-right diagonal");
  [tracker moveTouch:@"d" x:dpad.x - dpad.w y:MidY(dpad)];
  CHECK([tracker resolve].coreInput.buttons == BIT(LEFT), @"left, far outside the D-pad, still bound");
  [tracker moveTouch:@"d" x:dpad.x + dpad.w * 0.1 y:dpad.y + dpad.h * 0.9];
  CHECK([tracker resolve].coreInput.buttons == (BIT(DOWN) | BIT(LEFT)), @"down-left diagonal");
  // A + D-pad at once.
  [tracker beginTouch:@"a" x:MidX(a) y:MidY(a)];
  CHECK([tracker resolve].coreInput.buttons == (BIT(DOWN) | BIT(LEFT) | BIT(A)), @"diagonal and A together");
  [tracker endAllTouches];

  // Rotation with a finger on the D-pad: the finger follows the D-pad to
  // its new place, by identifier.
  [tracker beginTouch:@"rot" x:MidX(dpad) y:dpad.y + dpad.h * 0.1];
  LibretroSkinLayoutResult *portrait = DefaultLayout(@"gba", LibretroSkinOrientationPortrait, phone);
  [tracker applyLayout:portrait inputMap:[LibretroInputMap mapForConsole:@"gba"] touchRemap:nil];
  LibretroRect moved = LaidOut(portrait, @"dpad").frame;
  [tracker moveTouch:@"rot" x:MidX(moved) + moved.w * 0.4 y:MidY(moved)];
  CHECK([tracker resolve].coreInput.buttons == BIT(RIGHT), @"after a rotation the held D-pad finger follows it");
  [tracker endAllTouches];
  // Back to landscape for the next gestures.
  [tracker applyLayout:gba inputMap:[LibretroInputMap mapForConsole:@"gba"] touchRemap:nil];

  // A physical controller hides the controls: touches send nothing.
  tracker.controlsDisabled = YES;
  [tracker beginTouch:@"pad" x:MidX(a) y:MidY(a)];
  CHECK(Released([tracker resolve]), @"controls disabled: a touch on A sends nothing and lights nothing");
  [tracker endAllTouches];
  tracker.controlsDisabled = NO;

  // A finger lost without an end (key reused) starts over.
  [tracker beginTouch:@"x" x:MidX(a) y:MidY(a)];
  [tracker beginTouch:@"x" x:MidX(b) y:MidY(b)];
  CHECK([tracker resolve].coreInput.buttons == BIT(B) && tracker.touchCount == 1,
        @"a finger key reused without an end replaces the old finger");
  [tracker endAllTouches];

  // PlayStation triggers and N64 Z / C buttons from their default skins.
  LibretroSkinLayoutResult *psx = DefaultLayout(@"psx", LibretroSkinOrientationLandscape, phone);
  LibretroTouchTracker *psxTracker = Tracker(psx, @"psx", nil);
  LibretroRect l2 = LaidOut(psx, @"l2").frame, r2 = LaidOut(psx, @"r2").frame;
  [psxTracker beginTouch:@1 x:MidX(l2) y:MidY(l2)];
  [psxTracker beginTouch:@2 x:MidX(r2) y:MidY(r2)];
  CHECK([psxTracker resolve].coreInput.buttons == (BIT(L2) | BIT(R2)), @"PlayStation L2 + R2");
  LibretroSkinLayoutResult *n64 = DefaultLayout(@"n64", LibretroSkinOrientationLandscape, phone);
  LibretroTouchTracker *n64Tracker = Tracker(n64, @"n64", nil);
  LibretroRect z = LaidOut(n64, @"z").frame, cUp = LaidOut(n64, @"cUp").frame;
  [n64Tracker beginTouch:@1 x:MidX(z) y:MidY(z)];
  [n64Tracker beginTouch:@2 x:MidX(cUp) y:MidY(cUp)];
  LibretroTouchResolution *n64State = [n64Tracker resolve];
  CHECK(n64State.coreInput.buttons == BIT(L2) && n64State.coreInput.analog[1][1] == -0x7fff,
        @"N64 Z (RetroPad L2) and C-up (right analog up) together");
}

#pragma mark - Remaps, dead buttons, actions

static void TestRemapsAndDeadButtons(void) {
  Device phone = kDevices[1];
  LibretroSkinLayoutResult *gba = DefaultLayout(@"gba", LibretroSkinOrientationLandscape, phone);
  LibretroRect a = LaidOut(gba, @"a").frame;
  // A user remap: the A button sends B.
  LibretroTouchTracker *remapped = Tracker(gba, @"gba", @{@"a" : @[ @"b" ]});
  [remapped beginTouch:@1 x:MidX(a) y:MidY(a)];
  CHECK([remapped resolve].coreInput.buttons == BIT(B), @"a remapped item sends its new input");
  // A remap to an input this console lacks: dead, and never lit.
  LibretroTouchTracker *dead = Tracker(gba, @"gba", @{@"a" : @[ @"x" ]});
  [dead beginTouch:@1 x:MidX(a) y:MidY(a)];
  LibretroTouchResolution *deadState = [dead resolve];
  LibretroTouchContact *contact = deadState.contacts.firstObject;
  CHECK(deadState.coreInput.buttons == 0 && deadState.pressedItems.count == 0 &&
            [deadState.inertItems isEqualToSet:[NSSet setWithObject:@"a"]] &&
            [contact.inertInputs isEqualToArray:@[ @"x" ]] && contact.sentInputs.count == 0,
        @"a button that sends nothing is reported inert and never highlighted (%@)", Describe(deadState));
  // 3DS: L3 is blocked (HOME in Azahar): a remap to it sends nothing.
  LibretroSkinLayoutResult *threeDS = DefaultLayout(@"3ds", LibretroSkinOrientationLandscape, phone);
  LibretroRect threeA = LaidOut(threeDS, @"a").frame;
  LibretroTouchTracker *blocked = Tracker(threeDS, @"3ds", @{@"a" : @[ @"l3" ]});
  [blocked beginTouch:@1 x:MidX(threeA) y:MidY(threeA)];
  LibretroTouchResolution *blockedState = [blocked resolve];
  CHECK(blockedState.coreInput.buttons == 0 && blockedState.pressedItems.count == 0,
        @"a blocked RetroPad button is never sent nor lit");
  // A remap to a frontend action: the action is held while pressed.
  LibretroTouchTracker *action = Tracker(gba, @"gba", @{@"a" : @[ @"fastForward" ]});
  [action beginTouch:@1 x:MidX(a) y:MidY(a)];
  LibretroTouchResolution *actionState = [action resolve];
  CHECK([actionState.actions isEqualToSet:[NSSet setWithObject:@(LibretroFrontendActionFastForward)]] &&
            actionState.coreInput.buttons == 0 && [actionState.pressedItems containsObject:@"a"],
        @"a remap to fast forward holds the action, not a button");
  [action endTouch:@1];
  CHECK([action resolve].actions.count == 0, @"releasing it releases the action");
  // The contact log names what a finger really sends.
  LibretroTouchTracker *logged = Tracker(gba, @"gba", nil);
  [logged beginTouch:@1 x:MidX(a) y:MidY(a)];
  LibretroTouchContact *sent = [logged resolve].contacts.firstObject;
  CHECK(sent != nil && sent.mode == LibretroTouchModeFree && [sent.itemIdentifiers isEqualToArray:@[ @"a" ]] &&
            [sent.sentInputs isEqualToArray:@[ @"a" ]],
        @"diagnostics: the finger, the item and the input sent");
  LibretroTouchTracker *silent = Tracker(gba, @"gba", nil);
  silent.recordsContacts = NO;
  [silent beginTouch:@1 x:MidX(a) y:MidY(a)];
  CHECK([silent resolve].contacts.count == 0, @"no contact log unless diagnostics ask for it");
}

#pragma mark - Overlapping touch areas

static LibretroSkinItem *Item(NSString *identifier, LibretroSkinItemKind kind, LibretroRect frame,
                              NSArray<NSString *> *inputs, double edge) {
  LibretroSkinItem *item = [LibretroSkinItem new];
  item.identifier = identifier;
  item.kind = kind;
  item.frame = frame;
  LibretroInsets edges = {edge, edge, edge, edge};
  item.hitFrame = LibretroRectOutset(frame, edges);
  item.assetFrame = frame;
  item.inputs = inputs;
  return item;
}

static void TestOverlaps(void) {
  // A and B 10 points apart with 20-point touch margins: each margin covers
  // the other's drawing.
  LibretroSkinItem *a = Item(@"a", LibretroSkinItemKindButton, LibretroRectMake(100, 100, 60, 60), @[ @"a" ], 20);
  LibretroSkinItem *b = Item(@"b", LibretroSkinItemKindButton, LibretroRectMake(170, 100, 60, 60), @[ @"b" ], 20);
  LibretroSkinItem *menu = Item(@"menu", LibretroSkinItemKindButton, LibretroRectMake(100, 20, 60, 30), @[ @"menu" ], 60);
  LibretroSkinRepresentation *representation = [LibretroSkinRepresentation new];
  representation.generated = YES;
  representation.mappingSize = (LibretroSize){400, 300};
  representation.orientation = LibretroSkinOrientationLandscape;
  representation.items = @[ a, b, menu ];
  representation.screens = @[];
  LibretroInsets none = {0, 0, 0, 0};
  LibretroSkinLayoutResult *layout = [LibretroSkinLayout layoutRepresentation:representation
                                                                     viewSize:(LibretroSize){400, 300}
                                                                   safeInsets:none
                                                                    overrides:nil];
  LibretroTouchTracker *tracker = Tracker(layout, @"gba", nil);
  [tracker beginTouch:@1 x:155 y:130];
  CHECK([tracker resolve].coreInput.buttons == BIT(A), @"on A's drawing, B's touch margin adds no second press");
  [tracker endTouch:@1];
  [tracker beginTouch:@1 x:165 y:130];
  CHECK([tracker resolve].coreInput.buttons == (BIT(A) | BIT(B)), @"between the drawings, both margins fire (Delta)");
  [tracker endTouch:@1];
  [tracker beginTouch:@1 x:130 y:105];
  LibretroTouchResolution *top = [tracker resolve];
  CHECK(top.coreInput.buttons == BIT(A) && top.actions.count == 0, @"on A's drawing, the menu's margin never opens the menu");
  [tracker endTouch:@1];
  [tracker beginTouch:@1 x:130 y:35];
  LibretroTouchResolution *menuState = [tracker resolve];
  CHECK([menuState.actions isEqualToSet:[NSSet setWithObject:@(LibretroFrontendActionMenu)]] &&
            menuState.coreInput.buttons == 0,
        @"the menu button is exclusive");
}

#pragma mark - Imported Delta skin

static NSData *PDFData(void) {
  return [@"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
      dataUsingEncoding:NSUTF8StringEncoding];
}

static NSDictionary *Frame(double x, double y, double width, double height) {
  return @{@"x" : @(x), @"y" : @(y), @"width" : @(width), @"height" : @(height)};
}

/// A GBA skin as Delta / Provenance creators write them, with names other
/// emulators use: a diagonal token, a thumbstick on a console without one,
/// "run" for start, and a button NeoStation cannot use.
static LibretroSkin *ImportedGBA(void) {
  NSDictionary *edges = @{@"top" : @10, @"bottom" : @10, @"left" : @10, @"right" : @10};
  NSArray *items = @[
    @{@"inputs" : @{@"up" : @"up", @"down" : @"down", @"left" : @"left", @"right" : @"right"},
      @"frame" : Frame(20, 500, 150, 150)},
    @{@"inputs" : @[ @"a" ], @"frame" : Frame(300, 520, 70, 70)},
    @{@"inputs" : @[ @"b" ], @"frame" : Frame(220, 580, 70, 70)},
    @{@"inputs" : @[ @"a", @"b" ], @"frame" : Frame(270, 640, 40, 40)},
    @{@"inputs" : @[ @"l" ], @"frame" : Frame(0, 420, 100, 40)},
    @{@"inputs" : @[ @"r" ], @"frame" : Frame(290, 420, 100, 40)},
    @{@"inputs" : @[ @"run" ], @"frame" : Frame(200, 760, 60, 30)},
    @{@"inputs" : @[ @"select" ], @"frame" : Frame(130, 760, 60, 30)},
    @{@"inputs" : @[ @"menu" ], @"frame" : Frame(170, 800, 50, 30)},
    @{@"inputs" : @[ @"upLeft" ], @"frame" : Frame(0, 680, 40, 40)},
    @{@"inputs" : @{@"up" : @"analogStickUp", @"down" : @"analogStickDown", @"left" : @"analogStickLeft",
                    @"right" : @"analogStickRight"},
      @"thumbstick" : @{@"name" : @"knob.pdf", @"width" : @40, @"height" : @40},
      @"frame" : Frame(40, 300, 100, 100)},
    @{@"inputs" : @[ @"x" ], @"frame" : Frame(330, 300, 40, 40)},
  ];
  NSDictionary *portrait = @{
    @"assets" : @{@"resizable" : @"portrait.pdf"},
    @"items" : items,
    @"screens" : @[ @{@"inputFrame" : Frame(0, 0, 240, 160), @"outputFrame" : Frame(0, 60, 390, 260)} ],
    @"mappingSize" : @{@"width" : @390, @"height" : @844},
    @"extendedEdges" : edges,
  };
  NSDictionary *info = @{
    @"name" : @"Adapted GBA",
    @"identifier" : @"com.neostation.test.adapted",
    @"gameTypeIdentifier" : @"com.rileytestut.delta.game.gba",
    @"representations" : @{@"iphone" : @{@"edgeToEdge" : @{@"portrait" : portrait}}},
  };
  NSString *directory = [workDirectory stringByAppendingPathComponent:@"adapted-gba"];
  NSFileManager *manager = [NSFileManager defaultManager];
  [manager removeItemAtPath:directory error:nil];
  [manager createDirectoryAtPath:directory withIntermediateDirectories:YES attributes:nil error:nil];
  [[NSJSONSerialization dataWithJSONObject:info options:0 error:nil]
      writeToFile:[directory stringByAppendingPathComponent:@"info.json"]
       atomically:YES];
  [PDFData() writeToFile:[directory stringByAppendingPathComponent:@"portrait.pdf"] atomically:YES];
  [PDFData() writeToFile:[directory stringByAppendingPathComponent:@"knob.pdf"] atomically:YES];
  NSString *code = nil;
  return [LibretroSkin skinWithDirectory:directory consoleGeometry:@{@"gba" : @{@"size" : @[ @240, @160 ]}} errorCode:&code];
}

static void TestImportedSkin(void) {
  LibretroSkin *skin = ImportedGBA();
  CHECK(skin != nil, @"the adapted GBA skin parses");
  if (skin == nil) return;
  LibretroSkinRepresentation *representation = [skin representationForOrientation:LibretroSkinOrientationPortrait
                                                                              iPad:NO
                                                                        edgeToEdge:YES];
  LibretroInsets insets = {59, 0, 34, 0};
  LibretroSkinLayoutResult *layout = [LibretroSkinLayout layoutRepresentation:representation
                                                                     viewSize:(LibretroSize){390, 844}
                                                                   safeInsets:insets
                                                                    overrides:nil];
  LibretroTouchTracker *tracker = Tracker(layout, @"gba", nil);
  NSArray<NSArray *> *expectations = @[
    @[ @"item1", @(BIT(A)) ], @[ @"item2", @(BIT(B)) ], @[ @"item3", @(BIT(A) | BIT(B)) ], @[ @"item4", @(BIT(L)) ],
    @[ @"item5", @(BIT(R)) ], @[ @"item6", @(BIT(START)) ], @[ @"item7", @(BIT(SELECT)) ],
    @[ @"item9", @(BIT(UP) | BIT(LEFT)) ]
  ];
  NSString *prefix = @"iphone-edgeToEdge-portrait-";
  for (NSArray *expectation in expectations) {
    NSString *identifier = [prefix stringByAppendingString:expectation[0]];
    LibretroLaidOutItem *laidOut = LaidOut(layout, identifier);
    [tracker beginTouch:@1 x:MidX(laidOut.frame) y:MidY(laidOut.frame)];
    LibretroTouchResolution *resolution = [tracker resolve];
    CHECK(laidOut != nil && resolution.coreInput.buttons == [expectation[1] unsignedShortValue] &&
              [resolution.pressedItems isEqualToSet:[NSSet setWithObject:identifier]],
          @"imported %@ sends RetroPad 0x%04x and lights (%@)", expectation[0], [expectation[1] unsignedShortValue],
          Describe(resolution));
    [tracker endTouch:@1];
  }
  LibretroLaidOutItem *menu = LaidOut(layout, [prefix stringByAppendingString:@"item8"]);
  [tracker beginTouch:@1 x:MidX(menu.frame) y:MidY(menu.frame)];
  CHECK([[tracker resolve].actions isEqualToSet:[NSSet setWithObject:@(LibretroFrontendActionMenu)]],
        @"imported menu button opens the menu");
  [tracker endTouch:@1];
  // The thumbstick of a GBA skin drives the D-pad (a GBA has no stick).
  LibretroLaidOutItem *stick = LaidOut(layout, [prefix stringByAppendingString:@"item10"]);
  CHECK(stick.item.kind == LibretroSkinItemKindThumbstick &&
            [stick.item.inputs isEqualToArray:(@[ @"up", @"down", @"left", @"right" ])] &&
            stick.item.adaptedInputs.count == 4,
        @"a GBA thumbstick is adapted to the D-pad directions");
  [tracker beginTouch:@1 x:MidX(stick.frame) y:MidY(stick.frame)];
  [tracker moveTouch:@1 x:stick.frame.x + stick.frame.w y:MidY(stick.frame)];
  CHECK([tracker resolve].coreInput.buttons == BIT(RIGHT), @"pushing that stick right presses D-pad right");
  [tracker moveTouch:@1 x:MidX(stick.frame) + stick.frame.w * 0.1 y:MidY(stick.frame)];
  LibretroTouchResolution *small = [tracker resolve];
  CHECK(small.coreInput.buttons == 0, @"a small push stays under the digital threshold");
  // Build 448: below the threshold the D-pad stick sends nothing, so it is
  // not lit (before: lit with nothing sent); its knob still follows the
  // finger and it is not reported dead.
  CHECK(![small.pressedItems containsObject:stick.item.identifier] && small.stickVectors[stick.item.identifier] != nil &&
            ![small.inertItems containsObject:stick.item.identifier],
        @"a D-pad stick under its threshold moves its knob without a halo (%@)", Describe(small));
  [tracker moveTouch:@1 x:stick.frame.x + stick.frame.w y:MidY(stick.frame)];
  CHECK([[tracker resolve].pressedItems containsObject:stick.item.identifier],
        @"the same stick lights up once a direction reaches the core");
  // Build 448: one finger drives a stick (Delta). A second finger landing
  // on the held stick is ignored (before: its direction was added, left and
  // right reached the core together).
  [tracker beginTouch:@2 x:stick.frame.x + stick.frame.w * 0.1 y:MidY(stick.frame)];
  LibretroTouchResolution *twoFingers = [tracker resolve];
  CHECK(twoFingers.coreInput.buttons == BIT(RIGHT), @"a second finger on a held stick is ignored (%@)",
        Describe(twoFingers));
  [tracker endTouch:@2];
  [tracker endTouch:@1];
  // Once released, the stick takes the next finger again.
  [tracker beginTouch:@2 x:MidX(stick.frame) y:MidY(stick.frame)];
  [tracker moveTouch:@2 x:stick.frame.x y:MidY(stick.frame)];
  CHECK([tracker resolve].coreInput.buttons == BIT(LEFT), @"a released stick takes the next finger");
  [tracker endTouch:@2];
  // A key reused without an end (lost event) is a new finger, not a
  // second finger on its own stick.
  [tracker beginTouch:@3 x:MidX(stick.frame) y:MidY(stick.frame)];
  [tracker beginTouch:@3 x:MidX(stick.frame) y:MidY(stick.frame)];
  [tracker moveTouch:@3 x:stick.frame.x + stick.frame.w y:MidY(stick.frame)];
  CHECK([tracker resolve].coreInput.buttons == BIT(RIGHT), @"a reused finger key keeps driving the stick");
  [tracker endTouch:@3];
  // The unusable button: drawn, dead, never lit.
  LibretroLaidOutItem *x = LaidOut(layout, [prefix stringByAppendingString:@"item11"]);
  [tracker beginTouch:@1 x:MidX(x.frame) y:MidY(x.frame)];
  LibretroTouchResolution *dead = [tracker resolve];
  CHECK(dead.coreInput.buttons == 0 && dead.pressedItems.count == 0 && dead.inertItems.count == 1 &&
            [dead.contacts.firstObject.inertInputs isEqualToArray:@[ @"x" ]],
        @"a GBA skin's X button is reported dead, not lit (%@)", Describe(dead));
  [tracker endTouch:@1];
  // Converted names are reported for the compatibility diagnostics.
  LibretroSkinItem *run = LaidOut(layout, [prefix stringByAppendingString:@"item6"]).item;
  LibretroSkinItem *diagonal = LaidOut(layout, [prefix stringByAppendingString:@"item9"]).item;
  LibretroSkinItem *plain = LaidOut(layout, [prefix stringByAppendingString:@"item1"]).item;
  CHECK([run.adaptedInputs isEqualToArray:@[ @"run" ]] && [diagonal.adaptedInputs isEqualToArray:@[ @"upLeft" ]] &&
            plain.adaptedInputs.count == 0,
        @"adapted names are recorded per item");
}

#pragma mark - DS touch screen

static void TestTouchScreen(void) {
  Device phone = kDevices[1];
  LibretroSkinLayoutResult *nds = DefaultLayout(@"nds", LibretroSkinOrientationPortrait, phone);
  LibretroTouchTracker *tracker = Tracker(nds, @"nds", nil);
  LibretroLaidOutItem *touch = LaidOut(nds, @"touchScreen");
  CHECK(touch != nil, @"the DS default skin has a touch screen");
  if (touch == nil) return;
  LibretroRect frame = touch.frame;
  [tracker beginTouch:@1 x:MidX(frame) y:MidY(frame)];
  LibretroTouchResolution *centre = [tracker resolve];
  CHECK(centre.pointerPressed && abs(centre.pointerX) < 400 && abs(centre.pointerY - 16383) < 400,
        @"the bottom screen centre is the centre of the bottom half of the core picture (%d, %d)", centre.pointerX,
        centre.pointerY);
  [tracker moveTouch:@1 x:frame.x - 50 y:MidY(frame)];
  LibretroTouchResolution *edge = [tracker resolve];
  CHECK(edge.pointerPressed && edge.pointerX <= -32000, @"a stylus leaving the screen stays on its edge");
  // A second finger elsewhere does not steal the pointer; buttons still work.
  LibretroRect a = LaidOut(nds, @"a").frame;
  [tracker beginTouch:@2 x:MidX(a) y:MidY(a)];
  LibretroTouchResolution *both = [tracker resolve];
  CHECK(both.pointerPressed && both.coreInput.buttons == BIT(A), @"stylus and A together");
  [tracker endTouch:@1];
  LibretroTouchResolution *lifted = [tracker resolve];
  CHECK(!lifted.pointerPressed && lifted.pointerX == edge.pointerX && lifted.coreInput.buttons == BIT(A),
        @"lifting the stylus releases the pointer where it was last seen");
  [tracker endAllTouches];
  // With a controller, the touch screen keeps working.
  tracker.controlsDisabled = YES;
  [tracker beginTouch:@3 x:MidX(frame) y:MidY(frame)];
  CHECK([tracker resolve].pointerPressed, @"controls disabled: the touch screen still works");
}

int main(int argc, const char *argv[]) {
  @autoreleasepool {
    workDirectory = argc > 1 ? @(argv[1]) : NSTemporaryDirectory();
    TestDefaultSkinsSweep();
    TestGestures();
    TestRemapsAndDeadButtons();
    TestOverlaps();
    TestImportedSkin();
    TestTouchScreen();
  }
  if (failures > 0) {
    printf("%d of %d touch tracker check(s) failed\n", failures, checks);
    return 1;
  }
  printf("All %d touch tracker checks passed\n", checks);
  return 0;
}
