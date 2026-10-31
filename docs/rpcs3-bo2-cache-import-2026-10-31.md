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

## Suite concrète

1. Construire la bibliothèque statique complète avec le producteur candidat,
   puis compiler un nouveau core sous un contrat qui lie ce nouveau paquet,
   ses sources, son SDK et les contrôles ABI/export/codegen existants.
2. Tester l'import et le préchauffage avec le vrai pilote Metal ; mesurer
   séparément import, préchauffage et première frame, cache conservé.
3. Rejouer l'entrée multijoueur BO2 sur iPhone, puis un second lancement du
   même mode. Vérifier l'arrêt/reprise et les autres jeux avant promotion.

Le code source et ses adaptateurs ne démontrent pas encore la disparition
du gel. Aucun FPS supplémentaire ni temps gagné sur iPhone n'est établi.
GOW3 et le flickering AC restent ouverts. Aucun nouveau core, IPA ou release
n'est présenté comme livré par ce lot.
