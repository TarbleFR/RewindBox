# RPCS3 526 — migration SIMD native commune ARM64/NEON

État de préparation depuis `Claude` / `ed08da84f11a7182e133d80ecc9b2f602ce895ea` (525). Ce document distingue les observations de l'iPhone fournies, les modifications de source, les tests hôte et les validations encore nécessaires. **Les identités finales, les résultats Apple et l'IPA 526 restent à compléter après succès de leurs étapes ; aucune livraison ni amélioration de FPS n'est attestée par ce brouillon.**

## Problèmes établis par la nouvelle capture 525

Les quatre nouveaux journaux correspondent, pour le diagnostic RPCS3, au build **525**, PID **24255**, titre **BCES00510**, sur un appareil annonçant **7 989 460 992 octets** de mémoire totale. Le fichier NeoSwap conserve aussi des opérations anciennes : seules celles de ce PID sont rapprochées de la session courante. Les données brutes et les chemins personnels ne sont pas versionnés ; le relevé agrégé et les SHA-256 sont conservés séparément. Les milestones recopient une partie du diagnostic : 172 événements miroir sont dédupliqués ; leur dernier événement unique est conservé.

Le chargement recompilait **136 modules PPU** après le changement volontaire d'identité de cache 525. Le compteur de durée indique **308,190 s** depuis son propre début, environ 65,193 s avant le début de cette capture. Les lectures de cache PPU et les objets chargés représentent chacun **44 809 056 octets** ; 314 sondes incluent aussi l'existence de caches. Cette capture froide ne se compare pas à une session 524 déjà chaude. Les fenêtres proches de 33 FPS pendant cette phase concernent l'interface native : zéro image invitée, PPU/SPU inactifs. Elles ne mesurent pas God of War III à 33 FPS.

La courte partie après lancement contient environ 23 échantillons de présentation invitée, sans étiquette gameplay/menu/cinématique. Le profil SPU enregistre **zéro entrée d'interpréteur**, et le hash texture zéro octet. Elle ne démontre donc pas un coût de ces deux chemins dans ce passage du jeu. Les valeurs GPU restent **-1**, c'est-à-dire non mesurées. Les attentes de réservation sont des agrégats entre threads, pas des durées murales à soustraire aux images.

La restauration passe le TAR (**4,372659 s**), la VM (**0,573369 s**) puis les fonctions/segments/modules PPU. Les descripteurs de fichiers **3 et 4** sont rouverts et repositionnés. Pour **5**, l'ouverture retourne **faux** ; le dernier événement est `file_open_end`, position **1969210348**. La capture s'arrête avant le chemin de repli en mémoire ou l'erreur fatale existante. Elle n'établit ni une attente dans l'ouverture, ni la cause système de cet échec, ni un répertoire mal décodé. Le nouveau diagnostic ajoute le code d'erreur, la classe de racine virtuelle, l'état lecture seule/en mémoire et le jalon d'indisponibilité, sans chemin personnel et sans changer le comportement de récupération. Il ne répare pas à lui seul un fichier dont la cause d'indisponibilité reste inconnue.

La remise à zéro VMA introduite dans 525 est observée après arrêt : propriétaire non vivant, échantillon non valide et valeurs nulles. Avant arrêt : 61 606 016 octets demandés pour les textures, dont 11 images recyclables / 12 880 512 octets. Le maximum de footprint capturé est **2 411 157 496 octets**, celui de résident **2 480 635 904** ; ce ne sont pas des compteurs additifs. La mémoire compressée du processus n'est pas disponible dans ces quatre fichiers. Les donneurs atteignent **85 983 232 octets** préparés/résidents ; la cible NeoSwap de **7 Gio** et les alias de mappings ne créent pas de RAM physique supplémentaire. Les 761 événements de stockage rapprochés du PID n'indiquent aucune erreur OS ; 361 refus sont des décisions de quota. Leur durée maximale **97,254 ms** n'est pas à elle seule une saccade par image.

Ces observations justifient de préciser le diagnostic FS et de distinguer compilation froide/présentation native/émulation. Elles ne justifient pas de réduire les barrières, de modifier les atomiques CELL, de forcer une libération GPU ou d'activer une optimisation approximative.

## Architecture commune, utilisateurs réellement migrés

Le backend `rpcs3/util/simd.hpp` existait déjà : l'inventaire avant migration trouve **171 noms `gv_*`** et **180 branches ARM64**. Le PPU runtime utilise déjà ce backend : **481 occurrences de 147 opérations**, et le décodeur audio `cellAdec` **63 occurrences de 13 opérations**. Ces chiffres décrivent la source, toutes branches confondues, et non des appels mesurés. Les implémentations ARM64 y exécutent déjà directement NEON.

SSE2NEON est un header d'intrinsics inline, pas un traducteur dynamique. Beaucoup d'opérations simples, comme addition/AND/load, deviennent déjà une instruction NEON. Les raccorder à `gv_*` supprime une seconde API et rend les chemins cohérents ; cela ne suffit pas à prouver une accélération. Les réductions de travail sont identifiées séparément.

La migration complète de l'inventaire des **six consommateurs de SSE2NEON** raccorde l'interpréteur SPU et cinq composants RSX au même backend. Les 28 primitives communes ajoutées opèrent directement sur `v128` et leurs branches ARM64 n'appellent aucune ancienne implémentation SSE. La représentation des registres, leur taille 16 octets, leur alignement 16, l'endianness et le format des sauvegardes restent conservés. Les conversions de représentation fixes sont vérifiées dans le code compilé ; elles ne sont pas annoncées comme des allocations supprimées sans preuve.

| Composant 525 | Chemin 526 et utilisateurs basculés | Travail supprimé ou comportement conservé | Vérification attendue |
|---|---|---|---|
| `SPUInterpreter.cpp` : appels SSE2NEON et boucles scalaires | 114 corps actifs raccordés à `gv_*` ; primitives communes de masques, conversions, multiplication, réduction, popcount, permutations et shifts | Les opérations déjà une instruction restent équivalentes. CNTB utilise CNT ; CLZ traite les lanes ensemble ; SHUFB utilise TBL2 et élimine le tableau de deux vecteurs et les seize gathers ; neuf rotations/shifts par octets éliminent des tableaux temporaires ; CFLTU utilise la conversion unsigned native | Différentiels des vrais corps, alias de registres, contrôles/comptes limites, flottants/endianness ; absence de SSE2NEON dans le candidat ARM64 prétraité ; désassemblage |
| `Common/buffer_stream.hpp` | `stream_vector` et `stream_vector_from_memory` utilisent le store commun et les charges 128 bits | Une copie avant, un vecteur à la fois ; store non temporel x86 conservé, store normal cohérent ARM64 conservé | Alignements source 0..15 ; recouvrements ARM64 ±16/exact ; guards de plage ; instructions par symbole |
| `Common/BufferUtils.cpp` | Génération d'indices `iota16` raccordée au broadcast/add/store commun | Résultat modulo 16 bits et queues identiques ; les autres kernels NEON déjà efficaces restent en place | Petites tailles, queues, 65535/65536 et débordement, aucune écriture hors plage |
| `Program/ProgramStateCache.cpp` | Émission des constantes fragment raccordée au byte-swap, comparaison et store communs | Le chemin iOS était déjà NEON REV16 et groupé par quatre : efficacité conservée, pas de nouveau gain REV16 revendiqué ici | Sanitation NaN/Inf bit à bit, zéros signés/denormaux, offsets non triés/doublons, batch et queues |
| `RSXTexture.cpp` | Compensation des canaux de border color par XOR masqué | L'identité exacte `(octet−128) mod 256 = octet xor 128` élimine unpack→unpack→sub→shifts→packs | 256 valeurs par octet × 16 masques, couleurs multicanaux aléatoires, EOR dans le binaire |
| `Program/Assembler/FPToCFG.cpp` | `decode_instruction` utilise le byte-swap commun | Le swap par shifts/AND/OR et le rechargement de la variable locale deviennent REV16 | Résultat pour chaque octet/lane, codegen par symbole sans appel auxiliaire |

L'inventaire textuel de départ contient 503 appels `_mm_*` dans ces six fichiers, dont 464 dans tout `SPUInterpreter.cpp`. Quatre de ces derniers se trouvent dans le bloc historique `#if 0`, qui reste conservé, et des variantes x86 ne sont pas exécutées sur iOS. Le nombre textuel brut n'est pas un compte de gains. Dans la zone SPU hors du bloc `#if 0`, le relevé initial contient 460 occurrences toutes architectures confondues. Les branches ARM64 quittent ces API héritées ; les variantes x86, notamment flottantes, restent sous leurs gardes dédiées pour conserver leur comportement. La preuve déterminante est le candidat ARM64 prétraité et les unités réelles compilées, pas le nombre de remplacements textuels.

## Traduction PPU, distincte du SIMD hôte

Le correctif SPU `ROTQMBI` remplace aussi la négation signée de `INT32_MIN`, indéfinie en C++, par une soustraction non signée modulo avant le masque de trois bits. Un contrôle négatif UBSan distingue ce défaut source du résultat différentiel valide ; aucune barrière ni attente n’est modifiée.

Le nouveau builder `CellVectorLowering.h` produit de l'IR AArch64 pour quatre opérations PPU :

| Instruction invitée | Ancien calcul générique | Nouveau calcul ARM64 | Contrat |
|---|---|---|---|
| VMSUMUBM | Produits d'octets extraits et sommes intermédiaires | UDOT avec accumulateur, sous garde DOTPROD | Quatre produits non signés par mot, modulo 2^32 |
| VMSUMMBM | Extraction signée/non signée, produits puis sommes | Deux UDOT, biais XOR 0x80 et correction de 128×sum(B), sous garde DOTPROD | Résultat signé×unsigned exact, sans imposer I8MM |
| VMSUMSHM | Séparation des halfwords, produits et additions | SMULL bas/haut puis ADDP et accumulateur | Deux produits signés par mot, modulo 2^32 |
| VMSUMUHM | Séparation des halfwords, produits et additions | UMULL bas/haut puis ADDP et accumulateur | Deux produits unsigned par mot, modulo 2^32 |

Les versions saturées VMSUMSHS/UHS et l'état SAT restent identiques. Les membres d'une paire ou d'un groupe peuvent être renversés dans la représentation little-endian sans modifier la somme, ce qui est vérifié avec une référence indépendante en ordre invité big-endian. Le fallback sans DOTPROD reste conservé et doit être exécuté dans les tests. Aucune extension SVE/I8MM n'est exigée par ces nouvelles opérations.

La fixture compile les corps de production et les nouveaux builders, en remplaçant le registre **et le modèle de valeurs/opérateurs du DSL** par des adaptateurs minimaux LLVMIRBuilder. Elle exécute les kernels ARM64 produits et compare le code émis pour la cible JIT existante ; cela ne constitue ni un CPU invité complet, ni le passage réel de God of War III. La fréquence de ces quatre opcodes dans le titre n'est pas connue. Les chiffres de kernels doivent garder cette portée.

L'interpréteur PPU, les helpers SPU déjà natifs, les intrinsics AArch64 existants de CPUTranslator et les passes SPU déjà validées ne sont pas remplacés nominalement pour annoncer une nouvelle accélération. Le nom interne `x86_pshufb`, par exemple, émet déjà sur ARM64 AND 0x8f puis TBL1. Le renommer ne changerait pas le coût.

## Caches JIT, mémoire et cycle de vie

La version exacte du cœur et des dépendances reste celle du contrat canonique : RPCS3 XITRIX base `22f1152783cef1f7e04af7b1c895173e28fd5b03`, ABI 30 ; LLVM 22.1.8 avec son correctif GHC AArch64 conservé ; FFmpeg 8.1.1 et MoltenVK 1.4.2, Vulkan→Metal. Le nouvel objet doit être reconstruit depuis les sources, pas remplacé par un Core extrait d'une IPA externe.

Delta canonique `ca3c3332f7ef1f8a2d1221fb51fa567737fa9406e28543700b23376e0d68e5ae` : 258 postimages, onze chemins changés depuis 525 dont un nouveau header. Digests PPU `b77f5996577e4a4d` et SPU `35f4bbf84d9c21c3` : les deux caches compilés changent, en incluant explicitement le backend partagé, `v128`, le runtime SPU et le nouveau builder PPU. Le builder PPU doit entrer dans l'identité du cache avec ses consommateurs. Un changement d'identité impose un premier lancement froid ; ce coût doit être annoncé séparément d'un gain d'exécution. Les objets incompatibles ne sont pas chargés pour raccourcir artificiellement le démarrage. Aucune nouvelle arène exécutable, méthode JIT, adresse dépendante du processus, relocation ou règle de publication du code n'est introduite.

Les primitives SIMD n'allouent pas de stockage dynamique par opération et retirent certains temporaires scalaires/stack. Elles ne démontrent pas une forte réduction de footprint global : les caches, textures, ressources GPU et backing invités dominent d'autres budgets. Les fenêtres PPU bornées et les diagnostics VMA 525 sont conservés. Aucun changement de quota NeoSwap, donation, relais, réservation virtuelle, pool de workers, priorité, ordre mémoire ou barrière RSX n'est appliqué sans lien mesuré au problème.

Le Core reste ARMv8.4-A ; l'hôte vérifie déjà les features avant le JIT et `dlopen`. NEON générique/ARMv8-A ne rend pas ce Core compatible avec un appareil plus ancien. Le build n'ajoute aucune extension CPU supplémentaire, aucune variante incompatible forcée et aucun faux repli ARMv8-A.

## Chemins préservés et limite de couverture

`IOSDMACopy.h` produit déjà des copies vectorielles avant avec contrat de recouvrement ; les remplacer par un `memcpy` de plage complète pourrait modifier les dépendances. `IOSTextureHash.cpp` utilise déjà la variante XXH3 six lanes NEON/deux scalaires et une boucle de quatre stripes ; elle reste conservée. Les conversions vertex/copy-swap existantes, le décodeur audio `cellAdec` via `gv_*` et les backends natifs spécialisés de FFmpeg restent en place. La migration du runtime RPCS3 ne signifie pas une réécriture non mesurée de toutes les dépendances.

Les fonctions `gv_exp2_approxfs` et `gv_log2_approxfs` utilisent encore quatre appels scalaires à libm ; leur ancien polynôme SIMD est désactivé. Une approximation NEON sans contrat d'erreur, cas limites CELL et fréquence observée ne respecte pas les garanties demandées. Elles restent documentées comme non migrées. Le bloc precise SPU historique `#if 0` garde ses anciens noms sans être réactivé ; aucune réparation de ses flags FPSR n'est présentée comme active.

Aucun backend Metal direct, XMB/MetalFX d'interface, frameskip, réglage risqué ou télémétrie automatique n'est ajouté. NeoSwap, sauvegardes originales, pause/fermeture et correctifs RSX restent conservés. Les autres moteurs et interfaces RewindBox sont hors de ce delta. Aucune nouvelle interface traduisible n'est créée.

## Validation et mesures

**État provisoire, à remplacer par les reçus finaux :** les tests différentiels et leur cible Apple sont en cours de préparation. Le banc SPU x86_64 avec les vrais headers passe 4 894 912 comparaisons sous ASan/UBSan dans chacune des deux configurations de contraction (défaut puis désactivée), avec quatre arrondis et deux modes de dénormalisation. Le contrôle négatif UBSan de ROTQMBI est exécuté séparément ; seule cette fonction témoin exclut ce débordement signé dans le différentiel, le candidat restant entièrement instrumenté. Le banc RSX x86_64 avec ASan/UBSan passe 15 328 199 contrôles ; il ne valide pas encore l'exécution des instructions ARM64. Les cas de copie recouvrante sont réservés à ARM64. Les fixtures conservent le témoin de production 525, les empreintes des deux versions et l'ancienne couche seulement dans le témoin. Les tests SIMD hôte et PPU code généré restent deux preuves distinctes.

À consigner après succès : nombre de cas et alias SPU, sorties flottantes et contraction effective du Core, modes sans/avec DOTPROD, codegen par symbole, temps muraux/CPU des kernels alternés, matériel et compilateur exacts, ASan/UBSan, unités SDK iPhone réellement recompilées, lien complet, 88 exports/ABI 30 et absence d'introduction de dépendances. Les tests antérieurs inchangés sont réutilisés avec empreintes, sans les présenter comme une nouvelle campagne.

Les mesures finales doivent séparer :

- **Gain mesuré sur banc** : temps d'un kernel/fonction et réduction d'instructions, avec conditions exactes.
- **Bénéfice attendu** : moins d'opérations ou de temporaires dans un consommateur réel, sans conversion en FPS estimés.
- **À vérifier sur appareil** : même iPhone 16 Pro Max, même scène/réglages ; premier cache froid après invalidation puis cache chaud ; chargement, images/P95/P99, saccades, footprint/résident et thermique sur une session prolongée ; gameplay, menus et cinématiques séparés ; restauration de l'original, manette, pause/reprise, fermeture et second lancement.

Les journaux fournis constituent une vraie observation appareil de 525 ; ils ne valident pas 526. Aucun iPhone, contenu du jeu ou sauvegarde originale n'est exécuté par l'agent dans l'environnement de compilation. Aucune mesure GPU n'est inventée à partir de -1, et aucune réduction mémoire ne découle de la cible 7 Gio de NeoSwap.

## Sources et licences

Les modifications portent sur les sources RPCS3 conservées avec leurs notices et le delta canonique. Le README de la base indique GPL-2.0-only pour la majorité des fichiers, avec exceptions par fichier ; le header SSE2NEON MIT et ses attributions restent dans la source même si les six consommateurs iOS le quittent. Les nouveaux fichiers doivent porter leur licence explicite et être accompagnés de leur provenance. Les fixtures indépendantes sont des adaptateurs de test, pas une nouvelle licence pour les fragments RPCS3 qu'elles extraient.

Références primaires consultées pour les contrats (24 octobre 2026) :

- [Arm Neon Intrinsics Reference / ACLE](https://arm-software.github.io/acle/neon_intrinsics/advsimd.html) : correspondances CNT, CLZ, REV16, TBL, FCVTZU, widening et dot product ; version affichée `aef52c2` à la consultation. Ces correspondances guident le choix ; le désassemblage réel reste requis.
- [Arm C Language Extensions](https://arm-software.github.io/acle/main/acle.html) : disponibilité NEON et garde DOTPROD, distincte des extensions Matrix Multiply.
- [LLVM 22.1 Language Reference](https://releases.llvm.org/22.1.0/docs/LangRef.html) : arithmétique entière modulo la largeur, conversions, poison et contraintes d'environnement flottant. Ce manuel 22.1.0 définit le contrat ; la construction doit employer la version 22.1.8 épinglée et son patch existant.
- Sources de la base matérialisée : `util/simd.hpp`, `util/v128.hpp`, les six consommateurs ci-dessus, `CPU/CPUTranslator.*`, `Cell/PPUTranslator.cpp`, `Cell/SPULLVMRecompiler.cpp`, CMake des identités et le manifeste canonique.

Les signatures des intrinsics ont été vérifiées dans `IntrinsicsAArch64.td` de LLVM `llvmorg-22.1.8` (blob `fd56e0e3f9e7b304178c4221ce4f6415d0d5c3f4`). La construction et l’exécution LLVM 22.1.8 restent nécessaires pour valider leur intégration effective.

## Livraison privée

**À compléter uniquement après réussite et téléchargement vérifié :** numéro/version 526, commit Core, run/job/artifacts, SHA-256 du Core et de l'IPA, architectures/exports/entitlements/dépendances et contrôle indépendant de l'archive. Aucune modification de `main`, aucun tag et aucune release publique ne sont autorisés pour ce chantier. L'IPA testable doit être privée et sa signature/installation réellement disponible annoncée sans assimiler l'assemblage à une validation physique.
