# Wiimmfi — contre-expertise du 27 novembre 2026

Périmètre relu : `cecc0117`, branche `Claude`, trois revues indépendantes en lecture seule et vérification par l’intégrateur. Aucun jeu, dump NAND réel, clé ou identifiant de console utilisé.

| Défaut confirmé | Correction |
| --- | --- |
| Fusion de `setting.txt` de l’ancienne NAND avec les nouvelles clés | Exclusion des titres système de la fusion ; `setting.txt` importé conservé et requis au contrôle structurel |
| Base Mii actuelle remplacée par celle du dump | Conservation explicite de `shared2/menu/FaceLib`, ancêtres/descendants sans liens, copie vérifiée |
| Table de contenus TMD pas validée avant lecture des certificats | `TMDReader::IsValid()` et identité IOS13 exigés avant les getters |
| En-tête C++ exposé à l’importeur Swift/Objective-C | `DOLWiimmfi.h` déclaré privé dans le podspec |
| Patches mémoire locaux `[OnFrame]` actifs malgré cheats désactivés | En ligne, seules les valeurs amont par défaut sont chargées ; fichier joueur intact |
| WiiConnect24 utilisait libcurl hors des barrières IP | Refus avant ordonnanceur, mail, téléchargement et inscription hors ligne |
| Capture PCAP et journaux amont pouvaient conserver des identifiants | PCAP désactivé pour la session ; valeurs de série/ID retirées des quatre messages identifiés sur iOS |
| Refus global des modifications bloquait l’auto-routage du secouement | Exception limitée à Wii, joueur 1, axes Shake X/Y/Z |
| Boutons des propriétés contournaient le routeur de lancement | Passage par `GameLaunchService` : politique moteur, médias, session et historique |
| Empreinte du nouveau script omise de l’identité producteur | `dolphin_wiimmfi.py` ajouté à `source_inputs` et à la clé de cache |

La nouvelle ABI Wiimmfi **3** distingue ce cœur corrigé du candidat ABI 2 non livré. Aucun manifeste de livraison antérieur n’est modifié.

## Vérifications

- Reproduction synthétique avant/après de l’import : identité importée, sauvegarde du jeu actuelle et Mii actuels conservés ensemble après correction ; ancien snapshot conservé.
- 24 tests Flutter existants réussis ; test transactionnel renforcé avec `setting.txt` et Mii. Analyse Dart ciblée : aucun problème ; `pubspec.lock` inchangé.
- Patcher appliqué sur une source amont propre `7cac54161659421ed95c2cd1c0b0746539a4cd38`.
- Validateur FST/FAT réel : 1 cas valide et 16 refus/annulation sous ASan/UBSan ; LeakSanitizer désactivé uniquement sur l’hôte Linux sous traceur.
- Barrières IP existantes : 27 requêtes ×100 réussies ; contrôles cycle de vie et gestionnaire de cheats réussis.
- Nouvelles barrières WiiConnect24, politique OnFrame, PCAP et routage Shake : code effectivement patché relu indépendamment ; comportement réseau réel sur appareil non testé.
- Compilation iPhoneOS du cœur corrigé : en attente du producteur existant. Le bridge UIKit complet et l’application n’ont pas été compilés ici.

## Limites maintenues

La revue confirme des défauts réels de la première intégration ; elle ne démontre pas de panne serveur ni de bannissement observé. Les anciens tests ne couvraient pas `setting.txt`, les Mii, WiiConnect24 ou le circuit applicatif des boutons.

L’intégration demeure expérimentale : patch automatique certifié, ECC/HMAC, authenticité Nintendo, vraie NAND et authentification/matchmaking public/privé restent non validés. Aucun gain CPU/RAM/thermique revendiqué, aucune IPA produite. Le contrôle structurel n’atteste pas l’authenticité de la console.
