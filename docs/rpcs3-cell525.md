# RPCS3 525 — restauration des répertoires et durée de vie du cache PPU

Continuation sur `Claude` depuis `1bdad6ca`, avec les quatre nouveaux journaux
locaux. Les empreintes et le regroupement strict par build/PID sont dans
[le relevé reproductible](evidence/rpcs3-cell525-log-baseline.json), produit par
`tools/rpcs3/analyze_cell525_logs.py`. Les journaux bruts et les chemins personnels
ne sont pas versionnés. Aucun changement de `main`, tag ou release.

## Ce que la capture 524 établit

La session 524/PID 23669 est distinguée des anciennes sessions 520 et 522.
Les 390 événements de restauration copiés dans les milestones ne sont pas
comptés une seconde fois. Le TAR prend 2,420097 s et la VM 0,405081 s ; les
segments et modules PPU passent. La capture se termine à l'entrée de
`id_manager::id_map<lv2_fs_object>`, position 1969206997. Elle ne permet pas de
savoir si le prochain objet est un fichier, un répertoire ou une donnée invalide.
Le correctif HLE 524 reste conservé ; il concerne une création refusée, distincte
de ce chargement.

Les 40 modules PPU sont en cache, aucun n'est compilé. Le compteur de lecture
agrégé indique 89 618 112 octets pour 44 809 056 octets d'objets et quatre buffers
réutilisés. Le jalon JIT de 682,179 ms ne mesure pas le lancement complet de
l'application. Les shaders sont très majoritairement trouvés en cache et aucun
travail de pipeline n'est signalé pendant le ralentissement tardif. Cela ne
justifie pas une modification spéculative du traducteur NEON, des atomiques CELL,
du DMA ou des barrières PPU/SPU.

Les allocations demandées pour les textures passent de 268 652 416 à
1 079 519 744 octets, tandis que les pools système, scratch et surfaces restent
relativement stables. La scène n'est pas étiquetée : les fenêtres rapides et
lentes ne sont pas un essai avant/après. Le temps GPU vaut -1, donc n'est pas
mesuré. Les attentes de réservation sont des sommes entre threads, pas une
attente murale par image.

Le maximum de footprint NeoSwap est 4 437 186 552 octets ; résident et compressé
atteignent respectivement 2 234 351 616 et 1 351 680 000 octets. Ces compteurs
se recouvrent et ne s'additionnent pas. Les alias, prêts, octets archivés cumulés
et cible NeoSwap de 7 Gio ne sont pas de la RAM physique supplémentaire. Les
refus de croissance lorsque la mémoire système disponible devient faible
restent conservés.

## Correctifs natifs démontrés

| Symptôme ou défaut | Cause dans le code | Intervention et preuve |
| --- | --- | --- |
| Répertoire non vide mal restauré | `deserialize_vle(size)` utilise la valeur par défaut `MaxBits=0` ; la ternaire actuelle du lecteur donne une largeur de zéro, retourne faux après un octet et son résultat est ignoré | `lv2_dir` utilise explicitement `ensure(ar.deserialize_vle<64>(size))` sur iOS. Le writer et le sérialiseur global restent identiques. Six tailles, dont 127/128, sont vérifiées avec le vrai header ; le témoin échoue sur cinq répertoires non vides. |
| Lecture au-delà d'un nom sauvegardé sans NUL | Conversion implicite en `string_view` avant `mount_map.lookup` | Validation dans les 0x420 octets du format avant lookup ; le témoin ASan lit hors du tableau, le candidat rejette avant I/O. Les noms valides et leur padding restent identiques. |
| Objets PPU relus/décompressés | `ppu_effective_pipeline()` détruit les buffers validés à chaque consultation d'un réglage | Getter pur ; propriétaires imbriqués et concurrents dans les chargements PPU. Le dernier propriétaire libère les buffers, sous la limite globale existante de 32 Mio. |
| VMA encore affiché après arrêt | Les trois anciennes valeurs persistent après `vmaDestroyAllocator` | Snapshot cohérent lié au propriétaire et à sa génération, remis à zéro après destruction. Le reporter lit une copie par `try_lock`, sans accéder au GPU. |
| Part recyclable des textures inconnue | Le total textures ne distingue pas le pool d'images déjà rendu au cache | Nombre et octets existants copiés en O(1) sous le verrou déjà tenu à `on_frame_end`. Aucun parcours, purge, fence ou nouvel échantillonneur. |

La nouvelle trace FS est limitée à 256 événements et un message de limite par
restauration, indépendamment du budget FXO. Elle indique tag, ID/type, lookup,
montage, ouverture, allocation en mémoire, lecture, seek et entrées de répertoire,
sans chemins ni contenu. Elle ne crée ni timeout ni mécanisme de reprise.

Le lecteur VLE générique n'est pas corrigé globalement : les autres consommateurs
ne sont pas entraînés dans ce périmètre. Une taille annoncée excessive de fichier
en mémoire ou de répertoire peut encore provoquer une allocation avant validation
du payload. Le test le documente sans allouer une taille gigantesque ; aucune
borne arbitraire n'est ajoutée. Le nom invalide et la VLE invalide suivent le refus
fatal existant du cœur, sans récupération d'archive inventée.

## Mesures et vérification

Les fixtures utilisent les méthodes de production extraites, le vrai sérialiseur,
les layouts et enums de fichiers. Les adaptateurs remplacent explicitement les
opérations hôte (fichiers/montages/FXO, horloge et journal), pas un jeu émulé.
Localement : 22 cas de fichiers, six répertoires, limites de trace indépendantes,
16 cas de fenêtre PPU sous ASan/UBSan et 30 000 cycles concurrents des snapshots.
Le premier répertoire témoin lit jusqu'à 1065 sur 1112 octets ; corrigé, il atteint
1112 avec ses entrées et son itérateur exacts. Aucun octet de sauvegarde n'est
migré, réécrit ou supprimé.

Sur 40 objets gzip synthétiques de 1 Mio, les méthodes réelles réduisent
déterministement 80 à 48 chargements/décompressions logiques (80 à 48 Mio), avec
32 buffers réutilisés. Ce ne sont ni des lectures physiques de disque, ni une
reconstruction exacte des passes de God of War III. La rétention temporaire monte
de 1 à 32 Mio dans cette fixture, puis revient à zéro : ce n'est pas un gain RAM.
Les timings locaux avec l'adaptateur de buffer portable sont trop variables pour
une revendication de latence. L'essai Apple avec le vrai LLVM passe. Douze tours alternent avant/après sur le
même hôte macOS ARM64 ; les deux premiers sont écartés. Médianes des dix autres :

| Composant synthétique, cache de fichiers chaud | Avant | Après |
| --- | ---: | ---: |
| Durée murale | 29,2837 ms | 20,5723 ms |
| Temps CPU | 29,0415 ms | 20,2615 ms |
| Chargements/décompressions logiques | 80 | 48 |
| Octets décompressés | 83 886 080 | 50 331 648 |
| Pic de buffers retenus dans la fenêtre | 1 Mio | 32 Mio |

Les durées diminuent de 29,75 % et 30,23 % dans ce composant. Aucun cache système
n'est évincé : aucun stockage froid, jeu, image GPU ou FPS n'est mesuré.
Le modèle matériel n'est pas consigné par la fixture ; ce résultat ne devient
pas une mesure iPhone. Le canal textures coûte 112 octets sur cet hôte, sans
allocation par échantillon ; son microbenchmark mesure environ 9,83 ns par
publication et 8,98 ns par lecture, sans extrapolation à l'appareil.

Les deux premiers essais Apple sont conservés : `40118946165` échoue à la
compilation d'un déplacement d'archive propre à la fixture ; `40119211793`
révèle que Clang supprime le `strlen` du témoin lorsque le faux montage ignore
le nom. La fixture emprunte maintenant l'archive et observe la longueur utilisée
par le montage. Aucun fichier moteur n'a changé entre ces essais. Le troisième
run, [`40119436261`](https://github.com/TarbleFR/RewindBox/actions/runs/40119436261),
réussit les tests Apple, les 43 unités SDK iPhone, le lien complet, la validation
passive et les exports. Source : `c89b7809641ea976e0a0e29a52d8af2a7b7a3e5f`.
Le Core téléchargé est vérifié indépendamment : 77 002 760 octets,
SHA-256 `3aadeb5ff04facb3d047a0316332703e5b84322a00ad00998ad4087ac1935031`,
142 entrées authentifiées, 88 exports identiques à l'application 523, arm64,
plateforme iOS et minimum natif 16.3. Les archives Core/diagnostics téléchargées
correspondent aux tailles et SHA-256 GitHub Actions. L'assemblage IPA reste une
étape distincte, avec comparaison des 87 images ARM64 et 4410 ressources. Les preuves 524 des parties inchangées sont authentifiées par
commit, run, empreinte d'archive, 132 empreintes d'entrée et journal ; elles ne
sont pas rejouées comme une nouvelle campagne.

## Identités, provenance et périmètre

Base RPCS3 XITRIX `22f1152783cef1f7e04af7b1c895173e28fd5b03`, ABI 30,
LLVM 22.1.8 avec correctif GHC AArch64 conservé, FFmpeg 8.1.1 et MoltenVK 1.4.2.
Le delta canonique contient 253 postimages : cinq modifiées depuis 524 et trois
nouvellement incluses dans le delta. Une fixture inverse reconstruit les sept
fichiers précédents exactement et supprime le nouveau header de profilage.
La matérialisation complète sur la base propre est vérifiée.

Les sources et attributions RPCS3/ARMSX3 restent conservées ; les nouveaux
adaptateurs de test portent leur licence MIT. Les backports v0.12 déjà intégrés
(ISO, trampoline PPU, pliage NEON constant, fallback shader et effacement des mips
sur écrasement complet) restent inchangés. La correspondance exacte entre l'IPA
XITRIX v0.12 publiée et ses sources complètes reste non prouvée, comme indiqué
dans `xitrix_v012_backports` ; aucun moteur d'IPA externe n'est substitué.

Le digest PPU devient `ed8b442fb38656b6`, selon la règle CMake existante : premier
lancement froid par titre. Le digest SPU reste `a601a98f20f30c80`. Aucun passe,
réglage ou traducteur n'est modifié pour contourner cette règle. Le cœur reste
arm64/ARMv8.4-A ; la vérification CPU de l'hôte précède le JIT et `dlopen`. Aucun
cœur de repli ARMv8-A n'est inventé. NeoSwap, RSX, sauvegardes, autres moteurs,
StikJIT/LocalDevVPN et tous les réglages utilisateur restent conservés.

## Essais appareil encore nécessaires

Aucun appareil iOS ni contenu de jeu n'est disponible dans cet environnement.
La compilation Apple et les fixtures ne prouvent ni FPS, ni pic mémoire, ni
stabilité de God of War III sur appareil. Comparer 524 et 525 sur le même appareil,
la même scène, les mêmes réglages, d'abord après recompilation PPU puis caches
chauds ; séparer gameplay, menus et cinématiques. Recueillir le journal intégré
pour démarrage, restauration de l'original, manette, pause/reprise, arrêt et
deuxième lancement. La fermeture de la table FD et les nouvelles étapes doivent
être observées avant de conclure que la restauration du titre est réparée.

Les nouveaux compteurs n'affirment pas une résidence GPU :
`*_snapshot_valid=0` signifie échantillon indisponible ; après arrêt valide,
`owner_live=0` et `sample_valid=0`. Le pool recyclable est celui du dernier
frame-end publié ; textures actives et retraites GPU en attente restent non mesurées.


## Livraison privée vérifiée

IPA **0.0.8 (525)**, `RewindBox-Build525.ipa`, **186 630 220 octets**,
SHA-256 **`a95d49860b4ef74699284d4ed002b02318eb5551a427fee9fea574363d209cdd`**.
Source d'assemblage : `7269071664100e2fe2b10e559bc43cfc423c6a50` ;
[run 40120597675](https://github.com/TarbleFR/RewindBox/actions/runs/40120597675),
job `120951083411`, réussi. Les quatre transports GitHub sont chiffrés ; leurs
tailles et SHA-256, les fragments, l'enveloppe et le checksum de l'IPA déchiffrée
ont été contrôlés. Le récepteur a d'abord refusé le répertoire racine `.` de
BSD tar ; il accepte désormais uniquement cette entrée de répertoire explicite,
sans relâcher les gardes de traversée, liens ou fichiers spéciaux.

Le Core signé embarqué a pour SHA-256
`65dac69775250810a61aa014f492ea8f80bea2def4eb0b8689f48353b928443d`.
La différence avec l'artefact natif vient de la signature : ses segments hors
LINKEDIT et son empreinte code/données/ABI
`04934548624b4342a13cadd234c35fa05814e0d151eaefb0c4819cf263965775`
sont conservés. Les 88 exports correspondent exactement au contrat précédent.

L'application compilée 523 (`c1f550f8`, run `40104064265`) est réutilisée à
l'identique : aucune recompilation Flutter, car aucun de ses fichiers de produit
ne change. L'IPA est reconstruite et scellée avec le nouveau Core. Contrôle
indépendant final : **87 images ARM64**, dont **86 autres images identiques**,
**4410 ressources conservées**, **8 bundles en 525** dont sept extensions,
**84 images fines scellées** et **87 signatures ad hoc strictes vérifiées en CI**.
Les entitlements d'exécution sont identiques ; les notices, sources et recettes
natives restent embarquées. La racine Merkle des ressources normalisées reste
`754e938ac9214f564d2e1cbe7202f45e37661337d94037b9de9a307cde3c5407`.

L'IPA privée a été enregistrée pour téléchargement. La signature Apple pour
installation reste à refaire avec la méthode habituelle du mainteneur ; aucune
provision Apple ou installation physique n'est déclarée. Le
[reçu complet](evidence/rpcs3-cell525-validation.json) conserve les observations,
les deux échecs de préparation, les tests Apple, les mesures brutes et les limites.
