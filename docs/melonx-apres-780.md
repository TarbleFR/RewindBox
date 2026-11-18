# MeloNX après l’IPA 780

Bilan du 18 novembre 2026 avant publication. La version examinée sur iPhone est l’IPA 780. Les modifications ci-dessous sont locales sur `Claude`, après les commits S2Arm du déclenchement indépendant de la 781 (`9a4156b2f50cc44e45d9473fb053880dfd9c5321`). Les deux commits de production sont `5655578e617bff60f79b5662cbe4b24d12d69951` pour le moteur et l’import, et `1ed6a0681e03e429ba46dd92764593b12bc7bda0` pour le catalogue.

## Hogwarts Legacy v1.0.5

Sur trois lancements du titre `0100f7e00c70e000`, le même thread de service lève `ServiceNotImplementedException` lors de la commande 150 de `IManagerForApplication`. L’exception est immédiatement suivie de `SIGABRT`. La vidéo montre l’avertissement du jeu, puis le retour à l’écran d’accueil d’iOS. Les journaux cumulés ont été recoupés par titre, PID et session. La session de Smash entre les deux derniers essais est comptée séparément.

| PID Hogwarts | Arrêt sur la 780, heure de Paris | Première présentation après le contrôle des droits | Dernière empreinte / mémoire disponible |
|---|---|---:|---:|
| 43820 | 02 h 16 min 08,834 s | 11 s | 2 729 / 3 926 Mio |
| 43839 | 02 h 17 min 01,679 s | 10 s | 2 878 / 3 777 Mio |
| 43858 | 02 h 18 min 52,236 s | 10 s | 2 884 / 3 771 Mio |

L’arrêt survient environ 22 secondes après le début de chaque session du moteur. Le correctif traite `CreateAuthorizationRequest` dans le service de compte. En l’absence de fournisseur d’autorisation Nintendo, il retourne le refus prévu par le service. Aucun compte n’est créé et aucune connexion au compte du joueur n’est nécessaire à ce traitement. [Adaptation du service](../build-utils/melonx/adapt_account_cache_import.py)

Le répartiteur CMIF et la table de handles du noyau de la 780 ont reproduit l’exception avec la requête enregistrée. Sur le répartiteur corrigé, 512 appels ont rendu `InternetRequestDenied` (`0x767c`). La copie du handle reçue par le service a été fermée à chaque appel, le handle d’origine est resté utilisable et aucun objet de domaine n’a été renvoyé. Les requêtes sans handle ou avec un handle invalide ont rendu `InvalidArgument` (`0x2c7c`). La commande voisine contrôlée fonctionne toujours. Le menu, la sauvegarde et le jeu en extérieur restent à vérifier sur l’iPhone.

## Import des mises à jour NSZ

La playlist Switch et la fiche du jeu acceptent `.nsp` et `.nsz` dans l’action d’import de mise à jour. L’application décompresse le NSZ une seule fois lors de l’import, puis le moteur inspecte le NSP reconstruit avec LibHac. Il vérifie le type de contenu et le titre visé avant de changer `updates.json`. Une erreur retire le fichier en cours de préparation et préserve la sélection précédente. Le chargement du jeu réutilise directement la mise à jour installée. [Service d’import](../lib/services/melonx_embedded_library_service.dart) · [Décodeur](../native/melonx/EmbeddedNsz.cs) · [Inspection du moteur](../native/melonx/EmbeddedAddons.cs)

- Le sélecteur de la 780 refusait le même fichier avant son inspection. Le parcours Flutter corrigé a sélectionné et activé le NSZ, puis sélectionné un NSP existant. Les contrôles couvraient aussi un autre titre, un fichier corrompu, un échec d’enregistrement et le filtre des DLC.
- Avec un paquet de test synthétique contenant de vraies structures CNMT, Program et Control, le moteur compilé a rendu le titre `0100123456780000`, la version `1.2.3` et le Build ID `0102030405060708` pour le NSP d’origine comme pour le NSZ. La tentative d’import pour un autre jeu a rendu `addonWrongGame`.
- Les quatre reconstructions positives ont été comparées octet par octet. Elles couvrent NCZ en flux continu, des blocs stockés ou compressés et les limites de sections chiffrées. Six entrées altérées ont été refusées. Le décodeur travaille par blocs de 64 Kio et limite la fenêtre Zstandard à 128 Mio. Un gros fichier réel avec l’espace de stockage et le sélecteur Fichiers de l’iPhone reste à essayer. [Format NSZ](https://github.com/nicoboss/nsz)

## Temps de lancement et RAM

La 780 charge 2 112 shaders déjà en cache pour Hogwarts en 1,76 à 1,89 s sur l’iPhone. Un worker a attendu l’ouverture du cache Vulkan principal pendant 1 633, 1 474 et 1 609 ms. Ces temps se recouvrent. Sur Smash, 12 150 shaders ont été chargés en 9,65 s et la première présentation arrive à 17 s. Ces chronos partent de marqueurs distincts dans le journal. Ils ne mesurent pas le délai avant le premier mouvement jouable.

Le changement regroupe les petites lectures de métadonnées compressées dans un tampon réutilisable de 4 Kio. Les enregistrements valides conservent leur format et leurs valeurs. Avec un enregistrement brut tronqué et un bloc Brotli trop court, le témoin 780 était encore en boucle à l’expiration du délai d’une seconde. Le candidat signale la corruption à la voie de reconstruction existante. Un en-tête ou une longueur invalide libère également le tampon. [Lecteur de métadonnées](../native/melonx/EmbeddedShaderMetadataReader.cs)

Banc Linux x64, .NET 10 Release. Chaque programme du lot synthétique contient 25 champs dans le format comprimé de production. Les médianes portent sur 14 lectures chronométrées à chaud par taille et par version. Les valeurs décodées ont été comparées. Les allocations managées mesurées après échauffement sont équivalentes. La comparaison ne mesure ni la RAM résidente du téléphone, ni la cadence des jeux.

| Lecture des métadonnées | Core de la 780 | Candidat |
|---|---:|---:|
| 2 112 programmes | 16,80 ms | 11,99 ms |
| 12 150 programmes | 86,98 ms | 61,21 ms |

## Catalogue Switch

La révision `2026-11-18T0203Z.194be1570540` ajoute 664 entrées pour 110 jeux, dont 15 titres nouvellement couverts. Le catalogue **Cheats & Enhancements** répartit les nouveautés en 168 entrées FPS, 202 ultrawide, 281 graphiques, 2 de performances et 11 codes de triche. Le Build ID de la mise à jour sélectionnée sert au contrôle de compatibilité lorsqu’il est connu. Le choix d’un mod reste manuel. [Source d’origine, révision épinglée](https://github.com/Fl4sh9174/Switch-Emulator-Ultrawide-FPS-Mods/tree/5eed21701e8091389e2e746f073f694ea2ad4ec6)

- Les 117 archives ont été examinées. Le premier catalogue local pouvait reconstruire 665 entrées, mais le parseur natif a identifié 15 références sans instruction active. Le catalogue final écarte ces couples patch/version et conserve les versions utiles des mêmes mods. Il exclut aussi les ensembles qui dépendent de fichiers compagnons non pris en charge.
- L’application a reconstruit les 664 entrées depuis les archives originales. Le parseur IPSwitch du moteur a traité les 1 006 références ExeFS retenues, soit 12 011 écritures de patch. Son compilateur Atmosphère a accepté les 31 couples code/Build ID. Un test a activé puis retiré trois mods via le service de l’application, dont un combinant ExeFS et code de triche. Les fichiers installés, leur retrait, le refus d’une version incompatible et un unique téléchargement par archive ont été vérifiés.
- Toutes les entrées Switch antérieures ont été retrouvées à l’identique. Les 96 fichiers de catalogue des trois autres moteurs sont identiques octet par octet. Le catalogue contient les métadonnées et les empreintes. Le téléphone télécharge les ZIP originaux depuis le dépôt de l’auteur. [Générateur](../tools/enhancements/build_enhancement_catalog.py) · [Lecture des archives](../lib/services/enhancements/enhancement_origin.dart) · [Adaptateur MeloNX](../lib/services/enhancements/adapters/melonx_enhancement_adapter.dart)

## Compilation, livraison et essais sur appareil

L’IPA témoin `2d51f50ee4e0845823dc0bbe14d3cb0f76043667036da5c0af07c1cc711bec1a` provient de l’application `c005092532d8686ba05dfbc66d725bf17b01d5e1`. Son core iOS arm64 `631959ad378df6d1251072329c9cf816eaa539dc2b75a93a0738a0686a71aa68` provient de `f41ae7924b821ec791a812dccb857acba769ca67`. [Reçu de l’IPA 780](evidence/rewind780/standard-ipa-validation.json)

Pour le candidat, les composants managés de MeloNX ont compilé en Release sur Linux x64. La préparation a vérifié 275 entrées et 241 fichiers de source. Le contrat de composition a passé 519 contrôles, le banc des copies DMA de Hogwarts 172, celui du chargeur de shaders 28 et celui des codes du moteur 55. Les 8 tests d’intégrité du catalogue ont réussi. Les groupes Flutter ciblés ont réussi, y compris les parcours d’import, de catalogue, de crédits et de paramétrage du skin. Les groupes ciblés comptaient 53 et 38 tests Flutter. Les deux groupes complémentaires (import et catalogue, crédits et réglages du skin) comptaient 14 tests chacun, avec des parcours communs. Le pont Swift a passé l’analyse syntaxique. La compilation iOS avec le SDK Apple, l’édition de liens et la vérification du composant dans une IPA restent à effectuer lors de la livraison autorisée.

[Mesures brutes du banc et résultats structurés](evidence/melonx-apres-780/host.json)

**Le candidat compte zéro essai sur appareil à ce stade.** Pour la vérification sur appareil, reprendre Hogwarts v1.0.5 à 1x avec les mêmes réglages et la même sauvegarde. Relever la première présentation, l’arrivée au menu puis la première commande jouable, à froid et sur trois lancements à chaud. Continuer chaque session jouable au-delà de 55 s et mesurer la cadence présentée, les intervalles longs et la mémoire en extérieur. Vérifier également l’import d’un NSZ depuis Fichiers et l’activation d’un mod correspondant au Build ID du jeu installé. Le gain sur le délai complet et l’objectif des 30 FPS en extérieur restent ouverts.

Le crash Mario de la 718 et les commandes du skin au retour du menu ont un historique de vérification distinct. Les preuves antérieures du projet enregistrent la correction de durée de vie du drawable et 19 contrôles natifs du skin. Cette capture Hogwarts de la 780 ne fournit pas de nouvel essai appareil sur ces deux défauts. [Résultats antérieurs](evidence/melonx-719-gates/run.json) · [Scénarios Mario, skin et saccades](evidence/melonx-719-gates/device-protocol.md)
