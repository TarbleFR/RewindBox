# RPCS3 : observations de l’IPA privée 593

Analyse des journaux fournis le 29 octobre 2026. Les mesures décrivent l’IPA 593 livrée ; elles ne mesurent pas les correctifs développés ensuite. Aucun gain de FPS entre builds n’est établi par ces captures.

Le fichier [device-observations.json](device-observations.json) conserve les empreintes des neuf entrées, les identités des processus, les réglages actifs, les références de lignes et les agrégats par phase. Il ne contient aucun journal brut ni chemin privé de l’appareil ou de l’environnement de travail.

## Sources et séparation des sessions

| Référence | Fichier fourni |
| --- | --- |
| P4 | `RPCS3-performance(4).log` |
| P1 | `RPCS3-performance.1.log` |
| P3 | `RPCS3-performance(3).log` |
| M5 | `RPCS3-milestones(20261029-051248).log` |
| D5 | `RPCS3-diagnostic(20261029-051248).log` |
| D2 | `RPCS3-diagnostic(20261029-024119).log` |
| A5 | `app(20261029-051255).log` |

Le processus étudié est **build 593, PID 47785**. Ses sessions 1 et 2 sont Black Ops II (`BLES01717`), la session 3 God of War III (`BCES00510`) démarré normalement, la session 4 ce même jeu restauré depuis une sauvegarde d’état, puis la session 5 Assassin’s Creed (`BLES00158`). Les logs déclarent un GPU Apple A18 Pro et le pilote `0.2.162` (M5:820,826,833,855,873).

La preuve de livraison existante lie l’IPA au Core `c143be63`, run `40814736023`, SHA256 brut `0966c03dcd264fdbcf813f9a7af320434c5dac0f555c1460c917358394b1f0ac`. Les journaux portent le numéro d’application, mais ne fournissent pas une nouvelle empreinte du binaire chargé sur l’iPhone. Références réutilisées : `docs/evidence/rewind593-delivery.json` et `docs/evidence/rpcs3-runtime-20261029b/apple-core.json`.

La rotation demande une séparation explicite : **P1:1–3488 appartient au build 588/PID 47121, Bladestorm**, et reste exclu des résultats 593. P1:3489–3630 est la première session BO2 de 593 ; sa fenêtre 5 continue en P4:1–13 et n’est comptée qu’une fois. Les 737 premières lignes de M5 et les 1 865 premières lignes d’A5 reprennent exactement les anciens exports. Les copies de compteurs Core présentes dans D5 ne sont pas additionnées à P4.

Tous les démarrages PPU retenus réutilisent leurs modules : **72/72, 86/86, 40/40, 45/45 et 175/175**, avec zéro module compilé et zéro cache miss (M5:822,827,835,863,875). Ils ne constituent pas des démarrages PPU à cache froid.

## Phases mesurées

Les FPS ci-dessous sont le nombre d’images présentées divisé par la somme des durées de fenêtres. Les phases ne sont pas des scènes identiques entre jeux ou entre builds.

| Phase 593 | Images / durée | Images/s écoulée | Travail établi |
| --- | --- | ---: | --- |
| BO2, session 2, fenêtres 7–13 | 1 219 / 37,292873 s | 32,687211 | 6 228 hits SPU, 128 misses ; 6 221 événements de lecture de cache totalisant 3 918,311 ms. 17 intervalles d’image >100 ms, maximum 2 447,213 ms. |
| BO2, session 2, fenêtres 14–22 | 960 / 47,269435 s | 20,309107 | 32 longues opérations de pipeline graphique, total 19 926,181 ms. 29 intervalles >100 ms, maximum 3 783,054 ms. |
| GoW3 restauré, session 4, fenêtres 3–11 | 973 / 46,898807 s | 20,746796 | Cache SPU et codegen inactifs ; 973 drains MoltenVK pour 973 images, total 2 566,601 ms. Textures : 4,619–15,502 ms/image échantillonnée. |
| GoW3, session 4, fenêtres 13–15 | 0 / 15,178217 s | 0 | Aucune image, aucun dessin ni submit ; activité invitée partielle encore présente. |
| AC, session 5, fenêtres 28–43 | 2 262 / 82,778834 s | 27,325826 | Aucun travail de lecture/compilation SPU ni création de pipeline ; 64 721 soumissions synchrones totalisant 21 414,545 ms. |

Références respectives : **P4:199–408**, **409–710**, **960–1229**, **1261–1350**, **2227–2706**.

### Black Ops II : deux coûts différents

Avant les longues opérations Metal, le cache SPU atteint **97,986 % de hits**, mais les objets existants occasionnent encore des lectures et décompressions. Les 6 221 événements comptabilisent 18 781 336 octets d’objets décodés, environ 3 019 octets par événement. La première session présente aussi 10 181 événements de lecture pour 5 010,544 ms, contre seulement 31 codegens pour 241,031 ms (P1:3524–3630 et P4:1–13). Le compteur ne mesure ni le nombre de syscalls ni la taille compressée des fichiers.

La phase suivante a une autre signature : **32 opérations de pipeline de 218,876 à 1 085,744 ms**, dont 15,750841 s de création de bibliothèques fragment et 1,693905 s de bibliothèques vertex. Les lectures SPU restantes sont alors 367 événements/456,066 ms, et les codegens 39/630,150 ms. Réduire les accès aux objets SPU ne supprime pas ces créations Metal (P4:414–685).

Les symptômes d’armes ou d’avant-bras incorrects sont signalés par le mainteneur. Les compteurs ne permettent pas de les attribuer à une optimisation particulière. WCB, prehash et async textures sont inactifs dans ces sessions BO2 (M5:818–825 ; groupes OPT581 de P4).

### God of War III : travail continu, puis attente de label

Avant le gel, le prehash obtient 50 041 hits et 36 360 misses. Le worker lit **80 732 570 328 octets** pour 80 234 hashes/5 702,047 ms. Le total de hash hybride, worker inclus, est de 129 593 889 304 octets/9 182,994 ms : ces deux temps ne s’additionnent pas. Les readbacks `fault_read` comptent 978 sections, 3 586 867 220 octets demandés et 3 828,100 ms ; les octets demandés ne sont pas une mesure de transfert physique GPU (P4:960–1229).

Les deux queues Metal légitimes coexistent avec un drain par image et zéro attente de marqueur. Le même comportement se voyait déjà dans une phase lourde de 588 : 342 drains/342 images pour 1 659,904 ms (P3:737–917). Cela justifie une correction de sélection de queue conservant les garanties d’ordre ; ce compteur ne suffit pas à expliquer le gel.

**À 05:05:14.101734 UTC**, le RSX attend à l’adresse invitée `0x60300510` la valeur `0x71B4`, alors qu’il lit `0x71B3`, depuis 2 001 713 µs (M5:867). Le snapshot de **05:05:15.283544** indique 3,028 s sans image ; six SPU sont momentanément dans `MFC_Events_read`, masque `0x400` (M5:868, copie P4:1260).

Les fenêtres complètes suivantes restent sans rendu pendant **15,178217 s**, avec zéro JIT, hash, drain ou readback. Elles enregistrent néanmoins **3 609 attentes d’événement terminées et 69 872 PUTLLC réussis** (P4:1275,1305,1335). Le dump ne signifie donc pas que tous les SPU restent définitivement endormis. Ces compteurs ne distinguent pas les PUTLLC sans changement des écritures effectives et n’identifient pas le producteur du label manquant.

La fermeture est demandée à **05:05:33.218323 UTC** ; aucun retour d’image n’est observé avant celle-ci (A5:5944). Les traces ne prouvent ni une récupération ultérieure, ni une attente éternelle, ni une régression apparue en 593. La piste restante porte sur le producteur du label et l’ordre CPU/RSX/GPU après restauration.

### Assassin’s Creed : plateau à caches chauds et saccades ultérieures

Le plateau de 82,779 s autour de **27,326 images/s** ne contient aucun travail JIT ni création de pipeline. Il présente 2 679–2 710 dessins/image, **6,905–7,657 ms de textures**, 5,005–5,382 ms de préparation et 2,964–3,292 ms de vertex par image échantillonnée. Le groupe RSX utilise 1,105–1,131 cœur et son FIFO est occupé à 95,6–97,2 %. Les soumissions synchrones représentent environ 28,6 appels et 9,47 ms de durée d’appel par image. **Le GPU n’est pas chronométré** (`gpu_time_ms=-1`) ; ce temps ne devient pas une mesure d’exécution GPU (P4:2227–2706).

Des saccades distinctes suivent : fenêtre 49, trois nouveaux pipelines totalisent 1 741,475 ms, avec un intervalle d’image maximum de 1 790,422 ms ; fenêtre 57, un pipeline de 515,914 ms accompagne un maximum de 549 ms. La fenêtre 58 contient 806 lectures SPU/390 ms et 42 codegens/329 ms, sans nouveau pipeline, maximum d’image 516 ms (P4:2857–2889,3103–3163). Les torches qui clignotent restent un symptôme visuel rapporté, sans cause établie par ces compteurs. Async textures est actif ; les shaders restent en mode Legacy, single-threaded.

## NeoSwap et comparabilité

D5 n’observe que la fin d’AC. Entre deux snapshots du même processus, les compteurs augmentent de **18 premiers mappings, 1 179 648 octets et 197 209 ns de temps de mapping**, avec zéro échec de mapping (D5:1,1061). Les créations directes restent 2 210 ; les 18 demandes nouvelles rencontrent le budget de mapping direct (D5:200,1062). L’augmentation de 204 de `swap_failures` appartient au compteur cumulatif des tentatives d’allocation client échouées : elle ne représente pas 204 échecs de mapping invité.

Cette portion conserve deux donneurs, zéro donneur perdu, 90 718 208 octets partagés RPC et 795 objets relayés/83 034 112 octets. L’ancienne portion AC avait zéro donneur. Les deux portions rapportent `thermal=2`, sans couvrir l’historique thermique de BO2 ou GoW3. Un gain attribuable à NeoSwap entre ces captures n’est donc pas établi.

L’ancien export de performance commence après BO2 ; il ne fournit aucune fenêtre FPS BO2 comparable. GoW3 passe d’un démarrage neuf à une restauration avec des volumes de dessin différents. Les parcours AC, la nouveauté des caches et l’état de NeoSwap diffèrent. Les valeurs anciennes, notamment 10,477 images/s dans la phase GoW3 lourde de 588, sont conservées pour contextualiser le coût ; elles ne constituent pas un A/B prouvant un gain de 593.

Les agrégats `spu_build` incluent les lectures de cache ; les temps des opérations de pipeline peuvent se chevaucher avec l’activité invitée ; les temps d’attente de présentation peuvent inclure ces mêmes saccades. Aucun de ces totaux ne se convertit directement en FPS récupérables. Les percentiles de fenêtres ne sont pas moyennés. Les messages supprimés par le budget de log au démarrage d’AC sont aussi signalés dans le JSON : l’absence d’une erreur dans cet export n’est pas une preuve exhaustive d’absence d’erreur.

## Preuve d’identité du correctif JIT suivant

[codegen-identity.json](codegen-identity.json) conserve le résultat de CMake 3.31.10 : **PPU `a987639e9f838d1c`, SPU `d070cb361bdef607`**, identiques à la baseline 593. Les 40 entrées directement disponibles sont authentifiées ; le digest du backend LLVM inchangé est réutilisé avec son pin et son patch. Seuls trois corps I/O de `JITLLVM.cpp` changent ; restaurer ces corps reconstitue exactement le fichier livré. Les 14 cas d’alias candidat, dont 10 négatifs, passent ; une édition future et un mauvais chemin ne bénéficient pas de l’alias.

Le script reproductible est `test/rpcs3_codegen_593_identity_test.py`. Ses octets restent identiques au script exécuté ; aucun chemin de travail fixe ni ancien arbre Git CELL538 n’est requis. Il prend `--source`, `--baseline`, `--baseline-manifest`, `--upstream-metadata`, `--repo`, `--cmake`, `--output` et, facultativement, `--work-dir`. Aucun Core n’est compilé par ce contrôle. Les chemins d’exécution du reçu publié sont remplacés par des rôles ; les résultats et leurs empreintes restent inchangés.
