# Wiimmfi — navigation terminée et défauts corrigés

Suite à `bfb58ac3`, le défaut de navigation manette encore ouvert dans la [contre-expertise](wiimmfi-followup-audit-2026-11-27.md) est corrigé. Les correctifs précédents restent présents ; aucun défaut Wiimmfi identifié dans ces revues n’est laissé ouvert en source.

| Parcours | Correction |
| --- | --- |
| Propriétés du jeu et réglages Wii | Entrée Wiimmfi sélectionnable, indices sans collision, défilement et refus des doubles ouvertures |
| Écran Wiimmfi | Navigation haut/bas, commandes A/B, actions désactivées ignorées, sélection visible et défilement automatique ; toucher et clavier conservés |
| Confirmations, diagnostic, catalogue et lancement | Chaque modale possède les entrées ; un retour ferme uniquement l’enfant et restaure son parent |
| Codes d’erreur | Sélecteur de cinq chiffres : directions, A/B, chiffres du clavier et boutons tactiles ; lien officiel construit depuis le code validé |
| Import | Sélection de fichier native prioritaire ; annulation disponible pendant extraction/préservation, jamais pendant le commit ; fermeture bloquée pendant l’opération |
| Initialisation/fermeture rapide | Génération d’initialisation : une découverte tardive ne rattache plus les écouteurs après destruction ; clavier retiré aussi sur iOS, réinitialisation conservée |
| Activation au clavier | Un seul propriétaire des raccourcis ; garde de fermeture et identité propre à chaque confirmation, sans double activation de la commande située derrière |
| Liens officiels | Navigateur système et suspension/rétablissement des entrées avec le cycle de vie, sans assimiler le premier chargement d’un navigateur intégré à sa fermeture |

## Vérifications

- **35 tests existants réussis** : 10 Wiimmfi, 4 confirmations, 14 navigation/défilement/couches/répétition et 7 parcours de lancement. Aucun nouveau test ni suite défini ; scénarios pertinents renforcés dans les tests existants.
- Scénario réel des widgets avec boutons A/B simulés via le canal gamepad et clavier : annulation d’une confirmation, priorité au sélecteur natif, retour du catalogue, édition/validation du code `23899`, routage hors ligne/en ligne et restauration du parent.
- Initialisation retardée, appels concurrents, destruction et réinitialisation exécutés ; aucun écouteur tardif après destruction ni commande clavier ressuscitée.
- Analyse Dart ciblée sans problème ; `pubspec.lock` inchangé, `git diff --check` propre. Les widgets ont été compilés par Flutter Test, pas en application iOS complète.
- Les entrées source du Core ABI 4 sont identiques aux empreintes du [run 45979848094](https://github.com/TarbleFR/RewindBox/actions/runs/45979848094), binaire `a8c4540d…fb4aee6`. Aucun moteur recompilé pour ces seuls changements Dart ; aucune IPA produite ni manifeste de livraison remplacé.

## Validation sur appareil

Les commandes physiques sur iPhone, l’import d’une vraie NAND, les attributs de protection iOS, l’authentification et les courses Wiimmfi restent à observer dans une future IPA autorisée. Ce sont des validations non exécutées, aucune promesse de multijoueur fonctionnel ni de certification exhaustive. Les anciens échecs CI hors périmètre restent documentés ; aucun test n’a été affaibli pour les masquer.
