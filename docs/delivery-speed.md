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

En cours : contrat source 563 complet appelé deux fois dans une copie épinglée
de `0bf5854a`. Le résultat sera consigné ici.
