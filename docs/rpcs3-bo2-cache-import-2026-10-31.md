# BO2 : réduire le travail de compilation à l'entrée multijoueur

Le nouveau retour appareil maintient le gel à l'entrée multijoueur ouvert.
Les builds 605 et 606 conservent le core `a4d0c9a5` de la build 604 ; elles
n'intègrent pas le nouveau core décrit ici. Le changement porte sur l'import du cache MoltenVK,
pas sur les réglages du jeu ou les budgets mémoire.

## Ce que les journaux précédemment analysés établissent

L'analyse de la session **604, PID 56499, BLES01717** a séparé les rotations,
les autres builds et le menu solo. Les observations ci-dessous proviennent
de cette analyse ; les pièces brutes ne sont pas réanalysées dans cette reprise.

| Observation | Portée |
| --- | --- |
| Politique de boot interne à `1793394505.627265`, thread `7400849` | Le worker de transition déjà corrigé est utilisé. |
| Nouveau renderer à `1793394506.536707`, allocateur génération 2 initialisé | La transition a dépassé la recherche préalable du SELF. L'ENOENT isolé ne prouve pas un exécutable absent. |
| 13 fenêtres de préparation, dernière à `1793394572.651080` | **67,023815 s** observées après la politique de boot interne ; aucun achèvement du démarrage multijoueur dans cet intervalle. |
| État natif 6, zéro frame et activité PPU/SPU nulle dans ces fenêtres | L'état correspond à `system_state::ready`. Ce n'est pas une mesure de gameplay. |
| Demandes de compilation Metal : `575,28,30,29,27,28,24,25,26,22,30,25,30` | **899 demandes**, dont **324 après la première fenêtre**. Le compteur est remis à zéro entre fenêtres. La première peut chevaucher la fin de l'ancien renderer. Ce ne sont pas 899 compilations terminées. |
| Marge mémoire de 5 202 à 5 223 Mio, nouvelles allocations graphiques encore nulles | Aucune justification pour relever les budgets mémoire dans cette phase. |

Références conservées dans l'analyse de cette session :
`RPCS3-diagnostic(1).log:60,62,73`,
`RPCS3-milestones(1).log:480-488` et
`RPCS3-timeline(1).log:33-45`.

L'ordre réel des sources situe **probablement** l'attente dans
`render_device::create_pipeline_cache()` : l'allocateur est créé avant cet
appel et la configuration du nouveau renderer est capturée après son retour.
Les journaux conservés ne donnent pas directement les bornes de
`vkCreatePipelineCache`. Cette localisation reste une inférence, pas une
preuve que le pilote ne finira jamais son travail.

## Modification du travail effectué

MoltenVK **1.4.2**, verrouillé sur
`db66022459ffb663aa2b50f6b018bc2e124f5edf`, compile normalement les sources
MSL de chaque bibliothèque pendant la lecture du cache. Cette préparation
précède le préchauffage natif des pipelines RPCS3. Le cache est **déjà**
propre à l'exécutable : aucun nouveau cloisonnement par jeu n'est revendiqué.

Le candidat conserve les sources MSL compressées et leurs métadonnées à
l'import. Une bibliothèque importée n'est compilée que lorsqu'un pipeline
la demande. La compilation se déroule après la sortie du verrou global de
recherche du cache. Un état partagé et un mutex par bibliothèque évitent
les compilations en double, y compris après copie/fusion du cache.
Le préchauffage natif RPCS3 complet reste inchangé : les pipelines connus
doivent toujours être préparés avant le jeu. Les entrées importées mais
inutilisées ne déclenchent plus de compilation Metal.

Après un échec du MSL importé, une seule conversion neuve du SPIR-V original
est tentée. Elle utilise un convertisseur indépendant, puis au plus une
nouvelle compilation Metal. Un double échec est terminal pour cette entrée
en mémoire. Les données sérialisées restent intactes ; une récupération en
mémoire ne répare pas l'entrée persistée pour le lancement suivant.
Le drapeau demandant de refuser une compilation nécessaire ne lance pas de
travail et ne patiente pas derrière une compilation déjà active.

L'option de compilation `RBX_MVK_DEFERRED_CACHE_IMPORT` vaut **0 par défaut**.
Le producteur candidat l'active pour une reconstruction complète de la
bibliothèque statique RPCS3, avec les deux hooks de files déjà utilisés par
le core. Aucun objet précompilé n'est greffé dans une bibliothèque dont les
classes privées ont changé. La dépendance MeloNX n'est pas remplacée.

Le pont hôte conserve aussi les messages existants de début/fin de lecture
et de préparation du cache dans les milestones. Ce groupe est limité à
16 écritures/s sous verrou ; le budget ordinaire de 128 lignes/s et les
anciens groupes restent inchangés. Il n'y a pas de journal par shader.

## Validation et limites

Les résultats frais, les empreintes du patch et les limites des adaptateurs
sont conservés sous
`docs/evidence/rpcs3-bo2-multiplayer-604-20261030/` et dans les tests ciblés.
La préparation neuve des sources et la conservation des entrées du core
sont consignées sous `docs/evidence/rpcs3-bo2-multiplayer-604-20261031/`.

| Contrôle exécuté sur Linux | Résultat |
| --- | --- |
| Constructeur réellement extrait, adaptateurs C++ | 64 entrées importées : 64 appels de compilation en mode initial, zéro en mode différé. Les variantes spécialisées restent immédiates. |
| 12 scénarios des fonctions extraites | 24 demandes simultanées d'une entrée : une compilation ; entrées indépendantes admises en parallèle ; refus sans attente ; repli borné ; copies avant/après succès et échec terminal. |
| ASan/UBSan | Passent avec LeakSanitizer désactivé. L'échec initial de LeakSanitizer et sa reproduction sur un programme vide sont conservés ; les fuites ne sont pas vérifiées par ce mode. |
| Contrat du patch | Application, seconde application, vérification sans mutation et refus d'une source modifiée passent. |
| Producteur | Dix contrôles de refus d'artefacts incorrects passent. Une préparation réelle depuis un checkout neuf vérifie les postimages ; aucune compilation Apple n'est impliquée par cette préparation. |
| Messages hôtes | Les 14 formats existants, la limite indépendante de 16/s et 32 rédacteurs concurrents passent avec des adaptateurs de verrou/horloge. Le test hôte antérieur passe également. |

La revue a corrigé deux défauts avant intégration : une attente sous le
drapeau de refus de compilation, et un convertisseur de repli qui n'aurait
pas été protégé contre les défauts de cache ordinaires.

Le patch canonique du core reste
`70d694bb3ef812b87b8839e53335376028aa16476893512d012b77ef1952fd79`.
Son contrat source historique reste
`657aa623d118644888ec9fe588db68882bc61cacc794de26d4cfc2878cfba77d`.
La recette du core livré et son workflow n'ont pas été remplacés.
Les anciens résultats Apple ne valident pas cette nouvelle dépendance.

Le producteur autonome est
`build-utils/rpcs3/build_moltenvk_deferred_cache.py`. Il exige des répertoires
de travail/sortie neufs, reconstruit la cible statique entière et conserve
les commandes, le SDK, les dépendances verrouillées, les headers, les licences
et les empreintes des objets ARM64. Le workflow ciblé
`rpcs3-mvk-cache-validation.yml` prépare les contrôles Apple et un véritable
essai de cache/dispatch Metal sur macOS. Son existence ne vaut pas résultat
d'exécution ; les résultats effectifs doivent être liés au run et aux artefacts.

## Validation Apple effectuée

Le [run 41239096061](https://github.com/TarbleFR/RewindBox/actions/runs/41239096061),
source `7aa81cfb0ab749ebfd6c147929ca94751ea3a3ed`, réussit ses trois jobs dès
la première tentative. Les nouveaux adaptateurs passent sur Apple ARM64 avec
ASan/UBSan. Les bibliothèques statiques entières sont effectivement compilées
avec Xcode 16.4 ; le paquet iOS utilise le SDK 18.5 et cible iOS 16.3.

Les archives téléchargées ont été vérifiées contre leurs tailles, SHA-256 et
CRC ZIP. Le paquet iOS contient une bibliothèque ARM64 de 11 714 256 octets,
SHA-256 `0d711e4ad3610bb176e3c91e727940f7c448a25571158cc1919d633f1d622b1f`,
avec un objet Mach-O ciblant iOS 16.3.0. Les headers correspondent au manifeste.

| Artefact du run | Octets | SHA-256 |
| --- | ---: | --- |
| Prévalidation 13056672047 | 9 516 | `c3a968fde0254e477c83f5174e615f9414432ea78152db640efa1c2947b6e441` |
| Dépendance iOS 13056518647 | 5 144 230 | `833e431b0274002fba4fe36db65219144dedfa5440c7b7c821591c264352da0c` |
| Dépendance macOS et Metal 13057525542 | 5 696 056 | `8649ce9caf18ac7af9dc7b1fa68ffca3e9a94f338dbbb237b887d8aa6c0f4adc` |

Le probe appelle le vrai pilote Metal sur **Apple Paravirtual device**, le
périphérique virtualisé du runner macOS. Il crée les pipelines et termine
des dispatchs compute avec une fence ; il n'utilise pas un renderer simulé.
Une entrée de cache de 452 octets est sérialisée puis relue : **zéro compilation
de bibliothèque à l'import**, **une à la première demande**, aucune nouvelle
à la demande répétée. Huit demandes concurrentes de la même entrée déclenchent
une compilation et ne produisent aucun échec de pipeline.

Ces résultats vérifient le mécanisme avec Metal sur macOS. Ils ne mesurent
pas le multijoueur BO2, les images PS3 ou les FPS sur un iPhone. Les reçus et
journaux téléchargés sont sous `apple-preflight/` et `apple-metal/` dans les
preuves du 31 octobre. La compilation complète iOS du pilote a pris environ
320 s ; ce temps de build n'est pas un gain de temps de chargement du jeu.

La première demande de compilation du core, source `6140ed4f`,
[run 41240930719](https://github.com/TarbleFR/RewindBox/actions/runs/41240930719),
s'arrête avant préparation des sources natives et compilation. Le test des
fichiers de liaison indexait un chemin temporaire `/var` alors que le gate
conservait son chemin canonique `/private/var`. Le test normalise maintenant
son répertoire et exerce explicitement un alias de répertoire ; ses contrôles
de contenu et de confinement restent exigés. Les neuf cas passent localement.
L'échec original et son journal sont conservés sous `apple-core/failed-6140ed4f.*`.
Le pilote, le gate et la recette de compilation n'ont pas changé pour cette reprise.

La deuxième demande, source `6c03067c`,
[run 41241336642](https://github.com/TarbleFR/RewindBox/actions/runs/41241336642),
compile et lie le core iOS. Les contrôles préliminaires ABI et chargement
passif passent, puis la production de l'identité échoue : CMake a créé
`rpcs3/git-version.h`, absent de la liste des sources ordinaires figées.
Cette tentative reste en échec. Son binaire n'était pas inclus dans les
artefacts conservés ; son empreinte dans le journal ne permet pas de le livrer.
Les preuves disponibles sont conservées sous `apple-core/failed-6c03067c/`.

Le contrôle distingue maintenant cet unique fichier généré après compilation.
Il vérifie les octets attendus, le générateur CMake verrouillé, le commit et
l'état du checkout ainsi que les trois valeurs observées dans le journal de
configuration. Le fichier figure dans une identité séparée des **326 postimages
canoniques**. Les autres fichiers inconnus restent refusés. Les nouveaux tests
exercent le générateur CMake réel et le refus d'une dérive ou d'un fichier ajouté.
Une sauvegarde distincte conserve aussi le binaire marqué **non validé** si
un contrôle ultérieur échoue ; elle ne le transforme pas en core validé.

Le troisième [run 41243687649](https://github.com/TarbleFR/RewindBox/actions/runs/41243687649),
source `a4ae86d085c231e3c5c93f7f72d2eced0f38ec24`, compile et lie le core, puis
échoue dans le parseur de la commande de liaison. Il traite la valeur
`-install_name @rpath/libRPCS3Core.dylib` comme un fichier réponse. La vraie
commande ne contient aucun argument de fichier réponse. Le contrôle des
sources, dont le header généré, a passé avant cet échec. Le run reste en échec.

Cette fois, la sauvegarde contient le binaire original et les entrées nécessaires.
L'artefact diagnostics **13059157171**, de **51 408 674 octets**, est téléchargé ;
taille, SHA-256 et CRC ZIP sont vérifiés. Son empreinte est
`59386bd5fe26c07b1c99b7adc8f0f2b152d16f505fe606d4308c03ecaf9a9cf7`.
Le core contient **77 422 944 octets**, SHA-256
`f512e6c4a6a2bf3b2ff6f41a2f2e2f6b966240ec2295a35e31f406a36229001f`.
La finalisation reprend séparément à partir de ces octets conservés, sans
nouvelle compilation native et sans requalifier le run en réussite.
Les douze modes CPU/rendu conservent leurs résultats antérieurs authentifiés ;
aucun n'est réexécuté ou présenté comme un nouvel essai appareil.

Cette route produit uniquement le core. Elle ne compile ni n'emballe le
composant NeoSwap ou le pont hôte de l'application. Les nouvelles bornes de
journal côté hôte sont des sources prêtes à intégrer dans une compilation
application distincte ; elles ne sont pas contenues dans le dylib. Une future
intégration doit conserver cette distinction et vérifier le contrat de l'hôte.

## Core compilé, archive finalisée et vérifiée hors ligne

L'archive **`RewindBox-RPCS3Core-a4ae86d0.zip`** est créée puis vérifiée contre
l'artefact diagnostics original. Elle contient **28 319 202 octets**, SHA-256
`ff70d3cdb5bf89e032531b15f2ffe71cfef9e261442578304c8e08cbf4316658`.
Le binaire et la preuve d'origine restent inchangés. Les 13 membres incluent
les métadonnées du run échoué, le reçu du collecteur et le header capturé.
Il ne s'agit pas d'un nouvel artefact Core produit par une CI réussie.

L'identité porte explicitement le type
`rpcs3-ios-mvk-deferred-cache-offline-recovery` et conserve la conclusion
`failure` du run original. Le profil normal du vérificateur exige toujours
une CI réussie et refuse ce type. La finalisation hors ligne a ses propres
empreintes de code ; elle ne réécrit pas les 12 entrées de compilation de la
source `a4ae86d0`, ni la preuve originale.

| Vérification sur les octets récupérés | Résultat |
| --- | --- |
| Mach-O du core | ARM64 iOS, dylib, minimum 16.3.0, `@rpath/libRPCS3Core.dylib` |
| Interface | ABI 30, 88 exports exacts ; les sept ABI NeoSwap communes restent à 1 |
| Sources | 326 postimages natives matérialisées vérifiées, 38 entrées figées et 92 entrées Core conservées avec le seul delta hôte documenté |
| Génération de code | PPU `a987639e9f838d1c`, SPU `477a3fa442d27917`, identités observées dans le vrai journal |
| Dépendance liée | Une seule archive MoltenVK candidate dans la commande exécutée ; ses octets et son paquet source vérifiés |
| Entrée générée | Les 249 octets du header capturé correspondent à la preuve et aux messages CMake |
| Réutilisation | 12 modes historiques authentifiés par la CI ; zéro mode natif rejoué pour cette finalisation |

Le correctif du parseur et six cas ciblés couvrent la commande réellement
exécutée, les valeurs Mach-O dans les vrais fichiers réponse et le maintien
des refus de chemins sortants ou de réponses imbriquées. La validation de
récupération s'exécute sans compilation ni exécution native. Le profil de
récupération refuse aussi une archive différente des données vérifiées.

Les reçus, le journal compressé, la preuve originale et le rapport final sont
sous `apple-core/recovered-a4ae86d0/`. Le producteur est
`build-utils/rpcs3/finalize_mvk_cache_core_recovery.py` ; le vérificateur
`test/verify_rpcs3_mvk_cache_core_archive.py --recovery-profile` exige le ZIP
diagnostics, ses métadonnées run/artefact/jobs et les deux racines explicites :
sources application `a4ae86d0` et sources natives canoniques matérialisées.
Le binaire n'a été ni modifié ni signé par la finalisation.

## Suite concrète

1. Intégrer ce core et les bornes hôtes dans une future compilation application
   autorisée, en vérifiant le contrat et le type de récupération explicite.
2. Mesurer séparément import, préchauffage et première frame sur iPhone,
   cache conservé. Le préchauffage RPCS3 complet n'est pas exercé par le probe compute.
3. Rejouer l'entrée multijoueur BO2 sur iPhone, puis un second lancement du
   même mode. Vérifier l'arrêt/reprise et les autres jeux avant promotion.

Le core est compilé et son archive est vérifiée hors ligne. La disparition
du gel BO2, un temps gagné sur iPhone ou des FPS supplémentaires ne sont pas
établis. GOW3 et le flickering AC restent ouverts. Aucune IPA ni release
n'est créée par ce lot ; la référence application livrée conserve son core antérieur.
