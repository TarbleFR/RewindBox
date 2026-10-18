# Catalogue de cheats NeoStation

`manifest.json.gz` est le point d’entrée unique. L’application télécharge les packs référencés, vérifie SHA256 et tailles, puis extrait les fichiers de jeux. L’IPA embarque uniquement le même manifeste compressé ; aucun pack ni code n’est activé automatiquement.

Le schéma est versionné dans `tools/cheats/unified-schema.json`. Les entrées de transport portent `identity_group`, `part` et `parts` : plusieurs parties ne sont pas plusieurs jeux. `totals.programs` compte les programmes dédupliqués dans leurs groupes d’identité, avant duplication des dépendances nécessaires dans les parties. Ce nombre ne prétend pas mesurer des effets uniques ni des jeux commerciaux uniques.

`SOURCES.md` décrit les contributions actives et la portée de chaque référence. `ADAPTATIONS.md` décrit les essais de conversion et les exclusions. `audit.json.gz` garde les diagnostics et les 70 références historiques ; il ne fait pas partie du téléchargement fonctionnel.

## Régénération

Depuis la racine du dépôt :

```sh
python tools/cheats/unified_catalogue.py build \
  --sources tools/cheats/unified-sources.json \
  --output native/cheats/catalogue \
  --cache /chemin/vers/cache
python tools/cheats/unified_catalogue.py validate --input native/cheats/catalogue
python -m unittest discover -s test -p 'test_unified_cheat_*.py' -q
```

Les entrées sont épinglées par version et SHA256. `--offline` exige les fichiers du cache. `--reuse-normalised --refresh-sources libretro,mister` permet une itération ciblée sur un snapshot SQLite existant ; une régénération complète reste la référence lors d’un changement global des règles. La génération copie les mêmes octets du manifeste dans `packages/neo_cheat_catalog/ios/Resources/manifest.json.gz` et retire les anciens packs devenus inutiles.

## Identités et exécution

Une identité contient `type`, `scheme` et `value`. Deux empreintes ne se comparent que sous le même schéma. Par exemple, `rom-full`, `ines-prg-chr`, `nes-prg`, `snes-headerless`, `bsnes-cartridge`, `n64-big-endian` et `r4-header512-crc32-inverted` ne sont pas interchangeables. `source_identities` distingue des éditions de publication dont le domaine de calcul n’est pas attesté ; ce champ ne prouve jamais l’identité d’une ROM.

Les titres sans empreinte complète restent des éditions candidates à confirmer. Les contraintes de région, langue et révision sont conservées. Chaque programme garde ses lignes ordonnées, son dialecte, sa provenance, ses paramètres et sa fermeture de dépendances. Un programme conditionnel n’est jamais scindé pour rentrer dans une limite.

Les MD5 XML dont le domaine n’est pas attesté conservent le schéma `openemu-md5-unspecified` et exigent la confirmation d’édition. Ils ne sont jamais assimilés automatiquement aux empreintes brutes, sans en-tête ou déinterlacées.

`activation_profiles` impose un core précis quand un programme utilise une voie particulière, par exemple PicoDrive. `mgba_auto_isolated` interdit la coactivation avec un autre enregistrement GBA hors canal VBA : les preuves du décodeur AUTO portent sur une fermeture entière isolée, ses états de chiffrement étant partagés. Les groupes exclusifs restent des contraintes d’exécution.

Le statut publié `available` signifie programme complet accepté par un adaptateur documenté et ses limites. Il ne signifie pas que chaque effet a été joué et vérifié sur un appareil physique. Les preuves de parseur, de mémoire et de décodeur restent décrites séparément.

## Build 475 update

The inventory now includes the additional GoW3 01.00 source and two narrow adaptations of existing Artemis inputs. Exact scopes and counts: [`docs/unified-cheats-direct-build475.md`](../../../docs/unified-cheats-direct-build475.md). After regeneration, run `tools/cheats/unified_stable_packs.py` with the documented Build 474 baseline to retain immutable transport packs. Explicit `retired` members are checked by size/hash and excluded from current games and program totals. The native reader installs only each pack's assigned `game_ids`; superseded payloads are never offered as current cheats.
