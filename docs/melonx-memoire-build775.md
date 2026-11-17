# MeloNX après le build 775

## Ce que l’iPhone a enregistré

Hogwarts Legacy, session du 17 novembre 2026, 19 h 08 min 44 s à 19 h 10 min 55 s UTC, core `9546deb7`. Les cinq journaux sont recoupés par titre, PID et session. Les fichiers de performances, du core et de stderr couvrent aussi deux sessions de Super Smash Bros. Ultimate sur 767, une sur 771, et deux sessions antérieures de Hogwarts sur 771 et 773. Le journal de lancement remonte au build 606. La vidéo montre le jardin, sans identifiant permettant de synchroniser chaque image avec le build 775.

| Observation sur 775 | Interprétation |
|---|---|
| Empreinte au démarrage de 1 450 Mio. Pic relevé par le noyau de 4 622 Mio. À 19 h 09 min 52 s, empreinte de 4 679 022 312 octets, marge du processus de 2 300 299 544 octets et disponibilité globale de 4 %. | La pression globale peut être sévère avant que l’application épuise sa propre marge. |
| Au même instant, 772 Mio engagés par le GC environ. Le LOH représente 430 Mio, dont 151 Mio libres. | Le compactage peut rendre des pages au système. Les octets libres sont déjà inclus dans le LOH. |
| À la première alerte, échantillonnage du tas natif estimant 453 Mio encore vivants et 11 684 Mio alloués en 47 s. Quatre Gio offerts au système de mémoire invitée. À 92 s, le registre graphique indique 1 103 Mio et 191 Mio compressés. | Le premier chiffre est un stock échantillonné, le second un cumul. Le prêt indique une capacité mappée. Allocations Vulkan, registres Metal, pages compressées et empreinte iOS se recouvrent. Ces mesures ne donnent pas le volume exact des données de jeu résidentes. |
| Environ 844 Mio/s d’allocations managées sur les deux premières fenêtres, puis 28,0 Mio/s sur les dix fenêtres se terminant entre 46 et 102 s. Dans la fenêtre se terminant à 46 s, le suivi des textures compte 214 Mio et les mises à jour partielles des tableaux de textures 201 Mio. | Les dernières catégories sont des mesures inclusives sur le thread courant. Une synchronisation de texture peut avoir lieu dans une mise à jour de tableau. |
| Gen1 à 862,3 ms, avec 29,2 Mio promus. Six secondes plus tard, la politique du core déclenche une collecte complète après 897 ms sans présentation. La collecte suspend le moteur 1 914,8 ms et l’empreinte passe de 4 620 à 4 254 Mio. | Le chemin forcé est identifié. Les journaux ne donnent pas les piles d’allocation des objets promus par la Gen1, ni la fraction de sa pause due à la décompression. |
| À 19 h 10 min 43 s, 90 images en 5,015 s. Les descripteurs occupent 778 ms côté dessin et 303 ms côté calcul. Le GPU est occupé 18,9 ms par image, soit 34 % de la fenêtre. | Le travail du thread de rendu contribue aussi au temps d’image. Une attente de FIFO isolée ne mesure pas la saturation du GPU. |

Entre les relevés de 46 à 80 s inclus, les 706 intervalles de présentation consignés donnent 20,02 FPS, 1,05 FPS pour le 1 % low et 0,25 FPS pour le 0,1 % low. Calcul sur les durées arrondies du journal, en inversant la durée moyenne des 8 et de la seule image les plus lentes respectivement. Le maximum atteint 3 984 ms. Ce segment comprend du streaming et des gels. La session passe en arrière-plan après environ 131 s. L’arrêt du relevé par seconde à 80 s et la transition en arrière-plan ne prouvent pas une terminaison forcée.

## Changements du core

- `EmbeddedMemory.cs` — `EmbeddedHeapCompaction.OnPoll` et `Compact` vérifient la marge du processus avant de demander une collecte en plein jeu et à nouveau au dernier contrôle. Au-delà de 256 Mio, un trou de présentation ne suffit plus. Une valeur nulle conserve les gardes d’urgence antérieures. Le premier affichage et la pause effective disposent toujours de leurs propres règles. Compromis à vérifier sur l’iPhone : le compactage précédent de 154,8 ms avait aussi rendu 275 Mio pendant le chargement.
- `TextureBindingsArrayCache.cs` — `PrepareDelta`, `RecordDelta` et `DeltaUnchanged` réutilisent la référence de texture résolue quand elle désigne déjà l’entrée du pool. Une divergence matérialise une page de 256 références au maximum. Les alias de format, les valeurs nulles et les versions d’invalidation restent représentés exactement.
- `TextureBindingsArrayCache.FlushDeltaRun`, `ITextureArray.cs`, `ThreadedTextureArray.cs`, `ThreadedImageArray.cs` et `ThreadedArrayPool.cs` — le producteur fournit directement la plage modifiée. La file conserve un instantané privé jusqu’à sa consommation. Les backends qui consomment le tableau directement gardent leur chemin d’origine.
- `MemoryOwner.cs` — `ArrayPooling.BinarySearch` choisit le plus petit buffer compatible. `Get` alloue un nouveau buffer hors du verrou partagé en cas d’échec de la recherche. Le stockage emprunté conserve sa longueur logique et son propriétaire exclusif.

## Comparaison sur hôte

SDK .NET 10.0.100, Windows x64, configuration Release. Le témoin reprend les sources de l’artefact exact du build 775. Les essais de plages compilent les méthodes de production avec un consommateur de test qui relit les données après la remise à zéro du producteur. Les mesures ci-dessous sont des octets de références conservées ou des octets managés alloués par le thread du test.

| Cas | 775 | Candidat |
|---|---:|---:|
| État de 524 288 éléments avec résolution directe | 14 Mio | 10 Mio |
| Même tableau avec trois pages d’alias matérialisées | 14 680 064 octets | 10 508 288 octets |
| Trois emprunts simultanés sur un pool préparé à 128, 256 et 512 Kio | 524 464 octets | 96 octets |
| 16 384 envois de plages de 1 à 64 références, chemin multithread | 9 306 112 octets | 4 653 056 octets |
| Même charge, chemin direct | 9 306 464 octets | 9 306 464 octets |

Les contrôles couvrent les limites de page, les alias devenant nuls, les recréations du cache, les instantanés différés, les références libérées et 8 000 emprunts concurrents. Ces chiffres ne permettent pas de déduire un gain de FPS sur iPhone.

## Risques et vérification sur appareil

1. **Pression prolongée et pauses du GC.** Comparer à réglages identiques le lancement, l’entrée dans le jardin, dix minutes d’allers-retours intérieur/extérieur, puis une pause et une reprise. Relever par phase les octets alloués par seconde, le pic d’empreinte, le LOH libre après les collectes et les pauses. Vérifier en particulier que la marge du processus reste suffisante si les pages libres sont rendues plus tard.
2. **Coût du rendu et des transferts.** Comparer les temps de mise à jour des descripteurs, les présentations, les 1 % et 0,1 % low et les rotations de caméra. Les miroirs de buffers représentaient déjà 32,1 Mio, dont 24,7 Mio en grandes copies, sur un relevé du 775. La proportion réellement modifiée par buffer reste inconnue.
3. **Caches, audio et fermeture.** Les sept passages de la politique de buffers froids du 775 ont libéré zéro buffer. D’autres purges GPU ont effectivement rendu de la mémoire. Vérifier le rechargement des textures et le son avant de modifier les évictions. Le journal de lancement contient des échecs de fermeture sur 666 et 726. Une fermeture suivie d’un deuxième lancement sur le candidat reste nécessaire pour mesurer la restitution des ressources.
