# NeoSwap — Build 441

## Périmètre et état

Le mainteneur a demandé le 11 octobre 2026 d'implémenter les conclusions de
l'audit puis de produire la Build 441. Le travail part de la branche `Claude`,
révision `0913f260beb71874ac4aea48ac3ac8014232f119`, qui conserve les ajouts de
la Build 440. Seuls RPCS3, NeoSwap et leurs éléments de validation/livraison
sont concernés. La compilation SPU différée reste désactivée.

Ce document est un journal de travail : aucune validation sur iPhone physique
ni économie de mémoire n'est attestée à ce stade. Les contrôles Apple et la
compilation du nouveau Core sont en cours.

## Choix d'implémentation

- Remplacer le refus systématique des nouveaux objets invités pendant le jeu
  par l'acquisition d'objets préparés sur la file utilitaire de l'hôte.
- Conserver l'ABI Relay v1 et ajouter une interface préparée optionnelle,
  versionnée séparément. Aucun changement du backing des objets déjà publiés.
- Préparer des tailles exactes compatibles, conserver des limites de stock et
  recycler sans compter ce stock inutilisé dans « Donated ».
- Partager le budget des nouvelles préparations invitées, des donneurs et des
  prêts hôte ; comptabiliser les engagements avant d'accorder une autre part.
- Exporter les demandes, octets, refus et durées pour distinguer couverture
  des allocations, backing actif et footprint réel.

Les mappings fixes restent des appels noyau dans le protocole VM de RPCS3.
L'acquisition d'un objet préparé ne constitue pas une preuve de latence bornée
du mapping complet. Un défaut de stock utilise le repli original avant toute
publication ; après publication, tous les alias doivent conserver les mêmes
octets.

## Implémentation et vérifications locales

Le stock couvre les 256 tailles exactes multiples de 64 Kio jusqu'à 16 Mio,
avec au plus 128 objets et 64 Mio préparés. Chaque passage utilitaire prépare
au plus huit objets et 32 Mio, selon les demandes et la part de budget accordée.
Les premières demandes peuvent encore choisir le stockage ordinaire ; elles
alimentent les préparations suivantes. Les objets déjà FILE ne migrent pas.

L'API optionnelle Prepared Relay v1 est indépendante du Relay v1 et de l'ABI
principale RPCS3 30. Le retour d'un objet jamais publié transfère sa propriété
au nettoyage utilitaire sans mutex ni appel noyau. Les trois alias usuels du
Core utilisent des métadonnées incorporées ; les alias supplémentaires
conservent leur allocation contrôlée. Le nettoyage des objets préparés puis
publiés est différé, avec maintien des quarantaines en cas d'échec.

Les engagements invités non publiés et les IPC donneurs sont réservés dans le
budget partagé. Une petite demande donneur exacte peut recevoir une part avant
la croissance spéculative du relais hôte. Les callbacks d'une même décision ne
peuvent plus réutiliser le crédit donneur déjà consommé.

Vérifications locales réussies avant compilation Apple :

- Backend réel et fixtures : acquisition, 256 tailles, grants, pression,
  concurrence, retour inutilisé, alias, scrub différé et arrêt/relancement.
- Client RPCS3 matérialisé : stock disponible/absent/occupé, six alias, repli
  avant publication uniquement, remise en correspondance et statistiques.
- Compilation des trois exports Relay/Prepared/Stats, sans constructeur
  statique ni dépendance vers le broker hôte.
- Politique de budget et contrats donneurs, dont consommation du crédit par
  les callbacks et réservation de l'IPC au passage suivant.
- Treize tests Python du comparateur, et fixtures de snapshot/maintien FPS.
- Contrat source, hash canonique et tous les postimages RPCS3 vérifiés ; seuls
  cinq postimages changent : Relay.h, RelayClient.h et RPCS3IOS.cpp/.h/.exports.
- Contrôles du périmètre de livraison et analyse des workflows YAML.

Les suites natives concernées ont aussi réussi avec ASan/UBSan sur Linux.
LeakSanitizer était désactivé pour ces exécutions : l'environnement refuse
l'accès `/proc` requis. Cela n'est ni un résultat LSan ni une validation iOS.
La revue indépendante n'a identifié aucun défaut bloquant sur les chemins
d'ownership, d'alias et de partage du budget examinés.

Patch canonique testé :
`1bd59add61f51b7188b0d02a14903230e8915e606da1c62230c210114ce6e1d6`.
Source du Core 441 : `351b738c8d4d5fbe2c7498d4438776baecdba613`,
run `38163319515`. Les workflows de livraison sont préparés pour cette
référence ; l'IPA ne doit être construite qu'après succès du run et contrôle
de son identité. Les 62 entrées Core sont identiques entre cette référence et
les sources hôte de livraison.

Le contrôle historique de baseline conserve les empreintes 439 et ajoute
uniquement celles des deux fichiers `native/neoswap-relay/Backend.cpp/.h`
modifiés en 441. Les treize tests du pipeline et les trois tests de baseline
passent ; le contrôle de réutilisation hors ligne conserve 2 127 entrées
inchangées. Aucun autre backend ni fichier de bibliothèque n'est autorisé par
cette exception.

Contrôles Apple sur la même source : les contrats préalables du Core ont
réussi. Le run `38163495049` a réussi en 14 min 45 s : tests de comportement,
compilation iPhone arm64 du plugin avec les services donation/relais/stockage
activés, puis profils baseline/relais/intégré sur simulateur iOS 18. Artefact
`11711228394`, ZIP SHA-256
`0de5be990d5ba0fd453f5df97b3308d79e96aef8209bc4873c748fec65dfd91d`.

Le run natif `38165036674`, même source, a également réussi : backend avec
ASan/UBSan sur macOS (stock préparé, alias, restitutions, pression et tokens),
preuve IPC après sortie du créateur, compilation/liaison iPhone arm64 de
l'extension et du gestionnaire, puis sortie/relancement de l'extension sur
simulateur iOS 18. L'écriture de 1 Gio sur macOS et la capacité virtuelle
retenue de 8 Gio sont des scénarios distincts du harnais ; ils ne constituent
pas une mesure de RAM donnée pendant un jeu RPCS3 sur iPhone. Artefact de
résultats `11711344465`, ZIP SHA-256
`879621c03be8e37b809224b0821f15b11fd01256c7403a4b76cc9fc18068d098`.

## Validation appareil à réaliser

Comparer le même parcours de God of War III sur le même iPhone, avec les mêmes
réglages, état de cache et conditions thermiques. Conserver l'identité de
l'IPA et du Core, le footprint brut, les octets donnés actifs, les demandes et
replis invités, les réserves préparées, la pression système, les temps d'image
et la progression réelle du jeu. Ne jamais soustraire « Donated » du footprint
ni assimiler la capacité virtuelle à de la RAM physique supplémentaire.
