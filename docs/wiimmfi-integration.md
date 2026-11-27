# Wiimmfi dans Dolphin — 27 novembre 2026

[Contre-expertise et correctifs ABI 3](evidence/wiimmfi-counteraudit-2026-11-27.md) : source finale `a660c337`, identité/Mii, TMD, protections réseau/journaux et circuit de lancement revus. [Core final compilé et vérifié](https://github.com/TarbleFR/RewindBox/actions/runs/45977483996), SHA-256 `e4811001…3346250` ; [identité complète](evidence/wiimmfi-counteraudit-2026-11-27.json). Les preuves ABI 2 ci-dessous décrivent le premier candidat, remplacé avant toute livraison.

## Périmètre et identité

Branche `Claude`, DolphiniOS `7cac54161659421ed95c2cd1c0b0746539a4cd38` inchangé ; adaptation RewindBox du lecteur BootMii et du bridge. Le cœur livré jusqu’à l’IPA 847 reste celui de 608 (`640e4389…ddd6fc`). La nouvelle ABI Wiimmfi est optionnelle : une ancienne version refuse l’activation. Aucun autre moteur ni Nextendo modifié ; aucune IPA demandée ou produite.

| Fonction | Implémentation et preuve | Validation iPhone |
| --- | --- | --- |
| BootMii | Importeur Dolphin natif, tailles 0x21000000/0x21000400, clés séparées 0x400 ; progression pages/entrées, annulation | Non testée sur vraie NAND |
| Fichiers malformés | Lectures/écritures/flush contrôlés, FST/FAT bornées, cycles/traversées/collisions de casse refusés ; ASan/UBSan hôte | Non testée |
| Sauvegardes | Extraction dans un stage vide privé, sauvegardes des jeux et Mii actuels conservés ; identité/réglages console issus du dump ; SHA-256 de copie, ancien snapshot conservé et rollback testé | Non testée |
| Identité | ID Dolphin par défaut refusé, présence/tailles des credentials vérifiées, protection des fichiers iOS et exclusion des sauvegardes cloud | Authentification serveur non testée |
| Préparation jeu | Déclaration utilisateur d’image préparée officiellement ; ID/région/révision DiscIO + SHA-256 complet revérifié au lancement ; originaux intacts | Patch de sécurité non certifié |
| Session | JIT/Metal/ownership existants ; cheats/états/modifications du menu et captures de payload réseau bloqués, horloges nominales `CurrentRun`, vitesse réellement mesurée | Course non testée |
| Hors ligne | ABI 3 : réseau IP IOS Wii et requêtes WiiConnect24 bloqués hors ligne ; banc IP/IOCTL/IOCTLV/création de socket : 27 requêtes ×100 sans activité hôte ; gardes WiiConnect24 relus, non exécutés par ce banc | Non testé |
| Interruptions | Menu sans pause du guest, arrêt arrière-plan et perte/changement Wi-Fi/cellulaire, aucune reconnexion automatique | Non testées |
| Interface | Wii → paramètres système → Émulateurs → Wiimmfi ; propriétés du jeu → Gérer ; 12 langues, désactivé par défaut | Non testée |
| Réseau | Diagnostic explicite DNS/site HTTPS avec TLS normal, cache 5 min, aucun poll réseau désactivé | Ni auth ni matchmaking prouvés |

## Limites explicites

- ECC/HMAC du dump et authenticité cryptographique Nintendo non certifiées. « Structure reconnue » ne signifie jamais « authentifié ».
- Aucun patch automatique certifié : WIT générique ne démontre pas le bootstrap/updater MKW. Port WSTRT à auditer séparément ; aucun payload tiers redistribué.
- `wiimmfi.de/stat`, `/patcher`, `/error` refusés par HTTP 403 durant la recherche ; les neuf candidats restent non vérifiés, compteurs joueurs et serveurs inconnus, jamais zéro inventé.
- Le diagnostic ne lit pas le protocole Nintendo WFC. Les codes saisis restent visibles et renvoient à la documentation officielle ; le jeu demeure l’autorité pour ses erreurs.
- Aucune mesure comparative CPU/RAM/thermique ni preuve de salon public/privé sur iPhone 16 Pro Max. Un manque de vitesse est affiché, sans prétendre empêcher tout bannissement.
- Une session interrompue est arrêtée ; la reconnexion se fait depuis le jeu après relance. Le monitor détecte les interfaces/disponibilité, pas chaque changement de point d’accès Wi-Fi.

## Vérifications et compilation

Flutter 3.47.2 avec `pubspec.lock` inchangé ; analyse ciblée sans problème, 10 tests Wiimmfi et 14 tests historiques import/menu Wii réussis. Le banc NAND exécute le vrai corps du validateur avec une arborescence valide et 16 cas hostiles/annulation ; aucune donnée de console. LeakSanitizer indisponible sous le traceur Linux de cette session ; ASan/UBSan exécutés avec `detect_leaks=0` seulement en local. CI Apple garde ses options ordinaires.

Premier candidat cœur/bridge : `d473517b` (ABI 2), remplacé par la contre-expertise ABI 3. Producteur existant : [45972261314](https://github.com/TarbleFR/RewindBox/actions/runs/45972261314), source `b4ea094f` ; la première compilation ABI 1 a réussi mais ne valide pas le blocage hors ligne. [Résultats et empreintes](evidence/wiimmfi-2026-11-27.json). Compilation de ce premier candidat réussie : cœur arm64 et adaptateur d’import avec le SDK iPhoneOS, exports vérifiés et framework archivé ; 35 avertissements amont identiques, aucun nouveau. Le bridge UIKit complet et l’application ne sont pas compilés/livrés ici. Il ne fabrique aucune IPA. Le manifeste de livraison précédent reste intact ; le nouveau framework devra être sélectionné et authentifié dans la prochaine livraison autorisée.

## Protocole exact sur iPhone

1. Installer une future IPA autorisée contenant **à la fois** ce Flutter/bridge et le nouveau cœur ; la version déjà installée ne reçoit pas ces changements par un push Git.
2. Fermer toute session Dolphin. Ouvrir **Wii → Paramètres système → Émulateurs → Wiimmfi** ; confirmer l’import puis choisir votre `nand.bin` BootMii, avec `keys.bin` si séparé.
3. Vérifier la fin de l’import et retrouver votre sauvegarde Wii actuelle. « Structure reconnue » ne valide pas l’identité côté Wiimmfi ; ne pas utiliser l’identité d’une autre console.
4. Importer votre copie de Mario Kart Wii préparée avec le patcher officiel actuel. Dans **Propriétés du jeu → Gérer → Wiimmfi**, déclarer cette image après lecture de la confirmation ; activer Wiimmfi, puis **Lancer avec Wiimmfi**. Le pairing/JIT et Local Dev VPN habituels restent nécessaires.
5. En Wi-Fi, sélectionner Nintendo WFC dans le jeu ; noter le code exact et respecter tout délai serveur. Vérifier votre profil et code ami, rejoindre de vrais adversaires et terminer une course publique complète ; répéter en salon privé avec un ami.
6. Observer la vitesse réelle pendant les courses. Arrêter en cas de vitesse durablement insuffisante. Refaire le parcours après déconnexion/reconnexion, arrière-plan, relance et changement Wi-Fi/cellulaire ; vérifier le profil conservé et l’absence de boucle automatique.
7. Désactiver Wiimmfi, relancer hors ligne, vérifier sauvegarde/réglages/triches antérieurs, puis un jeu GameCube. Comparer deux séquences identiques (en ligne/hors ligne) pour CPU, mémoire et chauffe. Ne transmettre aucun dump, clé ni identité dans les journaux.

Sources : [NAND Dolphin](https://dolphin-emu.org/docs/guides/nand-usage-guide/), [importeur épinglé](https://github.com/OatmealDome/dolphin-ios/blob/7cac54161659421ed95c2cd1c0b0746539a4cd38/Source/Core/DiscIO/NANDImporter.cpp), [WSTRT](https://github.com/Wiimm/wiimms-szs-tools/blob/master/project/src/lib-staticr.c), [Wiimmfi](https://wiimmfi.de/).
