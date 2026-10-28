# RPCS3 Core 591 — durée de vie des données temporaires SPU et shaders

Le tableau de l'IPA **585** reste la référence des cinq jeux. Les mesures 586
complètent Black Ops II ; elles ne remplacent pas les autres sessions. Cette
intervention ajoute trois correctifs de code communs, sur le Core 589. Elle ne
change aucun levier de titre, réglage, format de cache, ABI ou moteur voisin.

| Jeu | Référence et problème | Correctifs inclus dans le candidat 591 | Ce qui reste à mesurer sur iPhone |
| --- | --- | --- | --- |
| Assassin's Creed | 585 : textures coûteuses et contention des réservations | Conserve les leviers 559/573 et le profil relâché déjà ajoutés en 589 ; ajoute les nettoyages communs ci-dessous | Temps de textures, attentes et cadence dans les mêmes scènes ; mémoire à chaud |
| Black Ops II | 585 : tempête PUTLLC ; 586 : contention ciblée absente, compilation et pression mémoire restantes | Conserve le profil 587 ; retire les structures LLVM résiduelles des blocs SPU finalisés, libère le scratch shader après préchargement, sécurise la reprise après erreur LLVM | Empreinte, compilations et temps d'image du même mode avec caches conservés ; aucune suppression de pause n'est annoncée |
| God of War III | Coûts historiques de textures/read-backs ; worker 581/583 et asynchrone protégé 587 | Préserve ces acquis, WCB et limite Auto ; ajoute les nettoyages communs | Mêmes savestate/scènes, rendement du worker et état réel du canari, cadence et mémoire |
| DBZ Budokai HD | Acquis mesuré de soumission anticipée ; pas de combat récent comparable | Préserve la soumission anticipée permanente et son acquis 563 ; ajoute les nettoyages communs | Combat comparable, mémoire et temps d'image ; pas de nouvel A/B permanent |
| Bladestorm | 585 : plateau stable à 30 FPS, nouvelles compilations après savestate | Préserve les leviers 575 ; les structures LLVM des nouvelles compilations ne restent plus toutes détenues jusqu'à la fermeture ; scratch shader rendu après warm-up | Pause après savestate et mémoire sur session longue. Ce patch ne supprime pas les compilations nécessaires et n'annonce pas 60 FPS |

## 1. Buffers de shaders retenus après préchargement

**Symptôme/cible :** conserver moins de données temporaires pendant le jeu,
notamment dans les sessions où la marge mémoire devient faible. La pression de
la 586 est avérée ; ces copies n'en sont pas pour autant l'origine démontrée.

**Cause dans le code :** `rsx::shaders_cache::load_fp_raw()` place une allocation
brute de fragment par pipeline dans le membre `fragment_program_data`. Après
`load()`, la file conservait ces allocations jusqu'à la destruction du renderer.
`preload_programs(nullptr, …)` a pourtant déjà fait copier l'ucode par
`search_fragment_program`/`clone_data()`. `add_pipeline_entry` compile en ligne,
sans notification disque ni capture du pointeur brut. Les deux groupes de
workers sont joints avant que `compile_shaders()` retourne, y compris à l'arrêt.

**Correction :** dans `rpcs3/Emu/RSX/rsx_cache.h`, après ces jonctions, remettre
à zéro les `unique_ptr`, puis vider la file par `pop_end(size())`. Les copies
possédées par le cache de programmes, les pipelines et le cache disque restent
intacts. Le pic pendant le préchargement n'est pas réduit.

**Validation ciblée :** vrais corps `load` et `load_fp_raw`, vrais `lf_fifo` et
helpers d'ownership des fragments, avec GPU/index remplacés par des adaptateurs.
Sur 48 pipelines de 8 Kio : 48 buffers retenus avant, zéro après ; les copies
compilées restent valides sur quatre rechargements et après annulation. Le test
rejette le nettoyage omis et le nettoyage avant compilation (use-after-free
détecté par ASan). Ce volume est celui du test hôte, pas un volume iPhone.

## 2. Structures LLVM des blocs SPU finalisés

**Symptôme/cible :** la compilation de milliers de blocs accumule du travail et
des structures de compilation pendant les sessions, dont BO2 et la reprise
Bladestorm. L'attribution de plusieurs gigaoctets à ces structures n'est pas
établie par les compteurs disponibles.

**Cause dans le code :** `jit_compiler` supprimait déjà les corps des fonctions
avec `deleteBody()`. En revanche, MCJIT continuait à posséder les Modules, leurs
déclarations et descriptors globaux pour les blocs compilés. Ils restaient dans
`OwnedModules` jusqu'à la destruction du compilateur.

**Correction :** dans `SPULLVMRecompiler.cpp::compile`, seulement après
finalisation des relocalisations, récupération de `getPointerToFunction` et
contrôle de l'entrée native, vider le point d'insertion de l'IRBuilder, retirer
le Module du MCJIT puis le détruire. Si le retrait échoue, conserver l'ancienne
propriété est le repli sûr. Le chemin `compile_interpreter` reste inchangé.

La lecture de LLVM épinglé `ca7933e47d3a3451d81e72ac174dcb5aa28b59d1` confirme
que `MCJIT::removeModule` retire le Module des ensembles de propriété, sans
libérer les objets natifs, les allocations RuntimeDyld ni leurs symboles. Les
mappings sont par noms de symboles, pas par adresse d'un ancien `Function`.
La prochaine compilation recrée les objets IR et réinitialise ses pointeurs.
Le `LLVMContext` reste vivant ; certaines constantes uniquées peuvent donc y
rester. Ce correctif ne prétend pas libérer toute la mémoire LLVM.

**Garde native exigée :** test C++ avec le véritable LLVM 22, bloc de nettoyage
extrait du code de production : retrait de 66 Modules, 64 nouveaux appelants
reliés aux fonctions/globals déjà compilés, relecture d'un véritable objet mis
en cache et rebinding du helper hôte. Les appels natifs et globals doivent
rester valides après destruction des Modules, en simple et ASan/UBSan. Un smoke
test LLVM 20 local ne remplace pas cette garde de CI.

## 3. Cache d'objets local après erreur LLVM récupérable

**Cause démontrée :** `jit_compiler::try_add(module, path, error)` installait un
`ObjectCache` local sur MCJIT, puis retournait après une erreur récupérable sans
effacer ce pointeur. Il pouvait donc désigner un objet de pile détruit pendant
l'opération suivante. Le chemin `try_add_cached` effectuait déjà ce nettoyage.

**Correction :** remettre le cache de l'engine à `nullptr` sur ce retour
d'erreur, avant la destruction de l'objet local. Aucun nouveau diagnostic.

**Test discriminant :** corps de production `try_add`, avec l'issue d'erreur
représentée par un adaptateur. L'ancien code échoue sur le pointeur résiduel ;
le nouveau passe, puis accepte une opération sans cache. Ce test ne provoque
pas une vraie erreur fatale LLVM et ne prétend pas valider un MCJIT corrompu.

## 4. Périmètre et état de validation

- Quatre fichiers natifs changent : les trois chemins ci-dessus et les alias
  exacts de `JITCacheCompatibility.cmake`. Les 301 autres fichiers du delta
  canonique sont inchangés.
- Les trois changements de comportement sont sous `RPCS3_IOS`. Leur texte
  hors iOS et le chemin interpréteur sont contrôlés contre les préimages 589.
- Les alias exacts gardent les identités PPU `a987639e9f838d1c` et SPU
  `d070cb361bdef607` : le changement de durée de vie n'altère ni émission
  d'objets ni ABI. Une autre modification future de ces fichiers invalide
  normalement leur alias. Pas de nouvelle recompilation à froid imposée.
- Les tests 591 seuls sont exécutés ; le reçu Core 589 est authentifié une
  fois. Les anciennes campagnes ne sont pas rejouées.
- Le test local Linux est explicitement partiel tant que le test C++ LLVM 22
  n'a pas tourné. La CI refuse cette preuve partielle pour construire le Core.

Cette version vise la rétention de mémoire et la sûreté de reprise. **Aucun
gain de FPS, baisse chiffrée de RAM iPhone, disparition de crash ou suppression
des pauses de compilation n'est revendiqué.** La dernière IPA livrée demeure
la 586 ; ces sources ne sont pas encore une IPA. Toute livraison suivante
doit partir de sa base vérifiée et ne contrôler que le delta et l'IPA finale.


## 5. Core iPhone compilé et vérifié

Run `40782533853`, source `12dd45b2125485614d232dd05675ceebaa6c0a1e`
(code `5ec092ca9f35314a954fb9db24f4fc7fd5785d58`) : **réussi**.
[Preuve Mac complète](evidence/rpcs3-cell591-macos.json).

- Véritable LLVM **22.1.8** sur Mac ARM64 : les tests natifs et les tests de
  propriété des shaders passent en simple et ASan/UBSan. Les 66 Modules sont
  détruits, 64 appelants ultérieurs et un objet réellement relu depuis le
  cache restent utilisables. Le code et les données natifs sont préservés.
- Core iPhone : **77 231 888 octets**, SHA-256
  `08903af6e8f2ff5ddf267c27fa3128df35d737037ec9fa359be024d5302d28f1` ;
  ABI 30, 88 exports, chargement passif et hooks MoltenVK conservés.
  Les archives du Core et des diagnostics ont été téléchargées et leurs
  digests vérifiés ; le Mach-O et l'identité ont été contrôlés à part.
- Durée du job : **12 min 47 s** ; compilation **9 min 57 s** ; nouveaux tests
  et authentification de la référence **1 min 08 s**. Pas de répétition des
  anciennes campagnes.
- `.github/diagnostics/rpcs3cell591_delivery_core.py` lie ce Core pour une
  future recette issue de la base 586, avec le profil Assassin's Creed 589.
  Le reçu et l'identité réels passent son contrat ; les entrées sont
  calculées une seule fois par processus. Ce module ne construit pas d'IPA.

Le Core est disponible dans l'artefact `12857734971`. **L'IPA 586 installée
reste sur son Core 587** : aucun résultat de jeu de la 591 n'est encore
mesuré, aucune nouvelle IPA ni release publique n'est créée ici.
