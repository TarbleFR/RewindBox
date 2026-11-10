# Sessions iPhone de la build 597 : observations vérifiées

## Identification et limites

Les nouveaux journaux détaillés RPCS3 et NeoSwap portent tous **build 597 / PID 51899**. Le téléphone expose un **Apple A18 Pro**, 7 989 460 992 octets de mémoire physique et **iOS 27.0 (24A5380h)**. Les entitlements mémoire sont présents. `thermalState=1` dans les 568 lignes NeoSwap.

Le core attendu pour l'IPA597 authentifiée est `88cdc5e3e115a0b8587711d77147467baf38128b`, PPU `a987639e9f838d1c`, SPU `477a3fa442d27917`. Ce rattachement provient du reçu de livraison et du numéro de build ; **ces pièces ne journalisent pas le SHA complet du core chargé**. Le choix CPU observé pendant GOW3 est `apple-m4`, avec les fonctionnalités ARM64 attendues.

Le journal des jalons conserve aussi des lignes 595 et 596. Le journal applicatif conserve plusieurs installations ; ses durées de soumission de lancement ne sont pas des temps jusqu'au gameplay. Aucune moyenne de FPS issue de ce fichier n'est calculée.

`RPCS3-performance(2).log` est intégralement inclus dans `RPCS3-diagnostic(6).log` : **1 464 doublons supprimés, 2 293 événements uniques**. Les clés de dédoublonnage sont build, PID, timestamp, stage et message. Le fichier `observed-build597.json` conserve les compteurs et les références fichier/ligne par fenêtre.

Les deux vidéos sont exactement les vidéos déjà présentes dans les preuves device595 : SHA256 `0098f502b3137e84bd203aeacb2d841caef6344b4ff9656d00b9031ae88cf3d5` et `b7e90925cf252f45b537e018fb28b165f17acffa99fc87d9c0c28cb473e05f0c`. Elles sont exclues de toute affirmation de changement visuel de la 597. Leur cadence d'encodage ne mesure pas la cadence du jeu.

## Sessions de la 597

Les horaires suivants sont ceux des rapports de fin du démarrage JIT, en **Europe/Paris, le 30 octobre 2026**.

| Session RPCS3 | Jeu | Démarrage | Heure | Fenêtres détaillées conservées |
| --- | --- | --- | --- | --- |
| 1 | BO2 BLES01717 | Normal | 02:51:48 | Aucune |
| 2 | BO2 BLES01717 | Normal | 02:52:22 | Aucune |
| 3 | Assassin's Creed BLES00158 | Normal | 02:54:45 | 40 partielle, 41–44 actives, 45–46 fermeture |
| 4 | GOW3 BCES00510 | Normal | 02:58:40 | 1 préparation, 2–28 invité, 29 restauration |
| 5 | GOW3 BCES00510 | Savestate | 03:01:10 | 1 préparation, 2–16 invité |

Source : `RPCS3-milestones(6).log`, lignes 163, 168, 176, 185 et 214. Le chargement du savestate se termine à 03:01:15.516 (ligne 217).

La fin des logs détaillés commence pendant Assassin's Creed : **le retour utilisateur BO2 est valide comme observation déclarée, mais son gain, ses saccades et l'absence de gel ne peuvent pas être quantifiés avec ces fenêtres conservées**.

## Assassin's Creed : coût persistant sans compilation

Fenêtres 41–44 de la session 3 : **577 intervalles invités sur 20 716,956 ms**, soit **27,852 images/s calculées sur les intervalles terminés**. Les moyennes de fenêtres vont de 26,681 à 30,053 images/s ; les p95 de fenêtres vont de 41,568 à 42,852 ms. Six intervalles dépassent 50 ms, aucun 100 ms ; maximum 61,802 ms.

Les quatre fenêtres contiennent **zéro compilation source, module, pipeline graphique ou compute, et zéro tentative de construction/chargement SPU**. Les temps échantillonnés de texture sont de **6,100 à 9,377 ms/image**, ceux des sommets de **2,366 à 2,721 ms/image**. Le SPU consomme 2,158–2,204 équivalents cœur et les threads RSX 0,974–1,019. Ces temps CPU recouvrent plusieurs threads ; ils ne s'additionnent pas pour calculer un temps d'image.

La fenêtre 41 comporte 161 110 échecs PUTLLC / 671 110 succès, 57 532 passages lourds, 284,966 ms d'attentes de plages VM sur tous les épisodes. La fenêtre 42 en comporte 162 559 / 593 490, 56 065 passages lourds et 358,885 ms d'attentes VM. Les attentes GETLLAR mesurées restent bien plus petites. Ce sont des pistes de coût, pas la démonstration d'un défaut de synchronisation.

La prélecture spéculative de hash est inactive sur ces fenêtres (`OPT581` : zéro hit, miss et travail), alors que le streaming asynchrone des textures est actif. Une optimisation du préhash GOW3 ne doit donc pas être présentée comme solution de ces saccades AC.

Références : diagnostic lignes 43–205 (fenêtres complètes, lignes distinctes dans le JSON). Le relevé 595 démontrait déjà des saccades sans compilation, dont une fenêtre p95 48,62 ms. Les scènes ne sont pas alignées : **aucun pourcentage de gain 595/597 n'est calculé**.

## GOW3 : blocage normal et ralentissement après restauration

### Démarrage normal

Le **30 octobre à 03:00:57.290**, `RSX_ACQUIRE` attend encore le label `0x60300510`, avec **`0x1A24` attendu et `0x1A23` observé**, après **2 001 715 µs**. Source : milestones ligne 187, diagnostic ligne 1462. L'ancien relevé 595 attendait la même adresse avec `0x6F0E` / `0x6F0D`. Les valeurs et la scène diffèrent ; l'invariant d'un incrément manquant persiste. Aucun événement de résolution ne figure avant la restauration suivante.

**Piège de mesure :** fenêtre 28, le compteur affiche environ 60,26 images/s, mais uniquement sur **13 intervalles terminés / 215,742 ms**, dans une fenêtre de **5 078,760 ms**. La pause terminale n'a pas encore d'intervalle achevé. Cela ne prouve absolument pas 60 images/s pendant le gel. Référence : diagnostic ligne 1469, `FRAMEPROF527`.

Le lancement normal réutilise ses 40 modules PPU ; les deux premières fenêtres SPU comptent au total 2 633 hits d'objets, zéro miss. Les libellés historiques `spu_compiles` incluent ces chargements : ils ne démontrent pas une recompilation LLVM de ces objets.

### Après le savestate

Les fenêtres 2–16 comptent 1 418 intervalles invités / 76 317,447 ms, soit **18,580 images/s** dans la portion retenue. La scène n'est pas identifiée par le journal ; ce chiffre ne constitue pas une comparaison avant/après. Treize fenêtres n'ont ni compilation shader ni tentative de construction/chargement SPU.

| Fenêtre | FPS par intervalles terminés | p95 (ms) | Textures échantillonnées (ms/image) | Sommets (ms/image) | Cœurs SPU |
| --- | ---: | ---: | ---: | ---: | ---: |
| 14 | 13,657 | 99,917 | 17,264 | 3,562 | 3,339 |
| 15 | 12,988 | 95,623 | 12,313 | 3,293 | 3,395 |
| 16 | 9,557 | 170,923 | 11,132 | 6,860 | 3,048 |

Aucune de ces trois fenêtres ne compile de shaders ou n'entre dans un chargement SPU. Les temps GPU restent indisponibles (`gpu_time_ms=-1`). Les appels PUTLLC réussis restent nombreux (1,93–2,72 millions par fenêtre), mais les attentes de plages VM ne représentent que 42,599–81,429 ms cumulées par fenêtre d'environ cinq secondes ; ces attentes mesurées ne suffisent pas à attribuer la totalité du coût SPU à de la contention.

Références : diagnostic lignes 2182–2293. Les workers de préhash réalisent environ 0,76–1,41 seconde de travail cumulée par fenêtre sur le savestate. Leurs lectures et les validations consommatrices peuvent lire plusieurs fois le même contenu ; les volumes de `OPT581` sont des plages de hash, pas des transferts GPU ni des octets tous inutiles.

## Mémoire et NeoSwap

Les compteurs NeoSwap sont un échantillonnage distinct : `sessionSequence=2` correspond ici à AC et `3` couvre **les deux sessions RPCS3 GOW3**, lancement normal puis restauration. Ne pas les joindre naïvement au numéro de session JIT.

Deux avertissements iOS surviennent pendant les dernières fenêtres GOW3 :

| Heure Paris | Empreinte (MiB) | Résident (MiB) | Ledger compressé (MiB) | Marge du processus (MiB) |
| --- | ---: | ---: | ---: | ---: |
| 03:02:19.391 | 5 222,79 | 1 722,02 | 2 425,36 | 1 506,05 |
| 03:02:32.181 | 5 256,62 | 1 639,86 | 2 529,05 | 1 399,38 |

Sources : NeoSwap lignes 552 et 565. La hausse de compression et les avertissements coïncident avec le ralentissement ; ils ne suffisent pas à isoler sa cause. `thermalState` reste 1. Le log termine sur `application_background` à 03:02:32.225 ; aucun Jetsam confirmé ni crash n'est établi par ce dernier événement.

`donorLostCount=1` est déjà présent au début de l'extrait AC, puis remis à zéro lors de la fermeture. Aucun nouvel instant de perte de donneur n'est visible dans la portion retenue. Les compteurs I/O restent à zéro ; les durées maximales de `fastAllocation` restent à 103 µs, avec zéro échec de préparation/retrait. Une lenteur du courtier d'allocation n'est pas établie.

Pour AC, les valeurs mémoire imbriquées dans `shaderStorage` sont parfois vieilles de plus de trois minutes (`reason=unsupported_title`). Les mesures présentées ici utilisent uniquement `processFootprintBytes`, `processResidentBytes`, `processCompressedLedgerBytes` et `processAvailableBytes` au niveau racine.

## Orientations étayées pour les modifications

1. Réexaminer la cohérence des sommets/textures et l'invalidation du rendu BO2/AC ; les correctifs de shader tardif de la 597 ne constituent pas une preuve de disparition des défauts rapportés.
2. Pour GOW3, conserver le suivi du producteur du label. Ne pas forcer la valeur, supprimer une barrière ou augmenter un timeout pour masquer l'incrément absent.
3. Réduire le travail de validation/préhash lorsque l'équivalence est démontrable. GOW3 présente des centaines de millisecondes de hash par fenêtre ; AC utilise un autre chemin.
4. Examiner les reprises de buffers et copies CPU : les coûts de sommets augmentent dans les dernières fenêtres sans nouvelle compilation.
5. Préserver les limites NeoSwap : pas de hausse arbitraire de budget en présence d'avertissements iOS et de compression croissante.

Ces observations concernent **le binaire livré 597**, pas le prochain candidat source. Aucun résultat de FPS supplémentaire ni correction visuelle du prochain candidat n'est revendiqué.

## Reproduction

```sh
python3 analyze.py --input /chemin/des/sept-pieces \
  --repo /chemin/de/la/source-RewindBox-597 \
  --output observed-build597.json
```

Le parseur lit les pièces sans les modifier. Il ne compile aucun moteur et ne lance aucun test natif.
