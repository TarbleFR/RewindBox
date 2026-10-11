# RPCS3 / NeoSwap — donations actives et empreinte de l’app

11 octobre 2026. Branche `Claude`. Départ :
`b238d64d470dd6c862d470e26f95138263b1e1b5`, bilan de la Build 438.
Cette modification concerne RPCS3/NeoSwap, son affichage et ses validations.
Sources testées et publiées : `c2db51002b536df4cf79ddc384c48b38d567c394` ;
arbre Git `9b86f9062c3626b53700e9c9702299a80e3d85cc`.

## Compteurs corrigés

La courbe « NeoSwap supplied » additionnait des compteurs hôte incluant
des réserves FAST et des prêts en nettoyage différé ; elle omettait les objets de RAM invitée pris en charge par le relais. La courbe
« RAM appareil » ajoutait au footprint du processus les objets du relais,
y compris des réserves inutilisées. Leur somme n’était pas une mesure de RAM
physique résidente.

L’affichage présente désormais deux valeurs indépendantes :

| Valeur | Définition |
|---|---|
| RAM de l’app | `TASK_VM_INFO.phys_footprint`, sans ajout ni soustraction de mémoire partagée. |
| NeoSwap donated / Donné par NeoSwap | Objets invités publiés et non retirés + prêts relais hôte actifs de RPCS3 + prêts donneurs actifs de RPCS3. |

Un objet invité entre dans le compteur après son premier mapping réussi.
Ses autres alias ne sont pas additionnés. Un unmap temporaire conserve
l’objet ; son retrait l’exclut immédiatement du don actif, même si son
nettoyage reste en attente. Les compteurs de réservation continuent alors
à retenir ses octets jusqu’à restitution effective.

Un prêt hôte libéré en FAST est lui aussi exclu dès son abandon par RPCS3,
même si le nettoyage différé échoue. Les compteurs occupés/quota sont conservés
jusqu’à ce nettoyage. Le relevé du graphique ne bloque pas sur le courtier :
il est indisponible si son verrou est occupé.

Les réserves FAST, les pools préparés mais non utilisés, la capacité virtuelle,
les fichiers et les octets cumulés ne sont pas des donations actives. Une
mesure absente ou un débordement donne une valeur indisponible, pas un zéro
inventé. Les paramètres et le graphique partagent le même calcul. Les douze
catalogues conservent leurs traductions et paramètres de substitution.

Les entrées du contrôleur de budget restent distinctes : elles doivent
toujours compter le backing occupé, y compris les réserves. La politique
d’admission, les plafonds, les alias et l’ABI du Core ne changent pas.

## Ce que le transfert réalise déjà, et sa limite

NeoSwap crée le backing dans un processus auxiliaire et le mappe dans RPCS3
sans copie. Les objets des donneurs et ceux du Guest Page Relay utilisent
une comptabilité de propriétaire distincte du mapping hôte. Cela peut sortir
leur contenu du footprint principal ; « partagé » seul ne suffit pas à
garantir cette propriété pour une allocation quelconque. Les mappings gardent
aussi des coûts hôte, notamment les tables de pages.

Le Core sélectionne le backing invité avant la publication du premier alias.
Une fois le jeu en cours (`gameplay_active`), les nouveaux objets invités
utilisent le repli existant. La création et le mapping relais actuels prennent
un mutex et peuvent appeler le noyau : supprimer simplement ce garde-fou
introduirait ces opérations dans les threads du jeu.

Cette modification ne migre pas la RAM invitée déjà publiée et ne prétend pas
augmenter la quantité transférée. Une extension du transfert en cours de jeu
demande un chemin préparé, un emprunt borné, la préservation de tous les alias
et des mesures de latence. Migrer un objet existant demande en plus de
suspendre ses utilisateurs et de conserver ses protections et réservations.
Les octets « Donated » mesurent le backing attribué, pas sa résidence physique
ni une économie de RAM déduite artificiellement.

Le Core épinglé reste `96d7e709abae9e230254e7b26db8286cf05eb5a4` ; aucun
changement PPU, SPU, RSX, JIT, ni des autres émulateurs.

## Validation

- Tests C++ du cycle de vie relais, de son intégration au courtier et de la
  politique du graphique réussis localement sous ASan/UBSan.
- Cas couverts : premier mapping échoué, publication unique malgré les alias,
  unmap/remap, pression, retrait et nettoyage échoué, réserve seule, exclusion
  des autres propriétaires, prêt FAST abandonné, échec de libération ordinaire,
  contention sans blocage, mesure absente et débordement.
- Catalogues canonique/Dart identiques dans les douze langues ; substitutions
  conservées. Contrats donneurs et visibilité des headers vérifiés.

Le [run ciblé `38159349568`](https://github.com/TarbleFR/neostation-ios/actions/runs/38159349568)
a réussi sur le SHA source ci-dessus, le 11 octobre 2026. Les deux jobs utilisent
le mode explicite `donation_metrics_only=true` : ils ne revendiquent pas la
réussite du contrôle global historique bloqué sur la baseline, qui reste intact.

| Validation exécutée | Résultat |
|---|---|
| macOS 15, Xcode 26.3, Apple Clang 17 | Trois exécutables ASan/UBSan réussis : politique du graphique, backend relais, prêts hôte du courtier. |
| SDK iPhoneOS 26.2, cible arm64 / iOS 17.4 | Syntaxe des cinq sources réelles validée : NeoSwapPlugin, NeoSwapRelayService, Rpcs3InternalBridgePlugin, RPCS3PerformanceOverlay, RPCS3InGameLocalization. |
| Contrats Apple | 22 tests donneurs et 12 tests extension relais réussis ; visibilité des headers, stub et producteurs/lecteurs des performances vérifiés. |
| Traductions natives | 204 libellés exécutés via Foundation ; variantes chinois traditionnel et repli vérifiés. |
| Ubuntu 24.04, Flutter 3.47.2 | Dépendances verrouillées, analyse ciblée réussie ; 25 tests locale/canal/dialogue/stockage réussis. |
| Identité | Core 436 inchangé, arbre de travail propre après chaque job. |

L’analyse Dart signale seulement une information de style préexistante
(`curly_braces_in_flow_control_structures`, ligne 13 du catalogue). Les
compilations de syntaxe signalent la nullabilité incomplète des déclarations
du stub Flutter ; ce stub n’est pas le framework embarqué dans une IPA.

Les deux artefacts ont été récupérés et leur provenance vérifiée : **1 270
empreintes d’entrées chacun**, toutes identiques aux sources locales testées.
Ils contiennent les commandes, résultats, journaux et catalogues textuels des
douze langues, sans prétendre à des captures UIKit sur appareil.

| Artefact | ID | SHA-256 de l’archive |
|---|---|---|
| Apple | `11709783255` | `09b878b20b7697700261e8b104e4ca7a2c5bdb356a30d1daaabd15dd291f08f5` |
| Flutter | `11709474205` | `f03573d98d0dd1fe1fbd7ff95b90a67d400ca087a20e39cff62f711ca60f493a` |

Les gardes locaux de livraison et de baseline ont également réussi (10 et
3 tests), ainsi que le contrôle offline du périmètre et `git diff --check`.

## Livraison Build 439

Le [run de livraison `38159604350`](https://github.com/TarbleFR/neostation-ios/actions/runs/38159604350)
a réussi les jobs `checks`, `native` et `cold`. Le job `warm` est ignoré comme
demandé par `benchmark=false`. La source de livraison
`9cc7738bd58645293b09f5ade9d8278ee4c8047e` ajoute seulement le bilan aux sources
validées par le run ciblé. Les contrôles de la chaîne de livraison ont exécuté
les tests NeoSwap natifs et Dart ; le test Swift inchangé a été réutilisé après
vérification de ses entrées. Le contrôle global historique bloqué n’est pas
présenté comme réussi.

| Identité de livraison | Valeur |
|---|---|
| IPA remise | `NeoStation-Build-439.ipa` |
| Source de compilation | `9cc7738bd58645293b09f5ade9d8278ee4c8047e` |
| Version / build / plateforme | 0.0.2 / 439 / arm64 iPhoneOS |
| Taille | 206 912 287 octets |
| SHA-256 de l’IPA | `59bea1cf499c9ca2be2c4e935092cd53eea9906e464f9f284dcfebdfd211b006` |
| Artefact chiffré GitHub | `11710530147` |
| SHA-256 de son archive | `47963bca92254a0d57f8be8eacc6f3a6167beed35ef2c70ea5f6ed9f4b41a63c` |
| Signatures vérifiées en CI | 57 signatures ad hoc ; re-signature Apple par SideStore requise |
| Compilation Xcode mesurée | 220,805 s |
| Signature et export mesurés | 48,032 s |

Après récupération, le SHA-256, la taille, le numéro de build et le commit
embarqué ont été comparés à `SHA256SUMS`, `signed-payload-identity.json`,
`final-structure.json`, `Info.plist` et `BUILD_SOURCE_IDENTITY.json`. L’archive
ZIP a passé son contrôle d’intégrité. Les constantes natives `NeoSwap donated`,
`guestPublishedLiveBackingBytes` et `donatedBytes` ont été retrouvées dans les
binaires Mach-O livrés.

La Build 439 contient les optimisations de la 438 et ce nouveau comptage. La
438 déjà remise conserve son identité. **Aucun essai de jeu sur iPhone ni gain
RAM/FPS n’a été mesuré pour la 439** ; ce compteur n’active pas de transfert
invité supplémentaire pendant le jeu.

## Sources primaires

- Apple XNU, [comptabilité du footprint et `use_pmap`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/vm/vm_map_xnu.h).
- Apple XNU, [mapping des objets purgeables ou ledger-tagged](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/vm/vm_map.c).
- Apple XNU, [propriété et retrait du propriétaire des objets](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/vm/vm_object.c).

Ces sources expliquent le mécanisme ; elles n’identifient pas le noyau de
l’iPhone utilisé. Les sondes `relay_macos_probe.mm` et `macOS_probe.cpp`
contenues dans le dépôt sont des preuves distinctes à exécuter et à dater,
pas une mesure de gains obtenus pendant une partie sur iPhone.
