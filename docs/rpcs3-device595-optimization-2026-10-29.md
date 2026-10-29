# RewindBox — optimisations après les retours du build 595

Lot de sources préparé sur `Claude`, base `c0df3394d81d957eb7b28c85802278b69cc0f71b`,
revérifiée sur GitHub pendant le travail. Copie isolée ; les autres checkouts ne
sont pas modifiés. Aucun Core, IPA, numéro de livraison ou release n'est produit.

## Modifications retenues

Les trois changements sont limités à `RPCS3_IOS` et sont inclus dans le patch
canonique `33320812eccaf55ce7e834fe9a3a01da004e8323f0ad149cbf424a2ac3dcef9c`.
Le petit diff relisible est `test/fixtures/rpcs3_device595_allocations.diff`.

1. **Déplacement des tableaux RSX.** `simple_array::swap` transfère désormais la
   propriété de l'allocation lorsque l'un des tableaux utilise son stockage
   interne et l'autre le tas. L'ancien déplacement vers un tableau vide copiait
   tout le contenu et allouait à nouveau. Seul le contenu interne, borné, est
   recopié. Les deux tableaux vides gardent leur traitement antérieur ; les
   échanges tas/tas et interne/interne restent identiques. La capacité suit
   désormais l'allocation transférée dans le cas mixte : son historique exact
   n'est volontairement pas conservé. Taille, alignement et disposition de la
   classe ne changent pas. Le constructeur de déplacement reste `noexcept`.
2. **Cache des textures temporaires.** Chaque entrée conserve la clé encodée et
   la plage d'invalidation, au lieu du descripteur complet et de son tableau de
   régions à copier. Ce sont les seuls champs relus par les consommateurs du
   cache. Les copies/mises à jour utilisent toujours la requête courante. Les
   invalidations, les libérations de vues et le nettoyage de fin de frame sont
   inchangés. Les handles d'images concernés sont des pointeurs non propriétaires,
   avec une assertion de type à la compilation.
3. **Recherche d'adresse.** Après `lower_bound`, une absence ou une adresse unique
   retourne directement. Les adresses dupliquées gardent la recherche de fin et
   leur ordre exact. Le seuil de 16 sections, l'index, ses verrous, la validation
   mémoire et le parcours de présentation restent inchangés.

## Résultats vérifiés

Six modes natifs ciblés passent sous GCC 13.3 sur Linux x86_64 : chacun des trois
tests en mode optimisé et avec AddressSanitizer/UndefinedBehaviorSanitizer.
Les assertions sont actives. Ce ne sont pas des exécutions ARM64/iPhone.

| Contrôle | Résultat |
| --- | --- |
| Tableaux complets avant/après + branche desktop | 726 336 comparaisons de contenu/alignement par mode ; copies, déplacements, échanges, auto-déplacements, réutilisation et allocations libérées vérifiés |
| Déplacement d'un tableau de 4 096 régions de 40 octets | 1 allocation de 163 840 octets avant ; 0 après, même contenu et pointeur de tas transféré |
| Cache temporaire | 12 422 contrôles par mode ; mêmes hits, mises à jour, invalidations et libérations |
| Cache, six insertions de tailles 0/1/2/8/64/256 | Avec le nouveau tableau dans les deux variantes : 8 allocations de recettes, 26 400 octets avant compaction ; 0 après |
| Valeur d'entrée du cache dans l'adaptateur hôte | 152 → 32 octets, hors nœud/allocateur de la table ; ce n'est pas une mesure RSS iPhone |
| Recherche et cycle de vie des sections | 22 753 requêtes, 8 618 mutations par mode ; même première correspondance, ordre de validation et appartenance aux plages |
| Matérialisation canonique depuis les préimages amont | 314 empreintes vérifiées ; 311 anciennes postimages inchangées, deux modifiées, une nouvelle |
| Contrat de liaison statique | Tous les symboles chargés par l'hôte restent exportés |

Le test des tableaux instrumente son allocateur hôte pour détecter les doubles
libérations et allocations encore vivantes. LeakSanitizer n'a pas pu fonctionner
dans cet environnement (`Can't open /proc/11/task`, environnement sous ptrace).
Son premier échec est conservé ici ; les modes ASan/UBSan ont ensuite été lancés
avec `--leak-check disabled`. Ne pas présenter ces résultats comme un passage LSan.
Le test existant de recherche désactive déjà LSan. Deux corrections ont concerné
uniquement le nouveau harnais : déclaration de `size32` manquante, puis frontière
de ligne vide dans la vérification d'extraction. Aucun garde produit n'a été retiré.

Le premier contrôle du cache, avant le changement des tableaux, mesurait
12 allocations/39 600 octets pour les mêmes six insertions. Son résultat reste
dans `temporary-cache-only-plain.json` comme étape intermédiaire ; les preuves
finales sont `temporary-plain.json` et `temporary-asan.json`. Le test final isole
la compaction du cache en utilisant le nouveau tableau dans les deux variantes.
Les interactions de propriété des tableaux sont vérifiées séparément sur les
classes complètes avant/après.

Toutes les mesures de recherche sont conservées dans `address-plain.json`, y
compris les régressions : avec 256 sections, une absence passe de 17,27 à 9,13 ns,
mais le recyclage passe de 94,85 à 95,55 ns ; avec 1 024 sections, de 258,99 à
271,37 ns pour le recyclage. Les petits blocs gardent le même chemin et présentent
aussi des variations défavorables. Aucun pourcentage de FPS n'en est déduit.

## Confrontation aux fichiers et au retour utilisateur

`observed-build595.json` conserve les empreintes des sept fichiers fournis,
les fenêtres retenues et les réglages observés. Les rotations ont été séparées
par build/PID/session : une partie du fichier précédent appartient au build 594.
Les deux vidéos plus anciennes ne constituent pas un A/B de ce nouveau lot.

| Jeu | État établi pour le build 595 |
| --- | --- |
| BO2 BLES01717 | Amélioration rapportée par le mainteneur, mais saccades et défauts armes/avant-bras persistants. Fenêtres 8–13 de session 2 : 28,58–41,06 FPS calculés sur les intervalles invités, textures échantillonnées 4,62–7,13 ms/frame. |
| GOW3 BCES00510 | Aucun progrès rapporté, gel reproductible. À 19:06:56 UTC : attente RSX sur `0x60300510`, attendu `0x6F0E`, observé `0x6F0D` après 2 000 225 µs. Aucun événement de résolution dans les jalons disponibles. L'origine du signal absent n'est pas prouvée. |
| Assassin's Creed BLES00158 | Scintillement des torches et stutters rapportés. Fenêtres 18–36 de session 5 : 27,40–38,36 FPS, textures 3,78–7,23 ms/frame. La fenêtre 18 n'effectue aucune compilation de shader et présente pourtant un p95 de 48,62 ms. La compilation ne suffit donc pas à expliquer ces saccades. |

Les trois titres chargent le recompilateur de shaders legacy. AC active le
streaming asynchrone des textures ; BO2 et GOW3 le désactivent. GOW3 charge encore
une configuration personnalisée (résolution 75 %, SPU Mega, WCB actif, bypass
MLAA actif). Ces constatations ne prouvent pas la cause des défauts et aucun
réglage utilisateur n'a été écrasé.

Les 737 échantillons NeoSwap sont du build 595/PID 50728 : aucun compteur d'erreur
I/O, avertissement mémoire iOS ou donneur perdu ; état thermique 1 sur cette
capture. Le ledger de mémoire compressée reste néanmoins entre 1,10 et 1,66 Gio.
Ces compteurs n'excluent pas un coût de pagination et ne justifient pas de modifier
les budgets de mémoire à l'aveugle.

## Pistes écartées et prochaine validation

La réutilisation du tampon d'indices pour émuler primitive-restart a été retirée :
le chemin est activé pour un ancien GPU AMD, pas pour MoltenVK. La recherche rapide
supplémentaire d'une texture sans verrou n'a pas été conservée : certains appelants
ne garantissent pas la protection de l'index. Les convertisseurs ARM64, JIT/LLVM,
hashes de textures, labels invités et barrières GPU ne sont pas modifiés sans
preuve d'équivalence suffisante. Les politiques existantes et leurs résultats
Apple restent historiques ; aucun test inchangé n'a été relancé.

Prochaine étape technique : valider ces trois chemins avec Apple Clang/ARM64,
puis la prochaine compilation de Core explicitement autorisée et les mêmes scènes
sur iPhone. Les routes de livraison actuelles restent épinglées à leur Core
historique ; ce lot n'est pas admissible comme ancien binaire validé. Un futur
préflight doit authentifier les sources inchangées et exécuter les modes affectés,
pas rejouer toute la chaîne historique.

Pour les défauts persistants, les axes prioritaires restent le producteur du label
GOW3, la cohérence des textures/rendus réutilisés pour les armes BO2 et les torches
d'AC, puis le coût des soumissions et du streaming de textures sous MoltenVK.
Le transfert des tableaux et la compaction du cache sont des réductions de travail
CPU établies, **pas des corrections démontrées de ces trois symptômes**.

Les résultats existants se réauthentifient sans compilation :

```sh
python test/rpcs3_device595_delta_test.py /path/to/candidate-core \
  --baseline /path/to/core-from-c0df3394 \
  --report /tmp/device595-verification.json
```

Les trois programmes à exécuter sur une nouvelle plateforme sont
`test/rpcs3_device595_test.py --case array`, le même avec `--case temporary`,
et `test/rpcs3_texture_address_index_test.py`, avec source, `--baseline` et
`--report`, en mode ordinaire et `--sanitizer address,undefined`.
