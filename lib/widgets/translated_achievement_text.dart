import 'package:achievement_translation/achievement_translation.dart';
import 'package:flutter/material.dart';
import '../l10n/achievement_translation_locale.dart';

/// Read-only adapter used by every Flutter achievement title/description site.
/// A title carries the provenance notice once; paired descriptions do not repeat it.
class TranslatedAchievementText extends StatelessWidget {
  const TranslatedAchievementText({super.key, required this.id, required this.title,
    required this.description, this.showDescription = false, this.style,
    this.maxLines, this.overflow, this.textAlign, this.client});
  final int id;
  final String title;
  final String description;
  final bool showDescription;
  final TextStyle? style;
  final int? maxLines;
  final TextOverflow? overflow;
  final TextAlign? textAlign;
  final AchievementTranslationClient? client;

  @override
  Widget build(BuildContext context) {
    final provider = client ?? AchievementTranslationClient.shared;
    return ListenableBuilder(listenable: provider, builder: (context, _) {
      final text = provider.text(AchievementSource(id: id, title: title, description: description));
      final note = showDescription ? null : AchievementTranslationLocale.notice(text, provider.language);
      final label = Text(showDescription ? text.description : text.title, style: style,
        maxLines: maxLines, overflow: overflow, textAlign: textAlign);
      if (note == null) return label;
      return Column(mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: textAlign == TextAlign.center ? CrossAxisAlignment.center : CrossAxisAlignment.start,
        children: [label, Text(note, style: (style ?? DefaultTextStyle.of(context).style).copyWith(
          fontSize: (style?.fontSize ?? 12) * 0.8, fontWeight: FontWeight.normal),
          textAlign: textAlign)],
      );
    });
  }
}
