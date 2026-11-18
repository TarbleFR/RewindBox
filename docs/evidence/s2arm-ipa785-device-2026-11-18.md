# Switch 2 sur iPhone — essai de l’IPA 785 du 18 novembre 2026

Mario Kart World en course sur iPhone17,2 (A18 Pro, 8 Go, iOS 27). Le reçu de la 785 et le dernier lancement du journal donnent le moteur du run 44230830821, correctifs 0001–0093. Le groupe de travail est actif. La 785 est la base livrée et mesurée. [Reçu de l’IPA 785](rewind785/delivery.json)

| Mesure sur iPhone | IPA 783 | IPA 785 |
| --- | ---: | ---: |
| Images journalisées de plus de 100 ms | 62 en 193 s (19,3/min) | 50 en 211 s (14,2/min) |
| Images journalisées de plus d’une seconde | 13 | 6 |
| Pire image | 4 401 ms | 5 413 ms |
| Traductions effectuées sur le fil d’envoi | 0 | 0 |
| Attentes de traduction sur le fil d’envoi | 34, 1 335 ms cumulées | 19, 947 ms cumulées |
| Bibliothèques Metal compilées sur le fil d’envoi | 36, 8 412 ms cumulées | 17, 2 860 ms cumulées |
| Lignes de préchauffage écartées faute de traduction actuelle et d’octets conservés | 951 pour 503 clés | 860 pour 459 clés |
| Plus grande coupure audio relevée | 399 ms | 126 ms |

Les deux passages couvrent des scènes et des caches différents. Les comptes portent sur les images journalisées. Le taux dans le tableau correspond à la durée entre la première et la dernière image journalisée.

- **Départ et changement de scène.** Sur la 785, des pipelines ou bibliothèques Metal sont en cause dans les six images de plus d’une seconde et dans 14 des 15 images de plus de 500 ms. À l’image 2841, l’attente des 41 pipelines prend 3 993 ms. Les premiers envois de 746 textures prennent 692 ms pour 175 Mo, avec 426 Mo lus sur le stockage et 40 ms de travail GPU. L’image 129 prend 999 ms, avec 59 968 pages relues et zéro nouveau pipeline ou bibliothèque.
- **Course.** Les 398 images consécutives 3289–3686 sont toutes à 1248 × 700, avec 2 492 appels de dessin par image en médiane. Temps d’image p50/p95/p99 de 25,85/47,99/90,49 ms, et 15,6 images de plus de 100 ms par minute. Dans les fenêtres de 300 images autour de ce passage, le GPU prend 17,17 à 18,52 ms en médiane et l’envoi NVN avec la présentation 21,51 à 22,31 ms. Ces temps se recouvrent. Après l’image 3900, plusieurs fenêtres donnent 20,21 à 23,88 ms en médiane, soit 42–49 FPS. Pour tenir 60 FPS, l’envoi et le GPU doivent chacun tenir 16,67 ms.
- **Mémoire et chaleur.** La mémoire compressée du processus atteint 1 140 Mo. Les relevés de 10 s montent à 148 956 lectures de pages, 177 948 compressions, 122 814 décompressions et 1 453 Mo lus. Les sondes par type de mémoire s’arrêtent à leur limite de temps. Elles voient jusqu’à 402 Mio compressés dans des régions anonymes hors de la fenêtre du jeu, avec des tags 0, 88 et 2 parmi les premiers. L’attribution du reste est ouverte. Pendant la grande saccade, Metal tient 3 093 Mo dans son ensemble résident, dont 1 220 Mo de textures, 1 024 Mo de tas et 588 Mo de tampons de pools. Le 0089 a ramené sept tampons d’envoi à 4 Mo, soit 156 Mo de capacité en moins. Les lectures anticipées autour des pools ont demandé 3 056 Mo en tout. L’état thermique devient sérieux à l’image 6041.
- **Démarrage et fermeture.** Le moteur démarre 5,0 s après la demande de lancement. Le préchauffage dure 7,4 s. Il récupère 3 589 pipelines d’une archive de 4 032. La session s’arrête en 883 ms après Quitter, avec le code 0 et un refus de mise en veille. Ensuite, la capture montre le message d’absence du moteur Switch au lancement de Hogwarts Legacy. Le pont condensait le refus de charger un deuxième moteur NativeAOT en une erreur d’indisponibilité. Le refus existe même après un arrêt normal du jeu.

| Priorité | Travail | Gain attendu et risque |
| --- | --- | --- |
| 1 | Conserver les entrées des shaders de jeu déjà enregistrés, réutiliser les pipelines d’une course à l’autre et limiter les compilations urgentes au moment où elles servent. | Fort sur les changements de scène. Vérifier le temps de chargement, les lectures et la chauffe. |
| 2 | Réduire les accès mémoire et le coût CPU mesurés dans les calculs d’envoi. Garder les premiers envois, les tris de pools et les compilations visibles séparément dans le journal. | Moyen sur la cadence, la chauffe et les petits à-coups. Conserver la réserve de textures et le rendu. |
| 3 | Publier la cause réelle du blocage Switch. Vérifier les chemins de fermeture et de relance de la Switch 2 avec le moteur suivant. | Faible risque pour le message. Le chargement de deux moteurs NativeAOT et leurs gestionnaires iOS dans le même processus demande une validation distincte. |

Les correctifs 0094–0099 étaient épinglés sur Claude lorsque la 785 a été livrée avec le moteur précédent. Leur effet sur la chauffe et la relance reste à mesurer. Les journaux de cet essai ne couvrent pas l’écran noir de Fast Fusion.

Pour comparer sur iPhone, lancer deux fois le même parcours pendant cinq minutes, avec la même luminosité et le même profil. Comparer les longues images par minute, les p50/p95/p99, les attentes de pipeline, les relectures, les trous audio et le temps avant l’état thermique sérieux. Quitter depuis une course, relancer Mario Kart World, puis essayer une autre console et Hogwarts Legacy. Renvoyer `engine.zip`, `s2arm-journal.jsonl` et `profiles.zip`.
