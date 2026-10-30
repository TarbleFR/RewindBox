# RPCS3 : corrections ciblées des incidents BO2, GOW3 et AC

Ce lot poursuit le commit local `b9346b59ee53`, après le correctif des petits
uploads de sommets. Il conserve le core amont verrouillé, les réglages des
jeux, les sauvegardes, l’ABI 30 et les 88 exports. Les modifications décrites
ci-dessous sont des corrections de sources et des reproductions hôtes.
Elles ne démontrent pas encore que les trois scènes signalées sont corrigées
sur l’iPhone. Le patch canonique est
`720d0d72d8ab93bbf7596d859652b8e21dd603995b8f455b3b8674de6fc53ac8`.
Aucun push, lancement de CI, core, IPA ou release n’est réalisé.

## BO2 : isoler le redémarrage de l’interface et conserver sa demande

La sélection du multijoueur change d’exécutable PS3. Le chemin `exitspawn`
appelait `BootGame()` depuis le callback UIKit de fin d’arrêt. La lecture du
SELF, la création du renderer et l’import synchrone des bibliothèques Metal
pouvaient donc bloquer le thread de l’interface. Le chemin du SELF et celui
du cache de shaders sont déjà résolus pour le bon exécutable : ils ne sont
pas remplacés à partir d’une ligne `ENOENT` préalable au lancement.

Le redémarrage interne utilise maintenant le worker possédé et borné déjà
utilisé pour les restaurations. L’arrêt et les opérations UIKit restent sur
leur thread ; les lectures/initialisations du nouvel exécutable utilisent le
worker et le verrou de l’API du core. Les générations du worker, l’identifiant
d’émulation et le titre sont vérifiés avant la capture de l’ancien contexte
et avant l’application des arguments au nouveau jeu. Une seule continuation
peut attendre pendant une tâche active ; une transition récursive ne crée ni
thread détaché ni file sans limite.

La revue a empêché un autre gel : rejeter simplement un `exitspawn` pendant
une sauvegarde pouvait laisser son PPU en attente si la préparation échouait.
Un unique callback de fin de sauvegarde, lié à son propriétaire, conserve
maintenant la demande. Il est détaché sous le mutex puis exécuté hors verrou.
Le résultat reste disponible si la sauvegarde finit avant l’inscription.
Après un échec de préparation, le processus encore vivant peut poursuivre sa
transition ; après une restauration réussie, seule sa substitution exacte
est admise. Après un échec ayant déjà détruit le processus, le core reste
arrêté avec une erreur explicite, sans relire un FXO absent.

Les 22 scénarios d’intégration passent en normal et ASan/UBSan : chargement
hors UIKit, interface disponible pendant le blocage pilote simulé, arrêt sans
chevauchement natif, générations/titres/identifiants, sauvegardes et reprise,
ainsi qu’une ancienne demande sur une session ultérieure laissée intacte.

Les contrôles du vrai header de statut, compilés sans exceptions, passent :
51 228 vérifications, dont 1 200 courses inscription/fin. Les adaptateurs du
test d’intégration représentent explicitement UIKit, le pilote et le VFS ;
ils ne sont pas un lancement réel de BO2 ou une mesure du temps Metal.

Preuves : [statut et intégration](evidence/rpcs3-device601-20261030/exitspawn/).
Le déplacement du chargement rend l’interface disponible ; il ne supprime
pas le travail de compilation du pilote et ne prouve pas encore que le mode
multijoueur termine son démarrage sur l’appareil.

## GOW3 : réveil du décrémenteur pendant une file MFC pleine

Un `WRCH` qui attend une place dans la file MFC ne doit pas être considéré
comme accepté. Dans ce chemin, `cpu_work()` suspend volontairement sa prise
ordinaire d’interruption. Le timer pouvait publier du travail sans que
l’événement invité du décrémenteur soit collecté par son SPU propriétaire.
Sa notification pouvait aussi arriver avant l’inscription effective de
l’attente, alors que les drapeaux `pending` étaient déjà présents.

Le propriétaire collecte maintenant l’événement du décrémenteur avant de
vérifier l’interruption de la file pleine. Le timer passe par la notification
du thread qui conserve le réveil hôte. Les acquittements, le PC du `WRCH`
non accepté, la reprise `IRET` et les anciennes corrections SNR restent
préservés. Aucun label RSX n’est forcé ; aucun timeout invité n’est ajouté.

La reproduction extrait les fonctions réelles, avec des adaptateurs explicites
pour l’horloge, la VM et l’attente hôte. Trois positions d’expiration qui
bloquent avant la correction reprennent ensuite ; 96 commandes sont acceptées
exactement une fois et 64 réveils concurrents sont exercés. Les modes normal
et ASan/UBSan passent ; retirer séparément chacune des deux corrections est
détecté par le test.

Ce défaut appartient au protocole du timer hôte de ce fork. Il n’est pas
présenté comme un correctif importé aveuglément de l’amont. Un alias exact,
limité au nouveau SHA et au bon chemin, conserve les objets SPU compatibles.
Le retour aux deux anciens corps hôtes reconstitue exactement le fichier
précédent ; les autres entrées physiques de génération sont contrôlées.

Preuves : [CPU, audit et limites](evidence/rpcs3-device601-20261030/cpu/README.md).
Le producteur du label manquant dans la scène GOW3 n’est toujours pas identifié.
Les nouveaux essais de boot qui chargent les bibliothèques Metal sont un
incident distinct de ce gel historique de l’introduction.

## AC : supprimer une hypothèse incorrecte sur les lectures de texture

Une seule instruction de texture peut lire un pixel voisin ou plusieurs
texels avec un filtrage linéaire. Le nombre statique d’instructions ne prouve
donc pas qu’une image puisse être lue pendant que le même draw l’écrit.

Sur iOS/MoltenVK, le chemin de copie existant couvre maintenant aussi ces
lectures simples lorsqu’il s’agit d’un véritable alias d’un attachement
couleur actif, sans multisampling. Les images distinctes, les copies déjà
isolées, la profondeur, le MSAA et les autres pilotes gardent leur chemin.
Les transitions, remaps et ressources temporaires existants sont conservés.

Le helper complet est exécuté avec un oracle indépendant de pixels avant
draw. Deux cas auparavant dépendants de l’ordre des fragments deviennent
indépendants de cet ordre. Les gardes, les formats, les remaps, les layouts
et les échecs d’allocation passent en normal et ASan/UBSan ; le chemin hors
iOS est inchangé.

Cette correction ajoute **une copie par draw nouvellement concerné**. Le
test ne mesure ni son coût GPU ni la fréquence de ce chemin dans AC. Il ne
constitue pas une preuve que les torches utilisent cet alias. Les pixels et
les durées d’image doivent être mesurés ensemble ; aucun gain de FPS n’est
annoncé. L’élargissement supposé des barrières de profondeur a été écarté
après vérification des stores et de la documentation Khronos.

Preuves : [rendu et coût explicite](evidence/rpcs3-device601-20261030/renderer/color-feedback/README.md).

## Validation suivante et piste encore ouverte

La validation Apple des seuls chemins affectés doit précéder les essais
des mêmes passages sur iPhone : entrée multijoueur BO2, introduction GOW3 et
couloir des torches AC. Les anciens résultats Apple gardent leur révision et
ne valident pas automatiquement ces nouvelles sources. Il n’y a ni nouveau
numéro d’IPA ni release dans ce lot.

La perte de réservation `LR` pendant une attente de file MFC pleine a aussi
été reproduite séparément. Sa correction demande un protocole d’attente VM
qui couvre les stores directs ne notifiant pas toujours le waiter ; une
simple attente sur le notifier ou un polling généralisé n’est pas retenu.
Cette piste et ses limites sont conservées pour la suite dans
[lr-followup](evidence/rpcs3-device601-20261030/cpu/lr-followup/README.md).
