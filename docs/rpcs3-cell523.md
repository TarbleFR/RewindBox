# RPCS3 523 — restauration et mesures mémoire

Travail sur `Claude`, après la livraison 522 (`139f3d79`), sans modification de
`main`, tag ou release. Les contrôles et la construction iPhone sont dédiés au
cœur modifié ; les preuves des composants inchangés sont authentifiées et réutilisées.

## Ce que les nouveaux journaux établissent

Le [rapport local reproductible](evidence/rpcs3-cell523-log-baseline.json) sépare
les anciens builds des **1351 lignes natives du build 522, PID 22952, BCES00510**.
Le fichier d'opérations n'indique pas de build : son association utilise le PID
et les dates communes. Ses 1843 événements uniques ne sont pas exhaustifs :
120 événements perdus sont déclarés. Les doublons des jalons ne sont pas additionnés.
Le journal d'application conserve plusieurs moteurs et lancements ; il ne sert
pas de source numérique mélangée pour les performances RPCS3.

Le lancement PPU réutilise 40 modules, sans recompilation, en environ 736 ms.
Les fenêtres tardives ralentissent vers 8–13 FPS avec environ 3,6 cœurs SPU
occupés. Les compteurs de temps GPU restent indisponibles (`-1`). Les scènes
ne sont pas identifiées : aucun intervalle n'est arbitrairement appelé menu,
cinématique ou gameplay. La fenêtre chevauchant l'arrêt/restauration est séparée.

Le TAR de restauration fait 1614785536 octets : environ 2,566 s entre ses jalons.
La restauration VM prend environ 0,431 s. Le dernier jalon est `ppu_exec_begin`,
position 1969125883. Cela ne démontre ni un verrou précis, ni une corruption,
ni la cause d'une terminaison. Le correctif ci-dessous n'est pas présenté comme
une restauration God of War III désormais confirmée.

Les allocations Vulkan atteignent environ 2,24 Go, avec plusieurs centaines de
Mo entre blocs réservés et allocations. Cet écart inclut la fragmentation ; il
n'est pas entièrement récupérable. Les archives vidéo montrent une file pleine
et des pixels archivés, sans notice de restauration de pixels dans cette capture.
Cela ne suffit pas à attribuer le ralentissement à une lecture NeoSwap.
Les prêts relais, alias mappés, résident, compressé et footprint se recouvrent :
ils ne s'additionnent pas. Une capacité configurée n'est pas de la RAM physique.

## Changements retenus et preuves

| Problème dans le code | Intervention | Validation et limite |
| --- | --- | --- |
| La validation de la table HLE restaurée vérifiait son premier octet, avant de protéger et réécrire une plage plus grande | Vérification de toute la table lisible et de son enveloppe allouée de 64 Kio, avec bornes de taille/adresse ; échec explicite du snapshot, sans essai comme overlay | 39 cas natifs, dont un contrôle négatif avec page absente acceptée par l'ancienne condition ; la sauvegarde originale n'est pas réécrite par cette vérification |
| Les rechargements internes et le redémarrage après création d'une sauvegarde pouvaient lancer le chargement dans le rappel de nettoyage UIKit | Un worker possédé, une seule admission, génération capturée avant l'arrêt, accès sérialisé au moteur, annulation des anciens rappels et jonction hors du verrou API, avec état SHUTTING_DOWN maintenu jusqu'à sa fin | 17 cas ASan/UBSan exécutent les méthodes de production, avec doubles Core/UI/fichiers : ancien chargement sur UIKit reproduit, nouveau hors UIKit ; annulations, fermeture concurrente, exception, deuxième restauration et refus d'auto-jonction |
| Le parcours VM multipliait les petits transferts même pour des lignes de cache contiguës | Regroupement borné à 64 Kio et saut des bitmaps vides, avec ordre des octets et points `breathe()` conservés | 160 cas différentiels ; 8 cas avec le vrai lecteur serial et ZSTD, y compris les données suivantes dans le flux ; capacité temporaire du lecteur inchangée dans ces cas |
| Le dernier jalon de restauration ne nommait pas l'opération PPU/FXO précise | Phases PPU/modules/graphique/entrées et début/fin de construction des objets, positions et état du lecteur | Maximum 512 événements FXO par restauration ; aucun timeout, déblocage forcé, modification de tags, de format ou d'ordre des objets |
| Les totaux Vulkan ne distinguaient pas les catégories qui grossissent | Instantané des octets demandés par pools système, surfaces, textures, swapchain, scratch, autres ; samplers en nombre d'objets | Une tentative de verrou lecteur, sept recherches, dans le rapport existant toutes les 5 s ; refus explicite si occupé. Essai avec verrou écrivain tenu et 30000 resets/reconstructions concurrents. Ni allocation GPU ni attente de fence ajoutée |

Le changement UIKit concerne les chemins internes. Le chargement demandé par
le menu hôte possède déjà sa file `_runtimeQueue` ; le déport interne ne prouve
donc pas la cause du dernier arrêt PPU observé. Le nettoyage RSX/renderer reste
au même endroit, avant la remise du travail. Aucun thread détaché supplémentaire.
Le worker dort après son travail et est joint lors de l'arrêt du Core. Son coût
mémoire sur iPhone reste à mesurer ; aucune économie de RAM physique n'est revendiquée.

## Mesure ARM64 du composant VM

[Actions 40099814314](https://github.com/TarbleFR/RewindBox/actions/runs/40099814314),
Apple M1 virtualisé, Xcode 16.4. Même source avant/après, blocs de 32 Mio,
12 tours en ordre alterné ; deux premiers écartés, médiane des dix suivants.
Chaque échantillon répète douze opérations. Il s'agit d'un banc mémoire chaud,
sans fichier, émulation ou mesure FPS. Pas d'intervalle de confiance calculé.

| Contenu des pages | Lecture avant → après | Écriture avant → après |
| --- | --- | --- |
| Zéro | 0,338 → 0,021 ms | 1,822 → 1,319 ms |
| Dense | 2,306 → 1,978 ms | 3,561 → 3,284 ms |
| Épars | 0,528 → 0,213 ms | 1,759 → 1,680 ms |
| Longues plages presque pleines | 2,303 → 1,984 ms | 3,212 → 2,962 ms |

Sur la fixture dense de 8 Mio, les transferts de payload passent de 2048 à 129.
Le premier essai Linux présentait une régression dans certains cas denses ; les
mesures ARM64 ci-dessus sont distinctes et ne sont pas des mesures sur A18 Pro.
Le [reçu complet](evidence/rpcs3-cell523-memory-probe.json) conserve les tours,
sources et empreintes. Les 8 essais ZSTD ne montrent pas d'augmentation de la
capacité du tampon de lecture (jusqu'à 16 Mio), ce qui n'est pas une mesure de RAM.

## Sources et périmètre

Base RPCS3 : XITRIX `22f1152783cef1f7e04af7b1c895173e28fd5b03`, delta canonique
avec les modifications locales déclarées dans `canonical-source.json`.
Pont local 0.1.0, Core ABI 30 ; LLVM 22.1.8 avec correctif AArch64 GHC,
FFmpeg 8.1.1 et MoltenVK 1.4.2. Les identités de code généré doivent rester PPU
`9013390836efe46e` / SPU `a601a98f20f30c80`, vérifiées pendant la compilation.

La [comparaison XITRIX v0.12](rpcs3-xitrix-v012.md) et ses attributions restent
valables : correctifs ISO, saut PPU ARM64/ARMSX3, SHUFB constant, limites du
shader interpreter et copies complètes de mipmaps sont déjà intégrés. Aucun
moteur d'IPA externe n'est transplanté. La correspondance complète entre l'IPA
XITRIX publiée et toutes ses sources reste non démontrée.

Les sources RPCS3 conservent leurs licences et auteurs. Les nouveaux helpers
internes sont GPL-2.0-or-later ; les adaptateurs de test locaux sont MIT.
Pas de migration de sauvegardes, suppression de cache utilisateur, changement
des réservations/atomiques CELL, barrières RSX, précision numérique ou NEON
de gameplay. Les anciens candidats NEON sans bénéfice établi restent écartés.
Le profilage ne justifie pas une nouvelle couche de traduction ni une réduction
aveugle de l'arène JIT. Choix manuels, StikJIT, LocalDevVPN et garde CPU avant
JIT/dlopen sont préservés. Core ARMv8.4-A ; aucune variante ARMv8-A annoncée à tort.
Pas de XMB, MetalFX d'interface, VPN interne, télémétrie, frameskip ajouté ou
modification de MeloNX, autres moteurs, traductions ou fonctions d'interface.

## Construction et essai sur appareil

Le Core final a réellement compilé pour iPhoneOS depuis
`e8437623a1ba37874adfacd8521c596e94d055c3`,
[Actions 40103133192](https://github.com/TarbleFR/RewindBox/actions/runs/40103133192).
Les 42 unités du contrôle SDK passent, puis le moteur complet est lié.
Le [reçu de validation](evidence/rpcs3-cell523-validation.json) conserve les
artefacts, leurs empreintes et les résultats natifs : 17 cas worker, 39 cas HLE/FXO,
instantanés GPU avec 30000 reconstructions concurrentes, ASan/UBSan. Les 160 cas VM
et 8 flux serial/ZSTD inchangés sont authentifiés depuis la campagne M1.
Un contrôle local supplémentaire compare les positions exactes des 160 séries
`breathe()`, avec la transformation du harness et ses empreintes enregistrées.

L'artefact téléchargé est vérifié indépendamment : 127 entrées natives, ABI 30,
88 exports exacts, ARM64/iPhoneOS, minimum de déploiement du Core 16.3,
PPU `9013390836efe46e` / SPU `a601a98f20f30c80` inchangés. Le contrôle statique
de chargement passif ne remplace pas un `dlopen` ou un JIT exécuté sur appareil.
SHA-256 du Core avant signature :
`d678bce3c8bb56a137393bb72bc6eea5d96a3053106c3cef78da8d63b438e9b4`.

Le premier passage SDK (`40101861338`) a refusé deux diagnostics ajoutés
(qualification de namespace et inclusion `shared_mutex`) ; ils sont corrigés et
ce passage n'a produit aucun Core et n'est pas livré. Le contrôle négatif de l'arrêt concurrent rejette
l'ancienne variante qui terminait le cycle avant la jonction du worker.
Le workflow générique `40103133217` échoue toujours avant compilation sur son ancien
test lexical Build 487 (`FREEZE_DUMP end`). Le test et le fichier natif concerné
sont identiques à ceux du Core 522 ; cette garde n'est pas affaiblie. Les contrôles
dédiés 523 ci-dessus passent. Aucun succès de toute la CI n'est revendiqué.

La **Build 523**, version **0.0.8**, a ensuite été reconstruite depuis
`c1f550f8be86c91d65dc564ebddff593f2e3fe46` sur `Claude` :
[Actions 40104064265](https://github.com/TarbleFR/RewindBox/actions/runs/40104064265),
jobs `checks`, `native` et `Release device build • cold` réussis.
Les composants validés non modifiés sont réutilisés avec leurs identités exactes.
Les sources produit de l'application restent identiques au Build 522
(`ace28d4231b96aad749cc948a05d03206a6f6662`).

Les quatre morceaux chiffrés ont été téléchargés, vérifiés contre leurs SHA-256
GitHub et leur manifeste commun, assemblés puis déchiffrés. L'IPA finale fait
**186268879 octets**, SHA-256 :
`7fa958570e802c489db4d4df07b7388cde4bb18f94c2555bcce060db9aedb8a1`.
Les identités du Core, ses sections de code/données, les segments hors LINKEDIT,
les exports et les dépendances sont vérifiés sur les octets téléchargés.
Les 84 images fines du reçu de scellement correspondent ; les 87 images Mach-O
sont contrôlées pour les entitlements VPN. Les 87 signatures ad hoc ont passé
`codesign --verify --strict` sur macOS, avec contrôle profond du ZIP final.
L'application demande iOS 18.0 et conserve sa garde CPU ARMv8.4-A.
Les signatures Apple et l'installation sur iPhone restent à effectuer par
re-signature **SideStore**. Aucun VPN interne, tag, changement de `main` ou
release GitHub n'est produit. Le lien privé de l'IPA est remis dans la conversation.

Les empreintes des autres cœurs embarqués sont identiques au Build 522.
Le pont Swift MeloNX est recompilé sans modification de source : seules ses
sections de stubs changent dans les octets comparés, avec dépendances et symboles
identiques. Il n'est pas déclaré bit-identique ; aucun correctif MeloNX n'est ajouté.
Les modifications d'images compilées sont consignées dans le reçu.

Pour revérifier l'IPA téléchargée depuis ce commit d'assemblage :

```sh
python3 build-utils/validate_rpcs3_cell523_ipa.py RewindBox-Build523.ipa --build-number 523
python3 packages/dolphin_internal_bridge/ci/verify_ipa.py RewindBox-Build523.ipa
```

Aucun iPhone ni dump légal du jeu n'est accessible dans cet environnement.
Restent à vérifier sur appareil : restauration de la copie du même état, lancement,
ISO, manette, JIT, pause/reprise, fermeture et deuxième lancement. Comparer le
522 et le candidat sur le même appareil, jeu/update, scène et réglages, avec
température initiale comparable, caches froids puis chauds. Séparer gameplay,
menu et cinématique ; relever lancement, CPU/GPU si disponible, p95/p99, saccades,
footprint maximal échantillonné et nouveaux pools GPU. Conserver les originaux.
