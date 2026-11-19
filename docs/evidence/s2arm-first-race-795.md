# Mario Kart World — préparation graphique après la 794

La révision graphique 1 concerne le titre `0400C3F00006E000`, le build NSO `9e244438c3d8ef1c703a6a85ef99c4f0` et la chaîne de traduction `0be3f28548fd`. L’import et la préparation du code CPU conservent leur identité. Le pont teste la révision graphique même quand le journal dit `prepare: reused`. En français, le message de mise à jour est **« Reconstruction des shaders et des pipelines graphiques »**. Il est suivi du nombre de fichiers parcourus puis des compteurs de progression.

## Mesures de référence sur iPhone 16 Pro Max

Le journal du processus 4953 montre le chemin de réutilisation de la 794. L’empreinte SHA-256 de son `host.log` est `29ac89238ddaf9c6eae9de21b9eeaa9298824a6f75013892c7ee0acc390eb539`. Le préchauffage existant a pris 10,679 s en arrière-plan. Il a traité 3 680 shaders, 4 506 pipelines graphiques et 172 pipelines de calcul. Metal a satisfait 4 678 créations à partir de l’archive. Le moteur a écarté 369 lignes pour 196 identités de shader sans traduction actuelle ni entrée conservée.

| Image | Temps d’image | Soumission et présentation | GPU | Autres mesures |
| ---: | ---: | ---: | ---: | --- |
| 228 | 4 044,4 ms | 20,6 ms | 2,5 ms | 12,8 ms de transfert de texture, 70,8 Mio lus par le processus |
| 1 379 | 3 145,9 ms | 1,8 ms | 5,5 ms | Aucun nouveau pipeline, bibliothèque ou transfert. Le processus a lu 63,1 Mio |
| 1 640 | 735,9 ms | 599,1 ms | 46,0 ms | 778 premiers transferts, 123,2 Mio en 351,5 ms |
| 4 815 | 1 157,9 ms | 1 098,7 ms | 22,7 ms | Attente de traduction de 111,7 ms, un appel de compilation de bibliothèque MSL de 674,1 ms, attentes de pipelines de 197,4 et 68,7 ms |

Les 769 lignes de ralentissement publiées comprennent **105 images au-delà de 100 ms, 35 au-delà de 200 ms et 9 au-delà de 500 ms**. Le filtre du journal donne des bornes inférieures pour la session. Sur ces lignes, le fil de soumission a attendu 12 traductions pour un total de 1 212,4 ms et a effectué 10 compilations à partir de MSL pour 701,8 ms. Les 14 attentes détaillées de pipelines totalisent 653,3 ms. Les bilans de premiers usages publiés comptent 23 dessins classiques sautés et zéro dessin task/mesh sauté pour ce motif.

Dans la fenêtre de 300 images qui se termine à l’image 5 100, les temps d’image p95 et p99 sont de 68,90 et 270,16 ms. Les 20 relevés de mémoire culminent à 5 175 Mio. L’état thermique relevé est nominal puis `fair`. Le gouverneur est aussi passé en HOLD, puis en RUN, alors que l’état thermique était encore nominal, sous l’effet de la mémoire disponible. Les FPS moyens et les centiles de la session entière nécessitent ses intervalles individuels.

## Premier lancement après mise à jour

Le moteur utilise les descriptions complètes du profil commun et recherche les deux variantes du circuit dans le manifeste personnel hérité de la 794. Le premier appel de soumission du jeu attend la construction du lot obligatoire et sa vérification par relecture de l’archive Metal. Les entrées ordinaires du manifeste personnel continuent en arrière-plan. Une suspension thermique reporte les admissions facultatives. L’arrêt de session conserve les points de reprise.

Le reçu d’une génération validée permet à l’ouverture suivante de retrouver les archives. Pour vérifier leur effet dans une course, le journal distingue les constructions de bibliothèque depuis le MSL, les créations de pipelines, les relectures strictes de l’archive et la première liaison de l’objet préchauffé dans l’encodeur. Les lignes de `stage-recovery.tsv` identifient individuellement les retraductions et les entrées originales encore absentes.

## Sources des variantes

Le profil livré comprend 12 lignes R de 432 octets et 58 lignes S. Pour chaque R, les 20 premiers octets du SHA-256 de l’état complet correspondent à l’identité d’archive enregistrée sur le jeu. Les traces situent les observations entre les images 0 et 9 830 de leurs parcours respectifs. L’association exhaustive entre ces images et les écrans de choix de pilote, de véhicule ou de circuit demande une capture synchronisée. Les traces et leurs numéros d’image sont identifiés dans [les empreintes de référence](s2arm-mkw-reference/reference-evidence.json). Le [manifeste lisible](s2arm-mkw-reference/reference-0400C3F00006E000.tsv) suit le format de `graphics/tools/direct/pso_seed.py`.

Pour l’image 4 815, les identités exactes sont `ba2073dfd3a104a3130bc7ab5212f7ff77144f32` (vertex `2524467d394b8e2e`) et `69097fd97c7b8882373adb1caa67c2ad72f64765` (vertex `c5984a7abe090de0`). Les deux utilisent le fragment `eb4884ca0964a92f`. Le journal de la 794 contient ces identités. Les fichiers reçus ne contiennent pas les deux descriptions complètes. Le moteur peut les vérifier dans le manifeste local de l’installation 794. Une recette différée conserve ce statut jusqu’à la rencontre de l’état exact.

## Vérification sur l’appareil

1. Utiliser le même export du jeu, le même circuit, pilote, véhicule, résolution, limite de FPS et mode d’alimentation sur les deux IPA. Noter la version d’iOS, l’état thermique et la mémoire au départ. Conserver la même copie initiale des données pour chaque branche de la comparaison.
2. Installer la 795 sur la 794 et ouvrir le jeu déjà préparé. Chronométrer du premier message de reconstruction à la validation des archives. Quitter pendant la préparation sur une copie de l’essai, puis reprendre. Conserver les reçus de génération avant et après. Une seconde ouverture validée doit sélectionner la même génération.
3. Tester également une première course sur une copie de référence avec un historique joueur vide. Refaire le passage à chaud, puis un troisième passage et la reprise après chauffe. La génération de production et la sauvegarde du joueur peuvent rester en place pendant les essais ordinaires.
4. Récupérer pour **chaque lancement** le `host.log`, le `s2arm-journal.jsonl`, les fichiers de signatures `frames.txt` de ce lancement et le dossier `Diagnostics/S2Arm/engine/<gid>/preparation/<UUID>` identifié dans ce journal. Conserver la vidéo ou les images du départ et des premières zones pour la comparaison visuelle. Les fichiers de profil d’une autre session produiraient des centiles trompeurs.
5. Exécuter `python3 tools/s2arm_prototype/shader_session_metrics.py host.log frames.txt --first DEBUT --last FIN` sur les mêmes segments. Les fenêtres complètes du nouveau moteur fournissent aussi les trois seuils même si le journal filtre les images individuelles. Comparer le temps hors des appels submit/present et le plus long intervalle directement mesuré. Le temps CPU global du processus seul ne permet pas d’attribuer les pauses aux threads du jeu.
6. Confronter les lignes de récupération et de traduction, les créations de bibliothèques, les créations de PSO, la relecture stricte et la liaison dans l’encodeur. Pour le cas 4 815, exiger une ligne de liaison de l’objet préchauffé pour **chacune** des deux identités dès son premier dessin. Comparer les compteurs de dessins sautés aux signatures et à la vidéo.

Aucune capture iPhone de la 795 appariée avec cette capture de la 794 n’est disponible au moment de la préparation du candidat.

## Livraison privée 795

Le run [44562030688](https://github.com/TarbleFR/RewindBox/actions/runs/44562030688) a produit l’IPA au commit `81e4b8963c1c749d76f5220cdbb3fa49c233c914`. Le téléchargement vérifié contient 333 297 719 octets et 97 images natives. Son SHA-256 est `5d598aea119dba67e67c8f87294f1692d30b99074cb2f59cd9864ac2eb714858`. Les 6 vérificateurs hors CI ont réussi.

Le moteur installé provient du [producteur 44558981086](https://github.com/TarbleFR/RewindBox/actions/runs/44558981086), artefact `14550055216`. SHA-256 du binaire arm64 `d9f0da1286c7600f7bc79b24a8156355fa1c9147bdd6878af2fb8ec11769dea0`, empreinte de sa charge utile `b46ac2153c20c23b9da3786dcd93f1094acb1625e9d8e6e679a693c3dd34f1e1`. La bibliothèque de préparation provient du [run 44555747908](https://github.com/TarbleFR/RewindBox/actions/runs/44555747908). SHA-256 du XCFramework compressé `80ed6cd43bdc67fa1936f5ec130f29ffb309c1ad41d39ab068dfc16f76f53b4c`.

| Pont | Comparaison avec la 794 |
| --- | --- |
| `armsx2_internal_bridge` | Même code après normalisation des références équivalentes à objc_msgSend |
| `libretro_internal_bridge` | Même code après normalisation des références équivalentes à objc_msgSend |
| `melonx_internal_bridge` | Empreinte identique |
| `rpcs3_internal_bridge` | Même code après normalisation des références équivalentes à objc_msgSend |

Les deux IPA signées ont été comparées pour ARMSX2. Les 935 chargements ARM64 qui diffèrent désignent le même symbole `_objc_msgSend` de la même bibliothèque. Les 65 exports, les 24 dépendances et la section de code du pont coïncident. Les autres différences d’octets se trouvent dans l’UUID et la signature. Le contrôle se reproduit avec `tools/s2arm_prototype/verify_bridge_stubs.py --include-armsx2`, l’IPA et les deux inventaires signés. [Comparaison ARMSX2](rewind795/qualification/armsx2-794-795.json)

| Contrôle Actions | Portée | Étapes ou résultats confirmés |
| --- | --- | --- |
| [Job 135682716146](https://github.com/TarbleFR/RewindBox/actions/runs/44558981086/job/135682716146) | Source qualifiée `14347e79` | Check adaptive shader cache changes, Measure gaps across concurrent submissions and presentation, Verify shader-library sharing and warm priority on the Mac GPU, Read back a texture prepared from an earlier recorded bind, Check the guest entry points of the framework (patches 0003-0010), Package the guest frameworks for RewindBox's delivery (macos-26 only), active-hold-urgent-run, close-unblocks-verification, first-submit-mandatory-barrier, game-stage-parsers, required-stage-failure, 12 recettes complètes, 2 PSO relus strictement sur 2 objets, pixel contrôlé |
| [Job 135671190758](https://github.com/TarbleFR/RewindBox/actions/runs/44555747908/job/135671190758) | Source qualifiée `f299358c` | Check the bounded decoder used by shader indexing, Build S2ArmPrepare.xcframework |
| [Job 135693863216](https://github.com/TarbleFR/RewindBox/actions/runs/44562100663/job/135693863216) | Source exacte de l’IPA (moteur), déclencheur `0db0ebbb` `81e4b896` | Verify the tested source equals the delivered engine pin, Check adaptive shader cache changes, Measure gaps across concurrent submissions and presentation, Verify shader-library sharing and warm priority on the Mac GPU, Read back a texture prepared from an earlier recorded bind, active-hold-urgent-run, close-unblocks-verification, first-submit-mandatory-barrier, game-stage-parsers, required-stage-failure, 12 recettes complètes, 2 PSO relus strictement sur 2 objets, pixel contrôlé |
| [Job 135693862339](https://github.com/TarbleFR/RewindBox/actions/runs/44562100572/job/135693862339) | Source exacte de l’IPA (pont iOS), déclencheur `0db0ebbb` `81e4b896` | Compile the bridge sources for iOS arm64, Upgrade, interrupt and reopen a prepared graphics generation, Bridge, session and preparation identity contracts, migration-and-repair, a reused game reports its separate graphics preparation and progress, retrying an interrupted graphics launch admits only the same unconfigured game, 11 unités iOS arm64 compilées, 17 tests du menu, 252 contrôles (bridge), 42 contrôles (park and resume), 20 contrôles (CPU identity) |

Les suites générales ont le statut `not-run` pour Flutter et `not-run` pour les tests natifs. Le contrat de livraison a été exécuté. La fluidité, la température et la fidélité graphique de cette IPA sur iPhone restent à mesurer.

[Inventaire signé](rewind795/signed-payload-identity.json) · [Contrôle du téléchargement](rewind795/download795-verification.json) · [Reçu de livraison](rewind795/delivery.json)

### Observations du test Metal sur Mac

Sur le GPU Apple paravirtualisé, la fixture avec historique vide et programmes de test a résolu trois fonctions, créé trois bibliothèques depuis le MSL et forcé deux créations de PSO. Les deux descripteurs ont réussi la relecture stricte de l’archive. L’encodeur a lié les deux objets et la lecture des pixels a réussi. À la relance de cette fixture, Metal a de nouveau créé trois bibliothèques depuis le MSL. Il a servi les deux PSO depuis l’archive avec zéro création forcée de PSO. Après interruption au premier reçu strict, une seule création de PSO a été forcée à la reprise. Un sommet obligatoire refusé a empêché l’activation malgré la présence d’une archive copiée.

Le test de migration a forcé la retraduction NativeAOT d’une entrée prioritaire dont l’ancien MSL restait compatible et a vérifié sa reprise avant publication. La fixture de récupération a passé un fragment NVN2 par le traducteur NativeAOT de production, puis par Metal. La valeur RGBA32Uint relue était `0000002a 00000007 00000063 00000001`. La fixture de texture a contrôlé la première utilisation après un transfert anticipé de 262 144 octets, puis tous les texels après une écriture du jeu. Le nombre de clés récupérées sur les 196 de l’installation 794 et les attentes des deux pipelines de l’image 4 815 restent à lire dans les diagnostics de l’iPhone.

Le SHA-256 du moteur signé extrait de l’IPA est `41f0009fc2e6098bc893da0795d6ca831ea6807e1d394cb3cb759c5429d9fe5a`. Le contrôle ARM64 retrouve dans le Runner signé les deux décodeurs de shaders transmis au moteur. Les chemins des liaisons de textures observées atteignent les fonctions d’anticipation. [Moteur signé](rewind795/qualification/engine-signed.json) · [Runner signé](rewind795/qualification/runner-signed.json)
