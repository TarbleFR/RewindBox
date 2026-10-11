# RPCS3 / NeoSwap — donations actives et empreinte de l’app

11 octobre 2026. Branche `Claude`. Départ :
`b238d64d470dd6c862d470e26f95138263b1e1b5`, bilan de la Build 438.
Cette modification concerne RPCS3/NeoSwap, son affichage et ses validations.

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
- Les vérifications Apple et Flutter ciblées sont exécutées séparément du
  contrôle global historique déjà bloqué sur la baseline. Leurs résultats
  doivent être associés au SHA exact testé.

Aucune nouvelle IPA ni validation de jeu sur iPhone n’est attestée ici.
L’IPA Build 438 précédemment livrée conserve son identité et son contenu.

## Sources primaires

- Apple XNU, [comptabilité du footprint et `use_pmap`](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/vm/vm_map_xnu.h).
- Apple XNU, [mapping des objets purgeables ou ledger-tagged](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/vm/vm_map.c).
- Apple XNU, [propriété et retrait du propriétaire des objets](https://github.com/apple-oss-distributions/xnu/blob/f6217f891ac0bb64f3d375211650a4c1ff8ca1ea/osfmk/vm/vm_object.c).

Ces sources expliquent le mécanisme ; elles n’identifient pas le noyau de
l’iPhone utilisé. Les sondes `relay_macos_probe.mm` et `macOS_probe.cpp`
contenues dans le dépôt sont des preuves distinctes à exécuter et à dater,
pas une mesure de gains obtenus pendant une partie sur iPhone.
