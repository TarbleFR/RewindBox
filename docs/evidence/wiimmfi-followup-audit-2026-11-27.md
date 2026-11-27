# Wiimmfi — confirmation et défauts supplémentaires

Revue de `e0c4a54c` le 27 novembre 2026. Les [corrections précédentes](wiimmfi-counteraudit-2026-11-27.md) sont présentes ; leur [Core ABI 3 compilé](https://github.com/TarbleFR/RewindBox/actions/runs/45977483996) correspond aux empreintes enregistrées. Cela ne validait pas tous les parcours applicatifs.

| Nouveau défaut confirmé | Scénario et correction |
| --- | --- |
| Dossier courant vide prioritaire sur une sauvegarde importée | Dolphin peut créer `data/` avant la première sauvegarde. La fusion supprimait alors les données du dump. Priorité actuelle seulement aux fichiers utiles ; même règle pour les Mii, liens toujours refusés. |
| Suivi de fin de partie absent depuis le panneau Wiimmfi | L'appel direct au service enregistrait une partie sans démarrer le gestionnaire de clôture. Passage par le dialogue complet de lancement pour libérer temps joué et médias à la sortie. |
| Fermeture impérative pendant une opération | Les croix parentes contournaient `PopScope`. Fermeture utilisateur respectant le verrou et maintien du panneau pendant les opérations. |
| Arrière-plan pendant le démarrage natif | L'arrêt attendait derrière BootCore/shaders sur la file runtime. Un signal atomique distinct interrompt le démarrage avant la libération du CPU, sans réactiver les journaux avant l'arrêt effectif. |

## Vérifications et état

- Reproduction synthétique du dossier vide exécutée sur les fonctions réelles : perte de la copie importée confirmée avant correction ; dump source intact.
- Dix tests Wiimmfi existants renforcés et réussis : dossiers vides/Finder, données actuelles, identité importée, Mii, sauvegarde précédente et liens.
- Analyse Dart ciblée sans problème pour la fusion et les parcours UI. Sept tests de lancement existants réussis, dont le scénario renforcé null/en ligne/hors ligne avec fermeture de la route enfant et maintien du parent occupé.
- Cycle de vie natif existant : 20 cycles GC/Wii réussis avec la vraie fonction d’interruption ; signal remis à zéro, politique réseau inchangée par le signal. Patcher appliqué sur un amont propre, contrôles de syntaxe réussis.
- Nouvelle ABI Wiimmfi **4** et export d’interruption exigés par le bridge ; compilation Apple à suivre. Le Core ABI 3 précédent ne contient pas ce correctif. Le test hôte ne simule pas un arrière-plan UIKit réel.

## Défaut ergonomique restant

Les actions Wiimmfi du panneau ne sont pas intégrées à la navigation manette de l’onglet Gérer. Elles restent utilisables au toucher. Une entrée manette ouvrant un panneau navigable reste à implémenter ; aucun fonctionnement à la manette n’est revendiqué.

## Limites

La nouvelle revue confirme les corrections antérieures et révèle des cas que leurs contrôles ne couvraient pas. Elle ne constitue pas une certification exhaustive. Aucun dump, jeu, identifiant ou secret réel utilisé ; aucune IPA produite. Import réel, attributs iOS de protection, application/bridge UIKit complet, authentification et course Wiimmfi sur iPhone restent non validés. Aucun gain de performances annoncé. Les anciens échecs CI hors périmètre restent documentés dans le bilan précédent.
