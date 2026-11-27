# Wiimmfi — contre-expertise du 27 novembre 2026

Périmètre relu : `cecc0117`, branche `Claude`, revues indépendantes ciblées en lecture seule et vérification par l’intégrateur. Aucun jeu, dump NAND réel, clé ou identifiant de console utilisé.

| Défaut confirmé | Correction |
| --- | --- |
| Fusion de `setting.txt` de l’ancienne NAND avec les nouvelles clés | Exclusion des titres système de la fusion ; `setting.txt` importé conservé et requis au contrôle structurel |
| Base Mii actuelle remplacée par celle du dump | Conservation explicite de `shared2/menu/FaceLib`, ancêtres/descendants sans liens, copie vérifiée |
| Table de contenus TMD pas validée avant lecture des certificats | `TMDReader::IsValid()` et identité IOS13 exigés avant les getters |
| En-tête C++ exposé à l’importeur Swift/Objective-C | `DOLWiimmfi.h` déclaré privé dans le podspec |
| Patches mémoire locaux `[OnFrame]` actifs malgré cheats désactivés | En ligne, seules les valeurs amont par défaut sont chargées ; fichier joueur intact |
| WiiConnect24 utilisait libcurl hors des barrières IP | Requêtes planifiées et explicites refusées avant tout appel HTTP hors ligne |
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
- Cœur final ABI 3 compilé : source `a660c337`, [run 45977483996](https://github.com/TarbleFR/RewindBox/actions/runs/45977483996), SHA-256 `e4811001…3346250`. Archive téléchargée et empreintes comparées ; prédicat de confidentialité défini dans le Mach-O. [Identité complète et preuves](wiimmfi-counteraudit-2026-11-27.json). Le bridge UIKit complet et l’application n’ont pas été compilés ici.

## Dernière revue des parcours

- Protection iOS/exclusion de sauvegarde cloud étendue aux NAND actuelle et historiques avant renommage ; aucun snapshot supprimé. La revue a trouvé une absence de protection, pas une fuite observée.
- Causes Wiimmfi traduites conservées dans le circuit normal de lancement ; les refus restent explicites.
- Diagnostic : état NAND relu à la demande et affiché, cache de cinq minutes réservé au réseau ; clés d’images normalisées dans le panneau.
- Dix tests Wiimmfi existants revérifiés après ces seuls changements Flutter, dont les appels de protection des snapshots via bridge simulé (attributs iOS réels non vérifiés) ; analyse Dart sans problème. Aucun nouveau changement de logique de jeu depuis `a101ee24`.

- Contrats CI adaptés sans retirer de contrôle : import BootMii explicitement relié au garde global de stockage ; extraction Dart du test de lancement compatible avec les paramètres nommés. Les 25 contrôles de stockage et les 15 scénarios existants de lancement réussissent. Les autres routes moteur ne sont pas modifiées.
- Deux échecs historiques du workflow Touch restent distincts : ancienne release donneuse `0.0.1` introuvable et assertion d’affichage incompatible avec un import présent avant Wiimmfi. Ils ne démontrent pas une régression de ce lot ; l’application iOS complète reste non compilée ici.

- Le contrôle global Libretro révèle aussi trois échecs antérieurs au lot : tests de rotation des journaux sur un ancien chemin, variable `invalid` non déclarée dans son bridge natif, artefact de cores ancien introuvable (run `45975249078`). Aucun de ces fichiers moteur n’a été modifié pour Wiimmfi.

Dernier complément natif : les logs texte/hexadécimaux HTTP, IPC et OSReport peuvent contenir des données sensibles indépendamment des captures PCAP. Pendant Wiimmfi, les deux entrées du journal interne Dolphin sont donc suspendues sur iOS ; les diagnostics JSON contrôlés RewindBox restent disponibles. Aucun réglage persistant, TLS ou comportement du jeu n’est modifié ; journaux internes rétablis à l’arrêt. Les vrais corps des deux entrées passent 100 cycles : aucun formatage de sortie ni appel aux listeners dans les corps testés en ligne, reprise hors ligne ; les arguments peuvent être construits avant ces gardes, aucun gain CPU démontré. Le run `45975248905` est remplacé par `45977483996`. Les 35 avertissements du Core sont inchangés ; deux avertissements du banc hôte ont été corrigés en séparant les unités comme dans le produit, puis contrôle réussi avec `-Werror` (banc corrigé non réexécuté sur Apple, code du Core inchangé).

## Limites maintenues

La revue confirme des défauts réels de la première intégration ; elle ne démontre pas de panne serveur ni de bannissement observé. Les anciens tests ne couvraient pas `setting.txt`, les Mii, WiiConnect24 ou le circuit applicatif des boutons.

L’intégration demeure expérimentale : patch automatique certifié, ECC/HMAC, authenticité Nintendo, vraie NAND et authentification/matchmaking public/privé restent non validés. Aucun gain CPU/RAM/thermique revendiqué, aucune IPA produite. Le contrôle structurel n’atteste pas l’authenticité de la console.
