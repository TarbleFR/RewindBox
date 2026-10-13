# Build 453 — Azahar 2127.0-alpha1 / FastInterp

Demande du mainteneur du 13 octobre 2026 : remplacer le cœur 3DS embarqué par
Azahar 2127 alpha, proposer Fast Interpreter activé/désactivé et livrer une IPA.
Base : Build 452, source 1594e78cdb2170c5e07b61af1eacc6733d61bd87.
Livraison : 0.0.7+453. Travail sur Claude.

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

Le choix est dans le menu en jeu › Réglages d’émulation, avec un libellé
traduit indiquant le prochain lancement. Il faut fermer puis relancer le jeu
pour reconstruire les processeurs émulés. Désactivé sélectionne ARM_DynCom ;
activé sélectionne FastInterp. Les préférences explicites restent prioritaires
sur le défaut activé.

## Vérifications

- Six tests de comportement du paquetage réussis localement : empreintes,
  plateforme, contenu d’archive, fichiers de base altérés, préservation des
  autres cœurs et des fichiers système.
- Collection de cœurs : run 38352378859 réussi, artefact 11791735934.
  Les 201 fichiers de son identité ont aussi été vérifiés après téléchargement.
- Tests libretro dédiés : run 38352918459, source
  6640179852d414f1c90c9516b465b0bd37b677f1, jobs Dart et natif réussis.
  Comprend le catalogue, les douze traductions, les préférences de lancement et
  le cycle activé → désactivé → nouveau magasin → activé → nouveau magasin.
- Sonde simulateur : run 38352640264, source
  e2be44b156796a9e85d1e853c44d1b881b0deb0a, trois jobs réussis. Les changements
  suivants portent uniquement sur des tests Dart et de la documentation.
- Livraison finale : run 38352930579, périmètre full, source
  81efc2109e1052678bd881b8fc7c8dc1c53aa8bc. Jobs checks, native et
  Release device build cold réussis ; le benchmark warm n’était pas demandé.
- Aucun test de jeu sur iPhone ni mesure de FPS à ce stade. Les états instantanés
  de versions différentes ne sont pas garantis compatibles par cette livraison.

## IPA livrée

- Artefact GitHub Actions : 11792880020 (211 062 173 octets), run 38352930579.
- Archive chiffrée SHA-256 :
  `080d5b83ef5d534d2e118b5a1c10c72027f7f5f4a5933d4702486c679bccd3b1`.
- IPA : `NeoStation-Build453.ipa`, 210 809 287 octets, version 0.0.7 (453).
- IPA SHA-256 :
  `7a7582f34a9f1ddfccea7955ba8b9ce16cb8efed3ee5a997442afdb1bd6b842d`.
- Empreinte identique à SHA256SUMS et signed-payload-identity.json ; contrôle
  CRC de toute l’archive réussi, une application principale, iOS 18 minimum.
- Les 59 signatures ad hoc ont été vérifiées en CI. Le code et les données
  compilés, ainsi que les métadonnées ABI, sont inchangés après signature.
  SideStore doit appliquer la signature Apple et le provisioning à l’installation.
- Vérification après téléchargement : build 453, version officielle Azahar,
  présence de citra_use_fastinterp, absence des anciennes options JIT et
  licence GPLv3 embarquée. Copie locale et copie sur le PC de même SHA-256.
- Copie PC : `C:\Users\Coren\Downloads\NeoStation-Build453.ipa`.
- Pas de test d’installation ni de jeu sur iPhone ; aucun résultat 60 FPS mesuré.
  Fermer puis relancer le jeu après changement d’Interpréteur rapide.
