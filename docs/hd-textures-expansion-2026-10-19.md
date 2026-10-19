# Catalogue de textures HD — expansion (objectif 800+) et Nintendo 64, 19 octobre 2026

Demande du mainteneur (19 octobre 2026) : étendre massivement le catalogue unifié de textures HD de la Build 486 (objectif 800 packs distincts, réels, vérifiés et crédités, idéalement installables en un geste), sur la seule branche `Claude`, sans système parallèle, sans réhébergement, sans contourner une protection d'hébergeur ni créer une entrée fictive ; étudier la Nintendo 64 (Mupen64Plus-Next), la NES, la PS1 et la Dreamcast ; outiller la découverte et le contrôle des liens ; aucune release, rien sur `main`.

Inventaire généré (packs, auteurs, conditions, vérification, exclusions) : [`HD_TEXTURE_CATALOG_SOURCES.md`](HD_TEXTURE_CATALOG_SOURCES.md). Architecture de la Build 486 : [`build486-hd-textures-catalogue.md`](build486-hd-textures-catalogue.md).

## 1. Résultat

Révision `2026-10-19.72e26f767470` (index hébergé `native/textures/catalogue/manifest.json.gz`, copie embarquée identique octet pour octet) :

| | Build 486 | Maintenant |
|---|---:|---:|
| Packs distincts | 170 | 857 |
| En un geste (fichier de l'auteur téléchargé, installé et contrôlé ici) | 144 | 189 |
| Lien manuel (page de l'auteur) | 26 | 668 |
| Identifiants de jeux distincts | 171 | 910 |
| Sources (dépôt GitHub ou page d'un créateur) | 128 | 275 |
| Auteurs crédités | 149 | 298 |

| Console | Build 486 (un geste / manuel) | Maintenant (un geste / manuel) | Identifiants de jeux |
|---|---:|---:|---:|
| PlayStation 2 (ARMSX2) | 44 / 11 | 44 / 652 | 53 → 761 |
| GameCube (Dolphin) | 23 / 1 | 28 / 1 | 19 → 22 |
| Wii (Dolphin) | 20 / 2 | 23 / 2 | 11 → 14 |
| PSP (PPSSPP) | 54 / 3 | 68 / 4 | 72 → 85 |
| Nintendo 3DS (Azahar) | 8 / 9 | 10 / 9 | 20 → 21 |
| Nintendo 64 (Mupen64Plus-Next) | — | 21 / 0 | 0 → 11 |

Un pack servant les disques GameCube et les titres Wii Virtual Console est compté pour les deux consoles . Ajoutés : 687 packs (45 en un geste dont 21 N64, 642 liens manuels dont 637 ps2ktxpak) ; retirés : aucun.

Aucun pack n'a été retiré ; aucun doublon n'a été publié (deux entrées installant les mêmes fichiers d'un même téléchargement sont refusées par le générateur, les miroirs et copies sont exclus, § 4).

**Ce qui est vérifié, et ce qui ne l'est pas.** Un pack *en un geste* a été téléchargé depuis le lien de son auteur, reconnu comme ZIP ou 7z, installé avec le code de production de l'application et contrôlé comme le moteur le lit (noms `tex1_`, `textures.ini`, `pack.json`, noms Rice de GLideN64, PNG intègres) ; taille et SHA-256 sont dans l'index. Un pack *manuel* n'est qu'un lien vers la page de son créateur : son archive n'a pas été téléchargée ici. **Aucun pack n'a été chargé dans un jeu** dans ce cycle : « archive et installation vérifiées, rendu non testé ».

## 2. Sources exploitées

- **GitHub** (dépôts, releases, sujets, code) : outil `tools/textures/discover.py` exécuté par le job `discover` de `hd-textures.yml` (runs `39245687230`/`39245691110`, résumé par le run `39256854044` : 132 dépôts lisibles par un moteur). Chaque candidat a été revu à la main (arbre, README, licence, identifiants, structure) avant d'être écrit dans `tools/textures/sources/` ; les autres sont dans `excluded.json` avec leur raison.
- **ps2ktxpak** ([`ps2ktxpak/catalog`](https://github.com/ps2ktxpak/catalog), commit `807733e5`, licence MIT, « ARMSX2's PS2 texture pack catalogue ») : catalogue revu par ses mainteneurs qui recense les packs PS2 des créateurs (fils GBAtemp, listes Google, pages personnelles) avec titre, numéros de série, créateurs, page principale, coût d'accès, permission et état d'hébergement. `tools/textures/import_ps2ktxpak.py` en tire **637 entrées manuelles** : seulement les packs gratuits, crédités, avec une page d'annonce du créateur (jamais un hébergeur de fichiers ni un miroir), absents du catalogue ; numéros de série du créateur, sinon de la PCSX2 GameIndex (`091ab687`) par titre exact, alors marqués « à confirmer » (334 packs). Écartés et comptés dans `tools/textures/ps2ktxpak-report.json` : payants 204, coût non renseigné 78, sans série ni titre GameIndex 83, déjà présents 7, sans page d'annonce 5, créateur absent 2, doublon 1, série inconnue 1. Le texte MIT de ps2ktxpak est livré avec le catalogue (`packages/neo_texture_catalog/ios/Resources/ps2ktxpak-LICENSE.txt`) et cité dans l'inventaire ; les packs restent la propriété de leurs créateurs.
- **Forums, GameBanana, ModDB, Google Drive/Docs/Sites, Reddit, EmuTalk, n64textures.com** : inaccessibles depuis le conteneur de travail (politique de sortie) ; rien n'en est tiré directement et la politique n'a pas été contournée. Ils sont représentés seulement par les fiches revues de ps2ktxpak (PS2). Le job `links` (runners GitHub) vérifie que ces pages répondent (§ 5).

## 3. Nintendo 64 — Mupen64Plus-Next (GLideN64)

- **Preuve technique** : sources `libretro/mupen64plus-libretro-nx` (GLideNHQ compilé pour toutes les plateformes, options `mupen64plus-txHiresEnable`, `-txHiresFullAlphaChannel`, `-EnableEnhancedHighResStorage`, dossier `<système libretro>/Mupen64plus/hires_texture/<nom ROM>/`, noms Rice `<nom>#<crc>#<fmt>#<siz>[#<palette>]_<suffixe>.png`) et binaire iOS épinglé (`LibretroCores-fdeaef56…`, run `38638115521`) sondé par `tools/textures/probe_cores.py` (job `cores`, run `39251651918`) : options et marqueurs présents.
- **Adaptateur** (`packages/neo_texture_catalog`, aucun cœur reconstruit) : identité `n64-rom-name-hex` lue dans l'en-tête de la ROM (`.z64`, `.v64` octets permutés, `.n64` petit-boutiste ; nom en hexadécimal car l'index n'admet que `[A-Za-z0-9-]`), filtre exact de GLideN64 (`.png`/`.bmp` sensibles à la casse, `#` obligatoire, dossiers cachés et `~!~` ignorés), détection du dossier du jeu dans une archive (et refus d'un pack pour une autre ROM), installation dans le dossier du nom de ROM, interrupteur par jeu dans `Config/Games/Mupen64Plus-Next.json` (`mupen64plus-txHiresEnable` = `True`/`False`, avec `-txHiresFullAlphaChannel` et `-EnableEnhancedHighResStorage` = `True` à l'activation), ligne « Textures HD » du menu en jeu Mupen64Plus-Next et rangée de la bibliothèque. Les packs de cache HTS/HTC ne sont pas proposés (exclus avec raison).
- **Cache de GLideNHQ** (défaut trouvé dans les sources avant toute livraison) : au premier démarrage avec un pack, GLideNHQ lit et décode tout le dossier puis écrit `<système>/Mupen64plus/cache/<nom ROM>_HIRESTEXTURES.hts` (stockage fichier, option « enhanced Hi-Res storage » : textures décodées sur disque plutôt qu'en mémoire) ou `.htc` (cache mémoire sauvegardé, `-EnableTextureCache`, activé par défaut) ; ensuite il recharge ce fichier dès que ses options concordent, **sans relire le pack** (`TxHiResCache`, `TxCache::load`), et le charge même quel que soit le réglage quand le dossier du pack n'existe plus. Une mise à jour, un remplacement ou une suppression seraient donc restés sans effet. Le magasin appelle désormais `-didChangePackFolder:` après chaque installation, remplacement, import ou suppression réussi ; l'adaptateur N64 supprime alors ces deux fichiers pour ce seul nom de ROM (test Foundation : caches du jeu supprimés, cache d'un autre jeu conservé). La page signale que le premier démarrage après un pack nouveau ou mis à jour lit tout le pack et peut être long (texte dans les douze langues).
- **Packs** : 21 packs GLideN64 PNG en un geste pour 11 identifiants de ROM : 19 assets de release vérifiés dans le conteneur (GhostlyDark « Reloaded » pour Banjo-Kazooie, Banjo-Tooie, GoldenEye 007, Mario Kart 64, Majora's Mask, Ocarina of Time, Super Mario 64, Super Smash Bros., Resident Evil 2, Mario Craft 64, F-Zero X, etc.) et 2 archives de dépôt vérifiées sur CI (run `39264550682` : polices et tableaux de Super Mario 64 par Fanfreluche, 172 textures ; Space Station Silicon Valley HD par JappaWakka, 194 textures). BK Reloaded est à sa dernière version v0.2.1 (2 871 textures). Les applications 486/487 ignorent ces packs (système inconnu, rejet pack par pack) : ils n'apparaissent qu'avec la Build 488.

## 4. Plateformes étudiées et non ouvertes

- **NES** : les « HD Packs » sont une fonction de Mesen, non embarqué ; Nestopia ne les lit pas (sonde `cores`) : exclus.
- **PS1** : Beetle PSX HW épinglé (`10e4b0c`) sait suivre et remplacer des textures, mais l'option est décrite par ses auteurs comme instable (« Will probably crash in most games ») et le journal 456 montre le rendu logiciel sur l'iPhone ; aucune preuve d'exécution matérielle : non proposé.
- **Dreamcast** : Flycast n'est pas embarqué (JIT requis).
- **PPSSPP Basis Universal** (`.basis`, Naruto Impact, Ys Seven) : non lu par le PPSSPP embarqué : exclus.

## 5. Contrôle des liens et mise à jour sans IPA

- `discover.py links` (job `links`) : pour chaque pack, page et parties de téléchargement (statut, taille annoncée), nouvelle release GitHub ; une requête par URL, au plus une par seconde et par hôte ; un hôte qui refuse un contrôle automatique (401, 403, 429, 503) est noté « refusé », jamais contourné. Résultat : run `39259632196` (858 entrées, 829 URL) : **aucun pack en un geste cassé** (161 à jour, 30 signalés « version plus récente »). Revue des 30 : seule BK Reloaded avait réellement une version plus récente (v0.2.1, revérifiée) ; les autres sont des dépôts épinglés à leur tête (plus récente que leurs tags de release) ou des dépôts dont la dernière release concerne un autre pack (PokeTex XY, mod de difficulté de Pokémon Y Resurrection, version PCSX2 de MK Deception). Packs manuels : 28 pages accessibles, 7 avec une release plus récente (MK Armageddon renvoie désormais vers la dernière release, v1.6), **632 pages gbatemp.net refusent le contrôle automatique (HTTP 403)** : ni contournées ni comptées comme cassées — leur accessibilité n'est donc pas vérifiée ici..
- Le catalogue reste hors ligne (index embarqué, dernier index valide conservé) ; l'index hébergé sur `Claude` est rafraîchi par l'application sans nouvelle IPA : les packs PS2, GameCube, Wii, PSP et 3DS ajoutés atteignent les Builds 486 et 487 installées ; seuls les packs N64 demandent la Build 488.

## 6. Vérifications

Exécutées dans le conteneur de travail (Linux, sans SDK Apple ni Flutter) : identités (40 images synthétiques, dont `.z64`/`.v64`/`.n64` et noms refusés), installation (67 vérifications, dont filtres et détection GLideN64), libellés (12 langues, 158 clés natives et 4 Flutter ; 147 vérifications de couverture), porte de l'IPA (13 refus, dont notice ps2ktxpak absente ou modifiée et adaptateur N64 absent), `build_catalogue.py --check` ; vérification réelle des assets de release (dont les 19 packs N64 et BK Reloaded v0.2.1) avec le code d'installation de l'application.

Sur CI (`hd-textures.yml`) :

- **Archives de dépôt** : runs `39254972220` (12 packs, dont Project Mirai DX refusé : deux PNG endommagés), `39257349302` (9), `39258904471` (Ridge Racers 2), `39264550682` (les deux packs N64) ; `check_ci_records.py` compare les 88 enregistrements d'archives de dépôt aux artefacts de leurs runs.
- **Run complet `39265084257` sur `f4834ce5`** (Xcode 26.3, Flutter 3.47.2), toutes les parties réussies :
  - host (job `118102460207`) : 46 vérifications (libellés, catalogue `2026-10-19.72e26f767470`, enregistrements CI, archives, identités, installation, porte de l'IPA, contrats existants, `flutter analyze` — 3 remarques non bloquantes — et 86 tests Dart) ; les neuf contrats `PRE_EXISTING` échouent à l'identique sur la base `dc653f12` ;
  - native (job `118102461270`) : test Foundation du magasin et des adaptateurs avec la section N64 (identité, filtres, installation, options du jeu, caches GLideNHQ supprimés pour ce seul nom de ROM à l'installation et à la suppression), pod compilé et lié pour iPhone (8 sources), page Textures HD exécutée dans le menu Graphismes ARMSX2, pont libretro lié pour iPhone (77 objets), commandes tactiles, natif unifié ;
  - uikit (job `118102459992`) : sept tests de la page dans le Simulateur, dont `testNintendo64UsesGLideN64OptionsOfTheGame` (pack proposé pour la ROM, pas celui d'un autre jeu, interrupteur écrivant les options du jeu).
- **Discover / links / cores** : runs `39245687230`, `39260093158` (N64), `39256854044` (résumé), `39259632196` (liens), `39251651918` (cœurs).

Aucune de ces vérifications n'affiche une texture dans un jeu.

## 7. Limites

- Aucun pack chargé dans un jeu ni installé sur un iPhone dans ce cycle.
- Les 668 packs manuels ne sont pas téléchargés par NeoStation : l'utilisateur suit la page du créateur (conditions, version, hébergeur) puis importe l'archive depuis Fichiers ; 334 entrées ps2ktxpak demandent une confirmation de l'édition.
- Archives de dépôt GitHub : taille et SHA-256 mesurées le 19 octobre 2026 ; une archive régénérée différemment serait refusée, jamais installée, jusqu'à la mise à jour de l'index hébergé.
- Les sources inaccessibles depuis le conteneur (forums, GameBanana, Google, Reddit…) n'ont pas été explorées directement.
