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
| 0317 | `892454c0e`, `464e19898`, `185de53d7`, `08fd71f8a`, `6b1a22267`, `8d1bae402` (décodeur) ; les bouts feuille (`bdaf69d07`, `b56e1c8b0`, `59f257104`) et le nettoyage de session (`9e2a24ed4`) ont été retirés après l’échec du run 45161270894 | Stabilité du runtime, détaillée ci-dessous | CI : tests du runtime |

Détail du patch 0317 :

- **Défaut de page en concurrence.** Un défaut de page que personne ne réclame est ré-exécuté si la page est déjà accessible, au plus 8 fois de suite. L'amont l'a vu en SIGBUS sur 4 jeux, dont un jeu de course first-party.
- **Attente de synchronisation.** `WaitSynchronization` épingle les événements dès l'entrée : un événement dont la poignée est fermée pendant l'attente n'arrête plus le jeu en fin de vidéo (2001-0114). Notre 0157 rendait ce cas systématique.
- **Fuites au park et à la reprise.** Retiré après l’échec du run 45161270894, à réexaminer.
- **`MapMemory`** repasse par une copie sur `EACCES`.
- **Alignement de pile.** Retiré après l’échec du run 45161270894, à réexaminer.
- **`SetHeapSize`** met x1 à 0 en cas d'échec.
- **Paires exclusives « far ».** Une paire avec `xzr` est maintenant émulée au lieu de faire planter (SIGSEGV).
- **Décodeur vidéo.** Gardes contre un `malloc` NULL.

- 0318 (`d2a28bf43`, `0b8145a6b`, `73e4b57ce`, `1dc3dd611`, `a8918d7eb`, `344609653`, `9ca83e5b1`, `905e91390`) :
  - contexte caméra sans appareil : l'amont avait vu Mario Kart World s'arrêter juste après cet appel dans 5 sessions sur 5, sur iPad ;
  - une erreur GPU de mémoire épuisée ne met plus de programmes en quarantaine permanente, ce qui donnait des scènes noires dans les sessions suivantes ;
  - fuite du pool de mesures audren ; boucle amiibo qui occupait un cœur entier ; polices lues d'un bloc (des millions d'appels système à chaque lancement) ; export du diagnostic par blocs ;
  - runtime (`2b1a56ca9` + `39b877abd`, `b2eb9cb99`, `077455c53`, `4de2ebffc`) : le vidage de tous les fils ne fait plus que des appels noyau pendant la suspension. Notre vidage automatique (chien de garde « image figée » à 10 s, 90 s sans première image) pouvait sinon geler toute l'app. S'y ajoutent l'accès far à cheval sur la fin de fenêtre, l'écriture via NULL quand le bas d'espace est épuisé, et `svc 0x02` sur une image de module ;
  - fil de soumission : les tampons de l'arène ne passent plus par l'autorelease, et `gw_commit` lit les seules pages notées au lieu de balayer 16 384 emplacements (384 Kio par soumission chez nous). L'amont a mesuré −10 % d'instructions par dessin, sur un autre titre.

## Bilan des huit tranches

| Tranche | Commits | PORT | CANDIDATE | Couverts par nos patchs | Risqués | Hors iOS ou faible valeur |
|---|---:|---:|---:|---:|---:|---:|
| Moteur graphique, 10–15 nov. | 272 | 26 | 80 | 51 | 24 | 91 |
| Moteur graphique, 15–23 nov. | 272 | 28 | 81 | 13 | 13 | 137 |
| Shaders et pipelines | 255 | 16 | 18 | 7 | 8 | 206 |
| Runtime, partie 2 | 279 | 8 | 9 | 6 | 10 | 246 |
| Services et compatibilité | 281 | 47 | 30 | 5 | 24 | 175 |
| Code iOS du moteur | 402 | 8 | 5 | 6 | 13 | 370 |
| Préparation et outils | 1 186 | 2 | 11 | 7 | 6 | 1 160 |

| Runtime, partie 1 | 279 | 30 | 14 | 18 | 12 | 205 |

**Mesures gratuites à faire sur iPhone** (tranche runtime, partie 1) :
- retirer la priorité temps réel des fils d'encodage avec `S2A_RB_ENC_RT=0`, sur une session chaude entière. L'amont a mesuré, sur un téléphone à 2 cœurs P chaud, un CPU passé de 0,57–0,76 W à 0,34–0,45 W et de 30–39 à 42–47 image/s ;
- produire une IPA de test sans `CADisableMinimumFrameDurationOnPhone`. L'amont a mesuré 34,4 image/s avec la clé contre 50,6 sans, à code égal.

## Reporté à un lot suivant, avec la raison

- **Lot du traducteur de shaders** (`33ba71d54`, `2a341dafe` + `d837c0558`, `7ed61fcbd`, `b982a589a`, `2d3fc8bf6`, `b2d7c15e3`, `99aafb48a`, `1cd1b834e`, `e65e0e718`, `751d6dddc`, `cadd50c49` + `9a48c5a29`, `0197b06fd`, `ef02e8d64` + `de08893c5`).
  - Ce qu'il apporte :
    - early-Z NVN2 : l'amont mesure −15 % de GPU sur un titre ;
    - min/max sûrs face aux NaN (blocs noirs) ;
    - ballot/vote laissés en place dans les shaders de tâche (Mario Kart World dessine son décor en tâche/maillage) ;
    - propagation de l'AST sans explosion mémoire ;
    - mulhi transformé en décalage, gathers fusionnés.
  - Il s'applique sur notre arbre.
  - Pourquoi il est reporté : tout changement du traducteur change `xfp`. Le moteur refuserait alors le pack NVN2 de Mario Kart World (contrôle d'identité 0271), et chaque shader serait retraduit à sa première utilisation, ce qui aggraverait les attentes de pipelines.
  - Il faut le faire dans un lot qui régénère aussi le pack (`build_nvn2_shader_pack.py`, à partir d'une capture).
- **Mesures d'abord :**
  - `-O2` au lieu de `-Os` pour la bibliothèque NVN iOS : l'amont mesure −7 à −9 % d'instructions sur Mac ; il faut un A/B sur appareil ;
  - `os_unfair_lock` pour `g_rmu` (`337056321` + `43d8b5fa4`) : sept `trylock` de nos patchs sont à inverser ;
  - ARC sur les autres chemins chauds (`89ab97043`, `cd9e28261`, `21f506c2f`) : risque d'use-after-free avec nos fils de préparation ;
  - réencodage partiel des UBO (`2dfa519b0` + `a52905337`) ;
  - même cible sans mode tuiles (`fb96ab7db`) ;
  - zone de rendu bornée (`f83afb3ef` + `f77af8a45`, à porter ensemble) ;
  - attentes GPU de `nvn_be_sub_begin` (`d9cf7d16e`).
- **Stabilité, à porter à la main ensuite** : leur contexte diffère trop du nôtre pour un portage rapide sûr.
  - `eabe485ff` et `767719706` : flashs et lectures noires sur des textures partagées ;
  - `e89f79aa6` : le scratch de trame rend ses blocs ;
  - `d3d807bdc`, `208fb5816`, `1d408d1dc`, `7bc2fbc01` : plantages ;
  - `52452def5` : voile blanc quand l'échelle n'est pas 1, ce qui arrive avec notre réduction en Fair ;
  - `39069a99f` ;
  - côté iOS : vidange à l'arrière-plan sortie du rappel UIKit (`6be2acdb7` + `168edb961`, contre le chien de garde de 10 s), exceptions CoreHaptics (`5a5b78559`), manette rallumée (`63dce1412`) ;
  - préparation sur l'appareil : NRR Switch 2 décalé (`03ba764ef`), NUP dédupliqué (`d649f0ccf`), correctifs du rewriter.
- **Audio :**
  - DSP NEON (`40bd92a7b`…`5f7f76fa2`) : le downmix 5.1 est 4,7 fois plus rapide chez l'amont ;
  - −200 réveils par seconde (`6094ec6d5`) ;
  - à porter avec soin dans `AppleHardwareDeviceSession.cs`, que 14 de nos patchs modifient.

## Écarté, avec la raison

- **Contraire à nos mesures ou à la chaleur :**
  - instantanés actifs par défaut (`8a11b7e58` et 50 commits liés) ;
  - mode de débordement de la mémoire invitée (`805cc41c0`…) : 0052 a mesuré 15–24 image/s au lieu de 33–48 ;
  - prise de cœur différée active par défaut (`f823f4f22`) ;
  - interpolation MetalFX par défaut à 30 image/s (16 commits) ;
  - repli à 60 image/s retiré sous chaleur critique (`3d39b7b34`) ;
  - échelle au-delà de 1 (`80029714f`) ;
  - attentes GPU ajoutées sur le fil de soumission (PR #324) ;
  - verrouillage `mlock` des pools audio (`d4a717d89`).
- **Incompatibles avec notre modèle :**
  - pipelines hybrides et variantes du paquet PC (`d03fd4ecb`, `941855a93`…) : il faudrait le traducteur PC et des packs trois fois plus gros ;
  - clé de shader v2 : elle invaliderait les caches ;
  - réglages par jeu (`55978ff38`) : ils cassent le contrat du pont ;
  - swizzle UIView global (`822463f4e`) ;
  - racine du pack déplacée (`1c23104b7`) ;
  - sortie brute `_exit(0)` (`48d48e8a2`), contraire à 0006 ;
  - codecs construits en « auto » (`9c9959340`).
- **Sans objet sur iOS :** Android, OpenHarmony, Vulkan, PC, macOS, Windows, interface amont.

## Mesures utiles faites pendant ce lot

Ce ne sont pas des mesures sur iPhone des nouveaux patchs. Ce sont des relevés du journal de la session 824 (`c758810c`, 9 000 images) et des résultats de tests.

- **Pipelines construits à la demande :** 576 pipelines, 7 221,5 ms d'attente au total.
  - 8 constructions de 50 ms ou plus font 5 369 ms (74 %), dont une seule de 3 822,6 ms à l'image 1010 ; 367 pipelines ont pris moins de 1 ms (archive).
  - Images 300 à 600 : 354 premières utilisations, 2 798 ms. Parmi elles, 106 clés jamais vues (1 857,5 ms), 47 déjà attendues dans une session antérieure (254 ms) et 201 déjà préparées dans une session antérieure (686,5 ms).
  - Les clés sont stables d'une session à l'autre : 374 des 576 reviennent.
- **Mémoire Metal :** à l'image 1018, Metal tient 8 983 Mo pour 5 461 Mo recommandés. Une partie vient sans doute des buffers sans copie comptés en entier (amont `af995916f`). Ce chiffre nourrit le gouverneur.
- **Anticipation des pipelines :** au plus 2,063 ms par soumission pour un budget de 2 ms (42 refus, 2 dépassements, 89 340 recherches négatives). Environ 2 soumissions par image (18 000 à l'image 9 000).
- **Trafic des passes :** 191 Mio chargés et autant stockés par image pour un atlas creux dont les passes durent quelques dizaines de µs. La passe principale (7,5 Mio par ouverture) est rouverte 6 à 11 fois par image. Les copies de profondeur sont sous-comptées d'environ 5 fois.
- **Textures partagées :** 2 659 reprises de stockage, dont 2 655 d'objets vivants ; 157 textures écrites par le GPU libérées comme orphelines (271 Mo) ; 154 écritures GPU dans des textures embarquées. Aucun dessin sauté.
- **Erreurs GPU :** une seule rafale, d'environ 40 tampons rejetés « victime d'une récupération GPU ». Elle survient vers l'image 6836 (180 s), application probablement en arrière-plan (CPU 0,04 W) et chaleur Serious. Rien à voir avec les clippings en course.
- **Mario Kart World et le traducteur :** le journal montre des pipelines tâche/maillage, mais aucune variante de sortie typée. Le port amont `2a0343454` ne lui apporterait donc presque rien.
- **Tests :**
  - `t_rb_alias_key` (8 cas), `t_rb_warm_order` (dont un mélange de 9 018 lignes) et `t_rb_dsnap_rule` passent en local avec gcc, clang et les sanitizers, puis sur la CI ;
  - runs 45153497523, 45155914850 et 45156872271 réussis ;
  - run 45161270894 en échec, voir 0317 plus haut.
