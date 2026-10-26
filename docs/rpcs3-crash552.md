# RPCS3 552 — plantage au lancement de la 551 (26 octobre 2026)

Signalement : « RPCS3 plante lorsque je lance un jeu », avec `app_1.log`,
`RPCS3-diagnostic.log` et `RPCS3-milestones.log` exportés après trois
lancements sur l'IPA privée 551.

## 1. Faits (journaux)

| Processus | Jeu | Fin de boot (`game_boot_return`) | Processus suivant |
| --- | --- | --- | --- |
| 33884 | Dragon Ball Z HD Collection `BLES01658` | 12:58:00.113 | 33896 démarre 2,3 s plus tard |
| 33896 | Dragon Ball Z HD Collection | 12:58:14.597 | 33901 démarre 3,4 s plus tard |
| 33901 | God of War III `BCES00510` | 12:58:30.113 | aucun |

* Les trois boots réussissent (`status=0`), puis plus rien : ni jalon
  `JITPROF_BOOT` (fin du chargement des modules PPU, avant toute exécution du
  jeu), ni échantillon de performance, ni gel signalé (`FREEZE_DUMP`, déclenché
  après 3 s sans image), ni ligne d'erreur. L'application redémarre (journal de
  l'app : « Game started — monitoring active » puis « Starting RewindBox »).
* Avec le profil global, la même Dragon Ball Z atteignait `JITPROF_BOOT`
  0,40 à 0,44 s après la fin du boot (processus 31733 et 31897 en 545, 32192
  en 547). La 551 meurt donc **dans les 0,4 s** qui suivent : le jeu n'a encore
  émis aucune commande RSX ; seul le thread RSX démarre (chargement du cache de
  shaders, sa boîte de dialogue native, premières soumissions et présentations
  Vulkan, premières compilations de pipelines).
* Un nouveau processus 2,3 s après la fin du boot exclut un gel suivi d'une
  fermeture manuelle : c'est un plantage.

## 2. Ce que la 551 activait pour la première fois

`CONFIG_LAYERS` et la politique de boot de chaque démarrage enregistré avant la
551 (541 à 548) indiquent `fifo=1024` et `async_tex=false`. Dans les deux jeux
lancés en 551, le profil activait ensemble :

| Réglage | Dragon Ball Z (nouveau profil 551) | God of War III (profil enfin appliqué) | Agit avant 0,4 s ? |
| --- | --- | --- | --- |
| Soumissions MoltenVK asynchrones + files à priorité globale haute | oui | oui | **oui** : premières soumissions et présentations du thread RSX |
| Streaming asynchrone des textures | oui | oui (GameDB officielle + profil) | non : seuls les envois de textures du jeu l'utilisent |
| Cache FIFO RSX 4 Kio | oui | oui | non : aucune commande du jeu ; le tampon tient exactement 32 × 128 octets |
| Lot ARM64 (copie DMA, hachage de textures) | oui | oui | non : chemins des textures du jeu |
| Crochet QoS des compilations Metal | tous les jeux | tous les jeux | oui, mais il ne fait que choisir la file d'un `dispatch_async` (lu dans MoltenVK 1.4.2, `MVKSync.mm:451`) |

Hypothèse retenue : les **soumissions asynchrones** (jamais exécutées
ailleurs), la seule nouveauté active dans les deux jeux pendant cette fenêtre
et capable de faire planter le pilote. Elle n'est pas prouvée : aucune pile
d'appel n'a été fournie.

## 3. Pourquoi aucune erreur n'était visible

`report_fatal_error` (`rpcs3/ios/RPCS3IOS.cpp`) transmet son message au
journal de l'hôte puis appelle `std::abort()` aussitôt. Le journal de diagnostic
écrivait chaque ligne sur une file GCD de classe *utility*, de façon
asynchrone : la ligne était encore en mémoire quand le processus mourait. Aucune
erreur fatale de RPCS3 n'a jamais pu atteindre `RPCS3-diagnostic.log`.

## 4. Modifications (552)

* **Dragon Ball Z** n'a plus de profil : il retrouve le profil global avec
  lequel il tournait en 547 (31–35 fps, sans plantage). Un levier ne reviendra
  que seul et avec une mesure sur l'iPhone.
* **God of War III** garde le profil 551 (héritage de l'ancienne
  configuration, blocs SPU Mega, contournement MLAA, 75 %, 30 fps, RSX
  multithread…) sauf deux réglages Vulkan jamais exécutés sur l'iPhone : les
  soumissions MoltenVK restent synchrones (`Disabled`, explicite) et le
  streaming asynchrone des textures est désactivé (`false`, explicite : la
  GameDB officielle le demande). Sur MoltenVK, ce dernier active le calcul
  asynchrone, donc le DMA direct (mémoire invitée importée en tampons Vulkan) et
  une synchronisation des deux files par événements Vulkan.
* **Journal** : les lignes `core_log` sont écrites avant le retour de
  l'appel (`write(2)`, sans `fsync`) ; un message fatal précède donc l'arrêt. Les
  autres étapes (échantillons par seconde, etc.) restent asynchrones. Rien de ce
  que la file exécute n'écrit de diagnostic : l'attente ne peut pas se
  boucler.
* Le Core est celui de la 551 (run `40247161327`), inchangé.

## 5. Vérifications (sans iPhone)

* `test/rpcs3_game_profile_service_test.dart` : 12 tests, dont Dragon Ball Z
  sans profil et God of War III avec `MoltenVK Asynchronous Submits: Disabled`
  et `Asynchronous Texture Streaming: false` dans le YAML publié.
* `test/rpcs3_cell551_test.py` rejoué sur le Core 551 matérialisé avec le
  profil 552 (ASan+UBSan puis TSan) : 19 réglages hérités sur l'ancien fichier
  observé, valeurs effectives vérifiées (textures asynchrones `false`,
  soumissions `Disabled`).
* `test/rpcs3_core_log_durable552_test.py` : contrat de source partout ; sur
  macOS (job de livraison), le vrai journal Foundation reçoit une ligne fatale
  puis `abort()` : la ligne est dans le fichier ; le journal 551 (témoin) la
  perd ; 800 lignes de 8 threads entremêlées d'échantillons, puis `abort()` :
  aucune perdue, aucun interblocage.

## 6. Protocole iPhone

1. Lancer Dragon Ball Z : il doit atteindre le jeu comme en 547.
2. Lancer God of War III : premier démarrage avec son profil complet ; la
   première session compile les objets SPU pour les blocs Mega.
3. En cas de nouveau plantage : exporter `RPCS3-diagnostic.log`,
   `RPCS3-milestones.log` et le rapport iOS (Réglages › Confidentialité et
   sécurité › Analyses et améliorations › Données d'analyse, entrée du jour au
   nom de l'app). Un plantage par erreur fatale de RPCS3 apparaîtra désormais
   comme dernière ligne `core_log`.

## 7. Livraison privée 552 (26 octobre 2026)

- Recette : `.github/workflows/rpcs3-fix552-delivery.yml`,
  `.github/diagnostics/rpcs3fix552_tree.py` et `rpcs3fix552_delivery.py`,
  `build-utils/validate_rpcs3_552_ipa.py`, `validate_liquid_glass_fix552_ipa.py`,
  `validate_melonx_threading552_ipa.py`, clé publique
  `build-utils/delivery-552-rpcs3-recipient.pem` (clé privée hors dépôt). Les
  fichiers `melonxparity552_*`, `delivery-552-recipient.pem` et
  `validate_liquid_glass552_ipa.py` appartiennent à l'essai à blanc de la
  session MeloNX (run `40331958399`, non livré), qui devient la 553 sur cet
  arbre.
- Arbre : celui de la 551, plus les seuls fichiers du correctif `6b527ca` (les
  deux fichiers livrés sont les deux fichiers livrés de la 551). Les fichiers
  livrés remis à leur version 551, l'arbre redonne exactement celui de la 551
  (`lib` `0dbd5db9`, `packages` `26776d4b`) ; remis à leur version 550, celui
  des reçus 550 de l'interface et de MeloNX.
- Run `40335530316` (push `6a72700`), `checks` et `cold` réussis du premier
  coup. Sur macOS, le vrai journal 552 garde la ligne fatale à travers
  `abort()` et les 800 lignes de la rafale ; le journal 551 (témoin) perd la
  ligne fatale et toute la rafale.
- Artefact chiffré `12657104494` (187 031 965 octets, archive SHA-256
  `4db768dd4619fe0c2c7aa0ab6d434848b998b6d4f11db36395e45be0af888e5f`), déchiffré
  en local : IPA **0.0.8 (552)**
  `RewindBox-Build552-6a7270071cf0b7f28ef802c53dd64e9a6ad4153b-cold.ipa`,
  **186 533 120 octets**, SHA-256
  **`5ffc8bcd6a0ad681d2deff87f4fce5b0ed637c76116b13a0073e90a676037467`**, égale à
  `SHA256SUMS` et à `signed-payload-identity.json`. Core identique à
  l'artefact 551 (`38bd663e…`). Dans l'image Dart compilée : plus de numéro de
  série Dragon Ball Z, profil God of War III avec `Disabled`. Reçu :
  `docs/evidence/rpcs3-fix552-delivery.json`. Remise à l'utilisateur pour
  re-signature SideStore. Aucune validation sur iPhone. **Ne pas réutiliser le
  numéro 552.**
