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
- Aucun shader n'est traduit au moment du gel : 28 recherches dans le cache de shaders, 32,9 Ko alloués en tout ; le
  cache disque (2 120 programmes) est le même dans toutes les sessions. Aucun programme créé en jeu n'est en cause.
- Le blocage du minuteur de 828 (`adapt_compile_wait_guest_time`) ne s'est jamais engagé : le fil de rendu n'attendait
  pas dans `WaitForPipelineAtDraw`.
- Le SIGABRT de `FHeartBeatThread` à t=47–51 s est le chien de garde de 25 s d'Unreal Engine, une conséquence.

## 3. Attentes du fil de rendu écartées par ces mesures

- Attente d'une compilation promue (dessin ou dispatch) : servie par le fil « demand » ou par le travailleur après au
  plus une compilation ; le fil « demand » est resté inactif et aucune compilation ne dure.
- Construction de pipeline sur le fil de rendu (verrou du cache principal) : elle serait mesurée.
- Attente de liaison d'un programme créé en jeu (`CheckProgramLink` → `_compileTask.Wait()`) : aucun programme n'est
  créé en jeu ; les programmes du cache n'attendent que leurs modules, compilés au chargement.
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
