# Parallélisme S2Arm NVN2 · A18 Pro

## État au 27 novembre 2026

Le rendu peut déjà employer plusieurs command buffers et trois jeux de ressources de présentation. Le travail sur cette branche avance la remise des commandes à l’encodeur et permet certains calculs invités pendant un rejeu en cours. Les options de performance restent désactivées au démarrage. Le refus de présentation Metal 3 doit rendre immédiatement la réservation correspondante, quel que soit le profil.

| Changement | Activation pour un essai | Témoin |
| --- | --- | --- |
| Publier le premier lot prêt au 65e enregistrement, si l’encodeur est disponible | `S2A_RB_REC_EARLY=1`, fil d’encodage actif | `S2A_RB_REC_EARLY=0` |
| Calculer sept handles indépendants pendant un rejeu | `S2A_RB_REPLAY_SCALAR_QUERIES=1` avec `S2A_RB_REPLAY_WORKER=1` | Même worker, requêtes scalaires à 0. Comparer également au profil usuel où le worker est arrêté. |
| Chercher un des trois slots libres dans le délégué d’affichage NVN2 | `S2A_RB_PRESENT_FREE_SLOT=observe` pour compter les occasions, puis `=1` pour les utiliser | `=0`. Redémarrer le processus entre bras. |
| Horodater les commandes et tickets natifs | `S2A_RB_PARALLEL_TRACE=1`, début de fenêtre optionnel `S2A_RB_PARALLEL_FROM=N` | `=0` |
| Suivre une même session sur 30 minutes | `S2A_RB_PARALLEL_LONG=1` puis démarrer le Banc d’essai habituel. Le compagnon continue après la fenêtre standard de 180 s. | `=0` |

Le journal Mario Kart World du 20 novembre confirme Metal 4 sur A18 Pro. Sur iPhone, le sélecteur direct choisit Metal 4 à partir d’iOS 27 si le GPU appartient à la famille Metal 4. iOS 26.x utilise Metal 3 pour la compatibilité de la présentation. La valeur explicite `NXGAL_BE=mtl3` sélectionne aussi Metal 3. Les deux séries hors écran et le rejeu de 189 images ont sélectionné Metal 3 sur GPU Apple paravirtualisé. Les comparaisons techniques et les limites figurent dans le rapport ci-dessous.

## Lire une capture

```sh
python3 tools/s2arm_a18pro/parallelism/timeline.py engine.log --timeline timeline.json > frames.json
python3 tools/s2arm_a18pro/parallelism/wait_summary.py engine.log --out waits.json
```

Ouvrir `timeline.json` avec Perfetto. Une piste montre la fenêtre murale de préparation, une autre le travail de la file principale entre les horodatages GPU et la troisième les affichages confirmés. Les identités de soumission, segment et ressource figurent dans les événements. Utiliser un journal par lancement. Un intervalle manquant ou un ticket sans preuve d’affichage reste visible dans les compteurs de couverture. `observed_display_interval_ms` inclut les grands écarts entre deux affichages observés malgré un saut de ticket. `consecutive_presentation_interval_ms` isole les paires consécutives.

## Décisions à prendre sur appareil

1. Comparer témoin/candidat individuellement à 1×, interpolation coupée, en commençant par le cas d’usage réellement rencontré. Examiner les pires images autant que les médianes. Conserver les caches et le gouverneur identiques.
2. Choisir un mode de profondeur à partir de sa latence, de son énergie par image et de son débit sur appareil. Les bras de profondeur 1, 2, 3 et adaptative sont implémentés dans le banc Metal hors écran. Les plafonds de soumissions, d’allocateurs et de tickets du moteur ne dénombrent pas les images natives d’un jeu multifile.
3. Relever chaque attente sur le chemin causal. Avant de retarder un réemploi, prouver la dernière lecture, y compris par le présentateur. Les quatorze opérations de synchronisation de référence restent nécessaires au scénario concerné.
4. Vérifier les quatre circuits MKW 150 cc, Zelda et Fire Emblem sur trois répétitions de 30 minutes par configuration admissible. Rapporter minutes 1, 5, 10, 20 et 30, interruptions audio, progression au-delà de la frame 3234 et incidents de fermeture.

[Preuves, commandes et limites](../../docs/evidence/s2arm-parallelism/README.md) · [Architecture, compteurs et protocole physique](../../docs/evidence/s2arm-parallelism/architecture.md)
