# Tri de l'amont S2Arm pour le lot 825

- **Plage examinée :** de notre épingle `6b6a5715` (v0.2.5+125, 9–10 novembre) à `eca18550d`, tête de `main` du 23 novembre. Cela fait 8 359 commits, dont 4 664 hors fusions, en trois semaines. L'IPA S2Arm fournie par l'utilisateur est la v0.6.9 (`S2ACommit` = `72018836e`, 22 novembre), à 30 commits de la tête.
- **Méthode :**
  - les commits ont été répartis en huit tranches selon les fichiers touchés : moteur graphique ×2, shaders et pipelines, runtime ×2, services et compatibilité, code iOS du moteur, préparation et outils ;
  - chaque tranche a été comparée, en lecture seule, à notre arbre 0001–0312 ;
  - pour chaque commit retenu : lecture du diff, recherche d'un équivalent dans nos patchs, `git apply --check`.
- **Ce qui est exclu d'office :** Android et OpenHarmony (y compris la relecture Vulkan `graphics/nvn/replay`), lanceurs PC, macOS, Windows, interface de l'app S2Arm, chaîne d'empaquetage PC. Environ 1 400 commits ne touchent que ces parties.

## Ports ciblés plutôt qu'une montée de l'épingle

- **Ce que représente notre série :** 60 865 lignes ajoutées en 312 patchs, dont 226 touchent `nvn_mtl.m`.
- **Ce qu'a changé l'amont dans le même temps :**
  - `nvn_mtl.m` : +5 779 / −874 ;
  - `vawin.c`, `pack_apply.c`, `thread.c`, `svc_mem.c` : de +746 à +1 408 lignes chacun ;
  - de nouveaux sous-systèmes : instantanés, relecture Vulkan, pipelines hybrides.
- **Pourquoi une montée n'est pas raisonnable maintenant :** il faudrait rebaser chaque patch et revalider sur iPhone ce qui marche aujourd'hui, notamment le gouverneur mémoire, le cache sur l'appareil, le park et la reprise. Plusieurs défauts amont contredisent aussi nos choix mesurés :
  - instantanés actifs par défaut ;
  - mode de débordement de la mémoire invitée, mesuré comme nuisible par 0052 ;
  - prise de cœur différée active par défaut ;
  - interpolation d'images MetalFX par défaut à 30 image/s.
- **La voie retenue :** des ports ciblés, chacun en patch propre sur notre série, avec son test.

## Intégré dans ce lot

| Patch | Commits amont | Effet | Validation |
|---|---|---|---|
| 0312 | `5863a69cf`, `cb6853c50` (clé), `50f032a62` | Textures partagées : clé normalisée, orphelines gardées tant qu'un identifiant les lit | CI : test C pur, compilation iOS |
| 0314 | `864e92cf1` | Une écriture de stencil ne force plus une nouvelle copie de la profondeur | CI : test C pur, tests GPU |
| 0316 | `cbf37ad7d` | Tas de compteurs construit même avec le fil d'encodage : moins de soumissions quand le GPU est occupé | CI : tests GPU (compilation) |
| 0317 | `892454c0e`, `464e19898`, `9e2a24ed4` (partie hors instantanés), `185de53d7`, `bdaf69d07`, `b56e1c8b0`, `59f257104`, `08fd71f8a`, `6b1a22267`, `8d1bae402` (décodeur) | Stabilité du runtime, détaillée ci-dessous | CI : tests du runtime |

Détail du patch 0317 :

- **Défaut de page en concurrence.** Un défaut de page que personne ne réclame est ré-exécuté si la page est déjà accessible, au plus 8 fois de suite. L'amont l'a vu en SIGBUS sur 4 jeux, dont un jeu de course first-party.
- **Attente de synchronisation.** `WaitSynchronization` épingle les événements dès l'entrée : un événement dont la poignée est fermée pendant l'attente n'arrête plus le jeu en fin de vidéo (2001-0114). Notre 0157 rendait ce cas systématique.
- **Fuites au park et à la reprise.** Le démontage de session s'exécute sous un pool d'autorelease, et les textures fantômes sortent du jeu de résidence.
- **`MapMemory`** repasse par une copie sur `EACCES`.
- **Alignement de pile.** Des « bouts feuille » réalignent la pile sur 16 octets avant la libc et les 189 fonctions NVN laissées sur la pile du jeu. Coût annoncé par l'amont : +0,5 ns par appel, sur les fils du jeu.
- **`SetHeapSize`** met x1 à 0 en cas d'échec.
- **Paires exclusives « far ».** Une paire avec `xzr` est maintenant émulée au lieu de faire planter (SIGSEGV).
- **Décodeur vidéo.** Gardes contre un `malloc` NULL.

Les tranches encore en cours de lecture complètent ce document.
