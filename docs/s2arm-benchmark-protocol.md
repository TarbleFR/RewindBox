# Banc d’essai Switch 2 — protocole v1

Le lot 0171 établit une référence reproductible avant toute nouvelle réduction
de cache, de préchargement ou de qualité. La première IPA qui le contient est une
**référence de départ**, pas une preuve de gain par rapport aux anciennes IPA.
Les mesures historiques restent utiles pour trouver une cause, mais ne sont pas
comparables à une fenêtre choisie autrement.

## Une comparaison valide

Comparer l’IPA précédente et la candidate sur le **même iPhone**, avec le même
jeu et sa même mise à jour, la même sauvegarde, le même scénario de 180 secondes,
les mêmes réglages réellement appliqués, la même manette et le même état initial
des caches. Conserver les caches compatibles et les sauvegardes. Ne pas effacer
le cache de shaders entre deux essais d’une comparaison à cache chaud.

1. Choisir un contre-la-montre ou une séquence rejouable, avec un point de départ
   visuel précis. Noter circuit/scène, véhicule/personnage, règles, actions et
   repère de départ. Le moteur n’a aucun identifiant de circuit privilégié.
2. Parcourir une fois ce scénario pour remplir les caches, quitter proprement le
   jeu, puis laisser le téléphone refroidir. Le protocole de cache est
   `warm-route-v1`. Une étude de premier lancement/cache froid sera une comparaison
   séparée, explicitement nommée, avec le même état initial des deux côtés.
3. Débrancher le téléphone. Garder le même environnement, luminosité, mode
   d’alimentation, accessoire et plage de batterie. Attendre un téléphone froid
   au toucher et un état thermique normal. L’état thermique normal seul ne prouve
   pas une température physique identique ; la confirmation humaine est notée.
4. Relancer RewindBox, puis le même jeu. Attendre la fin des préparations. Revenir
   au même repère. Ouvrir ☰ → Banc d’essai, donner un nom de scénario identique
   aux essais, vérifier les conditions, puis démarrer. La fenêtre commence après
   fermeture du dialogue. Elle dure 180 secondes sans modifier la vitesse du jeu.
5. Refaire les mêmes actions. Ne pas ouvrir de menu, changer un réglage, enregistrer
   l’écran, brancher le téléphone ou passer l’application en arrière-plan. Ces
   événements rendent l’essai non comparable lorsqu’ils sont détectés.
6. À la fin, laisser le jeu tourner le temps du relevé mémoire de fond. Ce relevé
   commence **après** la fenêtre qui sert au score. Quitter ensuite normalement
   afin de récupérer les journaux via l’export habituel de diagnostics.

Pour une conclusion de performance, faire trois fenêtres valides par version,
avec refroidissement entre elles et ordre alterné A/B puis B/A. Publier chaque
fenêtre et la dispersion, pas seulement la meilleure. Une hausse des images
longues, des trous audio ou de la chaleur interdit de conclure à une amélioration
globale sur le seul FPS moyen. Les trois répétitions sont un protocole appareil,
pas une nouvelle suite automatique de tests du moteur.

## Ce que la synthèse doit séparer

| Mesure | Sens et limite |
|---|---|
| Temps d’image p50/p95/p99 | Intervalles observés pendant la fenêtre, avec dénominateur et couverture. Distinguer soumissions du moteur et présentations Metal réellement confirmées. |
| Images >100/200/500 ms par minute | Comptes strictement supérieurs au seuil, divisés par la durée mesurée ; un intervalle manquant à une frontière n’est pas inventé. |
| FPS affichés | Présentations confirmées par Metal, et non nombre de tours CPU. Les callbacks encore absents après le délai de collecte rendent la couverture incomplète. |
| Part du temps à 30/60 | Période réellement envoyée à la présentation ; intervalle demandé par le jeu publié séparément. Les modes autres/inconnus restent visibles. |
| État thermique | Durée dans chacun des quatre états ; ce n’est pas une mesure de watts ni une température de composant. |
| Pages et compression par 10 s | Deltas et durée réelle de chaque tranche. Séparer page-ins du processus et compteurs de toute la machine. Un page-in ne prouve pas la relecture du même fichier. |
| Mémoire | Footprint, compressed **logique**, ledgers graphics et leur compressed logique. Ne pas additionner des vues comptables qui se recouvrent. |
| Metal | `currentAllocatedSize` est une allocation comptabilisée par Metal, pas la mémoire GPU résidente. Une résidence non mesurable reste indisponible. |
| Son | Estimation de manque de frames, callbacks retardés, underruns, reprises et sessions de sortie. Cela n’est pas une mesure acoustique de tous les trous entendus. |
| GC .NET | Collectes par génération, octets alloués, pause cumulée et alerte de fréquence/pause ; aucune pause maximale individuelle inventée. |

Les identités source, moteur, IPA, appareil, OS, jeu, protocole et réglages appliqués
accompagnent la fenêtre. Des préférences modifiées pour le prochain lancement ne
doivent pas être présentées comme les réglages de la session en cours.

Les intervalles audio sont comptabilisés à leur observation par le producteur ou
le callback ; une estimation peut couvrir une frontière de fenêtre. Les trous
visuels de début/fin sont des bornes censurées séparées des intervalles complets.

Une fenêtre interrompue, une perte de données, une identité absente ou un changement
de conditions est conservé avec sa raison et exclu d’une conclusion de gain. Une
fin par crash peut ne laisser aucune synthèse : l’absence n’est jamais un succès.

## Attribution mémoire après le score

Le parcours complet descend les sous-cartes VM et inclut tous les tags, dont le
tag 32. Il tourne sur une file de fond, sans toucher les octets du jeu. Il publie
début, fin, durée, couverture, statut et ledgers associés. Il s’annule si la
génération de session change ou si le jeu s’arrête. Il ne bloque pas l’interface.

Ce parcours n’est pas atomique : le jeu continue à allouer pendant son exécution.
Les alias peuvent compter plusieurs fois les mêmes pages. Sa somme par mapping
ne constitue donc pas un footprint physique. Un appel Mach peut durer longtemps
sous verrou noyau ; aucune limite dure de quelques millisecondes n’est promise.

Le poste dominant doit être retrouvé sur plusieurs parcours complets et rapproché
des ledgers avant de réduire son budget. Le volume compressed correspond à la
taille d’origine des pages comptabilisées, pas à l’espace physique du compresseur.
La part graphics compressed ne doit pas être soustraite automatiquement du total
compressed comme si les deux formaient une partition garantie.

## Lecture anticipée, processeur, son et chaleur

Les compteurs actuels de 0089 indiquent des conseils de lecture et des pages
absentes, pas des lectures utiles terminées. La mesure à ajouter ensuite distingue
conseils acceptés, pages uniques suivies, demande ultérieure, résidence à la
demande et lecture naturelle confirmée. Expirations, pertes et couverture inconnue
ne deviennent pas des « pages inutiles ». Aucun budget ne baisse sur la seule
quantité de conseils envoyés.

Les profils CPU et les captures GPU intrusives sont des passes diagnostiques
séparées du score. Chercher le producteur d’une attente avant de toucher une
barrière. Le coût GPU, disque et compression ne se déduit pas de leur coïncidence
avec l’état thermique ; il faut une intervention isolée et le même protocole.

Pour le son, mesurer d’abord manque de frames et retard des callbacks. La marge
de tampon, le groupe de travail audio et une reprise sans redémarrage seront un
lot séparé si les données le justifient ; aucune augmentation de latence cachée.

Un mode endurance est **proposé**, pas activé par 0171 : résolution plus basse et
cadence stable de 30 i/s seulement si le jeu conserve sa bonne vitesse. Il exige
une comparaison de qualité, cadence, audio et durée en état thermique sérieux.

## Régression et remise

Appliquer ce protocole à Mario Kart World puis aux jeux `04007EF01F8AE000` et
`040041E0212AE000`, actuellement satisfaisants d’après le mainteneur. Vérifier
aussi vitesse du jeu, commandes, rendu, son, sauvegarde, arrêt et reprise. Une
compilation seule ne valide aucune de ces observations sur iPhone.

Chaque bilan indique **corrigé**, **compilé**, **livré**, **observé** séparément.
L’IPA reste privée selon la recette standard. Les journaux bruts privés ne sont
pas ajoutés au dépôt. Seuls des agrégats anonymisés et identités vérifiées y vont.

Références : [recette](standard-delivery-recipe.md),
[intégration moteur](s2arm-engine-bridge.md),
[audit de cadence](evidence/s2arm-cadence-803.md).
