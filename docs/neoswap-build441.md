# NeoSwap — Build 441

## Périmètre et état

Le mainteneur a demandé le 11 octobre 2026 d'implémenter les conclusions de
l'audit puis de produire la Build 441. Le travail part de la branche `Claude`,
révision `0913f260beb71874ac4aea48ac3ac8014232f119`, qui conserve les ajouts de
la Build 440. Seuls RPCS3, NeoSwap et leurs éléments de validation/livraison
sont concernés. La compilation SPU différée reste désactivée.

Les contrôles Apple, la compilation du nouveau Core et la livraison de l'IPA
ont réussi. L'IPA a été récupérée, déchiffrée et vérifiée ; aucune validation
sur iPhone physique, économie de mémoire ni amélioration de FPS n'est attestée.

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
Ce stock réserve, depuis l'hôte, des jetons et des intervalles dans le backing
partagé déjà fourni par le relais ; son plafond de 64 Mio ne mesure pas 64 Mio
de RAM physique transférée dans une extension.
Les mécanismes adaptés de MeloNX et livrés en 438, ainsi que le comptage des
donations actives livré en 439, sont conservés.

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
run `38163319515`, réussi. L'artefact `11712198473` a été récupéré et vérifié :

- ZIP : 28 307 730 octets, SHA-256
  `fc400b54809a984698e6eac1d0627c8713c8d11b5e11386c10aac9c682812485`.
- Binaire `libRPCS3Core.dylib` : 75 406 728 octets, SHA-256
  `44c9dc4ca7b49c2c611da5b1b0cbb9acc77aa1c5596fc51a9e4416752eae37b2`.

L'intégrité CRC du ZIP, l'identité des 62 entrées Core et les ABI ont été
vérifiées. Les 62 entrées sont identiques entre cette référence et les sources
hôte de livraison ; les workflows épinglent ce Core validé.

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

## Livraison Build 441 vérifiée

Source hôte : `e1283fe543a8de5d6609359253d10dde46dbff2a`.
Le run de livraison `38167644455` a terminé avec succès : jobs `checks`
(`114553432661`), `native` (`114553432932`) et `cold` (`114553700601`).
L'artefact chiffré `11712993580` a été récupéré et déchiffré, puis l'IPA réelle
a passé les vérifications de `verify_delivery.py` consignées dans
`verified-delivery.json`.

| Identité vérifiée | Valeur |
|---|---|
| Version / build / plateforme | 0.0.2 / 441 / arm64 iPhoneOS |
| Taille de l'IPA | 207 211 278 octets |
| SHA-256 de l'IPA | `324f41191d77ed5a847862e29c744d9405f5c7f42c7d6097f8380606082977e0` |
| Taille du ZIP de l'artefact chiffré | 207 431 069 octets |
| SHA-256 du ZIP | `495d2770f0a4e2ce01be9a43a0a8e8aeb593b1af762b16c62eecb733d92c9a30` |

Les empreintes et tailles des archives, leurs CRC, les rapports de livraison,
`Info.plist` et `BUILD_SOURCE_IDENTITY.json` correspondent aux sources et aux
artefacts attendus. Les 54 empreintes d'images du rapport de signature sont
conformes aux binaires livrés. Le Core embarqué conserve le même code, les
mêmes données et les mêmes métadonnées ABI que le Core publié après signature ;
ses exports, dont les deux nouveaux points d'entrée Prepared/Stats, ont été
contrôlés par analyse Mach-O.

Les 57 signatures ad hoc ont été vérifiées en CI macOS. Aucune vérification
`codesign` locale ni confiance de certificat Apple n'est revendiquée par le
contrôle hors ligne. L'installation nécessite la re-signature Apple et le
provisioning par SideStore. Aucun essai de jeu, relevé de mémoire résidente ou
mesure de FPS sur iPhone n'a été réalisé pour cette IPA.

Un commit documentaire ultérieur ne change pas le SHA source de l'IPA : sa
référence de compilation reste `e1283fe543a8de5d6609359253d10dde46dbff2a`.

## Validation appareil à réaliser

Comparer le même parcours de God of War III sur le même iPhone, avec les mêmes
réglages, état de cache et conditions thermiques. Conserver l'identité de
l'IPA et du Core, le footprint brut, les octets donnés actifs, les demandes et
replis invités, les réserves préparées, la pression système, les temps d'image
et la progression réelle du jeu. Ne jamais soustraire « Donated » du footprint
ni assimiler la capacité virtuelle à de la RAM physique supplémentaire.
