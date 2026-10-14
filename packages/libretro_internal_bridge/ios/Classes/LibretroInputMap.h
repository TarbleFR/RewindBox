#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// Three separate layers, as the maintainer asked:
/// 1. logical controls of a console ("a", "start", "leftStickUp",
///    "touchScreen", "menu"...), named with the Delta / Provenance
///    vocabulary;
/// 2. their representation in a skin (LibretroSkinItem.inputs, user touch
///    remaps);
/// 3. their transmission to the libretro core (this class: RetroPad id,
///    analog axis, pointer or frontend action).
///
/// Logical names (canonical, lowerCamelCase):
///   up down left right a b c x y z l r l2 r2 l3 r3 start select mode
///   cUp cDown cLeft cRight
///   leftStickUp leftStickDown leftStickLeft leftStickRight
///   rightStickUp rightStickDown rightStickLeft rightStickRight
///   touchScreen
/// Frontend actions, valid for every console, never sent to the core:
///   menu quickSave quickLoad fastForward toggleFastForward swapScreens
///
/// Per-console tables (logical -> RetroPad; glyph in brackets). Directions
/// up/down/left/right -> JOYPAD UP/DOWN/LEFT/RIGHT everywhere.
///   nes:          a[A]->A  b[B]->B  start[START]->START  select[SELECT]->SELECT
///   gb, gbc:      same as nes
///   gba:          nes + l[L]->L  r[R]->R
///   snes:         gba + x[X]->X  y[Y]->Y
///   md, mcd, 32x: a[A]->Y  b[B]->B  c[C]->A  x[X]->L  y[Y]->X  z[Z]->R
///                 start[START]->START  mode[MODE]->SELECT
///                 (Genesis Plus GX and PicoDrive use the same RetroPad layout)
///   sms, gg, sg1000: b[1]->B  a[2]->A  start[START]->START
///   arcade:       b[1]->B  a[2]->A  y[3]->Y  x[4]->X  l[5]->L  r[6]->R
///                 select[COIN]->SELECT  start[START]->START
///   nds:          snes buttons + touchScreen -> POINTER
///   n64:          a[A]->B  b[B]->Y  z[Z]->L2  l[L]->L  r[R]->R  start[START]->START
///                 cUp/cDown/cLeft/cRight[C▲ C▼ C◀ C▶] -> right analog (y -, y +, x -, x +)
///                 leftStick* -> left analog, rightStick* -> right analog (same as C)
///   psx:          a[○]->A  b[✕]->B  x[△]->X  y[□]->Y  l[L1]->L  r[R1]->R
///                 l2[L2]->L2  r2[R2]->R2  l3[L3]->L3  r3[R3]->R3
///                 start[START]->START  select[SELECT]->SELECT
///                 (digital pad: the core's DualShock analog mode is not selected)
///   psp:          a[○]->A  b[✕]->B  x[△]->X  y[□]->Y  l[L]->L  r[R]->R
///                 start[START]->START  select[SELECT]->SELECT  leftStick* -> left analog
///                 (PPSSPP libretro: Circle=A, Cross=B, Triangle=X, Square=Y)
///   3ds:          a[A]->A  b[B]->B  x[X]->X  y[Y]->Y  l[L]->L  r[R]->R
///                 l2[ZL]->L2  r2[ZR]->R2  start[START]->START  select[SELECT]->SELECT
///                 leftStick* (Circle Pad) -> left analog, rightStick* (C-Stick) -> right analog
///                 touchScreen -> POINTER
///   pce, tg16, pccd, tgcd: b[II]->B  a[I]->A  select[SELECT]->SELECT  start[RUN]->START
///   ws, wsc:      a[A]->A  b[B]->B  start[START]->START
///                 r2[Y1]->R2  r[Y2]->R  l2[Y3]->L2  l[Y4]->L (Beetle WonderSwan's Y pad)
///                 select[⟳]->SELECT (turns the screen for vertical games)
///   ngp, ngpc:    a[A]->B  b[B]->A  start[OPTION]->START (Beetle NeoPop crosses A and B)
///   lynx:         a[A]->A  b[B]->B  l[OPT1]->L  r[OPT2]->R  start[PAUSE]->START
///   vb:           a[A]->A  b[B]->B  l[L]->L  r[R]->R  start[START]->START  select[SELECT]->SELECT
///                 l2[R▲]->L2  l3[R▼]->L3  r2[R◀]->R2  r3[R▶]->R3 (right D-pad)
///   2600:         b[1]->B  select[SELECT]->SELECT  start[RESET]->START
///   7800:         b[1]->B  a[2]->A  select[SELECT]->SELECT  start[PAUSE]->START  x[RESET]->X
///   5200:         a[1]->A  b[2]->B  start[START]->START  select[PAUSE]->SELECT
///                 l[0-9]->L (a5200's on-screen keypad)  y[*]->Y  x[#]->X
///   cv:           b[L]->B  a[R]->A  y[1]->Y  x[2]->X  l[3]->L  r[4]->R
///                 start[*]->START  select[#]->SELECT
///   mini:         a[A]->A  b[B]->B  c[C]->R
///   gw, duck, wsv: a[A]->A  b[B]->B  select[SELECT]->SELECT  start[START]->START
///   ard:          a[A]->A  b[B]->B
///   wasm4:        a[X]->A  b[Z]->B
///   uze:          same as snes
/// Buttons a console's core reads that are not listed (2600 difficulty
/// switches, 5200 and ColecoVision keypad keys beyond these, Pokémon mini
/// shake and power, Lynx rotation) keep their RetroPad id on controllers.
///
/// Blocked RetroPad buttons (never sent, whatever the source): nds R3
/// (DeSmuME "Quick Screen Switch"), 3ds L3 and R3 (Azahar HOME / swap
/// screens and touch tap). Swapping screens inside the core would make
/// NeoStation's fixed screen regions and touch mapping wrong; the frontend
/// action "swapScreens" swaps them on NeoStation's side instead.

typedef NS_ENUM(NSInteger, LibretroInputTargetKind) {
  LibretroInputTargetNone = 0,
  /// RETRO_DEVICE_JOYPAD id in `identifier`.
  LibretroInputTargetButton,
  /// Analog stick `stick` (0 left, 1 right), axis `axis` (0 x, 1 y), sign `sign` (-1 / +1).
  LibretroInputTargetAnalog,
  /// RETRO_DEVICE_POINTER (DS / 3DS touch screen).
  LibretroInputTargetPointer,
  /// Frontend action in `action`.
  LibretroInputTargetAction,
};

typedef NS_ENUM(NSInteger, LibretroFrontendAction) {
  LibretroFrontendActionNone = 0,
  LibretroFrontendActionMenu,
  LibretroFrontendActionQuickSave,
  LibretroFrontendActionQuickLoad,
  LibretroFrontendActionFastForward,        // while held
  LibretroFrontendActionToggleFastForward,  // on press
  LibretroFrontendActionSwapScreens,        // DS / 3DS: swap NeoStation's screen places
};

typedef struct {
  LibretroInputTargetKind kind;
  unsigned identifier;
  unsigned stick;
  unsigned axis;
  int sign;
  LibretroFrontendAction action;
} LibretroInputTarget;

/// Physical GameController elements a user can remap: "buttonA", "buttonB",
/// "buttonX", "buttonY", "leftShoulder", "rightShoulder", "leftTrigger",
/// "rightTrigger", "leftThumbstickButton", "rightThumbstickButton",
/// "buttonOptions", "buttonMenu", "dpadUp", "dpadDown", "dpadLeft",
/// "dpadRight". The two sticks keep their analog meaning and are not
/// remapped.
FOUNDATION_EXPORT NSArray<NSString *> *LibretroGamepadElements(void);

/// RetroPad id NeoStation has always sent for a physical element
/// (positional SNES layout: buttonA -> B, buttonB -> A, buttonX -> Y,
/// buttonY -> X, shoulders -> L / R, triggers -> L2 / R2, thumbstick
/// buttons -> L3 / R3, buttonOptions -> SELECT, buttonMenu -> START, D-pad
/// -> directions). -1 for an unknown element.
FOUNDATION_EXPORT int LibretroGamepadPassthroughButton(NSString *element);

/// Accumulated core input produced by one source (touch or one controller).
typedef struct {
  uint16_t buttons;
  int16_t analog[2][2];
} LibretroCoreInput;

@interface LibretroInputMap : NSObject

/// Map of a NeoStation console id ("nes", "snes", "gb", "gbc", "gba",
/// "md", "mcd", "32x", "sms", "gg", "sg1000", "arcade", "nds", "n64",
/// "psx", "psp", "3ds", then the consoles of lot 1: "pce", "tg16", "pccd",
/// "tgcd", "ws", "wsc", "ngp", "ngpc", "lynx", "vb", "2600", "7800",
/// "5200", "cv", "mini", "gw", "duck", "wsv", "ard", "wasm4", "uze"). An
/// unknown console gets an empty logical table: controllers then use the
/// passthrough mapping only.
+ (instancetype)mapForConsole:(NSString *)console;

/// The 38 console ids above, in this order (LibretroCoreCatalog.consoles).
+ (NSArray<NSString *> *)consoles;

@property(nonatomic, copy, readonly) NSString *console;

/// Logical buttons of the console in display order (no directions, stick
/// directions or actions), e.g. psp -> a b x y l r start select.
@property(nonatomic, copy, readonly) NSArray<NSString *> *buttons;
@property(nonatomic, readonly) BOOL hasLeftStick;   // n64, psp, 3ds
@property(nonatomic, readonly) BOOL hasRightStick;  // 3ds (n64 C buttons are buttons)
@property(nonatomic, readonly) BOOL hasTouchScreen; // nds, 3ds
/// RetroPad bits never sent to the core (see above).
@property(nonatomic, readonly) uint16_t blockedButtons;

/// Product glyph printed on the console for a logical button ("○" for psp
/// "a", "C" for md "c", "ZL" for 3ds "l2", "1" for sms "b"...). Never
/// translated; nil for directions, sticks, touch screen and actions.
- (nullable NSString *)glyphForInput:(NSString *)input;

/// LibretroLocale key of a spoken / translated name when the glyph is not
/// readable by VoiceOver or is a direction: "buttonCircle", "buttonCross",
/// "buttonTriangle", "buttonSquare", "inputUp", "inputDown", "inputLeft",
/// "inputRight", "inputLeftStick", "inputRightStick", "inputTouchScreen",
/// "inputRotateScreen" (WonderSwan select),
/// "inputMenu", "inputQuickSave", "inputQuickLoad", "inputFastForward",
/// "inputToggleFastForward", "swapScreens"; nil when the glyph itself is the
/// name ("A", "L", "START"...).
- (nullable NSString *)labelKeyForInput:(NSString *)input;

/// Canonical logical name for a raw skin input, or nil when this console
/// cannot use it. Aliases (case-insensitive): l1 -> l, r1 -> r,
/// analogStickUp / leftThumbstickUp / leftanalogup -> leftStickUp (and the
/// other directions), rightThumbstickUp -> rightStickUp, cross / circle /
/// square / triangle -> b / a / y / x (psx, psp), c-up / cup / "c up" / "c▲"
/// -> cUp (and the others), rightAnalogUp -> rightStickUp, analogUp ->
/// leftStickUp, run / play -> start, zl / zr -> l2 / r2 (3ds, psx),
/// touchScreenX / touchScreenY -> touchScreen,
/// screenSwap / reverseScreens / swapScreens -> swapScreens,
/// toggleFastForward, fastForward, quickSave, quickLoad, menu. Inputs whose
/// target is blocked for the console (3ds l3 / r3 / home / homeMenu, nds r3)
/// return nil.
- (nullable NSString *)canonicalInput:(NSString *)raw;

/// Same, and `converted` (optional) tells whether the name needed an
/// adaptation beyond Delta's own vocabulary: a Provenance / Manic spelling
/// ("run", "zl", "c up", "rightAnalogUp", PlayStation shape names...) or a
/// stick of a console without one, which drives its D-pad
/// (leftStickUp / analogStickUp -> up on nes, snes, gb, gbc, gba, md, mcd,
/// 32x, sms, gg, sg1000, arcade, nds, psx).
- (nullable NSString *)canonicalInput:(NSString *)raw converted:(nullable BOOL *)converted;

/// Canonical inputs of one raw skin input: a diagonal D-pad token ("upLeft",
/// "up_left", "up-left", "up+left", "leftUp"...) gives its two directions,
/// pressed together; anything else gives canonicalInput: as a one-element
/// array, or an empty array when this console cannot use it. `converted`
/// as above (always YES for a diagonal token).
- (NSArray<NSString *> *)canonicalInputs:(NSString *)raw converted:(nullable BOOL *)converted;

/// Transmission to the core. Unknown names give LibretroInputTargetNone.
- (LibretroInputTarget)targetForInput:(NSString *)input;

/// Adds one active logical input to `state`. Buttons are OR-ed. Analog
/// targets set their axis to sign * magnitude * 0x7fff, where `magnitude`
/// is in [0, 1] (0 is treated as 1, full deflection). Actions and pointer
/// are ignored here. Blocked buttons are never set.
- (void)applyInput:(NSString *)input magnitude:(double)magnitude toState:(LibretroCoreInput *)state;

/// Logical input a physical element sends by default for this console, i.e.
/// the logical input whose RetroPad target equals
/// LibretroGamepadPassthroughButton(element); nil when the console has no
/// logical input for that id (the element then passes its historical
/// RetroPad id through, so core functions such as Nestopia's FDS disk side
/// on L keep working) or when that id is blocked.
- (nullable NSString *)defaultInputForGamepadElement:(NSString *)element;

/// Final target of a physical element: the user's override {element:
/// logical input or action} when valid, else the default logical input,
/// else the passthrough RetroPad id; LibretroInputTargetNone when that id is
/// blocked.
- (LibretroInputTarget)gamepadTargetForElement:(NSString *)element
                                     overrides:(nullable NSDictionary<NSString *, NSString *> *)overrides;

@end

NS_ASSUME_NONNULL_END
