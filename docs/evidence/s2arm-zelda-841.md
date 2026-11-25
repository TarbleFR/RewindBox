# Zelda : rapport du lot diagnostic et moteur 0361–0378

Objectif : 100 % de vitesse et 60 images/s sur A18 Pro, avec GPU soutenu sous 16,6 ms et sans Serious. **Cet objectif reste à démontrer sur iPhone.** Cette mise à jour apporte les corrections de synchronisation déjà épinglées et les mesures nécessaires au prochain lot GPU.

## Ce que montre la 840

Le journal `0400486024DEC000/host.log` fourni contient 14 relevés cumulatifs. Son format correspond aux patchs 0357–0360 ; l’étiquette 840 vient du mainteneur, le journal ne contenant pas le SHA de l’IPA.

Sur les bornes effectivement journalisées **1800 → 4200** :

| Mesure | Différence | Par image |
|---|---:|---:|
| Allocateurs | 4825,891 ms | **2,010788 ms** |
| Visibilité | 0 ms | 0 ms |
| Waits de file enregistrés | 1764 | 0,735 |
| Drains comptabilisés | 0 | 0 |

Le seuil de 1 ms/image est franchi : l’essai d’allocateur par image est justifié. Cette plage inclut des transitions. Les fenêtres de 300 images en 3D montrent environ 1,10–3,91 ms/image d’allocateur. Le zéro de drains de la 840 omet certains chemins externes ; 0364 corrige leur attribution.

Les GPU p50 des fenêtres 2100–3900 sont **25,77–31,35 ms**, avec une vitesse **27,9–55,5 %**, en Serious. La session démarre déjà en Fair. Les anciennes 4,4–7,2 ms/image agrégées ne sont pas un témoin apparié : une baisse causale globale n’est pas établie. Les profils de quatre secondes et cette session courte ne remplacent pas trois fenêtres de 180 secondes.

## Intégrations

Les corrections 0361–0366 protègent les allocateurs après annulation, conservent l’ordre et la rétention des waits dans le vrai worker, évitent le drainage d’une dépendance déjà terminée et remettent les options de session à zéro.

| Interrupteur | Comportement proposé pour essai |
|---|---|
| `S2A_RB_ALLOC_FRAME=1` | Append des soumissions d’une même image dans un allocateur ; reset protégé par la dernière fence GPU. Nombre d’allocateurs plafonné à huit ; octets rapportés. |
| `S2A_RB_WAKE_DIAG=1` | Attentes, retours, timeouts, signaux et délais ≤1 ms par fichier/ligne : encodage, présentation, fences et SVC. Retours d’API et interruptions noyau restent distincts. |
| `S2A_RB_GPUDIAG=1` | Coupures et réouvertures par image ; demande `early_z` existante, annotation et bloqueurs lexicaux MSL. Source inconnue et couverture perdue sont signalées. |
| `S2A_RB_PROBE_EVERY=30` | Travail GPU fixe sondé sans attente du CPU toutes les 30 images ; durée, pas MHz. |
| `S2A_RB_DISPATCH_ORDER=game` | Épargne une barrière entre dispatchs invités consécutifs sans barrière du jeu ; copies, transitions et bits explicites restent ordonnés. |
| `S2A_RB_PSO_WAIT_BOOST=1` | Priorité user-interactive temporaire pour le propriétaire de la compilation effectivement attendue. |
| `S2A_RB_ARCHIVE_ERROR_NIL=1` | Sérialisation sans sortie NSError Metal ; refus, retry, nettoyage, renommage et index conservés. |

Ces nouveaux modes sont **sur demande**, diagnostics coupés par défaut. Aucune correction spéculative des réveils n’est appliquée. Les délais existants des attentes et les règles d’horloge, de cadence et de résolution restent conservés. Huit comparaisons de sources vérifient les fonctions de vitesse/présentation après retrait des seules enveloppes de comptage ; `hle_nvn.c` reste identique à l’octet.

Le plafond de huit allocateurs ne borne pas les octets de leurs heaps : le pic mémoire et le rendu doivent être mesurés avant activation générale du mode par image.

## Vérifications et limites

| État | Résultat |
|---|---|
| Corrigé | Sources et patchs 0361–0378 sur `Claude`. |
| Testé | GCC : 347 assertions ; Clang : 347 sur chaque hôte macOS 15/26. Archive : 34 contrôles par hôte. Fences/worker/visibilité/sessions : 35 contrôles. Contrôle négatif des barrières rouge comme attendu. |
| Compilé | Moteur iPhoneOS sur macOS 15/26, source `35eb173f`, run `45574225411`, tentative 1. |
| Traducteur | 252 entrées, 2 943 682 octets inchangés face à la 840 et à 0366 ; empreinte reproduite `121d1bca8eb35c16`, registre et ABI identiques. Expansion XML explicite, sans exécution MSBuild. |
| Livré | IPA privée 841 vérifiée : source `a019a0b7`, run `45578695343`, tentative 1 ; 335 288 498 octets, 98 images natives et six validateurs passés. MeloNX `693c9c94` et NS2Pro conservés. |
| Observé sur A18 Pro | Journal 840 analysé. Aucun relevé du nouveau lot ; aucun gain FPS/watts revendiqué. |
| Pixels Metal 4 | Non exécutés : le GPU virtuel CI refuse Metal 4. |
| A/B et endurance | 0 comparaison appariée réalisée ; trois fenêtres de 180 s par variante puis au moins dix minutes restent requises. |

Le contrat de livraison passe 120 contrôles (quatre ignorés) ; les groupes de tests d’application Flutter/natifs restent non exécutés selon la recette. Le contrôle des signatures et des empreintes ne remplace pas une partie sur téléphone.

La première compilation a révélé un pointeur d’erreur ARC non qualifié, corrigé en 0376. La relecture a complété les helpers de réveil, distingué les retours de syscalls des erreurs pthread et rapproché `early_z` de l’annotation existante.

## Prochaine mesure

Pour attribuer les réveils, commencer par un relevé court avec ces lignes fusionnées dans les réglages existants, puis relancer l’app :

```ini
S2A_RB_WAKE_DIAG=1
S2A_RB_GPUDIAG=0
S2A_RB_PROBE_EVERY=30
```

Pour la capture GPU, passer ensuite `S2A_RB_WAKE_DIAG=0` et `S2A_RB_GPUDIAG=1` : la journalisation des passes reste ainsi séparée de l’attribution des réveils. Pour les passages chronométrés, couper les deux diagnostics, garder la même cadence de sonde et changer **un seul mode moteur à la fois**. Même scène, batterie 40–60 %, départ Nominal, mêmes sauvegardes/résolution/caches/luminosité ; ordre alterné et refroidissement selon le protocole. Comparer vitesse, FPS, GPU p50/p95/p99, temps en Serious, énergie/image, mémoire, erreurs GPU, audio et pixels du replay.

Le lot traducteur attend un nouveau journal GPUDIAG et sera livré seul, avec retraduction avant le jeu. Les travaux TBDR, compression de profondeur et file de résidences viennent ensuite. La saturation/éviction du cache système à environ 1,33 Go reste non prouvée ; sa politique n’a pas été modifiée.

[Plan et mesures détaillées](s2arm-optimisation-globale.md) · [Preuves du moteur](s2arm-zelda-0378/checks.json) · [Deltas 840](s2arm-zelda840-sync.json) · [Lecteur reproductible](s2arm-sync-window-reader.py)

[Reçu de la 841](rewind841/delivery.json) · SHA-256 IPA : `44c4989632012a89e81c9a873537c9aaa11b42e83413b102e66112ecb08302d8`.


## Suivi après les premiers essais sur iPhone

Les captures CPU/GPU du 25 novembre ont maintenant été analysées : [rapport appareil et prochaines priorités](s2arm-zelda-841-device.md). Les statuts « en attente » ci-dessus décrivent la livraison initiale ; cette nouvelle observation confirme le fonctionnement des diagnostics et le ralentissement 3D, sans établir de gain A/B ni de replay pixels exact. Aucun nouveau moteur ou IPA n’est produit pour cette analyse.
