# Première utilisation des shaders et pipelines NVN2

Le journal de Mario Kart World attribue 808,8 des 808,9 ms du premier draw à l’attente d’une compilation déjà en file. Le compteur de lookahead totalise 175,3 ms sur 59 scans. Le journal ne donne pas le temps de lookahead individuel de la trame 272. Les 43 compilations MSL sur le thread de soumission de cette fenêtre représentent 6,686 ms. La durée totale de soumission de 355,142 ms comprend d’autres travaux.

| Patch moteur | Chemin modifié | Observation à rechercher sur appareil |
| --- | --- | --- |
| 0283 | Les deux formes de `ProgramSetShaders` capturent les octets nécessaires à la traduction anticipée. Les workers produisent la bibliothèque à partir d’une copie détenue. Le replay vérifie l’identité effective du code mutable. Les entrées MSL effectivement compilées, y compris les variantes, alimentent le générateur AIR macOS. | Bibliothèques prêtes avant le premier bind, chargements binaires et temps MSL de soumission. |
| 0284 | La lecture des catalogues commence avant `nnMain`. La convention de profondeur et le device Metal conditionnent la construction des PSO. Les références, l’historique personnel et les recettes réordonnées passent avant le catalogue externe. Une compilation demandée par un draw peut reprendre une tâche encore en file avec la même clé. | Débuts et fins des phases, temps du premier draw, compilations déjà engagées et attentes résiduelles. |
| 0285 | Le premier scan et son unique reprise partagent le budget de 2 ms de la soumission. Le chemin borné exploite les métadonnées d’attachements déjà connues et mémorise les programmes absents jusqu’à ce que la génération des bibliothèques ou des programmes change. | Compteurs `[rb-look-budget]`, temps maximal par soumission et dépassements observés. |
| 0286 | L’inventaire des archives et la réouverture de 64 clés de démarrage au maximum passent sur une file d’E/S. Le thread de soumission consulte les objets publiés en mémoire. Au premier lancement après mise à jour, les recettes lentes puis les listes de référence et personnelles fournissent les clés à rechercher dans les archives existantes. Le chemin d’écriture tient compte du titre, du build, du GPU et de la chaîne de compilation. Les anciens fichiers restent réutilisables après une vérification stricte par Metal. | `[rb-archive-open]` indique les clés préouvertes, les accès prêts et les ouvertures reportées. La création du PSO Metal est mesurée séparément de la recherche. |
| 0287 | Le profil local conserve l’intervalle demandé pendant 120 présentations de jeu consécutives et les capacités des tables de textures sparse et de lectures bindless. Le titre, le build de l’exécutable et la chaîne de traduction identifient le fichier. Les réservations sont bornées et les choix explicites de présentation restent prioritaires. | `[rb-direct-profile]` signale l’apprentissage, l’écriture et la reprise au lancement suivant. |

Les deux dispositions de cache utilisent le répertoire parent du `pso_user.tsv` effectif. Le générateur `build-utils/s2arm/build_nvn2_shader_pack.py` produit les bibliothèques AIR avec la chaîne de compilation iPhoneOS du Mac. Les archives Metal du téléphone conservent les pipelines pour son GPU. Une source ou une combinaison de pipeline encore inconnue peut entraîner une compilation. Une compilation Metal déjà engagée pour le même PSO reste partagée.

## Configuration de comparaison

```text
S2A_RB_BIND_AHEAD=1
S2A_RB_REGISTER_LIBRARIES=1
S2A_RB_CAPTURE_COMPILED_MSL=1
S2A_RB_PREWARM_TIERS=1
S2A_RB_PSO_LANES=2
S2A_RB_PSO_LIVE_LANE=1
S2A_RB_LOOK_AGAIN=1
S2A_RB_LOOK_BUDGET=1
S2A_RB_ARCHIVE_PREOPEN=1
S2A_RB_ARCHIVE_WRITE_ALWAYS=1
S2A_RB_AUTO_PROFILE=1
```

Aucune nouvelle fenêtre A18 Pro n’est disponible pour cette révision. Les deux points de comparaison à relever sur un parcours identique sont la trame 0 et le chargement de circuit, au premier puis au second lancement.

## Mémoire et température

Le gouverneur compare les octets alloués par Metal au budget recommandé du GPU. Il suit séparément la marge du processus. Sur l’exemple fourni de 5 461 Mio recommandés, le seuil de 85 % vaut environ 4 642 Mio. Le budget de croissance volontaire plafonne à 5 120 Mio. Une allocation indispensable à la validité d’une texture peut dépasser le budget de placement. Le nombre total de tas et la mémoire Metal réellement allouée permettent de repérer ces exceptions.

| Composant moteur | Décision |
|---|---|
| Gouverneur et tuiles sparse | Viser deux ou trois tas de 256 Mio. Conserver une copie valide et attendre la fin du travail GPU avant de rendre une page réutilisable. |
| Staging et lecture anticipée | Réutiliser des tranches partagées après la fin de leur upload. Soumettre hors du thread de rendu des indications de lecture sur les plages physiques mappées. |
| Constantes traduites | Enregistrer la fin exclusive prouvée par binding dans la réflexion du stage. Vérifier le digest du source, la clé du stage et la version du traducteur. Un accès indirect sans borne conserve la taille complète. |
| TBDR | Vérifier le prochain effacement, les lecteurs bindless, les alias et les attentes avant de supprimer un store. Une texture couleur neuve peut se dispenser du remplissage initial si une passe l’efface intégralement. |
| Température | En Fair, admettre un worker de recettes chaudes et suspendre les prédictions. En Serious, suspendre aussi ce worker. Une cadence invitée inférieure peut reprendre après deux fenêtres GPU consécutives en retard. |
| Profil du titre | Enregistrer le pool invité déclaré par le runtime, le GPU, le mode TBDR, la cible des tas et le format des bornes vérifiées. Le budget disponible au nouveau lancement reste prioritaire. |

Les conteneurs AIR construits sur Mac, les archives de pipelines écrites sur l’appareil et les réflexions par stage ont des usages distincts. Une modification de l’ABI du traducteur peut demander une nouvelle traduction. Les comparaisons de cache chaud doivent conserver le même appareil, l’exécutable du jeu et la même chaîne de traduction. Les 175,3 ms du log initial couvrent 59 recherches cumulées. La comparaison par soumission demande la durée d’une seule soumission.

Le [contrôle du moteur 0287](s2arm-fluidity-803/engine287-build.json) conserve les preuves de réouverture des archives en Fair et Serious et les résultats du banc de pixels. Le correctif 0293 transporte l’obligation d’initialiser la texture jusqu’à la création du véritable encodeur sur le worker. Une pression Metal critique ferme aussi l’admission des recettes anticipées lorsque la marge du processus reste élevée.

Le [banc du moteur 0293](s2arm-fluidity-803/engine293-build.json) a rouvert un PSO écrit en Fair et un autre écrit en Serious. Les deux images uploadées restent correctes sur 128 pixels avec le premier lot en vol. Le test d’uniformes mesure 288 octets de c1 initialisés, vérifie le pixel RGBA attendu et maintient 65 536 octets pour un accès opaque. Le backend Mac, les frameworks iOS arm64 et le pont UIKit compilent.

L’[IPA privée 817 vérifiée](rewind817/nvn2-817.json) contient 97 images natives. Trois empreintes diffèrent de la 816. Outre Runner et S2ArmEngine, le pont rpcs3_internal_bridge reprend exactement l’empreinte des builds 811 à 815. Son répertoire source est identique entre les deux révisions de livraison. La cause de la différence de compilation de la 816 reste indéterminée. Les 48 identités imposées par le manifeste concordent.
