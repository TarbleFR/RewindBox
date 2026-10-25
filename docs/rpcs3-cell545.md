# RPCS3 545 — correctifs publics d'ARMSX3 22528 (25 octobre 2026)

Demande : porter dans le Core RPCS3 de RewindBox les correctifs absents et
utiles des notes de version d'ARMSX3 22528-eef0dc9c. `eef0dc9c` est une build
iOS privée : il ne résout aucun commit public d'`ARMSX2/ARMSX3`. Seuls des
commits publics sont portés, de préférence depuis RPCS3 amont, dont ils
proviennent pour la plupart. Base : delta canonique 543 (cœur `d3689eb2`,
identités PPU/SPU `a987639e9f838d1c` / `d070cb361bdef607`), propriété transmise
par la session RPCS3 543.

## 1. Classement des points de la note

| Point de la note | Source publique | Décision |
| --- | --- | --- |
| Cache SPU : plus gros programmes d'abord, doublons ignorés | RPCS3 `d3ef196ff`, `4cf9ad1e7` | **Porté.** Utile pour God of War III, dont le profil RewindBox recompile les blocs SPU enregistrés à chaque lancement |
| Paquets d'installation personnalisés | ARMSX3 `471b57b36` (sur RPCS3 `36eaed481`, `c4d834480`) | **Porté.** Notre `unpkg.cpp` n'avait aucun contrôle : une entrée `../` était écrite hors du dossier d'installation, n'importe où dans le conteneur de l'app |
| Homebrew et jeux signés pour CFW par le chemin debug | RPCS3 `b77d4a520`, `8dc93f2e0`, `4e078e07a` | **Porté** (vérifié par la compilation du Core, pas par un fichier SELF réel) |
| — | RPCS3 `a321a0a18` | **Porté** : borne `iv_idx < key_count` du déchiffreur SCE (lecture hors tampon possible) |
| Sauvegardes d'état (fichiers ouverts puis supprimés) | RPCS3 `d1d0cbcce` | **Porté** : la position du fichier était insérée au milieu de son contenu, et un indice hors tampon était utilisé une fois des données écrites sur disque |
| — | RPCS3 `76d4c4565` (#19905) | **Porté** : `cellSaveData` limite `fileNum`/`sizeKB` pour les SDK ≤ 2.6 ou `fileListMax` 0 |
| Journaux SPU allégés | RPCS3 `e53ac18f8` | **Déjà présent** : désassemblage et IR produits seulement s'ils sont journalisés |
| — | RPCS3 `0dec46b12` | **Porté** : un tampon de 50 000 octets n'est plus alloué à chaque ligne de journal |
| Mémoire locale effacée avant compilation | — | **Déjà présent** (`clear_warmup_local_store`, sur toute la fonction) |
| Cache de shaders écrit d'un seul tenant ; cache pipeline réécrit seulement s'il a grandi | — | **Déjà présent** (542 et 543) |
| Blocs mémoire graphique de 64 Mio | — | **Déjà couvert** par la politique 508 (tas iOS > 4 Gio) |
| Réécriture du MFC shuffling, réglage « MFC Shuffle Instructions Decrementer » | RPCS3 `08f58134c`… `6110dbb27` | **Non porté** : option activée par ARMSX3 pour Sonic Generations seulement, sans réglage RewindBox ; change le schéma de configuration |
| Attentes mailbox/signal, `write_snr` ralenti, délai MMIO RawSPU | RPCS3 `4f8625b9b`, `3a3ba6139`, `9418abd51`, `d86d677f2`, `e3c4a1367`, `d4c52a8d4` | **Non porté** : change la synchronisation SPU de tous les jeux, God of War III compris, sans preuve RewindBox ; à mesurer dans une build dédiée |
| Réseau (masque, route, files P2P) | RPCS3 `e3e6bec6d`, `dd63e706a` | **Non porté** : RewindBox n'a pas RPCN |
| Patchs de jeux (Tales of Graces f, J-Stars, Blitz…) | `canary_patches.yml` de l'app Android | **Non porté** : contenu d'application, pas du code Core |
| Sauvegardes sur un stockage qui refuse de renommer | ARMSX3 `d1c845f57` | **Non porté** : stockage partagé Android ; le conteneur iOS renomme |
| Sortie LiveContainer/Nyxian, état refusé, redémarrage après état disque, pool d'images, shader endommagé, Raw SPU, licence Sonic Mania, UI licences | — | **Non portable** : build iOS privée, aucune source |

## 2. Changement de cache SPU sans recompilation

`SPUCommonRecompiler.cpp` fait partie de l'empreinte SPU : le modifier
recompilerait une fois tous les jeux. Le changement ne touche que l'ordre et la
déduplication de la liste de préchauffage ; chaque programme passe par le même
analyseur et le même traducteur. `JITCacheCompatibility.cmake` associe donc ce
fichier exact à l'empreinte 543, comme en 538 pour `JITLLVM.cpp`. La fonction
CMake réelle, exécutée par `cache_identities`, confirme PPU `a987639e9f838d1c` et
SPU `d070cb361bdef607`.

## 3. Tests

`test/rpcs3_cell545_test.py` copie les corps de production du Core 545 et
reconstruit ceux du 543 depuis `test/fixtures/rpcs3_cell545.diff`. ASan+UBSan et
assertions de bornes de la bibliothèque standard
(`docs/evidence/rpcs3-cell545-local.json`) :

- PKG : 9 cas de noms et 5 noms de dossier ; avec le 543, une entrée
  `../../../../Library/Preferences/app.plist` aboutit à
  `/Library/Preferences/app.plist`.
- Préchauffage SPU : 592 enregistrements → 400 compilations, aucune perte, plus
  gros d'abord ; le 543 en compile 592.
- Sauvegarde d'état : quatre cas corrects ; le 543 produit une disposition
  invalide sans écriture préalable et un indice hors tampon après.
- `cellSaveData` 5/5, tampon de journal (0 allocation pour 1 000 lignes contre
  1 000), borne SCE.
- Tests de source des builds 264 à 499, préchauffage SPU, 435 et 444 : réussis
  sur l'arbre 545. Le delta régénéré se rematérialise à l'identique sur un
  checkout vierge de l'amont.

Aucun test sur iPhone, aucun gain de FPS revendiqué.

## 4. Livraison privée 545

IPA cumulative : hôte 542 validé, correctifs MeloNX de fermeture (544), Core
RPCS3 545. Elle s'installe par-dessus la 543 ou la 544 (même identifiant
d'application, numéro supérieur). Aucune release, aucun tag, aucune fusion vers
`main`.
