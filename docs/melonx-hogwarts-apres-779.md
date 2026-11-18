# Hogwarts Legacy à 1x après l’IPA 779

## Version et capture

La référence iPhone est Hogwarts Legacy, titre `0100f7e00c70e000`, IPA 777, PID 40796, génération 1, session `37D75F23-0BFF-4AD8-9945-4E889EE22B79`, le 17 novembre 2026. Les deux fichiers du journal du core contiennent chacun les mêmes 319 événements de ce PID. Le calcul conserve un seul événement par PID, séquence et horodatage. La session Smash en fin d’export est exclue.

| Composant | Source | SHA-256 du binaire iOS arm64 |
|---|---|---|
| Core de la capture 777 | `7ad86a14377da6ce1f8ce51bfec2f3bc9cc16183` | `939a939ff1653f0c13788e8658c61a83d2ac8a4fe1ac0074a8051950800bb072` |
| Core prévu par le manifeste 779 | `5924dd56fc615b6d2e581ddee726cbb3e3f445e0` | `7c8509d2881b6bd0aa0717270a08829002e8547fdcfe28daa79f7bea7f88e9fe` |
| Candidat de ce compte rendu | Basé sur `Claude` à `1744224e73d2516c885b6044e96ee4eef3693d87` | Compilation Release hôte. Binaire NativeAOT iOS et IPA en attente. |

L’archive officielle du core de la 779, run `44193668756`, a pour SHA-256 `a224697b1ba8ab2d2d3bcf2168e6343faf1b4adcd27d65893304762d40f88bc0`. L’inventaire de ses entrées et les fichiers préparés confirment l’intégration d’`adapt_descriptor_pool_lifetime.py` et d’`adapt_buffer_mirror_windows.py`. Le premier binaire du tableau a servi à symboliquer les échantillons de la 777.

## Ce que montre l’iPhone

Du premier contrôle natif à 20 h 57 min 46 s UTC jusqu’à la première présentation Metal à 20 h 57 min 56 s, il s’écoule environ 10 s, dont environ 7 s depuis la création de la vue de présentation. L’instant de prise de contrôle par le joueur reste inconnu.

Sur la fenêtre t = 46–80 s, les 29 relevés de FPS moteur ont une médiane de 23,9. La scène exacte est inconnue. Les 806 intervalles de présentation totalisent 34,183 s après arrondi, soit 23,58 présentations/s. Médiane 33 ms, p95 67 ms, p99 133 ms, maximum 1 383 ms. Les compteurs de seuil avant arrondi donnent 254 intervalles de plus de 50 ms et 16 de plus de 100 ms, soit environ 446 et 28 par minute de temps couvert. Compter directement les entiers de la liste de gaps sous-estime ces franchissements. Les 809 intervalles de demande de drawable couvrent environ 34,353 s, soit 23,55 demandes/s. La médiane des maxima d’attente `nextDrawable` par relevé vaut 0,3 ms et le maximum 36,1 ms. Le journal indique `customVsync=120` et une période écran de 8,33 ms.

La dernière fenêtre de 5 026,2 ms couvre 58 images, 896,9 ms de préparation des descripteurs graphiques, 298,0 ms en compute, 4 184 382 descripteurs écrits et 22 040 parcours de références de tableaux. Elle compte 675 soumissions, dont 245 pour synchronisation stricte, 165 pour l’auto-flush des draws, 99 pour les attachments et 58 pour la présentation. Les attentes fast flush atteignent 713,1 ms. Le compteur voisin des *créations* strictes attribue 141 opérations aux syncpoints 3D, 60 à SetReference et 63 aux syncpoints en file. Aucun draw de cette fenêtre n’a attendu de compilation. Le GPU rapporte 22,7 ms/image et 26 % d’occupation. Les durées se recouvrent. Les deux profils lents symboliqués contiennent respectivement 19 et 17 échantillons en exécution sous `DescriptorSetUpdater.BindExtraSets` sur le thread de rendu.

Trois alertes mémoire se produisent à 20 h 58 min 33 s, 20 h 59 min 23 s et 20 h 59 min 38 s UTC. La seconde indique 4 892 Mio d’empreinte, 1 763 Mio de marge processus et 4 % de mémoire disponible sur l’appareil. Le dernier inventaire managé donne environ 840 Mio de heap, dont 502 Mio sur le LOH et 208 Mio libres dans celui-ci. Les caches de textures et de buffers déclarent environ 104 et 124 Mio. Les 13 453 blocs Vulkan dédiés représentent 688 Mio natifs. Les deux donneurs fournissent un mapping invité de 4 Gio. Les mappings, les compteurs de caches, le heap et les pages facturées par iOS se recouvrent. Le relevé VM partiel de la première alerte rapporte notamment 901 Mio graphiques résidents et 158 Mio graphiques compressés. Les pages physiques par propriétaire restent partiellement inconnues.

Parmi les 11 événements GC journalisés, une pause bloquante atteint 81,868 ms et une phase de pause d’un GC en arrière-plan atteint 43,016 ms. À t = 74, le journal associe 12 FPS à 518 Mio de compression additionnelle et 33 578 pages décompressées depuis la lecture précédente. À t = 76, l’appel de télémétrie dure 1 707,1 ms. Les lignes t = 76 et t = 89 sont écrites environ 10 s après la ligne précédente. L’instant exact de lecture des compteurs VM et énergie de la 777 ne peut pas être reconstruit. Les valeurs `en=` de ces lignes ne permettent pas d’estimer les watts de l’iPhone. La température passe de nominal à fair durant cette courte session.

## Modifications et vérifications

| Chemin de production | Changement et contrôle |
|---|---|
| `adapt_cached_shader_stages.py` — lecture et écriture du cache SPIR-V, GAL, création Vulkan | Chaque étage du programme garde une tranche alignée du tableau décompressé jusqu’à la fin de sa compilation, y compris en asynchrone. Le code garde la longueur réelle et les octets de chaque étage. L’écriture produit directement le format little-endian existant. Un enregistrement mal formé repart en traduction invitée et les enregistrements valides suivants peuvent toujours être utilisés. |
| `ShaderCollection` | Les clés de replay et d’emprunt entre programmes dérivent d’un seul hachage de chaque étage. Les clés, l’ordre des étages, les octets du cache et les résultats GLSL, SPIR-V graphique et compute sont comparés entre les deux versions compilées. |
| `ParallelDiskCacheLoader` | Les workers de traduction invitée démarrent à la première entrée qui demande cette traduction. Un cache vide ou entièrement validé évite huit démarrages. Le chemin de traduction conserve huit workers, la file bornée, l’annulation et la jonction de chaque thread démarré avant de libérer le contexte. |
| `adapt_descriptor_and_block_usage.py` — `DescriptorSetUpdater` | Un changement de texture ou d’image scalaire conserve les tableaux indépendants déjà liés. Une mutation du tableau, un nouveau programme ou command buffer force leur mise à jour. Les vues de buffers conservent leur traitement spécifique. Les deux exécutions du banc décodent le contenu lié à chaque draw/dispatch. Le contrôle négatif qui oublie une mutation échoue. |
| `MemoryAllocatorBlockList` | Un bloc dédié entier garde son état libre/occupé sans allouer de liste de plages. Les opérations partielles matérialisent les plages sous le verrou existant. Les compteurs de taille et de mapping sont mis à jour sous le verrou de publication et de retrait. Le pilote conserve chaque allocation jusqu’à sa véritable fin d’utilisation. Le test exerce 13 453 blocs, les octets stockés, les mappings, les échecs et huit threads partageant le même allocateur. |
| `MeloNXPerfJournal.swift` et `MeloNXHotSpots.swift` | Les lectures CPU, VM, énergie et présentation ont chacune leur horloge monotone. `win=` donne quatre couples fin,intervalle en ms depuis le début de session, dans cet ordre. Le calcul d’énergie utilise deux lectures réussies du même compteur. À fair, le parcours VM lourd est différé. À serious et critical, le profil facultatif s’arrête aussi en cours d’acquisition. Après une amélioration, le profil peut reprendre après 30 s et le parcours VM après 60 s à nominal. Une alerte mémoire suspend les deux pendant au moins 60 s. Les callbacks de crash et les appels managés susceptibles de déclencher un GC gardent leurs priorités. |

Les donneurs mappés restent sous la propriété de la session. Le trim des ressources froides et le traitement des écritures GPU restent ceux de la 779. Ce candidat conserve les barrières, les fences, les draws, la cadence invitée, le chemin audio et les paramètres de rendu.

### Comparaison sur hôte

Le banc .NET 10 Release compare les sources du core 779 aux modifications. Les processus de chargement sont alternés dans l’ordre témoin, candidat, candidat, témoin. Chaque processus exécute cinq passages après échauffement. Le lot synthétique compte 1 024 programmes à deux étages et 208 Kio de code par programme. Les contrôles de format utilisent séparément de vrais shaders SPIR-V vertex, fragment et compute du dépôt.

| Travail délimité | Core 779 sur hôte | Candidat sur hôte |
|---|---:|---:|
| Lecture du cache et calcul des clés de 1 024 programmes, médiane | 57,61 ms | 10,94 ms |
| Allocations managées de ce même travail | 218 505 216 octets | 90 112 octets |
| Construction et contrôle de 128 entrées nouvellement traduites, médiane | 5,58 ms | 5,09 ms |
| Accès au tableau indépendant pour 400 changements scalaires | 400 | 0 |
| Binds Vulkan sur ces 400 changements, avec 2 396 descripteurs de base écrits | 1 199 | 799 |
| Mémoire managée allouée pour construire 10 000 blocs dédiés | 1 760 000 octets | 1 040 000 octets |
| Démarrages de workers invités pour un cache vide ou entièrement valide | 8 | 0 |

Les 544 observations de descripteurs donnent la même trace. L’allocateur ajoute deux compteurs de 64 bits par liste et économise 72 octets managés par bloc dédié entier, soit 0,92 Mio pour 13 453 blocs sur le runtime hôte. Le volume natif alloué reste identique. Les allocations de lecture du cache sont cumulées sur le lot. La mesure de RAM résidente nécessite un appareil. La compilation des bibliothèques du moteur et la lecture du cache sur hôte établissent ce qui se passe dans ces chemins. Le délai jusqu’au premier mouvement jouable, la fluidité, l’audio et la chauffe du candidat restent à mesurer sur iPhone.

Le contrat de composition a passé 519 contrôles. Les 238 fichiers de l’archive de sources préparée ont été comparés aux fichiers du moteur et les 272 entrées de préparation ont été vérifiées. Le banc du chargeur de shaders a passé 28 contrôles et celui de sa durée de vie en a passé 214, y compris en cas d’annulation, d’échec ou de fermeture concurrente. Les tests de miroirs et de durée de vie des pools ont aussi été rejoués. Les 70 contrôles du journal de performances ont réussi. Le moteur modifié a été compilé en Release sur Linux. Les fichiers Swift ont également passé l’analyse syntaxique pour la cible iOS arm64. La compilation et l’édition de liens avec le SDK Apple restent à effectuer.

## Parcours iPhone à reproduire

1. Utiliser le même iPhone, la même sauvegarde, la même version de Hogwarts et les mêmes réglages à 1x. Consigner pour chaque essai la charge, le branchement, la luminosité, l’état thermique initial, l’état des caches et la provenance du core. Mesurer séparément un premier passage à cache froid, puis trois lancements à cache chaud. Conserver le cache usuel.
2. Horodater le lancement, la première présentation, le chargement terminé et le premier mouvement du personnage. Écarter lancement et menus des percentiles de jeu. Utiliser le journal applicatif et un repère de scène pour la première image jouable.
3. Depuis la même sauvegarde, marcher cinq minutes dans les jardins, tourner la caméra aux mêmes repères et lancer les mêmes sorts. Continuer dix minutes sur le même trajet extérieur, puis revenir trois minutes. Relever la cadence par segment et sa dérive entre les cinq premières et les cinq dernières minutes.
4. Tester séparément 30 s de menu puis une perte et une reprise d’activité. Comparer le rendu des sorts, ombres et végétation, le son, la reprise, les pauses >50/>100 ms par minute, les avertissements, GC, compression, descripteurs, soumissions et temps GPU. Utiliser les temps de lecture `win=` pour les taux du candidat et signaler les fenêtres incomplètes.

Aucune session iPhone de ce candidat n’a été exécutée. L’IPA 779 demeure le repère du mainteneur. Le déclenchement privé de la recette Apple et la prochaine IPA attendent son ordre.
