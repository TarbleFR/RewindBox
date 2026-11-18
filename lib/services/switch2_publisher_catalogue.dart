/// Publisher references keyed by the base program ID. Artwork is fetched
/// from Nintendo on demand, and belongs to the original rights holders.
abstract final class Switch2PublisherCatalogue {
  static const _fireEmblem = '04007ef01f8ae000';
  static const _fireEmblemTitle = "Fire Emblem: Fortune's Weave";
  static const _fireEmblemMedia =
      'https://www.nintendo.com/eu/media/images/assets/nintendo_switch_2_games/fireemblemfortunesweave';

  static String? title(String? programId) =>
      programId?.trim().toLowerCase() == _fireEmblem ? _fireEmblemTitle : null;

  static Map<String, dynamic>? gameInfo(String? programId) {
    if (title(programId) == null) return null;
    return const {
      'noms': [
        {'region': 'wor', 'text': _fireEmblemTitle},
      ],
      'synopsis': [
        {'langue': 'fr', 'text': 'Au bord de la ruine, l’Empire de Dagda compte sur quatre héros. Remontez le temps pour réunir leurs alliés et dirigez-les dans des combats tactiques au tour par tour.'},
        {'langue': 'en', 'text': 'Travel into Dagda’s past, gather allies across four heroes’ stories, and lead them in turn-based tactical battles to avert the empire’s ruin.'},
      ],
      'dates': [
        {'region': 'wor', 'text': '2026-09-17'},
      ],
      'genres': [{
        'noms': [
          {'langue': 'fr', 'text': 'RPG tactique'},
          {'langue': 'en', 'text': 'Tactical RPG'},
        ],
      }],
      'developpeur': {'text': 'Intelligent Systems'},
      'editeur': {'text': 'Nintendo'},
      'joueurs': {'text': '1'},
      'medias': [
        {
          'type': 'box-2D', 'format': 'webp', 'region': 'jp',
          'url': 'https://www.nintendo.com/jp/games/switch2/aacsa/products/assets/img/software_img_package.webp',
        },
        {
          'type': 'fanart', 'format': 'jpg', 'region': 'eu',
          'url': '$_fireEmblemMedia/16x9_NSwitch2_FireEmblemFortunesWeave_image1280w.jpg',
        },
        {
          'type': 'ss', 'format': 'jpg', 'region': 'fr',
          'url': '$_fireEmblemMedia/fireemblemfortunesweave_pagecontent_/captures/FEFW_Screenshots_CaiCrits_FR.jpg',
        },
      ],
    };
  }
}
