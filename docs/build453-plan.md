# Build 453 — Azahar 2127.0-alpha1 / FastInterp

Demande du mainteneur du 13 octobre 2026 : remplacer le cœur 3DS embarqué par
Azahar 2127 alpha, proposer Fast Interpreter activé/désactivé et livrer une IPA.
Base : Build 452, source 1594e78cdb2170c5e07b61af1eacc6733d61bd87.
Candidate réservée : 0.0.7+453. Travail sur Claude.

## Cœur et périmètre

- Binaire officiel Azahar iOS ARM64 2127.0-alpha1, sans modification.
- Archive SHA-256 : 61e96e167a3ddf28c2e0fbab51ae6c952ab272c58de0b4de62cbbe60c2fc65d7.
- Dylib SHA-256 : a646ee8f804327e2d33cbacf4d4f64b6725d25c7d7ece1ccc13698b16f3bf1d8.
- Sources : azahar-emu/azahar, 5f3306d13cab40bbd5cf38f2cf3ae8b6e6eedca6.
- Les 13 autres cœurs, MoltenVK, fichiers système et identifiants de framework
  sont réutilisés depuis le run 38195212647 et vérifiés octet par octet.
- Aucun émulateur autonome ajouté. Identifiant azahar, chemins de sauvegarde,
  données système, commandes et disposition des écrans conservés.
- Licence de cette version : GPLv3 ou ultérieure. Texte complet embarqué.

## Option

La source officielle déclare citra_use_fastinterp, valeurs enabled / disabled,
défaut enabled. Sous IOS, les JIT CPU et shader sont désactivés à la compilation :
leurs anciennes clés citra_use_cpu_jit et citra_use_shader_jit ne sont plus
déclarées dans le binaire officiel et doivent quitter les overrides du catalogue.

Le choix sera dans le menu en jeu › Réglages d’émulation, avec un libellé
traduit indiquant le prochain lancement. Il faut fermer puis relancer le jeu
pour reconstruire les processeurs émulés. Désactivé sélectionne ARM_DynCom ;
activé sélectionne FastInterp. Les préférences explicites restent prioritaires
sur le défaut activé.

## Vérifications

- Six tests de comportement du paquetage réussis localement : empreintes,
  plateforme, contenu d’archive, fichiers de base altérés, préservation des
  autres cœurs et des fichiers système.
- Vérifications natives, catalogue, traductions, compilation et identité IPA :
  à consigner après exécution.
- Aucun test de jeu sur iPhone ni mesure de FPS à ce stade. Les états instantanés
  de versions différentes ne sont pas garantis compatibles par cette livraison.
