# MeloNX (RSwitch), IPA 824 : Hogwarts Legacy s'arrête au bout de 47 à 50 s

23 novembre 2026. Journaux privés de l'appareil (IPA 824 : deux sessions de Hogwarts Legacy ; IPA 822 : une session) :
seuls des comptes et des durées figurent ici. Rien de ce correctif n'est mesuré sur iPhone.

## Ce qui arrête le jeu

- Les deux sessions se terminent par SIGABRT sur le fil invité `FHeartBeatThread`, 47 et 48 s après le lancement.
- Pile symbolisée sur le Core 663a759ade90 : code JIT de l'invité → gestionnaire de signal →
  `NativePageTable.VirtualMemoryEvent` (`InvalidMemoryRegionException`, garde de la table de pages :
  `relativeOffset=0x40000003`, soit l'adresse invitée 3) → aucune prise en charge au-dessus du signal →
  `RuntimeExceptionHelpers.FailFast` → `abort`.
- L'adresse 3 est écrite par le jeu lui-même : le fil de pulsation d'Unreal provoque ce plantage quand un fil surveillé
  n'a pas avancé pendant 25 s de temps invité.
- Ni `NativeBuffer`, ni la compaction mémoire, ni le gestionnaire de signal, ni les synchronisations n'apparaissent dans
  la pile ou dans les journaux de la panne. Les sept adaptateurs propres à la 824 ont été relus un par un ; aucun ne
  bloque.

## Ce qui s'est arrêté 25 s plus tôt

- La première image de jeu, à 21,2 s puis à 22,2 s, juste après la première relecture GPU dans un tampon.
- Les sessions saines (IPA 820, 821, 822) font leur seconde relecture entre 1,3 et 22 s plus tard ; les sessions de la
  824 ne la font jamais.
- Ensuite, plus aucune phase du fil GPU ni du fil de rendu ne se termine (fenêtres de 5 s : 0 attente de file, 0 vidage,
  0 repos).
- Côté invité, `RenderThread 1` attend une condition depuis 13 984 ms, et les 50 fils de l'invité sont en attente.
- Pendant ce temps, les fils de compilation terminent 9 à 14 pipelines de calcul par fenêtre de 5 s, chacun en 350 à
  1 100 ms ; le temps cumulé de ces compilations égale la durée de la fenêtre.

## Pourquoi c'est si lent : Metal compile à froid

| | IPA 822 | IPA 824 |
|---|---|---|
| Pipelines construits, première fenêtre | 535 calcul (1,2 s) + 3 059 graphiques | 8 à 113 calcul, 1 graphique |
| Pipelines de calcul ensuite | 0 (tous prêts) | environ 10 par fenêtre, environ 500 ms chacun |
| Bibliothèques du cache MoltenVK compilées à la première utilisation | 2 816 en 908 ms | moins de 256 par session ; la première en 135 ms (0 ms dans la 822) |
| Compilations propres (journal des constructions), seconde session | — | 2 |

MoltenVK et son MSL sont identiques entre les deux Core. Le temps perdu est donc la compilation par Metal du MSL déjà
en cache : le cache Metal du système était vide ou purgé. La cause de la purge n'est pas connue (installation, iOS,
place disque). La seconde session de la 824, réchauffée par la première, construit 113 pipelines de calcul dans sa
première fenêtre.

## Pourquoi cela tue le jeu

- Un dispatch de calcul ne peut pas être sauté. Le fil de rendu attend chaque pipeline qui lui manque
  (`BackgroundCompilationScheduler.WaitForPipelineAtDraw`, sans limite), les uns après les autres.
- Le travail GPU de l'invité s'arrête, et l'invité avec lui. À 0,5 à 1 s par programme de calcul (535 en tout pour
  Hogwarts), la première image dure plus que les 25 s du chien de garde.
- Selon l'utilisateur, la fin était la même avec l'IPA précédente : ce n'est pas une régression du code de la 824.

## Correctif : `adapt_compile_wait_guest_time`

Sur console, aucun jeu n'attend jamais la compilation d'un pipeline : les shaders sont compilés d'avance. Le temps que
l'invité mesure pendant une telle attente appartient donc à l'émulateur, pas au jeu.

- `GuestTimeHold` (nouveau fichier de `Ryujinx.Common`) entoure l'attente des dessins et des dispatchs du fil de rendu
  (`WaitForPipelineAtDraw`, son corps inchangé).
- Une attente de moins de 33 ms ne touche jamais l'horloge. Au-delà, une minuterie arrête l'horloge de l'invité jusqu'à
  la fin de l'attente.
- Une attente qui commence moins de 250 ms après la fin d'une attente tenue est tenue dès son début. Une rafale de
  compilations ne montre ainsi à l'invité que 33 ms, plus le rendu entre elles.
- `TickSource` (compteur CNTPCT du JIT, `svcGetSystemTick`, services de temps) se fige pour deux raisons : la tenue et
  la pause. La pause passe désormais par l'instantané : le chronomètre n'est plus jamais arrêté sous ses lecteurs.
- L'horloge ne recule jamais, quel que soit le fil qui la lit. Si un remplacement d'instantané échoue, l'ancien est
  republié. Un jeton d'une session précédente est ignoré.
- Le moteur Vulkan atteint `GuestTimeHold` par trois délégués publiés dans `AppContext` : aucun type partagé, aucune
  doublure de test à modifier.

Une relecture indépendante de la première version a relevé six défauts, tous corrigés avant l'envoi :

- une dérive de l'horloge par les attentes courtes (pipelines des shaders utilitaires à chaque présentation) ;
- un `TickScalar` lu à 0 pendant une transition, alors que SurfaceFlinger divise par cette valeur ;
- une exception pendant une transition, qui figeait l'horloge pour de bon ;
- une attente d'une session précédente ;
- la pause non sûre face aux lectures concurrentes ;
- un budget de 33 ms compté par attente au lieu de l'être par rafale.

Rien ne change de ce qui est compilé, de l'ordre, de ce qu'un dessin attend ou lie, ni des dessins sautables. Un
pipeline que le fil de rendu crée lui-même, sans compilation en arrière-plan, n'est pas tenu.

Porte `compile-wait-guest-time` (65 vérifications, horloge de production) :

| | Contrôle | Candidat |
|---|---|---|
| 200 000 attentes courtes : temps invité / hôte | 66,4 / 66,3 ms | 92,9 / 92,7 ms (aucune dérive) |
| Attente de 600 ms vue par l'invité | 600,6 ms | 37,4 ms |
| Attente de 10 ms vue par l'invité | 10,3 ms | 10,3 ms |
| Pulsation modèle (2 s, une image = 16 attentes de 150 ms) | « bloqué » (écart 2,4 s) | aucun blocage (images de 51 et 17 ms) |
| Lectures en arrière sous pauses concurrentes (entre fils / même fil) | 53,8 millions / 23 700 | 0 / 0 |
| `TickScalar` lu à 0 | 0 | 0 sur 2,4 milliards de lectures |
| Coût d'une lecture | 49 ns | 53 ns |

Le contrôle montre que des pauses et reprises concurrentes faisaient déjà reculer l'horloge de l'invité. Le candidat
corrige aussi ce défaut. Les assemblages de production HLE et Vulkan compilent sans avertissement dans les fichiers
modifiés.

## À lire dans les journaux de la prochaine IPA

- Une ligne « Pipeline compile wait of N ms on the guest's GPU path » par attente d'au moins 1 s, pour les 16
  premières.
- Dans la ligne des étapes de rendu : « compile waits held from the guest's clock ».
- Réfuté si une session qui écrit ces lignes se termine encore par l'écriture du fil `FHeartBeatThread` à l'adresse 3.
- Si le cache Metal est vide, la première image de jeu peut rester figée longtemps (plusieurs dizaines de secondes à
  quelques minutes, non mesuré), puis le jeu repart. Les lancements suivants sont rapides.

## Risques

- Pendant une attente tenue, le temps de l'invité est arrêté alors que ses fils tournent : une boucle qui attend une
  échéance en temps invité attend la fin de la compilation.
- L'audio, la synchronisation verticale et le réseau suivent le temps hôte. L'horloge murale de l'invité prend du
  retard du temps caché, comme pour une pause.
- Un vrai blocage sur une compilation qui ne finit jamais figerait le jeu au lieu de le laisser se terminer.
