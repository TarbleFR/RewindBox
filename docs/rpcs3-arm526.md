# RPCS3 526 — backend SIMD commun ARM64/NEON

Depuis `Claude` / `ed08da84f11a7182e133d80ecc9b2f602ce895ea` (525), le delta raccorde les six derniers consommateurs SSE2NEON au backend SIMD commun, ajoute quatre traductions PPU AArch64 et précise l'échec de réouverture des fichiers sauvegardés. Les résultats sur banc, les observations de l'iPhone en 525 et la validation de la nouvelle IPA restent distincts. Aucun gain global de FPS ou de mémoire sur iPhone n'est mesuré.

Les empreintes, rapports et essais incomplets sont consignés dans [le relevé de validation](evidence/rpcs3-arm526-validation.json). Les journaux bruts et chemins personnels ne sont pas versionnés.

## Problèmes, interventions et preuves

| Problème observé ou défaut de source | Cause établie et intervention | Preuve et portée |
|---|---|---|
| Une seconde API SIMD reste utilisée par le SPU et cinq composants RSX | Les consommateurs SSE2NEON sont migrés vers `gv_*`, avec 28 primitives communes supplémentaires ; les branches ARM64 utilisent directement NEON ou des charges/écritures vectorielles | 114 corps SPU modifiés ; contrôle du prétraitement, dépendances et code émis. Les opérations simples déjà NEON ne reçoivent aucun gain présumé |
| SHUFB effectue seize gathers depuis un tableau temporaire ; CNTB émule le comptage de bits | TBL2 pour la permutation et CNT pour les octets ; les règles de sélection et valeurs spéciales CELL restent conservées | Différentiel des corps de production, contrôles et alias de registres ; mesures LLVM22 du backend final ci-dessous |
| CFLTU reconstruit la moitié unsigned avec des conversions signées et masques | FCVTZU réalise directement conversion, saturation et NaN→zéro | Cas limites flottants et configurations de contraction ; aucune approximation ni modification de précision |
| ROTMAI peut décaler dans le mauvais sens sur ARM64 | La macro SSE2NEON applique `-imm` sans parenthèses à son argument composé ; `gv_sar32` suit le contrat CELL | Référence scalaire indépendante pour huit instructions immédiates : le témoin ROTMAI présente 62 erreurs sur 128 immédiats ; le candidat suit la référence. Aucun appel d'interpréteur n'est observé dans la capture du jeu fournie |
| ROTQMBI contient une négation signée de `INT32_MIN` | Soustraction non signée modulo avant le masque de trois bits | Témoin UBSan séparé ; candidat instrumenté. Ni attente ni barrière modifiée |
| Des produits/sommes PPU génériques produisent des suites AArch64 plus longues | Builder natif pour quatre VMSUM, distinct du SIMD hôte | Exécution LLVM22 des kernels et référence big-endian ; deux kernels byte-dot accélèrent sur le banc, sans fréquence connue dans God of War III |
| La restauration 525 s'arrête après l'échec d'ouverture du fichier ID 5 | La cause système n'est pas connue ; ajout du code d'erreur, de la classe de racine virtuelle, des états lecture seule/en mémoire et du jalon d'indisponibilité | Les fichiers 3/4 sont rouverts ; 5 retourne faux. Le diagnostic ne change pas la récupération, ne supprime aucun fichier et ne prouve pas la reprise du savestate utilisateur |

## Couverture réelle de la migration

Le backend `rpcs3/util/simd.hpp` était déjà natif : **171 noms `gv_*`** et **180 branches ARM64** avant ce chantier. Le runtime PPU l'utilisait déjà à **481 occurrences / 147 opérations**, et le décodeur audio `cellAdec` à **63 occurrences / 13 opérations**. Ces comptes sont textuels, toutes architectures confondues, pas des fréquences mesurées.

SSE2NEON est un header d'intrinsics inline, pas une traduction dynamique. Le remplacer par une interface commune rend l'architecture cohérente ; un ADD déjà compilé en ADD NEON peut rester strictement identique. Les réductions de travail suivantes sont distinguées des simples raccordements :

| Ancien consommateur | Utilisateurs effectivement basculés | Réduction ou garantie conservée |
|---|---|---|
| `Cell/SPUInterpreter.cpp` | 114 corps actifs vers `gv_*` : arithmétique, masques, comparaisons, conversions, multiplication, réductions et permutations | SHUFB/TBL2, CNTB/CNT, CLZ vectoriel, CFLTU/FCVTZU ; shifts par lane avec les règles CELL. Les neuf rotations/shifts par octets utilisent des fenêtres vectorielles natives bornées |
| `RSX/Common/buffer_stream.hpp` | `stream_vector`, `stream_vector_from_memory` | Copie avant un vecteur à la fois ; store non temporel x86 et store normal cohérent ARM64 conservés |
| `RSX/Common/BufferUtils.cpp` | Génération d'indices `iota16` | Broadcast/add/store communs ; résultat modulo 16 bits et queues identiques |
| `RSX/Program/ProgramStateCache.cpp` | Émission des constantes fragment | Le chemin iOS était déjà REV16/masque/store groupé par quatre : efficacité conservée, aucun nouveau gain REV16 revendiqué ici |
| `RSX/RSXTexture.cpp` | Compensation des canaux du border color | XOR masqué remplace unpack→unpack→sub→shifts→packs, selon l'identité exacte `(octet−128) mod 256 = octet xor 128` |
| `RSX/Program/Assembler/FPToCFG.cpp` | `decode_instruction` | REV16 remplace shifts/AND/OR et le rechargement local, sans permutation entre halfwords |

Les **28 nouvelles primitives** sont des implémentations du backend commun. Elles n'appellent pas l'ancien adaptateur dans leurs branches ARM64. `v128` conserve son format de 16 octets, son alignement 16, ses vues de registres et l'endianness nécessaires aux états de sauvegarde. Les conversions fixes de représentation ne sont pas annoncées comme des allocations supprimées.

L'inventaire de départ compte 503 appels `_mm_*` dans les six fichiers, dont 464 dans l'ensemble de `SPUInterpreter.cpp`. Quatre sont dans le bloc historique `#if 0` ; d'autres sont des variantes x86. Les branches ARM64 quittent l'API héritée ; les variantes x86, notamment flottantes, et le bloc désactivé restent préservés. Le contrôle porte sur les opérations ARM64 actives et les dépendances des unités compilées, pas sur une suppression globale des noms SSE.

## Code PPU généré et caches

`CellVectorLowering.h` produit de l'IR AArch64, indépendamment des opérations hôte `gv_*` :

| Instruction invitée | Traduction native retenue | Contrat |
|---|---|---|
| VMSUMUBM | UDOT avec accumulateur, sous garde DOTPROD | Quatre produits unsigned par mot, modulo 2^32 |
| VMSUMMBM | Deux UDOT, biais XOR 0x80 et correction de 128×sum(B), sous garde DOTPROD | Produits signed×unsigned exacts, sans I8MM |
| VMSUMSHM | SMULL bas/haut, ADDP et accumulateur | Deux produits signed par mot, modulo 2^32 |
| VMSUMUHM | UMULL bas/haut, ADDP et accumulateur | Deux produits unsigned par mot, modulo 2^32 |

Les instructions saturées VMSUMSHS/UHS et l'état SAT restent inchangés. Le fallback sans DOTPROD est conservé et exécuté dans la fixture. Aucune extension SVE/I8MM supplémentaire n'est imposée. Le groupement des termes sous représentation little-endian est vérifié contre une référence indépendante en ordre invité big-endian.

La fixture compile les vrais corps de méthodes et le builder, mais remplace le registre **et les valeurs/opérateurs du DSL** par des adaptateurs LLVMIRBuilder minimaux. Elle exécute les kernels ARM64 produits ; elle n'exécute ni le traducteur PPU complet, ni un CPU invité complet, ni le jeu. La fréquence des quatre opcodes dans God of War III n'est pas mesurée.

Le delta canonique est **`5ba0430b436e30ffb10e0d390e74a0cba97358f526519c71508c07b1bfe8d563`**, avec **258 postimages** et onze chemins changés depuis 525, dont un nouveau header. Les digests deviennent PPU **`154c7bf72760385a`** et SPU **`f059b89241cfd758`** : le backend partagé, `v128`, le runtime SPU et le builder PPU sont inclus explicitement. Les deux caches compilés changent ; le premier lancement par titre sera froid. Aucun objet incompatible n'est réutilisé pour raccourcir artificiellement ce lancement.

Aucune nouvelle arène exécutable, méthode JIT, adresse dépendante du processus, relocation ou règle de publication du code n'est introduite. Le Core reste ARMv8.4-A, avec vérification des features avant préparation JIT et `dlopen` ; aucun faux repli ARMv8-A n'est annoncé.

## Ce que les journaux de l'iPhone établissent

Le diagnostic courant est **525 / PID 24255 / BCES00510**, sur un appareil annonçant **7 989 460 992 octets** de mémoire totale. Les opérations NeoSwap anciennes sont séparées ; 172 miroirs de milestones sont dédupliqués, et le dernier événement unique est conservé.

Le lancement recompilait **136 modules PPU** après le changement d'identité de cache 525. Le compteur démarre avant la capture et indique **308,190 s** ; ce résultat froid ne se compare pas à une session 524 chaude. Les fenêtres proches de 33 FPS pendant cette phase concernent l'interface native : zéro image invitée et PPU/SPU inactifs. Les lectures de cache PPU et les objets chargés représentent chacun **44 809 056 octets** ; les 314 sondes incluent l'existence des caches.

La courte séquence invitée comporte 23 échantillons, sans distinction gameplay/menu/cinématique. Les compteurs d'entrée d'interpréteur SPU et de hash texture restent nuls. Le temps GPU vaut **-1**, donc n'est pas mesuré. Aucun coût de ces chemins dans ce passage du jeu, ni amélioration 526, ne peut être déduit de cette capture.

La restauration passe le TAR (**4,372659 s**), la VM (**0,573369 s**) et les fonctions/segments/modules PPU. Les fichiers 3/4 sont rouverts et repositionnés ; 5 retourne faux à `file_open_end`, position **1969210348**. La capture se termine avant le repli en mémoire ou l'erreur fatale existante. Elle ne prouve ni attente dans `open`, ni répertoire mal décodé, ni cause système précise de l'échec.

Le reset VMA de 525 est observé après arrêt : propriétaire non vivant, échantillon non valide et compteurs nuls. Avant arrêt : **61 606 016 octets** demandés pour les textures, dont 11 images recyclables / **12 880 512 octets**. Le maximum de footprint est **2 411 157 496 octets**, celui de résident **2 480 635 904** ; ils ne s'additionnent pas. Le compressé du processus manque dans ces fichiers. Les donneurs atteignent **85 983 232 octets** préparés/résidents ; cible NeoSwap de 7 Gio et alias ne sont pas de la RAM physique supplémentaire. Les 761 événements de stockage rapprochés ne présentent aucune erreur OS ; 361 sont des refus de quota. Leur maximum **97,254 ms** n'est pas à lui seul une saccade par image.

## Validation actuelle et mesures

Les sept cas préalables du **cinquième essai**, source **`6a60950964aadd3487b477dc35712c5ac1d39586`**, [run `40128154799`](https://github.com/TarbleFR/RewindBox/actions/runs/40128154799), sont validés individuellement. Les cinq cas SIMD/PPU ont été exécutés directement avec le backend final **`a0aa419c826b6501cfe3824b18998089849206f456b2e20afffb998804cfb2b4`** ; les deux preuves FS/gate inchangées sont réutilisées directement du deuxième essai, sous contrôle des entrées et de l'environnement. Les sept SHA-256 des rapports correspondent au reçu préalable `all_tests_passed=true`. Le workflow a ensuite été annulé pendant l'étape Core pour corriger le support des fichiers de dépendances `.d` dans un ancien mock de la porte syntaxique. Ces preuves préalables ne sont donc pas une construction réussie du Core final ; la sixième campagne en atteste séparément le lien et le binaire.

| Validation | Preuve du candidat final disponible | Portée |
|---|---|---|
| SPU : 114 corps actifs | **4 894 912 comparaisons de registres et 325 888 contrôles scalaires par configuration**, sous ASan/UBSan : contraction par défaut, puis désactivée ; chacune couvre quatre arrondis et deux modes de dénormalisation | Réels corps et primitives, registre/opcodes/échelles adaptés ; aucun jeu exécuté |
| Contrôles SPU spécifiques | 65 536 masques, les 256 contrôles SHUFB et les alias ; référence ISA indépendante pour les shifts, dont 62/128 divergences attendues du témoin ROTMAI ; contrôle négatif UBSan pour ROTQMBI | L'ancien débordement signé n'est désactivé que dans cette fonction témoin du différentiel ; le candidat reste instrumenté |
| Fenêtres par octets finales | **199 680 contrôles de bornes**, 260 comptes dont UINT32_MAX ; rotations/zero-fill et sortie nulle pour shifts ≥16 | Temporaires alignés sur **32 octets pour la rotation et 64 pour les shifts**, conformément au Core 525 ; format invité `v128` toujours aligné sur 16 |
| Cinq composants RSX | **15 328 295 contrôles ARM64 ASan/UBSan**, dont **96 recouvrements** ; 16 alignements source, 104 tailles `iota16`, 1 000 tours de constantes ; candidate-only sans ancien header/token actif | Méthodes réelles extraites et `v128` réel, adaptateurs registres/données ; aucun GPU exécuté |
| Instructions hôte émises | CNT, TBL2, shifts natifs et FCVTZU vérifiés ; REV16/EOR/stores vérifiés par symbole RSX ; fenêtres avec charges/écritures natives, sans TBL ni appel auxiliaire chaud | Protection de pile conservée ; seul son appel froid d'échec de canari est admis |
| Quatre kernels PPU LLVM22 | **75 941 cas/opération**, before/after/fallback, référence big-endian et cinq contrôles UDOT matériels ; exécution directe dans le cinquième essai | Registre et opérateurs du DSL adaptés ; pas de pipeline PPU complet ni d'iPhone |
| Diagnostic FS | 24 cas de fichiers, 15 classifications de racines, fingerprint d'état avant/après identique et refus conservés ; preuve directe réutilisée de `28f896c7`, run `40124207015` | Compilateur Apple Clang17 authentifié et entrées FS identiques ; diagnostic uniquement, pas de restauration de l'original utilisateur |
| Orchestration de la porte SIMD | Preuve directe réutilisée du même deuxième essai ; refus d'une opération héritée active, préservation des échecs et contrôle de dépendances | Cas d'orchestration et smoke de compilateur ; ne remplace pas les dépendances et les 47 unités iPhone de la construction réelle |
| Core final : 47 unités SDK iPhone, lien, ABI et binaire | **Réussi** : source `1deb79bf93ab65f1b71b86ba03b10a55efe908c7`, [run `40128792897`](https://github.com/TarbleFR/RewindBox/actions/runs/40128792897), job `120975858312`. 47 unités SDK réelles, lien complet, arm64 iPhoneOS / ARMv8.4-A, ABI30 / 88 exports exacts. Artefact Core `12574852306`, SHA-256 du dylib `863d81225880c8ec604e00ddb8bc676ab86de7210ab60b7367d9eb4c01810883`. Cinq fermetures de dépendances sans SSE2NEON ; les neuf callbacks de fenêtres ont leurs alignements et nombres d’instructions de525, avec BFXIL restauré et seul appel froid de canari | Le Core précédent `5396ec9d…` appartenait à la variante historique alignée sur 16 et ne valide pas le delta final |
| IPA privée finale | **[ROOT_COMPLETE: version/commit/run/artifact/SHA, intégrité, entitlements, dépendances, signatures et lien privé]** | Assemblage distinct de l'installation et du gameplay sur appareil |

Les erreurs de preuve des premiers essais restent détaillées dans le JSON : filtres trop larges sur les déclarations SDK et le seul appel froid `__stack_chk_fail`, détection de features LLVM vide sur Darwin ARM64. Les probes contrôlent maintenant les opérations actives sans retirer la protection de pile et exigent une sonde Darwin valide puis cinq UDOT matériels. L'hypothèse d'alias ARM dans `types.hpp` était fausse. La variante TBL1 des shifts par octets a également été rejetée après ses régressions mesurées. Enfin, la lecture des **vrais Core 525 et de la variante 526 historique** a révélé la perte des alignements de temporaires 32/64, et un calcul d'adresse BFXIL remplacé par AND+ADD. Les contraintes d'alignement ont été restaurées ; les rapports ci-dessous portent sur cette source corrigée. La cause exacte des écarts de temps — adresse, accès mémoire, placement du code ou bruit du banc — n'est pas isolée, et aucun gain de RAM n'en est déduit.

Les timings suivants proviennent tous des **rapports directs du cinquième essai**, avec **Clang/LLVM 22.1.8**, sur **Apple M1 (Virtual) / VirtualMac2,1**, macOS 15.7.9 ARM64. Chaque comparaison alterne avant/après douze fois et écarte les deux premiers tours ; les tableaux donnent les médianes des dix restants. Les tests de conformité SPU passent dans **les deux configurations de contraction** ; les benchmarks SPU ne mesurent que **la configuration par défaut**, sans sanitizers. Il ne s'agit pas d'un essai de jeu ou de stockage, et les petits écarts n'ont pas de significativité statistique établie.

SPU : **1 000 000 appels par tour**, même corpus et registre adapté. Tous les huit kernels mesurés sont présentés, y compris ceux plus lents :

| Kernel SPU | Murale avant (ns/appel) | Murale après (ns/appel) | CPU avant→après (ns/appel) | Variation murale |
|---|---:|---:|---:|---:|
| CNTB | 14,621 | 8,391 | 14,588→8,254 | −42,61 % |
| SHUFB | 29,259 | 10,877 | 29,231→10,864 | −62,82 % |
| ROTM | 7,987 | 8,197 | 7,973→8,160 | +2,62 % |
| ROTHM | 8,434 | 7,660 | 8,393→7,644 | −9,18 % |
| ROTQBY | 7,599 | 7,653 | 7,590→7,628 | +0,71 % |
| ROTQMBY | 6,048 | 5,916 | 6,029→5,902 | −2,19 % |
| SHLQBY | 5,948 | 6,195 | 5,945→6,191 | +4,14 % |
| CFLTU | 14,498 | 9,442 | 14,472→9,434 | −34,87 % |

CNTB, SHUFB et CFLTU réduisent nettement le travail de ces kernels. ROTM, ROTQBY et SHLQBY sont légèrement plus lents dans ce relevé ; ces valeurs restent consignées, sans extrapolation en FPS ni gain attribué aux fenêtres. Le raccordement commun des opérations déjà efficaces et la préservation de leurs contraintes d'alignement restent distincts d'une accélération mesurée. Les détails de chaque tour et les temps non arrondis sont conservés dans le rapport.

RSX border color : **4 194 304 appels par tour** ; médiane murale **1,791229→1,452272 ns/appel** (−18,92 %) et CPU **1,791358→1,452327 ns/appel**. Cela mesure la fonction de conversion scalaire supprimant l'expansion SIMD, pas le temps GPU, le débit de textures ou les FPS.

PPU : **1 048 576 appels par tour**, code généré et corpus chauds, sans éviction de cache invité/fichier. Le tableau emploie les **nouvelles mesures directes du cinquième essai**, et non les anciennes médianes du troisième essai :

| Kernel PPU généré | Temps avant | Temps après | Instructions avant→après | Variation murale |
|---|---:|---:|---:|---:|
| VMSUMUBM | 1,60648 ms | 1,18002 ms | 18→6 | −26,55 % |
| VMSUMMBM | 1,72231 ms | 1,22473 ms | 20→13 | −28,89 % |
| VMSUMUHM | 1,13937 ms | 1,16231 ms | 13→9 | +2,01 % |
| VMSUMSHM | 1,15217 ms | 1,11912 ms | 14→9 | −2,87 % |

Les deux byte-dot prennent environ **26,5 % et 28,9 % de temps en moins** dans ces kernels. Les deux halfword-dot ont des écarts plus faibles, dont +2,01 % pour VMSUMUHM ; aucune accélération significative n'est revendiquée pour eux. Le compte d'instructions comprend transferts et retour, sur la cible de génération `apple-m4`. Ce nom LLVM n'est ni le matériel du runner ni un iPad utilisé pour la mesure.

## Périmètre préservé et validations appareil

La migration ne réécrit pas les chemins déjà natifs et spécialisés : runtime PPU, audio `cellAdec`, copies DMA avant, variantes NEON vertex/copy-swap, hash XXH3 six lanes NEON/deux scalaires, FFmpeg. Le nom interne `x86_pshufb` produit déjà AND 0x8f/TBL1 sur ARM64 ; un renommage n'aurait apporté aucun gain. Les approximations `gv_exp2_approxfs`/`gv_log2_approxfs` gardent leurs quatre appels à libm : remplacer leur contrat par un polynôme SIMD non validé modifierait la fidélité.

La visite répétée des plages historiques dans `JITLLVM.cpp::finalizeMemory` reste une piste à mesurer. Supprimer ces plages sans prouver les contraintes de relocation et de publication du code serait risqué ; cette logique reste conservée.

Les primitives n'allouent pas de stockage dynamique par opération ; cela ne prouve pas une forte réduction du footprint du processus. Aucun quota NeoSwap, prêt/relais, réservation virtuelle, pool de travailleurs, priorité, atomique, ordre mémoire ou barrière RSX n'est changé. Sauvegardes originales et garanties de cycle de vie restent conservées. Aucun backend Metal direct, XMB/MetalFX d'interface, frameskip, nouveau réglage risqué, télémétrie automatique ou interface nécessitant une traduction n'est ajouté. Les autres moteurs et interfaces RewindBox restent hors du delta.

Les journaux fournis sont une observation réelle de **525**, pas une validation appareil de **526**. Aucun iPhone, jeu ou savestate original n'est exécuté par l'agent. Pour comparer sur l'iPhone 16 Pro Max : même scène, réglages et appareil ; première compilation froide séparée, puis caches chauds ; gameplay, menus et cinématiques séparés. Relever lancement/chargements, FPS et temps d'image/P95/P99, saccades, footprint/résident et thermique sur une session prolongée. Vérifier aussi restauration de l'original, manette, pause/reprise, arrêt et second lancement avec les journaux intégrés. Un temps GPU de -1 reste indisponible ; la capacité NeoSwap n'est jamais convertie en économie physique mesurée.

## Sources, licences et livraison

Base RPCS3 XITRIX **`22f1152783cef1f7e04af7b1c895173e28fd5b03`**, ABI **30** ; LLVM **22.1.8** avec son correctif GHC AArch64 conservé ; FFmpeg **8.1.1** et MoltenVK **1.4.2**, Vulkan→Metal. La recette reconstruit le Core depuis les sources, sans substitution d'un binaire extrait d'une IPA externe.

Le README de la base indique GPL-2.0-only pour la majorité des fichiers, avec exceptions par fichier. Les notices RPCS3 restent conservées ; le header SSE2NEON MIT et ses crédits restent dans la source, même si ses six consommateurs iOS le quittent. Le nouveau header natif porte explicitement `SPDX-License-Identifier: GPL-2.0-only`. Les adaptateurs indépendants de test ne changent pas la licence des fragments RPCS3 extraits. Le delta canonique et ses postimages conservent la provenance des modifications.

Références primaires consultées le 24 octobre 2026 :

- [SPU ISA v1.2 IBM/Sony/Toshiba, 27 janvier 2007](https://moss.csc.ncsu.edu/~mueller/cluster/ps3/SDK3.0/docs/arch/SPU_ISA_v1.2_27Jan2007_pub.pdf), p. 148 : contrat de ROTMAI.
- [Arm Neon Intrinsics Reference / ACLE](https://arm-software.github.io/acle/neon_intrinsics/advsimd.html), version affichée `aef52c2` : correspondances des opérations natives et instructions ; le désassemblage du candidat reste requis.
- [Arm C Language Extensions](https://arm-software.github.io/acle/main/acle.html) : disponibilité NEON et DOTPROD, distincts des extensions Matrix Multiply.
- [LLVM 22.1 Language Reference](https://releases.llvm.org/22.1.0/docs/LangRef.html) : arithmétique modulo la largeur, conversions, poison et environnement flottant. Le contrat documentaire 22.1.0 reste distinct de la version 22.1.8 construite.
- Sources matérialisées : `util/simd.hpp`, `util/v128.hpp`, les six consommateurs, `CPU/CPUTranslator.*`, `Cell/PPUTranslator.cpp`, `Cell/SPULLVMRecompiler.cpp`, CMake des identités et manifeste canonique. Les signatures ont été rapprochées d'`IntrinsicsAArch64.td` au tag `llvmorg-22.1.8`, blob `fd56e0e3f9e7b304178c4221ce4f6415d0d5c3f4`.

Les identités et le lien de livraison restent à renseigner dans le tableau de validation après téléchargement et contrôle des artefacts. Aucun changement de `main`, tag ou release publique n'est autorisé pour ce chantier. L'assemblage réussi d'une IPA ne prouve pas son installation, sa reprise ou ses performances sur l'iPhone.
