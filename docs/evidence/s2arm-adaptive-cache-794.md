# S2Arm sur iPhone — comparaison de la 793 et du candidat 794

## Point de départ

L’IPA privée 793 a été vérifiée après déchiffrement. Le run `44519970706` a produit 333 236 934 octets au commit `32b9b219`. Son SHA-256 est `08c80531625f7917a1fe533c009813d04dd75d0efa8016648e0d642f57aac690`. Le producteur moteur est `44516643903` et le SHA-256 de son Mach-O arm64 est `f393bb5bbaed880377e5a1a766a7606c13b7177f956ebf149b156479b672f2f5`. La 793 contient les correctifs 0122 à 0126. Ses tests ciblés sur Mac ont vérifié le partage de bibliothèques, les variantes de profondeur, l’ordonnancement et la réutilisation stricte d’une archive de pipelines. Les suites générales Flutter et natives de l’IPA ont le statut `not-run`. [Vérification privée](rewind793/download793-verification.json) · [Tests de l’IPA](rewind793/standard-tests.json) · [Preuves du moteur](s2arm-adaptive-cache-792.md)

La mesure de référence sur iPhone retrouvée pour Mario Kart World concerne la **786**. Sur 3 005 intervalles observés, elle donne 33,31 FPS, un p95 de 47,24 ms, un p99 de 102,79 ms et 34 / 13 / 4 intervalles au-dessus de 100 / 200 / 500 ms. Il manque 540 intervalles sur la plage. Les six attentes détaillées de PSO totalisent 698,3 ms. Les quatre appels MSL des images lentes détaillées totalisent 1 536,8 ms. Les 687 anciennes clés sans source viennent de la 779. Le démarrage de la 786 écartait encore 807 lignes associées à 434 clés. Les titres, parcours, versions de traducteur et états des caches doivent correspondre avant d’attribuer un écart à un correctif. À la rédaction, aucune paire de captures iPhone comparables 792/793 ou 793/794 n’est disponible. [Périmètre et méthode de mesure](s2arm-adaptive-cache-792.md)

## Hypothèses à vérifier sur la 794

| Correctif | Situation exercée | Preuve attendue |
| --- | --- | --- |
| 0127 | Plusieurs consommateurs se présentent pendant le passage de RUN à ONE ou HOLD. Une archive est en cours d’écriture quand le budget change. | La limite commune est respectée après la transition. L’opération Metal déjà engagée finit, les entrées différées restent récupérables, l’urgence peut avancer et la fermeture libère les workers. |
| 0128 | Un fichier MSL présent est refusé par Metal ou une entrée de reconstruction existante diffère des octets réellement rencontrés. | Les octets de la rencontre réelle permettent de rétablir l’entrée. Une réparation publie une traduction utilisable et une demande ultérieure produit le résultat graphique attendu. Compter séparément les cas où les octets d’origine restent indisponibles. |
| 0129 | Deux lancements observent la même succession de PSO. Le troisième doit préparer la prochaine variante exacte. Deux autres historiques divergent au même point. | Le worker sert d’abord une demande urgente, produit le PSO prédit, l’encodeur lie ce même objet et le pixel lu sur le GPU est correct. Le cas divergent s’abstient. Un témoin sur la même histoire, apprentissage désactivé au troisième lancement, doit échouer précisément au contrôle de l’objet prédit. |

Le test 0129 utilise un jeu de shaders synthétiques, deux jeux de données séparés et des processus Mac distincts. La commande est `build/tests/t_nvn_warmbump --transition-gpu`. La présence du test et l’application de son patch ne suffisent pas à déclarer sa réussite. Les statuts de compilation du moteur, de l’IPA et des essais sur matériel sont à consigner séparément une fois les reçus disponibles.

## Trois écarts de ponts natifs entre les IPA 792 et 793

Le contrôle lit les images signées de la 793, vérifie leur empreinte de charge utile, décode les deux entrées de table d’adresses globales qui importent `_objc_msgSend` et vérifie que leur cible, leur bibliothèque et leurs paramètres de liaison sont identiques. Il recalcule ensuite l’empreinte en mémoire après substitution des références à ces deux entrées dans les stubs ARM64. Pour chacun des trois ponts, cette seule transformation reproduit exactement l’empreinte 792 attendue. [Vérificateur reproductible](../../tools/s2arm_prototype/verify_bridge_stubs.py) · [Reçu signé 792](rewind792/signed-payload-identity.json) · [Reçu signé 793](rewind793/signed-payload-identity.json)

| Pont | SHA-256 de charge utile 793 | SHA-256 792 retrouvé par substitution | Références ordinaires / Objective-C |
| --- | --- | --- | ---: |
| `libretro_internal_bridge` | `da21cb1c0790676ba70a55d853d74cb823587bcbd93f0ac9b784718a854d68e4` | `0cb53f3e8470d03114b0b8eb4fdcb6489bbec83bfdcea19c086843d2f4d58826` | 1 / 2 057 |
| `melonx_internal_bridge` | `7938b9d2bbeab3edaf5025c9c618ca468555fd540e8ffb1fead2be6b92d98bc6` | `584c953301ac4d103e7bef69154e85110b244dccb6424fcbf44a7b79012cd3f1` | 1 / 330 |
| `rpcs3_internal_bridge` | `f852400ebda027398fd8d39d1d136b62013ef87a6284fa3f33fc1bdaa9bc99d3` | `5cfa0b5b036ab36c2e18c9f81b05ed45ad7a8b847c937ec62437e60c12a88b19` | 1 / 843 |

Le vérificateur s’exécute depuis la racine du projet.

```sh
python3 tools/s2arm_prototype/verify_bridge_stubs.py "$IPA_793" \
  docs/evidence/rewind793/signed-payload-identity.json \
  docs/evidence/rewind792/signed-payload-identity.json
```

Ces trois empreintes 793 sont différentes à l’octet de leurs références. L’analyse localise l’écart de charge utile dans le choix de deux entrées de liaison équivalentes. Un essai fonctionnel de chaque pont et la comparaison des images de l’IPA 794 sont des vérifications distinctes.

## Captures iPhone à exporter

Pour **chaque lancement**, conserver ensemble les quatre éléments ci-dessous. Nommer le lot avec le numéro d’IPA, le build du jeu, le numéro de lancement et le scénario. Exporter le journal moteur dès la fin de la session pour que la rotation de `host.log` reste identifiable.

| Élément | Contenu exact |
| --- | --- |
| Journal moteur | Dans l’export du dossier `engine`, conserver `engine/0400C3F00006E000/host.log` pour Mario Kart World, ou le `host-<horodatage>.log` correspondant si le fichier a déjà tourné. Garder le début de la préparation et la fin de session. |
| Profils | Dans l’export du dossier `profiles`, conserver `profiles/<horodatage>-f<image>/frames.txt` et `cpuprof.txt` pour **chaque** capture couvrant le menu, le chargement, le départ et le changement de zone. Conserver les noms des dossiers pour retrouver les numéros d’image. |
| Journal de RewindBox | `Documents/Diagnostics/S2Arm/s2arm-journal.jsonl` pour rattacher la préparation, l’identité du moteur, la fermeture et une éventuelle reprise à la bonne session. |
| Fidélité et repères | Captures d’écran aux mêmes repères ou courte vidéo jumelée, avec heure et image de départ si disponibles. Annoter les effets attendus, les ombres, les éléments de l’interface et la première image complète après transition. Faire une passe visuelle distincte si l’enregistrement modifie sensiblement la cadence. |

Pour une anomalie de persistance, joindre en plus **l’inventaire daté** du répertoire graphique de ce titre avant la fermeture, après relance et après mise à jour. Relever les tailles et empreintes de `pso_user.tsv`, du fichier voisin `pso_user.tsv.rb-trace-v1-*`, de `pipelines/identity.json`, de `pipelines/batches.tsv` et des archives référencées lorsqu’ils existent. Compter les entrées de reconstruction conservées et celles rejetées dans les journaux. Réserver les fichiers sources du jeu et les sauvegardes à l’appareil.

## Comparaison à reproduire

1. Sur le même iPhone 16 Pro Max, fixer la version d’iOS, le build exact du jeu, la sauvegarde de départ, le circuit, le véhicule, la caméra, la résolution, le plafond FPS, la luminosité et l’alimentation. Noter la température ambiante, l’état thermique initial et le mode économie d’énergie. Conserver à part le cache graphique de référence.
2. Pour chacune des trois IPA **792, 793 et 794**, effectuer les trois lancements de la matrice ci-dessous. Démarrer chaque série avec une copie identique du cache graphique initial vide et de la sauvegarde de départ. Pour répéter une cellule sur le même build, repartir d’une copie du cache de ce build prise juste avant la cellule. Entre deux passages, quitter le jeu puis fermer complètement RewindBox. Faire séparément « Quitter → reprendre » dans RewindBox et relever dans le journal si le moteur a été mis en veille, reconstruit ou arrêté définitivement.
3. Tester les deux mises à jour sur place, **792 → 793**, puis **793 → 794**. Pour chaque paire, prendre deux copies identiques du cache chaud et de la sauvegarde du build de départ. Sur la première, relancer le build de départ comme témoin. Sur la seconde, installer l’IPA suivante par-dessus et rejouer aussitôt la même scène. Conserver les identifiants d’application et de signature, la version d’iOS, le build du jeu et le conteneur. Relever séparément les reconstructions, les PSO strictement servis par l’archive et les objets liés pour chaque paire. Pour isoler la prédiction, comparer une troisième passe activée et une passe avec `S2A_RB_PSO_TRANSITIONS=0` sur deux copies de la même histoire chaude, lorsque ce réglage est disponible.
4. Prolonger un même parcours pendant au moins 20 minutes pour chaque IPA, puis laisser refroidir en restant dans le jeu. Relever l’heure des passages RUN, ONE, HOLD et du retour à RUN, leur raison et les premiers travaux servis après reprise. Si un HOLD survient naturellement, répéter la fermeture dans cet état sur une passe dédiée. Consigner « non observé » si une transition manque.
5. Délimiter les mêmes scènes pour les deux builds et produire le JSON de mesure pour chacune avec la commande sous la matrice. Publier le nombre d’intervalles uniques et manquants avec chaque résultat. Les lignes `wholeLog` du JSON couvrent le journal entier. Garder les appels GPU, les attentes et les compilations répartis par étape et par fil pour éviter les additions de durées qui se recouvrent.

| IPA | Lancement 1, cache froid | Lancement 2, cache chaud | Lancement 3, même parcours |
| --- | --- | --- | --- |
| 792 | Cache graphique initial vide | Cache issu du lancement 1 de la 792 | Cache issu du lancement 2 de la 792 |
| 793 | Même état initial que la 792 | Cache issu du lancement 1 de la 793 | Cache issu du lancement 2 de la 793 |
| 794 | Même état initial que la 792 | Cache issu du lancement 1 de la 794 | Cache issu du lancement 2 de la 794 |

```sh
python3 tools/s2arm_prototype/shader_session_metrics.py "$HOST_LOG" \
  "$PROFIL_A/frames.txt" "$PROFIL_B/frames.txt" --first "$PREMIERE_IMAGE" --last "$DERNIERE_IMAGE"
```

| Mesure | Interprétation et critère de comparaison |
| --- | --- |
| FPS et temps d’image | FPS moyen, p95, p99, effectif et nombre d’intervalles >100, >200 et >500 ms. Les signatures mesurent la cadence des commandes. Conserver séparément les lignes `on-screen up to frame` et les images perdues à l’écran. |
| Traduction | Clés manquantes utilisables ou irrécupérables, entrées restaurées depuis les octets conservés, nombre et durée des traductions et des attentes d’un travail déjà lancé. Isoler le gameplay du préchauffage. |
| Bibliothèque Metal | Nombre et durée des créations depuis MSL, chargements de bibliothèques binaires disponibles et réutilisations de l’objet exact en mémoire. Un appel depuis MSL peut profiter du cache privé du pilote. Le journal seul ne mesure pas son travail interne. |
| Pipeline graphique | Créations en gameplay et attentes cumulées du rendu. Un PSO fourni par l’archive exige une création réussie avec `MTLPipelineOptionFailOnBinaryArchiveMiss`. Compter séparément les misses stricts, les créations de secours, les objets déjà en mémoire et les échecs. Une ligne de manifeste atteste seulement de la présence d’un descripteur. |
| Anticipation | Conserver les compteurs finaux `promoted`, `published`, `warmed Metal objects bound` et `published but unused`. Une liaison à l’encodeur établit une utilisation effective. Rapporter les objets liés parmi les objets publiés, ainsi que les priorités accordées au travail urgent. |
| Mémoire et température | Pic de mémoire **échantillonné**, ressources disponibles ou inconnues, état thermique Apple, niveau du gouverneur et horaire du premier ralentissement soutenu. Sans mesure de fréquence ni baisse attribuable, le temps avant throttling reste inconnu. |
| Fidélité | Comparer les images jumelées, signatures de passes et dessins, profondeur EQUAL et compteurs `first uses up to frame` classiques et mesh. Toute disparition de draw, d’objet ou d’effet doit accompagner les chiffres de cadence. |

## Défauts reproduits et contrôles du candidat

Sur les sources de la 793, deux workers suspendus entre la lecture du niveau et la réservation ont tous les deux obtenu un permis après passage en ONE et en HOLD. Le même test avec la réservation synchronisée en accorde respectivement un et zéro. Sur le GPU du Mac, le témoin reconstruit avec l’écrivain de la 793 a lancé 25 descripteurs supplémentaires après le septième. Avec 0127, les 25 restants ont attendu et les suites HOLD et ONE ont relu 32 archives de pipelines sur 32 en mode strict. Lorsque le délai de fermeture a expiré, 7 descripteurs sur 32 avaient été archivés, aucun des 25 suivants n’a démarré. Dans un autre cas de fermeture, Metal a accepté le descripteur, puis refusé de sérialiser son archive. Un premier essai de récupération a soumis de nouveau le descripteur. Le test ONE a détecté ce double départ lorsqu’un refus de sérialisation s’est produit naturellement. Le correctif suivant garde l’objet MTLBinaryArchive et demande une seule nouvelle sérialisation, après contrôle du budget. Il conserve les clés réservées jusqu’au résultat. [Premier contrôle GPU](https://github.com/TarbleFR/RewindBox/actions/runs/44530285447/job/135581458575)

Les témoins de la 793 ont conservé l’octet corrompu après un bind et laissé le MSL tronqué en échec après son refus par Metal. Sur le candidat, le premier bind a réparé le fichier en tâche de fond. Un nouveau processus a ensuite retraduit le shader depuis cette seule entrée avec le traducteur NativeAOT. Dans le cas du MSL tronqué avec JSON valide, le GPU a lu les quatre composantes entières attendues, 42, 7, 99 et 1, après régénération. Ce premier essai a aussi révélé trois appels Metal pour la même source irrécupérable lorsque le chemin du cache contenait un double séparateur. Le contrôle sans entrée saine exige un seul appel pour les trois demandes du même processus. [Journal de la réparation](https://github.com/TarbleFR/RewindBox/actions/runs/44531198402/job/135584663715)

Le test de prédiction a exécuté deux séries de trois processus et un septième processus témoin avec relecture désactivée. À la troisième session concordante, le travail urgent a précédé le successeur choisi par le moteur. Un objet Metal a été promu, publié puis lié à l’encodeur, et le pixel a été lu. À la troisième session divergente, les trois compteurs sont restés à zéro. Le témoin a échoué exactement sur l’absence de l’objet prédit. Les 42 contrôles préexistants de partage de bibliothèques, de variantes et de prélecture ont également réussi. [Journal de la prédiction](https://github.com/TarbleFR/RewindBox/actions/runs/44531198402/job/135584663715)

## Moteur produit et vérifié

Au commit `5e4e07c695f995c232fa61a84768554d53ca5408`, les deux builds du moteur iOS et les deux liens du composant guest ont réussi. Sur chaque runner, aucun avertissement supplémentaire par rapport à la 793 ni aucun diagnostic sur les 392 lignes de production ajoutées ou modifiées. Les 126 premiers correctifs conservent leurs empreintes. [Producteur 44535281536](https://github.com/TarbleFR/RewindBox/actions/runs/44535281536)

L’archive moteur authentifiée porte le SHA-256 `6f7e646028812dc0aec4af24a62e8de4ebbb4b42f0b90cd790f44b4f9aa61319` (artefact `14535823720`). Son Mach-O arm64 de 113 607 152 octets porte le SHA-256 `55077b6b3ac0e9e7cd7abb7a12bc29f7ed4b36cb2fbff80b88e916b4ea28fb21`. Son empreinte de charge utile est `f444d69a3d9ac4b8528f59f9172306b856e0298df6bfe4d2de7a956d20c2d360`. Les 141 exports du moteur, l’export de NS2Pro, les dépendances dynamiques, les chemins de chargement, le minimum iOS 18 et la chaîne de traduction `0be3f28548fd` concordent avec la 793. Le désassemblage confirme que la retraduction appelle directement les fonctions communes de réservation et de libération du permis. [Pin du moteur](../../build-utils/s2arm/engine-pin.json)

Sur le GPU du producteur, le refus de sérialisation injecté en ONE a conservé le même objet Metal jusqu’au deuxième appel, avec exactement 32 ajouts dans l’ordre et 32 hits stricts. Deux refus successifs ont laissé un miss sans index, comme l’expiration du délai avant le deuxième essai. Les tests de relance ont également relu l’archive écrite pendant une fermeture en HOLD. Le chemin de cache avec séparateurs redondants a produit un seul appel Metal pour trois demandes de MSL invalide sans entrée saine. La réparation du fichier de même longueur, le pixel 42/7/99/1, les six lancements de prédiction avec leur témoin et les 42 contrôles de bibliothèques ont tous réussi sur cette version. [Journal du GPU](https://github.com/TarbleFR/RewindBox/actions/runs/44535281536/job/135598912097)
