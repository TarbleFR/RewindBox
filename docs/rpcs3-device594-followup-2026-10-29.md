# RPCS3 — corrections après les journaux iPhone 594

Ce travail part du build **594 livré**, du Core
[fe587e27](https://github.com/TarbleFR/RewindBox/commit/fe587e27fcefadaa36315a3ddc7dc1edba17b825)
et de Claude à
[c609b0d](https://github.com/TarbleFR/RewindBox/commit/c609b0d05a583d2d39f636f328830a6256439807).
Les corrections de cohérence CPU/RSX, de présentation MoltenVK, de compilation
BO2, les accès indexés aux textures et les clés déterministes de framebuffer
étaient déjà embarqués. Elles ne sont pas comptées à nouveau.

Les changements ci-dessous concernent **cinq fichiers natifs**. Ils ont des
tests ciblés sur Linux x86_64, sans nouveau Core Apple, IPA ou release. Aucun
gain de FPS ni disparition des symptômes sur iPhone n'est établi.

Le premier dossier temporaire a disparu après l'interruption de la session,
avant son enregistrement sur Claude. Les changements et adaptateurs ont été
restaurés depuis les sources authentifiées. Les résultats présents ici sont
ceux des **nouvelles exécutions**, avec leurs propres empreintes et compteurs.
Les anciens reçus temporaires ne sont pas présentés comme des fichiers conservés.

## Ce que montrent les nouveaux journaux

L'analyse sélectionne seulement le build 594, PID 49019 : 427 lignes dans
le fichier de performances tournant et 2 534 dans le courant. Elle écarte
les 3 163 lignes 593 du premier fichier et n'additionne pas les copies du
journal diagnostic. Les empreintes, fenêtres et lignes sources sont dans
[device-observations.json](evidence/rpcs3-device594-20261029/device-observations.json).
Le script [observations.py](evidence/rpcs3-device594-20261029/observations.py)
reproduit les résultats à partir des quatre fichiers JSONL fournis.

Les FPS valent nombre d'intervalles / durée totale de ces intervalles. Ces
fenêtres de rendu invité peuvent inclure des transitions ou cinématiques.
Elles ne constituent ni un comparatif contrôlé avec 593, ni une mesure du
candidat corrigé.

| Jeu et intervalle | Intervalles | Durée | FPS calculés | Intervalles > 50 ms |
|---|---:|---:|---:|---:|
| BO2, session 2, fenêtres 7–21 | 1 711 | 74,140 s | 23,08 | 91 |
| Assassin's Creed, session 3, fenêtres 22–36 | 2 107 | 77,779 s | 27,09 | 221 |
| GOW3 restauré, session 5, fenêtres 3–19 | 1 489 | 89,296 s | 16,67 | 946 |

**BO2.** Sur l'ensemble de la session 2, 46 créations de pipelines signalées
comme lentes totalisent 27,446 s, dont 23,168 s dans les bibliothèques fragment
Metal. La plus longue dure 922,454 ms. Les 46 adresses de modules fragment sont
distinctes ; cela ne démontre pas des recompilations répétées du même shader.
Ces totaux de session ne sont pas confondus avec la fenêtre du tableau.
L'unique capture de gel 594 survient dans BO2 pendant une création de pipeline
enregistrée comme terminée, au milieu de plusieurs compilations. La capture
indique 4,096 s sans frame ; elle ne démontre pas que l'opération individuelle
explique à elle seule cette durée, ni l'origine des défauts des armes.

**Assassin's Creed.** Dans l'intervalle à 27,09 FPS, aucune création de pipeline
graphique n'est enregistrée. La génération de code SPU compte 15 opérations
pour 150,571 ms. Les 57 161 soumissions synchrones totalisent 18,999 s et la
préparation des textures varie de 3,508 à 9,465 ms par frame échantillonnée.
Ces cumuls peuvent recouvrir d'autres travaux et ne sont pas du temps
intégralement récupérable. Les 152 échantillons thermiques valent 2.

**GOW3.** La présentation asynchrone est active, avec deux queues d'exécution
et zéro attente complète de secours dans l'intervalle retenu. Cela confirme
un comportement déjà corrigé ; cela ne prouve aucun FPS supplémentaire.
Le hachage de textures représente 306,559 Go et 23,884 s cumulées. Ce total
**inclut** les 200,302 Go et 15,467 s du worker. Les lectures GPU sur faute CPU
concernent 1 491 sections, 5,493 Go et 5,577 s cumulées. Write Color Buffers
et le bypass MLAA sont tous deux actifs.

La mémoire dans ces fenêtres GOW3 va de 4 144 à 5 213 Mio, avec 1 442 Mio
de marge minimale. Les échantillons de mapping ne montrent ni échec ni perte
de donneur pour AC ou GOW3. Ces données ne justifient pas davantage de mémoire
NeoSwap.

**Le gel GOW3 rapporté reste ouvert.** Les traces 594 continuent à produire
des frames jusqu'à l'arrêt. Cette observation n'annule pas le problème
signalé. L'ancien blocage 593 sur le label 0x60300510, attendant 0x71B4 avec
0x71B3 visible, reste historique. Aucun label n'est forcé et aucune attente
invitée n'est sautée.

## Modifications natives

### 1. Définir le retour d'une lecture FIFO incomplète

Dans RSXFIFO.cpp, FIFO_control::read() ignorait un échec de read_unsafe()
lorsqu'un paquet était déjà en cours. La sortie pouvait rester inchangée,
alors que l'appelant utilise une commande initialement non initialisée.
Le retour est maintenant explicitement FIFO_EMPTY.

Ce changement reprend la correction
[RPCS3 43a42d1](https://github.com/RPCS3/rpcs3/commit/43a42d1a868794ae5ff592a1d0055c2c615eaa44).
Le test utilise une sentinelle définie pour reproduire l'ancienne sortie non
écrite sans lire une valeur C++ indéterminée.

### 2. Conserver la première donnée d'un paquet partiellement publié

Lorsque PUT publie l'en-tête avant sa première donnée, le code avançait GET
interne jusqu'à cette donnée. La reprise par read_unsafe() lisait ensuite
quatre octets plus loin, sautant le premier argument.

Uniquement si la première lecture retourne FIFO_EMPTY, le correctif recule
GET interne de quatre octets et remet le compteur restant à zéro. Le prochain
essai relit l'en-tête. Les erreurs, annulations, récupérations de GET et
l'attente bloquante Fast gardent leur comportement. Aucun champ ni format
de sauvegarde ne change.

Les tests compilent la déclaration FIFO réelle, ses méthodes inline, douze
méthodes extraites et les constantes de production. La RAM invitée et les
callbacks de réservation, attente et récupération sont simulés.

| Contrôle exécuté | 594 | Candidat |
|---|---:|---:|
| Sorties non écrites pendant 188 928 attentes | 188 928 | 0 |
| Paquets dont la première donnée est sautée | 1 728 | 0 |
| Mots correctement repris après publication partielle | — | 586 368 |
| Réentrées depuis le GET publié | — | 576 |

Sont également couverts : 47 232 arguments repris dans les paquets en cours,
6 912 attentes d'en-tête, neuf erreurs/annulations/récupérations, six attentes
Fast et 48 appels au vrai restore_state(). Les modes Atomic/Ordered/AsPS3,
caches 1/4 Kio, publication GET immédiate/différée, limites de page et paquets
de 1 à 2 047 mots sont exercés. La sérialisation complète d'une sauvegarde et
l'ordre mémoire concurrent réel ne sont pas testés.

### 3. Retirer les anciennes plages de textures et réduire les parcours

Dans texture_cache_utils.h, destroy() peut laisser une plage valide lorsqu'une
section n'a aucune ressource GPU. Après retag, clear puis réutilisation, une
appartenance à un bloc voisin pouvait survivre avec une nouvelle plage ne
recouvrant plus ce voisin.

Les chemins iOS de reset() et ranged_storage_block::clear() appellent maintenant
invalidate_range() après destroy(). Les slots restent alloués : le défaut
reproduit est une appartenance obsolète, pas un accès démontré à de la mémoire
libérée.

L'invariant de plage permet de retirer une entrée d'index par recherche
dichotomique sur adresse et ordre du slot, puis vérification du pointeur.
Le second parcours linéaire à l'insertion est supprimé. Seuil de 16,
ordre des candidats, validations, verrous et champs restent identiques.

La restauration a aussi révélé que invalidate_range() est privé. Une amitié
ciblée vers le type du bloc, sous iOS, autorise cet appel. Les nouveaux tests
conservent le niveau d'accès privé et compilent clear() avec la déclaration
réelle ; rendre toute la classe publique dans l'adaptateur aurait masqué
cette erreur de compilation.

Le cas address passe 22 753 requêtes et 8 618 mutations, avec 26 872 contrôles
complets d'index/appartenance, 4 105 retags de frontière, 216 contrôles négatifs
de l'ancien comportement et trois clear/réutilisations. Le cas exact passe,
pour chacun des deux cycles de vie, 13 492 requêtes, 3 365 cas debug et
4 036 mutations. Il compare l'index réel à son propre repli linéaire iOS,
sur le même stockage restauré, avec les suppressions par échange avec la
dernière entrée.

Mesures actuelles, **Linux x86_64, GCC 13.3**, médianes de sept séries :

| Sections | 594, ns/recyclage | Candidat, ns/recyclage |
|---:|---:|---:|
| 8 | 36,484 | 32,497 |
| 16 | 25,637 | 27,315 |
| 17 | 44,045 | 42,215 |
| 64 | 75,856 | 66,641 |
| 256 | 264,027 | 117,356 |
| 1 024 | 732,980 | 321,008 |

Le coût baisse dans les blocs chargés de cette mesure ; il augmente à
16 sections. Les timings de lookup, y compris les cas plus lents, restent
dans le reçu. La distribution réelle des blocs dans les jeux est inconnue.
Aucune conversion de ces valeurs en FPS iPhone n'est possible.

### 4. Attendre les uploads avant tous leurs consommateurs

Dans VKGSRender.cpp et VKTextureCache.cpp, le mode safe attendait l'upload
au stage fragment uniquement. Une transition de layout, une copie de readback
ou un échantillonnage vertex peut pourtant consommer les données auparavant.

Sous iOS, les deux soumissions attendent désormais les stages TRANSFER,
VERTEX_SHADER et FRAGMENT_SHADER. Le producteur reste soumis avant le
consommateur. Aucun queue_wait_idle, changement de queue, nouveau blocage CPU
ni attente globale ALL_COMMANDS n'est ajouté. Les conversions compute de
readback restent chaînées par les barrières transfert→compute existantes.
Le chemin hors iOS est conservé.

Les règles pertinentes sont celles de
[VkSubmitInfo](https://docs.vulkan.org/refpages/latest/refpages/source/VkSubmitInfo.html)
et des [chaînes de synchronisation Vulkan](https://docs.vulkan.org/spec/latest/chapters/synchronization.html).
Les tests enregistrent les vrais paquets avec un adaptateur Vulkan :
16 cas principaux et 12 readbacks. La baseline iOS échoue volontairement sur
les deux consommateurs non protégés ; candidat et variantes hors iOS passent.
Aucun scheduler GPU réel n'est exécuté.

L'upload asynchrone est activé dans la configuration AC observée. La
responsabilité de cette erreur dans les torches n'est pas démontrée.
L'attente élargie peut réduire le recouvrement GPU ; son coût reste à mesurer
sur appareil.

### 5. Actualiser vues, filtrage et conversion lorsque le shader change

Dans RSXThread.cpp, prefetch_fragment_program() conserve l'ancien masque BX2
et marque dirty les unités dont l'usage change. Les registres de texture
peuvent rester identiques alors que TEX devient TEX_bx2, ou inversement :
cela affecte pourtant la vue sRGB/SNORM, le filtrage et la conversion.

Le XOR complet des masques est conservé, y compris pour les unités absentes
du nouveau shader. Elles restent dirty sans upload jusqu'à leur prochaine
utilisation. Une texture SNORM passée en BX2, retirée puis réintroduite,
peut ainsi retrouver le filtrage demandé.

Le contrôle global fragment est recalculé lors d'un changement BX2, y compris
au retrait de sa dernière unité, et lors de **tout changement du masque des
références**. Après retrait et retour d'une texture sans BX2, retrouver les
coefficients seuls ne suffit pas si le flag global de conversion a été perdu.

La revue a aussi reproduit le cas inverse : après retrait de la dernière
texture logicielle, FORMAT_CONVERT restait actif sans être nécessaire. Le
véritable normaliseur BO2 conservait ce bit, son comparateur distinguait la
clé et la propriété Vulkan activait encore l'option GLSL de conversion.
L'élargissement aux retraits supprime cette divergence dans les quatre cas
testés. Il ne prouve pas encore combien de compilations BO2 sont évitées.

Le changement est limité à iOS. Aucun champ ni format de cache n'est ajouté ;
le générateur de shaders n'est pas modifié. Les tests extraient préfetch,
choix de vue/filtrage, génération et transfert des paramètres, normalisation
et comparaison des clés, avec les constantes de production.

Les deux modes passent 16 transitions sRGB/SNORM, 24 cas de cycle de vie et
sept contrôles négatifs. Les 16 défauts de transition reproduits sur la
baseline passent à zéro, comme les quatre cas de clés/options de conversion
superflues. Les unités 0/15 et les chemins hors iOS sont couverts. Décodage
invité, images et mémoire de transfert sont simulés. Cette preuve ne vaut
pas encore validation des armes BO2 ou des torches AC sur GPU.

## Preuves et compatibilité

Les rapports ciblés contiennent les empreintes des sources, adaptateurs et
programmes effectivement compilés :

- [FIFO](evidence/rpcs3-device594-20261029/fifo-partial-plain.json) et
  [ASan/UBSan](evidence/rpcs3-device594-20261029/fifo-partial-asan.json).
- [Textures address](evidence/rpcs3-device594-20261029/texture-lifecycle-address-plain.json) et
  [ASan/UBSan](evidence/rpcs3-device594-20261029/texture-lifecycle-address-asan.json).
- [Textures exact](evidence/rpcs3-device594-20261029/texture-lifecycle-exact-plain.json) et
  [ASan/UBSan](evidence/rpcs3-device594-20261029/texture-lifecycle-exact-asan.json).
- [Uploads](evidence/rpcs3-device594-20261029/async-upload-wait-plain.json) et
  [ASan/UBSan](evidence/rpcs3-device594-20261029/async-upload-wait-asan.json).
- [Transitions de shader](evidence/rpcs3-device594-20261029/bx2-sampler-transition-plain.json) et
  [ASan/UBSan](evidence/rpcs3-device594-20261029/bx2-sampler-transition-asan.json).

LeakSanitizer est désactivé dans cet environnement ; ASan et UBSan restent
actifs. Ces tests ne rendent aucune image et n'exécutent aucun jeu.

La vérification du patch unique porte sur 313 postimages : cinq modifiées,
308 conservées depuis 594. La fixture réversible reconstruit la baseline
avant les fixtures historiques. L'ABI 30, les 88 exports et les sources de
génération PPU a987639e9f838d1c / SPU d070cb361bdef607 sont conservés.
Aucun cache utilisateur n'est effacé.

Le contrôle Apple réutilise les **neuf programmes inchangés correspondant à
20 modes déjà réussis** du Core 594, avec authentification de leurs identités.
Les quatre anciens modes texture sont remplacés. Les dix modes du nouveau
delta restent à exécuter sur Apple lors d'un build explicitement demandé.
L'authentification ne rejoue ni les anciennes suites natives ni CMake.

Le reçu [canonical-integration.json](evidence/rpcs3-device594-20261029/canonical-integration.json)
lie les entrées du dépôt aux sources testées. Il ne remplace pas une future
compilation du Core iPhone et ne transforme pas les preuves Apple historiques
en tests de ce candidat.

## Prochaines optimisations et validations

1. **BO2 : premières bibliothèques fragment Metal.** Suivre la réutilisation
   des vrais modules et variantes des longues créations. Les adresses
   distinctes ne justifient pas de supposer un doublon supprimable. Garder
   l'interpréteur graphique et la compilation SPU différée désactivés ; ne pas
   masquer les pauses en sautant des draws.
2. **Assassin's Creed : torches et plateau sans compilation.** Vérifier le
   rendu avec les correctifs d'upload et de transition de shader, puis comparer
   le même parcours à état thermique similaire. Les coûts RSX, textures et
   soumissions restent les pistes mesurées ; un nouveau préchauffage SPU ou
   davantage de mémoire ne découle pas de cette plage.
3. **GOW3 : validation des textures et lectures sur faute CPU.** Réduire le
   hachage ou les readbacks en préservant les vrais lecteurs. Les 1 491 lectures
   malgré le bypass MLAA excluent une désactivation générale de Write Color
   Buffers sur cette seule base.
4. **Reprise des commandes GOW3.** Le backport complet de la sémantique GET
   récente de RPCS3 reste séparé : commandes de contrôle, position d'exécution
   et format de sauvegarde doivent être traités ensemble. Les deux corrections
   FIFO présentes ne permettent pas d'annoncer le gel sur label résolu.

Les corrections FSR1/compute et de comparaison de profondeur déjà intégrées
ne sont pas réimportées. Les modifications MeloNX et les preuves de livraison
594 sont conservées. Aucun nouveau réglage joueur, journal applicatif, numéro
de livraison ou release n'est ajouté.
