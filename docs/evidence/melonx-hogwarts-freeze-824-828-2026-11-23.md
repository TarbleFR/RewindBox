# Hogwarts Legacy, IPA 824 à 828 : gel à t≈22 s — ce qui est prouvé, ce qui ne l'est pas

23 novembre 2026. Sources : journaux privés de l'appareil (performance, core, stderr, crash, launch) des sessions
822 (pid 12224, Hogwarts ; 12544, SSBU), 824 (13605, 13625 Hogwarts ; 13995, 14467 SSBU), 825 (15452 SSBU) et
828 (17014, 17066 Hogwarts). Seuls des comptes et des durées sont repris ici.

## 1. L'effondrement « ×200 » des pipelines compute : le cache Metal du système était vide

- 822 : 535 pipelines compute construits en 1 212 ms dans la première fenêtre de 5 s (2,3 ms chacun).
- 824/828 : après une première fenêtre plus ou moins rapide, 5 à 14 constructions par fenêtre, 450 à 650 ms chacune,
  une seule à la fois, en continu jusqu'à la fin de la session.
- La première session 824 (13605) est la seule où la création du périphérique GPU a pris 541,5 ms (1 à 3 ms partout
  ailleurs, 822 compris) : les shaders internes de MoltenVK y ont été recompilés.
- Le cache se remplit exactement au rythme des compilations des sessions précédentes :

| Session | Constructions compute « rapides » au départ | Total compilé par la session précédente |
|---|---|---|
| 13605 (824) | 8 | — (822 : 539) |
| 13625 (824) | 113 | 105 (+ fin de session non journalisée) |
| 17014 (828) | 198 | 189 |
| 17066 (828) | 285 | 281 |

  Chaque session démarre avec ce que la précédente a compilé : ce sont des compilations Metal mises en cache par le
  système, pas un ralentissement du moteur.
- Le code de compilation et de liaison est identique entre 822 et 828 (ShaderCollection.cs, PipelineState.cs,
  PipelineBase.cs, PipelineCacheManager.cs, VulkanRenderer.cs, ProgramQueue.cs, SetProgramCommand.cs,
  ThreadedRenderer.cs, DmaClass.cs) ; seize fichiers seulement diffèrent entre les deux arbres. MoltenVK est identique
  de 821 à 828 (même identité normalisée dans `docs/evidence/rewind82x/signed-payload-identity.json`).
- Ce qui a vidé le cache entre 04 h 55 et 08 h 59 UTC : cause la plus probable, non prouvée sur iOS. Comparaison des
  manifestes de livraison : entre 822 et 824, l'application ne change que par le Core MeloNX `fcea4ea2` et par S2Arm
  (patchs 0308 à 0311, et le bridge `d4525af9e` du 23 novembre à 07 h 57 UTC, livré dans la 824). Ce bridge fait
  passer `MTL_SHADER_CACHE_SIZE` de 64 Mio à 1 Gio. Cette variable borne le cache du compilateur Metal de
  l'application, qui est commun à tous ses émulateurs. Jusqu'à la 823 (une IPA S2Arm), une session Switch 2 tournait
  donc avec un cache borné à 64 Mio, alors que les pipelines de Hogwarts le dépassent largement. Depuis la 824, la borne
  est de 1 Gio : le cache se remplit d'une session à l'autre (tableau ci-dessus) et les installations de 825 et 828 ne
  l'ont pas vidé. Une mise à jour d'iOS l'invaliderait aussi (non vérifié).
- Le moteur de la 823 est celui de la 822 (`8d810e8f`). Le commit `7d45996a` d'une autre session indique que le
  mainteneur a vu la même fin « avec l'IPA précédente ». Si c'était la 823, le gel ne vient pas du diff du moteur
  822 → 824, mais du cache Metal vide.

## 2. Le gel : signature mesurée

- Dans les quatre sessions figées, le fil de rendu s'arrête après exactement 36 dessins, 18 constructions de pipelines
  graphiques et 5 dispatchs (17014 : 118 dessins, 5 dispatchs), quel que soit l'état du cache (8 à 285 pipelines
  rapides). Le point d'arrêt est donc fixe dans le flux de commandes du jeu.
- Ensuite : aucun dessin, aucun dispatch, fil de rendu sous 1 % de CPU (en attente, pas en boucle) ; le fil GPU reste
  dans `gpuDispatch` (17014 : le fil de présentation dans `frameWait`).
- Aucune phase mesurée n'est en cours sur ces fils : ni `syncInvoke`, ni `queueBackpressure` (la file de commandes
  n'est pas pleine), ni `bufferReadback`, ni `queryReadback`, ni construction de pipeline par le fil de rendu (le
  compteur `computePipelineBuild` en cours reste à 1 avec un âge qui repart de zéro : c'est le travailleur qui
  enchaîne ses compilations).
- ~~Aucun shader n'est traduit au moment du gel : 32,9 Ko alloués~~ — erreur de lecture, corrigée le 24 novembre
  (section 10) : la colonne est en Kio. La fenêtre du gel compte 28 appels au cache de shaders et 32,9 Mio alloués :
  le jeu traduit de nouveaux programmes à ce moment-là (la 822 : 128 appels, 59 Mio dans la même fenêtre).
- Le blocage du minuteur de 828 (`adapt_compile_wait_guest_time`) ne s'est jamais engagé : le fil de rendu n'attendait
  pas dans `WaitForPipelineAtDraw`.
- Le SIGABRT de `FHeartBeatThread` à t=47–51 s est le chien de garde de 25 s d'Unreal Engine, une conséquence.

## 3. Attentes du fil de rendu écartées par ces mesures

- Attente d'une compilation promue (dessin ou dispatch) : servie par le fil « demand » ou par le travailleur après au
  plus une compilation ; le fil « demand » est resté inactif et aucune compilation ne dure.
- Construction de pipeline sur le fil de rendu (verrou du cache principal) : elle serait mesurée.
- ~~Attente de liaison d'un programme créé en jeu : aucun programme n'est créé en jeu~~ — faux (voir ci-dessus) :
  c'est l'attente du gel (section 10).
- Libération d'un programme : uniquement à la fermeture.
- `SyncManager` (824, `adapt_unblocked_sync_queries`) : l'ordre des verrous `_handles` → handle est le même partout ;
  la 824 retire une attente au lieu d'en ajouter.
- Compactage sous pression mémoire (824) : 0 compactage pendant les sessions figées.

## 4. Ce qui n'est pas prouvé

L'appel exact dans lequel le fil de rendu attend. Aucun journal ne peut le montrer : les journaux du fil de rendu
sont écrits par ce fil lui-même (dernier à 22,26 s), et l'observateur natif des blocages ne relevait les piles que
lorsqu'un appel du journal au moteur restait bloqué, ce qui n'arrive pas ici. Les attentes restantes non mesurées
sont des attentes de fence (`CommandBufferPool.WaitAndDecrementRef`, `StagingBuffer.WaitFreeCompleted`) et les appels
dans MoltenVK/Metal ; aucune n'est désignée par les journaux actuels.

## 5. Ce qui a été ajouté pour le prouver au premier essai

Commit fb88bf8f0 (bridge, mesure seule) : quand un jeu en cours n'a présenté aucune image depuis 2, 5 et 12 s après sa
première image, l'observateur relève chaque fil du processus (état, CPU, 32 adresses de retour) ; deux gels au plus
par journal, puis la fin du gel. `tools/melonx/stall_report.py` nomme les adresses du moteur avec la carte des
symboles de l'artefact du Core (vérifié sur la capture de la 822 : `ThreadedRenderer.RenderLoop`,
`GPFifoDevice.WaitForCommands`, `WorkerQueue.WorkerLoop`).

Lecture au premier essai :

```bash
python3 tools/melonx/stall_report.py MeloNX-performance.log --pid <pid> --symbols ios-arm64/Ryujinx.Library.symbols.txt.gz
```

## 6. Retour au moteur de la 822 (demande du mainteneur)

Commit `e776bfd45` : le moteur de la 822 à l'identique (`fcea4ea2` et `7d45996a` annulés), plus le seul
`EmbeddedOnline.cs` de Nextendo (`3554d839`), compilé par `melonx-core.yml` (run 45283827082). L'IPA de diagnostic
(Core de ce run, bridge `fb88bf8f0`, S2Arm à 1 Gio) est confiée à la session S2Arm. Si Hogwarts gèle encore, les
relevés « #F » donnent l'appel exact.

Livrée dans l'IPA privée 829 (commit de livraison `5a550d21`, run 45289424111, reçu
`docs/evidence/rewind829/delivery.json`). Pour lire les relevés « #F » de la 829 :
- Core MeloNX : artefact 14869999889 (carte `ios-arm64/Ryujinx.Library.symbols.txt.gz`), empreinte de charge
  `ab0d56fc` ;
- MeloNXMoltenVKStandalone : empreinte de charge `eee9229e` (le même binaire depuis la 821).

## 7. Expérience décisive sans nouvelle IPA

Réinstaller l'IPA 822 telle quelle et lancer Hogwarts une fois :
- s'il gèle au même point (36 dessins, 5 dispatchs), la cause n'est pas dans le diff 822 → 824 mais dans un défaut
  latent révélé par le cache Metal vide ;
- s'il atteint le menu, la cause est dans les seize fichiers qui diffèrent entre les deux moteurs.

## 8. IPA 829 (moteur de la 822 + Nextendo) : le gel reste — 24 novembre

Session 18006 : même arrêt après la relecture GPU de 21,5 s (« TryReadBackIntoBuffer »), chien de garde du jeu
25 s plus tard. Faits établis par cette session :
- Le moteur MeloNX de la 822 gèle aussi : la cause n'est pas dans les changements du moteur faits après la 822.
- Pool JIT : arène de 1 024 Mio préparée (65 536 pages), dernière étape journalisée 512 Mio, comme dans les
  sessions 824–828 ; la 822 dépassait 640 Mio parce qu'elle continuait à jouer. Le défaut d'octobre (arène de
  512 Mio, adaptateur `adapt_jit_arena`) se signalait par « JIT Cache exhausted » : ce message n'apparaît dans aucun
  journal de 824 à 829.
- Réglages de lancement identiques à ceux de la 822 (politique Hogwarts, jeu en ligne configuré, arène JIT).
- Activité réseau identique avant le gel (mêmes échecs `SetSocketOption` vers 14 s).
- Compilations : 320 pipelines compute trouvés en 2,3 s, puis 64 en 23 s (le cache Metal n'est rempli qu'en partie).

Comparaison des binaires signés 802 → 829 (`docs/evidence/rewind8xx/signed-payload-identity.json`) : 17 sur 98
diffèrent. Pour MeloNX : le Core, MoltenVK (depuis la 821), le bridge, Runner et App. La 822, qui atteignait le jeu,
avait déjà le MoltenVK et le moteur de la 829. Le binaire du bridge alterne entre deux empreintes sans changement de
sources (821, 822, 823 : sources identiques) ; la 821, qui passait ce point, avait l'empreinte des sessions figées.

Non établi : l'appel exact où le rendu attend. Les relevés « #F » sont écrits dans `MeloNX-performance.log`, absent
des journaux reçus.

## 9. Historique : toutes les sessions Hogwarts reçues, IPA 606 à 829 — 24 novembre

Sources : les 97 sessions Hogwarts des journaux de performance reçus (aucune de la 802), lues fenêtre par fenêtre
(pipelines compute et graphiques construits, dessins, dispatchs).

- Le jeu passait ce point dans toutes les IPA de 621 à 822 dont une session est reçue : au moins une session atteint
  des dizaines de milliers de dessins par fenêtre de 5 s après t≈25 s.
- Aucune session avant la 824 ne s'arrête comme celles de 824–829 (36 dessins, 5 dispatchs, puis plus rien) :
  - 662 (huit sessions, fin à 14–24 s) : mort native du processus avec le GC NativeAOT reconstruit, corrigée par la
    663 (retour au GC officiel) ;
  - 669 17770, 693 38333 et 38363 : aucune image, processus presque inactif dès le départ ;
  - 672 92832 et 92877 : encore en progrès (images présentées à 33 et 44 s) quand elles finissent ;
  - les autres sessions courtes ont été fermées entre 3 et 16 s.
- Cache Metal froid avant la 824 : des sessions ont compilé leurs pipelines compute à 150–450 ms pièce (640 5576 ;
  658 79315, 79477, 79931, 80176, 80566, 80774 ; 672 18339, 18409, 92832, 92877 ; 694 39157). Celles qui ont duré ont
  toutes passé ce point, lentement (658 79315 : 363 dessins et 40 dispatchs à 31 s, puis la partie). Un cache froid
  seul n'arrêtait donc pas le jeu.
- Depuis la 726 (Core 725, `adapt_variant_replay_all` : tous les états enregistrés sont préparés au lancement), la
  première fenêtre construit 526 à 535 pipelines compute et ~3 500 graphiques. Toutes les sessions reçues de la 726 à
  la 822 les ont trouvés dans le cache (0,1 à 1,2 s pour les 535). La 824 est la première session avec un cache froid
  depuis ce changement ; dans les 824–829, le seul travailleur compile des pipelines compute un par un (~0,5 s
  chacun) pendant toute la session et presque plus de graphiques (0 à 2 par fenêtre), alors que les sessions froides
  de 658/672 construisaient les deux.
- Pendant le gel (828 17066, mesures du Core) : à partir de 22,5 s, le fil de rendu reste dans une seule commande
  (`renderDrain` en cours, âge 3,0 → 28,5 s) et le fil GPU dans `gpuDispatch` depuis le même instant ; une seule
  construction compute est en cours à tout moment, et elle se termine (âge 0,2 à 1,8 s). Aucune phase mesurée du fil
  de rendu (lecture, requête, construction de pipeline) n'est ouverte.
- Code (moteur de la 822) : un dispatch n'est jamais sauté (`ShaderInfoBuilder.Build` : `allowAsyncCompileSkip`
  exige un programme sans écriture, et un programme compute écrit) ; un dispatch dont le pipeline manque attend le
  préchauffage du programme dans `TryWaitForBackgroundComputePipeline` → `WaitForPipelineAtDraw` (attente par tranches
  de 4 ms, presque sans CPU), ou construit le pipeline lui-même. Laquelle de ces attentes, ou une autre, tient le
  rendu : non établi sans les relevés « #F ».

Pool JIT et autres moteurs (question du mainteneur, même jour) :
- Dans la session 829 (18006), seul MeloNX tourne dans le processus : aucune de ses 172 lignes de moteur ne vient de
  S2Arm ni de RPCS3. S2Arm ne règle ses variables (dont `MTL_SHADER_CACHE_SIZE`) qu'au lancement d'un jeu Switch 2
  (`runLaunchWithGid`), dans son propre processus.
- Arène JIT : 1 024 Mio préparés en 1,68 s, sonde ARM64 exécutée, « actual engine JIT authorization confirmed » à 7 s
  — mêmes étapes et même durée que la 822 (1,65 s). Utilisation au gel : 512 Mio au plus (824, 828).
- « JIT Cache exhausted » (le défaut d'octobre) n'apparaît que dans deux sessions reçues, 658 11121 et 666 15155,
  terminées à 12 et 16 s ; dans aucune session de 824 à 829.
- Ce que les moteurs partagent : le cache du compilateur Metal de l'application (un seul pour MeloNX, S2Arm et RPCS3).

## 10. La cause, dans le code et dans les mesures — 24 novembre

La chaîne, de bout en bout (moteur de la 822 = moteur de la 829, `scratchpad` local régénéré à l'octet près depuis
la source épinglée : 0 écart sur 539 empreintes du contrat) :

1. Hogwarts tourne avec la compilation asynchrone des shaders (`asyncShaders=True` dans les sessions 824–829 ; SSBU :
   `False`). Un programme graphique traduit en jeu dont les shaders écrivent en mémoire ne peut pas être lié
   incomplet (`ShaderInfoBuilder.Build` : `allowAsyncCompileSkip = enableAsyncCompile && !hasShaderWrites`).
2. `SetProgramCommand` l'attend alors sur le fil de rendu : `ProgramQueue.WaitForProgram` →
   `ShaderCollection.CheckProgramLink(blocking: true)` → `_compileTask.Wait()`, c'est-à-dire toute sa compilation de
   fond, pipeline de préchauffage compris. Le détachement d'`adapt_setprogram_warmup` (« la liaison attend les
   modules, pas le préchauffage ») ne s'applique pas avec la compilation asynchrone (`playTimeWarmUp` exige
   `!info.EnableAsyncCompile`).
3. Cette attente ne demande rien : ni `PromoteBackgroundCompilation`, ni promotion de la tâche. Le préchauffage reste
   dans la file haute priorité, dans l'ordre d'arrivée.
4. Depuis `64e49a84e` (22 novembre, `adapt_render_thread_compile_relief`), les préchauffages des 535 programmes
   compute du cache sont eux aussi en haute priorité, mis en file au lancement, donc devant tout programme traduit en
   jeu. Un seul travailleur sur l'iPhone (6 cœurs) ; le fil « demand » ne prend que les compilations demandées.
5. Cache Metal chaud (822) : les 535 sont faits en 1,2 s, la file est vide quand le jeu traduit ses programmes. Cache
   froid (824–829) : ~0,5 s chacun, 150 à 500 encore devant à 22 s, soit 75 à 250 s d'attente.

Mesures qui collent à chaque maillon : traduction de programmes dans la fenêtre du gel (28 appels, 32,9 Mio) ; fil
de rendu dans une seule commande depuis 22,5 s sous 1 % de CPU (attente bloquante, aucune phase mesurée) ; une seule
compilation compute en cours à la fois, celle du travailleur (« Worker pipelines found in the main cache »), le fil
« demand » inactif ; le fil GPU bloqué derrière le rendu (`SyncMap.WaitSyncAvailability`, non mesuré) ; à la pause
de la 828, le `RenderThread` du jeu attend depuis 15,3 s et son `RHIThread` tourne en boucle ; chien de garde d'Unreal
25 s plus tard. Le minuteur de la 828 (`adapt_compile_wait_guest_time`, posé sur `WaitForPipelineAtDraw`) ne s'est
jamais engagé : l'attente n'était pas celle d'un dessin. Avant le 22 novembre, les préchauffages compute du cache
étaient en basse priorité : les sessions à cache froid de 640–694 passaient.

Correctif (`adapt_render_thread_compile_relief`, une ligne de moteur) : avant `_compileTask.Wait()`, la vérification
bloquante demande la compilation (`PromoteBackgroundCompilation()`), comme le font déjà un dessin et un dispatch.
L'attente ne dure plus qu'une compilation (~0,5 s à froid) au lieu de toute la file. Rien n'est sauté ni retiré :
la liaison attend toujours le même pipeline. Seuls les programmes à préchauffage non détaché atteignent cette ligne
(traduits en jeu avec la compilation asynchrone) ; programmes du cache et sessions sans compilation asynchrone (SSBU)
n'y passent pas. Test du contrat : 549 contrôles passés ; compilation : CI du Core. Effet sur l'iPhone : non mesuré.

## 11. Confirmation par les piles, et première session sur l'IPA 830 — 24 novembre

Relevé « #F2.2 » de la session 829 figée (pid 18006, 12 s sans image), symbolisé avec la carte du Core de la 829 :
- fil de rendu : `SetProgramCommand` → `ProgramQueue.WaitForProgram` → `WaitForLink` →
  `ShaderCollection.CheckProgramLink` → `Task.Wait` ;
- fil GPU : `DmaClass.DmaCopy` → `SignalPreciseRead` → `BufferModifiedRangeList.WaitForAndFlushRanges` →
  `SyncMap.WaitSyncAvailability`.
C'est l'attente de la section 10, à l'appel près.

IPA 830 (Core 7cf4ff80d, session 19155, 163 s) : le jeu dépasse 22 s et atteint la partie (le mainteneur : « ça
fonctionne », avec beaucoup de saccades). Mesures :
- 41–69 s : 25,6 images/s présentées, 6 trous de plus de 100 ms (3,7 s) ; 97–160 s : 10,2 images/s, 25 trous de
  plus de 100 ms (55,4 s), dont un de 27,9 s (70–97 s).
- Le trou de 27,9 s : 144 dessins ont attendu leur pipeline graphique, 24,8 s en tout (`draws that waited for a
  compile`), environ 170 ms par compilation. Sur la session, ces attentes font environ 68 s.
- Cache Metal encore froid pour les pipelines graphiques : 500 pipelines compute rapides dans la première fenêtre
  (le cache se remplit : 320 dans la 829), tous les compute faits à 41 s ; environ 2 000 pipelines graphiques
  compilés pendant la session, 100 à 500 ms chacun, deux fils en permanence.
- Mémoire : empreinte jusqu'à 4,2 Gio, 4,8 Gio compressés, 8 % disponibles sur l'appareil, alerte mémoire à 84 s ;
  pendant le trou de 27,9 s, 112 534 décompressions et 140 743 défauts de page. La 822 (qui jouait) montait à
  4,6 Gio et 4,9 Gio compressés.
- Ramasse-miettes : pauses de gen2 en arrière-plan de 28 ms au plus pendant le jeu ; pas en cause.
- Le relevé « #F » n'a pas couvert le trou de 27,9 s : ses deux relevés par processus ont servi au chargement.

À mesurer à la session suivante : combien de pipelines graphiques la première fenêtre trouve dans le cache, et ce qu'il
reste d'attentes de compilation.
