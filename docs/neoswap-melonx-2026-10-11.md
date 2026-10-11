# NeoSwap RPCS3 — adaptation du donneur MeloNX

Date : 11 octobre 2026. Branche : `Claude`. Source de départ :
`6cdbf6fdf552cc316187d18d2fff21c6731382dc` (sources après livraison 437).
Cette intervention concerne uniquement le courtier NeoSwap utilisé par RPCS3,
ses tests, sa validation et sa livraison. La **Build 438** a été compilée et
son IPA vérifiée ; elle n'a pas été testée sur l'iPhone.

## Source étudiée et choix d'intégration

Commit de Stossy :
[`2889267834c7581ad5e2753de6dbda6f5ae3b5fa`](https://starforgejo.dev/projects/MeloNX/commit/2889267834c7581ad5e2753de6dbda6f5ae3b5fa).
Les trois ancres fournies désignent `MLXRamDonor.h`, `MLXRamDonor.m` et
`MLXRamDonorProtocol.h`. L'étude couvre aussi `DonatedMemory.cs`,
`HostMemoryBudget.cs` et les chemins de récupération de pages du même commit.

| Mécanisme MeloNX | Situation et décision NeoSwap |
|---|---|
| Extension donneuse, objets Mach partagés, mapping hôte, sortie optionnelle du donneur | Déjà couvert par les donneurs et Guest Page Relay. Conserver les identités PID/génération, les preuves de comptabilité et l'observation de sortie existantes. Aucun deuxième framework empaqueté. |
| Plus petite plage libre suffisante (`DonatedMemory`) | Adapté en C++ dans les deux allocateurs existants, en conservant leurs structures et contrats. |
| Acquisition adaptée à la disponibilité | Conserver les budgets hôte, donneur et système. Corriger le maintien d'une grosse demande bloquée qui empêchait la sélection d'une demande plus petite. |
| Discard de pages libres, pression et budgets de caches | Le relais remet déjà à zéro les objets retirés avec `MADV_ZERO`, et l'hôte vide ses réserves inactives sous pression. Ne pas remplacer cette garantie par le lazy free de `MADV_FREE_REUSABLE`. |

Il s'agit d'une adaptation des idées pertinentes, pas d'une copie du framework
Objective-C/C# ou de ses binaires. Le commit est crédité dans les allocateurs.
Les plafonds mémoire et les règles JIT/PPU/SPU/RSX du Core restent inchangés.

## Changements effectifs

1. **Pool des donneurs** (`native/neoswap-donation/Pool.cpp`) : examiner les
   trous dans tous les blocs vérifiés, choisir le plus petit trou suffisant
   après contrôle de l'alignement, puis publier le prêt. Un trou exact arrête
   la recherche. Aucun nouvel appel système, remplissage mémoire ou allocation
   de métadonnées sur ce chemin. Les grands intervalles restent disponibles
   pour les buffers contigus suivants.
2. **Relais invité et prêts hôte RPCS3** (`native/neoswap-relay/Backend.cpp`) :
   même politique sur les plages du bitmap, y compris les queues de segments.
   Un compteur de pages occupées évite de parcourir les bits des segments vides
   ou insuffisamment libres. Il ne diminue qu'après le succès de la remise à
   zéro ; une erreur ou une quarantaine conserve la réservation. Les segments
   partiellement occupés gardent un parcours borné par le bitmap existant.
3. **Demandes des donneurs** (`NeoSwapPlugin.mm`,
   `NeoSwapDonationScheduler.h`) : à chaque maintenance sans préparation en
   cours, réinterroger la file des demandes, même si une grosse demande est
   déjà mémorisée. Une petite demande peut alors avancer. Durant la préparation
   d'un helper, conserver la séquence pour que son résultat ne valide jamais
   une autre demande. La grosse demande reste dans la file.

Le pool et le relais gardent leurs jetons, quotas, alignements, protections des
alias, sorties de session et chemins de repli existants. Aucune page vivante
n'est déplacée ou jetée. L'ABI NeoSwap et le Core RPCS3 épinglé ne changent pas.

## Vérifications

Environnement local : Linux, g++ C++20, `-Wall -Wextra -Werror`, ASan/UBSan
pour les exécutables natifs. LeakSanitizer ne peut pas accéder à `/proc/2/task`
dans cet environnement ; les exécutions utilisent `ASAN_OPTIONS=detect_leaks=0`
(ASan et UBSan restent actifs).

| Vérification | Résultat |
|---|---|
| `neoswap_pool_fragmentation_test.cpp` lié à `Pool.cpp` | Réussi : trous internes et entre blocs, demandes 16/32 Mio préservant 64/128 Mio contigus, alignement, isolation, 1 024 prêts, perte de donneur, nettoyage et relancement. |
| `neoswap_preparation_test.cpp` | Réussi : préparation avec le pool modifié. |
| `relay_backend_test.cpp` lié au backend de production | Réussi : meilleur trou exact/non exact, choix entre segments, fusion, alias, pression, erreurs et durée de vie. |
| Nouveaux scénarios de fragmentation sur les allocateurs de départ | Échec attendu des assertions : ils détectent réellement le comportement first-fit corrigé. |
| `neoswap_relay_loans_test.cpp` avec courtier et backend de production | Réussi : routage, quotas, étagères FAST, remplissage hors frame, emprunts concurrents, erreurs et fin de session. |
| `neoswap_demand_test.cpp` avec sélectionneur et courtier de production | Réussi : petite demande prioritaire à l'arrêt, identité figée pendant préparation, rejet d'ancien acquittement et reprise de la grosse demande. |
| `neoswap_donor_contract_test.py` | 20 réussis, 2 ignorés (codesign et projet Xcode Apple requis). |
| `neoswap_relay_extension_test.py` | 11 réussis, 1 ignoré (environnement Apple requis). |
| `neoswap_bridge_syntax_stub_test.py`, `neo_swap_core_pin_test.py` | Réussis ; entrées exactes du Core `96d7e709abae9e230254e7b26db8286cf05eb5a4` conservées. |
| Revue indépendante et `git diff --check` | Réussis. |

Une micro-mesure avec opérations système injectées a repéré le coût d'un
parcours complet des segments vides dans la première implémentation. Le
compteur de pages occupées supprime ce parcours. Cette mesure ne prouve ni
les latences d'une partie, ni un gain de FPS sur iPhone.

**Contrôle global bloqué, préexistant :** `test/check_neo_swap_scope.py`
s'arrête dans `import_memory_candidate_scope_test.py:1070` sur
`assets/legal/THIRD_PARTY_NOTICES.md` (« Reviewed ARMSX2 integration changed »).
Le même échec est reproduit sur une archive propre du commit de départ.
Ce fichier et la porte ne sont pas modifiés par cette intervention. Aucun
contrôle n'est affaibli pour faire passer une nouvelle compilation candidate.

## Livraison Build 438

La livraison utilise `.github/workflows/retroarch-delivery.yml`, déjà employé
pour la Build 437. Cette chaîne n'exécute pas le contrôle global historique
décrit ci-dessus ; son succès ne constitue donc pas un succès de ce contrôle.
Ses propres gardes de périmètre restent actives : liste explicite des sources
et tests NeoSwap modifiés, empreintes exactes des deux allocateurs, refus des
modifications hors périmètre et maintien du manifeste historique. Les entrées
du Core RPCS3 `96d7e709abae9e230254e7b26db8286cf05eb5a4` sont inchangées ;
son artefact du run `38081733944` est réutilisé après contrôle d'identité.

La première tentative, run `38155428580`, s'est arrêtée avant la production
d'une IPA : le test des réserves du relais supposait que 200 Kio restaient
200 Kio après arrondi à la page mémoire de l'hôte. Sur macOS avec des pages de
16 Kio, la demande est arrondie à 208 Kio. Le compteur de padding mesure la
différence entre l'intervalle réservé et cette demande arrondie. Le test lit
désormais `sysconf(_SC_PAGESIZE)` et conserve une assertion exacte ; aucun
code produit n'a été modifié pour résoudre cet échec.

Le run `38155641731`, sur
`a6f96e05f9ad1118e60871eda57925e1103a1eee`, a réussi les jobs `checks`,
`native` et `cold`. Le job `warm` est ignoré conformément à `benchmark=false`.
Les cinq exécutables natifs ont réellement été exécutés sur macOS avec
ASan/UBSan : fragmentation du pool, préparation, demandes, backend du relais
et prêts du relais. La compilation syntaxique iPhone arm64 du plugin a aussi
réussi avec les chemins donation, relais et stockage activés ensemble.
L'artefact de validation native `11707469831` contient 68 empreintes d'entrées,
vérifiées contre les sources de ce commit.

Les preuves Dart et Swift inchangées ont été réutilisées après contrôle de
leurs entrées et de leur provenance. Elles ne sont pas présentées comme de
nouvelles exécutions. Les tests natifs modifiés, eux, ont été exécutés à
nouveau avant la compilation de l'IPA.

| Élément vérifié | Valeur |
|---|---|
| Branche et sources | `Claude`, `a6f96e05f9ad1118e60871eda57925e1103a1eee` |
| Run de livraison réussi | `38155641731` |
| IPA | `NeoStation-Build438-a6f96e05f9ad1118e60871eda57925e1103a1eee-cold.ipa` |
| Taille | 206 911 584 octets |
| SHA-256 | `89b18faaee480698a83b759c79cddc4352e6094b702a9d62cc5a2e1ac970a783` |
| Version et cible | 0.0.2, build 438, arm64 / iPhoneOS |
| Signatures vérifiées | 57 signatures ad hoc ; re-signature Apple par SideStore nécessaire à l'installation |
| Durée mesurée de compilation Xcode | 276,499 s |
| Durée mesurée de signature et export | 56,870 s |
| Validation sur appareil | Aucun essai iPhone ; aucun gain RAM/FPS mesuré |

L'IPA récupérée localement correspond à `SHA256SUMS`, à
`signed-payload-identity.json` et au rapport `final-structure`. Son
`Info.plist` indique bien la build 438 et les métadonnées légales embarquées
portent le `host_commit` exact ci-dessus. Ces contrôles attestent l'identité
du fichier livré et sa construction, pas la stabilité d'une partie sur iPhone.

## Limites et validation sur iPhone

La compilation Xcode et l'export IPA ont réussi ; aucun essai iPhone n'a
encore été effectué pour ces changements. Les gains de RAM résidente et de
FPS restent à mesurer. Les scénarios démontrent une
meilleure utilisation de la capacité existante, pas une augmentation de la RAM
physique. Pour comparer, garder le même parcours God of War III et observer
les refus/prêts, la marge système, le footprint et les temps d'image.

La récupération partielle des pages d'un donneur persistant n'est pas activée :
sa preuve actuelle exige que la capacité préparée reste comptabilisée dans le
donneur. Un discard partiel demanderait un protocole de preuve adapté. Le
relais, lui, conserve sa récupération existante au retrait sûr des objets.
