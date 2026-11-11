# RPCS3 Core 933 — profil local par jeu et première décision apprise

Demande du mainteneur (chantier urgent du 11 novembre 2026, transmis par Codex, priorité 3) : relier l'identité du jeu, la base
RPCS3, les corrections iOS et le comportement observé, et **garder pour les lancements suivants les décisions validées pour un
jeu sur cet appareil**, en partageant une correction par mécanisme plutôt que par liste de titres.

**Niveau de preuve.** Écrit et testé sur hôte (Linux, g++, ASan/UBSan). **Compilé pour iOS** par la CI : source `cab3606b`,
demande `bbef3768`, run `43077626247`, travail iPhone vert. Artefact `13884331357` (zip `98a5f3a8…`, 30 567 592 octets),
bibliothèque `fb1d3f0f…`, 81 096 000 octets, identité `rpcs3-ios-core933`, ABI 30. Le binaire contient
`Resolved title policy 933`, `COREPROF LOCALPROFILE933`, l'en-tête `rewindbox-local-profile 1` et le chemin `local_profiles/`.
Rien n'a été exécuté sur un iPhone ; aucun gain d'images par seconde, d'énergie ou de mémoire n'est annoncé.

Moteur : branche `core933-resolver` (base Core 932 `94354ea`), commits :
- `c798c82`, le profil et la règle ;
- `42869e2`, la ligne de démarrage placée à côté de la décision. La fin de la politique de titre reste telle que le Core 921
  l'a écrite, et son incrément s'inverse toujours sur la source. Le pilote l'avait détecté ; le test 933 le contrôle désormais
  en quelques secondes ;
- `c9432d3`, les corrections de la revue indépendante (§ 3).

Canonique `03b63d88` (474 fichiers), delta `bb99b13f`, build 933.

## 1. Profil local (`REWINDBOX_LOCAL_PROFILE_933`)

- **Symptôme.** Une décision prise pendant une partie (un levier utile pour ce jeu) se perd à la fermeture : chaque lancement
  repart de la liste de titres du Core, figée à la compilation.
- **Mécanisme.** Le Core ne gardait aucune mémoire par jeu en dehors des réglages de l'utilisateur et des caches.
- **Correction.**
  - Fichier `config/local_profiles/<numéro>.txt`, à côté de `config.yml`, propre à l'appareil.
  - Clé : numéro du jeu et version du jeu (`APP_VER`, qu'une mise à jour change). Un profil d'une autre version est ignoré
    puis remplacé.
  - Borné à 4 Kio, décisions et valeurs fermées. Une ligne inconnue (Core plus récent) est sautée et comptée.
  - Écrit en entier et de façon atomique (`fs::pending_file`), seulement quand une décision est apprise, retirée ou validée
    (trois premières fois), depuis le fil des rapports.
  - Lu par `Emulator::Load` juste avant la politique de titre. Un fichier coupé, illisible ou trop gros est ignoré ; le démarrage
    continue toujours.
  - Ligne de démarrage `Resolved title policy 933` : état du profil, version, valeur et **origine** du levier
    (`setting_enabled`, `setting_disabled`, `title_list`, `learned`, `withdrawn`, `none`).
- **Vérification exécutée.** Harnais hôte (511 contrôles après la revue) : format, lecture stricte, et sept démarrages successifs d'un même
  titre à travers le vrai code du magasin, sur un répertoire temporaire.
- **Limite.** Le profil vit sur l'appareil : rien n'est partagé entre appareils ni envoyé.

## 2. Première décision apprise : lecture anticipée des objets SPU (`REWINDBOX_LEARNED_PREFETCH_933`)

- **Symptôme.** Pendant le jeu, les fils de compilation SPU ouvrent des milliers de petits fichiers d'objets en cache : à-coups.
  - Black Ops II : 4,3 s sur une fenêtre de 5 s pour 7 162 objets (Build 614).
  - Assassin's Creed : 4 000 objets la première minute, 0,4 à 0,7 ms chacun.
  - Journaux privés des Builds 643 à 694 : d'autres sessions de jeu montrent le même coût, par exemple 1 674 lectures en
    628 ms dans une fenêtre de 5 s, à 0,38 ms chacune, donc lues sur disque.
- **Mécanisme.** La lecture anticipée du Core 616 (déjà validée : 0,02 ms par objet servi depuis la mémoire) n'était activée
  que pour deux listes de titres, BO2 et AC.
- **Correction.** En mode Automatique seulement, pour un titre hors de la liste :
  - **apprendre** : une fenêtre où la lecture anticipée est éteinte et où les fils de compilation ont passé au moins 500 ms à lire
    au moins 200 objets SPU, dont au moins la moitié pour des compilations de jeu et non du préchauffage au démarrage ;
  - **appliquer** : au lancement suivant seulement, jamais en cours de partie ;
  - **valider** : 500 objets servis depuis la mémoire pendant un lancement (le fichier n'est réécrit qu'aux trois premières
    validations) ;
  - **retirer** : après deux minutes de jeu (fenêtres avec images seulement : une pause ou l'arrière-plan ne comptent pas) avec
    moins de 1 % des objets prévus servis, c'est-à-dire de la mémoire tenue pour rien. Une décision retirée le reste pour cette
    version du jeu.
  - Le réglage de l'utilisateur, global ou par jeu (Activé ou Désactivé), passe toujours avant.
  - Ligne `COREPROF LOCALPROFILE933` à chaque décision (apprise, validée, retirée), avec la preuve et `saved=`.
- **Pourquoi c'est sûr.** Mêmes octets, même validation, même liaison que la lecture sur disque : le code du jeu ne change pas.
  La mémoire tenue est bornée par le Core 616 (48 Mio) et rendue quand l'émulation s'arrête ; le retrait la reprend si elle ne
  sert pas.
- **Ce qui ne déclenche pas.** God of War III, Build 694 : 1 810 objets en 1,85 s, mais pendant le préchauffage du démarrage
  (aucune compilation de jeu dans ces fenêtres). La lecture anticipée ne raccourcirait pas cette attente.
- **Vérification exécutée.**
  - 511 contrôles avec ASan/UBSan (après la revue, § 3), dont : seuils (199 objets, 499 ms, préchauffage), lecture anticipée
    déjà active, titre de la liste, version différente, fichier abîmé ou trop gros, écriture en échec (l'ancien fichier reste
    entier), fenêtres héritées du lancement précédent, plafond des validations.
  - 17 mutants détectés :
    - 11 par le harnais : préchauffage appris, pause comptée, apprentissage pendant la lecture anticipée, décision retirée
      réapprise, autre version acceptée, fichier coupé lu, numéro invalide, écriture ratée déclarée réussie, fenêtre du
      lancement précédent utilisée, validation réécrite à chaque fois, titre sans version doté d'un profil ;
    - 6 par le contrat de source : levier appris malgré un réglage de l'utilisateur, profil lu après la politique, compteurs
      de lecture, de compilations de jeu ou de session non transmis, règle nourrie avant la lecture de la fenêtre.
  - Les incréments que leurs tests inversent directement sur l'arbre final (905, 906, 921, 924, 929, 930) s'inversent encore.
- **Limite.** Les seuils viennent des journaux d'appareil des Builds 614 à 694 ; leur effet sur iPhone n'est pas mesuré.

## 3. Revue indépendante

Une revue indépendante (domaines : concurrence, sens des compteurs, ordre du démarrage, chemins, analyse du fichier, formats)
n'a trouvé ni course ni plantage. Trois défauts corrigés, un risque documenté :

| Constat | Mécanisme | Correction | Vérification |
|---|---|---|---|
| F1 : un jeu lancé moins de 5 s après un autre peut hériter de sa fin de session (apprendre ou valider à tort) | le rapporteur ouvre sa session à la création de la fenêtre de rendu, après la politique de titre ; les compteurs JIT et ceux de la lecture anticipée ne sont vidés que par le rapport | la première fenêtre de chaque session, et toute fenêtre rapportée avant elle, ne sont pas utilisées | cas du harnais : fenêtre de l'ancienne session puis première fenêtre lourdes, sans effet ; mutant détecté |
| F2 : chaque démarrage qui valide réécrivait le fichier | `validated++` à chaque validation | écriture aux trois premières validations seulement | cas du harnais ; mutant détecté |
| F3 : un titre sans `APP_VER` ni `VERSION` (« Unknown ») avait une clé permanente | `valid_version` acceptait « Unknown » | une version doit contenir un chiffre, sinon aucun profil | cas du harnais ; mutant détecté |
| F4 : sans cache SPU, la décision apprise ne se valide ni ne se retire | rien n'est prévu, donc rien n'est servi | documenté : aucune mémoire tenue, aucun coût | — |

Après corrections : 511 contrôles et 17 mutants détectés (8 + 3 par le harnais, 6 par le contrat de source, dont la session
non transmise).

## 4. Rapprochement avec l'audit

| Point de l'audit | Avant | Core 933 |
|---|---|---|
| décisions validées gardées pour les lancements suivants | aucune mémoire par jeu | profil local par numéro et version (§ 1) |
| corrections partagées par mécanisme et compatibilité | listes de titres | lecture anticipée apprise pour tout titre qui montre le coût (§ 2) |
| attribution des compilations (démarrage / jeu, connu / nouveau) | déjà présente : SPUPROF `loading_*` / `gameplay_*`, SHADERPIPE543 `vs_cached` / `vs_compiled` | réutilisée comme preuve de la règle |
| origine de chaque valeur | absente pour les leviers | ligne 933 pour la lecture anticipée ; à étendre |

## 5. Reste à faire

- Étendre l'origine à tous les leviers, puis faire porter au Core la couche « corrections RewindBox » encore résolue côté Dart
  (`_serialOverrides`).
- Mémoire et rechargement (priorité 5), en repartant des mesures du Core 925+.

## 6. Protocole iPhone

Un titre hors liste avec beaucoup d'objets SPU (cache chaud), deux lancements de suite :
- 1er lancement : chercher `COREPROF LOCALPROFILE933 ... verdict=learned` et `saved=1` ;
- 2e lancement : `Resolved title policy 933: ... spu_object_prefetch=1 source=learned`, puis `SPUPREFETCH616 hits=` et
  `JITPROF spu_cache_read` en baisse sur les mêmes scènes ;
- aucun changement attendu pour BO2 et AC (`source=title_list`).

Un gain n'est attribué qu'après répétition, à conditions égales.
