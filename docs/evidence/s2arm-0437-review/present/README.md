# Durée des lectures source et admission de présentation

## Constats sur le code livré

Les manifestes 843 et 844 épinglent le même S2Arm amont `6b6a571` et respectivement les producteurs `06b4743f2` et `197dd41ab`. Les versions du pont iOS, de sa préférence et du menu sont identiques. La préférence par jeu initialise `S2A_RB_FI` au lancement. Un processus démarré sans armement renvoie −1 au commutateur. Le backend Metal 3 et une désactivation pour incompatibilité renvoient −2. Dans les deux versions, la génération classique exige un palier déclaré d’au plus 45 Hz, puis un écart entre entrées positif d’au plus 1,25 période. L’historique retient le dernier ticket admissible et exige deux entrées consécutives. Une présentation fournie par la display link, un format de couche incompatible et l’activation d’un patch de cadence peuvent exclure une image. Le calcul de période NVN et le filtre transitoire de huit images, l’armement et le choix MetalFX puis image réelle sont identiques octet par octet aux emplacements vérifiés par `cadence.py`. La grille C obtient 1 412 190 mêmes décisions, dont 165 632 admissibles.

Le patch 0405 de la 844 change la file Metal, les attentes de producteur, la résidence et l’ordre de libération des tickets. Le patch 0418 de la 845 rend ensuite la file dédiée optionnelle. Des changements de coût et de synchronisation peuvent influer sur les intervalles que la règle reçoit. La comparaison de source ne permet donc pas de déterminer la cause des FPS sur appareil. Aucun jeu ni fichier utilisateur ne participe à la reproduction.

## Durée de vie

Le slot 1 lit la texture source même lorsqu’il prépare uniquement l’historique et ne produit aucune image à afficher. Le slot 2 lit la même source pour l’image réelle. Sur le chemin original, l’absence du second drawable ou son échec avant soumission termine immédiatement le ticket pendant que la commande GPU du slot 1 peut encore lire la texture. Même lorsque les deux soumissions réussissent, le retour CPU du slot 2 ouvre le ticket sans vérifier celui du premier. Le calcul des statistiques du slot 1 pouvait encore lire `mvFlag.contents` après la remise du sémaphore de réutilisation du slot.

Le correctif enregistre les deux fins dans la section critique existante de feedback. Chaque lecture se termine soit en feedback GPU, succès ou erreur, soit sur un chemin qui ne soumet aucune commande pour ce slot. Une allocation nulle de MTL4CommitOptions fait abandonner la soumission avant la prise du sémaphore. Un callback reçu avec un argument nul termine la commande mais n’exploite aucun résultat de motion. Un callback manquant conserve le ticket. L’absence de drawable intermédiaire permet toujours de copier l’entrée. La perte de possession de la couche avant les deux lectures garde sa terminaison immédiate. Le stock statique ajouté est de 128 octets pour huit tickets. Le chemin réussi utilise les sections critiques de callbacks existantes et supprime le callback applicatif de fin propre au slot 2.

Le sémaphore du slot est rendu après le dernier consommateur CPU de son feedback. La table d’arguments et les ressources d’interpolation restent couvertes par le slot et sa procédure `fi_drain`. Les blocs de feedback retiennent les objets qu’ils capturent sous ARC. Pour la file dédiée, le ticket conserve aussi `g_rb_present_source` et le pin de la texture parente ou de son tas. Pour la file partagée, la correction maintient l’attente du ticket aux deux chemins `nvnWindowAcquireTexture` avant la prochaine écriture. Les callbacks de présentation à l’écran utilisent le numéro de ticket et les compteurs de drawable, sans lecture supplémentaire de la source. Le test hôte simule les lectures GPU, les objets et la résidence. Le comportement de rétention d’Apple reste à vérifier sur appareil.

## Capacité et arrêts

`present_enqueue` pouvait perdre la seule place libre pendant le déverrouillage autour de `DM_BLOCK_END`. Avec deux producteurs et une retraite, le témoin pthread atteint neuf tickets pour huit places. La nouvelle boucle vérifie à nouveau la capacité avec le mutex tenu et donne un pic de huit. La lecture de `g_present_discard` permet aussi de sortir de la boucle.

Les tickets de présentation commencent à 1 et augmentent par `++g_pq_in`. La fin contiguë augmente dans `rb_present_complete`. Le code de fin de session déplace le lecteur sur la fin de file et conserve les numéros absolus. Un ticket passé en file mais jamais pris peut être écarté, après distinction par `g_pq_read`. Les chemins de suspension et de display link bloquée attendent les travaux déjà en encodage et les callbacks en vol. Le même mutex publie les deux fins et le décrément final des callbacks. Le drain de session attend également la sortie du thread display link et du présentateur classique. Son expiration à dix secondes renvoie une erreur avant de libérer les tickets restants. `host_adapt.m` propage cette erreur. L’aide `session_wait_backend` contrôle ensuite séparément les fences de rendu ainsi que les travailleurs concernés. Un arrêt GPU où une commande ne rapporte jamais son résultat n’établit pas qu’une nouvelle session peut démarrer. L’attente de stall sans résultat GPU peut continuer indéfiniment.

## Reproduction Linux

Prérequis Python 3, Git, GCC pour la localisation des en-têtes GNU Objective-C, Clang, pthread, les bibliothèques de développement GNU Objective-C et BlocksRuntime. Les sources du moteur doivent être déjà préparées par les patches de RewindBox. Le dossier CANDIDAT peut être préparé en appliquant le [patch 0445](../../../../build-utils/s2arm/engine/patches/0445-complete-presentation-after-both-readers.patch) à une copie de la référence. Cette copie sert seulement aux tests hors dépôt. L’outil `reconstruct.py` utilise le dépôt RewindBox et un clone de l’amont qui contient le commit épinglé.

```sh
python3 reconstruct.py "$REWINDBOX" "$UPSTREAM" "$DOSSIER_SORTIE/sources"
python3 cadence.py "$DOSSIER_SORTIE/sources"
python3 run_probe.py "$REFERENCE"
python3 run_probe.py "$CANDIDAT"
python3 run_admission.py "$REFERENCE/graphics/nvn/gfx/nvn/nvn_mtl.m"
python3 run_admission.py "$CANDIDAT/graphics/nvn/gfx/nvn/nvn_mtl.m"
```

Les deux commandes témoins sortent avec le code 1 quand elles reproduisent le défaut. Les commandes corrigées sortent avec le code 0. La variable facultative `BLOCKS_PREFIX` indique un préfixe alternatif contenant les en-têtes et la bibliothèque statique x86_64 de BlocksRuntime. `run_probe.py` extrait les corps de `fi_commit`, `fi_job`, du règlement du ticket et des deux attentes de drain. Seule l’enveloppe d’autorelease est remplacée pour le runtime GNU. Un retour via le stub représente une commande GPU terminée. Le traitement de recevabilité est vérifié par des compilations C indépendantes depuis chaque version livrée.

Les 1 920 scénarios couvrent la perte ou le transfert de couche, la soumission sans image intermédiaire, les deux drawables, les échecs d’encodage, d’options de feedback, les erreurs et retours nuls des callbacks, les achèvements immédiats, différés et inversés. ASan et UBSan sont actifs. Le témoin donne 681 cas divergents et le candidat zéro. Le test supplémentaire du candidat vérifie 8 000 tickets groupés par huit avec des notifications répétées et retardées ainsi que les deux attentes de drain avec des callbacks inversés. Un timeout de shutdown est injecté séparément. Les contrôles de fuites de fin de processus sont désactivés pour le registre GNU Objective-C. Les objets de fixture vivent pendant l’essai.

```sh
BENCH_BINARY=base.bin python3 run_probe.py "$REFERENCE"
BENCH_BINARY=candidate.bin python3 run_probe.py "$CANDIDAT"
python3 timing.py
```

Exécuter ces trois commandes depuis le répertoire contenant les scripts. Le banc de coût utilise deux exécutables optimisés, 10 000 échauffements et 200 000 parcours réussis par mesure, sur 32 paires en ordre alterné. Le temps CPU du thread change de −6,78 % en médiane appariée, avec un intervalle par rang entre −7,22 % et −5,66 %. Le témoin A/A donne +0,75 % entre −0,33 % et +1,19 %. Les colonnes brutes se trouvent dans `results/timings.tsv`. Ces chiffres décrivent le coût CPU de ce banc GNU, sans mesure de FPS, d’énergie, de GPU Apple ou de fluidité physique.

Le correctif moteur actif de durée de vie porte le numéro 0445. Pour reproduire séparément le cas de la file de résidence (0446), exécuter `python3 check_residency.py /chemin/arbre`. Le script extrait les instructions d’inscription et de retrait ainsi que le choix de la file. Les deux doubles Objective-C comptent chaque inscription et chaque retrait sur le mauvais propriétaire. Le dernier jeu est détaché après le vidage de la session. [Sémantique Metal de retrait de résidence](https://developer.apple.com/documentation/metal/mtl4commandqueue/removeresidencyset%28_%3A%29).
