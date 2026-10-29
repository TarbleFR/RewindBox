# RPCS3 iOS — optimisations des coûts récurrents, 29 octobre 2026

## Modifications livrées

Source enregistrée sur `Claude` :
[`5f46a6cf`](https://github.com/TarbleFR/RewindBox/commit/5f46a6cfbaf8a3c2994afe034fc2d5a098d03269).
Le [contrat commité](evidence/rpcs3-global-20261029/committed-contract.json)
authentifie ses **225 entrées de dépôt, 313 postimages RPCS3, 97 sources
complémentaires et 16 rapports natifs**, ainsi que les 19 contrôles de rejet.
L'arbre source distant est identique à l'arbre vérifié localement.

Cinq optimisations sont implémentées dans le moteur : lecture d'horloge MFC
conditionnelle, compaction du timer SPU, cache des descripteurs Vulkan séparé
par type de pipeline, partage des hashes synchrones de textures et suppression
des balayages NeoSwap sans retrait en attente. Six fichiers du delta RPCS3 et
un fichier du stockage hôte changent. Le module de compatibilité des caches
est compris dans ces six fichiers.

La baseline de ce lot est le commit
[`3e4fcfa1`](https://github.com/TarbleFR/RewindBox/commit/3e4fcfa121e01fd08934486b833dde6a69a2d318),
qui contient déjà les correctifs après les journaux iPhone 594. Le présent lot
les conserve. Les [correctifs FIFO, textures et transitions de shaders](rpcs3-device594-followup-2026-10-29.md)
ne sont pas présentés comme de nouvelles optimisations CPU de ce lot.

Les **16 modes natifs ciblés exécutés sur Linux x86_64 passent** : sept modes
optimisés, sept ASan/UBSan et deux TSan. Une mesure séparée du hachage et une
vérification CMake des identités de cache passent également. Les résultats
ci-dessous sont des mesures hôte et des réductions de travail vérifiées.
**Aucun gain de FPS, aucune amélioration visuelle et aucune résolution du gel
sur iPhone ne sont encore mesurés avec ce code.** Aucun Core, IPA, numéro de
livraison, tag ou release n'est créé par ce lot source.

## 1. SPU : supprimer la lecture d'horloge sans effet

Dans `spu_thread::do_mfc()`, le masque d'exécution lisait toujours `get_tsc()`.
Lorsque le mélange des commandes vaut zéro, les bits aléatoires sont pourtant
entièrement neutralisés. Sur ARM64, cette fonction contient une lecture du
compteur matériel ; le changement évite cet appel lorsqu'il ne peut modifier
le résultat.

Le masque reste entièrement actif dans ce cas. La file vide bénéficie du même
raccourci, même si un mélange est configuré. Avec une file non vide et un
mélange 1–16, l'expression et la lecture du compteur restent présentes.
La fonction `do_mfc()` poursuit son exécution : aucun transfert, tag, contrôle
de barrière ou traitement d'interruption n'est sauté.

Les contrôles [optimisés](evidence/rpcs3-global-20261029/spu-mfc-plain.json)
et [ASan/UBSan](evidence/rpcs3-global-20261029/spu-mfc-asan-ubsan.json) distinguent :

- 18 939 904 comparaisons mathématiques du masque, couvrant toutes les valeurs
  des 16 bits consommés du compteur et les tailles/limites 0–16 ;
- 78 336 scénarios, soit 235 008 appels du vrai exécuteur `do_mfc()` ;
- 13 824 lectures du compteur avec limite zéro dans la référence, **zéro dans
  le candidat** ;
- 48 960 livraisons de tags, 113 832 barrières et 85 779 reprises de listes
  identiques ; 4 944 échappements d'interruption sur file vide conservés.

Les transferts DMA et les canaux périphériques sont des adaptateurs qui
enregistrent leurs appels. Ce test ne simule pas l'intégralité du CELL.

Sur le **masque seul**, sept séries d'un million d'appels donnent une médiane
de **11,608 → 1,624 ns** lorsque le mélange vaut zéro. Ce chiffre ne mesure
ni l'exécuteur complet, ni le coût ARM64 sur iPhone.

## 2. SPU : compacter les échéances en un passage

Le worker `spu_dec_intr_timer::operator()()` effaçait chaque échéance expirée
du vecteur `armed`. Chaque effacement pouvait redéplacer les mêmes éléments
restants. Un lot d'expirations provoquait donc un travail quadratique.

Le nouveau code applique une compaction stable, puis efface un seul suffixe.
Chaque survivant est déplacé au plus une fois. L'ordre des échéances et des
notifications, les tokens de génération et le calcul du prochain réveil
restent identiques. Les callbacks continuent de s'exécuter après libération
du mutex et avec rétention de l'instance SPU concernée.

La capacité du lot d'échéances est réservée à la première expiration,
avant tout déplacement. Il n'y a aucune allocation si rien n'expire.
L'entrée est triviale et ses déplacements ne lèvent pas d'exception ; un
échec de cette première allocation laisse la file intacte. Le lot temporaire
est borné par le nombre d'entrées armées et n'ajoute pas de cache permanent.

Les [tests optimisés](evidence/rpcs3-global-20261029/spu-timer-plain.json) et
[ASan/UBSan](evidence/rpcs3-global-20261029/spu-timer-asan-ubsan.json) couvrent
210 combinaisons, un réarmement réentrant, l'arrêt après réveil et deux
échecs d'allocation injectés. Ils vérifient 636 comparaisons d'ordre et
d'échéance, 2 172 notifications identiques et 6 145 tokens obsolètes refusés.

| Travail dans ces scénarios | Référence | Candidat |
|---|---:|---:|
| Effacements non vides | 10 357 | 277 |
| Emplacements décalés par les `erase` | 960 340 | 0 |
| Allocations des lots d'échéances | 1 065 | 277 |

Le zéro concerne les décalages des effacements répétés : la compaction
elle-même peut déplacer les survivants. Pour six échéances simultanées,
le balayage extrait avec de vrais vecteurs et un mutex hôte mesure
**133,345 → 51,167 ns**. Le contrôle sans expiration mesure
**26,964 → 29,088 ns**. La fréquence de ces lots dans les jeux n'est pas
établie par les journaux disponibles.

## 3. Vulkan : conserver séparément les bindings graphics et compute

Le cache précédent partageait ses handles de descripteurs entre les deux
types de pipeline et ignorait le layout ainsi que le nombre exact de sets.
Il pouvait oublier un binding graphics toujours valide après un usage
compute, ou supprimer à tort un bind lorsque les mêmes handles étaient
employés avec un autre layout ou bind point.

Sous iOS, deux entrées bornées conservent désormais le layout exact, le
nombre de sets et leurs handles. Un appel n'est supprimé que si ces données
correspondent pour le même type de pipeline. Les offsets dynamiques restent
transmis à chaque appel et invalident seulement l'entrée concernée.
Le véritable début d'un enregistrement invalide les deux entrées.

Cette séparation suit les états indépendants définis par
[`vkCmdBindDescriptorSets`](https://docs.vulkan.org/refpages/latest/refpages/source/vkCmdBindDescriptorSets.html).
Le code n'infère aucune compatibilité entre layouts différents. `firstSet`
reste zéro, comme dans les deux wrappers existants.

Les tests compilent les vraies déclarations, les deux surcharges de bind,
les cycles `begin/reset/end`, `program::bind()` et
`descriptor_table_t::commit()`. Ce dernier retourne réellement le même handle
lorsque ses descripteurs sont propres ; la réutilisation existe donc dans
un chemin de production. Les frontières du driver et des allocations GPU
restent modélisées.

| Trace contrôlée | Émissions avant | Émissions après |
|---|---:|---:|
| 128 demandes alternant graphics/compute à état stable | 128 | 2 |
| 32 demandes via les vrais `program::bind/commit` | 32 | 2 |
| 36 demandes avec changement de descripteur et retour d'overlay | 36 | 5 |
| 33 demandes avec compute à offsets dynamiques | 33 | 17 |
| 64 demandes graphics identiques | 1 | 1 |
| 64 changements de handles | 64 | 64 |

Les allocations restent respectivement trois et cinq dans les deux cas
`program::bind`. Aucun verrou ni allocation de cache n'est ajouté. L'empreinte
de la classe dans l'adaptateur iOS passe de 288 à 336 octets, soit **48 octets
par command buffer**, sans augmentation de leur nombre. Le chemin desktop
reste identique à sa baseline.

Les 20 scénarios, dont 4 096 opérations mixtes, passent avec **zéro écart
d'état**, contre 1 141 dans les contrôles historiques. Le total des émissions
de tous ces scénarios augmente : des binds auparavant omis à tort sont
rétablis. Il ne constitue donc pas une mesure de performance globale.

Sept séries de deux millions d'opérations, avec driver réduit à un compteur :

| Wrapper hôte | Avant | Après |
|---|---:|---:|
| Hits graphics purs | 1,076 ns/op | 1,504 ns/op |
| Handles changeants, aucun bind évité | 8,995 ns/op | 8,483 ns/op |
| Alternance graphics/compute stable | 4,926 ns/op | 1,598 ns/op |

Ces nombres excluent le coût réel Vulkan/MoltenVK/Metal. Les
[rapports optimisé](evidence/rpcs3-rsx-bind-20261029/descriptor-bind-plain.json)
et [ASan/UBSan](evidence/rpcs3-rsx-bind-20261029/descriptor-bind-asan-ubsan.json)
contiennent les résultats par scénario et leurs empreintes.

## 4. Textures : partager un hash synchrone déjà calculé

Seul le worker publiait ses résultats dans la table de prehash. Après un
miss, le thread RSX calculait le même hash mais ne le partageait pas.
Une autre section de plage identique, ou le worker encore en avance sur
cette plage, pouvait donc recalculer les mêmes octets dans la même époque.

`buffered_section::sync()` publie maintenant son résultat réellement calculé
si le prehash est actif, la plage atteint 64 KiB, l'époque est non nulle et
reste courante, et aucune écriture ciblée n'impose un bypass. La clé conserve
l'adresse et la longueur exactes. Le worker consulte déjà la table avant
son calcul : son code reste inchangé.

`publish()` réserve le slot par **une seule tentative de CAS**, sans attente
ni spin. Un producteur concurrent fait abandonner la publication ; la
validation reste possible par le chemin normal. Les champs, la capacité et
les allocations de la table restent inchangés. Les validations après écriture
ciblée gardent leur propre hash et ne publient pas ce résultat.

Le changement agit lorsque le prehash est activé. Son activation automatique
actuelle reste réservée à GOW3 ; aucun nouveau réglage joueur ni extension
de liste de jeux n'est ajouté.

| Travail déterministe vérifié | Référence | Candidat |
|---|---:|---:|
| Hashes pour 96 validations de huit alias sur 12 époques | 96 | 12 |
| Octets hachés dans ce cas | 6 291 456 | 786 432 |
| Hashes pour 32 plages distinctes | 32 | 32 |
| Sections chevauchantes modifiées rejetées | 3/3 | 3/3 |
| Hashes du vrai worker dans le scénario de partage | 3 | 2 |

Les contrôles couvrent aussi le reset d'une section, l'avance d'époque
pendant le calcul, les publications tardives, les collisions et les chemins
désactivés. Quatre mutations sont rejetées : réutilisation supprimée,
bypass supprimé, époque ignorée et retour à un unique producteur non protégé.

Le stress candidat effectue **500 000 tentatives de publication** et
500 000 recherches sur un même slot. Les publications abandonnées ne sont
pas comptées comme des succès. Chaque résultat accepté est vérifié ; les
trois modes observent effectivement des succès. Les tests
[plain](evidence/rpcs3-global-20261029/texture-hash-reuse-plain.json),
[ASan/UBSan](evidence/rpcs3-global-20261029/texture-hash-reuse-asan-ubsan.json)
et [TSan](evidence/rpcs3-global-20261029/texture-hash-reuse-tsan.json) passent,
sans suppression TSan. Le modèle des trois chevauchements stimule leurs
invalidations explicitement ; les deux modes scoped-write ci-dessous
réexécutent aussi les vrais parcours d'invalidation.

### Mesure séparée et limites

Le [reçu primaire de mesure seule](evidence/rpcs3-global-20261029/texture-hash-reuse-benchmark.json)
utilise sept paires alternées, une affinité CPU, le worker garé par attente
atomique sans spin et les observations de hash retirées du chronométrage.
Le buffer de séquence existant est préalloué. Le CPU hôte n'est pas garanti
exclusif et cette mesure exclut l'ordonnancement du réveil d'époque.

Médianes en microsecondes par validation, pour huit sections :

| Taille | Même plage : avant → après | Plages distinctes : avant → après |
|---|---:|---:|
| 32 KiB, sous le seuil de partage | 1,795 → 1,986 | 1,805 → 1,846 |
| 64 KiB | 4,699 → 0,635 | 3,519 → 3,869 |
| 256 KiB | 16,284 → 2,330 | 19,618 → 19,571 |
| 1 MiB | 58,933 → 7,131 | 62,934 → 67,307 |
| 3 686 400 octets | 213,833 → 25,694 | 211,804 → 227,521 |

Le bénéfice démontré dépend des plages répétées. Les médianes distinctes
restent plus élevées dans plusieurs cas, dont +9,94 % à 64 KiB. Les séries
64 KiB couvrent 3,413–3,984 µs avant et 3,337–3,990 µs après. Le contrôle
32 KiB varie aussi sans publication ; on ne peut attribuer tout cet écart
au CAS. La première mesure, plus bruitée, reste conservée dans le reçu plain.

La proportion réelle de plages répétées par époque n'est pas connue pour
la scène GOW3. **Aucun bénéfice net par image n'est affirmé.** Les compteurs
existants de hits couvrent maintenant le worker et les producteurs synchrones ;
ils ne doivent plus être utilisés seuls pour attribuer tout le travail servi
au worker. Aucune nouvelle télémétrie applicative n'est ajoutée.

## 5. NeoSwap : éviter la collecte lorsqu'aucun retrait n'attend

`Store::Impl::run()` appelait `collect_discarded()` avant chaque travail et
au réveil périodique. La fonction parcourait toutes les entrées et cherchait
leurs jobs en file, y compris lorsqu'aucune entrée n'avait été retirée.

Un drapeau privé `discarded_pending`, protégé par le mutex existant, permet
un retour immédiat dans ce cas. Lorsqu'une collecte est nécessaire, les
entrées non retirées ne parcourent plus la file des jobs. Toute entrée retenue
par un lecteur, un job ou un état busy maintient le drapeau. Un effacement
explicite peut laisser un faux positif, éliminé au prochain passage, sans
perdre de retrait. Le trim continue de s'exécuter.

Les quotas, la compression, les formats, les lectures et écritures réelles,
le CRC, les synchronisations disque et les leases ne changent pas.

Les trois modes [plain](evidence/rpcs3-global-20261029/neoswap-discard-plain.json),
[ASan/UBSan](evidence/rpcs3-global-20261029/neoswap-discard-asan.json) et
[TSan](evidence/rpcs3-global-20261029/neoswap-discard-tsan.json) passent :
96 000 opérations différentielles, 124 861 audits de métadonnées et les
**11 cas existants du Store réel**, avec fichiers POSIX, mmap, compression,
concurrence, leases, erreurs injectées et réutilisation des extents.

Le microbenchmark de collecte porte uniquement sur les métadonnées. Avec
1 024 entrées vivantes et 16 jobs, aucun retrait en attente mesure
**10,340 µs → 0,00179 µs** par appel ; avec une entrée retirée mais bloquée,
**10,713 → 5,114 µs**. Un seul retrait bloqué sans autre entrée mesure
**3,522 → 4,154 ns**. Aucun de ces chiffres ne mesure une restauration NAND,
la boucle complète du worker ou le gameplay.

## Compatibilité, tests réutilisés et compilation

Le patch canonique contient toujours 313 postimages. **Six changent, 307
restent identiques** à la baseline de ce lot. Le patch unique est rematérialisé
sur 178 préimages amont exactes et ses 135 fichiers ajoutés, avec 215 blobs
amont authentifiés au total en incluant les suppléments. Voir le
[reçu d'intégration](evidence/rpcs3-global-20261029/canonical-integration.json).

Les contrôles de source/recette, l'ABI 30, les 88 exports et les directives
conditionnelles de 264 fichiers passent. Les dépendances réellement employées
sont consignées dans [host-environment.json](evidence/rpcs3-global-20261029/host-environment.json).
La validation Linux utilise GCC 13.3 ; l'en-tête officiel LZ4 1.9.4 correspond
à la bibliothèque installée. LeakSanitizer est désactivé ; ASan et UBSan sont
actifs dans les modes concernés.

### Identités des caches PPU/SPU

Les changements SPU concernent deux fonctions hôtes appelées à l'exécution.
Les générateurs, l'analyseur, la structure SPU, les symboles et les cibles
de relocation restent identiques. L'alias de compatibilité est actualisé
pour le **hash exact** de ce fichier, sans correspondance générique.

La [preuve dédiée](evidence/rpcs3-global-20261029/spu-cache-identity.json)
authentifie 41 entrées de codegen : 40 fichiers physiques et le postimage
LLVM externe déjà épinglé. Une seule exécution de CMake 3.31.6 en mode
script vérifie les identités et les contre-exemples ; aucune configuration
ou compilation du Core n'est lancée.

| Source | PPU | SPU |
|---|---|---|
| Baseline | `a987639e9f838d1c` | `d070cb361bdef607` |
| Candidat avec alias exact | `a987639e9f838d1c` | `d070cb361bdef607` |
| Candidat sans cet alias | `a987639e9f838d1c` | `d51127b0f85ff252` |
| Modification future non reconnue | `a987639e9f838d1c` | `8543982eead10b72` |

Un mauvais chemin est également refusé. Ces optimisations n'imposent donc
pas de recompilation à froid des caches PPU/SPU existants.

### Suites réellement rejouées

Deux programmes historiques ont effectivement changé : viewport/scissor
inclut le nouveau `clear_state_cache`, et scoped-write inclut le nouveau
`sync/publish`. Leurs quatre modes ont été réexécutés. Le stimulus historique
est conservé ; seule la déclaration du cache de l'extracteur viewport est
adaptée à la source native.

- Viewport/scissor : 10 000 draws répétés, 20 000 aléatoires, 56 cas binaires
  et 514 masques passent en [plain](evidence/rpcs3-rsx-bind-20261029/viewport-scissor-plain.json)
  et [ASan/UBSan](evidence/rpcs3-rsx-bind-20261029/viewport-scissor-asan-ubsan.json).
- Scoped-write : 2 808 écritures, 96 scénarios de bindings et 200 courses
  passent en [plain](evidence/rpcs3-global-20261029/rsx-write-sampler-plain.json)
  et [ASan/UBSan](evidence/rpcs3-global-20261029/rsx-write-sampler-asan-ubsan.json).
  Les contrôles historiques restent reproduits ; aucun payload périmé
  n'est accepté par le candidat dans le modèle.

Les sept autres programmes déjà réussis sur Apple restent identiques,
soit **16 modes réutilisés sans exécution**. Les cinq programmes du lot
device594 restent également identiques et leurs dix modes Linux ne sont
pas rejoués. Le prochain build Apple explicitement demandé devra exécuter
**26 modes** : ces dix modes encore en attente, les douze nouveaux modes et
les quatre modes historiques réellement modifiés.

Le nouveau gate vérifie les sources et programmes exacts, reconstruit chaque
baseline, réauthentifie la preuve CMake et les reçus. Le script
`test/rpcs3_global_contract_test.py` relie les 16 rapports au commit source
et rejette 19 reçus volontairement altérés. Cette authentification ne lance
aucun compilateur ni suite native. Les compteurs complets du test scoped-write
ont été renforcés à la suite de la revue indépendante du gate ; une simple
valeur `passed` ne masque plus un payload périmé ou un scénario absent.

## Croisement avec les mesures iPhone et les pistes déjà traitées

Les nouvelles traces utilisées restent celles du build 594, processus 49019.
Les intervalles de rendu retenus sont documentés et reproductibles dans
[l'analyse device594](rpcs3-device594-followup-2026-10-29.md) et son
[extraction chiffrée](evidence/rpcs3-device594-20261029/device-observations.json).

| Jeu / intervalle | Observation sur 594 | Mesure avec ce candidat |
|---|---|---|
| BO2, session 2, fenêtres 7–21 | 23,08 FPS calculés, 91 images >50 ms, 36 >100 ms | Non disponible |
| Assassin's Creed, session 3, fenêtres 22–36 | 27,09 FPS calculés, 221 images >50 ms, 11 >100 ms | Non disponible |
| GOW3 restauré, session 5, fenêtres 3–19 | 16,67 FPS calculés, 946 images >50 ms, 38 >100 ms | Non disponible |

Ces parcours ne sont pas un A/B de scènes et d'états thermiques identiques.
Ils ne fournissent pas un nouveau 1 % low, ni une amélioration moyenne du candidat.

**BO2.** Les 46 longues créations de pipelines de sa session cumulent
27,446 s, dont 23,168 s de bibliothèques fragment ; les adresses de modules
fragment sont distinctes. Le cache de bindings réduit du travail récurrent
mais n'est pas présenté comme supprimant ces premières compilations Metal.
Les correctifs de transition et d'upload du lot précédent restent à valider
sur les armes et l'avant-bras.

**Assassin's Creed.** L'intervalle retenu n'a aucune compilation graphique.
Ses 15 opérations SPU codegen cumulent 150,571 ms. Le temps cumulé des
57 161 soumissions synchrones atteint 18,999 s et le coût texture observé
reste de 3,508 à 9,465 ms/image échantillonnée. Les optimisations de cache
Vulkan concernent ce travail récurrent. Un préchauffage supplémentaire ne
découle pas de cette plage. Le flickering des torches reste à vérifier sur GPU.

**GOW3.** Les 306,559 Go hachés et 23,884 s cumulées incluent déjà le worker
(200,302 Go et 15,467 s) : ne pas additionner ces valeurs. Le partage des
hashes vise cette charge, sous réserve de mesurer la fréquence réelle des
plages répétées. Les 1 491 readbacks sur faute CPU, 5,493 Go et 5,577 s,
ne sont pas supprimés. Tester `should_flush()` avant `copy_texture()` a été
écarté : sa barrière peut résoudre un héritage ou initialiser des données
qui deviennent ensuite flushables. Les retirer pourrait perdre des octets
nécessaires au jeu.

Le gel GOW3 signalé reste ouvert. Le seul nouveau snapshot de gel appartient
à BO2 ; les traces GOW3 594 continuent de produire des images jusqu'à l'arrêt.
Les valeurs de labels ne sont jamais forcées. La sémantique complète GET,
les commandes de contrôle et la sauvegarde/restauration exigent une preuve
commune avant un backport plus large.

**Budokai HD.** L'[A/B historique](evidence/rpcs3-cell563-dbz-ab-measured.json)
avait établi environ +1,8 FPS médian et −1,7 ms de readback par image avec
les soumissions anticipées, sur ses scènes contrôlées. Cette optimisation
déjà intégrée reste présente ; ce gain ne vient pas du nouveau lot. Aucun
nouveau parcours Budokai comparable n'est fourni. Les anciens raccourcis
de readback anticipé, la désactivation générale de WCB et les modifications
non prouvées de réservations restent écartés.

## Fichiers modifiés et suite utile

| Fichier moteur | Changement de ce lot |
|---|---|
| `rpcs3/Emu/Cell/SPUThread.cpp` | Masque MFC et compaction des échéances |
| `rpcs3/Emu/CPU/JITCacheCompatibility.cmake` | Alias du seul hash runtime vérifié |
| `rpcs3/Emu/RSX/VK/vkutils/commands.h` | Deux états bornés de descripteurs |
| `rpcs3/Emu/RSX/VK/vkutils/commands.cpp` | Déduplication exacte et invalidations |
| `rpcs3/Emu/RSX/Common/texture_cache.cpp` | Publication du hash synchrone éligible |
| `rpcs3/ios/IOSTexturePrehash.h` | Publication multi-producteurs non bloquante |
| `native/neoswap-storage/Store.cpp` | Collecte conditionnelle des retraits |

Les six premiers fichiers sont intégrés dans
`build-utils/rpcs3/embedded-core.patch`. Le manifeste, son pin, la fixture
réversible, les tests ciblés et la route du contrôle Apple sont actualisés.
Les conditions de déclenchement du build restent inchangées. Les changements
de la livraison 594 et de MeloNX sont conservés.

Les prochaines optimisations doivent être décidées sur trois résultats :

1. **Coût net par image des plages répétées GOW3.** Comparer le même parcours,
   les octets réellement hachés, le temps RSX et les longues images ; garder
   visibles les cas distincts sans gain et les lectures CPU nécessaires.
2. **Premières bibliothèques fragment BO2.** Relier modules, variantes et
   réutilisation réelle avant de supprimer une compilation. Conserver les
   limites mémoire/concurrence déjà validées, sans interpréteur graphique,
   compilation SPU différée ni draws sautés.
3. **Rendu AC/BO2 et reprise GOW3.** Exécuter les scènes signalées avec le
   candidat compilé et mesurer les temps d'image au même état de cache et
   thermique. La correction des contrats source ne prouve pas encore la
   disparition des artefacts ou du gel. Un backport FIFO plus large reste
   conditionné à la préservation de la sauvegarde et des vrais producteurs
   de synchronisation.

L'émission PPU/SPU LLVM, les calculs flottants et les chemins NEON déjà
intégrés ne sont pas remplacés par des approximations. La progression
vérifiée ici porte sur le travail runtime supprimé et sa compatibilité,
avec les mesures sur iPhone encore à faire.
