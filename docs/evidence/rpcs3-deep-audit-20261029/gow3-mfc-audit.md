# GOW3 — MFC, LLVM et restauration

Base de comparaison : `rpcs3-followup-verify`, matérialisation du lot `a363d923`.
Les fonctions examinées sont celles de `rpcs3-core`. Aucun lien causal avec la
scène GOW3 figée n'est établi par ce travail.

| Piste | Fonctions et contrainte | Preuve obtenue | Statut |
|---|---|---|---|
| Tag des barrières mises en file par LLVM | `SPULLVMRecompiler::WRCH`, branche de secours `MFC_Cmd`; `spu_thread::do_mfc`, `get_mfc_completed`, `set_ch_value(MFC_WrTagUpdate)` | L'émetteur écrivait `cmd` mais conservait le `tag` précédent du slot, alors qu'il ajoutait le tag courant au masque de clôture. `do_mfc` reconstruit ensuite ce masque depuis le tag périmé. Le chemin C++ copie le descripteur complet. Le test reproduit 47 616 complétions prématurées sur 49 152 scénarios, puis zéro après correction. | Corrigé : stockage du tag courant dans les branches `BARRIER`, `EIEIO`, `SYNC`. |
| Réactivation de DMA différés après restauration | `spu_thread(serial)`, `serialize_common`, `cpu_task`, `cpu_work`, `get_ch_value(MFC_RdTagStat)`, `Emulator::FinalizeRunRequest` | La file et ses masques sont restaurés, mais `cpu_flag::pending` ne l'est pas. Le lancement ne le réarme pas lorsque les interruptions sont désactivées. Avec le mélange des commandes activé, la file différée peut ainsi perdre son appel à `do_mfc`. La valeur par défaut du mélange est zéro. | Défaut transmis à l'agent parent, propriétaire de la correction et des tests de restauration. Pertinence pour la session GOW3 non établie. |
| Production du label par DMA PUT | `SPULLVMRecompiler::WRCH`, `spu_thread::process_mfc_cmd`, `do_dma_transfer`, `do_list_transfer` | Les PUT LLVM constants sont forcés vers le helper C++ (`must_use_cpp_functions`); les commandes non constantes suivent aussi le helper. Le chemin C++ conserve les verrouillages de plage et les protections RSX. Le code ne permet pas d'identifier quelle instruction invitée devait produire `0x6F0E` à `0x60300510`. | Pas de raccourci natif PUT démontré comme cause; aucun label forcé ni verrou retiré. |
| Ordre de la file MFC et des barrières | `spu_thread::do_mfc` | `std::remove_if` traite les commandes dans l'ordre source. `removed` permet de reconnaître une barrière devenue première. Les listes bloquées gardent leur clôture; la barrière globale reste présente jusqu'à leur reprise. Le test du tag vérifie que la correction ne libère aucune barrière avant l'acquittement de liste. | Ordre conservé par le correctif; aucun défaut nouveau du compactage démontré. |
| Prélecture de listes près de la fin du LS | `do_list_transfer`, `map_ls` | La lecture anticipée de six entrées peut franchir la fin logique du LS, mais `map_ls` mappe cinq fenêtres du même stockage (LS et deux miroirs de chaque côté). Une simple prélecture de 48 octets ne prouve donc pas un accès non mappé. | Hypothèse d'accès hors mapping écartée pour cette prélecture. |
| État des transferts à la restauration | `serialize_common`, constructeur de restauration | Commande active, taille de file, barrières, clôtures, demandes de tag, état des canaux et contenu exact de la file sont sérialisés. Les réservations sont réacquises et leur contenu recopié. | Pas d'omission de la file elle-même; la réactivation de l'ordonnanceur reste une question distincte, traitée ci-dessus. |
| File pleine dans le code LLVM | `WRCH`, sélection du slot de secours; `Utilities/Thread.cpp::handle_access_violation`; `exec_wrch`, `exec_wrch_result`, `process_mfc_cmd` | Une file légale de 16 transferts différés déclenche une écriture à `0xffdeadf0`; son consommateur traite cette plage comme un HALT SPU et met le thread en pause. Il n'existe pas de reprise MFC cachée dans ce gestionnaire. Le chemin C++ traite la file, attend si nécessaire et respecte l'arrêt/reprise de l'écriture bloquante. Le nouveau test reproduit 96 HALT historiques et 96 reprises réussies. | Corrigé : branche vers le helper WRCH générique lorsque la file est pleine, après publication du PC courant et préservation des stores de registres. |
| Interruption avant acceptation d'une commande, pendant le drainage d'une file pleine | `process_mfc_cmd`, `do_mfc`, `check_mfc_interrupts`, `IRET` interpréteur/LLVM | Le préfixe historique appelle `do_mfc()` avant le switch qui accepte la nouvelle commande. Une interruption peut alors enregistrer `pc + 4` et sortir; `IRET` reprend directement `srr0`. La commande n'est encore que dans `ch_mfc_cmd`, et aucun consommateur autonome de ce descripteur après la sortie n'a été trouvé. Le test reproduit 96 sauts historiques du WRCH; la correction permet 96 reprises et 96 acquittements de liste par interruption, avec 192 commandes acceptées exactement une fois après retour. | Corrigé par l'agent parent dans `SPUThread.cpp` : `do_mfc(false)`, puis contrôle d'interruption avec le PC courant avant acceptation. |

## Référence architecturale

IBM, Sony Computer Entertainment et Toshiba, *Cell Broadband Engine
Architecture*, version 1.02, 11 octobre 2007, §7.9.3, page 77 : le tag fourni
sert à observer la fin de la commande `barrier`, qui attend les commandes
antérieures. La barrière ordonne l'ensemble de la file; cela ne rend pas son
tag de complétion facultatif.

La section §9.1.1, tableau 9-2, classe l'écriture de `MFC_Cmd` comme bloquante.
Une file pleine doit donc bénéficier du traitement d'attente existant; elle
ne justifie pas une pause assimilée à un HALT invité.

Source primaire consultée :
https://www.cresco.enea.it/LA1/cresco_sp14_ylichron/CBE-docs/CBEA_v1.02_11Oct2007_pub.pdf

Le défaut de stockage du tag est également présent dans le commit amont local
`22f1152783cef1f7e04af7b1c895173e28fd5b03`; il n'est pas attribué au dernier lot.

## Modification et vérification

`rpcs3/Emu/Cell/SPULLVMRecompiler.cpp` : une instruction d'émission
`CreateStore(tag.value, _ptr(pmfc, &spu_mfc_cmd::tag))` dans le chemin de mise
en file des trois commandes de barrière. Une seconde correction teste
`slot < 16` avant l'accès à la file. Sinon, elle publie le PC, appelle
`ensure_gpr_stores()`, puis `spu_write_channel` via `exec_wrch`, et rejoint
directement la suite sans ajouter une seconde fois la commande. Le chemin
de mise en file non pleine conserve ses clôtures, son ordre et son compteur.

Les nouveaux tests extraient le bloc de secours LLVM complet, le vrai
`do_mfc`, le calcul des tags terminés, la branche de requête de tag et la
branche C++ de mise en file des barrières. Un évaluateur des opérations IR
charge et stocke dans une mémoire bornée; les transferts DMA, l'horloge et la
livraison du canal restent des frontières hôtes explicites.

- 49 152 combinaisons : trois commandes, 32 tags courants, 256 anciens octets
  de tag, slots de file 1 et 15.
- 47 616 complétions prématurées avant, zéro après; toutes les variantes
  corrigées concordent avec le chemin C++.
- 192 encodages de DMA ordinaires inchangés.
- Les six sélections de file pleine du rapport intermédiaire du tag décrivent
  le comportement historique, avant la seconde correction.
- Tests hôtes C++20 avec assertions actives, mode normal et ASan/UBSan réussis.

Les rapports `gow3-mfc-llvm-plain.json` et `gow3-mfc-llvm-asan.json` conservent
les empreintes des sources et des corps exécutés à l'étape intermédiaire.
`gow3-mfc-llvm-tag-stage.diff` permet de reconstruire exactement cette source
depuis la base immuable. Les rapports n'ont pas été réécrits pour leur attribuer
la correction suivante.

Le test de la seconde étape `test/rpcs3_spu_mfc_full_queue_test.py` authentifie cette étape
intermédiaire, puis exécute le bloc LLVM final dans un adaptateur de CFG avec
mémoire bornée. Il extrait le vrai préfixe d'attente de `process_mfc_cmd`, la
branche `set_ch_value(MFC_Cmd)` et les helpers `exec_wrch`/`exec_wrch_result`.
Après le préfixe, son adaptateur utilise la branche C++ réelle des trois
commandes de barrière; il ne prétend pas exécuter tout le dispatcher MFC.

Les rapports de cette étape `gow3-mfc-full-plain.json` et `gow3-mfc-full-asan.json`
attestent les résultats suivants avant la correction d'interruption :

- Nouvelle exécution des 49 152 combinaisons de tags : 47 616 complétions
  prématurées avant, zéro après, et 192 encodages de DMA ordinaires inchangés.
- 96 combinaisons de commande et tag pour chacun des scénarios : file pleine
  récupérable, arrêt avant drainage, reprise à la même instruction, sortie
  `again`, liste bloquée attendant son acquittement, interruption durant le
  drainage.
- Aucune double mise en file; le PC courant et la commande restent disponibles
  lors de l'arrêt. Aucune libération de la liste ou de sa barrière avant
  l'acquittement simulé.
- Le cas d'interruption durant le drainage vérifie la parité avec le helper
  générique inchangé, qui peut enregistrer `pc + 4`. Il ne constitue pas une
  preuve du comportement complet de l'ordonnanceur invité.

La revue ultérieure de `IRET` a confirmé que ce dernier cas peut sauter le
`WRCH` avant acceptation de sa commande. Il est donc conservé comme preuve
d'un défaut hérité, pas comme validation du comportement architectural. Le
parent a appliqué la correction dans `SPUThread.cpp` : appeler `do_mfc(false)`,
puis `check_mfc_interrupts(pc)` et sortir si nécessaire, avant le test de
place libre. Cela conserve la possibilité pour une interruption de débloquer
une liste tout en reprenant la commande courante. Les passages internes de
shuffling de `do_mfc(false)` finissent avant le contrôle externe d'interruption;
le placement du contrôle entre passages internes n'est donc pas identique.

Le nouveau test final `test/rpcs3_spu_mfc_full_irq_test.py` reconstruit le
préfixe historique depuis la base, vérifie l'empreinte du harnais complet de
la seconde étape, puis remplace ce préfixe par le code de production final.
Il exécute également les corps réels de `IRET` et `exec_list_unstall`. La
gestion des flags de l'instruction `IRET` et les effets du gestionnaire
d'interruption restent des adaptateurs déclarés.

Les preuves `gow3-mfc-full-irq-plain.json` et `gow3-mfc-full-irq-asan.json`
attestent, en mode normal et ASan/UBSan :

- Les 49 152 scénarios de tags et tous les cas de file pleine ci-dessus
  repassent sur les sources finales.
- 96 commandes sautées après `IRET` avec le préfixe historique, contre 96
  reprises du `WRCH` courant avec le préfixe corrigé.
- 96 interruptions déjà pendantes avant drainage, avec shuffling sans étapes
  et plusieurs masques d'exécution nécessaires pour vider la file.
- 96 listes toujours bloquées au moment de l'interruption : aucune commande
  libérée avant acquittement, interruption livrée sans attendre une place
  libre, acquittement par le helper réel, puis retour à la commande courante.
- 192 commandes acceptées exactement une fois après le retour d'interruption.

Les rapports des deux étapes antérieures restent inchangés; le test final
authentifie leurs sources et leurs harnais sans réexécuter leurs binaires.

Deux erreurs de préparation du harnais de la seconde étape ont été corrigées avant ses
exécutions : les arguments par défaut de `do_mfc` manquaient dans la déclaration
de l'adaptateur, et un `if` de cet adaptateur déclenchait
`-Wmisleading-indentation`. Aucune de ces corrections ne concernait le code
de production. Les rapports finaux correspondent au harnais corrigé.

Les revues indépendantes de `cpu_native`, `wake_audit` et de l'agent parent
ont vérifié la domination de tous les stores de file par la garde, le PC de
reprise, la préservation des stores, l'absence de seconde mise en file et
l'exclusion de `WRCH MFC_Cmd` des boucles avec registres élidés.
La revue finale du harnais IRQ par `wake_audit` a également vérifié les
extractions, la reconstruction des étapes, le retour par `IRET`, les
acquittements et les empreintes des rapports, sans problème concret relevé.

`ensure_gpr_stores()` agit au moment de la génération du code : il peut
conserver des stores de registres sur le chemin non plein qui étaient
auparavant supprimés. Cette préservation est nécessaire au contrat du helper
retenu; aucun bénéfice de performance de cette correction n'est revendiqué.

Les trois scripts acceptent `--compiler` (valeur par défaut `CXX` ou `c++`) et
`HOST_MACOS_SDK`. Les options anti-PIE du test sanitizé sont limitées à Linux.
La portabilité de l'interface n'est pas une exécution vérifiée sur macOS.

LLVM n'a pas été compilé, le code ARM64 n'a pas été exécuté, les transferts
DMA et la concurrence mémoire restent adaptés sur l'hôte. Aucun test sur
appareil ni gain FPS n'a été mesuré. Le digest de `SPULLVMRecompiler.cpp`
change; aucun alias de compatibilité n'a été ajouté, afin que les anciens
objets SPU ne conservent pas l'émission fautive. Ni ces tests ni les traces
disponibles ne prouvent que ces défauts causent le gel GOW3 observé.
