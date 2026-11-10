# GOW3 — événements SPU, attentes et reprise CPU

Base exacte : `rpcs3-followup-verify`, matérialisation du lot RewindBox
`a363d923`. Le constat précédent « aucune cause établie dans les traces » ne
suffisait pas à écarter des défauts de protocole dans le code. La reprise de
l'audit a donc comparé producteurs, consommateurs, chemins interprétés et
LLVM, restauration et attentes, avec deux lectures indépendantes.

Le journal historique montre le label `0x60300510` attendu à `0x6F0E` et
observé à `0x6F0D`. Cela identifie une attente non satisfaite, pas l'instruction
invitée chargée de produire la valeur suivante. Aucune des corrections
ci-dessous n'est présentée comme la résolution démontrée de cette scène.

| Piste | Fonctions examinées et contrainte | Preuve et décision | Potentiel / risque / statut |
|---|---|---|---|
| Signal SNR perdu ou parasite | `spu_channel::push`, `spu_thread::push_snr`, `set_events`, `get_events` | Le champ `old_count` recevait l'inverse du compte ancien. Le consommateur exige `old_count < count` : premier signal sans événement, répétition sur canal plein avec événement abusif. Correction `!= 0`, sans changement des atomiques, de la livraison ni des verrous. | Fort pour la justesse des échanges SPU; petite modification sémantique, testée; corrigé. |
| Travail MFC oublié à la restauration | Constructeur `spu_thread(serial)`, `serialize_common`, `cpu_task`, `cpu_work`, `get_ch_value`/`read_channel`, état initial `CPUThread::state`, lancement `Emulator::FinalizeRunRequest` | File/masques/tags restaurés, drapeau hôte `pending` absent. Sans interruption active, aucune réactivation automatique. Ajout du drapeau si file non vide et mélange MFC activé; aucun transfert exécuté dans le constructeur. | Fort pour cette reprise conditionnelle; défaut non attribué à GOW3, réglage par défaut zéro; corrigé. |
| Publication de tag de barrière LLVM | `SPULLVMRecompiler::WRCH`, `do_mfc`, `get_mfc_completed`, `set_ch_value(MFC_WrTagUpdate)` | Tag du slot précédent conservé dans la branche barrière, contrairement au C++. Une barrière encore bloquée pouvait paraître achevée. Correction et preuves détaillées dans `gow3-mfc-audit.md`. | Fort pour l'ordre observable; change le code émis, donc cache SPU invalidé; corrigé. |
| File LLVM pleine et interruption avant acceptation | `WRCH`, préambule plein de `process_mfc_cmd`, `check_mfc_interrupts`, `IRET` | La file pleine conduisait à une adresse traitée comme HALT. Le nouveau chemin utilise le helper bloquant. Son examen a révélé que le drainage pouvait interrompre avant acceptation avec retour `pc+4`, sautant la commande; `do_mfc(false)` puis contrôle d’interruption avec `pc` préserve le WRCH à rejouer. | Deux réparations directes; tests finaux IRQ réussis, dont 192 acceptations exactement une fois après IRET; détails dans le registre MFC. |
| Notification perdue lors de l'inscription d'une réservation | `reservation_notifier_begin_wait`, `end_wait`, `reservation_notifier_notify`, attentes GETLLAR et RdEventStat | Inscription avant revalidation de `rtime`; génération changée avant notification. Un changement avant l'attente invalide sa valeur attendue. Les chemins iOS examinés utilisent aussi des attentes bornées et des comparaisons répétées de la ligne. | Aucune perte permanente démontrée; conserver protocole et barrières. Pas de modification spéculative. |
| Endormissement RdEventStat et course avec set_events | `get_ch_value(SPU_RdEventStat)`, `get_events`, `set_events`, `thread_ctrl::wait_on_custom` | La boucle générale relit le compteur après une attente de 100 µs; `m_sync` conserve la notification, l'attente composite observe aussi état et file de tâches. SNR corrige la production de l'événement, pas une suppression de ces attentes. | Aucun défaut supplémentaire établi dans l'attente; concurrence matérielle non validée par les adaptateurs. |
| PUTLLC sans écriture et réservation ARM64 | `do_putllc`, `do_cell_atomic_128_store`, `reservation_check`, `cmp_rdata`, `rdata_fence`, politique expérimentale iOS | Les écritures réelles restent sous protocole de réservation/plage; la voie exacte revérifie le temps et les données. La politique no-op préservant les réservations est automatique pour DBZ et BO2, pas GOW3. Supprimer comparaisons ou barrières réduirait les garanties sans preuve de nécessité. | Chemin potentiellement coûteux mais aucune nouvelle simplification sûre démontrée ici; ne pas confondre PUTLLC réussi avec progression du producteur du label. |
| Code généré et caches après correction | Sources SPU, liste CMake des entrées codegen, `JITCacheCompatibility.cmake` | Aucune nouvelle équivalence de hash. Les trois fichiers CPU changés font évoluer l'identité SPU; le fichier d'alias reste inchangé. Les objets anciens ne sont pas réutilisés sous la nouvelle identité. | Compatibilité correcte au prix possible d'une reconstruction des objets SPU au prochain lancement. Coût appareil non mesuré. |
| Production exacte du label GOW3 | PUT LLVM/C++, DMA/listes, écriture de sémaphore RSX et historique MLAA/restauration | Les PUT LLVM concernés passent au helper C++ qui conserve protections et verrouillages RSX. Le label lui-même n'a pas été forcé. Les extraits disponibles ne fournissent ni programme invité/PC producteur ni ordre des événements de la scène. | Ouvert : requiert reproduction de la scène avec les corrections ou capture existante identifiant le producteur; aucune fausse preuve causale. |

## Modifications réellement présentes

- `rpcs3/Emu/Cell/SPUThread.h` : ancien compteur de `spu_channel::push`
  corrigé; commentaire adapté au retour structuré. Le mailbox quatre entrées
  a sa propre implémentation correcte et ne change pas.
- `rpcs3/Emu/Cell/SPUThread.cpp` : réarmement de `cpu_flag::pending` après
  désérialisation d'une file MFC différée. L'opération conserve les autres
  drapeaux; barrières, commandes, réservations et format sauvegardé inchangés.
  Le préambule d’attente de place dans la file prend désormais une interruption
  avec le PC du WRCH non encore accepté, pour permettre sa reprise.
- `rpcs3/Emu/Cell/SPULLVMRecompiler.cpp` : stockage du tag des commandes
  `BARRIER`, `EIEIO`, `SYNC`, et retour au helper bloquant sur file pleine,
  détaillés dans l'autre registre.

Le défaut SNR existe aussi dans le commit amont local
`22f1152783cef1f7e04af7b1c895173e28fd5b03`; il n'a pas été introduit par le
lot précédent. L'architecture CELL spécifie l'événement SNR lorsque le compte
passe de zéro à non nul : IBM/Sony/Toshiba, *Cell Broadband Engine
Architecture*, v1.02, 11 octobre 2007, page 156. Le même document §7.9.3,
page 77, définit l'observation de l'achèvement d'une barrière par son tag.
Source primaire consultée :
https://www.cresco.enea.it/LA1/cresco_sp14_ylichron/CBE-docs/CBEA_v1.02_11Oct2007_pub.pdf

## Vérifications nouvelles

Les six modes finaux (SNR, restauration, MFC avec IRQ) sont des compilations
C++20 ciblées avec assertions actives, normal et ASan/UBSan. Quatre passages
intermédiaires MFC, avant approfondissement de la file pleine puis de l’IRQ,
restent conservés et authentifiés. Aucun Core ou IPA n'a été compilé.

| Test | Résultat vérifié | Limite explicite |
|---|---|---|
| SNR, vraie classe de canal et corps `push_snr`/`set_events`/`get_events` | 768 scénarios : avant 256 événements manquants et 512 parasites; après zéro divergence. 1 280 comparaisons de charge utile, 512 cycles pop/re-push, huit scénarios attente/jostling/notification différée et quatre reprises CAS déterministes. | Atomiques et notifications adaptés; pas une preuve de concurrence sur ARM64. |
| Restauration, vraie sérialisation des champs et file, bloc constructeur, `read_channel`, `do_mfc`, complétion de tags | 144 scénarios; 72 attentes bloquées avant aboutissent après; 36 listes restent bloquées jusqu'à acquittement. 24 queues vides et 48 cas mélange désactivé inchangés. | Sérialiseur et ordonnanceur hôtes explicites; pas le format complet d'un fichier savestate ni un transfert DMA réel. Le drainage par lecture de canal ne dépend pas d'un timeout. |
| File pleine et interruption avant acceptation, CFG final et vrais préambule/IRQ/IRET | 96 HALT historiques remplacés par le drainage; 96 arrêts/reprises, 96 attentes de listes, 96 événements déjà présents avec drainage multipasse. 96 WRCH historiquement sautés reproduits; 192 nouvelles commandes acceptées exactement une fois après IRET, dont 96 avec acquittement de liste depuis le gestionnaire. | Effets du gestionnaire d’interruption adaptés explicitement; pas une exécution native de l’ISR invité ni de ses drapeaux de contrôle. |
| Émission de tag LLVM et vrai protocole MFC | 49 152 scénarios; 47 616 complétions prématurées avant et zéro après, tous les résultats corrigés concordent avec le chemin C++. | Évaluateur des opérations du builder IR, sans compilation de LLVM ni exécution AArch64. |

Les premiers assemblages des harnais SNR/restauration ont révélé uniquement
des erreurs de préparation des adaptateurs : indentation, alias du canal,
conversion de sentinelle entière et sérialisation d'un argument constant.
Ces défauts des tests ont été corrigés avant les deux passages finaux; aucune
assertion de régression n'a été supprimée.

`gow3-source-and-proof-record.json` conserve les hashes avant/après et
l'authentification des six programmes finaux et des quatre étapes intermédiaires effectivement testés. Le test SNR a
précédé le changement du constructeur dans `SPUThread.cpp`; son programme
extrait final reste identique à l'octet. Ses rapports originaux sont conservés
et leur réutilisation est attestée sans recompilation inutile.

À cet état du lot : PPU `a987639e9f838d1c` inchangé;
SPU `d070cb361bdef607` → `477a3fa442d27917`. Il s'agit du calcul des entrées
CMake, avec le digest externe LLVM déjà attesté réutilisé; aucun objet invité
n'a été recompilé pour produire cette preuve. La première utilisation du
nouveau cache SPU peut donc recompter des compilations et pauses de démarrage.
Leur coût et les FPS sur iPhone ne sont pas mesurés.

Deux limites de coût/ordonnancement restent explicites : `ensure_gpr_stores()`
peut limiter l’élimination de stores au niveau du bloc compilé, même si la
file n’est finalement pas pleine; `do_mfc(false)` peut effectuer plusieurs
passes de mélange avant le contrôle d’IRQ à sa sortie. Cette IRQ reste avant
l’acceptation du nouveau WRCH et avant l’attente d’une file toujours pleine.
Ces corrections ne sont donc pas présentées comme des gains FPS.

La revue indépendante de la reprise MFC n'a trouvé aucun défaut bloquant.
Les contrôles de scène GOW3, du pipeline appareil et de concurrence native
restent ouverts. L'investigation adjacente de la file pleine LLVM a produit les deux corrections
supplémentaires ci-dessus; ses étapes de preuve figurent dans le registre MFC.
