# Wiimmfi — même parcours visuel que Nextendo

Après `61658cbd`, Wiimmfi reprend les composants et la hiérarchie simples de Nextendo. Les services gardent leur authentification propre ; aucune identité Wii ni connexion serveur n’est inventée.

| Étape | Nextendo | Wiimmfi |
| --- | --- | --- |
| Accès principal | Menu d’import de la playlist Switch → Nextendo | Même bouton partagé, playlist Wii → Wiimmfi ; aucune entrée sur GameCube |
| Identité | Connexion au compte, puis fiche du compte | Préparer ma Wii, puis fiche de console importée et changement de console |
| Activation | Services en ligne | Même composant Services en ligne ; guide la préparation manquante avant activation |
| État | Une ligne synthétique | Une ligne synthétique, limitée à la préparation locale ; connexion effective dans le jeu |
| Jeux | Catalogue replié | Candidats repliés, toujours indiqués non vérifiés |

`OnlineServiceIdentitySection` et `OnlineServicesSwitch` sont utilisés par les deux services. Nextendo ne change pas sa connexion, ses serveurs ou ses jetons. Wiimmfi garde la NAND de la propre Wii du joueur et la déclaration explicite d’un jeu déjà préparé avec le patcher officiel.

## Parcours Wiimmfi

1. Ouvrir Wiimmfi depuis le menu de la playlist Wii ; Propriétés → Gérer et Paramètres système restent des accès secondaires au même écran.
2. Préparer la Wii ou activer directement Services en ligne : si la NAND manque, confirmation et sélection BootMii sont proposées. Une annulation n’active pas les services.
3. Depuis les paramètres Wiimmfi du jeu, enregistrer l’image préparée ; activer les services propose aussi cette étape si elle manque.
4. Lancer le jeu puis utiliser son menu en ligne. L’écran global rappelle la préparation/déclaration du jeu ; un jeu enregistré n’est pas présenté comme une authentification serveur réussie.

Le diagnostic, les codes d’erreur, l’aide officielle et la suppression de configuration sont regroupés sous Aide et réglages avancés. Navigation manette/clavier, retour au parent, progression et annulation restent conservés. Les réponses locales tardives sont écartées par génération et le parent récupère ses entrées après disparition complète de la modale.

## Vérifications et limites

- 10 tests Wiimmfi existants renforcés : composants communs, détails repliés, switch guidé avec NAND manquante et annulation, retour à une console prête, codes, lancement hors ligne/en ligne et écran global honnête.
- 32 tests Nextendo existants réussis ; contrat existant du bouton d’import intégré adapté au composant partagé et réussi. Analyse Dart ciblée sans problème, aucune nouvelle suite ni test défini.
- Core Dolphin ABI 4 et entrées moteur inchangés, réutilisation du [run 45979848094](https://github.com/TarbleFR/RewindBox/actions/runs/45979848094). Aucun moteur recompilé ni IPA produite ; `pubspec.lock` et données joueur conservés.
- Authentification/courses Wiimmfi, import réel et commandes physiques sur iPhone restent non validés. L’interface ne lance aucun test réseau supplémentaire à l’ouverture et ne certifie pas le patch du jeu.
