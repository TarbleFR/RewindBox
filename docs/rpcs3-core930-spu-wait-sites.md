# RPCS3 Core 930 — le profil SPU dit sur quoi attend un thread SPU

Core 930 = Core 929 plus la classification des attentes SPU dans le profil de régions SPU (`COREPROF SPUPROF923`).
Marqueur : `REWINDBOX_SPU_WAIT_SITE_930`. **Diagnostic seulement : rien n'est changé dans l'exécution du jeu. Rien n'a
encore tourné sur un iPhone avec ce Core.**

Point 1 de l'ordre défini par le mainteneur pour Black Ops II (11 novembre 2026) : « instrumenter les attentes SPU ».

## 1. Pourquoi l'étiquette actuelle ne suffit pas

Dans les journaux de la build 725 (Black Ops II, PID 52378, privés, hors Git), 41 % des échantillons SPU sont en
attente et `wait_calls=` les attribue presque tous à `sys_spu_thread_send_event`. Cette étiquette est celle du dernier
appel nommé, pas celle de l'attente : `spu_thread::current_func` n'est remis à zéro qu'à l'abandon d'un appel, jamais après
son retour. Un thread qui attend un canal, une commande MFC ou un `STOP` garde le nom de son dernier appel système. Le
Core 930 garde cette colonne (renommée dans l'en-tête `wait_calls_scope=last_named_call`) pour lire les anciens journaux.

## 2. Ce que le Core 930 mesure

Le recompilateur SPU LLVM appelle `update_pc()` avant chaque lecture ou écriture bloquante de canal, chaque commande MFC
et chaque `STOP` : l'instruction à l'adresse LS[pc] est donc celle qui attend. À chaque échantillon en attente, le
profil classe, dans cet ordre (`rpcs3/ios/IOSSpuWaitSite930.h`) :

1. les drapeaux du thread : `flag_pause`, `flag_suspend`, `flag_memory`, `flag_debug` ;
2. sinon l'instruction à LS[pc] : `rdch_event`, `rdch_in_mbox`, `rdch_signal`, `rdch_tag_status`, `rdch_atomic_status`,
   `rdch_list_stall`, `rdch_other`, `rchcnt_wait`, `wrch_out_mbox`, `wrch_out_intr_mbox`, `wrch_tag_update`,
   `wrch_other` ;
3. pour une écriture du canal de commande MFC, la dernière commande : `mfc_getllar`, `mfc_putllc`, `mfc_putlluc`,
   `mfc_get`, `mfc_put`, `mfc_other` ;
4. pour un `STOP` : `stop_receive_event`, `stop_yield`, `stop_other` ; sinon `not_a_call`.

Ligne produite : `wait_sites=nom:échantillons,…` sur la ligne de chaque thread de `COREPROF SPUPROF923`, avant
`wait_calls=` ; l'en-tête ajoute `wait_sites_scope=flags_then_instruction_at_saved_pc`. L'analyseur
`tools/rpcs3/capture_analyzer.py` l'affiche quand elle existe. Les lectures sont faites sans verrou sur le thread
échantillonné, comme celle du pc déjà présente ; rien n'y est écrit. Deux fichiers : `rpcs3/ios/IOSSpuWaitSite930.h`
(nouveau) et `rpcs3/ios/RPCS3IOSFreezeDump.cpp`. Les numéros de canal, les codes `STOP` et les opcodes sont vérifiés à la
compilation contre ceux du moteur (`static_assert`). Aucune entrée de génération de code ; identités PPU a987639e / SPU
477a3fa4 inchangées.

## 3. Contrôle (hôte)

`test/rpcs3_spu_wait_site930_test.py` : vérifications statiques contre `SPUThread.h`, `SPUOpcodes.h`, `sys_spu.h` et les
appels `update_pc()` du recompilateur, puis 27 vérifications du vrai classificateur sur de vrais mots d'instruction SPU
(g++ ASan+UBSan). Contre-épreuve toujours exécutée : un classificateur qui lit le canal dans le champ `rb` au lieu du
champ canal est détecté. Le test du profil 923 passe toujours. Le pilote du Core 930 enchaîne les incréments 901 à 930.

## 4. Les deux autres points de l'ordre

- **Point 2, verrou d'écriture exact des réservations** : chaque PUTLLC lourd parque tous les PPU (fenêtre de 5 s :
  1,76 M verrous, 785 ms ; 1,70 M parcages de moins de 0,5 µs). Aucun saut supplémentaire n'est sûr : les PPU en
  attente ou endormis sont déjà sautés, et sauter un PPU en cours d'exécution perd ses écritures ordinaires. Regrouper
  les parcages est à haut risque. Aucun changement sans une mesure d'appareil qui le justifie.
- **Point 3, pipelines compilés en jeu** : chaque construction coûteuse (435-581 ms) est un nouveau fragment shader, jamais
  vu dans les sessions 724 ; un préchauffage ne peut pas aider. Le mode interpréteur asynchrone aiderait mais reste coupé
  sans l'accord du mainteneur (règle du tableau).

## 5. Bilan

- **Coût supprimé** : aucun ; c'est une mesure.
- **Coût restant** : un tableau de 26 compteurs par thread SPU suivi et une lecture de l'instruction par échantillon en
  attente, seulement quand le profil SPU est actif.
- **Chemin critique** : inchangé hors profil.
- **Mémoire** : 26 × 4 octets par thread suivi.
- **Risques** : lecture concurrente d'un état SPU qui change (une attente peut être mal classée pour un échantillon) ; le
  classement par drapeaux passe avant l'instruction.

## 6. Protocole d'appareil

Black Ops II en multijoueur, profil SPU actif comme pour la build 725 ; exporter les journaux. Lire `wait_sites=` par
thread : la part `rdch_*`, `mfc_*` et `stop_*` dit si les SPU attendent le PPU, la mémoire ou un événement, ce qui choisit
la prochaine correction.
