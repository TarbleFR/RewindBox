# NeoSwap — Build 441

## Périmètre et état

Le mainteneur a demandé le 11 octobre 2026 d'implémenter les conclusions de
l'audit puis de produire la Build 441. Le travail part de la branche `Claude`,
révision `0913f260beb71874ac4aea48ac3ac8014232f119`, qui conserve les ajouts de
la Build 440. Seuls RPCS3, NeoSwap et leurs éléments de validation/livraison
sont concernés. La compilation SPU différée reste désactivée.

Ce document est un journal de travail : aucune validation iPhone ni économie
de mémoire n'est attestée à ce stade. La compilation Apple reste à effectuer.

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
Le Core publié 436 reste provisoirement épinglé jusqu'à production et contrôle
du nouveau Core ; il ne contient pas les changements 441.

## Validation appareil à réaliser

Comparer le même parcours de God of War III sur le même iPhone, avec les mêmes
réglages, état de cache et conditions thermiques. Conserver l'identité de
l'IPA et du Core, le footprint brut, les octets donnés actifs, les demandes et
replis invités, les réserves préparées, la pression système, les temps d'image
et la progression réelle du jeu. Ne jamais soustraire « Donated » du footprint
ni assimiler la capacité virtuelle à de la RAM physique supplémentaire.
