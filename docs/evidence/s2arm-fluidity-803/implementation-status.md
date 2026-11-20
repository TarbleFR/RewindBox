# Lot 0171 — état et limites de validation

## Périmètre

- 0170 : correction de la provenance du mode de présentation générique, avec retour explicite `S2A_RB_NATIVE_CADENCE=0` ajouté par 0171.
- 0171 : protocole de 180 s, menu générique, compteurs bornés, audio/GC, ledgers et parcours mémoire complet après le score.
- Nextendo : Core déjà compilé et authentifié du run 44753917742, source `8988ced5014dd23caae2eefac70b3d37f5a5b7f0`, à intégrer dans la même IPA.
- Aucun budget de textures/prélecture, ordonnanceur audio, pas de simulation ou traducteur de shaders modifié par 0171.

## Vérifications source

Le contrôle existant `tools/weak_link_decl.py check` a d’abord signalé trois déclarations faibles non enregistrées, déjà présentes à 0170. Leurs consommateurs ont un repli explicite ; les annotations manquantes sont ajoutées auprès des déclarations (`nvn_rb_route_read`, `s2a_rb_guest_input_release`, `s2a_rb_mkw_measure`). Le même contrôle passe ensuite : 31 symboles host enregistrés, aucun flag de liaison manuscrit. Le contrôle n’est ni modifié ni désactivé.

Les revues indépendantes couvrent les familles, les crochets de présentation, les métadonnées host, la mémoire et la concurrence du collecteur. Elles ont notamment corrigé l’identité amont confondue avec le moteur patché, les préférences confondues avec les réglages actifs, les rappels de minuterie périmés et l’arrêt pendant l’initialisation du banc. La lecture VM utilise l’API iOS déjà employée par le moteur, avec des adresses de 64 bits.

Le premier run 0171 (44771503834) a refusé l’interface avant compilation : le nouvel appel du banc n’était pas déclaré dans `S2ArmGuestABI.h`. La déclaration partagée est ajoutée et employée par le menu et le pont. Les deux fournisseurs NativeAOT restent des symboles internes recherchés par le collecteur ; leur conservation est exigée et la CI vérifie leur présence dans le framework final. Le contrôle d’exports existant n’est pas modifié ni contourné.

L’analyseur de comparaison a été appliqué à deux exports privés existants : [comparaison refusée](legacy-comparison-refused.json), car aucun ne porte les marqueurs du protocole. Aucune différence de performance n’est produite. Il ne s’agit ni d’un banc synthétique ni d’un test d’exécution du moteur.

## Statut du moteur compilé

| Étape | État |
| --- | --- |
| Correctifs et instrumentation dans les sources | Intégrés et relus ; application de 0171 sur 0170 et contrôle des déclarations faibles réussis |
| Compilation du moteur 0170 | Réussie sur macOS 15 et 26, run 44759330364 ; zéro avertissement sur ses lignes ajoutées |
| Compilation du lot 0171 | Réussie sur macOS 15 et 26, run 44772035018, source `342f534efc856eedeba9b085df291757bc942d41` ; zéro avertissement sur les lignes ajoutées |
| Pin et IPA privée 803 | Pin contrôlé par le run 44774890033 ; IPA 803 livrée en privé et vérifiée, run 44775472323 |
| Gain de fluidité, chaleur, son, attribution mémoire sur iPhone | Non observé ; il manque les nouvelles mesures appareil |
| Régression des deux autres jeux Switch 2 | Non vérifiée sur appareil avec 803 ; état satisfaisant rapporté sur les versions précédentes |

Les suites Flutter/natives approfondies ne sont pas exécutées, conformément à AGENTS.md. Les contrôles obligatoires de configuration, ABI, signatures, identité et livraison restent actifs. Aucun avertissement nouveau sur les lignes ajoutées n’est accepté lors de la revue des journaux CI.

## Décisions qui attendent les données

Le poste compressé dominant, le taux d’usage de la prélecture et les trous audio réellement entendus ne sont pas encore attribués. Il n’est pas justifié de réduire arbitrairement un cache ou de changer une échéance audio avant ces relevés. Le mode endurance et les retraits/désactivations de familles sont des propositions classées dans [l’audit](audit-803.md). La première IPA instrumentée est une référence ; elle ne transforme pas les anciens essais non appariés en un avant/après.

## Preuve de compilation

[Identité moteur et artefact](engine171-build.json) : 171 patchs correspondent exactement au dépôt. La chaîne shaders `0be3f28548fd` et la charge NS2Pro sont identiques à la base 802. Les trois nouveaux exports sont présents dans le framework final. Les 12 avertissements par plateforme existaient dans 0170, sur des lignes inchangées ; aucun sur les ajouts 0170/0171. L’annotation Actions relative à Node.js existait également avant ce lot.

## Livraison privée 803

La [livraison](../rewind803/delivery.json) provient de `c5422386b72ec4ea88b010dab3826075ee7e79f8`, run 44775472323, tentative 1. Les quatre pièces chiffrées, les reçus, les 97 images natives et les 10 identifiants de bundles concordent. [Identités exactes de S2Arm et Nextendo](../rewind803/s2arm-identity803.json). IPA : 333553734 octets, SHA-256 `d7d2cb41d3683bc20d804adfdf346aa3d12cf34abe3b55b83f5e669c9f90510b`.

La [revue de compilation application](../rewind803/application803-warnings.json) ne trouve aucun avertissement dans les cinq fichiers modifiés, soit 249 lignes ajoutées. Les sources des avertissements S2Arm ailleurs sont inchangées depuis 802 ; leur émission dans 802 n’a pas été vérifiée, son journal étant indisponible. Les diagnostics du moteur sont documentés [séparément](../rewind803/engine171-warnings.json). Le framework libretro recompilé a des relais générés par le linker différents mais équivalents : code principal et données identiques, mêmes destinations `_objc_msgSend`, avec UUID et signature différents. Le [classement binaire](../rewind803/libretro-image-difference.json) conserve les détails.

L’IPA a été remise en privé après vérification ; la clé privée de transport a été supprimée après conservation des reçus. Aucun essai physique iPhone, aucune validation de partie, aucun gain de FPS ou de chaleur n’est déclaré. La comparaison 803/802 selon le protocole reste indisponible : 802 n’avait pas ce protocole. 803 constitue la première référence instrumentée.

## Tas hôte iOS — lots 0172 à 0176

Référence fournie par le mainteneur pour Mario Kart World (`0400C3F00006E000`) sur iPhone17,2, 8 Go, iOS 27, IPA 803. Footprint 4 346 Mo, compressed logique 1 205 Mo, graphics compressed 212 Mo. Tranches communiquées en Mio par tag : 2 = 755, 0 = 243, 100 = 163, 88 = 64. Environ 22 500 page-ins / 10 s et 31 % de CPU système. En session longue sur 802, jusqu’à 85 000 page-ins, 312 000 compressions / 10 s et 63 % de CPU système. Ces relevés motivent le choix du tas. Ils ne déterminent ni un propriétaire ni un résultat apparié.

| Propriétaire suivi | Octets comptabilisés en mémoire au moment du relevé |
| --- | --- |
| Traduction | Allocations des descripteurs de modules, tables de symboles, traps et sauts lointains. Code exécutable mappé exclu. |
| Pages et fenêtres | Plages de suivi des écritures, tableaux courants et retirés, index de plages et répertoire de la fenêtre lointaine. Réservation virtuelle du jeu exclue. |
| Vues de textures | Capacité allouée du registre de textures et des deux index, plus la taille structurelle des jeux de vues vivants. Une acquisition du verrou impossible donne une valeur indisponible. |
| Pipelines | Capacité malloc des clés et pointeurs de la table de rendu. Taille superficielle des objets retenus publiée séparément par référence. Plusieurs références peuvent désigner le même objet. Les allocations privées de Metal sont inconnues. |
| Commandes | Enregistrements NVN, nœuds de l’index de pages, intervalles alloués et table d’internement. Les blocs de commandes mmap relèvent d’une autre comptabilité. |
| Son | Capacité demandée des buffers AudioQueue effectivement alloués et encore détenus, toutes sorties confondues, sans travail ajouté au callback audio. Le tas managé et les allocations privées de Core Audio sont hors couverture. |

`[RB-VM-HEAP]` associe les lignes de zone et la synthèse par horodatage monotone et génération. Les valeurs de zone et les compteurs internes se recouvrent. `over_threshold` utilise le seuil strict de 100 Mo décimaux sur les sites suivis. Les références superficielles PSO ont leur propre indicateur. Aucun propriétaire dépassant réellement ce seuil sur la 803 n’est établi par les données disponibles. Les octets rendus par `malloc_zone_pressure_relief` ont leur propre ligne `[RB-HEAP-RELIEF]`.

Le cache des archives ouvertes gardait les objets et des alias de lot jusqu’à la fin du processus. Son plafond candidat est de 128 fichiers distincts, avec les huit plus récents conservés sur une alerte système. Ces deux plafonds d’essai devront être confrontés aux temps d’image. Les descripteurs Metal en cours conservent leurs archives. Les entrées de traduction utilisées par le traitement de fautes restent actives jusqu’au retrait des lecteurs. Aucun changement de format de fichier, de sauvegarde ou d’identité shader.

Revue avant livraison : les victimes de la LRU restent retenues dans une collection possédée jusqu’après la libération du verrou des archives. Leur destruction ne se produit donc plus sous ce verrou. Une archive dont l’ouverture échoue est retirée de l’index de présence pour autoriser sa reconstruction ; le mode actif conserve le fichier jusqu’au remplacement réussi. Le fournisseur audio protège également sa nouvelle branche contre les exceptions à la frontière native, avec un retour indisponible. Les lignes malloc distinguent le heartbeat d’origine, l’intervalle réel de collecte et le retard de la file. Le comportement 803 reste derrière `S2A_RB_HEAP_TRIM=0`.

| Étape | État du lot |
| --- | --- |
| Corrigé dans les sources | Relevé malloc par minute, propriétaires, plafond LRU, libération des tables du chargeur au retrait et restitution à malloc sur alerte. Repli global au lancement avec `S2A_RB_HEAP_TRIM=0`. |
| Compilé pour iOS | Premier moteur `6bdf6fec` conservé dans la [preuve initiale](engine176-build.json), avec son contrôle du pin. Révision `f956b7d8` réussie sur macOS 15 et 26 : [run 44790771355](https://github.com/TarbleFR/RewindBox/actions/runs/44790771355), [empreintes et vérifications](engine176-review-build.json). Les 176 patchs correspondent au dépôt ; les 171 premiers, les exports, la charge NS2Pro, la préparation, les données système et la chaîne shaders restent identiques à 803. [Revue des avertissements](engine176-review-warnings.json) : mêmes 12 diagnostics par plateforme que 803, zéro sur les 374 lignes nouvelles. [Contrôle CI du pin](https://github.com/TarbleFR/RewindBox/actions/runs/44793831852) réussi sur les trois archives ; fichier régénéré strictement identique au pin intégré dans `b47339a9`. |
| IPA privée livrée | En attente. Brouillon 804 préparé à partir de `b47339a9` : 97 images de base vérifiées, aucune erreur de schéma ni conflit de sources ni changement produit non classé. Brouillon non figé et livraison non déclenchée. La recette exige une clé publique de transport épinglée. La consigne actuelle exclut toute clé dans GitHub ; aucune nouvelle clé n’y est ajoutée. La clé privée de la 803 a été supprimée après vérification, selon son reçu. |
| Observé sur appareil | Aucune fenêtre candidate disponible. Objectif non validé. |

Pour statuer, conserver trois fenêtres valides de 180 s **par version**. Utiliser le même circuit nommé, le même appareil et le même état de cache chaud, avec refroidissement et ordre alterné, selon le [protocole](../../s2arm-benchmark-protocol.md). Pour chaque fenêtre, associer le parcours VM post-score complet à son identifiant et convertir les pages comprimées du tag 2 avec la taille de page déclarée. Comparer les médianes des relevés par version et les médianes des débits de page-ins du processus ramenés à 10 s. Publier aussi les valeurs individuelles, le p95 affiché et les images affichées >100 ms/min. Acceptation : baisse du tag 2 d’au moins 250 000 000 octets, baisse de la médiane des page-ins, sans hausse des deux métriques de temps d’image. Un tag manquant, une couverture manquante ou une fenêtre invalide laisse le résultat en attente.

### Comparaison des six fenêtres

L’outil hors moteur [compare_heap_windows.py](compare_heap_windows.py) réutilise les validations de `compare_benchmarks.py` pour les quinze paires possibles. Il exige trois UUID distincts par version, la référence 803, des identités homogènes et les mêmes conditions. Chaque parcours VM doit être complet et suivre le score du même UUID ; ses catégories doivent totaliser les compteurs publiés. Le tag 2 absent reste indisponible, jamais zéro.

Compatibilité de lecture 803 : seuls `end.complete` et `mapping_tag.external_pager_or_shadow`, construits par des expressions C de type `int` dans `rb_vm_audit.m`, acceptent aussi les entiers JSON exacts `0` et `1`. Le rapport conserve les valeurs sources correspondantes. Les autres booléens restent stricts ; chaînes, nombres flottants, compteurs booléens et autres valeurs sont refusés. Le producteur 803 et les validations du comparateur existant restent inchangés.

Pour les page-ins, l’outil prend la médiane des dix-huit débits réels par fenêtre, ramenés à dix secondes, puis celle des trois fenêtres. Pour le tag 2, le p95 affiché et les images >100 ms/min, il prend la médiane des trois valeurs de fenêtre. Les valeurs individuelles et leur dispersion restent dans le JSON ; aucun quantile fusionné n’est inventé. Résultats distincts : comparaison refusée, objectif non atteint, objectif atteint sur ce scénario. Ce dernier résultat exige les quatre critères, sans extrapolation aux FPS, à la chauffe ni aux autres circuits.

Usage : répéter `--baseline JOURNAL UUID` trois fois et `--candidate JOURNAL UUID` trois fois, puis donner `--output RAPPORT.json`. Les journaux restent privés. Vérification syntaxique réussie et refus confirmé sur un export historique sans protocole ; aucune fenêtre appareil valide fournie, aucun résultat positif fabriqué. Aucune nouvelle suite de tests n’est ajoutée.
