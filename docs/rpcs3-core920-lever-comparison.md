# RPCS3 Core 920 — plus d'alternance des leviers en jeu ; ce qu'attend et coûte le vidage ZCULL de Black Ops II

Suite de l'instruction formelle du mainteneur du 10 novembre (jouabilité, performances, RAM et stabilité de Black
Ops II) : « Supprime les alternances automatiques du fonctionnement ordinaire. […] Réserve les comparaisons à un mode
explicitement demandé, borné et journalisé, jamais imposé au joueur. » Core 920 = Core 919 + deux changements.
**Aucune mesure iPhone n'a été faite avec ce Core ni avec le Core 919.** Cette suppression ne résout pas à elle seule
les goulots de Black Ops II : elle retire une dégradation imposée au joueur et rend les mesures suivantes comparables.

## 1. Défaut : les Cores 917 à 919 coupaient eux-mêmes leurs leviers en jeu

- Le Core 917 (`REWINDBOX_PARK_SPIN_COMPARE_917`) puis le Core 918 (`REWINDBOX_BUSY_WAIT_REFERENCE_918`) comparent
  deux leviers dans la même scène : l'attente active de 8 µs de l'écrivain du verrou de réservation (Writer lock park
  spin) et la durée de référence des attentes actives (Busy wait reference duration, échelle 42 sur le compteur de
  1 GHz de l'iPhone, 1 sans le levier).
- Cette comparaison tournait **dès que le réglage d'un levier valait Automatic, sa valeur par défaut**. Pendant une
  tempête de PUTLLC lourds (100 000 par fenêtre ou plus), le thread du rapport de performances basculait les leviers
  entre ses fenêtres de 5 s : 6 fenêtres d'avance, puis trois passes de 16 fenêtres par paires (park spin coupé ;
  échelle 1 ; les deux coupés ; les deux allumés ; deux fois), séparées de 22 fenêtres. Ce sont les fenêtres 7-22,
  45-60 et 83-98 comptées depuis le démarrage, menus compris (0:30-1:50, 3:40-5:00, 6:50-8:10).
- Pour le joueur : dans les dix premières minutes de chaque démarrage, jusqu'à 24 fenêtres avec le park spin coupé
  et 24 avec l'échelle à 1, soit jusqu'à 36 fenêtres (3 minutes) avec au moins un levier coupé (toutes celles des
  passes qui suivent une fenêtre de tempête), et des images/s qui peuvent changer d'une fenêtre à l'autre pendant une
  passe. Pour les mesures : les fenêtres de ces passes mélangent
  les états des leviers (les lignes `COREPROF PARKCMP917` les nomment) et ne se comparent pas directement d'un build à
  l'autre.

## 2. Correction (`REWINDBOX_LEVER_COMPARISON_ON_REQUEST_920`)

- Nouveau réglage **Lever comparison between report windows** (Experimental → FPS Experiments,
  `rpcs3/Emu/system_config.h` `lever_comparison`, défaut Automatic, pris en compte au démarrage suivant).
- **Automatic et Disabled n'alternent jamais** : les deux leviers restent tels que leurs propres réglages les
  résolvent (Automatic : allumés, la politique de production vérifiée des Cores 917 et 918 ; Enabled : allumés ;
  Disabled : coupés).
- **Enabled** : la comparaison des Cores 917 à 919, inchangée, pour un levier dont le propre réglage vaut Automatic
  seulement, bornée à ses trois passes, chaque bascule journalisée (`COREPROF PARKCMP917`), les deux leviers allumés
  ensuite. C'est un diagnostic à demander exprès, jamais une valeur par défaut.
- `rpcs3/ios/RPCS3IOSExperimentalPolicy.cpp` : `policy.busy_wait_compare` et `resolved.writer_park_compare` exigent
  en plus `lever_comparison == Enabled`. Nouvelle ligne de politique `Resolved title policy 920: lever_comparison=…
  park_spin_alternates=… busy_wait_alternates=…`.
- La description du réglage Busy wait reference duration n'annonce plus de comparaison.
- Ce que font les leviers ne change pas ; aucun levier non sûr n'est forcé.

Préférences et sessions : le réglage est enregistré comme les autres réglages de l'émulateur ; un profil existant ne
le contient pas et vaut donc Automatic. L'app ne possède aucun profil par titre qui écrive ces clés (aucune référence
hors du Core) et les leviers par titre (`IOSTitleLevers.h`) ne les touchent pas. Dans un même processus, un démarrage
qui suit un démarrage comparé ne compare pas (test ci-dessous).

## 3. Contrôle avant/après (hôte)

`test/rpcs3_lever_comparison920_test.py` construit deux fois, sous AddressSanitizer et UndefinedBehaviorSanitizer
(g++) et avec clang, un banc fait du vrai en-tête de comparaison (`ios/IOSWriterParkSpin917.h`), du vrai bloc du
thread du rapport qui l'applique (`ios/RPCS3IOSPerformance.cpp`) et des vraies instructions de politique
(`ios/RPCS3IOSExperimentalPolicy.cpp`) : avec le code du Core 919 (contrôle, l'incrément du Core 920 annulé) et avec
l'arbre testé. Modèle : 140 fenêtres de jeu, chacune dans une tempête de PUTLLC lourds, compteur de 1 GHz.

| Cas | Bascules du park spin | Bascules de l'échelle | Fenêtres avec un levier coupé | Étapes `PARKCMP917` |
|---|---|---|---|---|
| Core 919, tous les réglages par défaut | 24 | 12 | 24 (spin) + 24 (échelle) | 48, dernière bascule fenêtre 96 |
| Core 920, comparaison Automatic ou Disabled, chacune des 9 combinaisons des deux leviers (18 démarrages) | 0 | 0 | 0 | 0 |
| Core 920, démarrage qui suit un démarrage comparé (deux fois) | 0 | 0 | 0 | 0 |
| Core 920, comparaison Enabled, leviers Automatic | 24 | 12 | 24 + 24, toutes dans les passes | 48 ; les deux allumés à la fin |
| Core 920, comparaison Enabled, park spin Enabled ou Disabled | 0 | > 0 ou 0 | seul un levier Automatic bascule | — |

Le contrôle reproduit les bascules de l'ancienne politique ; le Core 920 n'en fait aucune hors du mode demandé, et
les leviers tournent comme leurs réglages le disent (Automatic : allumés, échelle 42). Les tests des Cores 917 et 918
acceptent les deux règles et passent sur l'arbre du Core 920.

## 4. ZCULL : ce qu'attend et ce que coûte le vidage surveillé (`REWINDBOX_ZCULL_COST_920`)

Le Core 919 fait soumettre plus tôt à Black Ops II le command buffer d'un rapport que l'invité va lire. Deux mesures
manquaient pour juger ce levier sur l'appareil :

- **Le rapport réellement attendu.** `ZCULLLEAD659` donne l'âge du plus *ancien* rapport en attente d'un emplacement
  lu (5 à 15 ms sur la build 676) ; une lecture attend pourtant le plus *récent*, et le vidage surveillé n'apprend un
  emplacement que si ce dernier a 1 ms ou plus. Sur la build 676, Black Ops II avait ce levier coupé : toutes ses
  lignes `ZCULLWATCH660` (session 3) portent `enabled=0 slots=0:0:0:0:0`. Aucune donnée de l'appareil ne dit donc
  encore si ses lectures arment le levier.
- **Le coût des nouvelles soumissions** sur le thread RSX (la soumission du command buffer, encodage MoltenVK
  compris).

Nouvelle ligne par fenêtre : `COREPROF ZCULLCOST920 session=… window=… newest=nombre:total_ms:max_ms
newest_over_1ms=… watched_submit=nombre:total_ms:max_ms scope=process_window window_boundary_approximate=1`
(`rpcs3/Emu/RSX/RSXZCULL.cpp`, `ios/IOSZcullOnDemand.h`, `ios/IOSZcullWatched.h`, `Emu/RSX/VK/VKGSRender.cpp`).

Contrôle hôte (`test/rpcs3_zcull_cost920_test.py`, banc du Core 660 avec le vrai code ZCULL et de soumission, formes
d'images Black Ops II du Core 919) :

| Modèle hôte (24 images) | Lectures qui attendent | Âge du plus récent rapport (total) | Soumissions surveillées chronométrées |
|---|---|---|---|
| `bo2read`, levier allumé | 2 | 11,7 ms | 22 (= prises) |
| `bo2read`, levier coupé | 23 (toutes ≥ 1 ms) | 134,4 ms | 0 |
| `bo2busy`, levier allumé | 1 | 9,0 ms | 23 (= prises) |
| `bo2busy`, levier coupé | 24 (toutes ≥ 1 ms) | 213,3 ms | 0 |

Chaque lecture qui enregistre un âge du plus ancien enregistre aussi celui du plus récent (jamais plus vieux) ; chaque
soumission surveillée prise est chronométrée une fois, aucune levier coupé. L'horloge du banc n'avance pas pendant
une soumission : la durée se lit sur l'appareil seulement.

Décision sur l'export suivant (Black Ops II, IPA contenant ce Core) :

- **Le levier s'arme** (`ZCULLWATCH660 slots=` appris et `taken=` > 0, `newest_over_1ms` proche de `newest`) :
  l'attente éliminée se lit dans `ZCULLDEMAND619 waits` et son temps, le coût dans `watched_submit=` (total ms) et
  `RSXSYNC551 submit=`, rapportés aux images/s, au temps CPU du thread PPU principal et à la couverture GPU. S'il coûte
  plus qu'il n'élimine, Black Ops II sort de la liste.
- **Il ne s'arme pas** (`newest_over_1ms` faible, `short_lead` élevé) : les lectures attendent un rapport mis en file
  moins de 1 ms avant ; soumettre plus tôt ne sert à rien et le Core suivant visera l'exécution du command buffer
  lui-même.

## 5. Inchangé

Aucune condition d'attente, aucun verrou, aucune valeur ni ordre de rapport ZCULL, aucun réglage de résolution, de
précision, de limite d'images, de nombre ou de priorité de SPU, de délai GETLLAR/PUTLLC ou d'option LLVM. Aucun
fichier d'entrée des identités de code généré PPU/SPU n'est modifié : les caches restent valides. ABI 30, 92 exports.

## 6. Identités

Moteur `4c4961b` (base Core 919 `8210faf`), incrément `build-utils/rpcs3/core920-from-919.patch` (9 fichiers),
correctif canonique `9377bd66`, delta `core920-delta.patch` `87c02e84`. Compilation, empreintes et état sur l'appareil
dans `build-utils/rpcs3/core-pin.json` et `docs/AI_TASK_BOARD.md`.

## 7. Protocole iPhone

Celui du [Core 918](rpcs3-core918-busy-wait.md) § 8 : Black Ops II, lancement, scène lente jusqu'à neuf minutes après
le lancement, export aussitôt avec les fichiers `.1`. Pour la mesure ordinaire, laisser Lever comparison between
report windows sur Automatic : plus aucune fenêtre n'a de levier coupé. Une comparaison voulue se demande avec
Enabled pour un démarrage, puis le réglage revient à Automatic.
