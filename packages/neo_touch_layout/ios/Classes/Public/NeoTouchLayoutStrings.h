// SPDX-License-Identifier: GPL-3.0-or-later
#import <Foundation/Foundation.h>

NS_ASSUME_NONNULL_BEGIN

/// The twelve NeoStation locales (en, fr, de, es, it, pt, ru, id, ja, ko, zh, zh_Hant).
FOUNDATION_EXPORT NSArray<NSString*>* NeoTouchLayoutLocales(void);
/// One of the twelve locales for an app locale identifier ("zh_Hant" for
/// Traditional Chinese, "en" when the language is not supported).
FOUNDATION_EXPORT NSString* NeoTouchLayoutCanonicalLocale(NSString* _Nullable identifier);
FOUNDATION_EXPORT NSDictionary<NSString*, NSString*>* NeoTouchLayoutTextsForLocale(NSString* _Nullable locale);
/// Translated text of the touch-controls editor and of the in-game menu rows.
FOUNDATION_EXPORT NSString* NeoTouchLayoutText(NSString* key, NSString* _Nullable locale);

NS_ASSUME_NONNULL_END
