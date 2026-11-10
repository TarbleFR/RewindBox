# RPCS3 Core 919 — Black Ops II attend ses rapports ZCULL

Suite de la mission du 10 novembre (Black Ops II doit tourner plus vite) et de la consigne du mainteneur : « les
diagnostics sont suffisamment fournis pour avancer ». Core 919 = Core 918 + ce document. **Aucune mesure iPhone n'a
été faite avec ce Core.** Ce qui suit vient des journaux applicatifs de la build 676, du code et d'un modèle hôte qui
exécute le vrai code ZCULL et le vrai code de soumission du rendu Vulkan.

## 1. Symptôme chiffré

Journaux de la build 676 (Core 905, `BLES01717`, PID 25658, session 3, fenêtres de jeu 9 à 19, 20 à 26 images/s) :

| Mesure par fenêtre de 5 s | Valeur |
|---|---|
| Lectures de rapports ZCULL qui attendent (`ZCULLDEMAND619 waits`) | 42 à 113 |
| Temps d'attente total de ces lectures | 205 à 1 165 ms |
| Threads qui attendent (`ZCULL624 fault_threads`) | PPU uniquement (0 SPU) |
| Âge moyen du plus ancien rapport en attente au moment de la lecture (`ZCULLLEAD659`) | 5,0 à 15,0 ms (max 24,5 ms) |
| Command buffer sur le GPU (`GPUTIME621`, fenêtre 12, moyennes) | 2,2 ms d'exécution, 1,5 ms de file |
| Soumissions anticipées de 561 (`OPT561`, fenêtre 12) | 615 pour 104 images (5,9 par image, plafond 6), 72 019 refus par le plafond |

Fenêtre 12 : 72 lectures attendent 594 ms au total, soit 8,3 ms chacune et 5,7 ms par image de 49 ms. Le jeu est
limité par le processeur invité (GPU occupé 32 %, FIFO du RSX occupée 46 %) : ce temps est pris sur les threads PPU.

## 2. Chemin de production

- MoltenVK ne publie le résultat d'une requête d'occlusion qu'à la fin de tout son command buffer. Le command buffer
  d'un rapport n'est soumis qu'à la prochaine soumission : la soumission anticipée de 561 (seulement quand le GPU a
  fini la précédente, au plus 6 par image), la demande d'un invité, ou le flip.
- Quand un thread PPU lit un emplacement de rapport encore en attente, le gestionnaire de faute (`ios_on_demand_fault`,
  lectures asynchrones de 630) demande au thread RSX de soumettre ce command buffer, puis attend que le GPU l'ait fini.
- Un rapport mis en file 5 à 15 ms avant sa lecture, avec un command buffer qui prend 3,7 ms entre sa soumission et
  sa fin, aurait été prêt s'il avait été soumis peu après : c'est le cas que le « vidage surveillé » du Core 660
  (`REWINDBOX_ZCULL_WATCHED_FLUSH_660`) traite pour Assassin's Creed. Il apprend les emplacements que l'invité attend
  1 ms ou plus après leur dernier rapport, puis arme, quand un tel rapport est mis en file, la soumission « frontière »
  du Core 659 de son command buffer (au prochain début de draw sans passe ouverte, sinon après 32 draws).
- Black Ops II en avait été écarté sur un modèle hôte où il lit un rapport aussitôt après l'avoir mis en file ; les
  journaux de l'appareil disent le contraire (section 1). Le chiffre « 45,8 → 67,0 ms » cité alors est celui du modèle
  de la garde de profondeur (vidages sautés), pas des soumissions surveillées.
- Second obstacle, propre à Black Ops II : un armement surveillé était aussi refusé dès que l'image avait utilisé les
  6 soumissions de 561, et une soumission surveillée comptait dans ces 6. Black Ops II les épuise (5,9 par image).

## 3. Modification

- `REWINDBOX_ZCULL_WATCHED_BO2_919` (`rpcs3/ios/IOSTitleLevers.h`) : Black Ops II rejoint la liste du vidage
  surveillé. L'apprentissage ne change pas : un titre qui lit ses rapports aussitôt n'apprend rien et ne soumet rien
  de plus.
- `REWINDBOX_ZCULL_WATCHED_OWN_BUDGET_919` (`rpcs3/Emu/RSX/VK/VKGSRender.cpp`, `rpcs3/ios/IOSZcullWatched.h`) : un
  armement surveillé n'est refusé que par son propre budget (2 par image) ; une soumission surveillée ne compte plus
  dans les 6 de 561. Une image prend donc au plus 6 soumissions anticipées et 2 surveillées.
- Ligne de politique `Resolved title policy 919`.

Seules les frontières des command buffers bougent : les valeurs des rapports, leur ordre et le moment où l'invité les
lit ne changent pas ; aucune passe n'est coupée. Aucune condition d'attente, aucun réglage de résolution, de précision,
de limite d'images, de nombre ou de priorité de SPU, de délai GETLLAR/PUTLLC ou d'option LLVM. Aucun fichier d'entrée
des identités de code généré n'est modifié : les caches restent valides.

## 4. Contrôle discriminant (hôte)

`test/rpcs3_zcull_watched919_test.py` construit le banc du Core 660 (`test/native/rpcs3_zcull_levers660_harness.cpp.in` :
le vrai `RSXZCULL.h/.cpp`, `sync_hint`, les fonctions de requêtes, d'indices et de soumission anticipée de
`VKGSRender.cpp`, le bloc de requêtes de `emit_geometry`, sous AddressSanitizer et UndefinedBehaviorSanitizer, autour d'un
modèle de rendu, de GPU et d'invité) deux fois : avec le code du Core 918 (contrôle, obtenu en annulant l'incrément du
Core 919) et avec l'arbre testé. Deux formes d'images Black Ops II (environ 2 400 draws, un rapport sur trois draws dans
256 emplacements tournants, un emplacement relu 20 à 30 % de l'image après son rapport) :

| Modèle hôte (24 images) | Lectures qui attendent | Attente totale | Durée moyenne d'image |
|---|---|---|---|
| `bo2read`, Core 918 tel que livré (levier coupé pour BO2) | 23 sur 23 | 127,8 ms | 34,89 ms |
| `bo2read`, code du Core 918 avec le levier allumé | 23 sur 23 (22 armements refusés par le plafond de 561) | 127,8 ms | 34,89 ms |
| `bo2read`, Core 919 | 2 sur 23 | 11,6 ms | 30,05 ms |
| `bo2busy` (561 sous son plafond), Core 918 tel que livré | 24 sur 24 | 106,3 ms | 33,86 ms |
| `bo2busy`, Core 919 | 1 sur 24 | 4,4 ms | 29,61 ms |

Le contrôle reproduit le défaut avant correction ; la deuxième ligne montre qu'ajouter le titre seul n'aurait pas
suffi. Dans toutes les exécutions : écritures de rapports et lectures égales à l'oracle et au contrôle (valeurs, ordre,
empreintes), aucune passe coupée, au plus 6 soumissions de 561 et 2 surveillées par image ; levier coupé, le flux
d'événements (chaque soumission, passe et draw) est celui du contrôle ; Assassin's Creed (déjà surveillé) lit les mêmes
valeurs et n'attend pas plus. Le test du Core 660 passe toujours sur le banc étendu.

Ces chiffres sont ceux d'un modèle hôte. Ils montrent le mécanisme ; ils ne prédisent pas le gain sur l'iPhone.

## 5. Ce que l'export suivant décidera

- **Le levier agit** si, en jeu, `ZCULLWATCH660` montre des emplacements appris (`slots=` premier champ) et des
  soumissions prises (`taken=`), et si `ZCULLDEMAND619 waits` baisse avec les images/s qui montent.
- **Il n'agit pas** si `slots=` reste à 0 avec `short_lead` élevé : Black Ops II lit alors ses rapports moins de 1 ms
  après le dernier, et le Core suivant visera l'exécution du command buffer elle-même.
- **Il coûte** si `RSXSYNC551 submit=` monte plus que l'attente ne baisse.

## 6. Limites

- L'âge du **dernier** rapport d'un emplacement attendu n'est pas dans les journaux (seulement celui du plus ancien) ;
  le modèle donne un seul rapport par image à l'emplacement relu.
- La part du thread PPU principal dans ces attentes n'est pas mesurée ; tous les threads PPU sont comptés.
- Aucun gain n'est connu sur l'iPhone.

## 7. Protocole iPhone

Celui du [Core 918](rpcs3-core918-busy-wait.md) § 8, inchangé : Black Ops II, lancement, scène lente jusqu'à neuf
minutes après le lancement, export aussitôt avec les fichiers `.1`.
