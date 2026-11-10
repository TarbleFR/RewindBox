# RewindBox — audit critique et nouvelle phase RPCS3

## Conclusion précédente corrigée

Le lot `a363d923` démontrait trois modifications locales sûres dans les scénarios
testés. Il ne démontrait ni une amélioration globale de la fluidité, ni la
disparition des défauts de BO2/AC, ni la résolution du gel de GOW3. Le présenter
comme une fin de tâche était prématuré. La nouvelle phase reprend ces objectifs,
élargit les investigations et conserve séparément les preuves de code, les tests
hôte et les observations sur iPhone.

Base de cette phase : `a363d923`, sur la branche locale `Claude`. Au début du
travail et lors de la vérification finale, la branche distante était toujours à
`c0df3394`, et les trois derniers
correctifs étaient présents dans le patch canonique et dans les sources utilisées
pour les tests. Les changements sont réalisés dans le checkout isolé existant.
Le Core présent dans l'IPA 595 reste le binaire historique `f42573af` ; aucune
source de cette phase n'a été exécutée sur l'iPhone. Aucun réglage du mainteneur
n'est remplacé.

## Ce que les traces permettaient réellement de cibler

Les fenêtres BO2 et AC déjà analysées comportent des ralentissements sans aucune
compilation de shader. Le formatage des shaders ne peut donc pas être leur cause
unique. Les temps textures observés justifient de poursuivre les chemins de
création, de réemploi, de copie et de synchronisation, mais ne permettent pas
d'attribuer chaque milliseconde à une fonction particulière.

Pour GOW3, l'attente RSX sur `0x60300510` reste constatée : `0x6F0E` attendu,
`0x6F0D` observé. L'activité SPU persistante n'identifie pas l'instruction chargée
de produire le signal. La nouvelle recherche a donc suivi les protocoles SPU et
MFC dans le code, plutôt que de conclure à l'absence de correctif à partir du seul
label. Les défauts trouvés ci-dessous ont des reproductions indépendantes ; leur
lien avec cette scène précise n'est pas encore établi.

La séparation des journaux par build/PID/session est conservée dans
`cpu-existing-memory-observations.json`. Un pic initialement considéré pendant
la recherche appartenait au build 594 et a été exclu des conclusions sur 595.
Les mesures applicatives, MEMPROF et NeoSwap n'ont pas nécessairement les mêmes
instants d'échantillonnage : leurs maxima ne doivent pas être additionnés.

## Modifications de production retenues

### SPU, LLVM et progression des transferts

- **Canaux SNR, `SPUThread.h::spu_channel::push`.** Le compteur précédent était
  inversé. `push_snr` pouvait manquer l'événement S1/S2 sur le passage vide → plein
  et en générer quand le canal était déjà plein. Le compteur retourné reflète
  maintenant l'état précédent réel, y compris la livraison à un SPU en attente.
  Les valeurs du canal, le mode OR, les opérations atomiques et les notifications
  du canal restent inchangés.
- **Restauration, constructeur de `spu_thread` dans `SPUThread.cpp`.** Une file
  MFC restaurée avec le mélange des transferts activé réarme le travail différé.
  La file était sérialisée, mais pas ce drapeau hôte ; certaines attentes pouvaient
  rester bloquées. Les listes suspendues exigent toujours leur acquittement. Cette
  correction ne peut pas expliquer à elle seule le gel GOW3 observé avec le
  mélange des transferts désactivé.
- **Barrières LLVM, `SPULLVMRecompiler.cpp::WRCH`.** La mise en file d'une commande
  BARRIER/EIEIO/SYNC stocke maintenant son tag. Le slot recyclé conservait sinon
  un ancien tag, permettant de déclarer terminée une barrière encore retenue par
  une liste DMA. La publication du nombre d'entrées reste après les champs.
- **File MFC pleine et interruption avant acceptation.** Le chemin LLVM utilise
  le traitement bloquant normal lorsque les 16 slots sont occupés, au lieu d'écrire
  à l'adresse de faute qui mène à un arrêt de débogage. La reprise conserve le PC
  et les registres. Lors du drainage avant acceptation, une interruption doit
  reprendre le WRCH courant : la nouvelle commande n'est pas encore exécutée.
  Les cas de reprise, arrêt, acquittement de liste et acceptation unique sont
  vérifiés par le test ciblé du contrôle de flux. Le drainage peut effectuer
  plusieurs passes avant de traiter l'interruption à sa sortie ; aucune nouvelle
  commande n'est acceptée entre-temps.

Ces changements sont des réparations d'exactitude. La sauvegarde nécessaire au
slowpath LLVM peut limiter l'élimination de stores dans le bloc compilé ; aucun
gain de temps du code ARM64 n'est revendiqué. Les identités SPU doivent changer
normalement, sans alias masquant une modification sémantique. La première
utilisation du futur Core peut donc recompiler son cache SPU ; les comparaisons
de gameplay devront distinguer ce démarrage du cache déjà chaud.

### Textures, profondeur et synchronisation GPU

- **Réemploi des vues, `VKTextureCache.cpp::create_new_texture`.** Le changement
  de correspondance native des canaux passe par `set_native_component_layout`.
  L'affectation directe contournait l'invalidation des vues et de leur accès
  rapide. C'est un autre chemin que le remappage temporaire corrigé précédemment.
- **Pool d'images, `find_cached_image`.** Le hash compact n'est plus considéré
  comme une égalité suffisante : profondeur, nombre de mipmaps et classe du
  format doivent aussi correspondre. Les chevauchements des bits profondeur/mips
  et les formats de profondeur différents émulés par un même format Vulkan
  pouvaient sélectionner une image incompatible.
- **Format des surfaces de profondeur, `cached_texture_section::create`.** La
  conversion utilise le helper commun des formats GCM, couvrant les variantes
  16/24 bits et flottantes. La première correction locale du ternaire inversé
  aurait encore perdu la distinction flottante ; la revue des vrais types a
  conduit à cette correction complète.
- **Usages des images temporaires, `create_temporary_subresource_storage`.** Les
  capacités demandées sont transmises à l'allocation, en conservant les usages
  nécessaires à la destination de copie. La conversion de présentation demande
  notamment `TRANSFER_SRC` : le constructeur utilisait auparavant une constante
  qui l'omettait, malgré le paramètre reçu et le filtrage du pool.
- **Portée des barrières, `vkutils/image_helpers.cpp::change_image_layout`.** Les
  transitions concernées par `GENERAL` et la boucle de retour des attachments
  couvrent aussi les lectures du vertex shader. Le masque d'accès annonçait des
  lectures shader mais la portée ne couvrait que le fragment shader. Les masques
  d'accès, ressources, plages et nombres de barrières restent identiques. Les
  consommateurs compute examinés possèdent leurs barrières explicites ; aucun
  élargissement compute arbitraire n'est ajouté.
- **Copies et effacements.** Les petits ensembles de sources évitent une table
  de hachage allouée sur le tas. Pour les cubemaps et textures 3D couleur, un
  effacement préalable est évité seulement si les copies couvrent intégralement
  chaque face/tranche et chaque mip. Les trous, doublons laissant une tranche
  absente, copies partielles, profondeurs et cas hors limite gardent l'effacement.
  Les barrières nécessaires restent en place. Pour les petits lots, les images
  sont restaurées dans leur ordre de première utilisation, au lieu de l'ordre
  indéterminé de la table de hachage. Chaque image est restaurée après toutes
  les copies ; aucune dépendance entre ces restaurations distinctes n'est ajoutée.

Les variantes de formats incompatibles peuvent désormais rater le pool et
nécessiter une nouvelle image : c'est le coût de la correction, pas une baisse
universelle des allocations. Les tests des effacements modélisent les texels
écrits par les rectangles destination ; ils n'exécutent pas le pilote Metal,
les conversions typeless ou MSAA. Les corps de ces copies restent inchangés et
ont été relus. La disparition des artefacts des jeux n'est pas encore vérifiée.

### Shaders, mémoire et intégration iOS

- **Décompilateurs vertex/fragment et `ShaderParam.h`.** Le formateur cherche
  les marqueurs `$` et copie les portions littérales une fois, au lieu de tester
  11/19 marqueurs à chaque caractère et de déplacer le suffixe à chaque
  remplacement. Des lambdas remplacent les objets `std::bind` alloués. Le vertex
  `AddCode` formate une fois le texte partagé par ses deux sorties. Ordre des
  callbacks, déclarations, points-virgules et prétraitement TEXBEM sont conservés.
  Aucun changement de précision arithmétique ou de cache de pipelines n'est ajouté.
- **Allocateur JIT, `JITArenaAllocator.h`.** La libération fusionne directement
  les intervalles voisins, sans insertion temporaire suivie d'effacements.
  La recherche des pages libérables utilise l'ordre des intervalles. Disposition,
  adresses retournées et contraintes d'alignement sont conservées.
- **NeoSwap, `Store.cpp::Impl::trim_to`.** Le balayage conserve son total mémoire
  local et soustrait les mappings libérés. Il ne recompte plus toute la table
  après chaque victime. L'ordre, les pins et les exclusions restent identiques.
- **Streaming, `VKAsyncScheduler.cpp`.** Les 16 384 slots de synchronisation
  gardent leur rotation, mais chaque sémaphore/événement pilote n'est créé qu'à
  sa première utilisation. Cela supprime leur création massive au démarrage du
  streaming et réduit la rétention avant un tour complet. Après un tour, le
  nombre total d'objets est inchangé. Les premières utilisations paient encore
  leur création, parfois sous verrou : latence et risque d'allocation tardive
  ne sont pas mesurés sur Metal. AC active ce streaming dans les traces ; BO2 et
  GOW3 le désactivent.

## Vérifications, gains limités au chemin mesuré et résultats négatifs

Les preuves finales sont dans `docs/evidence/rpcs3-deep-audit-20261029/`.
Les fonctions/classes réellement modifiées sont compilées dans des harnais
différentiels avant/après, sous GCC Linux x86_64, avec assertions actives, puis
ASan/UBSan, sauf le test des masques de barrières exécuté en mode normal seulement.
La suite POSIX complète de Store est également exécutée. Les frontières
Vulkan, certains callbacks et le builder LLVM sont adaptés : cela ne remplace
ni une compilation complète LLVM/Apple, ni une exécution GPU. LeakSanitizer n'est
pas revendiqué.

| Vérification | Résultat établi |
| --- | --- |
| Canal SNR | 768 scénarios ; 256 événements manquants et 512 parasites avant, zéro désaccord après |
| Restauration MFC | 144 cas ; 72 attentes bloquées avant progressent après ; 36 listes exigent toujours leur acquittement |
| Tag des barrières MFC | 49 152 scénarios ; 47 616 complétions prématurées avant, zéro après |
| File MFC pleine et IRQ | 96 HALT historiques et 96 WRCH sautés reproduits ; 192 commandes acceptées exactement une fois après IRET, dont 96 avec acquittement de liste bloquée |
| Allocateur JIT complet | 240 000 opérations, 720 000 comparaisons de pages et 6 561 cas limites ; allocation d'une fusion adjacente 1 → 0 |
| Store | 2 400 scénarios, 12 000 balayages ; recomptages complets 184 750 → 12 000 ; même ordre d'éviction, suite POSIX passée |
| Formateur shader | 76 391 comparaisons Format, 10 913 AddCode et 91 littéraux du moteur ; textes et états utiles identiques |
| Pool de synchronisation | 99 000 identités de slots comparées sur plus de deux tours ; création initiale 16 384 → 0, puis un objet au premier besoin ; destructions exactement une fois |
| Textures | 20 739 contrôles de vues : 6 095 erreurs avant, zéro après ; 90 005 contrôles du pool : 2 050 erreurs avant, zéro après ; quatre mauvaises classifications de profondeur et quatre omissions d'usages corrigées |
| Copies | 13 000 scénarios et 3 692 couvertures ; 657 effacements évités dans la matrice, mêmes texels destination modélisés ; 124 419 vues créées et détruites |
| Barrières | `texture-barriers.json` : 7 680 combinaisons ; 1 152 portées de lecture sans vertex avant, zéro après ; mêmes accès, images, plages, familles de queues et nombres de barrières |

Quelques ordres de grandeur hôte, avec leurs limites : fusion JIT fortement
fragmentée 193 → 71 ns ; éviction Store de 1 024 entrées 6,76 → 3,55 ms ; formatage
fragment synthétique courant 7,58 → 0,75 µs. Les recherches JIT sur de petites
listes et deux cas Store sans éviction ont des médianes plus lentes, conservées
dans les rapports. Ces nombres ne sont ni des temps GPU, ni un gain de FPS sur
iPhone, ni une estimation du temps total d'une frame.

La collection des sources de copie pour un à huit éléments supprime deux à neuf
allocations par appel ; son travail de gestion mesuré baisse de 60 à 86 %.
Le cas à neuf sources distinctes reste 8,7 % plus lent dans la médiane finale.
Le code extrait de cette seule gestion augmente de 955 octets. La spécialisation
peut aussi dupliquer le corps des copies GPU : ces 955 octets ne bornent pas la
taille de la vraie fonction ni le coût du cache d'instructions iOS. Le choix est
retenu pour la suppression mesurée des petites allocations, avec ce compromis
à contrôler lors de la première compilation Apple affectée.

Les expériences défavorables sont conservées au lieu d'être masquées :

- Trois caches de payloads shaders bruts ont été implémentés et mesurés : partagé,
  partagé non bloquant, privé par worker. Le dernier réduit 256 lectures identiques
  à une ou huit selon les workers, mais pénalise le cas de fichiers tous distincts
  à huit workers d'environ 15,5 % dans sa médiane hôte. Il est **retiré du code de
  production** ; `rsx_cache.h` est exactement revenu à la base. Trois fixtures et
  leurs résultats permettent de reprendre l'expérience sans la confondre avec
  le produit. Aucun cache réel de ces jeux n'est disponible pour établir leur
  multiplicité de payloads.
- La première variante de déduplication des sources de copies pénalisait certains
  gros lots. La sélection a été réexaminée hors boucle avant la décision finale ;
  les premiers résultats restent archivés.
- Un tas de victimes NeoSwap figé au début du balayage n'est pas équivalent : une
  référence externe peut être libérée pendant le traitement, rendant une victime
  nouvellement éligible. La suppression des recomptages conserve ce comportement.
- Une fusion naïve du prétraitement TEXBEM avec le nouveau scanner change le cas
  `$$0`. Le prétraitement distinct reste présent.

## Registre transversal et contraintes d'arrêt

Les registres détaillés répertorient les chemins et fonctions, impact potentiel,
faisabilité, preuves, risques et statut de chaque piste. Les quatre registres JSON
contiennent 38 entrées, complétées par neuf pistes dans le compte rendu CPU/GOW3
et son approfondissement MFC. Certaines entrées se recoupent ; même regroupées,
elles dépassent les quinze pistes distinctes demandées et couvrent ces domaines :

| Domaine | Investigations effectuées et résultat |
| --- | --- |
| PPU/LLVM | Codegen/cache, pipeline de passes, conversions vectorielles et contraintes ABI ; pas de remplacement arithmétique sans équivalence établie |
| SPU/LLVM | SNR, réservations, MFC, tags, file pleine, interruptions, restauration ; plusieurs défauts de protocole corrigés |
| RSX | Soumissions, dépendances, labels, durée de vie et destruction des ressources ; la suppression globale des attentes n'est pas justifiée |
| Vulkan/MoltenVK | Usages d'images, portées shader, objets de synchronisation et file de commandes |
| Shaders | Formateur optimisé ; publication des programmes, normalisation des pipelines et cache brut examinés ; trois variantes de cache retirées |
| Textures | Vues natives, remappage temporaire, collisions du pool, classes, profondeur, mips, cubemaps/3D, copies et barrières |
| Mémoire/NeoSwap | Recalculs de budget, éviction, références externes, fragmentation JIT, observations séparées par processus |
| Multithreading | Publication/consommation, callbacks hors verrous, files et réveils ; contraintes de reprise vérifiées |
| ARM64/NEON | Lowering existant, copies chevauchantes et formats ; pas de code supposé plus rapide sans comparaison native disponible |
| Intégration iOS | Allocateur JIT, streaming réellement activé selon le titre, Core effectivement livré et mémoire du processus |

Les détails se trouvent dans `cpu-investigation.json`, `shader-investigations.json`,
`rsx-investigations.json` et les comptes rendus GOW3 et textures du même dossier.
Ce registre distingue les pistes réfutées, les améliorations retenues et celles
dont la preuve manquante est identifiée.

Deux exemples de contraintes concrètes, au-delà d'un manque de logs :

1. Le regroupement des soumissions Vulkan ne peut pas simplement fusionner leurs
   paquets : chaque commande possède une fence consommée par sa réutilisation,
   les requêtes et la durée de vie des ressources. La documentation Vulkan précise
   que l'ordre de soumission ne crée pas à lui seul une dépendance mémoire.
   Une refonte exige un replay GPU préservant ces observateurs.
2. Le cache vertex ne compare que huit octets. Un changement plus loin dans la
   plage peut donc passer inaperçu. Le remplacer par un hash complet ajoute une
   lecture de toute la plage à chaque hit et ne résout pas seul la cohérence d'un
   snapshot concurrent. Une génération d'écriture doit couvrir CPU, SPU et DMA,
   ou une capture doit identifier les plages effectivement réutilisées à tort.

La recherche amont a aussi comparé le maintien du depth buffer pour ZPASS à
[RPCS3 #19608](https://github.com/RPCS3/rpcs3/pull/19608) et à
[#18827](https://github.com/RPCS3/rpcs3/issues/18827). Le correctif fusionné traite
des requêtes perdues, mais sa discussion décrit aussi une régression de pitch/
aliasing. Il n'est pas importé aveuglément ni remplacé par le contournement
« seulement sans color buffer ». Le registre conserve cette décision et les
références. Le signalement [#15397](https://github.com/RPCS3/rpcs3/issues/15397)
concerne BO1 et ne prouve rien pour les armes de BO2.

## État des jeux et prochaine preuve utile

| Jeu | Code nouveau pertinent | Ce qui reste à établir |
| --- | --- | --- |
| GOW3 | Événements SPU, tags/barrières, progression et reprise MFC ; formats de profondeur | Origine exacte du label absent et disparition du gel sur la scène ; certains cas corrigés supposent une configuration différente des traces |
| BO2 | Vues recyclées, formats/classes, usages et synchronisation des ressources ; coût des copies et shaders | Disparition des défauts armes/avant-bras et baisse des saccades avec caches chauds |
| Assassin's Creed | Mêmes corrections de rendu, portée vertex des barrières, streaming et copies | Disparition du flickering des torches, mesure des premiers usages du streaming et des frametimes soutenus |

Ordre des prochaines vérifications : compilation Apple des composants affectés
et validation du Core correspondant ; mêmes scènes sur iPhone avec source et
caches identifiés ; si le gel subsiste, état du producteur PPU/SPU du label ; si
les défauts de rendu subsistent, capture des ressources/vertex/ZPASS concernés ;
puis mesure de la part d'encodage Metal et des attentes avant une refonte des
soumissions. Les optimisations du cache shader brut sont moins prioritaires
tant que le profil de doublons et la régression sur les fichiers uniques ne sont
pas résolus.

## Intégration reproductible

Le patch canonique contient les onze fichiers moteur modifiés, soit six
postimages antérieures remplacées et cinq nouvelles : **319 postimages**, dont
**308 antérieures inchangées**. `native/neoswap-storage/Store.cpp` est la douzième
source de production modifiée dans l'application. Les modifications des deux
lots locaux précédents sont conservées.

- SHA256 du patch : `5ba1424bcd40afc96f3263e236d84ed643cb7aac15cbcd1fb513e85d24e27ec8`.
- Delta lisible : `test/fixtures/rpcs3_deep_audit_20261029.diff` ; SHA256
  `093b683c6896ed1ff087a90df47375057b1b2d2ffe1cf61af4ee27ca0f314a40`.
- Identité PPU inchangée : `a987639e9f838d1c` ; SPU :
  `d070cb361bdef607` → `477a3fa442d27917`. Aucun nouvel alias de compatibilité.
- Rematérialisation complète depuis l'amont épinglé, 319 empreintes et exports
  chargés par l'application vérifiés ; contrôle source/recette/ABI réussi.
- `contract-verification.json` authentifie 21 exécutions hôte enregistrées :
  17 sur les programmes finaux et quatre étapes MFC historiques reconstruites.
  Les deux suites Store POSIX sont aussi authentifiées. Le programme MFC final
  reprend les scénarios des étapes précédentes. Cette vérification ne relance
  ni compilateur, ni CMake, ni ancien binaire.

Commande de vérification du lot, après matérialisation du Core candidat et de
la base `a363d923` dans les répertoires indiqués :

```sh
python test/rpcs3_deep_audit_contract_test.py ../rpcs3-deep-verify \
  --baseline ../rpcs3-followup-verify \
  --report docs/evidence/rpcs3-deep-audit-20261029/contract-verification.json
```

Les recettes de livraison et les pins binaires historiques restent intacts ;
ils ne valident pas les nouvelles sources. Aucun push n'a été effectué.

Ce document est un état vérifiable d'avancement et de reprise. Il ne déclare pas
atteints les objectifs FPS/frametimes des trois jeux. Aucun nouvel événement
de télémétrie permanente, Core, IPA ou release n'est ajouté pour produire ces
résultats.
