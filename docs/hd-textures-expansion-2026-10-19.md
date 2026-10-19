# Catalogue de textures HD — expansion (objectif 800+) et Nintendo 64, 19 octobre 2026

Demande du mainteneur (19 octobre 2026) : étendre massivement le catalogue unifié de textures HD de la Build 486 (objectif 800 packs distincts, réels, vérifiés et crédités, idéalement installables en un geste), sur la seule branche `Claude`, sans système parallèle, sans réhébergement, sans contourner une protection d'hébergeur ni créer une entrée fictive ; étudier la Nintendo 64 (Mupen64Plus-Next), la NES, la PS1 et la Dreamcast ; outiller la découverte et le contrôle des liens ; aucune release, rien sur `main`.

Inventaire généré (packs, auteurs, conditions, vérification, exclusions) : [`HD_TEXTURE_CATALOG_SOURCES.md`](HD_TEXTURE_CATALOG_SOURCES.md). Architecture de la Build 486 : [`build486-hd-textures-catalogue.md`](build486-hd-textures-catalogue.md).

## 1. Résultat

Révision `__REVISION__` (index hébergé `native/textures/catalogue/manifest.json.gz`, copie embarquée identique octet pour octet) :

| | Build 486 | Maintenant |
|---|---:|---:|
| Packs distincts | 170 | __PACKS__ |
| En un geste (fichier de l'auteur téléchargé, installé et contrôlé ici) | 144 | __ONETAP__ |
| Lien manuel (page de l'auteur) | 26 | __MANUAL__ |
| Identifiants de jeux distincts | 171 | __IDS__ |
| Sources (dépôt GitHub ou page d'un créateur) | 128 | __SOURCES__ |
| Auteurs crédités | 149 | __AUTHORS__ |

__TABLE__

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
- **Packs** : 19 packs GLideN64 PNG en un geste (GhostlyDark « Reloaded », Mario Kart 64, F-Zero X, Zelda, Banjo, Conker…), plus 2 archives de dépôt (Super Mario 64 polices et tableaux, Space Station Silicon Valley) vérifiées par le job `repositories` (§ 6). Les applications 486/487 ignorent ces packs (système inconnu, rejet pack par pack) : ils n'apparaissent qu'avec la Build 488.

## 4. Plateformes étudiées et non ouvertes

- **NES** : les « HD Packs » sont une fonction de Mesen, non embarqué ; Nestopia ne les lit pas (sonde `cores`) : exclus.
- **PS1** : Beetle PSX HW épinglé (`10e4b0c`) sait suivre et remplacer des textures, mais l'option est décrite par ses auteurs comme instable (« Will probably crash in most games ») et le journal 456 montre le rendu logiciel sur l'iPhone ; aucune preuve d'exécution matérielle : non proposé.
- **Dreamcast** : Flycast n'est pas embarqué (JIT requis).
- **PPSSPP Basis Universal** (`.basis`, Naruto Impact, Ys Seven) : non lu par le PPSSPP embarqué : exclus.

## 5. Contrôle des liens et mise à jour sans IPA

- `discover.py links` (job `links`) : pour chaque pack, page et parties de téléchargement (statut, taille annoncée), nouvelle release GitHub ; une requête par URL, au plus une par seconde et par hôte ; un hôte qui refuse un contrôle automatique (401, 403, 429, 503) est noté « refusé », jamais contourné. Résultat : __LINKS__.
- Le catalogue reste hors ligne (index embarqué, dernier index valide conservé) ; l'index hébergé sur `Claude` est rafraîchi par l'application sans nouvelle IPA : les packs PS2, GameCube, Wii, PSP et 3DS ajoutés atteignent les Builds 486 et 487 installées ; seuls les packs N64 demandent la Build 488.

## 6. Vérifications

__CHECKS__

## 7. Limites

- Aucun pack chargé dans un jeu ni installé sur un iPhone dans ce cycle.
- Les 668 packs manuels ne sont pas téléchargés par NeoStation : l'utilisateur suit la page du créateur (conditions, version, hébergeur) puis importe l'archive depuis Fichiers ; 334 entrées ps2ktxpak demandent une confirmation de l'édition.
- Archives de dépôt GitHub : taille et SHA-256 mesurées le 19 octobre 2026 ; une archive régénérée différemment serait refusée, jamais installée, jusqu'à la mise à jour de l'index hébergé.
- Les sources inaccessibles depuis le conteneur (forums, GameBanana, Google, Reddit…) n'ont pas été explorées directement.
