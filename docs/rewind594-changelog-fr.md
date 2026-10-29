# RewindBox 594 : les changements depuis la 593

La 594 réunit **13 changements RPCS3 et 16 changements MeloNX** ajoutés depuis
l’IPA privée 593. Cette liste décrit les corrections et optimisations des moteurs ;
elle ne recompte pas celles déjà livrées dans la 593.

## État et versions retenues

**La compilation de l’IPA et ses contrôles CI ont réussi au premier essai**, depuis
la source `97365ce57f17499101e88d50019b6c63be554b83`.
Résultat : [compilation de la 594 — run 40848076659](https://github.com/TarbleFR/RewindBox/actions/runs/40848076659).
Le job `123360403474` s’est déroulé le 29 octobre 2026 de 09:14:29 à 09:28:29 UTC,
soit 14 minutes. L’arbre produit est `1d43bbac26b3146d5d24afff0553d0c18d5bc20e`.

Les deux moteurs compilés et authentifiés ont été réutilisés avec leurs identités
originales. Les contrôles CI confirment la version **0.0.8 (594)** pour l’application
et ses sept extensions, **88 signatures ad hoc vérifiées** et **85 binaires Mach-O
dont le code, les données et l’ABI sont conservés pendant la signature**.
La phase Xcode a duré **320,895 s**, puis la signature et l’export **52,616 s**.

Le fichier produit, `RewindBox-Build594.ipa`, contient **188 316 921 octets**.
Son SHA-256 est `714021770922547c532e1439466d5725b4f8eb17c18ca629fe996d985124fe63`.
Les vérifications indépendantes après téléchargement ont réussi sur cette IPA :
les deux moteurs signés et leurs reçus embarqués correspondent aux archives
originales authentifiées. Le fichier vérifié est prêt à télécharger dans la
conversation. Son enregistrement privé durable attend une autorisation explicite.
L’installation sur iPhone reste à effectuer, après re-signature avec SideStore.

Preuves : [reçu de la 594](evidence/rewind594-delivery.json) et
[rapports de compilation et de validation](evidence/rewind594/).

| Moteur | Référence livrée dans la 593 | Source retenue pour la 594 |
| --- | --- | --- |
| RPCS3 | `c143be63f95751616f98d7bf9f1f34f297862df2` | `fe587e27fcefadaa36315a3ddc7dc1edba17b825` |
| MeloNX | `2f535c379ae385b68f0b33731d18efaf9e568047` | `ebcee3529645a781311429a869434005e76d6275` |

## RPCS3 : 13 changements

Les détails, preuves et mesures de ces quatre lots sont réunis dans le
[rapport cumulatif RPCS3](https://github.com/TarbleFR/RewindBox/blob/97365ce57f17499101e88d50019b6c63be554b83/docs/rpcs3-core-followup-2026-10-29.md).

### 1. Textures actualisées après les écritures du CPU

Les chemins concernés signalent désormais la fin de leurs écritures avant de
réutiliser une texture. Un ancien résultat de contrôle du contenu ne peut plus
faire accepter une texture devenue obsolète, même s’il a été préparé en arrière-plan.

### 2. Contrôle des textures déjà utilisées par le rendu

Une texture déjà liée à un sampler est maintenant réévaluée lorsque sa mémoire
change. Les écritures ciblées invalident les plages concernées ; les textures
sans rapport conservent leur accès rapide.

### 3. Attente sur la bonne queue MoltenVK

La queue de présentation est identifiée par sa famille et son index exacts.
Lorsque cette identité est connue, l’attente peut viser le travail de présentation
précédent sans vider également les transferts indépendants. Le repli sûr est conservé.

### 4. Lectures plus directes du cache JIT

Les petits objets compressés sont lus en une seule lecture positionnelle dans un
tampon de pile. Les plus gros évitent les déplacements répétés dans le fichier.
Les accès réussis ne refont plus de contrôle d’existence inutile ; les contrôles
de corruption et de taille restent actifs.

### 5. Libération correcte des paquets Vulkan

Un paquet créé avec `new` est désormais détruit avec `delete`, ce qui corrige
l’incompatibilité d’allocation détectée par ASan. L’ordre des soumissions et
les règles de synchronisation GPU sont conservés.

### 6. Réveil fiable des compilateurs en attente

La libération d’un ticket de compilation synchronise correctement la notification
avec l’attente du demandeur. Elle supprime une notification perdue qui pouvait
ajouter une attente inutile d’environ 20 ms, sans changer les limites de concurrence.

### 7. Réutilisation des shaders fragment équivalents

La clé du cache ignore certaines propriétés lorsque l’analyse démontre qu’elles
n’affectent pas le programme. Cela permet de réutiliser une compilation existante.
Les programmes ambigus gardent leur clé originale et le compilateur reçoit toujours
le programme complet.

### 8. Publication sûre des clés de shaders

Une nouvelle clé fragment est copiée sous le verrou d’écriture avant sa publication.
Les lecteurs concurrents ne voient plus une clé en cours de transformation.
Les recherches qui trouvent déjà leur entrée n’effectuent pas de copie supplémentaire.

### 9. Recherche indexée des textures compressées

Dans les blocs de plus de 16 sections, un index d’adresses évite de parcourir les
sections sans rapport. Les vérifications de format, dimensions, mipmaps et contenu
sont conservées, ainsi que l’ordre de sélection du premier résultat valide.

### 10. Réutilisation des viewport et scissor identiques

Les limites de vue et de découpage déjà actives ne sont plus renvoyées inutilement
à Vulkan lorsqu’elles sont strictement identiques. Les nouveaux enregistrements,
les changements de pipeline et les états inconnus invalident correctement ce cache.

### 11. Moins de réveils inutiles après une complétion

Une ancienne complétion ne réveille plus le worker si elle ne fait pas avancer
le travail terminé. Les drains explicites, fences, barrières et soumissions
conservent leurs règles.

### 12. Accès direct aux textures non compressées déjà présentes

La recherche exacte utilise également l’index dans les grands blocs. Un résultat
valide évite le parcours de sections étrangères et la construction d’une liste
de chevauchements. Les cas qui exigent un repli conservent le parcours historique.

### 13. Clés de framebuffer entièrement initialisées

Les 64 bits de la clé sont initialisés, y compris les 31 bits auparavant laissés
indéterminés. Des paramètres identiques produisent ainsi la même clé, ce qui évite
des différences artificielles lors des recherches dans le cache.

## MeloNX : 16 changements

### Mémoire et textures

Ce premier groupe correspond au lot moteur80, décrit avec ses preuves dans le
[rapport mémoire et textures](https://github.com/TarbleFR/RewindBox/blob/97365ce57f17499101e88d50019b6c63be554b83/docs/melonx-hogwarts-memory-2026-10-29.md).

### 1. Propriété des textures correctement conservée

La libération d’une texture dans un slot retire exactement le propriétaire concerné.
Elle ne supprime plus les appartenances à d’autres pools avec un seul décrément
de référence ; une libération répétée reste sans effet supplémentaire.

### 2. Expiration des anciennes textures de rendu

La condition du cache court est corrigée pour permettre l’expiration prévue des
textures devenues inutiles. Les références de cache ne sont pas ajoutées en double,
et la réutilisation d’une texture annule son expiration.

### 3. Moins de tableaux temporaires pour les ressources bindless

Les tableaux temporaires de textures et d’images sont réutilisés dans un stockage
borné, puis débarrassés de leurs références. Les commandes différées conservent
leur propre instantané, ce qui évite aussi de dépendre d’un tableau appelant réutilisé.

### 4. Réutilisation des ensembles de stockages Vulkan

Les ensembles conservent leur capacité au lieu d’être reconstruits inutilement.
Un changement limité au sampler ou à une vue du même stockage évite ce travail,
tout en conservant les mises à jour de descripteurs et les barrières nécessaires.

### Travail CPU du rendu

Ces changements du moteur81 sont détaillés dans le
[rapport sur les coûts CPU du rendu](https://github.com/TarbleFR/RewindBox/blob/97365ce57f17499101e88d50019b6c63be554b83/docs/melonx-fps-followup-2026-10-29.md).

### 5. Agrandissement moins coûteux du cache de pipelines

Les tableaux du cache grandissent par paliers géométriques. La table de recherche
s’adapte à son occupation, réutilise les hashes déjà calculés et nettoie les
références retirées, afin de limiter les copies et allocations lors des ajouts.

### 6. Moins de collisions entre les clés de pipelines

Le calcul du hash distingue désormais l’ordre des éléments. Les permutations qui
entraient systématiquement en collision peuvent être séparées, tout en conservant
la comparaison complète des clés et l’exclusion des éléments inactifs.

### 7. Recherche plus précise dans le cache bindless

Le hash prend en compte davantage de composantes de la clé, notamment le pool,
le type, la cible, la longueur et les informations de buffer. Cela réduit les
comparaisons inutiles sans changer les règles d’égalité ou de propriété.

### 8. Pas d’invalidation inutile pour un buffer inchangé

Réappliquer exactement le même état de buffer ne marque plus ses descripteurs
comme modifiés. Les acquisitions de ressources, recherches nécessaires, barrières
et invalidations dues à de vrais changements sont conservées.

### 9. Réutilisation locale des recherches de mémoire

Une région hôte et une région invitée récemment utilisées peuvent être retrouvées
directement sous le verrou existant. Ces références sont invalidées avant un
changement de topologie ; les recherches simples évitent aussi un tableau temporaire.

### 10. Parcours linéaire des chevauchements de textures

Pour les mappings contigus, ordonnés et bornés, deux curseurs remplacent le parcours
croisé des plages. Les mappings fragmentés ou hors de ce cadre conservent leur
chemin de repli et les erreurs prévues.

### Démarrage et gestion des erreurs

Ce dernier groupe appartient au moteur82. Ses preuves et les deux étapes de
validation figurent dans le
[rapport sur le démarrage MeloNX](https://github.com/TarbleFR/RewindBox/blob/97365ce57f17499101e88d50019b6c63be554b83/docs/melonx-startup-2026-10-29.md).

### 11. Préchauffage des pipelines du cache en arrière-plan

Le préchauffage initial facultatif utilise les workers existants, même avec les
shaders asynchrones en jeu désactivés. Il est séparé de la disponibilité du programme.
Les modules restent validés et les rendus réellement nécessaires gardent leurs
règles synchrones ; le nombre de workers est borné, mais pas la file d’attente.

### 12. Erreurs fatales des shaders conservées et signalées

La première erreur fatale de compilation en arrière-plan est retenue par le renderer
et remontée, même si le programme concerné n’est jamais dessiné. Le nettoyage attend
les tâches nécessaires encore actives avant de libérer leurs ressources.

### 13. Échecs du renderer transmis aux threads en attente

Les exceptions ne sont plus absorbées silencieusement. L’erreur originale est
publiée avant de réveiller les threads concernés ; une file partiellement consommée
après un échec n’est pas rejouée. L’invité s’arrête avant la destruction du renderer.

### 14. Fermeture complète des workers de traduction

La file de traduction des shaders est fermée et tous les workers effectivement
démarrés sont attendus, y compris après une erreur précoce ou un démarrage partiel.
Un échec de chargement ne laisse donc plus ces workers poursuivre leur activité.

### 15. Sortie propre lorsque le GPU ne démarre pas

L’attente de disponibilité du GPU dispose d’états terminaux d’échec et d’annulation.
Dans ces cas, les threads invités quittent l’attente sans exécuter le CPU invité.
Une initialisation encore active doit terminer son nettoyage avant la libération.

### 16. Un seul scan du firmware au lancement

Le contrôle préalable supprime un scan redondant avant la lecture de version,
qui effectue déjà une recherche fraîche. Le lancement passe de deux scans à un,
avec les mêmes comportements en cas de firmware absent, remplacé ou invalide.

## Résultats et limites

Le Core RPCS3 a réussi ses **24 modes ciblés sur Apple ARM64**, puis sa compilation
iPhone. MeloNX a produit ses bibliothèques iPhone et simulateur ; sa validation
corrigée a confirmé deux exécutions distinctes de homebrew non graphique sur simulateur.
Le premier smoke du moteur82 reste enregistré comme échoué : le test corrigé a
ensuite réussi sur les mêmes binaires, sans les recompiler.

**Aucun gain de FPS, de temps de lancement ou de RAM résidente n’est encore mesuré
sur l’iPhone avec ces nouveaux moteurs.** Les baisses d’allocations et de travail
observées dans les tests hôte ne se convertissent pas directement en FPS ou en
mémoire économisée pendant un jeu.

**Certains microcas sont plus lents.** L’index RPCS3 accélère les résultats dispersés
dans de grands blocs, mais ajoute du travail aux recherches infructueuses, à certains
premiers résultats et au recyclage. Dans les mesures Apple, une recherche exacte
sans résultat à 1 024 sections passe d’environ 2,55 à 3,11 microsecondes.
Côté MeloNX, certains cas courts d’allocation ont un temps CPU supérieur malgré
moins d’octets alloués, et un hash plus complet ajoute un coût au cas à une entrée.
La distribution réelle de ces opérations dans les jeux reste à mesurer.

**La correction du gel de God of War III n’est pas démontrée.** La sélection de
queue MoltenVK corrige une attente excessive identifiée ; elle n’établit pas la
cause du gel ultérieur. La disparition des artefacts d’armes de BO2 ou de torches
d’Assassin’s Creed reste également à vérifier sur l’iPhone.

L’interface et les réglages de l’application restent ceux de la 593. NeoSwap est
conservé. RPCS3 garde ABI30, ses 88 exports, les identités PPU/SPU et les formats de
cache ; MeloNX garde ABI2 et ses 47 exports. Aucun résultat de test hôte ou de
simulateur n’est présenté comme une validation de jeu sur l’appareil physique.
