# Core MeloNX compilé et vérifié

La livraison finale provient du commit `e7143e566462bf6e3d9c143ce24532c1ad7aeb10` sur `Claude`. Elle inclut les quinze fichiers de production décrits dans [le rapport technique](melonx-occlusion-2026-10-30.md), dont la correction supplémentaire du rendu conditionnel Vulkan. Le core intermédiaire `24b1ad9a` est conservé comme preuve historique de la seule suite d’affichage réutilisée et ne constitue pas cette livraison.

[Workflow Apple réussi](https://github.com/TarbleFR/RewindBox/actions/runs/40998920652), job `123878488200`, tentative 1 ; artefact `12953505421`. Durée du job : **12 min 06 s**, dont **367 s** pour les deux compilations NativeAOT et leur ABI, **225 s** pour le smoke iOS ARM64, **38 s** pour les deux suites affectées et l’authentification des résultats réutilisés.

Deux suites Apple sont exécutées sur ce candidat. Trente résultats inchangés sont authentifiés, dont la suite d’affichage Apple de la compilation intermédiaire ; ils ne sont pas présentés comme exécutés à nouveau. Les deux nouvelles sessions homebrew SVC ferment leurs sessions et rendent leur backing. Les tests d’occlusion couvrent 274 scénarios et 16 432 vérifications ; le test de politiques couvre 58 vérifications, dont le comparateur de visibilité réel. Le cas synthétique de requêtes passe de 64 à 8 décisions de soumission, sans mesure FPS iPhone.

| Binaire réel | Octets | SHA256 |
| --- | ---: | --- |
| iOS ARM64 | 37 601 600 | `b0bb4cd7da18337fd66eedec218df4a783efeff38f7c412cef2a00be813f41e6` |
| Simulateur iOS ARM64 | 37 911 992 | `a53e404f668b4c470247092ea83e877004f4a6661548b704b508aeee2fb7556e` |

L’archive téléchargée contient **87 766 998 octets**. Son SHA256, identique au digest GitHub, est `0b734460e07c35dc81575940b0feff86af5d755a6f8a25b5d395d3b99b8818c1`. L’inspection indépendante vérifie le CRC ZIP, les deux vrais Mach-O ARM64, leurs plateformes iOS/simulateur, l’ABI 2 et ses 47 exports requis parmi 84 symboles publics, les identités du commit et du workflow, les 108 entrées de préparation, les 148 membres adaptés, les reçus frais et réutilisés et le rapport du smoke. Elle ne constitue pas une exécution sur iPhone. Les champs minOS Mach-O sont des minimums de lien et ne sont pas une promesse de compatibilité autonome du core sur un ancien iOS.

Le fichier iOS se trouve dans `ios-arm64/Ryujinx.Library.dylib`. L’archive contient également le core simulateur, les sources amont et adaptées, les notices et les rapports. Aucune IPA, nouvelle version commerciale, release publique ou tag n’est produit.

Les deux expériences GPU restent **OFF par défaut** et réservées à Hogwarts ; leur interface de réglage dans une future application reste à intégrer. Le repli JIT progressif n’est pas activé, faute de rollback natif prouvé : une allocation échouée exige un nouveau processus. Les profils Unreal et la correction des textures noires sur appareil restent non validés. Les mesures FPS, frametimes, mémoire et stabilité sur iPhone 16 Pro Max restent à réaliser avec le protocole du rapport technique.

Reçu indépendant complet : [apple-core.json](evidence/melonx-occlusion-20261030/apple-core.json). Les contrats et scripts de compilation originaux restent conservés ; les empreintes du nouveau contrat se trouvent dans l’artefact. Ne pas reconstruire ce core pour une intégration ultérieure lorsque ses 108 entrées restent identiques.
