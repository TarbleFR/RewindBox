# Build 440 — cadrage et répartition (11 octobre 2026)

Demande du mainteneur du 11 octobre 2026, branche `Claude`. Six
fonctions, plus la validation, puis deux ajouts du même jour (bouton
retour des lecteurs, suppression des sources depuis Fichiers). Le
mainteneur a livré entre-temps, depuis une autre session, la Build 438
(adaptation mémoire NeoSwap/MeloNX pour RPCS3) et la Build 439 (comptage
des dons NeoSwap, `2b1c0dea`). À sa demande (« la 439 est finie, tu peux
faire par-dessus »), cette candidate est la **Build 440**, construite sur
`origin/Claude` `2b1c0dea` et à installer par-dessus la 439. Ce document
fixe les décisions prises après l’analyse et les limites de chaque paquet
de travail. Les rapports d’analyse détaillés restent hors dépôt ; chaque
paquet écrit son propre document `docs/…`.

## Décisions

### A. Dolphin Wii « Secouer »

- Le bouton tactile « Secouer » presse la secousse de la Wiimote seule
  (Touchscreen 132–134 du profil Touch, déjà liées à Shake X/Y/Z). Le
  Nunchuk n’est pas concerné.
- Appui maintenu : la secousse dure tant que le doigt est posé, avec un
  minimum de 120 ms au relâchement normal (un tap ou VoiceOver produit une
  secousse détectable). Relâchement immédiat sur annulation du toucher,
  pause, passage en arrière-plan et fermeture du jeu.
- Bouton ajouté par code (les nibs du donneur ne changent pas), ancré
  au-dessus de la colonne droite. Pas d’option afficher/masquer.
- Manette : une ligne « Secouer » dans le menu Commandes en jeu (Wii
  uniquement) assigne un bouton aux trois axes par l’API de liaison
  existante, avec retour arrière en cas d’échec ; la branche
  écran tactile + téléphone du joueur 1 reste en place. Les profils
  existants ne sont pas réécrits. GameCube inchangé.
- Interdits : `DolphinSessionMenu.h`, `packages/dolphin_internal_bridge/core/`,
  `build-utils/patch_dolphin_internal_core_v2.py`,
  `native/dolphin_motion/strings.json`, les nibs et DolphinCore. Les
  nouveaux textes viennent du catalogue Dart (`dolphin_shake_locale.dart`)
  transmis par les libellés de session.

### B. Licences RAP (RPCS3)

- Entrée « Importer des licences RAP » dans le menu Importer existant de la
  bibliothèque PS3, après l’import de dossier. Anglais : « Import RAP
  licenses ».
- Sélection multiple par le sélecteur ouvert sur place existant
  (`Rpcs3InternalBridge.pickGameFilesOpenInPlace` /
  `releaseScopedResources`), extension `.rap` en toute casse.
- Format RPCS3 : 16 octets, nom = Content ID de 36 caractères
  (`XXYYYY-ZZZZZZZZZ_00-…`), le suffixe de doublon « (n) » ajouté par
  Fichiers est retiré. Installation dans
  `…/RPCS3/Data/dev_hdd0/home/00000001/exdata/<CONTENT_ID>.rap`
  (extension minuscule, ID en majuscules, comme le lit le cœur épinglé).
- Même contenu déjà présent : « déjà présente ». Contenu différent sous le
  même ID : demande unique, puis remplacement avec copie de l’ancienne dans
  `NeoStation/RPCS3/RapBackups` ; refus = conservé et signalé. Garde
  `Data/vfs.yml` si `dev_hdd0` est redirigé.
- Rapport par fichier : importée / remplacée / déjà présente / refusée
  (motif). Aucune tuile de jeu, aucun `onLibraryChanged`, imports existants
  intacts.

### C. Onglet consoles de la barre principale

- Icône console avec « + », juste après la première icône et avant la
  recherche, mêmes styles et états que les autres onglets. Toujours visible
  sur iOS (non masquable).
- Corps de l’onglet : la page des consoles intégrées en mode barre
  principale (consoles disponibles et déjà ajoutées, ajout au menu
  principal, import, actions de bibliothèque, habillages). Un doublon se
  juge par console matérielle (Mega Drive et Genesis comptent comme la même
  console). Rafraîchissement immédiat, persistance, ordre et réglages des
  consoles existantes conservés. Pas d’action « retirer » : le masquage
  reste dans Réglages › Systèmes. Une console dont le cœur manque dans
  l’IPA apparaît indisponible.
- « Consoles intégrées » quitte Réglages › Dossiers : le fichier revient
  octet pour octet à la version revue `a5650b9b`.

### D. Interface 120 Hz

- Réglages › Général, iOS uniquement, « Interface 120 Hz », description
  « Améliore la fluidité des menus et du défilement sur les écrans
  compatibles. ». Activé par défaut (comportement de la 437), appliqué au
  prochain lancement.
- La clé `CADisableMinimumFrameDurationOnPhone` est déjà à YES dans toutes
  les IPA : l’option agit par un nouveau plugin `packages/ui_refresh_rate`
  qui remplace `+[FlutterDisplayLinkManager displayRefreshRate]` (activé :
  valeur d’origine ; désactivé : min(valeur, 60)). Préférence
  `NeoStation.UI.HighRefreshRate.Enabled` lue une fois par processus.
  Aucun moteur d’émulation n’est touché.
- Écran sans ProMotion ou moteur Flutter sans ce point d’accroche : état
  « non disponible ». Mesure passive par `FrameTiming`, y compris au retour
  d’un jeu, plus une action « Mesurer » bornée (~1,5 s). Jamais de 120 Hz
  annoncé sans mesure.
- La cloche de notifications ne pulse plus sans notification (boucle de
  rendu au repos supprimée). Les autres animations restent inchangées.

### E. Vérificateur de BIOS

- Réglages › Outils › « BIOS / Vérificateur de BIOS » (iOS), page
  `lib/screens/libretro/libretro_bios_checker_screen.dart`, données
  `assets/data/libretro_bios_requirements.json` tirées des `.info`
  libretro (core-info `5a74858a`), de System.dat (`f206bf65`), de la
  documentation libretro et des sources des cœurs.
- Strictement en lecture : aucune écriture hors du cache de hachage
  (`Library/Caches/Libretro/bios-check-v1.json`). Seul lien d’import : le
  flux existant « Copier les sauvegardes et BIOS de RetroArch ».
- La règle de lancement PS1 de NeoStation ne change pas ; le vérificateur
  la rapporte telle quelle (indication de renommage le cas échéant). Un BIOS
  optionnel manquant ne bloque jamais un lancement.
- BIOS conditionnels (Mega-CD, FDS, BS-X, Sufami, 64DD, Neo Geo) : comptés
  « manquant obligatoire » seulement si la bibliothèque contient des jeux du
  système concerné, sinon « manquant optionnel » avec la condition affichée.
- Jeux FBNeo de consoles que NeoStation n’envoie pas à FBNeo : non listés
  (exclusion motivée dans le JSON). « Invalide » seulement par un contrôle
  prouvé (vide, illisible, trop court, en-tête, CRC de membres essentiels).

### F. Réglages RetroArch

- Paramètres du jeu › Émulateur : la ligne « Application RetroArch
  (externe) » n’est plus proposée. Un jeu déjà réglé ainsi garde son
  réglage, affiché comme « réglage précédent » jusqu’au choix d’un cœur
  (aucune migration des préférences).
- Paramètres du système : « RetroArch embarqué » (nom demandé par le
  mainteneur ; le sous-titre nomme le cœur) dans le même style que
  DolphiniOS, ARMSX2, RPCS3 et Dusklight, avec Habillages, Vérificateur de
  BIOS et un rappel des réglages du menu en jeu. Les systèmes sans cœur
  intégré gardent la ligne de l’application RetroArch.
- Les textes qui présentaient l’application RetroArch comme nécessaire sont
  reformulés (carte RetroArch de Réglages › Dossiers, assistant iOS,
  message de relance) sans toucher au fichier verrouillé des dossiers.

### G. Bouton retour des lecteurs (ajout du 11 octobre)

- Demande : « ajoute un bouton retour en arrière pour la lecture des
  livres […] car c’est compliqué de sortir et revenir dans le menu
  précédent ». La flèche de retour n’existait que dans la barre du haut,
  masquée au bout de 4 s et après chaque page ; `lib/main.dart`
  (verrouillé) impose des transitions sans balayage de retour iOS.
- Un seul contrôle de retour à la fois : la flèche de la barre quand elle
  est affichée, sinon un petit bouton flottant au même endroit (zone
  sûre, 44 × 44 pt, couleurs du thème du lecteur), dans les trois lecteurs.
  Il passe par la fermeture existante (sauvegarde de la position,
  orientation). Pas de geste de bord (conflit avec le tournage des pages).
  Voir `docs/library-reader-back-button-build440.md`.

### H. Sources de la Bibliothèque dans Fichiers (ajout du 11 octobre)

- Demande : supprimer les sources manuellement depuis les dossiers de
  NeoStation ; « les gens doivent les trouver par eux-mêmes ». Choix du
  mainteneur : chaque source installée (hors sources natives) a un fichier
  dans Fichiers › NeoStation › Library › Sources ; supprimer le fichier
  retire la source. L’app n’affiche aucun bouton, lien, chemin ni message
  sur ce dossier, et le README n’en parle pas.
- Aucune source n’est retirée sur une erreur de lecture, ni au premier
  lancement après la mise à jour. Supprimer tout le dossier retire les
  sources dont NeoStation avait écrit le fichier. Progression, favoris,
  catalogues et livres sont conservés. Voir
  `docs/library-source-files-build440.md`.

## Paquets et fichiers partagés

Chaque paquet travaille dans son propre arbre et ne modifie que ses
fichiers. Fichiers partagés :

- `lib/l10n/libretro_locale.dart` (C, E, F) : nouvelles clés seulement à la
  fin de chacune des douze cartes, sans réordonner ; valeur existante
  modifiée seulement pour les clés du paquet. Fusion par union à
  l’intégration.
- `test/localization_12_locale_coverage_test.py` (A, B, D, F) : ajout du
  catalogue du paquet dans la liste, rien d’autre.
- `test/neoplay_build397_integration_test.py` (C, E) : modifications
  minimales et locales.
- Réservés à l’intégration : `AGENTS.md`,
  `build-utils/verify_delivery_reuse.py` (`BUILD440_DELTA`, CRLF),
  `.github/workflows/retroarch-delivery.yml`,
  `.github/workflows/libretro-checks.yml`,
  `native/import-memory-candidate.json`. Chaque paquet indique les tests à
  ajouter aux workflows.
- Points d’accroche déjà posés : `UiRefreshRateService.instance.startProbe()`
  dans `AppScreen.initState` et la classe `LibretroBiosCheckerScreen`
  (`console` optionnel), remplacés par leurs paquets.

## Validation

Tests Dart et Python sur Windows pour chaque paquet, revue indépendante,
puis contrôles natifs macOS par `workflow_dispatch --ref Claude`
(dolphin-motion-check, ui-refresh-rate-check, libretro-checks) et livraison
`retroarch-delivery.yml` avec `build_number=440`. Les comportements sur
iPhone restent à confirmer par le mainteneur.

## Résultats et livraison (11 octobre 2026)

Windows (Flutter 3.47.2, Python 3.12), arbre intégré avant renumérotation :
suite Flutter complète, 1 838 réussis et 29 échecs, tous déjà présents sur
`origin/Claude` (la référence en compte 30 : le test RPCS3 du menu d’import
est réparé). Après rebase sur `2b1c0dea` : 391 tests ciblés et 735 tests
`library_*` réussis (seul échec : le test Windows connu
`library_scan_restart`), contrats Python verts, `flutter analyze` sans
erreur ni avertissement.

| Contrôle | Run | Révision | Résultat |
|---|---|---|---|
| `retroarch-delivery.yml` (checks, native, cold) | `38161126590` | `cbd0ff01` | réussi |
| `libretro-checks.yml` | `38161113820` | `cbd0ff01` | réussi |
| `ui-refresh-rate-check.yml` | `38161174475` | `1bc0edf8` | réussi |
| `dolphin-motion-check.yml` | `38161120708` | `cbd0ff01` | échec du harnais (CoreGraphics non lié au paquet XCTest) |
| `dolphin-motion-check.yml` | `38161934907` | `0913f260` | réussi, simulateur compris |
| `dolphin-pacing-check.yml` | `38161122592` | `cbd0ff01` | bloqué avant ses tests par le verrou NeoSwap |
| `cheats-media-check.yml` | `38161124298` | `cbd0ff01` | bloqué avant ses tests par le verrou NeoSwap |

`1bc0edf8` et `0913f260` ne diffèrent de `cbd0ff01` que par
`.github/workflows/ui-refresh-rate-check.yml` et le harnais
`test/dolphin_touch_shake_ui_test.py` : aucune entrée de l’application ne
change. Le verrou NeoSwap (`test/import_memory_candidate_scope_test.py`,
appelé par `check_neo_swap_scope.py` et `cheat_bulk_scope_test.py`) refuse
`assets/legal/THIRD_PARTY_NOTICES.md` et `docs/LEGAL_AND_CREDITS.md` depuis
`08145438` (crédits des habillages), avant ce cycle ; il n’est pas modifié
ici.

IPA livrée : `NeoStation-Build440-cbd0ff0124a4af7a34d1b10b3e22e0991d7d5e64-cold.ipa`,
artefact chiffré `NeoStation-Build-440-cbd0ff0124a4af7a34d1b10b3e22e0991d7d5e64-cold`,
SHA-256 `13070ac3434a25289b3a1ecf25903c19340fb331dc6a184eef1be752398531b4`,
207 202 787 octets, version 0.0.2 (440), signature ad hoc de préparation
(re-signature Apple par SideStore requise). Vérifié après déchiffrement :
empreinte identique à `SHA256SUMS` et à `signed-payload-identity.json`,
marqueurs Secouer Wii dans `dolphin_internal_bridge`, préférence et canal
120 Hz dans l’exécutable Runner (aucun `ui_refresh_rate.framework` séparé),
données BIOS dans les ressources Flutter. Aucun essai sur iPhone.
