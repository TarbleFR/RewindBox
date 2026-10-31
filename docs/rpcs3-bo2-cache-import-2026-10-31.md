# BO2 : réduire le travail de compilation à l'entrée multijoueur

Le nouveau retour appareil maintient le gel à l'entrée multijoueur ouvert.
La build 605 conserve le core `a4d0c9a5` de la build 604 ; elle n'intègre pas
le candidat décrit ici. Le changement porte sur l'import du cache MoltenVK,
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

## Suite concrète

1. Compiler un nouveau core sous un contrat qui lie le paquet iOS vérifié,
   ses sources, son SDK et les contrôles ABI/export/codegen existants.
2. Mesurer séparément import, préchauffage et première frame sur iPhone,
   cache conservé. Le préchauffage RPCS3 complet n'est pas exercé par le probe compute.
3. Rejouer l'entrée multijoueur BO2 sur iPhone, puis un second lancement du
   même mode. Vérifier l'arrêt/reprise et les autres jeux avant promotion.

Le code source et ses adaptateurs ne démontrent pas encore la disparition
du gel. Aucun FPS supplémentaire ni temps gagné sur iPhone n'est établi.
GOW3 et le flickering AC restent ouverts. Aucun nouveau core, IPA ou release
n'est présenté comme livré par ce lot.
