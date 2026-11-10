# Durée des livraisons privées et contrat source calculé une fois

27 octobre 2026. Mesures prises sur les runs réels ; le gain du nouveau
mécanisme n'est pas encore mesuré sur CI.

## 1. Où passe le temps

**Livraison 563** (build Xcode complet, run `40501404250`) : 40 min de bout
en bout, car le job macOS (32,6 min) ne démarre qu'après `checks` (7,6 min).

| Poste du job macOS | Durée |
|---|---:|
| Re-preuve de builds antérieurs (appels du module de livraison) | 9,9 min |
| Compilation Xcode | 8,3 min |
| Environnement (Xcode, Flutter, hôte, pin) | 5,2 min |
| Empaquetage, scellement, validateurs | 4,5 min |
| Attente du Core | 2,0 min |
| Intégration et téléchargements | 2,0 min |

**Livraison 561** (« Core seul », sans Xcode) : job macOS de 21,0 min.
**Run Core** : ~15 min, dont 12 min de compilation.

**La cause principale.** Chaque appel du module de livraison commence par le
contrat source complet : le pin du build, son contrat parent, puis toute la
chaîne des recettes antérieures dans leurs vues emboîtées. Sur macOS, cela
prend ~2 min, et le job l'appelle 6 fois (étapes « Record exact build
environment », « Wait for the exact source-built… Core », « Require
successful exact MeloNX engine… », « Download the exact source-built
MeloNX… », « Bind the downloaded 558 engine… », « Execute the actual
Foundation logger… »). Le travail propre de ces étapes prend quelques
secondes. Le même contrat est donc recalculé à l'identique ~12 min par
livraison.

## 2. Le contrat calculé une fois (`build-utils/delivery_contract_memo.py`)

Le premier appel d'un job calcule le contrat et l'enregistre avec une clé.
Un appel suivant du même job ne réutilise le rapport que si la clé est
identique :
- le commit et l'arbre de l'index en usage ;
- **tous les fichiers suivis tels qu'ils sont dans l'arbre de travail** (copie
  de travail de l'index, rafraîchie), ce qui couvre chaque fichier suivi que
  le contrat ouvre et chaque `git diff` contre l'arbre de travail ;
- chaque fichier non suivi que le contrat a ouvert, chaque dossier listé et
  chaque motif `glob` (relevés par un hook d'audit Python), et les chemins non
  suivis dont le contrat teste l'existence, déclarés par l'appelant
  (`INSTALLED`, seul cas de la chaîne actuelle) ;
- l'environnement vérifié (`BUILD_NUMBER`, `GITHUB_SHA`, `GITHUB_REF_NAME`,
  `GIT_INDEX_FILE`), la version de Python et la plateforme.

**Règles.**
- Toute différence recalcule le contrat, et la raison est affichée (fichiers
  suivis modifiés, fichiers non suivis, environnement…).
- Un contrat qui échoue, ou qui laisse la copie de travail modifiée, n'est
  jamais enregistré.
- L'enregistrement vit dans `build/source-contract-memo/`, qu'aucune étape ne
  téléverse : un autre job ou une autre machine ne le réutilise jamais.
- Aucun contrôle n'est retiré : le rapport réutilisé est celui que le même job
  a calculé sur les mêmes octets.

**Utilisation** dans le `main()` du module de livraison d'un build :

```python
import delivery_contract_memo as memo  # build-utils sur sys.path
report = memo.reuse(BUILD, source_contract, declared=[INSTALLED])
```

Le module d'arbre du build doit lister `build-utils/delivery_contract_memo.py`
dans sa recette, sinon le pin le retire.

**Gain attendu.** Des étapes de build modifient sur place des fichiers suivis
entre deux appels (« Generate iOS host », « Configure release host »).
Après elles, la clé change et le contrat est recalculé une fois. Le gain se
situe donc entre ~6 et ~10 min sur le job macOS, sur ~12 min de calcul
répété. Le premier run réel l'affichera étape par étape.

## 3. Validation hors CI

- `test/delivery_contract_memo_test.py`, sur un dépôt jetable :
  - un second appel sans changement réutilise le rapport ;
  - sept sortes de changement le recalculent : fichier suivi, fichier non
    suivi ouvert, dossier listé, existence déclarée, environnement, index,
    commit ;
  - un contrat qui échoue n'est pas enregistré, ni un contrat qui modifie la
    copie de travail ;
  - l'index en usage n'est jamais modifié.
- **Chaîne réelle** : le contrat source 563 complet, appelé deux fois dans une
  copie épinglée de `0bf5854a`. Résultat consigné au § 4.

## 4. Mesure sur la chaîne réelle

Contrat source 563 complet, dans une copie épinglée de `0bf5854a`, sur ce
conteneur Linux (pas sur le runner macOS) :
- **premier appel : 53 s** (calcul complet) ; **appels suivants : 0,1 s**
  (réutilisation), avec le même rapport ;
- la copie de travail reste égale à l'index épinglé ;
- un fichier épinglé modifié (`rpcs3cell563_core.py`) force le recalcul, qui
  échoue sur ce fichier, et rien n'est enregistré ;
- le premier essai a montré qu'il fallait écarter les caches de bytecode
  (`__pycache__`), que les imports et les vues créent et suppriment. Ils
  dérivent des sources suivies, déjà couvertes par la clé.

Le gain réel sur CI sera lu dans le premier run qui l'utilise : chaque étape
affiche « reused » ou « recomputed » avec la raison.

## 5. Livraison 718 : durées mesurées, cause du retard et correctif (10 novembre 2026)

Mesures lues dans les horodatages des jobs et étapes de l'API Actions, les reçus `validation.json` des
groupes et les journaux `xcodebuild` des XCTests ; aucune estimation. Comparables : 694 (run
`42506743712`, dernier succès), 718 tentative 1 (run `42741950414`, échec du groupe natif) et 718
relance (run `42747501121`, succès, recette corrigée `6ad78af6`). Les livraisons 653, 662 et 688 ont
duré 20,1 à 21,0 min : la recette standard n'avait pas ralenti avant 718.

| Poste | 694 | 718 tentative 1 | 718 relance |
|---|---:|---:|---:|
| Bout en bout (création du run → fin du dernier job) | 20 min 39 s | 22 min 40 s (échec, sans empaquetage) | 22 min 38 s |
| Preflight (dont contrat de livraison) | 52 s (25 s) | 55 s (27 s) | 55 s (27 s) |
| File d'attente des runners après preflight | 3 s | natif 3 s, application 3 min 33 s | 3 s |
| Job Flutter (19 commandes) | 8 min 08 s | 7 min 40 s | réutilisé (preuve de la tentative 1) |
| Job natif | 15 min 23 s | 21 min 18 s | 13 min 56 s |
| – préparation (checkout → précache, simulateur) | 1 min 35 s | 2 min 20 s | 5 min 38 s (Flutter 3 min 48 s) |
| – étape de tests | 13 min 18 s | 18 min 34 s | 7 min 45 s |
| – somme des commandes | 787 s (18) | 1095 s (21) | 435 s (19) |
| – XCTest traduction / session centrale | 166 s / 398 s | 261 s / 521 s | 97 s / 55 s |
| – dont phase « Testing started » (lancement + tests) | 110 s / 278 s | 198 s / 400 s | 46 s / 20 s |
| Republication des composants (parallèle) | 1 min 08 s | 1 min 24 s | 1 min 17 s |
| Application : préparation avant Xcode | 5 min 49 s | 4 min 54 s | 6 min 54 s |
| Compilation Release Xcode 26.3 | 6 min 31 s | 5 min 48 s | 7 min 18 s |
| Intégration avant l'attente des tests | 41 s | 41 s | 56 s |
| Attente et authentification des tests | 2 min 41 s | 6 min 39 s (échec) | 11 s |
| Identité, empaquetage, scellement, validateurs, chiffrement, envoi | 4 min 00 s | non atteint | 6 min 20 s |
| Téléchargement des 4 pièces / vérification locale de l'IPA | non mesuré | — | 3 s / 47 s |

**Temps hors du run de livraison.** Producteurs des Cores consommés sans recompilation : run du
Core RPCS3 914 `42736141716` 18,9 min, run du Core MeloNX 717 `42728675479` 44,6 min. Dans la
livraison, ils coûtent un téléchargement authentifié (RPCS3 12 s + installation et ABI 13 s ; MeloNX
10 s + preuves 21 s).

**Cause de l'échec de la tentative 1.** 20 des 21 commandes natives réussies ;
`pocket-skin-input-chain` s'arrête sur `No module named 'PIL'` (0,45 s). La recette avait ajouté au
groupe natif la commande que le groupe Flutter exécute déjà avec le Pillow épinglé, sur le même arbre
(réussie là, 124 s). L'application avait compilé le binaire Release et s'est arrêtée à l'attente des
tests, par conséquence.

**Cause du retard du job natif (le chemin critique de 694 et de 718).** Les 20 commandes communes ont
tourné 1,3 à 1,9 fois plus lentement en 718 (runner plus lent) et les trois ajouts ont pesé 16 s. Le
poste dominant n'était ni Xcode ni un calcul répété : le XCTest de traduction laissait `xcodebuild`
démarrer le simulateur puis l'éteindre à la fin (reçu de la session centrale : « Shutdown »). Le XCTest
de la session centrale le redémarrait alors et attendait 278 s (694) et 400 s (718) dans sa phase de
test pour 4 à 5 s de tests réels. Les XCTests Dolphin et ARMSX2, lancés sur l'appareil déjà démarré,
attendaient 7 à 15 s.

**Correctifs (`6ad78af6`, recette seule, après gel, sans changement produit).**
- Le job natif démarre une fois, en arrière-plan, l'appareil que choisit chaque XCTest (premier iPhone
  disponible du runtime iOS du SDK), avant l'installation de Flutter, et l'attend juste avant le groupe.
  Mesuré dans la relance : démarrage 1 min 17 s (migration de données comprise), appareil « Booted »
  dans le reçu central, phases « Testing started » 46 s et 20 s.
- Le doublon natif de `pocket-skin-input-chain` est retiré ; le test reste exécuté dans le groupe
  Flutter. Garde du contrat : aucune commande native fraîche n'importe PIL (contrôle négatif : la
  recette de la tentative 1).
- `rpcs3-timeline-616-foundation` est retiré : même argv que `rpcs3-timeline-613-foundation`
  (`test/rpcs3_diagnostics546_native_test.py`), journaux identiques octet pour octet en 694 et 718.
  `expand_commands` refuse désormais un argv identique dans un groupe (contrôles négatifs : recettes
  694 et 718).
- Le groupe Flutter de la relance réutilise la preuve réussie de la tentative 1 (même arbre effectif
  `af020701`, mêmes commandes, 4 lectures de recette inchangées ; garde de réutilisation et reçu
  vérifiés localement puis par la CI). Le contrat de livraison est rejoué en entier (59 tests).

**Gains mesurés.**
- Étape de tests natifs : 18 min 34 s → 7 min 45 s (−10 min 49 s face à la tentative 1 ; −5 min 33 s
  face à 694).
- Job natif : 21 min 18 s → 13 min 56 s (−7 min 22 s ; −1 min 27 s face à 694), malgré +3 min 18 s de
  préparation.
- Attente des tests sur le chemin critique de l'application : 6 min 39 s → 11 s (−6 min 28 s) ;
  2 min 41 s dans 694 (−2 min 30 s).
- Job Flutter : 7 min 40 s de runner évitées (réutilisation), hors du chemin critique.

**Ce que la mesure ne montre pas.** Le bout en bout de la relance (22 min 38 s) n'est pas inférieur à
694 (20 min 39 s) : le chemin critique est maintenant le job application, et son runner a été plus
lent sur les mêmes étapes (préparation +1 min 05 s, Xcode +47 s, intégration +15 s, fin d'empaquetage
+2 min 20 s, soit +4 min 27 s), ce qui a absorbé les 2 min 30 s d'attente supprimées. Avec un runner
natif aussi lent que celui de la tentative 1, l'application aurait attendu les tests ; elle ne les
attend plus que pour authentifier leurs preuves. La cible de moins de 40 min est tenue (22 min 38 s),
sans garantie : la file d'attente macOS (3 min 33 s en 718-1) et la vitesse des runners restent hors
de la recette.

**Incompressible ou non traité.** Le job application, qui compile toujours l'application et ses deux
ponts modifiés, puis intègre, scelle, valide et chiffre (17 à 21 min selon le runner, attente
exclue) ; le contrat de livraison (27 s) ; la file d'attente des runners. Observé et non prouvé :
pendant le démarrage du simulateur, le téléchargement du cache Flutter de 2,2 Go (succès de cache) est
tombé d'environ 50 Mo/s à 3–10 Mo/s (3 min 48 s contre 42 s et 1 min 18 s). Démarrer l'appareil après
la restauration du cache libérerait environ 2 à 3 min sur le job natif. Le job natif n'étant plus sur
le chemin critique, ce changement n'est pas fait sans mesure.

**Point 4 de la demande (mémo du contrat et recalculs).** Dans 718, le contrat source est calculé une
fois par job (application : étape « baseline », 9 s ; une réutilisation enregistrée « reused,
computed earlier in this job on the same bytes », aucun recalcul ni invalidation ; natif : un calcul
dans le groupe). Les 9,9 min de preuves répétées du build 563 (§ 1) n'existent plus depuis la recette
standard ; elles ne sont pas la cause de 718. Chaque composant est téléchargé une fois par job qui en a
besoin : la republication refait ces téléchargements sur son propre runner, en parallèle (1 min 17 s),
pour garder les archives. Les caches (SDK Flutter et pub par version et verrou, StikJIT par empreinte
exacte de ses entrées et run producteur, puis installation vérifiée) gardent des clés exactes ; aucune
présence de fichier ne remplace une preuve. Application, natif et republication démarrent ensemble
après le preflight ; l'application n'attend les tests qu'avant d'intégrer leur identité.
