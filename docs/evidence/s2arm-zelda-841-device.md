# Zelda 841 : lecture des deux profils sur iPhone

Relevé du 25 novembre 2026, titre `0400486024DEC000`, appareil A18 Pro indiqué par le mainteneur. **La pleine vitesse en 3D n'est pas atteinte.** Ces deux fichiers env activent des diagnostics différents ; ils ne comparent pas une optimisation CPU à une optimisation GPU. Les nouveaux modes allocateur, dispatch et priorité PSO restent désactivés. Aucun changement du moteur ni nouvelle IPA dans ce relevé.

Le mainteneur observe 10–15 puis 20–25 FPS, rarement 40, un jeu ralenti, des gels à l'apparition des décors, aucun défaut graphique ou audio. Le profil GPU est ressenti plus lent. Ces observations sont conservées comme retour utilisateur ; elles ne constituent pas un replay de pixels déterministe.

## Sources et couverture

Les archives contiennent aussi des sessions anciennes. Les deux sessions utiles sont sélectionnées par la présence effective des compteurs, pas par le seul nom des ZIP :

| Capture | Journal Zelda | SHA-256 | Reconnaissance |
|---|---|---|---|
| CPU | `host-20261125-102948.log` | `f6bc748177e6a9a3e680719a44d7393920c3333bd6a75c2e4e131b8e0f929dfa` | 25 rapports réveils, aucune ligne GPUDIAG |
| GPU | `host.log` | `3cf018e1ea13c32c61004eb96d64fcf767715d9d452706f126bd9ebf159991ff` | 94 219 lignes GPUDIAG, aucun rapport réveils |

Archive moteur : `engine(20261125-094316).zip`, SHA-256 `5a4f37a5a8af8763b88da13091514d0c0d396b99592895779074a9fd3039b699`. Archive profils : `profiles(20261125-094317).zip`, SHA-256 `166739dcf11fe4842f9c600bbef9a88a243055fe6eb3d8fa9f545a2ecc4b8e68`. Neuf captures CPU de quatre secondes portent des horodatages 10:20–10:37 ; elles ne sont pas neuf fenêtres de 180 secondes. Les heures des fichiers sont reproduites telles quelles, sans conversion supposée.

Les formats et les options correspondent au moteur livré en 841 ; le host.log ne prouve pas à lui seul le SHA de l'IPA installée. Le journal `host-20261125-101848.log`, sans ces diagnostics, reste distinct des deux profils demandés.

Les plages ci-dessous couvrent les rapports de 300 images en 3D après la première transition. Elles ont des contenus et durées différents. Ce ne sont **ni des fenêtres A/B appariées ni des percentiles calculés sur toute la session**. Les bornes sont des instantanés réellement présents : aucune valeur initiale n'est inventée.

## Vitesse, GPU et attentes

| Mesure | Diagnostic CPU, 2700 → 6900 | Diagnostic GPU, 3600 → 5700 |
|---|---:|---:|
| Images entre bornes | 4200 | 2100 |
| FPS des rapports de 300 images | 14,5–34,3 | 14,7–24,8 |
| Vitesse `[rb-speed]` | 24,2–57,2 % | 24,5–41,3 % |
| GPU p50 de chaque rapport | 21,96–36,89 ms | 24,62–34,00 ms |
| Δ attente allocateurs | 19 884,933 ms | 15 070,945 ms |
| Attente allocateurs par image | **4,734508 ms** | **7,176640 ms** |
| Δ attente visibilité | 0 ms | 0 ms |
| Δ waits de file enregistrés | 3795 | 1769 |
| Δ drains de file et durée | 0 ; 0 ms | 0 ; 0 ms |
| États thermiques des rapports de cette plage | Fair | Serious |

Le seuil d'essai de `S2A_RB_ALLOC_FRAME=1` est nettement franchi. Ce mode existe dans la 841 mais les deux configurations fournies imposaient `0`. Les attentes n'ont donc pas disparu ; une amélioration par rapport aux anciennes 4,4–7,2 ms agrégées n'est pas démontrée. Le zéro visibilité est cohérent avec la réservation à la demande, sans établir un gain causal face à une scène antérieure.

Ces attentes CPU ne sont pas des millisecondes que l'on peut soustraire au GPU : une partie peut simplement refléter son retard. Même les GPU p50 de la capture CPU exigent une réduction d'environ **24–55 %** pour atteindre 16,6 ms, selon la fenêtre. L'allocateur seul ne promet donc pas 60 FPS.

Les rapports des menus atteignent environ 100 % / 60 FPS. Dans la capture CPU, le retour à une scène légère atteint 99,6 % / 59,8 FPS au rapport 7500 ; ce point n'est pas une preuve de pleine vitesse en 3D. L'horloge invitée rapportée reste 1,000 seconde par seconde et les fenêtres en 3D restent à l'intervalle invité 1, sans attente de pacing par présentation. Le ralentissement observé n'est pas un nouveau limiteur de cadence dans ces captures.

## Les gels ne viennent pas uniquement des shaders

| Capture et image | Durée de l'image | Travail de compilation rapporté | Uploads | Lecture disque du processus |
|---|---:|---:|---:|---:|
| CPU 2550 | 3634,1 ms | 12,0 ms | 94,8 Mo ; 1296,8 ms | 550,9 Mo |
| CPU 2570 | 2609,8 ms | 12,8 ms | 392,2 Mo ; 1671,9 ms | 498,9 Mo |
| CPU 2717 | 3967,1 ms | 3593,2 ms | 0 | 552,8 Mo |
| GPU 3567 | 1423,1 ms | 6,4 ms | 366,1 Mo ; 984,9 ms | 469,0 Mo |
| GPU 5319 | 1213,1 ms | 914,8 ms | 0 | 0,8 Mo |

Ces postes peuvent se recouvrir et ne s'additionnent pas en un budget exclusif. La lecture disque est celle du processus, pas uniquement celle des shaders ou des textures. Au CPU 2717, la soumission compile aussi trois bibliothèques MSL pour 2316,7 ms et attend une traduction en vol 256,6 ms. Déplacer seulement la création des PSO ne traite donc pas tout le chemin froid.

Les premières utilisations journalisées atteignent 770,2 ms dans le profil CPU et 537,4 ms dans le profil GPU. Le compteur ordinal et les lignes filtrées ne permettent pas d'en déduire un nombre exhaustif de toutes les attentes.

Le cache persistant n'est pas vide : 1520 pipelines / 196,6 Mo sont annoncés au démarrage CPU, 1561 / 204,2 Mo au démarrage GPU. Le préchauffage reconstruit respectivement 1510 et 1551 pipelines depuis les archives, avec zéro compilation PSO signalée dans ce préchauffage. Les premières utilisations de variantes ou décors nouveaux restent à traiter. Ces chiffres ne prouvent aucune saturation ou éviction entre jeux du cache système iOS ; l'hypothèse de 1,33 Go reste non vérifiée.

## Réveils : sources maintenant identifiées

Différences des compteurs CPU 2700 → 6900, sur **161,764930 secondes** mesurées par les deux en-têtes monotones de réveils :

| Emplacement du moteur 0378 | Type | Retours/s | Signaux/s |
|---|---|---:|---:|
| `runtime/src/thread.c:655` | Attente sur adresse des fils invités | 6877,8 | 0 |
| `runtime/src/thread.c:379` | Signal correspondant | 0 | 6683,5 |
| `runtime/src/thread.c:2346` | Sommeil du backoff de yield | 2879,0 | 0 |
| `graphics/nvn/gfx/nvn/nvn_rec.h:341` | Attente de dm-encode | 1244,3 | 0 |
| `graphics/nvn/gfx/nvn/nvn_rec.h:361` | Signal au worker d'encodage | 0 | 1246,5 |
| `runtime/src/thread.c:516` | Attente temporisée du jeu | 1021,0 | 0 |
| `runtime/src/thread.c:2914` | Sommeil court | 280,6 | 0 |
| `rb_fence_wait.h:31` | Attente de fence | 82,5 | 0 |

Le sommeil de yield à la ligne 2346 représente 465 729 retours, et 465 724 entrées à délai ≤1 ms dans cette plage. **Ce sont des appels/retours d'API, pas des interruptions du noyau.** Un signal n'implique pas qu'un thread dormait ; un retour d'attente peut être résolu en espace utilisateur. Ne pas additionner les deux côtés d'une même synchronisation pour expliquer artificiellement les 13 410 interruptions/s historiques. Les compteurs noyau rapportent ici 3258–6928/s par fenêtre CPU, contre 5401–10 990/s dans les fenêtres GPU ; les sessions non appariées ne prouvent aucune baisse avant/après.

La première piste CPU devient le mécanisme de yield et d'attente des travailleurs, pas un allongement arbitraire de tous leurs délais. Toute correction devra garder une notification observable, respecter les échéances invitées et mesurer la latence de reprise. Aucun délai de jeu n'est modifié dans ce relevé.

## GPUDIAG : coût des passes et limites du diagnostic

Sur les 2100 images GPU 3601–5700 : **102–142 passes/image, médiane 117**. À 854×480, en sommant les réouvertures des différentes ressources de même rôle et dimensions par image : couleur médiane 24, profondeur médiane 25. Cela ne désigne pas une seule texture ni nécessairement la seule cible principale.

La fermeture `rp_flush:11045` représente 221 025 appels attribués. Le compteur pointe principalement vers le helper, ce qui ne révèle pas son appelant initial. Avant une refonte de fusion des passes ou de mémoire de tuile, il faut propager cette cause à travers `rp_flush`. Les autres causes observées incluent la préparation de feedback, les clears en attente, les changements de commande, les dessins et les découpages de soumission. Une fermeture enregistrée n'est pas une passe que l'on a prouvé pouvoir supprimer.

Au rapport 5700, la fenêtre annonce **131 Mo de load et 135 Mo de store par image**. Il s'agit d'octets logiques d'attachements ; la bande passante DRAM physique et ses watts ne sont pas mesurés. Les refus de lecture UBO attribués à une soumission antérieure encore active restent présents (4636 dans cette fenêtre). Les retirer sans preuve de dépendance serait incorrect.

Le relevé des shaders expose deux limites à corriger avant d'en tirer des correctifs de profondeur :

- Les 2112 lignes shader de la session ont `guest_early=0`, ce qui signifie **inconnu**, et non « faux ». Zéro `missing_requested_early` ne prouve donc pas que toutes les demandes sont respectées.
- Le tableau de 256 clés sature à chaque fenêtre 3D. Sur la plage retenue, 135 721 observations de dessins ne sont pas enregistrées dans ce tableau (`dropped_keys`, malgré son nom). Les 393 clés distinctes enregistrées incluent 106 bibliothèques avec opération OR atomique et la clé `56299ef2536d6a84_b`, vue sur 1 072 427 dessins avec profondeur. Les faits lexicaux d'une bibliothèque complète ne prouvent ni l'exécution de l'instruction par l'entrée spécialisée ni la désactivation matérielle d'early-Z.

Le compteur de passes reste exploitable, mais 27 observations de nouvelles cibles sont perdues et zéro cause de coupure n'est perdue dans cette plage. L'absence d'artefacts rapportée par le mainteneur est utile ; le replay déterministe sans différence de pixels reste à exécuter.

## Thermique et sonde

Le profil CPU démarre Nominal puis reste Fair dans les relevés ; aucun Serious n'y est enregistré. Le profil GPU démarre Fair et passe Serious, premier heartbeat en état 2 à l'image 3875. Le toucher du téléphone ne permet donc pas de conclure à l'état thermique iOS. La durée exacte en Serious n'est pas reconstruite à partir des seuls numéros d'images ; l'endurance de dix minutes reste à réaliser.

La sonde de travail fixe toutes les 30 images donne une médiane de **0,257 ms** en 3D CPU et **0,218 ms** en 3D GPU ; dans les menus sélectionnés, 0,877 et 0,850 ms. La sonde accélère donc au passage en 3D dans ces captures : elles ne montrent pas une augmentation soutenue de sa durée expliquant à elle seule le GPU à 25–37 ms. Cela oriente vers le travail et les dépendances du rendu, sans exclure la gestion de puissance d'iOS. Cette durée n'est pas une fréquence en MHz, ni une mesure de puissance GPU.

## Ordre retenu pour la suite

| Priorité | Action | Critère de validation ; gain non encore mesuré |
|---|---|---|
| 1 | Essai isolé de l'allocateur par image, déjà livré | Trois fenêtres 180 s par mode, diagnostics coupés, mêmes scène/caches/résolution. Réduire l'attente actuellement 4,73 ms/image, avec p99, mémoire, rendu et chauffe stables. Ne pas promettre sa soustraction au temps GPU. |
| 2 | Préparation des premières variantes MSL/PSO et des pages de textures | Séparer les types de gels, comparer premier passage et passage chaud. Priorité PSO testée séparément ; pas d'activation combinée qui empêcherait l'attribution. |
| 3 | Compléter la couverture du diagnostic de passes et de profondeur | Cause initiale des appels `rp_flush`, métadonnée early-Z réellement disponible, saturation explicitement traitée ; garder le traducteur intact pour ce correctif diagnostic. |
| 4 | Lot traducteur livré seul | Lectures vectorielles, marque de pool et gather : candidats du plan, à valider ; aucune suppression forcée de discard/masque ni early-Z forcé à partir de ces seuls faits. Une seule retraduction avant le jeu et replay déterministe exact. |
| 5 | Économies TBDR puis résidences | Utiliser les causes prouvées ; bande passante physique, énergie et ≥10 min de thermique. Les 266 Mo logiques/image ne suffisent pas à chiffrer des watts. |

Les deux nouveaux fichiers A/B diffèrent **uniquement** par `S2A_RB_ALLOC_FRAME=0/1`. Ils conservent les 46 réglages d'origine, coupent WAKE_DIAG/GPUDIAG et gardent la même sonde à 30 images et les autres nouveaux modes de la 841 désactivés. Le mode candidat reste un essai, sans activation générale. Arrêter cet essai si défaut visuel, blocage ou alerte mémoire, conserver son journal et revenir au fichier A ; ne pas supprimer les caches.

Statut de ce suivi : **observations iPhone analysées ; aucun nouveau correctif moteur, test de moteur, build ou livraison d'IPA effectué**. Les tests antérieurs ne sont pas relancés pour une analyse de journaux. L'objectif 100 % / 60 FPS et l'absence de Serious prolongée ne sont pas validés.

## Reproduction

[Données dérivées](s2arm-zelda-841-device.json) · [Lecteur](s2arm-zelda-841-device-reader.py).

```bash
python docs/evidence/s2arm-zelda-841-device-reader.py \
  --cpu-log CPU/host-20261125-102948.log --gpu-log GPU/host.log > observations.json
```

Le lecteur vérifie les bornes cumulatives, refuse les sessions réinitialisées et les faits shader contradictoires ; il ne publie pas les lignes privées brutes. Les quatre différences CPU/GPU ont également été recoupées avec le lecteur indépendant [s2arm-sync-window-reader.py](s2arm-sync-window-reader.py). Les percentiles de fenêtres ne sont jamais agrégés comme un percentile de session.
