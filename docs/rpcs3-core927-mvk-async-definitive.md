# RPCS3 Core 927 — soumissions asynchrones MoltenVK : fonction rendue définitive, pour tous les jeux

Consigne du mainteneur (11 novembre 2026) : « Pas de protection et le but c'est de faire fonctionner les soumissions
asynchrones », après expertise approfondie, « appliqué à chaque jeu le nécessitant ».

Core 927 = Core 926 (deux leviers FPS de Black Ops II, compilé vert par le run 42935666936, non épinglé) + ce document.
**Aucune mesure iPhone n'a encore été faite avec ce Core : tout ce qui suit vient des journaux d'appareils des builds
640 à 724, de la lecture du code et de tests sur ordinateur.**

## 1. Ce que fait la fonction, et ce qu'elle coûte quand elle est absente

Avec des soumissions synchrones, `vkQueueSubmit` encode les commandes Metal du tampon sur le fil qui l'appelle : le fil
RSX. Avec des soumissions asynchrones, MoltenVK met la soumission en file et l'encode sur son propre fil.

| Jeu | Synchrone (fil RSX) | Asynchrone (fil RSX) | Source |
|---|---|---|---|
| Black Ops II | 462-606 ms par fenêtre de 5 s, 3,5 à 4,8 ms par image | 7,5-8,3 ms par fenêtre, 0,05 ms par image | builds 694/723/724, et 643 à 662 |
| Assassin's Creed | 0,93-1,36 s par fenêtre | 15 ms par fenêtre | builds 601 et 624 |
| God of War III | 490-640 ms par fenêtre, environ 5 ms par image | (pas de session asynchrone dans les journaux conservés) | build 583 |

Black Ops II est calé sur le balayage à 60 Hz : 52 % de ses images prennent deux balayages (build 724). Les 3,5 à 4,8 ms
rendues au fil RSX sont l'objectif de 3 ms fixé par le mainteneur ; le gain en images par seconde reste à mesurer sur
l'iPhone.

## 2. Pourquoi elle ne tournait plus : le blocage ne mesurait pas une panne

Les Cores 587 à 926 tenaient un fichier par jeu : un démarrage asynchrone qui se terminait avant 900 images présentées
ou sans arrêt propre du moteur de rendu marquait le jeu « échoué », définitivement. Le réglage « Enabled » ne passait pas
outre.

Dépouillement de tous les journaux (privés, non versés au dépôt) :

- 16 sessions asynchrones, 9 processus, builds 640 à 694 : 9 d'Assassin's Creed (57 118 présentations), 7 de Black Ops II
  (19 030 présentations). **0 acquisition en dépassement de délai, file d'encodage identifiée à chaque fois**, retard
  maximal d'un marqueur 88,7 ms.
- À partir du build 676, tout démarrage de Black Ops II est `canary=failed_before` ; God of War III de même (builds 694 à
  724). Le marquage vient d'un démarrage interrompu avant 900 images (les démarrages du build 662 étaient ceux des arrêts
  de 9 à 40 s sur PUTLLC, corrigés depuis par les Cores 664 et 924), jamais d'une panne des soumissions.

Le fichier de blocage est supprimé : plus rien ne s'interpose entre le réglage et MoltenVK.

## 3. Expertise : ce qui change réellement quand l'encodage a lieu plus tard

Deux relectures indépendantes (l'arbre MoltenVK que le Core lie, db660224 ; le moteur de rendu Vulkan de RPCS3), puis une
relecture du correctif. Constat d'ensemble : RPCS3 ne libère ni ne réutilise aucun objet avant le signal de la barrière
(« fence ») de sa soumission — textures périmées (921), mémoire dédiée (925), tampons de commandes, tas : tout passe par la
destruction différée. Les points qui dépendent de l'instant d'encodage sont les suivants.

| # | Constat (preuve) | Conséquence | Correction 927 |
|---|---|---|---|
| 1 | L'attente du dernier « present » avant une acquisition d'image **abandonnait après 2 s** (`IOSMoltenVKExecQueue.h`). Or le compteur des sémaphores MoltenVK avance quand la soumission qui attend est encodée, alors que l'acquisition le lit sur le fil appelant (`MVKSemaphoreMTLEvent`, MVKSync.mm:121-135). | Une acquisition qui double la file redonne le même jeton : le GPU attend une valeur que personne ne signale ; et le défaut d'origine du build 551 (image libérée sous le « present ») revient. Cas concret : file bloquée plus de 2 s (application suspendue puis reprise). | L'attente n'est plus jamais abandonnée ; chaque tranche de 2 s est comptée (`acquire_timeouts`). C'est ce que fait déjà le mode synchrone, où le fil encode lui-même. |
| 2 | MoltenVK ne marque une requête d'occlusion « écrite par le GPU » qu'à l'encodage de sa fin (`MVKQueryPool::endQuery`). Avant, `vkGetQueryPoolResults(WAIT)` rend `VK_NOT_READY` immédiatement. | La lecture ZCULL bloquante **tournait à vide** sur le fil RSX pendant tout l'encodage (un cœur occupé à ne rien faire, face au fil qui encode). Le résultat restait exact : les réserves de requêtes ne sont jamais réutilisées. | Chaque soumission de la file de présentation reçoit un marqueur, sa barrière en garde le ticket ; la lecture ZCULL **dort** jusqu'à l'encodage de son tampon, puis l'attente de MoltenVK bloque normalement. |
| 3 | Même cause pour `vk::wait_for_fence` : ses 100 µs d'attente active étaient consommés avant que les commandes existent. | Attente active inutile à chaque synchronisation dure. | L'attente dort jusqu'à l'encodage (même ticket), puis tourne et bloque comme avant. Une attente avec délai garde son délai. |
| 4 | Journal du build 650 (Assassin's Creed, PID 8767, asynchrone) : `Device lost` levé à 1793814730,525, `HOST_STATE app=background` à ,555. iOS refuse tout tampon Metal soumis en arrière-plan ; MoltenVK déclare alors le périphérique perdu, même avec `RESUME_LOST_DEVICE` (`MVKQueue::handleMTLCommandBufferError`). C'est **la seule perte de périphérique de tous les journaux**. | Le jeu meurt quand on quitte l'application un instant. L'asynchrone élargit la fenêtre : le travail en file est soumis après la bascule. | Le Core écoute lui-même l'application : à l'entrée en arrière-plan il ferme un verrou (soumissions, présentations, acquisitions et attentes du périphérique patientent), attend les appels en cours (500 ms au plus) puis la fin du travail en file (1 s au plus), et rouvre quand l'application redevient active. Rien n'est supprimé ni réordonné. |
| 5 | Le « streaming asynchrone des textures » ordonne deux files par des événements et sémaphores dont MoltenVK avance les compteurs à l'encodage ; en asynchrone chaque file encode sur son fil. | Ordre entre files non garanti si les deux leviers sont actifs. | Les deux ne sont pas combinés : en Automatic, une configuration qui active ce streaming garde des soumissions synchrones ; avec « Enabled », les textures sont envoyées par le fil RSX (ligne de journal). Le streaming est désactivé par défaut sur iOS et n'est plus repris de la base RPCS3 (c2519a25). |

Points vérifiés et sains : destruction différée après barrière, attente du périphérique avant toute reconstruction ou
destruction de la chaîne d'images (MoltenVK y attend sa file), transfert MetalFX déjà ordonné par un vidage de file,
sémaphores par image protégés par l'attente du point 1, réserves de requêtes non réutilisées.

## 4. Règle définitive

- **Automatic = tous les jeux** (sauf configuration avec streaming asynchrone des textures, point 5).
- **Enabled** = actif. **Disabled** = synchrone. Aucun fichier, aucun compteur de démarrages, aucun jeu en liste.
- Ligne de journal : `Resolved title policy 927: mvk_async=… rule=… texture_streaming=… boot_record=none`.

## 5. Mesures que le Core rapporte

- `COREPROF OPT587` : `mvk_async`, `boot_record=none`, `submits_marked`, `fence_encode_waits` et `query_encode_waits`
  (nombre : total ms : plus longue), `acquire_timeouts`, `encode_wait_timeouts`.
- `COREPROF GPUGATE927` (écrite dès que l'application est passée en arrière-plan) : bascules, appels mis en attente et
  durée, appels passés parce que le jeu s'arrêtait, bascules sans retour des appels en cours, attentes de fin de file.
- Lecture à faire sur l'iPhone : `RSXSYNC551 submit` par image (attendu autour de 0,05 ms pour Black Ops II), la part des
  images à un seul balayage, `zcull_wait` par image.

## 6. Tests (ordinateur)

`test/rpcs3_mvk_async927_test.py` : contrôle du source, puis exécution du **vrai** registre de la file d'encodage, de ses
tickets et du **vrai** verrou, contre des modèles des règles de MoltenVK et d'iOS, avec l'ancienne règle comme témoin
(g++ : normal, ASan/UBSan, TSan ; clang : normal) :

| Scénario | Ancienne règle | Core 927 |
|---|---|---|
| Sémaphores : 6 images, premier tampon long à encoder | 4 attentes GPU jamais signalées | 0 |
| Lecture ZCULL avant encodage | environ 270 000 retours `VK_NOT_READY` (attente active) | 0, même résultat |
| Présentation dont l'encodage dépasse 2 s | acquisition lancée par-dessus | attendue jusqu'au bout, 1 dépassement compté |
| Soumissions synchrones pendant la bascule en arrière-plan | environ 200 refusées | 0, appels repris au retour, aucun perdu |
| 30 soumissions en file à la bascule | 30 refusées | 0 (file vidée avant la fin de la bascule) |

Sur macOS (lot Apple du Core), le même test tourne sur la vraie bibliothèque libdispatch. `test/rpcs3_core927_test.py`
enchaîne les incréments 901 à 927 et les tests de chacun ; `test/rpcs3_core927_codegen_test.py` vérifie que les identités
du code généré ne changent pas (caches PPU/SPU conservés) ; `test/rpcs3_core_marker_rule927_test.py` couvre la règle de
marqueurs du vérificateur de livraison (les marqueurs du blocage sont exigés jusqu'au Core 926, refusés ensuite).

## 7. Core 926 (replié dans ce Core)

- Black Ops II : les réutilisations du mémo de recherche de textures sont maintenant servies (4 676 476 réutilisations
  vérifiées sur les builds 662 à 724, 0 différence), avec la vérification par échantillonnage des jeux servis.
- La « seconde chance » du fichier de blocage (926) est remplacée par sa suppression (927).
- Les insertions du Core 925 ont été déplacées pour que chaque incrément récent se retire seul.

## 8. Bilan selon la grille de la mission

- **Coût supprimé (attendu, non mesuré)** : 3,5 à 4,8 ms d'encodage Metal par image de Black Ops II sur le fil RSX ;
  0,93-1,36 s par fenêtre pour Assassin's Creed, 490-640 ms pour God of War III ; l'attente active des lectures ZCULL et
  des barrières pendant l'encodage.
- **Coût restant** : l'encodage lui-même, déplacé sur un autre fil (même travail au total) ; l'attente ZCULL du GPU
  (environ 3 ms par image pour Black Ops II) ; le stationnement des fils PPU à chaque PUTLLC exact.
- **Chemin critique** : fil RSX (soumission, acquisition, lecture ZCULL), fil d'encodage de MoltenVK.
- **Mémoire** : aucune allocation nouvelle par image ; une barrière temporaire par file à chaque passage en arrière-plan.
- **Risques** : (a) un jeu jamais essayé en asynchrone peut révéler un défaut propre à MoltenVK — le réglage par jeu
  « Disabled » rend le mode synchrone ; (b) dès que l'application est en arrière-plan, et jusqu'à ce qu'elle redevienne active, le rendu attend
  (comportement voulu ; avant, le processus continuait à soumettre jusqu'à sa suspension) ; (c) si une file reste bloquée, le fil RSX
  attend au lieu de continuer : c'est le comportement du mode synchrone, signalé par `acquire_timeouts` ; (d) iOS accepte
  le travail GPU jusqu'au retour de la bascule vers l'arrière-plan (règle documentée par Apple) : c'est ce qui autorise le
  dernier vidage ; à confirmer par `COREPROF GPUGATE927` et l'absence de `Device lost` sur l'appareil.

## 9. À vérifier sur l'iPhone (prochaine IPA, à la demande du mainteneur)

1. Black Ops II, God of War III, Assassin's Creed : `mvk_async=1` dès le premier démarrage, sans réglage.
2. Quitter l'application quelques secondes en pleine partie et revenir : le jeu reprend, pas de `Device lost`.
3. `RSXSYNC551 submit` par image et répartition des images à un ou deux balayages pour Black Ops II.
