# Switch 2 — régression de vitesse et import de dossiers sur l’IPA 786

L’essai du 18 novembre 2026 sur iPhone17,2 charge le moteur du run 44274723169 avec les correctifs 0001–0114. Les captures de la 785 remontent au moteur 44230830821. [Reçu 786](rewind786/delivery.json) · [Essai 785](s2arm-ipa785-device-2026-11-18.md)

| Relevé | IPA 785 | IPA 786 |
| --- | --- | --- |
| Temps des images relevé dans les signatures détaillées, p50 / p95 / p99 | 26,57 / 37,11 / 52,54 ms, images 3040–3437, 397 relevés utilisables | 27,37 / 45,31 / 57,05 ms aux images 1501–2100, 599 relevés. Après le passage de l’affichage à 30 Hz, 42,61 / 48,16 / 57,98 ms aux images 2107–2400, 294 relevés. |
| Plus gros blocage mesuré | 5 413 ms à l’image 2841, dont 3 993 ms de pipelines | 2 263 ms à l’image 1255, dont 2 020 ms pour cinq pipelines et trois bibliothèques Metal. Image 696 à 1 522 ms avec zéro nouveau shader ou pipeline. |
| Préchauffage | 3 589 pipelines repris de l’archive, 860 lignes inutilisables faute de traduction actuelle ou d’octets d’origine | 3 806 repris, 807 lignes pour 434 clés encore sans traduction actuelle ni octets d’origine. |
| Température | Départ en état `fair`, passage à `serious` à l’image 6041 | 21 relevés en état `fair` et 3 min 36 s de jeu. Aucun relevé en état nominal. |
| Son | Reprises de la file et trous répartis sur plusieurs fenêtres | 287,3 ms de trous cumulés sur quatre fenêtres, dont 287,2 ms au début. Aucun arrêt dans ces relevés. |
| Fermeture du jeu | Arrêt terminal. La tentative Switch suivante a rencontré le verrou du processus. | `sessionParked passed`, puis vue fermée. Environ 1,55 s du bouton Quitter à la fermeture. Le journal s’arrête sans relance. |

Les passages, la durée et la luminosité diffèrent. Les p50/p95/p99 du tableau utilisent l’intervalle entre les premiers ordres de rendu successifs. Les statistiques du moteur mesurent aussi l’affichage effectif. Dans deux fenêtres de 300 images après la bascule à l’image 2106, on compte 82 puis 96 images perdues à l’affichage et un p99 à 79,17 ms. Les fenêtres correspondantes donnent 23,9 et 22,5 FPS, avec un GPU à 33,38 et 35,03 ms en médiane. Le jeu revient à sa cadence de base puis redemande 30 FPS à l’image 4901. L’option de limite d’images RewindBox était désactivée. Le passage à 30 Hz agrandit l’intervalle entre deux occasions d’afficher une image tardive. Le temps GPU proprement dit reste à réduire séparément.

## Correctifs

- **Import de dossier.** Le dialogue des NUP s’ouvre à la sortie du sélecteur et affiche le nombre de fichiers lus pendant l’inventaire. Si une copie est nécessaire, le pourcentage vient des octets copiés, même pour des séries de petits fichiers. Un clonage APFS réussi évite le parcours de taille. Pendant ce clonage, l’indicateur tourne, la barre atteignant 100 % après l’installation du dossier. L’annulation laisse les dossiers terminés dans la bibliothèque et retire celui encore en préparation.
- **0115 – Affichage.** Le profil Mario Kart World garde la fréquence de base de l’affichage quand le jeu passe à 30 FPS en cours de jeu. Il garde la période choisie par le jeu. Comparer les images perdues et le p99 à l’affichage, puis les FPS et la chauffe sur les mêmes passages.
- **0116 – Relectures et diagnostic.** À l’image 696, 52 928 fautes ont lu le stockage et une texture creuse a demandé 8 216 tuiles en 65 lots. Trois inventaires de résidence ont aussi parcouru les objets de rendu. Un seul inventaire ordinaire peut maintenant démarrer sur la même image. Les relevés de panne restent immédiats. Comparer les inventaires évités et les pauses au passage de la même scène. Les tuiles utiles restent nécessaires au rendu.
- **0117 – Shaders.** Le préchargement conserve l’étage et le mode de profondeur que le jeu utilise au moment de la liaison. Un fichier absent à la première tentative autorise une nouvelle demande. Les traductions, clés et archives gardent leur format. Comparer les bibliothèques Metal compilées sur le fil d’envoi et les attentes de premier usage en rejouant le même départ de course.
- **Profilage.** La 786 a lancé trois relevés CPU lourds. Une suspension a duré 32,5 ms. Le profil Mario Kart World garde les mesures ordinaires de temps d’image et de mémoire, et les relevés lourds passent en mode diagnostic avec `S2A_RB_AUTO_PROBE=1`.

## Vérification en CI

Le moteur compile sur macOS 15 et 26. Aucun avertissement ne touche les 91 lignes ajoutées par ce lot. La signature du traducteur de shaders correspond à celle de la 786. Les tests d’import et l’analyse Dart réussissent, tout comme la compilation arm64 du pont et ses contrôles de session. [Moteur](https://github.com/TarbleFR/RewindBox/actions/runs/44301263731) · [Import](https://github.com/TarbleFR/RewindBox/actions/runs/44301481418) · [Pont](https://github.com/TarbleFR/RewindBox/actions/runs/44301481387)

## Restes à mesurer

Deux diagnostics de rendu restent visibles. L’image de taux d’ombrage est traitée à pleine cadence lorsque le moteur ne peut pas l’appliquer. Un attribut de sommet signé ou non signé est converti vers le type réellement demandé. Une amélioration de ces chemins exige une mesure GPU et une comparaison visuelle, notamment sur les palmiers.

La préparation de 23 281 434 350 octets a pris 87,2 s au premier lancement de la 786, dont 42,0 s de hachage. La nouvelle bibliothèque de préparation, producteur 44267909266 au lieu de 44174427912, change son empreinte de réutilisation. Le lot 0115–0117 conserve 44267909266. Vérifier que le journal de la prochaine installation indique `prepare reused` pour le même export. Le nettoyage de l’ancienne préparation a traité 205 930 entrées en 56,1 s après la mise en veille du jeu.

La 786 confirme 7 063 093 réutilisations de tables de limites sur 7 975 661 demandes observées. Le gain de cadence total reste distinct de ce compteur. La session contient une fenêtre de 10 s avec 1 751 Mo relus et plus de 100 000 lectures de pages. Éviter de réduire la réserve de textures ou d’augmenter le parallélisme tant que l’effet sur les relectures, le GPU et la chauffe est inconnu. Le groupe de travail reste arrêté dans le mode qui a permis la fermeture observée. Sa réactivation exige une reprise et une fermeture fiables.

Comparer deux passages identiques sur le même circuit avec l’appareil refroidi et le cache conservé. Suivre le p95/p99, le nombre d’images de plus de 100 ms par minute, les images perdues à l’affichage et la durée passée en état nominal. Confirmer l’import de Fire Emblem depuis le dossier parent et après annulation à mi-copie. Les journaux reçus renseignent une mise en veille et une fermeture de Mario Kart World, ainsi que le chemin de sauvegarde retenu. Il reste à essayer la relance et à vérifier une restauration de sauvegarde avec un changement de progression identifiable.
