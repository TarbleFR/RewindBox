# MeloNX — échec de préparation JIT dans la build601

Le journal fourni montre deux tentatives dans deux processus distincts (54910
et54931), le30 octobre à15:33:43 et15:33:59 UTC. Toutes deux chargent l’application
601 et le Core827f4653, puis échouent avant toute session invitée à
`PrepareSizedArena`: `The sized JIT helper protocol is required.` Les préflights
fichier, clés personnelles, contenu et firmware passent. Le message d’arrêt sûr
est la conséquence du classement `jitRestartRequired`, pas la cause initiale.
Le redémarrage entre ces deux tentatives ne résout pas le problème.

Le script helper livré déclare `rewindboxSizedArenaV1` et son garde de tentative
après la boucle bloquante de dispatch. Le premier appel de capacité command1
atteint donc une liaison lexicale non initialisée. Le test du script entier
reproduit `ReferenceError: Cannot access 'rewindboxSizedArenaV1' before
initialization`, sans allocation ni préparation. Cette reproduction établit le
défaut du script; le journal iPhone n’enregistre pas directement cette exception
JavaScript, mais son échec de capacité est cohérent avec ce chemin.

La correction déplace exactement le bloc existant avant la première boucle.
Son contenu, les fonctions, le protocole, les limites1024→512MiB, les pas64MiB,
les refus avant préparation et le garde empêchant toute seconde allocation
restent identiques. Aucun réglage du joueur, fichier de pairing, cache, jeu,
firmware ou sauvegarde n’est modifié. La quarantaine de sécurité reste active.
Les Core MeloNX827f4653 et RPCS3378509e8 et les autres composants restent gelés;
le helper est une ressource de l’application, pas une entrée compilée du Core.

Les anciens tests isolaient le bloc du protocole et l’initialisaient avant leurs
appels: ils ne couvraient pas l’ordre d’exécution du script empaqueté. Le nouveau
test exécute tout ce script, de vAttach/PID au nonce, capacité, négociation,
réentrée et détachement. Il couvre les neuf tailles, refus complet, échec de
préparation, répétition de capacité, ancien chemin512MiB et mauvais attachement.
Les transports debugserver et VM sont doublés.99 contrôles du script complet et
101 contrôles du protocole passent sous Node; la preuve Apple JavaScriptCore
passe dans le run41083688288, job124159148692:14 sessions complètes, avec
échec original reproduit et observations identiques à Node. Le chemin512MiB
produit exactement les mêmes16 paquets avant/après, sans nouvelle attente. Aucune exécution physique TXM, validation
du lancement sur iPhone ou mesure FPS n’est encore établie par ces tests.

Preuves locales: `docs/evidence/melonx-jit-helper-init-20261030/`. Le négatif
original est conservé. La comparaison de source exige le déplacement exact,
sans normaliser ni ignorer d’autre changement.

## Smash et intégration privée602

Le dernier lancement Smash du journal est le30 octobre à02:10:07.908 UTC,
avant les deux tentatives Hogwarts de la601. Son JIT réutilisé est prêt à
+0.323s; première présentation Metal à+8.952s.2743 shaders sont rechargés
entre02:10:09.456 et02:10:12.470, avec un worker de compilation actif et
plusieurs checkpoints/recyclages64MiB. Les autres lancements Smash du journal
prennent8.658,10.759,19.399 et29.055s jusqu’à la première présentation. Ces
mesures ne définissent ni l’arrivée au menu ni une régression de la601: aucune
tentative Smash601 n’est présente. Ne pas déduire un gain ou une résolution de
ce nouveau ralentissement de la correction du helper Hogwarts.

La602 ne change qu’une ressource produit par rapport à601: le script helper.
MeloNX827f4653 et RPCS3378509e8 sont réutilisés à l’octet du payload compilé,
avec les lots cumulatifs. Les114 entrées binaires et151 membres préparés
MeloNX restent identiques. Le reçu de compilation conserve l’ancien helper
pour sa provenance historique; seule la relocation exacte de cette ressource
hôte est autorisée dans la nouvelle livraison. Les23 tests Flutter,3342
contrôles de politique Swift et les tests complets Apple du helper sont
authentifiés avec leur origine et leurs entrées, sans nouvelle exécution.
La compilation602 passe dans le run41085116632; le fichier téléchargé est
vérifié indépendamment et remis au mainteneur. Voir
[le reçu de livraison](rewind602-test-ipa.md). Le mainteneur a différé
l’investigation Smash jusqu’à un nouveau log: le correctif livré cible Hogwarts.
